"""mapper.py 시간대 가중 MH 환산 헬퍼 단위 테스트.

spec §3.3 + §7 V2.
"""

from __future__ import annotations


from pipeline.agents.mapper import _weighted_mh_from_shift, _prorate_workers_with_mh


# ============================================================
# _weighted_mh_from_shift
# ============================================================


def test_weighted_mh_daytime_only():
    """주간 10명 → 10 × 8 = 80 MH."""
    shift = {"morning": 0, "daytime": 10, "overtime": 0, "night": 0, "all_night": 0, "total": 10}
    assert _weighted_mh_from_shift(shift) == 80.0


def test_weighted_mh_mixed_shifts():
    """주간 10 + 연장 5 + 야간 2 → 80 + 20 + 16 = 116."""
    shift = {"morning": 0, "daytime": 10, "overtime": 5, "night": 2, "all_night": 0, "total": 17}
    assert _weighted_mh_from_shift(shift) == 116.0


def test_weighted_mh_all_night():
    """철야 3 → 3 × 12 = 36."""
    shift = {"morning": 0, "daytime": 0, "overtime": 0, "night": 0, "all_night": 3, "total": 3}
    assert _weighted_mh_from_shift(shift) == 36.0


def test_weighted_mh_morning_overtime():
    """조출 4 + 연장 4 → 4×2 + 4×4 = 24."""
    shift = {"morning": 4, "daytime": 0, "overtime": 4, "night": 0, "all_night": 0, "total": 8}
    assert _weighted_mh_from_shift(shift) == 24.0


def test_weighted_mh_none():
    """None → 0."""
    assert _weighted_mh_from_shift(None) == 0.0


def test_weighted_mh_empty_dict():
    """빈 dict → 0."""
    assert _weighted_mh_from_shift({}) == 0.0


def test_weighted_mh_missing_keys():
    """일부 키 누락 → 누락 키 0 처리."""
    shift = {"daytime": 5}
    assert _weighted_mh_from_shift(shift) == 40.0


# ============================================================
# _prorate_workers_with_mh
# ============================================================


def test_prorate_plan_mh_basic():
    parsed_report = {
        "job_allocations": [
            {
                "company": "A",
                "final_flag": "O",
                "workers_today_cum": {
                    "morning": 0,
                    "daytime": 100,
                    "overtime": 0,
                    "night": 0,
                    "all_night": 0,
                    "total": 100,
                },
            }
        ],
    }
    mapped = [
        {"company": "A", "l6_main": "l6-1", "plan_mh": 600.0},
        {"company": "A", "l6_main": "l6-2", "plan_mh": 200.0},
    ]
    company_total_plan_mh = {"A": 800.0}
    active_l6_for_company = {"A": {"l6-1", "l6-2"}}
    out = _prorate_workers_with_mh(mapped, parsed_report, company_total_plan_mh, active_l6_for_company)
    assert out[0]["cum_actual_mh_today"] == 600.0
    assert out[1]["cum_actual_mh_today"] == 200.0
    assert out[0]["prorate_method"] == "plan_mh"
    assert out[1]["prorate_method"] == "plan_mh"


def test_prorate_uniform_fallback():
    parsed_report = {
        "job_allocations": [
            {
                "company": "B",
                "final_flag": "O",
                "workers_today_cum": {
                    "morning": 0,
                    "daytime": 60,
                    "overtime": 0,
                    "night": 0,
                    "all_night": 0,
                    "total": 60,
                },
            }
        ],
    }
    mapped = [
        {"company": "B", "l6_main": "l6-x", "plan_mh": 0},
        {"company": "B", "l6_main": "l6-y", "plan_mh": 0},
    ]
    company_total_plan_mh = {"B": 0.0}
    active_l6_for_company = {"B": {"l6-x", "l6-y"}}
    out = _prorate_workers_with_mh(mapped, parsed_report, company_total_plan_mh, active_l6_for_company)
    assert out[0]["cum_actual_mh_today"] == 240.0
    assert out[1]["cum_actual_mh_today"] == 240.0
    assert out[0]["prorate_method"] == "uniform_fallback"


def test_prorate_ignores_final_flag_x():
    parsed_report = {
        "job_allocations": [
            {
                "company": "C",
                "final_flag": "X",
                "workers_today_cum": {
                    "morning": 0,
                    "daytime": 100,
                    "overtime": 0,
                    "night": 0,
                    "all_night": 0,
                    "total": 100,
                },
            }
        ],
    }
    mapped = [{"company": "C", "l6_main": "l6-1", "plan_mh": 100.0}]
    company_total_plan_mh = {"C": 100.0}
    active_l6_for_company = {"C": {"l6-1"}}
    out = _prorate_workers_with_mh(mapped, parsed_report, company_total_plan_mh, active_l6_for_company)
    assert out[0]["cum_actual_mh_today"] == 0.0
    assert out[0]["prorate_method"] == "plan_mh"


def test_prorate_skips_activity_without_l6_main():
    parsed_report = {
        "job_allocations": [
            {
                "company": "D",
                "final_flag": "O",
                "workers_today_cum": {
                    "morning": 0,
                    "daytime": 10,
                    "overtime": 0,
                    "night": 0,
                    "all_night": 0,
                    "total": 10,
                },
            }
        ],
    }
    mapped = [{"company": "D", "l6_main": None, "plan_mh": 0}]
    company_total_plan_mh = {}
    active_l6_for_company = {}
    out = _prorate_workers_with_mh(mapped, parsed_report, company_total_plan_mh, active_l6_for_company)
    assert "cum_actual_mh_today" not in out[0]


def test_prorate_cum_workers_today_is_mh_div_8():
    parsed_report = {
        "job_allocations": [
            {
                "company": "E",
                "final_flag": "O",
                "workers_today_cum": {
                    "morning": 0,
                    "daytime": 80,
                    "overtime": 0,
                    "night": 0,
                    "all_night": 0,
                    "total": 80,
                },
            }
        ],
    }
    mapped = [{"company": "E", "l6_main": "l6-1", "plan_mh": 100.0}]
    company_total_plan_mh = {"E": 100.0}
    active_l6_for_company = {"E": {"l6-1"}}
    out = _prorate_workers_with_mh(mapped, parsed_report, company_total_plan_mh, active_l6_for_company)
    assert out[0]["cum_actual_mh_today"] == 640.0
    assert out[0]["cum_workers_today"] == 80.0
