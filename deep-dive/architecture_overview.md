# CPIA Architecture Overview (deep-dive 라이트)

- **Generated**: 2026-05-26 (Mock 재설계 PR #40 + AWS 마이그 + view_builder MEDIAN + backfill_v2 + ForecastChart catch-up + site_summary LLM cycle 후 갱신)
- **Git SHA**: `1ba783f` (A_Track HEAD). 이전 스냅샷 `ef7c6cd` 대비 **70+ commits, 204 files, +30,151 / -3,055 LOC, pipeline non-test 8,928 → 11,656 (+31%)**
- **Branch**: `A_Track` (main 머지 완료: `7e9e1a1` 산식 A + site_summary, `1ba783f` Mock 재설계 sync). 다른 세션이 `view_builder.py` 1 줄 변경 working tree 보유 (`trade IN ('건축','토목')` 필터 제거).
- **Range**: pipeline 전체 (9 active subsystem + 신규 exporter + collector IDLE worker + scripts 20+) + Next.js BFF (web/lib/pg.ts + transforms.ts + diagnosis.ts catch-up) — `~155k LOC` (.venv 제외)
- **Tests**: 392 baseline + 본 cycle 9 신규 (exporter_endpoint / exporter_render / filename_parser / forecaster_concurrency / idle_worker / llm_concurrency / optimizer_concurrency / parser_node / db_collector_inbox)
- **Pair**: `./design-intent/INDEX.md` (T1/T2 카탈로그) + `./deep_dive_<X>.md` 8 개 (각 300~1,100 줄 상세) + `../data-contract/INDEX.md` (FE↔BE 정합)

본 문서는 함수별 깊이 보다는 **시스템 다이어그램 + 서브시스템 요약 + Data layer + 변경 인터페이스 + 이슈 표** 위주. 함수 단위 깊이는 `./deep_dive_<X>.md` 참조.

> **이번 cycle 갱신 요지 (vs ef7c6cd / 2026-05-20)**:
>
> - **graph 진입점 이동 (D-12)**: `mapper` → `collector_node` (`55cad90`) + `parser_node` 분리 (`6b9db7c` state-key drift fix `parsed_reports→parsed`, `report_date→date`). 9-노드 production topology 완성 (collector → parser → mapper → hil_1 → atomizer → forecaster → hil_2 → optimizer → reporter).
> - **IMAP IDLE Collector 신설** (`pipeline/collector/` 폴더 신규): `filename_parser.py` 64 + `idle_worker.py` 260 + `config.py` 68 + `agents/collector_node.py` 63. Gmail IMAP IDLE 으로 첨부 자동 fetch → graph invoke. `collector_inbox` 테이블 + 4 helper.
> - **Exporter 신설** (3 신규 파일): `agents/exporter.py` 301 (`render_xlsx` + 4 시트 `_fill_*` + COL dict + timeshift 헬퍼) + `exporter_routes.py` 47 (`/export/run` FastAPI route) + `exporter_templates/consolidated_template.xlsx`. **reporter (graph 마지막 노드) ≠ exporter (FastAPI 라우트)** 분리 시작 — rename backlog (CLAUDE.md 가 약속한 reporter→exporter rename, 파일명은 미시행).
> - **공정률 산식 (A) WV × MH 가중** (`c0a0641`, view_builder.py:880~1021 `_build_s_curve`): 분모 = `SUM(plan_wv × plan_mh_rev2)`, planned = `SUM(weight × linear_progress)`, actual = `SUM(weight × MIN(1, cum_qty/plan_qty))` ((wa, l6) 매칭, company 무시 — 매칭률 100%). `full_grid` cross join 으로 actual 단조 증가 보장.
> - **Site 수준 LLM narrative** (`21c10f7`): `optimizer/site_summary.py` 141 LOC 신규 + `daily_reports.site_summary_text` 컬럼 + Azure JSON response_format. backfill_v2 `--with-summary` 플래그로 opt-in. live `optimize()` 미연결 (backlog).
> - **view_builder.py 752 → 1,882 LOC (+1,130, 2.5×)**: 산식 A + 4 시나리오 percentile + `_build_productivity_views_v2` (`_v2` 별도 함수 — `agent.py` 는 v1, backfill 은 v2 → 같은 컬럼 다른 산식, 잠재 drift) + KPI delay_days `AVG → PERCENTILE_CONT(0.5)` (`e9b66d4` outlier robust, 167,871일 → 11일) + quadrant ↔ by_wp `wp_id` Jaccard 11% → 100% (`2c2ba75`).
> - **ForecastChart catch-up 시각화** (FE): plan/actual/forecast/AI 시나리오 4선 + `lastActual → plan[today+recoveryDays]` slope 후 plan 동행 + 빨강 dashed 통일 + 마커 분산 (top/bottom). `web/lib/diagnosis.ts` `buildScenarioCurve` 가 catch_up 객체 반환.
> - **/api/mock/report list/detail 분리 (perf)** (`415c990` + `cc4e689`): 9 컬럼 jsonb 전체 (32MB) → list 는 4 필드만 (50KB, 600× 축소), detail 은 `/api/mock/report/[date]` 분리. Agent Tasks / Export / Reports / Review 진입 지연 제거.
> - **Concurrency 4× 단축**: `get_llm_semaphore()` + `CPIA_LLM_CONCURRENCY` (default 4) — forecaster `asyncio.gather` (10분→2.5분) + optimizer `to_thread` + atomizer batch_size 16→64.
> - **Mock 재설계 + AWS 마이그**: `synthetic v2` → `seed_dummy_year.py` 905 LOC (F3 분포 + prod target 90% 역산 + l5_disc trade + l7.5 + degradation_cases) + `scripts/aws_backup_and_migrate.py` 225 (pg_dump → SCP → restore, 절대경로) + `chroma_export/import.py` JSONL snapshot + 7 테이블 `is_mock` 컬럼 backfill (sites/daily_reports/forecasts/optimizer_advice/mapping_corrections/mapper_activities/mapped_history).
> - **신규 PG migration 4종**: `2026-05-19_collector_inbox.sql` / `2026-05-20_add_is_mock.sql` / `2026-05-21_phase1.sql` / `2026-05-23_mapper_l7_5_columns.sql` (mapper_activities 에 `l5_disc / l7_sub / l7_5_activity / sub_work_area` 4 컬럼). **단, `daily_reports.site_summary_text` 는 migration 파일 없음 — fresh DB rebuild 시 UndefinedColumnError 위험 (이슈 #N13)**.
> - **Backlog (다음 cycle)**:
>   - reporter → exporter 파일명 rename (CLAUDE.md 약속) + 13 import + GraphConfig.reporter + `_AGENTS_META[4]`
>   - site_summary 의 live `optimize()` 연결 (현재 backfill only)
>   - view_builder v1 ↔ v2 통일 (`_build_productivity_views` ↔ `_build_productivity_views_v2`)
>   - `mapped_history.trade` SQL 누락 (atomizer commit msg 가 약속했으나 SQL/dict 둘 다 미적용)
>   - exporter B_Track FE swap (`NEXT_PUBLIC_FASTAPI_BASE` env + `ConsolidatedReportCard.tsx` handleExport)
>   - 9-22 forecaster outlier root cause (외장판넬공사 동신패널 `plan_main_qty` 폭주 — `6a89848` 부분 해결, 잔존)

---

## 1. 시스템 다이어그램 (전체)

```
                              ┌──────────────────────────────────────────────────────────────────┐
                              │              [B_Track] Next.js Dashboard (web/)                   │
                              │   home / dashboard / tasks / reports / review / export            │
                              │   Layer 1 (현장 카드 6 site) / Layer 2 (상세 + HIL Modal)        │
                              │   ★ ForecastChart 4선 catch-up + site_summary_text narrative     │
                              └─────────────────────┬────────────────────────────────────────────┘
                                                    │ HTTP fetch
                              ┌─────────────────────┴────────────────────────────────────────────┐
                              │   Next.js API Routes — BFF (web/app/api/mock/* + lib/pg.ts)      │
                              │   • /api/mock/report      ← list (4 col, 50KB, 600× 축소)         │
                              │   • /api/mock/report/[d]  ← detail (9 jsonb + site_summary_text)  │
                              │   • /api/mock/dashboard  /agent-tasks  /agent-tasks/[d]           │
                              │     /consolidated  /review                                         │
                              │   • web/lib/transforms.ts (G1/G6/G20/G22/G18 11 transform)        │
                              │   • web/lib/diagnosis.ts buildScenarioCurve (catch-up + plan 동행) │
                              └─────────────────────┬────────────────────────────────────────────┘
                                                    │ asyncpg pool (PG direct SELECT)
                                                    │ + HTTP (FastAPI proxy, 점진 swap)
   ┌────────────────────────────────────────────────┴────────────────────────────────────────────┐
   │                                                                                              │
   │  ┌────────────────────────────────────┐    ┌────────────────────────────────────────────┐   │
   │  │   pipeline/api.py — FastAPI 1073   │    │   pipeline/exporter_routes.py — 47 NEW     │   │
   │  │   • GET /health                    │    │   • POST /export/run                       │   │
   │  │   • GET /api/sites (LATERAL fc)    │    │     (run_id → fetch_sheet_data → xlsx)     │   │
   │  │   • GET /api/runs/{id}/optimizer   │    │                                              │   │
   │  │   • GET /api/runs/{id}/wp_summary  │    │   pipeline/api.py:lifespan                  │   │
   │  │   • GET /api/sites/{id}/reports    │    │   ★ collector idle_loop task + exporter    │   │
   │  │   • GET /api/dashboard/performance │    │     router include (4b8a955)                │   │
   │  │   • GET /api/dashboard/impact      │    └────────────────────────────────────────────┘   │
   │  │   • GET /api/agents/status         │                                                       │
   │  │   • GET /api/sites/{id}/wbs_tree   │    ┌────────────────────────────────────────────┐   │
   │  │   • GET /api/tasks                 │    │   pipeline/collector/ — IMAP IDLE NEW       │   │
   │  │   • POST /api/runs/{id}/hil_1/...  │    │   • idle_worker.py 260 (asyncio loop)       │   │
   │  └────────────────────────────────────┘    │   • filename_parser.py 64 (YYYYMMDD_*.xlsx)│   │
   │                                            │   • config.py 68 (CollectorConfig)           │   │
   │                                            │   + collector_inbox PG 테이블 + 4 helper      │   │
   │                                            └─────────────────┬──────────────────────────┘   │
   └────────────────────────────────────────────────────────────┬─┴──────────────────────────────┘
                                                                │ Gmail attachment → graph.invoke()
                                                                │ + Postgres direct SELECT
   ┌────────────────────────────────────────────────────────────┴──────────────────────────────────┐
   │                           LangGraph StateGraph (pipeline/graph.py 628)                         │
   │                                                                                                │
   │   build_graph (production — 9 node):                                                            │
   │   ┌──────────┐  ┌──────────┐  ┌────────┐  ┌──────────┐  ┌──────┐  ┌──────────┐  ┌──────────┐  │
   │   │collector │→│  parser   │→│ mapper  │→│   hil_1  │→│atomize│→│forecaster│→│   hil_2  │  │
   │   │ NEW      │ │  NEW      │ │ resolve │ │ AUTO_    │ │ Chroma│ │ asyncio  │ │ risky    │  │
   │   │ node 63  │ │ wrapper 25│ │ _wa 7   │ │ BYPASS   │ │ batch │ │ gather 4 │ │ retrieve │  │
   │   │ (55cad9) │ │ (6b9db7c) │ │ stages  │ │ env      │ │ 16→64 │ │ (4×)     │ │ cross-co │  │
   │   └──────────┘  └──────────┘  └─────────┘  └────┬─────┘  └──────┘  └──────────┘  └────┬─────┘  │
   │       NEW           NEW                          │interrupt                                │       │
   │                                          Command(resume=                                  │       │
   │                                          hil_1_corrections)                               ▼       │
   │                                                                                  ┌────────────┐ │
   │                                                                                  │ optimizer  │ │
   │                                                                                  │ ★ 산식 A   │ │
   │                                                                                  │ view_b 1882│ │
   │                                                                                  │ site_summary│ │
   │                                                                                  │ NEW 141    │ │
   │                                                                                  └─────┬──────┘ │
   │                                                                                        ▼         │
   │                                                                                  ┌────────────┐ │
   │                                                                                  │  reporter  │ │
   │                                                                                  │ G8 last_run│ │
   │                                                                                  │ G2 hours_  │ │
   │                                                                                  │  saved_cum │ │
   │                                                                                  └─────┬──────┘ │
   │                                                                                        ▼ END     │
   │                                                                                                  │
   │   build_demo_graph        : forecaster → hil_2 → (optimizer | reporter) → END                    │
   │   build_atomized_demo_graph (NEW ef95e02): atomizer → forecaster → ... → reporter → END           │
   │                            (15일 backfill 표준, mapper/hil_1 skip, mapped 호출자 hydrate)        │
   └───────────────────────────┬─────────────────────────────────┬────────────────────────────────────┘
                               │                                 │
                ┌──────────────┴──────────────┐    ┌─────────────┴──────────────┐
                │  PostgreSQL (asyncpg pool)  │    │  ChromaDB (HTTP)           │
                │  pipeline/db.py (1229)      │    │  pipeline/chroma_client.py │
                │  ~35 helper + INSERT/SELECT │    │  • daily_activities         │
                │  + upsert_daily_report_     │    │    (atomizer write,         │
                │     view_col (9 col 화이트) │    │     forecaster/optimizer    │
                │  + 4 collector_inbox helper │    │     RAG read)               │
                │                              │    │  • wbs_master (mapper       │
                │  17 사용자 테이블 + 3 ckpt   │    │    alternatives)            │
                │  + collector_inbox (NEW)    │    │                              │
                │  + 7 테이블 is_mock 컬럼     │    │  43.200.85.209:5533 / 로컬   │
                │                              │    │  chroma_export/import JSONL │
                │  43.200.85.209:5532 / 로컬   │    │  snapshot (AWS 마이그)      │
                └──────────────────────────────┘    └────────────────────────────┘
```

---

## 2. 서브시스템 별 요약 (8 개 — 각 deep_dive 링크)

| 서브시스템 | 파일 | LOC | 본 cycle 변경 (one-liner) | 핵심 이슈 |
|---|---|---:|---|---|
| **[orchestration](./deep_dive_orchestration.md)** | graph.py / state.py / checkpointer.py / constants.py + **collector_node.py + parser_node.py + pipeline/collector/ + _concurrency.py NEW** | 628+310+94+5+63+25+(260+64+68)+~30 | graph 진입 collector 이동 (D-12) + IDLE worker + build_atomized_demo_graph + get_llm_semaphore | C2 (state.parsed 타입 annotation drift), C1 (AUTO_BYPASS prod 가드 부재), HIL2 AUTO_BYPASS 없음 |
| **[persistence](./deep_dive_persistence.md)** | db.py / api.py / chroma_client.py / checkpointer.py + **exporter_routes.py NEW + api_helpers/** | 1229+1073+35+47 | collector_inbox 테이블 + 4 helper / lifespan collector task + exporter include / mapper_activities +4 col / daily_reports.site_summary_text 컬럼 | **C1 site_summary_text migration 없음** / C2 /export/run 매번 PG 풀 재생성 / C3 mapped_history.trade INSERT 누락 / /api/agents/status N+1 |
| **[parser](./deep_dive_parser.md)** | parser.py / parser_post.py / parser_llm.py (DEPRECATED) / parser_node.py NEW / agents/collector.py (legacy) / collector/{filename_parser, idle_worker, config} | 760+201+658+25+70+(64+260+68) | parser 자체 변경 0 — 모든 변경이 graph 진입 분리 + IDLE listener | parser_warning PG 영속화 미구현 / parser_llm 회귀 env flag 미구현 / Activity 4 필드 항상 None (PoC) |
| **[mapper](./deep_dive_mapper.md)** | mapper.py | 604 (이전 571 +33) | mapper_activities 4 컬럼 추가 (l5_disc / l7_sub / l7_5_activity / sub_work_area), 자체 코드 미세 정리 | l7.5 4 컬럼 PoC 항상 None / `user_corrected` 라벨 WAResolution.source Literal 누락 / wa NULL row 가 forecast bucket 에서 누락 |
| **[atomizer](./deep_dive_atomizer.md)** | atomizer.py | 196 (이전 141 +55) | ChromaClient retry 3 + upsert batch 100 split (HNSW hang 방어) / `_format_document` 신규 / metadata 12→15 필드 / batch_size 16→64 | **M trade 컬럼 누락 (commit msg 약속 vs SQL/dict)** / `_format_document` short form fallback / today_assigned_workers vs assigned_workers 불일치 |
| **[forecaster](./deep_dive_forecaster.md)** | forecaster/{agent, prompt, classify, rerank, aggregate, synthetic, constants, __init__} | 1044 (339+202+189+134+114+50+8+8) | plan_main_qty atomic distinct SUM (l6 SUM 폭주 fix) / forecast() asyncio.gather + Semaphore 4× / get_llm_semaphore 흡수 | mh 4 컬럼 reference only (UI 미연동, 의도적) / 9-22 outlier 잔존 (`6a89848` 부분 해결) |
| **[optimizer](./deep_dive_optimizer.md)** | optimizer/{agent, prompt, retrieve, view_builder, **site_summary NEW**, synthetic_v2, synthetic_daily_report} | ~3641 (227+316+206+1882+**141**+363+498+8) | **★ 산식 A (`_build_s_curve`) WV×MH + activity 매칭** / site_summary LLM JSON / 4 시나리오 percentile / MEDIAN fix / quadrant↔by_wp Jaccard / retrieve incident 9종 / `_v2` 분기 (drift) | **#1 working tree 미커밋 (다른 세션)** / `Optional` import 누락 5+2 곳 / site_summary live 미연결 / v1 ↔ v2 같은 컬럼 다른 산식 |
| **[reporter](./deep_dive_reporter.md)** | reporter.py + **exporter.py NEW + exporter_templates/ NEW** | 161+301+47 | exporter 신규 (render_xlsx + 4 시트 _fill_* + COL dict + timeshift) + `/export/run` route + lifespan include | reporter→exporter rename 미시행 / B_Track FE swap 미실행 / 4 시트 산식 회귀 테스트 누락 / G2 atomized_count=0 silent 누적 |

**합계**: ~11,656 non-test LOC (pipeline) + ~10,469 LOC (web). T1 ≈ 180+ public 함수/클래스. 본 cycle deep_dive 산출 5,705 줄 / 8 파일.

---

## 3. Data Layer (사용자 강조 — BE↔FE 연결 명확화)

데이터가 흐르는 layer 를 4 단계로 분리. 각 단계마다 "어떤 스키마 / 어떤 적재처 / 누가 쓰나" 를 표기.

### 3.1 Layer 1 — Raw Source (외부 입력)

| 종류 | 형식 | 적재처 | Schema 정의 | 읽는 컴포넌트 |
|---|---|---|---|---|
| 작업일보 xlsx | xlsx (4 시트) | `pipeline/data/` 또는 IMAP attachment | openpyxl row/col + parser COL dict | `agents/parser.py` (line 100+, 시트별 _extract_*) |
| Master List xlsx | xlsx (1 시트) | `scripts/load_master_list.py` → `activity_master` 테이블 | column position constants (C_PLAN_WV=32 등) | `load_master_list.py` (parse + INSERT) |
| Gmail IMAP | RFC2822 message | `collector_inbox` 테이블 (dedup) | `(message_id, attachment_filename) UNIQUE` | `collector/idle_worker.py:run` IDLE loop |

### 3.2 Layer 2 — Parsed / Mapped (LangGraph state 중간)

state 키별로 누가 채우고 누가 읽는지 + PG 영속화 여부.

| State 키 | 타입 | 채우는 노드 | 읽는 노드 | 영속화 |
|---|---|---|---|---|
| `parsed` (이전 `parsed_reports`) | `ParsedDailyReport` | parser_node | mapper_node | parser_reports / parser_activities (PG) |
| `mapped` | `list[Activity]` (44 필드) | mapper_node | hil_1, atomizer, forecaster | mapper_activities (37 컬럼) |
| `hil_1_review_needed` | `list[ReviewItem]` | mapper_node (`_build_review_needed`) | hil_1_node (interrupt) | mapping_corrections (PG) |
| `hil_1_corrections` | `dict[int, dict]` | hil_1_node (Command resume) | mapper_node (`_apply_corrections`) | mapping_corrections |
| `atomized_ids` | `list[str]` | atomizer_node | forecaster, optimizer | Chroma daily_activities |
| `forecasts` | `list[ForecastRow]` (28 컬럼) | forecaster_node | hil_2, optimizer, reporter | forecasts (PG) |
| `hil_2_selection` | `list[str]` (group_key) | hil_2_node (Command resume) | optimizer_node | (none — graph-only) |
| `optimizer_advice` | `list[OptimizerAdvice]` | optimizer_node | reporter_node | optimizer_advice (PG) + daily_reports.optimizer_view_jsonb |
| `daily_report` | dict (종합) | reporter_node | (terminal) | daily_reports (PG) |
| `site_id` | str | reporter_node fallback (G8) | (multi-node lookup) | sites.last_run_id |

### 3.3 Layer 3 — Persistent Storage

#### PostgreSQL (17 user 테이블 + 3 LangGraph ckpt + collector_inbox)

| 테이블 | 신규 컬럼 (본 cycle) | 채우는 노드/스크립트 | 읽는 FE 페이지 |
|---|---|---|---|
| `sites` | (변경 없음) | reporter G8 / G2 + seed_sites.sql | dashboard / reports list |
| `pipeline_runs` | (변경 없음) | api.py `_run_one_cycle` + reporter (status='completed' fix) | reports list (run filter) |
| `daily_reports` | **`site_summary_text` text (★ migration 없음, 이슈 #N13)** + 9 jsonb (kpi/contractor_bars/trade_bars/quadrant/wp_summary/s_curve/optimizer_view/productivity/scenarios) + site_id partial unique idx | reporter (전체 row INSERT) + optimizer (`upsert_daily_report_view_col` 9 jsonb) + backfill_v2 `--with-summary` (site_summary) | reports/[date] detail / ForecastChart / WPSummaryTable / ProductivityBarToggle / QuadrantScatter |
| `forecasts` | (이전 cycle: `wa`) | forecaster_node | wp_summary tab / optimizer view |
| `optimizer_advice` | (이전 cycle) | optimizer_node | optimizer tab / reports/[date] |
| `mapping_corrections` | (이전 cycle) | hil_1_node | review page |
| `activity_master` | (이전 cycle: `wa`, `site_id`) | scripts/load_master_list.py | wbs_tree |
| `mapped_history` | (이전 cycle: `trade` — **commit 약속 vs 실 SQL 누락 이슈 #A-N3 / #N16**) | atomizer | tasks itemsByDate |
| `mapper_activities` | **`l5_disc`, `l7_sub`, `l7_5_activity`, `sub_work_area` 4 컬럼 (5-23 migration)** + 이전 alternatives jsonb + cum_workers/mh | mapper_node | review WBSTree alternatives dropdown / tasks |
| `parser_*` (5 테이블) | (이전 cycle) | parser_node | (없음 — 내부 audit) |
| **`collector_inbox` NEW** | (message_id, attachment_filename, status, fetched_at) | collector idle_worker | (없음 — 내부 dedup) |
| **7 테이블 `is_mock` boolean NEW** | sites/daily_reports/forecasts/optimizer_advice/mapping_corrections/mapper_activities/mapped_history | seed_dummy_year.py / backfill_mock_rows.py | `/api/mock/*` route `WHERE is_mock = $1` |

#### ChromaDB (2 컬렉션, HTTP 43.200.85.209:5533)

| 컬렉션 | 의도 | 적재 노드 | 읽는 노드 |
|---|---|---|---|
| `daily_activities` | 일별 활동 누적 embedding (RAG 유사 이력) | atomizer (`_format_document` live/backfill 2 모드 + 15 metadata 필드 + 1536d embedding) | forecaster (`fetch_degradation_cases`) + optimizer (`fetch_recovery_trajectory`) |
| `wbs_master` | WBS 마스터 embedding (mapper alternatives top-K) | scripts/load_master_list.py (1059 row) | mapper (`build_bp_context` → Chroma query) |

#### LangGraph Checkpoints (3 테이블 — AsyncPostgresSaver 자동 관리)

`checkpoints` / `checkpoint_writes` / `checkpoint_blobs` — `thread_id` = `run_id`. interrupt 발생 시 state snapshot 저장, `Command(resume=...)` 로 재개.

### 3.4 Layer 4 — FE Consumer (web/lib/types.ts → page/component)

| FE type (`web/lib/types.ts`) | BE source (PG 컬럼 또는 jsonb path) | derived rule (web/lib/transforms.ts 또는 diagnosis.ts) | 렌더 컴포넌트 |
|---|---|---|---|
| `Site` (8 필드) | `sites.*` + LATERAL `forecasts` AVG | api/mock/dashboard → SiteCard | home / dashboard SitesGrid |
| `ReportDaily` (status/productivity_today/delay_days/recovery_days) | `daily_reports.kpi_jsonb.*` + scenarios.site.base_p50.recovery_days fallback | api/mock/report list (4 필드) | reports left ReportDailyList |
| `ReportDetail` (9 jsonb + **`site_summary_text` NEW**) | `daily_reports.*_jsonb` 9 + `site_summary_text` | api/mock/report/[date] | reports right (ForecastChart / WPSummary / Quadrant / Optimizer) |
| `ProductivityDiagnosis` (13 필드) | (no BE — `web/lib/diagnosis-adapter.ts` mock 영구 — D-3 REVISED) | diagnosis.ts diagnose() | ProductivityTrendChart |
| `ScenarioPoint` (eta_days / recovery_pct / **`catch_up` NEW** / curve) | `daily_reports.scenarios_jsonb` | diagnosis.ts `buildScenarioCurve` (lastActual → plan[today+recoveryDays] slope → plan 동행) | ForecastChart 4선 (검정/빨강 dashed/회색/mint dashed) |
| `WPSummaryRow` (wp_id + grain) | `daily_reports.wp_summary_jsonb` 또는 `forecasts` triplet | wp_id = `f"{wa}-{slug(l6_main)}-{slug(company)}"` | WPSummaryTable |
| `OptimizerOutput[]` | `optimizer_advice` rows (배열) | api/runs/{id}/optimizer | OptimizerCard list |
| `DailyTask / AgentStageProgress / AgentTaskItem` | `mapped_history` (옵션 Y) + LangGraph state 단계 binary | api/mock/agent-tasks / [date] | tasks page |
| `WBSNode` | `activity_master` (트리 derive) | api/sites/{id}/wbs_tree | review WBSTree |

상세 매핑 = `data-contract/crosswalk.md` 의 3 면 표 (26 type × 190 field). 본 cycle 갱신 대상.

---

## 4. Tool / Helper Inventory

### 4.1 Core helpers

| 파일 | 함수/클래스 | LOC | 역할 |
|---|---|---:|---|
| `pipeline/db.py` | PGClient + 35+ helper + `upsert_daily_report_view_col` (9 col 화이트리스트) + 4 collector_inbox helper NEW | 1229 | asyncpg pool 단일 진입점 |
| `pipeline/api.py` | FastAPI 12 endpoint + lifespan (collector + exporter) | 1073 | BFF |
| `pipeline/exporter_routes.py` NEW | `/export/run` FastAPI route | 47 | xlsx 4 시트 다운로드 |
| `pipeline/agents/exporter.py` NEW | `render_xlsx` + `_fill_*` × 4 + COL dict + `_fill_timeshift` 헬퍼 + NoDataError | 301 | openpyxl 4 시트 write |
| `pipeline/chroma_client.py` | ChromaClient (HTTP) + retry 3 + batch 100 split | 35 | Chroma collection 진입점 |
| `pipeline/checkpointer.py` | `_LazyAsyncPostgresSaver` + `build_checkpointer` | 94 | InMemorySaver fallback |
| `pipeline/agents/optimizer/view_builder.py` | 45 함수 7 phase + EVM + KPI + bars + quadrant + scenarios + s_curve | 1882 | 9 jsonb view 산출 |
| `pipeline/agents/optimizer/site_summary.py` NEW | `build_site_summary_payload` + `generate_site_summary` (JSON mode) | 141 | site 수준 LLM narrative |
| `pipeline/agents/_concurrency.py` NEW | `get_llm_semaphore()` + `CPIA_LLM_CONCURRENCY` | ~30 | LLM 공용 semaphore (forecaster/optimizer/atomizer) |
| `pipeline/agents/parser_post.py` | 8 함수 (normalize_company / split_company_and_zone / extract_zone / pair_bp_summaries / filter_marker_rows / transform_*) | 201 | parser 후처리 |
| `pipeline/agents/collector_node.py` NEW | graph 진입 노드 (Gmail attachment fetch) | 63 | D-12 collector |
| `pipeline/agents/parser_node.py` NEW | parser wrapper (state-key drift fix) | 25 | D-12 parser split |
| `pipeline/collector/idle_worker.py` NEW | IMAP IDLE loop + graph.invoke | 260 | Gmail 첨부 자동 처리 |
| `pipeline/collector/filename_parser.py` NEW | YYYYMMDD_*.xlsx → date/company 추출 | 64 | 파일명 메타 |
| `pipeline/collector/config.py` NEW | CollectorConfig dataclass | 68 | env 통합 |

### 4.2 FastAPI 12 endpoint

| Method | Path | Helper | FE consumer |
|---|---|---|---|
| GET | `/health` | (none) | (ops) |
| GET | `/api/sites` | sites + LATERAL forecasts | home SiteCard / dashboard |
| GET | `/api/runs/{run_id}/optimizer` | optimizer_advice | reports OptimizerCard |
| GET | `/api/runs/{run_id}/wp_summary` | forecasts (triplet) | reports WPSummaryTable |
| GET | `/api/sites/{site_id}/reports` | daily_reports + pipeline_runs | reports list (point-in-time) |
| GET | `/api/dashboard/performance` | (custom join) | dashboard Performance tab |
| GET | `/api/dashboard/impact` | (custom) | dashboard Impact tab |
| GET | `/api/agents/status` | hard-code meta (D-9) | tasks AgentWorkflow |
| GET | `/api/sites/{site_id}/wbs_tree` | activity_master | review WBSTree |
| GET | `/api/tasks` | mapped_history + state | tasks page |
| POST | `/api/runs/{run_id}/hil_1/resume` | graph.aupdate_state | review HIL Modal |
| POST | `/export/run` (exporter_routes) | fetch_sheet_data + render_xlsx | export ConsolidatedReportCard |

### 4.3 Scripts (본 cycle 20+ 신규)

| 스크립트 | LOC | 역할 |
|---|---:|---|
| `scripts/seed_dummy_year.py` NEW | 905 | F3 분포 + prod target 90% 역산 + l5_disc trade + l7.5 + degradation_cases + today_conditions + chroma metadata |
| `scripts/backfill_daily_report_views_v2.py` NEW | 196 | view_builder v2 backfill + `--with-summary` (LLM) |
| `scripts/backfill_optimizer_advice_llm.py` NEW | 429 | optimizer_advice LLM 재산출 (일반화) |
| `scripts/aws_backup_and_migrate.py` NEW | 225 | pg_dump → SCP → restore orchestrator (절대경로) |
| `scripts/chroma_export.py` + `chroma_import.py` NEW | 60+60 | Chroma JSONL snapshot (AWS 마이그) |
| `scripts/poc_mock_redesign.py` NEW | 385 | Mock 재설계 PoC orchestrator |
| `scripts/poc_optimizer_5day_backfill.py` NEW | 290 | 5일 시연 데이터 backfill |
| `scripts/normalize_companies.py` NEW | 204 | 회사명 통합 정규화 |
| `scripts/apply_company_normalize.py` NEW | 148 | 정규화 결과 적용 |
| `scripts/apply_mapped_history_normalize.py` NEW | 138 | mapped_history 정규화 |
| `scripts/apply_l7_5_overwrite.py` NEW | 109 | l7.5 backfill |
| `scripts/resolve_l7_5_prototype.py` NEW | 323 | l7.5 매칭 프로토타입 |
| `scripts/backfill_chroma_daily_activities.py` NEW | 189 | Chroma 재적재 |
| `scripts/backfill_mock_rows.py` NEW | 212 | is_mock 컬럼 backfill |
| `scripts/cleanup_by_companies.py` NEW | 268 | 회사 단위 정리 |
| `scripts/cleanup_over_plan_qty.py` NEW | 100 | plan_qty 초과 정리 |
| `scripts/verify_backfill_passing.py` NEW | 351 | 통과 기준 9 SQL 검증 |
| `scripts/verify_ui_assertions.py` NEW | 206 | UI assertion 8건 자동 검증 |
| `scripts/local_db_reset.py` NEW | 72 | TRUNCATE all + Chroma delete (CASCADE 가드) |
| `scripts/audit_phase2_snapshot.py` NEW | 73 | phase2 snapshot |

---

## 5. PG Migration 누적 (timestamp 순)

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
2026-05-19_collector_inbox.sql        NEW — IDLE collector dedup
2026-05-19_daily_reports_views.sql    (22) — 9 view JSONB + site_id
2026-05-19_mapped_history_trade.sql   (11) — mapped_history.trade
2026-05-19_mapper_alternatives.sql    (15) — alternatives JSONB + GIN
2026-05-19_scenarios_jsonb.sql        (10) — daily_reports.scenarios_jsonb
2026-05-19_sites_hours_saved_cum.sql  (12) — G2 누적 절감 시간
2026-05-19_parser_full_schema.sql    (141) — parser_* 5 테이블 통합
2026-05-20_add_is_mock.sql            NEW — 7 테이블 is_mock boolean
2026-05-21_phase1.sql                 NEW — Mock 재설계 phase 1
2026-05-23_mapper_l7_5_columns.sql    NEW — mapper_activities + 4 컬럼
★ (없음)                              — daily_reports.site_summary_text 컬럼 (이슈 #N13)
```

---

## 6. Issue 표 (본 cycle 갱신 — 32 건)

| ID | 영역 | 심각도 | 설명 | 다음 행동 |
|---|---|---|---|---|
| **#N13** | persistence | **C** | `daily_reports.site_summary_text` 컬럼 migration SQL 부재 — fresh DB rebuild 시 UndefinedColumnError | `2026-05-26_daily_reports_site_summary.sql` 작성 |
| **#N14** | orchestration | **C** | `CPIA_HIL_AUTO_BYPASS` env 가 prod 가드 없이 활성 — 실수로 prod 우회 가능 | env name 에 `_DEMO` suffix + assert env != production |
| **#N15** | orchestration | **C** | `CPIAState.parsed` 타입 annotation drift — `list[Activity]` 로 잘못 박혀있으나 실제 `ParsedDailyReport` | state.py 타입 수정 |
| **#N16** | atomizer | M | `mapped_history.trade` SQL 누락 — commit msg (`16f1b88`) 가 약속했으나 atomizer.py:179-189 mh_rows dict + insert_mapped_history_batch SQL 모두 trade 키 미포함 → 항상 NULL | atomizer.py + db.py SQL 동시 수정 |
| **#N17** | optimizer | M | working tree `view_builder.py:1447` `AND ma.trade IN ('건축', '토목')` 1 줄 제거 (다른 세션 작업 중) — v2 산출 대상이 설비/전기까지 확장됨 | 다른 세션 commit 대기 |
| **#N18** | optimizer | M | `Optional` 미 import (view_builder 5 곳 + agent.py 2 곳) — `from __future__ import annotations` 덕에 런타임 OK, `typing.get_type_hints()` 호출 시 NameError | import 추가 |
| **#N19** | optimizer | M | `_build_productivity_views` (v1) ↔ `_build_productivity_views_v2` 병행 — agent.py:187 은 v1, backfill 은 v2. 같은 컬럼 (productivity_jsonb) 다른 산식 | v2 로 일원화 + v1 제거 |
| **#N20** | optimizer | M | site_summary 가 production graph 미연결 — `backfill_v2 --with-summary` 만 호출, live `optimize()` 미연동 | optimize() 안에 호출 추가 |
| **#N21** | persistence | M | `/export/run` 매 요청마다 PGClient 신규 풀 — `app.state.pg` 미재사용 | exporter_routes.py 가 lifespan pool 사용 |
| **#N22** | persistence | M | `insert_mapped_history_batch` ON CONFLICT 가 `trade` 컬럼 누락 → 최초값 고정, 이후 변경 무시 | ON CONFLICT 절에 trade 추가 |
| **#N23** | reporter | M | reporter → exporter rename 미시행 — 파일명 + 13 import + GraphConfig.reporter + _AGENTS_META[4]. CLAUDE.md 약속 (5-18) vs 실 코드 불일치 | 다음 cycle 일괄 rename |
| **#N24** | reporter | M | B_Track FE swap 미실행 — A_Track endpoint + 가이드 준비 완료, ConsolidatedReportCard.tsx 는 여전히 정적 sample 다운로드 | NEXT_PUBLIC_FASTAPI_BASE env + handleExport 교체 |
| **#N25** | parser | M | parser_warning 현재 stderr 로그만 — `parser_reports.warnings_jsonb` 컬럼 적재 미구현 | 다음 cycle |
| **#N26** | forecaster | M | 9-22 outlier 잔존 (외장판넬공사 동신패널 `plan_main_qty` 폭주) — `6a89848` 부분 해결, expected_completion 2485-07-15 / delay_days 167,935 가능 | classify.py 조건 강화 |
| **#N27** | mapper | M | `wa NULL` row 가 forecast bucket 에서 누락 — preflight 단계 정리 필요 | 다음 cycle |
| #N1 | optimizer | M | RAG fixture_prod vs synthetic_v2 baseline ±10% mismatch (사용자 합의) | C 시 실측 |
| #N4 | orchestration | M | `daily_reports.kpi_jsonb / wp_summary_jsonb / quadrant_jsonb` view 미산출 (일부 채워짐, 일부 빈 dict) | view_builder v2 통일과 함께 |
| #N28 | persistence | M | `/api/agents/status` N+1 7회 | join + group by 로 단일 query |
| #N29 | atomizer | L | `_format_document` short form fallback (unit 빈 str 시 backfill 모드 무시) | unit 정규화 추가 |
| #N30 | mapper | L | l7.5 4 컬럼 PoC 단계 항상 None (Master List 1:N) | Phase 2 확장 시 |
| #N31 | mapper | L | `user_corrected` 라벨 WAResolution.source Literal 누락 — graph.py 만 생성 | state.py Literal 추가 |
| #N32 | parser | L | `parser_llm.py` 658 LOC DEPRECATED — env flag 회귀 path 작동 미검증 | 다음 cycle 제거 |
| #N5 | orchestration | L | Command(resume) key int→str 변환 룰 명문화 미흡 | spec |
| #N9 | api | L | `/api/tasks` itemsByDate "Collector" key hardcode | Phase 2 |
| #N10 | api | L | `/api/sites` LATERAL 확장 시 성능 | EXPLAIN ANALYZE |
| #N11 | poc | L | Activity 4 필드 항상 None | PoC 미스코핑 |
| #N6 | reporter | L | reporter → exporter rename (#N23 동일) | 다음 cycle |
| #N7 | parser | L | parser_warning DB 적재 (#N25 동일) | 다음 cycle |
| #N8 | parser | L | parser_llm 제거 (#N32 동일) | 다음 cycle |
| #M1 | orchestration | L | `_LazyAsyncPostgresSaver._opened` race + dead_letter race | mutex |
| #M2 | persistence | L | init.sql ↔ migrations 정합 11 테이블 누락 — fresh init 단독으로는 schema 불완전 | init.sql 동기화 |
| D-1 | optimizer | M | 병행작업 룰 (드릴+콘크리트) 진단 미반영 | Phase 2 |

---

## 7. 파일 구조 요약 (annotated, 본 cycle 강조)

```
pipeline/
├── agents/
│   ├── atomizer.py             196  (+55) retry/batch/format_document/metadata 15
│   ├── collector.py             70  legacy — discover + collect_and_parse (현재 dead path)
│   ├── collector_node.py        63  ★ NEW graph 진입 노드 (Gmail attachment)
│   ├── parser_node.py           25  ★ NEW state-key drift fix wrapper
│   ├── exporter.py             301  ★ NEW render_xlsx + 4 시트 _fill_* + COL dict + timeshift
│   ├── exporter_templates/
│   │   ├── __init__.py           1  ★ NEW
│   │   └── consolidated_template.xlsx  binary  ★ NEW (4 시트 dummy 헤더)
│   ├── _concurrency.py          ~30 ★ NEW get_llm_semaphore() + CPIA_LLM_CONCURRENCY
│   ├── forecaster/
│   │   ├── agent.py            339  (+60) asyncio.gather + Semaphore 4× + plan_main_qty atomic
│   │   ├── aggregate.py        202  T18 mh reference only docstring
│   │   ├── classify.py         114  (PM v2)
│   │   ├── constants.py          8
│   │   ├── prompt.py           134
│   │   ├── rerank.py            50
│   │   └── synthetic.py        189
│   ├── mapper.py               604  (+33) mapper_activities 4 컬럼 (l5_disc/l7_sub/l7_5/sub_work_area)
│   ├── optimizer/
│   │   ├── agent.py            227  (+28) asyncio.gather + to_thread 4×
│   │   ├── prompt.py           316
│   │   ├── retrieve.py         206  (+45) incident keyword 9종 보강
│   │   ├── view_builder.py    1882  ★ (+1130) 산식 A WV×MH + MEDIAN + 4 시나리오 + v2 분기
│   │   ├── site_summary.py     141  ★ NEW LLM JSON site narrative
│   │   ├── synthetic_v2.py     363
│   │   └── synthetic_daily_report.py 498
│   ├── parser.py               760  (변경 없음)
│   ├── parser_llm.py           658  DEPRECATED 2026-05-20
│   ├── parser_post.py          201
│   └── reporter.py             161  (변경 없음 — rename backlog #N23)
├── api.py                     1073  (+23) lifespan collector task + exporter router include
├── api_helpers/                     (__pycache__ only — empty dir, 의심)
├── checkpointer.py              94
├── chroma_client.py             35
├── collector/
│   ├── __init__.py
│   ├── config.py                68  ★ NEW CollectorConfig
│   ├── filename_parser.py       64  ★ NEW YYYYMMDD_*.xlsx
│   └── idle_worker.py          260  ★ NEW IMAP IDLE loop
├── constants.py                  5
├── db.py                      1229  (+116) 4 collector_inbox helper + 4 컬럼 insert_mapper_activities_batch
├── exporter_routes.py           47  ★ NEW /export/run FastAPI
├── graph.py                    628  (+65) collector → parser → mapper 진입 변경 + build_atomized_demo_graph
├── main.py                       0  stub (drift)
├── state.py                    310  (+7) parsed key 등 (annotation drift 잔존 #N15)
├── synthetic/generate_history.py 0  drift
├── scripts/                         untracked dir
└── tests/                          ~50+ 파일, 401+ collected (본 cycle 9 신규)

web/                                10,469 LOC (TS/TSX)
├── lib/
│   ├── diagnosis.ts            178  (+89) buildScenarioCurve catch-up + plan 동행
│   ├── diagnosis-adapter.ts      8  (+8) mock 영구 (D-3 REVISED)
│   ├── fixtures.ts                  (+75) site_summary_text 필드 추가
│   ├── transforms.ts                (+101) WP/scenario transform
│   ├── types.ts                     (+27) ScenarioPoint.catch_up + ReportDetail.site_summary_text
│   ├── bar-filters.ts           12  NEW
│   ├── persona.ts                4  (+4)
│   ├── pg.ts                        (변경)
│   └── __tests__/transforms.test.ts  ~119
├── app/
│   ├── (app)/reports/page.tsx       (+97) aiAdvice / aiSummaryText 전달
│   ├── (app)/tasks/page.tsx        (+113)
│   ├── (app)/dashboard/page.tsx
│   ├── (app)/home/page.tsx          (+8)
│   ├── (app)/review/page.tsx        (+10)
│   ├── api/mock/report/route.ts     (+59) list-only (4 col)
│   ├── api/mock/report/[date]/route.ts  +56 ★ NEW detail (9 jsonb + site_summary)
│   ├── api/mock/agent-tasks/route.ts        (+121) list
│   ├── api/mock/agent-tasks/[date]/route.ts +85 ★ NEW
│   ├── api/mock/consolidated/route.ts       (+112)
│   ├── api/mock/dashboard/route.ts          (+45)
│   ├── api/mock/review/route.ts             (+63)
│   └── components/
│       ├── charts/ForecastChart.tsx        (+371) 4선 catch-up + 마커 분산 + 메타 grid
│       ├── charts/ProductivityTrendChart.tsx (+89)
│       ├── charts/QuadrantScatter.tsx
│       ├── reports/{ProductivityBarToggle, ReportDailyList, WPSummaryTable}
│       ├── tasks/AgentWorkflowList.tsx     (+33)
│       ├── review/WBSTree.tsx              (+48)
│       └── landing/* (CoreAi/Impact/Scalability/Background/FinalCta/AsIsToBe/Footer)
```

---

## 8. 검증 상태 (본 cycle)

| 항목 | 측정 | 상태 |
|---|---|---|
| Pipeline tests | 392 baseline + 9 신규 = 401+ collected | ✅ 통과 |
| Mock 재설계 9 SQL 통과 기준 (`verify_backfill_passing.py`) | 9/9 PASS (`15c0bdc`) | ✅ |
| UI assertion 8 건 자동 (`verify_ui_assertions.py`) | (실행 확인 필요) | ⚠️ |
| AWS 마이그 (E.6 final) | dashboard / reports / tasks 3 페이지 screenshot 통과 (`de936ba`) | ✅ |
| 시연 anchor 9-25 site KPI | delay=11일 + LLM narrative (`1315c28`) | ✅ |
| Phase D Playwright screenshot 6 페이지 (`bcab4ab`) | 통과 | ✅ |
| AWS PG 마이그 backup/restore (aws_backup_and_migrate.py) | 절대경로 fix 후 통과 (`7d10b6c`) | ✅ |
| Working tree | view_builder.py 1 줄 (다른 세션) + scripts/ untracked + 1 plan doc untracked | ⚠️ |

---

## 9. 시연 (PoC 2026-06-05) 흐름

```
1. 로그인 → 홈 화면 (6 site card)
2. 9-25 시연 site (m15x-ph3-ibl) 클릭 → reports/[date] detail
3. 좌측 ReportDailyList → 9-25 선택
4. 우측: KPI 카드 (delay=11일) + ForecastChart (4선 catch-up) + site_summary_text narrative (LLM)
5. WPSummaryTable (wp_id triplet) + QuadrantScatter + OptimizerCard list
6. Export 버튼 → /export/run → xlsx 다운로드 (4 시트)
7. tasks 페이지 → 단계별 binary progress (mapped_history 기반)
8. review 페이지 → WBSTree + HIL alternatives
```

---

*최종 수정: 2026-05-26 (1ba783f) — 70+ commits 흡수 cycle, 9 deep_dive 파일 신규 (총 5,705 줄)*
*이전 수정: 2026-05-20 (ef7c6cd) — parser+mapper refactor + view_builder 752 LOC + FastAPI 12 endpoint*
