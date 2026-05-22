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
from pipeline.constants import WORK_HOURS_PER_DAY


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
    """A7: qty 기반 delay 산식 — 60% 진행 상태 → 잔여물량/페이스 → 양수 delay.

    plan 1/1 ~ 12/31 (365일), 오늘 9/15 (window=258일).
    actual_cum_qty=60 (plan_total=100) → remaining=40, pace=60/258=0.2326,
    rem_days=172 → expected=3/6, delay=(3/6-12/31).days=65 (양수, 지연).
    mh_gap 는 reference 컬럼 (산식 검증 보조).
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
        actual_cum_qty=60.0,
        plan_total_qty_main=100.0,
    )
    assert result["schedule_state"] == "on_schedule"
    assert result["plan_mh_per_day"] == pytest.approx(10.0, abs=0.1)
    assert result["mh_gap"] == pytest.approx(180.0, abs=1.0)  # reference 컬럼 유지
    assert isinstance(result["delay_days"], int)
    assert 50 <= result["delay_days"] <= 80, f"기댓값 ~65 (rem_days~172), got {result['delay_days']}"


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
    """A7: actual_cum_qty=90 (90% 완료) → 잔여 10/페이스 0.349 → rem_days=29 → delay=-78 (앞당김)."""
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
        actual_cum_mh=3000.0,
        actual_cum_qty=90.0,
        plan_total_qty_main=100.0,
    )
    assert -100 <= result["delay_days"] <= -5, (
        f"기댓값 ~-78 (rem_days~29, pace~0.349), got {result['delay_days']}"
    )
    assert result["mh_gap"] < 0  # reference 컬럼: mh 도 expected 초과


class _MockColl:
    def __init__(self, metadatas: list[dict]):
        self._metadatas = metadatas

    def get(self, where, include):
        return {"metadatas": self._metadatas}


def test_fetch_chroma_actual_with_data():
    # A8: 반환이 (actual_window_start, actual_cum_mh, actual_cum_qty) 3-tuple
    coll = _MockColl(
        [
            {"date": "2025-09-20", "assigned_workers": 100},
            {"date": "2025-09-21", "assigned_workers": 100},
            {"date": "2025-09-22", "assigned_workers": 100},
        ]
    )
    from pipeline.agents.forecaster.aggregate import fetch_chroma_actual

    ws, mh, qty = fetch_chroma_actual(coll, "X", "Y", date(2025, 9, 25), 100)
    assert ws == date(2025, 9, 20)
    assert mh == pytest.approx(4 * 100 * WORK_HOURS_PER_DAY)  # 4일 (20,21,22,25)
    assert qty == 0.0  # unit 미지정 → 정확히 0.0 (main_unit=None 이라 qty 집계 없음)


def test_fetch_chroma_actual_empty():
    # A8: 반환이 (actual_window_start, actual_cum_mh, actual_cum_qty) 3-tuple
    coll = _MockColl([])
    from pipeline.agents.forecaster.aggregate import fetch_chroma_actual

    ws, mh, qty = fetch_chroma_actual(coll, "X", "Y", date(2025, 9, 25), 100)
    assert ws is None
    assert mh == pytest.approx(800)  # 100 × 8 = 오늘 1일만
    assert qty == 0.0  # main_unit=None → today_qty_main 기본값 0.0


def test_compute_delay_zero_total_days():
    """A7: plan_start == plan_finish (1일 공정). qty 기반 산식 검증.

    actual_cum_qty=5 (plan=10), window=1일 → pace=5, rem_days=1 → delay=+1일 (지연).
    plan_mh_per_day 산식 (reference) 은 그대로 검증.
    """
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
        actual_cum_qty=5.0,
        plan_total_qty_main=10.0,
    )
    # reference 컬럼
    assert result["plan_mh_per_day"] == pytest.approx(100.0)
    # qty 산식: remaining=5, pace=5/1=5, rem_days=1 → delay=1
    assert result["delay_days"] == 1
    assert result["remaining_qty"] == pytest.approx(5.0)


def test_compute_delay_plan_mh_zero():
    """A7: plan_mh_sum=0 이어도 qty 산식 정상 작동. mh 는 reference only.

    actual_cum_qty=40 (plan=100), window=152일 → pace=0.263, rem_days=228 → delay=+15일 (지연).
    plan_mh_per_day=0 (mh_sum=0) 이어도 qty 기반 delay 는 None 이 아님.
    """
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
        actual_cum_qty=40.0,
        plan_total_qty_main=100.0,
    )
    assert result["plan_mh_per_day"] == pytest.approx(0.0)  # mh reference
    assert isinstance(result["delay_days"], int)
    assert 10 <= result["delay_days"] <= 25, f"기댓값 ~+15 (pace=0.263, rem~228), got {result['delay_days']}"


def test_compute_delay_no_qty_returns_none():
    """A7: plan_total_qty_main=None (기본값) → delay_days=None (산출 불가 fallback).

    qty 인자 없는 호출은 delay_days=None 반환을 보장해야 함 (downstream 이 None 체크 의존).
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
        # plan_total_qty_main 미전달 → None fallback
    )
    assert result["delay_days"] is None
    assert result["remaining_qty"] is None
    assert result["avg_pace_qty"] is None
    # mh reference 컬럼은 그대로
    assert result["mh_gap"] == pytest.approx(180.0, abs=1.0)
