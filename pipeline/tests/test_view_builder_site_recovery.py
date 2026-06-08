from __future__ import annotations

# 2026-06-09: site 공기 만회 계약 변경 — Σ(wp_summary) → '지배 완료일(longest pole)' 이동량.
# 공종 만회는 병렬이라 더해지지 않는다. 현장 완공일은 가장 늦게 끝나는 WP 가 정하므로
# site recovery = max(by_wp no_action ec) − max(by_wp slot ec). delay_days 상한 클램프.

from pipeline.agents.optimizer.view_builder import reconcile_site_recovery


def _by_wp(no_action: str, base: str):
    return {
        "no_action": {"expected_completion": no_action, "recovery_days": 0},
        "base_p50": {"expected_completion": base},
    }


def test_site_recovery_is_longest_pole_not_sum():
    """두 공종이 각자 5일씩 당겨도 site 는 10일(합)이 아니라 지배 폴 이동량(5일)."""
    scenarios = {
        "by_wp": {
            # 늦게 끝나는 지배 폴 — 5일 당김 (12-31 → 12-26)
            "late": _by_wp("2025-12-31", "2025-12-26"),
            # 일찍 끝나는 폴 — 5일 당겨도 현장 완공일에 무영향
            "early": _by_wp("2025-06-30", "2025-06-25"),
        }
    }
    kpi: dict = {}
    reconcile_site_recovery([], kpi, scenarios)

    assert scenarios["site"]["base_p50"]["recovery_days"] == 5  # 10(합) 아님
    assert kpi["recovery_days"] == 5
    # 무조치 완공일 = 지배 폴 12-31, 만회 후 = 12-26
    assert scenarios["site"]["no_action"]["expected_completion"] == "2025-12-31"
    assert scenarios["site"]["base_p50"]["expected_completion"] == "2025-12-26"
    assert kpi["recovered_completion"] == "2025-12-26"
    assert scenarios["site"]["base_p50"]["delta_days"] == -5


def test_early_pole_recovery_contributes_zero():
    """지배 폴은 못 당기고 일찍 끝나는 폴만 당기면 site 만회 = 0."""
    scenarios = {
        "by_wp": {
            "late": _by_wp("2025-12-31", "2025-12-31"),   # 지배 폴 — 만회 없음
            "early": _by_wp("2025-06-30", "2025-06-10"),  # 20일 당겨도 무영향
        }
    }
    kpi: dict = {}
    reconcile_site_recovery([], kpi, scenarios)
    assert scenarios["site"]["base_p50"]["recovery_days"] == 0
    assert kpi["recovered_completion"] == "2025-12-31"


def test_recovery_clamped_to_delay_days():
    """만회는 지연(delay_days)을 넘지 못한다 — 헤드라인 정합."""
    scenarios = {"by_wp": {"late": _by_wp("2025-12-31", "2025-12-21")}}  # 모델상 10일
    kpi = {"delay_days": 3}
    reconcile_site_recovery([], kpi, scenarios)
    assert kpi["recovery_days"] == 3  # 10 → 3 클램프
    assert scenarios["site"]["base_p50"]["recovery_days"] == 3
    # 완공일도 클램프분에 맞춰 재계산 (12-31 − 3일)
    assert kpi["recovered_completion"] == "2025-12-28"


def test_handles_missing_scenarios_keys():
    """site/base_p50 키 없어도 생성하며 크래시 없음."""
    kpi: dict = {}
    scenarios: dict = {}
    reconcile_site_recovery([{"wp_id": "a", "recovery_days": 3}], kpi, scenarios)
    assert scenarios["site"]["base_p50"]["recovery_days"] == 3  # 날짜 전무 → wp_summary max 폴백
    assert kpi["recovery_days"] == 3


def test_missing_dates_falls_back_to_max_not_sum():
    """by_wp 에 완료예정일이 없으면 max(per-WP recovery_days) — 합산 아님."""
    scenarios = {
        "by_wp": {
            "a": {"base_p50": {"recovery_days": 5}},
            "b": {"base_p50": {"recovery_days": 2}},
        }
    }
    kpi: dict = {}
    reconcile_site_recovery([], kpi, scenarios)
    assert scenarios["site"]["base_p50"]["recovery_days"] == 5  # 7(합) 아님


def test_coerces_none_and_str_in_fallback():
    """폴백 경로에서 recovery_days 가 None/str 로 와도 안전 coerce."""
    scenarios = {
        "by_wp": {
            "a": {"base_p50": {"recovery_days": None}},
            "b": {"base_p50": {"recovery_days": "4"}},
            "c": {"base_p50": {"recovery_days": "abc"}},
        }
    }
    kpi: dict = {}
    reconcile_site_recovery([], kpi, scenarios)
    assert kpi["recovery_days"] == 4


def test_preserves_sibling_fields():
    """site.base_p50 의 rationale 등 비-recovery 필드는 보존."""
    scenarios = {
        "site": {"base_p50": {"rationale": "X"}},
        "by_wp": {"w1": _by_wp("2025-12-31", "2025-12-29")},
    }
    reconcile_site_recovery([], {}, scenarios)
    assert scenarios["site"]["base_p50"]["recovery_days"] == 2
    assert scenarios["site"]["base_p50"]["rationale"] == "X"
    assert scenarios["by_wp"]["w1"]["base_p50"]["expected_completion"] == "2025-12-29"  # by_wp 무손상


def test_scenario_ordering_optimistic_ge_base_ge_pessimistic():
    """optimistic 이 가장 많이 당기고 pessimistic 이 가장 적게 — 순서 보존."""
    scenarios = {
        "by_wp": {
            "late": {
                "no_action": {"expected_completion": "2025-12-31"},
                "optimistic_p25": {"expected_completion": "2025-12-20"},  # 11일
                "base_p50": {"expected_completion": "2025-12-26"},        # 5일
                "pessimistic_p75": {"expected_completion": "2025-12-29"}, # 2일
            }
        }
    }
    reconcile_site_recovery([], {}, scenarios)
    site = scenarios["site"]
    assert (
        site["optimistic_p25"]["recovery_days"]
        >= site["base_p50"]["recovery_days"]
        >= site["pessimistic_p75"]["recovery_days"]
    )
    assert site["optimistic_p25"]["recovery_days"] == 11
    assert site["pessimistic_p75"]["recovery_days"] == 2
