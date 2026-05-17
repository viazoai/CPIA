# CPIA 데이터 파이프라인 trace audit — 원본 → 가공 → 적재 단계별 실 데이터

- **Generated**: 2026-05-17
- **Git SHA**: `bf7e6d9` (A_Track, PR #19 head)
- **Scope**: 원본 작업일보 xlsx + 시뮬 fixture → 8 단계 (Parser → Mapper → HIL 1 → Atomizer → Forecaster → HIL 2 → Optimizer → Reporter) → 적재 (PG 8 테이블 + Chroma 2 컬렉션 + LangGraph 4 부속)
- **검증 방식**: Iron Law 3 요소 — 모든 단계 `$ command` + 실 출력 + 결론. 추측 0.

본 audit 는 audit-report (단계 일치도) 보다 한 단계 더 깊이 — **실 row 단위 인용 + JSON 구조 + before/after 데이터 transformation**. 다음 cycle 진입 시 데이터 흐름 이해 + 통합 검증의 reference 로 활용.

---

## 0. 현 데이터베이스 상태 snapshot (2026-05-17 14:50)

```
$ docker exec cpia-pg-local psql -U cpia -d cpia -c "..."
```

### PostgreSQL (10 활성 테이블)

| 테이블 | row count | 출처 / 책임 |
|---|---:|---|
| `pipeline_runs` | 11 | 모든 노드 — run lifecycle (status / current_node / atomized_count) |
| `forecasts` | 18 | Forecaster `insert_forecast` — 27 컬럼 (v3.1 main_unit + today_conditions) |
| `optimizer_advice` | 13 | Optimizer `insert_optimizer_advice` — 9 컬럼 (4 JSONB + diagnosis + assessment) |
| `mapping_corrections` | 2 | HIL 1 `insert_mapping_correction` — 6 컬럼 (drift #N2 schema mismatch, JSONB 합쳐 박음) |
| `daily_reports` | 2 | Reporter `insert_daily_report` — 7 컬럼 (drift #N3 schema mismatch, history_csv_row 컬럼) |
| `activity_master` | 1,059 | read-only — `scripts/load_master_list.py` 가 WBS Master List 적재 (Mapper + Forecaster SELECT) |
| `sites` | 1 | Dashboard — DEMO_SITE (mock) 1 row |
| `checkpoints` | 112 | LangGraph PostgresSaver (본 cycle 신규) |
| `checkpoint_writes` | 517 | LangGraph 부속 |
| `checkpoint_blobs` | 249 | LangGraph 부속 |

### ChromaDB (2 컬렉션)

| 컬렉션 | doc count | 1 doc = | 적재 주체 / 검색 주체 |
|---|---:|---|---|
| `wbs_master` | ~30 | (WA, L6) 그룹 | `scripts/load_master_list.py` 적재 / Mapper RAG (단계 ③) |
| `daily_activities` | 2,441 | 1 Activity (시트4 1 row) | Atomizer upsert / Forecaster RAG / Optimizer retrieve |

**daily_activities 2,441 = synthetic_v2 (27 그룹 × 90일 ≈ 2,430) + 본 cycle 시뮬 1 + rerun (~11 row).**

---

## Phase 0 — 원본 작업일보 xlsx (Parser 입력)

### 파일

```
docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx
```

4 시트 구조 (실제 xlsx):
- 시트1: BP사 × 공종 summary (오늘 인원 / 누계 / 작업 요지)
- 시트2: BP사 × 직종 인원 (cum_t)
- 시트3: BP사 × 장비 투입 (cum_t)
- 시트4: Activity (work_content 텍스트 + 물량)

### Parser 출력 — `parse_daily_report(xlsx) -> ParsedDailyReport` (실 호출)

```
$ PYTHONPATH=. .venv/bin/python3 -c "from pipeline.agents.parser import parse_daily_report; ..."

report_date=2025-09-25
project=M15X Ph-3 IBL PJT 작업일보
bp_summaries count=383
job_allocations count=14123
equipment_allocations count=8416
activities count=1193
```

**파일명 → meta 추출** (`_extract_meta:237`):
- `통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx` → `report_date="2025-09-25"`, `project="M15X Ph-3 IBL PJT 작업일보"`

### 시트 1 sample — `BPSummary` (383 row 중 첫 1 row)

```json
{
  "bp_code": null,
  "company": "PH_X-002",
  "disc_abbrev": "공통가설",
  "zone": "FAB/CUB",
  "scope": null,
  "work_text_yesterday": null,
  "work_text_today": null,
  "work_text_tomorrow": null,
  "today_incr_total": 0,
  "today_cum_total": 68
}
```

**가공 핵심**: `_disc_abbrev_to_kr` (AR→건축, EL→전기 등 영문 약어 → 한글), `_ffill` (병합 셀 forward-fill).

### 시트 2 sample — `JobAllocation` (14,123 row)

```json
{
  "bp_code": null,
  "company": "㈜에스티엠",
  "disc_abbrev": "공통가설",
  "job_type": "관리자06",
  "workers_cum_t": 0
}
```

**가공 핵심**: `_is_admin_job` (관리자 직종 필터) — Mapper / Forecaster 의 BP사 인원 산출 시 제외 의도. 단 본 row 는 관리자 → 후속 처리에서 무시.

### 시트 3 sample — `EquipmentAllocation` (8,416 row)

```json
{
  "bp_code": null,
  "company": "PH_X-002",
  "equipment_big": "굴삭운반기계류",
  "equipment_mid": "Back Hoe",
  "equipment_spec": "2㎥ 미만",
  "count_cum_t": 0
}
```

**가공 핵심**: 장비 컨텍스트 — Mapper `build_bp_context` 가 LLM input 에 BP사 보유 장비 정보로 박음.

### 시트 4 sample — `Activity` (1,193 row) — Mapper 입력

```json
{
  "wbs_activity_id": null,
  "l5_disc": "공통가설",
  "l6_main": null,
  "l7_sub": null,
  "l7_5_activity": null,
  "sub_work_area": null,
  "trade": "공통가설",
  "company": "㈜해광FAB",
  "unit": "ea",
  "today_qty": 0.0,
  "work_content": "1) 슈퍼데크 설치",
  "conditions": [],
  "assigned_workers": 0.0,
  "worker_source": "parsed",
  "plan_total_qty": 23.0,
  "plan_mh": null,
  "requires_review": false,
  "wa": null,
  "mapping_conf": null,
  "mapping_source": null
}
```

**핵심 fact**:
- `worker_source="parsed"` — 시트2 의 BP사 × 직종 인원 합산 (관리자 제외).
- `l6_main=None` / `wa=None` / `mapping_*=None` — **Parser 시점은 미매핑 상태**. Mapper 가 채움.
- `plan_total_qty=23.0` — 시트1 의 today_incr_total 또는 별 컬럼.
- 전체 1,193 row 중 매핑 가능 row 는 ~47 (남웅 + 비계 제외, `test_graph_e2e_namwong_47` 검증).

---

## Phase 1 — Mapper (`mapper.map_activity`)

### 6 단계 변환 (mapper.py:208~338)

```
1. fetch_bp_candidates (PG)
   → activity_master WHERE company=$1
   → DISTINCT (wa, l6_main) 후보 풀 (BP scope filter)

2. build_embedding_input (mapper.py:86)
   → "(work_content) (trade)" 순수 텍스트 (숫자/단위 제외)

3. Azure 임베딩 (text-embedding-3-small-ai-board-test, 1536d)
   → vector

4. Chroma wbs_master query (top-15)
   → BP filter 교집합 max 8 후보

5. build_llm_input (mapper.py:150)
   → BP사 풍부 컨텍스트 (시트1/2/3 정보 합쳐)
   → Azure gpt-5.1 분류
   → {choice: int, confidence: float, reason: str}

6. resolve_wa 4단계 (mapper.py:166)
   → WAResolution(value: str, source: str)
   → source ∈ {"auto_bp_single", "auto_l6_single", "auto_l6_multi_llm", "hil_required"}
   → requires_review = confidence < 0.7 OR source == "hil_required"
```

### activity_master sample (Mapper PG SELECT 대상) — 남웅 철콘 3 row

```sql
$ SELECT wbs_activity_id, wa, l5_disc, l6_main, l7_sub, l7_5_activity, company, unit, plan_total_qty, plan_mh_rev2, plan_start, plan_finish
  FROM activity_master WHERE company='남웅건설' AND l6_main='철근콘크리트공사' LIMIT 3;

   wbs_activity_id    | wa  | l5_disc |     l6_main      |   l7_sub   |           l7_5_activity           | company  | unit | plan_total_qty | plan_mh_rev2 | plan_start | plan_finish
----------------------+-----+---------+------------------+------------+-----------------------------------+----------+------+----------------+--------------+------------+-------------
 TNMCB1F6501A03030032 | CUB | 건축    | 철근콘크리트공사 | 거푸집공사 | 기초공사 : 거푸집 공사            | 남웅건설 | m2   |            500 |          456 | 2024-10-04 | 2024-10-27
 TNMCB1F6501A03020024 | CUB | 건축    | 철근콘크리트공사 | 철근공사   | 1층 바닥 Slab 공사 : 철근 조립    | 남웅건설 | ton  |            100 |          623 | 2024-11-16 | 2024-11-18
 TNMCB1F6501A03020023 | CUB | 건축    | 철근콘크리트공사 | 철근공사   | RC Wall & Column 공사 : 철근 조립 | 남웅건설 | ton  |            150 |         1215 | 2024-11-01 | 2024-11-07
```

→ **남웅건설 의 (CUB, 철근콘크리트공사) 그룹** = wa=CUB + l6_main 정합. Mapper 가 LLM rerank 단계에서 이 후보 풀 max 8건 → LLM 분류.

### wbs_master Chroma sample (Mapper RAG 대상) — `CUB|철근콘크리트공사`

```json
metadata:
{
  "companies": "남웅건설",
  "l5_disc": "건축",
  "l6_main": "철근콘크리트공사",
  "units": "ea,m2,m3,ton",
  "wa": "CUB"
}

document:
"""
Work Area: CUB (CUB, Main 공동구)
Discipline (L5): 건축
Work PKG-1 (L6): 철근콘크리트공사
Work PKG-2 (L7): 거푸집공사, 철근공사, 콘크리트공사
Units: ea, m2, m3, ton
Activities (L7.5 sample): 1층 바닥 Slab 공사 : 거푸집 공사, 1층 바닥 Slab 공사 : 철근 조립, ...
Companies: 남웅건설
"""
```

→ Chroma `wbs_master` 의 1 doc = 1 (wa, l6) 그룹. document 텍스트 = LLM 가 후보 평가 시 사용하는 "공종 설명" — units / L7 sub / L7.5 activity sample / companies 포함.

### Mapper 출력 sample — Activity 갱신 (예: 남웅 47 row 중 1)

`map_activity` 호출 후 Activity 의 신 필드 채움:

```diff
  "wa": null,           →  "wa": "CUB",
  "l6_main": null,      →  "l6_main": "철근콘크리트공사",
  "mapping_conf": null, →  "mapping_conf": 0.82,
  "mapping_source": null, → "mapping_source": "auto_bp_single",
  "requires_review": false  (mapping_conf >= 0.7 + source != "hil_required" 이므로 유지)
```

또 `_prorate_mh` (mapper.py:347) 호출 후: `assigned_workers` 가 BP사 인원 × (그 l6 candidate Σplan_mh / 전체 매핑 l6 candidate Σplan_mh) 비례 분배. 예: 남웅 88 인원 → 철콘 l6 에 88.0 (단일 그룹).

### LLM 호출 (Mapper 단계당 1회, 47 row → 47 LLM call ≈ $0.10)

- model: `gpt-5.1-chat-ai-board-test`
- system: `mapper/prompt.py:SYSTEM_PROMPT` (분류 룰 + few-shot)
- user: `build_llm_input` 출력 (work_content + BP사 컨텍스트 + 후보 max 8건)

---

## Phase 2 — HIL 1 (`hil_1_node`, 본 cycle 신규)

### 변환 (`graph.py:113~167`)

```
mapped → _build_review_needed → review_needed (requires_review=True 만 filter)
       → interrupt({"review_needed": [...]}) (≥1 시)
       → CLI prompt 또는 Command(resume={"0": {...}})
       → _apply_corrections → mapped 수정 + mapping_source="user_corrected"
       → PG insert_mapping_correction (corrections idx 마다 1 row)
```

### review_needed payload schema (interrupt value)

```json
{
  "review_needed": [
    {
      "idx": 1,
      "work_content": "1F 벽체 콘크리트 타설",
      "company": "남웅건설",
      "trade": "철근콘크리트공사",
      "wa": "CUB",
      "l6_main": "철근콘크리트공사",
      "mapping_conf": 0.55,
      "mapping_source": "hil_required"
    },
    {...}
  ]
}
```

### Command(resume=) 패턴 — drift #N5

```python
# 사용자 정정 입력
Command(resume={"0": {"wa": "CUB", "l6_main": "철근콘크리트공사"}, "2": {...}})
                 ↑ str key 필수 (int key 면 LangGraph 의 is_xxh3_128_hexdigest TypeError)
```

`hil_1_node` 가 `corrections = {int(k): v for k, v in corrections_raw.items()}` 로 변환 처리.

### PG `mapping_corrections` 실 row sample (2 row)

```sql
$ SELECT id, run_id, report_date, jsonb_pretty(original), jsonb_pretty(corrected), created_at
  FROM mapping_corrections ORDER BY created_at DESC LIMIT 2;
```

```
 id |  report_date  |                   original                   |                corrected                |          created_at
----+---------------+----------------------------------------------+-----------------------------------------+------------------------
  8 | 2025-09-27    | {                                            | {                                       | 2026-05-17 04:35:28+00
    |               |   "wa": "CUB",                               |   "wa": "CUB",                          |
    |               |   "trade": "철근콘크리트공사",               |   "l6_main": "철근콘크리트공사",        |
    |               |   "company": "남웅건설",                     |   "mapping_source": "user_corrected",   |
    |               |   "l6_main": "철근콘크리트공사",             |   "correction_type": "replace"          |
    |               |   "mapping_conf": 0.55,                      | }                                       |
    |               |   "work_content": "1F 벽체 콘크리트 타설",   |                                         |
    |               |   "mapping_source": "hil_required"           |                                         |
    |               | }                                            |                                         |
```

**drift #N2 schema 정합 관찰**:
- 실 PG `mapping_corrections` = 6 컬럼 (id + run_id + report_date + original + corrected + created_at).
- `postgres.md §8` spec 명시 = 10 컬럼 (위 6 + work_content + company + trade + correction_type top-level).
- 본 cycle 의 `insert_mapping_correction` = 실 schema 정합 4 인자 → `work_content / company / trade` 는 `original` JSONB 안에 합쳐, `correction_type` 은 `corrected` JSONB 안에 합쳐 박음. 의미 동일.

→ **schema migration 별 cycle (drift backlog #N2)** 진입 시 top-level 컬럼 추가 + insert signature 확장 + work_content GIN index 활성화.

---

## Phase 3 — Atomizer (`atomize`, atomizer.py:62)

### 변환 (3 단계)

```
1. valid filter: l6_main is not None 인 Activity 만 (Parser 시점 untagged row 제외)
2. assert_pipeline_run_exists (PG fail-fast) — orphan Chroma row 방지
3. _make_doc_id (SHA256 16자 prefix) → within-call dedup (같은 work_content 반복 시 마지막 metadata 채택)
4. _build_metadata (12 필드 스칼라화 — Chroma flat 제약)
5. Azure embedding batch (size 16) → text-embedding-3-small 1536d
6. Chroma daily_activities upsert
7. update_run_atomized_count (PG, 0-row RuntimeError)
```

### `_make_doc_id` 결정성 검증

```python
_make_doc_id("2025-09-25", "남웅건설", "철근콘크리트공사", "기초 거푸집 설치")
# → "73ff80435e312c41"  (test_atomizer.py:48 hardcoded 검증)
```

같은 (date, company, l6_main, work_content) 4-tuple → 항상 같은 16자 hex. **이후 upsert** semantics (재실행 시 새 row 추가 아닌 metadata 갱신).

### Chroma `daily_activities` 실 row sample (id=`73ff80435e312c41`)

```json
metadata:
{
  "assigned_workers": 88.0,
  "company": "남웅건설",
  "conditions": "",
  "date": "2025-09-25",
  "l5_disc": "건축",
  "l6_main": "철근콘크리트공사",
  "mapping_conf": 0.82,
  "run_id": "21a406f7-8a6d-433d-b39a-51cc7ca4e904",
  "today_qty": 0.0,
  "unit": "m2",
  "wa": "CUB",
  "worker_source": "mh_prorated"
}

document:
"기초 거푸집 설치"  ← work_content 텍스트 그대로
```

**가공 핵심**:
- `document` = `work_content` 그대로 (Chroma 의 검색 텍스트 — Forecaster RAG 시 query 텍스트와 cosine similarity).
- `metadata.conditions` = "" (parser 시점에 빈 list → atomizer 에서 CSV join, 빈 case 는 빈 str). Forecaster `rerank._normalize_chroma_metadata` 가 다시 list 로 변환.
- `today_qty=0.0` — 일부 row 가 물량 0 (시트4 본 row 에서 today_qty 미입력).
- `run_id` = 적재 시점의 pipeline_runs row 참조 (FK).

### PG `pipeline_runs.atomized_count` 갱신 (update_run_atomized_count)

```sql
UPDATE pipeline_runs SET atomized_count = $1, current_node = 'atomizer' WHERE run_id = $2
```

→ 0-row return → RuntimeError ("pipeline_runs(run_id=...) 미존재 — fixture 설정 확인").

---

## Phase 4 — Forecaster (`forecast`, forecaster/agent.py)

### 변환 (그룹화 + 8 단계)

```
1. 그룹화: mapped → (company, l6_main) 단위 fan-out
2. _forecast_one_group ① ~ ⑧:
   ① aggregate_today_by_unit — unit 별 Σ today_qty
   ② fetch_plan_for_group (PG activity_master) → plan_total_qty / plan_mh / plan_start / plan_finish
   ③ Chroma daily_activities RAG (current group 의 과거 유사) → rerank_cases
   ④ classify_assessment (RAG ≥3건 → RAG / else Plan / else None)
        - classify_assessment_rag (delta < -0.15 → "주의/이상", >= -0.15 → "정상")
   ⑤ fetch_chroma_actual + compute_delay → window mh 비교 + schedule_state
   ⑥ LLM (assessment != None) → reasoning + recovery_likelihood (Azure gpt-5.1)
   ⑦ classify_risk_level (assessment + recovery + delay + state) — hybrid 룰
   ⑧ insert_forecast (PG, 27 컬럼)
```

### PG `forecasts` 실 row sample — 시뮬 1 (run_id 156657ed) 3 그룹

```sql
$ SELECT company, l6_main, assessment, risk_level, today_productivity, today_assigned_workers, main_unit, today_qty_by_unit
  FROM forecasts WHERE run_id='156657ed-b1b3-409c-8202-c9f17dcfcfa8';
```

```
  company   |     l6_main      | assessment | risk_level | today_productivity | today_assigned_workers | main_unit | today_qty_by_unit
------------+------------------+------------+------------+--------------------+------------------------+-----------+-------------------
 남웅건설   | 철근콘크리트공사 | 이상       | 이상       |    13.93 (m3/인)   |          88            | m3        | {"m3": 1225.5}
 세보엠이씨 | 일반공조설비공사 | 정상       | 정상       |     0.84 (m2/인)   |         315.6          | m2        | {"m2": 263.7}
 창원기전   | 전등설비공사     | 정상       | 주의       |     0.29 (ea/인)   |          60.1          | ea        | {"ea": 17.6}
```

**핵심 fact 검증** — 본 cycle Forecaster fix 효과:
- 남웅 (synthetic ratio=0.45, n=5, baseline=31.07 m3/인): today_productivity = 31.07 × 0.45 = **13.93** → `classify_assessment_rag` 가 delta < -0.25 → **assessment="이상"**.
- 시뮬 1 의 raw md: `docs/audit/raw/v2-scenario-1-156657ed.md`.
- **이전 cycle (drift #3 bug 전)**: today_productivity = 5 × 31.07 × 0.45 = 69.91 → assessment="정상" (bias). 본 cycle `c093631` fix(synthetic_daily_report) 로 해소.

### Forecaster row 의 27 컬럼 schema (postgres.md §6)

```
id (BIGSERIAL) + run_id (UUID FK) + company / l6_main (grain)
+ 오늘 실측: today_qty_by_unit (JSONB) / today_assigned_workers / today_productivity / main_unit / today_conditions
+ Plan: plan_total_qty_by_unit (JSONB) / plan_mh_sum / plan_start / plan_finish / plan_mh_per_day
+ 누적 mh 비교: schedule_state / window_start / window_days / expected_in_window_mh / actual_in_window_mh / mh_gap / delay_days
+ RAG: rag_n_similar / similar_cases (JSONB)
+ LLM 산출: assessment / reasoning / recovery_likelihood
+ 종합: expected_completion / risk_level
+ created_at (TIMESTAMPTZ)
```

---

## Phase 5 — HIL 2 (`hil_2_node`)

### 변환

```
risky = forecast row 중 risk_level in {"주의", "이상"}
→ 빈 list → interrupt 미발생, hil_2_selection=[], pre_optimizer_cases={}, conditional_edge → reporter (이전 cycle 까지 END)
→ ≥1건 → 그룹 마다:
   - coll.get (Chroma 1회) → metadatas + documents
   - _group_baseline (5종 incident 제외 baseline productivity)
   - fetch_degradation_cases (저하 top-5, incident 3종 conditions 필터)
   - fetch_recovery_trajectory (각 case 의 다음 7일 회복 추세)
→ pre_optimizer_cases 영속 (state) + interrupt({"risky_groups": [...]})
→ Command(resume=[group_key, ...]) → hil_2_selection
```

### risky_groups payload sample (시뮬 1)

```json
{
  "risky_groups": [
    {
      "key": "남웅건설|철근콘크리트공사",
      "assessment": "이상",
      "risk_level": "이상",
      "reasoning": "맑음, 병행작업 없음. 유사 5건 평균 0.78 m3/인 대비 -42%. ...",
      "today_productivity": 13.93,
      "today_conditions": "장비대기",
      "preview_cases": [
        {"date": "2025-09-20", "conditions": "장비대기", "productivity": 12.5, "recovery": {"recovery_days": 2, ...}},
        ...
      ]
    },
    {
      "key": "창원기전|전등설비공사",
      "assessment": "정상",  // ← risk_level=주의 인데 assessment=정상 (cold_start path)
      "risk_level": "주의",
      "reasoning": "...",
      "preview_cases": [],   // ← cases=0 (cold_start, Chroma 적재 부족)
      "note": "cold_start_no_baseline"
    }
  ]
}
```

본 cycle 시뮬 1 = `--auto-select-all` flag → 모든 risky key 자동 resume (CLI 인터랙티브 우회).

---

## Phase 6 — Optimizer (`optimize`, optimizer/agent.py)

### 변환

```
hil_2_selection 마다:
- pre_optimizer_cases[key] cases<3 → cold_start row (LLM skip, recovery_distribution 만 산출)
- cases>=3 → build_llm_user_input → Azure gpt-5.1 → diagnosis + recommendations
- _compute_recovery_distribution (Counter) — LLM 산출 override (결정론 보장)
- insert_optimizer_advice (PG, 9 컬럼 JSONB falsy 보호)
```

### PG `optimizer_advice` 실 row sample — 시뮬 1 (run_id 156657ed) 2 그룹

```
 company  |     l6_main      | forecast_assessment |                                  diagnosis (head 200)                                    |     recovery_distribution
----------+------------------+---------------------+------------------------------------------------------------------------------------------+-------------------------------
 남웅건설 | 철근콘크리트공사 | 이상                | 맑음 조건임에도 장비 대기가 반복되며 생산성이 기준 대비 낮게 형성된 상황으로 보임.       | {"d+1": 2, "d+5": 1, "d+6": 1,
          |                  |                     | 과거 유사 케이스에서도 장비 대기 장기화 시 회복 지연이 반복됨.                          |  "not_recovered": 1}
 창원기전 | 전등설비공사     | 정상                | cold_start                                                                               | {}
```

**가공 핵심**:
- 남웅 = cases ≥3 → LLM 산출 (diagnosis + recommendations 4 rank).
- 창원 = cases <3 (cold_start path) → `_compose_cold_start_row` → `diagnosis="cold_start"` sentinel + 빈 recommendations + 빈 recovery_distribution.
- `recovery_distribution` = `_compute_recovery_distribution(cases)` (Counter 결정론) — LLM 산출 무시. 결정성 검증 시 100% 일치 (시뮬 1 vs rerun diff 0).

### 9 컬럼 schema (postgres.md §7)

```
id + run_id + company + l6_main + forecast_assessment
+ diagnosis (TEXT) + degradation_cases (JSONB) + recovery_pattern (JSONB)
+ recovery_distribution (JSONB, 결정론) + recommendations (JSONB ranked list)
+ created_at
```

JSONB falsy 보호: cold_start 의 빈 dict/list 도 INSERT (NULL X) — `is not None` 검사.

---

## Phase 7 — Reporter (`report`, reporter.py, 본 cycle 신규)

### 변환 (3 단계)

```
1. mapped empty → 짧은 fallback MD + PG INSERT skip
2. Azure gpt-5.1 호출:
   - SYSTEM_PROMPT (3 부 구조 + 한자 금지 + 들여쓰기 룰)
   - user message = _build_llm_input (4 키: date + activities + forecast + optimizer_advice)
3. _build_summary (4 키: total_workers + total_qty_by_trade + risk_counts + advice_count)
4. PG insert_daily_report (history_csv_row=summary, bp_name=None)
```

### PG `daily_reports` 실 row sample — 시뮬 1 rerun (run_id d9ff2092)

```
 id | report_date | bp_name | md_len |                  md_head (300 chars)                                |         summary (history_csv_row)
----+-------------+---------+--------+--------------------------------------------------------------------+--------------------------------------------
 16 | 2025-09-27  | (null)  |  1406  | # 2025-09-27 작업일보 종합 보고서                                  | {
    |             |         |        |                                                                    |   "risk_counts": {"이상":1, "정상":1, "주의":1},
    |             |         |        | ## 1부 작업 통합                                                    |   "advice_count": 2,
    |             |         |        |                                                                    |   "total_workers": 1507.0,
    |             |         |        | ### 남웅건설 / 철근콘크리트공사                                     |   "total_qty_by_trade": {
    |             |         |        | - 인원 합계: 528.0                                                  |     "전등설비공사": 17.6,
    |             |         |        | - 물량 합계: 1470.6 m3                                              |     "일반공조설비공사": 263.7,
    |             |         |        | - 작업 요지                                                          |     "철근콘크리트공사": 1225.5
    |             |         |        |   - 장비 FDN. - CT(Cooling Tower) - 철근 콘크리트 타설              |   }
    |             |         |        |   - Deck Plate 철근 콘크리트 타설 - 2절주 [5층 바닥]                | }
```

**drift #N3 schema 정합 관찰**:
- 실 PG `daily_reports` = 7 컬럼 (id + run_id + report_date + bp_name + report_md + history_csv_row + created_at).
- `postgres.md §5` spec 명시 = `date` / `summary` 필드명 (mismatch).
- 본 cycle 의 `insert_daily_report` = 실 schema 정합 5 인자 (report_date / history_csv_row / bp_name=None).
- 의미 동일 — `bp_name=None` (종합 보고서) + summary dict → history_csv_row JSONB.

### 의도적 drift (spec §3 명시)

| 항목 | PM 원안 v2 | 본 cycle | 사유 |
|---|---|---|---|
| 위치 | Atomizer 다음 (Forecaster 병렬) | Optimizer 다음 (hil_2 conditional 합류) | Forecaster + Optimizer 결과 모두 포함하는 종합 보고서 — 1 LLM call 효율 |
| 출력 | 사내 + 발주처용 2 종 | 종합 1 종 | PoC 시연 단순화 |
| LLM | Sonnet 4.6 | Azure gpt-5.1 | audit-report §3 (Azure 통일) |

---

## Phase 8 — LangGraph checkpoint (PostgresSaver, 본 cycle 신규)

### 변환

```
build_checkpointer() (checkpointer.py:80):
  if CPIA_CHECKPOINTER=="memory" → InMemorySaver
  elif POSTGRES_URL 없음 → InMemorySaver (안전 fallback)
  else → _LazyAsyncPostgresSaver (AsyncPostgresSaver + AsyncConnectionPool lazy open)
```

`_LazyAsyncPostgresSaver` (checkpointer.py:30):
- AsyncPostgresSaver 상속 (LangGraph isinstance 검사 통과)
- 5 method override (aput/aget_tuple/aput_writes/alist/aget) — 첫 호출 시 `_ensure_open` → `await self._lazy_pool.open()`

### PG 부속 테이블 (LangGraph auto-create)

| 테이블 | row count | 책임 |
|---|---:|---|
| `checkpoints` | 112 | thread_id 별 state snapshot (interrupt 시점) |
| `checkpoint_writes` | 517 | 노드 별 부분 write 로그 |
| `checkpoint_blobs` | 249 | 큰 state blob (state dict JSON) |
| `checkpoint_migrations` | (auto) | PostgresSaver schema 버전 |

### 사용 예 — HIL 2 시점 interrupt + resume

```
1. graph.ainvoke(initial_state, config={"configurable": {"thread_id": "hil2-resume-..."}})
   → forecaster 까지 진행 → hil_2_node 에서 interrupt({"risky_groups": [...]})
   → PostgresSaver 가 checkpoint 1 row 영속 (thread_id="hil2-resume-...")
2. ainvoke 호출자 가 `__interrupt__` 받음 + Dashboard/CLI 가 사용자 응답 수집
3. graph.ainvoke(Command(resume=[key]), config={"configurable": {"thread_id": "hil2-resume-..."}})
   → checkpoint 에서 thread_id 검색 → state 복원 → hil_2_node 재진입 → resume 처리 → optimizer 진행
```

→ 다중 사용자 동시 사용 시에도 thread_id 격리 OK. InMemorySaver 와 달리 process restart 후에도 영속.

---

## 데이터 흐름 요약 다이어그램

```
[원본 작업일보 xlsx]
   │  parse_daily_report
   ▼
[ParsedDailyReport (4 sheet)]
   │  mapper_node — 6단계 매핑 (BP filter + Embed + Chroma wbs_master + LLM + WA 4단계 + prorate_mh)
   │     ★ Azure LLM call × N(=47 for 남웅) ★
   ▼
[Activity[] with wa + l6_main + mapping_conf + requires_review]
   │  hil_1_node ★ 본 cycle 신규
   │     ├─ requires_review=False 다수 → 통과
   │     └─ requires_review=True ≥1 → interrupt → CLI prompt → corrections
   │        └─ PG mapping_corrections INSERT (per correction)
   ▼
[Activity[] (사용자 정정 + Mapper 추천 수용)]
   │  atomizer_node
   │     ├─ valid filter (l6_main != None)
   │     ├─ _make_doc_id (SHA256 16자, dedup)
   │     └─ Azure embedding × N → Chroma daily_activities upsert
   │  PG pipeline_runs.atomized_count UPDATE
   ▼
[Chroma daily_activities (N row, dedup 후 11 unique for 남웅 47)]
   │  forecaster_node
   │     ├─ 그룹화 (company, l6_main)
   │     ├─ Chroma RAG (current group 과거 유사 row)
   │     ├─ rerank_cases → 가중치 재정렬
   │     ├─ classify_assessment (RAG ≥3 → RAG 모드 / else Plan / else None)
   │     ├─ Plan activity_master fetch (l6 별 plan_total_qty / plan_mh)
   │     ├─ compute_delay (window mh 비교 + schedule_state)
   │     ├─ Azure LLM × N (assessment != None 일 때만, reasoning + recovery_likelihood)
   │     ├─ classify_risk_level (hybrid 룰)
   │     └─ PG forecasts INSERT (per group)
   ▼
[PG forecasts (N row, group 별 27 컬럼)]
   │  hil_2_node
   │     ├─ risky filter (risk_level in {주의, 이상})
   │     ├─ 그룹 별 Chroma 1회 호출 → degradation_cases + recovery_trajectory
   │     ├─ pre_optimizer_cases 영속 (state)
   │     └─ interrupt({"risky_groups": payload}) → Command(resume=[key])
   ▼
[state.hil_2_selection (사용자 선택 group)]
   │  conditional_edge: selection 비어있음 → reporter 직행 / 있음 → optimizer
   ▼
[optimizer_node (selection 있을 때만)]
   │  selected group 마다:
   │     ├─ cases<3 → cold_start row (LLM skip)
   │     └─ cases>=3 → Azure LLM × N → diagnosis + recommendations
   │  _compute_recovery_distribution (결정론)
   │  PG optimizer_advice INSERT (per group)
   ▼
[PG optimizer_advice (selected group 별 9 컬럼)]
   │  reporter_node ★ 본 cycle 신규
   │     ├─ mapped empty → fallback MD
   │     └─ Azure LLM × 1 → 종합 보고서 마크다운 (3 부)
   │  _build_summary (4 키)
   │  PG daily_reports INSERT (1 row, history_csv_row=summary, bp_name=None)
   ▼
[PG daily_reports (1 row)]
   │
   ▼
END

(전 과정에 걸쳐 LangGraph checkpoint = PostgresSaver
 → PG checkpoints + checkpoint_writes + checkpoint_blobs 자동 영속)
```

---

## LLM 호출 inventory (per run 평균)

| 단계 | LLM | 모델 | 호출 수 | per call cost |
|---|---|---|---:|---|
| Parser | — | — | 0 | 0 |
| Mapper | Azure | gpt-5.1-chat-ai-board-test | N (= 47 for 남웅) | ~$0.002 |
| Mapper 임베딩 | Azure | text-embedding-3-small-ai-board-test | N | ~$0.0001 |
| HIL 1 | — | — | 0 | 0 |
| Atomizer 임베딩 | Azure | text-embedding-3-small | N (dedup 후) | ~$0.0001 |
| Forecaster | Azure | gpt-5.1 | N_assessment_not_none | ~$0.005 |
| HIL 2 | — | — | 0 | 0 |
| Optimizer | Azure | gpt-5.1 | N_selected (cases>=3 만) | ~$0.01 |
| Reporter | Azure | gpt-5.1 | 1 | ~$0.005 |

본 cycle 시뮬 1 (3 그룹) ≈ Azure $0.10. 실 작업일보 (남웅 47 row + risky 1 group) ≈ $0.20~0.30.

---

## 본 audit 의 의도 + 다음 cycle 활용

1. **다음 cycle 진입 시 데이터 흐름 이해 reference** — 단계별 schema + 가공 룰 + 실 row sample 을 한 눈에 확인.
2. **drift backlog #N2 / #N3 (schema migration) 진입 시 사전 자료** — 실 PG schema vs postgres.md spec 의 정확한 mismatch 위치 명시.
3. **B_Track Dashboard 연동 시 Dashboard 가 SELECT 할 컬럼 확인** — `forecasts` (27 컬럼) + `optimizer_advice` (9 컬럼) + `daily_reports` (7 컬럼, history_csv_row JSONB 4 키) 의 명시 sample.
4. **PoC 시연 준비 (2026-06-05)** — 시뮬 1 실 호출 → 시연 시나리오 raw 검증 자료로 활용 가능. raw = `docs/audit/raw/v2-scenario-1-156657ed.md`.

---

## 부록 — 실 호출 명령 모음

```bash
# 작업일보 파싱 + 출력
PYTHONPATH=. pipeline/.venv/bin/python3 -c "from pipeline.agents.parser import parse_daily_report; ..."

# 시뮬 1 (남웅 ratio=0.45 + 세보 정상 + 창원 정상)
cd CPIA && set -a; source .env.local; set +a && \
  PYTHONPATH=. pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
    --date 2025-09-27 \
    --scenario "남웅건설|철근콘크리트공사|5|장비대기|0.45|1.0|m3" \
    --scenario "세보엠이씨|일반공조설비공사|3|정상|1.0|1.0|m2" \
    --scenario "창원기전|전등설비공사|2|정상|1.0|1.0|ea" \
    --auto-select-all

# PG 8 테이블 row count
docker exec cpia-pg-local psql -U cpia -d cpia -c "
  SELECT 'pipeline_runs' AS tbl, COUNT(*) FROM pipeline_runs
  UNION ALL SELECT 'forecasts', COUNT(*) FROM forecasts
  UNION ALL SELECT 'optimizer_advice', COUNT(*) FROM optimizer_advice
  UNION ALL SELECT 'mapping_corrections', COUNT(*) FROM mapping_corrections
  UNION ALL SELECT 'daily_reports', COUNT(*) FROM daily_reports
  UNION ALL SELECT 'activity_master', COUNT(*) FROM activity_master;
"

# Chroma sample 1 row
PYTHONPATH=. pipeline/.venv/bin/python3 -c "
from pipeline.chroma_client import ChromaClient
import os
c = ChromaClient(host=os.environ['CHROMA_HOST'], port=int(os.environ['CHROMA_PORT']))
da = c.get_or_create_daily_activities()
res = da.get(where={'\$and':[{'company':'남웅건설'},{'l6_main':'철근콘크리트공사'}]}, limit=1, include=['metadatas','documents'])
print(res)
"
```

---

**관련 문서:**
- `deep-dive/architecture_overview.md` — 시스템 다이어그램 + 서브시스템 요약
- `deep-dive/design-intent/INDEX.md` — T1 마스터 인덱스
- `docs/audit/2026-05-17-cpia-drift-backlog.md` — drift 흡수 + 신규 #N1~#N7
- `docs/audit/raw/v2-scenario-1-156657ed.md` — 시뮬 1 (남웅 0.45 + 세보/창원 정상) 실 호출 raw
- `docs/audit/raw/v2-scenario-2-e739277e.md` — 시뮬 2 (남웅 우천 0.8) raw
- `docs/audit/raw/v2-scenario-3-5a2010a7.md` — 시뮬 3 (남웅 돌관 0.45 ×1.3) raw
- `docs/audit/raw/v2-scenario-4-b6924645.md` — 시뮬 4 (신규 토목 cold_start) raw
- `docs/schema/postgres.md` — postgres schema spec (단 init.sql 와 #N2/#N3 mismatch)

---

# 부록 A — 4 시뮬 비교 + 추가 디테일 sample (보강)

본 부록은 사용자 명시 보강 요청 (2026-05-17) 에 따라 시뮬 4 건 모두 실 호출 + 디테일 sample 다수 추가.

## A.1 4 시뮬 결과 비교 표 (PG forecasts + optimizer_advice + daily_reports)

### Forecasts (4 시뮬 × 6 그룹 row)

| sim | run_id | company | l6_main | assessment | risk_level | today_prod | workers | rag_n_similar | conditions | reasoning (요지) |
|---|---|---|---|---|---|---:|---:|---:|---|---|
| 1 | 156657ed | 남웅건설 | 철근콘크리트공사 | **이상** | **이상** | 13.93 m3/인 | 88 | 5 | 맑음,장비대기 | 유사 5건 평균 22.8 m3/인 대비 -39% |
| 1 | 156657ed | 세보엠이씨 | 일반공조설비공사 | 정상 | 정상 | 0.84 m2/인 | 315.6 | 5 | 맑음 | 유사 5건 평균 0.67 m2/인 대비 +25% |
| 1 | 156657ed | 창원기전 | 전등설비공사 | 정상 | **주의** | 0.29 ea/인 | 60.1 | 0 | 맑음 | 유사 사례 0 (cold_start), Plan fallback 정상 |
| 2 | e739277e | 남웅건설 | 철근콘크리트공사 | 정상 | **주의** | 24.75 m3/인 | 88 | 1 | 맑음,**우천** | 유사 1건 24.58 m3/인 대비 +1%, 우천 → risk=주의 |
| 3 | 5a2010a7 | 남웅건설 | 철근콘크리트공사 | 정상 | **주의** | 10.71 m3/인 | 114.4 | 1 | 돌관,맑음 | 유사 1건 24.58 m3/인 대비 -56% **하지만 RAG <3 → Plan fallback → "정상"** |
| 4 | b6924645 | 신규건설 | 토목공사 | (null) | (null) | 0.00 | 0 | 0 | 맑음 | **cold_start** — 데이터 부족, 판단 보류 |

**핵심 관찰:**
1. **시뮬 1 남웅**: Forecaster fix 효과 100% 발현. today_prod=13.93 (=31.07×0.45) → delta -39% → "이상" 분류 정상.
2. **시뮬 3 남웅**: today_prod=10.71 (=baseline × 0.45 / 1.3). RAG delta -56% **인데도 assessment="정상"** — drift #N1 부산물. `classify_assessment` (classify.py:65) 가 `rag_n_similar < 3` 시 Plan fallback 진입 → Plan ratio 0.85+ 라 "정상" 분류. **synthetic_v2 적재 분포 정렬 cycle 후 RAG ≥3 보장 시 "이상" 분류 발현 예상.**
3. **시뮬 4 cold_start**: 모든 산식 0 propagation + assessment=null + Optimizer 미진입. 신 BP사/공종 등록 시 activity_master + synthetic_v2 적재 cycle 필수.

### Optimizer_advice (4 시뮬 × 4 row)

| sim | company | l6_main | forecast_assessment | diagnosis (요지) | recovery_distribution |
|---|---|---|---|---|---|
| 1 | 남웅건설 | 철근콘크리트공사 | **이상** | "장비 대기 반복, 회복 지연 패턴" | {d+1:2, d+5:1, d+6:1, not_recovered:1} |
| 1 | 창원기전 | 전등설비공사 | 정상 | **cold_start** (sentinel) | {} |
| 2 | 남웅건설 | 철근콘크리트공사 | 정상 | "정상 범위, 우천 영향 약함" | {d+1:2, d+5:1, d+6:1, not_recovered:1} |
| 3 | 남웅건설 | 철근콘크리트공사 | 정상 | "정상 범위, 돌관 특이 저하 없음" | {d+1:2, d+5:1, d+6:1, not_recovered:1} |
| 4 | — | — | — | **Optimizer 미진입** (risky 0 → hil_2_selection=[] → reporter 직행) | — |

**핵심 관찰:**
- **recovery_distribution 모두 동일** = {d+1:2, d+5:1, d+6:1, not_recovered:1}. 4 시뮬 의 같은 그룹 (남웅 철콘) Chroma 검색 결과가 같은 5 cases 반환 → 결정론 Counter 산출 동일. **결정성 검증 정합.**
- **시뮬 3 의 diagnosis quality**: LLM 이 "돌관 작업 조건에서도 특이 저하 근거 X" 라고 (실 데이터는 -56%) 판단 — Forecaster 의 assessment="정상" 시그널을 LLM 이 그대로 받음. drift #N1 효과가 Optimizer LLM 단까지 전파.
- **시뮬 4 의 Optimizer 미진입**: conditional_edge (hil_2 → reporter) 가 신 cycle 의 핵심 변경 — 이전 cycle 은 END 직행 → 신은 reporter 진입. 미흡 path 도 보고서 산출.

### Daily_reports (4 시뮬 × 4 row)

| sim | report_date | md_len | risk_counts | advice_count | total_workers | total_qty_by_trade |
|---|---|---:|---|---:|---:|---|
| 1 | 2025-09-27 | 1481 | {이상:1, 정상:1, 주의:1} | 2 | 1507.0 | 3 trade (철콘 1225.5 m3, 공조 263.7 m2, 전등 17.6 ea) |
| 2 | 2025-09-27 | 788 | {이상:0, 정상:0, 주의:1} | 1 | 264.0 | 철콘 2178.3 m3 |
| 3 | 2025-09-27 | 755 | {이상:0, 정상:0, 주의:1} | 1 | 343.2 | 철콘 1225.2 m3 |
| 4 | 2025-09-27 | 586 | {이상:0, 정상:0, 주의:0} | 0 | 0.0 | 토목공사 0.0 |

**핵심 관찰:**
- md_len 순서: 시뮬 1 (3 그룹) > 시뮬 2 (1 그룹 + 단단한 진단) > 시뮬 3 (1 그룹 + 진단) > 시뮬 4 (cold_start, 1 그룹 모두 0).
- summary 4 키 = Dashboard 카드 소스. risk_counts 가 위험도 분포, advice_count 가 권고 진입 그룹 수.
- **시뮬 4 의 daily_report 도 생성** — mapped 가 2 row 있어서 (assigned_workers=0 이라도) LLM 호출 진행 → fallback 보고서 산출.

## A.2 시뮬 1 Reporter 전체 report_md (보강 — 전체 1481 chars 인용)

```markdown
# 2025-09-27 작업일보 종합 보고서

## 1부 작업 통합

### 철근콘크리트공사 / 남웅건설
- 인원 합계: 88
- 물량 합계: 1225.5 m3
- 작업 요지
  - 장비 FDN. - CT(Cooling Tower) - 철근 콘크리트 타설
  - Deck Plate 철근 콘크리트 타설 - 2절주 [5층 바닥]
  - 1층 바닥 Slab 공사 : 철근 조립
  - 장비 FDN. - WFH(OAC WSS Filter Housing) - 철근 콘크리트 타설
  - PC Deck Plate 철근 콘크리트 타설 [4층 바닥]

### 일반공조설비공사 / 세보엠이씨
- 인원 합계: 315.6
- 물량 합계: 263.7 m2
- 작업 요지
  - 드레인 배관 Insulation 설치
  - 공조덕트 설치

### 전등설비공사 / 창원기전
- 인원 합계: 60.1
- 물량 합계: 17.6 ea
- 작업 요지
  - 전등 설비 Raceway

## 2부 생산성 진단

### 철근콘크리트공사 / 남웅건설
- today_productivity: 13.93 m3/인
- risk_level: 이상
- 진단: 맑음 조건이나 장비대기 존재. 유사 사례 평균 22.8 m3/인 대비 약 39% 낮아 다공정 병행 및 장비대기에 의한 저하 가능성이 높음.

### 일반공조설비공사 / 세보엠이씨
- today_productivity: 0.84 m2/인
- risk_level: 정상
- 진단: 맑음 조건에서 드레인 배관 및 덕트 Insulation 작업. 유사 사례 평균 0.67 m2/인 대비 약 +25%로 정상 범위.

### 전등설비공사 / 창원기전
- today_productivity: 0.29 ea/인
- risk_level: 주의
- 진단: 맑음 조건에서 일반적 Raceway 작업. 유사 사례는 없어 비교 기준은 없으나 계획 대비 큰 이탈 없으나 일정 지연 위험이 존재해 주의 필요.

## 3부 PM 선택 공종 권고

### 철근콘크리트공사 / 남웅건설
- 진단: 맑음 조건임에도 장비 대기가 반복되며 생산성이 기준 대비 낮게 유지되는 양상. 과거 사례에서도 장비 대기 장기화 시 회복 지연 빈번.
- 권고
  1. 타워크레인 또는 펌프카 등 주요 장비의 실제 대기 발생 원인 즉시 확인 권장
  2. 장비 대기 지속 시 자연 회복 가능성(D+1)은 낮은 편이므로 조기 개입 필요
  3. 잔여 물량 기준 D+3 이내 정상화 시 공기 영향은 제한적이므로 단기 회복 추세 모니터링
  4. 장비 대기 D+3 초과 시 장비 대수 증대 또는 타설 구역 조정 등 대안 검토 권장

(footnote) recovery_distribution: d+1 = 2, d+5 = 1, d+6 = 1, not_recovered = 1

### 전등설비공사 / 창원기전
- 진단: cold_start
- 권고: 제공된 권고 없음
```

**핵심 관찰:**
- SYSTEM_PROMPT 의 3 부 구조 그대로 LLM 산출. 들여쓰기 1~2 단계 룰 정합. 한자 0건 ✓.
- 1부 = mapped 합산 (BP사별 인원 + 물량 + 작업 요지). 2부 = forecast row 별 1 단락 (today_prod + risk_level + reasoning paraphrase). 3부 = optimizer_advice row 별 (diagnosis + recommendations rank + recovery_distribution footnote).
- 시뮬 1 의 창원 cold_start path → 3부 "권고: 제공된 권고 없음" — Optimizer 의 cold_start diagnosis sentinel 을 LLM 이 인지 + 적정 표현.

## A.3 Optimizer 의 recommendations JSONB 구조 sample (시뮬 1 남웅)

```json
[
  {
    "rank": 1,
    "text": "타워크레인 또는 펌프카 등 주요 장비 가용성의 금일 실제 대기 원인 확인 권장"
  },
  {
    "rank": 2,
    "text": "과거 사례상 장비 대기 지속 시 D+1 자연 회복 가능성은 낮은 편 — 조기 개입 검토 필요"
  },
  {
    "rank": 3,
    "text": "잔여 물량 기준 D+3 이내 정상화 시 공기 영향 제한적 — 단기 회복 가능성 모니터링"
  },
  {
    "rank": 4,
    "text": "장비 대기 현상 D+3 초과 시 장비 대수 증대 또는 타설 구역 조정 등 대안 검토 권장"
  }
]
```

**가공 핵심**:
- LLM (gpt-5.1) 산출. rank 1~4 = 위험도 순.
- text = 명령형 회피 (audit-report §3 명시) — "권장" / "검토 필요" 등 완곡 표현.
- 본 JSONB 가 Reporter 의 3 부 권고 list 로 그대로 transformation.

## A.4 Optimizer 의 degradation_cases JSONB (1 case sample)

```json
{
  "date": "2025-09-23",
  "recovery": {
    "trajectory": [
      {"date": "2025-09-24", "recovered": true, "conditions": "맑음", "productivity": 32.24},
      {"date": "2025-09-25", "recovered": false, "conditions": "", "productivity": 0.0}
    ],
    "recovery_days": 1
  },
  "activities": ["상부 PC Deck Plate 철근 조립 [6층 바닥]"],
  "conditions": "흐림,돌관",
  "productivity": 25.22,
  "assigned_workers": 92.9
}
```

**가공 흐름:**
- `optimizer/retrieve.py:fetch_degradation_cases:69` — Chroma daily_activities 검색 → 같은 (company, l6_main) + incident conditions ∈ {"우천", "돌관", "장비대기"} + productivity < baseline 인 row top-N.
- `optimizer/retrieve.py:fetch_recovery_trajectory:117` — 각 case 의 다음 7일 productivity 흐름 추적 → `recovery_days` = 첫 recovered=true 까지 일수.
- 본 case = 2025-09-23 흐림+돌관 day → 25.22 m3/인 (baseline 24.58 대비 +3% but 의도된 incident) → 다음날 32.24 (회복) → recovery_days=1.

**LLM input** 으로 본 JSONB list 전달 → diagnosis + recommendations 산출. `_compute_recovery_distribution` 가 recovery_days 값들 Counter (`{d+1: ..., d+5: ..., not_recovered: ...}`) 산출 → LLM 무관 결정론.

## A.5 Forecaster 8 단계 sample (시뮬 1 남웅 그룹 trace)

```
[입력] mapped row (남웅건설|철근콘크리트공사 단일 그룹, 5 row 합산)
       total today_qty=1225.5 m3, total assigned_workers=88, conditions=[맑음, 장비대기]

① aggregate_today_by_unit (aggregate.py:14)
   → {"m3": 1225.5}, main_unit="m3" (max qty)

② fetch_plan_for_group (PG activity_master)
   → plan_total_qty_by_unit={"m3": 6000.0 (예시)},
     plan_mh_sum=8000, plan_start=2024-10-04, plan_finish=2025-12-15

③ Chroma daily_activities RAG (group 별)
   → similar_cases [5 건 (같은 company+l6_main, 다른 date)] → rerank_cases

④ classify_assessment_rag (classify.py:27)
   → today_prod = today_qty / workers = 1225.5 / 88 = 13.93 m3/인
   → rag_avg_prod = (5 cases 평균) = 22.8 m3/인
   → delta = (13.93 - 22.8) / 22.8 = -0.39 (-39%)
   → delta < -0.25 → assessment="이상"

⑤ compute_delay (aggregate.py:23)
   → window mh = plan_mh × elapsed days vs actual mh
   → mh_gap = ... → delay_days = 73.8 일 (positive = 지연)
   → schedule_state = "on_schedule" (예시) — single day perspective

⑥ Azure LLM (gpt-5.1) — assessment != None 이라 진행
   → reasoning = "맑음·장비대기 있음. 유사 5건 평균 22.8 m3/인 대비 -39%. work_content 다공정 병행과 '장비대기'로 인한 생산성 저하 가능성."
   → recovery_likelihood = (LLM 산출, 신뢰도)

⑦ classify_risk_level (classify.py:83)
   → assessment="이상" + delay=73.8 + state="on_schedule"
   → risk_level="이상" (assessment 가 가장 강한 신호)

⑧ insert_forecast (db.py:205) — 27 컬럼 JSONB 다수
   → PG forecasts INSERT 1 row
```

## A.6 Mapper LLM call 흐름 sample (가상 — 실 xlsx 의 1 row)

본 trace 시작 시 Mapper LLM call (47 row × $0.002 ≈ $0.10) 비용 회피 — 실 호출 sample 대신 spec + code 인용:

```python
# 입력 (build_llm_input output, mapper.py:150)
{
  "work_content": "1F 벽체 콘크리트 타설",
  "company": "남웅건설",
  "trade": "철근콘크리트공사",
  "bp_context": "남웅건설 BP사: ... (시트1/2/3 풍부 컨텍스트)",
  "candidates": [
    {"wa": "CUB", "l6_main": "철근콘크리트공사", "score": 0.92, "doc": "Work Area: CUB ..."},
    {"wa": "CUB", "l6_main": "양생공사", "score": 0.78, ...},
    ... (max 8)
  ]
}

# LLM 출력 (Azure gpt-5.1)
{
  "choice": 0,           # candidates[0] 선택
  "confidence": 0.92,
  "reason": "work_content 의 '콘크리트 타설' 이 CUB|철근콘크리트공사 의 L7.5 sample 과 정합. 타 후보 보다 신뢰도 높음."
}

# resolve_wa (mapper.py:166) 4 단계 → WAResolution(value="CUB", source="auto_bp_single")
# Activity 갱신: wa="CUB", mapping_conf=0.92, requires_review=False (>= 0.7)
```

`mapping_source` 의 4 가지:
- `auto_bp_single`: BP filter 후 단일 (wa, l6) 만 남음 → 자동 결정 (LLM rerank 불필요).
- `auto_l6_single`: l6_main 후보가 단일 → 자동 결정.
- `auto_l6_multi_llm`: l6_main 다수 후보 → LLM rerank → choice 결정.
- `hil_required`: LLM confidence < 0.7 또는 모호 → HIL 1 큐 진입.

## A.7 HIL 1 corrections JSON sample (test_graph_e2e_hil1.py 의 실 e2e)

```python
# 1st ainvoke → __interrupt__ payload
{
  "review_needed": [
    {
      "idx": 0,
      "work_content": "work_0",
      "company": "company_0",
      "trade": "철근콘크리트공사",
      "wa": "OLD_WA",
      "l6_main": "철근콘크리트공사",
      "mapping_conf": 0.55,
      "mapping_source": "hil_required"
    }
  ]
}

# 2nd ainvoke (사용자 정정)
Command(resume={"0": {"wa": "USER_CORRECTED", "l6_main": "철근콘크리트공사"}})
                # ^ str key 필수 (int key 면 LangGraph TypeError — drift #N5)

# hil_1_node 처리 후 state.mapped[0]
{
  "wa": "USER_CORRECTED",          # ← 사용자 정정
  "l6_main": "철근콘크리트공사",
  "mapping_source": "user_corrected",
  "requires_review": False
}

# PG mapping_corrections INSERT
{
  "run_id": <uuid>,
  "report_date": "2025-09-25",
  "original": {
    "work_content": "work_0",
    "company": "company_0",
    "trade": "철근콘크리트공사",
    "wa": "OLD_WA",
    "l6_main": "철근콘크리트공사",
    "mapping_conf": 0.55,
    "mapping_source": "hil_required"
  },
  "corrected": {
    "wa": "USER_CORRECTED",
    "l6_main": "철근콘크리트공사",
    "mapping_source": "user_corrected",
    "correction_type": "replace"
  }
}
```

## A.8 Atomizer dedup detail (남웅 47 row → 11 unique 의 예시)

`_make_doc_id` = `SHA256("2025-09-25|남웅건설|철근콘크리트공사|<work_content>")[:16]`.

```
input mapped (47 row):
  row[0]:  date="2025-09-25", company="남웅건설", l6="철근콘크리트공사", work="기초 거푸집 설치" → doc_id=73ff80435e312c41
  row[1]:  date="2025-09-25", company="남웅건설", l6="철근콘크리트공사", work="기초 거푸집 설치" → doc_id=73ff80435e312c41 (중복)
  row[2]:  date="2025-09-25", company="남웅건설", l6="철근콘크리트공사", work="버림틀 설치"      → doc_id=009c588667375459
  row[3]:  date="2025-09-25", company="남웅건설", l6="철근콘크리트공사", work="버림틀 설치"      → doc_id=009c588667375459 (중복)
  ...
  → within-call dedup: 47 → 11 unique doc_id

처리:
  - Python 단 dedup (마지막 등장 metadata 채택, atomizer.py:85-89)
  - Azure embedding × 11 (47 아닌 dedup 후)
  - Chroma upsert × 11 (idempotent, 같은 id 재호출 시 metadata 갱신)

검증:
  - PG pipeline_runs.atomized_count = 11 (test_graph_e2e_namwong_47)
  - 재실행 시 같은 doc_id → upsert (새 row 추가 X)
```

**의도된 동작:**
- 같은 BP사가 같은 l6_main 에 같은 work_content 여러 번 기록 (예: 47 row 중 동일 콘크리트 타설 작업) → 1 doc_id 1 row 압축.
- `assigned_workers` 등 metadata 는 마지막 등장 값 (집계 X). Forecaster 가 그룹 단위 합산은 별도 PG SELECT 또는 Chroma group_by.

## A.9 Drift #N1 효과 검증 (시뮬 3 의 RAG fallback path)

시뮬 3 은 drift #N1 의 실 발현 사례 — **본 cycle 의 fixture fix 가 작동 하지만 RAG 분포 부족이 효과를 마스킹**.

```
시뮬 3 산식:
  - n=3, ratio=0.45, workers_ratio=1.3
  - baseline_q (남웅 철콘 m3) = 활성 master 의 plan_total_qty / 90 ≈ ?
  - baseline_workers = 88 (남웅 BP 인원 비례)
  - today_qty (row 당) = baseline_q × 0.45 / 3 (n 분배)
  - today_qty (group total) = baseline_q × 0.45
  - assigned_workers = 88 × 1.3 = 114.4
  - today_prod = (baseline_q × 0.45) / 114.4 = baseline_prod × 0.45 / 1.3

실 측정 (PG forecasts):
  - today_prod = 10.71 m3/인
  - rag_n_similar = 1 (synthetic_v2 같은 그룹 단 1 건)
  - rag_avg = 24.58 m3/인 (단일 사례 1)
  - delta = (10.71 - 24.58) / 24.58 = -56%

classify_assessment 라우팅 (classify.py:65):
  - rag_n_similar < 3 → RAG 신뢰 부족 → Plan fallback
  - classify_assessment_plan (today_prod vs plan_prod from activity_master)
  - plan_prod 산출 = plan_mh_sum / (plan_finish - plan_start)
  - 시뮬 fixture 의 plan vs today ratio 가 0.85+ → assessment="정상"

→ 의도된 -56% 저하가 "정상" 분류로 흡수.
```

**drift #N1 별 cycle 의 처리 방향:**
- synthetic_v2 적재 분포 정렬 — 27 그룹 × 90일 = 2430 row 가 같은 평균 productivity 보장.
- 단일 그룹 (남웅 철콘) 의 같은 incident type (예: 돌관) cases ≥3 보장 → RAG 모드 진입 → 의도된 저하 발현.
- 본 cycle 의 시뮬 3 가 fix 후 같은 시나리오 재실행 시 assessment="이상" 발현 예상.

## A.10 결정성 검증 (시뮬 1 vs rerun)

```
$ diff <(grep -E "assessment=|risk=|recovery_distribution" /tmp/v2-scenario-1.log) \
       <(grep -E "assessment=|risk=|recovery_distribution" /tmp/v2-scenario-1-rerun.log)

→ (출력 없음 — diff 0)
```

**결정론 컬럼** (assessment, risk_level, today_productivity, recovery_distribution) = 100% 일치.

**LLM 비결정성 허용 컬럼**:
- diagnosis: 1차 = "맑음 조건임에도 장비 대기가 반복되며..." / rerun = "맑음 조건임에도 장비 대기가 반복되며 생산성이 평시 대비 낮게 관찰됨..." — 첫 문장만 약간 변형.
- recommendations[i].text: 같은 의미 다른 표현.
- report_md: 본문 구성 같음, 단어 선택 약간 차이.

→ **결정성 검증 정합** (spec §10 성공 기준 #6). LLM 비결정성이 결정론 신호를 흐리지 않음.

---

## 부록 B — Azure 비용 inventory (실 측정)

| 시뮬 | scenarios | 그룹 수 | Forecaster LLM | Optimizer LLM | Reporter LLM | 임베딩 | 추정 cost |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | 3 | 3 | 3 | 1 (1 cold_start skip) | 1 | 6 | ~$0.05 |
| 1 rerun | 3 | 3 | 3 | 1 | 1 | 6 | ~$0.05 |
| 2 | 1 | 1 | 1 | 1 | 1 | 3 | ~$0.03 |
| 3 | 1 | 1 | 1 | 1 | 1 | 3 | ~$0.03 |
| 4 | 1 | 1 | 0 (assessment=None) | 0 (미진입) | 1 | 2 | ~$0.01 |
| **합계** | — | — | **8** | **4** | **5** | **20** | **~$0.17** |

본 cycle 의 audit 총 Azure 비용 ≈ **$0.17** (시뮬 4 건 + rerun + reporter 모두).

---

**관련 문서:**
- `docs/audit/raw/v2-scenario-{1,2,3,4}-*.md` — 4 시뮬 raw (개별 detail)
- `deep-dive/architecture_overview.md` — 시스템 다이어그램 + 8 서브시스템 요약
- `deep-dive/design-intent/INDEX.md` — T1 마스터 인덱스 (114 함수)
- `docs/audit/2026-05-17-cpia-drift-backlog.md` — 흡수 4 + 신규 #N1~#N7
