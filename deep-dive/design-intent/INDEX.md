# CPIA design-intent — Master INDEX

- **Generated**: 2026-05-17
- **Git SHA**: `f9a695f5315eba97b2686f55a72bc91ef6cae6b2` (A_Track)
- **Scope**: pipeline 전체 (agents 7개 + graph + state + db) — Web/B_Track 제외
- **Pair**: `../architecture_overview.md` (deep-dive 라이트)

코드 변경/추가 작업 진입 시 아래 T1 인덱스에서 **함수 이름 / 키워드 / 파일** grep → 매칭 시 해당 서브시스템 `design_intent_<X>.md` 의 T2 카드 확인 → 기존 핸들러 확장 vs 새 설계 판단.

---

## 서브시스템 7개

| 서브시스템 | 파일 | T1 | T2 | 핵심 책임 | 미해결 핵심 |
|---|---|---:|---:|---|---|
| orchestration | [design_intent_orchestration.md](./design_intent_orchestration.md) | 16 | 9 | LangGraph StateGraph + HIL interrupt/resume + checkpoint | HIL 1 미구현 (필드만), Reporter cycle 시 PostgresSaver 전환 |
| persistence | [design_intent_persistence.md](./design_intent_persistence.md) | 16 | 9 | PG asyncpg pool (7 테이블) + Chroma HTTP (2 컬렉션) | `mapping_corrections` dead schema, `fetch_activity` 미사용 의심 |
| parser | [design_intent_parser.md](./design_intent_parser.md) | 12 | 11 | xlsx → 4시트 (BPSummary/JobAllocation/EquipmentAllocation/Activity) | Collector (0 byte) 자리 비어있음 |
| mapper | [design_intent_mapper.md](./design_intent_mapper.md) | 9 | 9 | 6단계 매핑 (BP filter → Embed → Chroma → LLM → WA 4단계) | HIL 1 자리 비어있음, WA 3단계 (시트1 자연어) TODO |
| atomizer | [design_intent_atomizer.md](./design_intent_atomizer.md) | 4 | 4 | Chroma daily_activities 적재 + fail-fast PG | `embedding_dim` 필드 미사용 의심 |
| forecaster | [design_intent_forecaster.md](./design_intent_forecaster.md) | ~17 | 13 | RAG 우선 + Plan fallback 진단 (assessment + risk_level) | **audit drift #2** (assessment bias) — 임계값 회귀 권고 |
| optimizer | [design_intent_optimizer.md](./design_intent_optimizer.md) | ~22 | 7 | LLM 조언 + 결정론 recovery_distribution + synthetic fixture | **audit drift #3** (synthetic_daily_report productivity_ratio bug), D-1 (병행작업 룰) |

**합계**: T1 ≈ 96 public 함수/클래스 / T2 = 62 이슈 카드. T2 ≥ 2 점수 통과 함수는 거의 모든 핵심 로직을 커버 (테스트 + git log + 주석 다중 source).

---

## T1 — 전 서브시스템 함수 인덱스

### orchestration (`pipeline/graph.py` / `state.py` / `checkpointer.py` / `constants.py`)

| Function/Class | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `GraphConfig` | graph.py:33 | `@dataclass` | 4 sub-config 묶음 | — |
| `mapper_node` | graph.py:40 | `async (state, cfg) -> dict` | Parser → WBS 매핑 + `_prorate_mh` | ✅ |
| `atomizer_node` | graph.py:57 | `async (state, cfg) -> dict` | Chroma daily_activities 적재 | ✅ |
| `forecaster_node` | graph.py:64 | `async (state, cfg) -> dict` | 그룹별 생산성 진단 | ✅ |
| `hil_2_node` | graph.py:71 | `async (state, cfg) -> dict` | risky 그룹 사전 영속 + interrupt | ✅ |
| `optimizer_node` | graph.py:180 | `async (state, cfg) -> dict` | Selected group advice + PG insert | ✅ |
| `build_graph` | graph.py:233 | `(cfg) -> CompiledGraph` | mapper→atomizer→forecaster→hil_2→[optimizer\|END] | ✅ |
| `build_demo_graph` | graph.py:200 | `(cfg) -> CompiledGraph` | forecaster→hil_2→optimizer (mapper/atomizer skip) | ✅ |
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
| `MapperConfig` | mapper.py:191 | `@dataclass` | Azure/PG/Chroma + threshold 0.7 | ✅ |
| `map_activity` | mapper.py:208 | `async (activity, parsed, cfg) -> Activity` | 6단계 통합 (공개 API) | ✅ |
| `_prorate_mh` | mapper.py:347 | `async (mapped, parsed, pg) -> list[Activity]` | 인원 비례 분배 | ✅ |

### atomizer (`pipeline/agents/atomizer.py`)

| Function/Class | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `AtomizerConfig` | atomizer.py:24 | `@dataclass` | Azure + Chroma + batch/timeout/dim | ✅ |
| `_make_doc_id` | atomizer.py:39 | `(date, company, l6_main, work_content) -> str` | SHA256 16자 결정성 ID | ✅ |
| `_build_metadata` | atomizer.py:45 | `(a, date, run_id) -> dict` | 12 필드 평탄화 metadata | ✅ |
| `atomize` | atomizer.py:62 | `async (mapped, parsed_report, run_id, cfg) -> list[str]` | Chroma upsert (공개 API) | ✅ |

### forecaster (`pipeline/agents/forecaster/`)

| Function/Class | File:Line | Signature | One-line role | T2 |
|---|---|---|---|---|
| `ForecasterConfig` | agent.py:35 | `@dataclass` | 환경 설정 | — |
| `_format_chroma_result` | agent.py:53 | `(rag_result) -> list[dict]` | Chroma → rerank input | — |
| `_forecast_one_group` | agent.py:67 | `async (...) -> dict` | 8단계 진단 | ✅ |
| `forecast` | agent.py:229 | `async (mapped, run_id, today, cfg) -> list[dict]` | 그룹 fan-out + PG insert | ✅ |
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

---

## 미구현 stub (별도 카드 없음 — `../architecture_overview.md` 참조)

| 파일 | 크기 | 상태 | drift backlog 우선순위 |
|---|---|---|---|
| `pipeline/agents/collector.py` | 0 byte | 미구현 (interface 자리만) | #5 |
| `pipeline/agents/reporter.py` | 0 byte | 미구현 | #1 |
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

**audit drift 매핑**:
- #1 Reporter 구현 → `pipeline/agents/reporter.py` 0 byte
- #2 Forecaster assessment bias → `forecaster.classify_assessment` + `classify_assessment_rag/plan` 임계값
- #3 synthetic productivity_ratio bug → `optimizer.generate_fake_daily_report` + `_load_baseline_inputs`
- #4 HIL 1 구현 → `state.hil_1_corrections` + `mapper.requires_review` + `graph.build_graph` 노드 추가
- #5 Collector → `pipeline/agents/collector.py` 0 byte + `pipeline/main.py` + `pipeline/api.py`
