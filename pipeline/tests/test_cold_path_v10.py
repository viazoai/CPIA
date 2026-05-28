"""Task 16 — cold_start fallback 폐기 후 advice 없는 wp 는 by_wp entry X.

사용자 명시 — "콜드케이스는 절대로 없어야돼 오류가 나면 다시 재시도 하던가 해야되고
조건식에 안걸리면 그 날짜만 따로 취합해서 재시도 하던가 해야돼".

→ view_builder.py 의 _build_deterministic_cold_start fan-out 분기 폐기.
advice 적재 실패한 wp 는 by_wp entry X (FE graceful handling 책임).
by_wp = quadrant 1:1 보장은 retry 3-tier + Task 30 failed_wps batch 가 담당.
"""

from __future__ import annotations


def test_optimizer_view_no_cold_start_fallback():
    """advice_rows 가 일부 wp 만 cover → by_wp 는 그 wp 만 포함, cold_start fan-out X."""
    from pipeline.agents.optimizer.view_builder import _build_optimizer_view

    advice_rows = [
        {
            "company": "co1",
            "l6_main": "wp1",
            "diagnosis": "LLM 진단",
            "recommendations": [{"rank": 1, "keyword": "k", "action": "a", "reason": "r"}],
            "degradation_cases": [],
        }
    ]
    forecast_rows = [
        {"company": "co1", "l6_main": "wp1", "wa": "WA-1", "risk_level": "이상", "delay_days": 5},
        {
            "company": "co2",
            "l6_main": "wp2",
            "wa": "WA-2",
            "risk_level": "정상",
            "delay_days": 0,
        },  # advice 없음
    ]
    mapped: list[dict] = []
    wa_lookup = {("wp1", "co1"): ["WA-1"]}

    view = _build_optimizer_view(advice_rows, forecast_rows, mapped, wa_lookup=wa_lookup)

    # by_wp 에 advice 있는 wp 만 — cold_start fan-out 없음
    by_wp_keys = list(view.get("by_wp", {}).keys())
    assert by_wp_keys, "advice 있는 wp 는 by_wp 에 entry"
    # cold_start source label 없음
    for wp_data in view.get("by_wp", {}).values():
        source = wp_data.get("source")
        assert source not in (
            "deterministic_cold_start",
            "deterministic_cold_start_no_master",
        ), f"cold_start label 발견: {source}"


def test_view_builder_v2_no_cold_start_fan_out():
    """_build_productivity_views_v2 결과의 optimizer_view 가 cold_start fan-out 없음.

    실 PG 호출 의존성 강해서 mock 어려움. inspect 으로 코드 검증.
    """
    import inspect

    from pipeline.agents.optimizer.view_builder import _build_productivity_views_v2

    source = inspect.getsource(_build_productivity_views_v2)
    # cold_start fan-out 분기 (호출) 부재 확인 — Task 16 적용 여부
    assert "_build_deterministic_cold_start(" not in source, "cold_start fan-out 잔존 — Task 16 미적용"
