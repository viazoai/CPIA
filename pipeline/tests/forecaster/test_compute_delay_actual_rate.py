from __future__ import annotations

from datetime import date

from pipeline.agents.forecaster.aggregate import compute_delay


def _plan(start, finish, mh=800.0):
    return {"plan_start": start, "plan_finish": finish, "plan_mh_sum": mh}


# 주의: today_offset = (today - plan_start).days  (결정 §9-3, exclusive — +1 안 함).
# 따라서 "N일 경과" 를 만들려면 today = plan_start + N 일.


def test_delay_uses_actual_rate_not_plan_rate():
    # 100일 plan(1/1~4/10), 총 1000 qty → plan_per_day=10.
    # today=1/11 → today_offset=10 (10일 경과). 실적 누적 50 → actual_rate=50/10=5/일.
    # 계획누적=min(10*10,1000)=100, 부족=100-50=50.
    #   신(actual_rate): 50 ÷ 5  = 10일 지연.
    #   구(plan_rate):   50 ÷ 10 = 5일  ← 둘이 달라야 actual_rate 적용 증명.
    plan = _plan(date(2025, 1, 1), date(2025, 4, 10))  # total_days=100
    out = compute_delay(
        plan,
        today=date(2025, 1, 11),
        actual_window_start=date(2025, 1, 1),
        actual_cum_mh=0.0,
        actual_cum_qty=50.0,
        plan_total_qty_main=1000.0,
        today_qty_main=5.0,
    )
    assert out["delay_days"] == 10  # actual_rate 기반 (구 5 아님)


def test_delay_fallback_to_plan_rate_when_actual_zero():
    # actual_cum=0 → actual_rate 분모 0 폭주 금지, plan_per_day(10) 로 fallback.
    # today=1/11 offset=10, 계획누적=100, 부족=100-0=100 → 100 ÷ 10 = 10일.
    plan = _plan(date(2025, 1, 1), date(2025, 4, 10))
    out = compute_delay(
        plan,
        today=date(2025, 1, 11),
        actual_window_start=None,
        actual_cum_mh=0.0,
        actual_cum_qty=0.0,
        plan_total_qty_main=1000.0,
        today_qty_main=0.0,
    )
    assert out["delay_days"] == 10


def test_delay_uses_weighted_planned_to_date_when_provided():
    # 결정 A: planned_qty_to_date_main 명시 → linear 무시하고 그 값 사용.
    # today=1/11 offset=10, actual_cum 50 → actual_rate=5.
    # 가중 계획누적 80 (linear 면 100) → 부족 80-50=30 → 30÷5 = 6일.
    # (linear path 면 부족 50 → 10일 이므로 6 이면 가중 path 적용 증명.)
    plan = _plan(date(2025, 1, 1), date(2025, 4, 10))  # 100일, plan_per_day=10
    out = compute_delay(
        plan,
        today=date(2025, 1, 11),
        actual_window_start=date(2025, 1, 1),
        actual_cum_mh=0.0,
        actual_cum_qty=50.0,
        plan_total_qty_main=1000.0,
        today_qty_main=5.0,
        planned_qty_to_date_main=80.0,
    )
    assert out["delay_days"] == 6


def test_delay_capped_at_total_days():
    # 11일 plan(1/1~1/11, total_days=11), plan_per_day=1100/11=100.
    # today=1/11 offset=10, 실적 1.0 → actual_rate=0.1 (거의 0 페이스).
    # 계획누적=min(100*10,1100)=1000, 부족=999 → 999/0.1=9990일 폭주 → total_days(11)로 캡.
    plan = _plan(date(2025, 1, 1), date(2025, 1, 11))  # total_days=11
    out = compute_delay(
        plan,
        today=date(2025, 1, 11),
        actual_window_start=date(2025, 1, 1),
        actual_cum_mh=0.0,
        actual_cum_qty=1.0,
        plan_total_qty_main=1100.0,
        today_qty_main=0.1,
    )
    assert out["delay_days"] <= 11
