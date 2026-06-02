"""B2.5 (Cluster C6): wp_summary start_date/end_date = 실 plan 기간 (placeholder 아님).

순수 helper _wp_summary_dates 단위 검증 — plan_start/plan_finish None 가드 포함.
실 PG 통합 검증은 scripts/_rebuild_views.py 경로.
"""

from __future__ import annotations

from datetime import date

from pipeline.agents.optimizer.view_builder import _wp_summary_dates


def test_wp_summary_dates_uses_real_plan_period():
    today = date(2025, 9, 25)
    start, end = _wp_summary_dates({"plan_start": date(2025, 9, 1), "plan_finish": date(2025, 10, 31)}, today)
    assert start == "2025-09-01"
    assert end == "2025-10-31"
    assert end != str(today)


def test_wp_summary_dates_none_falls_back_to_today():
    today = date(2025, 9, 25)
    start, end = _wp_summary_dates({"plan_start": None, "plan_finish": None}, today)
    assert start == "2025-09-25"
    assert end == "2025-09-25"


def test_wp_summary_dates_missing_key_falls_back():
    today = date(2025, 9, 25)
    start, end = _wp_summary_dates({}, today)
    assert start == "2025-09-25"
    assert end == "2025-09-25"
