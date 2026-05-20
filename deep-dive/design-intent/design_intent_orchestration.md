# Design Intent — orchestration (graph + state + checkpointer + constants)

- **Generated**: 2026-05-20 (HIL bypass + 정규화 타이밍 + HIL2 auto-select 3 hotfix cycle)
- **Git SHA**: `ef7c6cd` (A_Track HEAD, branch A_Track)
- **Pair file**: `../architecture_overview.md` (deep-dive 라이트 산출)
- **Range**:
  - `pipeline/graph.py` (563 LOC, 이전 ~500 → +63)
  - `pipeline/state.py` (303 LOC)
  - `pipeline/checkpointer.py` (94 LOC, persistence 페어 카드도 참조)
  - `pipeline/constants.py` (5 LOC)
  - `pipeline/tests/test_graph_e2e*.py` (3 파일) + `test_graph_hil1.py` + `test_state.py` + `test_stubs_e2e.py`
- **스펙**:
  - `docs/superpowers/specs/2026-05-14-cpia-2인-langgraph-협업-design.md`
  - `docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md`

LangGraph StateGraph 조립 + 공유 상태 스키마 + HIL interrupt/resume + checkpoint. **7 node + 2 helper + 2 builder + 2 interrupt point**. 본 cycle 3 hotfix — (1) `normalize_company` import (cf2a791, #31 close), (2) 정규화 타이밍 (e163e1a, fetch_bp_candidates 전 일괄 정규화 — ㈜/(주) prefix cand_pool 빈 버그), (3) full cycle (844d4c3 — `CPIA_HIL_AUTO_BYPASS` env + `pipeline_runs` 사전 INSERT + HIL2 auto-select).

---

## T1 — Function Index

### graph.py (563 LOC) — Node 함수 + 빌더 + helper

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `GraphConfig` | graph.py:39 | `@dataclass` | 4 sub-config 묶음 + reporter | — |
| `mapper_node` | graph.py:48 | `async (state, cfg) -> dict` | Parser → WBS 매핑 + Semaphore 4 + BP cand_pool batch + 정규화 2회 + G24 호출 + 5 PG INSERT | ✅ |
| `_build_review_needed` | graph.py:168 | `(mapped) -> list[dict]` | requires_review=True 행 9 필드 extraction | ✅ |
| `_apply_corrections` | graph.py:189 | `(mapped, corrections: dict[int, dict]) -> list[Activity]` | corrections 적용 + mapping_source="user_corrected" + requires_review=False 강제 | ✅ |
| `hil_1_node` | graph.py:224 | `async (state, cfg) -> dict` | Mapper interrupt + `CPIA_HIL_AUTO_BYPASS` env 우회 + PG mapping_corrections INSERT | ✅ |
| `atomizer_node` | graph.py:292 | `async (state, cfg) -> dict` | Chroma daily_activities 적재 + ID 반환 | ✅ |
| `forecaster_node` | graph.py:299 | `async (state, cfg) -> dict` | 그룹별 진단 (RAG + Plan fallback) | ✅ |
| `hil_2_node` | graph.py:306 | `async (state, cfg) -> dict` | risky 그룹 사전 영속 + F5/F7 정정 + interrupt | ✅ |
| `optimizer_node` | graph.py:415 | `async (state, cfg) -> dict` | Selected group advice + view_builder + PG insert | ✅ |
| `reporter_node` | graph.py:435 | `async (state, cfg) -> dict` | 종합 보고서 + G8 sites.last_run_id + G2 hours_saved_cum + state.site_id PG fallback | ✅ |
| `build_demo_graph` | graph.py:476 | `(cfg) -> CompiledGraph` | forecaster → hil_2 → (optimizer\|reporter) → END (Parser/Mapper/Atomizer skip) | ✅ |
| `build_graph` | graph.py:514 | `(cfg) -> CompiledGraph` | mapper → hil_1 → atomizer → forecaster → hil_2 → (optimizer\|reporter) → END | ✅ |

### state.py (303 LOC) — TypedDict 9개

| TypedDict | File:Line | 역할 | T2? |
|---|---|---|---|
| `TimeShiftCounts` | state.py:17 | 6 시간대 분포 (morning/daytime/overtime/night/all_night/total) | — |
| `Activity` | state.py:32 | 작업일보 시트4 매핑 단위 (44 필드, 본 cycle 16개 신규) | ✅ |
| `BPSummary` | state.py:96 | 시트1 BP사×공종×Zone×Scope (20 필드) | — |
| `JobAllocation` | state.py:122 | 시트2 BP사×직종×시간대 (10 필드) | — |
| `EquipmentAllocation` | state.py:146 | 시트3 BP사×장비×시간대 (10 필드) | — |
| `WorkerOutput` | state.py:170 | 시트6 개별 작업자 (12 필드, 업체별만) | — |
| `ReportMeta` | state.py:193 | Cover (9 필드, 업체별만) | — |
| `ParsedDailyReport` | state.py:207 | 1 xlsx 통합 (8 필드) | — |
| `CPIAState` | state.py:226 | LangGraph 전체 상태 (16 필드) | ✅ |

### constants.py (5 LOC)

- AGENT 7 종 이름 상수 (collector / parser / mapper / atomizer / forecaster / optimizer / reporter).

---

## T2 — Issue Cards

### `mapper_node` — Parser → WBS 매핑 + 병렬화 + 정규화 2회

- **위치**: `pipeline/graph.py:48-165` (118 LOC)
- **시그니처**: `async def mapper_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - git log:
    - `cf2a791 fix(graph): import normalize_company — close #31`
    - `e163e1a fix(graph,scripts): POC 3사 + 정규화 타이밍 버그`
    - `844d4c3 fix(graph,cycle): full cycle 진행 — HIL bypass + pipeline_runs + HIL2 auto-select`
    - 이전 `03ebc3d perf(mapper): graph mapper_node 병렬화 + BP cand_pool batch fetch`
  - 주석 (graph.py:49~59):
    - "Parser 결과 + Parser/Mapper 산출 PG 영속."
    - "BP cand_pool 미리 batch fetch (1 PG connection × N BP) → map_activity 안의 매 활동마다 새 PG connection 폭발 회피"
    - "asyncio.gather + Semaphore(`CPIA_MAPPER_CONCURRENCY`, 기본 4) 로 묶어 Azure rate-limit 회피"
  - **정규화 타이밍 fix (e163e1a)**: fetch_bp_candidates 가 정확 일치 SQL → ㈜/(주) prefix 남아있으면 cand_pool 빔 → conf=0.1
- **설계 의도**:
  - 병렬화 성능: 79 row → Semaphore(4) → Azure rate-limit 회피 + PG cand_pool batch (1 connection × N company)
  - **정규화 2회**:
    1. graph.py:67~68 — fetch_bp_candidates 전 일괄 정규화 (parsed.activities)
    2. graph.py:145 — mapped 일괄 (방어 중복)
  - PG 영속 5건 (G24 호출 추가):
    - `insert_parser_report`
    - `insert_parser_activities_batch`
    - `insert_parser_job_allocations_batch` (G24, 이전 호출 누락 row=0)
    - `insert_parser_equipment_allocations_batch` (G24, 이전 호출 누락 row=0)
    - `insert_mapper_activities_batch` (33 컬럼 + alternatives)
- **대응 패턴**:
  - 입력: state["parsed"] (ParsedDailyReport)
  - 처리:
    - graph.py:67~68 — 정규화 1 (parsed.activities)
    - graph.py:74~79 — unique_companies batch fetch_bp_candidates
    - graph.py:82~93 — Semaphore + `asyncio.gather(map_activity, ...)`
    - graph.py:145 — 정규화 2 (mapped)
    - graph.py:108~152 — PG 영속 5건
  - 출력: `{"mapped": list[Activity], "current_node": "mapper"}`
- **관련**:
  - 호출자: build_graph mapper → hil_1
  - 페어: mapper.py `map_activity` (mapper.py:341)
  - 테스트: `test_graph_e2e.py` (line 96~)
- **Suspected related** (2026-05-20):
  - mapper.py `resolve_wa` step 1 — BP-zone deterministic 정확도 의존
  - parser_post.py `normalize_company` — graph.py:23 import
  - db.py 의 5 batch INSERT 함수

---

### `hil_1_node` — Mapper 검토 interrupt + AUTO_BYPASS env

- **위치**: `pipeline/graph.py:224-289` (66 LOC)
- **시그니처**: `async def hil_1_node(state: CPIAState, cfg) -> dict`
- **이슈**:
  - git log:
    - `1bb78fb feat(hil_1): Mapper 결과 사람 검토 + PG mapping_corrections 영속`
    - `844d4c3 fix(graph,cycle): full cycle 진행 — HIL bypass` (2026-05-20)
  - 주석 (graph.py:225~232):
    - "Mapper 결과 사람 검토. requires_review=True가 1건 이상이면 interrupt"
    - "cfg = GraphConfig (cfg=None 이면 PG insert skip — unit 테스트 path)"
    - "env CPIA_HIL_AUTO_BYPASS={1|true|on} → review_needed 가 있어도 interrupt 건너뛰고 빈 corrections 로 통과 (dev/검증 모드 — atomizer/forecaster 진행 위해)"
- **설계 의도**:
  - interrupt pattern (spec §5.1):
    - `interrupt({"review_needed": review_needed})` → 외부 user/PM input
    - `Command(resume=corrections)` → corrections_raw = {} 안전 처리
    - corrections key (int) ← str 변환 (LangGraph Command resume key int → str 룰, issue #N5)
  - **AUTO_BYPASS env (844d4c3)**: cycle1~4 의 interrupt 무한 루프 (resume={} → re-raise) 해결 — dev/검증 path
  - PG insert 조건: `cfg is not None and corrections` (Unit test + AUTO_BYPASS 시 PG INSERT skip)
- **대응 패턴**:
  - 입력: state["mapped"]
  - 처리:
    - `_build_review_needed` (graph.py:168) — requires_review=True 9 필드 추출
    - AUTO_BYPASS 체크 (graph.py:238~246)
    - `interrupt(...)` → `Command(resume=...)`
    - `_apply_corrections` (graph.py:189) — corrections 적용
    - `cfg.pg.insert_mapping_correction` 반복 (corrections per row)
  - 출력: `{"mapped": [...corrected], "hil_1_corrections": corrections, "current_node": "hil_1"}`
- **관련**:
  - 호출자: build_graph mapper → hil_1 → atomizer
  - 테스트: `test_graph_hil1.py`, `test_graph_e2e_hil1.py`
  - PG: `insert_mapping_correction` (db.py:370)
- **Suspected related** (2026-05-20):
  - `_build_review_needed` (graph.py:168) — interrupt payload 빌드
  - `_apply_corrections` (graph.py:189) — corrections 적용

---

### `hil_2_node` — risky 그룹 사전 영속 + F5/F7 정정 + interrupt

- **위치**: `pipeline/graph.py:306-412` (107 LOC)
- **시그니처**: `async def hil_2_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - 주석 (graph.py:307~318):
    - "Forecaster 직후 — risky (주의/이상) 그룹별 degradation + recovery 사전 영속 + interrupt"
    - "Spec §8.2 (F5 정정 — coll.get 1회 + F7 정정 — None 분기)"
    - "retrieve.fetch_* 호출은 본 노드 책임 (agent.py 는 import X — 결정 #8 / Task 6 test 6.5)"
    - "Chroma coll.get(...) 그룹당 1회만 호출 후 metadatas/documents 두 함수 (degradation/recovery) 에 전달 (round-trip 절감)"
    - "baseline None 또는 main_unit None 일 때 cold_start signal payload 박고 다음 그룹"
- **설계 의도**:
  - F5 정정: Chroma `coll.get()` 그룹당 1회만 호출 → metadatas + documents 를 `fetch_degradation_cases` + `fetch_recovery_trajectory` 두 함수에 전달 (round-trip 절감)
  - F7 정정 (graph.py:358~371): baseline_value=None → `pre_cases[key]=[]` + cold_start_no_baseline signal payload
  - resume payload: `Command(resume=[group_key, ...])` — selection list 직접
  - risky 0건 → interrupt 미발생, empty selection 반환 → conditional_edge 가 reporter 분기
  - **844d4c3 HIL2 auto-select**: `scripts/run_one_cycle.py` 에서 risky_groups 모든 key 를 selection 으로 채움
- **대응 패턴**:
  - 입력: state["forecast"] (risky 분류 포함)
  - 처리:
    - risky 그룹 iterate
    - Chroma `coll.get()` 1회 호출 (F5)
    - `_group_baseline` → None 분기 (F7) → cold_start payload
    - `fetch_degradation_cases` + `fetch_recovery_trajectory` (각 case 마다)
    - `pre_cases[key] = [...]`
    - `interrupt({"risky_groups": [{key, preview_cases, ...}]})` → `selected = ... or []`
  - 출력: `{"hil_2_selection": [keys], "pre_optimizer_cases": dict, "current_node": "hil_2"}`
- **관련**:
  - 호출자: build_graph forecaster → hil_2 → (optimizer | reporter)
  - 페어: retrieve.py `fetch_degradation_cases` + `fetch_recovery_trajectory`
  - 테스트: `test_graph_e2e_hil2.py` 4 path (interrupt_payload / resume_optimizer / skip_no_risky / resume_empty_selection)
- **Suspected related** (2026-05-20):
  - optimizer/agent.py `optimize` — `pre_optimizer_cases` 재활용 (결정 #8)
  - run_one_cycle.py — HIL2 auto-select 로직

---

### `reporter_node` — 종합 보고서 + G8/G2 + site_id PG fallback

- **위치**: `pipeline/graph.py:435-473` (39 LOC)
- **시그니처**: `async def reporter_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - git log: `22d44c2 feat(reporter): Mapper+Forecaster+Optimizer 종합 보고서 + PG daily_reports`
  - 주석 (graph.py:436~450):
    - "Mapper + Forecaster + Optimizer 결과 종합 보고서 생성 + PG INSERT"
    - "hil_2_selection=[] (Optimizer skip) 또는 risky 0건 path 에서도 본 노드 진입"
    - "mapped empty → fallback MD + PG INSERT skip"
- **설계 의도**:
  - 최종 노드 — 모든 cycle 종료 (build_graph + build_demo_graph 둘 다)
  - **G8 sites.last_run_id 갱신** + **G2 hours_saved_cum 누적** ((120-5)/60 × atomized_count 시간)
  - **state.site_id PG fallback** (graph.py:458~462): state.site_id 없으면 pipeline_runs 에서 fetch
- **대응 패턴**:
  - 입력: state["mapped"] + state["forecast"] + state["optimizer_advice"]
  - 처리:
    - reporter.py `report()` → report_md + summary
    - PG: `insert_daily_report` (db.py:405)
    - site_id PG fallback (state.get("site_id") 없으면 `SELECT site_id FROM pipeline_runs WHERE run_id=$1`)
    - `update_site_last_run` (G8) + `update_site_hours_saved_cum` (G2, atomized_count 기반)
  - 출력: `{"report_md": "...", "current_node": "reporter", "status": "completed"}`
- **관련**:
  - 호출자: optimizer | hil_2 → reporter → END
  - 페어: reporter.py `report`
  - PG: db.py `insert_daily_report` / `update_site_last_run` / `update_site_hours_saved_cum`
- **Suspected related** (2026-05-19):
  - optimizer.view_builder — daily_reports JSONB view 8개 사전 적재
  - db.py `upsert_daily_report_view_col` — view jsonb 적재 페어

---

### `optimizer_node` — Selected group advice (selection 비어있으면 skip)

- **위치**: `pipeline/graph.py:415-433` (19 LOC)
- **시그니처**: `async def optimizer_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - 결정 #8 (spec): retrieve 책임은 hil_2_node, optimize 는 LLM 만
- **설계 의도**:
  - conditional_edge 가 hil_2_selection 비어있으면 reporter 직진 → 본 노드 진입 자체 X
  - 진입 시 pre_optimizer_cases 재활용 (retrieve 재호출 X)
- **대응 패턴**:
  - 입력: state["forecast"] + state["hil_2_selection"] + state["pre_optimizer_cases"]
  - 처리: optimizer.agent `optimize()` 호출
  - 출력: `{"optimizer_advice": [...], "current_node": "optimizer"}`
- **관련**:
  - 호출자: build_graph hil_2 → optimizer (conditional)
  - 페어: optimizer/agent.py `optimize`
- **Suspected related**:
  - hil_2_node — pre_optimizer_cases 의 source

---

### `forecaster_node` — RAG + Plan fallback 진단

- **위치**: `pipeline/graph.py:299-304` (6 LOC)
- **시그니처**: `async def forecaster_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **설계 의도**:
  - 그룹별 (company, l6_main) 생산성 진단
  - RAG (Chroma daily_activities) 우선, 부족 시 Plan fallback (PG forecasts)
- **대응 패턴**:
  - 입력: state["mapped"] (atomizer 결과 idempotent)
  - 처리: forecaster.agent `forecast()` 호출
  - 출력: `{"forecast": [...], "current_node": "forecaster"}`
- **관련**:
  - 호출자: build_graph atomizer → forecaster → hil_2
- **Suspected related**:
  - hil_2_node — risky 분류 input

---

### `atomizer_node` — Chroma daily_activities INSERT + ID 반환

- **위치**: `pipeline/graph.py:292-297` (6 LOC)
- **시그니처**: `async def atomizer_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **설계 의도**:
  - 임베딩만 (LLM 호출 X)
  - 멱등성 dedupe — deterministic hash (결정 #N3 cycle drift 기록, 본 cycle 정상)
- **대응 패턴**:
  - 출력: `{"atomized_ids": [...], "current_node": "atomizer"}`
- **관련**:
  - 호출자: build_graph hil_1 → atomizer → forecaster
- **Suspected related**:
  - reporter_node — atomized_count 기반 G2 산식

---

### `build_graph` — production topology

- **위치**: `pipeline/graph.py:514-562` (49 LOC)
- **시그니처**: `def build_graph(cfg: GraphConfig) -> CompiledGraph`
- **이슈**:
  - 신규 노드 추가 (hil_1 + reporter)
  - conditional_edges (hil_2 → optimizer | reporter)
- **설계 의도**:
  - **topology**:
    ```
    START → mapper → hil_1 → atomizer → forecaster → hil_2
      → (optimizer | reporter)
      → reporter → END
    ```
  - conditional_edge (graph.py:556~560):
    ```python
    lambda s: "optimizer" if s.get("hil_2_selection") else "reporter"
    ```
- **대응 패턴**:
  - 입력: cfg (GraphConfig)
  - 처리: StateGraph add_node × 7 + add_edge × 6 + add_conditional_edges × 1 → compile
  - 출력: CompiledGraph (checkpointer 포함)
- **관련**:
  - 호출자: scripts/run_one_cycle.py, FastAPI api.py
  - 페어: `build_demo_graph` (graph.py:476)
- **Suspected related**:
  - 모든 7 node 함수

---

### `build_demo_graph` — Parser/Mapper/Atomizer skip (synthetic CLI 용)

- **위치**: `pipeline/graph.py:476-512` (37 LOC)
- **시그니처**: `def build_demo_graph(cfg: GraphConfig) -> CompiledGraph`
- **설계 의도**:
  - topology: `forecaster → hil_2 → (optimizer | reporter) → END`
  - state["mapped"] 사전 주입 가정 (synthetic_daily_report.py CLI 또는 test fixture)
  - 데모/PoC 빠른 시연 path
- **대응 패턴**:
  - 출력: CompiledGraph (3 노드만)
- **관련**:
  - 호출자: `synthetic_daily_report.py` CLI
  - 페어: `build_graph` (production)
- **Suspected related**:
  - optimizer/synthetic_daily_report.py — 본 함수의 유일한 호출자 (test 외)

---

### `_build_review_needed` — interrupt payload 9 필드

- **위치**: `pipeline/graph.py:168-187` (20 LOC)
- **시그니처**: `def _build_review_needed(mapped: list[Activity]) -> list[dict]`
- **설계 의도**:
  - requires_review=True 행 만 9 필드 (idx, work_content, company, trade, wa, l6_main, mapping_conf, mapping_source, ...) extraction
  - FE review modal 의 input 최소화 (Activity 44 필드 중 9개만)
- **대응 패턴**:
  - 입력: mapped (Activity list)
  - 처리: filter (requires_review=True) → 9 필드 dict 변환
  - 출력: list[dict]
- **관련**:
  - 호출자: hil_1_node (graph.py:224)
- **Suspected related**:
  - `_apply_corrections` — 본 함수와 페어

---

### `_apply_corrections` — corrections 적용 + metadata 갱신

- **위치**: `pipeline/graph.py:189-222` (34 LOC)
- **시그니처**: `def _apply_corrections(mapped: list[Activity], corrections: dict[int, dict]) -> list[Activity]`
- **설계 의도**:
  - HIL 1 corrections 적용 — mapping_source="user_corrected" + requires_review=False 강제
  - 답 안 한 row 는 Mapper 추천 그대로 수용
- **대응 패턴**:
  - 입력: mapped + corrections (dict[int, dict])
  - 처리: iterate corrections → Activity 의 wa/l6_main/source/review 갱신
  - 출력: list[Activity]
- **관련**:
  - 호출자: hil_1_node
- **Suspected related**:
  - `_build_review_needed` — 본 함수의 input 원천

---

### `CPIAState` — LangGraph 전체 상태 (16 필드)

- **위치**: `pipeline/state.py:226-259` (34 LOC)
- **시그니처**: `class CPIAState(TypedDict)`
- **이슈**:
  - state.py 137 → 303 LOC (Activity 16 필드 신규 + TimeShiftCounts 등)
- **설계 의도**:
  - **입력**: run_id, date, input_files, site_id (PG fallback 용)
  - **누적**: raw_texts, parsed, mapped, hil_1_corrections, atomized_ids
  - **분기**: report_md, forecast, hil_2_selection, pre_optimizer_cases, optimizer_advice
  - **상태 추적**: current_node, status ∈ {running, waiting_hil_1, waiting_hil_2, completed, failed}
- **관련**:
  - 모든 노드의 입출력
  - PostgresSaver thread_id 영속 (checkpointer)
- **Suspected related**:
  - `Activity` (state.py:32) — mapped/parsed 의 element type
  - `ParsedDailyReport` — parsed 필드 타입

---

### `Activity` — 작업일보 시트4 매핑 단위 (44 필드)

- **위치**: `pipeline/state.py:32-94` (63 LOC)
- **이슈**:
  - 2026-05-19 cycle 16 신규 필드: zone, bp_code, scope, yesterday_cum_qty, today_cum_qty, progress_percent, remaining_qty, remaining_percent, note, work_location_code, wbs_mid_name, wbs_sub_name, wbs_detail_name 등
  - PoC 제약 (issue #N11): wbs_activity_id / l7_sub / l7_5_activity / sub_work_area 항상 None (Master List 1:N)
- **설계 의도**:
  - 시트4 원천 필드 (Parser 채움) + WBS 매핑 (Mapper) + 분배 결과 (`_prorate_mh`) + HIL 1 플래그
- **관련**:
  - 모든 노드 통과 (mapper → atomizer → forecaster → optimizer)
- **Suspected related**:
  - mapper.py `map_activity` — wa/l6_main/conf/source/review 채움
  - mapper.py `_prorate_mh` — assigned_workers/plan_mh/cum_actual_mh_today 채움

---

## 변경 사항 정리 (cf3c143..HEAD, orchestration 3 hotfix)

| Commit | 날짜 | 메시지 | 파일 | 주요 변경 |
|---|---|---|---|---|
| cf2a791 | 2026-05-19 | fix(graph): import normalize_company — close #31 | graph.py | line 23: `from pipeline.agents.parser_post import normalize_company` |
| e163e1a | 2026-05-19 | fix(graph,scripts): POC 3사 + 정규화 타이밍 버그 | graph.py | line 67~68: fetch_bp_candidates 전 정규화 추가 |
| 844d4c3 | 2026-05-20 | fix(graph,cycle): full cycle 진행 — HIL bypass + pipeline_runs + HIL2 auto-select | graph.py | line 238~246: CPIA_HIL_AUTO_BYPASS env 추가 |
| ef7c6cd | 2026-05-20 | (반영) reporter_node 의 PG 처리 강화 | (db.py 직접) | site_id PG fallback graph.py:458~462 흡수됨 |

## Full cycle 5 검증 (844d4c3 commit msg)

| 항목 | 측정 | 상태 |
|---|---|---|
| mapper_activities | 146 row, mapping_source `auto_bp_zone_match` 74% / hil 1.4% | ✅ |
| atomized_ids | 64 | ✅ |
| forecasts | 27 | ✅ |
| optimizer_advice | 13 (risky 12 → 13 keys auto-select) | ✅ |
| daily_reports JSONB 6/9 (contractor_bars / trade_bars / s_curve / scenarios / optimizer_view / productivity) | 채워짐 | ✅ |
| daily_reports JSONB 3/9 (kpi / wp_summary / quadrant) | 빈 dict | ❌ Phase 2 |
| Schema validation | bp_code 100% / yesterday_cum_qty 100% / today_cum_qty 100% / plan_mh 100% / cum_actual_mh_today 99% / assigned_workers 95% / zone 16% | partial |

## POC 데이터셋 변경 (e163e1a)

| Before | After | activity_master rows |
|---|---|---|
| 4 BP사 | 3 BP사 (에스티엠 제거 — 0 row 불안정) | |
| | 남웅건설 | 179 |
| | 세보엠이씨 | 561 |
| | 창원기전 | 319 |

## 미해결 / Backlog

- `daily_reports.kpi_jsonb` / `wp_summary_jsonb` / `quadrant_jsonb` view_builder gap (issue #N4) — Phase 2
- `LangGraph Command(resume=dict)` key int → str 변환 룰 명문화 미흡 (issue #N5)
- PoC 제약: `Activity.wbs_activity_id` / `l7_sub` / `l7_5_activity` / `sub_work_area` 항상 None (issue #N11)
- Reporter LLM 모델 (Azure gpt-5.1 고비용) — 후속 plan 저비용 모델 전환 검토
- HIL 1 PG INSERT: cfg=None + corrections={} 시 skip 정상 동작 (이전 cycle "mapping_corrections row count 0" 문제 해소)
