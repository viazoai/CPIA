"""Tests for optimizer agent — spec §7 + §12.1.

4 unit:
1. test_optimize_skip_when_not_in_selection
2. test_optimize_cold_start_when_cases_less_than_3
3. test_optimize_source_does_not_call_retrieve  (결정 #8 + F5 source-level)
4. test_compute_recovery_distribution_deterministic
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline.agents.optimizer.agent import (
    OptimizerConfig,
    _compute_recovery_distribution,
    optimize,
)


def _make_cfg() -> OptimizerConfig:
    """단위 테스트용 OptimizerConfig — 실 endpoint/key 불필요."""
    return OptimizerConfig(
        azure_endpoint="https://stub",
        azure_api_key="stub",
        azure_api_version="2024-12-01-preview",
        llm_model="stub-llm",
        postgres_url="postgresql://stub",
        chroma_host="stub",
        chroma_port=0,
    )


def _forecast_row(
    *,
    company: str = "남웅건설",
    l6_main: str = "철근콘크리트공사",
    assessment: str = "이상",
    risk_level: str = "이상",
    main_unit: str | None = "m3",
    today_productivity: float = 0.45,
    today_conditions: str = "맑음,장비대기",
) -> dict:
    return {
        "company": company,
        "l6_main": l6_main,
        "assessment": assessment,
        "risk_level": risk_level,
        "main_unit": main_unit,
        "today_productivity": today_productivity,
        "today_conditions": today_conditions,
        "reasoning": "stub",
    }


def _case(date_iso: str, recovery_days: int | None) -> dict:
    """fetch_degradation_cases + fetch_recovery_trajectory 합쳐진 case dict."""
    return {
        "date": date_iso,
        "conditions": "맑음,장비대기",
        "productivity": 12.0,
        "assigned_workers": 88.0,
        "activities": ["기초공사 : 거푸집 공사"],
        "recovery": {
            "recovery_days": recovery_days,
            "trajectory": [
                {
                    "date": "2025-09-23",
                    "conditions": "맑음",
                    "productivity": 15.0,
                    "recovered": recovery_days is not None,
                }
            ],
        },
    }


# ---------------------------------------------------------------------------
# Test 1 — skip when not in selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_skip_when_not_in_selection():
    """spec §7: hil_2_selection 에 없는 (company, l6_main) 은 skip — advice row 0건."""
    forecast = [_forecast_row(company="남웅건설", l6_main="철근콘크리트공사")]
    hil_2_selection: list[str] = []  # 선택 0건 → skip
    pre_optimizer_cases: dict[str, list[dict]] = {
        "남웅건설|철근콘크리트공사": [
            _case("2025-09-22", 1),
            _case("2025-09-06", 1),
            _case("2025-09-15", None),
        ],
    }

    pg_mock = MagicMock()
    pg_mock.connect = AsyncMock(return_value=None)
    pg_mock.close = AsyncMock(return_value=None)
    pg_mock.insert_optimizer_advice = AsyncMock(return_value=None)

    with (
        patch("pipeline.agents.optimizer.agent.PGClient", return_value=pg_mock),
        patch("pipeline.agents.optimizer.agent.AzureOpenAI") as azure_cls,
    ):
        azure_cls.return_value = MagicMock()
        advice = await optimize(
            forecast=forecast,
            hil_2_selection=hil_2_selection,
            pre_optimizer_cases=pre_optimizer_cases,
            run_id=uuid.uuid4(),
            today=date(2025, 9, 25),
            cfg=_make_cfg(),
        )

    assert advice == []
    pg_mock.insert_optimizer_advice.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 2 — cold_start when cases < 3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_cold_start_when_cases_less_than_3():
    """옵션 B: cases=[] (cold_start) 이어도 LLM 호출 발생. _compose_cold_start_row bypass 제거.

    2026-05-22: cases < 3 분기 삭제 → 모든 그룹이 LLM 호출. degradation_cases=[] 를 그대로 LLM 에 전달.
    검증: LLM 호출 1회 + advice row 1건 + company/l6_main 보존.
    """
    forecast = [_forecast_row()]
    key = "남웅건설|철근콘크리트공사"
    hil_2_selection = [key]
    # 0 건 — cold_start 시나리오
    pre_optimizer_cases: dict[str, list[dict]] = {key: []}

    pg_mock = MagicMock()
    pg_mock.connect = AsyncMock(return_value=None)
    pg_mock.close = AsyncMock(return_value=None)
    pg_mock.insert_optimizer_advice = AsyncMock(return_value=None)

    llm_response = {
        "diagnosis": "이력 없음 — 마스터 baseline 기준 진단",
        "recommendations": [{"rank": 1, "text": "데이터 누적 후 재조회 권장"}],
        "recovery_distribution": {},
    }
    azure_mock = MagicMock()
    azure_mock.chat.completions.create = MagicMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content=__import__("json").dumps(llm_response)))]
        )
    )

    with (
        patch("pipeline.agents.optimizer.agent.PGClient", return_value=pg_mock),
        patch("pipeline.agents.optimizer.agent.AzureOpenAI", return_value=azure_mock),
    ):
        advice = await optimize(
            forecast=forecast,
            hil_2_selection=hil_2_selection,
            pre_optimizer_cases=pre_optimizer_cases,
            run_id=uuid.uuid4(),
            today=date(2025, 9, 25),
            cfg=_make_cfg(),
        )

    # 2026-05-27 Task 13: V10 2단계 + scenarios 병렬 → cold_start 이어도 LLM 3회 호출
    # (recs + scenarios + diag). cold case dispatch X — cases<3 도 V10 path 동일 실행.
    assert azure_mock.chat.completions.create.call_count == 3, (
        f"V10: recs + scenarios + diag 3회 호출 기대, got {azure_mock.chat.completions.create.call_count}"
    )

    # 옵션 B invariant: V10 recs 호출의 user payload 에 degradation_cases=[] 가 전달됐는지 검증.
    # recs payload 만 degradation_cases 키 보유 (scenarios·diag 도 동일하게 빈 array 전달).
    for call in azure_mock.chat.completions.create.call_args_list:
        messages_sent = call.kwargs.get("messages")
        user_msgs = [m for m in messages_sent if m["role"] == "user"]
        actual_user_msg = user_msgs[-1]
        payload = json.loads(actual_user_msg["content"])
        assert payload.get("degradation_cases") == [], (
            f"옵션 B: cases=[] 가 V10 LLM 호출에 그대로 전달돼야 함, got {payload.get('degradation_cases')!r}"
        )

    assert len(advice) == 1
    row = advice[0]
    assert row["company"] == "남웅건설"
    assert row["l6_main"] == "철근콘크리트공사"
    assert row["degradation_cases"] == []  # 빈 cases 그대로 보존
    # PG INSERT 보장
    pg_mock.insert_optimizer_advice.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 3 — source-level: agent.py 가 retrieve 호출 X
# ---------------------------------------------------------------------------


def test_optimize_source_does_not_call_retrieve():
    """결정 #8 + F5: agent.py optimize() 가 retrieve.fetch_degradation_cases / fetch_recovery_trajectory 호출 X.

    pytest-mock 의존성 회피 — source-level 검증 (inspect.getsource).
    pre_optimizer_cases (state 사전 영속) 만 사용 보장.
    """
    import inspect

    from pipeline.agents.optimizer import agent

    src = inspect.getsource(agent)
    assert "fetch_degradation_cases" not in src, (
        "agent.py 가 retrieve.fetch_degradation_cases 호출 X (pre_optimizer_cases 만 사용)"
    )
    assert "fetch_recovery_trajectory" not in src, "agent.py 가 retrieve.fetch_recovery_trajectory 호출 X"


# ---------------------------------------------------------------------------
# Test 4 — _compute_recovery_distribution deterministic
# ---------------------------------------------------------------------------


def test_compute_recovery_distribution_deterministic():
    """spec §7 + 결정 #20: Counter 기반 코드단 산출."""
    cases = [
        {"recovery": {"recovery_days": 1}},
        {"recovery": {"recovery_days": 1}},
        {"recovery": {"recovery_days": 2}},
        {"recovery": {"recovery_days": None}},
    ]
    dist = _compute_recovery_distribution(cases)
    assert dist == {"d+1": 2, "d+2": 1, "not_recovered": 1}
