# CPIA design-intent — Master INDEX

- **Generated**: 2026-05-19 (FE↔BE 연결 + 6 BE 적재 보완 cycle 후 갱신)
- **Git SHA**: `cf3c143` (A_Track HEAD, PR #28 pending — 조형준 main 머지 리뷰 대기)
- **Scope**: pipeline 전체 (agents 7 active + reporter + graph + state + db + checkpointer) — Web/B_Track 제외
- **Pair**: `../architecture_overview.md` (deep-dive 라이트)

코드 변경/추가 작업 진입 시 아래 T1 인덱스에서 **함수 이름 / 키워드 / 파일** grep → 매칭 시 해당 서브시스템 `design_intent_<X>.md` 의 T2 카드 확인 → 기존 핸들러 확장 vs 새 설계 판단.

> **이번 cycle 갱신 요지** (vs 이전 d57b0c5):
> - 신규 PG 컬럼 2건 + migration 2건: `sites.hours_saved_cum` (G2, `infra/postgres/migrations/2026-05-19_sites_hours_saved_cum.sql`) + `mapper_activities.alternatives` jsonb + GIN (G23, `infra/postgres/migrations/2026-05-19_mapper_alternatives.sql`)
> - persistence: `update_site_last_run` / `update_site_hours_saved_cum` helper 신규 (`pipeline/db.py:1017`, `pipeline/db.py:1033`), `insert_mapper_activities_batch` 에 `alternatives` 컬럼 추가 (`pipeline/db.py:621`)
> - orchestration: `mapper_node` 안에 G24 호출 추가 (`pipeline/graph.py:121` insert_parser_job_allocations_batch + `pipeline/graph.py:127` insert_parser_equipment_allocations_batch — 이전 호출 누락으로 row=0), `reporter_node` 끝에 G8 (sites.last_run_id) + G2 (hours_saved_cum) UPDATE + `state.site_id` PG fallback (`pipeline/graph.py:434`)
> - atomizer + forecaster: 안전 처리 hotfix — None work_content/conditions filter (`pipeline/agents/atomizer.py:69`, `pipeline/agents/forecaster/agent.py:255`)
> - mapper: `_select_top_k_alternatives` helper 신규 (`pipeline/agents/mapper.py:213`) + Chroma query include "distances" → `alternatives` jsonb 적재 (`pipeline/agents/mapper.py:290`, `pipeline/agents/mapper.py:393`)
> - Prod cycle 1회 완주 검증 (run_id=627e2c4d, 2026-05-19): G5=4, G8 매치, G2=7.67h, G19=6/6, G23 alt=6/6, G24 job=15, forecasts=4, daily_reports=1 — 6 적재 항목 모두 ✅
> - 신규 T2 카드 18건 — persistence (G2-1/G8-1/G23-1/G19-1), atomizer (A-N1/A-N2), forecaster (F-N1/F-N2), orchestration (O-G24/O-G8/O-G2/O-N6), reporter (R-G8/R-G2/R-N7), mapper (M-G23-1/M-G23-2/M-G23-3). 상세는 각 서브시스템 카드 참조.

---

## 서브시스템 8개

| 서브시스템 | 파일 | T1 | T2 | 핵심 책임 | 미해결 핵심 |
|---|---|---:|---:|---|---|
| orchestration | [design_intent_orchestration.md](./design_intent_orchestration.md) | 21 | 18 | LangGraph StateGraph + HIL 1/2 interrupt/resume + AsyncPostgresSaver checkpoint + mapper_node 의 G24 / reporter_node 의 G8+G2+site_id fallback | drift #N5 LangGraph Command(resume=dict) str key 룰 |
| persistence | [design_intent_persistence.md](./design_intent_persistence.md) | 20 | 15 | PG asyncpg pool (8 활성 + sites.hours_saved_cum 신규 + mapper_activities.alternatives 신규) + Chroma HTTP (2 컬렉션) | drift #N2 + #N3 schema migration (postgres.md vs init.sql), `fetch_activity` 미사용 의심 |
| parser | [design_intent_parser.md](./design_intent_parser.md) | 12 | 11 | xlsx → 4시트 (BPSummary/JobAllocation/EquipmentAllocation/Activity) | Collector (0 byte) 자리 비어있음 |
| mapper | [design_intent_mapper.md](./design_intent_mapper.md) | 10 | 12 | 6단계 매핑 + RAG top-K alternatives 적재 (G23) | WA 3단계 (시트1 자연어) TODO |
| atomizer | [design_intent_atomizer.md](./design_intent_atomizer.md) | 4 | 6 | Chroma daily_activities 적재 + fail-fast PG + None work_content/conditions 가드 (hotfix) | `embedding_dim` 필드 미사용 의심 |
| forecaster | [design_intent_forecaster.md](./design_intent_forecaster.md) | ~17 | 15 | RAG 우선 + Plan fallback 진단 (assessment + risk_level) + None work_content 가드 (hotfix) | classify.py:34 PM 원안 v2 정합 — drift #2 해소 (#3 root cause) |
| optimizer | [design_intent_optimizer.md](./design_intent_optimizer.md) | ~23 | 7 | LLM 조언 + 결정론 recovery_distribution + synthetic fixture (fix) | drift #N1 RAG fixture_prod vs synthetic_v2 분포 ±10% mismatch, D-1 (병행작업 룰) |
| reporter | [design_intent_reporter.md](./design_intent_reporter.md) | 5 | 7 | Mapper+Forecaster+Optimizer 종합 보고서 1 종 + PG daily_reports + G8 sites.last_run_id UPDATE + G2 hours_saved_cum 누적 | reporter→exporter rename backlog, 공통 _call_azure_llm 추출 후보 (low) |

**합계**: T1 ≈ 112 public 함수/클래스 / T2 ≈ 91 이슈 카드 (본 cycle +18).

---

## T1 — 전 서브시스템 함수 인덱스

### orchestration (`pipeline/graph.py` / `state.py` / `checkpointer.py` / `constants.py`)

| Function/Class | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `GraphConfig` | graph.py:39 | `@dataclass` | 4 sub-config 묶음 (+ reporter) | — |
| `mapper_node` | graph.py:47 | `async (state, cfg) -> dict` | Parser → WBS 매핑 + `_prorate_mh` + **G24** (job/equipment_allocations INSERT 호출 추가, 이전 호출 누락으로 row=0) + `insert_mapper_activities_batch` alternatives | ✅ O-G24 |
| `_build_review_needed` | graph.py:157 | `(mapped) -> list[dict]` | requires_review=True 만 review payload | ✅ |
| `_apply_corrections` | graph.py:178 | `(mapped, corrections) -> list[Activity]` | corrections 적용 + 답 안 한 row Mapper 추천 수용 | ✅ |
| `hil_1_node` | graph.py:213 | `async (state, cfg) -> dict` | review_needed 빌드 + interrupt + corrections 적용 + PG insert_mapping_correction | ✅ |
| `atomizer_node` | graph.py:268 | `async (state, cfg) -> dict` | Chroma daily_activities 적재 | ✅ |
| `forecaster_node` | graph.py:275 | `async (state, cfg) -> dict` | 그룹별 생산성 진단 | ✅ |
| `hil_2_node` | graph.py:282 | `async (state, cfg) -> dict` | risky 그룹 사전 영속 + interrupt | ✅ |
| `optimizer_node` | graph.py:391 | `async (state, cfg) -> dict` | Selected group advice + PG insert | ✅ |
| `reporter_node` | graph.py:411 | `async (state, cfg) -> dict` | Mapper+Forecaster+Optimizer 종합 report + **G8** sites.last_run_id UPDATE + **G2** hours_saved_cum 누적 + state.site_id 누락 시 pipeline_runs fallback | ✅ O-G8 / O-G2 / O-N6 |
| `build_graph` | graph.py:490 | `(cfg) -> CompiledGraph` | mapper→hil_1→atomizer→forecaster→hil_2→[optimizer\|reporter]→reporter→END | ✅ |
| `build_demo_graph` | graph.py:452 | `(cfg) -> CompiledGraph` | forecaster→hil_2→[optimizer\|reporter]→reporter→END (mapper/atomizer/hil_1 skip) | ✅ |
| `Activity` | state.py:11 | TypedDict | 작업일보 1행 | — |
| `BPSummary` | state.py:59 | TypedDict | 시트1 BP사 × 공종 | — |
| `JobAllocation` | state.py:74 | TypedDict | 시트2 BP사 × 직종 | — |
| `EquipmentAllocation` | state.py:84 | TypedDict | 시트3 BP사 × 장비 | — |
| `ParsedDailyReport` | state.py:95 | TypedDict | 4시트 통합 | — |
| `CPIAState` | state.py:106 | TypedDict | LangGraph 전체 상태 (17 필드) | ✅ |
| `build_checkpointer` | checkpointer.py:13 | `() -> InMemorySaver` | Phase 1 PoC checkpointer | ✅ |
| `WORK_HOURS_PER_DAY` | constants.py:5 | `int=8` | pipeline-wide constant | — |

### persistence (`pipeline/db.py` / `chroma_client.py`)

| Function/Class | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `PGClient` | db.py:18 | class | asyncpg 풀 래퍼 | — |
| `PGClient.connect` | db.py:24 | `async () -> None` | pool 생성 | — |
| `PGClient.close` | db.py:32 | `async () -> None` | pool 정리 | — |
| `PGClient.fetch_bp_candidates` | db.py:38 | `async (company) -> list[dict]` | BP사 → (wa, l6) 후보 | ✅ |
| `PGClient.fetch_activity` | db.py:56 | `async (wbs_activity_id) -> dict\|None` | ActivityID 단건 | — (미사용 의심) |
| `PGClient.fetch_l6_plan_mh_map` | db.py:72 | `async (company, l6_list) -> dict[str,int]` | N+1 회피 GROUP BY | ✅ |
| `PGClient.insert_pipeline_run` | db.py:98 | `async (run_id, ...) -> None` | pipeline_runs 1 row | — |
| `PGClient.delete_pipeline_run` | db.py:121 | `async (run_id) -> None` | test cleanup | — |
| `PGClient.assert_pipeline_run_exists` | db.py:127 | `async (run_id) -> None` | Atomizer fail-fast | ✅ |
| `PGClient.fetch_plan_for_group` | db.py:145 | `async (company, l6_main) -> dict\|None` | 그룹 Plan Σ | ✅ |
| `PGClient.update_run_atomized_count` | db.py:183 | `async (run_id, count) -> None` | 0-row RuntimeError 검증 | ✅ |
| `PGClient.insert_forecast` | db.py:205 | `async (row) -> None` | forecasts INSERT (27 컬럼) | ✅ |
| `PGClient.insert_optimizer_advice` | db.py:273 | `async (row) -> None` | optimizer_advice INSERT (9 컬럼, JSONB falsy 보호) | ✅ |
| `PGClient.insert_mapper_activities_batch` | db.py:621 | `async (run_id, report_date, activities) -> None` | mapper_activities INSERT (run_id, idx) 멱등 + **alternatives jsonb** (G23, 본 cycle 추가) + 풀 30 컬럼 | ✅ G23-1 / G19-1 |
| `update_site_last_run` | db.py:1017 | `async (pg, site_id, run_id) -> None` | **G8** — `UPDATE sites SET last_run_id=$1 WHERE site_id=$2`. reporter→END 진입 시 호출 | ✅ G8-1 |
| `update_site_hours_saved_cum` | db.py:1033 | `async (pg, site_id, atomized_count) -> None` | **G2** — `UPDATE sites SET hours_saved_cum = hours_saved_cum + delta WHERE site_id=$2`. 산식 `((AS_IS_MIN=120 - TO_BE_MIN=5) / 60.0) × atomized_count` (≈1.917h/일보). 상수 `db.py:1029-1030` | ✅ G2-1 |
| `ChromaClient` | chroma_client.py:14 | class | HTTP wrapper | — |
| `ChromaClient.get_or_create_wbs_master` | chroma_client.py:23 | `() -> Collection` | wbs_master (Mapper RAG) | ✅ |
| `ChromaClient.get_or_create_daily_activities` | chroma_client.py:30 | `() -> Collection` | daily_activities (유사 이력) | ✅ |

### parser (`pipeline/agents/parser.py`)

| Function/Class | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `ParseError` | parser.py:23 | Exception | 포맷 위반 | — |
| `_normalize_unit` | parser.py:40 | `(s) -> str` | M2→m2 | ✅ |
| `_disc_abbrev_to_kr` | parser.py:45 | `(abbrev) -> str\|None` | AR→건축 등 | ✅ |
| `_is_admin_job` | parser.py:52 | `(job) -> bool` | 관리자 직종 필터 | ✅ |
| `_is_total_row` | parser.py:57 | `(row) -> bool` | 합계 row 필터 | ✅ |
| `_ffill` | parser.py:65 | `(rows, header_end, fill_cols) -> list` | 병합 셀 forward-fill | ✅ |
| `_parse_sheet1_bp_summaries` | parser.py:90 | `(ws) -> list[BPSummary]` | 시트1 | ✅ |
| `_parse_sheet2_job_allocations` | parser.py:124 | `(ws) -> list[JobAllocation]` | 시트2 (관리자 필터) | ✅ |
| `_parse_sheet3_equipment_allocations` | parser.py:196 | `(ws) -> list[EquipmentAllocation]` | 시트3 | ✅ |
| `_parse_sheet4_activities` | parser.py:158 | `(ws) -> list[Activity]` | 시트4 (Mapper 입력) | ✅ |
| `_extract_meta` | parser.py:237 | `(xlsx_path, wb) -> tuple` | 파일명 → date + project | ✅ |
| `parse_daily_report` | parser.py:270 | `(xlsx_path) -> ParsedDailyReport` | 4시트 통합 (공개 API) | ✅ |

### mapper (`pipeline/agents/mapper.py`)

| Function/Class | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `_is_trade_job` | mapper.py:64 | `(job) -> bool` | 기능공 추출 | ✅ |
| `WAResolution` | mapper.py:74 | `@dataclass(frozen=True)` | WA 결정 4단계 출력 | ✅ |
| `build_embedding_input` | mapper.py:86 | `(activity) -> str` | 임베딩 단순 input (숫자 제외) | ✅ |
| `build_bp_context` | mapper.py:99 | `(company, parsed_report) -> str` | BP사 풍부 컨텍스트 | ✅ |
| `build_llm_input` | mapper.py:150 | `(activity, parsed_report) -> str` | LLM 분류 input | ✅ |
| `resolve_wa` | mapper.py:166 | `(activity, l6_choice, cand_pool, parsed) -> WAResolution` | WA 결정 4단계 | ✅ |
| `_select_top_k_alternatives` | mapper.py:213 | `(candidates, k=3) -> list[dict]` | **G23** — RAG candidate score desc top-K → `{wa, l6_main, score}` 추출, FE review dropdown 용 jsonb. Chroma query `include=["distances"]` (mapper.py:290) → `1.0 - dist` 산출 | ✅ M-G23-1 / M-G23-2 |
| `MapperConfig` | mapper.py:224 | `@dataclass` | Azure/PG/Chroma + threshold 0.7 | ✅ |
| `map_activity` | mapper.py:242 | `async (activity, parsed, cfg) -> Activity` | 6단계 통합 + `alternatives` 필드 반환 (mapper.py:393) | ✅ M-G23-3 |
| `_prorate_mh` | mapper.py:397 | `async (mapped, parsed, pg) -> list[Activity]` | 인원 비례 분배 | ✅ |

### atomizer (`pipeline/agents/atomizer.py`)

| Function/Class | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `AtomizerConfig` | atomizer.py:24 | `@dataclass` | Azure + Chroma + batch/timeout/dim | ✅ |
| `_make_doc_id` | atomizer.py:39 | `(date, company, l6_main, work_content) -> str` | SHA256 16자 결정성 ID | ✅ |
| `_build_metadata` | atomizer.py:45 | `(a, date, run_id) -> dict` | 12 필드 평탄화 metadata + `a["l6_main"] or ""` / `a["wa"] or ""` / `",".join(a.get("conditions") or [])` 가드 (atomizer.py:51-58, 본 cycle 안전 처리) | ✅ A-N1 |
| `atomize` | atomizer.py:62 | `async (mapped, parsed_report, run_id, cfg) -> list[str]` | Chroma upsert. valid filter `l6_main is not None and a.get("work_content")` (atomizer.py:69, None work_content 가드 — 본 cycle hotfix) | ✅ A-N2 |

### forecaster (`pipeline/agents/forecaster/`)

| Function/Class | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `ForecasterConfig` | agent.py:35 | `@dataclass` | 환경 설정 | — |
| `_format_chroma_result` | agent.py:53 | `(rag_result) -> list[dict]` | Chroma → rerank input | — |
| `_forecast_one_group` | agent.py:67 | `async (...) -> dict` | 8단계 진단. work_content set 조립 시 `if a.get("work_content")` 가드 + conditions set 시 `a.get("conditions") or []` (agent.py:91-92, None 가드) | ✅ F-N1 |
| `forecast` | agent.py:229 | `async (mapped, run_id, today, cfg) -> list[dict]` | 그룹 fan-out + PG insert. group 빌드 시 `if a["l6_main"] is None: continue` + `if not a.get("work_content"): continue` (agent.py:253-256, None 가드 — 본 cycle hotfix) | ✅ F-N2 |
| `SYSTEM_PROMPT` | prompt.py:12 | str | 3 단계 reasoning system | — |
| `FEW_SHOT_MESSAGES` | prompt.py:93 | list[dict] | 3 pair (정상/주의/이상) | — |
| `build_llm_user_input` | prompt.py:103 | `(today, similar, plan, assessment) -> dict` | LLM user input | ✅ |
| `RAG_NORMAL_BOUND` | classify.py:19 | `0.15` | ±15% delta | — |
| `RAG_WARN_BOUND` | classify.py:20 | `0.25` | ±25% delta | — |
| `PLAN_NORMAL_RATIO` | classify.py:21 | `0.85` | Plan ratio 정상 | — |
| `PLAN_WARN_RATIO` | classify.py:22 | `0.65` | Plan ratio 주의 | — |
| `classify_assessment_rag` | classify.py:27 | `(today, rag_avg) -> str` | RAG 모드 | ✅ |
| `classify_assessment_plan` | classify.py:41 | `(today, plan_qty, plan_mh) -> str` | Plan fallback | ✅ |
| `classify_assessment` | classify.py:65 | `(rag_n, ...) -> Optional[str]` | RAG/Plan/cold_start 라우팅 | ✅ |
| `classify_risk_level` | classify.py:83 | `(assessment, recovery, delay, state) -> Optional[str]` | hybrid 룰 | ✅ |
| `_normalize_chroma_metadata` | rerank.py:20 | `(m) -> dict` | atomizer CSV → list | ✅ |
| `rerank_cases` | rerank.py:32 | `(cases) -> list[dict]` | 가중치 재정렬 | ✅ |
| `aggregate_today_by_unit` | aggregate.py:14 | `(activities) -> dict[str, float]` | unit별 Σ | ✅ |
| `compute_delay` | aggregate.py:23 | `(plan, today, win_start, cum_mh) -> dict` | window mh 비교 + state | ✅ |
| `fetch_chroma_actual` | aggregate.py:86 | `(coll, ...) -> tuple` | 과거 누적 mh | ✅ |
| `generate_synthetic_day` | synthetic.py:21 | `(base_row, ...) -> dict` | 변동 패턴 1일 | ✅ |
| `WORK_HOURS_PER_DAY` | constants.py:8 | re-export | — | — |

### optimizer (`pipeline/agents/optimizer/`)

| Function/Class | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `OptimizerConfig` | agent.py:35 | `@dataclass` | 환경 설정 | — |
| `_compute_recovery_distribution` | agent.py:48 | `(cases) -> dict` | Counter 결정론 산출 (결정 #20) | ✅ |
| `_compose_cold_start_row` | agent.py:61 | `(r, cases, run_id) -> dict` | cold_start row | — |
| `_compose_row` | agent.py:75 | `(r, cases, llm, run_id) -> dict` | 정상 row | — |
| `_call_azure_llm` | agent.py:91 | `(input, cfg, azure) -> dict` | gpt-5.1 호출 fail-fast | — |
| `optimize` | agent.py:106 | `async (forecast, selection, pre_cases, ...) -> list` | advice 생성 + PG insert | ✅ |
| `SYSTEM_PROMPT` | prompt.py:21 | str | 명령형 회피 tone | ✅ |
| `FEW_SHOT_MESSAGES` | prompt.py:61 | list[dict] | 3 pair | — |
| `build_llm_user_input` | prompt.py:286 | `(forecast_row, deg_cases) -> dict` | LLM input contract | ✅ |
| `_group_day_productivity` | retrieve.py:33 | `(metas, unit) -> float` | 그 날 평균 productivity | — |
| `_group_baseline` | retrieve.py:46 | `(metadatas, ...) -> Optional[float]` | 5종 incident 제외 baseline | ✅ |
| `fetch_degradation_cases` | retrieve.py:69 | `(metadatas, documents, ...) -> list[dict]` | 저하 top-N (incident 3종) | ✅ |
| `fetch_recovery_trajectory` | retrieve.py:117 | `(metadatas, ..., window=7) -> dict` | 회복 trajectory + recovery_days | — |
| `generate_fake_daily_report` | synthetic_daily_report.py:50 | `(report_date, scenarios, ...) -> list[Activity]` | Activity 직접 주입 (drift #3) | ✅ |
| `_parse_scenario` | synthetic_daily_report.py:118 | `(raw) -> dict` | CLI scenario 파싱 | — |
| `_load_baseline_inputs` | synthetic_daily_report.py:155 | `async (pg, scenarios, days=90) -> tuple` | PG → activity_pools + baseline | — |
| `build_demo_graph_config` | synthetic_daily_report.py:298 | `() -> GraphConfig` | 전체 demo graph config | — |
| `_main_cli` (synthetic_daily_report) | synthetic_daily_report.py:339 | `async () -> int` | Task 11 CLI E2E | — |
| `generate_synthetic_v2_group` | synthetic_v2.py:35 | `(company, l6_main, ..., days=90, seed=42) -> list[dict]` | state machine 7 룰 90일 | ✅ |
| `_main_cli` (synthetic_v2) | synthetic_v2.py:169 | `async () -> None` | 27 그룹 × 90일 Chroma upsert | — |
| `_build_reporter_config` ✦ | synthetic_daily_report.py:285 | `() -> ReporterConfig` | env injection (본 cycle 신규, `build_demo_graph_config` 확장) | — |

### reporter ✦ NEW (`pipeline/agents/reporter.py`)

| Function/Class | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `SYSTEM_PROMPT` | reporter.py:24 | str | 3 부 구조 마크다운 schema (작업 통합 / 진단 / 권고) + 한자 금지 + 들여쓰기 룰 | — |
| `ReporterConfig` | reporter.py:51 | `@dataclass` | Azure 크레덴셜 + LLM model + PG URL + timeout/retries | ✅ |
| `_build_llm_input` | reporter.py:62 | `(mapped, forecast_rows, optimizer_advice, today) -> dict[str, Any]` | LLM user message JSON 빌더 (4 키: date + activities + forecast + optimizer_advice) | ✅ |
| `_build_summary` | reporter.py:88 | `(mapped, forecast_rows, optimizer_advice) -> dict` | history_csv_row JSONB summary (total_workers + total_qty_by_trade + risk_counts + advice_count) | ✅ |
| `report` | reporter.py:114 | `async (mapped, forecast_rows, optimizer_advice, run_id, today, cfg) -> tuple[str, dict]` | 종합 보고서 생성 + PG INSERT (공개 API) | ✅ |

---

## 미구현 stub (별도 카드 없음 — `../architecture_overview.md` 참조)

| 파일 | 크기 | 상태 | drift backlog 우선순위 |
|---|---|---|---|
| `pipeline/agents/collector.py` | 0 byte | 미구현 (interface 자리만) | #5 |
| `pipeline/agents/reporter.py` | ✓ 161 LOC | 구현 완료 (2026-05-17). 본 cycle G8+G2 PG UPDATE 추가 적재 path 는 graph.reporter_node 안 | [reporter 카드](./design_intent_reporter.md) |
| `pipeline/main.py` | 0 byte | CLI entry 미구현 | D-7 |
| `pipeline/api.py` | 0 byte | FastAPI 미구현 | D-7 |

---

## 검색 가이드

**함수 이름으로 빠르게 찾기**: 위 T1 표에서 ctrl+F.

**키워드별 진입점**:
- "HIL 1" / "mapping_corrections" / "requires_review" → orchestration + mapper + persistence
- "assessment" / "정상 bias" → forecaster (`classify_assessment` 진입)
- "synthetic" / "productivity_ratio" → optimizer (`generate_fake_daily_report`) + forecaster (`generate_synthetic_day`)
- "interrupt" / "Command(resume=" → orchestration (`hil_2_node`)
- "recovery_distribution" → optimizer (`_compute_recovery_distribution`)
- "Chroma" / "wbs_master" / "daily_activities" → persistence (`ChromaClient`) + mapper (검색) + atomizer (적재) + forecaster (RAG)
- "Plan fetch" / "fetch_l6_plan_mh_map" → persistence + mapper
- "한자" → 모든 서브시스템 (검수 0건 확인)

**audit drift 매핑** (2026-05-17 cycle 흡수 — 유지):
- #1 ✓ Reporter 구현 → `pipeline/agents/reporter.py` 161 LOC ([reporter 카드](./design_intent_reporter.md))
- #2 ✓ Forecaster assessment bias → root cause = #3 input over-산출 + #3 fix 로 자동 해소 (classify.py:34 PM 원안 v2 정합, 수정 X)
- #3 ✓ synthetic productivity_ratio bug → `optimizer.generate_fake_daily_report:78` n_activities 분배 정정 ([optimizer 카드 §2026-05-17 변경](./design_intent_optimizer.md))
- #4 ✓ HIL 1 구현 → `graph.hil_1_node` + `_build_review_needed` + `_apply_corrections` + `db.insert_mapping_correction` ([orchestration 카드 §2026-05-17 변경](./design_intent_orchestration.md))
- #5 ⚠ Collector → `pipeline/agents/collector.py` 0 byte + `pipeline/main.py` + `pipeline/api.py` (다음 cycle 권고)

**2026-05-19 cycle (FE↔BE 연결 + 6 BE 적재 보완) 흡수**:
- ✓ drift #2 (parser_job/equipment_allocations 항상 0) → `graph.mapper_node:121,127` 호출 추가 ([orchestration 카드 O-G24](./design_intent_orchestration.md))
- ✓ drift #1 (sites.hours_saved_cum / last_run_id 미적재) → `graph.reporter_node:434` G8 + G2 UPDATE + state.site_id 누락 fallback ([orchestration 카드 O-G8 / O-G2 / O-N6](./design_intent_orchestration.md), [reporter 카드 R-G8 / R-G2 / R-N7](./design_intent_reporter.md))
- ✓ G23 alternatives → `mapper._select_top_k_alternatives` + Chroma include "distances" + `insert_mapper_activities_batch` alternatives 컬럼 ([mapper 카드 M-G23-1/2/3](./design_intent_mapper.md), [persistence 카드 G23-1](./design_intent_persistence.md))
- ✓ atomizer/forecaster None work_content / conditions 가드 hotfix ([atomizer 카드 A-N1/A-N2](./design_intent_atomizer.md), [forecaster 카드 F-N1/F-N2](./design_intent_forecaster.md))
- ✓ Prod cycle 1회 완주 검증 (run_id=627e2c4d, 2026-05-19): G5=4 / G8 매치 / G2=7.67h / G19=6/6 / G23 alt=6/6 / G24 job=15 / forecasts=4 / daily_reports=1

**신규 drift 매핑** (defer):
- #N1 RAG fixture_prod vs synthetic_v2 분포 ±10% mismatch → `optimizer/test_synthetic_daily_report_fixture.py::test_fixture_rag_alignment` xfail strict=False
- #N2 / #N3 (mapping_corrections / daily_reports schema migration) — 2026-05-17 PM cycle 흡수 완료
- #N4 시뮬 2/3/4 추가 검증 → 별 cycle
- #N5 LangGraph Command(resume=dict) int key TypeError → `orchestration.hil_1_node` 가 int(k) 변환 처리
- #N6 .env.local 경로 spec 명시 어긋남 → 실 root /.env.local (cosmetic 정정 별 cycle)
- #N7 synthetic_daily_report main_cli final report_md 미 print → 가독성 개선 별 cycle
- Backlog (본 cycle 식별, 다음 cycle): G7 monthly_trend 산식, Exporter xlsx 출력, reporter→exporter rename, deriveBaseline 단위 정합, score 음수 clamping
