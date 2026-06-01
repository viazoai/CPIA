"""Phase 1 view_builder v2 helper 단위 테스트.

helper 단위 검증 (_simulate_today_qty noise 분포 테스트는 Task 4.1 실 qty 전환으로 폐기).
"""

from __future__ import annotations

import pytest

from pipeline.agents.optimizer.view_builder import (
    _compute_daily_quota,
    _compute_productivity,
    _make_display_label,
    _normalize_impact,
    _normalize_impact_share,
    _weighted_median,
)


def test_daily_quota_from_master():
    """plan_total_qty=100, total_days=10 -> daily=10.0."""
    assert _compute_daily_quota(100.0, 10) == pytest.approx(10.0)
    assert _compute_daily_quota(100.0, 0) == 0.0
    assert _compute_daily_quota(0.0, 5) == 0.0


def test_productivity_calc():
    """perperson / master_perperson * 100."""
    assert _compute_productivity(perperson=5.0, master_perperson=5.0) == pytest.approx(100.0)
    assert _compute_productivity(perperson=4.0, master_perperson=5.0) == pytest.approx(80.0)
    assert _compute_productivity(perperson=5.0, master_perperson=0) == 0.0
    assert _compute_productivity(perperson=5.0, master_perperson=-1) == 0.0


def test_weighted_median_basic():
    """wv 가중 누적 50% 지점."""
    assert _weighted_median([10, 20, 30], [1, 1, 1]) == 20
    assert _weighted_median([10, 20, 30], [1, 10, 1]) == 20
    assert _weighted_median([], []) == 0
    # weights 합 0 -> 단순 평균 fallback
    assert _weighted_median([10, 20, 30], [0, 0, 0]) == pytest.approx(20.0)


def test_normalize_impact_share_and_scalar_coexist():
    """A3: _normalize_impact_share — share-of-total (합=100%). 기존 scalar _normalize_impact 와 coexist."""
    # share-of-total: 100+200+300=600 → [16.67, 33.33, 50.0]
    shares = _normalize_impact_share([100, 200, 300])
    assert shares == pytest.approx([16.67, 33.33, 50.0], abs=0.01)
    assert sum(shares) == pytest.approx(100.0, abs=0.01)
    assert _normalize_impact_share([]) == []
    assert _normalize_impact_share([0, 0, 0]) == [0.0, 0.0, 0.0]
    # 기존 scalar 2-arg 함수 (_normalize_impact) 는 그대로 유지 (coexist 검증)
    assert _normalize_impact(100.0, 200.0) == pytest.approx(50.0)


def test_display_label_format():
    """'98.9% (3.20 ton/인)' 형식 — perperson/unit 있으면 풀, 없으면 % 만."""
    assert _make_display_label(98.9, 3.2, "ton") == "98.9% (3.20 ton/인)"
    assert _make_display_label(81.3, 0.06, "m2") == "81.3% (0.06 m2/인)"
    assert _make_display_label(50, None, None) == "50.0%"
    assert _make_display_label(50, 1.5, None) == "50.0%"
    assert _make_display_label(50, None, "ton") == "50.0%"


# ─── Integration test (real PG, 9-25 prototype) ───

from datetime import date  # noqa: E402

from pipeline.agents.optimizer.view_builder import (  # noqa: E402
    _build_productivity_views_v2,
)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_build_productivity_views_v2_9_25(pg_client):
    """9-25 prototype 적용된 mapper_activities + master 위에서 산식 검증.
    Phase B/C/D 가 530일 적용된 상태. 9-25 site_id m15x-ph3-ibl."""
    result = await _build_productivity_views_v2(
        pg=pg_client,
        site_id="m15x-ph3-ibl",
        today=date(2025, 9, 25),
    )
    # 구조
    for key in ["kpi", "productivity", "contractor_bars", "trade_bars", "quadrant", "wp_summary"]:
        assert key in result
    # KPI
    assert result["kpi"]["productivity_today"] > 0
    assert result["kpi"]["productivity_today"] <= 150
    assert "productivity_today_display" in result["kpi"]
    # 모든 row 에 display_label
    assert len(result["contractor_bars"]) > 0
    for b in result["contractor_bars"]:
        assert "display_label" in b
    assert len(result["trade_bars"]) > 0
    for b in result["trade_bars"]:
        assert "display_label" in b
    assert len(result["quadrant"]) > 0
    for q in result["quadrant"]:
        assert "display_label" in q
        assert q["productivity"] >= 0 and q["productivity"] <= 150
    assert len(result["wp_summary"]) > 0
    for w in result["wp_summary"]:
        assert "display_label" in w


@pytest.mark.asyncio
@pytest.mark.integration
async def test_build_productivity_views_v2_empty(pg_client):
    """plan 기간 밖 일자 -> empty dict 구조."""
    result = await _build_productivity_views_v2(
        pg=pg_client,
        site_id="m15x-ph3-ibl",
        today=date(2020, 1, 1),  # 데이터 전혀 없음
    )
    assert result["kpi"] == {}
    assert result["contractor_bars"] == []
    assert result["wp_summary"] == []


def test_augment_history_if_sparse():
    """그룹 row < min_count 면 동일 l6 다른 company 에서 augment."""
    from pipeline.agents.optimizer.view_builder import _augment_history_if_sparse

    items = [
        {"company": "광건", "l6_main": "수장공사", "v": 1},
        {"company": "신성", "l6_main": "수장공사", "v": 10},
        {"company": "신성", "l6_main": "수장공사", "v": 11},
        {"company": "신성", "l6_main": "수장공사", "v": 12},
        {"company": "신성", "l6_main": "수장공사", "v": 13},
    ] + [{"company": "OTIS", "l6_main": "승강기", "v": i} for i in range(6)]
    aug = _augment_history_if_sparse(items, min_count=5)
    # 광건 수장공사 row + augmented 4 = 5 (원본 1건 그대로 + 4개 augment)
    kw = [a for a in aug if a["company"] == "광건"]
    augmented = [a for a in kw if a.get("metadata", {}).get("augmented")]
    assert len(augmented) >= 4
    for a in augmented:
        assert "augmented_from_company" in a["metadata"]
        assert a["metadata"]["augmented_from_company"] == "신성"


# ─── Task 11 cold_start + augmentation weight ───


def test_apply_augmentation_weight():
    """augmented=True row -> 0.5, 일반 -> 1.0."""
    from pipeline.agents.optimizer.agent import _apply_augmentation_weight

    rows = [
        {"metadata": {"augmented": True}, "v": 1},
        {"metadata": {}, "v": 2},
        {"metadata": {"augmented": False}, "v": 3},
        {"v": 4},  # metadata 없음
    ]
    w = _apply_augmentation_weight(rows)
    assert w[0][1] == 0.5
    assert w[1][1] == 1.0
    assert w[2][1] == 1.0
    assert w[3][1] == 1.0


# ─── Task 12 atomizer 가독 형식 ───


def test_atomizer_format_document_live_mode():
    """live (perperson=None) -> 짧은 형식 (마스터 비교값 없음)."""
    from pipeline.agents.atomizer import _format_document

    a = {
        "company": "광건",
        "l6_main": "수장공사",
        "l7_5_activity": "풍도벽체 설치",
        "today_qty": 15,
        "unit": "m2",
        "assigned_workers": 265,
        "conditions": [],
    }
    doc = _format_document(a, date="2025-09-25")
    assert "광건" in doc
    assert "수장공사" in doc
    assert "풍도벽체 설치" in doc
    assert "15.0 m2" in doc
    assert "265 명" in doc
    assert "정상" in doc
    assert "/인" not in doc
    assert "%" not in doc


def test_atomizer_format_document_backfill_mode():
    """backfill (perperson + productivity_pct) -> 풀 형식."""
    from pipeline.agents.atomizer import _format_document

    a = {
        "company": "광건",
        "l6_main": "수장공사",
        "l7_5_activity": "풍도벽체 설치",
        "today_qty": 15,
        "unit": "m2",
        "assigned_workers": 265,
        "conditions": [],
    }
    doc = _format_document(a, date="2025-09-25", perperson=0.06, productivity_pct=98.9)
    assert "0.06 m2/인" in doc
    assert "98.9%" in doc


def test_atomizer_build_metadata_has_new_fields():
    """metadata 에 l7_5_activity + perperson + productivity_pct."""
    from pipeline.agents.atomizer import _build_metadata

    a = {
        "company": "광건",
        "l5_disc": "건축",
        "l6_main": "수장공사",
        "wa": "FAB",
        "unit": "m2",
        "today_qty": 15.0,
        "assigned_workers": 265.0,
        "worker_source": "mh_prorated",
        "mapping_conf": 1.0,
        "conditions": [],
        "l7_5_activity": "풍도벽체 설치",
        "perperson": 0.06,
        "productivity_pct": 98.9,
    }
    md = _build_metadata(a, date="2025-09-25", run_id="test-run")
    assert md["l7_5_activity"] == "풍도벽체 설치"
    assert md["perperson"] == 0.06
    assert md["productivity_pct"] == 98.9


def test_atomizer_build_metadata_live_placeholders():
    """live 시점 (perperson 키 없음) -> 0 placeholder."""
    from pipeline.agents.atomizer import _build_metadata

    a = {
        "company": "광건",
        "l5_disc": "건축",
        "l6_main": "수장공사",
        "wa": "FAB",
        "unit": "m2",
        "today_qty": 15.0,
        "assigned_workers": 265.0,
        "worker_source": "mh_prorated",
        "mapping_conf": 1.0,
        "conditions": [],
    }
    md = _build_metadata(a, date="2025-09-25", run_id="test-run")
    assert md["perperson"] == 0.0
    assert md["productivity_pct"] == 0.0
    assert md["l7_5_activity"] == ""
