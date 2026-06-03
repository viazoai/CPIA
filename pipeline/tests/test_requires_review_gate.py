"""이력기반 HIL 게이트 — compute_requires_review 단위 테스트.

5가지 케이스:
1. confident + 이력 있음 → 자동승인 (False)
2. 저신뢰 → HIL (True)
3. 신규 l7.5 (이력 없음) → HIL (True)
4. l7.5 미분류(None) → HIL (True)
5. user_corrected → 면제 (False)

드라이 테스트: LLM / DB 호출 없음.
"""

from __future__ import annotations

from pipeline.agents.mapper import compute_requires_review

HIST = {("철근콘크리트공사", "기초공사 : 거푸집 공사")}  # 시드 이력


def test_confident_with_history_auto():
    assert (
        compute_requires_review(
            "기초공사 : 거푸집 공사", "철근콘크리트공사", 0.99, HIST, 0.7, "auto_llm_rerank"
        )
        is False
    )


def test_low_conf_hil():
    assert (
        compute_requires_review(
            "기초공사 : 거푸집 공사", "철근콘크리트공사", 0.5, HIST, 0.7, "auto_llm_rerank"
        )
        is True
    )


def test_novel_l75_hil():
    assert compute_requires_review("2차 포장", "포장공사", 0.95, HIST, 0.7, "auto_llm_rerank") is True


def test_unclassified_hil():
    assert compute_requires_review(None, "외장판넬공사", 0.0, HIST, 0.7, "auto_llm_rerank") is True


def test_user_corrected_exempt():
    assert compute_requires_review(None, "외장판넬공사", 0.0, HIST, 0.7, "user_corrected") is False


from pipeline.graph import _apply_corrections


def test_apply_l75_remap_to_unclassified():
    mapped = [{"company": "A", "l6_main": "외장판넬공사", "l7_5_activity": "Glass Wool Panel 설치", "requires_review": True}]
    out = _apply_corrections(mapped, {0: {"wa": "FAB", "l6_main": "수장공사"}})  # l6 변경, l7.5 미지정
    assert out[0]["l7_5_activity"] is None  # 옛 l6 의 l7.5 무효화 → 미분류
    assert out[0]["mapping_source"] == "user_corrected" and out[0]["requires_review"] is False


def test_apply_l75_explicit():
    mapped = [{"company": "A", "l6_main": "수장공사", "l7_5_activity": None, "requires_review": True}]
    out = _apply_corrections(mapped, {0: {"wa": "CUB", "l6_main": "수장공사", "l7_5_activity": "경량벽체 설치"}})
    assert out[0]["l7_5_activity"] == "경량벽체 설치"


def test_apply_l75_key_present_none_explicit():
    """API 경로: l7_5_activity 키 있고 None + l6 변경 → 명시적 미분류."""
    mapped = [{"company": "A", "l6_main": "외장판넬공사", "l7_5_activity": "Old 항목", "requires_review": True}]
    out = _apply_corrections(mapped, {0: {"wa": "FAB", "l6_main": "수장공사", "l7_5_activity": None}})
    assert out[0]["l7_5_activity"] is None


def test_apply_l75_keep_when_l6_same_and_key_absent():
    """키 없음 + l6 동일 → 기존 l7.5 보존."""
    mapped = [{"company": "A", "l6_main": "수장공사", "l7_5_activity": "기존항목", "requires_review": True}]
    out = _apply_corrections(mapped, {0: {"wa": "CUB", "l6_main": "수장공사"}})  # 키 없음
    assert out[0]["l7_5_activity"] == "기존항목"
