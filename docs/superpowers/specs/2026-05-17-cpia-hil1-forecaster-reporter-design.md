# CPIA HIL 1 + Forecaster fix + Reporter 통합 cycle Design

**날짜:** 2026-05-17
**관련 audit:** `docs/audit/2026-05-17-cpia-e2e-audit-report.md`, `docs/audit/2026-05-17-cpia-drift-backlog.md`
**우선순위 출처:** drift-backlog #1 (Reporter) + #2 (Forecaster assessment) + #3 (시뮬 fixture bug) + #4 (HIL 1)
**브랜치:** A_Track (HEAD f9a695f, origin sync)
**PoC 데모 마감:** 2026-06-05 (목) — 본 cycle 종결 후 ~2 주 여유

---

## 0. 목적

CPIA E2E 파이프라인의 **3 갭** 을 1 spec / 1 plan / 1 PR 로 동시 메움.

1. **HIL 1 구현** (drift-backlog #4) — Mapper 결과 사람 검토. 현재 state placeholder + Activity flag 만 존재, graph node 없음. PoC 성공 기준 #2 직접 미충족.
2. **Forecaster fixture fix + RAG 정합 테스트** (drift-backlog #2 + #3) — `synthetic_daily_report.py:78` 의 n_activities 오버산출 버그. ratio=0.45 인데도 today_prod > baseline 산출 → assessment="정상" 종속성 → Optimizer 약한 권고. classify.py:34 는 PM 원안 v2 와 정합이라 그대로 둠.
3. **Reporter 신규** (drift-backlog #1) — `pipeline/agents/reporter.py` 현재 0 lines. Mapper + Forecaster + Optimizer 결과 종합 보고서 (사용자 의도). PoC 성공 기준 #1 직접 미충족.

3 갭 사이 의존성 0. **병렬 atomic 진행** (사용자 결정).

## 1. 스코프

**In scope:**
- `pipeline/graph.py` — hil_1_node 신규, reporter_node 신규, conditional_edges 변경
- `pipeline/agents/optimizer/synthetic_daily_report.py:78` — today_qty 산식 정정
- `pipeline/agents/optimizer/synthetic_daily_report.py:118` — n_activities=0 ValueError
- `pipeline/agents/reporter.py` — 신규 (0 lines → 풀 구현)
- `pipeline/db.py` — `insert_mapping_correction()` + `insert_daily_report()` 메서드 신규
- `pipeline/tests/` — HIL 1 unit + e2e (신규 2 파일), Reporter unit + 통합 (신규 1 파일), Forecaster fix 재현 + RAG 정합 (기존 확장)

**Out of scope:**
- Dashboard / FastAPI 연동 (B_Track) — HIL 1 = CLI 인터랙티브로 자체완결
- Collector / Parser / main.py / api.py — 본 cycle 미터치 (drift-backlog #5 별 cycle)
- classify.py 양방향 임계 추가 — PM 원안 v2 와 정합 (저하만 분류 의도)
- (out of scope 였으나 §7.4 보강으로 **본 cycle 포함**) PostgresSaver 전환은 본 cycle 의 Task 4 (신규) 로 분리 — design-intent O-6 권고 대응

## 2. 사전 fact (실 코드 검증 — Iron Law 3 요소 적용)

### 2.1 HIL 1 구현 상태

```
$ wc -l pipeline/agents/reporter.py pipeline/agents/collector.py pipeline/main.py pipeline/api.py
       0 pipeline/agents/reporter.py
       0 pipeline/agents/collector.py
       0 pipeline/main.py
       0 pipeline/api.py
```

- `pipeline/state.py:118` — `hil_1_corrections: dict` 자리 있음
- `pipeline/state.py:133` — `"waiting_hil_1"` Literal 정의됨
- `pipeline/state.py:56` — Activity `requires_review: bool` 정의됨
- `pipeline/agents/mapper.py:335` — `requires_review = confidence < cfg.conf_threshold or wa_result.source == "hil_required"` (LLM confidence < 0.7 또는 WA 결정 hil_required 시 True)
- `pipeline/graph.py:263` — `mapper → atomizer` 직진. **HIL 1 node 없음.**

**→ HIL 1 = "미아의 상태 — 끊어줬으나 구현 안 남음"** (사용자 표현).

### 2.2 Forecaster fixture 산술 fact

```
$ grep -n "today_qty\|baseline_q\|assigned_workers" pipeline/agents/optimizer/synthetic_daily_report.py | head -10
```

- line 78: `today_qty = round(baseline_q * sc["productivity_ratio"], 1)`
- line 84: `assigned_workers = round(base_workers * sc["workers_ratio"], 1)`
- line 215: `qty_lookup[(co, l6, unit)] = total / max(days, 1)` (baseline_qty = Σplan_total_qty / 90)

**산술 검증 (audit raw 시뮬 1 ca7d820c 와 정합):**
- n_activities=5, ratio=0.45, baseline_prod=31.07
- aggregate.py:14~20 → 5 row 가 모두 같은 (company, l6_main) 그룹 → today_qty_total = 5 × baseline_q × 0.45
- today_prod = today_qty_total / assigned_workers = (5 × baseline_q × 0.45) / base_workers = **5 × baseline_prod × 0.45 = 69.91** ≈ raw 69.62 ✓

**→ root cause = baseline_q (1 일치) 가 n_activities 만큼 반복되어 N× 오버산출.**

> **Footnote (RAG 평균 23.25 출처):** audit raw `docs/audit/raw/scenario-3-8ee67861.md` line 38 의 forecaster reasoning 인용 — "유사 4건 평균 23.25 m3/인 대비 +38%". 실 호출 시 재산출되는 동적 값 (synthetic_v2 적재 분포 + Chroma rerank 결과 의존).

### 2.3 Forecaster assessment 결정 path

```
$ sed -n '27,40p' pipeline/agents/forecaster/classify.py
def classify_assessment_rag(today_prod: float, rag_avg_prod: float) -> str:
    if rag_avg_prod == 0:
        return "정상"
    delta = (today_prod - rag_avg_prod) / rag_avg_prod
    eps = 1e-9
    if delta >= -RAG_NORMAL_BOUND - eps:  # -0.15
        return "정상"
    if delta >= -RAG_WARN_BOUND - eps:  # -0.25
        return "주의"
    return "이상"
```

- `delta >= -0.15` → "정상" (상향 변동 무조건 정상)
- PM 원안 v2 §0.1 ② 와 정합 — "유사 사례 대비 N% **저하** 분류" 의도
- → **classify.py:34 는 수정 X.** root cause 는 input (today_prod) 의 오버산출.

### 2.4 Reporter 구현 상태

```
$ wc -l pipeline/agents/reporter.py
       0 pipeline/agents/reporter.py
```

- `pipeline/state.py:122` — `report_md: str` 자리 있음
- `docs/schema/postgres.md:158~171` — `daily_reports` 테이블 schema 정의됨 (id/run_id/date/report_md/summary JSONB/created_at)
- `pipeline/graph.py` — reporter_node 없음

### 2.5 PG schema 변경 0건

```
$ grep -n "CREATE TABLE" docs/schema/postgres.md
```

- `daily_reports` (line 161) — 기존 그대로 사용 가능
- `mapping_corrections` (line 292) — 기존 그대로 사용 가능 (work_content / company / trade / original JSONB / corrected JSONB / correction_type)
- 신규 컬럼 / 신규 테이블 = 0건

### 2.6 LangGraph 패턴 fact

```
$ sed -n '71,177p' pipeline/graph.py  # hil_2_node 본문
```

- `graph.py:172` — `selected = interrupt({"risky_groups": payload_groups})` (HIL 2 패턴)
- `Command(resume=selection)` (synthetic_daily_report.py:459) — resume payload 패턴
- HIL 1 도 동일 패턴 차용 (interrupt + Command(resume=))

## 3. PM 원안 v2 와의 정합 / drift

| 항목 | PM 원안 v2 (planning/CPIA_PoC_실행계획_v2.md) | 본 cycle 결정 | 정합/drift |
|------|----------------------------------------------|---------------|-----------|
| HIL 1 위치 | Mapper 직후 (line 40, 232) | mapper → hil_1 → atomizer | **정합** |
| HIL 1 입력 채널 | Dashboard Modal (line 329) | **CLI 인터랙티브** (HIL 2 패턴) | **의도적 drift** — B_Track 의존 회피, PoC 자체완결 |
| Forecaster 분류 의도 | 유사 사례 대비 저하 분류 (§0.1 ②) | classify.py 그대로 | **정합** |
| Synthetic fixture | 명시 없음 (구현 디테일) | n_activities 분배 정정 | bug fix |
| Reporter 위치 | Atomizer 다음 (Forecaster 와 병렬, line 40 + 534) | **Optimizer 다음** | **의도적 drift** — Forecaster+Optimizer 결과 포함 종합 보고서 |
| Reporter 출력 | 사내용 + 발주처용 2 종 (line 132) | **종합 보고서 1 종** | **의도적 drift** |
| Reporter LLM | Sonnet 4.6 (line 83) | Azure gpt-5.1 | 의도된 변경 (audit-report §3 — Azure 통일) |

**drift 3 점은 사용자 의도적 결정** — spec 본 §3 에 명시.

## 4. 아키텍처

### 4.1 graph 변경

**현 graph (`graph.py:262~271`):**
```
START → mapper → atomizer → forecaster → hil_2 →
                                           ├─ (selection 있음) optimizer → END
                                           └─ (selection 없음) ──────────→ END
```

**신 graph:**
```
START → mapper → hil_1 → atomizer → forecaster → hil_2 →
                  │                                ├─ (selection 있음) optimizer ─┐
                  │                                └─ (selection 없음) ───────────┴─→ reporter → END
                  ↓
              interrupt(review_payload)
                  ↑ Command(resume=corrections)
```

### 4.2 LangGraph edges 변경

```python
# build_graph (graph.py:233~272) 변경
graph.add_node("hil_1", _hil_1)
graph.add_node("reporter", _reporter)
graph.add_edge("mapper", "hil_1")            # 변경 (기존: mapper → atomizer)
graph.add_edge("hil_1", "atomizer")          # 신규
graph.add_edge("optimizer", "reporter")      # 변경 (기존: optimizer → END)
graph.add_conditional_edges(                 # 변경 — END 분기를 reporter 로
    "hil_2",
    lambda s: "optimizer" if s.get("hil_2_selection") else "reporter",
    {"optimizer": "optimizer", "reporter": "reporter"},
)
graph.add_edge("reporter", END)              # 신규
```

`build_demo_graph` (graph.py:200~230) 도 동일 변경 적용 — synthetic_daily_report CLI 가 사용.

## 5. 컴포넌트

### 5.1 HIL 1 — `hil_1_node` (graph.py 안)

**signature:**
```python
async def hil_1_node(state: CPIAState, cfg: GraphConfig) -> dict:
```

**처리:**
1. `mapped = state["mapped"]`
2. `review_needed = [{"idx": i, "work_content", "company", "trade", "wa", "l6_main", "mapping_conf", "mapping_source"} for i, a in enumerate(mapped) if a.get("requires_review")]`
3. `if not review_needed: return {"hil_1_corrections": {}, "current_node": "hil_1"}`
4. `corrections = interrupt({"review_needed": review_needed})` — payload dict `{int_idx: {"wa": str, "l6_main": str}}`
5. corrections 적용:
   - 해당 idx 의 Activity 의 wa/l6_main 수정
   - `mapping_source="user_corrected"`, `requires_review=False`
6. PG `mapping_corrections` INSERT (per correction 1 row) — 매핑 룰:
   - `original` JSONB = `{"wa": <mapper 추천>, "l6_main": <mapper 추천>, "mapping_conf": <float>, "mapping_source": <auto_bp_single | auto_l6_single | hil_required>}`
   - `corrected` JSONB = `{"wa": <사용자 입력>, "l6_main": <사용자 입력>, "mapping_source": "user_corrected"}`
   - `correction_type` = `"replace"` (PoC 기본; `split` / `reject` 는 후속 cycle)
   - `work_content` / `company` / `trade` = review_needed payload 의 해당 idx 필드 그대로
7. `return {"mapped": corrected, "hil_1_corrections": corrections, "current_node": "hil_1"}`

**state 변경 0건** — 모두 이미 정의됨 (state.py:118, 56, 43).

**CLI 인터랙티브 (synthetic_daily_report 의 hil_2 패턴 차용):**

- **HIL 1 큐 크기 fact** (design-intent/design_intent_mapper.md:257): v3 시뮬 자동 98.7% but WA 결정 4단계 hil_required = 61% (남웅건설 case). 47 row 작업일보 → ~29 row review 가능. **일괄 처리 UX 가 중요.**

- **`--auto-correct-all` flag:** Mapper 추천 (wa, l6_main) 그대로 수용 + `mapping_source="user_corrected"` 박음 (학습 데이터로 활용 가능). 사람 입력 0건.

- **`input()` 인터랙티브 형식 (예시):**

```
[HIL-1 INTERRUPT] 29 row review 필요:
  [0] 남웅건설 | 철근콘크리트공사 | 1F 벽체 콘크리트 타설 (conf=0.55, source=hil_required)
      추천: wa=CUB, l6_main=철근콘크리트공사
  [1] 세보엠이씨 | 일반공조설비공사 | AHU 덕트 조립 (conf=0.62, source=hil_required)
      추천: wa=SK0XX, l6_main=일반공조설비공사
  ...

수정 형식: <idx> <wa> <l6_main> (쉼표 구분, 여러 row 일괄 처리 가능).
빈 입력 = 모든 row 추천 수용 (--auto-correct-all 와 동일).
선택> 0 CUB 철근콘크리트공사, 2 PIP 배관공사
[OK] HIL 1: 2 corrections applied (idx 0+2), 27 row 추천 수용
```

- **일부만 답:** 답 안 한 row 는 Mapper 추천 그대로 수용 (`requires_review=False`). 답 안 한 row 를 `requires_review=True` 유지 옵션은 후속 cycle (현재 PoC 는 모든 row 처리 후 진행).
- **파싱 오류:** 형식 위반 (예: `0` 만 입력, wa/l6 누락) → re-prompt 최대 3 회 → abort (Exit 3).

### 5.2 Forecaster fix — `synthetic_daily_report.py:78`

**수정 1 line:**
- 현: `today_qty = round(baseline_q * sc["productivity_ratio"], 1)`
- 신: `today_qty = round(baseline_q * sc["productivity_ratio"] / sc["n_activities"], 1)`

**산술 검증 (fix 후):**
- 시뮬 1 (n=5, ratio=0.45): row 당 today_qty = baseline_q × 0.45 / 5 → 5 row 합산 = baseline_q × 0.45 → today_prod = baseline_prod × 0.45 = 31.07 × 0.45 = 13.98
- RAG 평균 23.25 대비 -40% → classify.py:38 `delta < -0.25 → "이상"` 발현 ✓
- 시뮬 2 (n=3, ratio=0.8): today_prod = baseline × 0.8 → RAG 대비 변동 따라 "주의" 또는 "정상" 발현

**ValueError 가드:** `synthetic_daily_report.py:118 _parse_scenario` 에 `if int(parts[2]) <= 0: raise ValueError("n_activities > 0")` 추가.

### 5.3 Reporter — `pipeline/agents/reporter.py` 신규

**파일 구조:**
```python
"""Reporter agent — Mapper + Forecaster + Optimizer 결과 종합 보고서.

Spec: docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.3
"""
from __future__ import annotations
import json
import uuid
from dataclasses import dataclass
from datetime import date
from openai import AzureOpenAI
from pipeline.db import PGClient
from pipeline.state import Activity

SYSTEM_PROMPT = """건설 현장 작업일보 종합 보고서 생성기.
입력 JSON 의 (1) 매핑 결과 (mapped) (2) 진단 (forecast) (3) 권고 (optimizer_advice) 를 받아
마크다운 종합 보고서 1 종을 생성한다.

출력 schema (마크다운, 머리말 + 3 부):
  # YYYY-MM-DD 작업일보 종합 보고서

  ## 1부 작업 통합
    - trade/BP사별 인원·물량·작업 요지 (mapped 합산)
    - 표 우선, 행 많으면 bullet

  ## 2부 생산성 진단
    - 공종별 today_productivity / risk_level / reasoning (forecast row 별 1 단락)
    - assessment=None (cold_start) 인 경우 "데이터 부족 — 판단 보류" 그대로 유지

  ## 3부 PM 선택 공종 권고 (optimizer_advice 가 비어있으면 본 부 전체 생략)
    - 공종별 diagnosis + recommendations rank 1~4 (optimizer_advice row 별)
    - recovery_distribution 가 있으면 footnote 인용

규칙:
  - 마크다운만 (HTML 사용 금지, 한자 사용 금지 — 한글 + 영어만)
  - 들여쓰기 1~2 단계만 (3 단계 이상 금지)
  - 텍스트는 한국어 위주, 코드/식별자/외래어 고유명사만 영어
  - 진단의 risk_level 과 reasoning 이 의미적으로 정합되도록 (분류 결과 뒤집지 말 것)
"""

@dataclass
class ReporterConfig:
    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    llm_model: str
    postgres_url: str
    azure_timeout: float = 60.0
    azure_max_retries: int = 3

async def report(
    mapped: list[Activity],
    forecast_rows: list[dict],
    optimizer_advice: list[dict],
    run_id: uuid.UUID,
    today: date,
    cfg: ReporterConfig,
) -> tuple[str, dict]:
    # 1. mapped empty 시 fallback
    if not mapped:
        return ("# 보고서 생성 실패\n매핑 데이터 없음.", {})
    
    # 2. LLM input 합성
    llm_input = {
        "date": today.isoformat(),
        "activities": [...],         # mapped 요약
        "forecast": forecast_rows,    # Forecaster 결과
        "optimizer_advice": optimizer_advice,  # 빈 list 가능
    }
    
    # 3. Azure 호출 (retry 3, timeout 60s)
    client = AzureOpenAI(...)
    response = client.chat.completions.create(
        model=cfg.llm_model,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": json.dumps(llm_input, ensure_ascii=False)}],
    )
    report_md = response.choices[0].message.content
    
    # 4. summary JSONB 산출
    summary = {
        "total_workers": sum(a["assigned_workers"] for a in mapped),
        "total_qty_by_trade": {...},
        "risk_counts": {"정상": ..., "주의": ..., "이상": ...},
        "advice_count": len(optimizer_advice),
    }
    
    return (report_md, summary)


# graph.py 안에 reporter_node 추가
async def reporter_node(state: CPIAState, cfg: GraphConfig) -> dict:
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    today = date.fromisoformat(state["date"])
    report_md, summary = await report(
        state["mapped"], state["forecast"], state.get("optimizer_advice", []),
        run_id, today, cfg.reporter,
    )
    pg = PGClient(cfg.reporter.postgres_url)
    await pg.connect()
    try:
        await pg.insert_daily_report(run_id, today, report_md, summary)
    finally:
        await pg.close()
    return {"report_md": report_md, "current_node": "reporter"}
```

`GraphConfig` 에 `reporter: ReporterConfig` 필드 추가 (graph.py:32~37).

**PG client method 신규 2:**
- `PGClient.insert_mapping_correction(run_id, date, work_content, company, trade, original, corrected, correction_type)`
- `PGClient.insert_daily_report(run_id, date, report_md, summary)`

**Few-shot 1 건 (Reporter LLM prompt):**

```json
INPUT (golden fixture):
{
  "date": "2025-09-27",
  "activities": [
    {"company": "남웅건설", "trade": "철근콘크리트공사", "l6_main": "철근콘크리트공사",
     "unit": "m3", "today_qty": 14.0, "assigned_workers": 31.0,
     "work_content": "1F 벽체 콘크리트 타설"},
    {"company": "세보엠이씨", "trade": "일반공조설비공사", "l6_main": "일반공조설비공사",
     "unit": "m2", "today_qty": 120.0, "assigned_workers": 12.0,
     "work_content": "AHU 덕트 조립"}
  ],
  "forecast": [
    {"company": "남웅건설", "l6_main": "철근콘크리트공사",
     "today_productivity": 0.452, "assessment": "이상", "risk_level": "이상",
     "reasoning": "맑음, 병행작업 없음. 유사 5건 평균 0.78 m3/인 대비 -42%. work_content 에 '타워크레인 대기' 기재 — 장비 스케줄 충돌 가능성."}
  ],
  "optimizer_advice": [
    {"company": "남웅건설", "l6_main": "철근콘크리트공사", "forecast_assessment": "이상",
     "diagnosis": "타워크레인 스케줄 충돌로 인한 강한 저하. 잔여 물량 대비 D+5 시 4일 지연 추정.",
     "recommendations": [
       {"rank": 1, "text": "내일 오전 타워크레인 스케줄 확인 필수"},
       {"rank": 2, "text": "과거 패턴상 장비 확보 시 다음날 자연 복귀 가능성 높음"}
     ],
     "recovery_distribution": {"d+1": 2, "d+5": 1, "not_recovered": 1}}
  ]
}
```

```markdown
OUTPUT (LLM 산출 기대):
# 2025-09-27 작업일보 종합 보고서

## 1부 작업 통합

| 공종 | BP사 | 인원 | 물량 | 단위 | 주요작업 |
|---|---|---:|---:|---|---|
| 철근콘크리트공사 | 남웅건설 | 31.0 | 14.0 | m3 | 1F 벽체 콘크리트 타설 |
| 일반공조설비공사 | 세보엠이씨 | 12.0 | 120.0 | m2 | AHU 덕트 조립 |

## 2부 생산성 진단

**남웅건설 / 철근콘크리트공사** — risk_level: 이상, productivity 0.452 m3/인
> 맑음, 병행작업 없음. 유사 5건 평균 0.78 m3/인 대비 -42%. work_content 에 '타워크레인 대기' 기재 — 장비 스케줄 충돌 가능성.

## 3부 PM 선택 공종 권고

### 남웅건설 / 철근콘크리트공사
**진단:** 타워크레인 스케줄 충돌로 인한 강한 저하. 잔여 물량 대비 D+5 시 4일 지연 추정.

권고사항:
1. 내일 오전 타워크레인 스케줄 확인 필수
2. 과거 패턴상 장비 확보 시 다음날 자연 복귀 가능성 높음

> recovery_distribution: d+1=2건 / d+5=1건 / not_recovered=1건
```

→ 본 few-shot 은 `pipeline/tests/test_reporter.py` 의 golden fixture 로 활용 (LLM mock test 의 expected output prefix 검증용 + 통합 테스트 의 LLM 응답 정합성 검증).

## 6. 데이터 플로

```
[1] mapper_node
  → mapped: list[Activity] (일부 requires_review=True)
[2] hil_1_node (신규)
  → review_needed 필터 → interrupt(payload) → CLI prompt → corrections
  → mapped 수정 + PG mapping_corrections INSERT
[3] atomizer_node → 변경 X (Chroma 적재)
[4] forecaster_node → 변경 X (단 synthetic fixture fix 가 input 영향)
[5] hil_2_node → 변경 X
[6] optimizer_node → 변경 X (selection=[] 시 skip)
[7] reporter_node (신규)
  → mapped + forecast + optimizer_advice → Azure LLM → state.report_md
  → PG daily_reports INSERT
```

**state 변경 0건. PG schema 변경 0건. PG client method 신규 2.**

## 7. 에러 핸들링

### 7.1 HIL 1
- **사용자 입력 validation:** PoC 우선 — validation 생략. Master 에 없는 wa 도 그대로 적용. Mapper 다음 run 진입 시 `mapping_corrections` 검색으로 자가 학습 (postgres.md:311 의도).
- **일부만 정정:** 답 안 한 row 의 `requires_review=True` 유지 → Atomizer 진입 (Chroma 적재는 됨), 다음 run 에서 재정정.
- **CLI parsing error:** re-prompt 최대 3 회 → abort (Exit 3).
- **KeyboardInterrupt:** LangGraph default — checkpoint 에 waiting_hil_1 상태 저장 후 종료.

### 7.2 Forecaster fix
- **n_activities=0:** `_parse_scenario` 에 검사 추가 → ValueError.
- **baseline_q=0** (Master 미등록 그룹): 기존 cold_start path — aggregate.py 빈 dict 산출 → main_unit=None → assessment=None.
- **RAG 정합 회귀 테스트:** ±10% 임계 위반 시 pytest FAIL.

### 7.3 Reporter
- **Azure 호출 실패:** ForecasterConfig 패턴 차용 (timeout=60s, max_retries=3).
- **mapped empty:** "보고서 생성 실패: 매핑 데이터 없음" 짧은 MD + PG INSERT skip.
- **LLM 빈 응답:** retry 1 회 → fallback short MD.
- **PG INSERT FK violation:** `pg.assert_pipeline_run_exists(run_id)` 차용 (forecaster/agent.py:249).

### 7.4 전반
- **LangGraph checkpoint: PostgresSaver 전환** (design-intent/design_intent_orchestration.md:246 + architecture_overview.md O-6 권고 — "Reporter cycle 또는 통합 cycle 진입 시 전환"). 본 cycle = 통합 cycle 진입 = 전환 적기.
  - `pipeline/checkpointer.py:13 build_checkpointer()` 수정 — `InMemorySaver` → `PostgresSaver`
  - `langgraph-checkpoint-postgres` 의존성 추가 (pyproject.toml / requirements.txt)
  - `checkpoints` 테이블 LangGraph auto-manage (`PostgresSaver.from_conn_string` 호출 시 자동 생성)
  - 회귀: 기존 HIL 2 e2e 테스트들 (test_graph_e2e_hil2.py 4개) 가 thread_id 별 fresh checkpointer 박는 패턴 — 영향 격리 확인 필요. 회귀 발생 시 fallback flag 로 InMemorySaver 유지 분기 추가.

## 8. 테스트 전략

### 8.1 HIL 1 (신규 2 파일)
- `pipeline/tests/test_graph_hil1.py` — unit:
  - review_needed 필터 (requires_review=True 만, empty 시 interrupt 미발생)
  - corrections 적용 후 Activity wa/l6_main/mapping_source/requires_review 수정
  - 일부만 정정 시 잔여 row 의 requires_review 유지
- `pipeline/tests/test_graph_e2e_hil1.py` — 통합:
  - build_graph 진입 → interrupt → Command(resume=) → 결과 검증
  - HIL 1 + HIL 2 둘 다 발생 시나리오

### 8.2 Forecaster fix (기존 확장)
- `pipeline/tests/optimizer/test_synthetic_daily_report.py`:
  - **재현 (fix 전 FAIL):** ratio=0.45, n=5 → today_prod = 5 × baseline × 0.45
  - **픽스 후 PASS:** today_prod = baseline × 0.45
- **RAG 정합 회귀 (신규 테스트 함수):** synthetic_v2 정상일 productivity 평균 vs baseline_qty/base_workers 산출 productivity ±10% 이내
- **시뮬 4 건 실 호출 (Azure ~$0.10):** 본 cycle 종결 직전 게이트
  - 시나리오 1 (남웅 0.45) → assessment ∈ {"이상", "주의"}
  - 시나리오 2 (우천 0.8) → assessment="주의"
  - 시나리오 3 (돌관 0.45 ×1.3) → assessment ∈ {"이상", "주의"}
  - 시나리오 4 (cold_start) → assessment=None

### 8.3 Reporter (신규 1 파일)
- `pipeline/tests/test_reporter.py` — unit:
  - mapped+forecast+optimizer_advice 합성 prompt (golden fixture)
  - empty optimizer_advice 시 3부 권고 생략
  - Azure LLM mock + state.report_md 산출
  - PG INSERT mock 호출 검증
- 통합: 시뮬 1 (남웅 0.45) 1 건 실 Reporter 호출 → MD 산출 + PG `daily_reports` row 검증

### 8.4 회귀 baseline
- 현 baseline = **183 passed** (audit Task 0).
- 본 cycle 후 추정 = **183 + ~25 신규** (HIL 1 ~10 + Forecaster fix ~5 + Reporter ~10).
- **회귀 0 건 필수.**

### 8.5 결정성 검증 (audit Task 1 패턴 차용)
- 시뮬 1 (남웅 0.45) 동일 fixture 2 회 호출 → 결정론 컬럼 (today_productivity / risk_level / assessment / recovery_distribution) **100% 일치**.
- 자유텍스트 컬럼 (reasoning / recommendations / diagnosis / report_md) 은 LLM 비결정성 허용.

### 8.6 Azure 예산
- TDD unit: ~$0
- 시뮬 4 건 실 호출: ~$0.20
- rerun 결정성: ~$0.05
- Reporter 시뮬 1 호출: ~$0.10
- **총 ~$0.35**

## 9. 실행 절차 (병렬 atomic)

3 갭 사이 의존성 0 — 동시 atomic commit 진행 가능. PostgresSaver 전환 (§7.4 보강) 은 모든 graph 노드 / HIL 테스트에 영향 → 별 Task 로 분리. plan 단계에서 task 분리:

1. **Task 0 — 환경 점검 + 회귀 baseline** (현 183 passed 재확인)
2. **Task 1 — Forecaster fixture fix** (synthetic_daily_report.py:78 + 118 + 재현/픽스/RAG 정합 회귀 테스트)
3. **Task 2 — HIL 1 구현** (hil_1_node + graph edges + PG client method + CLI prompt + unit/e2e 테스트)
4. **Task 3 — Reporter 구현** (reporter.py + reporter_node + graph edges + PG client method + unit 테스트)
5. **Task 4 — PostgresSaver 전환** (신규 — design-intent O-6 권고 대응)
   - `pipeline/checkpointer.py` 수정 (InMemorySaver → PostgresSaver)
   - 의존성 추가 + `checkpoints` 테이블 auto-init 확인
   - 기존 HIL 2 e2e 테스트 (test_graph_e2e_hil2.py 4건) 회귀 검증 + 신규 HIL 1 e2e 테스트 (Task 2 산출) 회귀 검증
   - 회귀 발생 시 InMemorySaver fallback flag 분기
6. **Task 5 — 통합 검증** (회귀 183+~25 / 시뮬 4 건 실 호출 / 결정성 / 시뮬 1 Reporter 통합 / PostgresSaver checkpoint 영속 검증)
7. **Task 6 — 정리 + PR**

Task 1~3 은 의존성 0 → plan 단계에서 inline 순차 또는 subagent 병렬 선택 가능. Task 4 는 Task 2 + 3 완료 후 진입 (HIL 1 e2e 테스트가 회귀 대상이라). 사용자 결정 = 병렬 atomic (단 inline 실행 시 자연 순차).

## 10. 성공 기준

| # | 기준 | 검증 방법 |
|---|------|----------|
| 1 | HIL 1 interrupt + Command(resume=) 동작 | `pytest pipeline/tests/test_graph_e2e_hil1.py` PASS |
| 2 | Forecaster fixture fix 후 시뮬 1 (ratio=0.45) assessment ∈ {"이상", "주의"} | 시뮬 1 raw md fact |
| 3 | RAG 정합 회귀 테스트 ±10% 이내 PASS | `pytest pipeline/tests/optimizer/test_synthetic_daily_report.py::test_rag_alignment` |
| 4 | Reporter 종합 MD 산출 + PG INSERT | 시뮬 1 Reporter 통합 + `SELECT * FROM daily_reports WHERE run_id=$1` |
| 5 | 회귀 0 건 | `pytest pipeline/tests/` 183+~25 PASS |
| 6 | 결정성 검증 통과 | rerun diff = 0 (결정론 컬럼) |
| 7 | PostgresSaver checkpoint 영속 동작 | `pytest pipeline/tests/test_graph_e2e_hil2.py` 4건 + HIL 1 e2e PASS + `SELECT COUNT(*) FROM checkpoints WHERE thread_id=...` >= 1 |

## 11. 하드룰

- **Real code or no claim** — 모든 fact = `$ grep` 또는 `$ python3` 실 출력
- **No 한자** — 한글 + 영어만
- **Iron Law 3 요소** — `$ <명령어>` + `<실 출력>` + `→ <결론>`
- **TDD** — 신규 기능 = 실패 테스트 먼저, 버그 픽스 = 재현 테스트 먼저
- **회귀 0 건** — 183 baseline 유지
- **No fabrication** — 함수/파일/시그니처 모르면 grep 검증
- **macOS Apple Silicon, Python 3.9.6, `pipeline/.venv/bin/python3` 절대경로**
- **`from __future__ import annotations` 첫 줄 필수 (모든 .py)**

## 12. 핸드오프

본 spec → writing-plans skill → `docs/superpowers/plans/2026-05-17-cpia-hil1-forecaster-reporter-plan.md`.

plan 의 bite-sized task 분해:
- Task 0 환경 점검 (~5 step)
- Task 1 Forecaster fix (~10 step)
- Task 2 HIL 1 (~15 step)
- Task 3 Reporter (~15 step)
- Task 4 PostgresSaver 전환 (~10 step) — design-intent O-6 권고
- Task 5 통합 검증 (~10 step)
- Task 6 정리 + PR (~5 step)

총 ~70 step. inline (executing-plans) 또는 subagent (subagent-driven-development) 선택 가능.

---

**관련 문서:**
- `docs/audit/2026-05-17-cpia-e2e-audit-report.md` — 본 cycle 의 발견 출처
- `docs/audit/2026-05-17-cpia-drift-backlog.md` — 우선순위 #1+#2+#3+#4 통합
- `planning/CPIA_PoC_실행계획_v2.md` — PM 원안 v2
- `docs/schema/postgres.md` — daily_reports / mapping_corrections schema
- `docs/schema/mapping-layer.md` — Mapper 6단계 + WA 결정 4단계
