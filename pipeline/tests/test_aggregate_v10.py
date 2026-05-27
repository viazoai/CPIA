"""Task 4 (2026-05-27): pace floor 헬퍼 unit tests.

spec: docs/superpowers/specs/2026-05-27-cpia-report-redesign-design.md §4.2.3
의도: avg_pace_qty == 0 인 케이스에서 pace 가 today_qty_main 만 사용되어
over-pessimistic delay (>300일) 가 산출되던 문제 차단.
floor = max(today_qty_main, plan_per_day_qty * 0.3) 로 minimum pace 보장.
"""

from __future__ import annotations

from datetime import date

from pipeline.agents.forecaster.aggregate import compute_delay


def test_pace_floor_when_actual_zero():
    """actual_cum_qty=0, today_qty 매우 작음 → pace = plan_per_day × 0.3 floor 적용.

    setup:
      plan_start  = 2025-06-10
      plan_finish = 2025-12-30   (total_days = 204)
      today       = 2025-06-30
      window_days = 21 (2025-06-10 ~ 2025-06-30)
      actual_cum_qty = 0          → avg_pace_qty = 0
      plan_total_qty_main = 1.0   → plan_per_day_qty ≈ 0.0049
      today_qty_main = 0.001      → today_qty 만 쓰면 pace = 0.001 → remaining ≈ 1000일

    pace floor 적용 후:
      pace = max(0.001, 0.0049 × 0.3 = 0.00147) = 0.00147
      remaining_days = 1.0 / 0.00147 ≈ 680일
      delay_raw ≈ 680 − 183 (today→plan_finish) ≈ 497

    Task 4 단독 (delay cap 은 Task 5):
      assertion = today_qty_main 단독 쓰던 시절보다 delay_days 가 작음
    """
    plan = {
        "plan_start": date(2025, 6, 10),
        "plan_finish": date(2025, 12, 30),
        "plan_mh_sum": 1000.0,
    }
    today = date(2025, 6, 30)
    out = compute_delay(
        plan=plan,
        today=today,
        actual_window_start=date(2025, 6, 10),
        actual_cum_mh=872.4,
        actual_cum_qty=0.0,
        plan_total_qty_main=1.0,
        today_qty_main=0.001,
    )

    assert out["delay_days"] is not None, "pace floor 적용 시 delay_days 산출 가능해야 함"

    # today_qty_main(0.001) 만 사용 시 baseline:
    #   pace = 0.001
    #   remaining_days = 1.0 / 0.001 = 1000일
    #   today→plan_finish = 183일
    #   delay_baseline = 1000 - 183 = 817일
    # pace floor 적용 후 delay 는 baseline 보다 명확히 작아야 함 (over-pessimistic 차단).
    baseline_pace = 0.001
    baseline_remaining_days = 1.0 / baseline_pace
    baseline_today_to_finish = (plan["plan_finish"] - today).days
    baseline_delay = round(baseline_remaining_days) - baseline_today_to_finish
    assert out["delay_days"] < baseline_delay, (
        f"pace floor 가 작동하지 않음: delay_days={out['delay_days']} "
        f"baseline (today_qty_main only)={baseline_delay}"
    )


def test_pace_floor_when_today_qty_normal():
    """today_qty 가 plan_per_day × 0.3 보다 크면 today_qty 사용 (floor 영향 없음).

    setup:
      plan_per_day_qty = 1.0 / 204 ≈ 0.0049
      floor = 0.0049 × 0.3 = 0.00147
      today_qty_main = 0.01 > 0.00147 → pace = 0.01
      remaining_days = 1.0 / 0.01 = 100일
      today→plan_finish = 183일
      delay_raw = 100 - 183 = -83 (앞당김)
    """
    plan = {
        "plan_start": date(2025, 6, 10),
        "plan_finish": date(2025, 12, 30),
        "plan_mh_sum": 1000.0,
    }
    out = compute_delay(
        plan=plan,
        today=date(2025, 6, 30),
        actual_window_start=date(2025, 6, 10),
        actual_cum_mh=500.0,
        actual_cum_qty=0.0,
        plan_total_qty_main=1.0,
        today_qty_main=0.01,
    )
    assert out["delay_days"] is not None
    assert out["delay_days"] <= 0, (
        f"today_qty 가 floor 보다 클 땐 앞당김(<=0) 이어야 함: delay_days={out['delay_days']}"
    )
