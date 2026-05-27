# Deep Dive — persistence (PostgreSQL + ChromaDB + FastAPI + Exporter)

- **Generated**: 2026-05-26 (cycle: ef7c6cd → 1ba783f)
- **Scope**: `pipeline/db.py` + `pipeline/api.py` + `pipeline/chroma_client.py` + `pipeline/checkpointer.py` + `pipeline/exporter_routes.py` + `infra/postgres/migrations/*.sql`
- **Pair files**:
  - `./architecture_overview.md` (서브시스템 지도)
  - `./design-intent/design_intent_persistence.md` (T1/T2 카드 baseline)

본 cycle 의 큰 줄기는 다음 4 가지: (1) `collector_inbox` 테이블 + 4 helper 신규 (Gmail IDLE worker dedup), (2) `/export/run` xlsx endpoint + lifespan exporter router include, (3) `mapper_activities` 에 L7.5 / L5 propagate 4 컬럼 추가, (4) `is_mock` 컬럼 7 테이블 backfill + B_Track 의 Export/Reports/Review list/detail 분할 (N+1 제거 — FE 측만 영향, BE schema 무변경).

---

## 1. Overview — 3 레이어

```
                   ┌───────────────────────────────────┐
                   │  Browser (Next.js BFF + 경영진 UI) │
                   └────────────────┬──────────────────┘
                                    │  HTTP
                                    ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  FastAPI app (pipeline/api.py, port 8000)                    │
   │  - lifespan : PGClient connect + build_graph + collector task│
   │  - /health, /api/sites, /api/dashboard/*, /api/tasks, ...    │
   │  - /api/runs/{id}/hil_1/resume  → graph.ainvoke (Command)    │
   │  - /export/run  (exporter_routes.router include)             │
   └──────┬─────────────────────┬─────────────────────────────────┘
          │                     │
          │ app.state.pg        │ app.state.graph (compiled)
          ▼                     ▼
   ┌──────────────────┐  ┌─────────────────────────────────┐
   │ PGClient pool    │  │ LangGraph + AsyncPostgresSaver  │
   │ asyncpg, min=1,  │  │ (checkpointer.py)               │
   │ max=5            │  │ - InMemory  ↔ Lazy Async PG    │
   └────┬─────────────┘  └────────┬────────────────────────┘
        │  35+ helper                │  thread_id = run_id
        ▼                            ▼
   ┌────────────────────────────────────────────────────────┐
   │  PostgreSQL  (homelab port 5532  /  dev port 5432)     │
   │                                                         │
   │  domain tables (17)   +   langgraph checkpoint (3)     │
   │  pipeline_runs / sites / activity_master / forecasts   │
   │  optimizer_advice / mapping_corrections                │
   │  daily_reports (+ 9 view jsonb + site_summary_text)    │
   │  mapped_history / mapped_history_merge_log             │
   │  parser_reports / parser_activities                    │
   │  parser_job_allocations / parser_equipment_allocations │
   │  parser_worker_outputs / parser_report_meta            │
   │  mapper_activities (+ alternatives GIN)                │
   │  collector_inbox / prototype_embedding_cache           │
   │  checkpoints / checkpoint_writes / checkpoint_blobs    │
   └────────────────────────────────────────────────────────┘

   ┌────────────────────────────────────────────────────────┐
   │  ChromaDB  HttpClient  (homelab port 5533)             │
   │  - wbs_master          (cosine, ~189 doc) — Mapper RAG │
   │  - daily_activities    (cosine, N doc)    — Atomizer   │
   │                                              + retrieve│
   └────────────────────────────────────────────────────────┘

   ┌────────────────────────────────────────────────────────┐
   │  Collector (Gmail IMAP IDLE)                           │
   │  - lifespan asyncio.create_task(idle_loop(cfg))        │
   │  - insert_collector_inbox → run pipeline               │
   │  - update_collector_inbox_status(run_id, parse_status) │
   └────────────────────────────────────────────────────────┘
```

세 leg 모두 FastAPI lifespan 에서 동시 wiring 된다: PG pool open → LangGraph compile → (선택) collector idle task spawn → exporter router include. shutdown 은 역순.

---

## 2. 파일 목록 + LOC + 책임

| 파일 | LOC | 핵심 책임 |
|---|---:|---|
| `pipeline/db.py` | 1229 | asyncpg pool + 35+ helper (PGClient class + 모듈 함수) — 모든 SELECT/INSERT/UPDATE 단일 진입점 |
| `pipeline/api.py` | 1073 | FastAPI 12 endpoint + lifespan (PG pool + graph + collector idle + exporter router) |
| `pipeline/chroma_client.py` | 35 | `chromadb.HttpClient` 래퍼 — 2 컬렉션 (`wbs_master`, `daily_activities`) get_or_create |
| `pipeline/checkpointer.py` | 94 | `build_checkpointer()` + `_LazyAsyncPostgresSaver` — sync init 안 async pool open 회피 |
| `pipeline/exporter_routes.py` | 47 | `GET /export/run?site_id=&date=YYYY-MM-DD` — `fetch_sheet_data` → `render_xlsx` → bytes |
| `pipeline/api_helpers/` | 0 (`__init__.py` 없음) | `__pycache__` 만 잔존 — git 추적 모듈 없음 (코드 미사용) |
| `infra/postgres/init.sql` | 190 | dev 컨테이너 초기 7 테이블 (pipeline_runs, daily_reports, forecasts, optimizer_advice, mapping_corrections, sites, activity_master) |
| `infra/postgres/migrations/*.sql` | 21 file | 누적 schema 변경 (테이블 신설 + 컬럼 추가 + index 추가) |

`api_helpers/` 는 pycache 디렉토리만 있고 추적 모듈 0개 — 과거 분리 시도 흔적으로 보임 (`api.py` 가 inline SQL 다 보유).

---

## 3. PG 테이블 전수 카탈로그

### 3.1 도메인 테이블 (17)

#### 3.1.1 `pipeline_runs` — 파이프라인 실행 단위 (`init.sql:13`)

| 컬럼 | 타입 | NULL | 비고 |
|---|---|---|---|
| `run_id` | UUID | PK | `uuid_generate_v4()` default |
| `site_id` | TEXT | YES | sites.site_id 참조 (FK 미선언) |
| `report_date` | DATE | NO | |
| `status` | TEXT | NO | CHECK (`running`/`waiting_hil_1`/`waiting_hil_2`/`completed`/`failed`) |
| `current_node` | TEXT | YES | 현재 실행 노드명 |
| `error` | TEXT | YES | |
| `atomized_count` | INT | YES | default 0 — Atomizer 가 적재한 row 수 (2026-05-16_downstream_agents) |
| `started_at` | TIMESTAMPTZ | NO | `NOW()` |
| `completed_at` | TIMESTAMPTZ | YES | |
| `is_mock` | BOOL | NO | default FALSE (2026-05-20_add_is_mock) |

**Index**: `idx_pipeline_runs_date` (`report_date DESC`), `idx_pipeline_runs_site` (`site_id, report_date DESC`), `idx_pipeline_runs_status` (`status`).

**INSERT/UPDATE**: `PGClient.insert_pipeline_run` (`db.py:147`), `PGClient.update_run_atomized_count` (`db.py:238`), `PGClient.delete_pipeline_run` (`db.py:170`).
**SELECT**: `PGClient.get_pipeline_run` (`db.py:504`), `PGClient.assert_pipeline_run_exists` (`db.py:176`), 그리고 `api.py` 의 거의 모든 endpoint (`/api/tasks` 가 가장 무거움 — `db.py:876`~ inline SQL).

#### 3.1.2 `sites` — Dashboard Layer 1 카드 source (`init.sql:141`)

| 컬럼 | 타입 | NULL | 비고 |
|---|---|---|---|
| `site_id` | TEXT | PK | |
| `name` | TEXT | NO | |
| `plan_progress` | NUMERIC(5,2) | YES | |
| `actual_progress` | NUMERIC(5,2) | YES | |
| `status` | TEXT | YES | CHECK (`normal`/`caution`/`risk`/`unknown`) |
| `last_run_id` | UUID | YES | pipeline_runs FK (ON DELETE SET NULL) |
| `is_mock` | BOOL | NO | default TRUE (sites 만 default TRUE) |
| `location` | TEXT | YES | (2026-05-17_db_alignment) |
| `headcount` | INT | YES | |
| `hours_saved` | NUMERIC | YES | |
| `fte_saved` | NUMERIC | YES | |
| `hours_saved_cum` | NUMERIC | NO | default 0 (2026-05-19_sites_hours_saved_cum) |
| `updated_at` | TIMESTAMPTZ | NO | |

**UPDATE**: 모듈 함수 `update_site_last_run` (`db.py:1109`) — reporter→END edge 가 호출. `update_site_hours_saved_cum` (`db.py:1125`) — 산식 `(120-5)/60 × atomized_count h`.
**SELECT**: `fetch_site_by_id` (`db.py:1220`), `_SITES_SQL` (`api.py:279` — LATERAL forecasts JOIN), `_DASHBOARD_IMPACT_SQL` (`api.py:622`).

#### 3.1.3 `activity_master` — WBS Master List (`init.sql:162` + 5 migration)

복합 PK `(site_id, wbs_activity_id)` — 현장별 WBS 격리.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `site_id` | TEXT NOT NULL | 2026-05-17_activity_master_site_id (DROP DEFAULT 후 PK 일부) |
| `wbs_activity_id` | TEXT NOT NULL | PK 일부 |
| `wa` | TEXT | 2026-05-17_activity_master_wa |
| `l5_disc` | TEXT NOT NULL | 건축/설비/... |
| `l6_main` / `l6_code` | TEXT / TEXT | |
| `l7_sub` / `l7_code` | TEXT / TEXT | |
| `l7_5_activity` | TEXT | |
| `sub_work_area` | TEXT | |
| `company` | TEXT | BP사 정규화 후 값 |
| `unit` | TEXT | |
| `plan_total_qty` / `plan_mh_rev2` / `plan_mh_rev1` / `plan_mh_rev0` / `plan_wv` | NUMERIC | |
| `plan_start` / `plan_finish` / `actual_start` / `actual_finish` | DATE | |
| `source_file` / `loaded_at` | TEXT / TIMESTAMPTZ | |

**Index**: `idx_actmaster_lookup` (`l5_disc, company, unit`), `idx_actmaster_wa_l6` (`wa, l6_main`), `idx_actmaster_period` (`plan_start, plan_finish`), `idx_actmaster_site_company` (`site_id, company`), `idx_actmaster_site_l6` (`site_id, l5_disc, l6_main`), `idx_actmaster_site_period` (`site_id, plan_start, plan_finish`).

**적재**: `scripts/load_master_list.py` (외부, 1회 적재 ~189 row/site).
**SELECT**: Mapper 가 직접 호출하는 4 helper — `fetch_bp_candidates` (`db.py:38`), `fetch_activity` (`db.py:73`), `fetch_l6_plan_mh_map` (`db.py:106`), `fetch_plan_for_group` (`db.py:194`). Reports BFF endpoint 도 `wp_summary` SQL 에서 JOIN (`api.py:419`).

#### 3.1.4 `forecasts` — Forecaster 산출 (`init.sql:51` + 4 migration)

`DROP+CREATE` 되었다가 (`2026-05-16_downstream_agents`) 컬럼 추가 (`2026-05-16_forecaster`, `2026-05-16_optimizer_hil2`, `2026-05-18_forecasts_wa`, `2026-05-20_add_is_mock`).

28 컬럼 — id / run_id (CASCADE) / `company` / `l6_main` / `wa` (Phase 2) / `today_qty_by_unit` JSONB / `today_assigned_workers` / `today_productivity` / `main_unit` / `today_conditions` / `plan_total_qty_by_unit` JSONB / `plan_mh_sum` / `plan_start` / `plan_finish` / `plan_mh_per_day` / `schedule_state` / `window_start` / `window_days` / `expected_in_window_mh` / `actual_in_window_mh` / `mh_gap` / `delay_days` (NUMERIC) / `rag_n_similar` / `similar_cases` JSONB / `assessment` / `reasoning` / `recovery_likelihood` / `expected_completion` / `risk_level` / `is_mock` / `created_at`.

**JSONB shape**:
- `today_qty_by_unit` : `{"m": 80.0, "ea": 12.0}` (단위→실측 qty)
- `plan_total_qty_by_unit` : 동일 shape, Plan 합산
- `similar_cases` : top-K (productivity, conditions list)

**Index**: `idx_forecasts_run` (`run_id`), `idx_forecasts_wa_company_l6` (Phase 2 — `idx_forecasts_company_l6` 가 drop 됨), `idx_forecasts_risk` partial (`risk_level <> '정상'`), `idx_forecasts_state` (`schedule_state`).

**INSERT**: `PGClient.insert_forecast` (`db.py:260`) — `pipeline/agents/forecaster/agent.py:331` 가 row dict per group 으로 호출.
**SELECT**: `/api/sites` LATERAL (`api.py:291`), `/api/runs/{id}/wp_summary` (`api.py:419`), `/api/sites/{site_id}/reports` (`api.py:500`), `/api/dashboard/performance` (`api.py:562`), `/api/tasks` HAS_ANOMALY EXISTS (`api.py:900`).

#### 3.1.5 `optimizer_advice` — Optimizer 산출 (`init.sql:107` + 2 migration)

11 컬럼 — id / run_id (CASCADE) / `l6_main` / `company` (rename from `trade`, 2026-05-16_downstream_agents) / `diagnosis` / `forecast_assessment` / `recovery_pattern` JSONB / `degradation_cases` JSONB / `recovery_distribution` JSONB / `recommendations` JSONB / `is_mock` / `created_at`.

**JSONB shape**:
- `degradation_cases` : `retrieve.fetch_degradation_cases` 원본 — `[{date, productivity, conditions, …}, ...]`
- `recovery_pattern` : `[{date, recovery_days}, …]` (degradation_cases 와 1:1)
- `recovery_distribution` : `{"d+1": 3, "d+2": 1, "d+3": 0, "d+5": 0, "d+7": 0, "not_recovered": 1}` — `/api/dashboard/performance` 가 d+N * N weighted sum 으로 `recoverable_days` 계산 (`api.py:570`).
- `recommendations` : `[{rank, text}, ...]` ranked list

**Index**: `idx_optimizer_advice_run`, `idx_optimizer_advice_company_l6`.

**INSERT**: `PGClient.insert_optimizer_advice` (`db.py:332`) — `pipeline/agents/optimizer/agent.py:182`.
**SELECT**: `/api/runs/{id}/optimizer` (`api.py:352`).

#### 3.1.6 `mapping_corrections` — HIL 1 누적 (`init.sql:127`)

6 컬럼 — id / run_id (SET NULL) / `report_date` / `original` JSONB / `corrected` JSONB / `created_at`.

`original` 안에 `{wa, l6_main, mapping_conf, mapping_source, work_content, company, trade}` (Mapper 추천 + 컨텍스트), `corrected` 안에 `{wa, l6_main, mapping_source="user_corrected", correction_type="replace"}` (HIL 1 정정) — `db.py:370` docstring 명시.

**INSERT**: `PGClient.insert_mapping_correction` (`db.py:370`) — `pipeline/graph.py:265` (hil_1_node) 가 호출.

#### 3.1.7 `daily_reports` — Reporter + Optimizer view (`init.sql:33` + 4 migration)

19 컬럼 — id / run_id (CASCADE) / `site_id` (2026-05-19_daily_reports_views — partial unique idx) / `report_date` / `bp_name` / `report_md` / `history_csv_row` JSONB / 9 view jsonb (아래) / `site_summary_text` TEXT (commit `21c10f7` — migration 파일 부재, ⚠️ 이슈 §12 참조) / `is_mock` / `created_at`.

**9 view JSONB 컬럼** (`db.py:1050` `_VIEW_JSONB_COLS` 화이트리스트):

| 컬럼 | default | 의미 | builder |
|---|---|---|---|
| `kpi_jsonb` | `{}` | site KPI 카드 (실측, 계획, gap, SPI, 일자 등) | `optimizer/view_builder._build_kpi` |
| `contractor_bars_jsonb` | `[]` | 업체별 bar 차트 | `_build_contractor_bars` |
| `trade_bars_jsonb` | `[]` | 공종별 bar 차트 | `_build_trade_bars` |
| `quadrant_jsonb` | `[]` | 4분면 (생산성 × 위험) 산점 | `_build_quadrant` |
| `wp_summary_jsonb` | `[]` | WP (wa, l6_main, company) 요약 표 | `_build_wp_summary` |
| `s_curve_jsonb` | `[]` | 누적 곡선 (plan vs actual) | `_build_s_curve` |
| `optimizer_view_jsonb` | `{}` | Optimizer 진단 + 추천 카드 | `_build_optimizer_view` |
| `productivity_jsonb` | `{}` | 일자별 생산성 분포 | `_build_productivity` |
| `scenarios_jsonb` | `{}` | site 전체 + WP 별 4 시나리오 (`no_action`/`optimistic_p25`/`base_p50`/`pessimistic_p75`) — 2026-05-19_scenarios_jsonb | `_build_scenarios` |

**Index**: `idx_daily_reports_run` (`run_id`), `idx_daily_reports_date` (`report_date DESC`), `daily_reports_run_site_date_uq` (PARTIAL UNIQUE on `(run_id, site_id, report_date) WHERE site_id IS NOT NULL`).

**INSERT/UPDATE**: `PGClient.insert_daily_report` (`db.py:405`, UPDATE-first 패턴) — `pipeline/agents/reporter.py:151`. `PGClient.upsert_daily_report_view_col` (`db.py:1062`, UPDATE-first + 화이트리스트) — `pipeline/agents/optimizer/agent.py:220` 가 col 별 9 회 호출.
**SELECT**: BFF `/api/mock/report` (FE Next.js), `/api/runs/{id}/optimizer` 는 advice 만 조회 (view jsonb 미사용).

#### 3.1.8 `mapped_history` — Atomizer 적재 (`2026-05-18_mapped_history` + `2026-05-19_mapped_history_trade`)

11 컬럼 — id / run_id (CASCADE) / `report_date` / `site_id` (FK sites) / `wa` / `l6_main` / `company` / `today_qty` / `today_assigned_workers` / `unit` / `trade` (한글 공종, FE 의도 source) / `created_at`. UNIQUE `(run_id, wa, l6_main, company)`.

**Index**: `idx_mapped_history_site_date` (`site_id, report_date DESC`), `idx_mapped_history_triplet` (`wa, l6_main, company, report_date DESC`).

**INSERT**: `PGClient.insert_mapped_history_batch` (`db.py:458`) — `pipeline/agents/atomizer.py:190`. ON CONFLICT 시 `today_qty / today_assigned_workers / unit` 만 EXCLUDED 로 덮어쓰기 (trade 는 갱신 X — bug 여지).
**SELECT**: `_WP_SUMMARY_SQL` (`api.py:419`), `_TASKS_ITEMS_SQL` (`api.py:912`).

#### 3.1.9 `mapped_history_merge_log` — Phase 1 합산 감사 (`2026-05-21_phase1`)

10 컬럼 — id / src_id / tgt_id / run_id / report_date / site_id / wa / l6_main / old_company / new_company / merged_today_qty / merged_at. `idx_merge_log_date` (`report_date DESC`).

본 cycle 의 호출자는 `scripts/merge_mapped_history.py` (외부) — db.py helper 없음.

#### 3.1.10 `parser_reports` (`2026-05-18_parser_mapper_outputs`)

8 컬럼 — id / run_id UNIQUE / `report_date` / `project` / `bp_summaries` JSONB / `job_allocations` JSONB / `equipment_allocations` JSONB / `activity_count` / `is_mock` / `created_at`. `parser_reports_report_date_idx`.

**INSERT**: `PGClient.insert_parser_report` (`db.py:515`, ON CONFLICT (run_id) DO UPDATE) — `pipeline/graph.py:110`.
**SELECT**: `pipeline/agents/exporter.py:34` `fetch_sheet_data` 가 `pipeline_runs JOIN parser_reports` 로 `jsonb_array_elements` 합집합.

#### 3.1.11 `parser_activities` (위 migration + `2026-05-19_parser_full_schema` 확장)

23 컬럼 — id / run_id / report_date / idx / l5_disc / trade / company / unit / today_qty / work_content / plan_total_qty / **zone** / **bp_code** / **scope** / **yesterday_cum_qty** / **today_cum_qty** / **progress_percent** / **remaining_qty** / **remaining_percent** / **note** / **work_location_code** / **wbs_mid_name** / **wbs_sub_name** / **wbs_detail_name** / is_mock / created_at. UNIQUE `(run_id, idx)`. Index: `parser_activities_run_idx`, `parser_activities_company_idx`, `parser_activities_zone_idx`, `parser_activities_bp_code_idx`.

**INSERT**: `insert_parser_activities_batch` (`db.py:558`) — `graph.py:120`.
**SELECT**: `exporter.py:73` 가 `parser_activities pa JOIN pipeline_runs pr` 로 시트4 합집합.

#### 3.1.12 `mapper_activities` (위 migration + `2026-05-19_daily_reports_views` + `2026-05-19_mapper_alternatives` + `2026-05-23_mapper_l7_5_columns`)

37 컬럼 — id / run_id / report_date / idx / company / trade / unit / today_qty / wa / l6_main / mapping_conf / mapping_source / requires_review / assigned_workers / worker_source / plan_total_qty / plan_mh / conditions JSONB / zone / bp_code / scope / yesterday_cum_qty / today_cum_qty / progress_percent / remaining_qty / remaining_percent / note / work_location_code / wbs_mid_name / wbs_sub_name / wbs_detail_name / **alternatives** JSONB (GIN) / **cum_workers_today** / **cum_actual_mh_today** / **l5_disc** / **l7_sub** / **l7_5_activity** / **sub_work_area** / is_mock / created_at. UNIQUE `(run_id, idx)`.

**Index**: `mapper_activities_run_idx`, `mapper_activities_wa_l6_idx`, `mapper_activities_company_idx`, `mapper_activities_zone_idx`, `mapper_activities_bp_code_idx`, `mapper_activities_alternatives_gin` GIN.

**INSERT**: `insert_mapper_activities_batch` (`db.py:639`, 37 컬럼 ON CONFLICT DO UPDATE 전 컬럼) — `pipeline/graph.py:149`. 본 cycle (`d40c84f`) 가 마지막 4 컬럼 (l5_disc, l7_sub, l7_5_activity, sub_work_area) 추가.

#### 3.1.13 `parser_job_allocations` (`2026-05-19_parser_full_schema`)

14 컬럼 — id / run_id / report_date / idx / bp_code / company / disc_abbrev / manager_code / worker_code / job_type / `workers_yesterday_cum` JSONB / `workers_today_incr` JSONB / `workers_today_cum` JSONB / final_flag / `workers_cum_t` / is_mock / created_at.

**JSONB shape** (`TimeShiftCounts`): `{"morning": int, "daytime": int, "overtime": int, "night": int, "all_night": int, "total": int}` (시간대 6 필드).

**Index**: `parser_job_allocations_run_idx`, `parser_job_allocations_company_idx`, `parser_job_allocations_job_idx`.

**INSERT**: `insert_parser_job_allocations_batch` (`db.py:771`) — `graph.py:130`.
**SELECT**: `exporter.py` (시트2 — `jsonb_array_elements` 합집합).

#### 3.1.14 `parser_equipment_allocations`

14 컬럼 — id / run_id / report_date / idx / bp_code / company / disc_abbrev / equipment_big / equipment_mid / equipment_spec / `count_yesterday_cum` / `count_today_incr` / `count_today_cum` JSONB (`TimeShiftCounts`) / final_flag / count_cum_t / is_mock / created_at. Index `_run_idx`, `_company_idx`, `_big_mid_idx`.

**INSERT**: `insert_parser_equipment_allocations_batch` (`db.py:843`) — `graph.py:136`.

#### 3.1.15 `parser_worker_outputs` (시트6, 업체별만)

17 컬럼 — id / run_id / report_date / idx / `bp_name` (1 run × N 업체) / worker_name / job_type / wbs_mid_name / wbs_sub_name / wbs_detail_name / work_location_code / work_content / `shift_morning` / `shift_daytime` / `shift_overtime` / `shift_night` / `shift_all_night` / note / created_at. UNIQUE `(run_id, idx)`. Index `_run_idx`, `_bp_idx`, `_worker_idx`.

**INSERT**: `insert_parser_worker_outputs_batch` (`db.py:909`) — Merge 단계가 N 업체 outputs 를 합쳐 호출 (호출자 코드: `pipeline/agents/parser_post.py` 또는 graph merge 노드).

#### 3.1.16 `parser_report_meta` (Cover, 업체별만)

10 컬럼 — id / run_id / report_date / `bp_name` (1 run × N row) / project_name / project_code / site_id / writer / reviewer / approval / document_no / created_at. UNIQUE `(run_id, bp_name)`. Index `_run_idx`.

**INSERT**: `insert_parser_report_meta_batch` (`db.py:980`) — Merge 단계.

#### 3.1.17 `collector_inbox` — Gmail IDLE dedup (`2026-05-19_collector_inbox`)

10 컬럼:

| 컬럼 | 타입 | NULL | 비고 |
|---|---|---|---|
| `message_id` | TEXT | PK | RFC822 Message-ID (header) |
| `received_at` | TIMESTAMPTZ | NO | NOW() |
| `site_id` | TEXT | NO | |
| `report_date` | DATE | NO | |
| `bp_name` | TEXT | NO | |
| `attachment_filename` | TEXT | NO | |
| `attachment_path` | TEXT | NO | 로컬 디스크 경로 |
| `run_id` | UUID | YES | pipeline_runs FK (ON DELETE SET NULL) |
| `parse_status` | TEXT | NO | CHECK (`pending`/`running`/`completed`/`failed`/`dead_letter`) default `pending` |
| `error` | TEXT | YES | |
| `updated_at` | TIMESTAMPTZ | NO | NOW() |

**Index**: `collector_inbox_site_date_idx` (`site_id, report_date`), `collector_inbox_status_idx` PARTIAL (`parse_status IN ('pending','running','failed')`).

**INSERT/UPDATE** (모듈 함수, 본 cycle `7b96b1a` 신규):
- `insert_collector_inbox(pg, *, message_id, site_id, report_date, bp_name, attachment_filename, attachment_path)` (`db.py:1149`) — ON CONFLICT (message_id) DO NOTHING (dedup race safety).
- `update_collector_inbox_status(pg, message_id, *, run_id=None, parse_status, error=None)` (`db.py:1179`) — `run_id = COALESCE($3, run_id)` 패턴.
- `fetch_collector_inbox_by_message_id(pg, message_id)` (`db.py:1206`) — dedup 체크.

**호출자**: `pipeline/collector/idle_worker.py:26~28` (IMAP IDLE loop) + `pipeline/agents/collector_node.py` (run 직전 status 갱신).

#### 3.1.18 `prototype_embedding_cache` (`2026-05-21_phase1`)

`text_hash` PK / `source_text` TEXT / `embedding` `float8[]` / `created_at`. `idx_embedding_cache_created`.

L7.5 임베딩 캐시 — db.py helper 없음 (외부 `scripts/cache_*.py` 가 직접 SQL).

### 3.2 LangGraph checkpoint 테이블 (3)

`AsyncPostgresSaver.setup()` 가 idempotent 로 자동 생성 — `init.sql` / `migrations/` 미포함.

#### 3.2.1 `checkpoints`

LangGraph 표준 schema: `thread_id` TEXT / `checkpoint_ns` TEXT / `checkpoint_id` TEXT / `parent_checkpoint_id` TEXT / `type` TEXT / `checkpoint` JSONB / `metadata` JSONB / PK `(thread_id, checkpoint_ns, checkpoint_id)`.

`thread_id = run_id` (str) — `api.py:253` `config={"configurable": {"thread_id": run_id}}` 가 주입. `hil_1` interrupt 시점에 graph state 가 저장되고, `POST /api/runs/{id}/hil_1/resume` 가 `Command(resume=corrections_payload)` 으로 재개.

#### 3.2.2 `checkpoint_writes`

각 thread 의 pending writes — `(thread_id, checkpoint_ns, checkpoint_id, task_id, idx)` PK + `channel` / `type` / `blob`.

#### 3.2.3 `checkpoint_blobs`

큰 blob 분리 적재.

### 3.3 init.sql 미포함 / migration 만 존재 테이블

위 catalog 의 `pipeline_runs` / `daily_reports` / `forecasts` / `optimizer_advice` / `mapping_corrections` / `sites` / `activity_master` 7 개만 `init.sql` 정의. 나머지 `mapped_history` / `mapped_history_merge_log` / `parser_*` 5 / `mapper_activities` / `collector_inbox` / `prototype_embedding_cache` 10 개는 migration 만으로 생성 — fresh DB 부팅 시 init.sql + 21 migration 순차 적용 강제.

---

## 4. db.py helper 전수 표

### 4.1 PGClient class (instance method 28개)

| # | Helper | Line | Signature | 호출자 | 의도 (SQL pattern) |
|---|---|---:|---|---|---|
| 1 | `__init__` | 18 | `(dsn, min_size=1, max_size=5)` | api.py:163, exporter_routes.py:23 | 풀 메타 보관 |
| 2 | `connect` | 24 | `() -> None` | 동상 | `asyncpg.create_pool` |
| 3 | `close` | 32 | `() -> None` | 동상 | `pool.close()` |
| 4 | `fetch_bp_candidates` | 38 | `(company, site_id=None) -> list[dict]` | `graph.py:79` mapper | `SELECT DISTINCT wa,l6_main FROM activity_master WHERE company=$1 [AND site_id=$2]` |
| 5 | `fetch_activity` | 73 | `(wbs_activity_id, site_id=None) -> dict\|None` | (미사용 의심 — test 만) | `SELECT … FROM activity_master WHERE wbs_activity_id=$1` |
| 6 | `fetch_l6_plan_mh_map` | 106 | `(company, l6_list, site_id=None) -> dict[str,int]` | mapper `_prorate_mh` | `SELECT l6_main,SUM(plan_mh_rev2) GROUP BY l6_main` N+1 회피 |
| 7 | `insert_pipeline_run` | 147 | `(run_id, site_id, date, status='running')` | test fixture | `INSERT INTO pipeline_runs …` |
| 8 | `delete_pipeline_run` | 170 | `(run_id)` | test fixture | cleanup |
| 9 | `assert_pipeline_run_exists` | 176 | `(run_id)` | atomizer pre-check | `SELECT 1 … LIMIT 1`, 없으면 RuntimeError |
| 10 | `fetch_plan_for_group` | 194 | `(company, l6_main, site_id=None) -> dict` | forecaster | 2 SQL 분리 (qty_by_unit + summary) — `jsonb_object_agg` duplicate key 회피 |
| 11 | `update_run_atomized_count` | 238 | `(run_id, count)` | atomizer 종료 | `UPDATE pipeline_runs SET atomized_count=$1, current_node='atomizer' …`, 0-row → RuntimeError |
| 12 | `insert_forecast` | 260 | `(row: dict)` | forecaster/agent.py:331 | `INSERT INTO forecasts (28 col)` |
| 13 | `insert_optimizer_advice` | 332 | `(row: dict)` | optimizer/agent.py:182 | `INSERT INTO optimizer_advice (9 col, 4 JSONB)` |
| 14 | `insert_mapping_correction` | 370 | `(run_id, report_date, original, corrected)` | graph.py:265 hil_1 | `INSERT INTO mapping_corrections (run_id, report_date, original, corrected)` |
| 15 | `insert_daily_report` | 405 | `(run_id, report_date, report_md, history_csv_row, bp_name=None, site_id=None)` | reporter.py:151 | UPDATE-first → INSERT (partial unique idx 회피) |
| 16 | `insert_mapped_history_batch` | 458 | `(run_id, report_date, site_id, rows)` | atomizer.py:190 | `executemany` ON CONFLICT (run_id,wa,l6_main,company) DO UPDATE (today_qty/workers/unit 만) |
| 17 | `get_pipeline_run` | 504 | `(run_id) -> dict\|None` | (현 cycle 외부 미호출) | `SELECT run_id,site_id,report_date,status,current_node` |
| 18 | `insert_parser_report` | 515 | `(run_id, report_date, project, bp_summaries, job_allocations, equipment_allocations, activity_count)` | graph.py:110 | ON CONFLICT (run_id) DO UPDATE 전 컬럼 |
| 19 | `insert_parser_activities_batch` | 558 | `(run_id, report_date, activities)` | graph.py:120 | `executemany` 23 컬럼 ON CONFLICT (run_id,idx) DO UPDATE |
| 20 | `insert_mapper_activities_batch` | 639 | `(run_id, report_date, activities)` | graph.py:149 | `executemany` 37 컬럼 — 본 cycle 마지막 4 col propagate |
| 21 | `insert_parser_job_allocations_batch` | 771 | `(run_id, report_date, rows)` | graph.py:130 | `executemany` 시트2 TimeShiftCounts 3 group JSONB |
| 22 | `insert_parser_equipment_allocations_batch` | 843 | `(run_id, report_date, rows)` | graph.py:136 | `executemany` 시트3 동상 |
| 23 | `insert_parser_worker_outputs_batch` | 909 | `(run_id, report_date, rows, bp_name=None)` | merge 노드 | `executemany` 시트6 업체별 |
| 24 | `insert_parser_report_meta_batch` | 980 | `(run_id, report_date, metas)` | merge 노드 | UNIQUE (run_id, bp_name) — N 업체 |
| 25 | `fetch_one` | 1028 | `(sql, *args) -> dict\|None` | api.py:215 (`/health`), api.py:592 (`/api/dashboard/performance`) | 임의 SELECT 1 row |
| 26 | `fetch_all` | 1039 | `(sql, *args) -> list[dict]` | api.py 대부분 endpoint | 임의 SELECT |
| 27 | `_VIEW_JSONB_COLS` | 1050 | `tuple[str]` (9개) | `upsert_daily_report_view_col` 내부 | SQL injection 가드 화이트리스트 |
| 28 | `upsert_daily_report_view_col` | 1062 | `(run_id, site_id, report_date, col: str, value)` | optimizer/agent.py:220 | UPDATE `SET {col}=$4` (f-string + 화이트리스트) → 0 row → INSERT |

### 4.2 모듈 함수 (7)

| # | Function | Line | Signature | 호출자 | 의도 |
|---|---|---:|---|---|---|
| 29 | `update_site_last_run` | 1109 | `(pg, site_id, run_id)` | graph.py:473 reporter→END | `UPDATE sites SET last_run_id=$1, updated_at=NOW()` |
| 30 | `update_site_hours_saved_cum` | 1125 | `(pg, site_id, atomized_count)` | graph.py:474 reporter→END | `UPDATE sites SET hours_saved_cum=hours_saved_cum+$1` (산식 `(120-5)/60 × N` h) |
| 31 | `AS_IS_MIN` / `TO_BE_MIN` | 1121/1122 | `int = 120` / `int = 5` | G2 산식 상수 | 일보당 수작업 분 vs AI 처리 분 |
| 32 | `insert_collector_inbox` | 1149 | `(pg, *, message_id, site_id, report_date, bp_name, attachment_filename, attachment_path)` | collector/idle_worker.py | `INSERT INTO collector_inbox` ON CONFLICT (message_id) DO NOTHING |
| 33 | `update_collector_inbox_status` | 1179 | `(pg, message_id, *, run_id=None, parse_status, error=None)` | collector/idle_worker.py + collector_node.py | `UPDATE collector_inbox SET parse_status=$2, run_id=COALESCE($3,run_id), error=$4, updated_at=NOW()` |
| 34 | `fetch_collector_inbox_by_message_id` | 1206 | `(pg, message_id) -> dict\|None` | collector/idle_worker.py | dedup check `SELECT * WHERE message_id=$1` |
| 35 | `fetch_site_by_id` | 1220 | `(pg, site_id) -> dict\|None` | exporter_routes.py:26 | `/export/run` 가 site name 조회 |

총 35 helper. 추가로 `_LazyAsyncPostgresSaver` (`checkpointer.py:30`) class — LangGraph 가 PG 풀을 사용.

---

## 5. FastAPI 12 endpoint 전수

| # | Path | Method | Line | db helper 호출 | 응답 shape (요약) | FE 호출처 |
|---:|---|---|---:|---|---|---|
| 1 | `/health` | GET | 211 | `pg.fetch_one("SELECT 1 AS ok")` | `{status,pg,version}` | (probe) |
| 2 | `/api/runs/{run_id}/hil_1/resume` | POST | 223 | `graph.ainvoke(Command(resume))` — 내부에서 `insert_mapping_correction` | `{next_node}` | review modal 의 "승인" 버튼 |
| 3 | `/api/sites` | GET | 337 | `pg.fetch_all(_SITES_SQL)` | `Site[]` (16 필드) | dashboard Layer 1 카드 |
| 4 | `/api/runs/{run_id}/optimizer` | GET | 401 | `pg.fetch_all(_OPTIMIZER_SQL, run_id)` | `OptimizerOutput[]` (wp_id/diagnosis/similar_cases/recommendations/details) | 현장 상세 Optimizer 패널 |
| 5 | `/api/runs/{run_id}/wp_summary` | GET | 481 | `pg.fetch_all(_WP_SUMMARY_SQL, run_id)` | `WPSummaryRow[]` | WP 표 |
| 6 | `/api/sites/{site_id}/reports` | GET | 542 | `pg.fetch_all(_SITE_REPORTS_SQL, site_id, days)` | `ReportDaily[]` (date/status/productivity/delay/recovery) | 날짜별 카드 (days max 90) |
| 7 | `/api/dashboard/performance` | GET | 583 | `pg.fetch_one(_DASHBOARD_PERFORMANCE_SQL)` | `{productivity_today, delay_days, recoverable_days, abnormal_trades}` | fleet KPI 카드 |
| 8 | `/api/dashboard/impact` | GET | 643 | `pg.fetch_all(_DASHBOARD_IMPACT_SQL)` | `ImpactSiteDistribution[]` | site 별 hours_saved bar |
| 9 | `/api/agents/status` | GET | 729 | 7× `pg.fetch_all(_AGENT_ACTIVE_COUNT_SQL, node_name)` | `AgentStatus[]` (7 agent + meta) | "에이전트 현황" 카드 |
| 10 | `/api/sites/{site_id}/wbs_tree` | GET | 832 | `pg.fetch_all(_WBS_TREE_SQL)` | `WBSNode` 트리 (building→trade→work_package) | WBS 사이드바 |
| 11 | `/api/tasks` | GET | 1045 | `pg.fetch_all(_TASKS_SQL …)` + `pg.fetch_all(_TASKS_ITEMS_SQL …)` | `{tasks, progressByDate, itemsByDate}` | "작업일보 처리 현황" 페이지 |
| 12 | `/export/run` | GET | exporter_routes.py:16 | `fetch_site_by_id` + `fetch_sheet_data` (exporter.py) + `render_xlsx` | `Response` (xlsx bytes, `Content-Disposition` UTF-8) | "통합 작업일보 다운로드" 버튼 |

`/api/sites` SQL (`api.py:279`) — `sites LEFT JOIN LATERAL forecasts WHERE run_id=s.last_run_id` 로 마지막 run 의 max(today_productivity), abnormal_trades count, max(expected_completion), max(delay_days) 집계.

`/api/dashboard/performance` SQL (`api.py:562`) — `recoverable_days` 가 `(d+1)*1 + (d+2)*2 + (d+3)*3 + (d+5)*5 + (d+7)*7` weighted sum, `not_recovered` 는 무가중치.

`/api/agents/status` — 7 agent 메타 hard-coded (`_AGENTS_META` `api.py:662`), 각각 `SELECT COUNT(*) FROM pipeline_runs WHERE current_node = $1 AND status NOT IN ('completed','failed')` — 즉 **N+1 7회** (이슈 §12).

---

## 6. lifespan — `api.py:147` `lifespan(app)`

순서대로:

1. `pg_url = os.getenv("POSTGRES_URL")` — 미설정 시 `RuntimeError` (보안 차원, fail-fast).
2. `pg = PGClient(pg_url); await pg.connect()` → `app.state.pg`.
3. `cfg = _build_prod_graph_config()` — env 로 5 agent (atomizer/mapper/forecaster/optimizer/reporter) config 조립.
4. `graph = build_graph(cfg)` — 내부에서 `build_checkpointer()` 호출 → Lazy AsyncPostgresSaver wrap.
5. `app.state.graph = graph`, `app.state.cfg = cfg`.
6. **Collector idle (선택, 본 cycle `4b8a955` 신규)**: `load_collector_config(graph_cfg=cfg)` → `collector_cfg.enabled` True 면 `asyncio.create_task(idle_loop(collector_cfg))` 백그라운드 spawn. spec §10 fail-fast — `try/except` swallow 금지. POSTGRES_URL 누락은 위 step 1 이 먼저 잡음. `COLLECTOR_ENABLED=true` + 자격증명 누락은 `load_collector_config` 가 RuntimeError. 기본은 `enabled=False` → task 없음.
7. `yield`.
8. **shutdown**: collector_task 가 있으면 `request_shutdown()` flag → `collector_task.cancel()` → `await collector_task` (CancelledError swallow) → `await pg.close()`.

`app = FastAPI(lifespan=lifespan)` 생성 후 `app.include_router(exporter_router)` (api.py:203, 본 cycle `4b8a955`) — `/export` prefix 의 router 가 main app 에 결합.

---

## 7. `exporter_routes.py` — `/export/run`

47 LOC. 흐름:

```
GET /export/run?site_id=<X>&date=YYYY-MM-DD
  ├─ date parse (ValueError → 400 "date must be YYYY-MM-DD")
  ├─ PGClient(os.environ["POSTGRES_URL"]).connect()
  │   * ⚠️ 매 요청마다 신규 pool — app.state.pg 미재사용 (이슈 §12)
  ├─ fetch_site_by_id(pg, site_id) — None → 404
  ├─ fetch_sheet_data(pg, site_id, report_date) — exporter.py:34
  │     - 시트1 bp_summaries (parser_reports JOIN pipeline_runs)
  │     - 시트2 job_allocations (동상)
  │     - 시트3 equipment_allocations (동상)
  │     - 시트4 parser_activities 전체 (JOIN pipeline_runs, ORDER BY run_id, idx)
  │     - 0 row 시 NoDataError → 400
  ├─ pg.close()  (finally)
  ├─ render_xlsx(data, report_date, project=site["name"]) — bytes
  └─ Response(xlsx_bytes, media_type=…)
       * Content-Disposition 헤더 — UTF-8 한글 파일명 raw_headers 직접 주입
         (starlette Response(headers=…) 가 latin-1 인코딩 실패 회피)
```

`pipeline_runs JOIN parser_reports` 가 본 endpoint 의 grain 키 — `site_id, report_date` 의 모든 run 합집합 (한 현장의 N 업체 일보 통합).

---

## 8. Chroma collections — `chroma_client.py`

`ChromaClient.__init__(host, port=8000, ssl=False)` 가 `chromadb.HttpClient` wrap. 35 LOC.

### 8.1 `wbs_master` (`get_or_create_wbs_master`, `chroma_client.py:23`)

- **metadata**: `{"hnsw:space": "cosine"}`
- **1 doc = 1 (WA, L6) 그룹** (mapping-layer.md §5.2 형식).
- **add**: `scripts/load_wbs_master.py` (외부, 1회 적재 ~189 doc) — db.py 미관여.
- **query**: `pipeline/agents/mapper.py` (rerank candidate fetch) — `Mapper.map_activity` step 3.

### 8.2 `daily_activities` (`get_or_create_daily_activities`, `chroma_client.py:30`)

- **metadata**: 동상.
- **1 doc = 1 Activity** (시트4 line). `doc text = work_content`.
- **add**: `pipeline/graph.py:330` atomizer_node — `coll.add(ids, documents, embeddings, metadatas)`.
- **query**:
  - Forecaster RAG (`pipeline/agents/forecaster/retrieve.py`)
  - Optimizer retrieve (`pipeline/agents/optimizer/retrieve.py` — `fetch_degradation_cases`, `fetch_recovery_trajectory`)

---

## 9. AsyncPostgresSaver checkpoint — `checkpointer.py`

### 9.1 `build_checkpointer()` 분기 (`checkpointer.py:78`)

```python
if os.environ.get("CPIA_CHECKPOINTER", "postgres") == "memory":
    return InMemorySaver()
postgres_url = os.environ.get("POSTGRES_URL")
if not postgres_url:
    return InMemorySaver()  # safe fallback
return _LazyAsyncPostgresSaver(postgres_url)
```

unit test 는 `CPIA_CHECKPOINTER=memory` 로 InMemory 사용, prod 는 default `postgres` + 환경변수 존재 시 lazy PG.

### 9.2 `_LazyAsyncPostgresSaver` (`checkpointer.py:30`)

- `AsyncPostgresSaver` 상속 (LangGraph `isinstance(BaseCheckpointSaver)` 검사 통과).
- `__init__` 안에서 `AsyncConnectionPool(postgres_url, kwargs={"autocommit": True}, max_size=10, open=False)` — `open=False` 핵심: sync init 안에서 `await pool.open()` 호출 불가.
- 5 async method (`aput`, `aget_tuple`, `aput_writes`, `alist`, `aget`) 가 첫 호출 시 `_ensure_open()` → `await self._lazy_pool.open()` → `_opened=True` 마킹.

### 9.3 checkpoint 사용 흐름

1. graph compile 시 `.compile(checkpointer=build_checkpointer())` — `pipeline/graph.py:514` 부근.
2. graph.ainvoke 호출 시 `config={"configurable": {"thread_id": run_id}}` 주입 (`api.py:253`).
3. mapper_node 이후 `interrupt(...)` 호출 → graph state freeze → `checkpoints` 테이블 row INSERT.
4. `POST /api/runs/{run_id}/hil_1/resume` 가 `Command(resume=corrections_payload)` 으로 ainvoke 재호출 → AsyncPostgresSaver 가 `aget_tuple` 로 state 복원 → hil_1_node 가 `corrections` 받아 진행.

`thread_id` = `run_id` (uuid str) — 1 run 당 1 thread.

---

## 10. `upsert_daily_report_view_col` 상세 (`db.py:1062`)

### 10.1 문제

`daily_reports` 의 partial unique index `(run_id, site_id, report_date) WHERE site_id IS NOT NULL` 는 ON CONFLICT 와 안정 매칭 안 됨 — PostgreSQL 의 partial idx + ON CONFLICT inference 가 까다로움. 그래서 UPDATE-first 패턴으로 회피.

### 10.2 흐름

```python
if col not in self._VIEW_JSONB_COLS:
    raise ValueError(f"col '{col}' not in whitelist {self._VIEW_JSONB_COLS}")
# 9 컬럼 화이트리스트 가드 — f-string 으로 컬럼명 주입하므로 SQL injection 방어 필수.

async with self._pool.acquire() as con:
    row_count = await con.fetchval(
        f"""
        UPDATE daily_reports
        SET {col} = $4::jsonb
        WHERE run_id = $1 AND site_id = $2 AND report_date = $3
        RETURNING id
        """,
        run_id, site_id, report_date,
        _json.dumps(value, ensure_ascii=False, default=str),
    )
    if row_count is None:
        await con.execute(
            f"""
            INSERT INTO daily_reports (run_id, site_id, report_date, report_md, {col})
            VALUES ($1, $2, $3, '', $4::jsonb)
            """,
            run_id, site_id, report_date,
            _json.dumps(value, ensure_ascii=False, default=str),
        )
```

### 10.3 화이트리스트 9 컬럼

```
kpi_jsonb           contractor_bars_jsonb   trade_bars_jsonb
quadrant_jsonb      wp_summary_jsonb        s_curve_jsonb
optimizer_view_jsonb productivity_jsonb     scenarios_jsonb
```

### 10.4 산식 / 호출 순서

`optimizer/agent.py:220` 가 1 cycle 안에서 위 9 col 각각 1 회 호출 — optimizer view_builder 가 9 jsonb 산출 → 각 col 별 partial write. 한 col 실패해도 나머지 8 col 유지 (atomicity weak, 의도).

`insert_daily_report` (`db.py:405`) 도 같은 UPDATE-first 패턴 사용 — optimizer 가 row 먼저 만들고 reporter 가 뒤늦게 호출되는 경우 (UniqueViolation 회피).

---

## 11. migration 누적 목록 (21 파일, 시간순)

| 파일 | 한 줄 요지 |
|---|---|
| `20260516_add_activity_master.sql` | `activity_master` 신설 (WBS Master List 테이블, ~189 row/site) |
| `2026-05-16_downstream_agents.sql` | `pipeline_runs.atomized_count` + `forecasts` DROP+CREATE + `optimizer_advice` `trade`→`l6_main` rename |
| `2026-05-16_forecaster.sql` | `forecasts` 13 컬럼 추가 (qty_by_unit/productivity/plan_*/window/mh_gap/recovery_likelihood) + `delay_days` INT→NUMERIC |
| `2026-05-16_optimizer_hil2.sql` | `optimizer_advice` 4 컬럼 추가 (company/forecast_assessment/degradation_cases/recovery_distribution) + `recommendations` TEXT→JSONB ; `forecasts` `main_unit`/`today_conditions` |
| `2026-05-17_activity_master_site_id.sql` | `activity_master.site_id NOT NULL` + PK 재구성 (`(site_id, wbs_activity_id)`) + 3 index |
| `2026-05-17_activity_master_wa.sql` | `activity_master.wa TEXT` (prod alignment) |
| `2026-05-17_db_alignment.sql` | `sites` 4 컬럼 (`location`/`headcount`/`hours_saved`/`fte_saved`) |
| `2026-05-18_forecasts_wa.sql` | `forecasts.wa` + index 재구성 (`(wa, company, l6_main)`) |
| `2026-05-18_mapped_history.sql` | `mapped_history` 신설 — UNIQUE `(run_id, wa, l6_main, company)` |
| `2026-05-18_parser_mapper_outputs.sql` | `parser_reports` + `parser_activities` + `mapper_activities` 3 테이블 신설 (시트1~3 jsonb + 시트4 정규화 + Mapper enrich) |
| `2026-05-19_collector_inbox.sql` | **`collector_inbox` 신설** (PK message_id + CHECK parse_status + partial idx) |
| `2026-05-19_daily_reports_views.sql` | `daily_reports` 8 view jsonb + `site_id` (partial unique idx) ; `mapper_activities` `cum_workers_today`/`cum_actual_mh_today` |
| `2026-05-19_mapped_history_trade.sql` | `mapped_history.trade TEXT` (FE Activity.trade source) |
| `2026-05-19_mapper_alternatives.sql` | `mapper_activities.alternatives JSONB GIN` (review modal dropdown) |
| `2026-05-19_parser_full_schema.sql` | `parser_activities` 13 컬럼 확장 + `mapper_activities` 13 컬럼 확장 + `parser_job_allocations` / `parser_equipment_allocations` / `parser_worker_outputs` / `parser_report_meta` 4 테이블 신설 |
| `2026-05-19_scenarios_jsonb.sql` | `daily_reports.scenarios_jsonb` (4 시나리오 예측) |
| `2026-05-19_sites_hours_saved_cum.sql` | `sites.hours_saved_cum NUMERIC NOT NULL DEFAULT 0` (G2 KPI) |
| `2026-05-20_add_is_mock.sql` | **7 테이블 `is_mock BOOL NOT NULL DEFAULT FALSE`** (pipeline_runs / parser_reports / parser_activities / mapper_activities / forecasts / optimizer_advice / daily_reports) — mock fallback 인프라 |
| `2026-05-21_phase1.sql` | `prototype_embedding_cache` + `mapped_history_merge_log` 2 테이블 신설 (L7.5 임베딩 캐시 + merge audit) |
| `2026-05-23_mapper_l7_5_columns.sql` | **`mapper_activities` 4 컬럼 (`l5_disc`/`l7_sub`/`l7_5_activity`/`sub_work_area`)** — activity_master 의 L7.5 / L5 propagate |
| (commit 메시지만) `daily_reports.site_summary_text TEXT` | commit `21c10f7` 가 PG migration "추가" 라 적시했으나 **migration 파일 부재** — runtime ALTER 로만 적용된 상태. dev DB rebuild 시 누락 위험 (이슈 §12 #1) |

본 cycle (ef7c6cd → 1ba783f) 신규: `2026-05-19_collector_inbox.sql`, `2026-05-20_add_is_mock.sql`, `2026-05-21_phase1.sql`, `2026-05-23_mapper_l7_5_columns.sql` (4 개) + 본 cycle 외부 (B_Track) merge 로 가져온 site_summary_text (migration 파일 없음).

---

## 12. 이슈 표

### 12.1 Critical

| # | 이슈 | 위치 | 영향 | 근거 |
|---|---|---|---|---|
| C1 | `daily_reports.site_summary_text` 컬럼이 commit `21c10f7` 에서 "PG migration 추가" 로 언급됐으나 `infra/postgres/migrations/` 에 해당 SQL 파일 부재 | `daily_reports`, 호출 — `scripts/backfill_daily_report_views_v2.py:162`, `pipeline/agents/optimizer/site_summary.py` | fresh DB rebuild 시 `UPDATE … SET site_summary_text = $1` UndefinedColumnError. AWS 마이그 cycle 에서만 살아남음 (이미 ALTER 적용된 dump 사용) | `git show 21c10f7 --stat` 에 sql 파일 없음 (commit 메시지만 있음) |
| C2 | `/export/run` endpoint 가 매 요청마다 `PGClient(os.environ["POSTGRES_URL"]).connect()` 신규 풀 생성 + close — `app.state.pg` 재사용 안 함 | `exporter_routes.py:23-34` | 요청당 connection handshake / TLS overhead, 동시 N 요청 시 pool 폭증, POSTGRES_URL env 누락 시 KeyError 500 | `api.py:163` 이미 `app.state.pg` 보유 — Depends 주입으로 재사용 가능 |
| C3 | `insert_mapped_history_batch` ON CONFLICT DO UPDATE 가 `today_qty / today_assigned_workers / unit` 만 갱신, **`trade` 컬럼 누락** | `db.py:478~487` | 같은 (run_id, wa, l6_main, company) 재호출 시 trade 가 최초값으로 고정 — 후속 cycle 에 trade 보정 불가 | `db.py:480-487` SET 절에 trade 없음 |

### 12.2 Medium

| # | 이슈 | 위치 | 영향 | 근거 |
|---|---|---|---|---|
| M1 | `/api/agents/status` 가 7 agent meta 마다 `SELECT COUNT(*) FROM pipeline_runs WHERE current_node=$1 …` 호출 — 7× round-trip | `api.py:741-744` loop | agent 추가 시 N+1 선형 증가. 단일 SQL `GROUP BY current_node` 로 1 회 호출 가능 | `api.py:721` `_AGENT_ACTIVE_COUNT_SQL` 가 single-node SELECT 임 |
| M2 | `_SITES_SQL` LATERAL forecasts (`api.py:279`) — 모든 sites row 마다 LATERAL subquery 실행 | `api.py:279-298` | sites 6 row 규모는 OK. 확장 시 `EXPLAIN ANALYZE` 검토 필요. forecast index `idx_forecasts_run` 활용 가능. | mock 6 site 기준 `pg.fetch_all` 1 회 |
| M3 | `fetch_activity` (`db.py:73`) 호출자 코드 부재 — test 만 호출 | grep `insert_/fetch_/update_` 에 fetch_activity 무 hit | dead code. mapper rerank 에 통합 검토 필요 | `grep -rnE "fetch_activity\b" pipeline/agents pipeline/graph.py` 결과 0건 |
| M4 | `_VIEW_JSONB_COLS` 화이트리스트 — `site_summary_text` 미포함이므로 view col 통합 불가, separate UPDATE 경로 필요 (script 가 직접 SQL 작성) | `db.py:1050`, `scripts/backfill_daily_report_views_v2.py:162` | text 컬럼이라 jsonb 화이트리스트와 분리 정당하나, 별도 helper 부재로 inline SQL 산재 | scripts 가 raw `UPDATE daily_reports SET site_summary_text = $1 …` |
| M5 | `parser_reports` / `parser_activities` 등 11 테이블은 init.sql 미포함, migration 파일만 — fresh dev DB 부팅 시 21 migration 순차 적용 강제 | `infra/postgres/init.sql` vs `migrations/` 정합 안 됨 | 신규 개발자 셋업 시 README/Compose entrypoint 가 migration 자동 적용 보장 필요 | init.sql 에 7 테이블만, migration 만 보면 14 테이블 추가 |
| M6 | `checkpointer.py:78` `build_checkpointer` 가 `POSTGRES_URL` 없으면 silently InMemorySaver fallback — prod 환경에서 PG 미설정 사고 시 검출 어려움 (lifespan §6 step 1 이 fail-fast 이지만 graph compile 시점에 별도 fallback) | `checkpointer.py:90-92` | prod 에서 checkpointer 가 메모리로 떨어지면 H-i-L resume 가 process restart 시 손실 | lifespan 의 POSTGRES_URL RuntimeError 가 먼저 잡히긴 함, 하지만 build_checkpointer 단독 호출 (test 등) 시 위험 |
| M7 | `/api/tasks` items 가 `itemsByDate[date]["Collector"]` hard-coded — current_node 기반 agent 라우팅 미구현 | `api.py:986-1042` `_build_items_by_date` docstring 명시 PoC 단순화 | FE "Collector" 탭 외 표시 안 됨 | `result[date_val] = {"Collector": []}` hardcode |

### 12.3 Low / 메모

- `api_helpers/` 디렉토리에 추적 모듈 없음, pycache 만 잔존 → `git clean` / 디렉토리 제거 안전.
- `infra/postgres/init.sql` 헤더 주석 "스키마 변경은 ALTER TABLE 직접 X. migration 으로 누적" — 본 cycle 의 site_summary_text 누락이 유일한 위반 (C1).
- `forecasts` `DROP TABLE IF EXISTS` 가 `2026-05-16_downstream_agents.sql:9` 에 있음 — PoC 단계 가정. prod replay 시 데이터 삭제 위험 (현재 idempotent IF EXISTS 라 두 번 돌리면 첫 DROP 후 두 번째 DROP 무 영향, 하지만 dev 의 의도하지 않은 재실행은 데이터 손실).

---

## 13. 본 cycle (ef7c6cd → 1ba783f) 변경 요약

| Commit | 파일 | 변경 |
|---|---|---|
| `b614bff` | 7 테이블 (`2026-05-20_add_is_mock.sql`) | `is_mock BOOL NOT NULL DEFAULT FALSE` — mock fallback 인프라 |
| `a3db32a` | 다수 | 78사 통합일보 1 cycle 정상 적재까지 7개 fix + cleanup script |
| `3db3d18` | `2026-05-21_phase1.sql` | `prototype_embedding_cache` + `mapped_history_merge_log` 신설 |
| `7b96b1a` | `2026-05-19_collector_inbox.sql` + `db.py:1145~1217` | `collector_inbox` 테이블 + 4 module helper (`insert_collector_inbox`, `update_collector_inbox_status`, `fetch_collector_inbox_by_message_id`, `fetch_site_by_id`) |
| `a7e2465` | `pipeline/exporter_routes.py` (신규 47 LOC) | `/export/run` xlsx endpoint — PGClient ad-hoc + httpx 통합 테스트 |
| `b3010df` | `pipeline/agents/exporter.py:34` | `fetch_sheet_data` PG SELECT (pipeline_runs JOIN parser_reports + parser_activities) — 시트 1~4 합집합 |
| `4b8a955` | `pipeline/api.py:147,203` (+23 line) | lifespan 안 collector idle task spawn + `app.include_router(exporter_router)` |
| `415c990` | (FE 만 — web/) | Export/Reports/Review list/detail 분할 + N+1 제거 — BE schema 무변경 |
| `7e9e1a1` | merge (`21c10f7` 포함) | `daily_reports.site_summary_text` runtime ALTER + LLM site narrative (BE py + scripts + FE 만, migration 부재 — 이슈 C1) |
| `d40c84f` | `2026-05-23_mapper_l7_5_columns.sql` + `db.py:639~765` | `mapper_activities` 에 `l5_disc` / `l7_sub` / `l7_5_activity` / `sub_work_area` 4 컬럼 추가 — activity_master propagate (spec §8/§9 plan 누락 fix, 회귀 6건 해소) |

총 변경 (이 서브시스템 한정): `db.py` +120 LOC (385→1229 누적 중 본 cycle 분), `api.py` +23 LOC (1050→1073), `exporter_routes.py` +47 (신규), migration +4 파일.

---

## 14. 관련 (다른 deep-dive 페이지)

- `architecture_overview.md` §3.1 — PG 17 테이블 baseline 카탈로그 (본 페이지가 갱신).
- `design-intent/design_intent_collector.md` — `collector_inbox` 의 IMAP IDLE 생산자 측 디자인 의도 (collector_node 호출 관점).
- `design-intent/design_intent_mapper.md` — `mapper_activities` 의 alternatives / cum_workers 산출 측.
- `design-intent/design_intent_optimizer.md` — `upsert_daily_report_view_col` 의 9 jsonb 화이트리스트 호출 측 + `site_summary_text` LLM 산출.
- `design-intent/design_intent_exporter.md` — `/export/run` 흐름의 xlsx render 측 (exporter.py:290 `render_xlsx`).
