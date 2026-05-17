"""Tests for optimizer agent — spec §7 + §12.1.

4 unit:
1. test_optimize_skip_when_not_in_selection
2. test_optimize_cold_start_when_cases_less_than_3
3. test_optimize_source_does_not_call_retrieve  (결정 #8 + F5 source-level)
4. test_compute_recovery_distribution_deterministic
"""

from __future__ import annotations

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
    """spec §7: cases length < 3 → diagnosis='cold_start', LLM 호출 X.

    Azure chat.completions.create 가 호출되지 않음을 검증.
    """
    forecast = [_forecast_row()]
    key = "남웅건설|철근콘크리트공사"
    hil_2_selection = [key]
    # 2 건만 — < 3 threshold
    pre_optimizer_cases = {key: [_case("2025-09-22", 1), _case("2025-09-06", 1)]}

    pg_mock = MagicMock()
    pg_mock.connect = AsyncMock(return_value=None)
    pg_mock.close = AsyncMock(return_value=None)
    pg_mock.insert_optimizer_advice = AsyncMock(return_value=None)

    azure_mock = MagicMock()
    # LLM 호출 시 즉시 fail 하도록 — 호출되면 테스트 fail
    azure_mock.chat.completions.create = MagicMock(
        side_effect=AssertionError("cold_start path 에서 LLM 호출 발생")
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

    assert len(advice) == 1
    row = advice[0]
    assert row["diagnosis"] == "cold_start"
    assert row["company"] == "남웅건설"
    assert row["l6_main"] == "철근콘크리트공사"
    assert row["recommendations"] == []
    # cold_start row 도 PG INSERT 보장 (cold_start signal 보존)
    pg_mock.insert_optimizer_advice.assert_awaited_once()
    # LLM 호출 X
    azure_mock.chat.completions.create.assert_not_called()


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
