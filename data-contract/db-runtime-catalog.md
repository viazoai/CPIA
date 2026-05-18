# CPIA DB Runtime Catalog

> 생성: 2026-05-18 20:48:54 · 대상: `localhost:5532/cpia`
> pipeline_runs by status: completed=1, running=13
> crosswalk: `crosswalk.md`

## 한 눈에

| Stage | Tables / Row(s) | 시그널 |
|---|---|---|
| **seed** Seed (load_master_list) | `activity_master`=3704, `sites`=7 | ⚠R3 |
| **collector** Collector | (PG 적재 없음) | ✓ |
| **parser** Parser | `parser_reports`=5, `parser_activities`=284 | ⚠R7 |
| **mapper** Mapper | `mapper_activities`=284 | ⚠R3 ⚠R7 |
| **hil_1** HIL 1 (Mapper Review) | `mapping_corrections`=40 | ✓ |
| **atomizer** Atomizer | `mapped_history`=0 | ⚠R2 ⚠R7 |
| **reporter** Reporter | `daily_reports`=2 | ⚠R3 |
| **forecaster** Forecaster | `forecasts`=19 | ⚠R3 |
| **optimizer** Optimizer | `optimizer_advice`=1 | ⚠R4 |

## Stage 별 상세

### Stage `seed` — Seed (load_master_list)

- **Expected tables**: `activity_master`, `sites`
- **Source globs**: `scripts/load_master_list.py`, `scripts/**/*.py`
- **Actual call sites (grep):** 없음

- **`activity_master`**: row=3704, latest=2026-05-17T14:21:03+00:00
  - NULL ≥ 90%:
    - `l6_code` 100%
    - `l7_code` 100%
    - `sub_work_area` 100%
    - `plan_mh_rev1` 100%
    - `plan_mh_rev0` 100%
    - `plan_wv` 100%

- **`sites`**: row=7, latest=2026-05-18T11:08:53+00:00

- **BI 미도달 후보 (R5):** 24 컬럼
  - `activity_master.wbs_activity_id`
  - `activity_master.l5_disc`
  - `activity_master.l6_main`
  - `activity_master.l6_code`
  - `activity_master.l7_sub`
  - `activity_master.l7_code`
  - `activity_master.l7_5_activity`
  - `activity_master.sub_work_area`
  - `activity_master.company`
  - `activity_master.unit`
  - `activity_master.plan_total_qty`
  - `activity_master.plan_mh_rev2`
  - `activity_master.plan_mh_rev1`
  - `activity_master.plan_mh_rev0`
  - `activity_master.plan_wv`
  - … (+9 컬럼)

- **시그널:**
  - R3: `activity_master.l6_code` NULL ratio 100% ≥ 90%
  - R3: `activity_master.l7_code` NULL ratio 100% ≥ 90%
  - R3: `activity_master.sub_work_area` NULL ratio 100% ≥ 90%
  - R3: `activity_master.plan_mh_rev1` NULL ratio 100% ≥ 90%
  - R3: `activity_master.plan_mh_rev0` NULL ratio 100% ≥ 90%
  - R3: `activity_master.plan_wv` NULL ratio 100% ≥ 90%

### Stage `collector` — Collector

- **Expected tables**: (없음 — PG 적재 X)
- **Source globs**: `pipeline/agents/collector.py`
- **Actual call sites (grep):** 없음

### Stage `parser` — Parser

- **Expected tables**: `parser_reports`, `parser_activities`
- **Expected inserts**: `insert_parser_report`, `insert_parser_activities_batch`
- **Source globs**: `pipeline/agents/parser.py`, `pipeline/graph.py`
- **Actual call sites (grep):**
  - `pipeline/graph.py:76` → `insert_parser_report`
  - `pipeline/graph.py:85` → `insert_parser_activities_batch`
  - `pipeline/graph.py:90` → `insert_mapper_activities_batch`
  - `pipeline/graph.py:183` → `insert_mapping_correction`

- **`parser_reports`**: row=5, latest=2026-05-18T11:35:06+00:00
  - cycle 매핑: completed run 1 중 `parser_reports` 적재 누락 1

- **`parser_activities`**: row=284, latest=2026-05-18T11:35:07+00:00
  - cycle 매핑: completed run 1 중 `parser_activities` 적재 누락 1

- **BI 미도달 후보 (R5):** 15 컬럼
  - `parser_reports.report_date`
  - `parser_reports.project`
  - `parser_reports.bp_summaries`
  - `parser_reports.job_allocations`
  - `parser_reports.equipment_allocations`
  - `parser_reports.activity_count`
  - `parser_activities.report_date`
  - `parser_activities.idx`
  - `parser_activities.l5_disc`
  - `parser_activities.trade`
  - `parser_activities.company`
  - `parser_activities.unit`
  - `parser_activities.today_qty`
  - `parser_activities.work_content`
  - `parser_activities.plan_total_qty`

- **시그널:**
  - R7: `parser_reports` cycle 누락 1/1 completed run
  - R7: `parser_activities` cycle 누락 1/1 completed run

### Stage `mapper` — Mapper

- **Expected tables**: `mapper_activities`
- **Expected inserts**: `insert_mapper_activities_batch`
- **Source globs**: `pipeline/agents/mapper.py`, `pipeline/graph.py`
- **Actual call sites (grep):**
  - `pipeline/graph.py:76` → `insert_parser_report`
  - `pipeline/graph.py:85` → `insert_parser_activities_batch`
  - `pipeline/graph.py:90` → `insert_mapper_activities_batch`
  - `pipeline/graph.py:183` → `insert_mapping_correction`

- **`mapper_activities`**: row=284, latest=2026-05-18T11:35:07+00:00
  - cycle 매핑: completed run 1 중 `mapper_activities` 적재 누락 1
  - NULL ≥ 90%:
    - `plan_mh` 100%

- **BI 미도달 후보 (R5):** 16 컬럼
  - `mapper_activities.report_date`
  - `mapper_activities.idx`
  - `mapper_activities.company`
  - `mapper_activities.trade`
  - `mapper_activities.unit`
  - `mapper_activities.today_qty`
  - `mapper_activities.wa`
  - `mapper_activities.l6_main`
  - `mapper_activities.mapping_conf`
  - `mapper_activities.mapping_source`
  - `mapper_activities.requires_review`
  - `mapper_activities.assigned_workers`
  - `mapper_activities.worker_source`
  - `mapper_activities.plan_total_qty`
  - `mapper_activities.plan_mh`
  - … (+1 컬럼)

- **시그널:**
  - R3: `mapper_activities.plan_mh` NULL ratio 100% ≥ 90%
  - R7: `mapper_activities` cycle 누락 1/1 completed run

### Stage `hil_1` — HIL 1 (Mapper Review)

- **Expected tables**: `mapping_corrections`
- **Expected inserts**: `insert_mapping_correction`
- **Source globs**: `pipeline/graph.py`, `pipeline/api.py`
- **Actual call sites (grep):**
  - `pipeline/graph.py:76` → `insert_parser_report`
  - `pipeline/graph.py:85` → `insert_parser_activities_batch`
  - `pipeline/graph.py:90` → `insert_mapper_activities_batch`
  - `pipeline/graph.py:183` → `insert_mapping_correction`

- **`mapping_corrections`**: row=40, latest=2026-05-18T11:24:25+00:00

- **BI 미도달 후보 (R5):** 3 컬럼
  - `mapping_corrections.report_date`
  - `mapping_corrections.original`
  - `mapping_corrections.corrected`

### Stage `atomizer` — Atomizer

- **Expected tables**: `mapped_history`
- **Expected inserts**: `insert_mapped_history_batch`
- **Expected updates**: `update_run_atomized_count`
- **Source globs**: `pipeline/agents/atomizer.py`
- **Actual call sites (grep):**
  - `pipeline/agents/atomizer.py:135` → `insert_mapped_history_batch`
  - `pipeline/agents/atomizer.py:137` → `update_run_atomized_count`

- **`mapped_history`**: row=0
  - cycle 매핑: completed run 1 중 `mapped_history` 적재 누락 1

- **BI 미도달 후보 (R5):** 8 컬럼
  - `mapped_history.report_date`
  - `mapped_history.site_id`
  - `mapped_history.wa`
  - `mapped_history.l6_main`
  - `mapped_history.company`
  - `mapped_history.today_qty`
  - `mapped_history.today_assigned_workers`
  - `mapped_history.unit`

- **시그널:**
  - R2: `mapped_history` row=0 (적재 없음)
  - R7: `mapped_history` cycle 누락 1/1 completed run

### Stage `reporter` — Reporter

- **Expected tables**: `daily_reports`
- **Expected inserts**: `insert_daily_report`
- **Source globs**: `pipeline/agents/reporter.py`
- **Actual call sites (grep):**
  - `pipeline/agents/reporter.py:151` → `insert_daily_report`

- **`daily_reports`**: row=2, latest=2026-05-18T11:18:40+00:00
  - cycle 매핑: completed run 1 중 `daily_reports` 적재 누락 0
  - NULL ≥ 90%:
    - `bp_name` 100%

- **BI 미도달 후보 (R5):** 4 컬럼
  - `daily_reports.report_date`
  - `daily_reports.bp_name`
  - `daily_reports.report_md`
  - `daily_reports.history_csv_row`

- **시그널:**
  - R3: `daily_reports.bp_name` NULL ratio 100% ≥ 90%

### Stage `forecaster` — Forecaster

- **Expected tables**: `forecasts`
- **Expected inserts**: `insert_forecast`
- **Source globs**: `pipeline/agents/forecaster/**/*.py`
- **Actual call sites (grep):**
  - `pipeline/agents/forecaster/agent.py:272` → `insert_forecast`

- **`forecasts`**: row=19, latest=2026-05-18T11:43:18+00:00
  - cycle 매핑: completed run 1 중 `forecasts` 적재 누락 0
  - NULL ≥ 90%:
    - `wa` 100%

- **BI 미도달 후보 (R5):** 19 컬럼
  - `forecasts.company`
  - `forecasts.today_qty_by_unit`
  - `forecasts.today_assigned_workers`
  - `forecasts.plan_total_qty_by_unit`
  - `forecasts.assessment`
  - `forecasts.reasoning`
  - `forecasts.plan_start`
  - `forecasts.plan_finish`
  - `forecasts.plan_mh_per_day`
  - `forecasts.schedule_state`
  - `forecasts.window_start`
  - `forecasts.window_days`
  - `forecasts.expected_in_window_mh`
  - `forecasts.actual_in_window_mh`
  - `forecasts.mh_gap`
  - … (+4 컬럼)

- **시그널:**
  - R3: `forecasts.wa` NULL ratio 100% ≥ 90%

### Stage `optimizer` — Optimizer

- **Expected tables**: `optimizer_advice`
- **Expected inserts**: `insert_optimizer_advice`
- **Source globs**: `pipeline/agents/optimizer/**/*.py`
- **Actual call sites (grep):**
  - `pipeline/agents/optimizer/agent.py:153` → `insert_optimizer_advice`
  - `pipeline/agents/optimizer/synthetic_daily_report.py:25` → `insert_pipeline_run`
  - `pipeline/agents/optimizer/synthetic_daily_report.py:405` → `insert_pipeline_run`

- **`optimizer_advice`**: row=1, latest=2026-05-17T09:27:00+00:00
  - cycle 매핑: completed run 1 중 `optimizer_advice` 적재 누락 0

- **새는 데이터 (R4 — state-only):**
  - state["last_incident"] 할당 @ pipeline/agents/optimizer/synthetic_v2.py:75 — expected_tables 컬럼에 없음
  - state["equip_wait_streak"] 할당 @ pipeline/agents/optimizer/synthetic_v2.py:75 — expected_tables 컬럼에 없음
  - state["equip_wait_streak"] 할당 @ pipeline/agents/optimizer/synthetic_v2.py:79 — expected_tables 컬럼에 없음
  - state["equip_wait_streak"] 할당 @ pipeline/agents/optimizer/synthetic_v2.py:82 — expected_tables 컬럼에 없음
  - state["last_incident"] 할당 @ pipeline/agents/optimizer/synthetic_v2.py:83 — expected_tables 컬럼에 없음
  - state["equip_wait_streak"] 할당 @ pipeline/agents/optimizer/synthetic_v2.py:83 — expected_tables 컬럼에 없음
  - state["equip_wait_streak"] 할당 @ pipeline/agents/optimizer/synthetic_v2.py:86 — expected_tables 컬럼에 없음
  - state["last_incident"] 할당 @ pipeline/agents/optimizer/synthetic_v2.py:88 — expected_tables 컬럼에 없음
  - state["last_incident"] 할당 @ pipeline/agents/optimizer/synthetic_v2.py:91 — expected_tables 컬럼에 없음
  - state["equip_wait_streak"] 할당 @ pipeline/agents/optimizer/synthetic_v2.py:106 — expected_tables 컬럼에 없음
  - state["last_incident"] 할당 @ pipeline/agents/optimizer/synthetic_v2.py:163 — expected_tables 컬럼에 없음
  - state["rain_streak"] 할당 @ pipeline/agents/optimizer/synthetic_v2.py:164 — expected_tables 컬럼에 없음

- **BI 미도달 후보 (R5):** 4 컬럼
  - `optimizer_advice.l6_main`
  - `optimizer_advice.recovery_pattern`
  - `optimizer_advice.company`
  - `optimizer_advice.forecast_assessment`

---

## 룰 범례

- **R0** schema 미존재
- **R1** expected insert/update 호출 누락 (코드 grep)
- **R2** 테이블 row=0 (적재 없음)
- **R3** column NULL ratio ≥ 90%
- **R4** `state["X"] = ...` 인데 expected_tables 어느 컬럼에도 없음 (PG 안 새어나감 후보)
- **R5** BE 컬럼이 crosswalk 어느 FE field 와도 매칭 안 됨 (dead column 후보)
- **R6** crosswalk 매칭은 있는데 row=0 또는 NULL high → FE 가 mock fallback
- **R7** `pipeline_runs.status='completed'` 인 run 중 per_cycle 테이블에 적재 누락
