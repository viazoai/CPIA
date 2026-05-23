"""anchor 정합 — 9-25 완공 row today_cum_qty ≈ plan_total_qty (F3 적분 1.0).
spec §10.
"""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pytest

SEED_PATH = Path(__file__).parents[3] / "scripts" / "seed_dummy_year.py"


def _load_seed():
    spec = importlib.util.spec_from_file_location("seed", SEED_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_completed_row_today_cum_qty_equals_plan_total():
    """plan_finish == 2025-09-25 인 row 가 9-25 에 적재될 때 today_cum_qty ≈ plan_total."""
    m = _load_seed()
    am_row = {
        "wbs_activity_id": "act-completed",
        "l5_disc": "건축",
        "l6_main": "콘크리트공사",
        "l7_sub": "RC공사",
        "l7_5_activity": "완공 작업",
        "sub_work_area": "",
        "company": "광건",
        "wa": "WA-end",
        "unit": "M3",
        "plan_total_qty": 1000.0,
        "plan_mh_rev2": 5000.0,
        "plan_start": date(2024, 4, 11),
        "plan_finish": date(2025, 9, 25),
    }
    rng = m._seeded_rng("anchor-test")
    row = m._build_mapper_row(date(2025, 9, 25), am_row, None, rng)
    assert row is not None
    # F3 cum_frac(1.0) = 1.0 (적분) → today_cum_qty = plan_total × 1.0 = 1000
    assert row["today_cum_qty"] == pytest.approx(1000.0, rel=1e-3)


def test_in_progress_row_at_anchor_partial_completion():
    """plan_finish == 2026-03-31 (anchor 이후) 인 row 가 9-25 에 partial 진행."""
    m = _load_seed()
    am_row = {
        "wbs_activity_id": "act-progress",
        "l5_disc": "전기",
        "l6_main": "전등설비공사",
        "l7_sub": "전등설비공사",
        "l7_5_activity": "진행 중 작업",
        "sub_work_area": "",
        "company": "태우",
        "wa": "WA-mid",
        "unit": "EA",
        "plan_total_qty": 1000.0,
        "plan_mh_rev2": 5000.0,
        "plan_start": date(2024, 4, 11),
        "plan_finish": date(2026, 3, 31),
    }
    rng = m._seeded_rng("anchor-test-2")
    row = m._build_mapper_row(date(2025, 9, 25), am_row, None, rng)
    # progress ≈ 0.745, plateau 구간 → cum_frac ≈ 0.696
    assert 0.60 * 1000.0 < row["today_cum_qty"] < 0.80 * 1000.0
