"""v10 프롬프트 상수 snapshot test — 의도된 키워드 + 한자 0건 검증."""

from __future__ import annotations

import re

from pipeline.agents.optimizer.prompt import (
    DIAG_PROMPT_V10,
    RECS_PROMPT_V10,
    SCENARIOS_PROMPT_V10,
    build_diag_input_v10,
    build_recs_input_v10,
    build_scenarios_input_v10,
)

_SAMPLE_ROW = {
    "company": "남웅건설",
    "l6_main": "철근콘크리트공사",
    "main_unit": "ea",
    "assessment": "주의",
    "risk_level": "이상",
    "today_productivity": 0.5,
    "today_conditions": "정상",
    "delay_days": 7,
    "point_in_time_delay_days": 5,
    "mh_gap": 12.3,
}

_SAMPLE_CASE = {
    "date": "2025-06-28",
    "conditions": "우천",
    "productivity": 0.3,
    "activities": ["타설 중단"],
    "recovery": {"recovery_days": 3, "trajectory": []},
}


def test_build_recs_input_v10_has_all_required_fields():
    """recs payload — today + trade_frame + degradation_cases 필수 필드."""
    out = build_recs_input_v10(_SAMPLE_ROW, [_SAMPLE_CASE], "2025-07-01", "골조", "골조 frame text")
    assert out["today"]["frame_category"] == "골조"
    assert out["today"]["forward_delay_days"] == 7
    assert out["today"]["point_in_time_delay_days"] == 5
    assert out["today"]["mh_gap"] == 12.3
    assert out["today"]["risk_level"] == "이상"
    assert out["trade_frame"] == "골조 frame text"
    assert len(out["degradation_cases"]) == 1
    assert out["degradation_cases"][0]["recovery_days"] == 3


def test_build_diag_input_v10_includes_recs_out():
    """diag payload — recs 결과 포함."""
    recs = [{"rank": 1, "keyword": "양생 병렬화", "action": "지시", "reason": "trade frame 인용"}]
    out = build_diag_input_v10(_SAMPLE_ROW, [_SAMPLE_CASE], "2025-07-01", "골조", "골조 frame text", recs)
    assert out["recommendations"] == recs
    assert out["trade_frame"] == "골조 frame text"
    assert out["today"]["frame_category"] == "골조"


def test_build_scenarios_input_v10_has_trade_frame():
    """scenarios payload — wp + trade_frame + recovery_distribution."""
    out = build_scenarios_input_v10(
        _SAMPLE_ROW,
        no_action_ec="2025-12-30",
        recovery_distribution={"p50": 5},
        degradation_cases=[_SAMPLE_CASE],
        frame_category="골조",
        frame_text="골조 frame text",
    )
    assert out["wp"]["frame_category"] == "골조"
    assert out["trade_frame"] == "골조 frame text"
    assert out["no_action_expected_completion"] == "2025-12-30"
    assert out["recovery_distribution"] == {"p50": 5}
    assert len(out["degradation_cases"]) == 1


def test_build_recs_input_v10_empty_cases():
    """RAG cold (cases 빈 array) — degradation_cases = [], 다른 필드 정상."""
    out = build_recs_input_v10(_SAMPLE_ROW, [], "2025-07-01", "외장", "외장 frame")
    assert out["degradation_cases"] == []
    assert out["today"]["frame_category"] == "외장"


def test_build_recs_input_v10_missing_optional_fields():
    """forecast_row 에 일부 optional 필드 누락 → KeyError 없음 (defensive)."""
    minimal = {
        "company": "co",
        "l6_main": "wp",
        # main_unit, assessment, risk_level, today_productivity 등 미포함
    }
    out = build_recs_input_v10(minimal, [], "2025-07-01", "일반", "일반 frame")
    assert out["today"]["main_unit"] is None
    assert out["today"]["forward_delay_days"] is None
    assert out["today"]["mh_gap"] is None


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


def test_diag_prompt_recovery_pattern():
    """2026-05-29: 개조식 진단 — 회복 패턴 판단 + 분기점 (수치 prefix 는 view_builder 가 붙임)."""
    assert "개조식" in DIAG_PROMPT_V10
    assert "회복 패턴" in DIAG_PROMPT_V10
    assert "분기점" in DIAG_PROMPT_V10


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


def test_recs_prompt_keyword_guide():
    """2026-05-29: keyword 명사구 가이드 + 대괄호 금지 + 권고 2~3건 (사용자 요청)."""
    assert "대괄호" in RECS_PROMPT_V10  # keyword 에 [] 넣지마 (UI 가 감쌈)
    assert "2~3건" in RECS_PROMPT_V10  # Action Plan 건수
    assert "조치 요약" in RECS_PROMPT_V10


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
