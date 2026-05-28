"""Task 11 — SITE_SUMMARY_PROMPT_V10 + frame_category payload."""

from __future__ import annotations

import re

from pipeline.agents.optimizer.site_summary import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_V10,
    build_site_summary_payload,
)


def test_system_prompt_v10_has_frame_category_guard():
    """SYSTEM_PROMPT_V10 에 G8 가드 + frame_category 인용 명시."""
    assert "frame_category" in SYSTEM_PROMPT_V10
    assert "가드 8" in SYSTEM_PROMPT_V10 or "G8" in SYSTEM_PROMPT_V10
    assert "공종 고유" in SYSTEM_PROMPT_V10


def test_system_prompt_v10_no_generic_phrases():
    """일반론 금지 명시."""
    assert "일반론" in SYSTEM_PROMPT_V10 or "인력 재배치" in SYSTEM_PROMPT_V10


def test_system_prompt_v10_categories():
    """4 카테고리 고유 액션 예시 명시 (골조 / 외장 / 토공 / 마감)."""
    for kw in ["골조", "외장", "토공", "마감"]:
        assert kw in SYSTEM_PROMPT_V10, f"{kw} 누락"


def test_system_prompt_v10_no_kanji():
    """한자 0건."""
    found = re.findall(r"[一-鿿]", SYSTEM_PROMPT_V10)
    assert not found, f"한자 발견: {found}"


def test_system_prompt_preserved():
    """기존 SYSTEM_PROMPT 보존 (회귀 방지 — 다른 import 시 안전망)."""
    assert SYSTEM_PROMPT  # 그대로 존재
    assert SYSTEM_PROMPT != SYSTEM_PROMPT_V10  # 둘이 다름


def test_payload_has_frame_category():
    """build_site_summary_payload 의 top_risk_wps 에 frame_category 키 추가."""
    payload = build_site_summary_payload(
        report_date="2025-07-01",
        site_id="test",
        kpi={"delay_days": 5},
        scenarios={},
        wp_summary=[
            {
                "wp_id": "x",
                "wp_name": "철근콘크리트공사",
                "trade": "건축",
                "impact": 100,
                "l6_main": "철근콘크리트공사",
            }
        ],
        optimizer_view={"by_wp": {"x": {"diagnosis": "test", "recommendations": ["r1"]}}},
        s_curve=[],
    )
    assert payload["top_risk_wps"][0]["frame_category"] == "골조"


def test_payload_frame_category_fallback():
    """미등록 wp → frame_category = '일반' fallback."""
    payload = build_site_summary_payload(
        report_date="2025-07-01",
        site_id="test",
        kpi={"delay_days": 5},
        scenarios={},
        wp_summary=[
            {
                "wp_id": "x",
                "wp_name": "일반공조설비공사",
                "trade": "기계",
                "impact": 100,
                "l6_main": "일반공조설비공사",
            }
        ],
        optimizer_view={"by_wp": {"x": {"diagnosis": "test", "recommendations": ["r1"]}}},
        s_curve=[],
    )
    assert payload["top_risk_wps"][0]["frame_category"] == "일반"
