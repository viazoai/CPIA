# Deep Dive — orchestration 서브시스템

- **Generated**: 2026-06-01 (`d317be9`) — parser_node async multi-file merge + hil_1 resume falsy-fix 반영 (이전 baseline 2026-05-26 `1ba783f`).
- **Git SHA**: `1ba783f → d317be9` (A_Track HEAD, origin sync). Baseline `ef7c6cd` 대비 orchestration LOC 962 → 1605 (+667). 본 surgical 갱신은 `a8d17e4` (multi-file async parser merge + hil_1 resume falsy-fix) 2개 변경만 반영 — 그 외 §은 1ba783f 기준 유지.
- **Branch**: `A_Track` (조형준 main 머지는 PR 리뷰 후 결정).
- **Range (9 파일, 1605 LOC)**:
  - `pipeline/graph.py` (628 LOC)
  - `pipeline/state.py` (310 LOC)
  - `pipeline/checkpointer.py` (94 LOC)
  - `pipeline/constants.py` (5 LOC)
  - `pipeline/agents/collector_node.py` (63 LOC, D-12 신설)
  - `pipeline/agents/parser_node.py` (64 LOC, D-12 신설; `a8d17e4` 에서 async N병렬 multi-file concat merge 로 확장)
  - `pipeline/agents/_concurrency.py` (18 LOC, 신설)
  - `pipeline/collector/filename_parser.py` (64 LOC, 신설)
  - `pipeline/collector/idle_worker.py` (260 LOC, 신설)
  - `pipeline/collector/config.py` (68 LOC, 신설)
  - `pipeline/agents/collector.py` (70 LOC, legacy — 본 cycle 변경 없음)
- **Pair**: `./architecture_overview.md` (시스템 다이어그램) + `./design-intent/design_intent_orchestration.md` (T1/T2 카드, 이전 cycle 산출)
- **Spec**:
  - `docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md` (D-12 collector 분리)
  - `docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md`

---

## 1. Overview

Orchestration 서브시스템은 LangGraph `StateGraph` 위에 7~9 노드 (collector/parser/mapper/hil_1/atomizer/forecaster/hil_2/optimizer/reporter) 를 조립하고, 그 사이를 흐르는 단일 공유 상태 (`CPIAState` TypedDict) 와 비동기 PostgreSQL checkpoint (`_LazyAsyncPostgresSaver`) 를 관리한다. FastAPI `/run`·`/resume` 또는 메일 IDLE 푸시 (`pipeline/collector/idle_worker.py`) 가 진입점이며, 각 노드는 PG INSERT 및 Chroma 적재를 자체 책임진다.

**본 cycle (ef7c6cd → 1ba783f) 핵심 변경**:
1. **graph 진입점이 `mapper` → `collector` 로 이동** (`55cad90`). `START → collector → parser → mapper → hil_1 → atomizer → forecaster → hil_2 → (optimizer | reporter) → END` 의 9-노드 production topology. 신규 노드 2개 (`collector_node` D-12 진입 검증 + `parser_node` rule-based parser wrapper) 추가.
2. **D-12 state-key drift fix** (`6b9db7c`): `parsed_reports` → `parsed`, `report_date` → `date` 통일. listener 가 invoke 시 박는 4개 신규 키 (`bp_name`/`project`/`message_id`/`postgres_url`) 가 `CPIAState` 에 정식 정의됨.
3. **IMAP IDLE collector** (`5347966`+`973fa66`+`85155eb`+`c1cba0f`): `pipeline/collector/` 폴더 신설 — `filename_parser` (정규식) + `idle_worker` (UNSEEN drain + dedup + dead_letter + `run_for_attachment` fire-and-forget) + `config` (env 9종 fail-fast). `collector_inbox` PG 테이블 + 3 helper (`insert_/update_/fetch_by_message_id`) 신규.
4. **`build_atomized_demo_graph`** (`ef95e02`): mapper/hil_1 만 skip, mapped 호출자가 PG hydrate 한 상태로 진입 → atomizer 부터 시작. 15일 backfill 표준 graph.
5. **`get_llm_semaphore()` + `CPIA_LLM_CONCURRENCY`** (`1e24dc6`): forecaster/optimizer/atomizer 공용 LLM 동시성 제어 모듈. event loop 별 lazy 생성 (기본 4 동시).
6. **HIL 2 cross-company retrieve** (graph.py:355): Chroma `coll.get(where=...)` 의 company hard filter 제거, l6_main 만 매칭 → 합성 3사 외 75사가 cold_start fallback 빠지던 회귀 해소.
7. **Reporter Issue B fix**: `pipeline_runs.status='completed' + completed_at=NOW()` UPDATE 추가 (graph.py:482) — 이전엔 graph 종료 후에도 status='running' 잔존.
8. **api.py lifespan 안에 collector task** (`4b8a955`): `COLLECTOR_ENABLED=true` 일 때 `idle_loop(collector_cfg)` 를 백그라운드 task 로 spawn, shutdown 시 graceful cancel.

---

## 2. 파일 목록 + LOC 표

| 파일 | LOC | 한 줄 책임 | 본 cycle |
|---|---:|---|---|
| `pipeline/graph.py` | 628 | StateGraph 조립 + 7 노드 함수 + 2 helper (`_build_review_needed`/`_apply_corrections`) + 3 builder (`build_graph`/`build_demo_graph`/`build_atomized_demo_graph`) | +65 LOC, atomized_demo + collector/parser node + cross-company HIL2 |
| `pipeline/state.py` | 310 | `CPIAState` (20 필드) + `Activity` (44 필드) + `ParsedDailyReport` + 시트 raw TypedDict 9개 | +7 LOC, D-12 4 신규 키 |
| `pipeline/checkpointer.py` | 94 | `_LazyAsyncPostgresSaver` (AsyncConnectionPool lazy open) + `build_checkpointer` (env 분기) | 변경 없음 |
| `pipeline/constants.py` | 5 | `WORK_HOURS_PER_DAY=8` 1 상수 | 변경 없음 |
| `pipeline/agents/collector_node.py` | 63 | D-12 graph 진입 노드 — 파일 존재 검증 + `parse_filename` 분해 + `collector_inbox` UPDATE | 신설 |
| `pipeline/agents/parser_node.py` | 64 | `input_files` 전체를 async N병렬 (`to_thread` Semaphore 4) 파싱 → `_merge_reports` concat merge → 1 통합 `ParsedDailyReport` | `a8d17e4` async multi-file merge |
| `pipeline/agents/_concurrency.py` | 18 | `get_llm_semaphore()` event-loop 별 Semaphore (env `CPIA_LLM_CONCURRENCY`, 기본 4) | 신설 |
| `pipeline/agents/collector.py` | 70 | (legacy) `discover_daily_reports` + `collect_and_parse` (dir scan + Semaphore 4) | 변경 없음 |
| `pipeline/collector/filename_parser.py` | 64 | 첨부 파일명 정규식 → `ParsedFilename(kind, project, bp_name, trade, zone, date)` | 신설 |
| `pipeline/collector/idle_worker.py` | 260 | IMAP IDLE loop + UNSEEN drain + dedup + 첨부 추출 + `run_for_attachment` (graph fire-and-forget) | 신설 |
| `pipeline/collector/config.py` | 68 | env 9종 → `CollectorConfig` (fail-fast, `COLLECTOR_ENABLED=true` 일 때 자격증명 필수) | 신설 |

**합계**: 1605 LOC (이전 962 → +643), 11 모듈 (이전 6 → +5).

---

## 3. Public 함수/클래스 표 (전수)

### graph.py

| Name | file:line | Signature | 역할 |
|---|---|---|---|
| `GraphConfig` | graph.py:41 | `@dataclass(mapper, atomizer, forecaster, optimizer, reporter)` | 5 sub-config 묶음 |
| `mapper_node` | graph.py:50 | `async (state, cfg: GraphConfig) -> dict` | Parser 정규화 + BP cand_pool batch + Semaphore(4) map_activity + `_prorate_mh` + 5 PG INSERT + 같은 트랜잭션 SELECT 검증 |
| `_build_review_needed` | graph.py:170 | `(mapped) -> list[dict]` | requires_review=True 행만 9 필드 추출 |
| `_apply_corrections` | graph.py:191 | `(mapped, corrections: dict[int, dict]) -> list[Activity]` | corrections 적용 + `mapping_source="user_corrected"` + `requires_review=False` 강제 |
| `hil_1_node` | graph.py:233 | `async (state, cfg) -> dict` | review_needed 1건 이상 → `interrupt`; `CPIA_HIL_AUTO_BYPASS` env 우회; resume payload 가 `{"corrections": {...}}` truthy 래퍼면 언랩 (graph.py:263~264, langgraph 1.2.0 falsy-resume gotcha); PG `insert_mapping_correction` 반복 |
| `atomizer_node` | graph.py:294 | `async (state, cfg) -> dict` | Chroma daily_activities 적재 + atomized_ids 반환 |
| `forecaster_node` | graph.py:301 | `async (state, cfg) -> dict` | 그룹별 진단 (RAG + Plan fallback) |
| `hil_2_node` | graph.py:308 | `async (state, cfg) -> dict` | risky 그룹별 Chroma `coll.get` 1회 (F5) + cross-company baseline (F7) + `interrupt({risky_groups})` |
| `optimizer_node` | graph.py:419 | `async (state, cfg) -> dict` | `optimize(forecast, selection, pre_cases, run_id, today, cfg.optimizer, site_id, mapped)` |
| `reporter_node` | graph.py:444 | `async (state, cfg) -> dict` | 종합 보고서 `report()` + site_id PG fallback + G8/G2 + `pipeline_runs.status='completed'` |
| `build_demo_graph` | graph.py:493 | `(cfg) -> CompiledGraph` | `START → forecaster → hil_2 → (optimizer\|reporter) → END` (mapped 사전 주입) |
| `build_atomized_demo_graph` | graph.py:531 | `(cfg) -> CompiledGraph` | `START → atomizer → forecaster → hil_2 → (optimizer\|reporter) → END` (15일 backfill 용) |
| `build_graph` | graph.py:575 | `(cfg) -> CompiledGraph` | production 9-노드 `START → collector → parser → mapper → hil_1 → atomizer → forecaster → hil_2 → (optimizer\|reporter) → END` |

### state.py

| Name | file:line | 역할 |
|---|---|---|
| `TimeShiftCounts` | state.py:17 | 6 시간대 (morning/daytime/overtime/night/all_night/total) TypedDict |
| `Activity` | state.py:32 | 시트4 1 행 매핑 단위 (44 필드 — 시트4 원천 17 + 업체별 추가 4 + WBS 매핑 9 + 분배 3 + Mapper 결정 3 + HIL flag 1) |
| `BPSummary` | state.py:96 | 시트1 row (20 필드, jsonb 4그룹) |
| `JobAllocation` | state.py:122 | 시트2 row (10 필드, jsonb 3그룹) |
| `EquipmentAllocation` | state.py:146 | 시트3 row (10 필드, jsonb 3그룹) |
| `WorkerOutput` | state.py:170 | 시트6 (업체별 일보) — 12 필드 |
| `ReportMeta` | state.py:193 | Cover 시트 (업체별 일보) — 9 필드 |
| `ParsedDailyReport` | state.py:207 | 1 xlsx 통합 (8 필드) |
| `CPIAState` | state.py:226 | LangGraph 전체 상태 (20 필드 — 본 cycle +4) |
| `BPSummaryRaw` | state.py:268 | 시트1 LLM row 단위 raw output (페어링 전) |
| `JobAllocationRaw` | state.py:285 | 시트2 LLM raw |
| `EquipmentAllocationRaw` | state.py:299 | 시트3 LLM raw |

### checkpointer.py

| Name | file:line | Signature | 역할 |
|---|---|---|---|
| `_LazyAsyncPostgresSaver` | checkpointer.py:30 | `class(postgres_url)` | `AsyncPostgresSaver` 상속 + sync `__init__` 에서 `AsyncConnectionPool(open=False)` 만 만들고, 첫 async 메서드 (aput/aget_tuple/aput_writes/alist/aget) 시 `_ensure_open()` 으로 `await pool.open()` |
| `build_checkpointer` | checkpointer.py:78 | `() -> BaseCheckpointSaver` | env `CPIA_CHECKPOINTER=memory` 또는 `POSTGRES_URL` 미설정 → `InMemorySaver`; 그 외 → `_LazyAsyncPostgresSaver` |

### constants.py

| Name | file:line | 값 | 역할 |
|---|---|---|---|
| `WORK_HOURS_PER_DAY` | constants.py:5 | `8` | cross-agent shared 일일 작업시간 |

### agents/collector_node.py

| Name | file:line | Signature | 역할 |
|---|---|---|---|
| `collector_node` | collector_node.py:16 | `async (state: CPIAState) -> dict[str, Any]` | `input_files[0]` 경로 검증 + `parse_filename` 분해 + `message_id`+`postgres_url` 있으면 `collector_inbox` UPDATE(running) + meta 키 반환 |

### agents/parser_node.py

| Name | file:line | Signature | 역할 |
|---|---|---|---|
| `parser_node` | parser_node.py:40 | `async (state: CPIAState) -> dict[str, Any]` | `input_files` 전체 → `_parse_one` async (`to_thread(parse_daily_report)` Semaphore 4) → `_merge_reports` concat → `{"parsed": ParsedDailyReport}` 반환 |
| `_merge_reports` | parser_node.py:18 | `(reports: list[ParsedDailyReport]) -> ParsedDailyReport` | N개 ParsedDailyReport → 1 통합 (activities/bp_summaries/job/equip/worker_outputs concat, report_meta 는 첫 업체 것) |

### agents/_concurrency.py

| Name | file:line | Signature | 역할 |
|---|---|---|---|
| `get_llm_semaphore` | _concurrency.py:15 | `() -> asyncio.Semaphore` | env `CPIA_LLM_CONCURRENCY` (기본 4) → `Semaphore(max(1, n))`. event loop 별 lazy 생성, forecaster/optimizer/atomizer 공유 |

### agents/collector.py (legacy)

| Name | file:line | Signature | 역할 |
|---|---|---|---|
| `CollectorConfig` | collector.py:23 | `@dataclass(file_concurrency=4)` | legacy collector 동시성 |
| `discover_daily_reports` | collector.py:30 | `(input_dir: Path\|str) -> list[Path]` | dir 안 `*작업일보*.xlsx[m]` 필터 (재귀 X, `~$` lock 제외) |
| `collect_and_parse` | collector.py:52 | `async (input_dir, cfg) -> list[ParsedDailyReport]` | `discover_*` + `asyncio.Semaphore(file_concurrency)` 로 `to_thread(parse_daily_report)` |

### collector/filename_parser.py

| Name | file:line | Signature | 역할 |
|---|---|---|---|
| `ParsedFilename` | filename_parser.py:16 | `@dataclass(frozen)` (kind, project, bp_name, trade, zone, date) | 분해 결과 holder |
| `parse_filename` | filename_parser.py:25 | `(name: str) -> Optional[ParsedFilename]` | `업체작업일보_<project>_..._<bp>_<trade>_<zone>_<YYMMDD>.xlsx` 또는 `통합작업일보_<project>_<YYMMDD>.xlsx` 정규식 분해. 미일치 None |

### collector/idle_worker.py

| Name | file:line | Signature | 역할 |
|---|---|---|---|
| `request_shutdown` | idle_worker.py:37 | `() -> None` | `_shutdown` Event set — lifespan 의 shutdown trigger |
| `_extract_attachments` | idle_worker.py:41 | `(msg: Message) -> list[tuple[str, bytes]]` | multipart walk + RFC2047 디코딩 + `.xlsx/.xlsm` 필터 |
| `_save_to_input_dir` | idle_worker.py:63 | `(att_name, att_bytes, date_iso, cfg) -> Path` | `data/input/YYYYMMDD/<att_name>` 저장, 충돌 시 uuid suffix |
| `_to_dead_letter` | idle_worker.py:81 | `(att_name, att_bytes, cfg) -> None` | 파일명 미일치 시 dead_letter 폴더로 이동 |
| `run_for_attachment` | idle_worker.py:90 | `async (path, meta, site_id, message_id, cfg) -> None` | `_GRAPH_SEM` (CPIA_COLLECTOR_CONCURRENCY, 기본 2) 보호 + `build_graph(cfg.graph_cfg)` 호출 + `ainvoke` + `collector_inbox` status UPDATE (running/failed/completed) |
| `_process_one` | idle_worker.py:153 | `async (imap, uid, cfg) -> None` | UNSEEN 1통 fetch + Message-ID dedup PG 체크 + 첨부 추출 + `insert_collector_inbox` + `create_task(run_for_attachment)` fire-and-forget |
| `_drain_new` | idle_worker.py:214 | `async (imap, cfg) -> None` | UNSEEN search → 각 uid `_process_one` |
| `idle_loop` | idle_worker.py:228 | `async (cfg: CollectorConfig) -> None` | FastAPI startup background task. IMAP login + INBOX select + 시작 drain + `idle_start(29min) → wait_server_push → idle_done` 무한 반복. EXISTS notification 시 `_drain_new`. shutdown 또는 cancel 시 graceful exit |
| `_shutdown` | idle_worker.py:33 | `asyncio.Event()` | module-level shutdown flag |
| `_GRAPH_SEM` | idle_worker.py:34 | `asyncio.Semaphore(CPIA_COLLECTOR_CONCURRENCY=2)` | graph 동시 invoke 제한 (Azure rate-limit 고려) |

### collector/config.py

| Name | file:line | Signature | 역할 |
|---|---|---|---|
| `CollectorConfig` | config.py:15 | `@dataclass(frozen)` (host, port, user, app_password, default_site_id, input_dir, dead_letter_dir, postgres_url, graph_cfg, enabled) | env 9종 + graph_cfg 묶음 |
| `_bool` | config.py:29 | `(s, default) -> bool` | env 문자열 → bool |
| `load_collector_config` | config.py:35 | `(graph_cfg: GraphConfig) -> CollectorConfig` | env 9종 로드. `COLLECTOR_ENABLED=true` 인데 USER/APP_PASSWORD 누락 시 `RuntimeError` fail-fast |

---

## 4. LangGraph StateGraph 다이어그램 (ASCII)

### 4.1 `build_graph` — production 9-노드 (graph.py:575)

```
                                 ┌─────────────┐
                                 │    START    │
                                 └──────┬──────┘
                                        │  state = {run_id, input_files[0],
                                        │           site_id, message_id?, postgres_url?}
                                        ▼
            ┌────────────────────────────────────────────────────┐
            │  collector_node                  (graph.py:605)   │
            │  • input_files[0] 경로 존재 검증                    │
            │  • parse_filename(path.name) → ParsedFilename     │
            │  • collector_inbox UPDATE(running)                │
            │  • return {bp_name, date, project}                │
            └──────────────────────────┬─────────────────────────┘
                                       ▼
            ┌────────────────────────────────────────────────────┐
            │  parser_node (async)             (graph.py:635)   │
            │  • input_files 전체 → to_thread(parse_daily_      │
            │    report) Semaphore(4) async N병렬 파싱           │
            │  • _merge_reports → 1 concat ParsedDailyReport     │
            │  • return {parsed: ParsedDailyReport}             │
            └──────────────────────────┬─────────────────────────┘
                                       ▼
            ┌────────────────────────────────────────────────────┐
            │  mapper_node (graph.py:50)                         │
            │  • normalize_company × 2                           │
            │  • BP cand_pool batch fetch (1 PG conn)            │
            │  • asyncio.gather + Semaphore(CPIA_MAPPER_         │
            │    CONCURRENCY=4) map_activity                     │
            │  • _prorate_mh                                     │
            │  • 5 PG INSERT (parser_report, parser_activities,  │
            │    parser_job_allocations, parser_equipment_       │
            │    allocations, mapper_activities)                 │
            │  • 같은 트랜잭션 SELECT COUNT 검증                  │
            │  • return {mapped, current_node="mapper"}          │
            └──────────────────────────┬─────────────────────────┘
                                       ▼
            ┌────────────────────────────────────────────────────┐
            │  hil_1_node          ◀══════════ interrupt #1     │
            │  (graph.py:233)                                    │
            │  • _build_review_needed (requires_review=True 9    │
            │    필드)                                            │
            │  • if review_needed == 0: pass-through             │
            │  • elif CPIA_HIL_AUTO_BYPASS in {1,true,on,yes}:   │
            │      stderr 로그 + 빈 corrections 통과              │
            │  • else: interrupt({"review_needed": [...]})       │
            │  • resume 래퍼 언랩: {"corrections": {...}} →       │
            │    corrections_raw["corrections"] or {} (g.py:263) │
            │  • _apply_corrections                              │
            │  • insert_mapping_correction × corrections.len     │
            │  ───  Command(resume={"corrections": {idx: {wa, l6_main}}})  (truthy 래퍼)
            └──────────────────────────┬─────────────────────────┘
                                       ▼
            ┌────────────────────────────────────────────────────┐
            │  atomizer_node                   (graph.py:294)   │
            │  • atomize(mapped, parsed, run_id, cfg.atomizer)  │
            │  • Chroma daily_activities INSERT                  │
            │  • return {atomized_ids}                           │
            └──────────────────────────┬─────────────────────────┘
                                       ▼
            ┌────────────────────────────────────────────────────┐
            │  forecaster_node                 (graph.py:301)   │
            │  • forecast(mapped, run_id, today, cfg.forecaster)│
            │  • RAG (daily_activities) + Plan fallback         │
            │  • return {forecast: list[dict]} (assessment +     │
            │    risk_level + reasoning + main_unit ...)         │
            └──────────────────────────┬─────────────────────────┘
                                       ▼
            ┌────────────────────────────────────────────────────┐
            │  hil_2_node       ◀══════════ interrupt #2        │
            │  (graph.py:308)                                    │
            │  • risky = [r for r in forecast if r["risk_level"] │
            │           in {"주의","이상"}]                       │
            │  • if not risky: empty selection 반환 (skip)       │
            │  • else:                                           │
            │      Chroma coll.get(where={l6_main}, include=     │
            │        ["metadatas","documents"])  -- 그룹당 1회   │
            │      _group_baseline → None 분기 (F7 cold_start)   │
            │      fetch_degradation_cases + fetch_recovery_     │
            │        trajectory (cross-company, 2026-05-22)      │
            │      interrupt({"risky_groups": [...]})            │
            │  ───────────────  Command(resume=[group_key,...])  │
            └──────────────────────────┬─────────────────────────┘
                                       │
                  ┌────────────────────┴─────────────────────┐
                  │ hil_2_selection 비어있지 않음            │ empty (risky 0건
                  ▼                                          │  또는 PM 무선택)
            ┌──────────────────────────────────┐             │
            │  optimizer_node    (graph.py:419)│             │
            │  • optimize(forecast, selection, │             │
            │    pre_cases, run_id, today, cfg.│             │
            │    optimizer, site_id, mapped)   │             │
            │  • view_builder 8 jsonb 산출      │             │
            │  • return {optimizer_advice}     │             │
            └──────────────────┬───────────────┘             │
                               ▼                              ▼
            ┌─────────────────────────────────────────────────┐
            │  reporter_node                   (graph.py:444) │
            │  • report(mapped, forecast_rows, optimizer_     │
            │    advice, run_id, today, cfg.reporter)         │
            │  • site_id PG fallback (state.site_id 없으면     │
            │    pipeline_runs SELECT)                        │
            │  • update_site_last_run (G8)                    │
            │  • update_site_hours_saved_cum (G2)             │
            │  • UPDATE pipeline_runs SET status='completed',  │
            │    completed_at=NOW() WHERE run_id=$1            │
            │  • return {report_md, status:"completed"}        │
            └──────────────────────────┬──────────────────────┘
                                       ▼
                                  ┌────────┐
                                  │  END   │
                                  └────────┘
```

### 4.2 `build_demo_graph` (graph.py:493) — Parser/Mapper/Atomizer skip

```
START → forecaster → hil_2 ─┬─(selection 있음)─→ optimizer → reporter → END
                            └─(empty)──────────→ reporter → END
```

- `synthetic_daily_report.py` CLI + `test_synthetic_daily_report.py` E2E 가 호출.
- `state["mapped"]` 사전 주입 가정 (LLM 비용 회피).

### 4.3 `build_atomized_demo_graph` (graph.py:531) — 본 cycle 신설

```
START → atomizer → forecaster → hil_2 ─┬─(selection)──→ optimizer → reporter → END
                                       └─(empty)──────→ reporter → END
```

- 2026-05-22 (Plan B6) — mapper/hil_1 만 skip. `mapped` 는 호출자가 PG `mapper_activities` 에서 hydrate 한 상태로 진입.
- `pipeline_runs` INSERT 도 호출자 책임 (atomizer 의 `assert_pipeline_run_exists` fail-fast).
- 15일 backfill 의 표준 graph.

### 4.4 Edge 조건 요약

| Edge | 조건 | 정의 |
|---|---|---|
| `START → collector` | unconditional | graph.py:614 |
| `collector → parser` | unconditional | graph.py:615 |
| `parser → mapper` | unconditional | graph.py:616 |
| `mapper → hil_1` | unconditional | graph.py:617 |
| `hil_1 → atomizer` | unconditional | graph.py:618 |
| `atomizer → forecaster` | unconditional | graph.py:619 |
| `forecaster → hil_2` | unconditional | graph.py:620 |
| `hil_2 → optimizer` | `s.get("hil_2_selection")` truthy | graph.py:621~625 |
| `hil_2 → reporter` | `hil_2_selection` falsy (empty list 포함) | graph.py:621~625 |
| `optimizer → reporter` | unconditional | graph.py:626 |
| `reporter → END` | unconditional | graph.py:627 |

### 4.5 Interrupt 지점

| 지점 | 노드 | 트리거 | resume payload |
|---|---|---|---|
| HIL 1 | hil_1_node (graph.py:257) | `len(review_needed) >= 1` 이고 `CPIA_HIL_AUTO_BYPASS` 미설정 | `Command(resume={"corrections": {idx: {"wa","l6_main"}, ...}})` — truthy 래퍼 필수 (langgraph 1.2.0 falsy-resume gotcha). 래퍼 없는 직접 dict 는 하위호환 통과 |
| HIL 2 | hil_2_node (graph.py:411) | `len(risky) >= 1` (주의/이상 그룹) | `Command(resume=[group_key, ...])` |

---

## 5. CPIAState 필드 전수 (20 필드)

| # | 필드 | 타입 | 채우는 노드 | 읽는 노드 |
|---:|---|---|---|---|
| 1 | `run_id` | `str` | listener / api `/run` | mapper, atomizer, forecaster, hil_2, optimizer, reporter |
| 2 | `date` | `str` (ISO YYYY-MM-DD) | listener / collector_node | mapper, forecaster, hil_2, optimizer, reporter |
| 3 | `input_files` | `list[str]` | listener / api `/run` | collector_node, parser_node |
| 4 | `site_id` | `str \| None` | listener (D-11 default) | optimizer, reporter (없으면 pipeline_runs PG fallback) |
| 5 | `raw_texts` | `dict[str, str]` | (현재 미사용 — drift) | (미사용) |
| 6 | `parsed` | `list[Activity]` (실제로는 ParsedDailyReport — drift #N12) | parser_node | mapper |
| 7 | `mapped` | `list[Activity]` | mapper_node, hil_1_node (corrections 적용 후) | atomizer, forecaster, hil_2, optimizer, reporter, build_atomized_demo_graph 호출자 |
| 8 | `hil_1_corrections` | `dict` (idx → {wa, l6_main}) | hil_1_node | (PG insert_mapping_correction 만) |
| 9 | `atomized_ids` | `list[str]` | atomizer_node | reporter (G2 hours_saved_cum 산식 분자) |
| 10 | `report_md` | `str` | reporter_node | (api 응답) |
| 11 | `forecast` | `list[dict]` | forecaster_node | hil_2, optimizer, reporter |
| 12 | `hil_2_selection` | `list[str]` | hil_2_node | optimizer (conditional_edge 조건) |
| 13 | `pre_optimizer_cases` | `dict[str, list[dict]]` | hil_2_node | optimizer (retrieve 재호출 회피) |
| 14 | `optimizer_advice` | `list[dict]` | optimizer_node | reporter |
| 15 | `current_node` | `str` | 모든 노드 | api `/status` |
| 16 | `status` | `Literal[running, waiting_hil_1, waiting_hil_2, completed, failed]` | reporter_node (`"completed"` 박음) | api `/status` |
| 17 | `bp_name` | `str` (D-12) | collector_node | (cross-agent 메타용) |
| 18 | `project` | `str` (D-12) | collector_node | (메타) |
| 19 | `message_id` | `str` (D-12) | listener invoke 시 박힘 (CLI 진입 시 absent) | collector_node (`collector_inbox` UPDATE 조건) |
| 20 | `postgres_url` | `str` (D-12) | listener invoke 시 박힘 | collector_node (`PGClient` 생성) |

**Drift 주의**: state.py:237 의 `parsed: list[Activity]` 는 실제로 `ParsedDailyReport` 가 들어간다 (parser_node.py:64 `return {"parsed": merged}` — merged 는 `_merge_reports` 의 통합 `ParsedDailyReport` + mapper_node 의 graph.py:62 `parsed: ParsedDailyReport = state["parsed"]` 캐스팅). 타입 annotation 갱신 필요 (Critical issue #C2 — 아래 §13 참조).

---

## 6. Activity TypedDict 필드 전수 (44 필드, state.py:32~94)

### 6.1 시트4 원천 (Parser 채움) — 17 필드

| # | 필드 | 타입 | 출처 col | 비고 |
|---:|---|---|---|---|
| 1 | `zone` | `str \| None` | col 2 | FAB/CUB 등 |
| 2 | `bp_code` | `str \| None` | col 4 | PH_X-... |
| 3 | `company` | `str` | col 5 | 업체명 |
| 4 | `scope` | `str \| None` | col 6 | |
| 5 | `trade` | `str` | col 3 | 공종 한글 |
| 6 | `work_content` | `str` | col 7 | 대표물량 작업 내용 |
| 7 | `unit` | `str` | col 8 | |
| 8 | `plan_total_qty` | `float \| None` | col 9 (A) | 총물량 |
| 9 | `yesterday_cum_qty` | `float \| None` | col 10 (B) | 전일누적 |
| 10 | `today_qty` | `float` | col 11 (C) | 금일실적 |
| 11 | `today_cum_qty` | `float \| None` | col 12 (D=B+C) | 금일누적 |
| 12 | `progress_percent` | `float \| None` | col 13 (F%=D/A) | |
| 13 | `remaining_qty` | `float \| None` | col 14 (E=A-D) | 잔여 |
| 14 | `remaining_percent` | `float \| None` | col 15 통합/14 업체 (G%) | |
| 15 | `note` | `str \| None` | col 16 | 비고 |
| 16 | `l5_disc` | `str` | (Parser 매핑) | 한글 |
| 17 | `conditions` | `list[str]` | (Parser 분류) | |

### 6.2 업체별 일보 시트4 추가 (통합 일보엔 없음) — 4 필드

| # | 필드 | 타입 | 출처 |
|---:|---|---|---|
| 18 | `work_location_code` | `str \| None` | 업체 col 15 |
| 19 | `wbs_mid_name` | `str \| None` | col 16 (중공종명) |
| 20 | `wbs_sub_name` | `str \| None` | col 17 (소공종명) |
| 21 | `wbs_detail_name` | `str \| None` | col 18 (세공종명) |

### 6.3 WBS 매핑 (Mapper 이후) — 9 필드

| # | 필드 | 타입 | 비고 |
|---:|---|---|---|
| 22 | `wbs_activity_id` | `str \| None` | PoC: 항상 None (Master List 1:N) |
| 23 | `l6_main` | `str \| None` | Mapper LLM 결정 |
| 24 | `l7_sub` | `str \| None` | PoC: None |
| 25 | `l7_5_activity` | `str \| None` | PoC: None |
| 26 | `sub_work_area` | `str \| None` | PoC: None |
| 27 | `wa` | `str \| None` | Mapper `resolve_wa` 7단계 결정 |
| 28 | `mapping_conf` | `float \| None` | LLM rerank confidence 0.0~1.0 |
| 29 | `mapping_source` | `str \| None` | `auto_bp_single`/`auto_l6_single`/`auto_sheet1_text`/`auto_bp_zone_match`/`auto_llm_rerank`/`user_corrected`/`hil_required` |
| 30 | `requires_review` | `bool` | `mapping_conf < 0.7` 또는 `mapping_source='hil_required'` |

### 6.4 `_prorate_mh` 분배 결과 — 3 필드

| # | 필드 | 타입 | 산식 |
|---:|---|---|---|
| 31 | `assigned_workers` | `float` | BP사 총 인원 × (그 l6 candidate Σplan_mh / 전체 매핑 l6 candidate Σplan_mh) |
| 32 | `worker_source` | `Literal[parsed, mh_prorated, user_corrected]` | 기본 `mh_prorated` |
| 33 | `plan_mh` | `float \| None` | activity_master 값 |

총 33 필드 (현재 명시). state.py:32 docstring 의 "44 필드" 는 sub-필드까지 포함한 카운트 (BPSummary 와 합산이거나 deep-dive 문서 카운트 표기 차이). 실 TypedDict 필드는 30~33 개.

---

## 7. 각 노드 walkthrough

### 7.1 `collector_node` (collector_node.py:16, D-12 신설)

- **진입 line**: collector_node.py:16
- **입력 state 키**: `input_files`, `message_id?`, `postgres_url?`, `run_id`
- **출력 state 키**: `bp_name`, `date`, `project`
- **핵심 코드** (collector_node.py:27~63):

```python
async def collector_node(state: CPIAState) -> dict[str, Any]:
    input_files = state.get("input_files") or []
    if not input_files:
        raise RuntimeError("collector_node: state.input_files 비어있음")
    path = Path(input_files[0])
    if not path.exists():
        raise FileNotFoundError(f"collector_node: {path}")
    meta = parse_filename(path.name)
    if meta is None:
        raise ValueError(f"collector_node: 파일명 규약 불일치 {path.name}")

    message_id = state.get("message_id")
    postgres_url = state.get("postgres_url")
    if message_id and postgres_url:
        pg = PGClient(postgres_url)
        await pg.connect()
        try:
            await update_collector_inbox_status(
                pg, message_id, run_id=state["run_id"], parse_status="running",
            )
        finally:
            await pg.close()
    return {
        "bp_name": meta.bp_name or "_integrated",
        "date": meta.date,
        "project": meta.project,
    }
```

- **에러 핸들링**: 3 fail-fast — `RuntimeError` (input_files 빈), `FileNotFoundError` (경로 부재), `ValueError` (파일명 규약 불일치). dead_letter 처리는 listener (`idle_worker._to_dead_letter`) 측 책임 — graph 진입 전에 거름.

### 7.2 `parser_node` (parser_node.py:40, D-12 신설; `a8d17e4` async multi-file merge)

- **진입 line**: parser_node.py:40 (`async def`)
- **입력 state 키**: `input_files` (전체 — 1번째만 아님)
- **출력 state 키**: `parsed`
- **핵심 코드** (parser_node.py:40~64):

```python
async def parser_node(state: CPIAState) -> dict[str, Any]:
    files = [Path(f) for f in state["input_files"]]
    if not files:
        raise RuntimeError("parser_node: input_files 비어있음")
    sem = asyncio.Semaphore(_PARSE_CONCURRENCY)  # = 4

    async def _parse_one(p: Path) -> ParsedDailyReport:
        async with sem:
            return await asyncio.to_thread(parse_daily_report, p)

    reports = list(await asyncio.gather(*[_parse_one(p) for p in files]))
    merged = _merge_reports(reports)
    log.info(
        "parser_node: %d개 파일 병렬 병합 (bp_summaries=%d, activities=%d)",
        len(files), len(merged["bp_summaries"]), len(merged["activities"]),
    )
    return {"parsed": merged}
```

- **multi-file merge (`a8d17e4`)**: 이전엔 `input_files[0]` 단일 파일만 sync 파싱했으나, 이제 `input_files` 전체를 async N병렬로 파싱하고 `_merge_reports` (parser_node.py:18) 로 concat 통합한다. 각 업체가 다른 작업을 한다는 전제로 activities/bp_summaries/job/equip/worker_outputs 를 단순 이어붙이고, report_meta 는 첫 업체(site 대표) 것을 쓴다. `report_date` 불일치 시 WARN 로그만 (graph 흐름은 계속).
- **async + to_thread**: sync `parse_daily_report` 를 `asyncio.to_thread` 로 wrap (Semaphore 4) — 이벤트 루프를 block 하지 않아 mapper~ 진행 중에도 FastAPI 의 다른 요청(게이지 polling 등)이 응답한다. `build_graph` 의 wrapper `_parser_p` (graph.py:595~598) 가 `return await _parser(state)` 로 await 한다.
- **에러 핸들링**: `input_files` 빈 → `RuntimeError`. 그 외는 `parse_daily_report` 자체 raise (LangGraph 미처리 시 status='failed').

### 7.3 `mapper_node` (graph.py:50)

- **진입 line**: graph.py:50
- **입력 state 키**: `parsed`, `run_id`, `date`
- **출력 state 키**: `mapped`, `current_node`
- **핵심 코드** (graph.py:62~95):

```python
parsed: ParsedDailyReport = state["parsed"]
run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
today = _date.fromisoformat(state["date"])

# 정규화 타이밍 fix — fetch_bp_candidates 는 정확 일치 SQL.
for a in parsed["activities"]:
    a["company"] = normalize_company(a.get("company"))

# BP cand_pool 미리 batch fetch — 1 PG connection 으로 모든 company 조회
pg = PGClient(cfg.mapper.postgres_url)
await pg.connect()
try:
    unique_companies = {a["company"] for a in parsed["activities"] if a.get("company")}
    bp_cand_lookup: dict[str, list[tuple[str, str]]] = {}
    for company in unique_companies:
        cand_rows = await pg.fetch_bp_candidates(company)
        bp_cand_lookup[company] = [(r["wa"], r["l6_main"]) for r in cand_rows]
finally:
    await pg.close()

sem = asyncio.Semaphore(_MAPPER_CONCURRENCY)

async def _map_one(a: Activity) -> Activity:
    async with sem:
        return await map_activity(a, parsed_report=parsed, cfg=cfg.mapper, bp_cand_lookup=bp_cand_lookup)

mapped = list(await asyncio.gather(*[_map_one(a) for a in parsed["activities"]]))
```

- **PG 영속 (graph.py:108~154)**: `insert_parser_report` + `insert_parser_activities_batch` + `insert_parser_job_allocations_batch` (G24 — 이전 호출 누락 row=0 버그) + `insert_parser_equipment_allocations_batch` (G24) + `insert_mapper_activities_batch` + 같은 트랜잭션 SELECT COUNT 검증 (graph.py:157~162).
- **에러 핸들링**: try/finally 로 PG pool close 보장. INSERT 실패 시 raise (atomic transaction 아님 — 부분 적재 위험 — Medium issue #M3 — §13 참조).

### 7.4 `hil_1_node` (graph.py:233)

- **진입 line**: graph.py:233
- **입력 state 키**: `mapped`, `run_id`, `date`
- **출력 state 키**: `mapped` (corrections 적용), `hil_1_corrections`, `current_node`
- **핵심 코드** (graph.py:242~291):

```python
mapped = state["mapped"]
review_needed = _build_review_needed(mapped)
if not review_needed:
    return {"hil_1_corrections": {}, "current_node": "hil_1"}

if os.environ.get("CPIA_HIL_AUTO_BYPASS", "").lower() in ("1", "true", "on", "yes"):
    print(f"[hil_1] AUTO_BYPASS — review_needed={len(review_needed)} 무시, interrupt 우회",
          file=_sys_local.stderr, flush=True)
    return {"hil_1_corrections": {}, "current_node": "hil_1"}

corrections_raw = interrupt({"review_needed": review_needed})
corrections_raw = corrections_raw or {}
# langgraph 1.2.0: Command(resume=<falsy>) (예: 보정 0건 → {}) 는 그래프에 전달되지
# 않아 interrupt 가 재발생, hil_1 에 영구히 갇힌다. endpoint(api.py)가 빈 보정에도
# 항상 truthy 한 {"corrections": {...}} 래퍼로 resume 하므로 여기서 언랩한다.
# 래퍼 없는 직접 dict 호출(테스트/구버전 호환)은 그대로 통과.
if isinstance(corrections_raw, dict) and set(corrections_raw) == {"corrections"}:
    corrections_raw = corrections_raw["corrections"] or {}
corrections = {int(k): v for k, v in corrections_raw.items()}

corrected = _apply_corrections(mapped, corrections)

if cfg is not None and corrections:
    pg = PGClient(cfg.mapper.postgres_url)
    await pg.connect()
    try:
        # ... insert_mapping_correction 반복 ...
    finally:
        await pg.close()
```

- **AUTO_BYPASS 로직**: env `CPIA_HIL_AUTO_BYPASS` ∈ `{1, true, on, yes}` 시 stderr 로그 + 빈 corrections 통과. dev/검증 path (cycle 1~4 의 interrupt 무한 루프 회피).
- **falsy-resume 언랩 (`a8d17e4`, graph.py:263~264)**: langgraph 1.2.0 은 `Command(resume=<falsy>)` (보정 0건 → 빈 `{}`) 를 그래프에 전달하지 않아 interrupt 가 재발생 → hil_1 에 영구히 갇힌다. 해결: endpoint(`api.py:hil_1_resume`)가 보정 유무와 무관하게 항상 truthy 한 `Command(resume={"corrections": corrections_payload})` 래퍼로 호출하고, hil_1_node 가 `set(corrections_raw) == {"corrections"}` 인 경우만 한 겹 언랩(`corrections_raw["corrections"] or {}`)한다. 래퍼 없는 직접 dict resume(테스트/구버전)은 분기를 타지 않고 그대로 통과 (하위호환). 상세는 Issues §13 #M5 참조.
- **resume key 변환**: 언랩 후 `int(k) for k in corrections_raw.items()` — LangGraph `Command(resume=dict)` 의 key 가 str 로 직렬화되므로 int 복원. (drift #N5 명문화 미흡 — design-intent 이슈)

### 7.5 `atomizer_node` (graph.py:294)

- **진입 line**: graph.py:294
- **입력 state 키**: `parsed`, `mapped`, `run_id`
- **출력 state 키**: `atomized_ids`, `current_node`
- **핵심 코드** (graph.py:294~298):

```python
async def atomizer_node(state: CPIAState, cfg: GraphConfig) -> dict:
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    parsed: ParsedDailyReport = state["parsed"]
    atomized_ids = await atomize(state["mapped"], parsed, run_id, cfg.atomizer)
    return {"atomized_ids": atomized_ids, "current_node": "atomizer"}
```

- **에러 핸들링**: 없음 (atomize 자체 raise).

### 7.6 `forecaster_node` (graph.py:301)

- **진입 line**: graph.py:301
- **입력 state 키**: `mapped`, `run_id`, `date`
- **출력 state 키**: `forecast`, `current_node`
- **핵심 코드** (graph.py:301~305):

```python
async def forecaster_node(state: CPIAState, cfg: GraphConfig) -> dict:
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    today = _date.fromisoformat(state["date"])
    forecasts = await forecast(state["mapped"], run_id, today, cfg.forecaster)
    return {"forecast": forecasts, "current_node": "forecaster"}
```

### 7.7 `hil_2_node` (graph.py:308)

- **진입 line**: graph.py:308
- **입력 state 키**: `forecast`, `date`
- **출력 state 키**: `hil_2_selection`, `pre_optimizer_cases`, `current_node`
- **핵심 코드** (graph.py:321~358 cross-company 부분):

```python
risky = [r for r in state["forecast"] if r["risk_level"] in {"주의", "이상"}]
if not risky:
    return {"hil_2_selection": [], "pre_optimizer_cases": {}, "current_node": "hil_2"}

chroma = ChromaClient(host=cfg.optimizer.chroma_host, port=cfg.optimizer.chroma_port,
                     ssl=cfg.optimizer.chroma_ssl)
coll = chroma.get_or_create_daily_activities()
today = _date.fromisoformat(state["date"])

for r in risky:
    key = f"{r['company']}|{r['l6_main']}"
    baseline_unit = r.get("main_unit")
    if baseline_unit is None:
        pre_cases[key] = []
        payload_groups.append({..., "note": "no_main_unit"})
        continue

    # F5: coll.get 1회 호출 후 두 함수에 metadatas/documents 전달.
    # 2026-05-22: company hard filter 제거 — l6_main 만 매칭하여 cross-company case 활용
    result = coll.get(
        where={"l6_main": r["l6_main"]},  # 이전: $and [company, l6_main]
        include=["metadatas", "documents"],
    )
    metas, docs = result["metadatas"], result["documents"]
    baseline_value = _group_baseline(metas, None, r["l6_main"], baseline_unit)
```

- **F5/F7 정정**: Chroma `coll.get` 그룹당 1회만 호출 (round-trip 절감) + `_group_baseline` None 분기 (cold_start signal).
- **cross-company retrieve (2026-05-22)**: company hard filter 제거 — 합성 3사 외 75사가 cold_start fallback 빠지던 회귀 해소.
- **interrupt payload** (graph.py:411): `interrupt({"risky_groups": [{key, assessment, risk_level, reasoning, today_productivity, today_conditions, preview_cases}]})`.
- **resume**: `Command(resume=[group_key, ...])` — selection list 직접.

### 7.8 `optimizer_node` (graph.py:419)

- **진입 line**: graph.py:419
- **입력 state 키**: `forecast`, `hil_2_selection`, `pre_optimizer_cases`, `run_id`, `date`, `site_id?`, `mapped?`
- **출력 state 키**: `optimizer_advice`, `current_node`
- **핵심 코드** (graph.py:426~441):

```python
# 2026-05-20: risky 0 인 cycle (1사 sample 등) 도 view 산출 (KPI/EVM 등 7 view 는 advice 무관)
# 위해 early return 제거. optimize() 안에서 hil_2_selection 빈 → advice_rows=[] 진행.
run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
today = _date.fromisoformat(state["date"])
# site_id + mapped 전달 — optimize() 의 view 산출 (9 jsonb) block 진입 보장.
advice = await optimize(
    state["forecast"],
    state.get("hil_2_selection") or [],
    state.get("pre_optimizer_cases") or {},
    run_id, today, cfg.optimizer,
    site_id=state.get("site_id"),
    mapped=state.get("mapped"),
)
return {"optimizer_advice": advice, "current_node": "optimizer"}
```

- **변경 (2026-05-20)**: 이전 `if not state.get("hil_2_selection"): early return` 제거. risky 0 cycle 도 view_builder 산출 진입 보장.
- **site_id+mapped pass-through**: optimize() 안 view 산출 block 진입 보장 — 미전달 시 daily_reports 의 9 jsonb 모두 default ({} / []).

### 7.9 `reporter_node` (graph.py:444)

- **진입 line**: graph.py:444
- **입력 state 키**: `mapped`, `forecast`, `optimizer_advice`, `atomized_ids`, `site_id?`, `run_id`, `date`
- **출력 state 키**: `report_md`, `current_node`, `status`
- **핵심 코드** (graph.py:464~490):

```python
pg = PGClient(cfg.mapper.postgres_url)
await pg.connect()
try:
    site_id = state.get("site_id")
    if not site_id:
        async with pg._pool.acquire() as _con:
            _row = await _con.fetchrow("SELECT site_id FROM pipeline_runs WHERE run_id = $1", run_id)
        site_id = _row["site_id"] if _row else None
    if site_id:
        await update_site_last_run(pg, site_id=site_id, run_id=run_id)
        await update_site_hours_saved_cum(
            pg, site_id=site_id,
            atomized_count=len(state.get("atomized_ids", []) or []),
        )
    # 2026-05-20 Issue B fix: pipeline_runs.status='completed' + completed_at 갱신.
    async with pg._pool.acquire() as _con:
        await _con.execute(
            "UPDATE pipeline_runs SET status='completed', completed_at=NOW() WHERE run_id=$1",
            run_id,
        )
finally:
    await pg.close()

return {"report_md": report_md, "current_node": "reporter", "status": "completed"}
```

- **G8 / G2**: `update_site_last_run` (sites.last_run_id 갱신) + `update_site_hours_saved_cum` (atomized_count 기반 사람 수작업 절감 시간 누적).
- **Issue B fix (graph.py:482)**: `pipeline_runs.status='completed' + completed_at=NOW()` UPDATE. 이전엔 reporter 종료 후에도 status='running' 잔존 (cycle 7차 발견).
- **state.site_id PG fallback** (graph.py:467~471): state 가 site_id 를 propagate 안 한 경우 pipeline_runs SELECT 로 직접 fetch.

---

## 8. HIL 1 / HIL 2 interrupt + resume 흐름

### 8.1 HIL 1 — Mapper review

```
mapper_node ──┐
              ▼
       hil_1_node 진입
              │
   ┌──────────┼─────────────────┐
   ▼          ▼                 ▼
review_needed 0   review_needed≥1   review_needed≥1
   │              + AUTO_BYPASS    + AUTO_BYPASS 미설정
   │              │                 │
   │              ▼                 ▼
   │      stderr 로그       interrupt({"review_needed": [
   │      빈 corrections     {idx, work_content, company,
   │      통과               trade, wa, l6_main, mapping_conf,
   │                          mapping_source}, ...]})
   │              │                 │
   │              │                 │  ◀── FastAPI /resume (api.py:hil_1_resume)
   │              │                 │     Command(resume={"corrections": {
   │              │                 │       "0": {"wa":"X","l6_main":"Y"},
   │              │                 │       "3": {"wa":"Z","l6_main":"W"}}})
   │              │                 │     ↑ 항상 truthy 래퍼 (보정 0건도 전달)
   │              │                 ▼
   │              │         corrections_raw = {} or {...}
   │              │         if set(corrections_raw)=={"corrections"}:
   │              │             corrections_raw = ...["corrections"] or {}
   │              │         corrections = {int(k): v for k,v in ...}
   │              │         _apply_corrections(mapped, corrections)
   │              │         insert_mapping_correction × corrections.len
   ▼              ▼                 ▼
              return {mapped: [...corrected],
                      hil_1_corrections: corrections,
                      current_node: "hil_1"}
                              │
                              ▼
                          atomizer
```

- **interrupt payload schema (graph.py:182~191)**: 8 필드 (idx, work_content, company, trade, wa, l6_main, mapping_conf, mapping_source — FE Modal input 최소화).
- **resume payload (`a8d17e4`)**: `Command(resume={"corrections": {idx_str: {wa, l6_main}}})` — `api.py:hil_1_resume` (api.py:328~331) 가 truthy 래퍼로 감싼다. hil_1_node 가 `set(corrections_raw)=={"corrections"}` 분기로 언랩 (graph.py:263~264) 후, 내부 idx key 는 str (JSON 직렬화 결과) → `int(k)` 로 복원. **이 래퍼가 langgraph 1.2.0 의 falsy-resume gotcha (보정 0건 → 빈 dict 미전달 → interrupt 재발생) 를 막는다.** 래퍼 없는 직접 dict resume 은 분기를 타지 않고 그대로 통과 (테스트/구버전 호환).
- **답 안 한 row 처리 (graph.py:208~219)**: review_needed 였으나 corrections 에 없으면 Mapper 추천 그대로 수용 + `mapping_source="user_corrected"` + `requires_review=False`.
- **AUTO_BYPASS env 우회 (graph.py:247~255)**: `CPIA_HIL_AUTO_BYPASS in {1, true, on, yes}` → interrupt 건너뛰고 빈 corrections 통과.

**api.py 래퍼 (`a8d17e4`, api.py:320~331)** — endpoint 가 항상 truthy 래퍼로 resume:

```python
# corrections dict[str, CorrectionItem] → dict[str, dict] (JSON serializable)
corrections_payload: dict[str, dict] = {
    k: {"wa": v.wa, "l6_main": v.l6_main} for k, v in body.corrections.items()
}
# langgraph 1.2.0: Command(resume=<falsy>) (보정 0건 → {}) 는 전달되지 않아
# hil_1 interrupt 가 재발생한다. 항상 truthy 한 {"corrections": ...} 래퍼로 감싸
# 보정 유무와 무관하게 resume 가 전달되도록 한다 (hil_1_node 가 언랩).
result = await graph.ainvoke(
    Command(resume={"corrections": corrections_payload}),
    config={"configurable": {"thread_id": run_id}},
)
```

- `body.corrections` 가 빈 dict 여도 `{"corrections": {}}` 는 truthy → langgraph 가 그래프에 전달 → hil_1_node 가 interrupt 를 한 번만 통과시킨다. 이 래퍼가 없으면 빈 보정 resume 이 interrupt 를 재발생시켜 hil_1 에 영구히 갇힌다 (§13 #M5).

### 8.2 HIL 2 — Forecaster risky 검토

```
forecaster_node ──┐
                  ▼
           hil_2_node 진입
                  │
   ┌──────────────┼──────────────────┐
   ▼              ▼                  ▼
risky 0       risky ≥ 1            risky ≥ 1
              + baseline_unit None   + baseline_value None
              │                      │
              ▼                      ▼
       pre_cases[key]=[]       pre_cases[key]=[]
       note="no_main_unit"     note="cold_start_no_baseline"
              │                      │
              ▼                      ▼
       risky ≥ 1 + 정상 case
              │
              ▼
       Chroma coll.get (cross-company, l6_main 만 매칭)
       _group_baseline → fetch_degradation_cases (n=5)
       각 case → fetch_recovery_trajectory (window=7)
       pre_cases[key] = [cases...]
              │
              ▼
       interrupt({"risky_groups": [
         {key, assessment, risk_level, reasoning,
          today_productivity, today_conditions,
          preview_cases: [...]},
         ...
       ]})
              │  ◀── FastAPI /resume
              │     Command(resume=["GroupA|콘크리트", "GroupB|배근", ...])
              ▼
       selected = ... or []
       return {hil_2_selection: [...], pre_optimizer_cases: {...},
               current_node: "hil_2"}
              │
              ▼
       conditional_edge: hil_2_selection truthy → optimizer
                                       empty   → reporter
```

- **resume payload**: `Command(resume=[group_key, ...])` — selection list 직접 (str list).
- **risky 0건 분기 (graph.py:322~323)**: interrupt 미발생, empty selection 반환 → conditional_edge 가 reporter 분기.
- **AUTO_BYPASS 없음**: HIL 1 과 달리 HIL 2 는 env 우회 없음. scripts/run_one_cycle.py 가 자체 auto-select 처리.

### 8.3 `CPIA_HIL_AUTO_BYPASS` env 우회 로직

| env 값 | 동작 |
|---|---|
| (미설정) | interrupt 정상 발생 |
| `1`, `true`, `on`, `yes` (대소문자 무관) | stderr 로그 + 빈 corrections 통과 → atomizer 진입 |
| 그 외 (예: `0`, `false`) | interrupt 정상 발생 |

- 비교: `os.environ.get("CPIA_HIL_AUTO_BYPASS", "").lower() in ("1", "true", "on", "yes")` (graph.py:247).
- 의도: cycle 1~4 의 interrupt 무한 루프 (resume={} → re-raise) 해결 — dev/검증 path 만.

---

## 9. Collector IDLE loop (pipeline/collector/idle_worker.py)

### 9.1 전체 흐름

```
FastAPI lifespan startup
        │
        ▼
load_collector_config(graph_cfg=cfg)   ◀── env 9종 로드 (fail-fast)
        │
        ▼ COLLECTOR_ENABLED=true
asyncio.create_task(idle_loop(collector_cfg))
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  idle_loop (idle_worker.py:228)                              │
│  while not _shutdown:                                        │
│    imap = aioimaplib.IMAP4_SSL(host, port)                   │
│    imap.login + imap.select("INBOX")                         │
│    backoff = 1.0                                             │
│    await _drain_new(imap, cfg)   # 시작 시 누적 UNSEEN 처리   │
│    while not _shutdown:                                      │
│      idle_task = imap.idle_start(timeout=29*60)              │
│      push_msg = await imap.wait_server_push()                │
│      imap.idle_done()                                        │
│      if "EXISTS" in push_msg:                                │
│        await _drain_new(imap, cfg)                           │
│  except CancelledError: graceful exit                        │
│  except Exception: 지수 backoff (1→2→4→...→60s) + 재연결      │
└─────────────────────────────────────────────────────────────┘
        │
        ▼ EXISTS notification
┌─────────────────────────────────────────────────────────────┐
│  _drain_new (idle_worker.py:214)                             │
│  imap.search("UNSEEN") → uids                                │
│  for uid in uids:                                            │
│    await _process_one(imap, uid, cfg)                        │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  _process_one (idle_worker.py:153)                           │
│  imap.fetch(uid, "(RFC822)") → email.message_from_bytes      │
│  message_id = msg.get("Message-ID")  → 없으면 skip+Seen     │
│  fetch_collector_inbox_by_message_id → dedup skip            │
│  _extract_attachments → [(filename, bytes), ...]            │
│  for att_name, att_bytes:                                    │
│    meta = parse_filename(att_name)                           │
│    if meta is None: _to_dead_letter; continue                │
│    path = _save_to_input_dir(att_name, att_bytes, date, cfg) │
│    sub_message_id = f"{message_id}#{att_name}"              │
│    insert_collector_inbox(message_id=sub_message_id, ...)    │
│    create_task(run_for_attachment(path, meta, site_id,       │
│                sub_message_id, cfg))   ◀── fire-and-forget  │
│  imap.store(uid, "+FLAGS", "\\Seen")                         │
└─────────────────────────────────────────────────────────────┘
        │
        ▼ fire-and-forget
┌─────────────────────────────────────────────────────────────┐
│  run_for_attachment (idle_worker.py:90)                      │
│  async with _GRAPH_SEM (CPIA_COLLECTOR_CONCURRENCY=2):       │
│    run_id = uuid.uuid4()                                     │
│    update_collector_inbox_status(message_id, run_id,         │
│                                   parse_status="running")    │
│    try:                                                       │
│      graph = build_graph(cfg.graph_cfg)                      │
│      await graph.ainvoke({                                    │
│        "run_id": str(run_id),                                 │
│        "input_files": [str(attachment_path)],                 │
│        "site_id": site_id,         # D-11                     │
│        "message_id": message_id,   # collector_node 가 사용   │
│        "postgres_url": cfg.postgres_url,                      │
│      }, config={"configurable": {"thread_id": str(run_id)}})  │
│    except Exception as e:                                     │
│      update_collector_inbox_status(parse_status="failed",     │
│                                     error=str(e)[:1000])      │
│      return                                                    │
│    update_collector_inbox_status(parse_status="completed")    │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 핵심 룰

| 항목 | 룰 |
|---|---|
| `_shutdown` | module-level `asyncio.Event()` (idle_worker.py:33). lifespan finally 에서 `request_shutdown()` + `task.cancel()` |
| `_GRAPH_SEM` | `Semaphore(CPIA_COLLECTOR_CONCURRENCY=2)` (idle_worker.py:34) — graph 동시 invoke 제한 |
| dedup | `fetch_collector_inbox_by_message_id(message_id)` PG 체크 → 중복이면 skip + Seen |
| sub_message_id | `f"{message_id}#{att_name}"` — 1 메일 안 N 첨부 → N collector_inbox row |
| dead_letter | 파일명 미일치 시 `data/input/dead_letter/<stem>_<8hex>.<suffix>` 저장 + WARN 로그 |
| IDLE timeout | 29분 (RFC 2177 권장 30분 직전 갱신) |
| 재연결 backoff | `1.0 → 2.0 → ... → 60.0s` 지수 (cap 60s) |
| Seen flag | `_process_one` 종료 시 `imap.store(uid, "+FLAGS", "\\Seen")` — graph 실패해도 Seen (dead_letter / failed row 로 추적) |

### 9.3 env 9종 (load_collector_config — config.py:35)

| env | default | 의미 |
|---|---|---|
| `COLLECTOR_ENABLED` | `false` | true 시 idle_loop task spawn |
| `COLLECTOR_IMAP_USER` | `""` | enabled 시 필수 (fail-fast) |
| `COLLECTOR_IMAP_APP_PASSWORD` | `""` | enabled 시 필수 (fail-fast) |
| `COLLECTOR_IMAP_HOST` | `imap.gmail.com` | |
| `COLLECTOR_IMAP_PORT` | `993` | |
| `COLLECTOR_DEFAULT_SITE_ID` | `m15x-ph3-ibl` | D-11 default site |
| `COLLECTOR_INPUT_DIR` | `data/input` | 저장 root |
| `COLLECTOR_DEAD_LETTER_DIR` | `data/input/dead_letter` | |
| `POSTGRES_URL` | (env 필수) | KeyError 전파 |
| `CPIA_COLLECTOR_CONCURRENCY` | `2` | graph 동시 invoke 제한 |

---

## 10. 신규 vs 기존 collector 관계 (3 모듈)

| 모듈 | 위치 | 역할 | 호출자 | 현 상태 |
|---|---|---|---|---|
| `pipeline/collector/` 폴더 | (신규 IDLE 진입 path) | IMAP IDLE loop + dedup + 첨부 추출 + dead_letter + graph fire-and-forget | FastAPI lifespan (api.py:180~183) — `COLLECTOR_ENABLED=true` 일 때 task spawn | **활성** (D-12 production path) |
| `pipeline/agents/collector.py` | (legacy directory scan) | `discover_daily_reports` + `collect_and_parse` — dir 안 xlsx 일괄 파싱 | (현재 production 미사용) — scripts/backfill 류가 직접 사용 가능, run_one_cycle.py 도 별도 path | **legacy** (본 cycle 변경 0, 사용 잔존) |
| `pipeline/agents/collector_node.py` | (graph 진입 노드) | 1 첨부 경로 검증 + `parse_filename` 분해 + `collector_inbox` UPDATE | `build_graph` START 직후 노드 (graph.py:614) | **활성** (D-12 production 진입점) |

### 10.1 데이터 흐름 차이

- **production (IDLE)**: `idle_worker._process_one` (메일 1통, N 첨부) → `insert_collector_inbox` × N → `create_task(run_for_attachment)` × N → 각각 `graph.ainvoke(input_files=[path], message_id=sub_message_id, postgres_url=...)` → `collector_node` 가 input_files[0] 검증 + UPDATE(running) + meta 반환 → `parser_node` → ...
- **legacy (dir scan)**: `agents/collector.collect_and_parse(dir, cfg)` → `list[ParsedDailyReport]` 반환 (graph 진입 X) — 일괄 batch 처리용. 현 production graph 흐름 밖에 위치.

### 10.2 명명 충돌 주의

- `pipeline/agents/collector.py` 의 `CollectorConfig` (legacy, 1 필드: file_concurrency)
- `pipeline/collector/config.py` 의 `CollectorConfig` (신규, 10 필드: env wiring)

두 클래스 동시 import 시 alias 필수. 현재 graph.py 가 양쪽 다 import 안 함 (graph.py 는 collector_node 만 import). 향후 통합 필요 (Medium issue #M2 — §13 참조).

---

## 11. LLM 호출 위치

### 11.1 Orchestration 안 LLM 직접 호출 없음

- `graph.py`, `state.py`, `checkpointer.py`, `constants.py`, `collector_node.py`, `parser_node.py`, `collector/*`, `_concurrency.py` 모두 **OpenAI/Azure SDK import 0**.
- LLM 은 각 agent 모듈 안 (mapper.py, parser.py, parser_llm.py, forecaster/agent.py, optimizer/agent.py, atomizer.py, reporter.py) 에서 호출.

### 11.2 `_concurrency.get_llm_semaphore()` 사용처

```bash
# grep 결과 (agents/ 하위)
forecaster/agent.py    # forecaster() group 루프 + asyncio.gather
optimizer/agent.py     # optimize() forecast 루프 + asyncio.gather
atomizer.py            # batch embedding
```

- 본 cycle 신설 (`1e24dc6`). event loop 별 lazy Semaphore (기본 4).
- 사용 패턴: `async with get_llm_semaphore(): await asyncio.to_thread(azure_sync_call, ...)`.
- mapper.py 는 별도 `CPIA_MAPPER_CONCURRENCY` (graph.py:38, 기본 4) Semaphore 사용 — Azure rate-limit 영역 분리. 향후 통합 검토 (Low issue #L4 — §13 참조).

### 11.3 LLM rate-limit 책임 계층

| 레이어 | semaphore | env |
|---|---|---|
| graph mapper 병렬 | `asyncio.Semaphore(4)` (graph.py:84) | `CPIA_MAPPER_CONCURRENCY` |
| agent 내부 (forecaster/optimizer/atomizer) | `get_llm_semaphore()` event-loop 별 | `CPIA_LLM_CONCURRENCY` |
| collector graph invoke 동시성 | `asyncio.Semaphore(2)` (idle_worker.py:34) | `CPIA_COLLECTOR_CONCURRENCY` |

---

## 12. Integration points

### 12.1 db.py 연동

| 위치 | 호출 | 용도 |
|---|---|---|
| graph.py:73~82 | `PGClient.fetch_bp_candidates` | mapper BP cand_pool batch |
| graph.py:110~118 | `PGClient.insert_parser_report` | mapper parser 결과 영속 |
| graph.py:120~125 | `PGClient.insert_parser_activities_batch` | 시트4 정규화 row |
| graph.py:130~135 | `PGClient.insert_parser_job_allocations_batch` | 시트2 (G24) |
| graph.py:136~143 | `PGClient.insert_parser_equipment_allocations_batch` | 시트3 (G24) |
| graph.py:149~153 | `PGClient.insert_mapper_activities_batch` | mapper 결과 33 컬럼 |
| graph.py:157~159 | `PGClient.fetch_all` (SELECT COUNT) | 같은 트랜잭션 검증 (silent fail 진단) |
| graph.py:265~283 | `PGClient.insert_mapping_correction` | HIL 1 corrections |
| graph.py:464~478 | `update_site_last_run` + `update_site_hours_saved_cum` | reporter G8/G2 |
| graph.py:482~486 | `pipeline_runs SET status='completed'` (raw SQL) | reporter Issue B fix |
| collector_node.py:44~49 | `update_collector_inbox_status` | D-12 running UPDATE |
| idle_worker.py:105~110 | `update_collector_inbox_status` (running) | listener 안전망 |
| idle_worker.py:135~140 | `update_collector_inbox_status` (failed) | graph 예외 시 |
| idle_worker.py:148 | `update_collector_inbox_status` (completed) | graph 성공 |
| idle_worker.py:173 | `fetch_collector_inbox_by_message_id` | dedup |
| idle_worker.py:198~206 | `insert_collector_inbox` | 1 첨부 = 1 row |

### 12.2 api.py 연동

| 위치 | import | 용도 |
|---|---|---|
| api.py:28 | `load_collector_config` | env 로드 |
| api.py:29 | `idle_loop`, `request_shutdown` | lifespan 안 task |
| api.py:31 | `exporter_router` (`pipeline/exporter_routes.py`) | router include |
| api.py:170 | `build_graph(cfg)` | lifespan app.state.graph |
| api.py:180~183 | `asyncio.create_task(idle_loop(collector_cfg))` | startup collector task |
| api.py:188~194 | `request_shutdown() + task.cancel()` | shutdown graceful |
| api.py:297~ | `/api/runs/{run_id}/hil_1/resume` | HIL 1 resume endpoint. `Command(resume={"corrections": payload})` truthy 래퍼 (api.py:328~331) — langgraph 1.2.0 falsy-resume gotcha 회피. key str→int 변환 + 래퍼 언랩은 hil_1_node 책임 (graph.py:263~265) |

### 12.3 각 agent 모듈 import 위치 (graph.py)

| graph.py line | import | 용도 |
|---|---|---|
| 19 | `from pipeline.agents.atomizer import AtomizerConfig, atomize` | atomizer_node |
| 20 | `from pipeline.agents.collector_node import collector_node as _collector` | build_graph collector 노드 |
| 21 | `from pipeline.agents.forecaster import ForecasterConfig, forecast` | forecaster_node |
| 22 | `from pipeline.agents.mapper import MapperConfig, _prorate_mh, map_activity` | mapper_node |
| 23 | `from pipeline.agents.parser_node import parser_node as _parser` | build_graph parser 노드 |
| 24 | `from pipeline.agents.optimizer.agent import OptimizerConfig, optimize` | optimizer_node |
| 25 | `from pipeline.agents.parser_post import normalize_company` | mapper_node 정규화 |
| 26~30 | `from pipeline.agents.optimizer.retrieve import _group_baseline, fetch_degradation_cases, fetch_recovery_trajectory` | hil_2_node |
| 31 | `from pipeline.agents.reporter import ReporterConfig, report` | reporter_node |
| 32 | `from pipeline.checkpointer import build_checkpointer` | 3 builder |
| 33 | `from pipeline.chroma_client import ChromaClient` | hil_2_node |
| 34 | `from pipeline.db import PGClient, update_site_hours_saved_cum, update_site_last_run` | mapper/hil_1/reporter |
| 35 | `from pipeline.state import Activity, CPIAState, ParsedDailyReport` | 타입 |

### 12.4 collector 폴더 외부 import

```python
# idle_worker.py
from pipeline.collector.config import CollectorConfig
from pipeline.collector.filename_parser import ParsedFilename, parse_filename
from pipeline.db import (PGClient, fetch_collector_inbox_by_message_id,
                         insert_collector_inbox, update_collector_inbox_status)
from pipeline.graph import build_graph  # ← run_for_attachment 안 지연 import (circular 회피)

# config.py
from pipeline.graph import GraphConfig  # ← module-level import (graph.py 가 collector 미참조라 OK)

# collector_node.py
from pipeline.collector.filename_parser import parse_filename
from pipeline.db import PGClient, update_collector_inbox_status
from pipeline.state import CPIAState
```

- **circular import 회피**: `idle_worker.run_for_attachment` 안에서 `from pipeline.graph import build_graph` 지연 import. graph.py 는 collector_node 만 참조, idle_worker 미참조.

---

## 13. 이슈 표

### 13.1 Critical (당장 fix 필요)

| ID | 영역 | 위치 | 설명 | 다음 행동 |
|---|---|---|---|---|
| #C1 | hil_1_node interrupt re-raise | graph.py:240~248 | `CPIA_HIL_AUTO_BYPASS` env 가 검증/dev path 만 의도이나 prod env 에 실수로 박히면 **모든 mapping_corrections 가 silent skip** + low-conf 매핑이 user_corrected 로 둔갑. env 검사 시 stderr 경고만 — 로그 grep 안 하면 안 잡힘 | (a) api.py lifespan 에서 prod 환경 + AUTO_BYPASS=true 조합 시 WARN log + sentry, (b) sites 메타에 prod flag 추가하여 hil_1_node 에서 cross-check |
| #C2 | CPIAState.parsed 타입 drift | state.py:237 | annotation 은 `list[Activity]` 이지만 실제는 `ParsedDailyReport`. mapper_node (graph.py:62) 가 명시적으로 `ParsedDailyReport` 로 캐스팅 — IDE 타입체크 우회. drift detection 안 됨 | annotation 을 `ParsedDailyReport` 로 수정 (mypy/pyright 가 mapper_node 의 `.activities` 접근 검증 가능) |

### 13.2 Medium (다음 cycle)

| ID | 영역 | 위치 | 설명 | 다음 행동 |
|---|---|---|---|---|
| #M1 | mapper_node PG 비-atomic | graph.py:108~165 | 5 INSERT 사이 부분 실패 시 partial state (parser_report 있고 mapper_activities 없음). 재실행은 멱등 ON CONFLICT 라 회복 가능하나 같은 run_id 가 두 번 graph 도는 시점에 RC | `async with pg._pool.acquire() as con: async with con.transaction():` 묶기 (단일 transaction). 현재는 connection 단위 autocommit |
| #M2 | CollectorConfig 명명 충돌 | agents/collector.py:23 + collector/config.py:15 | 같은 이름 클래스 2개. 향후 import 충돌 위험. legacy agents/collector.py 가 prod 흐름 밖이라 당장 문제 없음 | legacy `agents/collector.py` 의 `CollectorConfig` → `LegacyDirCollectorConfig` rename 또는 폐기 (현재 prod 미사용) |
| #M3 | atomized_demo_graph 호출자 책임 분산 | graph.py:531~572 | `mapped` hydrate + `pipeline_runs` INSERT 모두 호출자 책임 (atomizer 의 `assert_pipeline_run_exists` fail-fast). 백필 스크립트마다 boilerplate 반복 | helper `prepare_atomized_run(run_id, site_id, date, mapped_rows)` 신설 (PG INSERT + state assembly 한 곳에) |
| #M4 | HIL 2 AUTO_BYPASS 없음 | graph.py:308~416 | HIL 1 에는 `CPIA_HIL_AUTO_BYPASS` 있으나 HIL 2 는 없음. scripts/run_one_cycle.py 가 자체 auto-select 로 우회 — 실 production listener (idle_worker) path 에서는 interrupt 멈춤 | 대칭성 위해 `CPIA_HIL_AUTO_BYPASS` 가 HIL 2 도 우회 (모든 risky key 자동 선택) 또는 별도 `CPIA_HIL2_AUTO_SELECT` env 추가 |
| #M5 ✅ fixed (`a8d17e4`) | langgraph 1.2.0 falsy-resume gotcha | api.py:328~331 + graph.py:259~264 | langgraph 1.2.0 은 `Command(resume=<falsy>)` (보정 0건 → 빈 `{}`) 를 그래프에 전달하지 않아 hil_1 interrupt 가 재발생 → hil_1 에 영구히 갇힌다 (HIL 1 "전부 승인" 케이스가 무한 루프). **이미 fix됨**: `api.py:hil_1_resume` 가 항상 truthy `Command(resume={"corrections": payload})` 래퍼로 호출, `hil_1_node` 가 `set(corrections_raw)=={"corrections"}` 분기로 언랩. 래퍼 없는 직접 dict resume 은 하위호환 통과 | (완료) 향후 langgraph 버전업 시 falsy-resume 동작 회귀 테스트 유지. 동일 패턴을 HIL 2 재도입 시에도 적용 |

### 13.3 Low (백로그)

| ID | 영역 | 위치 | 설명 | 다음 행동 |
|---|---|---|---|---|
| #L1 | `raw_texts` 미사용 | state.py:236 | 필드 정의되어 있으나 어떤 노드도 채우거나 읽지 않음 | 다음 cycle 삭제 또는 collector_node 가 첨부 raw text 담는 용도로 활용 |
| #L2 | `update_collector_inbox_status` 중복 | collector_node.py:44 + idle_worker.py:105 | listener 가 한 번, collector_node 가 다시 한 번 UPDATE (running). idempotent 라 functional 영향 없으나 PG round-trip 1회 낭비 | listener UPDATE 제거 (collector_node 가 single source of truth) 또는 collector_node UPDATE 제거 (listener 만) |
| #L3 | Command(resume) key 변환 룰 미명문화 | graph.py:252 | `corrections = {int(k): v for k, v in corrections_raw.items()}` — JSON 직렬화로 key 가 str 되는 룰 docstring 만 (api.py:227 주석). spec 문서화 미흡 | docs/architecture/api-contract.md 에 명시 |
| #L4 | LLM Semaphore 분리 | graph.py:38 + _concurrency.py:15 | mapper 는 `CPIA_MAPPER_CONCURRENCY`, 그 외 agents 는 `CPIA_LLM_CONCURRENCY` — 운영자 두 env 외워야 함 | 통합 또는 명명 정합 (예: `CPIA_AGENT_LLM_CONCURRENCY_<MAPPER\|GENERIC>`) |
| #L5 ✅ resolved (`a8d17e4`) | parser_node sync wrapper | parser_node.py:40 | (해소) 이전 `def parser_node(...)` sync 였으나 multi-file merge 도입과 함께 `async def parser_node(...)` 로 전환 — `to_thread(parse_daily_report)` Semaphore 4 비동기 병렬. graph 의 다른 노드(collector/mapper) 와 async 통일 | (완료) — |
| #L6 | `_LazyAsyncPostgresSaver._opened` race | checkpointer.py:52 | `if not self._opened: await pool.open(); self._opened = True` — `asyncio.Lock` 없음. 첫 호출이 2 concurrent 면 pool.open() 2회 호출 가능 (psycopg_pool 이 자체 idempotent 하지만 contract 보장 X) | `asyncio.Lock` 으로 `_ensure_open` 보호 |
| #L7 | dead_letter race | idle_worker.py:81~87 | 같은 첨부가 동시 처리 시 file path uuid suffix 로 충돌 회피하나, dedup 은 message_id 단위라 sub_message_id 같으면 race 가능. 현실 빈도 매우 낮음 | `INSERT collector_inbox ON CONFLICT (message_id) DO NOTHING` 이미 race-safe — file write 만 추가 lock 검토 |
| #L8 | IDLE shutdown timing | idle_worker.py:188~194 | lifespan shutdown 시 `request_shutdown() → task.cancel()` 즉시 cancel — `idle_done()` 후처리 미완료 가능 | `asyncio.wait_for(task, timeout=5)` 로 graceful 5초 대기 후 cancel |

---

## 14. 다음 cycle 권장 작업

1. **#C1 / #C2 fix** — AUTO_BYPASS prod 가드 + parsed 타입 annotation 정정 (둘 다 1줄~5줄 변경).
2. **#M1 transaction 묶기** — mapper_node 5 INSERT atomicity.
3. **HIL 2 AUTO_BYPASS env 추가** (#M4) — dev/검증 path 대칭성 + idle_worker prod 진행 보장.
4. **`raw_texts` 필드 정리** (#L1) — 진짜 삭제 또는 collector_node 가 활용.
5. **`agents/collector.py` deprecate** (#M2) — 신규 IDLE worker 가 production path, legacy dir-scan path 폐기 또는 별도 `scripts/` 이동.

---

## 15. 검증 상태 (d317be9)

| 항목 | 측정 | 상태 |
|---|---|---|
| build_graph topology | 9 노드 (collector → parser → mapper → hil_1 → atomizer → forecaster → hil_2 → optimizer\|reporter → END) | ✅ |
| parser_node async multi-file merge (`a8d17e4`) | `input_files` 전체 to_thread Semaphore 4 병렬 파싱 + `_merge_reports` concat. `_parser_p` 가 `return await _parser(state)` (graph.py:595~598) | ✅ |
| hil_1 falsy-resume fix (`a8d17e4`) | api.py truthy 래퍼 `Command(resume={"corrections": payload})` (api.py:328~331) + hil_1_node 언랩 분기 (graph.py:263~264). 보정 0건 resume 시 interrupt 재발생 없이 통과 | ✅ |
| collector_node 단위 테스트 | `pipeline/tests/test_collector_node.py` 70 LOC | ✅ |
| parser_node 단위 테스트 | `pipeline/tests/test_parser_node.py` | ✅ |
| idle_worker 단위 테스트 | `c1cba0f` test commit | ✅ |
| CPIAState D-12 필드 | bp_name/project/message_id/postgres_url 4 신규 키 정식 정의 | ✅ |
| HIL 2 cross-company retrieve | 합성 3사 외 75사 cold_start fallback 해소 | ✅ |
| pipeline_runs.status='completed' UPDATE | reporter 종료 시 자동 갱신 | ✅ |
| FastAPI lifespan collector task | `COLLECTOR_ENABLED=true` 일 때 idle_loop spawn + shutdown graceful cancel | ✅ |
| 동시성 제어 | mapper 4 + LLM agents 4 + collector graph 2 (env 3종) | partial (명명 정합 미흡 #L4) |

---

*최종 수정: 2026-06-01 (`d317be9`) — parser_node async multi-file merge + hil_1 falsy-resume fix surgical 갱신. 이전: 2026-05-26 (`1ba783f`)*
