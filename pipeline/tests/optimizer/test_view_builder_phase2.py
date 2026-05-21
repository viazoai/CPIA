"""Phase 2 view_builder + retrieve + backfill 변경 검증."""

from __future__ import annotations

from datetime import date

import pytest

from pipeline.agents.optimizer.view_builder import _wp_id_of


def test_wp_id_of_kebab_format():
    """_wp_id_of 가 kebab-case + lowercase 반환."""
    assert _wp_id_of("FAB-A02", "철근콘크리트공사", "남웅건설") == "fab-a02-철근콘크리트공사-남웅건설"
    assert _wp_id_of(None, "방수공사", "동성건업") == "unknown-방수공사-동성건업"
    assert _wp_id_of("CUB", "방수공사", None) == "cub-방수공사-unknown"


@pytest.mark.integration
async def test_quadrant_has_new_keys(pg_client):
    """C2 — quadrant dict 에 l7_5_activity / company / l6_main / workers + kebab wp_id."""
    from pipeline.agents.optimizer.view_builder import _build_productivity_views_v2

    result = await _build_productivity_views_v2(pg_client, "m15x-ph3-ibl", date(2025, 9, 25))
    assert result["quadrant"], "quadrant 비어 있음 — 9-25 데이터 부재?"
    for q in result["quadrant"]:
        assert "l7_5_activity" in q
        assert "company" in q
        assert "l6_main" in q
        assert "workers" in q
        assert isinstance(q["workers"], int)
        # wp_id kebab 형식 (정수 prefix WP- 아님)
        assert not q["wp_id"].startswith("WP-")
