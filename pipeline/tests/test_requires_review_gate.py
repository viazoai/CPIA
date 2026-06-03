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
