"""Forecaster aggregate.py 단위 테스트.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §5
"""

from __future__ import annotations

from datetime import date

import pytest

from pipeline.agents.forecaster.aggregate import (
    aggregate_today_by_unit,
    compute_delay,
)


def test_aggregate_today_by_unit_single():
    activities = [
        {
            "unit": "m",
            "today_qty": 80,
            "company": "X",
            "l6_main": "Y",
            "assigned_workers": 100,
            "work_content": "test",
            "conditions": [],
            "l5_disc": "설비",
            "wa": "AC",
            "worker_source": "mh_prorated",
            "mapping_conf": 0.8,
        },
    ]
    result = aggregate_today_by_unit(activities)
    assert result == {"m": 80.0}


def test_aggregate_today_by_unit_multi_unit():
    activities = [
        {
            "unit": "m",
            "today_qty": 80,
            "company": "X",
            "l6_main": "Y",
            "assigned_workers": 100,
            "work_content": "a",
            "conditions": [],
            "l5_disc": "설비",
            "wa": "AC",
            "worker_source": "mh_prorated",
            "mapping_conf": 0.8,
        },
        {
            "unit": "ea",
            "today_qty": 12,
            "company": "X",
            "l6_main": "Y",
            "assigned_workers": 100,
            "work_content": "b",
            "conditions": [],
            "l5_disc": "설비",
            "wa": "AC",
            "worker_source": "mh_prorated",
            "mapping_conf": 0.8,
        },
    ]
    result = aggregate_today_by_unit(activities)
    assert result == {"m": 80.0, "ea": 12.0}


def test_aggregate_today_by_unit_same_unit_sum():
    """같은 unit 의 여러 Activity → Σ."""
    activities = [
        {
            "unit": "m",
            "today_qty": 50,
            "company": "X",
            "l6_main": "Y",
            "assigned_workers": 100,
            "work_content": "a",
            "conditions": [],
            "l5_disc": "설비",
            "wa": "AC",
            "worker_source": "mh_prorated",
            "mapping_conf": 0.8,
        },
        {
            "unit": "m",
            "today_qty": 30,
            "company": "X",
            "l6_main": "Y",
            "assigned_workers": 100,
            "work_content": "b",
            "conditions": [],
            "l5_disc": "설비",
            "wa": "AC",
            "worker_source": "mh_prorated",
            "mapping_conf": 0.8,
        },
    ]
    result = aggregate_today_by_unit(activities)
    assert result == {"m": 80.0}


def test_compute_delay_on_schedule_behind():
    """plan 1/1 ~ 12/31 (365일), mh_sum=3650 (10 mh/day).
    오늘 9/15 (258일째). window 0/1~9/15 (258일). expected=2580. actual=2400.
    → mh_gap=180. delay_days=18.

    reviewer #12 정정: 모든 fixture Activity 에 l5_disc 포함 (atomizer schema 정합).
    아래 test_compute_delay 시리즈는 plan dict 만 받으므로 l5_disc 무관.
    """
    plan = {
        "plan_start": date(2025, 1, 1),
        "plan_finish": date(2025, 12, 31),
        "plan_mh_sum": 3650,
        "plan_total_qty_by_unit": {"m": 100.0},
    }
    result = compute_delay(
        plan=plan,
        today=date(2025, 9, 15),
        actual_window_start=date(2025, 1, 1),
        actual_cum_mh=2400.0,
    )
    assert result["schedule_state"] == "on_schedule"
    assert result["plan_mh_per_day"] == pytest.approx(10.0, abs=0.1)
    assert result["mh_gap"] == pytest.approx(180.0, abs=1.0)
    assert result["delay_days"] == pytest.approx(18.0, abs=0.5)


def test_compute_delay_early_before_start():
    """today 가 plan_start 전 → schedule_state = "early"."""
    plan = {
        "plan_start": date(2025, 12, 1),
        "plan_finish": date(2026, 2, 28),
        "plan_mh_sum": 900,
        "plan_total_qty_by_unit": {"m": 100.0},
    }
    result = compute_delay(
        plan=plan,
        today=date(2025, 11, 15),
        actual_window_start=date(2025, 11, 15),
        actual_cum_mh=0.0,
    )
    assert result["schedule_state"] == "early"


def test_compute_delay_post_due():
    """today 가 plan_finish 후 → schedule_state = "post_due"."""
    plan = {
        "plan_start": date(2024, 1, 1),
        "plan_finish": date(2024, 6, 30),
        "plan_mh_sum": 100,
        "plan_total_qty_by_unit": {"m": 100.0},
    }
    result = compute_delay(
        plan=plan,
        today=date(2025, 9, 25),
        actual_window_start=date(2025, 9, 25),
        actual_cum_mh=50.0,
    )
    assert result["schedule_state"] == "post_due"


def test_compute_delay_unknown_no_plan():
    """plan=None → schedule_state="unknown", delay_days=None."""
    result = compute_delay(
        plan=None,
        today=date(2025, 9, 25),
        actual_window_start=None,
        actual_cum_mh=100.0,
    )
    assert result["schedule_state"] == "unknown"
    assert result["delay_days"] is None
    assert result["plan_mh_per_day"] is None


def test_compute_delay_ahead():
    """actual > expected → delay_days < 0."""
    plan = {
        "plan_start": date(2025, 1, 1),
        "plan_finish": date(2025, 12, 31),
        "plan_mh_sum": 3650,
        "plan_total_qty_by_unit": {"m": 100.0},
    }
    result = compute_delay(
        plan=plan,
        today=date(2025, 9, 15),
        actual_window_start=date(2025, 1, 1),
        actual_cum_mh=3000.0,  # expected=2580 보다 많이
    )
    assert result["delay_days"] < 0
    assert result["mh_gap"] < 0


class _MockColl:
    def __init__(self, metadatas: list[dict]):
        self._metadatas = metadatas

    def get(self, where, include):
        return {"metadatas": self._metadatas}


def test_fetch_chroma_actual_with_data():
    coll = _MockColl(
        [
            {"date": "2025-09-20", "assigned_workers": 100},
            {"date": "2025-09-21", "assigned_workers": 100},
            {"date": "2025-09-22", "assigned_workers": 100},
        ]
    )
    from pipeline.agents.forecaster.aggregate import fetch_chroma_actual

    ws, mh = fetch_chroma_actual(coll, "X", "Y", date(2025, 9, 25), 100)
    assert ws == date(2025, 9, 20)
    assert mh == pytest.approx(4 * 100 * 8)  # 4일 (20,21,22,25)


def test_fetch_chroma_actual_empty():
    coll = _MockColl([])
    from pipeline.agents.forecaster.aggregate import fetch_chroma_actual

    ws, mh = fetch_chroma_actual(coll, "X", "Y", date(2025, 9, 25), 100)
    assert ws is None
    assert mh == pytest.approx(800)  # 100 × 8 = 오늘 1일만


def test_compute_delay_zero_total_days():
    """plan_start == plan_finish (1일 공정) 의 division by zero 방어 (reviewer #11)."""
    plan = {
        "plan_start": date(2025, 9, 25),
        "plan_finish": date(2025, 9, 25),
        "plan_mh_sum": 100,
        "plan_total_qty_by_unit": {"m": 10.0},
    }
    result = compute_delay(
        plan=plan,
        today=date(2025, 9, 25),
        actual_window_start=date(2025, 9, 25),
        actual_cum_mh=80.0,
    )
    # total_days=1, plan_mh_per_day=100, window=1, expected=100, actual=80, gap=20, delay=0.2
    assert result["plan_mh_per_day"] == pytest.approx(100.0)
    assert result["delay_days"] == pytest.approx(0.2, abs=0.05)


def test_compute_delay_plan_mh_zero():
    """plan_mh_sum=0 → division by zero 방어 (delay_days=0)."""
    plan = {
        "plan_start": date(2025, 1, 1),
        "plan_finish": date(2025, 12, 31),
        "plan_mh_sum": 0,
        "plan_total_qty_by_unit": {"m": 10.0},
    }
    result = compute_delay(
        plan=plan,
        today=date(2025, 6, 1),
        actual_window_start=date(2025, 1, 1),
        actual_cum_mh=0.0,
    )
    assert result["delay_days"] == pytest.approx(0.0)
