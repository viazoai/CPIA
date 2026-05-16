"""Forecaster prompt — system + few-shot 3 + user input builder.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §8
"""

from __future__ import annotations

import json
from typing import Any, Optional


SYSTEM_PROMPT = """당신은 건설 현장 생산성 분석 전문가다.
주어진 오늘 실적·과거 유사 사례·자동 분류 결과를 바탕으로 reasoning 1~2 문장을 작성한다.

reasoning 의 3 단계 구조 (필수):
  1. 오늘 조건 명시 — 날씨, conditions, work_content 요지
  2. RAG 비교 — 유사 N건 평균 대비 X% (assessment 결정 근거)
  3. 원인 추론 — work_content 텍스트 분석. 정상 시 생략 가능.

출력 schema (JSON):
  {
    "reasoning": str,
    "recovery_likelihood": float (0.0~1.0) | null
  }

규칙:
  - reasoning 은 입력의 assessment 와 정합되어야 한다 (분류 결과를 뒤집지 말 것)
  - assessment = "정상" → recovery_likelihood = null
  - recovery_likelihood = RAG 유사 사례에서 다음날 회복한 비율 추정
"""


_FEW_SHOT_1_INPUT = {
    "today": {
        "company": "Y건설",
        "l6_main": "거푸집공사",
        "today_productivity": 22.9,
        "conditions": ["우천", "병행작업"],
        "work_content": "FAB 2층 벽체 거푸집",
    },
    "similar_cases": [
        {"date": "2025-09-10", "productivity": 21.3, "conditions": ["우천"], "work_content": "벽체 거푸집"}
    ],
    "plan": {"plan_total_qty_by_unit": {"m2": 12000}, "plan_mh_sum": 84000},
    "assessment_by_code": "정상",
}
_FEW_SHOT_1_OUTPUT = {
    "reasoning": "오늘 우천 + 병행작업 있음. 유사 우천일 평균 21.3 m2/인 대비 +8%. 정상 변동 범위, 별도 원인 없음.",
    "recovery_likelihood": None,
}

_FEW_SHOT_2_INPUT = {
    "today": {
        "company": "세보엠이씨",
        "l6_main": "일반공조설비공사",
        "today_productivity": 0.14,
        "conditions": ["맑음"],
        "work_content": "AHU 덕트 + 자재 미입고 일부",
    },
    "similar_cases": [
        {"date": "2025-09-20", "productivity": 0.18, "conditions": ["맑음"], "work_content": "AHU 덕트"}
    ],
    "plan": {"plan_total_qty_by_unit": {"m": 6800}, "plan_mh_sum": 708154},
    "assessment_by_code": "주의",
}
_FEW_SHOT_2_OUTPUT = {
    "reasoning": "맑음, 병행작업 없음. 유사 5건 평균 0.18 m/인 대비 -22%. work_content 에 '자재 미입고' 기재 — 단기 회복 가능성.",
    "recovery_likelihood": 0.7,
}

_FEW_SHOT_3_INPUT = {
    "today": {
        "company": "남웅건설",
        "l6_main": "철근콘크리트공사",
        "today_productivity": 1.8,
        "conditions": ["맑음"],
        "work_content": "타워크레인 대기로 오전 작업 지연",
    },
    "similar_cases": [
        {"date": "2025-09-15", "productivity": 2.6, "conditions": ["맑음"], "work_content": "철근 조립"}
    ],
    "plan": {"plan_total_qty_by_unit": {"ton": 500}, "plan_mh_sum": 50000},
    "assessment_by_code": "이상",
}
_FEW_SHOT_3_OUTPUT = {
    "reasoning": "맑음, 병행작업 없음. 유사 5건 평균 2.6 ton/인 대비 -31%. work_content 에 '타워크레인 대기' 기재 — 장비 스케줄 충돌 가능성.",
    "recovery_likelihood": 0.8,
}


# reviewer #8: ensure_ascii=False 는 한글 (한자 X) 출력을 위함.
# 사용자 전역 CLAUDE.md "No 한자" 룰은 CJK ideograph 금지이며 한글은 허용.
FEW_SHOT_MESSAGES: list[dict[str, str]] = [
    {"role": "user", "content": json.dumps(_FEW_SHOT_1_INPUT, ensure_ascii=False)},
    {"role": "assistant", "content": json.dumps(_FEW_SHOT_1_OUTPUT, ensure_ascii=False)},
    {"role": "user", "content": json.dumps(_FEW_SHOT_2_INPUT, ensure_ascii=False)},
    {"role": "assistant", "content": json.dumps(_FEW_SHOT_2_OUTPUT, ensure_ascii=False)},
    {"role": "user", "content": json.dumps(_FEW_SHOT_3_INPUT, ensure_ascii=False)},
    {"role": "assistant", "content": json.dumps(_FEW_SHOT_3_OUTPUT, ensure_ascii=False)},
]


def build_llm_user_input(
    today: dict,
    similar_cases: list[dict],
    plan: Optional[dict],
    assessment: str,
) -> dict[str, Any]:
    """system + 3 few-shot 은 const. 본 함수는 user message JSON 만 생성."""
    return {
        "today": {
            "company": today["company"],
            "l6_main": today["l6_main"],
            "today_qty_by_unit": today["today_qty_by_unit"],
            "today_assigned_workers": today["today_assigned_workers"],
            "today_productivity": round(today["today_productivity"], 4),
            "conditions": today["conditions"],
            "work_content": today["work_content"],
        },
        "similar_cases": [
            {
                "date": c["metadata"]["date"],
                "productivity": round(c["metadata"]["productivity"], 4),
                "conditions": c["metadata"]["conditions"],
                "work_content": c["document"][:80],
            }
            for c in similar_cases
        ],
        "plan": {
            "plan_total_qty_by_unit": plan["plan_total_qty_by_unit"] if plan else {},
            "plan_mh_sum": plan["plan_mh_sum"] if plan else 0,
        },
        "assessment_by_code": assessment,
    }
