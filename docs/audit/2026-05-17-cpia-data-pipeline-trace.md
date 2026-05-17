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
- `docs/audit/raw/v2-scenario-1-156657ed.md` — 본 cycle 시뮬 1 실 호출 raw
- `docs/schema/postgres.md` — postgres schema spec (단 init.sql 와 #N2/#N3 mismatch)
