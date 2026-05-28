# Design Intent — persistence (PostgreSQL + ChromaDB + FastAPI + Exporter)

- **Generated**: 2026-05-26 (cycle: `ef7c6cd` → `1ba783f`, baseline 2026-05-20)
- **Pair file**: `../deep_dive_persistence.md` (655 LOC, source of truth)
- **Range**:
  - `pipeline/db.py` (1229 LOC, 이전 1113 → +116)
  - `pipeline/api.py` (1073 LOC, 이전 1050 → +23)
  - `pipeline/chroma_client.py` (35 LOC, 무변경)
  - `pipeline/checkpointer.py` (94 LOC, 무변경)
  - `pipeline/exporter_routes.py` (47 LOC, **NEW**)
  - `infra/postgres/migrations/` (21 SQL 파일, +5 신규)
  - `pipeline/tests/test_db*.py` (10+ 파일) + `test_api_*.py` (5 파일) + `test_collector_inbox.py`
- **스펙**:
  - `docs/superpowers/specs/2026-05-17-cpia-db-migration-api-contract-design.md`
  - `docs/architecture/api-contract.md`
  - `docs/schema/postgres.md`

asyncpg pool 래퍼 + ChromaDB HTTP 클라이언트 + **FastAPI 12 endpoint + Exporter router (`/export/run`)**. 본 cycle 의 큰 줄기 4가지:
1. `collector_inbox` 테이블 + 4 helper 신규 (Gmail IMAP IDLE worker dedup, commit `7b96b1a`)
2. `/export/run` xlsx endpoint + lifespan exporter router include (commit `a7e2465` + `4b8a955`)
3. `mapper_activities` 에 L7.5 / L5 propagate 4 컬럼 추가 (commit `d40c84f`, 회귀 6건 해소)
4. `is_mock` 컬럼 7 테이블 backfill + B_Track Export/Reports/Review list/detail 분할 (FE N+1 제거 — BE schema 무변경)

---

## T1 — Function Index

### db.py (1229 LOC) — PGClient 28 메서드 + 모듈 함수 7

#### PGClient 조회 (SELECT) — 7개

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `connect` / `close` | db.py:24/32 | `async () -> None` | 커넥션 풀 라이프사이클 | — |
| `fetch_bp_candidates` | db.py:38 | `async (company, site_id=None) -> list[dict]` | 공종 (WA, L6) 후보 풀 (Mapper BP filter) | ✅ |
| `fetch_activity` | db.py:73 | `async (wbs_activity_id, site_id=None) -> dict\|None` | ActivityID → Plan 값 + 메타 (dead code 의심) | ✅ |
| `fetch_l6_plan_mh_map` | db.py:106 | `async (company, l6_list, site_id=None) -> dict` | (l6_main → plan_mh) dict (N+1 회피) | ✅ |
| `fetch_plan_for_group` | db.py:194 | `async (company, l6_main, site_id=None) -> dict` | (company, l6_main) plan 합계 (2 SQL 분리) | ✅ |
| `get_pipeline_run` | db.py:504 | `async (run_id) -> dict\|None` | pipeline_runs 1 row | — |
| `fetch_one` / `fetch_all` | db.py:1028/1039 | `async (sql, *args) -> dict\|list[dict]` | 임의 SELECT helper | — |

#### PGClient INSERT (단일/배치) — 13개

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `insert_pipeline_run` | db.py:147 | `async (run_id, site_id, date, status='running')` | pipeline_runs 단일 INSERT | ✅ |
| `assert_pipeline_run_exists` | db.py:176 | `async (run_id) -> None` | row 미존재 시 RuntimeError | — |
| `delete_pipeline_run` | db.py:170 | `async (run_id) -> None` | test fixture cleanup용 | — |
| `update_run_atomized_count` | db.py:238 | `async (run_id, count)` | atomizer 적재 후 카운트 갱신 | — |
| `insert_forecast` | db.py:260 | `async (row: dict) -> None` | forecasts 단일 INSERT (28 컬럼 + wa) | ✅ |
| `insert_optimizer_advice` | db.py:332 | `async (row: dict) -> None` | optimizer_advice INSERT (9 컬럼 + JSONB 4종) | ✅ |
| `insert_mapping_correction` | db.py:370 | `async (run_id, report_date, original, corrected) -> None` | mapping_corrections INSERT | ✅ |
| `insert_daily_report` | db.py:405 | `async (run_id, report_date, report_md, history_csv_row, bp_name=None, site_id=None) -> None` | daily_reports UPDATE-first → INSERT | ✅ |
| `insert_mapped_history_batch` | db.py:458 | `async (run_id, report_date, site_id, rows) -> None` | mapped_history batch (ON CONFLICT UPDATE — **trade 누락**, C3) | ✅ |
| `insert_parser_report` | db.py:515 | `async (run_id, report_date, project, bp_summaries, job_allocations, equipment_allocations, activity_count) -> None` | parser_reports 1 row (ON CONFLICT DO UPDATE) | ✅ |
| `insert_parser_activities_batch` | db.py:558 | `async (run_id, report_date, activities) -> None` | parser_activities batch (23 컬럼) | ✅ |
| `insert_mapper_activities_batch` | db.py:639 | `async (run_id, report_date, activities) -> None` | mapper_activities batch (**37 컬럼 — L7.5 4 컬럼 추가**) | ✅ |
| `insert_parser_job_allocations_batch` | db.py:771 | `async (run_id, report_date, rows) -> None` | parser_job_allocations (시트2, 3 group JSONB) | ✅ |
| `insert_parser_equipment_allocations_batch` | db.py:843 | `async (run_id, report_date, rows) -> None` | parser_equipment_allocations (시트3) | ✅ |
| `insert_parser_worker_outputs_batch` | db.py:909 | `async (run_id, report_date, rows, bp_name=None) -> None` | parser_worker_outputs (시트6, 업체별) | ✅ |
| `insert_parser_report_meta_batch` | db.py:980 | `async (run_id, report_date, metas) -> None` | parser_report_meta (Cover, 업체별) | ✅ |

#### PGClient UPDATE — 1개

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `upsert_daily_report_view_col` | db.py:1062 | `async (run_id, site_id, report_date, col, value) -> None` | **daily_reports JSONB 부분 UPSERT (UPDATE-first + 9 col 화이트리스트)** | ✅ |

#### 모듈 함수 — 7개

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `update_site_last_run` | db.py:1109 | `async (pg, site_id, run_id) -> None` | G8 — sites.last_run_id 갱신 | ✅ |
| `update_site_hours_saved_cum` | db.py:1125 | `async (pg, site_id, atomized_count) -> None` | G2 — sites.hours_saved_cum 누적 ((120-5)/60 × N h) | ✅ |
| `insert_collector_inbox` | db.py:1149 | `async (pg, *, message_id, site_id, report_date, bp_name, attachment_filename, attachment_path) -> None` | **★ NEW** — IMAP IDLE 신규 메일 INSERT (ON CONFLICT DO NOTHING) | ✅ |
| `update_collector_inbox_status` | db.py:1179 | `async (pg, message_id, *, run_id=None, parse_status, error=None) -> None` | **★ NEW** — parse_status / run_id / error 갱신 (`run_id = COALESCE($3, run_id)`) | ✅ |
| `fetch_collector_inbox_by_message_id` | db.py:1206 | `async (pg, message_id) -> dict\|None` | **★ NEW** — dedup 체크 | ✅ |
| `fetch_site_by_id` | db.py:1220 | `async (pg, site_id) -> dict\|None` | **★ NEW** — `/export/run` 가 site name 조회용 | ✅ |

### chroma_client.py (35 LOC) — ChromaClient (무변경)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `get_or_create_wbs_master` | chroma_client.py:23 | `() -> Collection` | wbs_master 조회/생성 (Mapper RAG) | ✅ |
| `get_or_create_daily_activities` | chroma_client.py:30 | `() -> Collection` | daily_activities 조회/생성 (Forecaster + Optimizer retrieve) | ✅ |

### checkpointer.py (94 LOC) (무변경)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_LazyAsyncPostgresSaver` | checkpointer.py:30 | `class` | sync __init__ 안에서 await pool.open() 호출 불가 → lazy init | ✅ |
| `build_checkpointer` | checkpointer.py:78 | `() -> CheckpointerBase` | env `CPIA_CHECKPOINTER` 기반 InMemorySaver ↔ AsyncPostgresSaver 선택 (M6 silent fallback 위험) | ✅ |

### exporter_routes.py (47 LOC, **NEW** — commit `a7e2465`)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `router` | exporter_routes.py:13 | `APIRouter(prefix="/export")` | FastAPI sub-router (main app 가 lifespan 외 include) | — |
| `export_consolidated` | exporter_routes.py:16 | `async (site_id: str, date: str) -> Response` | **★ NEW** — `/export/run` xlsx endpoint (site 조회 → fetch_sheet_data → render_xlsx → bytes) | ✅ |

### api.py (1073 LOC) — FastAPI 12 endpoint + lifespan + exporter router include

| # | Method | Path | Line | Output | DB Calls |
|---|---|---|---|---|---|
| 1 | GET | `/health` | api.py:211 | `{status, pg, version}` | 1 SELECT |
| 2 | POST | `/api/runs/{run_id}/hil_1/resume` | api.py:223 | `{next_node}` | graph.ainvoke (Mapper resume) |
| 3 | GET | `/api/sites` | api.py:337 | `Site[]` | 1 SELECT (sites + forecasts LATERAL) |
| 4 | GET | `/api/runs/{run_id}/optimizer` | api.py:401 | `OptimizerOutput[]` | 1 SELECT |
| 5 | GET | `/api/runs/{run_id}/wp_summary` | api.py:481 | `WPSummaryRow[]` | 1 SELECT (3 join) |
| 6 | GET | `/api/sites/{site_id}/reports` | api.py:542 | `ReportDaily[]` | 1 SELECT (days 필터) |
| 7 | GET | `/api/dashboard/performance` | api.py:583 | `{fleet_kpi}` | 1 SELECT (CTE + agg) |
| 8 | GET | `/api/dashboard/impact` | api.py:643 | `ImpactSiteDistribution[]` | 1 SELECT |
| 9 | GET | `/api/agents/status` | api.py:729 | `AgentStatus[]` | **7× SELECT COUNT (M1 N+1)** |
| 10 | GET | `/api/sites/{site_id}/wbs_tree` | api.py:832 | `WBSNode (tree)` | 1 SELECT |
| 11 | GET | `/api/tasks` | api.py:1045 | `{tasks, progressByDate, itemsByDate}` | 2 SELECT |
| 12 | GET | `/export/run` | exporter_routes.py:16 | `Response (xlsx bytes)` | fetch_site_by_id + fetch_sheet_data (4 SQL) |

### api.py lifespan + 모듈 레벨 wiring (★ NEW 본 cycle)

| Function | File:Line | One-line role |
|---|---|---|
| `lifespan` | api.py:147 | PG pool open → graph compile → **collector idle task spawn (★ NEW `4b8a955`)** → yield → 역순 shutdown |
| `app.include_router(exporter_router)` | api.py:203 | **★ NEW (`4b8a955`)** — main app 에 `/export` prefix 결합 |

### pipeline/agents/exporter.py — public function (참조용, 본 cycle 신규)

| Function | File:Line | One-line role | T2? |
|---|---|---|---|
| `fetch_sheet_data` | agents/exporter.py:34 | **★ NEW (`b3010df`)** — `pipeline_runs JOIN parser_reports` + `parser_activities` 4 SQL 합집합 (시트1~4) | ✅ |
| `render_xlsx` | agents/exporter.py:290 | xlsx 4 시트 렌더링 (`SheetData → bytes`) | — |

---

## T2 — Issue Cards (Tier-1 핵심)

### `insert_mapper_activities_batch` — Mapper 최종 출력 (37 컬럼) ★ 본 cycle 변경

- **위치**: `pipeline/db.py:639-769` (≈130 LOC)
- **시그니처**: `async def insert_mapper_activities_batch(run_id, report_date, activities: list[dict]) -> None`
- **본 cycle 변경 (commit `d40c84f`)**:
  - **33 → 37 컬럼**: `l5_disc` / `l7_sub` / `l7_5_activity` / `sub_work_area` 4 컬럼 추가
  - migration: `2026-05-23_mapper_l7_5_columns.sql`
  - 의도: `activity_master` 의 L5/L7/L7.5 메타를 mapper 출력으로 propagate — spec §8/§9 plan 누락 fix, 회귀 6건 해소
  - ON CONFLICT DO UPDATE 절도 37 컬럼 전체 갱신
- **베이스라인 이슈** (유지):
  - 멱등성 키 `(run_id, idx)` PK + ON CONFLICT DO UPDATE 전 컬럼
  - alternatives jsonb (GIN) — FE review modal dropdown 옵션
  - cum_workers_today / cum_actual_mh_today — U1.B prorate 결과
- **설계 의도**:
  - 1 cycle 안의 모든 mapper 산출 batch 적재 (POC 146 row 규모)
  - L7.5 / L5 컬럼 추가는 mapper 가 BP사 일보 → activity_master 매칭 시 메타까지 영속화 → exporter / FE 가 별도 JOIN 없이 사용
- **대응 패턴**:
  - 입력: rows list (37 키)
  - 처리: executemany 1 query
  - 출력: None (side effect = PG INSERT)
- **관련**:
  - 호출자: `pipeline/graph.py:149` `mapper_node`
  - 테스트: `test_mapper_golden.py`, `test_mapper_alternatives.py`, `test_mapper_weighted_mh.py`, `test_db_new_columns_insert.py`
- **Suspected related**:
  - mapper.py `_select_top_k_alternatives` — alternatives jsonb 입력
  - mapper.py `_prorate_workers_with_mh` — cum_workers / cum_actual_mh_today 입력
  - mapper.py L7.5 propagate 로직 — 신규 4 컬럼 입력

---

### `upsert_daily_report_view_col` — UPDATE-first partial write 가드

- **위치**: `pipeline/db.py:1062-1106` (45 LOC)
- **시그니처**: `async def upsert_daily_report_view_col(run_id, site_id, report_date, col: str, value) -> None`
- **본 cycle 변경**: 무변경 (베이스라인 `ef7c6cd` 유지). 단 `site_summary_text` TEXT 컬럼이 새로 들어왔으나 화이트리스트 미포함 — M4 참조.
- **이슈** (베이스라인):
  - git log: `b5404a4 feat(db): upsert_daily_report_view_col — partial write per jsonb column (B.8)`
  - git log: `ef7c6cd fix(db): daily_reports site_id + upsert UPDATE-first + scenarios_jsonb whitelist`
  - 주석 (db.py:1052~1054): "UPDATE 우선 — partial unique index `(run_id, site_id, report_date) WHERE site_id IS NOT NULL` 가 ON CONFLICT 와 안정 매칭 안 됨"
- **설계 의도**:
  - Reporter cycle 안에서 JSONB 컬럼 9종을 1개씩 부분 업데이트 — 한 컬럼 fail 해도 다른 컬럼은 유지 (atomicity weak, 의도)
  - UPDATE-first → 신규일 때만 INSERT (대부분 reporter 가 사전 INSERT 보장)
  - **SQL injection 방어**: col 파라미터 9개 화이트리스트 체크 후 f-string 사용
  - **화이트리스트** (`_VIEW_JSONB_COLS`, db.py:1050):
    ```
    kpi_jsonb / contractor_bars_jsonb / trade_bars_jsonb / quadrant_jsonb
    wp_summary_jsonb / s_curve_jsonb / optimizer_view_jsonb
    productivity_jsonb / scenarios_jsonb
    ```
- **관련**:
  - 호출자: `pipeline/agents/optimizer/agent.py:220` — 9 col 각각 1 회 호출
  - 테스트: `test_db_daily_reports.py`
- **Suspected related**:
  - optimizer view_builder.py 의 9 build 함수 — 본 함수의 input 산출
  - `site_summary_text` TEXT 컬럼 — 별도 UPDATE 경로 (M4, `scripts/backfill_daily_report_views_v2.py:162`)

---

### `insert_mapped_history_batch` — 멱등 UPDATE atomizer 입력 ★ 이슈 C3

- **위치**: `pipeline/db.py:458-503` (≈45 LOC)
- **시그니처**: `async def insert_mapped_history_batch(run_id, report_date, site_id, rows: list[dict]) -> None`
- **본 cycle 변경**: 무변경. 단 deep_dive 가 **Critical C3** 신규 식별 — ON CONFLICT DO UPDATE SET 절이 `today_qty / today_assigned_workers / unit` 만 갱신, **`trade` 누락**. 같은 (run_id, wa, l6_main, company) 재호출 시 trade 가 최초값 고정 → 후속 cycle trade 보정 불가.
- **이슈** (베이스라인):
  - migration: `2026-05-18_mapped_history.sql` + `2026-05-19_mapped_history_trade.sql`
  - 멱등성 키 `(run_id, wa, l6_main, company)`
  - 주석 (db.py:447): "INSERT 대상 = wa + l6_main 둘 다 not None 인 활동 (Phase 3 결정)"
- **설계 의도**:
  - 현장별 당일 실적 누적 — forecaster RAG 입력 + s_curve actual
  - 같은 (wa, l6_main, company) 재호출 시 today_qty / today_assigned_workers / unit 마지막 값 채택
- **관련**:
  - 호출자: `pipeline/agents/atomizer.py:190`
  - 테스트: `test_db_mapped_history.py` (5 case), `test_db_mapped_history_helper.py` (4 case)
- **Suspected related**:
  - forecaster — mapped_history 의 직접 소비
  - view_builder s_curve actual — mapped_history 누적
  - C3 fix 후보: SET 절에 `trade = EXCLUDED.trade` 추가 — 회귀 테스트 필수

---

### `insert_forecast` — forecasts 28 컬럼 (wa 포함)

- **위치**: `pipeline/db.py:260-330` (71 LOC)
- **시그니처**: `async def insert_forecast(row: dict) -> None`
- **본 cycle 변경**: 무변경.
- **이슈** (베이스라인):
  - 27 → 28 컬럼 (wa 추가, migration: `2026-05-18_forecasts_wa.sql`)
  - JSONB: today_qty_by_unit / plan_total_qty_by_unit / similar_cases
- **설계 의도**:
  - Forecaster 산출 적재 — Reports + Dashboard fleet KPI source
  - row 단위 INSERT (그룹별)
- **관련**:
  - 호출자: `pipeline/agents/forecaster/agent.py:331`
  - 테스트: `test_db_forecasts_wa.py` (2 case)

---

### `insert_optimizer_advice` — JSONB 4종 + falsy 회피

- **위치**: `pipeline/db.py:332-368` (37 LOC)
- **시그니처**: `async def insert_optimizer_advice(row: dict) -> None`
- **본 cycle 변경**: 무변경.
- **이슈** (베이스라인):
  - 9 컬럼 (run_id, company, l6_main, forecast_assessment, diagnosis, degradation_cases JSONB, recovery_pattern JSONB, recovery_distribution JSONB, recommendations JSONB)
- **설계 의도**:
  - Optimizer LLM 출력 영속화 — Reports BFF 의 optimizer_view source
  - JSONB falsy 회피 ({} vs None 명확)
- **관련**:
  - 호출자: `pipeline/agents/optimizer/agent.py:182`
- **Suspected related**:
  - view_builder `_build_optimizer_view` — 본 컬럼들의 BFF transform

---

### `fetch_plan_for_group` — 2 SQL 분리 (jsonb_object_agg duplicate key 회피)

- **위치**: `pipeline/db.py:194-236` (43 LOC)
- **시그니처**: `async def fetch_plan_for_group(company, l6_main, site_id=None) -> dict`
- **본 cycle 변경**: 무변경.
- **이슈** (베이스라인):
  - 주석 (db.py:202): "Spec 3.2 — 2 SQL 분리로 jsonb_object_agg duplicate key 회피"
  - site_id 지정 시 필터, None 이면 전 현장 (back-compat)
- **설계 의도**:
  - Mapper 매핑 시 Plan 값 조회 (qty_by_unit + mh_sum + start/finish)
  - jsonb_object_agg 가 같은 unit 키 충돌 발생 → SUM(qty) GROUP BY unit 분리
- **관련**:
  - 호출자: forecaster
  - 테스트: `test_db.py::test_fetch_plan_for_group_real`

---

### `fetch_bp_candidates` — Mapper BP filter (site_id)

- **위치**: `pipeline/db.py:38-71` (34 LOC)
- **시그니처**: `async def fetch_bp_candidates(company, site_id=None) -> list[dict]`
- **본 cycle 변경**: 무변경.
- **이슈** (베이스라인):
  - 정확 일치 SQL — graph.py 의 일괄 정규화 (e163e1a) 와 협력
  - site_id 옵션 (back-compat)
- **설계 의도**:
  - Mapper 매핑 시 회사별 (WA, L6) 후보 풀 — Chroma rerank input
  - PG activity_master 의 정규화된 company 값과 매칭
- **관련**:
  - 호출자: `pipeline/graph.py:79` mapper

---

### `fetch_activity` — dead code 의심 (M3)

- **위치**: `pipeline/db.py:73-104`
- **시그니처**: `async def fetch_activity(wbs_activity_id, site_id=None) -> dict | None`
- **본 cycle 변경**: 무변경. deep_dive M3 — `grep` 결과 prod 호출자 0건 (테스트만).
- **설계 의도**:
  - 원안: ActivityID 단건 조회 → Mapper rerank 단계 통합
  - 현실: mapper 가 `fetch_bp_candidates` + `fetch_l6_plan_mh_map` 로 우회 — 본 함수 미진입
- **결정 필요**: 삭제 vs mapper 통합 (issue #N3)

---

### `update_site_last_run` / `update_site_hours_saved_cum` — G8 / G2 KPI

- **위치**: `pipeline/db.py:1109` (`update_site_last_run`, 16 LOC) + `db.py:1125` (`update_site_hours_saved_cum`, 24 LOC)
- **시그니처**:
  - `async def update_site_last_run(pg, site_id, run_id) -> None`
  - `async def update_site_hours_saved_cum(pg, site_id, atomized_count) -> None`
- **본 cycle 변경**: 무변경.
- **이슈** (베이스라인):
  - migration: `2026-05-19_sites_hours_saved_cum.sql` (NUMERIC DEFAULT 0)
  - G2 산식 상수: `AS_IS_MIN = 120` (db.py:1121), `TO_BE_MIN = 5` (db.py:1122) → `(120-5)/60 × atomized_count h`
  - module-level (PGClient 외) — graph.py 가 직접 호출
- **설계 의도**:
  - Dashboard Layer 1 의 G8 (마지막 run_id 트레이스) + G2 (누적 절감 시간) 적재
  - reporter_node 끝에서 호출 — full cycle 의 finalization
- **관련**:
  - 호출자: `pipeline/graph.py:473~474` `reporter_node → END` edge
  - 테스트: `test_db_update_site_last_run.py`, `test_db_hours_saved_cum.py`

---

### `insert_parser_*_batch` × 5 (시트2/3/6/Cover/시트4)

- **위치**: db.py:558 (activities) / 771 (job_allocations) / 843 (equipment) / 909 (worker_outputs) / 980 (report_meta)
- **시그니처**: `async def insert_parser_*_batch(run_id, report_date, rows: list[dict], ...) -> None`
- **본 cycle 변경**: 무변경.
- **이슈** (베이스라인):
  - migration: `2026-05-19_parser_full_schema.sql` (141 LOC) — 5 parser 테이블 통합
  - parser_job_allocations / parser_equipment_allocations 가 항상 0 row 였던 버그 fix (G24 적재 보완)
- **설계 의도**:
  - parser 정규화 결과 영속 — BFF `consolidated` route + `/export/run` 직접 소비
  - 시트별 분리 (시트2 job / 시트3 equipment / 시트4 activity / 시트6 worker / Cover meta)
- **관련**:
  - 호출자: `pipeline/graph.py:110~136` mapper_node + merge 노드
  - BFF 소비: `/api/mock/consolidated` + `exporter_routes.py:/export/run` (★ 본 cycle 신규 소비처)

---

### `_LazyAsyncPostgresSaver` / `build_checkpointer`

- **위치**: `pipeline/checkpointer.py:30` (class) + `checkpointer.py:78` (build)
- **시그니처**: `def build_checkpointer() -> CheckpointerBase`
- **본 cycle 변경**: 무변경. deep_dive 가 **M6** silent fallback 위험 신규 식별.
- **이슈** (베이스라인 + 신규):
  - 주석 (checkpointer.py:13): "AsyncConnectionPool 은 sync __init__ 안에서 await pool.open() 호출 불가" — lazy 처리
  - env `CPIA_CHECKPOINTER` ∈ {memory, postgres}
  - **M6**: `POSTGRES_URL` 미설정 시 `InMemorySaver()` silent fallback (checkpointer.py:90-92). lifespan 의 fail-fast 가 먼저 잡긴 하나, `build_checkpointer` 단독 호출 (test/외부 script) 시 H-i-L resume state 가 process restart 시 손실
- **설계 의도**:
  - InMemorySaver — unit test path (cfg=None 안전)
  - AsyncPostgresSaver — production path (LangGraph thread_id 영속)
  - lazy open — graph.ainvoke async context 에서 await pool.open() 호출
- **관련**:
  - 호출자: `pipeline/graph.py:514` `build_graph`
  - 테스트: `test_checkpointer.py`

---

### Chroma `get_or_create_wbs_master` / `get_or_create_daily_activities`

- **위치**: `pipeline/chroma_client.py:23` (wbs_master), `chroma_client.py:30` (daily_activities)
- **시그니처**: `def get_or_create_*() -> Collection`
- **본 cycle 변경**: 무변경.
- **이슈**:
  - 35 LOC 작은 wrapper — chromadb-client HTTP 진입점
  - metadata: `{"hnsw:space": "cosine"}` (cosine distance)
- **설계 의도**:
  - 2 컬렉션 분리:
    - **wbs_master** (~189 doc) — 1 doc = 1 (WA, L6) 그룹, Mapper RAG
    - **daily_activities** — 1 doc = 1 Activity, Atomizer INSERT, Forecaster + Optimizer retrieve
  - 동일 endpoint, 다른 collection name → 검색 의도 분리
- **관련**:
  - 호출자:
    - wbs_master: mapper `map_activity` step 3
    - daily_activities: atomizer_node + forecaster/retrieve + optimizer/retrieve

---

## T2 — Issue Cards (Tier-1 핵심) — ★ NEW 본 cycle 신규 카드 5종

### ★ NEW — `insert_collector_inbox` / `update_collector_inbox_status` / `fetch_collector_inbox_by_message_id` (collector_inbox 3 helper)

- **위치**: `pipeline/db.py:1149` (insert) + `db.py:1179` (update) + `db.py:1206` (fetch_by_message_id)
- **시그니처**:
  - `async def insert_collector_inbox(pg, *, message_id, site_id, report_date, bp_name, attachment_filename, attachment_path) -> None`
  - `async def update_collector_inbox_status(pg, message_id, *, run_id: uuid.UUID | None = None, parse_status: str, error: str | None = None) -> None`
  - `async def fetch_collector_inbox_by_message_id(pg, message_id) -> dict | None`
- **본 cycle 변경 (commit `7b96b1a`)**:
  - 신규 테이블 `collector_inbox` (migration `2026-05-19_collector_inbox.sql`) + 3 helper 신규
  - 테이블 10 컬럼 (`message_id` PK / `received_at` / `site_id` / `report_date` / `bp_name` / `attachment_filename` / `attachment_path` / `run_id` FK pipeline_runs ON DELETE SET NULL / `parse_status` CHECK / `error` / `updated_at`)
  - CHECK constraint: `parse_status IN ('pending','running','completed','failed','dead_letter')` default `pending`
  - Index: `collector_inbox_site_date_idx` (`site_id, report_date`), `collector_inbox_status_idx` PARTIAL `WHERE parse_status IN ('pending','running','failed')`
- **설계 의도**:
  - Gmail IMAP IDLE worker (`pipeline/collector/idle_worker.py`) 가 신규 메일 수신 시 dedup 후 적재
  - `message_id` (RFC822 Message-ID) PK + `ON CONFLICT (message_id) DO NOTHING` — IMAP IDLE 재연결 / 중복 push 시 race safety
  - `update_collector_inbox_status` 의 `run_id = COALESCE($3, run_id)` 패턴 — run 생성 전 status 만 갱신할 때 기존 run_id 보존
  - parse_status 상태 머신: `pending` → `running` → `completed` / `failed` / `dead_letter`
- **대응 패턴**:
  - 입력: message_id (PK), 메타 6 필드
  - 처리: 1 INSERT / 1 UPDATE / 1 SELECT
  - 출력: None / None / dict | None
- **관련**:
  - 호출자: `pipeline/collector/idle_worker.py:26~28` (IDLE loop) + `pipeline/agents/collector_node.py` (run 직전 status 갱신)
  - 테스트: `test_collector_inbox.py`
  - lifespan: `api.py:180~183` `load_collector_config(graph_cfg=cfg)` → `collector_cfg.enabled` 면 `asyncio.create_task(idle_loop(collector_cfg))`
- **Suspected related**:
  - `pipeline/collector/config.py` `load_collector_config` — env `COLLECTOR_ENABLED` + 자격증명 검증 (fail-fast)
  - `pipeline/agents/collector_node.py` — pipeline 진입 시 `update_collector_inbox_status(message_id, run_id=run_id, parse_status='running')`

---

### ★ NEW — `app.include_router(exporter_router)` + lifespan collector idle (commit `4b8a955`)

- **위치**: `pipeline/api.py:147` (lifespan) + `api.py:203` (include_router)
- **본 cycle 변경**:
  - lifespan 6~8 step (deep_dive §6):
    1. `pg_url = os.getenv("POSTGRES_URL")` — 미설정 시 RuntimeError (fail-fast)
    2. `pg = PGClient(pg_url); await pg.connect()` → `app.state.pg`
    3. `cfg = _build_prod_graph_config()`
    4. `graph = build_graph(cfg)` (build_checkpointer 내부 호출)
    5. `app.state.graph = graph`, `app.state.cfg = cfg`
    6. **★ NEW** `load_collector_config(graph_cfg=cfg)` → `collector_cfg.enabled` True 면 `asyncio.create_task(idle_loop(collector_cfg))` 백그라운드 spawn (Spec §10 fail-fast — try/except swallow 금지)
    7. yield
    8. shutdown: collector_task 가 있으면 `request_shutdown()` flag → cancel → await (CancelledError swallow) → `await pg.close()`
  - **★ NEW** `app.include_router(exporter_router)` (api.py:203) — `/export` prefix 의 router 가 main app 에 결합
- **설계 의도**:
  - lifespan 안에서 IMAP IDLE worker spawn — 서버 시작과 함께 메일 수신 시작, shutdown 시 graceful cancel
  - `COLLECTOR_ENABLED=false` (default) → task 없음 (PoC 시연 환경 보호)
  - `COLLECTOR_ENABLED=true` + 자격증명 누락 → `load_collector_config` 가 RuntimeError (fail-fast)
  - exporter router 분리 — `/export/run` xlsx download 가 기존 12 endpoint 와 prefix 격리
- **이슈**:
  - C2 (Critical) — `/export/run` 가 `app.state.pg` 재사용 안 하고 매 요청마다 신규 풀 생성. lifespan 의 `app.state.pg` 가 이미 있는데도 미사용 → fix 후보: `Depends(get_pg)` 주입
- **관련**:
  - 호출자: FastAPI runtime (uvicorn lifespan protocol)
  - 테스트: `test_api_lifespan_collector.py` (가정 — collector_task 생성 여부 검증)

---

### ★ NEW — `/export/run` endpoint (commit `a7e2465`)

- **위치**: `pipeline/exporter_routes.py:16-47` (32 LOC)
- **시그니처**: `async def export_consolidated(site_id: str, date: str) -> Response`
- **본 cycle 변경 (commit `a7e2465`)**:
  - 신규 endpoint — 47 LOC 신규 파일 `exporter_routes.py`
  - 흐름: date parse (`YYYY-MM-DD` 아니면 400) → `PGClient(os.environ["POSTGRES_URL"]).connect()` → `fetch_site_by_id` (404) → `fetch_sheet_data` (NoDataError → 400) → `pg.close()` (finally) → `render_xlsx` → `Response(xlsx_bytes, media_type=...)`
  - **한글 파일명 패치**: starlette `Response(headers=...)` 가 latin-1 인코딩 강제로 `통합작업일보_...xlsx` 인코딩 실패 → `resp.raw_headers.append((b"content-disposition", cd_value))` 에 UTF-8 바이트 직접 주입 (RFC 6266 호환 클라이언트가 UTF-8 디코딩)
- **설계 의도**:
  - 시연 화면의 "통합 작업일보 다운로드" 버튼 — 한 site 의 N 업체 일보를 1 xlsx 로 합쳐 다운로드
  - `pipeline_runs JOIN parser_reports` 가 grain 키 — `(site_id, report_date)` 의 모든 run 합집합
  - 시트별: 시트1 bp_summaries / 시트2 job_allocations / 시트3 equipment_allocations / 시트4 parser_activities
- **이슈**:
  - **C2 Critical**: `PGClient(os.environ["POSTGRES_URL"]).connect()` 가 매 요청마다 신규 풀 생성 + close. `app.state.pg` 미재사용. 연결 handshake / TLS overhead, 동시 N 요청 시 pool 폭증, POSTGRES_URL env 누락 시 KeyError 500
  - fix 후보: `from fastapi import Request` → `pg: PGClient = request.app.state.pg` → finally 의 `pg.close()` 제거
- **관련**:
  - 호출자: 브라우저 (Next.js BFF → FastAPI direct 또는 proxy)
  - `pipeline/agents/exporter.py:34` `fetch_sheet_data` + `exporter.py:290` `render_xlsx`
  - 테스트: `test_export_run.py` (가정 — httpx 통합 테스트, commit msg 명시)

---

### ★ NEW — `fetch_sheet_data` (pipeline_runs JOIN, commit `b3010df`)

- **위치**: `pipeline/agents/exporter.py:34-95` (≈62 LOC)
- **시그니처**: `async def fetch_sheet_data(pg, site_id, report_date) -> SheetData`
- **본 cycle 변경 (commit `b3010df`)**:
  - 신규 public function — `/export/run` 의 데이터 fetch 책임
  - parser_reports / parser_activities 에 `site_id` 컬럼 없음 → `pipeline_runs pr JOIN ... USING (run_id) WHERE pr.site_id = $1 AND pr.report_date = $2` 패턴 4 회
  - 시트1 (bp_summaries) / 시트2 (job_allocations) / 시트3 (equipment_allocations) JSONB 합집합 + 시트4 (parser_activities) row 합집합
  - 0 row 시 `raise NoDataError(...)` → endpoint 가 400 변환
- **설계 의도**:
  - 한 (site_id, report_date) 의 N 업체 일보 = N pipeline_runs → 시트별 jsonb_array_elements 또는 row UNION
  - parser_reports 의 JSONB array 컬럼 (`bp_summaries` / `job_allocations` / `equipment_allocations`) 를 `jsonb_array_elements` 로 펼쳐 시트별 합산
  - `ORDER BY run_id, idx` — 업체 순서 안정화 (xlsx 시연용 일관성)
- **관련**:
  - 호출자: `pipeline/exporter_routes.py:30`
  - `SheetData` dataclass (agents/exporter.py:21) — 4 시트 묶음
  - `render_xlsx` (agents/exporter.py:290) — bytes 산출
- **Suspected related**:
  - parser_reports / parser_activities 의 INSERT 측 (`insert_parser_report` / `insert_parser_activities_batch`) — fetch_sheet_data 의 데이터 소스 생성자

---

## FastAPI 12 endpoint — Issue Cards (간략)

### POST `/api/runs/{run_id}/hil_1/resume` (api.py:223)

- 입력: `{corrections: {idx: {wa, l6_main}, ...}}`
- 출력: `{next_node}`
- 처리: graph.ainvoke 재개 (Command(resume=corrections))
- 관련: graph.py `hil_1_node` (graph.py:224) → `insert_mapping_correction` 호출

### GET `/api/sites` (api.py:337)

- 입력: 없음
- 출력: `Site[]` (16 필드)
- 처리: 1 SELECT (sites + forecasts LATERAL — M2)
- 미해결: M2 — sites 6 row 규모 OK, 확장 시 EXPLAIN ANALYZE 검토

### GET `/api/runs/{run_id}/optimizer` (api.py:401)

- 입력: run_id
- 출력: `OptimizerOutput[]` (wp_id/diagnosis/similar_cases/recommendations/details)
- 처리: 1 SELECT `_OPTIMIZER_SQL`
- 관련: optimizer agent.py view_builder

### GET `/api/dashboard/performance` (api.py:583)

- 출력: `{productivity_today, delay_days, recoverable_days, abnormal_trades}`
- 처리: 1 SELECT (CTE + agg)
- 산식: `recoverable_days` = `(d+1)*1 + (d+2)*2 + (d+3)*3 + (d+5)*5 + (d+7)*7` weighted sum (api.py:570), `not_recovered` 는 무가중치
- 관련: sites.hours_saved_cum, forecasts.assessment, optimizer_advice.recovery_distribution

### 기타 endpoint 미해결

- **M1** `/api/agents/status` (api.py:729): 7 agent meta 마다 `SELECT COUNT(*)` — 7× round-trip. agent 추가 시 N+1. fix 후보: 단일 SQL `GROUP BY current_node`
- **M7** `/api/tasks` (api.py:1045): itemsByDate `"Collector"` key hardcode (api.py:986-1042 `_build_items_by_date`). current_node 기반 agent 라우팅 미구현 (issue #N9)
- `/api/dashboard/impact` (api.py:643) / `/api/sites/{id}/wbs_tree` (api.py:832) — 베이스라인 유지

### ★ NEW GET `/export/run` (exporter_routes.py:16)

- 별도 T2 카드 참조 (C2 Critical: app.state.pg 미재사용)

---

## 데이터 모델 — PG 18 테이블 + 신규 컬럼 (이전 17 → +collector_inbox + prototype_embedding_cache + mapped_history_merge_log)

상세는 `../deep_dive_persistence.md` §3 참조. 본 cycle 신규/변경:

| 테이블 | 컬럼 | Type | Migration |
|---|---|---|---|
| **collector_inbox (NEW)** | 10 col (message_id PK + …) | mixed | **2026-05-19_collector_inbox** |
| **prototype_embedding_cache (NEW)** | text_hash PK / source_text / embedding float8[] / created_at | mixed | **2026-05-21_phase1** |
| **mapped_history_merge_log (NEW)** | 10 col (src_id/tgt_id/…/merged_at) | mixed | **2026-05-21_phase1** |
| pipeline_runs / parser_reports / parser_activities / mapper_activities / forecasts / optimizer_advice / daily_reports | `is_mock` | BOOL NOT NULL DEFAULT FALSE | **2026-05-20_add_is_mock** |
| mapper_activities | `l5_disc` / `l7_sub` / `l7_5_activity` / `sub_work_area` | TEXT | **2026-05-23_mapper_l7_5_columns** |
| daily_reports | `site_summary_text` | TEXT | **migration 부재** (commit `21c10f7` runtime ALTER 만 — 이슈 C1) |

---

## 변경 사항 정리 (ef7c6cd..1ba783f, persistence 관련)

| Commit | 파일 | 변경 |
|---|---|---|
| `b614bff` | 7 테이블 (`2026-05-20_add_is_mock.sql`) | `is_mock BOOL NOT NULL DEFAULT FALSE` — mock fallback 인프라 |
| `a3db32a` | 다수 | 78사 통합일보 1 cycle 정상 적재까지 7개 fix + cleanup script |
| `3db3d18` | `2026-05-21_phase1.sql` | `prototype_embedding_cache` + `mapped_history_merge_log` 신설 |
| `7b96b1a` | `2026-05-19_collector_inbox.sql` + `db.py:1145~1217` | **`collector_inbox` 테이블 + 4 module helper** (3 collector + `fetch_site_by_id`) |
| `a7e2465` | `pipeline/exporter_routes.py` (신규 47 LOC) | **`/export/run` xlsx endpoint** — PGClient ad-hoc + 한글 파일명 UTF-8 patch + httpx 통합 테스트 |
| `b3010df` | `pipeline/agents/exporter.py:34` | **`fetch_sheet_data` 신규** (pipeline_runs JOIN parser_reports + parser_activities) — 시트 1~4 합집합 |
| `4b8a955` | `pipeline/api.py:147,203` (+23 line) | **lifespan 안 collector idle task spawn + `app.include_router(exporter_router)`** |
| `415c990` | (FE 만 — web/) | Export/Reports/Review list/detail 분할 + N+1 제거 — BE schema 무변경 |
| `7e9e1a1` | merge (`21c10f7` 포함) | `daily_reports.site_summary_text` runtime ALTER + LLM site narrative (BE py + scripts + FE 만, **migration 부재** — 이슈 C1) |
| `d40c84f` | `2026-05-23_mapper_l7_5_columns.sql` + `db.py:639~765` | **`mapper_activities` 4 컬럼 (`l5_disc`/`l7_sub`/`l7_5_activity`/`sub_work_area`)** — activity_master 의 L7.5 / L5 propagate (회귀 6건 해소) |

총 변경 (이 서브시스템 한정): `db.py` +116 LOC (1113→1229), `api.py` +23 LOC (1050→1073), `exporter_routes.py` +47 (신규), migration +5 파일 (`2026-05-19_collector_inbox` / `2026-05-20_add_is_mock` / `2026-05-21_phase1` / `2026-05-23_mapper_l7_5_columns` / commit `21c10f7` 의 site_summary_text 는 migration 누락).

---

## 미해결 / Backlog

### Critical (deep_dive 신규 식별)

- **C1** `daily_reports.site_summary_text` migration SQL 부재 — commit `21c10f7` 가 runtime ALTER 만 적용, `infra/postgres/migrations/` 에 SQL 파일 없음. **fresh DB rebuild 시 `UndefinedColumnError`** (호출처: `scripts/backfill_daily_report_views_v2.py:162`, `pipeline/agents/optimizer/site_summary.py`). fix: `2026-05-XX_daily_reports_site_summary_text.sql` 신규 작성 필요.
- **C2** `/export/run` 매 요청 PG 풀 재생성 (`exporter_routes.py:23-34`) — `app.state.pg` 미재사용. 요청당 connection handshake / TLS overhead, 동시 N 요청 시 pool 폭증, POSTGRES_URL env 누락 시 KeyError 500. fix: `Depends(get_pg)` 또는 `request.app.state.pg` 주입.
- **C3** `insert_mapped_history_batch` ON CONFLICT DO UPDATE 가 `trade` 컬럼 누락 (`db.py:480-487`) — 같은 키 재호출 시 trade 최초값 고정. fix: SET 절에 `trade = EXCLUDED.trade` 추가 + 회귀 테스트.

### Medium (deep_dive 신규 + 기존)

- **M1** `/api/agents/status` 7× SELECT COUNT (`api.py:741-744` loop) — N+1. fix: `GROUP BY current_node` 단일 SQL.
- **M2** `_SITES_SQL` LATERAL forecasts (`api.py:279-298`) — sites 6 row 규모 OK, 확장 시 EXPLAIN ANALYZE 검토.
- **M3** `fetch_activity` (`db.py:73`) prod 호출자 0건 — dead code. 삭제 vs mapper 통합 결정 필요 (issue #N3).
- **M4** `_VIEW_JSONB_COLS` 화이트리스트와 `site_summary_text` TEXT 분리 — script 가 inline raw UPDATE 작성 (`scripts/backfill_daily_report_views_v2.py:162`). text 컬럼 전용 helper 추가 검토.
- **M5** init.sql ↔ migrations 정합 11 테이블 누락 — `parser_*` 5 + `mapper_activities` + `mapped_history` + `mapped_history_merge_log` + `collector_inbox` + `prototype_embedding_cache` + (체크포인트 3) 가 `init.sql` 에 없음. fresh dev DB 부팅 시 21 migration 순차 적용 강제 — README/Compose entrypoint 자동 적용 보장 필요.
- **M6** `build_checkpointer` (`checkpointer.py:90-92`) silent InMemorySaver fallback — `POSTGRES_URL` 미설정 시 조용히 메모리로. lifespan fail-fast 가 먼저 잡긴 하나, 단독 호출 (test/script) 시 H-i-L resume 가 process restart 시 손실 위험.
- **M7** `/api/tasks` itemsByDate `"Collector"` key hardcode (`api.py:986-1042` `_build_items_by_date`) — current_node 기반 agent 라우팅 미구현 (issue #N9).

### Low / 메모

- `api_helpers/` 디렉토리 pycache 만 잔존 — 추적 모듈 0개, `git clean` 안전.
- `forecasts DROP TABLE IF EXISTS` (`2026-05-16_downstream_agents.sql:9`) — PoC 가정, dev 재실행 시 데이터 손실.
- `infra/postgres/init.sql` 헤더 주석 "스키마 변경은 ALTER TABLE 직접 X. migration 으로 누적" — site_summary_text 누락이 유일한 위반 (C1).

---

## 관련 (다른 deep-dive 페이지)

- `../deep_dive_persistence.md` — 본 페이지의 source of truth (655 LOC).
- `../architecture_overview.md` §3.1 — PG 17 테이블 baseline 카탈로그.
- `./design_intent_collector.md` — `collector_inbox` 의 IMAP IDLE 생산자 측 디자인 (collector_node 호출 관점).
- `./design_intent_mapper.md` — `mapper_activities` 의 alternatives / cum_workers / L7.5 propagate 산출 측.
- `./design_intent_optimizer.md` — `upsert_daily_report_view_col` 9 jsonb 화이트리스트 호출 측 + `site_summary_text` LLM 산출.
- `./design_intent_exporter.md` — `/export/run` 흐름의 xlsx render 측 (exporter.py:290 `render_xlsx`).
