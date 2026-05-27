"""v10 프롬프트 상수 snapshot test — 의도된 키워드 + 한자 0건 검증."""

from __future__ import annotations

import re

from pipeline.agents.optimizer.prompt import RECS_PROMPT_V10


def test_recs_prompt_has_keyword_schema():
    """RECS_PROMPT_V10 가 keyword + action + reason 3 필드 schema 명시."""
    assert "keyword" in RECS_PROMPT_V10
    assert "action" in RECS_PROMPT_V10
    assert "reason" in RECS_PROMPT_V10
    assert "5~10자" in RECS_PROMPT_V10  # keyword 가이드


def test_recs_prompt_no_kanji():
    """RECS_PROMPT_V10 본문 한자 0건 (사용자 룰)."""
    found = re.findall(r"[一-鿿]", RECS_PROMPT_V10)
    assert not found, f"한자 발견: {found}"


def test_recs_prompt_g8_guard():
    """G8 공종 고유 인사이트 가드 + trade_frame 인용 요구."""
    assert "공종" in RECS_PROMPT_V10
    assert "trade_frame" in RECS_PROMPT_V10
    assert "G8" in RECS_PROMPT_V10  # 가드 명시


def test_recs_prompt_g6_guard():
    """G6 risk_level 강화 가드 (정상범주 금지)."""
    assert "정상범주" in RECS_PROMPT_V10
    assert "G6" in RECS_PROMPT_V10


def test_recs_prompt_action_categories():
    """G2 액션 6 카테고리 명시 (자원 투입 / 일정 조정 / 사전 점검 / 연쇄 알림 / 품질 검증 / 기록 강화)."""
    for cat in [
        "자원 투입",
        "일정·공정 조정",
        "사전 점검·조사",
        "연쇄 알림·협의",
        "품질·안전 검증",
        "기록·신호 강화",
    ]:
        assert cat in RECS_PROMPT_V10, f"{cat} 카테고리 누락"


def test_recs_prompt_weak_verbs_forbidden():
    """약한 동사 금지 명시 (G4)."""
    assert "확인 권장" in RECS_PROMPT_V10 or "확인 검토" in RECS_PROMPT_V10
    assert "지시하세요" in RECS_PROMPT_V10  # 강 동사 예시


def test_recs_prompt_json_output_schema():
    """출력 JSON schema 의 3 필드 (rank, keyword, action, reason) 명시."""
    assert "recommendations" in RECS_PROMPT_V10
    assert '"rank"' in RECS_PROMPT_V10
    assert '"keyword"' in RECS_PROMPT_V10
    assert '"action"' in RECS_PROMPT_V10
    assert '"reason"' in RECS_PROMPT_V10
