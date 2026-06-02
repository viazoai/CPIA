# Design Intent — orchestration (graph + state + checkpointer + constants + collector_node + parser_node + _concurrency + collector/*)

- **Generated**: 2026-06-01 (d317be9) — parser_node async multi-file merge + hil_1 resume falsy-fix surgical 갱신. 이전 cycle 2026-05-26 (1ba783f, D-12 collector_node 진입 + IDLE worker + build_atomized_demo_graph + cross-company HIL2 + reporter status fix + LLM Semaphore 분리).
- **Git SHA**: `1ba783f → d317be9` (A_Track HEAD, origin sync). 본 surgical 갱신은 `a8d17e4` (multi-file async parser merge + hil_1 resume falsy-fix) 1 커밋만 반영 — 그 외 카드는 1ba783f 기준 유지. 라인번호는 d317be9 기준 재검증.
- **Pair file**: `../architecture_overview.md` (deep-dive 라이트) + `../deep_dive_orchestration.md` (1143 줄, 본 cycle 1차 자료)
- **Range** (11 모듈, 1605 LOC):
  - `pipeline/graph.py` (628 LOC, 이전 563 → +65)
  - `pipeline/state.py` (310 LOC, 이전 303 → +7)
  - `pipeline/checkpointer.py` (94 LOC, 변경 0)
  - `pipeline/constants.py` (5 LOC, 변경 0)
  - `pipeline/agents/collector_node.py` (63 LOC, 신설)
  - `pipeline/agents/parser_node.py` (25 LOC, 신설)
  - `pipeline/agents/_concurrency.py` (18 LOC, 신설)
  - `pipeline/agents/collector.py` (70 LOC, legacy — 본 cycle 변경 0)
  - `pipeline/collector/filename_parser.py` (64 LOC, 신설)
  - `pipeline/collector/idle_worker.py` (260 LOC, 신설)
  - `pipeline/collector/config.py` (68 LOC, 신설)
- **스펙**:
  - `docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md` (D-12 collector 분리)
  - `docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md`
  - `docs/superpowers/specs/2026-05-14-cpia-2인-langgraph-협업-design.md`

LangGraph StateGraph 위에 **7~9 node + 2 helper + 3 builder + 2 interrupt point** 조립 + 공유 상태 + lazy AsyncPostgresSaver checkpoint + IMAP IDLE listener.

**본 surgical 갱신 (1ba783f → d317be9, `a8d17e4`) 2 핵심 변경**:
- **A. parser_node async multi-file merge**: sync 단일파일 래퍼 → `input_files` 전체 async N병렬 (`to_thread` Semaphore 4) 파싱 + `_merge_reports` concat → 1 통합 `ParsedDailyReport`. `build_graph` 의 `_parser_p` wrapper 가 `return await _parser(state)` 로 await 추가 (graph.py:595~598). 옛 issue #L5 (parser sync) 해소.
- **B. hil_1 langgraph 1.2.0 falsy-resume fix (신규 T2 카드)**: `Command(resume=<falsy>)`(보정 0건 → 빈 `{}`) 미전달로 interrupt 재발생 → hil_1 영구 갇힘 ("승인 눌러도 안 넘어감"). `api.py:hil_1_resume` 가 항상 truthy 래퍼 `Command(resume={"corrections": payload})` (api.py:328~331), `hil_1_node` 가 `set(corrections_raw)=={"corrections"}` 분기로 언랩 (graph.py:263~264). 결정론 재현으로 root cause 확정.

**이전 cycle (ef7c6cd → 1ba783f) 7 핵심 변경** (1ba783f 기준 라인번호 — d317be9 에서 다소 shift, 카드 본문 참조):
1. **`build_graph` 진입점 이동** (`55cad90`): `mapper → ...` → `collector → parser → mapper → ...` 9-노드 production topology. 신규 graph 노드 2 개 (`collector_node` + `parser_node`).
2. **D-12 state-key drift fix** (`6b9db7c`): listener 가 invoke 시 박는 4 신규 키 (`bp_name`/`project`/`message_id`/`postgres_url`) 를 `CPIAState` 에 정식 정의.
3. **IMAP IDLE collector** (`5347966` + `973fa66` + `85155eb` + `c1cba0f`): `pipeline/collector/` 폴더 신설 — `filename_parser` (정규식) + `idle_worker` (UNSEEN drain + dedup + dead_letter + `run_for_attachment` fire-and-forget) + `config` (env 9 종 fail-fast). `collector_inbox` PG 테이블 + 3 helper.
4. **`build_atomized_demo_graph`** (`ef95e02`): mapper/hil_1 만 skip. mapped 는 호출자가 PG hydrate. 15일 backfill 표준 graph.
5. **`get_llm_semaphore()` + `CPIA_LLM_CONCURRENCY`** (`1e24dc6`): forecaster/optimizer/atomizer 공용 LLM 동시성. event loop 별 lazy.
6. **HIL 2 cross-company retrieve** (graph.py:355, 2026-05-22): Chroma `coll.get(where=...)` 의 company hard filter 제거 → 합성 3사 외 75사가 cold_start fallback 빠지던 회귀 해소.
7. **Reporter Issue B fix** (graph.py:482, 2026-05-20): `pipeline_runs.status='completed' + completed_at=NOW()` UPDATE 추가. 이전엔 graph 종료 후에도 status='running' 잔존.

---

## T1 — Function Index

### graph.py (628 LOC) — Node 함수 7 + 빌더 3 + helper 2

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `GraphConfig` | graph.py:49 | `@dataclass` | 5 sub-config (mapper / atomizer / forecaster / optimizer / reporter) | — |
| `mapper_node` | graph.py:57 | `async (state, cfg) -> dict` | Parser → WBS 매핑 + Semaphore 4 + BP cand_pool batch + 정규화 2회 + G24 호출 + 5 PG INSERT + 같은 트랜잭션 SELECT 검증 | ✅ |
| `_build_review_needed` | graph.py:177 | `(mapped) -> list[dict]` | requires_review=True 행 9 필드 extraction | ✅ |
| `_apply_corrections` | graph.py:198 | `(mapped, corrections: dict[int, dict]) -> list[Activity]` | corrections 적용 + mapping_source="user_corrected" + requires_review=False 강제 | ✅ |
| `hil_1_node` | graph.py:233 | `async (state, cfg) -> dict` | Mapper interrupt + `CPIA_HIL_AUTO_BYPASS` env 우회 + resume 래퍼 언랩 (langgraph 1.2.0 falsy-resume fix, graph.py:263~264) + PG mapping_corrections INSERT | ✅ |
| `atomizer_node` | graph.py:307 | `async (state, cfg) -> dict` | Chroma daily_activities 적재 + ID 반환 | ✅ |
| `forecaster_node` | graph.py:314 | `async (state, cfg) -> dict` | 그룹별 진단 (RAG + Plan fallback) | ✅ |
| `hil_2_node` | graph.py:321 | `async (state, cfg) -> dict` | risky 그룹 사전 영속 + F5/F7 정정 + cross-company retrieve + interrupt | ✅ |
| `optimizer_node` | graph.py:406 | `async (state, cfg) -> dict` | Selected group advice + view_builder + site_id/mapped pass-through (early return 제거) | ✅ |
| `reporter_node` | graph.py:431 | `async (state, cfg) -> dict` | 종합 보고서 + G8 sites.last_run_id + G2 hours_saved_cum + site_id PG fallback + pipeline_runs status='completed' UPDATE | ✅ |
| `build_demo_graph` | graph.py:496 | `(cfg) -> CompiledGraph` | forecaster → hil_2 → (optimizer\|reporter) → END (Parser/Mapper/Atomizer skip) | ✅ |
| `build_atomized_demo_graph` ★ NEW | graph.py:534 | `(cfg) -> CompiledGraph` | atomizer → forecaster → hil_2 → (optimizer\|reporter) → END (15일 backfill 표준) | ✅ |
| `build_graph` | graph.py:578 | `(cfg) -> CompiledGraph` | **collector → parser → mapper → hil_1 → atomizer → (exporter‖forecaster) → hil_2 → (optimizer\|reporter) → END**. `_parser_p` wrapper 가 async `parser_node` 를 `return await _parser(state)` 로 await (graph.py:595~598) | ✅ |

### state.py (310 LOC) — TypedDict 12 개

| TypedDict | File:Line | 역할 | T2? |
|---|---|---|---|
| `TimeShiftCounts` | state.py:17 | 6 시간대 분포 (morning/daytime/overtime/night/all_night/total) | — |
| `Activity` | state.py:32 | 작업일보 시트4 매핑 단위 (33 필드) | ✅ |
| `BPSummary` | state.py:96 | 시트1 BP사×공종×Zone×Scope (20 필드, jsonb 4 그룹) | — |
| `JobAllocation` | state.py:122 | 시트2 BP사×직종×시간대 (10 필드, jsonb 3 그룹) | — |
| `EquipmentAllocation` | state.py:146 | 시트3 BP사×장비×시간대 (10 필드, jsonb 3 그룹) | — |
| `WorkerOutput` | state.py:170 | 시트6 개별 작업자 (12 필드, 업체별만) | — |
| `ReportMeta` | state.py:193 | Cover (9 필드, 업체별만) | — |
| `ParsedDailyReport` | state.py:207 | 1 xlsx 통합 (8 필드) | — |
| `CPIAState` | state.py:226 | LangGraph 전체 상태 (20 필드, 본 cycle +4) | ✅ |
| `BPSummaryRaw` | state.py:268 | 시트1 LLM row 단위 raw output (페어링 전) | — |
| `JobAllocationRaw` | state.py:285 | 시트2 LLM raw | — |
| `EquipmentAllocationRaw` | state.py:299 | 시트3 LLM raw | — |

### checkpointer.py (94 LOC)

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_LazyAsyncPostgresSaver` | checkpointer.py:30 | `class(postgres_url)` | `AsyncPostgresSaver` 상속 + sync `__init__` 에서 `AsyncConnectionPool(open=False)` 만 만들고 첫 async 메서드 시 `_ensure_open()` 으로 lazy `pool.open()` | ✅ |
| `build_checkpointer` | checkpointer.py:78 | `() -> BaseCheckpointSaver` | env 분기 — `CPIA_CHECKPOINTER=memory` 또는 `POSTGRES_URL` 미설정 → `InMemorySaver`; 그 외 → `_LazyAsyncPostgresSaver` | ✅ |

### constants.py (5 LOC)

| Name | File:Line | 값 | 역할 |
|---|---|---|---|
| `WORK_HOURS_PER_DAY` | constants.py:5 | `8` | cross-agent shared 일일 작업시간 |

> ~~7 agent name 상수 (collector/parser/.../reporter)~~ — 이전 cycle 카드 기재 오류, 현재 상수 1 개 (`WORK_HOURS_PER_DAY`) 만 존재.

### agents/collector_node.py (63 LOC, 신설) ★ NEW

| Name | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `collector_node` ★ NEW | collector_node.py:16 | `async (state: CPIAState) -> dict[str, Any]` | D-12 graph 진입점 — `input_files[0]` 경로 검증 + `parse_filename` 분해 + `collector_inbox` UPDATE(running) + meta 키 반환 | ✅ |

### agents/parser_node.py (64 LOC, 신설) ★ NEW

| Name | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `parser_node` ★ NEW | parser_node.py:40 | `async (state: CPIAState) -> dict[str, Any]` | async N병렬 multi-file merge — `input_files` 전체를 `to_thread(parse_daily_report)` Semaphore 4 로 병렬 파싱 후 `_merge_reports` concat → `{"parsed": ParsedDailyReport}` 반환 (`a8d17e4`, 이전 sync 단일파일 래퍼에서 전환) | ✅ |
| `_merge_reports` ★ NEW | parser_node.py:18 | `(reports: list[ParsedDailyReport]) -> ParsedDailyReport` | N개 ParsedDailyReport → 1 통합 (activities/bp_summaries/job/equip/worker_outputs concat, report_meta 는 첫 업체 것) | — |

### agents/_concurrency.py (18 LOC, 신설) ★ NEW

| Name | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `get_llm_semaphore` ★ NEW | _concurrency.py:15 | `() -> asyncio.Semaphore` | env `CPIA_LLM_CONCURRENCY` (기본 4) → `Semaphore(max(1, n))` event loop 별 lazy. forecaster/optimizer/atomizer 공유 | ✅ |

### agents/collector.py (legacy, 70 LOC, 변경 0)

| Name | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `CollectorConfig` | collector.py:23 | `@dataclass(file_concurrency=4)` | legacy collector 동시성 (1 필드) | — |
| `discover_daily_reports` | collector.py:30 | `(input_dir: Path\|str) -> list[Path]` | dir 안 `*작업일보*.xlsx[m]` 필터 (재귀 X, `~$` lock 제외) | — |
| `collect_and_parse` | collector.py:52 | `async (input_dir, cfg) -> list[ParsedDailyReport]` | `discover_*` + `asyncio.Semaphore(file_concurrency)` 로 `to_thread(parse_daily_report)` | — |

### collector/filename_parser.py (64 LOC, 신설) ★ NEW

| Name | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `ParsedFilename` ★ NEW | filename_parser.py:16 | `@dataclass(frozen)` (kind, project, bp_name, trade, zone, date) | 분해 결과 holder | — |
| `parse_filename` ★ NEW | filename_parser.py:25 | `(name: str) -> Optional[ParsedFilename]` | `업체작업일보_<project>_..._<bp>_<trade>_<zone>_<YYMMDD>.xlsx` 또는 `통합작업일보_<project>_<YYMMDD>.xlsx` 분해. 미일치 None | — |

### collector/idle_worker.py (260 LOC, 신설) ★ NEW

| Name | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `request_shutdown` ★ NEW | idle_worker.py:37 | `() -> None` | `_shutdown` Event set — lifespan shutdown trigger | — |
| `_extract_attachments` ★ NEW | idle_worker.py:41 | `(msg: Message) -> list[tuple[str, bytes]]` | multipart walk + RFC2047 디코딩 + `.xlsx/.xlsm` 필터 | — |
| `_save_to_input_dir` ★ NEW | idle_worker.py:63 | `(att_name, att_bytes, date_iso, cfg) -> Path` | `data/input/YYYYMMDD/<att_name>` 저장, 충돌 시 uuid suffix | — |
| `_to_dead_letter` ★ NEW | idle_worker.py:81 | `(att_name, att_bytes, cfg) -> None` | 파일명 미일치 시 dead_letter 폴더로 이동 | — |
| `run_for_attachment` ★ NEW | idle_worker.py:90 | `async (path, meta, site_id, message_id, cfg) -> None` | `_GRAPH_SEM` 보호 + `build_graph(cfg.graph_cfg)` 호출 + `ainvoke` + `collector_inbox` status UPDATE (running/failed/completed) | ✅ |
| `_process_one` ★ NEW | idle_worker.py:153 | `async (imap, uid, cfg) -> None` | UNSEEN 1 통 fetch + Message-ID dedup PG 체크 + 첨부 추출 + `insert_collector_inbox` + `create_task(run_for_attachment)` fire-and-forget | — |
| `_drain_new` ★ NEW | idle_worker.py:214 | `async (imap, cfg) -> None` | UNSEEN search → 각 uid `_process_one` | — |
| `idle_loop` ★ NEW | idle_worker.py:228 | `async (cfg: CollectorConfig) -> None` | FastAPI startup background task. IMAP login + INBOX select + 시작 drain + `idle_start(29min) → wait_server_push → idle_done` 무한 반복 + 지수 backoff | ✅ |

### collector/config.py (68 LOC, 신설) ★ NEW

| Name | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `CollectorConfig` ★ NEW | config.py:15 | `@dataclass(frozen)` (host, port, user, app_password, default_site_id, input_dir, dead_letter_dir, postgres_url, graph_cfg, enabled) | env 9 종 + graph_cfg 묶음 | — |
| `_bool` ★ NEW | config.py:29 | `(s, default) -> bool` | env 문자열 → bool | — |
| `load_collector_config` ★ NEW | config.py:35 | `(graph_cfg: GraphConfig) -> CollectorConfig` | env 9 종 로드. `COLLECTOR_ENABLED=true` 인데 USER/APP_PASSWORD 누락 시 `RuntimeError` fail-fast | ✅ |

---

## T2 — Issue Cards

### `mapper_node` — Parser → WBS 매핑 + 병렬화 + 정규화 2회

- **위치**: `pipeline/graph.py:50-167` (118 LOC)
- **시그니처**: `async def mapper_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - git log:
    - `cf2a791 fix(graph): import normalize_company — close #31`
    - `e163e1a fix(graph,scripts): POC 3사 + 정규화 타이밍 버그`
    - `844d4c3 fix(graph,cycle): full cycle 진행 — HIL bypass + pipeline_runs + HIL2 auto-select`
    - `03ebc3d perf(mapper): graph mapper_node 병렬화 + BP cand_pool batch fetch`
  - 주석 (graph.py:51~60): "Parser 결과 + Parser/Mapper 산출 PG 영속." / "BP cand_pool 미리 batch fetch (1 PG connection × N BP) → map_activity 안의 매 활동마다 새 PG connection 폭발 회피" / "asyncio.gather + Semaphore(CPIA_MAPPER_CONCURRENCY, 기본 4) 로 묶어 Azure rate-limit 회피"
  - **정규화 타이밍 fix (e163e1a)**: fetch_bp_candidates 가 정확 일치 SQL → ㈜/(주) prefix 남아있으면 cand_pool 빔 → conf=0.1
  - **본 cycle 변경 (1ba783f)**: `state["parsed"]` 의 source 노드가 `parser_node` 로 분리됨 — `parser_node` 가 `parse_daily_report` 호출 후 `{"parsed": ParsedDailyReport}` 박음, mapper 는 단순 소비. 본 노드 코드 자체는 변경 0 (D-12 진입점 변경의 downstream beneficiary).
- **설계 의도**:
  - 병렬화 성능: 79 row → Semaphore(4) → Azure rate-limit 회피 + PG cand_pool batch (1 connection × N company)
  - **정규화 2회**:
    1. graph.py:69~70 — fetch_bp_candidates 전 일괄 정규화 (parsed.activities)
    2. graph.py:146~147 — mapped 일괄 (방어 중복)
  - PG 영속 5건 (G24 호출 추가):
    - `insert_parser_report` (graph.py:110)
    - `insert_parser_activities_batch` (graph.py:120)
    - `insert_parser_job_allocations_batch` (graph.py:130, G24 — 이전 호출 누락 row=0)
    - `insert_parser_equipment_allocations_batch` (graph.py:136, G24 — 이전 호출 누락 row=0)
    - `insert_mapper_activities_batch` (graph.py:149)
  - **같은 트랜잭션 SELECT COUNT 검증** (graph.py:157~162) — silent fail 진단용 (`_dbg` stderr 로그).
- **대응 패턴 (시그니처)**:
  - 발동 조건: parser_node 다음 노드 — `parser → mapper` edge (graph.py:616).
  - 입력: state["parsed"] (ParsedDailyReport)
  - 처리:
    - graph.py:69~70 — 정규화 1 (parsed.activities)
    - graph.py:76~80 — unique_companies batch fetch_bp_candidates
    - graph.py:84~95 — Semaphore + `asyncio.gather(map_activity, ...)`
    - graph.py:107 — `_prorate_mh(mapped, parsed, pg)`
    - graph.py:146~147 — 정규화 2 (mapped)
    - graph.py:110~153 — PG 영속 5건
    - graph.py:157~162 — 트랜잭션 안 SELECT COUNT 3건
  - 출력: `{"mapped": list[Activity], "current_node": "mapper"}`
- **관련**:
  - 호출자: `build_graph` (graph.py:617) `parser → mapper → hil_1`
  - 페어: `mapper.py.map_activity` + `mapper.py._prorate_mh`
  - PG: `db.py` 의 5 batch INSERT 함수 + `fetch_bp_candidates`
  - 테스트: `pipeline/tests/test_graph_e2e.py`
- **Suspected related** (2026-05-26):
  - `mapper.py.resolve_wa` step 1 — BP-zone deterministic 정확도 의존
  - `parser_post.normalize_company` — graph.py:25 import
  - `_LazyAsyncPostgresSaver` — atomicity 영향 (issue #M1)

---

### `hil_1_node` — Mapper 검토 interrupt + AUTO_BYPASS env + resume 래퍼 언랩

- **위치**: `pipeline/graph.py:233-305` (73 LOC)
- **시그니처**: `async def hil_1_node(state: CPIAState, cfg) -> dict`
- **이슈**:
  - git log:
    - `1bb78fb feat(hil_1): Mapper 결과 사람 검토 + PG mapping_corrections 영속`
    - `844d4c3 fix(graph,cycle): full cycle 진행 — HIL bypass` (2026-05-20)
    - `a8d17e4 feat(graph): multi-file async parser merge + hil_1 resume falsy-fix` (2026-06-01)
  - 주석 (graph.py:234~241): "Mapper 결과 사람 검토. requires_review=True 가 1건 이상이면 interrupt" / "cfg = GraphConfig (cfg=None 이면 PG insert skip — unit 테스트 path)" / "env CPIA_HIL_AUTO_BYPASS={1\|true\|on} → review_needed 가 있어도 interrupt 건너뛰고 빈 corrections 로 통과 (dev/검증 모드 — atomizer/forecaster 진행 위해)"
  - **본 cycle 변경 (`a8d17e4`, graph.py:259~264)**: resume 래퍼 언랩 분기 추가 — 별도 카드 (`hil_1_node — langgraph 1.2.0 falsy-resume fix`, 아래) 참조. 코드 추가는 언랩 4줄.
  - deep_dive_orchestration.md §13.1 #C1: `CPIA_HIL_AUTO_BYPASS` 는 dev/검증 path 전용이지만 prod env 가드 부재. 실수로 prod 에 박히면 모든 low-conf 매핑이 silent skip + user_corrected 로 둔갑.
- **설계 의도**:
  - interrupt pattern (spec §5.1):
    - `interrupt({"review_needed": review_needed})` → 외부 user/PM input
    - `Command(resume=...)` → `corrections_raw = corrections_raw or {}` 안전 처리 + 래퍼 언랩 (아래 카드)
    - corrections key (int) ← str 변환 (LangGraph Command resume key int → str 룰, issue #L3)
  - **AUTO_BYPASS env (844d4c3)**: cycle1~4 의 interrupt 무한 루프 (resume={} → re-raise) 해결 — dev/검증 path
  - PG insert 조건: `cfg is not None and corrections` (Unit test + AUTO_BYPASS 시 PG INSERT skip)
- **대응 패턴 (시그니처)**:
  - 발동 조건: `mapper → hil_1` (graph.py:647). 진입 시 `_build_review_needed(mapped)` 호출하여 review_needed 추출.
  - 입력: state["mapped"]
  - 처리:
    - `_build_review_needed` (graph.py:177) — requires_review=True 9 필드 추출
    - review_needed 0 → pass-through (graph.py:244~245)
    - AUTO_BYPASS 체크 (graph.py:247~255) — stderr 로그 + 빈 corrections 통과
    - `interrupt(...)` (graph.py:257) → `Command(resume=...)`
    - resume 래퍼 언랩 (graph.py:263~264) — `set(corrections_raw)=={"corrections"}` 일 때만
    - `int(k)` 키 복원 (graph.py:265)
    - `_apply_corrections` (graph.py:198) — corrections 적용
    - `pg.insert_mapping_correction` 반복 (corrections per row, graph.py:276~296)
  - 출력: `{"mapped": [...corrected], "hil_1_corrections": corrections, "current_node": "hil_1"}`
- **관련**:
  - 호출자: `build_graph` mapper → hil_1 → atomizer
  - 테스트: `test_graph_hil1.py`, `test_graph_e2e_hil1.py`, `test_api_hil1_resume.py` (resume 래퍼 계약)
  - PG: `insert_mapping_correction` (db.py)
  - FastAPI 진입점: `api.py:297~349` `/api/runs/{run_id}/hil_1/resume`
- **Suspected related** (2026-06-01):
  - `_build_review_needed` (graph.py:177) — interrupt payload 빌드
  - `_apply_corrections` (graph.py:198) — corrections 적용
  - `api.py:hil_1_resume` (api.py:298) — truthy 래퍼로 resume 호출 (아래 falsy-resume 카드)
  - HIL 2 와 비교 — HIL 2 에는 AUTO_BYPASS 없음 (issue #M4)

---

### `hil_1_node` — langgraph 1.2.0 falsy-resume fix (resume 래퍼 언랩) ★ NEW

- **위치**: `pipeline/graph.py:257-265` (언랩 분기) + `pipeline/api.py:320-331` (래퍼 호출)
- **시그니처**: `async def hil_1_node(state: CPIAState, cfg) -> dict` (graph.py:233) ↔ `async def hil_1_resume(run_id: str, body: Hil1ResumeRequest) -> Hil1ResumeResponse` (api.py:298)
- **이슈**:
  - git log: `a8d17e4 feat(graph): multi-file async parser merge + hil_1 resume falsy-fix` (2026-06-01).
  - spec `docs/superpowers/specs/2026-06-01-cpia-graph-multifile-PoC-progress.md §★UPDATE 2`: "hil_1 resume 영구 갇힘 (langgraph 1.2.0) — `Command(resume=<falsy>)`(빈 보정 `{}`)는 전달 안 돼 interrupt 재발생. fix: `api.py` 가 항상 truthy 래퍼 `{"corrections": {...}}` 로 resume, `graph.py:hil_1_node` 가 언랩(`set(keys)=={"corrections"}`). harness 결정론 검증 그린(빈/non-empty 둘 다 reporter 완주, mapping_source=user_corrected 적용 확인)."
  - 같은 spec §2 PoC 결과: "hil_1 resume 버그 — `/api/runs/{id}/hil_1/resume` 가 `next_node:mapper` 반환 + status 안 풀림(재개 실패)." → 사용자 증상 "승인 눌러도 안 넘어감".
  - **root cause (결정론 재현)**: langgraph 1.2.0 이 `Command(resume=<falsy>)` (보정 0건 → 빈 `{}`) 를 그래프에 전달하지 않음. interrupt 가 재발생 → hil_1 에 영구히 갇힘. 빈 dict vs 비어있지 않은 dict 의 동작 차이로 확정 (재현 스크립트 `/tmp/cpia_test_resume.py`·`/tmp/cpia_test_minimal_resume.py`). HIL 1 "전부 승인 / 보정 0건" 케이스가 무한 루프.
  - 주석 (graph.py:259~262): "langgraph 1.2.0: Command(resume=<falsy>) (예: 보정 0건 → {}) 는 그래프에 전달되지 않아 interrupt 가 재발생, hil_1 에 영구히 갇힌다. endpoint(api.py)가 빈 보정에도 항상 truthy 한 {"corrections": {...}} 래퍼로 resume 하므로 여기서 언랩한다. 래퍼 없는 직접 dict 호출(테스트/구버전 호환)은 그대로 통과."
  - 주석 (api.py:325~327): "langgraph 1.2.0: Command(resume=<falsy>) (보정 0건 → {}) 는 전달되지 않아 hil_1 interrupt 가 재발생한다. 항상 truthy 한 {"corrections": ...} 래퍼로 감싸 보정 유무와 무관하게 resume 가 전달되도록 한다 (hil_1_node 가 언랩)."
- **설계 의도**:
  - **endpoint 가 항상 truthy 래퍼로 호출**: `api.py:hil_1_resume` 가 보정 유무와 무관하게 `Command(resume={"corrections": corrections_payload})` (api.py:328~331) 로 호출. `corrections_payload` 가 빈 `{}` 이어도 `{"corrections": {}}` 는 truthy → langgraph 가 그래프에 전달 → interrupt 를 한 번만 통과.
  - **hil_1_node 가 래퍼만 언랩**: `set(corrections_raw) == {"corrections"}` (graph.py:263) 인 경우만 한 겹 벗김 (`corrections_raw["corrections"] or {}`, graph.py:264). 래퍼 없는 직접 dict resume (테스트/구버전) 은 분기를 타지 않고 그대로 통과 — 하위호환.
  - **falsy 신호를 truthy sentinel/래퍼로 감싸는 패턴**: langgraph interrupt resume 시 "보정 0건" 같은 의미 있는 falsy 값을 그대로 넘기면 미전달되므로, 항상 truthy 한 단일 key 래퍼로 감싸고 수신측이 언랩한다.
- **대응 패턴 (시그니처)**:
  - 발동 조건: FE review 화면 "모두 AI 추천대로 확정" 또는 일부 remap 후 확정 → `/api/hil/resume` 프록시 → FastAPI `/api/runs/{run_id}/hil_1/resume`.
  - 입력 (api): `Hil1ResumeRequest.corrections: dict[str, CorrectionItem]` (빈 dict 허용)
  - 처리:
    - api.py:320~322 — `corrections_payload = {k: {"wa": v.wa, "l6_main": v.l6_main} for ...}`
    - api.py:328~331 — `graph.ainvoke(Command(resume={"corrections": corrections_payload}), config={thread_id})`
    - graph.py:257~258 — `corrections_raw = interrupt(...) or {}`
    - graph.py:263~264 — `if set(corrections_raw)=={"corrections"}: corrections_raw = corrections_raw["corrections"] or {}`
    - graph.py:265 — `corrections = {int(k): v for k, v in corrections_raw.items()}`
  - 출력: `{"next_node": result["current_node"]}` (api.py:348) — 정상 통과 시 `atomizer` (interrupt 재발생 X)
  - 에러 (api): EmptyChannelError → 404, InvalidUpdateError → 409, current_node None → 500
- **관련**:
  - 호출자: `api.py:hil_1_resume` (api.py:298), FE `web/app/api/hil/resume/route.ts` (B_Track, 범위 밖 — waiting_hil_1 run 자동 선택 → FastAPI resume 프록시)
  - 페어: `hil_1_node` 본체 카드 (위)
  - 테스트: `pipeline/tests/test_api_hil1_resume.py` — `test_hil1_resume_preserves_string_key_in_command_resume` 가 `set(cmd.resume)=={"corrections"}` + 내부 key str 유지 계약 검증 (test:192~197)
- **Suspected related** (2026-06-01):
  - `api.py:hil_1_resume` (api.py:298) — truthy 래퍼 생성 source
  - FE `web/app/api/hil/resume/route.ts` + `web/app/(app)/review/page.tsx` (B_Track, 범위 밖이나 hint — "모두 AI 추천대로 확정" 게이트가 빈 corrections 호출 = 본 fix 가 막는 케이스)
  - deep_dive_orchestration.md §13.2 #M5 (✅ fixed) — HIL 2 재도입 시 동일 패턴 적용 권장

---

### `hil_2_node` — risky 그룹 사전 영속 + F5/F7 정정 + cross-company retrieve + interrupt

- **위치**: `pipeline/graph.py:308-416` (109 LOC)
- **시그니처**: `async def hil_2_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - 주석 (graph.py:309~320): "Forecaster 직후 — risky (주의/이상) 그룹별 degradation + recovery 사전 영속 + interrupt" / "Spec §8.2 (F5 정정 — coll.get 1회 + F7 정정 — None 분기)" / "retrieve.fetch_* 호출은 본 노드 책임 (agent.py 는 import X — 결정 #8 / Task 6 test 6.5)" / "Chroma coll.get(...) 그룹당 1회만 호출 후 metadatas/documents 두 함수 (degradation/recovery) 에 전달 (round-trip 절감)" / "baseline None 또는 main_unit None 일 때 cold_start signal payload 박고 다음 그룹"
  - **본 cycle 변경 (2026-05-22, graph.py:353~354 주석)**: `coll.get(where={"l6_main": r["l6_main"]})` — 이전 `$and [company, l6_main]` → `l6_main` 만 매칭. **company hard filter 제거**. 합성 3사 외 75사가 case=0 cold_start fallback 빠지던 회귀 해소. `fetch_degradation_cases` / `fetch_recovery_trajectory` 호출 시 company 인자 `None` 전달 (graph.py:380, 390).
- **설계 의도**:
  - F5 정정: Chroma `coll.get()` 그룹당 1회만 호출 → metadatas + documents 를 `fetch_degradation_cases` + `fetch_recovery_trajectory` 두 함수에 전달 (round-trip 절감)
  - F7 정정 (graph.py:362~375): baseline_value=None → `pre_cases[key]=[]` + cold_start_no_baseline signal payload
  - cross-company retrieve (2026-05-22): l6_main 만 매칭 → 합성 외 BP사도 가까운 case 1개 이상 노출
  - resume payload: `Command(resume=[group_key, ...])` — selection list 직접 (str list)
  - risky 0건 → interrupt 미발생, empty selection 반환 → conditional_edge 가 reporter 분기
- **대응 패턴 (시그니처)**:
  - 발동 조건: `forecaster → hil_2` (graph.py:620). `risky = [r for r in state["forecast"] if r["risk_level"] in {"주의", "이상"}]` 1건 이상.
  - 입력: state["forecast"] (risky 분류 포함)
  - 처리:
    - risky 0건 분기 (graph.py:321~323) — empty selection 반환 → reporter
    - risky 그룹 iterate (graph.py:335~409)
    - baseline_unit None (graph.py:338~350) — `no_main_unit` signal
    - Chroma `coll.get()` 1회 호출 (graph.py:355~358, F5, **company filter 제거**)
    - `_group_baseline` → None 분기 (graph.py:361~375, F7) → cold_start payload
    - `fetch_degradation_cases` + `fetch_recovery_trajectory` (graph.py:377~397, 각 case 마다, cross-company)
    - `pre_cases[key] = cases`
    - `interrupt({"risky_groups": payload_groups})` (graph.py:411) → `selected = ... or []`
  - 출력: `{"hil_2_selection": [keys], "pre_optimizer_cases": dict, "current_node": "hil_2"}`
- **관련**:
  - 호출자: `build_graph` forecaster → hil_2 → (optimizer \| reporter)
  - 페어: `retrieve.py.fetch_degradation_cases` + `fetch_recovery_trajectory`
  - 테스트: `test_graph_e2e_hil2.py` 4 path (interrupt_payload / resume_optimizer / skip_no_risky / resume_empty_selection)
- **Suspected related** (2026-05-26):
  - `optimizer/agent.py.optimize` — `pre_optimizer_cases` 재활용 (결정 #8)
  - `scripts/run_one_cycle.py` — HIL 2 auto-select 로직 (HIL 2 에는 env-level AUTO_BYPASS 없음 — issue #M4)
  - `optimizer/retrieve.py._group_baseline` — None 판정 룰

---

### `reporter_node` — 종합 보고서 + G8/G2 + site_id PG fallback + pipeline_runs status='completed' UPDATE

- **위치**: `pipeline/graph.py:444-490` (47 LOC)
- **시그니처**: `async def reporter_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - git log: `22d44c2 feat(reporter): Mapper+Forecaster+Optimizer 종합 보고서 + PG daily_reports`
  - 주석 (graph.py:445~448): "Mapper + Forecaster + Optimizer 결과 종합 보고서 생성 + PG INSERT" / "hil_2_selection=[] (Optimizer skip) 또는 risky 0건 path 에서도 본 노드 진입" / "mapped empty → fallback MD + PG INSERT skip"
  - **본 cycle 변경 (2026-05-20 Issue B fix, graph.py:479~486)**: `UPDATE pipeline_runs SET status='completed', completed_at=NOW() WHERE run_id=$1` 추가. 이전엔 reporter 종료 후에도 status='running' / completed_at=NULL 잔존 (cycle 7차 발견). 주석 graph.py:479~481 명시.
- **설계 의도**:
  - 최종 노드 — 모든 cycle 종료 (build_graph + build_demo_graph + build_atomized_demo_graph 셋 다)
  - **G8 sites.last_run_id 갱신** (graph.py:473) + **G2 hours_saved_cum 누적** ((120-5)/60 × atomized_count 시간, graph.py:474~478)
  - **state.site_id PG fallback** (graph.py:467~471): state 가 site_id 를 propagate 안 한 경우 `SELECT site_id FROM pipeline_runs WHERE run_id=$1` 직접 fetch
  - **status UPDATE (graph.py:482~486)**: graph 종료 시 status='running' 잔존 회귀 해소
- **대응 패턴 (시그니처)**:
  - 발동 조건: `optimizer → reporter` (graph.py:626) 또는 `hil_2 → reporter` (graph.py:621~625, hil_2_selection 비어있음).
  - 입력: state["mapped"] + state["forecast"] + state["optimizer_advice"] + state["atomized_ids"] + state.get("site_id")
  - 처리:
    - `report()` (graph.py:452~459) — report_md + summary
    - PG: `insert_daily_report` (reporter.py 내부)
    - site_id PG fallback (graph.py:467~471)
    - `update_site_last_run` (G8) + `update_site_hours_saved_cum` (G2, atomized_count 기반)
    - `UPDATE pipeline_runs SET status='completed', completed_at=NOW()` (graph.py:482~486)
  - 출력: `{"report_md": "...", "current_node": "reporter", "status": "completed"}`
- **관련**:
  - 호출자: optimizer \| hil_2 → reporter → END
  - 페어: `reporter.py.report`
  - PG: `db.py.insert_daily_report` / `update_site_last_run` / `update_site_hours_saved_cum` + raw SQL UPDATE
- **Suspected related** (2026-05-26):
  - `optimizer.view_builder` — daily_reports JSONB view 8 개 사전 적재
  - `db.py.upsert_daily_report_view_col` — view jsonb 적재 페어
  - api.py `/status` — status 가 reporter 종료 시 'completed' 로 정확히 박힘

---

### `optimizer_node` — Selected group advice + early return 제거 + site_id/mapped pass-through

- **위치**: `pipeline/graph.py:419-441` (23 LOC)
- **시그니처**: `async def optimizer_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - 결정 #8 (spec): retrieve 책임은 hil_2_node, optimize 는 LLM 만
  - **본 cycle 변경 (2026-05-20, graph.py:424~430 주석)**: 이전 `if not state.get("hil_2_selection"): early return` 제거. risky 0 cycle 도 view_builder 산출 진입 보장. `optimize()` 안에서 hil_2_selection 빈 → advice_rows=[] 진행. site_id+mapped 도 pass-through — `agent.py:175` 의 `if site_id:` block 진입 보장 → daily_reports 9 jsonb 채워짐 (cycle 7차 issue A root cause fix).
- **설계 의도**:
  - conditional_edge 가 hil_2_selection 비어있으면 reporter 직진 → 본 노드 진입 자체 X (build_graph 의 default path)
  - 단, build_demo_graph / build_atomized_demo_graph 같은 변형에서도 view 산출은 필요 → optimize() 안에서 빈 selection 도 받아들이도록 책임 이동
  - 진입 시 pre_optimizer_cases 재활용 (retrieve 재호출 X)
- **대응 패턴 (시그니처)**:
  - 발동 조건: `hil_2 → optimizer` conditional (graph.py:621~625, hil_2_selection truthy).
  - 입력: state["forecast"] + state["hil_2_selection"] + state["pre_optimizer_cases"] + state.get("site_id") + state.get("mapped")
  - 처리: `optimizer.agent.optimize(forecast, selection, pre_cases, run_id, today, cfg.optimizer, site_id=..., mapped=...)` (graph.py:431~440)
  - 출력: `{"optimizer_advice": [...], "current_node": "optimizer"}`
- **관련**:
  - 호출자: `build_graph` hil_2 → optimizer (conditional)
  - 페어: `optimizer/agent.py.optimize`
- **Suspected related** (2026-05-26):
  - `hil_2_node` — pre_optimizer_cases 의 source
  - `optimizer.view_builder` — site_id+mapped 가 진입 보장하는 9 jsonb 산출 block

---

### `forecaster_node` — RAG + Plan fallback 진단

- **위치**: `pipeline/graph.py:301-305` (5 LOC)
- **시그니처**: `async def forecaster_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - **본 cycle 변경**: 노드 코드 자체는 변경 0. 단, agent 내부 (`forecaster/agent.py`) 에서 `get_llm_semaphore()` (★ NEW `1e24dc6`) 를 사용하기 시작 — LLM 호출 패턴이 `async with get_llm_semaphore(): await to_thread(...)` 로 통일.
- **설계 의도**:
  - 그룹별 (company, l6_main) 생산성 진단
  - RAG (Chroma daily_activities) 우선, 부족 시 Plan fallback (PG forecasts)
- **대응 패턴 (시그니처)**:
  - 발동 조건: `atomizer → forecaster` (graph.py:619). 무조건.
  - 입력: state["mapped"] (atomizer 결과 idempotent)
  - 처리: `forecast(state["mapped"], run_id, today, cfg.forecaster)` (graph.py:304)
  - 출력: `{"forecast": [...], "current_node": "forecaster"}`
- **관련**:
  - 호출자: `build_graph` / `build_demo_graph` / `build_atomized_demo_graph` 모두 진입
- **Suspected related** (2026-05-26):
  - `hil_2_node` — risky 분류 input
  - `get_llm_semaphore` — agent 내부 동시성 (issue #L4)

---

### `atomizer_node` — Chroma daily_activities INSERT + ID 반환

- **위치**: `pipeline/graph.py:294-298` (5 LOC)
- **시그니처**: `async def atomizer_node(state: CPIAState, cfg: GraphConfig) -> dict`
- **이슈**:
  - **본 cycle 변경**: 노드 코드 자체 변경 0. `atomize()` 내부에서 `get_llm_semaphore()` 사용. `build_atomized_demo_graph` (★ NEW) 가 본 노드를 START 직후 entry 로 사용 → `assert_pipeline_run_exists` fail-fast 가 호출자 책임 (Medium issue #M3).
- **설계 의도**:
  - 임베딩만 (LLM 호출 X — 임베딩 SDK 만)
  - 멱등성 dedupe — deterministic hash
- **대응 패턴 (시그니처)**:
  - 발동 조건: `hil_1 → atomizer` (graph.py:618) 또는 `START → atomizer` (build_atomized_demo_graph, graph.py:562).
  - 입력: state["mapped"] + state["parsed"]
  - 처리: `atomize(mapped, parsed, run_id, cfg.atomizer)` (graph.py:297)
  - 출력: `{"atomized_ids": [...], "current_node": "atomizer"}`
- **관련**:
  - 호출자: `build_graph` hil_1 → atomizer → forecaster, `build_atomized_demo_graph` START → atomizer
- **Suspected related** (2026-05-26):
  - `reporter_node` — atomized_count 기반 G2 산식
  - `assert_pipeline_run_exists` — `build_atomized_demo_graph` 진입 시 fail-fast (issue #M3)

---

### `collector_node` ★ NEW — D-12 graph 진입 노드

- **위치**: `pipeline/agents/collector_node.py:16-63` (48 LOC)
- **시그니처**: `async def collector_node(state: CPIAState) -> dict[str, Any]`
- **이슈**:
  - git log: D-12 `55cad90 feat(graph): collector_node 진입점 — listener 박은 input_files 검증 + meta 분해`
  - 신설 cycle: `5347966` + `973fa66` + `85155eb` 의 collector 분리 작업과 함께. spec `docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md §6.5`.
  - 주석 (collector_node.py:17~26): "첨부 경로 검증 + filename_parser → state 메타 박기 + collector_inbox UPDATE" / "선행 (listener): collector_inbox INSERT(parse_status=pending) 완료" / "본 노드 책임 (Spec §6.5): 1) 경로 존재 검증 2) filename_parser 분해 3) message_id+postgres_url 있으면 UPDATE(running, run_id) — CLI 진입 시 message_id absent → skip 4) mapper 가 쓸 메타 반환"
  - **fail-fast 3 종**: `RuntimeError` (input_files 빈) / `FileNotFoundError` (경로 부재) / `ValueError` (파일명 규약 불일치). dead_letter 처리는 listener (`idle_worker._to_dead_letter`) 측 책임 — graph 진입 전에 거름.
- **설계 의도**:
  - **D-12 single source of truth**: 이전엔 listener 가 date/bp_name 분해까지 했음. D-12 에서 listener 는 path/메타-trigger 만 박고, 분해는 본 노드가 담당.
  - **CLI vs IDLE 진입 양립**: `message_id` 가 state 에 있으면 (IDLE listener path) `collector_inbox` UPDATE(running). 없으면 (CLI / main.py 진입) skip — UPDATE 는 IDLE path 한정.
  - **listener UPDATE 중복**: listener 의 `run_for_attachment` 도 같은 UPDATE 를 호출 (idle_worker.py:105) — idempotent 라 functional 영향 없으나 PG round-trip 1회 낭비 (issue #L2).
- **대응 패턴 (시그니처)**:
  - 발동 조건: `START → collector` (graph.py:614). 무조건.
  - 입력: state["input_files"][0] + state.get("message_id")? + state.get("postgres_url")? + state["run_id"]
  - 처리:
    - 경로 검증 (collector_node.py:27~32) — input_files 빈 / 부재 시 raise
    - `parse_filename(path.name)` (collector_node.py:33) — None 이면 raise
    - message_id+postgres_url 있으면 `update_collector_inbox_status(pg, message_id, run_id, parse_status="running")` (collector_node.py:39~51)
  - 출력: `{"bp_name": meta.bp_name or "_integrated", "date": meta.date, "project": meta.project}`
- **관련**:
  - 호출자: `build_graph` START → collector → parser (graph.py:614~615)
  - 페어: `pipeline.collector.filename_parser.parse_filename` + `pipeline.db.update_collector_inbox_status`
  - listener: `pipeline.collector.idle_worker.run_for_attachment` (입력 state 의 4 신규 키 박는 쪽)
  - 테스트: `pipeline/tests/test_collector_node.py` (70 LOC)
- **Suspected related** (2026-05-26):
  - `pipeline/collector/idle_worker.py.run_for_attachment` — `message_id`+`postgres_url` 박는 source
  - `pipeline/agents/collector.py` (legacy `discover_daily_reports` + `collect_and_parse`) — 본 노드와 무관한 dir-scan path (issue #M2)

---

### `parser_node` ★ NEW — async N병렬 multi-file concat merge graph 노드

- **위치**: `pipeline/agents/parser_node.py:40-64` (async `parser_node`) + `pipeline/agents/parser_node.py:18-37` (`_merge_reports`)
- **시그니처**: `async def parser_node(state: CPIAState) -> dict[str, Any]`
- **이슈**:
  - git log:
    - D-12 신설 — `6b9db7c fix(state): parsed_reports → parsed, report_date → date drift fix`. 이전엔 mapper 가 직접 parser 호출했으나, D-12 부터 graph 노드로 분리 + state 키 통일.
    - `a8d17e4 feat(graph): multi-file async parser merge + hil_1 resume falsy-fix` (2026-06-01) — sync 단일파일 래퍼 → async N병렬 multi-file merge.
  - 주석 (parser_node.py:15, 43~45): "_PARSE_CONCURRENCY = 4 — 파일 단위 병렬 (sync parse 를 to_thread 로 wrap — 이벤트 루프 block 회피)" / "sync parse_daily_report 를 asyncio.to_thread 로 wrap (Semaphore 4) — 이벤트 루프를 block 하지 않음"
  - **이전 sync → async 전환 (`a8d17e4`, 옛 issue #L5 해소)**: D-12 초기엔 `def parser_node(...)` sync 가 `input_files[0]` 단일 파일만 파싱. multi-file PoC 에서 sync 10개 순차 파싱(~30-50초) 이 FastAPI 전체 hang 유발 (spec §2 PoC ⚠️) → `async def parser_node(...)` + `to_thread` Semaphore 4 로 전환. `build_graph` 의 wrapper `_parser_p` (graph.py:595~598) 도 `return await _parser(state)` 로 await 추가 (옛 "parser_node 는 sync" 가정 제거).
- **설계 의도**:
  - **multi-file concat merge**: `input_files` 전체 (업체별 작업일보 N개) 를 async 병렬 파싱 후 `_merge_reports` (parser_node.py:18) 로 1 통합 `ParsedDailyReport` 로 concat → 1 run. 각 업체가 다른 작업을 한다는 전제로 activities/bp_summaries/job/equip/worker_outputs 를 단순 이어붙이고, report_meta 는 첫 업체(site 대표) 것을 쓴다 (`report_date` 불일치 시 WARN 로그만, graph 흐름 계속).
  - **mapper/atomizer/forecaster/optimizer/reporter 무변경**: parser_node 만 N개 merge → 하류는 통합 데이터를 단일 run 으로 진단/출력 (사용자 승인 설계, spec §2).
  - **이벤트 루프 non-block**: sync `parse_daily_report` 를 `asyncio.to_thread` 로 wrap (Semaphore 4) — mapper~ 진행 중에도 FastAPI 의 다른 요청(게이지 polling 등)이 응답.
  - **state-key drift fix (D-12)**: `parsed_reports` → `parsed` 단일 이름 정착.
- **대응 패턴 (시그니처)**:
  - 발동 조건: `collector → parser` (graph.py:645). 무조건. `_parser_p` wrapper 가 `await _parser(state)`.
  - 입력: state["input_files"] (전체 — 1번째만 아님)
  - 처리:
    - `files = [Path(f) for f in state["input_files"]]` + `sem = asyncio.Semaphore(4)` (parser_node.py:50)
    - `_parse_one(p)` — `async with sem: await asyncio.to_thread(parse_daily_report, p)` (parser_node.py:52~54)
    - `reports = await asyncio.gather(*[_parse_one(p) for p in files])`
    - `merged = _merge_reports(reports)` (parser_node.py:57)
  - 출력: `{"parsed": merged}` (parser_node.py:64) — merged 는 통합 `ParsedDailyReport`
  - 에러: input_files 빈 → `RuntimeError`. 그 외 `parse_daily_report` 자체 raise. LangGraph 미처리 시 status='failed'.
- **관련**:
  - 호출자: `build_graph` collector → parser → mapper (graph.py:645~646), wrapper `_parser_p` (graph.py:595~598)
  - 페어: `pipeline.agents.parser.parse_daily_report` (rule-based + LLM 검증 wrapper)
  - 테스트: `pipeline/tests/test_parser_node.py`
- **Suspected related** (2026-06-01):
  - `mapper_node` (graph.py:57) — `state["parsed"]` consumer (merged ParsedDailyReport)
  - `_merge_reports` (parser_node.py:18) — concat 페어
  - `CPIAState.parsed` annotation drift (issue #C2) — annotation 은 `list[Activity]` 이나 실제 `ParsedDailyReport` 들어감

---

### `build_graph` — production topology (collector→parser→...→reporter + exporter dual-END)

- **위치**: `pipeline/graph.py:578-660` (83 LOC)
- **시그니처**: `def build_graph(cfg: GraphConfig) -> CompiledGraph`
- **이슈**:
  - **`55cad90`**: 7-노드 → 9-노드. START → **collector → parser** → mapper → hil_1 → atomizer → forecaster → hil_2 → (optimizer\|reporter) → END. 신규 노드 2 개 (`_collector` / `_parser`) 가 graph 앞단에 추가됨 (graph.py:634~635 add_node + graph.py:644~646 add_edge).
  - **`2c2e4a6` (D-3/D-8)**: atomizer fan-out + exporter dual-END — `atomizer → exporter` + `atomizer → forecaster`, `exporter → END` (graph.py:649~651). 본 노드 (`_exporter` = `consolidated_xlsx_node`, graph.py:614~616) 는 fault isolation 으로 예외 silent skip (spec §★UPDATE — exporter 범위 밖).
  - **본 cycle 변경 (`a8d17e4`, graph.py:595~598)**: `_parser_p` wrapper 가 async `parser_node` 를 `return await _parser(state)` 로 await (이전 sync 가정 제거). "parser_node 는 sync" 옛 주석 삭제됨.
  - conditional_edges (hil_2 → optimizer \| reporter) 유지 (graph.py:653~657).
- **설계 의도**:
  - **D-12 진입점 이동의 결과**: 이전엔 listener 가 graph 호출 전에 path 검증 + 메타 분해 + collector_inbox UPDATE 다 했음. D-12 에서 listener 는 path/메타-trigger 만 박고 분해는 graph 안 `collector_node` 가 담당 (single source of truth) → graph 자체가 "수신 → 파싱 → 매핑 → 진단 → 보고" 전체 lifecycle 을 표현.
  - **build_graph 가 production path**: 모든 IDLE listener 호출이 본 builder 결과를 사용 (`idle_worker.run_for_attachment` 의 `build_graph(cfg.graph_cfg)` 지연 import — graph.py:98).
  - conditional_edge:
    ```python
    lambda s: "optimizer" if s.get("hil_2_selection") else "reporter"
    ```
- **대응 패턴 (시그니처)**:
  - 발동 조건: api.py lifespan startup 또는 listener fire-and-forget 시 1회 호출 (CompiledGraph 캐시).
  - 입력: cfg (GraphConfig)
  - 처리: `StateGraph(CPIAState)` 인스턴스 → `add_node` × 10 (collector/parser/mapper/hil_1/atomizer/exporter/forecaster/hil_2/optimizer/reporter) + `add_edge` (START→collector→parser→mapper→hil_1→atomizer, atomizer fan-out → exporter‖forecaster, exporter→END, forecaster→hil_2, optimizer→reporter→END) + `add_conditional_edges` × 1 (hil_2) → `compile(checkpointer=build_checkpointer())`
  - 출력: CompiledGraph (PostgresSaver 또는 InMemorySaver checkpointer 포함)
- **관련**:
  - 호출자: `scripts/run_one_cycle.py`, FastAPI `api.py` (lifespan app.state.graph), `idle_worker.run_for_attachment` (지연 import)
  - 페어: `build_demo_graph` (graph.py:496), `build_atomized_demo_graph` (graph.py:534)
- **Suspected related** (2026-05-26):
  - 모든 9 node 함수
  - `build_checkpointer` — compile 시점 checkpointer 결정

---

### `build_demo_graph` — Parser/Mapper/Atomizer skip (synthetic CLI 용)

- **위치**: `pipeline/graph.py:496-531` (36 LOC)
- **시그니처**: `def build_demo_graph(cfg: GraphConfig) -> CompiledGraph`
- **이슈**:
  - **본 cycle 변경**: 코드 변경 없음. 단, ★ NEW `build_atomized_demo_graph` 가 추가되어 "데모/백필" 카테고리에 형제 builder 가 생김.
- **설계 의도**:
  - topology: `forecaster → hil_2 → (optimizer \| reporter) → END`
  - state["mapped"] 사전 주입 가정 (synthetic_daily_report.py CLI 또는 test fixture)
  - 데모/PoC 빠른 시연 path
- **대응 패턴 (시그니처)**:
  - 입력: cfg (GraphConfig)
  - 처리: 4 노드 (forecaster / hil_2 / optimizer / reporter) + conditional_edge
  - 출력: CompiledGraph
- **관련**:
  - 호출자: `synthetic_daily_report.py` CLI, `test_synthetic_daily_report.py` E2E
  - 페어: `build_graph` (production), `build_atomized_demo_graph` (15일 backfill)
- **Suspected related** (2026-05-26):
  - `optimizer/synthetic_daily_report.py` — 본 함수의 유일한 production 호출자 (test 외)

---

### `build_atomized_demo_graph` ★ NEW — 15일 backfill 표준 graph

- **위치**: `pipeline/graph.py:534-575` (42 LOC)
- **시그니처**: `def build_atomized_demo_graph(cfg: GraphConfig) -> CompiledGraph`
- **이슈**:
  - git log: `ef95e02` (2026-05-22, Plan B6) — mapper/hil_1 만 skip. mapped 는 호출자가 PG `mapper_activities` 에서 hydrate 한 상태로 진입. 15일 backfill 의 표준 graph.
  - 주석 (graph.py:531~538): "START -> atomizer -> forecaster -> hil_2 -> (optimizer \| reporter) -> END" / "2026-05-22 (Plan B6) — mapper / hil_1 만 skip. mapped 는 호출자가 PG mapper_activities 에서 hydrate 해서 state['mapped'] 에 주입한 상태로 진입" / "pipeline_runs INSERT 도 호출자 책임 (atomizer.assert_pipeline_run_exists fail-fast)"
  - **Medium issue #M3**: 호출자가 `mapped` hydrate + `pipeline_runs` INSERT 모두 책임. 백필 스크립트마다 boilerplate 반복.
- **설계 의도**:
  - **mapper LLM 비용 회피**: 백필 시 mapper_activities 가 이미 PG 에 있으면 LLM 재호출 불필요 — hydrate 만 하고 atomizer 부터 시작.
  - **demo_graph vs atomized_demo_graph 분리**: demo_graph 는 atomizer 도 skip (state["atomized_ids"] 사전 주입), atomized_demo_graph 는 atomizer 만 진입 (실 Chroma 적재 필요).
- **대응 패턴 (시그니처)**:
  - 입력: cfg (GraphConfig). 호출자가 state["mapped"] (hydrated) + state["run_id"] (pipeline_runs INSERT 완료) 주입.
  - 처리: 5 노드 (atomizer / forecaster / hil_2 / optimizer / reporter) + conditional_edge
  - 출력: CompiledGraph
- **관련**:
  - 호출자: 15일 backfill 스크립트 (별도 `scripts/` 모듈)
  - 페어: `build_graph` (production 9 노드), `build_demo_graph` (4 노드)
  - 의존: `atomizer.assert_pipeline_run_exists` (fail-fast)
- **Suspected related** (2026-05-26):
  - `atomizer.assert_pipeline_run_exists` — 호출자 책임 강제 fail-fast
  - 향후 helper `prepare_atomized_run(run_id, site_id, date, mapped_rows)` (issue #M3)

---

### `_build_review_needed` — interrupt payload 9 필드

- **위치**: `pipeline/graph.py:177-195` (19 LOC)
- **시그니처**: `def _build_review_needed(mapped: list[Activity]) -> list[dict]`
- **이슈**:
  - **본 cycle 변경**: 코드 변경 없음. 본 cycle hil_1_node 의 falsy-resume fix 도 본 helper 영향 없음.
- **설계 의도**:
  - requires_review=True 행 만 9 필드 (idx, work_content, company, trade, wa, l6_main, mapping_conf, mapping_source) extraction
  - FE review modal 의 input 최소화 (Activity 33 필드 중 9개만)
- **대응 패턴 (시그니처)**:
  - 입력: mapped (Activity list)
  - 처리: list comprehension — `requires_review=True` filter → 9 필드 dict 변환
  - 출력: list[dict]
- **관련**:
  - 호출자: hil_1_node (graph.py:243)
- **Suspected related** (2026-05-26):
  - `_apply_corrections` — 본 함수와 페어
  - FE `MappingReviewModal.tsx` — 9 필드 schema 의 consumer

---

### `_apply_corrections` — corrections 적용 + metadata 갱신

- **위치**: `pipeline/graph.py:198-230` (33 LOC)
- **시그니처**: `def _apply_corrections(mapped: list[Activity], corrections: dict[int, dict]) -> list[Activity]`
- **이슈**:
  - **본 cycle 변경**: 코드 변경 없음.
- **설계 의도**:
  - HIL 1 corrections 적용 — mapping_source="user_corrected" + requires_review=False 강제
  - 답 안 한 row (review_needed 였으나 corrections 에 없음) 는 Mapper 추천 그대로 수용 + 같은 metadata 강제 (재시도 X — PoC 기본)
- **대응 패턴 (시그니처)**:
  - 입력: mapped + corrections (dict[int, dict])
  - 처리: iterate corrections → Activity 의 wa/l6_main/source/review 갱신 (TypedDict spread)
  - 출력: list[Activity]
- **관련**:
  - 호출자: hil_1_node (graph.py:267)
- **Suspected related** (2026-05-26):
  - `_build_review_needed` — 본 함수의 input 원천
  - `insert_mapping_correction` — 본 함수 후 PG INSERT

---

### `CPIAState` — LangGraph 전체 상태 (20 필드, 본 cycle +4)

- **위치**: `pipeline/state.py:226-265` (40 LOC)
- **시그니처**: `class CPIAState(TypedDict)`
- **이슈**:
  - git log: `6b9db7c fix(state): parsed_reports → parsed, report_date → date drift fix` + D-12 4 신규 키 추가.
  - 주석 (state.py:260~265): "D-12 — collector_node / parser_node 산출 + listener invoke 인자. `parsed` / `date` / `site_id` / `input_files` 는 위에 이미 정의됨 — collector/parser 가 같은 키로 박음"
  - **본 cycle 변경 (D-12)**: 4 신규 키 — `bp_name` / `project` / `message_id` / `postgres_url`.
  - **Critical issue #C2 (state.py:237 drift)**: annotation 은 `parsed: list[Activity]` 이나 실제는 `ParsedDailyReport`. mapper_node (graph.py:62) 가 명시적으로 `ParsedDailyReport` 로 캐스팅 — IDE 타입체크 우회.
  - **Low issue #L1**: `raw_texts: dict[str, str]` (state.py:236) 필드 정의되어 있으나 어떤 노드도 채우거나 읽지 않음.
- **설계 의도**:
  - **입력**: run_id, date, input_files, site_id (PG fallback 용)
  - **누적**: raw_texts (미사용), parsed, mapped, hil_1_corrections, atomized_ids
  - **분기**: report_md, forecast, hil_2_selection, pre_optimizer_cases, optimizer_advice
  - **상태 추적**: current_node, status ∈ {running, waiting_hil_1, waiting_hil_2, completed, failed}
  - **D-12 신규 (4)**: bp_name (파일명 분해), project (파일명 prefix), message_id (listener invoke 시 박힘, CLI 진입 시 absent), postgres_url (collector_node 가 collector_inbox UPDATE 용)
- **관련**:
  - 모든 노드의 입출력
  - PostgresSaver thread_id 영속 (checkpointer)
- **Suspected related** (2026-05-26):
  - `Activity` (state.py:32) — mapped 의 element type
  - `ParsedDailyReport` — `parsed` 필드 실제 타입 (annotation drift)
  - `idle_worker.run_for_attachment` (idle_worker.py:120~127) — D-12 4 신규 키 박는 source

---

### `Activity` — 작업일보 시트4 매핑 단위 (33 필드)

- **위치**: `pipeline/state.py:32-93` (62 LOC)
- **이슈**:
  - **본 cycle 변경**: 필드 수 변경 0 (이전 cycle 16 신규 필드 추가는 그대로 유지).
  - PoC 제약: wbs_activity_id / l7_sub / l7_5_activity / sub_work_area 항상 None (Master List 1:N)
  - deep_dive_orchestration.md §6 분석: 실 TypedDict 필드 30~33 개 — docstring 의 "44 필드" 는 sub-필드까지 포함한 카운트.
- **설계 의도**:
  - 시트4 원천 필드 (Parser 채움) + WBS 매핑 (Mapper) + 분배 결과 (`_prorate_mh`) + HIL 1 플래그
  - 5 카테고리:
    1. 시트4 원천 17 필드 (zone/bp_code/company/scope/trade/work_content/unit/qty 6 필드/note 등)
    2. 업체별 일보 추가 4 필드 (work_location_code, wbs_mid/sub/detail_name)
    3. WBS 매핑 9 필드 (wbs_activity_id/l5_disc/l6_main/.../wa/mapping_conf/mapping_source/requires_review)
    4. _prorate_mh 분배 3 필드 (assigned_workers / worker_source / plan_mh)
- **관련**:
  - 모든 노드 통과 (mapper → atomizer → forecaster → optimizer → reporter)
- **Suspected related** (2026-05-26):
  - `mapper.py.map_activity` — wa/l6_main/conf/source/review 채움
  - `mapper.py._prorate_mh` — assigned_workers/plan_mh 채움

---

### `_LazyAsyncPostgresSaver` — LangGraph checkpoint lazy pool

- **위치**: `pipeline/checkpointer.py:30-75` (46 LOC)
- **시그니처**: `class _LazyAsyncPostgresSaver(AsyncPostgresSaver)`
- **이슈**:
  - **본 cycle 변경**: 코드 변경 없음.
  - 주석 (checkpointer.py:1~19): "build_checkpointer 는 sync 함수 — AsyncConnectionPool 의 await pool.open() 을 직접 호출 못 함. 따라서 _LazyAsyncPostgresSaver (AsyncPostgresSaver 상속) 가 첫 async method 호출 시 자동 pool.open() 처리" / "LangGraph 의 isinstance(checkpointer, BaseCheckpointSaver) 검사를 위해 base class 상속"
  - **Low issue #L6 (race)**: `_ensure_open` 에 `asyncio.Lock` 없음. 첫 호출이 2 concurrent 면 pool.open() 2회 호출 가능 — psycopg_pool 이 자체 idempotent 라고 알려졌으나 contract 보장 X.
- **설계 의도**:
  - `AsyncConnectionPool(open=False)` 를 sync __init__ 에서 생성 → 첫 async 메서드 (aput/aget_tuple/aput_writes/alist/aget) 시 `_ensure_open()` 으로 lazy `await pool.open()`.
  - `kwargs={"autocommit": True}` + `max_size=10`.
- **대응 패턴 (시그니처)**:
  - 발동 조건: `build_checkpointer()` 가 `POSTGRES_URL` 설정 + `CPIA_CHECKPOINTER != memory` 시 인스턴스화.
  - 입력: postgres_url
  - 처리: __init__ — pool 만 생성 (open=False), 5 async 메서드 모두 `_ensure_open` 후 super() 위임.
  - 출력: BaseCheckpointSaver 인스턴스 (PG 기반)
- **관련**:
  - 호출자: `build_checkpointer` (checkpointer.py:94)
  - 페어: `build_graph` / `build_demo_graph` / `build_atomized_demo_graph` 모두 `compile(checkpointer=build_checkpointer())` 호출
- **Suspected related** (2026-05-26):
  - `psycopg_pool.AsyncConnectionPool` — pool 생성/close 정책
  - `langgraph.checkpoint.postgres.aio.AsyncPostgresSaver` — base class

---

### `build_checkpointer` — env 분기 (memory vs postgres)

- **위치**: `pipeline/checkpointer.py:78-94` (17 LOC)
- **시그니처**: `def build_checkpointer() -> BaseCheckpointSaver`
- **이슈**:
  - **본 cycle 변경**: 코드 변경 없음.
- **설계 의도**:
  - InMemorySaver 분기 2 가지:
    1. `CPIA_CHECKPOINTER=memory` 명시 (Phase 1 호환, 개발/테스트용)
    2. `POSTGRES_URL` 미설정 (안전 fallback)
  - 그 외 → `_LazyAsyncPostgresSaver` (PG 기반).
- **대응 패턴 (시그니처)**:
  - 입력: 환경 변수 (`CPIA_CHECKPOINTER`, `POSTGRES_URL`)
  - 처리: env 체크 → 분기
  - 출력: `InMemorySaver` 또는 `_LazyAsyncPostgresSaver`
- **관련**:
  - 호출자: 3 builder (graph.py:528, 572, 628)
- **Suspected related** (2026-05-26):
  - `_LazyAsyncPostgresSaver`
  - `InMemorySaver` (langgraph 기본)

---

### `collector_node` (이미 위에 카드 작성됨 — 중복 회피)

---

### `parser_node` (이미 위에 카드 작성됨 — 중복 회피)

---

### `get_llm_semaphore` ★ NEW — forecaster/optimizer/atomizer 공용 LLM 동시성

- **위치**: `pipeline/agents/_concurrency.py:15-18` (4 LOC)
- **시그니처**: `def get_llm_semaphore() -> asyncio.Semaphore`
- **이슈**:
  - git log: `1e24dc6 feat(agents): get_llm_semaphore() 공용 LLM 동시성 모듈`
  - 주석 (_concurrency.py:1~5): "LLM 동시성 제어 — forecaster + optimizer + atomizer 공유. env: CPIA_LLM_CONCURRENCY (기본 4). 사용: `async with get_llm_semaphore(): await asyncio.to_thread(azure_sync_call, ...)`" / "Lazy 생성 (event loop 별). 같은 loop 안에서는 같은 인스턴스가 자연스럽게 공유됨"
  - **Low issue #L4 (분리)**: mapper 는 `CPIA_MAPPER_CONCURRENCY` (graph.py:38), 그 외 agents 는 `CPIA_LLM_CONCURRENCY` (_concurrency.py:17) — 운영자 두 env 외워야 함. 명명 정합 미흡.
- **설계 의도**:
  - **Azure LLM rate-limit 공유**: forecaster / optimizer / atomizer 가 한 process 안에서 LLM 호출 시 같은 Semaphore 공유 → tokens-per-min 초과 회피.
  - **event loop 별 lazy**: 같은 loop 안에서 호출되면 같은 Semaphore 인스턴스 (asyncio 가 보장). 다른 loop (예: test) 에서 호출되면 다른 인스턴스.
- **대응 패턴 (시그니처)**:
  - 입력: env `CPIA_LLM_CONCURRENCY` (기본 4)
  - 처리: `Semaphore(max(1, n))` 반환 — 매 호출마다 새 인스턴스 (loop 별 캐시 X — event-loop 자체가 공유 단위)
  - 출력: `asyncio.Semaphore`
  - 호출 패턴: `async with get_llm_semaphore(): await asyncio.to_thread(azure_sync_call, ...)`
- **관련**:
  - 호출자 (agents/ 하위):
    - `forecaster/agent.py` — group 루프 + asyncio.gather
    - `optimizer/agent.py` — forecast 루프 + asyncio.gather
    - `atomizer.py` — batch embedding
- **Suspected related** (2026-05-26):
  - `graph.py:38` `_MAPPER_CONCURRENCY` — 별도 Semaphore (issue #L4)
  - `idle_worker.py:34` `_GRAPH_SEM` — graph invoke 동시성 (다른 layer)

---

### `idle_loop` ★ NEW — IMAP IDLE 무한 루프

- **위치**: `pipeline/collector/idle_worker.py:228-260` (33 LOC)
- **시그니처**: `async def idle_loop(cfg: CollectorConfig) -> None`
- **이슈**:
  - git log: `5347966 feat(collector): IMAP IDLE 푸시 트리거 + UNSEEN drain + dedup + dead_letter`
  - 주석 (idle_worker.py:228~229): "FastAPI startup background task. shutdown 까지 IDLE 유지 + reconnect"
  - **Low issue #L8 (shutdown timing)**: lifespan shutdown 시 `request_shutdown() → task.cancel()` 즉시 cancel — `idle_done()` 후처리 미완료 가능. `asyncio.wait_for(task, timeout=5)` 미적용.
- **설계 의도**:
  - **IMAP IDLE RFC 2177**: 29 분 timeout (서버 권장 30분 직전 갱신).
  - **시작 drain**: process restart 시 누적 UNSEEN 처리 (`_drain_new` 1회).
  - **EXISTS notification 기반 push**: polling 없이 서버가 push 할 때만 fetch — 부하 최소.
  - **지수 backoff**: `1.0 → 2.0 → ... → 60.0s` (cap 60s) — IMAP 연결 끊김 시 재연결.
  - **graceful exit**: `asyncio.CancelledError` 캐치 후 return (lifespan shutdown).
- **대응 패턴 (시그니처)**:
  - 발동 조건: FastAPI lifespan startup 안 `asyncio.create_task(idle_loop(collector_cfg))` (api.py:180~183).
  - 입력: CollectorConfig (host/port/user/app_password)
  - 처리:
    - while not _shutdown:
      - `aioimaplib.IMAP4_SSL` 연결 + `login` + `select("INBOX")`
      - `_drain_new(imap, cfg)` — 시작 시 누적 처리
      - inner while:
        - `imap.idle_start(timeout=29*60)`
        - `push_msg = await imap.wait_server_push()`
        - `imap.idle_done()`
        - if "EXISTS" in push_msg: `_drain_new`
      - CancelledError → graceful return
      - Exception → backoff sleep + reconnect
  - 출력: None (영속 task)
- **관련**:
  - 호출자: `api.py:180~183` (FastAPI lifespan)
  - 페어: `_drain_new` → `_process_one` → `run_for_attachment`
  - shutdown: `request_shutdown()` (idle_worker.py:37) — `_shutdown` Event set
- **Suspected related** (2026-05-26):
  - `aioimaplib.IMAP4_SSL` — RFC 2177 IDLE 구현
  - `api.py` lifespan finally — graceful cancel

---

### `run_for_attachment` ★ NEW — graph fire-and-forget per attachment

- **위치**: `pipeline/collector/idle_worker.py:90-150` (61 LOC)
- **시그니처**: `async def run_for_attachment(attachment_path, meta, site_id, message_id, cfg) -> None`
- **이슈**:
  - git log: `5347966` 와 함께 신설.
  - 주석 (idle_worker.py:97, 115~118): "semaphore 보호 + graph 1회 호출. 실패 시 collector_inbox.failed 박음" / "D-12: graph 진입점이 collector_node — listener 는 path/메타-trigger 만 박고 date/bp_name/project 분해는 collector_node 가 담당 (single source of truth). collector_inbox UPDATE(running) 도 collector_node 가 하므로 위쪽 명시적 UPDATE 는 listener 측 안전망 (graph 진입 전 사고 대비) — 중복 UPDATE 는 idempotent"
  - **Low issue #L2 (중복 UPDATE)**: listener 가 한 번 (idle_worker.py:105), collector_node 가 다시 한 번 (collector_node.py:44) UPDATE(running). idempotent 라 functional 영향 없으나 PG round-trip 1회 낭비.
  - **Medium issue #M4 (HIL 2 AUTO_BYPASS 없음)**: `idle_worker` path 에서는 HIL 2 interrupt 가 멈춤 — env-level 우회 없음. scripts/run_one_cycle.py 만 자체 auto-select.
- **설계 의도**:
  - **fire-and-forget per attachment**: 1 메일 = N 첨부 = N graph invoke. `_GRAPH_SEM` (`CPIA_COLLECTOR_CONCURRENCY=2`) 로 동시 graph 호출 2개 제한 (Azure rate-limit 보호).
  - **circular import 회피**: `from pipeline.graph import build_graph` 를 함수 내부에서 지연 import (idle_worker.py:98) — graph.py 가 collector 미참조라 module-level 가능하지만 명시적 안전.
  - **collector_inbox lifecycle**: pending (listener `_process_one`) → running (listener 안전망 + collector_node) → completed/failed (run_for_attachment 종료 후).
  - **D-12 state 박기**: `message_id` + `postgres_url` 박아서 collector_node 가 PG UPDATE 가능하도록.
- **대응 패턴 (시그니처)**:
  - 발동 조건: `_process_one` 안에서 첨부 1개당 `create_task(run_for_attachment(...))` (idle_worker.py:209).
  - 입력: attachment_path (Path), meta (ParsedFilename), site_id, message_id (sub_message_id), cfg (CollectorConfig)
  - 처리:
    - `async with _GRAPH_SEM` (idle_worker.py:100)
    - `update_collector_inbox_status(running)` (idle_worker.py:105~110)
    - `build_graph(cfg.graph_cfg)` + `graph.ainvoke({run_id, input_files, site_id, message_id, postgres_url}, config={thread_id})` (idle_worker.py:119~129)
    - 예외 → `update_collector_inbox_status(failed, error=...)` (idle_worker.py:135~140) → return
    - 성공 → `update_collector_inbox_status(completed)` (idle_worker.py:148)
  - 출력: None (fire-and-forget)
- **관련**:
  - 호출자: `_process_one` (idle_worker.py:209)
  - 페어: `build_graph` (graph.py:575, 지연 import)
  - PG: `update_collector_inbox_status` (3회 호출 — running/failed/completed)
- **Suspected related** (2026-05-26):
  - `collector_node` — message_id+postgres_url consumer (UPDATE 중복 issue #L2)
  - `hil_2_node` — listener path 에서 interrupt 시 멈춤 (issue #M4)
  - `_GRAPH_SEM` — 동시 graph invoke 2개 제한

---

### `load_collector_config` ★ NEW — env 9 종 → CollectorConfig fail-fast

- **위치**: `pipeline/collector/config.py:35-68` (34 LOC)
- **시그니처**: `def load_collector_config(graph_cfg: GraphConfig) -> CollectorConfig`
- **이슈**:
  - git log: `5347966` 와 함께 신설.
  - 주석 (config.py:36~43): "환경 변수에서 로드 — Spec §8.2 의 9 env" / "Spec §10 결정 (env-only, fail-fast): 자격증명 (USER / APP_PASSWORD) 은 코드에 default 없음. COLLECTOR_ENABLED=true 인데 USER 또는 APP_PASSWORD 가 비어있으면 RuntimeError. COLLECTOR_ENABLED=false 면 자격증명 누락 허용 (로컬 / 테스트 환경). host / port 는 운영 swap 편의를 위해 default 유지 (secrets 아님)"
  - **Medium issue #M2 (CollectorConfig 명명 충돌)**: 같은 이름 클래스 2개 (agents/collector.py:23 legacy 1 필드 + collector/config.py:15 신규 10 필드). 향후 import 충돌 위험.
- **설계 의도**:
  - **env-only, fail-fast**: 자격증명 코드 default 없음 — 환경 설정 누락을 코드 시작 시점에 fail.
  - **COLLECTOR_ENABLED 조건부 검사**: enabled=true 일 때만 USER/APP_PASSWORD 필수 — 로컬/테스트 환경 (enabled=false) 에서는 누락 허용.
  - **host/port default 유지**: secrets 아니라 운영 swap 편의 (`imap.gmail.com:993`).
  - **POSTGRES_URL 은 KeyError 전파**: `os.environ["POSTGRES_URL"]` — collector 외 영역에서도 필수라 별도 처리 안 함.
- **대응 패턴 (시그니처)**:
  - 발동 조건: `api.py:28` lifespan startup 1회 호출.
  - 입력: graph_cfg (GraphConfig — collector 가 graph build 시 필요)
  - 처리:
    - `_bool` 로 COLLECTOR_ENABLED 파싱
    - enabled=true + USER/APP_PASSWORD 미존재 → `RuntimeError` (config.py:47~56)
    - 9 env 로드 → `CollectorConfig(frozen=True)` 반환
  - 출력: `CollectorConfig` dataclass
- **관련**:
  - 호출자: `api.py:28` (lifespan startup)
  - 페어: `CollectorConfig` (config.py:15), `idle_loop(cfg)` consumer
- **Suspected related** (2026-05-26):
  - `agents/collector.py.CollectorConfig` (legacy 명명 충돌, issue #M2)
  - `api.py` lifespan — `load_collector_config(graph_cfg) → idle_loop(cfg) task`

---

## 이슈 표

### Critical (당장 fix 필요)

| ID | 영역 | 위치 | 설명 | 다음 행동 |
|---|---|---|---|---|
| #C1 | hil_1_node AUTO_BYPASS prod 가드 부재 | graph.py:240~248 | `CPIA_HIL_AUTO_BYPASS` env 가 검증/dev path 만 의도이나 prod env 에 실수로 박히면 모든 mapping_corrections 가 silent skip + low-conf 매핑이 user_corrected 로 둔갑. env 검사 시 stderr 경고만 — 로그 grep 안 하면 안 잡힘 | (a) api.py lifespan 에서 prod 환경 + AUTO_BYPASS=true 조합 시 WARN log + sentry, (b) sites 메타에 prod flag 추가하여 hil_1_node 에서 cross-check |
| #C2 | CPIAState.parsed 타입 annotation drift | state.py:237 | annotation 은 `list[Activity]` 이지만 실제는 `ParsedDailyReport` (parser_node.py:25 return + mapper_node graph.py:62 캐스팅). IDE 타입체크 우회. drift detection 안 됨 | annotation 을 `parsed: ParsedDailyReport` 로 수정 (mypy/pyright 가 mapper_node 의 `.activities` 접근 검증 가능) |

### Medium (다음 cycle)

| ID | 영역 | 위치 | 설명 | 다음 행동 |
|---|---|---|---|---|
| #M1 | mapper_node 5 INSERT 비-atomic | graph.py:108~165 | 5 INSERT 사이 부분 실패 시 partial state (parser_report 있고 mapper_activities 없음). 재실행은 멱등 ON CONFLICT 라 회복 가능하나 같은 run_id 가 두 번 graph 도는 시점에 RC | `async with pg._pool.acquire() as con: async with con.transaction():` 묶기 (단일 transaction). 현재는 connection 단위 autocommit |
| #M2 | CollectorConfig 명명 충돌 | agents/collector.py:23 + collector/config.py:15 | 같은 이름 클래스 2개. legacy agents/collector.py 가 prod 흐름 밖이라 당장 문제 없으나 향후 import 충돌 위험 | legacy `agents/collector.py` 의 `CollectorConfig` → `LegacyDirCollectorConfig` rename 또는 폐기 (현재 prod 미사용) |
| #M3 | atomized_demo_graph 호출자 boilerplate | graph.py:531~572 | `mapped` hydrate + `pipeline_runs` INSERT 모두 호출자 책임 (atomizer 의 `assert_pipeline_run_exists` fail-fast). 백필 스크립트마다 반복 | helper `prepare_atomized_run(run_id, site_id, date, mapped_rows)` 신설 (PG INSERT + state assembly 한 곳에) |
| #M4 | HIL 2 AUTO_BYPASS 없음 | graph.py:308~416 | HIL 1 에는 `CPIA_HIL_AUTO_BYPASS` 있으나 HIL 2 는 없음. scripts/run_one_cycle.py 가 자체 auto-select 로 우회 — 실 production listener (idle_worker) path 에서는 interrupt 멈춤 | 대칭성 위해 `CPIA_HIL_AUTO_BYPASS` 가 HIL 2 도 우회 (모든 risky key 자동 선택) 또는 별도 `CPIA_HIL2_AUTO_SELECT` env 추가 |

### Low (백로그)

| ID | 영역 | 위치 | 설명 | 다음 행동 |
|---|---|---|---|---|
| #L1 | `raw_texts` 미사용 | state.py:236 | 필드 정의되어 있으나 어떤 노드도 채우거나 읽지 않음 | 다음 cycle 삭제 또는 collector_node 가 첨부 raw text 담는 용도로 활용 |
| #L2 | `update_collector_inbox_status` 중복 UPDATE | collector_node.py:44 + idle_worker.py:105 | listener 가 한 번, collector_node 가 다시 한 번 UPDATE(running). idempotent 라 functional 영향 없으나 PG round-trip 1회 낭비 | listener UPDATE 제거 (collector_node 가 single source of truth) 또는 collector_node UPDATE 제거 (listener 만) |
| #L3 | Command(resume) key 변환 룰 미명문화 | graph.py:252 | `corrections = {int(k): v for k, v in corrections_raw.items()}` — JSON 직렬화로 key 가 str 되는 룰 docstring 만 (api.py:227 주석). spec 문서화 미흡 | `docs/architecture/api-contract.md` 에 명시 |
| #L4 | LLM Semaphore env 분리 | graph.py:38 + _concurrency.py:15 | mapper 는 `CPIA_MAPPER_CONCURRENCY`, 그 외 agents 는 `CPIA_LLM_CONCURRENCY` — 운영자 두 env 외워야 함 | 통합 또는 명명 정합 (예: `CPIA_AGENT_LLM_CONCURRENCY_<MAPPER\|GENERIC>`) |
| #L5 | parser_node sync wrapper | parser_node.py:15 | `def parser_node(...)` sync — LangGraph 가 sync 노드를 별도 thread 에 던지나 graph 의 다른 노드 (collector/mapper) 는 async. 통일성 부재 | `async def parser_node(...)` 로 async wrap + `await asyncio.to_thread(parse_daily_report, path)` 호출 |
| #L6 | `_LazyAsyncPostgresSaver._opened` race | checkpointer.py:52 | `if not self._opened: await pool.open(); self._opened = True` — `asyncio.Lock` 없음. 첫 호출이 2 concurrent 면 pool.open() 2회 호출 가능 (psycopg_pool 이 자체 idempotent 하지만 contract 보장 X) | `asyncio.Lock` 으로 `_ensure_open` 보호 |
| #L7 | dead_letter race | idle_worker.py:81~87 | 같은 첨부가 동시 처리 시 file path uuid suffix 로 충돌 회피하나, dedup 은 message_id 단위라 sub_message_id 같으면 race 가능. 현실 빈도 매우 낮음 | `INSERT collector_inbox ON CONFLICT (message_id) DO NOTHING` 이미 race-safe — file write 만 추가 lock 검토 |
| #L8 | IDLE shutdown 5초 graceful 미적용 | idle_worker.py:188~194 | lifespan shutdown 시 `request_shutdown() → task.cancel()` 즉시 cancel — `idle_done()` 후처리 미완료 가능 | `asyncio.wait_for(task, timeout=5)` 로 graceful 5초 대기 후 cancel |

---

## 변경 요약

### d317be9 surgical 갱신 (1ba783f → d317be9, `a8d17e4` 1 commit)

| Commit / 시점 | 영역 | 변경 요약 | 파일 |
|---|---|---|---|
| `a8d17e4` (2026-06-01) | parser_node async multi-file merge | sync 단일파일 래퍼 → async N병렬 (`to_thread` Semaphore 4) 파싱 + `_merge_reports` concat. `_parser_p` 가 `return await _parser(state)` 로 await | parser_node.py:18~64, graph.py:595~598 |
| `a8d17e4` (2026-06-01) | hil_1 falsy-resume fix | `api.py` 가 항상 truthy 래퍼 `Command(resume={"corrections": payload})` (api.py:328~331), `hil_1_node` 가 `set(corrections_raw)=={"corrections"}` 분기로 언랩 (graph.py:263~264) — langgraph 1.2.0 미전달 버그 회피 | graph.py:257~265, api.py:320~331 |

### 이전 cycle 변경 요약 (ef7c6cd → 1ba783f, 202 commits — 1ba783f 기준 라인번호)

| Commit / 시점 | 영역 | 변경 요약 | 파일 |
|---|---|---|---|
| `55cad90` | build_graph topology | 7 → 9 노드 (collector + parser 진입) | graph.py:575~628 |
| `6b9db7c` | state-key drift fix | parsed_reports → parsed, report_date → date, D-12 4 신규 키 (bp_name/project/message_id/postgres_url) | state.py:226~265 |
| `5347966` + `973fa66` + `85155eb` + `c1cba0f` | IMAP IDLE collector 신설 | `pipeline/collector/` 폴더 3 모듈 신설 (filename_parser + idle_worker + config) | collector/*.py 392 LOC |
| `ef95e02` (2026-05-22 Plan B6) | build_atomized_demo_graph 신설 | mapper/hil_1 skip, 15일 backfill 표준 graph | graph.py:531~572 |
| `1e24dc6` | get_llm_semaphore 신설 | forecaster/optimizer/atomizer 공용 LLM 동시성 (event loop 별 lazy) | _concurrency.py |
| (2026-05-22) | HIL 2 cross-company retrieve | graph.py:355 — `coll.get(where={"l6_main": ...})` company hard filter 제거 | graph.py:353~398 |
| (2026-05-20 Issue B fix) | reporter status='completed' UPDATE | `UPDATE pipeline_runs SET status='completed', completed_at=NOW()` | graph.py:479~486 |
| (2026-05-20) | optimizer early return 제거 | risky 0 cycle 도 view 산출 진입 보장 + site_id/mapped pass-through | graph.py:424~440 |
| `4b8a955` | api.py lifespan collector task | COLLECTOR_ENABLED=true 시 idle_loop background task spawn + shutdown graceful cancel | api.py:180~194 |

---

## T2 카드 총괄 (이전 cycle vs 본 cycle)

**d317be9 surgical 갱신 (`a8d17e4`)**:

| 카드 | 상태 |
|---|---|
| `hil_1_node — langgraph 1.2.0 falsy-resume fix` ★ NEW | 신규 카드 (resume 래퍼 언랩 + api.py truthy 래퍼, 7 섹션) |
| `hil_1_node` (본체) | 갱신 (resume 래퍼 언랩 분기 + 라인번호 d317be9) |
| `parser_node` | 갱신 (sync 단일파일 → async N병렬 multi-file merge + `_merge_reports`) |
| `build_graph` | 갱신 (`_parser_p` await + exporter dual-END + 라인번호) |
| T1 graph.py / parser_node.py 테이블 | 갱신 (라인번호 d317be9 + parser_node async row + `_merge_reports` 추가) |

**이전 cycle (1ba783f) 갱신/신규** (그대로 보존):

| 카드 | 상태 |
|---|---|
| `mapper_node` | 갱신 (본 cycle 변경 section 추가) |
| `_build_review_needed` | 갱신 (본 cycle 변경 없음 명시) |
| `_apply_corrections` | 갱신 (본 cycle 변경 없음 명시) |
| `atomizer_node` | 갱신 (get_llm_semaphore 사용 + build_atomized_demo_graph entry 명시) |
| `forecaster_node` | 갱신 (get_llm_semaphore 사용 명시) |
| `hil_2_node` | 갱신 (cross-company retrieve 변경 명시) |
| `optimizer_node` | 갱신 (early return 제거 + pass-through 변경 명시) |
| `reporter_node` | 갱신 (Issue B fix status='completed' UPDATE 추가) |
| `build_graph` | 갱신 (9-노드 topology 이동) |
| `build_demo_graph` | 갱신 (build_atomized_demo_graph 형제 명시) |
| `build_atomized_demo_graph` ★ NEW | 신규 카드 |
| `CPIAState` | 갱신 (D-12 4 필드 + #C2 drift + #L1 raw_texts 미사용) |
| `Activity` | 갱신 (필드 수 변경 0 명시) |
| `_LazyAsyncPostgresSaver` ★ NEW T2 | 신규 카드 (이전엔 T1 만, 본 cycle T2 승격 — #L6 race issue) |
| `build_checkpointer` ★ NEW T2 | 신규 카드 (이전엔 T1 만, 본 cycle T2 승격) |
| `collector_node` ★ NEW | 신규 카드 (D-12 graph 진입점) |
| `parser_node` ★ NEW | 신규 카드 (D-12 state-key drift fix) |
| `get_llm_semaphore` ★ NEW | 신규 카드 (1e24dc6) |
| `idle_loop` ★ NEW | 신규 카드 (IMAP IDLE 무한 루프) |
| `run_for_attachment` ★ NEW | 신규 카드 (graph fire-and-forget) |
| `load_collector_config` ★ NEW | 신규 카드 (env 9종 fail-fast) |

**누적 합계**: T2 카드 24개 (이전 cycle 신규 9 + 갱신 14, d317be9 에서 `hil_1_node — falsy-resume fix` 1 신규 추가). d317be9 surgical 갱신은 신규 T2 1개 (falsy-resume fix) + 기존 T2 3개 갱신 (hil_1_node 본체 / parser_node / build_graph).

---

*최종 수정: 2026-06-01 (d317be9 — `a8d17e4`: parser_node async multi-file merge + hil_1 langgraph 1.2.0 falsy-resume fix surgical 갱신. 신규 T2 카드 1 + 기존 3 갱신 + T1 라인번호 재검증)*
*이전 수정: 2026-05-26 (1ba783f — D-12 collector_node 진입 + IDLE worker + build_atomized_demo_graph + cross-company HIL2 + reporter status fix + LLM Semaphore 분리 cycle)*
*이전 수정: 2026-05-20 (ef7c6cd — HIL bypass + 정규화 타이밍 + HIL2 auto-select 3 hotfix cycle)*
