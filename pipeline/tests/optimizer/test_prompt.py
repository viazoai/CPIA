"""Tests for optimizer prompt — spec §6.1 + §6.2 + §6.3 + §12.1.

3 unit:
1. test_system_prompt_korean_no_command_tone  # ★ C-Major 1 — "필수" 없음 검수 + 한자 0건
2. test_few_shot_messages_count_3
3. test_build_llm_user_input_includes_today_conditions  # F3
"""

from __future__ import annotations

import json


def test_system_prompt_korean_no_command_tone():
    """spec §6.1: 한글 + 명령형 회피 + 한자 0건. spec 예시 인용 시 한자 잔존 가능성 — 검수 보호."""
    from pipeline.agents.optimizer.prompt import SYSTEM_PROMPT

    # 한자 검수 (CJK U+4E00~U+9FFF)
    cjk_found = [ch for ch in SYSTEM_PROMPT if "一" <= ch <= "鿿"]
    assert not cjk_found, f"한자 발견: {cjk_found[:5]}"

    # 명령형 tone 회피
    for cmd in ("확인 필수", "반드시 ", "해야 합니다"):
        assert cmd not in SYSTEM_PROMPT, f"명령형 tone 발견: {cmd}"

    # 한글 포함 (단순 sanity)
    assert "권장" in SYSTEM_PROMPT or "권고" in SYSTEM_PROMPT


def test_few_shot_messages_count_3():
    """spec §6.2: FEW_SHOT_MESSAGES 정확히 3 pair (= 6 messages, role=user/assistant 번갈음)."""
    from pipeline.agents.optimizer.prompt import FEW_SHOT_MESSAGES

    # 3 pair = 6 messages
    assert len(FEW_SHOT_MESSAGES) == 6, f"FEW_SHOT_MESSAGES 길이 != 6: {len(FEW_SHOT_MESSAGES)}"

    # role 번갈음 (user, assistant, user, assistant, user, assistant)
    expected_roles = ["user", "assistant", "user", "assistant", "user", "assistant"]
    actual_roles = [m["role"] for m in FEW_SHOT_MESSAGES]
    assert actual_roles == expected_roles, f"role 시퀀스 불일치: {actual_roles}"

    # 각 message 는 dict 이며 content 필드 존재
    for i, m in enumerate(FEW_SHOT_MESSAGES):
        assert isinstance(m, dict), f"message {i} 가 dict 아님"
        assert "content" in m, f"message {i} 에 content 없음"
        # 한자 검수 — few-shot 본문 자체도 한자 0건 의무
        cjk_in_content = [ch for ch in m["content"] if "一" <= ch <= "鿿"]
        assert not cjk_in_content, f"FEW_SHOT[{i}] 한자 발견: {cjk_in_content[:5]}"


def test_build_llm_user_input_includes_today_conditions():
    """spec §6.3: build_llm_user_input output 의 today.today_conditions 가 forecast_row 값으로 채워짐."""
    from pipeline.agents.optimizer.prompt import build_llm_user_input

    forecast_row = {
        "company": "남웅건설",
        "l6_main": "철근콘크리트공사",
        "main_unit": "m3",
        "assessment": "이상",
        "today_productivity": 0.45,
        "today_conditions": "맑음,장비대기",
    }
    degradation_cases = [
        {
            "date": "2025-09-22",
            "conditions": "맑음,장비대기",
            "productivity": 12.47,
            "activities": ["기초공사 : 거푸집 공사"],
            "recovery": {
                "recovery_days": 1,
                "trajectory": [
                    {"date": "2025-09-23", "conditions": "맑음", "productivity": 15.42, "recovered": True}
                ],
            },
        },
    ]

    out = build_llm_user_input(forecast_row, degradation_cases)

    # today block
    assert "today" in out
    assert out["today"]["company"] == "남웅건설"
    assert out["today"]["l6_main"] == "철근콘크리트공사"
    assert out["today"]["main_unit"] == "m3"
    assert out["today"]["assessment"] == "이상"
    assert out["today"]["today_productivity"] == 0.45
    # 핵심: today_conditions 가 박혀있음
    assert out["today"]["today_conditions"] == "맑음,장비대기"

    # degradation_cases block — recovery 가 recovery_days + trajectory 로 flatten
    assert "degradation_cases" in out
    assert len(out["degradation_cases"]) == 1
    case0 = out["degradation_cases"][0]
    assert case0["date"] == "2025-09-22"
    assert case0["conditions"] == "맑음,장비대기"
    assert case0["productivity"] == 12.47
    assert case0["activities"] == ["기초공사 : 거푸집 공사"]
    assert case0["recovery_days"] == 1
    assert case0["trajectory"] == [
        {"date": "2025-09-23", "conditions": "맑음", "productivity": 15.42, "recovered": True}
    ]

    # JSON serialize 가능 검증 (spec §6.2 와 동일 형식)
    s = json.dumps(out, ensure_ascii=False)
    assert "맑음,장비대기" in s


def test_build_llm_user_input_empty_degradation_cases():
    """spec §6.3: degradation_cases=[] 일 때도 builder 가 안전하게 동작 (cold start signal)."""
    from pipeline.agents.optimizer.prompt import build_llm_user_input

    forecast_row = {
        "company": "남웅건설",
        "l6_main": "철근콘크리트공사",
        "main_unit": "m3",
        "today_productivity": 20.0,
        "today_conditions": "맑음",
        "assessment": "정상",
    }
    result = build_llm_user_input(forecast_row, degradation_cases=[])

    # cold_start path: builder 가 KeyError 없이 안전 처리 + degradation_cases 빈 list 반환
    assert "today" in result
    assert "degradation_cases" in result
    assert result["degradation_cases"] == []
    # today block 은 forecast_row 값으로 정상 채워짐
    assert result["today"]["company"] == "남웅건설"
    assert result["today"]["today_conditions"] == "맑음"

    # builder output 이 JSON serializable (spec §6.2 와 동일 형식)
    s = json.dumps(result, ensure_ascii=False)
    assert "남웅건설" in s
