"""view_builder _compose_evm 단위 테스트 — pure function, PG 호출 X."""

from __future__ import annotations

from pipeline.agents.optimizer.view_builder import _compose_evm


def test_compose_evm_세보엠이씨_기계소화():
    """세보엠이씨 기계소화 케이스: SPI~32.47, CPI~51.32."""
    plan_row = {
        "cum_plan_qty": 77774,
        "cum_plan_mh": 744043,
        "plan_qty_full": 77774,
        "plan_mh_full": 744043,
    }
    actual_row = {"cum_actual_qty": 25252, "cum_actual_mh": 470692}
    r = _compose_evm(plan_row, actual_row)
    assert abs(r["spi"] - 32.47) < 0.1, f"SPI={r['spi']}"
    assert abs(r["cpi"] - 51.32) < 0.1, f"CPI={r['cpi']}"


def test_compose_evm_returns_none_when_no_plan():
    """plan_qty_full=0 이면 SPI/CPI 모두 None."""
    plan_row = {
        "cum_plan_qty": 0,
        "cum_plan_mh": 0,
        "plan_qty_full": 0,
        "plan_mh_full": 0,
    }
    actual_row = {"cum_actual_qty": 0, "cum_actual_mh": 0}
    r = _compose_evm(plan_row, actual_row)
    assert r["spi"] is None
    assert r["cpi"] is None
    assert r["ev"] == 0


def test_compose_evm_cpi_none_when_ac_zero():
    """AC=0 (work 미시작) 이면 CPI=None, SPI 는 계산 가능."""
    plan_row = {
        "cum_plan_qty": 100,
        "cum_plan_mh": 800,
        "plan_qty_full": 100,
        "plan_mh_full": 800,
    }
    actual_row = {"cum_actual_qty": 20, "cum_actual_mh": 0}
    r = _compose_evm(plan_row, actual_row)
    assert r["spi"] == 20.0  # 20/100 x 100 (EV=20% of 800=160, PV=800 -> 20%)
    assert r["cpi"] is None


def test_compose_evm_plan_row_none_safe():
    """plan_row=None safe handling."""
    actual_row = {"cum_actual_qty": 100, "cum_actual_mh": 200}
    r = _compose_evm(None, actual_row)
    assert r["spi"] is None
    assert r["cpi"] is None


from pipeline.agents.optimizer.view_builder import _build_contractor_bars, _build_trade_bars, _bar_status


def test_bar_status_thresholds():
    assert _bar_status(95) == "normal"
    assert _bar_status(90) == "normal"
    assert _bar_status(85) == "caution"
    assert _bar_status(80) == "caution"
    assert _bar_status(79) == "risk"
    assert _bar_status(0) == "risk"


def test_build_contractor_bars_sorted_desc():
    """by_contractor 의 CPI desc 정렬 + status mapping."""
    productivity = {
        "by_contractor": {
            "회사A": {"cpi": 95.2},
            "회사B": {"cpi": 82.7},
            "회사C": {"cpi": 50.1},
        }
    }
    bars = _build_contractor_bars(productivity)
    assert len(bars) == 3
    assert bars[0]["label"] == "회사A"
    assert bars[0]["value"] == 95.2
    assert bars[0]["status"] == "normal"
    assert bars[1]["status"] == "caution"
    assert bars[2]["status"] == "risk"


def test_build_contractor_bars_handles_none_cpi():
    """cpi=None 인 contractor 는 0 으로 처리."""
    productivity = {"by_contractor": {"회사A": {"cpi": None}}}
    bars = _build_contractor_bars(productivity)
    assert bars[0]["value"] == 0.0
    assert bars[0]["status"] == "risk"


def test_build_trade_bars_uses_by_l6():
    """trade bar 는 by_l6 dict 사용."""
    productivity = {
        "by_l6": {
            "콘크리트 타설": {"cpi": 88.5},
            "철근 가공": {"cpi": 92.0},
        }
    }
    bars = _build_trade_bars(productivity)
    assert len(bars) == 2
    assert bars[0]["label"] == "철근 가공"  # 92.0 first
    assert bars[1]["label"] == "콘크리트 타설"


def test_build_contractor_bars_empty():
    """by_contractor 비어있으면 빈 list."""
    assert _build_contractor_bars({}) == []
    assert _build_contractor_bars({"by_contractor": {}}) == []


from pipeline.agents.optimizer.view_builder import (
    _compute_impact_p90,
    _normalize_impact,
    _quadrant_label,
    _wp_id_of,
)


def test_compute_impact_p90_empty_list_returns_one():
    """Minor 6 guard — 빈 list 시 IndexError 없이 1.0 반환."""
    assert _compute_impact_p90([]) == 1.0


def test_compute_impact_p90_short_list_uses_max():
    """10 미만이면 max fallback."""
    assert _compute_impact_p90([10, 20, 30]) == 30


def test_compute_impact_p90_ten_or_more():
    """10 이상이면 quantiles 의 [8] (90 percentile)."""
    # 1, 2, ..., 10 -> P90 ~ 9.x
    p90 = _compute_impact_p90([float(i) for i in range(1, 11)])
    assert 9.0 <= p90 <= 10.0


def test_normalize_impact_caps_at_100():
    """raw > p90 이면 100 으로 capping."""
    assert _normalize_impact(200, 100) == 100.0
    assert _normalize_impact(50, 100) == 50.0
    assert _normalize_impact(0, 100) == 0.0
    assert _normalize_impact(50, 0) == 0.0  # p90=0 safe


def test_quadrant_label_four_quadrants():
    assert _quadrant_label(50, 70) == "risk"  # low prod + high impact
    assert _quadrant_label(50, 30) == "caution"  # low prod
    assert _quadrant_label(90, 70) == "watch"  # high impact
    assert _quadrant_label(90, 30) == "safe"


def test_wp_id_kebab_case():
    assert _wp_id_of("Zone A", "콘크리트 타설", "세보") == "zone-a-콘크리트-타설-세보"
    assert _wp_id_of(None, None, None) == "unknown-unknown-unknown"


from datetime import date as _date

from pipeline.agents.optimizer.view_builder import _merge_curves, _extend_forecast


def test_merge_curves_planned_and_actual():
    planned = [{"date": _date(2026, 1, 1), "cum_plan_qty": 100}, {"date": _date(2026, 1, 2), "cum_plan_qty": 200}]
    actual = [{"report_date": _date(2026, 1, 1), "day_qty": 50}, {"report_date": _date(2026, 1, 2), "day_qty": 70}]
    out = _merge_curves(planned, actual)
    assert len(out) == 2
    assert out[0]["date"] == "2026-01-01"
    assert out[0]["planned"] == 100
    assert out[0]["actual"] == 50  # cumulative day 1
    assert out[1]["actual"] == 120  # cumulative day 2


def test_merge_curves_with_recovery():
    planned = [{"date": _date(2026, 1, 1), "cum_plan_qty": 100}]
    actual = []
    recovery = [{"date": "2026-01-01", "recovery_days": 3}]
    out = _merge_curves(planned, actual, recovery)
    assert out[0]["recovery_days"] == 3


def test_merge_curves_empty():
    assert _merge_curves([], []) == []


def test_extend_forecast_linear_extrapolation():
    merged = [
        {"date": "2026-01-01", "actual": 100},
        {"date": "2026-01-02", "actual": 150},  # rate = 50/day
    ]
    out = _extend_forecast(merged, days_ahead=3)
    forecast_points = [m for m in out if m.get("forecast") is not None]
    # 시작점 (last actual) + 3 days = 4 forecast point
    assert len(forecast_points) == 4
    assert forecast_points[0]["forecast"] == 150  # last actual 시작점
    assert forecast_points[1]["forecast"] == 200  # +50
    assert forecast_points[2]["forecast"] == 250
    assert forecast_points[3]["forecast"] == 300


def test_extend_forecast_skip_when_too_few_actual():
    """actual point 1 개 이하 면 forecast 연장 skip."""
    merged = [{"date": "2026-01-01", "actual": 100}]
    out = _extend_forecast(merged)
    assert out == merged  # 그대로


# ---------------------------------------------------------------------------
# 2026-05-19: EVM 산식 컨셉 변경 — mapped CTE 제거 (분모 = 마스터플랜 전체)
# ---------------------------------------------------------------------------


def test_progress_ratio_sql_helper_exists():
    """_PROGRESS_RATIO_SQL helper 가 by_group SQL 통일에 사용됨."""
    from pipeline.agents.optimizer.view_builder import _PROGRESS_RATIO_SQL

    assert "LEAST(1.0" in _PROGRESS_RATIO_SQL
    assert "GREATEST(0.0" in _PROGRESS_RATIO_SQL
    assert "NULLIF" in _PROGRESS_RATIO_SQL
    assert "$2::date" in _PROGRESS_RATIO_SQL
    assert "am.plan_start" in _PROGRESS_RATIO_SQL
    assert "am.plan_finish" in _PROGRESS_RATIO_SQL


def test_evm_by_wa_l6_company_function_exists():
    """wa_l6_company group 은 별도 함수로 분리됨 (wa 는 mapper 전용 키 → mapper anchor 유지)."""
    from pipeline.agents.optimizer import view_builder

    assert callable(view_builder._evm_by_wa_l6_company)


def test_compose_evm_master_plan_denominator():
    """2026-05-19 컨셉: 분모=마스터플랜 전체, 분자=mapper_activities 전체.

    plan_row 가 site 전체 master SUM (mapped CTE 없이) 이고 actual_row 가 작아도
    SPI/CPI 모두 계산됨 (분모 stable, 분자가 scope 결과로 변동).
    """
    plan_row = {
        "cum_plan_qty": 10000.0,  # 전체 마스터플랜
        "cum_plan_mh": 80000.0,
        "plan_qty_full": 10000.0,
        "plan_mh_full": 80000.0,
    }
    actual_row = {"cum_actual_qty": 500.0, "cum_actual_mh": 4500.0}
    r = _compose_evm(plan_row, actual_row)
    # progress = 500/10000 = 0.05
    # EV = 0.05 * 80000 = 4000
    # SPI = 4000/80000 * 100 = 5.0
    # CPI = 4000/4500 * 100 ≈ 88.89
    assert abs(r["spi"] - 5.0) < 0.01
    assert abs(r["cpi"] - 88.89) < 0.1
    assert r["ev"] == 4000.0
    assert r["pv"] == 80000.0
    assert r["ac"] == 4500.0
