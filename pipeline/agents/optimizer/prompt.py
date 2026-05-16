"""Optimizer prompt — SYSTEM_PROMPT + FEW_SHOT_MESSAGES + build_llm_user_input.

Spec: docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §6.1 + §6.2 + §6.3

원칙:
- SYSTEM_PROMPT 는 한글 + 영어만 (한자 0건).
- 명령형 tone ("확인 필수" / "반드시" / "해야 합니다") 회피 — 선택지 제시 형식 ("권장" / "권고" / "검토 권장").
- FEW_SHOT_MESSAGES 는 OpenAI ChatCompletion 표준 (user/assistant 페어 3건 = 6 messages).
- conditions 는 comma-joined str (atomizer 결정 #19 / 본 cycle 결정 통일).
"""

from __future__ import annotations

import json


# ---------------------------------------------------------------------------
# §6.1 SYSTEM_PROMPT
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """당신은 건설 현장 생산성 진단 + 회복 패턴 분석 전문가입니다.

PM 이 선택한 공종에 대해, 과거 유사 저하 케이스 5건 + 각 case 의 회복 trajectory 를 받습니다.

임무:
1. 오늘 저하 원인 진단 (1~2 문장, 작업 내용 텍스트에서 근거 추론)
2. PM 에게 제시할 권고사항 (ranked list 3~4건, 선택지 제시 형식)

권고사항 tone:
  - "확인 권장" / "검토 권고" / "고려 필요" — 선택지 제시
  - 단정형 / 강제형 표현 회피 (선택지 제시 형식 유지)
  - 1순위 = 즉시 검토 권장 (예: "타워크레인 스케줄 확인 권장")
  - 2순위 = 과거 회복 패턴 기반 예상 (예: "D+1 60% 자연 복귀 가능성 — 즉시 대응 불필요할 수 있음")
  - 3순위 = 잔여 물량 기준 만회 예상 (예: "D+3 이내 정상화 시 공기 영향 미미")
  - 4순위 = D+N 초과 시 대안 검토 (예: "D+3 초과 시 야간 연장 또는 주말 투입 검토 권고")

원칙:
- 최종 판단 및 실행은 PM 결정 사항. 권고는 근거 기반 선택지 제시.
- 수치 계산 (인원 재배치 명령 등) 금지. 맥락 기반 조언만.
- 한자 사용 금지 (한글 + 영어).
- `recovery_distribution` 은 코드단에서 산출되어 제공됨 — 참고만, 본인이 직접 세지 말 것.
- activities (degradation_cases.activities) 는 단순 활동명 (예: "기초공사 : 거푸집 공사"). 조건/야간/돌관 정보는 today.today_conditions + 각 case 의 conditions 메타 (예: "맑음,장비대기") 에 박혀 있음. 둘 다 보고 진단.

출력 형식 (JSON):
{
  "diagnosis": "...",
  "recommendations": [
    {"rank": 1, "text": "..."},
    {"rank": 2, "text": "..."}
  ]
}

(recovery_distribution 은 코드단 추가, 본 응답에 포함 불필요.)
"""


# ---------------------------------------------------------------------------
# §6.2 FEW_SHOT_MESSAGES — 3 회복 패턴 sample (user/assistant 페어)
# ---------------------------------------------------------------------------

FEW_SHOT_MESSAGES = [
    # 1: 장비대기 D+1 우세 회복 (spec §6.2 원본)
    {
        "role": "user",
        "content": json.dumps(
            {
                "today": {
                    "company": "남웅건설",
                    "l6_main": "철근콘크리트공사",
                    "main_unit": "m3",
                    "assessment": "이상",
                    "today_productivity": 0.45,
                    "today_conditions": "맑음,장비대기",
                },
                "degradation_cases": [
                    {
                        "date": "2025-09-22",
                        "conditions": "맑음,장비대기",
                        "productivity": 12.47,
                        "activities": ["기초공사 : 거푸집 공사"],
                        "recovery_days": 1,
                        "trajectory": [
                            {
                                "date": "2025-09-23",
                                "conditions": "맑음",
                                "productivity": 15.42,
                                "recovered": True,
                            }
                        ],
                    },
                    {
                        "date": "2025-09-06",
                        "conditions": "맑음,장비대기",
                        "productivity": 10.51,
                        "activities": ["RC Wall & Column 공사 : 철근 조립"],
                        "recovery_days": 1,
                        "trajectory": [
                            {
                                "date": "2025-09-07",
                                "conditions": "맑음",
                                "productivity": 16.17,
                                "recovered": True,
                            },
                            {
                                "date": "2025-09-08",
                                "conditions": "우천",
                                "productivity": 13.11,
                                "recovered": False,
                            },
                        ],
                    },
                ],
            },
            ensure_ascii=False,
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps(
            {
                "diagnosis": "장비 대기로 인한 저하 (추정). 타워크레인 스케줄 충돌 가능성. 과거 5건 중 4건이 D+1 자연 복귀.",
                "recommendations": [
                    {"rank": 1, "text": "내일 오전 타워크레인 스케줄 확인 권장"},
                    {
                        "rank": 2,
                        "text": "과거 패턴상 장비 확보 시 D+1 80% 자연 복귀 가능성 — 즉시 추가 조치 불필요할 수 있음",
                    },
                    {"rank": 3, "text": "잔여 물량 기준 D+3 이내 정상화 시 공기 영향 미미"},
                    {"rank": 4, "text": "D+3 초과 시 야간 연장 또는 주말 돌관 투입 검토 권고"},
                ],
            },
            ensure_ascii=False,
        ),
    },
    # 2: 자재미입고 D+2 우세 회복
    {
        "role": "user",
        "content": json.dumps(
            {
                "today": {
                    "company": "대한건설",
                    "l6_main": "철근콘크리트공사",
                    "main_unit": "ton",
                    "assessment": "이상",
                    "today_productivity": 0.55,
                    "today_conditions": "맑음,자재미입고",
                },
                "degradation_cases": [
                    {
                        "date": "2025-09-10",
                        "conditions": "맑음,자재미입고",
                        "productivity": 0.62,
                        "activities": ["RC Wall & Column 공사 : 철근 조립"],
                        "recovery_days": 2,
                        "trajectory": [
                            {
                                "date": "2025-09-11",
                                "conditions": "맑음,자재미입고",
                                "productivity": 0.71,
                                "recovered": False,
                            },
                            {
                                "date": "2025-09-12",
                                "conditions": "맑음",
                                "productivity": 1.02,
                                "recovered": True,
                            },
                        ],
                    },
                    {
                        "date": "2025-08-28",
                        "conditions": "맑음,자재미입고",
                        "productivity": 0.58,
                        "activities": ["RC Slab 공사 : 철근 조립"],
                        "recovery_days": 2,
                        "trajectory": [
                            {
                                "date": "2025-08-29",
                                "conditions": "맑음,자재미입고",
                                "productivity": 0.66,
                                "recovered": False,
                            },
                            {
                                "date": "2025-08-30",
                                "conditions": "맑음",
                                "productivity": 1.05,
                                "recovered": True,
                            },
                        ],
                    },
                ],
            },
            ensure_ascii=False,
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps(
            {
                "diagnosis": "자재 미입고로 인한 저하 (추정). 철근 입고 지연 가능성. 과거 패턴상 D+2 시점에 정상화 사례 우세.",
                "recommendations": [
                    {"rank": 1, "text": "자재 입고 일정 확인 권장 — 협력사 컨택"},
                    {
                        "rank": 2,
                        "text": "과거 패턴상 D+2 정상화 가능성 — 단기 인원 재배치는 후순위 고려",
                    },
                    {"rank": 3, "text": "잔여 물량 기준 D+3 이내 정상화 시 공기 영향 제한적"},
                    {"rank": 4, "text": "D+3 초과 시 대체 자재 확보 또는 후속 공정 선행 검토 권고"},
                ],
            },
            ensure_ascii=False,
        ),
    },
    # 3: 미회복 우세 (장기 지연 — 돌관 검토 시나리오)
    {
        "role": "user",
        "content": json.dumps(
            {
                "today": {
                    "company": "남웅건설",
                    "l6_main": "철근콘크리트공사",
                    "main_unit": "m3",
                    "assessment": "이상",
                    "today_productivity": 0.40,
                    "today_conditions": "맑음,장비대기",
                },
                "degradation_cases": [
                    {
                        "date": "2025-09-15",
                        "conditions": "맑음,장비대기",
                        "productivity": 11.20,
                        "activities": ["RC Slab 공사 : 콘크리트 타설"],
                        "recovery_days": None,
                        "trajectory": [
                            {
                                "date": "2025-09-16",
                                "conditions": "맑음,장비대기",
                                "productivity": 12.10,
                                "recovered": False,
                            },
                            {
                                "date": "2025-09-17",
                                "conditions": "맑음,장비대기",
                                "productivity": 13.80,
                                "recovered": False,
                            },
                            {
                                "date": "2025-09-18",
                                "conditions": "맑음",
                                "productivity": 14.50,
                                "recovered": False,
                            },
                        ],
                    },
                ],
            },
            ensure_ascii=False,
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps(
            {
                "diagnosis": "장비 대기 누적으로 인한 장기 저하 (추정). 과거 유사 케이스에서 D+3 까지 미회복 사례 다수.",
                "recommendations": [
                    {"rank": 1, "text": "장비 가용성 근본 원인 점검 권장 — 협력사·장비사 미팅 검토"},
                    {
                        "rank": 2,
                        "text": "과거 패턴상 D+3 이내 자연 복귀 가능성 낮음 — 적극 개입 고려",
                    },
                    {"rank": 3, "text": "잔여 물량 기준 공기 지연 리스크 — 만회 계획 수립 권고"},
                    {"rank": 4, "text": "야간 연장 또는 주말 돌관 투입을 D+2 시점부터 검토 권고"},
                ],
            },
            ensure_ascii=False,
        ),
    },
]


# ---------------------------------------------------------------------------
# §6.3 build_llm_user_input
# ---------------------------------------------------------------------------


def build_llm_user_input(forecast_row: dict, degradation_cases: list[dict]) -> dict:
    """forecast_row 는 §2.2 의 ForecastRow schema 가정 — main_unit / today_productivity / today_conditions 박힘.

    Input contract for `degradation_cases`:
      each case must be a dict containing keys from `fetch_degradation_cases` output
      (date / conditions / productivity / activities / assigned_workers) PLUS a `recovery`
      key with `fetch_recovery_trajectory` output (`{"trajectory": [...], "recovery_days": int|None}`).
      Caller (agent.py optimize()) is responsible for merging the two retrieve results.
    """
    return {
        "today": {
            "company": forecast_row["company"],
            "l6_main": forecast_row["l6_main"],
            "main_unit": forecast_row.get("main_unit"),
            "assessment": forecast_row["assessment"],
            "today_productivity": forecast_row.get("today_productivity"),
            "today_conditions": forecast_row.get("today_conditions", ""),
        },
        "degradation_cases": [
            {
                "date": c["date"],
                "conditions": c["conditions"],  # str
                "productivity": c["productivity"],
                "activities": c["activities"],
                "recovery_days": c["recovery"]["recovery_days"],
                "trajectory": c["recovery"]["trajectory"],
            }
            for c in degradation_cases
        ],
    }
