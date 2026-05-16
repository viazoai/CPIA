# CPIA Forecaster — 데이터 흐름 + 구현 spec

> **본 spec 의 산물**: Atomizer 다음 단계 Forecaster 의 데이터 계약 + 구현 spec. (company, l6_main) grain RAG 진단 + Plan fallback + delay_days (사용자 개념: 누적 mh window 비교) + risk_level hybrid 룰.
>
> 작성: 2026-05-16 (A 트랙) · 기반: PM 원안 (`planning/CPIA_PoC_실행계획_v2.md` 조형준 프로, `CLAUDE.md`, `docs/superpowers/specs/2026-05-14-cpia-2인-langgraph-협업-design.md`), downstream-agents spec (`docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md` §6), 9/25 실 작업일보 + PG `activity_master` schema + `pipeline/agents/atomizer.py` 실 metadata schema + `/tmp/cpia_forecaster_sim.py` 시뮬레이션.
>
> **brainstorming 채택 결정 8 + 3건 → reviewer 16건 정정 반영.**

---

## 0. 한눈에 보기 + 결정 사항

### 0.1 brainstorming 채택 결정 (8 + 3)

| # | 사안 | 결정 |
|---|---|---|
| ① | LLM 모델 | **Azure `gpt-5.1-chat-ai-board-test`** (Parser/Mapper/Reporter 와 동일 단일 모델). **temperature 파라미터 박지 않음** — Parser/Mapper 패턴 따름 (gpt-5 family reasoning 모델 미지원 가능성). |
| ② | Plan vs RAG 우선순위 | **RAG 우선 (≥3건) + Plan fallback (<3건)** — PM 원안 v2 §2 "품셈 제거 → RAG 컨텍스트 판단" 정수 |
| ③ | assessment 임계값 | **가정값 박고 회귀 후 조정** — Plan productivity ratio 0.85/0.65, RAG productivity delta ±15%/±25%. 코드 명시 분류 (LLM 자율 X). |
| ④ | RAG cold start | RAG=0 + Plan 없음 → `assessment = None`, LLM 호출 skip, reasoning = "데이터 부족, 판단 보류". row 자체는 생성. |
| ⑤ | row 구조 | 코드 결정 = assessment / expected_completion / delay_days / risk_level. LLM = reasoning + recovery_likelihood. |
| ⑥ | LLM prompt | **Few-shot 3건** (정상/주의/이상 1건씩, cold start 는 LLM skip 이라 미포함), 3 단계 reasoning, JSON 출력 schema. |
| ⑦ | RAG metadata 활용 | where filter (company, l6_main, date 30일) + Python rerank (worker_source=user_corrected ×0.7, mapping_conf<0.7 ×1.5) |
| ⑧ | synthetic history | **Phase 1 필수** — `scripts/generate_synthetic_history.py`. atomizer 와 동일 `_build_metadata()` schema 로 적재. |
| ⑨ | delay_days 정의 | **사용자 개념 — 누적 mh window 비교**. plan_mh_per_day × window_days vs 실제 누적. 음수 = ahead. PM 원안 v2 §4 "delay_days = 3" 의미 정합. |
| ⑩ | schedule_state | 3 enum — `"early"` (today < plan_start), `"on_schedule"`, `"post_due"` (today > plan_finish). post_due 는 risk_level="이상" 강제. plan 미등록 시 추가 enum `"unknown"`. |
| ⑪ | 모듈 분리 | **5 모듈 패키지** — `pipeline/agents/forecaster/{agent,aggregate,classify,rerank,prompt,synthetic}.py`. atomizer.py 도 향후 동일 패턴 리팩토링. |

### 0.2 추가 가정값 (회귀 후 조정)

| 임계 | 값 | 근거 |
|---|---|---|
| RAG delta 정상 | ≥ -15% | PM 원안 v2 §3-B "우천일 -15~25%" 정상 변동 범위 |
| RAG delta 주의 | -15% ~ -25% | 동일 |
| RAG delta 이상 | < -25% | 동일 |
| Plan productivity ratio 정상 | ≥ 0.85 | 일반적 진척률 (가정) |
| Plan productivity ratio 주의 | 0.65 ~ 0.85 | 동일 |
| Plan productivity ratio 이상 | < 0.65 | 동일 |
| `recovery_likelihood` 회복 가능 | ≥ 0.7 | PM 원안 v2 §3-B "다음날 회복 80%" 대비 conservative (0.7) |
| `delay_days` 회복 여유 임계 | ≤ 5일 | PM 원안 v2 §4 데모 예시 "D+3 이내 정상화" 변형 (5일로 여유) |

핵심 = `mapping-layer.md` 의 (WA, L6) 매핑 grain 을 Forecaster `(company, l6_main)` grain 으로 일관 유지. v1 골든 trade 단일 grain 대체 — downstream-agents-design.md 결정 #3 (옵션 X) 계승.

---

## 1. 데이터 흐름 정합

```
[Atomizer 완료 시점 — state]
  state["mapped"]:        list[Activity]  (~30 row, (company, l6_main) grain)
  state["atomized_ids"]:  list[str]
Chroma daily_activities: ≥900 row (synthetic 30일 + 9/25 atomize 결과)

                              ↓
┌──────────────────────── Forecaster ───────────────────────┐
│                                                           │
│  for each (company, l6_main) group in state.mapped:       │
│                                                           │
│   ① aggregate.py — 집계 (코드)                              │
│     today_qty_by_unit      = Σ Activity.today_qty by unit │
│     today_assigned_workers = Activity.assigned_workers    │
│     main_unit             = max(today_qty_by_unit) 의 unit │
│     today_productivity    = today_qty[main_unit]          │
│                              / today_assigned_workers      │
│                                                           │
│   ② aggregate.py — PG activity_master Σ (코드, 2 SQL)       │
│     plan_total_qty_by_unit = Σ plan_total_qty by unit     │
│     plan_mh_sum            = Σ plan_mh_rev2                │
│     plan_start             = MIN(plan_start)               │
│     plan_finish            = MAX(plan_finish)              │
│                                                           │
│   ③ rerank.py + agent.py — RAG 검색 + 정규화 + rerank        │
│     Chroma.daily_activities.query(                        │
│       query_embeddings=[embed(today work_content)],       │
│       where={"$and": [{"company": ...}, {"l6_main": ...}]},│
│       n_results=10)                                        │
│     # chromadb 0.5.20 validate_where: 단일 dict 다중 op +   │
│     # ISO string 피연산 거부 → date 30 일 윈도우는 코드단    │
│     # list-comp 컷 (agent.py _format_chroma_result 직후).   │
│     → _normalize_chroma_metadata (productivity derive,     │
│        conditions string→list)                            │
│     → rerank_cases (worker_source/mapping_conf 가중치)     │
│     → top-5 = similar_cases (agent.py 가 [:rag_top_k] 자름)│
│                                                           │
│   ④ classify.py — assessment 분류 (코드)                    │
│     if rag_n_similar >= 3:                                │
│       delta = (today_prod - rag_avg_prod) / rag_avg_prod  │
│       if delta >= -0.15: "정상"                           │
│       elif delta >= -0.25: "주의"                         │
│       else:                "이상"                          │
│     elif plan_mh_sum > 0:                                 │
│       plan_prod_proxy = plan_total_qty[main_unit]         │
│                          / (plan_mh_sum / 8)              │
│       today_prod_proxy = today_qty[main_unit]             │
│                          / today_workers                  │
│       ratio = today_prod_proxy / plan_prod_proxy          │
│       if ratio >= 0.85: "정상"                            │
│       elif ratio >= 0.65: "주의"                          │
│       else:               "이상"                          │
│     else:                                                 │
│       assessment = None  (cold start, LLM skip)           │
│                                                           │
│   ⑤ aggregate.py — compute_delay (코드)                     │
│     if plan is None:                                      │
│       schedule_state = "unknown", delay_days = None       │
│     else:                                                 │
│       plan_mh_per_day = plan_mh_sum / 공정_기간_일수       │
│       window_start    = max(min(Chroma date), plan_start) │
│       window_days     = today - window_start + 1           │
│       expected_in_w   = window_days × plan_mh_per_day     │
│       actual_in_w     = Σ unique date workers × 8h         │
│       mh_gap          = expected - actual                  │
│       delay_days      = mh_gap / plan_mh_per_day           │
│       schedule_state  = early|on_schedule|post_due         │
│                                                           │
│   ⑥ prompt.py + agent.py — LLM 호출 (Azure gpt-5.1)         │
│     if assessment is None:                                │
│       reasoning = "데이터 부족 — 판단 보류"               │
│       recovery_likelihood = None  (LLM skip)              │
│     else:                                                 │
│       LLM 호출 (system + few-shot 3 + user)               │
│       출력 = {reasoning, recovery_likelihood}             │
│                                                           │
│   ⑦ classify.py — risk_level 결정 (코드 hybrid)             │
│     post_due → "이상" 강제                                │
│     정상 + delay_days>5 → "주의" / else "정상"            │
│     주의 + recovery≥0.7 + delay≤5 → "주의" / else "이상"  │
│     이상 + delay≤0 → "주의" / else "이상"                 │
│                                                           │
│   ⑧ db.py — PG forecasts INSERT 1 row                       │
│                                                           │
└───────────────────────────────────────────────────────────┘
                              ↓
state["forecast"]: list[dict]  (N rows = unique (company, l6) 수)
                              ↓
              [interrupt:hil_2]  PM 이 risk_level ∈ {주의, 이상} row 선택
                              ↓
                          Optimizer
```

---

## 2. PM 원안 v2 plan §4 정합

| 항목 | PM 원안 v2 plan §4 (조형준 프로) | 본 spec 결정 | 정합 |
|---|---|---|---|
| 기능 | 오늘 생산성이 과거 유사 상황 대비 적정한지 진단 + 리스크 공종 목록 | 동일 + (company, l6_main) grain | ✓ |
| 입력 | 오늘 Mapper JSON + ChromaDB | mapped + Chroma daily_activities + PG activity_master | ✓ + Plan 비교 추가 |
| Step 1 | 공종별 생산성 계산 | by_unit Σ + main_unit productivity | ✓ |
| Step 2 | ChromaDB 유사 조건 5건 조회 | where filter (company, l6_main, date 30일) + rerank | ✓ |
| Step 3 | Opus 4.7 판단 | Azure gpt-5.1 (단일 endpoint 사용자 환경) | 모델 변경, 흐름 동일 |
| 출력 grain | trade 단일 | (company, l6_main) — 옵션 X 정밀화 | ✓ |
| Cold start | "WBS Man-Hour fallback" | RAG <3건 → Plan productivity ratio fallback. Plan 도 없으면 None. | ✓ 정합 |
| reasoning 스타일 | 3 단계 (조건 → RAG → 원인) | 동일 — Few-shot 3 박힘 | ✓ byte-level |
| delay_days | 3 (예시) | mh_gap / plan_mh_per_day | ✓ 의미 정합 |
| risk_level | "주의" (예시) | hybrid 룰 | ✓ |
| 리스크 공종 → H-i-L 2 | "PM 이 조언 대상 공종 선택" | risk_level ∈ {주의, 이상} | ✓ |

**PM 원안 흐름 보존**: ✓

---

## 3. row 구조 (PG `forecasts` 테이블 + `state["forecast"]`)

### 3.1 PG `forecasts` 스키마

```sql
CREATE TABLE forecasts (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    company TEXT NOT NULL,
    l6_main TEXT NOT NULL,

    -- 오늘 실측 (그 (company, l6_main) 단위 집계)
    today_qty_by_unit JSONB,                  -- {"m": 80.0, "ea": 12.0}
    today_assigned_workers NUMERIC,
    today_productivity NUMERIC,               -- by main_unit (max qty)

    -- Plan 기준 (PG activity_master Σ)
    plan_total_qty_by_unit JSONB,
    plan_mh_sum NUMERIC,
    plan_start DATE,                          -- MIN(activity_master.plan_start)
    plan_finish DATE,                         -- MAX(activity_master.plan_finish)
    plan_mh_per_day NUMERIC,                  -- plan_mh_sum / (plan_finish - plan_start + 1)

    -- 누적 mh window 비교
    schedule_state TEXT,                      -- "early|on_schedule|post_due|unknown"
    window_start DATE,
    window_days INT,
    expected_in_window_mh NUMERIC,
    actual_in_window_mh NUMERIC,
    mh_gap NUMERIC,                           -- 양수 = 부족
    delay_days NUMERIC,                       -- mh_gap / plan_mh_per_day

    -- RAG
    rag_n_similar INT,
    similar_cases JSONB,                      -- top-5 brief (productivity, conditions list)

    -- 진단 (assessment 코드 ④, reasoning + recovery_likelihood LLM ⑥)
    assessment TEXT,                          -- "정상|주의|이상" or NULL (cold start)
    reasoning TEXT,
    recovery_likelihood NUMERIC,              -- 0.0~1.0 or NULL

    -- 종합 (코드 ⑦ hybrid)
    expected_completion DATE,                 -- PoC: = plan_finish 그대로. Phase 2 추세 외삽.
    risk_level TEXT,                          -- "정상|주의|이상" or NULL

    -- optimizer cycle Task 1 (v3.1) — Optimizer / hil_2 소비용 2 필드
    main_unit TEXT,                           -- positive_units 중 max qty (모든 unit 0 → NULL)
    today_conditions TEXT,                    -- conditions_set 정렬 후 "," join (빈 set → "")

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_forecasts_run         ON forecasts (run_id);
CREATE INDEX idx_forecasts_company_l6  ON forecasts (company, l6_main);
CREATE INDEX idx_forecasts_risk        ON forecasts (risk_level) WHERE risk_level <> '정상';
CREATE INDEX idx_forecasts_state       ON forecasts (schedule_state);
```

**NOT NULL 제거 사유**: PoC 단계 cold start (assessment=None, plan=None) row 도 INSERT 가능해야 함. run_id / company / l6_main 3개만 NOT NULL 유지.

### 3.2 state["forecast"] dict (Reporter / Dashboard 소비)

각 row 는 PG `forecasts` 컬럼 그대로 + `similar_cases` 가 JSONB 가 아닌 list[dict].

### 3.3 schema 동기화 3곳 의무

| 파일 | 변경 |
|---|---|
| `infra/postgres/init.sql` | `forecasts` 테이블 정의 본 spec §3.1 과 일치 |
| `infra/postgres/migrations/2026-05-16_forecaster.sql` | 신규 마이그레이션 (§13.2) |
| `docs/schema/postgres.md` | §6 forecasts 표 정정 + §12 변경 이력 |

---

## 4. 모듈 분리 (5 모듈 패키지)

```
pipeline/agents/forecaster/
├── __init__.py                       # forecast() export
├── agent.py                          # LangGraph node + main async forecast() entry
├── aggregate.py                      # ① today by_unit Σ / ② PG Σ / ⑤ compute_delay
├── classify.py                       # ④ assessment / ⑦ risk_level 분류 룰
├── rerank.py                         # ③ _normalize_chroma_metadata + rerank_cases
├── prompt.py                         # ⑥ system + few-shot 3 + user input builder
└── synthetic.py                      # ⑧ Phase 1 dummy generator (CLI 진입점도)

pipeline/tests/forecaster/
├── __init__.py
├── test_aggregate.py
├── test_classify.py
├── test_rerank.py
├── test_synthetic.py
├── test_prompt.py
└── test_forecaster_integration.py    # 실 PG + 실 Chroma + 실 Azure
```

**원칙**:
- 각 모듈 ≤ 150 lines, 단일 책임, **순수 함수** (PGClient/Chroma 의존은 agent.py 에서 주입)
- `aggregate.py` / `classify.py` / `rerank.py` 는 dependency-free
- `prompt.py` 는 LLM client 의존성 X — input dict 만 생성
- `synthetic.py` 는 standalone CLI 도

향후 `atomizer.py` 도 동일 패턴 리팩토링 가능.

---

## 5. aggregate.py 명세

### 5.1 `aggregate_today_by_unit(activities) -> dict[str, float]`

```python
def aggregate_today_by_unit(activities: list[Activity]) -> dict[str, float]:
    """같은 (company, l6_main) 그룹 안의 Activity 들의 today_qty 를 unit 별 Σ."""
    by_unit: dict[str, float] = {}
    for a in activities:
        u = a["unit"]
        by_unit[u] = by_unit.get(u, 0.0) + a["today_qty"]
    return by_unit
```

### 5.2 `fetch_plan_for_group(pg, company, l6_main) -> dict | None` — 2 SQL 분리

**reviewer C-2 정정**: 의사 SQL 의 `GROUP BY unit, plan_start, plan_finish, plan_mh_rev2` 가 row 쪼개기 → `jsonb_object_agg` duplicate key 위험. **2 query 로 분리**.

```python
async def fetch_plan_for_group(pg: PGClient, company: str, l6_main: str) -> Optional[dict]:
    """PG activity_master 의 그 (company, l6_main) candidate Σ. 미등록 시 None.

    Query A: unit 별 plan_total_qty 합
    Query B: 전체 plan_mh_sum + 기간 MIN/MAX
    """
    qty_rows = await pg._pool.fetch(
        """
        SELECT unit, SUM(plan_total_qty) AS qty
        FROM activity_master
        WHERE company = $1 AND l6_main = $2 AND unit IS NOT NULL
        GROUP BY unit
        """,
        company, l6_main,
    )
    if not qty_rows:
        return None   # BP사 미등록

    summary = await pg._pool.fetchrow(
        """
        SELECT
            SUM(plan_mh_rev2) AS plan_mh_sum,
            MIN(plan_start)   AS plan_start,
            MAX(plan_finish)  AS plan_finish
        FROM activity_master
        WHERE company = $1 AND l6_main = $2
        """,
        company, l6_main,
    )

    return {
        "plan_total_qty_by_unit": {r["unit"]: float(r["qty"] or 0) for r in qty_rows},
        "plan_mh_sum": float(summary["plan_mh_sum"] or 0),
        "plan_start": summary["plan_start"],
        "plan_finish": summary["plan_finish"],
    }
```

**PGClient 신규 메서드 — Task 분해 시 추가**:
- `fetch_plan_for_group(company, l6_main) -> Optional[dict]`
- `insert_forecast(row) -> None` (§5.6)

### 5.3 `compute_delay(plan, today, actual_window_start, actual_cum_mh) -> dict`

**사용자 개념**:
> "전체 plan 일정보다 빠르게 들어왔으면 공정 acc, 일정 아예 넘어서서 들어오는건 명확한 delay.
> 9/1~9/30 plan, 9/15 일보, 정상 누적 15 mh 인데 actual 10 mh 면 5 mh 부족 → 5일 delay."

```python
def compute_delay(
    plan: Optional[dict],
    today: date,
    actual_window_start: Optional[date],
    actual_cum_mh: float,
) -> dict[str, Any]:
    """누적 mh window 비교 — 사용자 개념 충실. Plan 미등록 시 unknown.

    plan_mh_per_day  = plan_mh_sum / 공정_기간_일수
    expected_in_w    = window_days × plan_mh_per_day
    mh_gap           = expected - actual           (양수 = 부족)
    delay_days       = mh_gap / plan_mh_per_day

    schedule_state:
      plan 없음            → "unknown"   (cold start BP사)
      today < plan_start   → "early"     (공종 시작 전)
      plan_start ≤ today ≤ plan_finish → "on_schedule"
      today > plan_finish  → "post_due"  (공종 종료 후 진입)
    """
    if plan is None or plan.get("plan_start") is None or plan.get("plan_finish") is None:
        return {
            "plan_mh_per_day": None,
            "schedule_state": "unknown",
            "window_start": None,
            "window_days": 0,
            "expected_in_window_mh": None,
            "actual_in_window_mh": actual_cum_mh,
            "mh_gap": None,
            "delay_days": None,
        }

    plan_start = plan["plan_start"]
    plan_finish = plan["plan_finish"]
    plan_mh_sum = plan["plan_mh_sum"]

    total_days = (plan_finish - plan_start).days + 1
    plan_mh_per_day = plan_mh_sum / total_days if total_days > 0 else 0.0

    if today < plan_start:
        schedule_state = "early"
    elif today > plan_finish:
        schedule_state = "post_due"
    else:
        schedule_state = "on_schedule"

    ws = actual_window_start or today
    window_days = max(1, (today - ws).days + 1)
    expected_in_w = window_days * plan_mh_per_day
    mh_gap = expected_in_w - actual_cum_mh
    delay_days = mh_gap / plan_mh_per_day if plan_mh_per_day > 0 else 0.0

    return {
        "plan_mh_per_day": plan_mh_per_day,
        "schedule_state": schedule_state,
        "window_start": ws,
        "window_days": window_days,
        "expected_in_window_mh": expected_in_w,
        "actual_in_window_mh": actual_cum_mh,
        "mh_gap": mh_gap,
        "delay_days": delay_days,
    }
```

### 5.4 `fetch_chroma_actual(coll, company, l6_main, today, today_assigned_workers) -> dict`

agent.py 책임 함수 (Chroma client 의존성 격리).

```python
def fetch_chroma_actual(
    coll, company: str, l6_main: str, today: date, today_assigned_workers: float,
) -> tuple[Optional[date], float]:
    """Chroma daily_activities 에서 (company, l6_main) 의 date 별 unique workers 추출.

    return: (actual_window_start, actual_cum_mh)
      actual_window_start = min(Chroma date 들)  (오늘 포함)
      actual_cum_mh       = Σ (date 별 workers × 8h)
    """
    result = coll.get(
        where={"$and": [{"company": company}, {"l6_main": l6_main}]},
        include=["metadatas"],
    )
    date_to_workers: dict[str, float] = {}
    for m in result.get("metadatas") or []:
        d = m["date"]
        if d == today.isoformat():
            continue   # 오늘 자기자신 제외 (Atomizer 가 이미 적재했을 수 있음)
        date_to_workers[d] = float(m["assigned_workers"])
    # 오늘 강제 추가
    date_to_workers[today.isoformat()] = today_assigned_workers

    if not date_to_workers:
        return None, today_assigned_workers * 8

    window_start = date.fromisoformat(min(date_to_workers.keys()))
    actual_cum_mh = sum(w * 8 for w in date_to_workers.values())   # 1 work-day = 8h
    return window_start, actual_cum_mh
```

### 5.5 PoC 한계 (시뮬 검증 + reviewer 발견)

| # | 한계 | PoC 처리 | Phase 2 |
|---|---|---|---|
| 1 | actual_window_start = 실 누적 부재 | `max(min(Chroma date), plan_start)` — 있는 데이터 안에서 | plan_start 부터 full 비교 |
| 2 | actual_cum_mh doc 중복 | date 별 unique workers × 8h | 동일 (옵션 X 충분) |
| 3 | plan_mh_per_day 평균값 | 단순 산술 평균 | sub_work_area 별 weighted avg |
| 4 | 휴일/주말 무시 | 8h × 365일 가정 | 공휴일 캘린더 |
| 5 | Plan 미등록 BP사 | `schedule_state = "unknown"`, delay_days = None | mapping_corrections 누적 시 cross-walk |
| 6 | Chroma 0 row + plan 있음 | window_start = today, window_days = 1 | 위와 동일 |

### 5.6 `PGClient.insert_forecast(row) -> None` — SQL 본문

**reviewer Mi-4 정정**: 28 컬럼 INSERT SQL 명시.

```python
async def insert_forecast(self, row: dict) -> None:
    """forecasts 테이블 INSERT 1 row. row dict 키와 컬럼명 1:1 매칭."""
    assert self._pool is not None
    await self._pool.execute(
        """
        INSERT INTO forecasts (
            run_id, company, l6_main,
            today_qty_by_unit, today_assigned_workers, today_productivity,
            plan_total_qty_by_unit, plan_mh_sum, plan_start, plan_finish, plan_mh_per_day,
            schedule_state, window_start, window_days,
            expected_in_window_mh, actual_in_window_mh, mh_gap, delay_days,
            rag_n_similar, similar_cases,
            assessment, reasoning, recovery_likelihood,
            expected_completion, risk_level
        ) VALUES (
            $1, $2, $3,
            $4, $5, $6,
            $7, $8, $9, $10, $11,
            $12, $13, $14,
            $15, $16, $17, $18,
            $19, $20,
            $21, $22, $23,
            $24, $25
        )
        """,
        row["run_id"], row["company"], row["l6_main"],
        json.dumps(row["today_qty_by_unit"]), row["today_assigned_workers"], row["today_productivity"],
        json.dumps(row["plan_total_qty_by_unit"]) if row["plan_total_qty_by_unit"] else None,
        row["plan_mh_sum"], row["plan_start"], row["plan_finish"], row["plan_mh_per_day"],
        row["schedule_state"], row["window_start"], row["window_days"],
        row["expected_in_window_mh"], row["actual_in_window_mh"], row["mh_gap"], row["delay_days"],
        row["rag_n_similar"], json.dumps(row["similar_cases"]),
        row["assessment"], row["reasoning"], row["recovery_likelihood"],
        row["expected_completion"], row["risk_level"],
    )
```

---

## 6. classify.py 명세

### 6.1 `classify_assessment` (③ 임계값) — **reviewer M-2 정정: 단위당 productivity 비교**

```python
def classify_assessment_rag(today_prod: float, rag_avg_prod: float) -> str:
    """RAG 모드 — productivity delta 임계 ±15% / ±25%."""
    if rag_avg_prod == 0:
        return "정상"
    delta = (today_prod - rag_avg_prod) / rag_avg_prod
    if delta >= -0.15: return "정상"
    if delta >= -0.25: return "주의"
    return "이상"


def classify_assessment_plan(
    today_prod: float,
    plan_total_qty_main: float,
    plan_mh_sum: float,
) -> str:
    """Plan fallback — 단위당 productivity ratio 임계 0.85 / 0.65.

    plan_prod_proxy = plan_total_qty[main_unit] / (plan_mh_sum / 8)
                     # 그 공종이 정상 진행 시 1 인-day 가 만드는 unit 수
    today_prod      = today_qty[main_unit] / today_workers  (이미 main_unit 단위)
    ratio           = today_prod / plan_prod_proxy

    의미: RAG delta 와 같은 축 — productivity ratio.
    """
    if plan_mh_sum <= 0 or plan_total_qty_main <= 0:
        return "정상"
    plan_prod_proxy = plan_total_qty_main / (plan_mh_sum / 8)
    if plan_prod_proxy == 0:
        return "정상"
    ratio = today_prod / plan_prod_proxy
    if ratio >= 0.85: return "정상"
    if ratio >= 0.65: return "주의"
    return "이상"


def classify_assessment(
    rag_n: int,
    today_prod: float,
    rag_avg_prod: float,
    plan_total_qty_main: Optional[float],
    plan_mh_sum: Optional[float],
) -> Optional[str]:
    """② RAG 우선 + Plan fallback + ④ cold start."""
    if rag_n >= 3:
        return classify_assessment_rag(today_prod, rag_avg_prod)
    if plan_mh_sum and plan_mh_sum > 0 and plan_total_qty_main:
        return classify_assessment_plan(today_prod, plan_total_qty_main, plan_mh_sum)
    return None  # cold start (LLM skip)
```

### 6.2 `classify_risk_level` (⑦ hybrid 룰)

```python
def classify_risk_level(
    assessment: Optional[str],
    recovery_likelihood: Optional[float],
    delay_days: Optional[float],
    schedule_state: str,
) -> Optional[str]:
    """delay_days + schedule_state 종합 hybrid.

    임계 5일·0.7 = 가정값 (회귀 후 조정. 0.7 = PM 원안 v2 80% 대비 conservative).

    delay_days 의미:
      > 0 = expected 대비 부족 (behind, catch-up 필요)
      = 0 = on track
      < 0 = ahead
      None = plan 미등록 (cold start)
    """
    if assessment is None:
        return None
    if schedule_state == "post_due":
        return "이상"  # 공종 종료 후 진입 = 명확한 delay
    if schedule_state == "unknown" or delay_days is None:
        # plan 미등록 — assessment 만으로 결정
        return assessment

    if assessment == "정상":
        if delay_days > 5: return "주의"
        return "정상"
    if assessment == "주의":
        if (recovery_likelihood is not None
            and recovery_likelihood >= 0.7
            and delay_days <= 5):
            return "주의"
        return "이상"
    # assessment == "이상"
    if delay_days <= 0:
        return "주의"  # 누적 ahead — 회복 여유
    return "이상"
```

---

## 7. rerank.py 명세

### 7.1 `_normalize_chroma_metadata` — **reviewer B-1 정정**

atomizer 가 박는 metadata schema 와 Forecaster 가 가정하는 schema 일치시키는 정규화.

```python
def _normalize_chroma_metadata(m: dict) -> dict:
    """Atomizer (atomizer.py:45) 적재 schema → Forecaster 사용 schema.

    atomizer 박는 키:
      date, run_id, company, l5_disc, l6_main, wa, unit,
      today_qty, assigned_workers, worker_source, mapping_conf,
      conditions: ",".join(list) → STRING

    Forecaster 추가 derive:
      productivity = today_qty / assigned_workers
      conditions   = string.split(",")  (empty string → [])
    """
    today_qty = float(m.get("today_qty", 0))
    workers = float(m.get("assigned_workers", 0))
    productivity = today_qty / workers if workers > 0 else 0.0

    conditions_raw = m.get("conditions", "")
    conditions = conditions_raw.split(",") if conditions_raw else []

    return {**m, "productivity": productivity, "conditions": conditions}
```

### 7.2 `rerank_cases(cases) -> list[dict]`

```python
def rerank_cases(cases: list[dict]) -> list[dict]:
    """Chroma query 결과 → 정규화 + rerank.

    가중치 (distance 작을수록 가까움):
      worker_source = "user_corrected" → ×0.7 (최우선)
      mapping_conf < 0.7              → ×1.5 (우선순위 ↓)

    정렬 후 전체 반환 — caller (agent.py) 가 [:rag_top_k] 자름.
    """
    out = []
    for c in cases:
        meta = _normalize_chroma_metadata(c["metadata"])
        score = c["distance"]
        if meta.get("worker_source") == "user_corrected":
            score *= 0.7
        if meta.get("mapping_conf", 1.0) < 0.7:
            score *= 1.5
        out.append({**c, "metadata": meta, "rerank_score": score})
    return sorted(out, key=lambda x: x["rerank_score"])
```

---

## 8. prompt.py 명세

### 8.1 system prompt (고정)

```
당신은 건설 현장 생산성 분석 전문가다.
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
  - assessment = None 케이스는 LLM 호출 자체를 안 함 (코드 분기로 처리)
```

### 8.2 Few-shot 3 예시

```
[FEW-SHOT 1 — 정상 (PM 원안 v2 §2 거푸집 인용)]
input:  {today: "거푸집 22.9 m2/인, conditions: [우천,병행작업]",
         rag_avg_prod: 21.3,  delta: +8%,  assessment: "정상"}
output: {"reasoning": "오늘 우천, 병행작업 있음. 유사 우천일 평균 21.3 m2/인 대비 +8% — 정상 범위.",
         "recovery_likelihood": null}

[FEW-SHOT 2 — 주의 (9/25 실 데이터 수제작)]
input:  {today: "세보 일반공조 401명, m 80, work_content: AHU 덕트 + 자재 미입고 일부",
         rag_avg_prod: 0.18 m/인,  delta: -22%,  assessment: "주의"}
output: {"reasoning": "맑음, 병행 없음. 유사 5건 평균 0.18 m/인 대비 -22%. work_content 에 '자재 미입고' 기재 — 단기 회복 가능성.",
         "recovery_likelihood": 0.7}

[FEW-SHOT 3 — 이상 (PM 원안 v2 §4 철근 인용)]
input:  {today: "철근 1.8 ton/인, work_content: 타워크레인 대기로 오전 작업 지연",
         rag_avg_prod: 2.6,  delta: -31%,  assessment: "이상"}
output: {"reasoning": "맑음, 병행 없음. 유사 5건 평균 2.6 ton/인 대비 -31%. '타워크레인 대기' 기재 — 장비 스케줄 충돌 가능성.",
         "recovery_likelihood": 0.8}
```

### 8.3 `build_llm_user_input(today, similar_cases, plan, assessment) -> dict`

```python
def build_llm_user_input(
    today: dict,
    similar_cases: list[dict],
    plan: Optional[dict],
    assessment: str,                 # cold start (None) 은 LLM skip — 본 함수 호출 X
) -> dict:
    """system + 3 few-shot 은 const, 본 함수는 user message 만 만듦."""
    return {
        "today": {
            "company": today["company"],
            "l6_main": today["l6_main"],
            "today_qty_by_unit": today["today_qty_by_unit"],
            "today_assigned_workers": today["today_assigned_workers"],
            "today_productivity": round(today["today_productivity"], 4),
            "conditions": today["conditions"],          # list
            "work_content": today["work_content"],
        },
        "similar_cases": [
            {
                "date": c["metadata"]["date"],
                "productivity": round(c["metadata"]["productivity"], 4),
                "conditions": c["metadata"]["conditions"],   # list (정규화 후)
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
```

### 8.4 Azure 호출 (agent.py 책임) — **reviewer C-1 정정: temperature 제거**

```python
# pipeline/agents/forecaster/agent.py 안. Parser/Mapper 패턴 따름.
azure = AzureOpenAI(...)
response = azure.chat.completions.create(
    model=cfg.llm_model,                         # "gpt-5.1-chat-ai-board-test"
    messages=[
        {"role": "system",    "content": SYSTEM_PROMPT},
        {"role": "user",      "content": FEW_SHOT_1_INPUT},
        {"role": "assistant", "content": FEW_SHOT_1_OUTPUT},
        {"role": "user",      "content": FEW_SHOT_2_INPUT},
        {"role": "assistant", "content": FEW_SHOT_2_OUTPUT},
        {"role": "user",      "content": FEW_SHOT_3_INPUT},
        {"role": "assistant", "content": FEW_SHOT_3_OUTPUT},
        {"role": "user",      "content": json.dumps(llm_input, ensure_ascii=False)},
    ],
    response_format={"type": "json_object"},
    # temperature 박지 않음 — gpt-5 family reasoning 모델 미지원 가능성
    # (Parser/Mapper 패턴, mapper.py:290~300 참조)
)
llm_out = json.loads(response.choices[0].message.content)
```

---

## 9. synthetic.py 명세 (⑧ Phase 1 필수)

### 9.1 알고리즘

```python
def generate_synthetic_day(
    base_row: dict,
    day_offset: int,
    weather: str,
    incident: str,
) -> dict:
    """PM 원안 v2 §3-B 변동 패턴. atomizer._build_metadata() 와 동일 schema 박음.

    변동 룰:
      weather="우천"     → today_qty × (1 - random[0.15, 0.25])
      incident="장비대기" → today_qty × (1 - random[0.20, 0.35])
      incident="자재미입고" → today_qty × (1 - random[0.10, 0.20])
      기본 변동           → × (1 + random[-0.05, 0.05])

    Chroma 적재 시 atomizer 와 같은 _build_metadata() 사용 (reviewer B-1 정정).
    """
```

### 9.2 실행 흐름

```bash
# Phase 1 회귀 진입 전 1회 실행 (CLI)
uv run python -m pipeline.agents.forecaster.synthetic \
    --reference-date 2025-09-25 \
    --days 30 \
    --target-l6-count 30
```

**입력**: 9/25 매핑 결과 (`scripts/load_master_list.py` 적재된 activity_master) + 30일 backward

**출력**: Chroma `daily_activities` 적재 ~900 row (30일 × ~30 unique (company, l6))

**비용**: **~$0.001** (text-embedding-3-small, 900 doc × 평균 50 token = 45,000 token × $0.00002/1K — reviewer 정정, 기존 $0.5 과대 추정)

**실행 시간**: ~1~2분 (Azure embedding 배치 16, latency 1~2초)

### 9.3 PoC 한계

| 한계 | PoC | Phase 2 |
|---|---|---|
| work_content variation 부족 | 9/25 원본 그대로 재사용 | 실 누적 → variation 자연 |
| 회복 패턴 미구현 | weather/incident 독립 sampling | 어제 incident 추적 |
| 단일 reference date | 9/25 1건만 | 실 데이터로 완전 교체 |

---

## 10. agent.py 명세 (LangGraph node + entry)

```python
# pipeline/agents/forecaster/agent.py

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional
import json
import uuid

from openai import AzureOpenAI

from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient
from pipeline.state import Activity, CPIAState

from .aggregate import (
    aggregate_today_by_unit, fetch_plan_for_group,
    compute_delay, fetch_chroma_actual,
)
from .classify import classify_assessment, classify_risk_level
from .prompt import build_llm_user_input, SYSTEM_PROMPT, FEW_SHOT_MESSAGES
from .rerank import rerank_cases


@dataclass
class ForecasterConfig:
    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    llm_model: str                  # "gpt-5.1-chat-ai-board-test"
    embedding_model: str            # "text-embedding-3-small-ai-board-test"
    postgres_url: str
    chroma_host: str
    chroma_port: int
    chroma_ssl: bool = False
    azure_timeout: float = 60.0
    azure_max_retries: int = 3
    rag_n_candidates: int = 10
    rag_top_k: int = 5
    rag_window_days: int = 30
    # temperature 박지 않음 — reviewer C-1 정정


async def forecast(
    mapped: list[Activity],
    run_id: uuid.UUID,
    today: date,
    cfg: ForecasterConfig,
) -> list[dict[str, Any]]:
    """Forecaster entry. (company, l6_main) group 별 1 row 생성."""
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    chroma = ChromaClient(host=cfg.chroma_host, port=cfg.chroma_port, ssl=cfg.chroma_ssl)
    coll = chroma.get_or_create_daily_activities()
    azure = AzureOpenAI(
        api_key=cfg.azure_api_key,
        api_version=cfg.azure_api_version,
        azure_endpoint=cfg.azure_endpoint,
        timeout=cfg.azure_timeout,
        max_retries=cfg.azure_max_retries,
    )

    try:
        await pg.assert_pipeline_run_exists(run_id)

        # group by (company, l6_main)
        groups: dict[tuple[str, str], list[Activity]] = {}
        for a in mapped:
            if a["l6_main"] is None:
                continue
            key = (a["company"], a["l6_main"])
            groups.setdefault(key, []).append(a)

        forecast_rows: list[dict[str, Any]] = []
        for (company, l6_main), activities in groups.items():
            row = await _forecast_one_group(
                company, l6_main, activities, run_id, today,
                pg, coll, azure, cfg,
            )
            await pg.insert_forecast(row)
            forecast_rows.append(row)

        return forecast_rows
    finally:
        await pg.close()


async def _forecast_one_group(
    company: str, l6_main: str, activities: list[Activity],
    run_id: uuid.UUID, today: date,
    pg, coll, azure, cfg,
) -> dict[str, Any]:
    """1 (company, l6_main) group 처리. §1 흐름 ① ~ ⑧ 순서."""

    # ① 집계
    today_qty_by_unit = aggregate_today_by_unit(activities)
    today_assigned_workers = activities[0]["assigned_workers"]   # 옵션 X 동일
    main_unit = max(today_qty_by_unit, key=today_qty_by_unit.get) if today_qty_by_unit else None
    today_productivity = (
        today_qty_by_unit[main_unit] / today_assigned_workers
        if main_unit and today_assigned_workers > 0 else 0.0
    )
    work_content = " / ".join(set(a["work_content"] for a in activities))[:200]
    conditions_set = sorted(set(c for a in activities for c in a["conditions"]))

    # ② Plan
    plan = await fetch_plan_for_group(pg, company, l6_main)

    # ③ RAG 검색 + 정규화 + rerank
    embed_resp = azure.embeddings.create(model=cfg.embedding_model, input=[work_content])
    today_embed = embed_resp.data[0].embedding
    # 정오표 (2026-05-16): chromadb 0.5.20 validate_where 가 단일 dict 안 다중
    # operator + ISO string operand 모두 거부. date 30 일 윈도우는 코드단 컷.
    # (company, l6_main) 만 Chroma where 로 필터.
    where_filter = {
        "$and": [
            {"company": company},
            {"l6_main": l6_main},
        ]
    }
    rag_result = coll.query(
        query_embeddings=[today_embed],
        where=where_filter,
        n_results=cfg.rag_n_candidates,
    )
    similar_cases_raw = _format_chroma_result(rag_result)
    window_start_iso = (today - timedelta(days=cfg.rag_window_days)).isoformat()
    today_iso = today.isoformat()
    similar_cases_in_window = [
        c for c in similar_cases_raw
        if window_start_iso <= c["metadata"]["date"] < today_iso
    ]
    similar_cases = rerank_cases(similar_cases_in_window)[: cfg.rag_top_k]

    # ④ assessment
    rag_n = len(similar_cases)
    rag_avg_prod = (
        sum(c["metadata"]["productivity"] for c in similar_cases) / rag_n
        if rag_n > 0 else 0.0
    )
    plan_main_qty = (
        plan["plan_total_qty_by_unit"].get(main_unit)
        if plan and main_unit else None
    )
    assessment = classify_assessment(
        rag_n=rag_n,
        today_prod=today_productivity,
        rag_avg_prod=rag_avg_prod,
        plan_total_qty_main=plan_main_qty,
        plan_mh_sum=plan["plan_mh_sum"] if plan else None,
    )

    # ⑤ compute_delay
    actual_window_start, actual_cum_mh = fetch_chroma_actual(
        coll, company, l6_main, today, today_assigned_workers,
    )
    delay_info = compute_delay(plan, today, actual_window_start, actual_cum_mh)

    # ⑥ LLM
    if assessment is None:
        # cold start — LLM skip
        reasoning = "데이터 부족 (RAG 0건, Plan 미등록) — 판단 보류"
        recovery_likelihood = None
    else:
        today_data = {
            "company": company, "l6_main": l6_main,
            "today_qty_by_unit": today_qty_by_unit,
            "today_assigned_workers": today_assigned_workers,
            "today_productivity": today_productivity,
            "conditions": conditions_set,
            "work_content": work_content,
        }
        llm_input = build_llm_user_input(today_data, similar_cases, plan, assessment)
        response = azure.chat.completions.create(
            model=cfg.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *FEW_SHOT_MESSAGES,
                {"role": "user", "content": json.dumps(llm_input, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            # temperature 박지 않음 (reviewer C-1)
        )
        llm_out = json.loads(response.choices[0].message.content)
        reasoning = llm_out.get("reasoning", "")
        recovery_likelihood = llm_out.get("recovery_likelihood")

    # ⑦ risk_level
    risk_level = classify_risk_level(
        assessment, recovery_likelihood,
        delay_info["delay_days"], delay_info["schedule_state"],
    )

    # ⑧ row
    return {
        "run_id": run_id,
        "company": company,
        "l6_main": l6_main,
        "today_qty_by_unit": today_qty_by_unit,
        "today_assigned_workers": today_assigned_workers,
        "today_productivity": today_productivity,
        "plan_total_qty_by_unit": plan["plan_total_qty_by_unit"] if plan else None,
        "plan_mh_sum": plan["plan_mh_sum"] if plan else None,
        "plan_start": plan["plan_start"] if plan else None,
        "plan_finish": plan["plan_finish"] if plan else None,
        "plan_mh_per_day": delay_info["plan_mh_per_day"],
        "schedule_state": delay_info["schedule_state"],
        "window_start": delay_info["window_start"],
        "window_days": delay_info["window_days"],
        "expected_in_window_mh": delay_info["expected_in_window_mh"],
        "actual_in_window_mh": delay_info["actual_in_window_mh"],
        "mh_gap": delay_info["mh_gap"],
        "delay_days": delay_info["delay_days"],
        "rag_n_similar": rag_n,
        "similar_cases": [
            {"date": c["metadata"]["date"],
             "productivity": round(c["metadata"]["productivity"], 4),
             "conditions": c["metadata"]["conditions"]}    # 정규화 후 list
            for c in similar_cases
        ],
        "assessment": assessment,
        "reasoning": reasoning,
        "recovery_likelihood": recovery_likelihood,
        # PoC: expected_completion = plan_finish 그대로. Phase 2 추세 외삽.
        "expected_completion": plan["plan_finish"] if plan else None,
        "risk_level": risk_level,
        # optimizer cycle Task 1 (v3.1) — Optimizer / hil_2 가 소비할 2 필드
        "main_unit": main_unit,
        "today_conditions": ",".join(conditions_set) if conditions_set else "",
    }


def _format_chroma_result(rag_result: dict) -> list[dict]:
    """Chroma query 결과 → rerank 가 받는 format."""
    if not rag_result.get("ids") or not rag_result["ids"][0]:
        return []
    return [
        {
            "document": doc,
            "distance": dist,
            "metadata": meta,
        }
        for doc, dist, meta in zip(
            rag_result["documents"][0],
            rag_result["distances"][0],
            rag_result["metadatas"][0],
        )
    ]
```

LangGraph node wrapper (차후 graph 통합 spec):

```python
async def forecaster_node(state: CPIAState, cfg: GraphConfig) -> dict:
    today = date.fromisoformat(state["date"])
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    forecasts = await forecast(state["mapped"], run_id, today, cfg.forecaster)
    return {"forecast": forecasts, "current_node": "forecaster"}
```

---

## 11. 시뮬 검증 결과 (`/tmp/cpia_forecaster_sim.py`, 2026-05-16)

세보엠이씨 / 일반공조설비공사 1 group + synthetic 5건 dummy:

```
① today_qty_by_unit       = {m: 80, ea: 12}
   today_assigned_workers = 401.4
   today_productivity (m) = 0.1993 m/인

② plan_total_qty_by_unit  = {m: 6800, m2: 12400, ea: 950}
   plan_mh_sum            = 708,154
   plan_start             = 2025-01-01
   plan_finish            = 2026-06-20

③ Synthetic 5건 — prod 0.147 ~ 0.202 분포
④ Rerank — 모두 synthetic 라 변화 X
⑤ RAG avg = 0.1798, today = 0.1993, delta = +10.9%
⑥ assessment = "정상"

⑦ compute_delay:
   plan_mh_per_day        = 1,321.2 mh/day
   schedule_state         = on_schedule
   window_days            = 6일
   expected_in_window_mh  = 7,927
   actual_in_window_mh    = 19,267 (6 × 401.4 × 8 = 19,267.2 → round)
   mh_gap                 = -11,340 (음수)
   delay_days             = -8.6일 (ahead)

⑩ risk_level = "정상" (정상 + ahead → 정상)
```

**검증 사항**: ✓ 5 모듈 분리 / ✓ delay_days 의미 정합 / ✓ schedule_state 3 enum / ✓ risk_level hybrid 룰 / ✓ Few-shot input schema. **단 시뮬은 atomizer 와 다른 metadata schema 를 사용** → reviewer B-1 발견. 본 spec 의 `_normalize_chroma_metadata` 함수로 정정. Phase 1 integration test 단계에서 실 Chroma schema 로 재검증 필수.

---

## 12. TDD 테스트 plan

### 12.1 unit (실 호출 X)

```
# test_aggregate.py
test_aggregate_today_by_unit                     # Σ by unit
test_compute_delay_on_schedule                   # 정상 범위
test_compute_delay_early                          # today < plan_start
test_compute_delay_post_due                      # today > plan_finish
test_compute_delay_unknown                        # plan=None → schedule_state="unknown"
test_compute_delay_ahead                          # actual > expected
test_compute_delay_behind                         # actual < expected
test_compute_delay_zero_total_days                # plan_start == plan_finish
test_fetch_chroma_actual_with_data                # Chroma N row → window 정확
test_fetch_chroma_actual_empty                    # Chroma 0 row → window=today

# test_classify.py
test_classify_assessment_rag_normal              # delta -10% → 정상
test_classify_assessment_rag_caution             # delta -20% → 주의
test_classify_assessment_rag_risk                # delta -30% → 이상
test_classify_assessment_plan_fallback_normal    # productivity ratio 0.9 → 정상
test_classify_assessment_plan_fallback_caution   # ratio 0.7 → 주의
test_classify_assessment_plan_fallback_risk      # ratio 0.5 → 이상
test_classify_assessment_cold_start              # RAG=0, Plan=None → None
test_classify_risk_normal_on_track               # 정상 + delay≤5 → 정상
test_classify_risk_normal_with_delay             # 정상 + delay>5 → 주의
test_classify_risk_caution_recoverable           # 주의 + recovery≥0.7 + delay≤5 → 주의
test_classify_risk_caution_unrecoverable         # 주의 + recovery<0.7 → 이상
test_classify_risk_severe_ahead                  # 이상 + delay≤0 → 주의
test_classify_risk_severe_behind                 # 이상 + delay>0 → 이상
test_classify_risk_post_due                      # state="post_due" → 이상 강제
test_classify_risk_unknown                        # state="unknown" → assessment 그대로
test_classify_risk_cold_start                    # assessment=None → None

# test_rerank.py
test_normalize_conditions_string_to_list         # "맑음,우천" → ["맑음","우천"]
test_normalize_conditions_empty_string           # "" → []
test_normalize_productivity_derive               # today_qty/workers
test_rerank_user_corrected_priority              # worker_source ×0.7
test_rerank_low_mapping_conf_demoted             # mapping_conf<0.7 ×1.5
test_rerank_empty                                 # cases=[] → []

# test_synthetic.py
test_synthetic_clear_normal                       # 맑음/정상 → ±5% 변동
test_synthetic_rainy_decrease                     # 우천 → -15~25%
test_synthetic_equipment_wait                     # 장비대기 → -20~35%
test_synthetic_seed_reproducible                  # seed 고정 → 동일 출력
test_synthetic_metadata_schema_match_atomizer    # _build_metadata schema 동일

# test_prompt.py
test_prompt_build_normal                          # assessment=정상 → recovery=null
test_prompt_build_caution                         # 입력 JSON 구조
test_prompt_build_conditions_list                 # conditions 정규화 후 list
```

### 12.2 integration (실 PG + 실 Chroma + 실 Azure, `@pytest.mark.slow`)

```
test_fetch_plan_for_group_real_pg               # 실 activity_master 1059 row 안 (company, l6) 1건 정합
test_fetch_plan_for_group_unknown_bp            # 미등록 BP사 → None
test_forecaster_sebo_with_synthetic              # synthetic 30일 적재 후 세보 정상 1 row
test_forecaster_namwong_normal                   # 9/25 남웅 철콘 정상
test_forecaster_cold_start_unknown_bp           # 미등록 BP사 → assessment=None, schedule_state="unknown"
test_forecaster_pg_insert_all_columns           # forecasts row 모든 컬럼 정합
test_forecaster_no_chroma_data                   # Chroma 비어있음 + Plan 가용 → Plan fallback
test_forecaster_chroma_metadata_schema_match    # Atomizer 적재 후 query → 정규화 정확
test_forecaster_temperature_not_supported       # gpt-5.1 + temperature 명시 시 raise (회피 검증)
test_forecaster_chroma_date_range_filter        # $gte/$lt 단일 dict 검증
```

### 12.3 E2E (`@pytest.mark.golden`)

```
test_forecaster_e2e_9_25                         # mapper + atomizer + forecaster 통과
                                                  # state["forecast"] N row
                                                  # PG forecasts row 수 = unique (company, l6)
                                                  # risk_level 분포 snapshot
```

---

## 13. postgres.md 정정 사항 (3곳 동기화 의무)

### 13.1 init.sql

`forecasts` 테이블 정의를 §3.1 SQL 과 일치.

### 13.2 마이그레이션 (`infra/postgres/migrations/2026-05-16_forecaster.sql` 신규)

**reviewer Coh-3 + M-4 정정**: JSONB 컬럼 2개 + delay_days NUMERIC 추가.

```sql
-- forecasts 컬럼 추가 (본 spec §3.1 정합)
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS today_qty_by_unit JSONB;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS today_productivity NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS plan_total_qty_by_unit JSONB;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS plan_start DATE;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS plan_finish DATE;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS plan_mh_per_day NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS schedule_state TEXT;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS window_start DATE;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS window_days INT;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS expected_in_window_mh NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS actual_in_window_mh NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS mh_gap NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS recovery_likelihood NUMERIC;

-- delay_days INT → NUMERIC 변환 (PoC forecasts 빈 테이블 가정, USING noop)
ALTER TABLE forecasts ALTER COLUMN delay_days TYPE NUMERIC USING delay_days::NUMERIC;

-- index
CREATE INDEX IF NOT EXISTS idx_forecasts_state ON forecasts (schedule_state);
```

### 13.3 postgres.md

§6 forecasts 표 + §12 변경 이력에 본 spec 반영.

---

## 14. CPIAState 정정 (`pipeline/state.py`)

본 spec 의 결정으로 state 필드 추가/제거 X. `state["forecast"]: list[dict]` 의 dict 키는 §3.2 와 일치.

---

## 15. Phase 1 vs Phase 2 분리

### 15.1 Phase 1 — 본 PoC (2026-06-05 마감)

| 사안 | 결정 시점 |
|---|---|
| Task 0: synthetic history 30일 + Chroma 적재 (Phase 1 prerequisite) | Task 1 진입 전 |
| Task 1: postgres 마이그레이션 + init.sql + postgres.md 3곳 동기화 (§13) | 본 spec → plan |
| Task 2: aggregate.py 5 함수 + 단위 테스트 (fetch_plan 2 SQL 분리) | 동일 |
| Task 3: classify.py + 단위 테스트 (assessment Plan fallback metric + risk_level) | 동일 |
| Task 4: rerank.py + _normalize_chroma_metadata + 단위 테스트 | 동일 |
| Task 5: synthetic.py + atomizer schema 일치 + CLI + 단위 테스트 | Task 0 통합 가능 |
| Task 6: prompt.py + Few-shot 3 const + 단위 테스트 | 동일 |
| Task 7: agent.py + PGClient 신규 2 메서드 (fetch_plan_for_group / insert_forecast) | 동일 |
| Task 8: integration + E2E 회귀 | 동일 |
| Task 9: graph.py forecaster_node 연결 | 차후 graph 통합 spec |
| 임계값 (0.85/0.65, ±15%/±25%, 5일, 0.7) 회귀 후 조정 | Phase 1 회귀 분석 후 |

### 15.2 Phase 2 — PoC 이후

| 사안 | 비고 |
|---|---|
| actual_window_start = plan_start 부터 full 비교 | 실 1~6 개월 누적 확보 후 |
| plan_mh_per_day 시간 변동 (sub_work_area weighted avg) | activity_master granular 조회 |
| 휴일/주말 캘린더 | 공휴일 API 연동 |
| Plan fallback metric 정밀화 | 9/25 회귀 분석 후 |
| expected_completion 추세 외삽 | delay_days 의미 재정의 |
| RAG metadata 추가 활용 (conditions 매칭 가중치) | 운영 데이터 누적 후 |
| synthetic → 실 데이터 완전 교체 | 1~6 개월 후 |
| Few-shot 케이스 추가 (운영 golden 누적) | 동일 |
| LLM 모델 조정 (gpt-5-mini reasoning) | 운영 진단 품질 모니터링 후 |
| H-i-L 1 정정 누적 → worker_source=user_corrected rerank 효과 검증 | B_Track UI 안정 후 |

---

## 16. 미해결 사안 → Phase 2 위임

| # | 사안 | 비고 |
|---|---|---|
| 1 | sub_work_area 별 plan_start/finish 분산 weighted 처리 | Phase 1 단순 MIN/MAX |
| 2 | conditions 매칭 가중치 vs LLM 자율 비교 | A/B 테스트 후 |
| 3 | recovery_likelihood 0.7 + delay 5일 임계 검증 | 회귀 결과 |
| 4 | Plan fallback metric (단위당 productivity 비교) 의 main_unit 혼재 처리 | 9/25 회귀 후 |
| 5 | post_due Few-shot 4번째 추가 여부 | Phase 2 |
| 6 | embed cache (work_content 반복 호출 절약) | Phase 2 비용 |

---

## 17. 본 spec 의 다음 단계

```
[즉시]
  1. spec 문서 저장: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md  ✓ 완료 (리뷰 정정 반영)
  2. 사용자 spec 검토 게이트                                                       ← 현재
  3. writing-plans → docs/superpowers/specs/2026-05-16-cpia-forecaster-plan.md
     (Task 0 ~ 9 분해)
  4. subagent-driven-development 로 Task 0 ~ 9 실행

[차후 — 별도 brainstorming 사이클]
  Optimizer spec → Reporter spec → graph.py 통합 (LangGraph fan-in + interrupt 2)
```

---

## 18. 변경 이력

| 일자 | 변경 | 작성 |
|---|---|---|
| 2026-05-16 | 초안 — Forecaster 데이터 계약 + 구현 spec. 8 + 3 결정 (LLM Azure, RAG 우선, 임계 가정, cold start None, row 구조, Few-shot 3, metadata rerank, synthetic 필수 + delay_days 사용자 개념 + schedule_state 3 enum + 5 모듈 분리). 9/25 + synthetic 5건 시뮬 검증 (delay_days=-8.6, schedule_state=on_schedule, risk_level=정상). | A 트랙 |
| 2026-05-16 | spec §1 + §10 chromadb where 표기 정오표 — chromadb 0.5.20 `validate_where` 가 단일 dict 다중 operator + ISO string operand 모두 거부 → `{"$and": [{"company": ...}, {"l6_main": ...}]}` 만 Chroma where, date 30 일 윈도우는 코드단 list-comp 컷 (`_format_chroma_result` 직후). 함께: Forecaster 후속 6 fix (main_unit positive_units 필터, reasoning 3 종 분기, `WORK_HOURS_PER_DAY` 상수 추출, `graph.py` date alias, boundary tests 7건). | A 트랙 |
| 2026-05-16 | optimizer cycle Task 1 동반 — main_unit + today_conditions 2 필드 추가 (today_productivity 이미 박힘). §3.1 forecasts 스키마 + §10 agent.py return dict 동기화. Optimizer / hil_2 가 소비. spec: `docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md` §2.1 + §2.2 + §11.1. | A 트랙 |
| 2026-05-16 | 리뷰 정정 — coherence-reviewer + feasibility-reviewer 의 **16 발견 사항 모두 반영**: <br>**B-1**: atomizer schema (`productivity` 없음, `conditions` string) → `_normalize_chroma_metadata()` 정규화 함수 추가 (§7.1).<br>**C-1**: `temperature=0.3` 제거 (gpt-5 family 미지원, Parser/Mapper 패턴 따름) (§8.4, §10).<br>**C-2**: `fetch_plan_for_group` SQL 2 query 분리 (jsonb_object_agg duplicate 회피) (§5.2).<br>**Coh-2**: `fetch_chroma_actual()` 본체 명시, compute_delay nil path 추가 (§5.3, §5.4).<br>**Coh-3**: 마이그레이션 JSONB 컬럼 2개 + delay_days NUMERIC 변환 추가 (§13.2).<br>**Coh-4**: assessment=None LLM skip 명시 (§10).<br>**M-1**: Chroma where filter `{"date": {"$gte": ..., "$lt": ...}}` 단일 dict 로 통합 (§10).<br>**M-2**: Plan fallback metric 단위당 productivity ratio 로 교체 (§6.1).<br>**M-3**: nil path (plan 없음 / Chroma 0 row) 명시 처리 (§5.3 schedule_state="unknown").<br>**M-4**: delay_days INT → NUMERIC `ALTER COLUMN` (§13.2).<br>**Mi-2**: forecasts schema NOT NULL 제거 (cold start row INSERT 가능) (§3.1).<br>**Mi-3**: conditions empty string → list 정규화 (§7.1).<br>**Mi-4**: `insert_forecast(row)` SQL 본문 명시 (28 컬럼) (§5.6).<br>**Coh-5**: recovery_likelihood 0.7 근거 명시 (PM 원안 v2 80% 대비 conservative) (§0.2).<br>**Coh-7**: expected_completion = plan_finish (PoC) 주석 (§3.1, §10).<br>**Coh-8**: rag_top_k 자르는 위치 명시 (agent.py 책임, §7.2 주석). <br>**부수**: synthetic 비용 $0.5 → $0.001 정정 (§9.2). | A 트랙 |
