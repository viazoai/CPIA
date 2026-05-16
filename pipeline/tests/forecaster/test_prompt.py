"""Forecaster prompt.py 단위 테스트.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §8
"""

from __future__ import annotations

import json


from pipeline.agents.forecaster.prompt import (
    SYSTEM_PROMPT,
    FEW_SHOT_MESSAGES,
    build_llm_user_input,
)


def test_system_prompt_has_3step_structure():
    """system prompt 가 3 단계 reasoning 구조 명시."""
    assert "3 단계" in SYSTEM_PROMPT or "3단계" in SYSTEM_PROMPT
    assert "조건" in SYSTEM_PROMPT and "RAG" in SYSTEM_PROMPT


def test_system_prompt_has_json_schema():
    """system prompt 가 JSON 출력 schema 명시."""
    assert "reasoning" in SYSTEM_PROMPT
    assert "recovery_likelihood" in SYSTEM_PROMPT


def test_few_shot_messages_3_pairs():
    """3 few-shot = 3 (user, assistant) = 6 messages."""
    assert len(FEW_SHOT_MESSAGES) == 6


def test_few_shot_alternating_roles():
    """user, assistant 교차."""
    expected_roles = ["user", "assistant", "user", "assistant", "user", "assistant"]
    actual = [m["role"] for m in FEW_SHOT_MESSAGES]
    assert actual == expected_roles


def test_few_shot_normal_recovery_null():
    """정상 케이스 assistant output 의 recovery_likelihood = null."""
    normal_output = json.loads(FEW_SHOT_MESSAGES[1]["content"])
    assert normal_output["recovery_likelihood"] is None


def test_few_shot_caution_recovery_not_null():
    """주의 케이스 assistant output 의 recovery_likelihood ≠ null."""
    caution_output = json.loads(FEW_SHOT_MESSAGES[3]["content"])
    assert caution_output["recovery_likelihood"] is not None


def test_few_shot_severe_recovery_not_null():
    """이상 케이스 assistant output 의 recovery_likelihood ≠ null."""
    severe_output = json.loads(FEW_SHOT_MESSAGES[5]["content"])
    assert severe_output["recovery_likelihood"] is not None


def test_build_llm_user_input_structure():
    """build_llm_user_input 출력 구조 검증."""
    today = {
        "company": "세보엠이씨",
        "l6_main": "일반공조설비공사",
        "today_qty_by_unit": {"m": 80, "ea": 12},
        "today_assigned_workers": 401.4,
        "today_productivity": 0.1993,
        "conditions": ["맑음"],
        "work_content": "AHU 덕트 연결",
    }
    similar = [
        {
            "document": "AHU 덕트",
            "metadata": {"date": "2025-09-20", "productivity": 0.2, "conditions": ["맑음"]},
        },
    ]
    plan = {"plan_total_qty_by_unit": {"m": 6800}, "plan_mh_sum": 708154}

    result = build_llm_user_input(today, similar, plan, "정상")

    assert result["today"]["company"] == "세보엠이씨"
    assert result["today"]["conditions"] == ["맑음"]
    assert len(result["similar_cases"]) == 1
    assert result["similar_cases"][0]["date"] == "2025-09-20"
    assert result["plan"]["plan_mh_sum"] == 708154
    assert result["assessment_by_code"] == "정상"


def test_build_llm_user_input_no_plan():
    """plan=None → plan dict 빈 값."""
    today = {
        "company": "X",
        "l6_main": "Y",
        "today_qty_by_unit": {"m": 1},
        "today_assigned_workers": 1,
        "today_productivity": 1.0,
        "conditions": [],
        "work_content": "",
    }
    result = build_llm_user_input(today, [], None, "정상")
    assert result["plan"]["plan_mh_sum"] == 0
