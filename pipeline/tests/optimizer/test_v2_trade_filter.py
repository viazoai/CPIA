"""Task 17 — _build_productivity_views_v2 SQL 에 trade IN ('건축','토목') 안전망."""

from __future__ import annotations

import inspect

from pipeline.agents.optimizer.view_builder import _build_productivity_views_v2


def test_v2_sql_has_trade_filter():
    """v2 SQL WHERE 절에 trade IN ('건축', '토목') 명시."""
    source = inspect.getsource(_build_productivity_views_v2)
    assert "ma.trade IN" in source or "trade IN" in source, "trade IN 필터 부재"
    assert "'건축'" in source
    assert "'토목'" in source
