"""Forecaster aggregate — 집계 + delay 계산. 순수 함수 (Chroma/PG 의존성 X).

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §5
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from .constants import WORK_HOURS_PER_DAY


def aggregate_today_by_unit(activities: list[dict]) -> dict[str, float]:
    """같은 (company, l6_main) 그룹 안의 Activity 들의 today_qty 를 unit 별 Σ."""
    by_unit: dict[str, float] = {}
    for a in activities:
        u = a["unit"]
        by_unit[u] = by_unit.get(u, 0.0) + a["today_qty"]
    return by_unit


def compute_delay(
    plan: Optional[dict],
    today: date,
    actual_window_start: Optional[date],
    actual_cum_mh: float,
) -> dict[str, Any]:
    """누적 mh window 비교 — 사용자 개념. plan 미등록 시 unknown.

    plan_mh_per_day  = plan_mh_sum / 공정_기간_일수
    expected_in_w    = window_days × plan_mh_per_day
    mh_gap           = expected - actual           (양수 = 부족)
    delay_days       = mh_gap / plan_mh_per_day

    schedule_state:
      plan 없음            → "unknown"
      today < plan_start   → "early"
      plan_start ≤ today ≤ plan_finish → "on_schedule"
      today > plan_finish  → "post_due"
    """
    if plan is None or plan.get("plan_start") is None or plan.get("plan_finish") is None:
        return {
            "plan_mh_per_day": None,
            "schedule_state": "unknown",
            "window_start": None,
            "window_days": 0,
            "expected_in_window_mh": None,
            "actual_in_window_mh": actual_cum_mh,
            "mh_gap": None,
            "delay_days": None,
        }

    plan_start = plan["plan_start"]
    plan_finish = plan["plan_finish"]
    plan_mh_sum = plan["plan_mh_sum"]

    total_days = (plan_finish - plan_start).days + 1
    plan_mh_per_day = plan_mh_sum / total_days if total_days > 0 else 0.0

    if today < plan_start:
        schedule_state = "early"
    elif today > plan_finish:
        schedule_state = "post_due"
    else:
        schedule_state = "on_schedule"

    ws = actual_window_start or today
    window_days = max(1, (today - ws).days + 1)
    expected_in_w = window_days * plan_mh_per_day
    mh_gap = expected_in_w - actual_cum_mh
    delay_days = mh_gap / plan_mh_per_day if plan_mh_per_day > 0 else 0.0

    return {
        "plan_mh_per_day": plan_mh_per_day,
        "schedule_state": schedule_state,
        "window_start": ws,
        "window_days": window_days,
        "expected_in_window_mh": expected_in_w,
        "actual_in_window_mh": actual_cum_mh,
        "mh_gap": mh_gap,
        "delay_days": delay_days,
    }


def fetch_chroma_actual(
    coll,
    company: str,
    l6_main: str,
    today: date,
    today_assigned_workers: float,
) -> tuple[Optional[date], float]:
    """Chroma daily_activities 에서 (company, l6_main) date 별 unique workers 추출.

    Spec §5.4 정합 — reviewer #5 정정:
    return: (actual_window_start, actual_cum_mh)
      Chroma 에 과거 row 없음 (오늘만)  → (None, today_workers × 8)
      Chroma 에 과거 row 있음           → (min(Chroma date), Σ unique date workers × 8h)
    """
    result = coll.get(
        where={"$and": [{"company": company}, {"l6_main": l6_main}]},
        include=["metadatas"],
    )
    date_to_workers: dict[str, float] = {}
    for m in result.get("metadatas") or []:
        d = m["date"]
        if d == today.isoformat():
            continue  # 오늘 자기자신 제외
        date_to_workers[d] = float(m["assigned_workers"])

    # Chroma 에 과거 row 가 하나도 없음 → 오늘만 카운트, window_start = None
    if not date_to_workers:
        return None, today_assigned_workers * WORK_HOURS_PER_DAY

    # 오늘 강제 추가 후 누적
    date_to_workers[today.isoformat()] = today_assigned_workers
    window_start = date.fromisoformat(min(date_to_workers.keys()))
    actual_cum_mh = sum(w * WORK_HOURS_PER_DAY for w in date_to_workers.values())
    return window_start, actual_cum_mh
