# Design Intent — persistence (PostgreSQL + ChromaDB + FastAPI)

- **Generated**: 2026-05-20 (db.py 3배 + api.py 0→1050 LOC + 16 migration cycle)
- **Git SHA**: `ef7c6cd` (A_Track HEAD, branch A_Track)
- **Pair file**: `../architecture_overview.md`
- **Range**:
  - `pipeline/db.py` (1113 LOC, 이전 385 → 거의 3배)
  - `pipeline/api.py` (1050 LOC, 이전 0 → FastAPI 12 엔드포인트 완성)
  - `pipeline/chroma_client.py` (35 LOC)
  - `pipeline/checkpointer.py` (94 LOC)
  - `infra/postgres/migrations/` (16 SQL 파일)
  - `pipeline/tests/test_db*.py` (10+ 파일) + `test_api_*.py` (5 파일) + `test_chroma_client.py` + `test_checkpointer.py`
- **스펙**:
  - `docs/superpowers/specs/2026-05-17-cpia-db-migration-api-contract-design.md`
  - `docs/architecture/api-contract.md`
  - `docs/schema/postgres.md`

PostgreSQL asyncpg pool 래퍼 + ChromaDB HTTP 클라이언트 + **FastAPI 12 엔드포인트** (이전 0 byte → 1050 LOC). 16개 migration (2026-05-16 ~ 05-19) — 신규 테이블 6종 + 신규 컬럼 21건. `upsert_daily_report_view_col` (UPDATE-first + 9 컬럼 화이트리스트) — partial write 가드. Chroma 2 컬렉션 (`wbs_master` Mapper RAG + `daily_activities` Forecaster/Optimizer retrieve).

---

## T1 — Function Index

### db.py (1113 LOC) — PGClient 25 메서드

#### 조회 (SELECT) — 7개

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `connect` / `close` | db.py:24/32 | `async () -> None` | 커넥션 풀 라이프사이클 | — |
| `fetch_bp_candidates` | db.py:38 | `async (company, site_id=None) -> list[dict]` | 공종 (WA, L6) 후보 풀 (Mapper BP filter) | ✅ |
| `fetch_activity` | db.py:73 | `async (wbs_activity_id, site_id=None) -> dict\|None` | ActivityID → Plan 값 + 메타 (미사용 의심) | ✅ |
| `fetch_l6_plan_mh_map` | db.py:106 | `async (company, l6_list, site_id=None) -> dict` | (l6_main → plan_mh) dict (N+1 회피) | ✅ |
| `fetch_plan_for_group` | db.py:194 | `async (company, l6_main, site_id=None) -> dict` | (company, l6_main) plan 합계 (2 SQL 분리) | ✅ |
| `get_pipeline_run` | db.py:486 | `async (run_id) -> dict\|None` | pipeline_runs 1 row | — |
| `fetch_one` / `fetch_all` | db.py:1000/1011 | `async (sql, *args) -> dict\|list[dict]` | 임의 SELECT helper | — |

#### INSERT (단일/배치) — 13개

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `insert_pipeline_run` | db.py:147 | `async (run_id, site_id, date, status) -> None` | pipeline_runs 단일 INSERT | ✅ |
| `assert_pipeline_run_exists` | db.py:176 | `async (run_id) -> None` | row 미존재 시 RuntimeError | — |
| `delete_pipeline_run` | db.py:170 | `async (run_id) -> None` | test fixture cleanup용 | — |
| `insert_forecast` | db.py:260 | `async (row: dict) -> None` | forecasts 단일 INSERT (28 컬럼 + wa) | ✅ |
| `insert_optimizer_advice` | db.py:332 | `async (row: dict) -> None` | optimizer_advice INSERT (9 컬럼 + JSONB 4종) | ✅ |
| `insert_mapping_correction` | db.py:370 | `async (run_id, report_date, original, corrected) -> None` | mapping_corrections INSERT | ✅ |
| `insert_daily_report` | db.py:405 | `async (run_id, report_date, report_md, history_csv_row, bp_name=None, site_id=None) -> None` | daily_reports INSERT (site_id auto-fetch) | ✅ |
| `insert_mapped_history_batch` | db.py:440 | `async (run_id, report_date, site_id, rows) -> None` | mapped_history batch (ON CONFLICT UPDATE) | ✅ |
| `insert_parser_report` | db.py:497 | `async (run_id, report_date, project, bp_summaries, job_allocations, equipment_allocations, activity_count) -> None` | parser_reports 1 row (ON CONFLICT DO UPDATE) | ✅ |
| `insert_parser_activities_batch` | db.py:540 | `async (run_id, report_date, activities) -> None` | parser_activities batch (23 컬럼) | ✅ |
| `insert_mapper_activities_batch` | db.py:621 | `async (run_id, report_date, activities) -> None` | mapper_activities batch (**33 컬럼 + alternatives + cum_workers/mh**) | ✅ |
| `insert_parser_job_allocations_batch` | db.py:743 | `async (run_id, report_date, rows) -> None` | parser_job_allocations (시트2, 3 group JSONB) | ✅ |
| `insert_parser_equipment_allocations_batch` | db.py:815 | `async (run_id, report_date, rows) -> None` | parser_equipment_allocations (시트3) | ✅ |
| `insert_parser_worker_outputs_batch` | db.py:881 | `async (run_id, report_date, rows, bp_name=None) -> None` | parser_worker_outputs (시트6, 업체별) | ✅ |
| `insert_parser_report_meta_batch` | db.py:952 | `async (run_id, report_date, metas) -> None` | parser_report_meta (Cover, 업체별) | ✅ |

#### UPDATE — 1개

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `upsert_daily_report_view_col` | db.py:1034 | `async (run_id, site_id, report_date, col, value) -> None` | **daily_reports JSONB 부분 UPSERT (UPDATE-first + 9 col 화이트리스트)** | ✅ |

#### Module-level — 2개

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `update_site_last_run` | db.py:1081 | `async (pg, site_id, run_id) -> None` | G8 — sites.last_run_id 갱신 | ✅ |
| `update_site_hours_saved_cum` | db.py:1097 | `async (pg, site_id, atomized_count) -> None` | G2 — sites.hours_saved_cum 누적 ((120-5)/60 × atomized_count h) | ✅ |

### chroma_client.py (35 LOC) — ChromaClient

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `get_or_create_wbs_master` | chroma_client.py:23 | `() -> Collection` | wbs_master 조회/생성 (Mapper RAG) | ✅ |
| `get_or_create_daily_activities` | chroma_client.py:30 | `() -> Collection` | daily_activities 조회/생성 (Forecaster + Optimizer retrieve) | ✅ |

### checkpointer.py (94 LOC)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_LazyAsyncPostgresSaver` | checkpointer.py | `class` | sync __init__ 안에서 await pool.open() 호출 불가 → lazy init | ✅ |
| `build_checkpointer` | checkpointer.py:78 | `() -> CheckpointerBase` | env `CPIA_CHECKPOINTER` 기반 InMemorySaver ↔ AsyncPostgresSaver 선택 | ✅ |

### api.py (1050 LOC) — FastAPI 12 endpoint

| # | Method | Path | Line | Output | DB Calls |
|---|---|---|---|---|---|
| 1 | GET | `/health` | api.py:188 | `{status, pg, version}` | 1 SELECT |
| 2 | POST | `/api/runs/{run_id}/hil_1/resume` | api.py:200 | `{next_node}` | graph.ainvoke (Mapper resume) |
| 3 | GET | `/api/sites` | api.py:314 | `Site[]` | 1 SELECT (sites + forecasts LATERAL) |
| 4 | GET | `/api/runs/{run_id}/optimizer` | api.py:378 | `OptimizerOutput[]` | 1 SELECT |
| 5 | GET | `/api/runs/{run_id}/wp_summary` | api.py:458 | `WPSummaryRow[]` | 1 SELECT (3 join) |
| 6 | GET | `/api/sites/{site_id}/reports` | api.py:519 | `ReportDaily[]` | 1 SELECT (days 필터) |
| 7 | GET | `/api/dashboard/performance` | api.py:560 | `{fleet_kpi}` | 1 SELECT (CTE + agg) |
| 8 | GET | `/api/dashboard/impact` | api.py:620 | `ImpactSiteDistribution[]` | 1 SELECT |
| 9 | GET | `/api/agents/status` | api.py:706 | `AgentStatus[]` | 7× SELECT COUNT |
| 10 | GET | `/api/sites/{site_id}/wbs_tree` | api.py:809 | `WBSNode (tree)` | 1 SELECT |
| 11 | GET | `/api/tasks` | api.py:1022 | `{tasks, progressByDate, itemsByDate}` | 2 SELECT |

---

## T2 — Issue Cards (Tier-1 핵심)

### `insert_mapper_activities_batch` — Mapper 최종 출력 (33 컬럼)

- **위치**: `pipeline/db.py:621-737` (117 LOC)
- **시그니처**: `async def insert_mapper_activities_batch(run_id, report_date, activities: list[dict]) -> None`
- **이슈**:
  - 33 컬럼 — 2026-05-19 cycle 에 alternatives + cum_workers_today + cum_actual_mh_today 추가
  - 멱등성 키 `(run_id, idx)` PK + ON CONFLICT DO UPDATE 모든 컬럼
  - migration: `2026-05-18_parser_mapper_outputs.sql` + `2026-05-19_mapper_alternatives.sql` + `2026-05-19_daily_reports_views.sql` (cum_workers)
- **설계 의도**:
  - 파일 단위 cycle 안의 모든 mapper 산출 batch 적재 (POC 146 row)
  - alternatives jsonb — FE review modal 의 dropdown 옵션
  - cum_workers/cum_actual_mh_today — U1.B prorate 결과
- **대응 패턴**:
  - 입력: rows list (33 키)
  - 처리: executemany 1 query
  - 출력: None (side effect = PG INSERT)
- **관련**:
  - 호출자: graph.py `mapper_node` (graph.py:48~165)
  - 테스트: `test_mapper_golden.py`, `test_mapper_alternatives.py`, `test_mapper_weighted_mh.py`, `test_db_new_columns_insert.py`
- **Suspected related** (2026-05-19):
  - mapper.py `_select_top_k_alternatives` — alternatives jsonb 입력
  - mapper.py `_prorate_workers_with_mh` — cum_workers / cum_actual_mh_today 입력

---

### `upsert_daily_report_view_col` — UPDATE-first partial write 가드

- **위치**: `pipeline/db.py:1034-1078` (45 LOC)
- **시그니처**: `async def upsert_daily_report_view_col(run_id, site_id, report_date, col: str, value) -> None`
- **이슈**:
  - git log: `b5404a4 feat(db): upsert_daily_report_view_col — partial write per jsonb column (B.8)`
  - git log: `ef7c6cd fix(db): daily_reports site_id + upsert UPDATE-first + scenarios_jsonb whitelist` (2026-05-20)
  - 주석 (db.py:1052~1054): "UPDATE 우선 — partial unique index `(run_id, site_id, report_date) WHERE site_id IS NOT NULL` 가 ON CONFLICT 와 안정 매칭 안 됨"
- **설계 의도**:
  - Reporter cycle 안에서 JSONB 컬럼 9종을 1개씩 부분 업데이트 — 한 컬럼 fail 해도 다른 컬럼은 유지
  - UPDATE-first → 신규일 때만 INSERT (대부분 reporter 가 사전 INSERT 보장)
  - **SQL injection 방어**: col 파라미터 9개 화이트리스트 체크 후 f-string 사용
  - **화이트리스트** (`_VIEW_JSONB_COLS`):
    ```
    kpi_jsonb / contractor_bars_jsonb / trade_bars_jsonb / quadrant_jsonb
    wp_summary_jsonb / s_curve_jsonb / optimizer_view_jsonb
    productivity_jsonb / scenarios_jsonb
    ```
- **대응 패턴**:
  - 입력: run_id, site_id, report_date, col (화이트리스트), value (JSONB)
  - 처리: col 체크 → UPDATE (RETURNING id) → row 없으면 INSERT
  - 출력: None
- **관련**:
  - 호출자: optimizer `optimize` (agent.py:~50) — 9 view jsonb 적재
  - 테스트: `test_db_daily_reports.py` (간접 검증)
- **Suspected related** (2026-05-20):
  - optimizer view_builder.py 의 8+1 build 함수 — 본 함수의 input 산출
  - ef7c6cd cycle — scenarios_jsonb 화이트리스트 추가

---

### `insert_mapped_history_batch` — 멱등 UPDATE atomizer 입력

- **위치**: `pipeline/db.py:440-484` (45 LOC)
- **시그니처**: `async def insert_mapped_history_batch(run_id, report_date, site_id, rows: list[dict]) -> None`
- **이슈**:
  - migration: `2026-05-18_mapped_history.sql` + `2026-05-19_mapped_history_trade.sql` (trade 컬럼 추가)
  - 멱등성 키 `(run_id, wa, l6_main, company)` ON CONFLICT UPDATE
  - 주석 (db.py:447): "INSERT 대상 = wa + l6_main 둘 다 not None 인 활동 (Phase 3 결정)"
- **설계 의도**:
  - 현장별 당일 실적 누적 — forecaster RAG 입력 + s_curve actual
  - 같은 (wa, l6_main, company) 재호출 시 today_qty / today_assigned_workers / unit 마지막 값 채택
- **대응 패턴**:
  - 입력: rows (wa, l6_main, company, today_qty, today_assigned_workers, unit, trade)
  - 처리: executemany ON CONFLICT (run_id, wa, l6_main, company) DO UPDATE
  - 출력: None
- **관련**:
  - 호출자: atomizer_node (graph.py:292) 또는 mapper_node (정확한 호출자 확인 필요)
  - 테스트: `test_db_mapped_history.py` (5 case), `test_db_mapped_history_helper.py` (4 case)
- **Suspected related** (2026-05-19):
  - forecaster — mapped_history 의 직접 소비
  - view_builder s_curve actual — mapped_history 누적

---

### `insert_forecast` — forecasts 28 컬럼 (wa 신규)

- **위치**: `pipeline/db.py:260-330` (71 LOC)
- **시그니처**: `async def insert_forecast(row: dict) -> None`
- **이슈**:
  - 27 → 28 컬럼 (wa 추가, migration: `2026-05-18_forecasts_wa.sql`)
  - JSONB: today_qty_by_unit / plan_total_qty_by_unit / similar_cases
- **설계 의도**:
  - Forecaster 산출 적재 — Reports + Dashboard fleet KPI source
  - row 단위 INSERT (forecaster 가 27 row 정도 — 그룹별)
- **대응 패턴**:
  - 입력: 28-key dict (run_id, company, l6_main, today/plan/window/MH gap/RAG/평가/완료/main_unit/today_conditions/wa)
  - 처리: _json.dumps + INSERT
  - 출력: None
- **관련**:
  - 호출자: graph.py `forecaster_node` (graph.py:299)
  - 테스트: `test_db_forecasts_wa.py` (2 case)
- **Suspected related**:
  - forecaster/agent.py — row dict 생성 source

---

### `insert_optimizer_advice` — JSONB 4종 + falsy 회피

- **위치**: `pipeline/db.py:332-368` (37 LOC)
- **시그니처**: `async def insert_optimizer_advice(row: dict) -> None`
- **이슈**:
  - 9 컬럼 (run_id, company, l6_main, forecast_assessment, diagnosis, degradation_cases JSONB, recovery_pattern JSONB, recovery_distribution JSONB, recommendations JSONB)
- **설계 의도**:
  - Optimizer LLM 출력 영속화 — Reports BFF 의 optimizer_view source
  - JSONB falsy 회피 ({} vs None 명확)
- **관련**:
  - 호출자: agent.py `optimize` (~50)
- **Suspected related**:
  - view_builder `_build_optimizer_view` — 본 컬럼들의 BFF transform

---

### `fetch_plan_for_group` — 2 SQL 분리 (jsonb_object_agg duplicate key 회피)

- **위치**: `pipeline/db.py:194-236` (43 LOC)
- **시그니처**: `async def fetch_plan_for_group(company, l6_main, site_id=None) -> dict`
- **이슈**:
  - 주석 (db.py:202): "Spec 3.2 — 2 SQL 분리로 jsonb_object_agg duplicate key 회피"
  - site_id 지정 시 필터, None 이면 전 현장 (back-compat)
- **설계 의도**:
  - Mapper 매핑 시 Plan 값 조회 (qty_by_unit + mh_sum + start/finish)
  - jsonb_object_agg 가 같은 unit 키 충돌 발생 → SUM(qty) GROUP BY unit 분리
- **대응 패턴**:
  - 입력: company, l6_main, site_id
  - 처리: 2 SQL — qty_by_unit + summary
  - 출력: `{plan_total_qty_by_unit, plan_mh_sum, plan_start, plan_finish}`
- **관련**:
  - 호출자: forecaster — plan 정보 fetch
  - 테스트: `test_db.py::test_fetch_plan_for_group_real`
- **Suspected related**:
  - `fetch_bp_candidates` — mapper rerank 와 페어

---

### `fetch_bp_candidates` — Mapper BP filter (site_id)

- **위치**: `pipeline/db.py:38-71` (34 LOC)
- **시그니처**: `async def fetch_bp_candidates(company, site_id=None) -> list[dict]`
- **이슈**:
  - 정확 일치 SQL — graph.py:67~68 의 일괄 정규화 (e163e1a) 와 협력 필수
  - site_id 옵션 (back-compat)
- **설계 의도**:
  - Mapper 매핑 시 회사별 (WA, L6) 후보 풀 — Chroma rerank input
  - PG activity_master 의 정규화된 company 값과 매칭
- **대응 패턴**:
  - 입력: company (정규화 후), site_id
  - 처리: SELECT wa, l6_main FROM activity_master WHERE company=$1 [AND site_id=$2]
  - 출력: list[dict]
- **관련**:
  - 호출자: graph.py:74~79 — unique_companies batch fetch
- **Suspected related** (정규화 타이밍):
  - graph.py:67~68 — fetch_bp_candidates 전 일괄 정규화 (e163e1a fix)
  - parser_post.py `normalize_company`

---

### `update_site_last_run` / `update_site_hours_saved_cum` — G8 / G2 KPI

- **위치**: `pipeline/db.py:1081` (`update_site_last_run`, 16 LOC) + `db.py:1097` (`update_site_hours_saved_cum`, 17 LOC)
- **시그니처**:
  - `async def update_site_last_run(pg, site_id, run_id) -> None`
  - `async def update_site_hours_saved_cum(pg, site_id, atomized_count) -> None`
- **이슈**:
  - migration: `2026-05-19_sites_hours_saved_cum.sql` (NUMERIC DEFAULT 0)
  - G2 산식: AS_IS (수작업) - TO_BE (AI 검토) = (120-5)/60 × atomized_count 시간 (commit msg)
  - module-level (PGClient 외) — graph.py 가 직접 호출
- **설계 의도**:
  - Dashboard Layer 1 의 G8 (마지막 run_id 트레이스) + G2 (누적 절감 시간) 적재
  - reporter_node 끝에서 호출 — full cycle 의 finalization
- **대응 패턴**:
  - 입력: pg, site_id, run_id / atomized_count
  - 처리: 1 UPDATE
  - 출력: None
- **관련**:
  - 호출자: graph.py `reporter_node` (graph.py:451~471)
  - 테스트: `test_db_update_site_last_run.py`, `test_db_hours_saved_cum.py`
- **Suspected related**:
  - reporter_node — site_id PG fallback 과 함께 호출
  - dashboard/performance endpoint — hours_saved_cum source

---

### `insert_parser_*_batch` × 5 (시트2/3/6/Cover/시트4)

- **위치**: db.py:540 (activities) / 743 (job_allocations) / 815 (equipment) / 881 (worker_outputs) / 952 (report_meta)
- **시그니처**: `async def insert_parser_*_batch(run_id, report_date, rows: list[dict], ...) -> None`
- **이슈**:
  - migration: `2026-05-19_parser_full_schema.sql` (141 LOC) — 5 parser 테이블 통합
  - 본 cycle 의 G24 적재 보완 (drift #2 해소) — parser_job_allocations / parser_equipment_allocations 가 항상 0 row 였던 버그 fix
- **설계 의도**:
  - parser 정규화 결과 영속 — BFF `consolidated` route 가 직접 SELECT
  - 시트별 분리 (시트2 job / 시트3 equipment / 시트4 activity / 시트6 worker / Cover meta)
- **대응 패턴**:
  - 입력: rows list (시트별 14~23 컬럼)
  - 처리: executemany
  - 출력: None
- **관련**:
  - 호출자: graph.py `mapper_node` (graph.py:121~127) — G24 호출 추가
  - BFF 소비: `/api/mock/consolidated` route
- **Suspected related** (2026-05-19):
  - mapper_node — 본 함수들의 직접 호출

---

### `_LazyAsyncPostgresSaver` / `build_checkpointer`

- **위치**: `pipeline/checkpointer.py:78` (build) + class (lazy wrapper)
- **시그니처**: `def build_checkpointer() -> CheckpointerBase`
- **이슈**:
  - 주석 (checkpointer.py:13): "AsyncConnectionPool 은 sync __init__ 안에서 await pool.open() 호출 불가" — lazy 처리
  - env `CPIA_CHECKPOINTER` ∈ {memory, postgres}
- **설계 의도**:
  - InMemorySaver — unit test path (cfg=None 안전)
  - AsyncPostgresSaver — production path (LangGraph thread_id 영속)
  - lazy open — graph.ainvoke async context 에서 await pool.open() 호출
- **대응 패턴**:
  - 입력: env (CPIA_CHECKPOINTER)
  - 처리: 분기 (memory or postgres) — postgres 면 _LazyAsyncPostgresSaver wrap
  - 출력: CheckpointerBase 호환 객체
- **관련**:
  - 호출자: graph.py `build_graph` (graph.py:514)
  - 테스트: `test_checkpointer.py`
- **Suspected related**:
  - graph.py `build_graph` / `build_demo_graph` — 본 함수 결과를 .compile(checkpointer=) 에 전달

---

### Chroma `get_or_create_wbs_master` / `get_or_create_daily_activities`

- **위치**: `pipeline/chroma_client.py:23` (wbs_master), `chroma_client.py:30` (daily_activities)
- **시그니처**: `def get_or_create_*() -> Collection`
- **이슈**:
  - 35 LOC 작은 wrapper — chromadb-client HTTP 진입점
  - metadata: `{"hnsw:space": "cosine"}` (cosine distance)
- **설계 의도**:
  - 2 컬렉션 분리:
    - **wbs_master** (~189 doc) — 1 doc = 1 (WA, L6) 그룹, Mapper RAG
    - **daily_activities** — 1 doc = 1 Activity, Atomizer INSERT, Forecaster + Optimizer retrieve
  - 동일 endpoint, 다른 collection name → 검색 의도 분리
- **대응 패턴**:
  - 입력: 없음 (HTTP client 내부)
  - 처리: collection get_or_create
  - 출력: chromadb Collection
- **관련**:
  - 호출자:
    - wbs_master: mapper `map_activity` step 3
    - daily_activities: atomizer_node + hil_2_node + forecaster
- **Suspected related**:
  - mapper.py `_select_top_k_alternatives` — wbs_master 의 top-K
  - retrieve.py `fetch_degradation_cases` / `fetch_recovery_trajectory` — daily_activities retrieve

---

## FastAPI 12 엔드포인트 — Issue Cards (간략)

### POST `/api/runs/{run_id}/hil_1/resume` (api.py:200)

- 입력: `{corrections: {idx: {wa, l6_main}, ...}}`
- 출력: `{next_node}` (다음 노드)
- 처리: graph.ainvoke 재개 (Command(resume=corrections))
- 관련: graph.py `hil_1_node` (graph.py:224)

### GET `/api/sites` (api.py:314)

- 입력: 없음
- 출력: `Site[]` (id, name, kpi, status)
- 처리: 1 SELECT (sites + forecasts LATERAL)
- 미해결: 6 site fixture 규모, 확장 시 성능 검토 (issue #N10)

### GET `/api/runs/{run_id}/optimizer` (api.py:378)

- 입력: run_id
- 출력: `OptimizerOutput[]` (advice rows + view jsonb)
- 처리: 1 SELECT daily_reports.optimizer_view_jsonb
- 관련: optimizer agent.py view_builder

### GET `/api/dashboard/performance` (api.py:560)

- 출력: `{fleet_kpi}` (전 site 통합 KPI)
- 처리: 1 SELECT (CTE + agg)
- 관련: sites.hours_saved_cum, forecasts.assessment

### GET `/api/dashboard/impact` (api.py:620) / `/api/agents/status` (api.py:706) / `/api/sites/{id}/wbs_tree` (api.py:809) / `/api/tasks` (api.py:1022)

- 미해결:
  - `/api/agents/status`: 7× SELECT COUNT — N+1 가능성 (현재 7 agent 고정)
  - `/api/tasks`: itemsByDate "Collector" key hardcode (current_node 기반 라우팅 미구현, issue #N9)

---

## 데이터 모델 — PG 17 테이블 + 신규 컬럼

상세는 `../architecture_overview.md` §3.1 참조. 본 cycle 신규/변경 컬럼:

| 테이블 | 컬럼 | Type | Migration |
|---|---|---|---|
| activity_master | wa | TEXT | 2026-05-17_activity_master_wa |
| activity_master | site_id | TEXT | 2026-05-17_activity_master_site_id |
| forecasts | wa | TEXT | 2026-05-18_forecasts_wa |
| daily_reports | site_id | TEXT (partial unique idx) | 2026-05-19_daily_reports_views |
| daily_reports | kpi_jsonb / contractor_bars_jsonb / trade_bars_jsonb / quadrant_jsonb / wp_summary_jsonb / s_curve_jsonb / optimizer_view_jsonb / productivity_jsonb | JSONB | 2026-05-19_daily_reports_views |
| daily_reports | scenarios_jsonb | JSONB | 2026-05-19_scenarios_jsonb |
| mapper_activities | alternatives (jsonb + GIN) | JSONB | 2026-05-19_mapper_alternatives |
| mapper_activities | cum_workers_today / cum_actual_mh_today | DOUBLE | 2026-05-19_daily_reports_views |
| mapped_history | trade | TEXT | 2026-05-19_mapped_history_trade |
| sites | location / headcount / hours_saved / fte_saved | mixed | 2026-05-17_db_alignment |
| sites | hours_saved_cum | NUMERIC | 2026-05-19_sites_hours_saved_cum |

---

## 변경 사항 정리 (cf3c143..HEAD, persistence 관련)

| Commit | 변경 |
|---|---|
| ef7c6cd | fix(db): daily_reports site_id + upsert UPDATE-first + scenarios_jsonb whitelist |
| b5404a4 | feat(db): upsert_daily_report_view_col — partial write per jsonb column (B.8) |
| 4cd36e3 | feat(mapper): U1.B cum_workers prorate (plan_mh 비율) + uniform fallback |
| (api.py 12 endpoint 구현은 다수 commit 누적) | |

## 미해결 / Backlog

- `fetch_activity` (db.py:73) 미사용 의심 — test 만 호출, mapper rerank 통합 검토 필요 (issue #N3)
- `infra/postgres/migrations` vs `docs/schema/postgres.md` 정합 자동화 (issue #N2)
- `/api/agents/status` 7× SELECT COUNT — agent 추가 시 N+1
- `/api/tasks` itemsByDate "Collector" key hardcode (issue #N9)
- `/api/sites` LATERAL forecasts — 확장 시 EXPLAIN ANALYZE 검토 (issue #N10)
- Chroma env homelab 미준비 — 본 cycle 잠시 dev 로컬 fallback (api-contract.md §1)
