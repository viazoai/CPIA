"""Phase 2 view_builder + retrieve + backfill 변경 검증."""

from __future__ import annotations

from datetime import date

import pytest

from pipeline.agents.optimizer.view_builder import _wp_id_of


def test_wp_id_of_kebab_format():
    """_wp_id_of 가 kebab-case + lowercase 반환."""
    assert _wp_id_of("FAB-A02", "철근콘크리트공사", "남웅건설") == "fab-a02-철근콘크리트공사-남웅건설"
    assert _wp_id_of(None, "방수공사", "동성건업") == "unknown-방수공사-동성건업"
    assert _wp_id_of("CUB", "방수공사", None) == "cub-방수공사-unknown"


@pytest.mark.integration
async def test_quadrant_has_new_keys(pg_client):
    """C2 — quadrant dict 에 l7_5_activity / company / l6_main / workers + kebab wp_id."""
    from pipeline.agents.optimizer.view_builder import _build_productivity_views_v2

    result = await _build_productivity_views_v2(pg_client, "m15x-ph3-ibl", date(2025, 9, 25))
    assert result["quadrant"], "quadrant 비어 있음 — 9-25 데이터 부재?"
    for q in result["quadrant"]:
        assert "l7_5_activity" in q
        assert "company" in q
        assert "l6_main" in q
        assert "workers" in q
        assert isinstance(q["workers"], int)
        # wp_id kebab 형식 (정수 prefix WP- 아님)
        assert not q["wp_id"].startswith("WP-")


@pytest.mark.integration
async def test_returns_9_keys(pg_client):
    """C3 — _build_productivity_views_v2 가 optimizer_view/scenarios/s_curve 포함 9 key 반환."""
    from pipeline.agents.optimizer.view_builder import _build_productivity_views_v2

    result = await _build_productivity_views_v2(pg_client, "m15x-ph3-ibl", date(2025, 9, 25))
    expected = {
        "kpi",
        "productivity",
        "contractor_bars",
        "trade_bars",
        "quadrant",
        "wp_summary",
        "optimizer_view",
        "scenarios",
        "s_curve",
    }
    assert set(result.keys()) >= expected, f"missing: {expected - set(result.keys())}"


def test_build_wa_lookup():
    """C4 — (l6_main, company) → DISTINCT wa list."""
    from pipeline.agents.optimizer.view_builder import _build_wa_lookup

    items = [
        {"wa": "FAB", "l6_main": "철근콘크리트공사", "company": "남웅건설"},
        {"wa": "CUB", "l6_main": "철근콘크리트공사", "company": "남웅건설"},
        {"wa": "FAB", "l6_main": "방수공사", "company": "동성건업"},
        {"wa": None, "l6_main": "방수공사", "company": "동성건업"},
    ]
    lookup = _build_wa_lookup(items)
    assert lookup[("철근콘크리트공사", "남웅건설")] == ["FAB", "CUB"]
    assert lookup[("방수공사", "동성건업")] == ["FAB"]


# ─── C5 — deterministic cold_start (8 cause × 5 rule + edge) ───


def test_deterministic_cold_start_diagnosis_format_and_length():
    from pipeline.agents.optimizer.view_builder import _build_deterministic_cold_start

    q = {
        "wp_id": "fab-x-y",
        "perperson": 1.70,
        "perperson_unit": "m³/인",
        "impact": 65.0,
        "trade": "건축",
        "workers": 3,
        "company": "남웅건설",
        "l7_5_activity": "무근 콘크리트 타설",
        "l6_main": "철근콘크리트공사",
    }
    master = {"daily_qty": 25.0, "daily_workers": 10, "unit": "m³"}
    result = _build_deterministic_cold_start(
        q,
        master,
        [],
        workers=3,
        risk_level="이상",
        delay_days=2,
    )
    assert "보통 인당 2.50 m³" in result["diagnosis"]
    assert "오늘은 인당 1.70 m³ (68.0%)" in result["diagnosis"]
    assert len(result["diagnosis"]) <= 140
    assert result["source"] == "deterministic_cold_start"


def test_deterministic_cold_start_master_none_fallback():
    from pipeline.agents.optimizer.view_builder import _build_deterministic_cold_start

    q = {
        "wp_id": "fab-x",
        "perperson": 1.70,
        "perperson_unit": "m³/인",
        "impact": 50.0,
        "trade": "건축",
        "workers": 3,
        "company": "남웅",
        "l7_5_activity": "X",
        "l6_main": "Y",
    }
    result = _build_deterministic_cold_start(
        q,
        None,
        [],
        workers=3,
        risk_level="—",
        delay_days=0,
    )
    assert "마스터 데이터 없음" in result["diagnosis"]
    assert "1.70 m³/인" in result["diagnosis"]
    assert result["source"] == "deterministic_cold_start_no_master"


def test_deterministic_cold_start_unit_none_safe():
    from pipeline.agents.optimizer.view_builder import _build_deterministic_cold_start

    q = {
        "wp_id": "x",
        "perperson": 1.0,
        "perperson_unit": None,
        "impact": 30.0,
        "trade": "건축",
        "workers": 2,
        "company": "X",
        "l7_5_activity": "Y",
        "l6_main": "Z",
    }
    master = {"daily_qty": 10, "daily_workers": 10, "unit": None}
    result = _build_deterministic_cold_start(
        q,
        master,
        [],
        workers=2,
        risk_level="정상",
        delay_days=0,
    )
    assert "단위미상" in result["diagnosis"]
    assert result["source"] in (
        "deterministic_cold_start",
        "deterministic_cold_start_no_master",
    )


@pytest.mark.parametrize(
    "pct,impact,delay,trade,expected_substr",
    [
        (45, 90, 6, "건축", "후속 양생 의존성"),
        (50, 70, 3, "건축", "장비 가용성"),
        (65, 40, 5, "토목", "선행 작업 지연"),
        (65, 60, 0, "건축", "인력 분산"),
        (75, 30, 0, "토목", "기상 영향"),
        (75, 30, 0, "건축", "동시 작업 간섭"),
        (85, 20, 0, "건축", "자재 대기"),
        (95, 10, 0, "건축", ""),
    ],
)
def test_pick_cause_8_branches(pct, impact, delay, trade, expected_substr):
    from pipeline.agents.optimizer.view_builder import _pick_cause

    cause = _pick_cause(pct, impact, delay, trade)
    if expected_substr:
        assert expected_substr in cause, f"({pct},{impact},{delay},{trade}) → {cause!r}"
    else:
        assert cause == ""


@pytest.mark.parametrize(
    "pct,impact,delay,workers,trade,expected_count,expected_substrs",
    [
        # 각 룰 독립 평가 (R3 = trade=건축 + pct<80 → 광범위 trigger).
        (65, 60, 0, 3, "건축", 2, ["인력 +1", "선행 토목"]),  # R1+R3
        (65, 60, 3, 3, "건축", 3, ["인력 +1", "후속 작업", "선행 토목"]),  # R1+R2+R3
        (75, 20, 0, 3, "건축", 1, ["선행 토목"]),  # R3 only
        (50, 25, 0, 3, "건축", 2, ["선행 토목", "장비"]),  # R3+R4
        (95, 5, 0, 3, "건축", 1, ["현 페이스 유지"]),  # R5 only
        (40, 90, 5, 2, "건축", 4, ["인력 +1", "후속 작업", "선행 토목", "장비"]),  # R1+R2+R3+R4
    ],
)
def test_pick_recommendations_combinations(
    pct,
    impact,
    delay,
    workers,
    trade,
    expected_count,
    expected_substrs,
):
    from pipeline.agents.optimizer.view_builder import _pick_recommendations

    recs = _pick_recommendations(pct, impact, delay, workers, trade)
    assert len(recs) == expected_count, f"got {recs}"
    for sub in expected_substrs:
        assert any(sub in r for r in recs), f"missing {sub!r} in {recs}"


@pytest.mark.integration
async def test_fetch_chroma_cases_lookup_returns_dict():
    """C6 — ChromaDB daily_activities lookup. 빈 컬렉션이라도 dict[wp_id → list] 반환."""
    from pipeline.agents.optimizer.view_builder import _fetch_chroma_cases_lookup

    items = [
        {
            "wp_id": "fab-x-방수-남웅",
            "l7_5_activity": "방수 시공",
            "l6_main": "방수공사",
            "company": "남웅건설",
        }
    ]
    lookup = await _fetch_chroma_cases_lookup(items, date(2025, 9, 25))
    assert "fab-x-방수-남웅" in lookup
    assert isinstance(lookup["fab-x-방수-남웅"], list)


@pytest.mark.integration
async def test_optimizer_view_all_quadrant_filled(pg_client):
    """C7 — quadrant 모든 WP 가 optimizer_view.by_wp 에 채워짐 (advice or cold_start)."""
    from pipeline.agents.optimizer.view_builder import _build_productivity_views_v2

    result = await _build_productivity_views_v2(pg_client, "m15x-ph3-ibl", date(2025, 9, 25))
    q_ids = {q["wp_id"] for q in result["quadrant"]}
    bw_keys = set(result["optimizer_view"]["by_wp"].keys())
    assert q_ids <= bw_keys, f"누락 WP: {q_ids - bw_keys}"
    for k, v in result["optimizer_view"]["by_wp"].items():
        assert v.get("diagnosis"), f"diagnosis 빔: {k}"


def test_build_scenarios_schema_with_empty_input():
    """C8 — 기존 _build_scenarios([], []) 도 site/by_wp + 4 키 schema 만족 (advice 없을 때 fallback)."""
    from pipeline.agents.optimizer.view_builder import _build_scenarios

    s = _build_scenarios([], [])
    assert "site" in s and "by_wp" in s
    for k in ("no_action", "optimistic_p25", "base_p50", "pessimistic_p75"):
        assert k in s["site"], f"missing {k}"
    assert s["by_wp"] == {}


@pytest.mark.integration
async def test_phase2_views_v2_scenarios_and_s_curve_non_null(pg_client):
    """C8 통합 — _build_productivity_views_v2 의 scenarios / s_curve 가 빈 stub 이 아님."""
    from pipeline.agents.optimizer.view_builder import _build_productivity_views_v2

    result = await _build_productivity_views_v2(pg_client, "m15x-ph3-ibl", date(2025, 9, 25))
    assert isinstance(result["scenarios"], dict)
    assert "site" in result["scenarios"]
    assert "by_wp" in result["scenarios"]
    # site scenarios = 4 키 만족
    for k in ("no_action", "optimistic_p25", "base_p50", "pessimistic_p75"):
        assert k in result["scenarios"]["site"]
    # s_curve = list[dict]
    assert isinstance(result["s_curve"], list)
    assert len(result["s_curve"]) > 0, "s_curve 빈 list — 실 SQL 미호출"
    assert isinstance(result["s_curve"][0], dict)


def test_fetch_degradation_cases_l7_5_filter():
    """C9 — l7_5_activity 인자 추가, 동일 activity 만 남김."""
    from pipeline.agents.optimizer.retrieve import fetch_degradation_cases

    metadatas = [
        {
            "company": "남웅",
            "l6_main": "방수공사",
            "l7_5_activity": "방수 시공",
            "unit": "m2",
            "today_qty": 10,
            "assigned_workers": 5,
            "conditions": "장비대기",
            "date": "2025-09-20",
            "worker_source": "synthetic_v2",
        },
        {
            "company": "남웅",
            "l6_main": "방수공사",
            "l7_5_activity": "방수 보수",
            "unit": "m2",
            "today_qty": 8,
            "assigned_workers": 4,
            "conditions": "장비대기",
            "date": "2025-09-20",
            "worker_source": "synthetic_v2",
        },
    ]
    documents = ["d1", "d2"]

    # 필터 없음 → 2 cases (같은 날짜 → 그룹핑되어 1 case 일 수도)
    no_filter = fetch_degradation_cases(
        metadatas,
        documents,
        "남웅",
        "방수공사",
        date(2025, 9, 25),
        "m2",
        100.0,
        n=10,
    )
    # 필터 = "방수 시공" → row1 만 (row2 제외)
    filtered = fetch_degradation_cases(
        metadatas,
        documents,
        "남웅",
        "방수공사",
        date(2025, 9, 25),
        "m2",
        100.0,
        n=10,
        l7_5_activity="방수 시공",
    )
    # 필터 후 documents 가 row1 ("d1") 만 포함
    if filtered:
        assert all("d1" in c.get("activities", []) for c in filtered)
        assert all("d2" not in c.get("activities", []) for c in filtered)
    # 필터 시 case 수 <= no_filter 의 case 수
    assert len(filtered) <= len(no_filter)


def test_group_baseline_l7_5_filter():
    """C9 — _group_baseline 의 l7_5_activity 필터."""
    from pipeline.agents.optimizer.retrieve import _group_baseline

    metadatas = [
        {
            "company": "남웅",
            "l6_main": "방수공사",
            "l7_5_activity": "방수 시공",
            "unit": "m2",
            "today_qty": 10,
            "assigned_workers": 2,
            "conditions": "",
        },
        {
            "company": "남웅",
            "l6_main": "방수공사",
            "l7_5_activity": "방수 보수",
            "unit": "m2",
            "today_qty": 8,
            "assigned_workers": 4,
            "conditions": "",
        },
    ]
    # 필터 없음: 평균 (10/2 + 8/4) / 2 = (5 + 2) / 2 = 3.5
    no_filter = _group_baseline(metadatas, "남웅", "방수공사", "m2")
    assert no_filter == 3.5
    # 필터 = "방수 시공": 10/2 = 5.0
    filtered = _group_baseline(metadatas, "남웅", "방수공사", "m2", l7_5_activity="방수 시공")
    assert filtered == 5.0


def test_backfill_jsonb_cols_has_9():
    """C10 — backfill_v2 의 _JSONB_COLS 가 9 컬럼 (optimizer_view/scenarios/s_curve 포함)."""
    from scripts.backfill_daily_report_views_v2 import _JSONB_COLS

    expected = {
        "kpi_jsonb",
        "productivity_jsonb",
        "contractor_bars_jsonb",
        "trade_bars_jsonb",
        "quadrant_jsonb",
        "wp_summary_jsonb",
        "optimizer_view_jsonb",
        "scenarios_jsonb",
        "s_curve_jsonb",
    }
    assert set(_JSONB_COLS) == expected, f"diff: {expected ^ set(_JSONB_COLS)}"
