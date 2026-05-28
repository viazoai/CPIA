# CPIA Backend 데이터 카탈로그 (A_Track pipeline/)

> **재생성**: 2026-05-26 cycle (`ef7c6cd → 1ba783f`). 전수 재작성 (이전 412 줄 카탈로그 폐기).
> **Source of truth**: `deep-dive/deep_dive_persistence.md` (655 줄, 2026-05-26).
> 본 카탈로그는 FE↔BE crosswalk (`./crosswalk.md`) 의 input 으로 동작한다.
> 모든 row 의 Location = `file:line` grep / migration sql 확인 / 실 PG schema 확인 결과.
>
> **본 cycle BE 핵심 변경 (★ NEW)**:
> 1. 신규 테이블 `collector_inbox` (5-19 migration) — Gmail IMAP IDLE dedup.
> 2. 신규 테이블 `prototype_embedding_cache` + `mapped_history_merge_log` (5-21 phase1).
> 3. 신규 컬럼 `daily_reports.site_summary_text` — **migration 파일 부재 (이슈 #N13)**.
> 4. 신규 컬럼 `mapped_history.trade` (5-19 migration) — **atomizer INSERT 누락 (이슈 #C3)**.
> 5. 신규 컬럼 `mapper_activities.l5_disc / l7_sub / l7_5_activity / sub_work_area` (5-23 migration).
> 6. 7 테이블 `is_mock BOOL NOT NULL DEFAULT FALSE` backfill (5-20 migration).
> 7. 신규 endpoint `GET /export/run` — `pipeline/exporter_routes.py:16` (47 LOC).
> 8. lifespan 변경 — `api.py:147` 안에서 collector idle task spawn + `app.include_router(exporter_router)` (api.py:203).
> 9. 9 jsonb view 산식 변경 — 산식 A (WV × MH 가중) `view_builder.py:880~1021`, MEDIAN fix `view_builder.py:296~309`, scenarios 4 percentile `view_builder.py:1239~1241`, v1 ↔ v2 drift.
> 10. site_summary LLM — `pipeline/agents/optimizer/site_summary.py` (141 LOC) → `daily_reports.site_summary_text`.

---

## 표 스키마

모든 source row 는 다음 6 컬럼 의 표로 정리:

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|

- **Kind**: `pg_column` / `pg_jsonb_key` / `state_attr` / `dataclass_field` / `api_endpoint` / `derived_metric` / `chroma_meta` / `langgraph_ckpt`.
- **Location**: 가장 강한 source 위치 (`file:line`). 다중 시 1차 위치.
- **본 cycle**: ★ NEW (본 cycle 신규) / ★ MOD (본 cycle 수정) / 빈칸 (변경 없음).

---

## §A. PG 도메인 테이블 (17 user + 3 ckpt + collector_inbox + 2 phase1 = 21 테이블)

### §A.1 `pipeline_runs` — 파이프라인 실행 단위

소스: `infra/postgres/init.sql:13` + `2026-05-16_downstream_agents.sql:6` (atomized_count) + `2026-05-20_add_is_mock.sql:534`.

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| pipeline_runs.run_id | pg_column | infra/postgres/init.sql:14 | UUID PK (uuid_generate_v4) | FastAPI `/run` (사전 INSERT) + test fixture | PK | |
| pipeline_runs.site_id | pg_column | infra/postgres/init.sql:15 | TEXT | (외부) | | |
| pipeline_runs.report_date | pg_column | infra/postgres/init.sql:16 | DATE NOT NULL | (외부) | idx_pipeline_runs_date | |
| pipeline_runs.status | pg_column | infra/postgres/init.sql:17 | TEXT NOT NULL CHECK (`running`/`waiting_hil_1`/`waiting_hil_2`/`completed`/`failed`) | INSERT 시 `running` (db.py:163) — UPDATE path 부재 (drift §M-status) | idx_pipeline_runs_status | |
| pipeline_runs.current_node | pg_column | infra/postgres/init.sql:19 | TEXT | atomizer 시점에만 `atomizer` 박힘 (db.py:251) — 다른 node 미설정 (drift §M-status) | | |
| pipeline_runs.error | pg_column | infra/postgres/init.sql:20 | TEXT | (미사용) | | |
| pipeline_runs.atomized_count | pg_column | infra/postgres/init.sql:21 (+ migrations/2026-05-16_downstream_agents.sql:6) | INTEGER DEFAULT 0 | atomizer 종료 (db.py:251) | | |
| pipeline_runs.started_at | pg_column | infra/postgres/init.sql:22 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | INSERT 시 | | |
| pipeline_runs.completed_at | pg_column | infra/postgres/init.sql:23 | TIMESTAMPTZ | (UPDATE helper 부재 — drift §M-status) | | |
| pipeline_runs.is_mock | pg_column | migrations/2026-05-20_add_is_mock.sql:534 | BOOL NOT NULL DEFAULT FALSE | mock seed scripts | | ★ NEW |

**Index**: `idx_pipeline_runs_date` (`report_date DESC`, init.sql:26), `idx_pipeline_runs_site` (`site_id, report_date DESC`, init.sql:27), `idx_pipeline_runs_status` (`status`, init.sql:28).

### §A.2 `sites` — Dashboard Layer 1 카드 source

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| sites.site_id | pg_column | init.sql:142 | TEXT PK | mock seed | PK | |
| sites.name | pg_column | init.sql:143 | TEXT NOT NULL | mock seed | | |
| sites.plan_progress | pg_column | init.sql:144 | NUMERIC(5,2) | mock seed | | |
| sites.actual_progress | pg_column | init.sql:145 | NUMERIC(5,2) | mock seed | | |
| sites.status | pg_column | init.sql:146 | TEXT CHECK (`normal`/`caution`/`risk`/`unknown`) DEFAULT `unknown` | mock seed | | |
| sites.last_run_id | pg_column | init.sql:147 | UUID FK pipeline_runs ON DELETE SET NULL | `update_site_last_run` (db.py:1109) — graph.py:473 reporter→END | | |
| sites.is_mock | pg_column | init.sql:148 | BOOL NOT NULL DEFAULT TRUE | mock seed (sites 만 default TRUE) | | |
| sites.location | pg_column | migrations/2026-05-17_db_alignment.sql:179 | TEXT | mock seed | | |
| sites.headcount | pg_column | migrations/2026-05-17_db_alignment.sql:180 | INT | mock seed | | |
| sites.hours_saved | pg_column | migrations/2026-05-17_db_alignment.sql:181 | NUMERIC | mock seed | | |
| sites.fte_saved | pg_column | migrations/2026-05-17_db_alignment.sql:182 | NUMERIC | mock seed | | |
| sites.hours_saved_cum | pg_column | migrations/2026-05-19_sites_hours_saved_cum.sql:522 | NUMERIC NOT NULL DEFAULT 0 (시간 h) | `update_site_hours_saved_cum` (db.py:1125, 산식 `(120-5)/60 × atomized_count`) | | |
| sites.updated_at | pg_column | init.sql:154 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | UPDATE 시 NOW() | | |

**SELECT**: `_SITES_SQL` (api.py:279) LATERAL forecasts JOIN, `_DASHBOARD_IMPACT_SQL` (api.py:622), `fetch_site_by_id` (db.py:1220).

### §A.3 `activity_master` — WBS Master List

복합 PK `(site_id, wbs_activity_id)` — `migrations/2026-05-17_activity_master_site_id.sql:138` 가 단일 PK 재구성.

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| activity_master.site_id | pg_column | migrations/2026-05-17_activity_master_site_id.sql:128 | TEXT NOT NULL | scripts/load_master_list.py | PK 일부 | |
| activity_master.wbs_activity_id | pg_column | migrations/20260516_add_activity_master.sql:596 | TEXT NOT NULL | scripts/load_master_list.py | PK 일부 | |
| activity_master.wa | pg_column | migrations/2026-05-17_activity_master_wa.sql:169 | TEXT | scripts/load_master_list.py | idx_actmaster_wa_l6 | |
| activity_master.l5_disc | pg_column | migrations/20260516_add_activity_master.sql:599 | TEXT NOT NULL | scripts/load_master_list.py | idx_actmaster_lookup, idx_actmaster_site_l6 | |
| activity_master.l6_main | pg_column | migrations/20260516_add_activity_master.sql:600 | TEXT | scripts/load_master_list.py | | |
| activity_master.l6_code | pg_column | migrations/20260516_add_activity_master.sql:601 | TEXT | scripts/load_master_list.py | | |
| activity_master.l7_sub | pg_column | migrations/20260516_add_activity_master.sql:602 | TEXT | scripts/load_master_list.py | | |
| activity_master.l7_code | pg_column | migrations/20260516_add_activity_master.sql:603 | TEXT | scripts/load_master_list.py | | |
| activity_master.l7_5_activity | pg_column | migrations/20260516_add_activity_master.sql:604 | TEXT | scripts/load_master_list.py | | |
| activity_master.sub_work_area | pg_column | migrations/20260516_add_activity_master.sql:605 | TEXT | scripts/load_master_list.py | | |
| activity_master.company | pg_column | migrations/20260516_add_activity_master.sql:608 | TEXT | scripts/load_master_list.py | idx_actmaster_lookup, idx_actmaster_site_company | |
| activity_master.unit | pg_column | migrations/20260516_add_activity_master.sql:609 | TEXT | scripts/load_master_list.py | idx_actmaster_lookup | |
| activity_master.plan_total_qty | pg_column | migrations/20260516_add_activity_master.sql:612 | NUMERIC | scripts/load_master_list.py | | |
| activity_master.plan_mh_rev2 | pg_column | migrations/20260516_add_activity_master.sql:613 | NUMERIC | scripts/load_master_list.py | | |
| activity_master.plan_mh_rev1 | pg_column | migrations/20260516_add_activity_master.sql:614 | NUMERIC | scripts/load_master_list.py | | |
| activity_master.plan_mh_rev0 | pg_column | migrations/20260516_add_activity_master.sql:615 | NUMERIC | scripts/load_master_list.py | | |
| activity_master.plan_wv | pg_column | migrations/20260516_add_activity_master.sql:616 | NUMERIC | scripts/load_master_list.py | s_curve 분모 사용 (view_builder.py:899) | |
| activity_master.plan_start | pg_column | migrations/20260516_add_activity_master.sql:619 | DATE | scripts/load_master_list.py | idx_actmaster_period, idx_actmaster_site_period | |
| activity_master.plan_finish | pg_column | migrations/20260516_add_activity_master.sql:620 | DATE | scripts/load_master_list.py | idx_actmaster_period, idx_actmaster_site_period | |
| activity_master.actual_start | pg_column | migrations/20260516_add_activity_master.sql:623 | DATE | scripts/load_master_list.py | | |
| activity_master.actual_finish | pg_column | migrations/20260516_add_activity_master.sql:624 | DATE | scripts/load_master_list.py | | |
| activity_master.source_file | pg_column | migrations/20260516_add_activity_master.sql:627 | TEXT | scripts/load_master_list.py | | |
| activity_master.loaded_at | pg_column | migrations/20260516_add_activity_master.sql:628 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | scripts/load_master_list.py | | |

### §A.4 `forecasts` — Forecaster 산출 (28 컬럼)

`DROP+CREATE` (`migrations/2026-05-16_downstream_agents.sql:9`) → 4 차례 ALTER. INSERT helper `PGClient.insert_forecast` (`db.py:260`, $1~$28).

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| forecasts.id | pg_column | migrations/2026-05-16_downstream_agents.sql:12 | BIGSERIAL PK | (auto) | PK | |
| forecasts.run_id | pg_column | migrations/2026-05-16_downstream_agents.sql:13 | UUID NOT NULL FK pipeline_runs ON DELETE CASCADE | forecaster/agent.py:331 | idx_forecasts_run | |
| forecasts.company | pg_column | migrations/2026-05-16_downstream_agents.sql:14 | TEXT NOT NULL | forecaster row.company | idx_forecasts_wa_company_l6 | |
| forecasts.l6_main | pg_column | migrations/2026-05-16_downstream_agents.sql:15 | TEXT NOT NULL | forecaster row.l6_main | idx_forecasts_wa_company_l6 | |
| forecasts.wa | pg_column | migrations/2026-05-18_forecasts_wa.sql:188 | TEXT | forecaster row.wa (Phase 2 grain wa 추가) | idx_forecasts_wa_company_l6 | |
| forecasts.today_qty_by_unit | pg_column | migrations/2026-05-16_forecaster.sql:53 | JSONB | forecaster aggregate.py:18 | | |
| forecasts.today_assigned_workers | pg_column | migrations/2026-05-16_downstream_agents.sql:18 | NUMERIC | forecaster | | |
| forecasts.today_productivity | pg_column | migrations/2026-05-16_forecaster.sql:54 | NUMERIC | forecaster (max qty 단위 기준) | | |
| forecasts.main_unit | pg_column | migrations/2026-05-16_optimizer_hil2.sql:92 | TEXT | forecaster (max qty 단위 결정) | optimizer 재사용 (view_builder.py:1061) | |
| forecasts.today_conditions | pg_column | migrations/2026-05-16_optimizer_hil2.sql:93 | TEXT (comma-joined) | forecaster | optimizer 재사용 | |
| forecasts.plan_total_qty_by_unit | pg_column | migrations/2026-05-16_forecaster.sql:55 | JSONB | forecaster (db.py:fetch_plan_for_group) | | |
| forecasts.plan_mh_sum | pg_column | migrations/2026-05-16_downstream_agents.sql:21 | NUMERIC | forecaster | | |
| forecasts.plan_start | pg_column | migrations/2026-05-16_forecaster.sql:56 | DATE | forecaster | | |
| forecasts.plan_finish | pg_column | migrations/2026-05-16_forecaster.sql:57 | DATE | forecaster | | |
| forecasts.plan_mh_per_day | pg_column | migrations/2026-05-16_forecaster.sql:58 | NUMERIC | forecaster (`plan_mh_sum / (finish-start+1)`) | | |
| forecasts.schedule_state | pg_column | migrations/2026-05-16_forecaster.sql:59 | TEXT (`early`/`on_schedule`/`post_due`/`unknown`) | forecaster | idx_forecasts_state | |
| forecasts.window_start | pg_column | migrations/2026-05-16_forecaster.sql:60 | DATE | forecaster | | |
| forecasts.window_days | pg_column | migrations/2026-05-16_forecaster.sql:61 | INT | forecaster | | |
| forecasts.expected_in_window_mh | pg_column | migrations/2026-05-16_forecaster.sql:62 | NUMERIC | forecaster | | |
| forecasts.actual_in_window_mh | pg_column | migrations/2026-05-16_forecaster.sql:63 | NUMERIC | forecaster | | |
| forecasts.mh_gap | pg_column | migrations/2026-05-16_forecaster.sql:64 | NUMERIC | forecaster (`expected - actual`, 양수 = 부족) | | |
| forecasts.delay_days | pg_column | migrations/2026-05-16_forecaster.sql:67 | NUMERIC (INT→NUMERIC USING) | forecaster (`mh_gap / plan_mh_per_day`) | MEDIAN aggregator (view_builder.py:296) | |
| forecasts.rag_n_similar | pg_column | migrations/2026-05-16_downstream_agents.sql:23 | INT | forecaster | | |
| forecasts.similar_cases | pg_column | migrations/2026-05-16_downstream_agents.sql:24 | JSONB list[{date, productivity, conditions:list[str]}] | forecaster/retrieve.py | | |
| forecasts.assessment | pg_column | migrations/2026-05-16_downstream_agents.sql:26 | TEXT (`정상`/`주의`/`이상`/NULL) | forecaster code ④ | | |
| forecasts.reasoning | pg_column | migrations/2026-05-16_downstream_agents.sql:27 | TEXT | forecaster LLM (cold start = "데이터 부족 — ...") | | |
| forecasts.recovery_likelihood | pg_column | migrations/2026-05-16_forecaster.sql:65 | NUMERIC (0.0~1.0 or NULL) | forecaster code ⑥ | | |
| forecasts.expected_completion | pg_column | migrations/2026-05-16_downstream_agents.sql:28 | DATE (PoC: = plan_finish) | forecaster | scenarios `_coerce_date` (view_builder.py:1226) | |
| forecasts.risk_level | pg_column | migrations/2026-05-16_downstream_agents.sql:30 | TEXT (`정상`/`주의`/`이상`/NULL) | forecaster code ⑦ | idx_forecasts_risk PARTIAL (`risk_level <> '정상'`) | |
| forecasts.is_mock | pg_column | migrations/2026-05-20_add_is_mock.sql:538 | BOOL NOT NULL DEFAULT FALSE | mock seed | view_builder.py:203 `ma.is_mock = FALSE` 필터 | ★ NEW |
| forecasts.created_at | pg_column | migrations/2026-05-16_downstream_agents.sql:32 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | (auto) | | |

### §A.5 `optimizer_advice` — Optimizer 산출 (11 컬럼)

INSERT helper `PGClient.insert_optimizer_advice` (`db.py:332`, $1~$9 — `is_mock` 미설정, default FALSE).

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| optimizer_advice.id | pg_column | init.sql:108 | BIGSERIAL PK | (auto) | PK | |
| optimizer_advice.run_id | pg_column | init.sql:109 | UUID NOT NULL FK pipeline_runs ON DELETE CASCADE | optimizer/agent.py:182 | idx_optimizer_advice_run | |
| optimizer_advice.l6_main | pg_column | init.sql:110 (+ migrations/2026-05-16_downstream_agents.sql:40 rename `trade → l6_main`) | TEXT NOT NULL | optimizer row.l6_main | idx_optimizer_advice_company_l6 | |
| optimizer_advice.company | pg_column | migrations/2026-05-16_optimizer_hil2.sql:81 | TEXT | optimizer row.company | idx_optimizer_advice_company_l6 | |
| optimizer_advice.diagnosis | pg_column | init.sql:112 | TEXT (LLM 또는 `cold_start`) | optimizer (agent.py:67,82) | | |
| optimizer_advice.forecast_assessment | pg_column | migrations/2026-05-16_optimizer_hil2.sql:82 | TEXT (`주의`/`이상`) | optimizer | | |
| optimizer_advice.recovery_pattern | pg_column | init.sql:114 | JSONB list[{date, recovery_days}] (degradation_cases 와 1:1 mirror) | optimizer (agent.py:69 cold=[], :76) | s_curve 의 4번째 곡선 (view_builder.py:984) | |
| optimizer_advice.degradation_cases | pg_column | migrations/2026-05-16_optimizer_hil2.sql:83 | JSONB list[{date, productivity, conditions:str, assigned_workers, activities, recovery:{trajectory,recovery_days}}] | optimizer (pre_cases 그대로) | optimizer_view_jsonb 생성 input | |
| optimizer_advice.recovery_distribution | pg_column | migrations/2026-05-16_optimizer_hil2.sql:84 | JSONB dict[str,int] (`d+N` / `not_recovered`) | optimizer `_compute_recovery_distribution` | scenarios `_expand_recovery_to_days` (view_builder.py:1154), `_DASHBOARD_PERFORMANCE_SQL` weighted sum (api.py:569) | |
| optimizer_advice.recommendations | pg_column | init.sql:117 (+ migrations/2026-05-16_optimizer_hil2.sql:85 TEXT→JSONB) | JSONB list[{rank, text}] (cold=[]) | optimizer LLM | site_summary `top_recommendation` (site_summary.py:97) | |
| optimizer_advice.is_mock | pg_column | migrations/2026-05-20_add_is_mock.sql:539 | BOOL NOT NULL DEFAULT FALSE | mock seed | | ★ NEW |
| optimizer_advice.created_at | pg_column | init.sql:118 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | (auto) | | |

### §A.6 `mapping_corrections` — HIL 1 누적 (6 컬럼)

INSERT helper `PGClient.insert_mapping_correction` (`db.py:370`) — graph.py:265 hil_1_node 호출.

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| mapping_corrections.id | pg_column | init.sql:128 | BIGSERIAL PK | (auto) | PK | |
| mapping_corrections.run_id | pg_column | init.sql:129 | UUID FK pipeline_runs ON DELETE SET NULL (nullable) | hil_1_node (graph.py:265) | | |
| mapping_corrections.report_date | pg_column | init.sql:130 | DATE NOT NULL | hil_1_node | idx_mapping_corrections_date | |
| mapping_corrections.original | pg_column | init.sql:131 | JSONB NOT NULL `{wa, l6_main, mapping_conf, mapping_source, work_content, company, trade}` | hil_1_node (graph.py:143-152) | | |
| mapping_corrections.corrected | pg_column | init.sql:132 | JSONB NOT NULL `{wa, l6_main, mapping_source="user_corrected", correction_type="replace"}` | hil_1_node (graph.py:153-159) | | |
| mapping_corrections.created_at | pg_column | init.sql:133 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | (auto) | | |
| mapping_corrections.is_mock | pg_column | migrations/2026-05-20_add_is_mock.sql (전수) | BOOL NOT NULL DEFAULT FALSE | mock seed | | ★ NEW |

> **Spec drift** (carried): postgres.md §8 spec 의 top-level 컬럼 (work_content/company/trade/correction_type) → 실 schema 6 컬럼만 (db.py:380~389 docstring 자인). `original` / `corrected` JSONB 안에 합쳐서 박는 우회 path.

### §A.7 `daily_reports` — Reporter + Optimizer view (19 컬럼)

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| daily_reports.id | pg_column | init.sql:34 | BIGSERIAL PK | (auto) | PK | |
| daily_reports.run_id | pg_column | init.sql:35 | UUID NOT NULL FK pipeline_runs ON DELETE CASCADE | reporter (db.py:405) / optimizer (db.py:1062) | idx_daily_reports_run | |
| daily_reports.site_id | pg_column | migrations/2026-05-19_daily_reports_views.sql:325 | TEXT (FK 미선언) | reporter (db.py:425 pipeline_runs lookup) | daily_reports_run_site_date_uq PARTIAL UNIQUE (`(run_id, site_id, report_date) WHERE site_id IS NOT NULL`) | |
| daily_reports.report_date | pg_column | init.sql:36 | DATE NOT NULL | reporter | idx_daily_reports_date | |
| daily_reports.bp_name | pg_column | init.sql:37 | TEXT | reporter | | |
| daily_reports.report_md | pg_column | init.sql:38 | TEXT NOT NULL | reporter (graph.py:329) | | |
| daily_reports.history_csv_row | pg_column | init.sql:39 | JSONB `{total_workers, total_qty_by_trade, risk_counts, advice_count}` (컬럼명 ↔ 실 값 drift) | reporter (reporter.py:107-112) | | |
| daily_reports.kpi_jsonb | pg_column | migrations/2026-05-19_daily_reports_views.sql:315 | JSONB DEFAULT `{}` `{productivity_today, spi, cpi, target_productivity, delay_days, expected_completion, recovery_days, recovered_completion, ...}` | view_builder `_build_kpi` (view_builder.py:284) / v2 `_build_productivity_views_v2` (view_builder.py:1709) | | |
| daily_reports.contractor_bars_jsonb | pg_column | migrations/2026-05-19_daily_reports_views.sql:316 | JSONB DEFAULT `[]` list[{label, value, baseline, status, perperson?, perperson_unit?, display_label?}] | view_builder `_build_contractor_bars` (view_builder.py:331) / v2 (view_builder.py:1557) | | |
| daily_reports.trade_bars_jsonb | pg_column | migrations/2026-05-19_daily_reports_views.sql:317 | JSONB DEFAULT `[]` list[{label, value, baseline, status, ...}] | view_builder `_build_trade_bars` (view_builder.py:352) / v2 (view_builder.py:1575) | | |
| daily_reports.quadrant_jsonb | pg_column | migrations/2026-05-19_daily_reports_views.sql:318 | JSONB DEFAULT `[]` list[{wp_id, wp_name, trade, productivity, impact, quadrant, size, l7_5_activity?, company?, l6_main?, workers?, perperson?, perperson_unit?, display_label?}] | view_builder `_build_quadrant` (view_builder.py:719) / v2 (view_builder.py:1642) | | |
| daily_reports.wp_summary_jsonb | pg_column | migrations/2026-05-19_daily_reports_views.sql:319 | JSONB DEFAULT `[]` list[{wp_id, wp_name, trade, bp_name, start_date, end_date, progress_pct, productivity, impact, baseline, status, perperson?, perperson_unit?, display_label?}] | view_builder `_build_wp_summary` (view_builder.py:762) / v2 (view_builder.py:1665) | | |
| daily_reports.s_curve_jsonb | pg_column | migrations/2026-05-19_daily_reports_views.sql:320 | JSONB DEFAULT `[]` list[{date, planned?, actual?, forecast?, recovery_days?}] (% 환산, 분모 = SUM(plan_wv × plan_mh_rev2)) | view_builder `_build_s_curve` (view_builder.py:880~1021) | | ★ MOD (산식 A) |
| daily_reports.optimizer_view_jsonb | pg_column | migrations/2026-05-19_daily_reports_views.sql:321 | JSONB DEFAULT `{}` `{by_wp:{wp_id:{diagnosis, similar_cases, recommendations, details, source?}}, default_wp_id}` | view_builder `_build_optimizer_view` (view_builder.py:1024) + cold_start fallback `_build_deterministic_cold_start` (view_builder.py:480) | site_summary input (site_summary.py:79) | |
| daily_reports.productivity_jsonb | pg_column | migrations/2026-05-19_daily_reports_views.sql:322 | JSONB DEFAULT `{}` (v1: `_build_productivity_views` EVM dict / v2: `{site, by_company, by_l6}` 산식 다름 — drift §M-v1v2) | v1 `_build_productivity_views` (view_builder.py:48) / v2 `_build_productivity_views_v2` (view_builder.py:1410) | | ★ MOD |
| daily_reports.scenarios_jsonb | pg_column | migrations/2026-05-19_scenarios_jsonb.sql:508 | JSONB DEFAULT `{}` `{site:{no_action/optimistic_p25/base_p50/pessimistic_p75:{expected_completion, recovery_days, delta_days, case_count}}, by_wp:{[wp_id]: 동일 4 키}}` | view_builder `_build_scenarios` (view_builder.py:1215) — percentile 4 (P25=낙관/P50/P75=비관 swap, view_builder.py:1239-1241) | site_summary `base_p50` (site_summary.py:69) | ★ NEW |
| daily_reports.site_summary_text | pg_column | (commit `21c10f7` runtime ALTER — **migration 파일 부재 #N13/C1**) | TEXT | `site_summary.generate_site_summary` (site_summary.py:117) Azure JSON response_format → backfill 또는 optimizer | site_summary input source: kpi + scenarios + wp_summary + optimizer_view + s_curve | ★ NEW |
| daily_reports.is_mock | pg_column | migrations/2026-05-20_add_is_mock.sql:540 | BOOL NOT NULL DEFAULT FALSE | mock seed | | ★ NEW |
| daily_reports.created_at | pg_column | init.sql:40 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | (auto) | | |

### §A.8 `mapped_history` — Atomizer 적재 (11 컬럼)

INSERT helper `insert_mapped_history_batch` (`db.py:458`) — atomizer.py:190 호출. ON CONFLICT (run_id, wa, l6_main, company) DO UPDATE.

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| mapped_history.id | pg_column | migrations/2026-05-18_mapped_history.sql:196 | BIGSERIAL PK | (auto) | PK | |
| mapped_history.run_id | pg_column | migrations/2026-05-18_mapped_history.sql:197 | UUID NOT NULL FK pipeline_runs ON DELETE CASCADE | atomizer | UNIQUE (run_id, wa, l6_main, company) | |
| mapped_history.report_date | pg_column | migrations/2026-05-18_mapped_history.sql:198 | DATE NOT NULL | atomizer | idx_mapped_history_site_date, idx_mapped_history_triplet | |
| mapped_history.site_id | pg_column | migrations/2026-05-18_mapped_history.sql:199 | TEXT NOT NULL FK sites | atomizer | idx_mapped_history_site_date | |
| mapped_history.wa | pg_column | migrations/2026-05-18_mapped_history.sql:200 | TEXT NOT NULL | atomizer | idx_mapped_history_triplet | |
| mapped_history.l6_main | pg_column | migrations/2026-05-18_mapped_history.sql:201 | TEXT NOT NULL | atomizer | idx_mapped_history_triplet | |
| mapped_history.company | pg_column | migrations/2026-05-18_mapped_history.sql:202 | TEXT NOT NULL | atomizer | idx_mapped_history_triplet | |
| mapped_history.today_qty | pg_column | migrations/2026-05-18_mapped_history.sql:203 | NUMERIC | atomizer (ON CONFLICT DO UPDATE — db.py:484) | s_curve actual `day_qty` (view_builder.py:954) | |
| mapped_history.today_assigned_workers | pg_column | migrations/2026-05-18_mapped_history.sql:204 | NUMERIC | atomizer (ON CONFLICT DO UPDATE — db.py:485) | | |
| mapped_history.unit | pg_column | migrations/2026-05-18_mapped_history.sql:205 | TEXT | atomizer (ON CONFLICT DO UPDATE — db.py:486) | | |
| mapped_history.trade | pg_column | migrations/2026-05-19_mapped_history_trade.sql:343 | TEXT | atomizer.py:130 (★ 본 cycle SQL INSERT 누락 — 이슈 #C3) | api.py `_TASKS_ITEMS_SQL` mh.l6_main 사용 (api.py:916) — trade 컬럼 미사용 drift | ★ NEW |
| mapped_history.created_at | pg_column | migrations/2026-05-18_mapped_history.sql:206 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | (auto) | | |

### §A.9 `mapped_history_merge_log` — Phase 1 합산 감사 (10 컬럼)

스크립트 `scripts/merge_mapped_history.py` 가 호출 — db.py helper 부재.

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| mapped_history_merge_log.id | pg_column | migrations/2026-05-21_phase1.sql:558 | BIGSERIAL PK | (script) | PK | ★ NEW |
| mapped_history_merge_log.src_id | pg_column | migrations/2026-05-21_phase1.sql:559 | BIGINT NOT NULL | (script) | | ★ NEW |
| mapped_history_merge_log.tgt_id | pg_column | migrations/2026-05-21_phase1.sql:560 | BIGINT NOT NULL | (script) | | ★ NEW |
| mapped_history_merge_log.run_id | pg_column | migrations/2026-05-21_phase1.sql:561 | UUID NOT NULL | (script) | | ★ NEW |
| mapped_history_merge_log.report_date | pg_column | migrations/2026-05-21_phase1.sql:562 | DATE NOT NULL | (script) | idx_merge_log_date | ★ NEW |
| mapped_history_merge_log.site_id | pg_column | migrations/2026-05-21_phase1.sql:563 | TEXT NOT NULL | (script) | | ★ NEW |
| mapped_history_merge_log.wa | pg_column | migrations/2026-05-21_phase1.sql:564 | TEXT | (script) | | ★ NEW |
| mapped_history_merge_log.l6_main | pg_column | migrations/2026-05-21_phase1.sql:565 | TEXT | (script) | | ★ NEW |
| mapped_history_merge_log.old_company | pg_column | migrations/2026-05-21_phase1.sql:566 | TEXT NOT NULL | (script) | | ★ NEW |
| mapped_history_merge_log.new_company | pg_column | migrations/2026-05-21_phase1.sql:567 | TEXT NOT NULL | (script) | | ★ NEW |
| mapped_history_merge_log.merged_today_qty | pg_column | migrations/2026-05-21_phase1.sql:568 | NUMERIC | (script) | | ★ NEW |
| mapped_history_merge_log.merged_at | pg_column | migrations/2026-05-21_phase1.sql:569 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | (auto) | | ★ NEW |

### §A.10 `parser_reports` (9 컬럼)

INSERT helper `insert_parser_report` (`db.py:515`) — graph.py:110 호출. ON CONFLICT (run_id) DO UPDATE.

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| parser_reports.id | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:221 | BIGSERIAL PK | (auto) | PK | |
| parser_reports.run_id | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:222 | UUID NOT NULL | parser_node (graph.py:110) | UNIQUE (run_id) | |
| parser_reports.report_date | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:223 | DATE NOT NULL | parser_node | parser_reports_report_date_idx | |
| parser_reports.project | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:224 | TEXT NOT NULL | parser_node (project 명) | | |
| parser_reports.bp_summaries | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:225 | JSONB NOT NULL list[BPSummary] | parser_node (state.py:96 BPSummary 전수) | exporter.py:34 시트1 합집합 | |
| parser_reports.job_allocations | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:226 | JSONB NOT NULL list[JobAllocation] | parser_node (state.py:122 JobAllocation) | exporter.py 시트2 | |
| parser_reports.equipment_allocations | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:227 | JSONB NOT NULL list[EquipmentAllocation] | parser_node (state.py:146) | exporter.py 시트3 | |
| parser_reports.activity_count | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:228 | INT NOT NULL | parser_node (len(activities)) | | |
| parser_reports.is_mock | pg_column | migrations/2026-05-20_add_is_mock.sql:535 | BOOL NOT NULL DEFAULT FALSE | mock seed | | ★ NEW |
| parser_reports.created_at | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:229 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | (auto) | | |

### §A.11 `parser_activities` (25 컬럼)

INSERT helper `insert_parser_activities_batch` (`db.py:558`) — graph.py:120 호출. ON CONFLICT (run_id, idx) DO UPDATE.

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| parser_activities.id | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:236 | BIGSERIAL PK | (auto) | PK | |
| parser_activities.run_id | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:237 | UUID NOT NULL | parser_node | parser_activities_run_idx, UNIQUE (run_id, idx) | |
| parser_activities.report_date | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:238 | DATE NOT NULL | parser_node | | |
| parser_activities.idx | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:239 | INT NOT NULL | parser_node (list index) | UNIQUE (run_id, idx) | |
| parser_activities.l5_disc | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:240 | TEXT | parser_node (Activity.l5_disc) | | |
| parser_activities.trade | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:241 | TEXT | parser_node (Activity.trade) | | |
| parser_activities.company | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:242 | TEXT NOT NULL | parser_node | parser_activities_company_idx | |
| parser_activities.unit | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:243 | TEXT | parser_node | | |
| parser_activities.today_qty | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:244 | DOUBLE PRECISION | parser_node | | |
| parser_activities.work_content | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:245 | TEXT | parser_node | | |
| parser_activities.plan_total_qty | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:246 | DOUBLE PRECISION | parser_node | | |
| parser_activities.zone | pg_column | migrations/2026-05-19_parser_full_schema.sql:374 | TEXT | parser_node | parser_activities_zone_idx | |
| parser_activities.bp_code | pg_column | migrations/2026-05-19_parser_full_schema.sql:375 | TEXT | parser_node | parser_activities_bp_code_idx | |
| parser_activities.scope | pg_column | migrations/2026-05-19_parser_full_schema.sql:376 | TEXT | parser_node | | |
| parser_activities.yesterday_cum_qty | pg_column | migrations/2026-05-19_parser_full_schema.sql:377 | DOUBLE PRECISION | parser_node | | |
| parser_activities.today_cum_qty | pg_column | migrations/2026-05-19_parser_full_schema.sql:378 | DOUBLE PRECISION | parser_node | | |
| parser_activities.progress_percent | pg_column | migrations/2026-05-19_parser_full_schema.sql:379 | DOUBLE PRECISION | parser_node | | |
| parser_activities.remaining_qty | pg_column | migrations/2026-05-19_parser_full_schema.sql:380 | DOUBLE PRECISION | parser_node | | |
| parser_activities.remaining_percent | pg_column | migrations/2026-05-19_parser_full_schema.sql:381 | DOUBLE PRECISION | parser_node | | |
| parser_activities.note | pg_column | migrations/2026-05-19_parser_full_schema.sql:382 | TEXT | parser_node | | |
| parser_activities.work_location_code | pg_column | migrations/2026-05-19_parser_full_schema.sql:383 | TEXT | parser_node (업체별 시트4 only) | | |
| parser_activities.wbs_mid_name | pg_column | migrations/2026-05-19_parser_full_schema.sql:384 | TEXT | parser_node (업체별 시트4 only) | | |
| parser_activities.wbs_sub_name | pg_column | migrations/2026-05-19_parser_full_schema.sql:385 | TEXT | parser_node (업체별 시트4 only) | | |
| parser_activities.wbs_detail_name | pg_column | migrations/2026-05-19_parser_full_schema.sql:386 | TEXT | parser_node (업체별 시트4 only) | | |
| parser_activities.is_mock | pg_column | migrations/2026-05-20_add_is_mock.sql:536 | BOOL NOT NULL DEFAULT FALSE | mock seed | | ★ NEW |
| parser_activities.created_at | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:247 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | (auto) | | |

### §A.12 `mapper_activities` (38 컬럼)

INSERT helper `insert_mapper_activities_batch` (`db.py:639`, $1~$37 + is_mock default) — graph.py:149 호출. ON CONFLICT (run_id, idx) DO UPDATE 전 컬럼 갱신.

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| mapper_activities.id | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:256 | BIGSERIAL PK | (auto) | PK | |
| mapper_activities.run_id | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:257 | UUID NOT NULL | mapper_node | mapper_activities_run_idx, UNIQUE (run_id, idx) | |
| mapper_activities.report_date | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:258 | DATE NOT NULL | mapper_node | | |
| mapper_activities.idx | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:259 | INT NOT NULL | mapper_node | UNIQUE (run_id, idx) | |
| mapper_activities.company | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:260 | TEXT NOT NULL | mapper_node | mapper_activities_company_idx | |
| mapper_activities.trade | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:261 | TEXT | mapper_node | | |
| mapper_activities.unit | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:262 | TEXT | mapper_node | | |
| mapper_activities.today_qty | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:263 | DOUBLE PRECISION | mapper_node | | |
| mapper_activities.wa | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:264 | TEXT | mapper_node | mapper_activities_wa_l6_idx | |
| mapper_activities.l6_main | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:265 | TEXT | mapper_node | mapper_activities_wa_l6_idx | |
| mapper_activities.mapping_conf | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:266 | DOUBLE PRECISION | mapper_node (rerank confidence) | hil_1 review filter (graph.py:120) | |
| mapper_activities.mapping_source | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:267 | TEXT (`auto_bp_single`/`auto_l6_single`/`auto_sheet1_text`/`hil_required`/`user_corrected`) | mapper_node | | |
| mapper_activities.requires_review | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:268 | BOOL NOT NULL DEFAULT FALSE | mapper_node | hil_1 review_needed filter | |
| mapper_activities.assigned_workers | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:269 | DOUBLE PRECISION | mapper `_prorate_mh` (mapper.py:389) | quadrant impact 산식 (view_builder.py:731) | |
| mapper_activities.worker_source | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:270 | TEXT (`parsed`/`mh_prorated`/`user_corrected`) | mapper `_prorate_mh` | | |
| mapper_activities.plan_total_qty | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:271 | DOUBLE PRECISION | mapper_node (PG fetch) | quadrant impact (view_builder.py:731) | |
| mapper_activities.plan_mh | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:272 | DOUBLE PRECISION | mapper_node | quadrant impact (view_builder.py:731) | |
| mapper_activities.conditions | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:273 | JSONB NOT NULL DEFAULT `[]` (list[str]) | mapper_node | | |
| mapper_activities.zone | pg_column | migrations/2026-05-19_parser_full_schema.sql:393 | TEXT | mapper_node (parser propagate) | mapper_activities_zone_idx | |
| mapper_activities.bp_code | pg_column | migrations/2026-05-19_parser_full_schema.sql:394 | TEXT | mapper_node | mapper_activities_bp_code_idx | |
| mapper_activities.scope | pg_column | migrations/2026-05-19_parser_full_schema.sql:395 | TEXT | mapper_node | | |
| mapper_activities.yesterday_cum_qty | pg_column | migrations/2026-05-19_parser_full_schema.sql:396 | DOUBLE PRECISION | mapper_node | | |
| mapper_activities.today_cum_qty | pg_column | migrations/2026-05-19_parser_full_schema.sql:397 | DOUBLE PRECISION | mapper_node | s_curve actual (view_builder.py:112) | |
| mapper_activities.progress_percent | pg_column | migrations/2026-05-19_parser_full_schema.sql:398 | DOUBLE PRECISION | mapper_node | | |
| mapper_activities.remaining_qty | pg_column | migrations/2026-05-19_parser_full_schema.sql:399 | DOUBLE PRECISION | mapper_node | | |
| mapper_activities.remaining_percent | pg_column | migrations/2026-05-19_parser_full_schema.sql:400 | DOUBLE PRECISION | mapper_node | | |
| mapper_activities.note | pg_column | migrations/2026-05-19_parser_full_schema.sql:401 | TEXT | mapper_node | | |
| mapper_activities.work_location_code | pg_column | migrations/2026-05-19_parser_full_schema.sql:402 | TEXT | mapper_node | | |
| mapper_activities.wbs_mid_name | pg_column | migrations/2026-05-19_parser_full_schema.sql:403 | TEXT | mapper_node | | |
| mapper_activities.wbs_sub_name | pg_column | migrations/2026-05-19_parser_full_schema.sql:404 | TEXT | mapper_node | | |
| mapper_activities.wbs_detail_name | pg_column | migrations/2026-05-19_parser_full_schema.sql:405 | TEXT | mapper_node | | |
| mapper_activities.alternatives | pg_column | migrations/2026-05-19_mapper_alternatives.sql:352 | JSONB NOT NULL DEFAULT `[]` list[{wa, l6_main, score}] sorted desc K=3 | mapper_node (rerank top-K) | mapper_activities_alternatives_gin GIN | |
| mapper_activities.cum_workers_today | pg_column | migrations/2026-05-19_daily_reports_views.sql:332 | DOUBLE PRECISION | mapper_node | | |
| mapper_activities.cum_actual_mh_today | pg_column | migrations/2026-05-19_daily_reports_views.sql:333 | DOUBLE PRECISION | mapper_node | s_curve actual mh (view_builder.py:113) | |
| mapper_activities.l5_disc | pg_column | migrations/2026-05-23_mapper_l7_5_columns.sql:578 | TEXT | mapper_node (activity_master propagate, d40c84f cycle) | | ★ NEW |
| mapper_activities.l7_sub | pg_column | migrations/2026-05-23_mapper_l7_5_columns.sql:579 | TEXT | mapper_node | | ★ NEW |
| mapper_activities.l7_5_activity | pg_column | migrations/2026-05-23_mapper_l7_5_columns.sql:580 | TEXT | mapper_node | view_builder.py:1445 v2 필터 (`AND l7_5_activity IS NOT NULL`) | ★ NEW |
| mapper_activities.sub_work_area | pg_column | migrations/2026-05-23_mapper_l7_5_columns.sql:581 | TEXT | mapper_node | | ★ NEW |
| mapper_activities.is_mock | pg_column | migrations/2026-05-20_add_is_mock.sql:537 | BOOL NOT NULL DEFAULT FALSE | mock seed | view_builder.py:203 `ma.is_mock = FALSE` | ★ NEW |
| mapper_activities.created_at | pg_column | migrations/2026-05-18_parser_mapper_outputs.sql:274 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | (auto) | | |

### §A.13 `parser_job_allocations` (15 컬럼, 시트2)

INSERT helper `insert_parser_job_allocations_batch` (`db.py:771`) — graph.py:130 호출.

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| parser_job_allocations.id | pg_column | migrations/2026-05-19_parser_full_schema.sql:412 | BIGSERIAL PK | (auto) | PK | |
| parser_job_allocations.run_id | pg_column | migrations/2026-05-19_parser_full_schema.sql:413 | UUID NOT NULL | parser_node | parser_job_allocations_run_idx, UNIQUE (run_id, idx) | |
| parser_job_allocations.report_date | pg_column | migrations/2026-05-19_parser_full_schema.sql:414 | DATE NOT NULL | parser_node | | |
| parser_job_allocations.idx | pg_column | migrations/2026-05-19_parser_full_schema.sql:415 | INT NOT NULL | parser_node | UNIQUE | |
| parser_job_allocations.bp_code | pg_column | migrations/2026-05-19_parser_full_schema.sql:416 | TEXT | parser_node | | |
| parser_job_allocations.company | pg_column | migrations/2026-05-19_parser_full_schema.sql:417 | TEXT NOT NULL | parser_node | parser_job_allocations_company_idx | |
| parser_job_allocations.disc_abbrev | pg_column | migrations/2026-05-19_parser_full_schema.sql:418 | TEXT | parser_node | | |
| parser_job_allocations.manager_code | pg_column | migrations/2026-05-19_parser_full_schema.sql:419 | TEXT (Mm##) | parser_node | | |
| parser_job_allocations.worker_code | pg_column | migrations/2026-05-19_parser_full_schema.sql:420 | TEXT (sk##) | parser_node | | |
| parser_job_allocations.job_type | pg_column | migrations/2026-05-19_parser_full_schema.sql:421 | TEXT NOT NULL | parser_node | parser_job_allocations_job_idx | |
| parser_job_allocations.workers_yesterday_cum | pg_column | migrations/2026-05-19_parser_full_schema.sql:422 | JSONB TimeShiftCounts `{morning, daytime, overtime, night, all_night, total}` | parser_node | | |
| parser_job_allocations.workers_today_incr | pg_column | migrations/2026-05-19_parser_full_schema.sql:423 | JSONB TimeShiftCounts | parser_node | | |
| parser_job_allocations.workers_today_cum | pg_column | migrations/2026-05-19_parser_full_schema.sql:424 | JSONB TimeShiftCounts | parser_node | | |
| parser_job_allocations.final_flag | pg_column | migrations/2026-05-19_parser_full_schema.sql:425 | TEXT (O/X) | parser_node | | |
| parser_job_allocations.workers_cum_t | pg_column | migrations/2026-05-19_parser_full_schema.sql:426 | INT NOT NULL DEFAULT 0 | parser_node (Total 편의) | | |
| parser_job_allocations.created_at | pg_column | migrations/2026-05-19_parser_full_schema.sql:427 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | (auto) | | |

### §A.14 `parser_equipment_allocations` (14 컬럼, 시트3)

INSERT helper `insert_parser_equipment_allocations_batch` (`db.py:843`) — graph.py:136 호출.

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| parser_equipment_allocations.id | pg_column | migrations/2026-05-19_parser_full_schema.sql:436 | BIGSERIAL PK | (auto) | PK | |
| parser_equipment_allocations.run_id | pg_column | migrations/2026-05-19_parser_full_schema.sql:437 | UUID NOT NULL | parser_node | `_run_idx`, UNIQUE (run_id, idx) | |
| parser_equipment_allocations.report_date | pg_column | migrations/2026-05-19_parser_full_schema.sql:438 | DATE NOT NULL | parser_node | | |
| parser_equipment_allocations.idx | pg_column | migrations/2026-05-19_parser_full_schema.sql:439 | INT NOT NULL | parser_node | UNIQUE | |
| parser_equipment_allocations.bp_code | pg_column | migrations/2026-05-19_parser_full_schema.sql:440 | TEXT | parser_node | | |
| parser_equipment_allocations.company | pg_column | migrations/2026-05-19_parser_full_schema.sql:441 | TEXT NOT NULL | parser_node | `_company_idx` | |
| parser_equipment_allocations.disc_abbrev | pg_column | migrations/2026-05-19_parser_full_schema.sql:442 | TEXT | parser_node | | |
| parser_equipment_allocations.equipment_big | pg_column | migrations/2026-05-19_parser_full_schema.sql:443 | TEXT NOT NULL | parser_node | `_big_mid_idx` | |
| parser_equipment_allocations.equipment_mid | pg_column | migrations/2026-05-19_parser_full_schema.sql:444 | TEXT NOT NULL | parser_node | `_big_mid_idx` | |
| parser_equipment_allocations.equipment_spec | pg_column | migrations/2026-05-19_parser_full_schema.sql:445 | TEXT | parser_node | | |
| parser_equipment_allocations.count_yesterday_cum | pg_column | migrations/2026-05-19_parser_full_schema.sql:446 | JSONB TimeShiftCounts | parser_node | | |
| parser_equipment_allocations.count_today_incr | pg_column | migrations/2026-05-19_parser_full_schema.sql:447 | JSONB TimeShiftCounts | parser_node | | |
| parser_equipment_allocations.count_today_cum | pg_column | migrations/2026-05-19_parser_full_schema.sql:448 | JSONB TimeShiftCounts | parser_node | | |
| parser_equipment_allocations.final_flag | pg_column | migrations/2026-05-19_parser_full_schema.sql:449 | TEXT | parser_node | | |
| parser_equipment_allocations.count_cum_t | pg_column | migrations/2026-05-19_parser_full_schema.sql:450 | INT NOT NULL DEFAULT 0 | parser_node | | |
| parser_equipment_allocations.created_at | pg_column | migrations/2026-05-19_parser_full_schema.sql:451 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | (auto) | | |

### §A.15 `parser_worker_outputs` (17 컬럼, 시트6 업체별)

INSERT helper `insert_parser_worker_outputs_batch` (`db.py:909`) — merge 노드 호출.

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| parser_worker_outputs.id | pg_column | migrations/2026-05-19_parser_full_schema.sql:460 | BIGSERIAL PK | (auto) | PK | |
| parser_worker_outputs.run_id | pg_column | migrations/2026-05-19_parser_full_schema.sql:461 | UUID NOT NULL | parser_post merge | `_run_idx`, UNIQUE (run_id, idx) | |
| parser_worker_outputs.report_date | pg_column | migrations/2026-05-19_parser_full_schema.sql:462 | DATE NOT NULL | parser_post merge | | |
| parser_worker_outputs.idx | pg_column | migrations/2026-05-19_parser_full_schema.sql:463 | INT NOT NULL | parser_post merge | UNIQUE | |
| parser_worker_outputs.bp_name | pg_column | migrations/2026-05-19_parser_full_schema.sql:464 | TEXT | parser_post merge | `_bp_idx` | |
| parser_worker_outputs.worker_name | pg_column | migrations/2026-05-19_parser_full_schema.sql:465 | TEXT NOT NULL | parser_post merge | `_worker_idx` | |
| parser_worker_outputs.job_type | pg_column | migrations/2026-05-19_parser_full_schema.sql:466 | TEXT | parser_post merge | | |
| parser_worker_outputs.wbs_mid_name | pg_column | migrations/2026-05-19_parser_full_schema.sql:467 | TEXT | parser_post merge | | |
| parser_worker_outputs.wbs_sub_name | pg_column | migrations/2026-05-19_parser_full_schema.sql:468 | TEXT | parser_post merge | | |
| parser_worker_outputs.wbs_detail_name | pg_column | migrations/2026-05-19_parser_full_schema.sql:469 | TEXT | parser_post merge | | |
| parser_worker_outputs.work_location_code | pg_column | migrations/2026-05-19_parser_full_schema.sql:470 | TEXT | parser_post merge | | |
| parser_worker_outputs.work_content | pg_column | migrations/2026-05-19_parser_full_schema.sql:471 | TEXT | parser_post merge | | |
| parser_worker_outputs.shift_morning | pg_column | migrations/2026-05-19_parser_full_schema.sql:472 | INT NOT NULL DEFAULT 0 | parser_post merge | | |
| parser_worker_outputs.shift_daytime | pg_column | migrations/2026-05-19_parser_full_schema.sql:473 | INT NOT NULL DEFAULT 0 | parser_post merge | | |
| parser_worker_outputs.shift_overtime | pg_column | migrations/2026-05-19_parser_full_schema.sql:474 | INT NOT NULL DEFAULT 0 | parser_post merge | | |
| parser_worker_outputs.shift_night | pg_column | migrations/2026-05-19_parser_full_schema.sql:475 | INT NOT NULL DEFAULT 0 | parser_post merge | | |
| parser_worker_outputs.shift_all_night | pg_column | migrations/2026-05-19_parser_full_schema.sql:476 | INT NOT NULL DEFAULT 0 | parser_post merge | | |
| parser_worker_outputs.note | pg_column | migrations/2026-05-19_parser_full_schema.sql:477 | TEXT | parser_post merge | | |
| parser_worker_outputs.created_at | pg_column | migrations/2026-05-19_parser_full_schema.sql:478 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | (auto) | | |

### §A.16 `parser_report_meta` (12 컬럼, Cover 업체별)

INSERT helper `insert_parser_report_meta_batch` (`db.py:980`) — merge 노드 호출. UNIQUE (run_id, bp_name).

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| parser_report_meta.id | pg_column | migrations/2026-05-19_parser_full_schema.sql:487 | BIGSERIAL PK | (auto) | PK | |
| parser_report_meta.run_id | pg_column | migrations/2026-05-19_parser_full_schema.sql:488 | UUID NOT NULL | parser_post merge | `_run_idx`, UNIQUE (run_id, bp_name) | |
| parser_report_meta.report_date | pg_column | migrations/2026-05-19_parser_full_schema.sql:489 | DATE NOT NULL | parser_post merge | | |
| parser_report_meta.bp_name | pg_column | migrations/2026-05-19_parser_full_schema.sql:490 | TEXT NOT NULL | parser_post merge | UNIQUE | |
| parser_report_meta.project_name | pg_column | migrations/2026-05-19_parser_full_schema.sql:491 | TEXT | parser_post merge | | |
| parser_report_meta.project_code | pg_column | migrations/2026-05-19_parser_full_schema.sql:492 | TEXT | parser_post merge | | |
| parser_report_meta.site_id | pg_column | migrations/2026-05-19_parser_full_schema.sql:493 | TEXT | parser_post merge | | |
| parser_report_meta.writer | pg_column | migrations/2026-05-19_parser_full_schema.sql:494 | TEXT | parser_post merge | | |
| parser_report_meta.reviewer | pg_column | migrations/2026-05-19_parser_full_schema.sql:495 | TEXT | parser_post merge | | |
| parser_report_meta.approval | pg_column | migrations/2026-05-19_parser_full_schema.sql:496 | TEXT | parser_post merge | | |
| parser_report_meta.document_no | pg_column | migrations/2026-05-19_parser_full_schema.sql:497 | TEXT | parser_post merge | | |
| parser_report_meta.created_at | pg_column | migrations/2026-05-19_parser_full_schema.sql:498 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | (auto) | | |

### §A.17 `collector_inbox` — Gmail IMAP IDLE dedup (10 컬럼) ★ NEW

소스: `migrations/2026-05-19_collector_inbox.sql:288`.

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| collector_inbox.message_id | pg_column | migrations/2026-05-19_collector_inbox.sql:289 | TEXT PK (RFC822 Message-ID) | `insert_collector_inbox` (db.py:1149) — collector/idle_worker.py | PK | ★ NEW |
| collector_inbox.received_at | pg_column | migrations/2026-05-19_collector_inbox.sql:290 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | collector | | ★ NEW |
| collector_inbox.site_id | pg_column | migrations/2026-05-19_collector_inbox.sql:291 | TEXT NOT NULL | collector | collector_inbox_site_date_idx | ★ NEW |
| collector_inbox.report_date | pg_column | migrations/2026-05-19_collector_inbox.sql:292 | DATE NOT NULL | collector | collector_inbox_site_date_idx | ★ NEW |
| collector_inbox.bp_name | pg_column | migrations/2026-05-19_collector_inbox.sql:293 | TEXT NOT NULL | collector | | ★ NEW |
| collector_inbox.attachment_filename | pg_column | migrations/2026-05-19_collector_inbox.sql:294 | TEXT NOT NULL | collector | | ★ NEW |
| collector_inbox.attachment_path | pg_column | migrations/2026-05-19_collector_inbox.sql:295 | TEXT NOT NULL (로컬 디스크 경로) | collector | | ★ NEW |
| collector_inbox.run_id | pg_column | migrations/2026-05-19_collector_inbox.sql:296 | UUID FK pipeline_runs ON DELETE SET NULL | `update_collector_inbox_status` (db.py:1179) — collector_node 호출 | | ★ NEW |
| collector_inbox.parse_status | pg_column | migrations/2026-05-19_collector_inbox.sql:297 | TEXT NOT NULL CHECK (`pending`/`running`/`completed`/`failed`/`dead_letter`) DEFAULT `pending` | `update_collector_inbox_status` (db.py:1179) | collector_inbox_status_idx PARTIAL (`parse_status IN ('pending','running','failed')`) | ★ NEW |
| collector_inbox.error | pg_column | migrations/2026-05-19_collector_inbox.sql:299 | TEXT | `update_collector_inbox_status` | | ★ NEW |
| collector_inbox.updated_at | pg_column | migrations/2026-05-19_collector_inbox.sql:300 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | `update_collector_inbox_status` (NOW() 갱신) | | ★ NEW |

### §A.18 `prototype_embedding_cache` — L7.5 임베딩 캐시 (4 컬럼) ★ NEW

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| prototype_embedding_cache.text_hash | pg_column | migrations/2026-05-21_phase1.sql:549 | TEXT PK | scripts/cache_*.py (외부) | PK | ★ NEW |
| prototype_embedding_cache.source_text | pg_column | migrations/2026-05-21_phase1.sql:550 | TEXT NOT NULL | (script) | | ★ NEW |
| prototype_embedding_cache.embedding | pg_column | migrations/2026-05-21_phase1.sql:551 | FLOAT8[] NOT NULL | (script) | | ★ NEW |
| prototype_embedding_cache.created_at | pg_column | migrations/2026-05-21_phase1.sql:552 | TIMESTAMPTZ NOT NULL DEFAULT NOW() | (auto) | idx_embedding_cache_created | ★ NEW |

### §A.19~A.21 LangGraph checkpoint 테이블 (3, AsyncPostgresSaver 자동 생성)

`checkpointer.py:30~76 _LazyAsyncPostgresSaver` 가 첫 async 호출 시 `await self._lazy_pool.open()` → 표준 PG schema 자동 생성.

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| checkpoints.thread_id | langgraph_ckpt | auto (AsyncPostgresSaver) | TEXT | LangGraph (= run_id str, api.py:253) | PK 일부 | |
| checkpoints.checkpoint_ns | langgraph_ckpt | auto | TEXT NOT NULL DEFAULT '' | LangGraph | PK 일부 | |
| checkpoints.checkpoint_id | langgraph_ckpt | auto | TEXT | LangGraph | PK 일부 | |
| checkpoints.parent_checkpoint_id | langgraph_ckpt | auto | TEXT | LangGraph | | |
| checkpoints.type | langgraph_ckpt | auto | TEXT | LangGraph | | |
| checkpoints.checkpoint | langgraph_ckpt | auto | JSONB NOT NULL (graph state 직렬화) | LangGraph aput | hil_1 interrupt 시 state freeze | |
| checkpoints.metadata | langgraph_ckpt | auto | JSONB NOT NULL DEFAULT '{}' | LangGraph | | |
| checkpoint_writes.thread_id / checkpoint_ns / checkpoint_id / task_id / idx | langgraph_ckpt | auto | TEXT/INT (PK) | LangGraph aput_writes | PK | |
| checkpoint_writes.channel / type / blob / task_path | langgraph_ckpt | auto | TEXT / TEXT / BYTEA / TEXT | LangGraph | | |
| checkpoint_blobs.thread_id / checkpoint_ns / channel / version / type / blob | langgraph_ckpt | auto | TEXT/TEXT/TEXT/TEXT/TEXT/BYTEA | LangGraph | PK (thread_id, checkpoint_ns, channel, version) | |

---

## §B. JSONB key 인벤토리 (view_builder 산식 인용 + producer 코드 직접 grep)

### §B.1 `daily_reports.history_csv_row` (reporter summary)

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| history_csv_row.total_workers | pg_jsonb_key | reporter.py:108 | number | reporter (Σ Activity.assigned_workers) | |
| history_csv_row.total_qty_by_trade | pg_jsonb_key | reporter.py:109 | object<string,number> (l5_disc 한글 → Σ today_qty) | reporter | |
| history_csv_row.risk_counts | pg_jsonb_key | reporter.py:110 | object<string,int> ("정상"/"주의"/"이상") | reporter | |
| history_csv_row.advice_count | pg_jsonb_key | reporter.py:111 | int | reporter | |

> 컬럼명 `history_csv_row` ↔ 실 박힘 (summary dict) 의미 mismatch (drift §D).

### §B.2 `forecasts.today_qty_by_unit` / `plan_total_qty_by_unit`

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| forecasts.today_qty_by_unit.<unit> | pg_jsonb_key | forecaster/aggregate.py:18 | number | forecaster (unit별 today_qty Σ) | |
| forecasts.plan_total_qty_by_unit.<unit> | pg_jsonb_key | db.py:209~217 fetch_plan_for_group | number | forecaster (activity_master GROUP BY unit) | |

### §B.3 `forecasts.similar_cases[]`

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| similar_cases[].date | pg_jsonb_key | forecaster/agent.py:210 | string (ISO date) | forecaster RAG | |
| similar_cases[].productivity | pg_jsonb_key | forecaster/agent.py:213 | number | forecaster RAG | |
| similar_cases[].conditions | pg_jsonb_key | forecaster/rerank.py:26-27 | string[] (Chroma comma-joined str 를 `split(",")` 한 list) | forecaster | |

### §B.4 `optimizer_advice.degradation_cases[]`

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| degradation_cases[].date | pg_jsonb_key | optimizer/retrieve.py:106 | string (ISO date) | optimizer | |
| degradation_cases[].conditions | pg_jsonb_key | optimizer/retrieve.py:107 | string (comma-joined str — 결정 #19) | optimizer | |
| degradation_cases[].productivity | pg_jsonb_key | optimizer/retrieve.py:108 | number | optimizer | |
| degradation_cases[].assigned_workers | pg_jsonb_key | optimizer/retrieve.py:109 | number | optimizer | |
| degradation_cases[].activities | pg_jsonb_key | optimizer/retrieve.py:110 | string[] (Chroma documents) | optimizer | |
| degradation_cases[].recovery.trajectory | pg_jsonb_key | optimizer/retrieve.py:161 + graph.py:262 | object[] (`[{date, conditions, productivity, recovered}, ...]`) | optimizer | |
| degradation_cases[].recovery.recovery_days | pg_jsonb_key | optimizer/retrieve.py:161 | int \| null | optimizer | |

### §B.5 `optimizer_advice.recovery_pattern[]` / `recovery_distribution`

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| recovery_pattern[].date | pg_jsonb_key | optimizer/agent.py:76 | string (ISO date) | optimizer (degradation_cases 와 1:1) | |
| recovery_pattern[].recovery_days | pg_jsonb_key | optimizer/agent.py:76 | int \| null | optimizer | |
| recovery_distribution.d+N | pg_jsonb_key | optimizer/agent.py:86 _compute_recovery_distribution | int (window=7, N=1..7) | optimizer | |
| recovery_distribution.not_recovered | pg_jsonb_key | optimizer/agent.py:86 | int | optimizer | |

### §B.6 `optimizer_advice.recommendations[]`

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| recommendations[].rank | pg_jsonb_key | optimizer/agent.py:87 | int (1~4) | optimizer LLM | |
| recommendations[].text | pg_jsonb_key | optimizer/agent.py:87 | string (한국어 LLM 산출) | optimizer LLM | |

### §B.7 `mapping_corrections.original` / `corrected`

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| mapping_corrections.original.wa | pg_jsonb_key | graph.py:143-152 | string \| null | mapper | |
| mapping_corrections.original.l6_main | pg_jsonb_key | graph.py:143-152 | string \| null | mapper | |
| mapping_corrections.original.mapping_conf | pg_jsonb_key | graph.py:143-152 | number | mapper | |
| mapping_corrections.original.mapping_source | pg_jsonb_key | graph.py:143-152 | string enum (5 values) | mapper | |
| mapping_corrections.original.work_content | pg_jsonb_key | graph.py:143-152 | string | parser | |
| mapping_corrections.original.company | pg_jsonb_key | graph.py:143-152 | string | parser | |
| mapping_corrections.original.trade | pg_jsonb_key | graph.py:143-152 | string (l5_disc 한글) | parser | |
| mapping_corrections.corrected.wa | pg_jsonb_key | graph.py:153-159 | string | hil_1 user | |
| mapping_corrections.corrected.l6_main | pg_jsonb_key | graph.py:153-159 | string | hil_1 user | |
| mapping_corrections.corrected.mapping_source | pg_jsonb_key | graph.py:156 | string (= `"user_corrected"` 항상) | hil_1 (hard-code) | |
| mapping_corrections.corrected.correction_type | pg_jsonb_key | graph.py:157 | string (= `"replace"` 항상) | hil_1 (hard-code) | |

### §B.8 `daily_reports.kpi_jsonb`

view_builder `_build_kpi` (view_builder.py:284) + v2 (view_builder.py:1709). MEDIAN aggregator fix (2026-05-23, view_builder.py:301: AVG → PERCENTILE_CONT(0.5)).

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| kpi_jsonb.productivity_today | pg_jsonb_key | view_builder.py:313 / :1710 | number | view_builder (CPI 또는 wv_median) | |
| kpi_jsonb.productivity_today_simple_mean | pg_jsonb_key | view_builder.py:1711 | number | v2 only | ★ NEW |
| kpi_jsonb.productivity_today_perperson | pg_jsonb_key | view_builder.py:1712 | number \| null | v2 only | ★ NEW |
| kpi_jsonb.productivity_today_unit | pg_jsonb_key | view_builder.py:1715 | string \| null | v2 only | ★ NEW |
| kpi_jsonb.productivity_today_display | pg_jsonb_key | view_builder.py:1716 | string (display_label) | v2 only | ★ NEW |
| kpi_jsonb.productivity_history_diff | pg_jsonb_key | view_builder.py:1719 | number (0 placeholder) | v2 only | |
| kpi_jsonb.spi | pg_jsonb_key | view_builder.py:314 | number | v1 EVM | |
| kpi_jsonb.cpi | pg_jsonb_key | view_builder.py:315 | number | v1 EVM | |
| kpi_jsonb.target_productivity | pg_jsonb_key | view_builder.py:316 / :1723 | number (= 100) | view_builder (상수) | |
| kpi_jsonb.delay_days | pg_jsonb_key | view_builder.py:317 / :1720 | int | MEDIAN forecasts.delay_days (PERCENTILE_CONT 0.5) | ★ MOD |
| kpi_jsonb.expected_completion | pg_jsonb_key | view_builder.py:318 / :1721 | string (ISO date) | MEDIAN forecasts.expected_completion (PERCENTILE_DISC 0.5) | ★ MOD |
| kpi_jsonb.recoverable_productivity | pg_jsonb_key | view_builder.py:1722 | number (`max(0, 100 - wv_median)`) | v2 only | ★ NEW |
| kpi_jsonb.recovery_days | pg_jsonb_key | view_builder.py:1725 / :1833 | int | scenarios.site.base_p50.recovery_days | ★ NEW |
| kpi_jsonb.recovered_completion | pg_jsonb_key | view_builder.py:1726 / :1834 | string \| null | scenarios.site.base_p50.expected_completion | ★ NEW |

### §B.9 `daily_reports.contractor_bars_jsonb` / `trade_bars_jsonb`

v1 `_build_contractor_bars` (view_builder.py:331), v2 (view_builder.py:1557). v2 가 perperson/display_label 추가.

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| contractor_bars_jsonb[].label | pg_jsonb_key | view_builder.py:341 / :1559 | string (company) | view_builder | |
| contractor_bars_jsonb[].value | pg_jsonb_key | view_builder.py:342 / :1560 | number (CPI 또는 wv_median) | view_builder | |
| contractor_bars_jsonb[].baseline | pg_jsonb_key | view_builder.py:343 / :1562 | number (= 90 v1 / = 100 v2) | view_builder (상수) | |
| contractor_bars_jsonb[].status | pg_jsonb_key | view_builder.py:344 / :1561 | string (`normal`/`caution`/`risk`) | `_bar_status` (90/80) / `_status_of` (90/70) | ★ MOD |
| contractor_bars_jsonb[].perperson | pg_jsonb_key | view_builder.py:1563 | number \| null | v2 only | ★ NEW |
| contractor_bars_jsonb[].perperson_unit | pg_jsonb_key | view_builder.py:1564 | string \| null | v2 only | ★ NEW |
| contractor_bars_jsonb[].display_label | pg_jsonb_key | view_builder.py:1567 | string | v2 only | ★ NEW |
| trade_bars_jsonb[] | pg_jsonb_key | view_builder.py:1575 | (동일 shape, label = l6_main) | view_builder | |

### §B.10 `daily_reports.quadrant_jsonb`

v1 `_build_quadrant` (view_builder.py:719), v2 (view_builder.py:1642).

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| quadrant_jsonb[].wp_id | pg_jsonb_key | view_builder.py:750 / :1644 | string (`_wp_id_of` kebab `wa-l6_main-company`) | view_builder | |
| quadrant_jsonb[].wp_name | pg_jsonb_key | view_builder.py:751 / :1645 | string (v1: `wa + l6_main` / v2: `l7_5 · wa`) | view_builder | |
| quadrant_jsonb[].trade | pg_jsonb_key | view_builder.py:752 / :1651 | string (= l6_main) | view_builder | |
| quadrant_jsonb[].productivity | pg_jsonb_key | view_builder.py:753 / :1652 | number | view_builder | |
| quadrant_jsonb[].impact | pg_jsonb_key | view_builder.py:754 / :1653 | number (v1: P90 normalize / v2: share-of-total) | view_builder | ★ MOD |
| quadrant_jsonb[].quadrant | pg_jsonb_key | view_builder.py:755 / :1654 | string (`risk`/`caution`/`watch`/`safe`) | `_quadrant_label` (80/50) / `_quadrant_of` (70/50) | ★ MOD |
| quadrant_jsonb[].size | pg_jsonb_key | view_builder.py:756 / :1655 | number (v1: 30~120 / v2: `plan_total_qty/10`) | view_builder | ★ MOD |
| quadrant_jsonb[].l7_5_activity | pg_jsonb_key | view_builder.py:1646 | string | v2 only | ★ NEW |
| quadrant_jsonb[].company | pg_jsonb_key | view_builder.py:1647 | string | v2 only | ★ NEW |
| quadrant_jsonb[].l6_main | pg_jsonb_key | view_builder.py:1648 | string | v2 only | ★ NEW |
| quadrant_jsonb[].actual_trade | pg_jsonb_key | view_builder.py:1649 | string (`건축`/`토목`) | v2 only | ★ NEW |
| quadrant_jsonb[].workers | pg_jsonb_key | view_builder.py:1650 | int | v2 only | ★ NEW |
| quadrant_jsonb[].perperson / perperson_unit / display_label | pg_jsonb_key | view_builder.py:1656~1660 | number / string / string | v2 only | ★ NEW |

### §B.11 `daily_reports.wp_summary_jsonb`

v1 `_build_wp_summary` (view_builder.py:762, quadrant + placeholder), v2 (view_builder.py:1665).

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| wp_summary_jsonb[].wp_id / wp_name / trade / bp_name / start_date / end_date / progress_pct / productivity / impact / baseline / status | pg_jsonb_key | view_builder.py:1666~1680 | (위 quadrant + 기간 + progress_pct + status) | view_builder | |
| wp_summary_jsonb[].perperson / perperson_unit / display_label | pg_jsonb_key | view_builder.py:1681~1685 | number / string / string | v2 only | ★ NEW |

> v2 정렬 = `impact desc` (view_builder.py:1689).

### §B.12 `daily_reports.s_curve_jsonb` ★ MOD (산식 A)

`_build_s_curve` (view_builder.py:880~1021). 분모 = `SUM(plan_wv × plan_mh_rev2)` (view_builder.py:899). actual SQL = full_grid CROSS JOIN + WINDOW SUM 으로 단조 누적 보장 (view_builder.py:962~973).

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| s_curve_jsonb[].date | pg_jsonb_key | view_builder.py:997 / :1001 | string (ISO date) | view_builder | |
| s_curve_jsonb[].planned | pg_jsonb_key | view_builder.py:998 | number (%, `SUM(plan_wv × plan_mh_rev2 × linear_progress(t)) / 분모 × 100`) | view_builder | ★ MOD |
| s_curve_jsonb[].actual | pg_jsonb_key | view_builder.py:1002 | number (%, `SUM(weight × MIN(1, cum_qty(t)/plan_qty)) / 분모 × 100`, (wa, l6_main) 매칭 + cap=1) | view_builder | ★ MOD |
| s_curve_jsonb[].forecast | pg_jsonb_key | view_builder.py:861, :870 | number (직전 7일 평균 rate × remaining days) | view_builder `_extend_forecast` | ★ MOD |
| s_curve_jsonb[].recovery_days | pg_jsonb_key | view_builder.py:1009 | int \| null | optimizer_advice.recovery_pattern | |

### §B.13 `daily_reports.optimizer_view_jsonb`

`_build_optimizer_view` (view_builder.py:1024) + cold_start `_build_deterministic_cold_start` (view_builder.py:480).

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| optimizer_view_jsonb.by_wp[wp_id].diagnosis | pg_jsonb_key | view_builder.py:1119 / :585 | string | optimizer_advice.diagnosis 또는 `_compose_diagnosis` (cold_start) | |
| optimizer_view_jsonb.by_wp[wp_id].similar_cases | pg_jsonb_key | view_builder.py:1120 / :586 | list[{date, description, outcome}] | view_builder | |
| optimizer_view_jsonb.by_wp[wp_id].recommendations | pg_jsonb_key | view_builder.py:1121 / :587 | list[str] (rank 제거) | view_builder | |
| optimizer_view_jsonb.by_wp[wp_id].details | pg_jsonb_key | view_builder.py:1122 / :588 | list[{label, value}] (6 칸) | view_builder | |
| optimizer_view_jsonb.by_wp[wp_id].source | pg_jsonb_key | view_builder.py:589 | string (`deterministic_cold_start` / `..._no_master` / `..._master_too_small`) | cold_start only | ★ NEW |
| optimizer_view_jsonb.default_wp_id | pg_jsonb_key | view_builder.py:1128 / :1826 | string \| null | view_builder | |

### §B.14 `daily_reports.productivity_jsonb` ★ MOD (v1 ↔ v2 산식 drift)

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| productivity_jsonb (v1) | pg_jsonb_key | view_builder.py:48 _build_productivity_views | `{today:EVM, by_contractor:dict, by_l6:dict, by_wp:dict}` (EVM = `{spi, cpi, ev, pv, ac, cum_actual_qty, plan_qty_full}`) | mapper_activities + activity_master EVM | |
| productivity_jsonb.site (v2) | pg_jsonb_key | view_builder.py:1729 | `{wv_median, simple_mean, n_companies, n_l75}` | v2 산식 (group_perperson_unit + weighted_median) | ★ NEW |
| productivity_jsonb.by_company (v2) | pg_jsonb_key | view_builder.py:1735 | dict[str,{wv_median, simple_mean, n_l75, sum_wv}] | v2 | ★ NEW |
| productivity_jsonb.by_l6 (v2) | pg_jsonb_key | view_builder.py:1744 | dict[str,{wv_median, simple_mean, n_l75, sum_wv}] | v2 | ★ NEW |

### §B.15 `daily_reports.scenarios_jsonb` ★ NEW

`_build_scenarios` (view_builder.py:1215). recovery_distribution → percentile 4 (P25=낙관/P50/P75=비관 swap, view_builder.py:1239-1241).

| Source ID | Kind | Location | Type | Producer | 본 cycle |
|---|---|---|---|---|---|
| scenarios_jsonb.site.no_action | pg_jsonb_key | view_builder.py:1231 | `{expected_completion, recovery_days:0, delta_days:0, case_count}` | view_builder | ★ NEW |
| scenarios_jsonb.site.optimistic_p25 | pg_jsonb_key | view_builder.py:1239 | `{expected_completion (← no_action - P75 recovery_days), recovery_days (P75), delta_days, case_count}` | view_builder (P25 라벨 ↔ P75 값 swap, view_builder.py:1237 자인) | ★ NEW |
| scenarios_jsonb.site.base_p50 | pg_jsonb_key | view_builder.py:1240 | `{expected_completion, recovery_days (P50), delta_days, case_count}` | view_builder | ★ NEW |
| scenarios_jsonb.site.pessimistic_p75 | pg_jsonb_key | view_builder.py:1241 | `{expected_completion (← no_action - P25), recovery_days (P25), delta_days, case_count}` | view_builder | ★ NEW |
| scenarios_jsonb.by_wp[wp_id] | pg_jsonb_key | view_builder.py:1252 | (동일 4 키 site 와 같은 shape) | view_builder | ★ NEW |

---

## §C. LangGraph state attr (`pipeline/state.py` CPIAState)

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| CPIAState.run_id | state_attr | state.py:230 | str | FastAPI `/run` (사전 INSERT 된 pipeline_runs.run_id str) | checkpoint state + pipeline_runs row | |
| CPIAState.date | state_attr | state.py:231 | str (ISO YYYY-MM-DD) | FastAPI `/run` payload | checkpoint state | |
| CPIAState.input_files | state_attr | state.py:232 | list[str] | FastAPI `/run` payload | checkpoint state | |
| CPIAState.site_id | state_attr | state.py:233 | str \| None | collector_node / parser_node | checkpoint state (Optimizer view UPSERT 용) | |
| CPIAState.raw_texts | state_attr | state.py:236 | dict[str,str] | (dead — collector.py 빈 파일, drift §M-collector) | checkpoint state | |
| CPIAState.parsed | state_attr | state.py:237 | list[Activity] (실 사용은 ParsedDailyReport — 타입 drift §M-parsed) | parser_node | checkpoint state + parser_reports / parser_activities INSERT | |
| CPIAState.mapped | state_attr | state.py:238 | list[Activity] | mapper_node + hil_1_node (corrections 반영) | checkpoint state + mapper_activities INSERT | |
| CPIAState.hil_1_corrections | state_attr | state.py:239 | dict (idx → {wa, l6_main}) | hil_1_node interrupt resume payload | checkpoint state + mapping_corrections rows | |
| CPIAState.atomized_ids | state_attr | state.py:240 | list[str] (Chroma doc_id list) | atomizer_node (atomizer.py:118) | checkpoint state + Chroma daily_activities + pipeline_runs.atomized_count UPDATE + mapped_history rows | |
| CPIAState.report_md | state_attr | state.py:243 | str | reporter_node (graph.py:329) | checkpoint state + daily_reports.report_md | |
| CPIAState.forecast | state_attr | state.py:244 | list[dict] (forecast row 27 필드 dict) | forecaster_node | checkpoint state + forecasts row N개 | |
| CPIAState.hil_2_selection | state_attr | state.py:246 | list[str] (`"{company}\|{l6_main}"` keys) | hil_2_node interrupt resume payload | checkpoint state | |
| CPIAState.pre_optimizer_cases | state_attr | state.py:247 | dict[str, list[dict]] | hil_2_node (retrieve.py 산출 + .recovery 키 inject) | checkpoint state (휘발 — DB INSERT 직접 X) | |
| CPIAState.optimizer_advice | state_attr | state.py:248 | list[dict] (optimizer row 9 필드 dict) | optimizer_node | checkpoint state + optimizer_advice row N개 | |
| CPIAState.current_node | state_attr | state.py:251 | str | 모든 *_node 가 자기 이름 박음 | checkpoint state + pipeline_runs.current_node (atomizer만, drift §M-status) | |
| CPIAState.status | state_attr | state.py:252 | Literal[`running`/`waiting_hil_1`/`waiting_hil_2`/`completed`/`failed`] | (어느 node 도 직접 박지 않음 — drift §M-status) | checkpoint state | |
| CPIAState.bp_name | state_attr | state.py:262 | str | collector_node (첨부 파일명 분해) | checkpoint state | ★ NEW |
| CPIAState.project | state_attr | state.py:263 | str | collector_node (파일명 prefix) | checkpoint state | ★ NEW |
| CPIAState.message_id | state_attr | state.py:264 | str | listener invoke (RFC822 Message-ID) | checkpoint state + collector_inbox.run_id update 용 | ★ NEW |
| CPIAState.postgres_url | state_attr | state.py:265 | str | collector_node (collector_inbox UPDATE 용) | checkpoint state | ★ NEW |

총 20 state_attr (이전 15 + collector 4 신규 + site_id propagate 1).

---

## §D. Agent output dataclass / field

### §D.1 `ParsedDailyReport` (`state.py:207`, parser_node 산출)

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| ParsedDailyReport.report_date | dataclass_field | state.py:216 | str | parser_node | parser_reports.report_date | |
| ParsedDailyReport.project | dataclass_field | state.py:217 | str | parser_node | parser_reports.project | |
| ParsedDailyReport.bp_summaries | dataclass_field | state.py:218 | list[BPSummary] | parser_node | parser_reports.bp_summaries (jsonb) | |
| ParsedDailyReport.job_allocations | dataclass_field | state.py:219 | list[JobAllocation] | parser_node | parser_reports.job_allocations (jsonb) + parser_job_allocations rows | |
| ParsedDailyReport.equipment_allocations | dataclass_field | state.py:220 | list[EquipmentAllocation] | parser_node | parser_reports.equipment_allocations (jsonb) + parser_equipment_allocations rows | |
| ParsedDailyReport.activities | dataclass_field | state.py:221 | list[Activity] | parser_node | parser_activities rows + mapper_activities rows (mapper 후) | |
| ParsedDailyReport.worker_outputs | dataclass_field | state.py:222 | list[WorkerOutput] (업체별 only) | parser_node | parser_worker_outputs rows (merge 후) | ★ NEW |
| ParsedDailyReport.report_meta | dataclass_field | state.py:223 | ReportMeta \| None | parser_node | parser_report_meta rows (merge 후) | ★ NEW |

### §D.2 `Activity` (`state.py:32`, 시트4 1행)

37 필드 — 전수.

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| Activity.zone | dataclass_field | state.py:46 | str \| None | parser_node | parser_activities.zone, mapper_activities.zone | |
| Activity.bp_code | dataclass_field | state.py:47 | str \| None | parser_node | parser_activities.bp_code, mapper_activities.bp_code | |
| Activity.company | dataclass_field | state.py:48 | str NOT NULL | parser_node | (전 테이블) | |
| Activity.scope | dataclass_field | state.py:49 | str \| None | parser_node | parser_activities.scope, mapper_activities.scope | |
| Activity.trade | dataclass_field | state.py:50 | str (l5_disc 한글) | parser_node | parser_activities.trade, mapper_activities.trade — mapped_history.trade 적재 (★ INSERT 누락 #C3) | |
| Activity.work_content | dataclass_field | state.py:51 | str | parser_node | atomizer Chroma documents (atomizer.py:101) | |
| Activity.unit | dataclass_field | state.py:52 | str | parser_node | atomizer Chroma metadata.unit, mapped_history.unit | |
| Activity.plan_total_qty | dataclass_field | state.py:53 | float \| None | parser_node | mapper_activities.plan_total_qty | |
| Activity.yesterday_cum_qty | dataclass_field | state.py:54 | float \| None | parser_node | parser_activities.yesterday_cum_qty | |
| Activity.today_qty | dataclass_field | state.py:55 | float | parser_node | mapped_history.today_qty, atomizer Chroma metadata | |
| Activity.today_cum_qty | dataclass_field | state.py:56 | float \| None | parser_node | parser_activities.today_cum_qty, mapper_activities.today_cum_qty (s_curve actual) | |
| Activity.progress_percent | dataclass_field | state.py:57 | float \| None | parser_node | (전 테이블) | |
| Activity.remaining_qty | dataclass_field | state.py:58 | float \| None | parser_node | (전 테이블) | |
| Activity.remaining_percent | dataclass_field | state.py:59 | float \| None | parser_node | (전 테이블) | |
| Activity.note | dataclass_field | state.py:60 | str \| None | parser_node | (전 테이블) | |
| Activity.work_location_code | dataclass_field | state.py:63 | str \| None | parser_node (업체별 시트4) | (전 테이블) | |
| Activity.wbs_mid_name | dataclass_field | state.py:64 | str \| None | parser_node (업체별 시트4) | (전 테이블) | |
| Activity.wbs_sub_name | dataclass_field | state.py:65 | str \| None | parser_node (업체별 시트4) | (전 테이블) | |
| Activity.wbs_detail_name | dataclass_field | state.py:66 | str \| None | parser_node (업체별 시트4) | (전 테이블) | |
| Activity.wbs_activity_id | dataclass_field | state.py:69 | str \| None (PoC: 항상 None) | mapper_node | (drift §M-poc-none) | |
| Activity.l5_disc | dataclass_field | state.py:70 | str | parser_node | atomizer Chroma metadata.l5_disc, mapper_activities.l5_disc | ★ NEW (mapper_activities propagate) |
| Activity.l6_main | dataclass_field | state.py:71 | str \| None | mapper_node | mapper_activities.l6_main, mapped_history.l6_main, forecasts.l6_main | |
| Activity.l7_sub | dataclass_field | state.py:72 | str \| None (PoC: None — 1:N) | mapper_node | mapper_activities.l7_sub | ★ NEW (column) |
| Activity.l7_5_activity | dataclass_field | state.py:73 | str \| None (PoC: None — 1:N) | mapper_node | mapper_activities.l7_5_activity | ★ NEW (column) |
| Activity.sub_work_area | dataclass_field | state.py:74 | str \| None (PoC: None — 1:N) | mapper_node | mapper_activities.sub_work_area | ★ NEW (column) |
| Activity.conditions | dataclass_field | state.py:75 | list[str] | parser_node | atomizer Chroma metadata.conditions (comma-join), mapper_activities.conditions (jsonb list) | |
| Activity.assigned_workers | dataclass_field | state.py:79 | float | mapper `_prorate_mh` (mapper.py:389) | mapper_activities.assigned_workers, mapped_history.today_assigned_workers, forecasts.today_assigned_workers, atomizer Chroma metadata | |
| Activity.worker_source | dataclass_field | state.py:80 | Literal[`parsed`/`mh_prorated`/`user_corrected`] | mapper `_prorate_mh` | mapper_activities.worker_source, atomizer Chroma metadata.worker_source (optimizer/retrieve.py:92 filter key) | |
| Activity.plan_mh | dataclass_field | state.py:85 | float \| None | (PoC: 항상 None — _prorate_mh 가 PG 별도 조회) | mapper_activities.plan_mh (quadrant impact 산식) | |
| Activity.wa | dataclass_field | state.py:88 | str \| None | mapper_node | mapper_activities.wa, mapped_history.wa, forecasts.wa, atomizer Chroma metadata, mapping_corrections.original.wa | |
| Activity.mapping_conf | dataclass_field | state.py:89 | float \| None | mapper_node (rerank confidence) | mapper_activities.mapping_conf, hil_1 review filter (graph.py:120) | |
| Activity.mapping_source | dataclass_field | state.py:90 | str \| None | mapper_node | mapper_activities.mapping_source, mapping_corrections.original.mapping_source | |
| Activity.requires_review | dataclass_field | state.py:93 | bool | mapper_node | mapper_activities.requires_review, hil_1 review_needed filter | |

### §D.3 `BPSummary` / `JobAllocation` / `EquipmentAllocation` (`state.py:96~167`)

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| BPSummary.bp_code | dataclass_field | state.py:102 | str \| None | parser_node | parser_reports.bp_summaries (jsonb) | |
| BPSummary.company | dataclass_field | state.py:103 | str | parser_node | parser_reports.bp_summaries (jsonb) | |
| BPSummary.disc_abbrev | dataclass_field | state.py:104 | str \| None | parser_node | parser_reports.bp_summaries (jsonb) | |
| BPSummary.zone | dataclass_field | state.py:105 | str \| None | parser_node | parser_reports.bp_summaries (jsonb) | |
| BPSummary.scope | dataclass_field | state.py:106 | str \| None | parser_node | parser_reports.bp_summaries (jsonb) | |
| BPSummary.work_text_yesterday | dataclass_field | state.py:107 | str \| None | parser_node | parser_reports.bp_summaries (jsonb) | |
| BPSummary.work_text_today | dataclass_field | state.py:108 | str \| None | parser_node | parser_reports.bp_summaries (jsonb) — mapper bp_context 의 시트1 텍스트 | |
| BPSummary.work_text_tomorrow | dataclass_field | state.py:109 | str \| None | parser_node | parser_reports.bp_summaries (jsonb) | |
| BPSummary.workers_yesterday_incr / workers_yesterday_cum / workers_today_incr / workers_today_cum | dataclass_field | state.py:112~115 | TimeShiftCounts \| None (jsonb 6필드 `morning/daytime/overtime/night/all_night/total`) | parser_node | parser_reports.bp_summaries (jsonb) | ★ NEW (4 시간대 그룹) |
| BPSummary.today_incr_total / today_cum_total | dataclass_field | state.py:118,119 | int | parser_node | (편의 Total) | |
| JobAllocation.bp_code / company / disc_abbrev / manager_code / worker_code / job_type | dataclass_field | state.py:128~133 | str / str / str / str / str / str | parser_node | parser_job_allocations (각 컬럼) | |
| JobAllocation.workers_yesterday_cum / workers_today_incr / workers_today_cum | dataclass_field | state.py:136~138 | TimeShiftCounts \| None | parser_node | parser_job_allocations (jsonb) | ★ NEW (3 시간대 그룹) |
| JobAllocation.final_flag | dataclass_field | state.py:140 | str \| None (O/X) | parser_node | parser_job_allocations.final_flag | |
| JobAllocation.workers_cum_t | dataclass_field | state.py:143 | int | parser_node | parser_job_allocations.workers_cum_t (편의 Total) | |
| EquipmentAllocation.bp_code / company / disc_abbrev / equipment_big / equipment_mid / equipment_spec | dataclass_field | state.py:152~157 | str/str/str/str/str/str | parser_node | parser_equipment_allocations (각 컬럼) | |
| EquipmentAllocation.count_yesterday_cum / count_today_incr / count_today_cum | dataclass_field | state.py:160~162 | TimeShiftCounts \| None | parser_node | parser_equipment_allocations (jsonb) | ★ NEW |
| EquipmentAllocation.final_flag / count_cum_t | dataclass_field | state.py:164,167 | str \| None / int | parser_node | parser_equipment_allocations (각 컬럼) | |

### §D.4 `WorkerOutput` (`state.py:170`) ★ NEW + `ReportMeta` (`state.py:193`) ★ NEW

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| WorkerOutput.worker_name / job_type / wbs_mid_name / wbs_sub_name / wbs_detail_name / work_location_code / work_content | dataclass_field | state.py:177~183 | str / str / str?/str?/str?/str?/str? | parser_post merge | parser_worker_outputs (각 컬럼) | ★ NEW |
| WorkerOutput.shift_morning / shift_daytime / shift_overtime / shift_night / shift_all_night | dataclass_field | state.py:185~189 | int (1/0 또는 시간) | parser_post merge | parser_worker_outputs (각 컬럼) | ★ NEW |
| WorkerOutput.note | dataclass_field | state.py:190 | str \| None | parser_post merge | parser_worker_outputs.note | ★ NEW |
| ReportMeta.project_name / project_code / site_id / bp_name / writer / reviewer / approval / report_date / document_no | dataclass_field | state.py:196~204 | (각 str \| None, report_date 만 str) | parser_post merge | parser_report_meta (각 컬럼) | ★ NEW |

### §D.5 Forecaster forecast row dict (`pipeline/agents/forecaster/agent.py:190~226`)

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| forecast[].run_id / company / l6_main / today_qty_by_unit / today_assigned_workers / today_productivity / plan_total_qty_by_unit / plan_mh_sum / plan_start / plan_finish / plan_mh_per_day / schedule_state / window_start / window_days / expected_in_window_mh / actual_in_window_mh / mh_gap / delay_days / rag_n_similar / similar_cases / assessment / reasoning / recovery_likelihood / expected_completion / risk_level / main_unit / today_conditions | dataclass_field | forecaster/agent.py:191~225 | (forecasts 28 컬럼 dict — §A.4 와 1:1) | forecaster | forecasts (insert_forecast db.py:260) | |
| forecast[].wa | dataclass_field | forecaster/agent.py | str (Phase 2 grain 추가) | forecaster | forecasts.wa | ★ MOD (grain) |

### §D.6 hil_2 pre_cases dict value (`pipeline/agents/optimizer/retrieve.py:106~161`)

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| pre_cases[k][].date | dataclass_field | retrieve.py:106 | str (ISO date) | optimizer/retrieve | optimizer_advice.degradation_cases (jsonb) | |
| pre_cases[k][].conditions | dataclass_field | retrieve.py:107 | str (comma-joined) | optimizer/retrieve | optimizer_advice.degradation_cases (jsonb) | |
| pre_cases[k][].productivity / assigned_workers / activities | dataclass_field | retrieve.py:108~110 | float / float / list[str] | optimizer/retrieve | optimizer_advice.degradation_cases (jsonb) | |
| pre_cases[k][].recovery | dataclass_field | retrieve.py:161 + graph.py:262 | dict (trajectory + recovery_days) | optimizer/retrieve | optimizer_advice.degradation_cases[].recovery (jsonb) | |

### §D.7 Optimizer row dict (`pipeline/agents/optimizer/agent.py:63~87`)

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| optimizer_advice[].run_id / company / l6_main / forecast_assessment / diagnosis / degradation_cases / recovery_pattern / recovery_distribution / recommendations | dataclass_field | optimizer/agent.py:63~87 | (optimizer_advice 9 컬럼 dict — §A.5 와 1:1) | optimizer | optimizer_advice (insert_optimizer_advice db.py:332) | |

### §D.8 Reporter summary dict (`pipeline/agents/reporter.py:108~111`)

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| reporter.summary.total_workers / total_qty_by_trade / risk_counts / advice_count | dataclass_field | reporter.py:108~111 | (history_csv_row 4 키 — §B.1 과 1:1) | reporter | daily_reports.history_csv_row (jsonb) | |

### §D.9 site_summary LLM payload (`pipeline/agents/optimizer/site_summary.py:46~114`) ★ NEW

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| site_summary.payload.report_date | dataclass_field | site_summary.py:102 | str (ISO date) | `build_site_summary_payload` | LLM input | ★ NEW |
| site_summary.payload.site_id | dataclass_field | site_summary.py:103 | str | builder | LLM input | ★ NEW |
| site_summary.payload.progress_pct | dataclass_field | site_summary.py:104 | `{planned, actual}` (s_curve report_date 시점 값) | builder | LLM input | ★ NEW |
| site_summary.payload.gap_pct | dataclass_field | site_summary.py:105 | number (`planned - actual`) | builder | LLM input | ★ NEW |
| site_summary.payload.delay_days | dataclass_field | site_summary.py:106 | int (kpi.delay_days) | builder | LLM input | ★ NEW |
| site_summary.payload.ai_recovery_days | dataclass_field | site_summary.py:107 | int (scenarios.site.base_p50.recovery_days) | builder | LLM input | ★ NEW |
| site_summary.payload.expected_completion | dataclass_field | site_summary.py:108 | `{if_no_action, ai_scenario, plan}` | builder | LLM input | ★ NEW |
| site_summary.payload.top_risk_wps | dataclass_field | site_summary.py:113 | list[{wp_name, trade, diagnosis, top_recommendation}] (impact desc top 3, `cold_start` 진단 제외) | builder | LLM input | ★ NEW |
| site_summary.output | dataclass_field | site_summary.py:135 | str (Azure JSON `{"summary": "..."}` 의 `summary` 추출, 200~300자 한국어) | `generate_site_summary` (Azure OpenAI, `response_format={"type": "json_object"}`) | daily_reports.site_summary_text | ★ NEW |

> **호출 경로**: graph.py reporter_node 가 site_summary 호출 X. live cycle 에서 박는 path **부재** — `scripts/backfill_daily_report_views_v2.py:152~167` (--with-summary 옵션) + `scripts/backfill_optimizer_advice_llm.py:272` 의 backfill 호출이 유일. 따라서 prod live 일보는 site_summary_text NULL (이슈 #N14 — graph integration backlog).

### §D.10 Chroma metadata (`pipeline/agents/atomizer.py:47~58`)

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| chroma.daily_activities.documents | chroma_meta | atomizer.py:101 | str (Activity.work_content) | atomizer | Chroma daily_activities | |
| chroma.daily_activities.metadata.date | chroma_meta | atomizer.py:47 | str (ISO) | atomizer | Chroma | |
| chroma.daily_activities.metadata.run_id | chroma_meta | atomizer.py:48 | str (uuid) | atomizer | Chroma | |
| chroma.daily_activities.metadata.company / l5_disc / l6_main / wa / unit / today_qty / assigned_workers / worker_source / mapping_conf / conditions | chroma_meta | atomizer.py:49~58 | mixed (conditions = comma-joined str) | atomizer | Chroma (forecaster/optimizer retrieve 소비) | |
| chroma.daily_activities.metadata.l7_5_activity / perperson / productivity_pct / augmented / augmented_from_company / worker_source=`backfill_v2` | chroma_meta | scripts/backfill_chroma_daily_activities.py (외부) | mixed | backfill v2 (외부) | Chroma (view_builder._get_all_backfill_metas 사용) | ★ NEW |
| chroma.daily_activities.hnsw.M / construction_ef / search_ef | chroma_meta | chroma_client.py:41~43 | int (32 / 200 / 100) | `ChromaClient.get_or_create_daily_activities` | Chroma collection metadata (2026-05-26 16/10 → 32/200/100, 좁은 filter contigious 2D array 에러 회피) | ★ NEW |
| chroma.wbs_master.documents | chroma_meta | chroma_client.py:24 | str (mapping-layer.md §5.2 형식) | scripts/load_wbs_master.py (외부) | Chroma wbs_master (mapper RAG) | |
| chroma.wbs_master.hnsw.space | chroma_meta | chroma_client.py:27 | str (= `cosine`) | `ChromaClient.get_or_create_wbs_master` | Chroma collection metadata | |

---

## §E. FastAPI 12 endpoint (`pipeline/api.py`) + 1 router (`exporter_routes.py`)

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| GET /health | api_endpoint | api.py:211 | `{status, pg:bool, version}` | `pg.fetch_one("SELECT 1 AS ok")` (api.py:215) | (probe) | |
| POST /api/runs/{run_id}/hil_1/resume | api_endpoint | api.py:223 | `Hil1ResumeResponse {next_node}` | `graph.ainvoke(Command(resume=corrections_payload))` (api.py:251) — 내부 `insert_mapping_correction` | EmptyChannelError → 404, InvalidUpdateError → 409 | |
| GET /api/sites | api_endpoint | api.py:337 | `Site[]` 16 필드 (`id/name/location/status/progress_planned/progress_actual/gap_percent/spi/productivity_today/abnormal_trades/fte_saved/hours_saved/headcount/total_hours/ai_replacement_rate/expected_completion/recovered_completion/delay_days/recovery_days`) | `_SITES_SQL` (api.py:279) — sites LEFT JOIN LATERAL forecasts | dashboard Layer 1 | |
| GET /api/runs/{run_id}/optimizer | api_endpoint | api.py:401 | `OptimizerOutput[]` `{wp_id, diagnosis, similar_cases, recommendations:list[str], details:list[{label,value}]}` | `_OPTIMIZER_SQL` (api.py:352) — optimizer_advice | 현장 상세 Optimizer 패널 | |
| GET /api/runs/{run_id}/wp_summary | api_endpoint | api.py:481 | `WPSummaryRow[]` `{wp_id, wp_name, trade, bp_name, start_date, end_date, progress_pct, productivity, status}` | `_WP_SUMMARY_SQL` (api.py:419) — mapped_history JOIN activity_master JOIN forecasts (triplet) | WP 표 | |
| GET /api/sites/{site_id}/reports | api_endpoint | api.py:542 | `ReportDaily[]` `{date, status, productivity_today, delay_days, recovery_days}` | `_SITE_REPORTS_SQL` (api.py:500) — pipeline_runs JOIN forecasts, days max 90 | 날짜별 카드 | |
| GET /api/dashboard/performance | api_endpoint | api.py:583 | `{productivity_today, delay_days, recoverable_days:int, abnormal_trades:int}` | `_DASHBOARD_PERFORMANCE_SQL` (api.py:562) — last_runs CTE + weighted sum (`d+1·1 + d+2·2 + d+3·3 + d+5·5 + d+7·7`) | fleet KPI 카드 | |
| GET /api/dashboard/impact | api_endpoint | api.py:643 | `ImpactSiteDistribution[]` `{site_id, site_name, hours_saved, fte_saved}` | `_DASHBOARD_IMPACT_SQL` (api.py:622) — sites ORDER BY hours_saved DESC | site별 hours_saved bar | |
| GET /api/agents/status | api_endpoint | api.py:729 | `AgentStatus[]` 7개 (`{step, name, korean_name, description, model, group, active_count, state}`) | 7× `_AGENT_ACTIVE_COUNT_SQL` (api.py:721) — N+1 (이슈 §M-agentsN1) | "에이전트 현황" 카드 | |
| GET /api/sites/{site_id}/wbs_tree | api_endpoint | api.py:832 | `WBSNode` 단일 루트 (`{id, type:building, name, parent_id:null, review_count:0, status:unknown, children:[trade]}`) trade 아래 work_package | `_WBS_TREE_SQL` (api.py:768) — activity_master DISTINCT l5_disc, l6_main | WBS 사이드바 | |
| GET /api/tasks | api_endpoint | api.py:1045 | `{tasks:DailyTask[], progressByDate:dict, itemsByDate:dict}` (days max 90) | `_TASKS_SQL` (api.py:876) + `_TASKS_ITEMS_SQL` (api.py:912) | "작업일보 처리 현황" 페이지 (이슈 §M-tasks-collector) | |
| GET /export/run | api_endpoint | exporter_routes.py:16 | `Response (xlsx bytes, Content-Disposition UTF-8)` | `fetch_site_by_id` + `fetch_sheet_data` (exporter.py:34, pipeline_runs JOIN parser_reports + parser_activities 4 시트 합집합) + `render_xlsx` (exporter.py:290) | 통합 작업일보 다운로드 (★ ad-hoc PGClient — 이슈 §M-export-pool) | ★ NEW |

**lifespan** (api.py:147~195):
1. POSTGRES_URL 검증 → RuntimeError fail-fast (api.py:158).
2. `PGClient(pg_url).connect()` → `app.state.pg` (api.py:163~165).
3. `_build_prod_graph_config()` → `build_graph(cfg)` (api.py:169~170) — `build_checkpointer()` 내부 호출.
4. **Collector idle (★ NEW, api.py:174~183)**: `load_collector_config(graph_cfg=cfg).enabled == True` 시 `asyncio.create_task(idle_loop(collector_cfg))`. 자격증명 누락은 RuntimeError fail-fast.
5. `yield`.
6. shutdown: `request_shutdown()` flag → `collector_task.cancel()` → `await pg.close()` (api.py:188~195).

**router include** (api.py:203, ★ NEW): `app.include_router(exporter_router)` — `/export` prefix.

---

## §F. db.py helper 시그니처 (35 함수)

### §F.1 PGClient class (28 instance method)

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| PGClient.__init__ | dataclass_field | db.py:18 | `(dsn, min_size=1, max_size=5)` | api.py:163, exporter_routes.py:23 | (pool 메타) | |
| PGClient.connect | dataclass_field | db.py:24 | `() -> None` | lifespan / exporter_routes | `asyncpg.create_pool` | |
| PGClient.close | dataclass_field | db.py:32 | `() -> None` | lifespan / exporter_routes | `pool.close()` | |
| PGClient.fetch_bp_candidates | dataclass_field | db.py:38 | `(company, site_id=None) -> list[dict]` | mapper (graph.py:79) | `SELECT DISTINCT wa, l6_main FROM activity_master WHERE company=$1 [AND site_id=$2]` | |
| PGClient.fetch_activity | dataclass_field | db.py:73 | `(wbs_activity_id, site_id=None) -> dict\|None` | test only (이슈 §M-dead-fetch_activity) | activity_master single row | |
| PGClient.fetch_l6_plan_mh_map | dataclass_field | db.py:106 | `(company, l6_list, site_id=None) -> dict[str,int]` | mapper `_prorate_mh` | activity_master GROUP BY l6_main SUM plan_mh_rev2 | |
| PGClient.insert_pipeline_run | dataclass_field | db.py:147 | `(run_id, site_id, date, status='running')` | test fixture | pipeline_runs INSERT | |
| PGClient.delete_pipeline_run | dataclass_field | db.py:170 | `(run_id)` | test fixture cleanup | pipeline_runs DELETE | |
| PGClient.assert_pipeline_run_exists | dataclass_field | db.py:176 | `(run_id)` raises RuntimeError | atomizer fail-fast | `SELECT 1 LIMIT 1` | |
| PGClient.fetch_plan_for_group | dataclass_field | db.py:194 | `(company, l6_main, site_id=None) -> dict` (qty_by_unit + plan_mh_sum + plan_start + plan_finish) | forecaster | 2 SELECT (GROUP BY unit + SUM/MIN/MAX) — jsonb dup key 회피 | |
| PGClient.update_run_atomized_count | dataclass_field | db.py:238 | `(run_id, count)` raises RuntimeError on 0 row | atomizer 종료 | `UPDATE pipeline_runs SET atomized_count=$1, current_node='atomizer'` (hard-code current_node) | |
| PGClient.insert_forecast | dataclass_field | db.py:260 | `(row: dict)` 28 컬럼 | forecaster/agent.py:331 | forecasts INSERT | |
| PGClient.insert_optimizer_advice | dataclass_field | db.py:332 | `(row: dict)` 9 컬럼 | optimizer/agent.py:182 | optimizer_advice INSERT | |
| PGClient.insert_mapping_correction | dataclass_field | db.py:370 | `(run_id, report_date, original, corrected)` | hil_1_node graph.py:265 | mapping_corrections INSERT | |
| PGClient.insert_daily_report | dataclass_field | db.py:405 | `(run_id, report_date, report_md, history_csv_row, bp_name=None, site_id=None)` UPDATE-first 패턴 (partial unique idx 회피) | reporter.py:151 | daily_reports UPDATE → INSERT | |
| PGClient.insert_mapped_history_batch | dataclass_field | db.py:458 | `(run_id, report_date, site_id, rows)` ON CONFLICT (run_id, wa, l6_main, company) DO UPDATE | atomizer.py:190 | mapped_history executemany — **trade 컬럼 INSERT 누락 #C3** | ★ MOD (trade 누락) |
| PGClient.get_pipeline_run | dataclass_field | db.py:504 | `(run_id) -> dict\|None` | (현 cycle 외부 미호출) | pipeline_runs SELECT | |
| PGClient.insert_parser_report | dataclass_field | db.py:515 | `(run_id, report_date, project, bp_summaries, job_allocations, equipment_allocations, activity_count)` ON CONFLICT (run_id) DO UPDATE | graph.py:110 | parser_reports INSERT | |
| PGClient.insert_parser_activities_batch | dataclass_field | db.py:558 | `(run_id, report_date, activities)` 23 컬럼 ON CONFLICT (run_id, idx) DO UPDATE | graph.py:120 | parser_activities executemany | |
| PGClient.insert_mapper_activities_batch | dataclass_field | db.py:639 | `(run_id, report_date, activities)` 37 컬럼 (★ 본 cycle 마지막 4 propagate) ON CONFLICT (run_id, idx) DO UPDATE | graph.py:149 | mapper_activities executemany | ★ MOD (+4 col) |
| PGClient.insert_parser_job_allocations_batch | dataclass_field | db.py:771 | `(run_id, report_date, rows)` 14 컬럼 (3 jsonb) | graph.py:130 | parser_job_allocations executemany | |
| PGClient.insert_parser_equipment_allocations_batch | dataclass_field | db.py:843 | `(run_id, report_date, rows)` 14 컬럼 (3 jsonb) | graph.py:136 | parser_equipment_allocations executemany | |
| PGClient.insert_parser_worker_outputs_batch | dataclass_field | db.py:909 | `(run_id, report_date, rows, bp_name=None)` 시트6 17 컬럼 | merge 노드 | parser_worker_outputs executemany | |
| PGClient.insert_parser_report_meta_batch | dataclass_field | db.py:980 | `(run_id, report_date, metas)` UNIQUE (run_id, bp_name) | merge 노드 | parser_report_meta executemany | |
| PGClient.fetch_one | dataclass_field | db.py:1028 | `(sql, *args) -> dict\|None` | api.py:215 (/health), api.py:592 (/dashboard/performance) | 임의 SELECT 1 row | |
| PGClient.fetch_all | dataclass_field | db.py:1039 | `(sql, *args) -> list[dict]` | api.py 대부분 endpoint | 임의 SELECT | |
| PGClient._VIEW_JSONB_COLS | dataclass_field | db.py:1050 | tuple[str] 9개 (`kpi/contractor_bars/trade_bars/quadrant/wp_summary/s_curve/optimizer_view/productivity/scenarios`) | `upsert_daily_report_view_col` 내부 | SQL injection 가드 화이트리스트 — site_summary_text 미포함 (#M4) | ★ MOD (+scenarios_jsonb) |
| PGClient.upsert_daily_report_view_col | dataclass_field | db.py:1062 | `(run_id, site_id, report_date, col, value)` UPDATE-first + 화이트리스트 | optimizer/agent.py:220 (9회) | daily_reports.{col} UPDATE → INSERT | |

### §F.2 모듈 함수 (7)

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| update_site_last_run | dataclass_field | db.py:1109 | `(pg, site_id, run_id)` | graph.py:473 reporter→END | sites.last_run_id UPDATE | |
| AS_IS_MIN / TO_BE_MIN | dataclass_field | db.py:1121,1122 | int (=120) / int (=5) | G2 산식 상수 | (일보당 수작업 분 vs AI 처리 분) | |
| update_site_hours_saved_cum | dataclass_field | db.py:1125 | `(pg, site_id, atomized_count)` 산식 `(120-5)/60 × N` h | graph.py:474 reporter→END | sites.hours_saved_cum UPDATE | |
| insert_collector_inbox | dataclass_field | db.py:1149 | `(pg, *, message_id, site_id, report_date, bp_name, attachment_filename, attachment_path)` ON CONFLICT (message_id) DO NOTHING | collector/idle_worker.py | collector_inbox INSERT (dedup race) | ★ NEW |
| update_collector_inbox_status | dataclass_field | db.py:1179 | `(pg, message_id, *, run_id=None, parse_status, error=None)` `run_id = COALESCE($3, run_id)` | collector/idle_worker.py + collector_node.py | collector_inbox UPDATE | ★ NEW |
| fetch_collector_inbox_by_message_id | dataclass_field | db.py:1206 | `(pg, message_id) -> dict\|None` | collector/idle_worker.py | collector_inbox SELECT (dedup check) | ★ NEW |
| fetch_site_by_id | dataclass_field | db.py:1220 | `(pg, site_id) -> dict\|None` (site_id, name, plan_progress, actual_progress, status, location) | exporter_routes.py:26 | sites SELECT (/export/run site name 조회) | ★ NEW |

---

## §G. Derived 산식 (DB 비저장, API/transform 시 계산)

| Source ID | Kind | Location | Type | Producer | Persistence | 본 cycle |
|---|---|---|---|---|---|---|
| s_curve.planned (산식 A) | derived_metric | view_builder.py:914~936 | `SUM(plan_wv × plan_mh_rev2 × LEAST(1.0, GREATEST(0.0, (gs.date - plan_start + 1) / NULLIF(plan_finish - plan_start + 1, 0))))` | view_builder | s_curve_jsonb[].planned | ★ MOD |
| s_curve.actual (산식 A) | derived_metric | view_builder.py:942~981 | full_grid CROSS JOIN am_agg × dates + WINDOW SUM (PARTITION BY wa, l6_main ORDER BY report_date) — 단조 누적 보장. cap = `LEAST(1.0, cum_qty / plan_qty)` × weight (`plan_wv × plan_mh_rev2`) | view_builder | s_curve_jsonb[].actual | ★ MOD |
| s_curve.percent denominator | derived_metric | view_builder.py:899,1020 | `SUM(plan_wv × plan_mh_rev2)` (site 전체) → % 환산 (`x / site_total_weight × 100`, cap 100) | view_builder | s_curve_jsonb 전 row | ★ MOD |
| s_curve.forecast | derived_metric | view_builder.py:824~877 `_extend_forecast` | 직전 7일 평균 rate (or planned×0.7 fallback) × remaining days, dedup | view_builder | s_curve_jsonb[].forecast | ★ MOD |
| kpi.delay_days MEDIAN | derived_metric | view_builder.py:296~309 / 1693~1706 | `PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delay_days)` (forecasts JOIN pipeline_runs WHERE site_id, report_date 일치) — AVG → MEDIAN 변경 (outlier 1건 끌림 해소) | view_builder | kpi_jsonb.delay_days | ★ MOD |
| kpi.expected_completion MEDIAN | derived_metric | view_builder.py:296~309 / 1693~1706 | `PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY expected_completion)` | view_builder | kpi_jsonb.expected_completion | ★ MOD |
| scenarios percentile 4 | derived_metric | view_builder.py:1230~1242 (site) + 1252~1263 (by_wp) | recovery_distribution → `_expand_recovery_to_days` (not_recovered=30 일 캡, view_builder.py:1154) → `_percentile` (statistics.quantiles n=100, view_builder.py:1172) → 4 시나리오 (P25/P50/P75 라벨↔값 swap: P25=낙관=P75일 적용, P75=비관=P25일 적용) | view_builder | scenarios_jsonb (site + by_wp) | ★ NEW |
| quadrant.impact P90 normalize (v1) | derived_metric | view_builder.py:369~382 | raw_impact = `SUM(plan_total_qty) × AVG(plan_mh)` (mapper_activities GROUP BY wa, l6, company) → `_compute_impact_p90` (n≥10 시 quantiles n=10 8번째, 아니면 max) → `_normalize_impact` (min 100, raw / p90 × 100) | view_builder | quadrant_jsonb[].impact (v1) | |
| quadrant.impact share-of-total (v2) | derived_metric | view_builder.py:1331~1345 | `_normalize_impact_share` — `x / total × 100` (일별 합 = 100%) | view_builder v2 | quadrant_jsonb[].impact (v2) | ★ NEW |
| site_summary payload top 3 risk wp | derived_metric | site_summary.py:71~99 | wp_summary impact desc sort top 3, optimizer_view.by_wp[wp_id] 에서 diagnosis (`cold_start` 제외) + recommendations[0] | view_builder + site_summary | LLM input (top_risk_wps) | ★ NEW |
| site_summary payload progress_pct | derived_metric | site_summary.py:63~65 | s_curve 에서 `date == report_date` 시점의 planned / actual | view_builder + site_summary | LLM input (progress_pct) | ★ NEW |
| dashboard.recoverable_days weighted sum | derived_metric | api.py:569~575 | `SUM(d+1·1 + d+2·2 + d+3·3 + d+5·5 + d+7·7)` (recovery_distribution 키 weighted) — not_recovered 무가중치 | api endpoint | `/api/dashboard/performance` | |
| sites.hours_saved_cum 산식 | derived_metric | db.py:1135 | `((AS_IS_MIN - TO_BE_MIN) / 60.0) × atomized_count` = `(120-5)/60 × N` h | `update_site_hours_saved_cum` | sites.hours_saved_cum 누적 | |
| sites.ai_replacement_rate | derived_metric | api.py:288 | `s.hours_saved / (s.headcount × 140) × 100` (단, headcount > 0 일 때만) | `_SITES_SQL` | Site.ai_replacement_rate | |
| AgentTaskItem.id | derived_metric | api.py:1030 | `RPT-{date.replace('-', '')}-{idx_by_date[date]:03d}` (날짜 + 순번) | `_build_items_by_date` | `/api/tasks` itemsByDate | |
| `/api/tasks` progress_percent | derived_metric | api.py:881~893 | current_node → percent (collector 12.5 / parser 25 / mapper or hil_1 37.5 / atomizer 50 / reporter 62.5 / forecaster 75 / optimizer 87.5 / completed 100) AVG | `_TASKS_SQL` | DailyTask.progress_percent | |

---

## §H. 본 cycle (ef7c6cd → 1ba783f) 변경 요약 (★ NEW + ★ MOD source)

| commit | 파일 / source | 변경 카탈로그 row | 본 cycle 영향 |
|---|---|---|---|
| `b614bff` | migrations/2026-05-20_add_is_mock.sql | 7 테이블 × `is_mock BOOL` (pipeline_runs / parser_reports / parser_activities / mapper_activities / forecasts / optimizer_advice / daily_reports) | §A 7 row ★ NEW + view_builder 가 `ma.is_mock = FALSE` 필터 (view_builder.py:203) |
| `3db3d18` | migrations/2026-05-21_phase1.sql | `prototype_embedding_cache` + `mapped_history_merge_log` 2 테이블 신설 (16 row) | §A.9, §A.18 ★ NEW |
| `7b96b1a` | migrations/2026-05-19_collector_inbox.sql + db.py:1145~1217 | `collector_inbox` 11 row + 4 module helper | §A.17 ★ NEW + §F.2 4 helper ★ NEW |
| `a7e2465` | pipeline/exporter_routes.py (신규 47 LOC) | `GET /export/run` endpoint | §E 1 row ★ NEW |
| `b3010df` | pipeline/agents/exporter.py:34 | `fetch_sheet_data` 가 pipeline_runs JOIN parser_reports + parser_activities 합집합 SQL | §E /export/run 의존 |
| `4b8a955` | pipeline/api.py:147,203 (+23 LOC) | lifespan 안 collector idle task spawn + `app.include_router(exporter_router)` | §E lifespan 변경 |
| `7e9e1a1` | merge (`21c10f7` 포함) | `daily_reports.site_summary_text` runtime ALTER + LLM site narrative | §A.7 site_summary_text ★ NEW (★ migration 부재 #C1) + §D.9 site_summary payload ★ NEW |
| `d40c84f` | migrations/2026-05-23_mapper_l7_5_columns.sql + db.py:639~765 | mapper_activities 4 컬럼 (l5_disc / l7_sub / l7_5_activity / sub_work_area) | §A.12 4 row ★ NEW + view_builder.py:1445 v2 필터 의존 |
| `2026-05-19_daily_reports_views.sql` (cycle 시작점 직후) | daily_reports 8 view jsonb + site_id partial unique idx + mapper_activities cum_workers_today / cum_actual_mh_today | §A.7, §A.12 row | |
| `2026-05-19_scenarios_jsonb.sql` | daily_reports.scenarios_jsonb (4 시나리오) | §A.7 scenarios_jsonb + §B.15 + §G scenarios 산식 ★ NEW | |
| `2026-05-19_mapped_history_trade.sql` + atomizer.py:130 | mapped_history.trade TEXT 컬럼 (★ atomizer INSERT 누락) | §A.8 trade row ★ NEW + 이슈 #C3 | |
| `2026-05-19_mapper_alternatives.sql` | mapper_activities.alternatives JSONB GIN | §A.12 alternatives row | |
| `2026-05-19_parser_full_schema.sql` | parser_activities +13 col / mapper_activities +13 col / 시트2~3 + 시트6 + Cover 4 신규 테이블 | §A.11, §A.12 확장 + §A.13~A.16 신규 | |
| `2026-05-19_sites_hours_saved_cum.sql` + db.py:1125 | sites.hours_saved_cum + `update_site_hours_saved_cum` | §A.2 + §F.2 + §G 산식 | |

---

## §I. 발견된 BE 단독 이슈 (deep_dive_persistence §12 매핑)

| ID | 등급 | 이슈 | 위치 | 근거 |
|---|---|---|---|---|
| **#C1 (= #N13)** | Critical | `daily_reports.site_summary_text` 컬럼 commit `21c10f7` "PG migration 추가" 언급, **migration 파일 부재**. fresh DB rebuild 시 UndefinedColumnError. AWS 마이그 cycle 에서만 살아남음 (이미 ALTER 적용된 dump). | `daily_reports`, `scripts/backfill_daily_report_views_v2.py:162`, `site_summary.py` | `git show 21c10f7 --stat` 에 sql 파일 없음 |
| **#C2** | Critical | `/export/run` endpoint 가 매 요청마다 `PGClient(os.environ["POSTGRES_URL"]).connect()` 신규 풀 생성 + close — `app.state.pg` 재사용 안 함 | `exporter_routes.py:23~34` | 요청당 handshake / TLS overhead, 동시 N 요청 시 pool 폭증 |
| **#C3** | Critical | `insert_mapped_history_batch` ON CONFLICT DO UPDATE 가 `today_qty / today_assigned_workers / unit` 만 갱신, **`trade` 컬럼 누락** | `db.py:478~487` SET 절 | 동일 (run_id, wa, l6_main, company) 재호출 시 trade 가 최초값으로 고정 — atomizer 도 INSERT 시 trade 미박힘 의심 |
| **#M1 (agentsN1)** | Medium | `/api/agents/status` 가 7 agent 마다 `SELECT COUNT(*) FROM pipeline_runs WHERE current_node=$1` — 7× round-trip | `api.py:741~744` loop | 단일 SQL `GROUP BY current_node` 로 1회 호출 가능 |
| **#M2** | Medium | `_SITES_SQL` LATERAL forecasts (api.py:279) — 모든 sites row 마다 LATERAL subquery 실행 | api.py:279~298 | 6 site 규모는 OK, 확장 시 EXPLAIN ANALYZE 검토 |
| **#M3 (dead-fetch_activity)** | Medium | `PGClient.fetch_activity` (db.py:73) 호출자 코드 부재 — test 만 | db.py:73 | mapper rerank 통합 검토 필요 |
| **#M4** | Medium | `_VIEW_JSONB_COLS` 화이트리스트 — `site_summary_text` 미포함 (text 컬럼이라 jsonb 화이트리스트와 분리 정당하나, 별도 helper 부재로 inline SQL 산재) | db.py:1050, `scripts/backfill_daily_report_views_v2.py:162` | scripts 가 raw `UPDATE daily_reports SET site_summary_text = $1 …` |
| **#M5** | Medium | `parser_reports` / `parser_activities` 등 14 테이블 init.sql 미포함, migration 만 — fresh dev DB 부팅 시 21 migration 순차 적용 강제 | infra/postgres/init.sql vs migrations/ | init.sql 7 테이블, migration 만 보면 14 테이블 추가 |
| **#M6** | Medium | `build_checkpointer` 가 `POSTGRES_URL` 없으면 silently InMemorySaver fallback — prod 환경 PG 미설정 사고 시 검출 어려움 (lifespan §1 이 fail-fast 이지만 단독 호출 시 위험) | checkpointer.py:90~92 | prod 에서 checkpointer 메모리 → H-i-L resume process restart 시 손실 |
| **#M7 (tasks-collector)** | Medium | `/api/tasks` items 가 `itemsByDate[date]["Collector"]` hard-coded — current_node 기반 agent 라우팅 미구현 | api.py:986~1042 `_build_items_by_date` | FE "Collector" 탭 외 표시 안 됨 |
| **#M-status** | Medium (carried) | `pipeline_runs.status` 전환 (`running → waiting_hil_1 / waiting_hil_2 / completed / failed`) UPDATE helper **0 개**. `current_node` 도 atomizer 만 박힘 (db.py:251 hard-code) | db.py 전수 grep | FE polling status / current_node 의존 동작 X |
| **#M-collector** | Medium (carried) | `state.raw_texts` (`state.py:236`) producer 부재 (`pipeline/agents/collector.py` 0 byte). graph.py 도 collector node 추가 X — START → mapper 직결 (graph.py:407 — `4b8a955` cycle 이후 collector idle task 만 있음, graph 노드는 아님) | state.py:236 | dead attr — 채워지는 path 없음 |
| **#M-parsed** | Medium (carried) | `CPIAState.parsed` 타입 시그니처 = `list[Activity]` (state.py:237) 인데 실 사용은 `ParsedDailyReport` dict (graph.py:43) | state.py:237 | 타입 spec ↔ 사용처 mismatch |
| **#M-v1v2** | Medium ★ NEW | `productivity_jsonb` (v1) vs (v2) — 같은 컬럼명, 다른 산식. v1 EVM (`{today, by_contractor, by_l6, by_wp}`), v2 wv-median (`{site, by_company, by_l6}`). 어느 버전이 박혔는지 컬럼에서 분간 불가 | view_builder.py:48 vs :1410 | FE 가 v1 가정으로 SELECT 하면 v2 row 에서 None 반환 |
| **#M-scenarios-swap** | Low ★ NEW | `_scenario` percentile 라벨 swap — `optimistic_p25` 의 recovery_days = P75 값 (큰 recovery 큰 만회), `pessimistic_p75` = P25 값 (작은 recovery 적은 만회). 라벨 ↔ 값 mismatch 의 의도적 swap (view_builder.py:1237~1241 자인) | view_builder.py:1237 주석 | FE 가 percentile 키 그대로 차트 라벨로 쓰면 의미 헷갈림 |
| **#M-history_csv_row** | Low (carried) | `daily_reports.history_csv_row` 컬럼명 ↔ 실 박힘 (summary dict) 의미 mismatch — 이름이 schema 잔재 | init.sql:39 vs reporter.py:108 | 컬럼 rename 또는 docstring 정리 backlog |
| **#M-mapping-corrections-spec** | Low (carried) | postgres.md §8 spec top-level 컬럼 (work_content/company/trade/correction_type) ↔ 실 schema 6 컬럼만. JSONB 안 합쳐 박는 우회 path | init.sql:127 + db.py:380~389 docstring | spec 정리 필요 |
| **#M-conditions-type** | Low (carried) | `forecasts.similar_cases[].conditions` (list) ↔ `optimizer_advice.degradation_cases[].conditions` (comma-joined str) 타입 불일치 — 같은 의미인데 type 다름 | forecaster/rerank.py:26 vs optimizer/retrieve.py:107 | FE 가 같은 의미 필드 두 형태로 받음 |
| **#M-forecast-cast** | Low (carried) | Forecaster / Optimizer row 가 dict literal (dataclass 부재) — column rename 시 silent break 위험. `row.get("...")` 가 None 으로 fall-through | forecaster/agent.py:191~225 / optimizer/agent.py:63~87 | 타입 안전성 X |
| **#N14** | High ★ NEW | `site_summary_text` 가 live graph 에 미통합. reporter_node / optimizer_node 둘 다 site_summary 호출 X — backfill 스크립트만 박음. live cycle 일보는 모두 NULL → FE narrative fallback (rule-based) 만 보임 | graph.py:415 reporter_node + optimizer/agent.py:145 optimize — 둘 다 generate_site_summary 미호출 | live integration 누락 |
| **#N15** | Low ★ NEW | `chroma_client.daily_activities` HNSW 파라미터 변경 (M 16 → 32, ef 10 → 200/100) 2026-05-26 — 기존 collection 은 metadata 변경 무효 (Chroma 0.5.x `get_or_create_collection` metadata 는 신규 생성 시만 반영). prod 에서 효과 보려면 collection 재생성 필요 | chroma_client.py:41~43 | metadata 갱신 안 됨 |

---

## §J. 카탈로그 row 총계

| 표 | row 수 | 비고 |
|---|---:|---|
| §A.1 pipeline_runs | 10 | +1 is_mock 본 cycle |
| §A.2 sites | 13 | +1 hours_saved_cum +1 is_mock |
| §A.3 activity_master | 23 | site_id PK 재구성 |
| §A.4 forecasts | 31 | +wa +is_mock |
| §A.5 optimizer_advice | 13 | +is_mock |
| §A.6 mapping_corrections | 7 | +is_mock |
| §A.7 daily_reports | 19 | +9 view jsonb +site_summary_text +scenarios_jsonb +site_id +is_mock |
| §A.8 mapped_history | 12 | +trade ★ |
| §A.9 mapped_history_merge_log | 12 | ★ NEW |
| §A.10 parser_reports | 10 | +is_mock |
| §A.11 parser_activities | 26 | +13 sheet4 +is_mock |
| §A.12 mapper_activities | 39 | +13 propagate +alternatives +cum_workers +cum_actual_mh +l5_disc/l7_sub/l7_5_activity/sub_work_area +is_mock |
| §A.13 parser_job_allocations | 16 | |
| §A.14 parser_equipment_allocations | 16 | |
| §A.15 parser_worker_outputs | 19 | |
| §A.16 parser_report_meta | 12 | |
| §A.17 collector_inbox | 11 | ★ NEW |
| §A.18 prototype_embedding_cache | 4 | ★ NEW |
| §A.19~21 langgraph ckpt (3 table) | 23 | auto |
| **§A 합계** | **316** | (이전 105 + 신규 211, 본 cycle 31 ★ NEW 신규) |
| §B JSONB key | 86 | 9 jsonb view 전수 |
| §C LangGraph state attr | 20 | +collector 4 ★ NEW +site_id |
| §D Agent output field | 95 | Activity 37 + BPSummary 12 + JobAllocation 10 + EquipmentAllocation 9 + WorkerOutput 7 ★ + ReportMeta 9 ★ + forecast 28 + optimizer 9 + reporter 4 + site_summary 9 ★ + chroma meta |
| §E FastAPI endpoint | 13 | +export/run ★ NEW |
| §F db.py helper | 35 | +4 collector ★ +fetch_site_by_id ★ |
| §G Derived 산식 | 15 | +5 본 cycle (s_curve A 4 row + scenarios 1) |
| §I 이슈 | 21 | C1~C3 critical + N14~N15 ★ NEW |

---

## §K. 본 cycle 핵심 변경 요지 (요약 — 메인 반환용 정리)

1. **`daily_reports.site_summary_text` migration 부재** (`#C1`) — 본 cycle 가장 큰 BE 단독 위험. fresh DB rebuild 시 컬럼 없음. AWS dump 만으로 살아남는 상태. **사용자 / DevOps 확인 필요**.
2. **`mapped_history.trade` SQL 누락** (`#C3`) — atomizer 가 mapped_history 에 trade 컬럼 INSERT 안 함. mapped_history.trade 컬럼은 5-19 migration 으로 신설됐으나 db.py:478~487 의 ON CONFLICT SET 절에 trade 부재. atomizer.py:130 INSERT path 도 확인 필요.
3. **`/export/run` ad-hoc PG pool** (`#C2`) — `app.state.pg` 재사용 안 함. exporter_routes.py:23 매 요청 신규 풀 생성.
4. **v1 ↔ v2 산식 drift** (`#M-v1v2`) — `productivity_jsonb` 같은 컬럼명, 다른 shape. FE 가 어느 버전 박혔는지 모름.
5. **scenarios P25/P75 라벨 swap 의도적** (`#M-scenarios-swap`) — `optimistic_p25` 가 P75 recovery_days 값 갖고 있음 (view_builder.py:1237 자인).
6. **9 jsonb view s_curve 산식 A** — `SUM(plan_wv × plan_mh_rev2)` 가중, full_grid CROSS JOIN + WINDOW SUM 단조 보장.
7. **MEDIAN fix** — `_build_kpi` delay_days/expected_completion AVG → PERCENTILE_CONT/DISC(0.5).
8. **site_summary live integration 부재** (`#N14`) — backfill 스크립트만 호출, live cycle 일보는 NULL. graph.py 에 site_summary 호출 추가 필요.
9. **Chroma HNSW 갱신 무효** (`#N15`) — 2026-05-26 M/ef 확대했으나 기존 collection 에 미반영.

---

## §L. 다음 사이클 backlog

- (#C1) `daily_reports.site_summary_text` migration sql 파일 생성 (`2026-05-2x_daily_reports_site_summary_text.sql`).
- (#C3) `db.py:478~487` `insert_mapped_history_batch` SET 절에 trade 추가 + atomizer.py 의 mh_rows 생성 시 Activity.trade 확인.
- (#C2) `exporter_routes.py:23` 가 `app.state.pg` 재사용 (Depends 주입).
- (#M1) `/api/agents/status` 단일 SQL `GROUP BY current_node` 로 통합.
- (#M-status) `pipeline_runs.status` UPDATE helper 신설 + graph.py 모든 노드 진입 시 호출.
- (#M-v1v2) `productivity_jsonb` 에 `version` 키 추가 또는 v1 폐기.
- (#N14) graph.py reporter_node 또는 optimizer_node 종료 직후 `generate_site_summary` 호출 추가 + daily_reports.site_summary_text UPDATE.
- (#N15) Chroma daily_activities collection 재생성 후 backfill 재적재 (M=32, ef=200/100 효과 검증).
