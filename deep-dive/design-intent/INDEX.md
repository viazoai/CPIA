# CPIA design-intent — Master INDEX

- **Generated**: 2026-05-20 (parser+mapper refactor + view_builder 752 LOC 신규 + FastAPI 12 엔드포인트 완성 cycle 후 갱신)
- **Git SHA**: `ef7c6cd` (A_Track HEAD). 이전 스냅샷 `cf3c143` 대비 80 commits, pipeline LOC 4380→8928.
- **Branch**: `A_Track` (조형준 main 머지 대기). B_Track 별도.
- **Scope**: pipeline 전체 (agents 7 active + reporter + graph + state + db + api + checkpointer). Web/B_Track 제외.
- **Pair**: `../architecture_overview.md` (deep-dive 라이트)

코드 변경/추가 작업 진입 시 아래 T1 인덱스에서 **함수 이름 / 키워드 / 파일** grep → 매칭 시 해당 서브시스템 `design_intent_<X>.md` 의 T2 카드 확인 → 기존 핸들러 확장 vs 새 설계 판단.

> **이번 cycle 갱신 요지** (vs cf3c143 / 2026-05-19):
> - **Parser 전면 리팩터** (5 commit): 4 시트 rule-based refactor + LLM 검증 wrapper (default on, env opt-out). `parser.py` 306→760. **`parser_llm.py` DEPRECATED 2026-05-20**. 신규 `parser_post.py` (201) — split_company_and_zone / extract_zone / pair_bp_summaries / transform_*. `collector.py` 0→70 (discover + asyncio.Semaphore(4) 병렬).
> - **Mapper `resolve_wa` 7단계 + shift-weighted MH** — 이전 5단계 (0+1+2+3+4) → 7단계 (0~6). 신규 source 2종: `auto_bp_zone_match` (BP-zone deterministic, fix C) + `auto_llm_rerank` (LLM rerank fallback, 옵션 A). hil_required 58% → 25% 목표. `_weighted_mh_from_shift` + `_prorate_workers_with_mh` 신규 (8h 고정 → 시간대 가중). `build_bp_context` BP 코드별 분리.
> - **Optimizer `view_builder.py` 752 LOC 신규** — daily_reports 의 8 + 1 view jsonb 산출. `_build_scenarios` (percentile 4 시나리오 no_action/p25/p50/p75) + `_build_quadrant` (impact P90 normalize) + `_build_s_curve` (4 sub 곡선) + `_build_optimizer_view` (4 섹션) + EVM 산식 정정.
> - **FastAPI 12 엔드포인트 완성** (`pipeline/api.py` 0 byte → 1050 LOC) — /health + HIL1 resume + 10 GET (sites/runs/optimizer/wp_summary/reports/performance/impact/agents/wbs_tree/tasks).
> - **PG 16 migration** — 신규 테이블 6종 (mapped_history / parser_activities / parser_job_allocations / parser_equipment_allocations / parser_worker_outputs / parser_report_meta) + 신규 컬럼 21건 (alternatives/cum_workers_today/scenarios_jsonb/hours_saved_cum/wa 등). `upsert_daily_report_view_col` (db.py:1034, UPDATE-first + 9 col 화이트리스트).
> - **Orchestration 3 hotfix**: cf2a791 (normalize_company import) + e163e1a (정규화 타이밍 — fetch_bp_candidates 전 일괄) + 844d4c3 (CPIA_HIL_AUTO_BYPASS env + pipeline_runs 사전 INSERT + HIL2 auto-select).
> - **atomizer / forecaster / reporter — 코드 변경 없음** (cf3c143 이후 commit 0). 카드 그대로 유효, last_checked 만 stamp.
> - **Full cycle 5 검증** (844d4c3): mapper_activities 146 row / auto_bp_zone_match 74% + hil 1.4% / atomized_ids 64 / forecasts 27 / optimizer_advice 13 / daily_reports 6/9 jsonb 채워짐 (kpi/wp_summary/quadrant 미산출 Phase 2).

---

## 서브시스템 8개

| 서브시스템 | 파일 | T1 | T2 | LOC | 핵심 책임 | 본 cycle 변경 |
|---|---|---:|---:|---:|---|---|
| orchestration | [design_intent_orchestration.md](./design_intent_orchestration.md) | 22 | 12 | 965 | LangGraph StateGraph + HIL 1/2 interrupt/resume + AsyncPostgresSaver checkpoint + 7 node + 2 builder | normalize_company import + 정규화 2회 + CPIA_HIL_AUTO_BYPASS env + HIL2 auto-select |
| persistence | [design_intent_persistence.md](./design_intent_persistence.md) | 27 (+12 API) | 16 | 2292 (db 1113 + api 1050 + chroma 35 + checkpointer 94) | PG asyncpg pool + Chroma HTTP + FastAPI 12 엔드포인트 | upsert_daily_report_view_col 신규 (UPDATE-first 9 col 화이트리스트) + api.py 12 엔드포인트 완성 + 16 migration |
| parser | [design_intent_parser.md](./design_intent_parser.md) | 20 | 11 | 1689 (parser 760 + parser_llm 658 DEPRECATED + parser_post 201 + collector 70) | xlsx → 4시트 (BPSummary/JobAllocation/EquipmentAllocation/Activity) + LLM 검증 wrapper | 4 시트 rule refactor + parser_post.py 신설 + LLM 검증 wrapper + collector 신설 |
| mapper | [design_intent_mapper.md](./design_intent_mapper.md) | 12 | 11 | 571 | 6단계 매핑 + resolve_wa 7단계 + shift-weighted MH + RAG top-K alternatives | resolve_wa 7단계 + auto_bp_zone_match + auto_llm_rerank + _weighted_mh_from_shift + _prorate_workers_with_mh + build_bp_context BP별 |
| atomizer | [design_intent_atomizer.md](./design_intent_atomizer.md) | 4 | 6 | 141 | Chroma daily_activities 적재 + fail-fast PG | **변경 없음** (이전 cycle hotfix 흡수) |
| forecaster | [design_intent_forecaster.md](./design_intent_forecaster.md) | 22 | 13 | 893 | RAG 우선 + Plan fallback 진단 (assessment + risk_level) | **변경 없음** |
| optimizer | [design_intent_optimizer.md](./design_intent_optimizer.md) | 30+ | 17 | 2449 (agent 199 + prompt 315 + retrieve 161 + synthetic 498 + synthetic_v2 363 + view_builder 752 NEW + reporter 161) | LLM 조언 + view_builder 8+1 jsonb + scenarios 4 시나리오 + recovery 결정론 | view_builder.py 752 LOC 신규 + _build_scenarios percentile 4 + view orchestration |
| reporter | [design_intent_reporter.md](./design_intent_reporter.md) | 5 | 7 | 161 | Mapper+Forecaster+Optimizer 종합 보고서 + daily_reports + G8/G2 | **변경 없음** (이전 cycle 흡수) |

**합계**: T1 ≈ 130+ public 함수/클래스 / T2 ≈ 93 이슈 카드. atomizer/forecaster/reporter 카드 라벨 stale 가능 (코드 변경 없음).

---

## T1 — 전 서브시스템 함수 인덱스 (Top hits)

### orchestration (`pipeline/graph.py` 563 / `state.py` 303 / `checkpointer.py` 94 / `constants.py` 5)

| Function/Class | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `GraphConfig` | graph.py:39 | `@dataclass` | 4 sub-config 묶음 (+ reporter) | — |
| `mapper_node` | graph.py:48 | `async (state, cfg) -> dict` | Parser → WBS 매핑 + Semaphore 4 + 정규화 2회 + G24 호출 + 5 PG INSERT | ✅ |
| `_build_review_needed` | graph.py:168 | `(mapped) -> list[dict]` | requires_review=True 9 필드 extraction | ✅ |
| `_apply_corrections` | graph.py:189 | `(mapped, corrections) -> list[Activity]` | corrections 적용 + source="user_corrected" | ✅ |
| `hil_1_node` | graph.py:224 | `async (state, cfg) -> dict` | interrupt + `CPIA_HIL_AUTO_BYPASS` env 우회 + PG mapping_corrections | ✅ |
| `atomizer_node` | graph.py:292 | `async (state, cfg) -> dict` | Chroma daily_activities 적재 | ✅ |
| `forecaster_node` | graph.py:299 | `async (state, cfg) -> dict` | 그룹별 생산성 진단 | ✅ |
| `hil_2_node` | graph.py:306 | `async (state, cfg) -> dict` | risky 사전 영속 + F5/F7 정정 + interrupt | ✅ |
| `optimizer_node` | graph.py:415 | `async (state, cfg) -> dict` | Selected group advice + view_builder + PG | ✅ |
| `reporter_node` | graph.py:435 | `async (state, cfg) -> dict` | 종합 보고서 + G8/G2 + site_id PG fallback | ✅ |
| `build_demo_graph` | graph.py:476 | `(cfg) -> CompiledGraph` | forecaster→hil_2→(opt\|rep)→END | ✅ |
| `build_graph` | graph.py:514 | `(cfg) -> CompiledGraph` | mapper→hil_1→atomizer→forecaster→hil_2→(opt\|rep)→reporter→END | ✅ |
| `CPIAState` | state.py:226 | TypedDict | LangGraph 전체 상태 16 필드 | ✅ |
| `Activity` | state.py:32 | TypedDict | 시트4 매핑 단위 44 필드 (16 신규) | ✅ |

### persistence (`pipeline/db.py` 1113 / `api.py` 1050 / `chroma_client.py` 35 / `checkpointer.py` 94)

| Function/Class | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| **db.py — SELECT** | | | | |
| `fetch_bp_candidates` | db.py:38 | `async (company, site_id=None) -> list[dict]` | Mapper BP filter (정확 일치) | ✅ |
| `fetch_activity` | db.py:73 | `async (wbs_activity_id, site_id=None) -> dict\|None` | ActivityID → Plan (미사용 의심 #N3) | ✅ |
| `fetch_l6_plan_mh_map` | db.py:106 | `async (company, l6_list, site_id=None) -> dict` | (l6 → plan_mh) dict (N+1 회피) | ✅ |
| `fetch_plan_for_group` | db.py:194 | `async (company, l6_main, site_id=None) -> dict` | 2 SQL 분리 (jsonb_object_agg duplicate key) | ✅ |
| **db.py — INSERT** | | | | |
| `insert_pipeline_run` | db.py:147 | `async (run_id, site_id, date, status)` | pipeline_runs INSERT | ✅ |
| `insert_forecast` | db.py:260 | `async (row: dict)` | 28 col + wa, JSONB 3종 | ✅ |
| `insert_optimizer_advice` | db.py:332 | `async (row: dict)` | 9 col, JSONB 4종 | ✅ |
| `insert_mapping_correction` | db.py:370 | `async (...)` | HIL 1 correction | ✅ |
| `insert_daily_report` | db.py:405 | `async (..., site_id=None)` | site_id auto-fetch | ✅ |
| `insert_mapped_history_batch` | db.py:440 | `async (...)` | ON CONFLICT UPDATE (run_id, wa, l6, company) | ✅ |
| `insert_parser_report` | db.py:497 | `async (...)` | parser_reports 1 row | ✅ |
| `insert_parser_activities_batch` | db.py:540 | `async (...)` | 23 col, ON CONFLICT (run_id, idx) | ✅ |
| `insert_mapper_activities_batch` | db.py:621 | `async (...)` | **33 col + alternatives + cum_workers/mh** | ✅ |
| `insert_parser_job_allocations_batch` | db.py:743 | `async (...)` | G24, 시트2 3 group JSONB | ✅ |
| `insert_parser_equipment_allocations_batch` | db.py:815 | `async (...)` | G24, 시트3 3 group JSONB | ✅ |
| `insert_parser_worker_outputs_batch` | db.py:881 | `async (...)` | 시트6 업체별 | ✅ |
| `insert_parser_report_meta_batch` | db.py:952 | `async (...)` | Cover 업체별 | ✅ |
| **db.py — UPDATE / Module-level** | | | | |
| `upsert_daily_report_view_col` | db.py:1034 | `async (run_id, site_id, report_date, col, value)` | **UPDATE-first + 9 col 화이트리스트** | ✅ |
| `update_site_last_run` | db.py:1081 | `async (pg, site_id, run_id)` | G8 — sites.last_run_id | ✅ |
| `update_site_hours_saved_cum` | db.py:1097 | `async (pg, site_id, atomized_count)` | G2 — (120-5)/60 × atomized_count h | ✅ |
| **chroma_client.py** | | | | |
| `ChromaClient.get_or_create_wbs_master` | chroma_client.py:23 | `() -> Collection` | Mapper RAG (189 doc) | ✅ |
| `ChromaClient.get_or_create_daily_activities` | chroma_client.py:30 | `() -> Collection` | Forecaster + Optimizer retrieve | ✅ |
| **checkpointer.py** | | | | |
| `_LazyAsyncPostgresSaver` | checkpointer.py | class | sync __init__ + async pool open lazy | ✅ |
| `build_checkpointer` | checkpointer.py:78 | `() -> CheckpointerBase` | env 분기 (InMemory \| Postgres) | ✅ |
| **api.py — FastAPI 12 endpoint** | | | | |
| `GET /health` | api.py:188 | — | {status, pg, version} | — |
| `POST /api/runs/{run_id}/hil_1/resume` | api.py:200 | — | {next_node} (graph.ainvoke resume) | ✅ |
| `GET /api/sites` | api.py:314 | — | Site[] (sites + forecasts LATERAL) | ✅ |
| `GET /api/runs/{run_id}/optimizer` | api.py:378 | — | OptimizerOutput[] | ✅ |
| `GET /api/runs/{run_id}/wp_summary` | api.py:458 | — | WPSummaryRow[] | ✅ |
| `GET /api/sites/{site_id}/reports` | api.py:519 | days | ReportDaily[] | ✅ |
| `GET /api/dashboard/performance` | api.py:560 | — | fleet_kpi | ✅ |
| `GET /api/dashboard/impact` | api.py:620 | — | ImpactSiteDistribution[] | ✅ |
| `GET /api/agents/status` | api.py:706 | — | AgentStatus[] (7× SELECT COUNT) | ✅ |
| `GET /api/sites/{site_id}/wbs_tree` | api.py:809 | — | WBSNode (tree) | ✅ |
| `GET /api/tasks` | api.py:1022 | site_id, days | tasks + progressByDate + itemsByDate | ✅ |

### parser (`pipeline/agents/parser.py` 760 / `parser_llm.py` 658 DEPRECATED / `parser_post.py` 201 / `collector.py` 70)

| Function | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| **parser.py** | | | | |
| `parse_daily_report` | parser.py:539 | `(xlsx_path) -> ParsedDailyReport` | 4 시트 통합 공개 API (LLM 검증 default on) | ✅ |
| `_parse_sheet1_bp_summaries` | parser.py:127 | `(ws) -> list[BPSummary]` | col 30 merged group boundary | ✅ |
| `_parse_sheet2_job_allocations` | parser.py:255 | `(ws) -> list[JobAllocation]` | | ✅ |
| `_parse_sheet4_activities` | parser.py:346 | `(ws) -> list[Activity]` | ffill 4 컬럼 + cross-check B+C=D | ✅ |
| `_parse_sheet3_equipment_allocations` | parser.py:428 | `(ws) -> list[EquipmentAllocation]` | | ✅ |
| `_should_verify_llm` | parser.py:591 | `() -> bool` | env CPIA_PARSER_VERIFY_LLM (default on) | ✅ |
| `_verify_sheet1_via_llm` | parser.py:597 | `(ws, bp_summaries)` | 시트1 LLM 검증 (8 error path) | ✅ |
| `_verify_sheet4_via_llm` | parser.py:679 | `(ws, activities)` | 시트4 LLM 검증 | ✅ |
| **parser_post.py (NEW)** | | | | |
| `filter_marker_rows` | parser_post.py:32 | `(raw_rows, target_key) -> list[dict]` | 소계/합계 제거 | ✅ |
| `pair_bp_summaries` | parser_post.py:44 | `(raw_rows) -> list[dict]` | 시트1 2-row pairing | ✅ |
| `normalize_company` | parser_post.py:92 | `(raw) -> str\|None` | ㈜/괄호 제거 | ✅ |
| `split_company_and_zone` | parser_post.py:108 | `(raw) -> str\|None` | 회사명 끝 FAB/CUB suffix 분리 | ✅ |
| `extract_zone` | parser_post.py:120 | `(v6) -> str\|None` | col 6 옵션 2 보수 매칭 | ✅ |
| `transform_bp_summaries` | parser_post.py:183 | `(raw_rows) -> list[dict]` | filter+pair+normalize+split 파이프라인 | ✅ |
| **parser_llm.py — DEPRECATED 2026-05-20** | | | | |
| `parse_daily_report_llm` | parser_llm.py:501 | `async (...)` | LLM chunk parsing (env flag 회귀) | — |
| **collector.py (NEW)** | | | | |
| `discover_daily_reports` | collector.py:30 | `(input_dir) -> list[Path]` | xlsx 재귀 탐색 (sort) | ✅ |
| `collect_and_parse` | collector.py:52 | `async (input_dir, cfg) -> list[ParsedDailyReport]` | asyncio.Semaphore(4) 병렬 | ✅ |

### mapper (`pipeline/agents/mapper.py` 571)

| Function | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `_weighted_mh_from_shift` | mapper.py:37 | `(shift_dict) -> float` | 시간대 가중 MH (조출 2/주간 8/연장 4/야간 8/철야 12) | ✅ |
| `_prorate_workers_with_mh` | mapper.py:48 | `(mapped, parsed_report, company_total_plan_mh, active_l6_for_company) -> list[dict]` | U1.A/B — l6 비례 분배 (plan_mh/uniform/zero 3 fallback) | ✅ |
| `_is_trade_job` | mapper.py:134 | `(job) -> bool` | 시트2 직종 noise 필터 | ✅ |
| `WAResolution` | mapper.py:144 | `@dataclass(frozen=True)` | source Literal 7종 | — |
| `build_embedding_input` | mapper.py:159 | `(activity) -> str` | 임베딩 input (숫자 제외) | ✅ |
| `build_bp_context` | mapper.py:172 | `(company, parsed_report) -> str` | **BP 코드별 분리** + 시트1+2+3 join | ✅ |
| `build_llm_input` | mapper.py:231 | `(activity, parsed_report) -> str` | embedding + bp_context + activity.bp_code 명시 | ✅ |
| `resolve_wa` | mapper.py:248 | `(activity, l6_choice, cand_pool, parsed_report, chosen_wa=None) -> WAResolution` | **WA 결정 7단계 (0~6)** | ✅ |
| `_select_top_k_alternatives` | mapper.py:312 | `(candidates, k=3) -> list[dict]` | RAG top-K alternatives jsonb | ✅ |
| `MapperConfig` | mapper.py:324 | `@dataclass` | Azure + Chroma + PG + conf_threshold | — |
| `map_activity` | mapper.py:341 | `async (activity, parsed_report, cfg, bp_cand_lookup=None) -> Activity` | 6단계 통합 (BP filter → 임베딩 → Chroma → LLM → 분류 → resolve_wa) | ✅ |
| `_prorate_mh` | mapper.py:496 | `async (mapped, parsed_report, pg) -> list[Activity]` | (company, l6_main) 단위 분배 외피 | ✅ |

### atomizer (`pipeline/agents/atomizer.py` 141) — **코드 변경 없음**

| Function | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `atomize` | atomizer.py | `async (mapped, cfg) -> list[str]` | Chroma daily_activities embed + INSERT | ✅ |
| `_build_doc` | atomizer.py | `(activity) -> str` | 임베딩 문서 조립 | ✅ |
| `_build_meta` | atomizer.py | `(activity) -> dict` | metadata (worker_source / company / l6_main / ...) | ✅ |
| `AtomizerConfig` | atomizer.py | `@dataclass` | Azure + Chroma | — |

### forecaster (`pipeline/agents/forecaster/` 8 파일, 893 LOC) — **코드 변경 없음**

| Function | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `forecast` | forecaster/agent.py:~ | `async (mapped, cfg) -> list[dict]` | 그룹별 RAG + Plan fallback 진단 | ✅ |
| `_classify_risk_level` | forecaster/classify.py:34 | `(row) -> Literal[...]` | 정상/주의/이상 분류 (PM 원안 v2) | ✅ |
| `_rerank_similar_cases` | forecaster/rerank.py | `(candidates) -> list[dict]` | 유사 사례 rerank | ✅ |
| `_aggregate_groups` | forecaster/aggregate.py | `(mapped) -> dict` | (company, l6_main) 단위 집계 | ✅ |
| `_load_synthetic` | forecaster/synthetic.py | `(cfg) -> dict` | synthetic 30일 fixture | ✅ |
| (외 prompt.py / constants.py / __init__.py) | | | | |

### optimizer (`pipeline/agents/optimizer/` 6 파일, 2449 LOC)

| Function | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| **agent.py** | | | | |
| `optimize` | agent.py:~50 | `async (...) -> list[dict]` | LLM 호출 + view_builder 8+1 + daily_reports UPSERT | ✅ |
| `_compute_recovery_distribution` | agent.py:99 | `(cases) -> dict[str, int]` | 결정 #20 코드단 deterministic Counter | ✅ |
| `_compose_cold_start_row` | agent.py:~130 | `(r, cases, run_id) -> dict` | cases<3 cold_start | ✅ |
| `_compose_row` | agent.py:~150 | `(r, cases, llm_output, run_id) -> dict` | LLM 출력 + cases merge | ✅ |
| `_call_azure_llm` | agent.py:~175 | `(...) -> dict` | 결정 #10 fail-fast | ✅ |
| **prompt.py** | | | | |
| `build_llm_user_input` | prompt.py:~50 | `(forecast_row, degradation_cases) -> dict` | LLM user message JSON | ✅ |
| **retrieve.py** | | | | |
| `fetch_degradation_cases` | retrieve.py:~30 | `(metas, docs, ...) -> list[dict]` | Step 1 (incident + < baseline×0.85) | ✅ |
| `fetch_recovery_trajectory` | retrieve.py:~80 | `(metas, ...) -> dict` | Step 2 (recovery ≥ baseline×0.95 first day) | ✅ |
| `_group_baseline` | retrieve.py:~120 | `(...) -> Optional[float]` | baseline 평균 (None → cold_start) | ✅ |
| **view_builder.py (NEW 752 LOC)** | | | | |
| `_build_productivity_views` | view_builder.py | `async (...)` | 4 EVM view (today/by_contractor/by_l6/by_wp) | ✅ |
| `_compose_evm` | view_builder.py | `(plan_row, actual_row) -> dict` | EV/PV/AC/SPI/CPI | ✅ |
| `_evm_by_group` | view_builder.py | `async (..., group_key)` | FULL OUTER JOIN group_key 다형성 | ✅ |
| `_build_kpi` | view_builder.py | `async (...)` | 헤더 KPI | ✅ |
| `_build_contractor_bars` / `_build_trade_bars` | view_builder.py | `(...)` | CPI desc bars | ✅ |
| `_build_quadrant` | view_builder.py | `async (...)` | 4분면 산점도 (impact P90 normalize) | ✅ |
| `_quadrant_label` | view_builder.py | `(productivity, impact) -> str` | risk/caution/watch/safe | ✅ |
| `_build_wp_summary` | view_builder.py | `async (...)` | quadrant 기반 WP 표 | ✅ |
| `_build_optimizer_view` | view_builder.py | `(advice_rows, forecast) -> dict` | by_wp 4 섹션 (진단/유사/권고/상세) | ✅ |
| `_build_scenarios` | view_builder.py | `(advice_rows, forecast) -> dict` | **percentile 4 시나리오 (2026-05-19 NEW)** | ✅ |
| `_expand_recovery_to_days` | view_builder.py | `(recovery_distribution) -> list[int]` | not_recovered +30 cap | ✅ |
| `_percentile` | view_builder.py | `(days, q) -> float` | quantiles inclusive | — |
| `_coerce_date` | view_builder.py | `(v) -> date\|None` | date/str/None 안전 coerce (2026-05-19 fix) | ✅ |
| `_build_s_curve` | view_builder.py | `async (...)` | planned/actual/forecast/recovery 4 곡선 | ✅ |
| `_merge_curves` / `_extend_forecast` | view_builder.py | `(...)` | date 정합 + linear 연장 | ✅ |
| **synthetic_v2.py** | | | | |
| `generate_synthetic_v2_group` | synthetic_v2.py | `(...)` | state machine 90일 + 회복 룰 7건 | ✅ |
| **synthetic_daily_report.py — Demo CLI** | | | | |
| `generate_fake_daily_report` | synthetic_daily_report.py | `(report_date, scenarios, ...) -> list[Activity]` | Activity 직접 생성 (Parser/Mapper skip) | ✅ |

### reporter (`pipeline/agents/reporter.py` 161) — **코드 변경 없음**

| Function | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `report` | reporter.py | `async (mapped, forecast_rows, optimizer_advice, run_id, today, cfg) -> (str, dict)` | 종합 보고서 + daily_reports INSERT | ✅ |
| `_build_llm_input` | reporter.py | `(...) -> dict` | LLM user message (spec §5.3) | ✅ |
| `_build_summary` | reporter.py | `(...) -> dict` | summary JSONB (Dashboard 카드 source) | ✅ |

---

## 검색 가이드

| 키워드 / 시나리오 | 서브시스템 | 우선 카드 |
|---|---|---|
| WA 결정 / 매핑 정확도 | mapper | `resolve_wa` (7단계) |
| BP 컨텍스트 / LLM input | mapper | `build_bp_context` + `build_llm_input` |
| MH 산식 / EVM AC 분모 | mapper + optimizer | `_weighted_mh_from_shift` + `_compose_evm` |
| 시트 추출 / 4 시트 rule | parser | `_parse_sheet1_bp_summaries` / `_parse_sheet4_activities` |
| FAB/CUB / zone 결정 | parser | `extract_zone` + `split_company_and_zone` |
| LLM 검증 / cost cap | parser | `_verify_sheet1_via_llm` (8 error path) |
| HIL / interrupt / resume | orchestration | `hil_1_node` (AUTO_BYPASS env) + `hil_2_node` (F5/F7) |
| daily_reports JSONB / view | optimizer + persistence | `_build_scenarios` + `upsert_daily_report_view_col` |
| 4분면 / impact P90 | optimizer | `_build_quadrant` + `_compute_impact_p90` |
| s_curve / forecast 연장 | optimizer | `_build_s_curve` + `_extend_forecast` |
| EVM 산식 / mapper anchor | optimizer | `_evm_by_group` + `_evm_for_group` |
| recovery_distribution / scenarios | optimizer | `_compute_recovery_distribution` + `_build_scenarios` |
| PG migration / 신규 컬럼 | persistence | (architecture_overview.md §3.3) + `upsert_daily_report_view_col` |
| FastAPI endpoint | persistence | api.py:188~1051 (12 endpoint) |
| 회사명 정규화 / cand_pool | parser_post + orchestration | `normalize_company` + graph.py:67~68 (정규화 타이밍) |
| HIL2 auto-select / full cycle | orchestration | `hil_2_node` + scripts/run_one_cycle.py |
| G8 / G2 KPI 적재 | reporter + persistence | `update_site_last_run` + `update_site_hours_saved_cum` |

---

*최종 수정: 2026-05-20 (ef7c6cd)*
