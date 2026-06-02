"""Task 13 — _process_one_v10_with_retry 의 retry 흐름 검증.

사용자 의도:
- Azure 일시 오류 시 in-line retry 3회 + exponential backoff.
- 3회 모두 실패 → failed_wps 에 append + None 반환 (cold case 절대 금지, 종합 retry batch 처리).

이 테스트는 mock azure client 로 Azure API 호출 횟수와 retry 분기를 결정론적으로 검증한다.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from pipeline.agents.optimizer.agent import (
    OptimizerConfig,
    _process_one_v10_with_retry,
)


@pytest.fixture
def cfg():
    return OptimizerConfig(
        azure_api_key="test",
        azure_api_version="2024-12-01-preview",
        azure_endpoint="https://test.openai.azure.com",
        llm_model="gpt-5.1-chat-ai-board-test",
        azure_timeout=30.0,
        azure_max_retries=0,
        postgres_url="postgresql://test",
        chroma_host="test",
        chroma_port=8000,
    )


@pytest.fixture
def sample_forecast_row():
    return {
        "company": "남웅건설",
        "l6_main": "철근콘크리트공사",
        "main_unit": "ea",
        "assessment": "주의",
        "risk_level": "이상",
        "today_productivity": 0.5,
        "today_conditions": "정상",
        "delay_days": 7,
        "point_in_time_delay_days": 5,
        "mh_gap": 12.3,
        "expected_completion": date(2025, 12, 30),
    }


def _mk_response(content_dict: dict) -> MagicMock:
    """Mock Azure response object — resp.choices[0].message.content = json string."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = json.dumps(content_dict, ensure_ascii=False)
    return resp


@pytest.mark.asyncio
async def test_retry_succeeds_on_third_attempt(cfg, sample_forecast_row):
    """첫 2회 APIError → 3회째 성공 → row 정상 반환, failed_wps 빈 상태."""
    call_count = {"recs": 0, "diag": 0, "scen": 0}

    def fake_chat_completions_create(*, model, messages, response_format):
        system = messages[0]["content"]
        # RECS_PROMPT_V10 식별: keyword + action + reason 3 필드 schema 언급
        if "keyword" in system and "action" in system and "reason" in system:
            call_count["recs"] += 1
            if call_count["recs"] <= 2:
                raise openai.APIError("transient", request=MagicMock(), body=None)
            return _mk_response(
                {"recommendations": [{"rank": 1, "keyword": "k", "action": "a", "reason": "r"}]}
            )
        # SCENARIOS_PROMPT_V10 식별: "공기 만회" or "시나리오" 키워드
        elif "공기 만회" in system or "시나리오" in system:
            call_count["scen"] += 1
            return _mk_response(
                {
                    "no_action": {
                        "expected_completion": "2025-12-30",
                        "recovery_days": 0,
                        "delta_days": 0,
                        "rationale": "test",
                    },
                    "optimistic": {
                        "expected_completion": "2025-12-25",
                        "recovery_days": 5,
                        "delta_days": -5,
                        "rationale": "test",
                    },
                    "base": {
                        "expected_completion": "2025-12-27",
                        "recovery_days": 3,
                        "delta_days": -3,
                        "rationale": "test",
                    },
                    "pessimistic": {
                        "expected_completion": "2025-12-29",
                        "recovery_days": 1,
                        "delta_days": -1,
                        "rationale": "test",
                    },
                }
            )
        else:  # DIAG_PROMPT_V10
            call_count["diag"] += 1
            return _mk_response({"diagnosis": "test diagnosis"})

    azure = MagicMock()
    azure.chat.completions.create.side_effect = fake_chat_completions_create
    sem = asyncio.Semaphore(1)
    failed_wps: list[dict] = []
    # B3 card streaming: 성공 row 는 _process_one_v10_with_retry 안에서 pg.insert_optimizer_advice 호출.
    pg = MagicMock()
    pg.insert_optimizer_advice = AsyncMock()

    # asyncio.sleep 우회 (exponential backoff 대기 제거) — async no-op
    async def _noop_sleep(_delay):
        return None

    with patch(
        "pipeline.agents.optimizer.agent.asyncio.sleep",
        new=_noop_sleep,
    ):
        out = await _process_one_v10_with_retry(
            sample_forecast_row,
            [],
            uuid.uuid4(),
            date(2025, 7, 1),
            cfg,
            azure,
            sem,
            failed_wps,
            pg,
            max_retries=3,
        )

    assert out is not None, f"성공 row 기대, failed_wps={failed_wps}"
    # per-task insert 가 호출됐는지 검증 (card streaming)
    pg.insert_optimizer_advice.assert_awaited_once()
    assert failed_wps == [], f"실패 wp 없어야 함, got {failed_wps}"
    # 첫 2회 실패 + 3회째 성공 = recs 총 3회 호출
    assert call_count["recs"] == 3, f"recs call_count={call_count['recs']}"
    # 3회째 attempt 에서 비로소 diag/scen 도 호출됨 (recs 가 먼저 raise 했으므로 1·2회는 diag/scen 호출 안 됨)
    # scen 은 recs 와 병렬이지만, recs 가 raise 한 attempt 의 scen 결과는 gather 가 예외로 묻혀 사용 안 됨.
    # diag 는 recs 완료 후 순차 호출 → 3회째 attempt 에서만 호출.
    assert call_count["diag"] == 1, f"diag call_count={call_count['diag']}"

    # row 구조 검증
    assert out["company"] == "남웅건설"
    assert out["diagnosis"] == "test diagnosis"
    assert len(out["recommendations"]) == 1
    assert out["recommendations"][0]["keyword"] == "k"
    assert "scenarios" in out


@pytest.mark.asyncio
async def test_retry_all_fail_appends_to_failed_wps(cfg, sample_forecast_row):
    """3회 모두 APIError → None 반환, failed_wps 에 append."""

    def always_fail(*args, **kwargs):
        raise openai.APIError("persistent", request=MagicMock(), body=None)

    azure = MagicMock()
    azure.chat.completions.create.side_effect = always_fail
    sem = asyncio.Semaphore(1)
    failed_wps: list[dict] = []
    pg = MagicMock()
    pg.insert_optimizer_advice = AsyncMock()

    async def _noop_sleep(_delay):
        return None

    with patch(
        "pipeline.agents.optimizer.agent.asyncio.sleep",
        new=_noop_sleep,
    ):
        out = await _process_one_v10_with_retry(
            sample_forecast_row,
            [],
            uuid.uuid4(),
            date(2025, 7, 1),
            cfg,
            azure,
            sem,
            failed_wps,
            pg,
            max_retries=3,
        )

    assert out is None, "3회 모두 실패 시 None 반환"
    # 실패 시 insert 호출 안 됨 (None 반환 전 insert 없음)
    pg.insert_optimizer_advice.assert_not_awaited()
    assert len(failed_wps) == 1, f"failed_wps 에 1건 append 기대, got {len(failed_wps)}"
    assert failed_wps[0]["company"] == "남웅건설"
    assert failed_wps[0]["l6_main"] == "철근콘크리트공사"
    assert "APIError" in failed_wps[0]["error"]
