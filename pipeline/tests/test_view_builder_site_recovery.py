from __future__ import annotations


def test_site_recovery_equals_wp_summary_sum():
    """site recovery = 화면 wp_summary 합 (모집단 정합)."""
    wp_summary = [
        {"wp_id": "a", "recovery_days": 5},
        {"wp_id": "b", "recovery_days": 2},
        {"wp_id": "c", "recovery_days": 0},
    ]
    kpi = {"recovery_days": 31}  # stale (by_wp 23 합)
    scenarios = {"site": {"base_p50": {"recovery_days": 31}}}
    from pipeline.agents.optimizer.view_builder import reconcile_site_recovery

    reconcile_site_recovery(wp_summary, kpi, scenarios)
    assert kpi["recovery_days"] == 7
    assert scenarios["site"]["base_p50"]["recovery_days"] == 7


def test_reconcile_handles_missing_scenarios_keys():
    """site/base_p50 키 없어도 생성하며 크래시 없음."""
    from pipeline.agents.optimizer.view_builder import reconcile_site_recovery

    kpi: dict = {}
    scenarios: dict = {}
    reconcile_site_recovery([{"wp_id": "a", "recovery_days": 3}], kpi, scenarios)
    assert kpi["recovery_days"] == 3
    assert scenarios["site"]["base_p50"]["recovery_days"] == 3


def test_reconcile_coerces_none_and_str():
    """recovery_days 가 None/str 로 와도 int 합산."""
    from pipeline.agents.optimizer.view_builder import reconcile_site_recovery

    kpi: dict = {}
    scenarios: dict = {}
    reconcile_site_recovery(
        [{"recovery_days": None}, {"recovery_days": "4"}, {"recovery_days": 2}], kpi, scenarios
    )
    assert kpi["recovery_days"] == 6
