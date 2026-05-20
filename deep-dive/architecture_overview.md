# CPIA Architecture Overview (deep-dive 라이트)

- **Generated**: 2026-05-20 (parser+mapper refactor + view_builder 신설 + FastAPI 12 엔드포인트 완성 + full-cycle 검증 후 갱신)
- **Git SHA**: `ef7c6cd` (A_Track HEAD, origin sync). 이전 스냅샷 `cf3c143` 대비 80 commits, pipeline LOC 4380→8928.
- **Branch**: `A_Track` (조형준 main 머지 대기). B_Track 별도.
- **Range**: pipeline 전체 (agents 7 active + reporter + graph + state + db + api + checkpointer) + Next.js BFF (web/lib/pg.ts + transforms.ts) — `~143k LOC` (.venv 제외 pipeline ~8.9k LOC + tests + web)
- **Tests**: 392 collected (pipeline/tests, 이전 197건 대비 2배)
- **Pair**: `./design-intent/INDEX.md` (메인 카탈로그) + `../docs/audit/2026-05-17-cpia-drift-backlog.md` (해소 우선순위) + `../docs/superpowers/specs/2026-05-20-cpia-parser-mapper-refactor-design.md` (직전 cycle spec)

본 문서는 함수별 깊이 보다는 **시스템 다이어그램 + 서브시스템 요약 + 변경 인터페이스 정리 + 이슈 표** 위주. 함수 단위 깊이는 `./design-intent/design_intent_<X>.md` 참조.

> **이번 cycle 갱신 요지** (vs 이전 cf3c143 / 2026-05-19):
> - **Parser 전면 리팩터** (5개 commit): 4 시트 rule-based 추출 + LLM 검증 wrapper (default on, env opt-out). `parser.py` 306→760 LOC. **`parser_llm.py` DEPRECATED 2026-05-20** (코드 보존, env flag 회귀 가능). 신규 `parser_post.py` (201 LOC) — `split_company_and_zone` / `extract_zone` / `pair_bp_summaries` / `transform_bp_summaries`.
> - **Collector 신설** (`pipeline/agents/collector.py` 70 LOC) — `discover_daily_reports` + `collect_and_parse` (asyncio.Semaphore 4 병렬). 이전 0 byte stub 채움.
> - **Mapper 7단계 `resolve_wa` + shift-weighted MH** — 이전 5단계 (0+1+2+3+4) → **7단계 (0~6)**. 신규 source 2종: `auto_bp_zone_match` (BP-zone deterministic, fix C) + `auto_llm_rerank` (LLM rerank fallback, 옵션 A). hil_required 58% → 25% 목표. `_weighted_mh_from_shift` + `_prorate_workers_with_mh` 신규 (8h 고정 → 시간대 가중 MH, EVM AC 분모 정합). `build_bp_context` BP 코드별 분리.
> - **Optimizer + view_builder 신설** (`pipeline/agents/optimizer/view_builder.py` **752 LOC 신규**) — daily_reports 의 8 + 1 view jsonb 산출 (kpi / contractor_bars / trade_bars / quadrant / wp_summary / s_curve / optimizer_view / productivity / **scenarios** 2026-05-19 추가). `_build_scenarios` (percentile 기반 4 시나리오 no_action / optimistic_p25 / base_p50 / pessimistic_p75) + `_build_quadrant` (impact P90 normalize) + `_build_s_curve` (planned/actual/forecast/recovery 4 곡선).
> - **FastAPI 12 엔드포인트 완성** (`pipeline/api.py` 0 byte → **1050 LOC**) — `/health` + HIL1 resume + 10 GET (sites / runs/{run_id}/optimizer / wp_summary / sites/{site_id}/reports / dashboard/performance / dashboard/impact / agents/status / sites/{site_id}/wbs_tree / tasks). BFF (web/lib/pg.ts) 의 mock route 가 점진적으로 본 엔드포인트로 swap 예정.
> - **PG 16개 migration + 8개 신규 테이블/컬럼**:
>   - 신규 테이블 6종: `mapped_history`, `parser_activities`, `parser_job_allocations`, `parser_equipment_allocations`, `parser_worker_outputs`, `parser_report_meta`
>   - 신규 컬럼: `forecasts.wa`, `activity_master.wa`/`site_id`, `daily_reports.{site_id, 8 view jsonb, scenarios_jsonb}`, `mapper_activities.{alternatives, cum_workers_today, cum_actual_mh_today}`, `mapped_history.trade`, `sites.hours_saved_cum`
>   - `upsert_daily_report_view_col` (db.py:1034) — UPDATE-first partial write 가드 + 9 컬럼 화이트리스트 (SQL injection 방어)
> - **Orchestration 3 hotfix**: `cf2a791` (`normalize_company` import 추가, #31 close) + `e163e1a` (정규화 타이밍 — `fetch_bp_candidates` 전 일괄 정규화, ㈜/(주) prefix 로 cand_pool 빈 버그) + `844d4c3` (full cycle 진행 — `CPIA_HIL_AUTO_BYPASS` env + `pipeline_runs` 사전 INSERT + HIL2 auto-select).
> - **Full cycle 5 검증** (844d4c3 commit msg): `mapper_activities` 146 row / mapping_source `auto_bp_zone_match` 74% + hil 1.4% / `atomized_ids` 64 / `forecasts` 27 / `optimizer_advice` 13 / `daily_reports` 8 jsonb 모두 채워짐 (kpi/wp_summary/quadrant 3 jsonb 미구현 잔존).
> - **POC 3사 데이터셋 변경**: 남웅건설 (179) + 세보엠이씨 (561) + 창원기전 (319). 에스티엠 (0 row) 제거.
> - **Backlog (defer)**:
>   - `kpi_jsonb` / `wp_summary_jsonb` / `quadrant_jsonb` view_builder 산출 비어있음 — Phase 2
>   - `Activity.{wbs_activity_id, l7_sub, l7_5_activity, sub_work_area}` Master List 1:N 제약으로 항상 None
>   - Reporter → Exporter rename (파일명/모듈명) 미시행
>   - `parser_warning` PG 영속화 (현재 stderr 로그만)
>   - V3~V5 검증 pending (146 case full simulation, 12개 unit test, 10 업체 POC 전체 cycle)

---

## 1. 시스템 다이어그램

```
                              ┌──────────────────────────────────────────────────────────┐
                              │              [B_Track] Next.js Dashboard                   │
                              │   home / dashboard / tasks / reports / review / export    │
                              │   Layer 1 (현장 카드 6 site) / Layer 2 (상세 + HIL Modal)  │
                              └─────────────────────┬────────────────────────────────────┘
                                                    │ HTTP (BFF)
                              ┌─────────────────────┴────────────────────────────────────┐
                              │   Next.js API Routes (real PG SELECT + FastAPI proxy)    │
                              │   • /api/mock/dashboard / agent-tasks / report / review   │
                              │   • /api/mock/consolidated  ← 점진적 FastAPI swap 진행중    │
                              └─────────────────────┬────────────────────────────────────┘
                                                    │ asyncpg pool + HTTP
   ┌────────────────────────────────────────────────┴─────────────────────────────────────┐
   │                                                                                       │
   │  ┌──────────────────────────────────────────┐    ┌────────────────────────────────┐  │
   │  │   web/lib/pg.ts + transforms.ts (BFF)    │    │  pipeline/api.py — FastAPI     │  │
   │  │   G1 deriveYearlySaving / G6 productivity │    │  ✓ 1050 LOC (이전 0 byte)      │  │
   │  │   /timeseries / G20 deriveSCurve (4 sub) │    │  • POST /api/runs/{id}/hil_1/  │  │
   │  │   / G22 wbsTreeBuild / G18 deriveImpact  │    │           resume               │  │
   │  │   (11 transform 함수)                     │    │  • GET /health                  │  │
   │  └──────────────────────────────────────────┘    │  • GET /api/sites               │  │
   │                                                  │  • GET /api/runs/{id}/optimizer │  │
   │                                                  │  • GET /api/runs/{id}/wp_summary│  │
   │                                                  │  • GET /api/sites/{id}/reports  │  │
   │                                                  │  • GET /api/dashboard/perf      │  │
   │                                                  │  • GET /api/dashboard/impact    │  │
   │                                                  │  • GET /api/agents/status       │  │
   │                                                  │  • GET /api/sites/{id}/wbs_tree │  │
   │                                                  │  • GET /api/tasks               │  │
   │                                                  └────────────────────────────────┘  │
   └───────────────────────────────────────┬───────────────────────────────────────────────┘
                                           │ in-process
   ┌───────────────────────────────────────┴───────────────────────────────────────────────┐
   │                           LangGraph StateGraph (pipeline/graph.py)                    │
   │                                                                                       │
   │   build_graph (production):                                                            │
   │   ┌──────────┐  ┌────────┐  ┌──────────┐  ┌──────┐  ┌────────────┐  ┌──────────┐     │
   │   │collector │→│ parser  │→│ mapper   │→│hil_1│→│  atomizer  │→│forecaster│     │
   │   │ ✓ 70 LOC│ │ ✓ 760  │ │ ✓ 571    │ │ ✓ 76│ │  ✓ 141     │ │ ✓ 893    │     │
   │   │  NEW     │ │  +parser│ │ resolve_wa│ │ env  │ │  Chroma    │ │ RAG 우선  │     │
   │   │ semafore │ │  _llm   │ │ 7단계 +  │ │AUTO_ │ │ daily_     │ │ + Plan    │     │
   │   │ 4 병렬   │ │  658    │ │ shift MH │ │BYPASS│ │ activities │ │ fallback  │     │
   │   │          │ │ (DEPRE) │ │ + alt    │ │      │ │ INSERT     │ │          │     │
   │   │          │ │ +parser │ │  top-K   │ │      │ │            │ │          │     │
   │   │          │ │  _post  │ │          │ │      │ │            │ │          │     │
   │   │          │ │  201    │ │          │ │      │ │            │ │          │     │
   │   └──────────┘  └────────┘  └──────────┘  └──┬───┘  └────────────┘  └──┬───────┘     │
   │       NEW                                     │interrupt                 │             │
   │                                       Command(resume=                    ▼             │
   │                                       hil_1_corrections)        ┌────────────┐         │
   │                                                                 │  hil_2     │         │
   │                                                                 │ F5/F7      │         │
   │                                                                 │ 정정 +     │         │
   │                                                                 │ pre_cases  │         │
   │                                                                 │ 사전 영속  │         │
   │                                                                 └──┬─────┬───┘         │
   │                                                                    │     │             │
   │                                          hil_2_selection 있음 ▼   ▼ empty 또는 risky 0건│
   │                                                          ┌────────────────┐             │
   │                                                          │  optimizer     │             │
   │                                                          │  ✓ 199 + 752   │             │
   │                                                          │   (view_builder│             │
   │                                                          │    NEW 752)    │             │
   │                                                          │  + 161 retrieve│             │
   │                                                          │  + 315 prompt  │             │
   │                                                          │  8 view jsonb  │             │
   │                                                          └──────┬─────────┘             │
   │                                                                 ▼                       │
   │                                                          ┌────────────┐                 │
   │                                                          │ reporter   │ ✓ 161           │
   │                                                          │ (종합 1 종) │                 │
   │                                                          │ + G8 sites.│                 │
   │                                                          │  last_run_id│                 │
   │                                                          │ + G2 hours_│                 │
   │                                                          │  saved_cum │                 │
   │                                                          └──────┬─────┘                 │
   │                                                                 ▼ END                    │
   │   build_demo_graph: forecaster → hil_2 → (optimizer | reporter) → END                    │
   │                     (mapper/atomizer/hil_1 skip — synthetic_daily_report.py CLI 용)       │
   └───────────────────────────┬─────────────────────────────────┬───────────────────────────┘
                               │                                 │
                ┌──────────────┴──────────────┐    ┌─────────────┴──────────────┐
                │  PostgreSQL (asyncpg pool)  │    │  ChromaDB (HTTP)           │
                │  pipeline/db.py (1113 LOC)  │    │  pipeline/chroma_client.py │
                │  ─────────────────────────  │    │  (35 LOC)                  │
                │  코어:                       │    │  ─────────────────────────  │
                │  • pipeline_runs            │    │  • wbs_master              │
                │  • checkpoints              │    │     → Mapper RAG (Chroma   │
                │    (Async PostgresSaver     │    │       top-K + distances)  │
                │     lazy init)              │    │  • daily_activities        │
                │  Parser 정규화 6 테이블:      │    │     → Forecaster RAG +    │
                │  • parser_reports           │    │       Optimizer retrieve   │
                │  • parser_activities (23 col)│    │       (degradation +      │
                │  • parser_job_allocations   │    │        recovery 2-step)   │
                │  • parser_equipment_alloc   │    └────────────────────────────┘
                │  • parser_worker_outputs    │
                │  • parser_report_meta       │
                │  Mapping 레이어:             │
                │  • activity_master (22 col +│
                │     wa / site_id)            │
                │  • mapper_activities (33 col│
                │     + alternatives + cum_*) │
                │  • mapped_history (9 col +  │
                │     trade)  NEW             │
                │  • mapping_corrections      │
                │  Reports + 진단:             │
                │  • forecasts (30 col + wa)  │
                │  • optimizer_advice (11 col)│
                │  • daily_reports (15 col):   │
                │     report_md + history_csv │
                │     + 8 view jsonb +        │
                │     scenarios_jsonb         │
                │  Site:                       │
                │  • sites (12 col + hours_   │
                │     saved_cum / fte_saved / │
                │     headcount / location)   │
                └─────────────────────────────┘
```

**Note**: `parser_llm.py` DEPRECATED (2026-05-20) — 코드 보존, env flag `CPIA_PARSER=llm` 으로 회귀 가능. `collector.py` + `run_one_cycle.py` 의 import 가 `parse_daily_report` (rule-based) 로 교체됨.

---

## 2. 서브시스템 요약 (8개)

| # | 서브시스템 | 핵심 파일 (LOC) | T1 (≈) | T2 (≈) | 본 cycle 변경 | 미해결 / 다음 |
|---|---|---|---:|---:|---|---|
| 1 | **orchestration** | `graph.py` (563) / `state.py` (303) / `checkpointer.py` (94) / `constants.py` (5) | 22 | 16 | `normalize_company` import + 정규화 2회 (fetch_bp_candidates 전) + `CPIA_HIL_AUTO_BYPASS` env + HIL2 auto-select + reporter G8/G2 | `daily_reports.kpi_jsonb` / `wp_summary_jsonb` / `quadrant_jsonb` 미산출 (view_builder gap) |
| 2 | **persistence** | `db.py` (1113) / `api.py` (1050) / `chroma_client.py` (35) / `checkpointer.py` (94) | 27 (PG 25 + Chroma 2 + Module-level 2) + 12 FastAPI route | 18 | `upsert_daily_report_view_col` 신규 (UPDATE-first + 9 col 화이트리스트) + 16 migration + `api.py` 12 엔드포인트 완성 | `fetch_activity` 미사용 의심, Phase 2 `recovery` BFF 반영 backlog, itemsByDate "Collector" hardcode |
| 3 | **parser** | `parser.py` (760) / `parser_llm.py` (658, DEPRECATED) / `parser_post.py` (201) / `collector.py` (70) | 20 | 11 | 4 시트 rule-based refactor (5 commits) + `parser_post.py` (split_company_and_zone / extract_zone / pair_bp_summaries / transform_bp_summaries) + 시트1/4 LLM 검증 wrapper (default on, env opt-out) + collector.py 신설 | V3 (146 case full sim) / V4 (12 unit test) / V5 (10 업체 POC + UI 12 정량) 검증 pending. `parser_warning` PG 영속화 미구현. `parser_llm.py` 제거 backlog |
| 4 | **mapper** | `mapper.py` (571) | 12 | 13 | `resolve_wa` 7단계 (auto_bp_zone_match + auto_llm_rerank 신규) + `_weighted_mh_from_shift` + `_prorate_workers_with_mh` (8h 고정 → 시간대 가중) + `build_bp_context` BP 코드별 분리 + `build_llm_input` activity.bp_code 명시 | hil_required 58% → 25% 목표 검증 pending (V3) |
| 5 | **atomizer** | `atomizer.py` (141) | 4 | 6 | **코드 변경 없음** (cf3c143 이후) — 안전 처리 hotfix는 이전 cycle 흡수됨 | `embedding_dim` 필드 미사용 의심 |
| 6 | **forecaster** | `agent.py` (279) + 6 sub-module (`prompt.py` 134 / `classify.py` 114 / `aggregate.py` 119 / `synthetic.py` 189 / `rerank.py` 50 / `constants.py` 8) | 22 | 13 | **코드 변경 없음** (cf3c143 이후) | `classify.py:34` PM 원안 v2 정합 (저하 분류 의도) |
| 7 | **optimizer** | `agent.py` (199) / `prompt.py` (315) / `retrieve.py` (161) / `synthetic_daily_report.py` (498) / `synthetic_v2.py` (363) / **`view_builder.py` (752, NEW)** | 30+ | 13 | **`view_builder.py` 752 LOC 신규** (8 + 1 view jsonb 산출) + `_build_scenarios` (percentile 4 시나리오) + `_compute_recovery_distribution` 코드단 deterministic (결정 #20) + `optimize()` view orchestration + `_coerce_date` fix | RAG fixture_prod vs synthetic_v2 ±10% mismatch (cycle C 검증 pending), view_builder 함수 밀도 (18 helper + 8 public) |
| 8 | **reporter** | `reporter.py` (161) | 5 | 7 | **코드 변경 없음** (cf3c143 이후) — 종합 보고서 + G8 sites.last_run_id + G2 hours_saved_cum 흡수 | reporter → exporter rename backlog |

**합계**: T1 ≈ 130+ 함수/클래스 / T2 ≈ 97 이슈 카드 (본 cycle +6 신규 추정)

---

## 3. 데이터 레이어

### 3.1 PostgreSQL 테이블 (17개)

| 그룹 | 테이블 | 컬럼 | 멱등성 키 | 비고 |
|---|---|---:|---|---|
| 코어 | `pipeline_runs` | 9 | (run_id) PK | atomized_count, status: running/waiting_hil_1/waiting_hil_2/completed/failed |
| 코어 | `checkpoints` 외 3 | — | thread_id | LangGraph AsyncPostgresSaver |
| Parser | `parser_reports` | 7 | (run_id, report_date) | bp/job/equipment JSONB |
| Parser | `parser_activities` | 23 | (run_id, idx) | parser 시트4 정규화 |
| Parser | `parser_job_allocations` | 14 | (run_id, idx) | 시트2, 3 group JSONB |
| Parser | `parser_equipment_allocations` | 14 | (run_id, idx) | 시트3, 3 group JSONB |
| Parser | `parser_worker_outputs` | 17 | (run_id, idx, bp_name) | 시트6, 업체별 |
| Parser | `parser_report_meta` | 10 | (run_id, idx, bp_name) | Cover, 업체별 |
| Mapping | `activity_master` | 22+ | (wbs_activity_id) | wa + site_id 신규 |
| Mapping | `mapper_activities` | 33 | (run_id, idx) | + alternatives JSONB + cum_workers_today + cum_actual_mh_today |
| Mapping | `mapped_history` | 9 | (run_id, wa, l6_main, company) | + trade 신규, atomizer + forecaster 입력 |
| Mapping | `mapping_corrections` | 6 | (auto pk) | HIL 1 corrections JSONB |
| Reports | `daily_reports` | 15 | partial unique (run_id, site_id, report_date) WHERE site_id IS NOT NULL | 8 view JSONB + scenarios_jsonb + history_csv_row + report_md |
| Reports | `forecasts` | 30 | (run_id, company, l6_main) | + wa 신규, JSONB similar_cases / qty_by_unit |
| Reports | `optimizer_advice` | 11 | (run_id, company, l6_main) | JSONB recommendations / degradation_cases / recovery_distribution |
| Site | `sites` | 12 | (site_id) PK | + hours_saved_cum / fte_saved / headcount / location 신규 |

### 3.2 ChromaDB 컬렉션 (2개)

- **`wbs_master`** — 1 doc = 1 (WA, L6) 그룹. Mapper RAG (`map_activity` step 3, n_results=top_k + cosine distance + include="distances" 로 alternatives 적재).
- **`daily_activities`** — 1 doc = 1 Activity. Atomizer INSERT, Forecaster + Optimizer retrieve (degradation `productivity < baseline×0.85 AND conditions ∋ {장비대기/자재미입고/돌관}` + recovery `productivity ≥ baseline×0.95 first day`).

### 3.3 PG 16 Migration (2026-05-16 ~ 05-19)

```
2026-05-16_downstream_agents.sql      (44) — forecasts(29) + optimizer_advice(11) 신규
2026-05-16_forecaster.sql             (27) — forecasts 컬럼 상세
2026-05-16_optimizer_hil2.sql         (25) — optimizer_advice 9 컬럼
20260516_add_activity_master.sql      (53) — activity_master 1059 row + wa
2026-05-17_activity_master_site_id.sql (55) — site_id 필터
2026-05-17_activity_master_wa.sql     (15) — wa 컬럼
2026-05-17_db_alignment.sql           (11) — sites +4 컬럼
2026-05-18_mapped_history.sql         (19) — mapped_history + index
2026-05-18_forecasts_wa.sql            (6) — forecasts.wa
2026-05-18_parser_mapper_outputs.sql  (70) — parser/mapper_activities 통합
2026-05-19_daily_reports_views.sql    (22) — 8 view JSONB + site_id
2026-05-19_mapped_history_trade.sql   (11) — mapped_history.trade
2026-05-19_mapper_alternatives.sql    (15) — alternatives JSONB + GIN
2026-05-19_scenarios_jsonb.sql        (10) — daily_reports.scenarios_jsonb
2026-05-19_sites_hours_saved_cum.sql  (12) — G2 누적 절감 시간
2026-05-19_parser_full_schema.sql    (141) — parser_* 5 테이블 통합
```

---

## 4. Tool / Helper Inventory (서브시스템 외 핵심)

| 파일 | 함수/클래스 | LOC | 역할 |
|---|---|---:|---|
| `pipeline/db.py` (1113) | `PGClient` 25 메서드 + `update_site_last_run` + `update_site_hours_saved_cum` | — | asyncpg pool 단일 진입점. fetch_bp_candidates / fetch_l6_plan_mh_map / fetch_plan_for_group / insert_*_batch × 7 / upsert_daily_report_view_col (UPDATE-first + 9 col 화이트리스트) |
| `pipeline/api.py` (1050) | FastAPI 12 endpoint | — | BFF용 GET 10 + POST 1 (hil_1/resume) + GET /health |
| `pipeline/chroma_client.py` (35) | `ChromaClient.get_or_create_wbs_master/daily_activities` | — | HTTP collection 진입점 |
| `pipeline/checkpointer.py` (94) | `_LazyAsyncPostgresSaver` + `build_checkpointer` | — | InMemorySaver fallback + Async PostgresSaver lazy open |
| `pipeline/agents/optimizer/view_builder.py` (752) | 8 public + 10 helper | — | EVM 산식 (_compose_evm / _evm_by_group) + KPI / bars / quadrant (P90 impact normalize) / scenarios (percentile 4) / s_curve (4 sub) / optimizer_view |
| `pipeline/agents/parser_post.py` (201) | 8 함수 | — | normalize_company / split_company_and_zone / extract_zone / pair_bp_summaries / filter_marker_rows / transform_{bp_summaries, job_allocations, equipment_allocations} |
| `pipeline/agents/collector.py` (70) | discover_daily_reports + collect_and_parse | — | xlsx 디렉토리 발견 + asyncio.Semaphore(4) 병렬 호출 |
| `pipeline/synthetic/generate_history.py` | (0 byte) | 0 | drift backlog — synthetic v2 데이터 생성 분리 미시행 |
| `pipeline/main.py` | (0 byte) | 0 | drift backlog D-7 — CLI 진입점 미구현 (현재 `scripts/run_one_cycle.py` 사용) |
| `scripts/run_one_cycle.py` | 1 round (HIL1+HIL2 auto) | — | demo/검증 CLI. pipeline_runs 사전 INSERT + HIL2 auto-select |
| `scripts/backfill_daily_report_views.py` | backfill 1 cycle | — | 기존 run 대상 view_builder 재산출 |
| `scripts/backfill_mapper_cum_workers.py` | backfill cum_workers | — | mapper_activities.cum_workers_today U1.B 회복 |
| `scripts/load_master_list.py` | 1 시트 → activity_master | — | Master List xlsx 적재 |

---

## 5. Issue 표

| ID | 영역 | 심각도 | 설명 | 다음 행동 |
|---|---|---|---|---|
| #N1 | optimizer | M | RAG fixture_prod vs synthetic_v2 baseline ±10% mismatch (사용자 합의 — 의도된 차이) | cycle C 시 실측 검증, generate_synthetic_v2_group rule 7건 확장 검토 |
| #N2 | persistence | M | `infra/postgres/migrations` vs `docs/schema/postgres.md` 간 schema 정합 | postgres.md 자동 생성 스크립트 검토 |
| #N3 | persistence | L | `fetch_activity` (db.py:73) 미사용 의심 (test 만 호출) | 다음 cycle 삭제 또는 mapper rerank 단계 통합 검토 |
| #N4 | orchestration | M | `daily_reports.kpi_jsonb` / `wp_summary_jsonb` / `quadrant_jsonb` 3개 view 미산출 (view_builder gap) | Phase 2 — activity_master.plan_start/finish 의존성 필요 |
| #N5 | orchestration | L | `LangGraph Command(resume=dict)` 의 key int → str 변환 룰 명문화 미흡 | spec 문서화 |
| #N6 | reporter | L | reporter → exporter rename (파일명 + 모듈 import) 미시행 | 다음 cycle, 13개 import 변경 |
| #N7 | parser | M | `parser_warning` 현재 stderr 로그만 — DB 적재 미구현 | 다음 cycle, `parser_reports.warnings_jsonb` 컬럼 추가 |
| #N8 | parser | L | `parser_llm.py` (658 LOC) DEPRECATED 코드 제거 미시행 | env flag deprecation 후 다음 cycle 제거 |
| #N9 | api | L | `/api/tasks` itemsByDate "Collector" key hardcode (current_node 라우팅 미구현) | Phase 2 정밀화 |
| #N10 | api | L | `/api/sites` (sites LATERAL forecasts) 6 site fixture 규모, 확장 시 성능 검토 | EXPLAIN ANALYZE, 필요 시 view 분리 |
| #N11 | poc | L | `Activity.{wbs_activity_id, l7_sub, l7_5_activity, sub_work_area}` Master List 1:N 으로 항상 None | PoC 단계 미스코핑 |
| #N12 | tests | L | atomizer / forecaster / reporter cf3c143 이후 코드 변경 없음 — 본 cycle T2 카드 라벨 stale 가능 | last_checked_at 갱신만, 카드 재작성 불필요 |
| D-1 | optimizer | M | 병행작업 룰 (드릴 + 콘크리트 등 동시) 진단 미반영 | Phase 2 |
| D-7 | orchestration | L | `pipeline/main.py` 0 byte stub (CLI 미구현) | scripts/run_one_cycle.py 가 대체 — 정상 |

---

## 6. 파일 구조 요약 (annotated)

```
pipeline/
├── agents/
│   ├── atomizer.py             141  Chroma daily_activities INSERT (변경 없음)
│   ├── collector.py             70  NEW — discover + collect_and_parse (semafore 4)
│   ├── forecaster/
│   │   ├── agent.py            279  RAG 우선 + Plan fallback (변경 없음)
│   │   ├── aggregate.py        119
│   │   ├── classify.py         114
│   │   ├── constants.py          8
│   │   ├── prompt.py           134
│   │   ├── rerank.py            50
│   │   └── synthetic.py        189
│   ├── mapper.py               571  resolve_wa 7 단계 + shift-weighted MH + build_bp_context BP별
│   ├── optimizer/
│   │   ├── agent.py            199  optimize() + view_builder orchestration
│   │   ├── prompt.py           315  SYSTEM_PROMPT + FEW_SHOT
│   │   ├── retrieve.py         161  fetch_degradation_cases + fetch_recovery_trajectory
│   │   ├── synthetic_daily_report.py  498  demo CLI
│   │   ├── synthetic_v2.py     363  state machine 7 회복 룰
│   │   └── view_builder.py     752  NEW — 8 view JSONB + scenarios
│   ├── parser.py               760  4 시트 rule + LLM 검증 wrapper (default on)
│   ├── parser_llm.py           658  DEPRECATED 2026-05-20 (env flag 회귀)
│   ├── parser_post.py          201  NEW — 정규화 + pair + transform
│   └── reporter.py             161  종합 보고서 + G8/G2 (변경 없음)
├── api.py                     1050  FastAPI 12 엔드포인트 (이전 0 byte)
├── checkpointer.py              94  Async PostgresSaver lazy open
├── chroma_client.py             35
├── constants.py                  5
├── db.py                      1113  PGClient 25 메서드 + 2 module-level update fn
├── graph.py                    563  build_graph + build_demo_graph + 7 node + 2 helper
├── main.py                       0  stub (D-7)
├── state.py                    303  9 TypedDict (CPIAState + Activity 44 필드 + ...)
├── synthetic/generate_history.py 0  drift
└── tests/                          45+ 파일, 392 tests
```

---

## 7. 검증 상태 (full cycle 5, 844d4c3)

| 항목 | 측정 | 상태 |
|---|---|---|
| mapper_activities | 146 row, mapping_source `auto_bp_zone_match` 74% / hil 1.4% | ✅ |
| atomized_ids | 64 | ✅ |
| forecasts | 27 | ✅ |
| optimizer_advice | 13 (risky 12 → 13 keys) | ✅ |
| daily_reports JSONB — contractor_bars / trade_bars / s_curve / scenarios / optimizer_view / productivity | 모두 채워짐 | ✅ |
| daily_reports JSONB — kpi / wp_summary / quadrant | 빈 dict {} (view_builder 미구현) | ❌ Phase 2 |
| Schema validation | bp_code 100% / yesterday_cum_qty 100% / today_cum_qty 100% / plan_mh 100% / cum_actual_mh_today 99% / assigned_workers 95% / zone 16% | partial |
| Regression | 392 tests collected, 1 xfailed (test_fixture_rag_alignment, drift #N1) | ✅ |

---

*최종 수정: 2026-05-20 (ef7c6cd)*
