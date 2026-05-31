from __future__ import annotations
from pipeline.agents.optimizer.view_builder import _row_productivity


def test_real_qty_drives_productivity():
    # master daily 10 qty / 2 workers = 5/인. 실적 6 qty / 2 workers = 3/인 → 60%.
    out = _row_productivity(
        today_qty=6.0, assigned_workers=2.0, daily_qty_master=10.0, daily_workers_master=2.0
    )
    assert round(out["perperson"], 2) == 3.0
    assert round(out["productivity"], 1) == 60.0


def test_zero_workers_safe():
    out = _row_productivity(0.0, 0.0, 10.0, 2.0)
    assert out["perperson"] == 0.0
    assert out["productivity"] == 0.0
