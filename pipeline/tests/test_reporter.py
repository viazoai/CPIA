"""Reporter unit + 통합 테스트.

Spec: docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.3

3 unit:
  1. test_reporter_mapped_empty_fallback — mapped empty → 짧은 fallback MD
  2. test_reporter_llm_mock_full_flow    — Azure mock 종합 MD 산출 + summary
  3. test_reporter_empty_optimizer_advice_skips_3bu — _build_llm_input 검증
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def reporter_cfg():
    from pipeline.agents.reporter import ReporterConfig

    return ReporterConfig(
        azure_endpoint="https://fake.openai.azure.com/",
        azure_api_key="fake_key",
        azure_api_version="2024-12-01-preview",
        llm_model="gpt-5.1-chat-ai-board-test",
        postgres_url=os.environ.get("POSTGRES_URL", "postgresql://fake"),
    )


@pytest.mark.asyncio
async def test_reporter_mapped_empty_fallback(reporter_cfg) -> None:
    """mapped empty → 짧은 fallback MD + PG INSERT skip + summary={}."""
    from pipeline.agents.reporter import report

    run_id = uuid.uuid4()
    today = date(2025, 9, 27)
    md, summary = await report(
        mapped=[],
        forecast_rows=[],
        optimizer_advice=[],
        run_id=run_id,
        today=today,
        cfg=reporter_cfg,
    )
    assert "보고서 생성 실패" in md
    assert "매핑 데이터 없음" in md
    assert summary == {}


@pytest.mark.asyncio
async def test_reporter_llm_mock_full_flow(reporter_cfg) -> None:
    """Azure LLM mock + Mapper+Forecaster+Optimizer 모두 있는 경우 종합 MD 산출."""
    from pipeline.agents.reporter import report

    fixture_mapped = [
        {
            "company": "남웅건설",
            "trade": "철근콘크리트공사",
            "l6_main": "철근콘크리트공사",
            "unit": "m3",
            "today_qty": 14.0,
            "assigned_workers": 31.0,
            "work_content": "1F 벽체 콘크리트 타설",
        }
    ]
    fixture_forecast = [
        {
            "company": "남웅건설",
            "l6_main": "철근콘크리트공사",
            "today_productivity": 0.452,
            "assessment": "이상",
            "risk_level": "이상",
            "reasoning": "유사 5건 평균 0.78 m3/인 대비 -42%.",
        }
    ]
    fixture_advice = [
        {
            "company": "남웅건설",
            "l6_main": "철근콘크리트공사",
            "forecast_assessment": "이상",
            "diagnosis": "타워크레인 스케줄 충돌.",
            "recommendations": [{"rank": 1, "text": "타워크레인 스케줄 확인"}],
            "recovery_distribution": {"d+1": 2, "not_recovered": 1},
        }
    ]

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = (
        "# 2025-09-27 작업일보 종합 보고서\n\n"
        "## 1부 작업 통합\n남웅건설 31.0 인원 14.0 m3\n\n"
        "## 2부 생산성 진단\n남웅건설 / 철근콘크리트공사 — risk_level: 이상\n\n"
        "## 3부 PM 선택 공종 권고\n타워크레인 스케줄 확인"
    )

    with (
        patch("pipeline.agents.reporter.AzureOpenAI") as mock_cls,
        patch("pipeline.agents.reporter.PGClient") as mock_pg_cls,
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_cls.return_value = mock_client
        # PG INSERT mock — 실 호출 안 함
        mock_pg = MagicMock()

        async def _connect():
            return None

        async def _close():
            return None

        async def _insert_daily_report(**_kwargs):
            return None

        mock_pg.connect = _connect
        mock_pg.close = _close
        mock_pg.insert_daily_report = _insert_daily_report
        mock_pg_cls.return_value = mock_pg

        run_id = uuid.uuid4()
        today = date(2025, 9, 27)
        md, summary = await report(
            mapped=fixture_mapped,
            forecast_rows=fixture_forecast,
            optimizer_advice=fixture_advice,
            run_id=run_id,
            today=today,
            cfg=reporter_cfg,
        )

    assert "2025-09-27" in md
    assert "1부" in md and "2부" in md and "3부" in md
    assert summary["total_workers"] == 31.0
    assert summary["risk_counts"]["이상"] == 1
    assert summary["advice_count"] == 1


@pytest.mark.asyncio
async def test_reporter_empty_optimizer_advice_skips_3bu(reporter_cfg) -> None:
    """optimizer_advice=[] → _build_llm_input 의 optimizer_advice 가 빈 list + summary.advice_count=0."""
    from pipeline.agents.reporter import _build_llm_input

    fixture_mapped = [
        {
            "company": "남웅건설",
            "trade": "철근콘크리트공사",
            "l6_main": "철근콘크리트공사",
            "unit": "m3",
            "today_qty": 14.0,
            "assigned_workers": 31.0,
            "work_content": "타설",
        }
    ]
    fixture_forecast = [
        {
            "company": "남웅건설",
            "l6_main": "철근콘크리트공사",
            "today_productivity": 0.45,
            "assessment": "정상",
            "risk_level": "정상",
            "reasoning": "정상 범위.",
        }
    ]
    llm_input = _build_llm_input(
        mapped=fixture_mapped,
        forecast_rows=fixture_forecast,
        optimizer_advice=[],
        today=date(2025, 9, 27),
    )
    assert llm_input["optimizer_advice"] == []
    assert llm_input["date"] == "2025-09-27"
    assert len(llm_input["activities"]) == 1
    assert llm_input["activities"][0]["company"] == "남웅건설"
