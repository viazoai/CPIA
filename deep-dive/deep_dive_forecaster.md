# Forecaster 서브시스템 Deep-Dive

> 갱신 baseline: `ef7c6cd` → HEAD `1ba783f` (Merge origin/main into A_Track, 2026-05-24)
> 작성 기준: 본 cycle 의 forecaster 관련 5 커밋 (6a89848 / 6ba0126 / 9856889 / bc04c94 / 1e24dc6) 반영
> Working tree 확인: `git diff pipeline/agents/forecaster/` = 빈 출력 → uncommitted 변경 없음 (다른 세션 작업 없음)

---

## 1. Overview

Forecaster 는 **(wa, company, l6_main) 단위 group 별 1 row** 씩 생산성 진단을 생성하는 LangGraph 노드다. Atomizer 가 채운 `state.mapped` (List[Activity]) 와 ChromaDB `daily_activities` 컬렉션 (synthetic 30일 + 실 누적) 을 입력으로 받아, group 별로 다음을 수행한다:

1. **오늘 집계** — Activity 들의 `today_qty` 를 unit 별 합 → max qty unit 을 `main_unit` 선택 → `today_productivity = today_qty[main_unit] / today_assigned_workers`
2. **Plan 조회** — PG `activity_master` 에서 (company, l6_main) candidate Σ → `plan_total_qty_by_unit / plan_mh_sum / plan_start / plan_finish`
3. **RAG 검색** — Chroma `daily_activities` 에 (company, l6_main) 필터로 `today_embed` 유사 top-K. Atomic schema 정규화 + rerank.
4. **Plan fallback** — RAG <3건 시 Plan 단위 productivity ratio (0.85 / 0.65) 분류로 떨어짐.
5. **assessment 분류** — 정상 / 주의 / 이상 / None (4 상태)
6. **delay 계산** — qty 기반: 잔여 물량 / 페이스 → expected_completion → delay_days = (expected_completion − plan_finish).days
7. **LLM reasoning + recovery_likelihood** — Azure OpenAI gpt-5.1, system + 3 few-shot + user input. JSON 응답.
8. **risk_level 분류** — assessment + recovery + delay + schedule_state hybrid 룰.
9. **forecasts INSERT** — 28 컬럼 (id/created_at auto 제외 26 데이터 + wa + main_unit/today_conditions).

**핵심 차별점:** 절대 기준 (품셈) 없이 RAG 우선 + Plan fallback hybrid 분류. cold start (RAG <3 + Plan 없음) 는 명시적 None + 데이터 부족 reasoning.

---

## 2. 파일 + LOC + 책임

| 파일 | LOC | 책임 |
|---|---|---|
| `pipeline/agents/forecaster/__init__.py` | 8 | `ForecasterConfig` / `forecast` / `WORK_HOURS_PER_DAY` re-export |
| `pipeline/agents/forecaster/agent.py` | **339** | LangGraph 진입점. `forecast()` orchestrator + `_forecast_one_group()` 8 phase. asyncio.gather + Semaphore (CPIA_LLM_CONCURRENCY=4) 동시성. |
| `pipeline/agents/forecaster/aggregate.py` | 202 | 순수 함수 4종 — `aggregate_today_by_unit` / `compute_delay` (qty 기반) / `fetch_chroma_actual` / `fetch_pg_actual_cum_qty` |
| `pipeline/agents/forecaster/classify.py` | 114 | 분류 룰 4종 — `classify_assessment_rag` / `classify_assessment_plan` / `classify_assessment` (routing) / `classify_risk_level` (hybrid) |
| `pipeline/agents/forecaster/rerank.py` | 50 | Chroma metadata 정규화 + rerank (worker_source / mapping_conf 가중치) |
| `pipeline/agents/forecaster/prompt.py` | 134 | `SYSTEM_PROMPT` + 3 `FEW_SHOT_MESSAGES` + `build_llm_user_input()` |
| `pipeline/agents/forecaster/synthetic.py` | 189 | PM 원안 v2 §3-B 변동 패턴 generator + CLI (Phase 1 더미 30일) |
| `pipeline/agents/forecaster/constants.py` | 8 | `WORK_HOURS_PER_DAY` re-export (pipeline.constants 로 승격) |
| **합계** | **1044** | |

---

## 3. 흐름 다이어그램

```
                 state.mapped (List[Activity])
                          │
                          ▼
       ┌──────────────────────────────────────────┐
       │ forecast() (agent.py:283)                │
       │ 1) PGClient / ChromaClient / AzureOpenAI │
       │    초기화 + pipeline_runs row 검증       │
       │ 2) groups: dict[(wa, company, l6), List] │
       │    — l6_main is None 스킵                │
       │    — work_content 빈 것 스킵             │
       │ 3) sem = get_llm_semaphore()  (4×)       │
       │ 4) asyncio.gather(*[_one(k,v) ...])      │
       └──────────────────────────────────────────┘
                          │ per group (parallel ≤4)
                          ▼
       ┌──────────────────────────────────────────┐
       │ _forecast_one_group() (agent.py:73)      │
       │                                          │
       │ ① 집계 (aggregate_today_by_unit)        │
       │    └─ main_unit = max qty unit           │
       │    └─ today_productivity                 │
       │    └─ conditions_set (union)             │
       │                                          │
       │ ② Plan (pg.fetch_plan_for_group)        │
       │    └─ activity_master Σ                  │
       │                                          │
       │ ③ RAG ─ azure.embeddings.create →       │
       │       coll.get preflight count →        │
       │       coll.query (safe_n) →              │
       │       date window cut →                  │
       │       rerank → top_K                     │
       │                                          │
       │ ④ classify_assessment (RAG 우선)        │
       │    └─ rag_n≥3 → RAG / else Plan / None  │
       │    └─ plan_main_qty = mapper distinct   │
       │       SUM (Fix 6a89848)                  │
       │                                          │
       │ ⑤ compute_delay (qty 기반)              │
       │    └─ fetch_chroma_actual (mh window)   │
       │    └─ fetch_pg_actual_cum_qty           │
       │    └─ remaining_qty / pace →            │
       │       expected_completion               │
       │                                          │
       │ ⑥ LLM ─ async with sem:                │
       │    azure.chat.completions.create        │
       │    └─ system + 3 few-shot + user JSON   │
       │    └─ {reasoning, recovery_likelihood}  │
       │    (assessment is None → LLM skip)      │
       │                                          │
       │ ⑦ classify_risk_level (hybrid)          │
       │                                          │
       │ ⑧ row dict (28 컬럼)                    │
       └──────────────────────────────────────────┘
                          │
                          ▼
       pg.insert_forecast(row)  ─ sem 밖 (asyncpg pool thread-safe)
                          │
                          ▼
                 List[forecast row] → state.forecast
```

---

## 4. Public 함수 / 클래스 표

| symbol | 파일 | 시그니처 | 역할 |
|---|---|---|---|
| `ForecasterConfig` | agent.py:40 | `@dataclass` — azure_*, llm_model, embedding_model, postgres_url, chroma_*, rag_n_candidates(10) / rag_top_k(5) / rag_window_days(30) | 설정 컨테이너. temperature 미박음 (gpt-5 family 미지원). |
| `forecast` | agent.py:283 | `async (mapped, run_id, today, cfg) -> list[dict]` | entry point — group 화 + gather + INSERT |
| `_forecast_one_group` | agent.py:73 | `async (company, l6_main, activities, run_id, today, pg, coll, azure, cfg) -> dict` | group 1건 처리 (spec §1 ①~⑧) |
| `_format_chroma_result` | agent.py:59 | `(rag_result) -> list[dict]` | Chroma query 결과 → rerank 입력 변환 |
| `aggregate_today_by_unit` | aggregate.py:43 | `(activities) -> dict[str, float]` | today_qty Σ by unit |
| `compute_delay` | aggregate.py:52 | `(plan, today, actual_window_start, actual_cum_mh, *, actual_cum_qty, plan_total_qty_main, today_qty_main) -> dict` | qty 기반 delay 산식 |
| `fetch_chroma_actual` | aggregate.py:157 | `(coll, company, l6_main, today, today_assigned_workers, *, today_qty_main, main_unit) -> (window_start, actual_cum_mh, actual_cum_qty)` | Chroma window 누적 (mh 만 사용) |
| `fetch_pg_actual_cum_qty` | aggregate.py:14 | `async (pg, company, l6_main, today, main_unit) -> float` | PG mapper_activities source of truth |
| `classify_assessment_rag` | classify.py:27 | `(today_prod, rag_avg_prod) -> str` | delta ±15%/±25% |
| `classify_assessment_plan` | classify.py:41 | `(today_prod, plan_total_qty_main, plan_mh_sum) -> str` | ratio 0.85/0.65 |
| `classify_assessment` | classify.py:65 | `(rag_n, today_prod, rag_avg_prod, plan_total_qty_main, plan_mh_sum) -> Optional[str]` | RAG ≥3 → RAG / else Plan / else None |
| `classify_risk_level` | classify.py:83 | `(assessment, recovery_likelihood, delay_days, schedule_state) -> Optional[str]` | hybrid 룰 |
| `rerank_cases` | rerank.py:32 | `(cases) -> list[dict]` | rerank_score 오름차순 |
| `_normalize_chroma_metadata` | rerank.py:20 | `(m) -> dict` | atomizer schema → Forecaster schema |
| `build_llm_user_input` | prompt.py:103 | `(today, similar_cases, plan, assessment) -> dict` | user message JSON |
| `SYSTEM_PROMPT` | prompt.py:12 | const | 진단 전문가 페르소나 + 3 단계 reasoning + JSON schema |
| `FEW_SHOT_MESSAGES` | prompt.py:93 | const list | 정상 / 주의 / 이상 1건씩 |
| `generate_synthetic_day` | synthetic.py:21 | `(base_row, day_offset, weather, incident, reference_date) -> dict` | 1 row variation |

---

## 5. agent.py forecast() — 진입점 + asyncio.gather 4× 동시성

`forecast(mapped, run_id, today, cfg)` (agent.py:283) 가 LangGraph `forecaster_node` (graph.py:301) 의 핵심 호출.

**진입 시퀀스:**
1. `PGClient.connect()`, `ChromaClient.get_or_create_daily_activities()`, `AzureOpenAI` 초기화
2. `pg.assert_pipeline_run_exists(run_id)` — fixture 미설정 silent no-op 방지
3. group 화 — key = `(wa, company, l6_main)` (`a["l6_main"] is None` / `not work_content` 둘 다 스킵)
4. `sem = get_llm_semaphore()` 를 **함수 entry 에서 한 번** 호출. helper 가 매 호출 새 인스턴스 반환 → closure 로 공유 필수 (6ba0126 패치)
5. `tasks = [_one(k, v) for k, v in groups.items()]` → `await asyncio.gather(*tasks)`

**Concurrency 경계:** `_one()` 안에서
- `async with sem:` 안 → `await _forecast_one_group(...)` (LLM 호출 포함)
- sem 밖 → `await pg.insert_forecast(row)` (asyncpg pool 자체 thread-safe)

**효과:** ~120 group × 1 LLM call 시 직렬 10 분 → 병렬 4× 약 2.5 분 (commit message 측정).

---

## 6. classify.py — LLM classify (PM 원안 v2 정합) 산식

`classify_assessment_rag` (classify.py:27):
```
delta = (today_prod - rag_avg_prod) / rag_avg_prod    # rag_avg=0 → "정상"
eps   = 1e-9                                          # boundary 보호
delta >= -0.15 - eps  → "정상"
delta >= -0.25 - eps  → "주의"
else                  → "이상"
```
- 음수 delta 만 임계 (성능 미달만 강조). 양수 delta (생산성 ↑) 는 모두 "정상".

`classify_assessment_plan` (classify.py:41):
```
plan_prod_proxy = plan_total_qty_main / (plan_mh_sum / WORK_HOURS_PER_DAY)
                # 그 공종이 정상 진행 시 1 인-day 가 만드는 unit 수
ratio = today_prod / plan_prod_proxy
ratio >= 0.85 → "정상"
ratio >= 0.65 → "주의"
else          → "이상"
```
- `plan_mh_sum <= 0` 또는 `plan_total_qty_main <= 0` → "정상" (방어).

`classify_assessment` (classify.py:65, **routing**):
```
rag_n >= 3              → RAG mode
elif plan 가용          → Plan fallback
else                    → None (cold start)
```

`classify_risk_level` (classify.py:83, **hybrid**):
```
assessment is None     → None
schedule_state==post_due → "이상"
schedule_state==unknown 또는 delay_days is None → assessment

assessment=="정상":
    delay_days > 5 → "주의" / else "정상"

assessment=="주의":
    recovery >= 0.7 AND delay_days <= 5 → "주의" / else "이상"

assessment=="이상":
    delay_days <= 0 → "주의" / else "이상"
```

---

## 7. rerank.py — RAG hit 의 rerank 산식

`rerank_cases` (rerank.py:32):
```
for c in cases:
    meta = _normalize_chroma_metadata(c.metadata)
    score = c.distance                       # 작을수록 가까움 (cosine distance)
    if meta.worker_source == "user_corrected":
        score *= 0.7                         # H-i-L 1 수정값 우대
    if meta.mapping_conf < 0.7:
        score *= 1.5                         # 매핑 약한 케이스 패널티
    out.append({**c, metadata: meta, rerank_score: score})
return sorted(out, key=lambda x: x.rerank_score)   # 오름차순
```

caller (agent.py:144) 가 `[:cfg.rag_top_k]` (기본 5) 잘라서 사용.

`_normalize_chroma_metadata` (rerank.py:20):
- atomizer 가 콤마 join 한 `conditions` 문자열 → `list[str]` 복원
- `productivity = today_qty / assigned_workers` derive (Chroma 미저장 → 매 호출 계산)

---

## 8. aggregate.py — group level aggregate (T18 mh reference only docstring 의미)

`compute_delay` (aggregate.py:52) 의 docstring 명시 (bc04c94):

> **qty 기반 delay 산식 (2026-05-22 fix)**
> 이전: mh-window deficit / plan_mh_per_day → 양 충족인데도 mh 부족이면 큰 delay.
> 이제: 잔여 물량 / 페이스 → expected_completion → delay (expected − plan_finish).
>
> **부수 (mh) 컬럼 (reference only — delay 산출 사용 X, PG schema 영향 회피):**
> - `plan_mh_per_day`: plan_mh_sum / total_days (기준 일 평균 인시)
> - `expected_in_window_mh`: plan_mh_per_day × window_days (window 누적 기준)
> - `actual_in_window_mh`: actual_cum_mh (Chroma window 누적 실 인시)
> - `mh_gap`: expected_in_window_mh − actual_in_window_mh (참고용)
> 위 4값은 forecast row jsonb 에 박혀 UI 미사용. 향후 mh 기반 KPI 위한 잠재 자산.

핵심 산식:
```
remaining_qty   = max(0, plan_total_qty_main - actual_cum_qty)
avg_pace_qty    = actual_cum_qty / window_days   (≤0 → today_qty_main fallback)
remaining_days  = remaining_qty / pace
expected_completion = today + timedelta(days=round(remaining_days))
delay_days      = (expected_completion - plan_finish).days
                  (양수 = 지연, 음수 = 앞당김, 0 = 충족)
```

`schedule_state`:
- plan 없음 → "unknown"
- today < plan_start → "early"
- plan_start ≤ today ≤ plan_finish → "on_schedule"
- today > plan_finish → "post_due"

`fetch_pg_actual_cum_qty` (aggregate.py:14) docstring:
> **2026-05-22**: Chroma 는 mapper 의 일부만 backfill 되어 있어 (광건 수장공사 22% 만 적재 케이스 확인) actual_cum_qty 산출에 부적합. PG mapper_activities 가 source of truth. 시연 환경 (`is_mock=false`) 만 합산.

`fetch_chroma_actual` (aggregate.py:157) 반환 의미:
- `window_start`: Chroma 내 (company, l6_main) 첫 적재 일자 (None = 데이터 없음)
- `actual_cum_mh`: window 내 워커 일수 × WORK_HOURS_PER_DAY 누적 (compute_delay 의 reference mh 산출 input)
- `actual_cum_qty`: 보조 reference (실 사용 X) — caller 가 무시하고 `fetch_pg_actual_cum_qty` 결과 사용

---

## 9. synthetic.py — fallback 진단 (Phase 1 cold-start 보충)

⚠️ 주의: synthetic.py 는 **runtime RAG hit 0건 fallback 이 아니라** Phase 1 cold start 용 Chroma 시드 generator. RAG hit 0건 fallback 은 classify.py 의 `classify_assessment` 가 Plan ratio 또는 None 으로 처리한다.

`generate_synthetic_day(base_row, day_offset, weather, incident, reference_date)` (synthetic.py:21) — PM 원안 v2 §3-B 변동 패턴:

```
delta = 0
weather=="우천"        → delta -= random.uniform(0.15, 0.25)
incident=="장비대기"    → delta -= random.uniform(0.20, 0.35)
incident=="자재미입고"  → delta -= random.uniform(0.10, 0.20)
delta += random.uniform(-0.05, 0.05)    # 기본 변동

today_qty   = base_row.today_qty * (1 + delta)
conditions  = [weather] + ([incident] if incident != "정상" else [])
date        = reference_date - timedelta(days=day_offset)
```

CLI (`_main_cli`, synthetic.py:65):
- 9/25 매핑 결과 ~30 unique (company, l6_main) × 30 일 = ~900 Chroma row
- weathers / incidents 분포: 맑음 70% / 우천 20% / 흐림 10%, 정상 80% / 장비대기 10% / 자재미입고 10%
- atomizer 와 동일 `_build_metadata()` schema 사용 (spec B-1)
- doc_id = `sha256("synthetic|date|company|l6_main|work_content")[:16]`

---

## 10. prompt.py — LLM prompt 전수

**SYSTEM_PROMPT** (prompt.py:12, 한국어 그대로):
```
당신은 건설 현장 생산성 분석 전문가다.
주어진 오늘 실적·과거 유사 사례·자동 분류 결과를 바탕으로 reasoning 1~2 문장을 작성한다.

reasoning 의 3 단계 구조 (필수):
  1. 오늘 조건 명시 — 날씨, conditions, work_content 요지
  2. RAG 비교 — 유사 N건 평균 대비 X% (assessment 결정 근거)
  3. 원인 추론 — work_content 텍스트 분석. 정상 시 생략 가능.

출력 schema (JSON):
  { "reasoning": str, "recovery_likelihood": float (0.0~1.0) | null }

규칙:
  - reasoning 은 입력의 assessment 와 정합되어야 한다 (분류 결과를 뒤집지 말 것)
  - assessment = "정상" → recovery_likelihood = null
  - recovery_likelihood = RAG 유사 사례에서 다음날 회복한 비율 추정
```

**FEW_SHOT_MESSAGES** (prompt.py:33~88): 3 쌍 (user/assistant), `ensure_ascii=False`:

| # | company / l6_main | today_prod | 유사 | assessment | reasoning 요지 | recovery |
|---|---|---|---|---|---|---|
| 1 | Y건설 / 거푸집공사 | 22.9 | 21.3 (+8%) | 정상 | 우천 + 병행작업, 정상 변동 범위 | null |
| 2 | 세보엠이씨 / 일반공조설비 | 0.14 | 0.18 (-22%) | 주의 | 자재 미입고 — 단기 회복 가능 | 0.7 |
| 3 | 남웅건설 / 철근콘크리트 | 1.8 | 2.6 (-31%) | 이상 | 타워크레인 대기 — 장비 충돌 | 0.8 |

prompt.py:91 주석: `ensure_ascii=False` 는 한글 출력을 위함이며 사용자 전역 CLAUDE.md "No 한자" 룰은 CJK ideograph 금지 (한글 허용). 위 reasoning 텍스트는 모두 한글.

**`build_llm_user_input`** (prompt.py:103) 생성 JSON:
```json
{
  "today": {"company","l6_main","today_qty_by_unit","today_assigned_workers","today_productivity","conditions","work_content"},
  "similar_cases": [{"date","productivity","conditions","work_content[:80]"}, ...],
  "plan": {"plan_total_qty_by_unit","plan_mh_sum"},
  "assessment_by_code": "정상|주의|이상"
}
```

호출 시 `response_format={"type": "json_object"}` 강제 (agent.py:229).

---

## 11. constants.py — 4분면 임계값

`pipeline/agents/forecaster/constants.py` (8 LOC):
```python
from pipeline.constants import WORK_HOURS_PER_DAY  # noqa: F401
```
=> `pipeline.constants.WORK_HOURS_PER_DAY = 8` (re-export, 후방 호환).

분류 임계값은 `classify.py:18~24` 에 상수화 (commit 8123554 권고 #7 후속):

| 상수 | 값 | 의미 |
|---|---|---|
| `RAG_NORMAL_BOUND` | 0.15 | RAG delta ±15% 까지 "정상" |
| `RAG_WARN_BOUND` | 0.25 | ±15~25% "주의", 초과 "이상" |
| `PLAN_NORMAL_RATIO` | 0.85 | Plan ratio ≥0.85 "정상" |
| `PLAN_WARN_RATIO` | 0.65 | 0.65~0.85 "주의", 미만 "이상" |
| `DELAY_DAYS_BOUND` | 5 | "정상 + delay>5 → 주의" / "주의 + recovery≥0.7 AND delay≤5 → 주의 유지" 임계 |
| `RECOVERY_LIKELIHOOD_BOUND` | 0.7 | "주의 + recovery 회복 가능" 임계 |

`WORK_HOURS_PER_DAY=8` 은 `classify_assessment_plan` 의 `plan_prod_proxy` 분모와 `fetch_chroma_actual` 의 mh 환산 양쪽에 사용.

---

## 12. RAG retrieve 흐름 — Chroma daily_activities

**Embedding:** `azure.embeddings.create(model=cfg.embedding_model, input=[work_content])` (1536d `text-embedding-3-small-ai-board-test`)

**Where filter** (단일 operator 제약 회피, commit 2107782):
```python
where_filter = {"$and": [{"company": company}, {"l6_main": l6_main}]}
```
- date range 는 Chroma `$gte/$lt` 가 숫자 전용이라 코드단에서 cut.

**Preflight count** (commit a7ceb5d, agent.py:118):
```python
preflight = coll.get(where=where_filter, include=[])
n_filtered = len(preflight.get("ids", []) or [])
safe_n = min(cfg.rag_n_candidates, n_filtered, 5)
```
- 이유: AWS Chroma 의 HNSW `ef_search=10` boundary case ("ef or M too small" 에러) 회피 — `n_results < ef_search` 보장. cap=5 명시.

**Query:**
```python
rag_result = coll.query(
    query_embeddings=[today_embed],
    where=where_filter,
    n_results=safe_n,
)
```
- 실패 시 Plan fallback (try/except, agent.py:130).

**Date window cut** (agent.py:139):
```python
window_start_iso = (today - timedelta(days=cfg.rag_window_days)).isoformat()   # 30일
today_iso = today.isoformat()
similar_cases_in_window = [
    c for c in similar_cases_raw
    if window_start_iso <= c["metadata"]["date"] < today_iso
]
```
- 오늘 자기자신 제외 (`< today_iso`).

**Rerank → top-K:** `rerank_cases(similar_cases_in_window)[:cfg.rag_top_k]` (기본 5).

---

## 13. forecasts 테이블 28 컬럼 — 어느 단계가 어느 컬럼 채우나

infra/postgres/init.sql:51~94 + db.py:260 `insert_forecast` 28 컬럼 매핑:

| # | 컬럼 | 타입 | 채우는 단계 | 비고 |
|---|---|---|---|---|
| auto | `id` | BIGSERIAL | PG | |
| 1 | `run_id` | UUID FK | forecast() entry | ON DELETE CASCADE |
| 2 | `company` | TEXT | group key | |
| 3 | `l6_main` | TEXT | group key | |
| 4 | `today_qty_by_unit` | JSONB | ① 집계 (`aggregate_today_by_unit`) | |
| 5 | `today_assigned_workers` | NUMERIC | ① (activities[0]) | |
| 6 | `today_productivity` | NUMERIC | ① (today_qty[main_unit] / workers) | |
| 7 | `plan_total_qty_by_unit` | JSONB | ② `pg.fetch_plan_for_group` | |
| 8 | `plan_mh_sum` | NUMERIC | ② | |
| 9 | `plan_start` | DATE | ② MIN(activity_master.plan_start) | |
| 10 | `plan_finish` | DATE | ② MAX(activity_master.plan_finish) | |
| 11 | `plan_mh_per_day` | NUMERIC | ⑤ compute_delay | reference only |
| 12 | `schedule_state` | TEXT | ⑤ | early/on_schedule/post_due/unknown |
| 13 | `window_start` | DATE | ⑤ (fetch_chroma_actual) | |
| 14 | `window_days` | INT | ⑤ | |
| 15 | `expected_in_window_mh` | NUMERIC | ⑤ | reference only |
| 16 | `actual_in_window_mh` | NUMERIC | ⑤ | reference only |
| 17 | `mh_gap` | NUMERIC | ⑤ | reference only |
| 18 | `delay_days` | NUMERIC | ⑤ qty 기반 | (expected_completion − plan_finish).days |
| 19 | `rag_n_similar` | INT | ③ (top-K len) | |
| 20 | `similar_cases` | JSONB | ③ top-5 brief (date/prod/conditions) | |
| 21 | `assessment` | TEXT | ④ `classify_assessment` | 정상/주의/이상/NULL |
| 22 | `reasoning` | TEXT | ⑥ LLM 또는 cold start 분기 텍스트 | |
| 23 | `recovery_likelihood` | NUMERIC | ⑥ LLM | 정상 / cold start → NULL |
| 24 | `expected_completion` | DATE | ⑤ delay_info.get | None 시 plan_finish 대체 |
| 25 | `risk_level` | TEXT | ⑦ `classify_risk_level` | hybrid |
| 26 | `main_unit` | TEXT | ① (max qty unit) | v3.1 Optimizer / hil_2 consume |
| 27 | `today_conditions` | TEXT | ① comma-joined conditions_set | v3.1 |
| 28 | `wa` | TEXT | _one() 에서 key 의 wa 부여 | Phase 2 |
| auto | `created_at` | TIMESTAMPTZ | PG `default now()` | |

---

## 14. plan_main_qty atomic 1:1 매칭 (commit 6a89848)

**이전** (agent.py 73 LOC 패치 전):
```python
plan_main_qty = plan["plan_total_qty_by_unit"][main_unit] if (plan and main_unit) else None
```
- `plan["plan_total_qty_by_unit"]` 는 `activity_master` 의 (company, l6_main) **전체 l6 SUM** (l6 일 전체 활동 합).
- 매칭된 atomic activity 가 그 l6 의 일부일 때 분모 과대 → `remaining_qty / pace = remaining_days` 폭주.

**현재** (agent.py:156~164):
```python
if main_unit:
    plan_qtys = {
        round(float(a["plan_total_qty"]), 4)
        for a in activities
        if a.get("unit") == main_unit and a.get("plan_total_qty") is not None
    }
    plan_main_qty = sum(plan_qtys) if plan_qtys else None
else:
    plan_main_qty = None
```
- group 안 mapper_activities (= `activities` list) 의 main_unit 매칭 `plan_total_qty` 의 **distinct value SUM**.
- mapper.plan_total_qty 는 atomic 매칭 broadcast (같은 wbs 가 multiple mapper row 면 동일 값) → `set` 으로 double count 방지.

**검증 결과** (commit message 인용, 9/22 site):
- 진특수 방수: l6 SUM=10,523 vs atomic=194 (54×) → delay 26,517 → top5 에서 사라짐
- 자동제어공사: 2,622 → -170 (앞당김)
- 장평건설 포장: 1,358 → 512 (-62%)
- 동신패널 외장판넬: 167,871 그대로 (atomic 1행 only — dummy seed anomaly, 산식과 무관)
- 회귀: 159 passed

영향: classify_assessment_plan 의 `plan_prod_proxy = plan_total_qty_main / (plan_mh_sum / 8)` 분자도 atomic SUM 으로 바뀌어 더 좁은 단위로 ratio 계산 (cold-start RAG <3 케이스). compute_delay 의 `remaining_qty` 도 동일 분모로 정상화.

---

## 15. LLM 호출 — 모델 / 회수 / Semaphore 4× 조정

**모델:** `cfg.llm_model = "gpt-5.1-chat-ai-board-test"` (Azure OpenAI). `ForecasterConfig` 주석 (agent.py:56):
> temperature 박지 않음 — spec C-1 정정 (gpt-5 family 미지원)

**회수:** group 당 **최대 1 회** (assessment is None → LLM skip, 데이터 부족 분기 텍스트만):
```python
if assessment is None:
    # cold start 분기 reasoning (agent.py:200~210)
    if main_unit is None:        → "오늘 물량 모든 unit 0 (인원만 투입). 판단 보류."
    elif plan is None:           → "Plan 미등록 + RAG <3건. 판단 보류."
    elif plan_main_qty is None:  → "main_unit '{}' 가 Plan unit set 에 없음 ... 판단 보류."
    else:                        → "데이터 부족 — RAG <3건. 판단 보류."
    recovery_likelihood = None
else:
    # azure.chat.completions.create
```

**Semaphore 4×** (agent.py:314):
```python
sem = get_llm_semaphore()  # closure 공유 — 함수 entry 에서 한 번
async def _one(...):
    async with sem:                           # LLM 호출만 sem 안
        row = await _forecast_one_group(...)
    row["wa"] = wa
    await pg.insert_forecast(row)             # asyncpg pool 자체 thread-safe → sem 밖
    return row
tasks = [_one(k, v) for k, v in groups.items()]
forecast_rows = list(await asyncio.gather(*tasks))
```

`get_llm_semaphore()` (pipeline/agents/_concurrency.py):
- env `CPIA_LLM_CONCURRENCY` (default 4)
- forecaster + optimizer + atomizer 가 공유 (같은 event loop 면 같은 인스턴스가 자연 공유)
- 매 호출 새 인스턴스 반환 → caller 가 closure 로 공유해야 함 (commit 6ba0126 가 명시)

**측정** (commit 6ba0126 message): ~120 group × 1 LLM call: 10분 → 2.5분 (4× 병렬).

**테스트:** `pipeline/tests/test_forecaster_concurrency.py` — cap 2 / 8 group → max_in_flight == 2 검증 (TDD).

---

## 16. 이슈 표

| # | 이슈 | 위치 | 영향 | 상태 |
|---|---|---|---|---|
| 1 | mh 컬럼 4개 (`plan_mh_per_day` / `expected_in_window_mh` / `actual_in_window_mh` / `mh_gap`) 가 UI 미사용 reference only | aggregate.py:75~80 | PG 저장만 됨, KPI 산출에 미연동 | 의도적 (향후 mh 기반 KPI 잠재 자산) |
| 2 | Chroma 일부만 backfill 되어 `actual_cum_qty` Chroma 산출 부정확 (광건 수장공사 22% 케이스) | aggregate.py:175~178 | PG `fetch_pg_actual_cum_qty` 로 우회 — Chroma 반환값은 보조 reference | mitigated (split path) |
| 3 | Chroma HNSW "ef or M too small" 에러 boundary case | agent.py:114~138 | Plan fallback 으로 graceful degrade. cap=5 + try/except 두 단계 방어 | mitigated (cycle 8차 재발 후 try/except 보강) |
| 4 | `classify_assessment_plan` 의 `plan_mh_sum<=0` 또는 `plan_total_qty_main<=0` 시 "정상" 반환 | classify.py:52 | 방어이지만 위험 누락 가능 (Plan 데이터 누락 = 정상 위장) | 의도적 (cold start 처리), 추후 None 으로 변경 검토 가능 |
| 5 | `aggregate_today_by_unit` 의 `today_assigned_workers = activities[0]["assigned_workers"]` 는 group 내 모든 Activity 가 동일 workers 라는 spec 옵션 X 가정에 의존 | agent.py:88 + state.py:35 | spec 위반 시 silent 0 또는 오차 | spec 옵션 X 채택 — `_prorate_mh` 이후 동일성 보장 |
| 6 | `expected_completion` None 시 `plan_finish` 로 대체 (PoC) | agent.py:275 | PG schema 영향 회피, Phase 2 에 추세 외삽 예정 | 의도적 (init.sql:90 주석) |
| 7 | synthetic.py 의 random.seed default=42 — CLI 옵션 있음 | synthetic.py:86 | 시드 결정적이지만 cold start 다양성 제한 | 의도적 (재현성) |
| 8 | Working tree 변경 없음 — 다른 세션 forecaster 작업 중 가능성 모니터링 항목 | 본 cycle 시점 git diff = 빈 출력 | — | clean |
| 9 | T18 commit bc04c94 가 docstring 만 추가 (산식 변경 없음) → docs/UI 와 산식 정합 reviewer 필수 | aggregate.py docstring | reference only 4 컬럼 의미 명문화 | resolved |

---

## 참고 — Spec & 관련 문서

- `docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md` (§5 aggregate, §6 classify, §7 rerank, §8 prompt, §9 synthetic, §10 agent)
- `docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md` (§2.3 WORK_HOURS 승격, v3.1 main_unit / today_conditions 추가)
- `docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md` (T1 / T4 / T18 round — 본 cycle 작업)
- `deep-dive/architecture_overview.md` (전체 LangGraph 흐름)
- `deep-dive/design-intent/design_intent_forecaster.md` (intent 카드)
- `infra/postgres/init.sql:47-99` (forecasts 28 컬럼)
- `infra/postgres/migrations/2026-05-16_forecaster.sql`, `2026-05-18_forecasts_wa.sql`
- `pipeline/tests/forecaster/` (test_agent / test_aggregate / test_classify / test_forecaster_e2e / test_forecaster_integration / test_forecaster_wa_grain / test_prompt / test_rerank / test_synthetic)
- `pipeline/tests/test_forecaster_concurrency.py` (Semaphore TDD)
