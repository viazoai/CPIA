# Design Intent — orchestration (graph + state + checkpointer + constants)

- **Generated**: 2026-05-17 (git SHA: f9a695f5315eba97b2686f55a72bc91ef6cae6b2, branch A_Track)
- **Pair file**: `../architecture_overview.md` (deep-dive 라이트 산출)
- **Range**: `pipeline/graph.py` (272) + `pipeline/state.py` (137) + `pipeline/checkpointer.py` (18) + `pipeline/constants.py` (5) — 합계 432 LOC

LangGraph StateGraph 조립 + 공유 상태 스키마 + HIL interrupt/resume + checkpoint. 노드 5개 + builder 2개 + checkpointer 1개. Phase 1 PoC 기준 HIL 2 만 완성, HIL 1 은 상태 필드만 있고 노드 미구현.

---

## T1 — Function Index

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `GraphConfig` | graph.py:33 | `@dataclass class GraphConfig` | Mapper/Atomizer/Forecaster/Optimizer 4 cfg 묶음 | — |
| `mapper_node` | graph.py:40 | `async (state: CPIAState, cfg: GraphConfig) -> dict` | Parser → WBS 매핑 + `_prorate_mh` 인원 분배 | ✅ |
| `atomizer_node` | graph.py:57 | `async (state, cfg) -> dict` | Mapped Activity → Chroma `daily_activities` 적재 | ✅ |
| `forecaster_node` | graph.py:64 | `async (state, cfg) -> dict` | Mapped + 유사 이력 → 생산성 진단 (risk_level) | ✅ |
| `hil_2_node` | graph.py:71 | `async (state, cfg) -> dict` | Risky 그룹 사전 영속 + `interrupt({"risky_groups": ...})` | ✅ |
| `optimizer_node` | graph.py:180 | `async (state, cfg) -> dict` | Selected group 별 advice row 생성 + PG insert | ✅ |
| `build_graph` | graph.py:233 | `(cfg: GraphConfig) -> CompiledGraph` | 본 graph (mapper→atomizer→forecaster→hil_2→[optimizer\|END]) | ✅ |
| `build_demo_graph` | graph.py:200 | `(cfg: GraphConfig) -> CompiledGraph` | 데모 graph (forecaster→hil_2→optimizer, mapper/atomizer skip) | ✅ |
| `Activity` | state.py:11 | `class Activity(TypedDict)` | 작업일보 1행 = 매핑 단위 | — |
| `BPSummary` | state.py:59 | `class BPSummary(TypedDict)` | 시트1 BP사 × 공종 row | — |
| `JobAllocation` | state.py:74 | `class JobAllocation(TypedDict)` | 시트2 BP사 × 직종 row | — |
| `EquipmentAllocation` | state.py:84 | `class EquipmentAllocation(TypedDict)` | 시트3 BP사 × 장비 row | — |
| `ParsedDailyReport` | state.py:95 | `class ParsedDailyReport(TypedDict)` | 1 작업일보 xlsx 4시트 통합 | — |
| `CPIAState` | state.py:106 | `class CPIAState(TypedDict)` | LangGraph 전체 상태 | ✅ |
| `build_checkpointer` | checkpointer.py:13 | `() -> InMemorySaver` | Phase 1 PoC checkpointer (InMemorySaver) | ✅ |
| `WORK_HOURS_PER_DAY` | constants.py:5 | `int = 8` | Pipeline-wide constant (8h/day) | — |

---

## T2 — Issue Cards

### `hil_2_node` — Forecaster 직후 risky 그룹 사전 영속 + interrupt

- **위치**: `pipeline/graph.py:71-177` (107 LOC, 8 분기)
- **시그니처**: `async def hil_2_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - git log `a0a7a82` (optimizer/Task 8): `checkpointer.py InMemorySaver + graph.py hil_2/optimizer node + conditional edge` — 최초 추가
  - git log `44ec63b` (optimizer/Task 9): `graph E2E hil_2 + Command(resume=) 4 path (slow)` — payload schema 검증 테스트 4개 추가
  - 함수 docstring (graph.py:71-83): "Spec §8.2 (F5 정정 — coll.get 1회 + F7 정정 — None 분기). 원칙: retrieve.fetch_* 호출은 본 노드 책임 (agent.py 는 import X — 결정 #8 / Task 6 test 6.5)."
  - 인라인 주석 `# F5: coll.get 1회 호출 후 두 함수에 metadatas/documents 전달` (line 115), `# F7: None 분기 명시` (line 124)
  - 메타: `docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §8.2` (F5/F7 정정)
  - `docs/audit/2026-05-17-cpia-e2e-audit-report.md:143` "graph.py:71 hil_2_node + graph.py:172 interrupt(...). 시뮬 1 raw §1.3 의 `[HIL-2 INTERRUPT] risky_groups: 2` 확인"
- **설계 의도**:
  - retrieve 책임 분리: `optimizer_node` 는 retrieve 재호출 금지, `hil_2_node` 가 사전에 `pre_optimizer_cases` 영속 (결정 #8). LangGraph checkpoint resume 시 Optimizer 단계가 결정론적이도록.
  - Chroma round-trip 절감: 그룹당 `coll.get(...)` 1회만 호출 후 metadatas/documents 를 degradation/recovery 두 함수에 전달 (F5).
  - cold_start 명시: `baseline_value is None` 또는 `main_unit is None` 일 때 `pre_cases[key]=[]` 박고 다음 그룹 (F7).
  - risky 0건 → `interrupt` 미발생, `empty selection` 반환 → conditional_edge 가 END 분기.
- **대응 패턴**:
  - 발동: `state["forecast"]` 에 `risk_level in {"주의", "이상"}` row 1건 이상
  - 입력: forecast list + cfg.optimizer
  - 처리: 그룹별 (`company`, `l6_main`) 묶음 → Chroma 1회 조회 → `fetch_degradation_cases` + `fetch_recovery_trajectory` → preview_cases ≥ 3 인 그룹만 `risky_groups` payload 에 포함 → `interrupt({"risky_groups": ...})`
  - 출력: `pre_optimizer_cases` + (resume 후) `hil_2_selection` + `current_node="hil_2"`
- **관련**:
  - 호출: `build_graph` (graph.py:251 add_node)
  - 호출 후 분기: conditional_edge (graph.py:266-270) — `hil_2_selection` 비어있으면 END, 있으면 `optimizer`
  - 테스트: `pipeline/tests/test_graph_e2e_hil2.py` (`test_graph_e2e_hil2_interrupt_payload:243` / `_resume_optimizer:296` / `_skip_no_risky:345` / `_resume_empty_selection:377`)
  - 상태 필드: `pre_optimizer_cases` (state.py:126), `hil_2_selection` (state.py:125)
- **Suspected related** (2026-05-17 stale):
  - `agents/forecaster/agent.py:_forecast_one_group` — risk_level 산출 책임 (`classify_risk_level`)
  - `agents/optimizer/retrieve.py:fetch_degradation_cases` / `fetch_recovery_trajectory` — hil_2_node 가 직접 호출
  - HIL 1 (Mapper interrupt) — 미구현. 같은 interrupt+Command(resume) 패턴 그대로 재사용 후보. drift backlog #4 참조.

---

### `optimizer_node` — Selected group 별 advice 생성 + PG insert

- **위치**: `pipeline/graph.py:180-197` (18 LOC)
- **시그니처**: `async def optimizer_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - git log `a0a7a82` (optimizer/Task 8) 최초 추가.
  - docstring (graph.py:180-184): "Optimizer — selected group 별 advice row 생성 + PG insert. retrieve 재호출 X. Spec §8.2 + §7. hil_2_node 가 사전 영속한 pre_optimizer_cases 만 소비."
  - 메타: `docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §7` (optimize() 스펙), §8.2 (retrieve 책임 분리).
- **설계 의도**:
  - 책임 단일화: retrieve 는 hil_2_node 에서 끝, optimizer_node 는 LLM 호출 + PG insert 만.
  - 결정론 보장: `_compute_recovery_distribution` 은 Counter 기반 deterministic 산출 (결정 #20), LLM 출력 override.
  - `hil_2_selection` 빈 리스트 → `optimizer_advice=[]` early return.
- **대응 패턴**:
  - 발동: `state["hil_2_selection"]` 비어있지 않음 (conditional edge 통과)
  - 입력: `pre_optimizer_cases[key]` (group_key in selection)
  - 처리: cold_start (cases<3) → LLM skip / 정상 → `optimize()` 호출
  - 출력: `optimizer_advice: list[dict]` + `current_node="optimizer"`
- **관련**:
  - `agents/optimizer/agent.py:optimize` — 실제 LLM 호출 + PG insert 함수
  - 테스트: `test_graph_e2e_hil2_resume_optimizer` (test_graph_e2e_hil2.py:296)
- **Suspected related** (2026-05-17 stale):
  - `db.py:insert_optimizer_advice` — 영속화 endpoint
  - JSONB falsy 보호 (`is not None` 패턴) — db.py:299-307

---

### `mapper_node` — Parser → WBS 매핑 + `_prorate_mh`

- **위치**: `pipeline/graph.py:40-54` (15 LOC)
- **시그니처**: `async def mapper_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - git log `8455dd1` (graph: Phase 1 StateGraph — mapper_node + atomizer_node 연결) 최초 추가.
  - git log `8e153b3` (graph: forecaster_node 통합) — docstring 제거 간결화.
  - 테스트: `pipeline/tests/test_graph_e2e.py:126 test_graph_e2e_namwong_47` — 47 row → 47 mapped activities, assigned_workers 88.0 prorated 검증.
- **설계 의도**:
  - 두 단계 분리: ① `map_activity` 매핑 호출 → ② `_prorate_mh` (BP사 단위 인원 비례 분배) PG 호출.
  - PG connection 생명주기 명시: `try/finally` 내에서 `pg.connect()` → `_prorate_mh()` → `pg.close()`.
- **대응 패턴**:
  - 발동: parser_node 완료, `state["parsed"]["activities"]` 존재
  - 입력: ParsedDailyReport + cfg.mapper
  - 처리: 각 activity 매핑 → BP 인원 분배
  - 출력: `mapped: list[Activity]` + `current_node="mapper"`
- **관련**:
  - `agents/mapper.py:map_activity` (mapper.py:208) — 6단계 매핑 함수
  - `agents/mapper.py:_prorate_mh` (mapper.py:347) — 인원 비례 분배
  - `db.py:fetch_l6_plan_mh_map` — N+1 회피 쿼리
- **Suspected related** (2026-05-17 stale):
  - HIL 1 자리 (mapper → hil_1 → atomizer). 현재는 mapper 직후 바로 atomizer.

---

### `atomizer_node` — Chroma daily_activities 적재

- **위치**: `pipeline/graph.py:57-61` (5 LOC)
- **시그니처**: `async def atomizer_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - git log `8455dd1` (graph: Phase 1 StateGraph) 최초 추가.
  - 테스트 `test_graph_e2e_namwong_47`: atomized_ids 11건 (남웅 47 row → dedup 11)
- **설계 의도**:
  - 단순 래퍼: `agents/atomizer.py:atomize` 호출 + `atomized_ids` 반환.
  - state 의 `parsed.report_date` 와 `run_id` 를 atomize 에 전달.
- **대응 패턴**:
  - 발동: mapper_node 완료, `state["mapped"]` 존재
  - 입력: mapped list + parsed (report_date 추출용) + cfg.atomizer
  - 처리: dedup + Azure embedding batch + Chroma upsert + PG `update_run_atomized_count`
  - 출력: `atomized_ids: list[str]` + `current_node="atomizer"`
- **관련**:
  - `agents/atomizer.py:atomize` (atomizer.py:62) — 본체
  - `db.py:assert_pipeline_run_exists` (db.py:127) — fail-fast 보호
- **Suspected related** (2026-05-17 stale): 없음.

---

### `forecaster_node` — 생산성 진단

- **위치**: `pipeline/graph.py:64-68` (5 LOC)
- **시그니처**: `async def forecaster_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - git log `8e153b3` (graph: forecaster_node 통합) 최초 추가.
  - git log `b9d0d80` (graph: date import alias — date shadowing 정리 권고 #6) — `_date.fromisoformat` 으로 변경.
  - 테스트 `test_graph_e2e_namwong_47`: forecast 1건 (남웅|철근콘크리트공사), `risk_level in {"정상","주의","이상",None}` 검증.
- **설계 의도**:
  - 단순 래퍼: `agents/forecaster/agent.py:forecast` 호출.
  - date import shadowing 회피 위해 `from datetime import date as _date` 별칭.
- **대응 패턴**:
  - 발동: atomizer_node 완료, `state["mapped"]` 존재
  - 입력: mapped list + run_id + today + cfg.forecaster
  - 처리: 그룹별 진단 (RAG 우선 + Plan fallback + cold_start)
  - 출력: `forecast: list[dict]` + `current_node="forecaster"`
- **관련**:
  - `agents/forecaster/agent.py:forecast` (agent.py:229) — entry
- **Suspected related** (2026-05-17 stale):
  - audit drift #2 (assessment "정상" bias) — `classify_assessment` 결정 path 추적 시 본 노드 출발.

---

### `build_graph` — StateGraph 조립 (mapper → atomizer → forecaster → hil_2 → [optimizer\|END])

- **위치**: `pipeline/graph.py:233-272` (40 LOC)
- **시그니처**: `def build_graph(cfg: GraphConfig) -> CompiledGraph`
- **이슈**:
  - git log `8455dd1` (Phase 1: mapper → atomizer → END) 최초.
  - git log `8e153b3` (forecaster 추가) — atomizer → forecaster.
  - git log `a0a7a82` (optimizer/Task 8) — hil_2 + optimizer + conditional_edge 추가.
  - docstring (graph.py:233-239): 5 단계 + conditional_edges 명시.
  - 테스트 `test_graph_e2e_namwong_47` — `risk_level in {"주의","이상"}` → `__interrupt__` 발생 확인, 아니면 END 분기 확인.
- **설계 의도**:
  - 진화형 조립: Phase 1(mapper+atomizer) → +forecaster → +hil_2/optimizer. 매 commit 마다 추가만 (기존 edge 보존).
  - conditional edge 1개: `hil_2 → optimizer | END` — `hil_2_selection` 비어있음 = risky 0건 OR PM 무선택.
- **대응 패턴**:
  - 발동: FastAPI `/run` 또는 CLI 진입 (현재 entry point 미구현 — `pipeline/main.py` / `pipeline/api.py` 0 byte)
  - 입력: GraphConfig (4 sub-config)
  - 처리: StateGraph 노드 5개 + edge 4개 + conditional_edge 1개 등록 후 `compile(checkpointer=build_checkpointer())`
  - 출력: CompiledGraph
- **관련**:
  - `build_demo_graph` (graph.py:200) — 자매 함수 (Parser/Mapper/Atomizer skip 데모)
  - `build_checkpointer` (checkpointer.py:13)
- **Suspected related** (2026-05-17 stale):
  - HIL 1 추가 자리 (mapper → hil_1 → atomizer). drift backlog #4 진입 시 본 함수에서 노드 +1, edge 1개 split.

---

### `build_demo_graph` — Parser/Mapper/Atomizer skip 데모 graph

- **위치**: `pipeline/graph.py:200-230` (31 LOC)
- **시그니처**: `def build_demo_graph(cfg: GraphConfig) -> CompiledGraph`
- **이슈**:
  - git log `ba5d274` (optimizer/Task 11: synthetic_daily_report + build_demo_graph + CLI). 최초.
  - docstring (graph.py:200-206): "데모 graph — START → forecaster → hil_2 → (optimizer | END) → END. Spec §10.3. Parser/Mapper/Atomizer skip — state['mapped'] 에 가짜 Activity list 사전 주입 가정 (LLM 비용 회피). build_graph 와 별도 (기존 graph 영향 X)."
- **설계 의도**:
  - 비용 회피: Parser/Mapper LLM 호출 ($0.02/run 매핑) 없이 hil_2/Optimizer 흐름만 시연.
  - `synthetic_daily_report.py` CLI + `test_synthetic_daily_report.py` E2E 가 진입점.
  - `build_graph` 와 완전 분리 — 기존 그래프 변경 없이 추가.
- **대응 패턴**:
  - 발동: synthetic_daily_report CLI 또는 test
  - 입력: `state["mapped"]` 에 가짜 Activity 사전 주입된 GraphConfig
  - 처리: forecaster → hil_2 → conditional → optimizer 또는 END
  - 출력: CompiledGraph (별도 checkpointer 인스턴스)
- **관련**:
  - `agents/optimizer/synthetic_daily_report.py:_main_cli` — CLI 엔트리
  - `pipeline/tests/optimizer/test_synthetic_daily_report.py` — E2E
- **Suspected related** (2026-05-17 stale):
  - audit drift #3 (synthetic fixture productivity_ratio bug) — 본 데모 graph 의 입력이 synthetic_daily_report.

---

### `CPIAState` — LangGraph 전체 상태 TypedDict

- **위치**: `pipeline/state.py:106-137` (32 LOC)
- **시그니처**: `class CPIAState(TypedDict)` — 17 필드
- **이슈**:
  - 주석 (state.py:124): `# optimizer cycle Task 1 (v3.1) — 3 필드 (hil_2 / Optimizer 데이터 계약)` — `hil_2_selection`, `pre_optimizer_cases`, `optimizer_advice` 추가 이력.
  - CLAUDE.md "Phase 0 — 코드 전에 둘이 함께 결정할 것" 명시: state.py 는 Agent 간 공유 데이터 구조, 합의 후 노드 코드 작성 게이트.
  - `docs/schema/state.md` 가 페어 문서 (자료 없음 — 파일은 있으나 본 cycle 미참조).
- **설계 의도**:
  - 누적식 상태: 각 node 가 `current_node` + 새 필드만 add (LangGraph reducer 패턴).
  - HIL 1 + HIL 2 자리 명시: `hil_1_corrections: dict` (line 118), `hil_2_selection: list[str]` (line 125). HIL 1 은 필드만 정의되어 있고 set 되는 코드 없음.
  - `status: Literal["running","waiting_hil_1","waiting_hil_2","completed","failed"]` (line 131-137) — 5 상태값 정의. `waiting_hil_1` 값은 정의만 있고 명시적 전환 코드 미확인.
- **대응 패턴**:
  - 발동: 모든 노드 입력/출력 시그니처에 박혀 있음
  - 입력: 노드별 add 필드 (return dict)
  - 처리: LangGraph reducer 가 merge
  - 출력: 누적 dict
- **관련**:
  - 모든 node 시그니처 (`async def X(state: CPIAState, cfg: ...) -> dict`)
- **Suspected related** (2026-05-17 stale):
  - HIL 1 미구현 — `hil_1_corrections` 필드는 있으나 mapper.py 에서 set 하는 코드 없음, graph.py 에 hil_1_node 부재. drift backlog #4.

---

### `build_checkpointer` — Phase 1 PoC InMemorySaver

- **위치**: `pipeline/checkpointer.py:13-18` (8 LOC)
- **시그니처**: `def build_checkpointer() -> InMemorySaver`
- **이슈**:
  - git log `a0a7a82` (optimizer/Task 8) 최초 추가.
  - docstring: "Phase 1 PoC checkpointer — InMemorySaver. interrupt + Command(resume=...) cycle 지원에 필요한 thread-local 상태 저장소."
  - 메타: `docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §8.1` — "InMemorySaver (Phase 1) → PostgresSaver (prod, Reporter cycle 또는 통합)".
  - 파일 상단 주석 (checkpointer.py:1-5): "prod (Reporter cycle 또는 통합 cycle): PostgresSaver 전환".
- **설계 의도**:
  - PoC 단순화: thread_id 만으로 인터럽트/resume 동작하면 충분, 진짜 영속성은 prod 전환 시점에 PostgresSaver.
  - CLAUDE.md 아키텍처 도식의 `checkpoints` 테이블은 LangGraph PostgresSaver 가 auto-manage 한다는 약속 — 현재는 미작동.
- **대응 패턴**:
  - 발동: `build_graph` / `build_demo_graph` 가 compile 시 호출
  - 입력: 없음
  - 처리: `InMemorySaver()` 인스턴스 생성
  - 출력: checkpointer
- **관련**:
  - `graph.py:230` (build_demo_graph compile)
  - `graph.py:272` (build_graph compile)
- **Suspected related** (2026-05-17 stale):
  - Reporter cycle 진입 시 PostgresSaver 전환. drift backlog #1.
  - `docs/schema/postgres.md:checkpoints` 테이블 — 현재 dead schema (LangGraph PostgresSaver 미활성).

---

## 2026-05-17 hil1-forecaster-reporter cycle 변경 (Git SHA d57b0c5)

### T1 신규 함수 5

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_build_review_needed` | graph.py:57 | `(mapped) -> list[dict]` | requires_review=True 인 Activity payload 빌더 (8 키: idx + work_content + company + trade + wa + l6_main + mapping_conf + mapping_source) | ✅ |
| `_apply_corrections` | graph.py:78 | `(mapped, corrections) -> list[Activity]` | corrections (idx→{wa, l6_main}) 적용 — 답한 row 정정 + 답 안 한 row Mapper 추천 수용 | ✅ |
| `hil_1_node` | graph.py:113 | `async (state, cfg) -> dict` | Mapper 결과 사람 검토 interrupt + PG mapping_corrections 영속 | ✅ |
| `reporter_node` | graph.py:311 | `async (state, cfg) -> dict` | Mapper+Forecaster+Optimizer 종합 보고서 생성 + PG daily_reports INSERT | ✅ |
| `_LazyAsyncPostgresSaver` | checkpointer.py:30 | class (AsyncPostgresSaver 상속) | AsyncConnectionPool lazy open wrapper — 첫 async method 호출 시 await pool.open() | ✅ |

`GraphConfig` 에 `reporter: ReporterConfig` 필드 추가 (graph.py:39). `build_graph` + `build_demo_graph` edges 변경:
- mapper → hil_1 → atomizer (기존 mapper → atomizer)
- hil_2 conditional → optimizer | reporter (기존 optimizer | END)
- optimizer → reporter (기존 optimizer → END)
- reporter → END (신규)

`build_checkpointer` 기존 InMemorySaver → `_LazyAsyncPostgresSaver` (POSTGRES_URL 있고 CPIA_CHECKPOINTER!="memory" 시). 두 fallback 분기 유지.

---

### T2 신규 카드

#### `hil_1_node` — Mapper 결과 사람 검토 interrupt

- **위치**: `pipeline/graph.py:113-167` (55 LOC, 분기 3)
- **시그니처**: `async def hil_1_node(state: CPIAState, cfg) -> dict`
- **이슈**:
  - git log `1bb78fb` (feat(hil_1): Mapper 결과 사람 검토 + PG mapping_corrections 영속) — 본 cycle 신규.
  - spec `docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.1` — 의도적 drift = CLI 인터랙티브 (PM 원안 v2 Dashboard Modal 회피).
  - drift backlog: #4 (PoC 성공 기준 #2 직접 미충족 — 본 commit 으로 해소).
  - 코드 주석 (graph.py:113-117): "Mapper 결과 사람 검토. requires_review=True 가 1건 이상이면 interrupt. Spec §5.1. cfg = GraphConfig (PG INSERT 용 postgres_url 추출, cfg=None 이면 PG insert skip — unit 테스트 path)."
  - LangGraph 패턴 fact (commit msg `1bb78fb`): "LangGraph multi-resume 검사 fix — Command(resume=dict) 의 key 는 str 필수 (int → TypeError). hil_1_node 가 int(k) 변환 처리." (drift #N5)
- **설계 의도**:
  - hil_2_node 패턴 차용 (interrupt + Command(resume=)) — graph.py:hil_2_node 의 risky_groups payload 와 대칭.
  - review_needed 빈 list → interrupt 미발생 (자동 통과) — 100% confidence row 인 경우 효율.
  - 답 안 한 row 처리: Mapper 추천 그대로 수용 + `mapping_source="user_corrected"` 박음 → "no decision = approve" 의미 (PoC 기본, 재시도 옵션은 후속 cycle).
  - PG 영속: 사용자 정정 row 마다 1 INSERT — 다음 run 진입 시 자가 학습 데이터 (postgres.md:311 의도).
  - cfg=None 분기: unit 테스트가 LangGraph runtime 없이 호출 가능 (review_needed=빈 list path).
- **대응 패턴**:
  - 발동: `graph.add_edge("mapper", "hil_1")` 후 mapper_node 종료 시
  - 입력: state.mapped (Mapper 출력) + cfg (PG URL 용)
  - 처리: `_build_review_needed` → 빈 list 시 즉시 return / 1+ 시 `interrupt({"review_needed": [...]})` → corrections_raw dict → int(k) 변환 → `_apply_corrections` → cfg.mapper.postgres_url 로 PGClient connect → corrections idx 마다 insert_mapping_correction → close
  - 출력: `{"mapped": corrected, "hil_1_corrections": corrections, "current_node": "hil_1"}`
- **관련**:
  - 내부 헬퍼: `_build_review_needed` + `_apply_corrections`
  - PG INSERT: `db.py:insert_mapping_correction`
  - LangGraph: `from langgraph.types import Command, interrupt` (graph.py:15)
  - 테스트: `tests/test_graph_hil1.py` (unit 3) + `tests/test_graph_e2e_hil1.py` (e2e 2 slow)
  - 차용 패턴: `hil_2_node` 의 `selected = interrupt({"risky_groups": payload_groups})`
- **Suspected related** (2026-05-17 stale):
  - `hil_2_node` — 동일 interrupt/resume 패턴. 향후 _common_interrupt helper 추출 후보 (low priority).
  - B_Track Dashboard `MappingReviewModal.tsx` — CLI 인터랙티브 의도적 drift. 통합 cycle 진입 시 채널 교체.

#### `reporter_node` — Mapper+Forecaster+Optimizer 종합 보고서 생성

- **위치**: `pipeline/graph.py:311-328` (18 LOC, 분기 1)
- **시그니처**: `async def reporter_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - git log `22d44c2` (feat(reporter): Mapper+Forecaster+Optimizer 종합 보고서 + PG daily_reports) — 본 cycle 신규.
  - spec `§5.3` — 의도적 drift = Optimizer 다음 + 종합 1 종 (PM 원안 v2 = Atomizer 다음 병렬 + 사내/발주처 2 종).
- **설계 의도**:
  - 얇은 wrapper — 실 로직은 `reporter.report` (별 파일). graph 노드 = run_id/today 변환 + state 추출 + report() 호출.
  - hil_2 conditional 의 양 분기 합류 — selection=[] 시에도 진입 (mapped=빈 인 cold_start path 도 fallback MD).
- **대응 패턴**:
  - 발동: optimizer → reporter (selection 있음) 또는 hil_2 → reporter (selection 없음) conditional_edge
  - 입력: state.mapped + state.forecast + state.optimizer_advice + state.run_id + state.date + cfg.reporter
  - 처리: run_id UUID 변환 → today date 변환 → `reporter.report(...)` 호출 → report_md 반환
  - 출력: `{"report_md": report_md, "current_node": "reporter"}`
- **관련**: [reporter 카드](./design_intent_reporter.md) (실 로직 + LLM call + PG INSERT 상세)

#### `_LazyAsyncPostgresSaver` — AsyncPostgresSaver lazy pool open wrapper

- **위치**: `pipeline/checkpointer.py:30-79` (50 LOC, 분기 1 lazy)
- **시그니처**: `class _LazyAsyncPostgresSaver(AsyncPostgresSaver): def __init__(self, postgres_url: str)`
- **이슈**:
  - git log `41908f6` (feat(checkpointer): InMemorySaver → AsyncPostgresSaver 전환 + memory fallback) — 본 cycle 신규.
  - design-intent O-6 권고: "Reporter cycle 또는 통합 cycle 진입 시 PostgresSaver 전환" — 본 cycle 흡수.
  - 기술 결정 (commit msg `41908f6`):
    - "PostgresSaver (sync) 는 graph.ainvoke 의 aget_tuple 등 async method 호출 시 NotImplementedError → AsyncPostgresSaver 사용 필수."
    - "AsyncConnectionPool 은 sync __init__ 안에서 await pool.open() 호출 불가 → _LazyAsyncPostgresSaver 가 첫 async method 호출 (graph.ainvoke 안) 에서 자동 pool.open() 처리."
    - "LangGraph 의 isinstance(checkpointer, BaseCheckpointSaver) 검사 통과를 위해 wrapper 가 AsyncPostgresSaver 상속."
- **설계 의도**:
  - 3 제약 동시 충족:
    - LangGraph async graph (ainvoke) → AsyncPostgresSaver
    - AsyncConnectionPool open=False (sync __init__ 안에서 async open 불가)
    - LangGraph BaseCheckpointSaver isinstance 검사 통과
  - 첫 async method 호출 시 lazy open (단 1회) — `self._opened` flag.
  - 5 method override: aput / aget_tuple / aput_writes / alist / aget (LangGraph 가 호출하는 async method 전부).
  - `autocommit=True` kwargs — checkpoint INSERT 별 transaction 자동 commit (별 transaction 안 진입).
- **대응 패턴**:
  - 발동: `build_checkpointer()` 가 `CPIA_CHECKPOINTER!="memory"` + `POSTGRES_URL` 존재 시 반환
  - 입력: postgres_url str
  - 처리: AsyncConnectionPool 생성 (open=False, max_size=10) → super().__init__(pool) → 첫 async method 호출 시 `_ensure_open` → `await self._lazy_pool.open()` → super().aXXX delegate
  - 출력: AsyncPostgresSaver-compatible 객체
- **관련**:
  - 호출자: `build_checkpointer:80` (graph.py:build_graph / build_demo_graph 가 사용)
  - 의존성: `pyproject.toml` 의 `langgraph-checkpoint-postgres>=2.0.0` + `psycopg[binary]` (uv add 2 패키지)
  - PG 테이블 4 자동 생성: checkpoints + checkpoint_writes + checkpoint_blobs + checkpoint_migrations
  - 테스트: `tests/test_checkpointer.py` 3건 (postgres default + memory fallback + no POSTGRES_URL fallback)
- **Suspected related** (2026-05-17 stale):
  - 본 wrapper 는 본 cycle 종결 후 production 진입점 (main.py / api.py — 현재 0 byte stub) 에서 lifecycle 관리 권장.
  - drift backlog #N5 LangGraph Command(resume=dict) int key TypeError — 본 wrapper 와 무관 (interrupt payload 변환 룰, hil_1_node 가 처리).

#### `_build_review_needed` + `_apply_corrections` — hil_1_node 분리 헬퍼

- **위치**: graph.py:57-76 + graph.py:78-111 (각 20/34 LOC, pure functions)
- **시그니처**:
  - `def _build_review_needed(mapped: list[Activity]) -> list[dict]`
  - `def _apply_corrections(mapped: list[Activity], corrections: dict[int, dict]) -> list[Activity]`
- **이슈**: hil_1_node 분리 헬퍼 — unit 테스트 단순 호출 위해 (state/cfg 무관). spec §5.1 #6 의 "답 안 한 row 는 Mapper 추천 수용" 룰 명시.
- **설계 의도**:
  - pure function — unit 테스트 단순 호출, LangGraph runtime 의존 X.
  - `_apply_corrections` 3 path 분기 — (a) requires_review=False 변경 X, (b) requires_review=True + corrections 있음 → 사용자 정정, (c) requires_review=True + corrections 없음 → Mapper 추천 수용. 모두 `mapping_source="user_corrected"` + `requires_review=False` 마킹.
- **대응 패턴**: 호출자 = `hil_1_node`. 테스트 = `tests/test_graph_hil1.py::test_hil_1_node_review_needed_filter` + `::test_hil_1_node_apply_corrections`.
