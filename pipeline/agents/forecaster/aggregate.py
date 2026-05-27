"""Forecaster aggregate — 집계 + delay 계산. 순수 함수 (Chroma/PG 의존성 X).

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §5
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from .constants import WORK_HOURS_PER_DAY


async def fetch_pg_actual_cum_qty(
    pg,
    company: str,
    l6_main: str,
    today: date,
    main_unit: Optional[str],
) -> float:
    """PG mapper_activities 에서 (company, l6_main, main_unit) 의 today 이전 누적 today_qty 합.

    2026-05-22: Chroma 는 mapper 의 일부만 backfill 되어 있어 actual_cum_qty 산출에 부적합.
    PG mapper_activities 가 source of truth. 시연 환경 (mock=false) 만 합산.
    """
    if not main_unit:
        return 0.0
    rows = await pg.fetch_all(
        """
        SELECT COALESCE(SUM(ma.today_qty), 0)::float AS s
        FROM mapper_activities ma
        WHERE ma.company = $1 AND ma.l6_main = $2 AND ma.unit = $3
          AND ma.report_date < $4 AND ma.is_mock = false
        """,
        company,
        l6_main,
        main_unit,
        today,
    )
    return float(rows[0]["s"]) if rows else 0.0


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
    *,
    actual_cum_qty: float = 0.0,
    plan_total_qty_main: Optional[float] = None,
    today_qty_main: float = 0.0,
) -> dict[str, Any]:
    """qty 기반 delay 산식 (2026-05-22 fix).

    이전: mh-window deficit / plan_mh_per_day → 양 충족인데도 mh 부족이면 큰 delay.
    이제: 잔여 물량 / 페이스 → expected_completion → delay (expected − plan_finish).

    핵심:
      remaining_qty   = max(0, plan_total_qty_main − actual_cum_qty)
      avg_pace_qty    = actual_cum_qty / window_days   (≤0 fallback = today_qty_main)
      remaining_days  = remaining_qty / pace
      expected_completion = today + remaining_days
      delay_days      = (expected_completion − plan_finish).days
                        (양수 = 지연, 음수 = 앞당김, 0 = 일정 충족)

    부수 (mh) 컬럼 (reference only — delay 산출 사용 X, PG schema 영향 회피):
      - plan_mh_per_day        plan_mh_sum / total_days (기준 일 평균 인시)
      - expected_in_window_mh  plan_mh_per_day × window_days (window 누적 기준)
      - actual_in_window_mh    actual_cum_mh (Chroma window 누적 실 인시)
      - mh_gap                 expected_in_window_mh − actual_in_window_mh (참고용)
      위 4값은 forecast row jsonb 에 박혀 UI 미사용. 향후 mh 기반 KPI 위한 잠재 자산.

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
            "expected_completion": None,
            "remaining_qty": None,
            "avg_pace_qty": None,
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
    mh_gap = expected_in_w - actual_cum_mh  # reference only

    # qty 기반 delay 산식
    if plan_total_qty_main is None or plan_total_qty_main <= 0:
        # plan qty 없으면 delay 산출 불가 — None
        delay_days = None
        expected_completion = None
        remaining_qty = None
        avg_pace_qty = None
    else:
        remaining_qty = max(0.0, plan_total_qty_main - actual_cum_qty)
        avg_pace_qty = actual_cum_qty / window_days if window_days > 0 else 0.0
        # 2026-05-27 Task 4: plan_per_day_qty 정의 + pace floor — over-pessimistic 방지
        # (spec §4.2.3). avg_pace_qty=0 인 케이스에서 today_qty_main 만 쓰면 오늘 값이
        # 비현실적으로 작을 때 pace 가 폭락해 delay 가 300~800일 까지 튐. floor 로
        # 일평균 계획의 30% 를 minimum 보장.
        plan_per_day_qty = plan_total_qty_main / total_days if total_days > 0 else 0.0
        if avg_pace_qty > 0:
            pace = avg_pace_qty
        else:
            pace = max(today_qty_main, plan_per_day_qty * 0.3)
        if pace > 0:
            remaining_days = remaining_qty / pace
            expected_completion = today + timedelta(days=round(remaining_days))
            delay_days = (expected_completion - plan_finish).days
        else:
            # 페이스 0 (실 진행 0 + 오늘도 0) — delay 산출 불가
            delay_days = None
            expected_completion = None

    return {
        "plan_mh_per_day": plan_mh_per_day,
        "schedule_state": schedule_state,
        "window_start": ws,
        "window_days": window_days,
        "expected_in_window_mh": expected_in_w,
        "actual_in_window_mh": actual_cum_mh,
        "mh_gap": mh_gap,
        "delay_days": delay_days,
        "expected_completion": expected_completion,
        "remaining_qty": remaining_qty,
        "avg_pace_qty": avg_pace_qty,
    }


def fetch_chroma_actual(
    coll,
    company: str,
    l6_main: str,
    today: date,
    today_assigned_workers: float,
    *,
    today_qty_main: float = 0.0,
    main_unit: Optional[str] = None,
) -> tuple[Optional[date], float, float]:
    """Chroma daily_activities 에서 (company, l6_main) date 별 workers + main_unit qty 누적.

    반환: (window_start, actual_cum_mh, actual_cum_qty)
      - window_start: Chroma 내 (company, l6_main) 첫 적재 일자 (None = 데이터 없음)
      - actual_cum_mh: window 내 워커 일수 × WORK_HOURS_PER_DAY 누적 (compute_delay 의
        reference mh 산출 input)
      - actual_cum_qty: 보조 reference (사용 X) — 아래 NOTE 참조

    2026-05-22 NOTE: Chroma 는 mapper_activities 의 일부만 backfill 되어 있어
    (광건 수장공사 22% 만 적재 케이스 확인) actual_cum_qty 산출에는 부적합.
    actual_cum_qty 는 PG `fetch_pg_actual_cum_qty` 로 별도 산출하여 호출자가 합칠 것.
    여기서 반환하는 actual_cum_qty 는 Chroma window 의 보조 reference 만.
    """
    result = coll.get(
        where={"$and": [{"company": company}, {"l6_main": l6_main}]},
        include=["metadatas"],
    )
    date_to_workers: dict[str, float] = {}
    date_to_qty: dict[str, float] = {}
    for m in result.get("metadatas") or []:
        d = m["date"]
        if d == today.isoformat():
            continue  # 오늘 자기자신 제외 (호출자가 따로 더함)
        date_to_workers[d] = float(m["assigned_workers"])
        if main_unit and m.get("unit") == main_unit:
            date_to_qty[d] = date_to_qty.get(d, 0.0) + float(m.get("today_qty") or 0.0)

    if not date_to_workers:
        return None, today_assigned_workers * WORK_HOURS_PER_DAY, today_qty_main

    date_to_workers[today.isoformat()] = today_assigned_workers
    date_to_qty[today.isoformat()] = date_to_qty.get(today.isoformat(), 0.0) + today_qty_main
    window_start = date.fromisoformat(min(date_to_workers.keys()))
    actual_cum_mh = sum(w * WORK_HOURS_PER_DAY for w in date_to_workers.values())
    actual_cum_qty = sum(date_to_qty.values())
    return window_start, actual_cum_mh, actual_cum_qty
