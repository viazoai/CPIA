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
- **degradation_cases 가 빈 array 인 경우 (신규 작업 — 과거 유사 저하 사례 없음)**: today 의 assessment / today_productivity / today_conditions / main_unit / company / l6_main 만으로 진단. "과거 유사 사례 없음" 사실을 진단에 명시하고, 일반적 baseline 관리 권고 3~4건 (모니터링·조기 신호 감지·기록 누적·후행 공정 영향 점검 류) 을 작성. 추측성 회복 패턴 언급은 금지.

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


def build_scenarios_llm_input(
    forecast_row: dict,
    no_action_ec: str | None,
    recovery_distribution: dict,
    degradation_cases: list[dict],
) -> dict:
    """scenarios LLM 입력 빌드.

    Args:
        forecast_row: ForecastRow (company / l6_main / l7_5_activity).
        no_action_ec: forecast 의 expected_completion ISO date (아무 조치 없을 때 완료 예상일).
        recovery_distribution: _compute_recovery_distribution 결과 dict (결정 #20 deterministic).
        degradation_cases: advice 진단에 사용된 degradation cases (recovery_days 포함).
    """
    return {
        "wp": {
            "company": forecast_row.get("company"),
            "l6_main": forecast_row.get("l6_main"),
            "l7_5_activity": forecast_row.get("l7_5_activity"),
        },
        "no_action_expected_completion": no_action_ec,
        "recovery_distribution": recovery_distribution,
        "degradation_cases": [
            {
                "date": c.get("date"),
                "recovery_days": c.get("recovery", {}).get("recovery_days"),
                "conditions": c.get("conditions"),
            }
            for c in (degradation_cases or [])
        ],
    }


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


# ---------------------------------------------------------------------------
# §6.4 SCENARIOS_PROMPT + build_scenarios_llm_input (변경 3 — 2026-05-26)
# ---------------------------------------------------------------------------

SCENARIOS_PROMPT = """당신은 건설 현장 공기 만회 시나리오 분석 전문가입니다.

WP (공종) 의 메타데이터 + 현재 예상 완료일 (조치 없을 때) + 과거 회복 분포 + 저하 사례를 받습니다.

임무:
4가지 시나리오 (no_action / optimistic / base / pessimistic) 각각에 대해:
1. expected_completion: ISO date (YYYY-MM-DD)
2. recovery_days: 만회 가능 일수 (no_action 은 0)
3. delta_days: no_action 대비 단축 일수 (no_action 은 0, 나머지는 음수)
4. rationale: 1문장 한국어 근거 (no_action 은 "현재 상태 유지 시 예상 완료일")

시나리오 정의:
- no_action: 아무 조치 없이 현재 속도 유지. recovery_days=0, delta_days=0.
- optimistic: recovery_distribution 의 최단 회복 구간 기반 (과거 가장 빠른 회복 패턴). delta_days 는 음수.
- base: recovery_distribution 의 중앙값 기반. delta_days 는 음수.
- pessimistic: recovery_distribution 의 장기 회복 구간 기반 (과거 가장 느린 회복 패턴). delta_days 는 no_action 보다 작은 개선폭 (delta_days 음수이지만 optimistic/base 보다 절댓값 작음).

원칙:
- no_action_expected_completion 을 기준으로 각 시나리오의 expected_completion 을 산출 (no_action_date - recovery_days).
- recovery_distribution 이 빈 dict 이거나 사례 없으면: optimistic=3일, base=5일, pessimistic=2일 기본값.
- delta_days = -(recovery_days). expected_completion = no_action_date - recovery_days.
- 수치 외 추측 금지. rationale 은 회복 분포 / 사례 근거만.
- 한자 사용 금지 (한글 + 영어).

출력 형식 (JSON):
{
  "no_action":   {"expected_completion": "YYYY-MM-DD", "recovery_days": 0,  "delta_days": 0,  "rationale": "..."},
  "optimistic":  {"expected_completion": "YYYY-MM-DD", "recovery_days": N,  "delta_days": -N, "rationale": "..."},
  "base":        {"expected_completion": "YYYY-MM-DD", "recovery_days": N,  "delta_days": -N, "rationale": "..."},
  "pessimistic": {"expected_completion": "YYYY-MM-DD", "recovery_days": N,  "delta_days": -N, "rationale": "..."}
}
"""


# ---------------------------------------------------------------------------
# §6.5 RECS_PROMPT_V10 — PoC v10 keyword+action+reason 3 필드 schema (2026-05-27 Task 8)
# 사용자 의도: 권고에 "무엇 + 왜" 둘 다 즉시 파악 가능하도록 3 필드 분리.
# Source: /tmp/poc_v10_keyword_schema.py:49-94 (PoC 검증된 본문 byte 단위 이전)
# ---------------------------------------------------------------------------

RECS_PROMPT_V10 = """당신은 건설 현장 PM 옆에서 매일 작업일보를 분석하고 즉시 실행 가능한 액션을 제시하는 분석가입니다.

받는 정보:
- 오늘 공종/회사/생산성/조건 + 평가 두 차원 (assessment + risk_level)
- delay_days 두 차원: forward + point_in_time / mh_gap
- 최근 5건의 비슷한 저하 사례
- trade_frame: 공종 고유 사고 프레임

작성할 것: **Action Plan 2~3건**. 각 항목은 **3 필드 (keyword + action + reason)** 로 분리.

【keyword 가이드 (5~10자 명사구 — 조치 요약)】
- **대괄호 [] 를 넣지 마세요.** keyword 는 순수 명사구만 (UI 가 [keyword] 형태로 감쌉니다).
- trade_frame 핵심 키워드 (양생·적층·양중·계측·간섭·동기화·함수율·면 분리 등) 우선 인용.
- 명사형 조치 요약 예: "면 건조 확보", "양중 순번 재조정", "함수율 점검", "증원 요청", "자재 시점 대조", "간섭 구간 통보".
- 금지: "확인 검토" / "모니터링 강화" 약한 명사구. 시점 표현 ("지금 즉시", "내일") 키워드 X.

【action 가이드 (개조식 — 명사 종결, 문장 종결어 금지)】
- 언제 / 누구에게 / 무엇을 명사구로 압축. **마침표·"~하세요/~합니다/~하십시오" 등 문장 종결어 금지** (telegraphic 개조식).
- 동사는 명사형으로 변환: 통보하세요→통보, 지시하세요→지시, 배치하세요→배치, 점검하세요→점검, 재조정하세요→재조정. 복수 조치는 "+" 또는 "→" 로 연결.
- 시점 표현: **최소 1건 조건 trigger** ("재발 시 / 입고 직후 / 도면 수령 즉시 / 결원 시 / 풍속 초과 시"). 절대 시각 (지금 즉시 / 내일) 은 보조로만.
- 약한 표현 ("확인 권장 / 검토") 금지.
- 예: "도면 수령 즉시 현장대리인에게 변위·침하 계측 기준선 재설정 + 위험 구간 통보"

【reason 가이드 (개조식 — 명사 종결, 저하/회복 사례 인용)】
- 저하 사례 날짜 + **저하/회복 work_content** 직접 인용. 일반론 금지. **"~했습니다/~입니다" 등 문장 종결어 금지** — "→" 로 인과 연결 (telegraphic 개조식).
- "저하 → 회복 패턴" 압축: "09-22 인력부족(가용 면 축소) → 건조 완료 구획 집중 배치 → D+1 회복".
- 사례 빈 array (RAG cold) 일 때는 trade_frame 의 물리적 제약만 인용.

【가드 (v9 유지)】
G1 시점 다양화 / G2 액션 카테고리 4개 / G3 환각 방지 (today_conditions 에 있어도 raw 5건에 없으면 사례 인용 금지, 회사명 today.company 일치)
G4 약한 동사 금지 / G6 위험도 이상 시 "정상범주" 금지 / G8 공종 고유 인사이트 자가 검열

원칙: 한자 금지. **스키마/필드명(risk_level, delay_days 등) 을 keyword/action/reason 본문에 그대로 쓰지 말 것 — 자연어로 풀어쓴다.**

출력 JSON:
{
  "recommendations": [
    {"rank": 1, "keyword": "...", "action": "...", "reason": "..."},
    {"rank": 2, "keyword": "...", "action": "...", "reason": "..."},
    ...
  ]
}
"""


# ---------------------------------------------------------------------------
# §6.6 DIAG_PROMPT_V10 — G6 강화 + delay 두 차원 + mh_gap (2026-05-27 Task 9)
# 사용자 의도: status 이상인데 진단 "정상범주" 라는 mismatch 제거 + delay 산출 근거 명시.
# Source: /tmp/poc_v9_g6_enhanced.py:68-101 (PoC v9 검증된 본문 byte 단위 이전)
# ---------------------------------------------------------------------------

DIAG_PROMPT_V10 = """당신은 건설 현장 PM 의 일일 의사결정을 돕는 분석가입니다.
진단 1줄(생산성/물량 수치 현황)은 시스템이 이미 작성했습니다. 당신은 **2줄째 "현장여건" 1줄만** 작성합니다.

작성할 것: 현장여건 1줄 (개조식, 명사 종결). 오늘 진척을 만든/막은 현장 조건(자재·인력·기상·간섭·양중 등)을 trade_frame 제약과 연결해 1가지 신호로.
- 오늘 조건이 "정상" 이면 없는 장애를 지어내지 말 것 — trade_frame 상 오늘 가장 관건인 제약 1가지만.

규칙: 아라비아 숫자만(한글 숫자 금지), 인시(man-hour) 절대수치 금지, 회복 패턴·만회방안·"분기점" 금지, 한자·영어 약어 금지. 위험도 "이상" 이면 "정상범주/정상 범위" 금지.

출력 JSON: {"diagnosis": "현장여건 1줄"}
"""


# ---------------------------------------------------------------------------
# §6.7 SCENARIOS_PROMPT_V10 — G8 강화: 공종 고유 회복 전략 rationale (2026-05-27 Task 10)
# 사용자 의도: 4 시나리오 rationale 이 일반론 X — trade_frame 고유 수법 인용.
# Source: /tmp/poc_trade_frames_v8.py:189-221 (PoC v8 검증된 G8 강화 본문 byte 단위 이전)
# ---------------------------------------------------------------------------

SCENARIOS_PROMPT_V10 = """당신은 건설 현장 공기 만회 시나리오 분석 전문가입니다.

WP (공종) 의 메타데이터 + 현재 예상 완료일 (조치 없을 때) + 과거 회복 분포 + 저하 사례 + **trade_frame** (공종 고유 사고 프레임) 을 받습니다.

임무: 4가지 시나리오 (no_action / optimistic / base / pessimistic) 각각에 대해:
1. expected_completion: ISO date (YYYY-MM-DD)
2. recovery_days: 만회 가능 일수 (no_action 은 0)
3. delta_days: no_action 대비 단축 일수 (음수)
4. **rationale**: 1~2 문장 한국어 근거. **trade_frame 의 고유 제약 (양생·적층·간섭·양중·계측 등) 에서 출발한 회복 전략 명시.**

시나리오 정의:
- no_action: 현재 속도 유지. recovery_days=0, delta_days=0.
- optimistic: recovery_distribution 최단 회복 기반. trade_frame 의 가장 강력한 병렬화·재배치 수단 활용 시.
- base: recovery_distribution 중앙값.
- pessimistic: recovery_distribution 장기 회복 기반. trade_frame 의 제약이 풀리지 않고 누적될 때.

**가드 8 — 공종 고유 회복 전략 (핵심)**:
- rationale 에 "인력 보강" / "공정 가속" / "모니터링 강화" 같은 일반론 단독 사용 금지.
- 반드시 trade_frame 의 고유 수법 인용 (예: 골조 = "위층 거푸집 선행 투입으로 양생 병렬화" / 외장 = "양중 슬롯 재배치 + 풍속 우회" / 토공 = "계측 trend 안정 후 작업 재개" / 마감 = "선행 양생 완료 확인 후 인력 보강" / 포장 = "양생 가능 온도 창 안에서 야간 작업").

원칙:
- no_action_expected_completion 을 기준으로 각 시나리오의 expected_completion 산출.
- recovery_distribution 이 빈 dict 이면: optimistic=3일, base=5일, pessimistic=2일 기본값.
- 수치 외 추측 금지. 한자 금지.

출력 형식 (JSON):
{
  "no_action":   {"expected_completion": "YYYY-MM-DD", "recovery_days": 0, "delta_days": 0, "rationale": "..."},
  "optimistic":  {"expected_completion": "YYYY-MM-DD", "recovery_days": N, "delta_days": -N, "rationale": "..."},
  "base":        {"expected_completion": "YYYY-MM-DD", "recovery_days": N, "delta_days": -N, "rationale": "..."},
  "pessimistic": {"expected_completion": "YYYY-MM-DD", "recovery_days": N, "delta_days": -N, "rationale": "..."}
}
"""


# ---------------------------------------------------------------------------
# §6.9 build_*_input_v10 — trade_frame + delay 두 차원 + mh_gap inject (2026-05-27 Task 12)
# ---------------------------------------------------------------------------


def _recovery_work_content(case: dict) -> str:
    """trajectory 에서 첫 recovered=True 날의 work_content (회복 narrative)."""
    for t in (case.get("recovery") or {}).get("trajectory") or []:
        if t.get("recovered"):
            return t.get("work_content") or ""
    return ""


def recovery_distribution_text(degradation_cases: list[dict]) -> str:
    """'N건 중 M건 회복 | D+1 회복 4건 · 미회복 1건' 형식 (회복 분포 텍스트).

    view_builder 도 동일 형식으로 UI 에 표시 (similar_cases 바로 밑).
    """
    cases = degradation_cases or []
    total = len(cases)
    if not total:
        return "유사 저하 사례 없음"
    dist: dict[str, int] = {}
    recovered = 0
    for c in cases:
        rd = (c.get("recovery") or {}).get("recovery_days")
        if rd:
            dist[f"D+{rd}"] = dist.get(f"D+{rd}", 0) + 1
            recovered += 1
        else:
            dist["미회복"] = dist.get("미회복", 0) + 1
    parts = " · ".join(
        f"{k} 회복 {v}건" if k != "미회복" else f"미회복 {v}건" for k, v in sorted(dist.items())
    )
    return f"{total}건 중 {recovered}건 회복 | {parts}"


def build_recs_input_v10(
    forecast_row: dict,
    degradation_cases: list[dict],
    today_date: str,
    frame_category: str,
    frame_text: str,
) -> dict:
    """RECS_PROMPT_V10 LLM 입력 빌드.

    2026-05-29: degradation_cases 에 저하/회복 work_content 추가 (reason 이 인용).
    - today: 오늘 데이터 + 평가 + delay 두 차원 + mh_gap + frame_category
    - trade_frame: 공종 고유 사고 프레임
    - degradation_cases: 최근 저하 사례 (저하/회복 narrative + recovery_days)
    """
    return {
        "today": {
            "date": today_date,
            "company": forecast_row["company"],
            "l6_main": forecast_row["l6_main"],
            "main_unit": forecast_row.get("main_unit"),
            "assessment": forecast_row.get("assessment"),
            "risk_level": forecast_row.get("risk_level"),
            "today_productivity": forecast_row.get("today_productivity"),
            "today_conditions": forecast_row.get("today_conditions", ""),
            "frame_category": frame_category,
            "forward_delay_days": forecast_row.get("delay_days"),
            "point_in_time_delay_days": forecast_row.get("point_in_time_delay_days"),
            "mh_gap": forecast_row.get("mh_gap"),
        },
        "trade_frame": frame_text,
        "degradation_cases": [
            {
                "date": c["date"],
                "conditions": c["conditions"],
                "저하": c.get("work_content") or "",
                "회복": _recovery_work_content(c),
                "recovery_days": (c.get("recovery") or {}).get("recovery_days"),
            }
            for c in (degradation_cases or [])
        ],
    }


def build_diag_input_v10(
    forecast_row: dict,
    degradation_cases: list[dict],
    today_date: str,
    frame_category: str,
    frame_text: str,
    recs_out: list[dict],
) -> dict:
    """DIAG_PROMPT_V10 LLM 입력 빌드.

    recs_out: RECS_PROMPT_V10 결과의 recommendations array. DIAG 가 진단에 참조.
    """
    base = build_recs_input_v10(forecast_row, degradation_cases, today_date, frame_category, frame_text)
    base["recommendations"] = recs_out or []
    # 2026-05-29: 회복 분포 — DIAG 첫 문장(회복 패턴 판단)이 인용.
    base["recovery_pattern"] = recovery_distribution_text(degradation_cases)
    return base


def build_scenarios_input_v10(
    forecast_row: dict,
    no_action_ec: str | None,
    recovery_distribution: dict,
    degradation_cases: list[dict],
    frame_category: str,
    frame_text: str,
) -> dict:
    """SCENARIOS_PROMPT_V10 LLM 입력 빌드. 기존 build_scenarios_llm_input 확장.

    추가: frame_category + trade_frame text (G8 강화 — 공종 고유 회복 전략 rationale).
    """
    return {
        "wp": {
            "company": forecast_row.get("company"),
            "l6_main": forecast_row.get("l6_main"),
            "l7_5_activity": forecast_row.get("l7_5_activity"),
            "frame_category": frame_category,
        },
        "trade_frame": frame_text,
        "no_action_expected_completion": no_action_ec,
        "recovery_distribution": recovery_distribution,
        "degradation_cases": [
            {
                "date": c.get("date"),
                "recovery_days": c.get("recovery", {}).get("recovery_days"),
                "conditions": c.get("conditions"),
            }
            for c in (degradation_cases or [])
        ],
    }
