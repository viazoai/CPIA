"""v10 프롬프트 상수 snapshot test — 의도된 키워드 + 한자 0건 검증."""

from __future__ import annotations

import re

from pipeline.agents.optimizer.prompt import (
    DIAG_PROMPT_V10,
    RECS_PROMPT_V10,
    SCENARIOS_PROMPT_V10,
)


def test_recs_prompt_has_keyword_schema():
    """RECS_PROMPT_V10 가 keyword + action + reason 3 필드 schema 명시."""
    assert "keyword" in RECS_PROMPT_V10
    assert "action" in RECS_PROMPT_V10
    assert "reason" in RECS_PROMPT_V10
    assert "5~10자" in RECS_PROMPT_V10  # keyword 가이드


def test_diag_prompt_g6_enhanced():
    """G6 강화 — risk_level=이상 시 '정상범주' 금지 명시."""
    assert "정상범주" in DIAG_PROMPT_V10  # 금지 표현 명시
    assert "risk_level" in DIAG_PROMPT_V10
    assert "절대 금지" in DIAG_PROMPT_V10 or "절대 룰" in DIAG_PROMPT_V10


def test_diag_prompt_delay_two_dimensions():
    """delay 두 차원 인용 강제."""
    assert "forward_delay_days" in DIAG_PROMPT_V10
    assert "point_in_time_delay_days" in DIAG_PROMPT_V10
    assert "두 차원" in DIAG_PROMPT_V10


def test_diag_prompt_mh_gap_inclusion():
    """mh_gap 자연 인용 가이드."""
    assert "mh_gap" in DIAG_PROMPT_V10
    assert "oversupply" in DIAG_PROMPT_V10 or "undersupply" in DIAG_PROMPT_V10


def test_diag_prompt_g8_trade_frame():
    """G8 공종 고유 가드."""
    assert "trade_frame" in DIAG_PROMPT_V10
    assert "공종" in DIAG_PROMPT_V10


def test_diag_prompt_no_kanji():
    """한자 0건."""
    found = re.findall(r"[一-鿿]", DIAG_PROMPT_V10)
    assert not found, f"한자 발견: {found}"


def test_diag_prompt_json_output():
    """출력 JSON {diagnosis: '...'} schema."""
    assert "diagnosis" in DIAG_PROMPT_V10


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


def test_scenarios_prompt_v10_g8():
    """G8 강화 — trade_frame 고유 회복 전략 명시."""
    assert "trade_frame" in SCENARIOS_PROMPT_V10
    assert "rationale" in SCENARIOS_PROMPT_V10
    assert "가드 8" in SCENARIOS_PROMPT_V10 or "G8" in SCENARIOS_PROMPT_V10


def test_scenarios_prompt_v10_no_generic_phrases():
    """일반론 금지 명시."""
    # "인력 보강 / 공정 가속 / 모니터링 강화" 일반론 금지 명시되어 있어야 함
    assert "일반론" in SCENARIOS_PROMPT_V10 or "단독 사용 금지" in SCENARIOS_PROMPT_V10


def test_scenarios_prompt_v10_categories():
    """공종 카테고리별 고유 수법 예시 명시."""
    for kw in ["골조", "외장", "토공", "마감", "포장"]:
        assert kw in SCENARIOS_PROMPT_V10, f"{kw} 예시 누락"


def test_scenarios_prompt_v10_no_kanji():
    """한자 0건."""
    found = re.findall(r"[一-鿿]", SCENARIOS_PROMPT_V10)
    assert not found, f"한자 발견: {found}"


def test_scenarios_prompt_v10_four_scenarios():
    """4 시나리오 정의 명시."""
    for sc in ["no_action", "optimistic", "base", "pessimistic"]:
        assert sc in SCENARIOS_PROMPT_V10, f"{sc} 시나리오 누락"
