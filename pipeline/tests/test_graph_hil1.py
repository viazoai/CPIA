"""HIL 1 node unit — review_needed 필터 + corrections 적용.

Spec: docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.1
"""

from __future__ import annotations

import asyncio

from pipeline.state import Activity


def _activity(
    idx: int,
    requires_review: bool,
    wa: str | None = "CUB",
    l6_main: str | None = "철근콘크리트공사",
    mapping_conf: float | None = 0.85,
    mapping_source: str = "auto_bp_single",
) -> Activity:
    """fixture helper — Activity TypedDict 19 키 모두 채움."""
    return {
        "wbs_activity_id": None,
        "l5_disc": "건축",
        "l6_main": l6_main,
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "trade": "철근콘크리트공사",
        "company": f"company_{idx}",
        "unit": "m3",
        "today_qty": 10.0,
        "work_content": f"work_{idx}",
        "conditions": ["맑음"],
        "assigned_workers": 5.0,
        "worker_source": "mh_prorated",
        "plan_total_qty": None,
        "plan_mh": None,
        "wa": wa,
        "mapping_conf": mapping_conf,
        "mapping_source": mapping_source,
        "requires_review": requires_review,
    }


def test_hil_1_node_no_review_passthrough() -> None:
    """모든 Activity 의 requires_review=False → interrupt 미발생, 통과."""
    from pipeline.graph import hil_1_node

    state = {"mapped": [_activity(0, False), _activity(1, False)]}
    result = asyncio.run(hil_1_node(state, cfg=None))
    assert result["hil_1_corrections"] == {}
    assert result["current_node"] == "hil_1"


def test_hil_1_node_review_needed_filter() -> None:
    """requires_review=True 인 Activity 만 review_needed payload 에 포함되는지 검증."""
    from pipeline.graph import _build_review_needed

    mapped = [
        _activity(0, False),
        _activity(1, True, mapping_conf=0.55, mapping_source="hil_required"),
        _activity(2, True, mapping_conf=0.62, mapping_source="hil_required"),
        _activity(3, False),
    ]
    review = _build_review_needed(mapped)
    assert len(review) == 2
    assert review[0]["idx"] == 1
    assert review[1]["idx"] == 2
    assert review[0]["mapping_conf"] == 0.55
    assert review[0]["mapping_source"] == "hil_required"
    assert review[0]["work_content"] == "work_1"
    assert review[0]["company"] == "company_1"


def test_hil_1_node_apply_corrections() -> None:
    """corrections dict (idx → {wa, l6_main}) 적용.

    Spec §5.1 #6:
    - 답한 row: wa/l6_main 수정 + mapping_source="user_corrected" + requires_review=False
    - 답 안 한 row (review_needed 였으나 corrections 에 없음): Mapper 추천 수용 +
      mapping_source="user_corrected" + requires_review=False
    """
    from pipeline.graph import _apply_corrections

    mapped = [
        _activity(0, False, wa="OLD"),
        _activity(1, True, wa="WRONG", mapping_source="hil_required"),
        _activity(2, True, wa="WRONG2", mapping_source="hil_required"),
    ]
    corrections = {1: {"wa": "CORRECTED_1", "l6_main": "철근콘크리트공사"}}
    out = _apply_corrections(mapped, corrections)
    # idx 0 — 영향 없음 (requires_review=False)
    assert out[0]["wa"] == "OLD"
    assert out[0]["requires_review"] is False
    # idx 1 — 사용자 정정
    assert out[1]["wa"] == "CORRECTED_1"
    assert out[1]["mapping_source"] == "user_corrected"
    assert out[1]["requires_review"] is False
    # idx 2 — corrections 에 없음 → Mapper 추천 그대로 수용
    assert out[2]["wa"] == "WRONG2"
    assert out[2]["mapping_source"] == "user_corrected"
    assert out[2]["requires_review"] is False
