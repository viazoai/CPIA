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
    """G6 강화 — 위험도 '이상' 시 '정상범주' 금지 명시 (2026-06: 현장여건 1줄 재설계)."""
    assert "정상범주" in DIAG_PROMPT_V10  # 금지 표현 명시
    assert "위험도" in DIAG_PROMPT_V10


def test_diag_prompt_forbids_manhour_absolute():
    """2026-06 재설계: delay 두 차원은 결정론 line 1 로 이관 — LLM 현장여건엔 인시 절대수치 금지."""
    assert "인시" in DIAG_PROMPT_V10
    assert "절대수치" in DIAG_PROMPT_V10


def test_diag_prompt_natural_narrative():
    """2026-06-10 (A) 재설계: 자연 서술 2~3문장 — 회복 패턴 + 오늘의 관건."""
    assert "2~3문장" in DIAG_PROMPT_V10
    assert "서술체" in DIAG_PROMPT_V10
    assert "회복 패턴" in DIAG_PROMPT_V10  # 작성 관점 1
    assert "관건" in DIAG_PROMPT_V10       # 작성 관점 2
    # 전보식 명사 종결은 금지로 명시
    assert "전보식" in DIAG_PROMPT_V10


def test_diag_prompt_g8_trade_frame():
    """G8 공종 고유 신호 가드 — trade_frame 제약 연결 요구."""
    assert "trade_frame" in DIAG_PROMPT_V10
    assert "trade_frame 제약" in DIAG_PROMPT_V10


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
    assert "강한 행위 동사" in RECS_PROMPT_V10  # 강 동사 권유체로 풀어쓰기


def test_recs_prompt_natural_tone():
    """2026-06-10 (A): action/reason 자연 권유·서술체 + 내부용어 누출 차단."""
    assert "권유체" in RECS_PROMPT_V10
    assert "권합니다" in RECS_PROMPT_V10  # action 종결 예시
    assert "때문입니다" in RECS_PROMPT_V10  # reason 종결 예시
    # 'trade_frame'·공종 분류명 본문 노출 금지
    assert "내부 용어" in RECS_PROMPT_V10


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


# ───────────────────────── 2026-06-10 (A+C) 브리핑 ─────────────────────────

from pipeline.agents.optimizer.prompt import (  # noqa: E402
    BRIEFING_PROMPT,
    MIGRATION_POLISH_PROMPT,
    build_briefing_input,
)


def test_briefing_prompt_schema_and_tone():
    """BRIEFING_PROMPT — 3~4문장 한 단락 서술체 + briefing JSON 출력."""
    assert "3~4문장" in BRIEFING_PROMPT
    assert "한 단락" in BRIEFING_PROMPT
    assert "전망입니다" in BRIEFING_PROMPT  # 서술체 종결 예시
    assert '"briefing"' in BRIEFING_PROMPT or "briefing" in BRIEFING_PROMPT
    # 새 수치 환각 금지
    assert "지어내지" in BRIEFING_PROMPT


def test_briefing_prompt_no_kanji():
    found = re.findall(r"[一-鿿]", BRIEFING_PROMPT)
    assert not found, f"한자 발견: {found}"


def test_build_briefing_input_shape():
    """build_briefing_input — 필수 facts 키 + recommendations 요약 정규화."""
    out = build_briefing_input(
        wp_label="장평건설 · 배수 공사",
        condition="자재미입고",
        today_level="1.02 m/인",
        plan_level="1.44 m/인",
        schedule_impact="30일 지연",
        schedule_basis="현황 페이스 기준 완공 약 30일 지연 — AI 만회 시 3일 단축",
        recovery_pattern="5건 중 3건 회복 | D+1 회복 3건",
        ai_recovery_days=3,
        recommendations=[{"keyword": "계측 기준선 점검", "action": "긴 액션 텍스트", "reason": "사유"}],
    )
    assert out["wp"] == "장평건설 · 배수 공사"
    assert out["schedule_impact"] == "30일 지연"
    assert out["ai_recovery_days"] == 3
    assert out["today_vs_plan"]["today"] == "1.02 m/인"
    # recommendations 는 keyword+action 만 (reason 은 브리핑에 불필요 → 미전달)
    assert out["recommendations"] == [{"keyword": "계측 기준선 점검", "action": "긴 액션 텍스트"}]


def test_build_briefing_input_handles_string_recs():
    """옛 string 권고 — action 만 담은 dict 로 정규화."""
    out = build_briefing_input(wp_label="A · B", recommendations=["타워크레인 확인"])
    assert out["recommendations"] == [{"action": "타워크레인 확인"}]


def test_build_briefing_input_defaults_none():
    """optional 미지정 시 None — KeyError 없음."""
    out = build_briefing_input(wp_label="A · B")
    assert out["today_condition"] is None
    assert out["ai_recovery_days"] is None
    assert out["recommendations"] == []


def test_migration_polish_prompt_dual_output():
    """MIGRATION_POLISH_PROMPT — briefing + recommendations 둘 다 출력, keyword 보존 명시."""
    assert '"briefing"' in MIGRATION_POLISH_PROMPT
    assert '"recommendations"' in MIGRATION_POLISH_PROMPT
    assert "보존" in MIGRATION_POLISH_PROMPT  # keyword·사실 보존
    assert "권합니다" in MIGRATION_POLISH_PROMPT


def test_migration_polish_prompt_no_kanji():
    found = re.findall(r"[一-鿿]", MIGRATION_POLISH_PROMPT)
    assert not found, f"한자 발견: {found}"
