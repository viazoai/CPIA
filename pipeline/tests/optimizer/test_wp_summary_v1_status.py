"""Task 14 — _build_wp_summary 의 status 가 forecasts.risk_level 기반."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from pipeline.agents.optimizer.view_builder import _build_wp_summary


@pytest.mark.asyncio
async def test_wp_summary_status_from_risk_level():
    """forecasts.risk_level=이상 → status='risk', =주의 → 'caution', =정상 → 'normal'."""
    mock_pg = AsyncMock()
    mock_pg.fetch_all.return_value = [
        {"company": "co1", "l6_main": "wp1", "risk_level": "이상"},
        {"company": "co2", "l6_main": "wp2", "risk_level": "주의"},
        {"company": "co3", "l6_main": "wp3", "risk_level": "정상"},
    ]

    quadrant = [
        {"company": "co1", "l6_main": "wp1", "productivity": 100},  # CPI 100 인데 risk_level=이상
        {"company": "co2", "l6_main": "wp2", "productivity": 50},
        {"company": "co3", "l6_main": "wp3", "productivity": 30},  # CPI 30 인데 risk_level=정상
    ]
    out = await _build_wp_summary(mock_pg, "site1", date(2025, 7, 1), {}, quadrant)

    assert out[0]["status"] == "risk", "risk_level=이상 → status=risk (CPI 무시)"
    assert out[1]["status"] == "caution"
    assert out[2]["status"] == "normal", "risk_level=정상 → status=normal (CPI 무시)"


@pytest.mark.asyncio
async def test_wp_summary_missing_risk_level_defaults_to_normal():
    """forecasts row 없음 (None) → status='normal' fallback."""
    mock_pg = AsyncMock()
    mock_pg.fetch_all.return_value = []  # forecasts 행 없음

    quadrant = [{"company": "co_unknown", "l6_main": "wp_unknown", "productivity": 50}]
    out = await _build_wp_summary(mock_pg, "site1", date(2025, 7, 1), {}, quadrant)

    assert out[0]["status"] == "normal"  # _risk_level_to_status(None) = "normal"


@pytest.mark.asyncio
async def test_wp_summary_preserves_other_fields():
    """quadrant_jsonb 의 다른 필드 (productivity, impact 등) 그대로 보존."""
    mock_pg = AsyncMock()
    mock_pg.fetch_all.return_value = [{"company": "co", "l6_main": "wp", "risk_level": "주의"}]
    quadrant = [
        {
            "company": "co",
            "l6_main": "wp",
            "productivity": 75,
            "impact": 50,
            "wp_id": "wp-001",
            "wp_name": "철근콘크리트공사",
        }
    ]
    out = await _build_wp_summary(mock_pg, "site1", date(2025, 7, 1), {}, quadrant)

    assert out[0]["productivity"] == 75  # 보존
    assert out[0]["impact"] == 50  # 보존
    assert out[0]["wp_name"] == "철근콘크리트공사"  # 보존
    assert out[0]["baseline"] == 90  # 신규 필드
    assert out[0]["status"] == "caution"  # risk_level 기반
