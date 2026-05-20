"""view_builder._build_scenarios 단위 테스트.

spec §5 + §7 V4.
"""

from __future__ import annotations

from datetime import date


from pipeline.agents.optimizer.view_builder import (
    _build_scenarios,
    _expand_recovery_to_days,
    _percentile,
)


# ============================================================
# _expand_recovery_to_days
# ============================================================


def test_expand_recovery_basic():
    """{'d+1': 2, 'd+3': 3} → [1,1,3,3,3]."""
    out = _expand_recovery_to_days({"d+1": 2, "d+3": 3})
    assert sorted(out) == [1, 1, 3, 3, 3]


def test_expand_recovery_not_recovered_cap():
    """not_recovered → +30 일 캡."""
    out = _expand_recovery_to_days({"d+5": 2, "not_recovered": 3})
    assert sorted(out) == [5, 5, 30, 30, 30]


def test_expand_recovery_empty():
    """빈 dict → 빈 list."""
    assert _expand_recovery_to_days({}) == []
    assert _expand_recovery_to_days(None) == []


# ============================================================
# _percentile
# ============================================================


def test_percentile_monotonic():
    """[1,2,3,4,5,6,7,8,9,10] 에서 p25 ≤ p50 ≤ p75."""
    days = list(range(1, 11))
    p25 = _percentile(days, 0.25)
    p50 = _percentile(days, 0.50)
    p75 = _percentile(days, 0.75)
    assert p25 <= p50 <= p75


def test_percentile_empty():
    """빈 list → 0."""
    assert _percentile([], 0.5) == 0


def test_percentile_single_value():
    """1개 → 그 값."""
    assert _percentile([7], 0.5) == 7


# ============================================================
# _build_scenarios
# ============================================================


def test_scenarios_basic():
    """advice 1건 + forecast 1건 → site + by_wp 각각 4 시나리오."""
    advice_rows = [
        {
            "company": "A",
            "l6_main": "L6",
            "recovery_distribution": {"d+5": 3, "d+10": 2, "d+3": 5},
        }
    ]
    forecast = [
        {
            "company": "A",
            "l6_main": "L6",
            "wa": "WA-1",
            "expected_completion": date(2026, 12, 31),
        }
    ]
    out = _build_scenarios(advice_rows, forecast)

    assert set(out["site"].keys()) == {"no_action", "optimistic_p25", "base_p50", "pessimistic_p75"}
    assert out["site"]["no_action"]["delta_days"] == 0
    assert (
        out["site"]["optimistic_p25"]["recovery_days"]
        <= out["site"]["base_p50"]["recovery_days"]
        <= out["site"]["pessimistic_p75"]["recovery_days"]
    )
    assert out["site"]["base_p50"]["delta_days"] == -out["site"]["base_p50"]["recovery_days"]

    # by_wp 의 WP_ID 존재 — _wp_id_of(wa, l6, company) 결과 (kebab)
    assert len(out["by_wp"]) == 1


def test_scenarios_cold_start():
    """advice 0건 → site no_action only, by_wp 빈 dict."""
    out = _build_scenarios([], [])
    assert out["by_wp"] == {}
    assert out["site"]["no_action"]["delta_days"] == 0
    assert out["site"]["base_p50"]["delta_days"] == 0


def test_scenarios_not_recovered_only():
    """recovery_distribution 이 not_recovered 만 → percentile 모두 30 (캡)."""
    advice_rows = [
        {
            "company": "A",
            "l6_main": "L6",
            "recovery_distribution": {"not_recovered": 5},
        }
    ]
    forecast = [
        {
            "company": "A",
            "l6_main": "L6",
            "wa": "WA-1",
            "expected_completion": date(2026, 12, 31),
        }
    ]
    out = _build_scenarios(advice_rows, forecast)
    assert out["site"]["base_p50"]["recovery_days"] == 30


def test_scenarios_forecast_mismatch_skipped():
    """advice 의 (company, l6_main) 이 forecast 에 없으면 by_wp 미포함."""
    advice_rows = [
        {
            "company": "A",
            "l6_main": "L6",
            "recovery_distribution": {"d+3": 3},
        }
    ]
    forecast = [
        {
            "company": "DIFFERENT",
            "l6_main": "L6",
            "wa": "WA-1",
            "expected_completion": date(2026, 12, 31),
        }
    ]
    out = _build_scenarios(advice_rows, forecast)
    assert out["by_wp"] == {}
    assert out["site"]["base_p50"]["recovery_days"] == 3
