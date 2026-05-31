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


async def fetch_pg_planned_qty_to_date(
    pg,
    company: str,
    l6_main: str,
    today: date,
    unit: Optional[str],
) -> Optional[float]:
    """activity_master 의 (company, l6_main, unit) activity 단위 가중 계획 누적 qty @ today.

    2026-05-30 결정 A: forecaster delay 기준을 site s_curve(view_builder)와 통일.
    각 activity 가 자기 plan_start..plan_finish 에 linear progress(cap 1) →
    plan_total_qty × fraction 의 합. s_curve planned 곡선과 동일 공식이라 site/WP delay 정합.
    (이전 group-envelope MIN(start)~MAX(finish) linear 는 9/24 에 계획%를 과소평가 → WP delay 0.)
    unit 없거나 activity 없으면 None (compute_delay 가 linear fallback).
    """
    if not unit:
        return None
    rows = await pg.fetch_all(
        """
        SELECT COALESCE(SUM(
            plan_total_qty * LEAST(1.0, GREATEST(0.0,
                ($4::date - plan_start + 1)::float
                / NULLIF((plan_finish - plan_start + 1)::float, 0)
            ))
        ), 0)::float AS s
        FROM activity_master
        WHERE company = $1 AND l6_main = $2 AND unit = $3
          AND plan_start IS NOT NULL AND plan_finish IS NOT NULL
          AND plan_total_qty IS NOT NULL
        """,
        company,
        l6_main,
        unit,
        today,
    )
    if not rows or rows[0]["s"] is None:
        return None
    return float(rows[0]["s"])


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
    planned_qty_to_date_main: Optional[float] = None,
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
            "forward_delay_days": None,
            "expected_completion": None,
            "remaining_qty": None,
            "avg_pace_qty": None,
            # 2026-05-27 Task 6: point_in_time_delay_days — plan 없으면 산출 불가, 0 안전 처리.
            "point_in_time_delay_days": 0,
            # 2026-05-29 SSOT: 산출근거 문자열 (plan 없으면 빈 값).
            "delay_basis": "",
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

    # 2026-05-29 prod fix: delay = point-in-time(누계 부족분/일평균) 을 主 산식으로.
    # 이전 forward 외삽(잔여/페이스 → expected_completion − plan_finish)은 actual_cum 이
    # distinct plan_total 을 초과(Σ vs distinct 불일치)하면 잔여 0 → expected=today →
    # delay = today − plan_finish = -37 같은 비현실 "앞섬" 을 냈다. point-in-time 은
    # window 독립 + 부족분만 보므로 그 왜곡이 없다. forward 는 forward_delay_days 로 참고 보존.
    delay_basis = ""
    if plan_total_qty_main is None or plan_total_qty_main <= 0:
        # plan qty 없으면 delay 산출 불가 — None
        delay_days = None
        forward_delay_days = None
        expected_completion = None
        remaining_qty = None
        avg_pace_qty = None
        point_in_time_delay_days = 0
    else:
        plan_per_day_qty = plan_total_qty_main / total_days if total_days > 0 else 0.0
        remaining_qty = max(0.0, plan_total_qty_main - actual_cum_qty)

        # --- 主: point-in-time 누계 부족분 ÷ 실제 누적평균일생산 (2026-05-29 reseed v2) ---
        # 분모를 일평균계획(plan_rate)에서 실제 누적평균일생산(actual_rate)으로 교체.
        # 지각 WP 는 느린 실제 페이스로 부족분을 만회하므로 delay 가 더 현실적으로 커진다.
        today_offset = (today - plan_start).days  # days_elapsed (결정 §9-3, exclusive)
        # actual_rate = 누적실적 / 경과일. 0(실적 없음/경과 0)이면 plan_per_day fallback (결정 §9-6).
        actual_rate = (actual_cum_qty / today_offset) if today_offset > 0 and actual_cum_qty > 0 else 0.0
        rate_denom = actual_rate if actual_rate > 0 else plan_per_day_qty
        if rate_denom > 0 and today_offset > 0:
            # 결정 A (2026-05-30): activity 단위 가중 계획-to-date 우선(site s_curve 정합).
            # 미전달(None) 시 group-envelope linear fallback (기존 호출/테스트 호환).
            if planned_qty_to_date_main is not None:
                plan_qty_to_date = min(planned_qty_to_date_main, plan_total_qty_main)
            else:
                plan_qty_to_date = min(plan_per_day_qty * today_offset, plan_total_qty_main)
            deficit_qty = max(0.0, plan_qty_to_date - actual_cum_qty)
            raw_delay = round(deficit_qty / rate_denom)
            # 캡: actual_rate≈0 일 때 delay 폭주(구 26,517일 류) 방지 (결정 §9-6).
            delay_days = max(-total_days, min(total_days, raw_delay))
            # 산출근거 — 카드 "일정 영향" 옆 노출 (사용자 요청).
            if deficit_qty > 0:
                delay_basis = (
                    f"계획누적 {plan_qty_to_date:,.0f} − 실제 {actual_cum_qty:,.0f} "
                    f"= {deficit_qty:,.0f} 부족 ÷ 실제페이스 {rate_denom:,.1f}/일 "
                    f"→ {delay_days}일 지연"
                )
            else:
                delay_basis = (
                    f"계획누적 {plan_qty_to_date:,.0f} 대비 실제 {actual_cum_qty:,.0f} "
                    f"— 부족 없음 (일정 충족)"
                )
        else:
            delay_days = 0
        point_in_time_delay_days = delay_days  # 호환 유지 (동일 값)
        # expected_completion = plan_finish + 지연 (부족 N일 → N일 늦게 완공).
        expected_completion = plan_finish + timedelta(days=delay_days)

        # --- 참고: forward 외삽 (옛 산식, forward_delay_days 로 보존) ---
        avg_pace_qty = actual_cum_qty / window_days if window_days > 0 else 0.0
        if avg_pace_qty > 0:
            pace = avg_pace_qty
        else:
            pace = max(today_qty_main, plan_per_day_qty * 0.3)
        if pace > 0:
            fwd_ec = today + timedelta(days=round(remaining_qty / pace))
            forward_delay_days = min((fwd_ec - plan_finish).days, round(total_days * 1.0))
        else:
            forward_delay_days = None

    return {
        "plan_mh_per_day": plan_mh_per_day,
        "schedule_state": schedule_state,
        "window_start": ws,
        "window_days": window_days,
        "expected_in_window_mh": expected_in_w,
        "actual_in_window_mh": actual_cum_mh,
        "mh_gap": mh_gap,
        "delay_days": delay_days,
        # 2026-05-29: forward 외삽(옛 산식) — 참고 보존. delay_days 主 산식은 point-in-time.
        "forward_delay_days": forward_delay_days,
        "expected_completion": expected_completion,
        "remaining_qty": remaining_qty,
        "avg_pace_qty": avg_pace_qty,
        # 2026-05-27 Task 6: 신규 — db.py insert_forecast $29 placeholder 와 짝.
        "point_in_time_delay_days": point_in_time_delay_days,
        # 2026-05-29 SSOT: point-in-time delay 산출근거 (UI 카드 노출용).
        "delay_basis": delay_basis,
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
