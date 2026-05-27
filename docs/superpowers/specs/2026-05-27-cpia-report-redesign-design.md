# CPIA Report 엔드 이미지 재정립 — Design Spec

> **작성**: 2026-05-27 (A_Track, HEAD `76590f4`)
> **시연 마감**: 2026-06-05 (목, 9일 남음)
> **사용자**: 조형준 프로 (시연자)
> **기반**: PoC v7 (2단계 호출) → v8 (공종 프레임) → v9 (G6 강화 + delay 두 차원) → v10 (keyword schema)

---

## 1. 목표 (Goal)

CPIA `/reports` 페이지에 표시되는 모든 LLM 산출물 (진단·권고·시나리오·site 요약) 을 **공종 고유 인사이트** 가 살아있는 형태로 재정립하고, 7/1~9/24 86일치 데이터를 건축·토목 trade 로 한정해 재 backfill 한다. 일반론 권고 (`"인력 재배치 / 모니터링 강화 / 후속공정 순서 교체"` 등 어디에 붙여도 되는 말) 를 0 건으로 만든다.

### 핵심 결과물

- `/reports` 02 섹션 (리스크 대안 검토): wp 별 진단·유사사례·권고·details 7칸 — 공종 고유 키워드 (양생·적층·양중·계측·간섭) 자연 인용
- `/reports` 03 섹션 (공기 단축 시나리오): 4 시나리오 rationale 도 공종 고유 회복 전략 인용 + wp 별 만회 일수 badge
- site_summary_text: 경영진용 1~2 단락, top_risk_wps 의 카테고리 고유 액션 인용

---

## 2. 배경 (Background)

### 2.1 사용자 의도 (verbatim)

> "옛날 사례에선 이런게 있고, 이런 회복사례가 있으니 이런식으로 대처하세요를 원하거든"
> "권고가 패턴이 왜 다 똑같아 오늘 6시며 내일이며 뭔가 템플릿이 너무 비슷해"
> "진단이라는건 전체적인 맥락을 다 보고나서 쓰는걸 원하는거야"
> "데이터 적재 자체를 건축 토목만 한정해서 넣으라는거야"
> "한달씩 점진 + UI 검증 그런식이야"
> "cold case 절대로 없어야돼 오류가 나면 다시 재시도 하던가"

### 2.2 동료 (제미나이 사용자) 피드백 — 권고 schema 변경 트리거

> "권고사항에 왜 이렇게 권고하는지에 대해서 이유를 달아놓은게 뭔가 연결성 있어보이긴하네"

→ 권고 형식을 `[keyword] action / 이유: reason` 3 필드로 분리 결정.

### 2.3 deep-dive 전수 충돌 발견 (4건)

| # | 이슈 | 위치 | 해결 |
|---|---|---|---|
| #N13 | `daily_reports.site_summary_text` migration 미정의 | init.sql | 본 spec migration |
| #A-N3 | `mapped_history.trade` 컬럼 SQL 누락 | atomizer.py:179-189 + db.py | 본 spec atomizer fix |
| #N17 | view_builder.py:1447 trade 필터 working tree 미커밋 | view_builder.py | 본 spec 커밋 |
| #N19 | v1↔v2 산식 분기 (agent.py:187=v1 / backfill_v2:125=v2) | view_builder.py | 본 spec v2 일원화 |

### 2.4 forecaster `delay_days` 산식의 over-pessimistic 발현

PoC v9 에서 한신비텍·NPW(2차 SCR) SYSTEM 검증 시 **336일 지연** 산출 — `actual_cum_qty=0` 일 때 `pace = today_qty (단일일)` fallback 이 1일 data noise 에 흔들림. 본 spec 에서 **pace floor + delay cap** 보강.

---

## 3. 범위 (Scope)

### 3.1 In scope

- 3 LLM 산출물 재설계: optimizer recs+diag (2단계) / scenarios / site_summary
- 공종 프레임 6 카테고리 외부화 (`data/trade_frames.json` + lookup helper)
- forecaster `aggregate.py` 산식 보강 (pace floor + delay cap + point_in_time_delay_days)
- `view_builder.py` v2 일원화 + wp_summary.status 통일 (forecasts.risk_level 인용)
- 데이터 적재 trade filter (seed_dummy_year.py 단계)
- 7/1~9/24 86일 재 backfill (3개월 점진 + 자동 검증)
- migration 2 컬럼 (`site_summary_text`, `point_in_time_delay_days`)
- FE 일부 수정 (ForecastChart "−N일 만회" badge, OptimizerResult 권고 keyword/reason 분리 polymorphic, similar_cases 3건 슬라이스)

### 3.2 Out of scope

- `reporter.py` `report_md` LLM 산출 (UI 어디서도 안 읽음 — 다음 사이클)
- **이번 사이클 mapper.py trade 채우기 X** — backfill 은 seed_dummy_year 가 mapper 로직 inline 으로 처리 (`_build_mapper_row`). prod LangGraph 의 mapper 노드 자체는 호출되지만 atomizer 가 `a.get("trade")` NULL safe (`atomizer.py:184`) 라 시연 기능 안 깨짐. mapper trade 채우기는 별개 이슈로 처리.
- forecaster `agent.py` LLM 변경 (이번 사이클 손대지 않음)
- 6월 이전 (24/4/11~25/6/30) 기존 데이터 (보존 — 구체 범위 §5.5)
- git issues #41/#42/#43/#45/#47/#48 (별개 처리 — #103)
- prod 환경 `CPIA_HIL_AUTO_BYPASS` 가드 (별개 이슈 #C1)

### 3.3 FE 디자인 불가침 룰 (변경 허용·금지 체크리스트)

CLAUDE.md (`feedback_no_design_change.md`) — FE layout/style/markup 변경 시 시연자 조형준 프로 의도 보존.

**✅ 허용 (BE 데이터·로직 변경)**
- props 추가 (옛 caller 호환 위해 optional 만)
- 배열 slicing / filtering (사용자 사전 합의 완료)
- 조건부 rendering (polymorphic — 옛 schema 호환)

**❌ 금지 (시각 디자인 영역)**
- className / Tailwind class 변경
- div 래핑 / flexbox·grid 재배치
- 색상·폰트·간격·border-radius 변경

**이번 spec 합의된 FE 변경 3건 (사용자 직접 OK)**
- ForecastChart aiAdvice 박스 — 우측 "−N일 만회" badge (✅ optional prop + 분류상 마크업이지만 사용자 직접 "괜찮아" 명시)
- OptimizerResult `similar_cases.slice(0, 3)` (✅ 데이터 필터링)
- OptimizerResult recommendations polymorphic (✅ 조건부 rendering — 옛 string vs 새 object 동시 지원)

---

## 4. Design

### 4.1 Architecture

#### 시스템 변경 위치 (LangGraph 파이프라인)

```
[Parser] → [Atomizer] → [Mapper] → [Forecaster] → [Optimizer] → [Reporter]
                ↓                       ↓             ↓
          db.py + mh_rows          aggregate.py    prompt.py 4종 v10
          (.trade fix #A-N3)       (pace floor +   + trade_frames.json
                                    delay cap +     lookup
                                    point_in_time)
```

#### 신규 모듈 (2개)
- `data/trade_frames.json` — 6 카테고리 정의 (정적 JSON lookup table)
- `pipeline/agents/optimizer/_trade_frames.py` — `lookup_frame(l6_main) -> (category, frame_text)` 헬퍼

#### 변경 모듈 (9개)

| 파일 | 변경 |
|---|---|
| `scripts/seed_dummy_year.py` | argparse `--trades 건축 토목` + `--start-date / --end-date`. `_build_mapper_row` 직후 trade filter |
| `pipeline/agents/atomizer.py` + `pipeline/db.py` | (a) `mapped_history` mh_rows dict + INSERT SQL `.trade` 키 (#A-N3) (b) **`insert_forecast` SQL 28 컬럼 + `point_in_time_delay_days` $29 placeholder 추가** (forecaster aggregate dict key 만 추가하면 PG NULL 만 적재되는 위험 차단) |
| `pipeline/agents/forecaster/aggregate.py` | pace floor + delay cap + `_compute_point_in_time_deficit_days`. **forecasts row dict 에 `point_in_time_delay_days` key 추가 (db.py INSERT 와 짝 맞춤)** |
| `pipeline/agents/optimizer/prompt.py` | `SYSTEM_PROMPT` 단일 → `RECS_PROMPT_V10` + `DIAG_PROMPT_V10` + `SCENARIOS_PROMPT_V10` 분리. build_*_input 4개에 trade_frame + delay 두 차원 + mh_gap inject |
| `pipeline/agents/optimizer/agent.py` | `_call_azure_llm` 2단계 (recs → diag). scenarios 별도 호출. retry 정책 추가 |
| `pipeline/agents/optimizer/site_summary.py` | SYSTEM_PROMPT_V10 (G8 + frame_category 인용). build_site_summary_payload 에 frame_category 포함 |
| `pipeline/agents/optimizer/view_builder.py` | (a) wp_summary.status = forecasts.risk_level 인용 (b) **v2 일원화 (#N19)** — `agent.py:219` live LangGraph node 도 `_build_productivity_views_v2` 호출 (live demo cycle 영향 — Section 4.5.4 E2E 에서 검증) (c) line 1447 trade 필터 안전망 (#N17) (d) `view_builder.py:1904 _build_deterministic_cold_start` 폐기 — 호출 분기 삭제 후 cases<3 도 LLM path |
| `infra/postgres/migrations/2026-05-27_report_redesign.sql` | `daily_reports.site_summary_text` + `forecasts.point_in_time_delay_days` |
| `scripts/backfill_optimizer_advice_llm.py` | `DEFAULT_TRADES = ('건축','토목')` 안전망 + retry 정책 |

#### FE 변경 (2 파일)

| 파일 | 변경 |
|---|---|
| `web/app/components/charts/ForecastChart.tsx` | aiAdvice 타입 `recovery_days?: number` 추가. 박스 우측에 "−N일 만회" badge 16px bold. layout 2 컬럼 (좌=wp 정보 / 우=badge items-center) |
| `web/app/components/reports/OptimizerResult.tsx` | similar_cases `.slice(0, 3)`. recommendations polymorphic rendering (string vs `{keyword, action, reason}` object) |
| `web/app/(app)/reports/page.tsx` | aiAdvice prop 생성 시 `detail.scenarios?.by_wp?.[wp_id]?.base_p50?.recovery_days` 추출 |

### 4.2 Components

#### 4.2.1 `data/trade_frames.json` — 6 카테고리

```json
{
  "골조": {
    "wps": ["철근콘크리트공사", "철골공사", "PC공사", "파일공사"],
    "frame_text": "골조는 한 층이 밀리면 위층이 그대로 따라 밀리는 적층 공정입니다. 진단의 출발은 (1) 양생 시간을 후속 거푸집·먹매김과 병렬화할 여지가 있는지, (2) 타설 사이클이 깨졌는지, (3) 위층 거푸집을 선행 투입해 양생과 병렬화할 수 있는지입니다. 양생 중인 층은 그대로 두고 위층 거푸집 선행 투입은 골조에서만 가능한 수법입니다."
  },
  "마감": {
    "wps": ["도장공사", "방수공사", "수장공사", "금속공사", "지붕공사", "C/R 조성공사"],
    "frame_text": "마감은 선행 공종의 건조·양생을 기다리느라 생긴 대기인지, 마감 자체 생산성 문제인지 먼저 가르는 것이 진단의 출발입니다. 함수율·온습도 환경 조건이 발목을 잡는지, 후속 검측·하자 재시공 리스크가 어디 있는지가 핵심 질문입니다."
  },
  "외장": {
    "wps": ["외장판넬공사"],
    "frame_text": "외장은 양중장비 (타워크레인) 점유 경쟁에서 밀렸는지, 외부 비계 해체 일정과 연동되는지, 풍속 기준으로 양중이 막힌 날수가 얼마인지가 진단의 출발입니다. 인력 추가가 아니라 양중 슬롯 재배치가 핵심 액션인 경우가 많습니다."
  },
  "승강기": {
    "wps": ["승강기공사"],
    "frame_text": "승강기는 건축 골조·외장 완료 시점에서 역산해 착수 일자가 정해집니다. (1) 골조 진척과의 연결 고리, (2) 시운전·검측 일정에서 역산했을 때 지금 위치가 맞는지, (3) 자재 입고와 설치 작업이 동기화되어 있는지가 진단의 출발입니다."
  },
  "토공·흙막이": {
    "wps": ["Common", "배수 공사", "토공사", "흙막이공사"],
    "frame_text": "토공·흙막이는 지하수위와 계측값 (변위·침하) 이 위험 신호인지, 우천 시 배수·법면 안정이 무너졌는지, 후속 골조 착수 시점을 역산했을 때 지금 위치가 맞는지가 진단의 출발입니다. 진도율 자체보다 계측 trend 가 인사이트의 핵심입니다."
  },
  "포장": {
    "wps": ["포장공사"],
    "frame_text": "포장은 후속 인프라 (소방·통신 매설) 와 직렬로 연결되고, 아스콘·콘크리트 양생은 온도·강우에 민감합니다. (1) 선행 매설 공정이 완료되었는지, (2) 양생 가능 온도 범위 안에서 작업 일정이 잡혔는지, (3) 후속 안전·차선 통제 일정과 동기화되어 있는지가 진단의 출발입니다."
  }
}
```

#### 4.2.2 `_trade_frames.py` lookup helper

```python
from __future__ import annotations
import json
from pathlib import Path
from typing import Tuple

_DATA = json.loads((Path(__file__).resolve().parents[3] / "data" / "trade_frames.json").read_text(encoding="utf-8"))
FALLBACK = ("일반", "단위 생산성·계획 진척·MH 효율 3 차원 균형을 본다.")


def lookup_frame(l6_main: str | None) -> Tuple[str, str]:
    """l6_main → (category, frame_text). miss 시 FALLBACK."""
    if not l6_main:
        return FALLBACK
    for cat, meta in _DATA.items():
        if l6_main in meta["wps"]:
            return cat, meta["frame_text"]
    return FALLBACK
```

**경로 안전성**: `Path(__file__).resolve().parents[3]` 는 repo root 가정. Docker / 단독 deploy 시 깨질 위험 → 실제 구현 시 `importlib.resources` 또는 `pyproject.toml` 의 package_data 방식 권장. 모듈 import 시점 1회 file read → `_DATA` 전역 cache → async 안전 (호출 시 file IO 없음).

#### 4.2.3 `aggregate.py` — pace floor + delay cap + point-in-time

```python
def compute_delay(plan: dict, today: date, actual_cum_qty: float, today_qty_main: float, ...) -> dict:
    total_days = (plan_finish - plan_start).days + 1
    plan_per_day_qty = plan_total_qty_main / total_days if total_days > 0 else 0.0

    # 1. pace floor (over-pessimistic 방지)
    if avg_pace_qty <= 0:
        pace = max(today_qty_main, plan_per_day_qty * 0.3)
    else:
        pace = avg_pace_qty

    # 2. forward delay + cap
    if pace > 0:
        remaining_days = remaining_qty / pace
        expected_completion = today + timedelta(days=round(remaining_days))
        delay_days_raw = (expected_completion - plan_finish).days
        delay_days = min(delay_days_raw, round(total_days * 1.0))   # cap
    else:
        delay_days = None
        expected_completion = None

    # 3. point-in-time deficit (신규)
    today_offset = (today - plan_start).days
    if plan_per_day_qty > 0 and today_offset > 0:
        plan_qty_to_date = plan_per_day_qty * today_offset
        deficit_qty = max(0, plan_qty_to_date - actual_cum_qty)
        point_in_time_delay_days = round(deficit_qty / plan_per_day_qty)
    else:
        point_in_time_delay_days = 0

    return {
        ...,
        "delay_days": delay_days,
        "expected_completion": expected_completion,
        "point_in_time_delay_days": point_in_time_delay_days,
        "mh_gap": expected_in_w - actual_cum_mh,  # 기존 유지
    }
```

#### 4.2.4 `prompt.py` 신규 prompt 4종

**RECS_PROMPT_V10** — 출력 JSON schema:
```json
{"recommendations": [
  {"rank": 1,
   "keyword": "양중 순번 재조정",
   "action":  "지금 즉시 에스비테크 팀장에게 ...",
   "reason":  "우천 시(6/28) 사례처럼 ..."},
  ...4건
]}
```

Keyword 가이드 (5~10자 명사구):
- trade_frame 키워드 (양생·적층·양중·계측·간섭·동기화·함수율 등) 우선
- G2 카테고리 시그널 자연 노출 (자원/일정/점검/알림/검증/기록)
- 금지: "확인 검토 / 모니터링 강화" 약한 명사구. 시점 표현 키워드 X.

Action 가이드: 한 문장 (G1 시점 4건 중 ≥2건 조건 trigger / G4 명령형 동사).

Reason 가이드: 한 문장 (raw 사례 또는 trade_frame 제약 인용, 일반론 금지).

**DIAG_PROMPT_V10** — G5 진단=총평 + G6 강화 + **delay 두 차원 명시 분리 인용** + mh_gap 인용.

Delay 두 차원 명명 통일 (드리프트 방지):
- `delay_days` (= forward delay, forecaster aggregate.py 의 `(expected_completion - plan_finish).days`) — UI "일정 영향" details 노출. 진단 첫 문장 "이 페이스 유지 시 N일 지연" 으로 인용
- `point_in_time_delay_days` (신규, forecaster 산출 `deficit_qty / plan_per_day_qty`) — UI 직접 노출 X. 진단 첫 문장 "현재 N일 뒤처졌으며 (계획 누계 X 대비 실 Y, 부족 Z)" 로 인용
- prompt input JSON key 두 개 분리 (`forward_delay_days` + `point_in_time_delay_days`) — 호환성·드리프트 방지

가드 G6 강화:
- **risk_level = "이상" 시 "정상범주 / 정상 범위 / 평시 대비 충분히 높음" 표현 절대 금지**
- assessment vs risk_level 충돌 시 risk_level 우선
- today_productivity 가 raw 평균보다 명백히 낮으면 "정상" 단어 금지

진단 첫 문장 패턴:
```
"현재 N일 뒤처졌으며 (계획 누계 X 대비 실 Y, 부족 Z), 이 페이스 유지 시 M일 지연.
 MH는 (oversupply/undersupply N시간) 인데도 ..."
```

**SCENARIOS_PROMPT_V10** — 4 시나리오 (no_action/optimistic/base/pessimistic) rationale 에 trade_frame 고유 회복 전략 인용 가드.

**SITE_SUMMARY_PROMPT_V10** — top_risk_wps 의 frame_category 별 고유 액션 인용 (양생 병렬화 / 양중 재배치 / 계측 안정 등).

#### 4.2.5 `optimizer/agent.py` — 2단계 호출 + scenarios 병렬화 + retry

Recs 와 scenarios 는 서로 input 독립 → **병렬 호출 가능** (semaphore 효율 ↑). Diag 만 recs output 의존이라 순차.

```python
async def _process_one_with_retry(r, cases, max_retries=3):
    for attempt in range(max_retries):
        try:
            async with sem:
                category, frame_text = lookup_frame(r["l6_main"])
                # 병렬: recs ‖ scenarios (input 독립)
                recs_task = _call_azure_llm_async(RECS_PROMPT_V10,
                    build_recs_input(r, cases, frame_text, ...))
                scen_task = _call_azure_scenarios_llm_async(SCENARIOS_PROMPT_V10,
                    build_scenarios_input(r, ..., frame_text))
                recs_out, scen_out = await asyncio.gather(recs_task, scen_task)
                # 순차: diag (recs 결과 인용)
                diag_input = build_diag_input(recs_input, recs_out["recommendations"])
                diag_out = await _call_azure_llm_async(DIAG_PROMPT_V10, diag_input)
            return _compose_row(r, cases, {"diagnosis": diag_out["diagnosis"],
                                            "recommendations": recs_out["recommendations"]},
                                run_id, scenarios=scen_out)
        except (openai.APIError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            if attempt == max_retries - 1:
                failed_wps_today.append((r["company"], r["l6_main"], str(e)))
                return None
            await asyncio.sleep(2 ** (attempt + 1))
```

#### 4.2.6 `view_builder.py` — 3 변경

1. **wp_summary.status 통일** (line 775):
```python
status = {"정상": "normal", "주의": "caution", "이상": "risk"}.get(
    forecasts_row.get("risk_level"), "normal"
)
```

2. **v2 일원화 (#N19)**: `agent.py:187` 호출도 `_build_productivity_views_v2`.

3. **line 1447 trade 필터 커밋 (#N17)**: `AND ma.trade IN ('건축','토목')` 안전망으로 유지.

4. **`_build_deterministic_cold_start` 폐기** (`view_builder.py:1904`): 호출 분기 삭제 후 cases<3 도 LLM path. 사례 빈 array 분기는 prompt 가 처리:
   ```python
   # AS-IS (view_builder.py 호출 분기)
   if len(cases) < 3:
       return _build_deterministic_cold_start(...)  # ← 분기 제거
   # 신규: 분기 없이 항상 optimizer agent 호출 path
   ```
   prompt 안 분기 명시: `"degradation_cases 빈 array (RAG cold): 모니터링·기록·조기 신호 중심 Action Plan, 추측성 회복 패턴 언급 금지. trade_frame 의 물리적 제약만 인용."`

#### 4.2.7 Migration + db.py INSERT 확장

**SQL migration**:
```sql
-- 2026-05-27_report_redesign.sql
ALTER TABLE daily_reports
  ADD COLUMN IF NOT EXISTS site_summary_text TEXT;

ALTER TABLE forecasts
  ADD COLUMN IF NOT EXISTS point_in_time_delay_days INTEGER;
```

**`db.py:insert_forecast` 확장** (28 → 29 컬럼, $29 placeholder 추가):
```python
# 의사 코드 — 실제 위치는 pipeline/db.py:260-329 의 INSERT 구문
INSERT INTO forecasts (
  run_id, company, l6_main, today_qty_by_unit, today_assigned_workers,
  plan_total_qty_by_unit, plan_mh_sum, rag_n_similar, similar_cases,
  assessment, reasoning, expected_completion, delay_days, risk_level,
  today_productivity, plan_start, plan_finish, plan_mh_per_day,
  schedule_state, window_start, window_days, expected_in_window_mh,
  actual_in_window_mh, mh_gap, recovery_likelihood, ...,
  point_in_time_delay_days   -- ★ 신규 (28번째 컬럼 위치, $29 placeholder)
) VALUES ($1, $2, ..., $28, $29)
```

**`aggregate.py` 반환 dict 도 동일 키 보장** (Section 4.2.3 참조):
```python
return {
    ...,
    "delay_days": delay_days,
    "point_in_time_delay_days": point_in_time_delay_days,   # ★ 신규
    "mh_gap": mh_gap,
}
```

→ aggregate 출력 ↔ db.py INSERT placeholder ↔ migration 컬럼 명 3 곳 짝이 맞아야 NULL 적재 0 보장.

#### 4.2.8 FE polymorphic rendering (`OptimizerResult.tsx`)

```tsx
{output.recommendations.map((r, i) => {
  if (typeof r === "string") {
    // 6월 이전 backfill (v6/v7 schema)
    return <li key={i}>{r}</li>;
  }
  // 7/1~9/24 backfill (v10 schema)
  return (
    <li key={i} className="mb-3">
      <div className="flex items-baseline gap-2">
        <span className="rounded bg-mint-soft px-1.5 py-0.5 text-[12px] font-semibold text-mint-text">
          {r.keyword}
        </span>
        <span className="text-sm text-ink">{r.action}</span>
      </div>
      <div className="ml-2 mt-1 text-[12.5px] text-ink-mid">
        <span className="font-semibold">이유:</span> {r.reason}
      </div>
    </li>
  );
})}
```

### 4.3 Data Flow

#### WP 1건 처리 시퀀스 (per wp, optimizer)

```
[Input] mapper_activities row + forecasts row (assessment, risk_level, delay 두 차원, mh_gap, plan_*) + degradation_cases (Chroma RAG, ≤5건) + data/trade_frames.json
  ↓
[Step 0] (category, frame_text) = lookup_frame(l6_main)
  ↓
[Step 1] RECS_PROMPT_V10 호출
  input: {today, trade_frame, degradation_cases}
  output: {recommendations: [{rank, keyword, action, reason}, ...4건]}
  ↓
[Step 2] DIAG_PROMPT_V10 호출
  input: {...recs_input, recommendations_from_step1}
  output: {diagnosis}  # 첫 문장에 delay 두 차원 + mh_gap 인용, G6 강화
  ↓
[Step 3] SCENARIOS_PROMPT_V10 호출
  input: {wp_meta, no_action_expected_completion, recovery_distribution, trade_frame, ...}
  output: {no_action, optimistic, base, pessimistic} 각 {expected_completion, recovery_days, delta_days, rationale}
  ↓
[Compose + Output] PG INSERT INTO optimizer_advice (diagnosis, recommendations, scenarios)
```

#### Site-level site_summary (모든 wp 처리 후 1회)

```
view_builder._build_optimizer_view / _build_wp_summary / _build_scenarios
  ↓
build_site_summary_payload(report_date, site_id, kpi, scenarios, wp_summary,
                          optimizer_view, s_curve)
  → top_risk_wps[i].{wp_name, trade, frame_category, diagnosis, top_recommendation}
  ↓
SITE_SUMMARY_PROMPT_V10 호출 (G8 + frame_category 인용 가드)
  → "기준일 진척률 X%, 계획 Y% 대비 Z%p 뒤처짐. 골조의 양생 병렬화,
     마감의 선행 양생 확인, 외장의 양중 재배치 즉시 효과 ..."
  ↓
UPDATE daily_reports SET site_summary_text = ...
```

#### 86일 Backfill 3 단계 chain

```
[1] seed_dummy_year.py --start 2025-07-01 --end 2025-09-24 --trades 건축 토목
    for d in window:
      for am_row in activity_master:
        if am_row.l5_disc not in args.trades: continue   # ★ trade filter
        mapper_row = _build_mapper_row(d, am_row, anchor, rng)   # F3 + prod target
        INSERT mapper_activities + parser_activities + mapped_history + forecasts
      (sample 일자 weekly + 9-24) Chroma upsert

[2] backfill_optimizer_advice_llm.py --start 2025-07-01 --end 2025-09-24
    DEFAULT_TRADES = ('건축','토목')   # 안전망
    for d in window:
      atomizer → forecaster (LLM) → hil_2 (auto) → optimizer (LLM, retry) → reporter
      failed_wps_today retry batch
      → optimizer_advice INSERT

[3] backfill_daily_report_views_v2.py --all-dates --with-summary
    for d in window:
      result = _build_productivity_views_v2(pg, site, d)   # v2 일원화
      UPDATE daily_reports SET kpi/.../optimizer_view/scenarios = ...
      site_summary = generate_site_summary(payload)
      UPDATE daily_reports SET site_summary_text = ...
```

### 4.4 Error Handling

#### 4.4.1 Cold case 절대 금지 정책

**(A) RAG cold_start (cases < 3) deterministic 4 슬롯 폐기 → LLM 호출 강제**

기존 `view_builder._build_deterministic_cold_start` 폐기. cases < 3 이어도 LLM 호출. prompt 안에 분기 명시: `"degradation_cases 빈 array (RAG cold): 모니터링·기록·조기 신호 중심 Action Plan, 추측성 회복 패턴 언급 금지. trade_frame 의 물리적 제약만 인용."`

**(B) LLM 호출 실패 — retry + 취합 재시도**

```python
max_retries = 3
backoff = [2, 4, 8]  # seconds
# 3회 실패 시 failed_wps[date].append(wp_key)
# 1일 끝난 후 failed_wps retry batch 1회
# batch 후도 실패 시 일자 단위 SKIP 표시 + 다음 일자 진행
# 모든 일자 끝난 후 failed_wps 전체 retry batch 1회 (최종)
# 최종 실패 wp 는 log 보고 (수동 처리)
```

#### 4.4.2 자동 OK 판단 가드 (월별)

```python
async def gate_month(month: int) -> bool:
    return all([
        await assert_count_zero(
            "SELECT COUNT(*) FROM optimizer_advice WHERE diagnosis='cold_start' "
            f"AND report_date >= '2025-{month:02d}-01'"),
        await assert_no_banned_words(["정상범주", "정상 범위"], month),
        await assert_skip_ratio_lt(0.01, month),
        await assert_wp_count_within_pct(0.9, month),
        await assert_count_zero(
            "SELECT COUNT(*) FROM daily_reports WHERE site_summary_text IS NULL "
            f"AND report_date >= '2025-{month:02d}-01'"),
        await assert_count_zero(
            "SELECT COUNT(*) FROM mapper_activities WHERE trade NOT IN ('건축','토목') "
            f"AND report_date >= '2025-{month:02d}-01'"),
    ])
```

#### 4.4.3 Edge cases

| 케이스 | 대응 |
|---|---|
| `plan_finish IS NULL` | aggregate 가 schedule_state="unknown" + delay_days=None. prompt input null inject + "추정 불가" 가드 |
| `pace = 0` (floor 적용 후도 0) | delay_days = None, expected_completion = None |
| `today < plan_start` | point_in_time_delay_days = 0 |
| `today > plan_finish` | plan_qty_to_date = plan_total_qty (cap), delay 자연 산출 |
| `trade_frame lookup miss` | FALLBACK frame_text 사용. LLM 호출 진행 |
| `mapping_conf=0 (trade=None)` | SQL assertion: 7/1 이후 0건 보장 (mock seed 1.0 일관) |
| `Chroma upsert 실패` | retry 1회 → warn + PG 적재는 진행 |
| `site_summary LLM 실패` | warn + 그 일자 jsonb 는 적재 (summary_text 만 NULL → gate 위반) |

### 4.4.4 Migration online safety

`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 둘 다 nullable + default 없음 → Postgres 11+ metadata-only operation (no table rewrite). Lock 시간 < 1s. AWS PG 대용량 테이블 (mapper_activities, daily_reports, forecasts) 영향 무시 수준.

### 4.5 Testing

#### 4.5.1 Unit tests (`pipeline/tests/`)

- `test_trade_frames.py`: lookup_frame known + fallback
- `test_aggregate_v10.py`: pace floor (actual=0 시), delay cap (raw > total_days 시), point_in_time deficit
- `test_recs_schema_v10.py`: keyword 5~10자 명사구 + action 명령형 + reason 사례 인용 (mock LLM)

**기존 cold_start 테스트 6 spot 처리 (필수)**:

`_build_deterministic_cold_start` 폐기 (Section 4.2.6 (4)) 로 다음 기존 테스트 처리 방침:

| 파일 | 현황 | 처리 |
|---|---|---|
| `pipeline/tests/optimizer/test_view_builder_phase2.py:75,89,104,117,131,145` (6 spot) | `_build_deterministic_cold_start` 직접 import + 호출 | **DELETE** (의도 무효화 — view_builder dispatch 분기 자체 폐기) |
| `pipeline/tests/optimizer/test_view_builder_v2.py:164` (Task 11 cold_start + augmentation weight) | deterministic path 검증 | **REPLACE** — cases<3 → LLM path 호출 mock 으로 재작성. "RAG 빈 array 분기 가드 작동" 검증으로 재정의 |
| `pipeline/tests/test_optimizer_scenarios.py:102` (`test_scenarios_cold_start`) | scenarios cold_start | **REPLACE** — LLM 호출 (사례 빈 array) 후 SCENARIOS_PROMPT 의 default 값 (optimistic=3일, base=5일, pessimistic=2일) 검증 |

신규 테스트:
- `test_cold_path_v10.py`: cases<3 input → LLM path 호출 + diagnosis ≠ 'cold_start' + recommendations 4건 보장

#### 4.5.2 Integration tests (실 PG + Azure)

`pipeline/tests/integration/test_optimizer_v10.py` — PoC v9 + v10 패턴 자동화:
- 3 wp sample (risk=정상 / 주의 / 이상) × 3 LLM
- assertion: G6 금지 단어 0건 / delay 두 차원 인용 / trade_frame 키워드 진단 포함 / 회사명 일치 / keyword 5~10자

#### 4.5.3 Regression (v6/v7 ↔ v10 비교)

`pipeline/tests/regression/test_v10_vs_v7.py`:
- 일반론 권고 비율 (v6 약 60% → v10 < 10%)
- 진단 길이 평균 (v6 1문장 → v10 2~3문장)
- 시점 다양화 (조건 trigger ≥2건 / 4건)
- keyword 존재 비율 (v6 0% → v10 100%)

#### 4.5.4 E2E (1일 sample backfill + Playwright + **live cycle 검증**)

**(A) backfill 1일 sample**:
```
seed_dummy_year --start 2025-07-01 --end 2025-07-01 --trades 건축 토목
backfill_optimizer_advice_llm --date 2025-07-01
backfill_daily_report_views_v2 --date 2025-07-01 --with-summary
```

**(B) Playwright 자동 검증** (`http://localhost:5536/reports?date=2025-07-01`):
- KpiStrip / GapKpiCard / QuadrantCountKpi 모두 값
- 분포도 wp 모두 trade ∈ {건축,토목}
- WPSummaryTable status = forecasts.risk_level
- wp 클릭 → OptimizerResult `[keyword] action` / `이유: reason` 표시
- 진단 텍스트 G6 금지 단어 0건
- ForecastChart aiAdvice 박스 "−N일 만회" badge
- similar_cases 3건만
- site_summary_text NULL 0건

**(C) Live cycle 검증 — v2 일원화 (#N19) prod 영향 확인 추가**:
- 작업일보 xlsx 1건 드롭 (시연 cycle 입력)
- LangGraph 9-node 실행 (`optimizer node` 가 `_build_productivity_views_v2` 호출)
- reports/[date] 페이지 라이브 산출 확인 — backfill 결과와 schema·산식 정합
- 회귀 항목: KPI 의 productivity 값이 v1 (EVM) → v2 (인당 비교) 로 바뀐 후도 PoC v10 진단 텍스트와 모순 없는지 (예: "productivity 90" 의미 동일 보존)

#### 4.5.5 점진 검증 chain (3개월)

```
[7월 (31일)] backfill chain → gate_month(7) → OK → 자동 다음
[8월 (31일)] backfill chain → gate_month(8) → OK → 자동 다음
[9월 (24일)] backfill chain → gate_month(9) → OK → 최종
[종합] 전체 failed_wps 1회 더 retry + 전체 SQL assertion
```

월별 gate 실패 시 사용자 호출.

---

## 5. Migration / Rollout

### 5.1 Pre-flight

1. SQL migration 적용: `psql < 2026-05-27_report_redesign.sql` (idempotent, metadata-only)
2. `data/trade_frames.json` commit
3. PoC v10 결과 commit (Reference: `/tmp/poc_v10_keyword_schema.py`)
4. 코드 변경 commit (atomic 단위로 — db/atomizer/aggregate/prompt/agent/view_builder/seed/backfill 분리)
5. **Azure quota dry-run 측정** (필수, D-9~D-8 = 5/27~5/28):
   - 7/1 단일일 backfill 1회 (60 wp × 3 LLM ≈ 180 호출)
   - 측정 항목:
     a. 분당 호출 burst (Azure 429 hit 비율)
     b. cases<3 wp 비율 (cold_start 폐기 후 LLM 호출 증가량 = 시간 예산 핵심 변수)
     c. 단일 wp 의 평균 wall time (recs ‖ scenarios → diag 순차 패턴 적용 후)
   - 측정 결과 기준 `CPIA_LLM_CONCURRENCY` (default 4) 와 retry backoff 재조정. 분당 quota 초과 시 `retry-after` 헤더 존중하는 quota-aware sleeper 추가

### 5.2 3개월 점진 실행 (자동 진행)

```bash
# 월별 chain. 각 월 gate OK 시 자동 다음 월.
./scripts/run_monthly_backfill.sh 2025-07
./scripts/run_monthly_backfill.sh 2025-08
./scripts/run_monthly_backfill.sh 2025-09  # 9/1~9/24
```

각 월 chain 내부:
```
seed_dummy_year --start ... --end ... --trades 건축 토목
backfill_optimizer_advice_llm --start ... --end ...
backfill_daily_report_views_v2 --all-dates --with-summary --start ... --end ...
gate_month   # SQL assertion + Playwright 자동 검증
```

### 5.5 6월 이전 데이터 취급 (확정)

- **DB**: 6월 이전 (24/4/11~25/6/30) 7 trade 모든 row 보존 (DELETE 안 함). migration 은 컬럼만 추가 — 옛 row 의 `point_in_time_delay_days` / `site_summary_text` 는 NULL 그대로
- **Backfill scripts**: 모든 hard-code `--start-date 2025-07-01` 의무 (휴먼 에러 차단)
- **FE**: reports 페이지의 date picker 가 7월 이후 일자 선택 시 자동으로 건축·토목 wp 만 보임 (PG `mapper_activities` 의 trade 필터링 결과 자연 도출). Dashboard / HR 페이지는 6월 이전 데이터 그대로 노출 (전 공종)

### 5.3 Rollback (필요 시)

- migration: ALTER TABLE ... DROP COLUMN (idempotent)
- backfill 결과: `DELETE FROM optimizer_advice WHERE report_date BETWEEN '2025-07-01' AND '2025-09-24'`
- 코드: revert commits

### 5.4 시연 D-day (2026-06-05) 사전 검증

전체 86일 backfill 완료 후 D-1 (6/4):
- 시연 시나리오 일자 3개 (예: 7/15, 8/15, 9/15) reports 페이지 수동 점검
- KPI / 진단 텍스트 / 권고 keyword / 시나리오 만회 일수 / site_summary 모두 채워졌는지

---

## 6. 우려·결정 미해결 (Open questions)

1. **시간 예산**: 86일 × 약 60 wp × 3 LLM ≈ 15,500 호출. semaphore 4 = 약 24시간 예상. 만약 retry batch 가 큰 비중이면 36~48시간 가능성. 사용자가 자리 비울 때 자동 진행.

2. **6월 이전 보존 데이터의 trade 분포**: 6월 이전은 7 trade 모두 적재된 상태. Dashboard / HR 페이지는 그대로 작동. reports 페이지는 7월 이후 일자 선택 시 건축·토목만 표시 (자연 도출).

3. **keyword 표기 통일** (PoC v10 미세 발견): "6/29" vs "6월 29일" 혼재. prompt 에 표기 가이드 추가하지 않으면 mixed. 우선 사용자에게 시연 후 결정 위임.

4. **prod 환경 `CPIA_HIL_AUTO_BYPASS` 가드** (#C1, design_intent_orchestration.md:230): 본 spec 범위 외. 별개 이슈로 처리.

5. **FE polymorphic rendering 의 type safety**: `recommendations: string[] | RecommendationObject[]` union 타입 명시 필요. TypeScript strict 모드에서 컴파일 OK 확인 필요.

---

## 7. Reference

- PoC 산출물: `/tmp/poc_action_prompt.py` (v7), `/tmp/poc_trade_frames_v8.py` (v8), `/tmp/poc_v9_g6_enhanced.py` (v9), `/tmp/poc_v10_keyword_schema.py` (v10)
- PoC 결과 로그: `/tmp/poc_v8_out2.log`, `/tmp/poc_v9_out.log`, `/tmp/poc_v10_out.log`
- deep-dive 9 파일: `deep-dive/architecture_overview.md` 외 8개
- design-intent 8 파일: `deep-dive/design-intent/design_intent_optimizer.md` 외 7개
- 사용자 룰: CLAUDE.md (FE 디자인 불가침 / 한자 금지 / forecaster·mapper·atomizer 룰 정정 — BE 변경 가능)
- 시연자: 조형준 프로
- 시연 마감: 2026-06-05 (목)
- Branch: A_Track, HEAD `76590f4`
