"""Task 4·5·6 (2026-05-27): pace floor + delay cap + point_in_time deficit unit tests.

spec: docs/superpowers/specs/2026-05-27-cpia-report-redesign-design.md §4.2.3
의도:
  Task 4 — avg_pace_qty == 0 인 케이스에서 pace 가 today_qty_main 만 사용되어
  over-pessimistic delay (>300일) 가 산출되던 문제 차단.
  floor = max(today_qty_main, plan_per_day_qty * 0.3) 로 minimum pace 보장.

  Task 5 — pace floor 적용 후에도 raw delay 가 클 수 있어 추가 cap 필요.
  cap = total_days × 1.0 → delay 가 wp 자체 기간을 초과하지 못함.

  Task 6 — point_in_time_delay_days 차원 추가.
  forward delay (남은 양 / 페이스) 와 별개로 "그 날짜의 누계 부족분 / 일평균 계획"
  을 산출. 진단 LLM (DIAG_PROMPT_V10) 이 사용자에게 "왜 지연 N일 산출됐는지"
  보조 설명용으로 인용.
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


def test_delay_cap_total_days():
    """delay_raw > total_days × 1.0 → cap 됨.

    setup:
      plan_start  = 2025-06-10
      plan_finish = 2025-06-30   (total_days = 21)
      today       = 2025-06-30
      actual_cum_qty = 0          → avg_pace_qty = 0
      plan_total_qty_main = 1.0   → plan_per_day_qty ≈ 0.0476
      today_qty_main = 0.0001     → 매우 작음
      pace floor = max(0.0001, 0.0476 × 0.3 = 0.0143) = 0.0143
      remaining_days = 1.0 / 0.0143 ≈ 70일
      today→plan_finish = 0
      delay_raw ≈ 70일 (cap 없으면 70일까지 튐)

    Task 5 cap = total_days × 1.0 = 21
      → delay_days = min(70, 21) = 21
    """
    plan = {
        "plan_start": date(2025, 6, 10),
        "plan_finish": date(2025, 6, 30),  # 21일짜리 wp
        "plan_mh_sum": 100.0,
    }
    out = compute_delay(
        plan=plan,
        today=date(2025, 6, 30),
        actual_window_start=date(2025, 6, 10),
        actual_cum_mh=50.0,
        actual_cum_qty=0.0,
        plan_total_qty_main=1.0,
        today_qty_main=0.0001,  # 매우 작음
    )
    # total_days = 21, cap = 21 × 1.0 = 21
    # pace floor 적용 후도 delay_raw 큼 → cap 적용
    assert out["delay_days"] is not None
    assert out["delay_days"] <= 21, f"delay cap 미적용: delay_days={out['delay_days']} > 21 (total_days)"


# ────────────────────────────────────────────────────────────────────────────
# Task 6 — point_in_time_delay_days
# spec: 2026-05-27-cpia-report-redesign-design.md §4.2.3
#   plan_qty_to_date = min(plan_per_day_qty × today_offset, plan_total_qty_main)
#   deficit_qty      = max(0, plan_qty_to_date - actual_cum_qty)
#   point_in_time_delay_days = round(deficit_qty / plan_per_day_qty)
# 의도: forward delay 와 별개 차원 ("오늘 시점 누계 부족이 며칠치인지").
# ────────────────────────────────────────────────────────────────────────────


def test_point_in_time_deficit_normal():
    """30일 30루베 plan, 15일째 실 7루베 → deficit 7 = 7일."""
    plan = {
        "plan_start": date(2025, 6, 1),
        "plan_finish": date(2025, 6, 30),  # total_days = 30
        "plan_mh_sum": 100.0,
    }
    out = compute_delay(
        plan=plan,
        today=date(2025, 6, 15),
        actual_window_start=date(2025, 6, 1),
        actual_cum_mh=50.0,
        actual_cum_qty=7.0,
        plan_total_qty_main=30.0,
        today_qty_main=0.5,
    )
    # plan_per_day_qty = 30/30 = 1.0
    # today_offset = (2025-06-15 - 2025-06-01).days = 14
    # plan_qty_to_date = min(1.0 × 14, 30.0) = 14
    # deficit = max(0, 14 - 7) = 7
    # point_in_time = round(7 / 1.0) = 7
    assert out["point_in_time_delay_days"] == 7


def test_point_in_time_before_plan_start():
    """today < plan_start → point_in_time = 0 (today_offset <= 0)."""
    plan = {
        "plan_start": date(2025, 7, 1),
        "plan_finish": date(2025, 12, 30),
        "plan_mh_sum": 100.0,
    }
    out = compute_delay(
        plan=plan,
        today=date(2025, 6, 30),
        actual_window_start=date(2025, 6, 30),
        actual_cum_mh=0.0,
        actual_cum_qty=0.0,
        plan_total_qty_main=10.0,
        today_qty_main=0.0,
    )
    assert out["point_in_time_delay_days"] == 0


def test_point_in_time_after_plan_finish():
    """today > plan_finish → plan_qty_to_date cap (plan_total_qty_main) 작동."""
    plan = {
        "plan_start": date(2025, 5, 1),
        "plan_finish": date(2025, 5, 31),  # total_days = 31
        "plan_mh_sum": 100.0,
    }
    out = compute_delay(
        plan=plan,
        today=date(2025, 6, 15),
        actual_window_start=date(2025, 5, 1),
        actual_cum_mh=80.0,
        actual_cum_qty=8.0,
        plan_total_qty_main=10.0,
        today_qty_main=0.3,
    )
    # plan_per_day_qty = 10 / 31 ≈ 0.3226
    # today_offset = (2025-06-15 - 2025-05-01).days = 45
    # plan_qty_to_date = min(0.3226 × 45 ≈ 14.5, 10.0) = 10.0  ← cap 적용
    # deficit = max(0, 10 - 8) = 2
    # point_in_time = round(2 / 0.3226) ≈ 6
    assert out["point_in_time_delay_days"] > 0


def test_point_in_time_no_qty_returns_zero():
    """plan_total_qty_main is None → point_in_time_delay_days = 0 (안전 처리)."""
    plan = {
        "plan_start": date(2025, 6, 1),
        "plan_finish": date(2025, 6, 30),
        "plan_mh_sum": 100.0,
    }
    out = compute_delay(
        plan=plan,
        today=date(2025, 6, 15),
        actual_window_start=date(2025, 6, 1),
        actual_cum_mh=50.0,
        actual_cum_qty=0.0,
        plan_total_qty_main=None,
        today_qty_main=0.0,
    )
    assert "point_in_time_delay_days" in out
    assert out["point_in_time_delay_days"] == 0


def test_point_in_time_no_plan_returns_zero():
    """plan is None → dict 에 point_in_time_delay_days 키 포함, 값 0."""
    out = compute_delay(
        plan=None,
        today=date(2025, 6, 15),
        actual_window_start=None,
        actual_cum_mh=0.0,
        actual_cum_qty=0.0,
        plan_total_qty_main=None,
        today_qty_main=0.0,
    )
    assert "point_in_time_delay_days" in out
    assert out["point_in_time_delay_days"] == 0
