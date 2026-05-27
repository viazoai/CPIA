# CPIA design-intent — Master INDEX

- **Generated**: 2026-05-26 (Mock 재설계 PR #40 + AWS 마이그 + view_builder MEDIAN + backfill_v2 + ForecastChart catch-up + site_summary LLM cycle 후 갱신)
- **Git SHA**: `1ba783f` (A_Track HEAD). 이전 스냅샷 `ef7c6cd` 대비 **70+ commits, 204 files, +30,151 / -3,055 LOC, pipeline non-test 8,928 → 11,656 (+31%)**
- **Branch**: `A_Track` (main 머지 완료 — `7e9e1a1` 산식 A + site_summary / `1ba783f` Mock 재설계 sync). working tree: view_builder.py 1 줄 (다른 세션).
- **Scope**: pipeline 전체 (9 active subsystem + 신규 exporter + collector IDLE worker + scripts 20+). Web/B_Track 제외.
- **Pair**: `../architecture_overview.md` (deep-dive 라이트, 415 줄) + `../deep_dive_<X>.md` × 8 (각 300~1,100 줄, 합계 5,705)

코드 변경/추가 작업 진입 시 아래 T1 인덱스에서 **함수 이름 / 키워드 / 파일** grep → 매칭 시 해당 서브시스템 `design_intent_<X>.md` 의 T2 카드 확인 → 기존 핸들러 확장 vs 새 설계 판단.

> **이번 cycle 갱신 요지 (vs ef7c6cd / 2026-05-20)**:
>
> - **graph 진입점 이동 (D-12)**: `mapper` → `collector_node` (`55cad90`) + `parser_node` 분리 (`6b9db7c` state-key drift fix). 9-노드 production topology 완성.
> - **IMAP IDLE Collector 신설**: `pipeline/collector/` 폴더 (filename_parser 64 + idle_worker 260 + config 68) + `agents/collector_node.py` 63 + `collector_inbox` 테이블 + 4 helper.
> - **Exporter 신설**: `agents/exporter.py` 301 + `exporter_routes.py` 47 + `exporter_templates/consolidated_template.xlsx`. reporter (graph 노드) ≠ exporter (FastAPI 라우트) 분리. rename backlog.
> - **산식 (A) WV × MH 가중** (`c0a0641`): view_builder.py:880~1021 `_build_s_curve` — 분모 SUM(plan_wv × plan_mh_rev2), planned/actual (wa, l6) 매칭, full_grid cross join 단조 보장.
> - **Site 수준 LLM narrative** (`21c10f7`): `site_summary.py` 141 LOC 신규 + `daily_reports.site_summary_text` 컬럼 + Azure JSON response_format. backfill_v2 `--with-summary` opt-in. live `optimize()` 미연결 backlog.
> - **view_builder 752 → 1,882 LOC (+1,130, 2.5×)**: 산식 A + 4 시나리오 percentile + v2 분기 (`_build_productivity_views_v2`, drift 위험 #N19) + MEDIAN fix + quadrant↔by_wp Jaccard.
> - **Concurrency 4×**: `get_llm_semaphore()` + `CPIA_LLM_CONCURRENCY` (default 4) + forecaster asyncio.gather + optimizer to_thread + atomizer batch 16→64.
> - **Atomizer 활발히 변경 (이전 라벨 "코드 변경 없음" 무효화)**: ChromaClient retry 3 + upsert batch 100 split / `_format_document` 신규 / metadata 12→15 필드 / batch_size 64.
> - **Forecaster 변경 (이전 라벨 무효화)**: plan_main_qty atomic distinct SUM (l6 SUM 폭주 fix) + asyncio.gather Semaphore 4× + get_llm_semaphore 흡수.
> - **Reporter 변경 (이전 라벨 무효화)**: reporter 자체는 그대로지만 **exporter 4 시트 xlsx + `/export/run` route 신규 흡수**.
> - **Mock 재설계 + AWS 마이그**: synthetic v2 → seed_dummy_year 905 LOC + AWS pg_dump/SCP/restore + Chroma JSONL export/import + 7 테이블 `is_mock` 컬럼.
> - **신규 PG migration 4종**: `2026-05-19_collector_inbox.sql` / `2026-05-20_add_is_mock.sql` / `2026-05-21_phase1.sql` / `2026-05-23_mapper_l7_5_columns.sql`. **`daily_reports.site_summary_text` migration 누락 — 이슈 #N13**.

---

## 서브시스템 8 개

| 서브시스템 | 파일 | T1 | T2 | LOC | 핵심 책임 | 본 cycle 변경 |
|---|---|---:|---:|---:|---|---|
| orchestration | [design_intent_orchestration.md](./design_intent_orchestration.md) | 22 → 33 | 12 → 21 | 868 | LangGraph StateGraph + 9 node + 2+1 builder + HIL 1/2 + IDLE worker + collector_node + parser_node + checkpoint | D-12 collector→parser→mapper 진입 + build_atomized_demo_graph + IDLE worker + get_llm_semaphore + Critical 2 (AUTO_BYPASS / parsed annotation) |
| persistence | [design_intent_persistence.md](./design_intent_persistence.md) | 27 → 35 (+ 12 endpoint + /export/run) | 16 → 21 | 584 | PG asyncpg pool + Chroma HTTP + FastAPI 12 endpoint + exporter route + collector_inbox helper | collector_inbox + 4 helper / lifespan collector task + exporter include / `/export/run` + fetch_sheet_data / mapper_activities +4 컬럼 / site_summary_text 컬럼 (★ migration 없음) / Critical 3 |
| parser | [design_intent_parser.md](./design_intent_parser.md) | 20 → 30+ | 11 → 13 | 517 | xlsx → 4시트 + LLM 검증 wrapper + IDLE listener + 파일명 분해 | parser/parser_post/parser_llm 자체 변경 0, 모든 변경이 graph 진입 분리 (collector_node + parser_node + filename_parser + idle_worker + config) |
| mapper | [design_intent_mapper.md](./design_intent_mapper.md) | 12 → 15 | 11 → 10 | 414 | 6단계 매핑 + resolve_wa 7단계 + shift-weighted MH + RAG top-K alternatives + cum_workers prorate | mapper_activities 33→37 컬럼 (l5_disc / l7_sub / l7_5_activity / sub_work_area, d40c84f) — mapper.py 자체는 미세 변경, db.py SQL 만 확장 |
| atomizer | [design_intent_atomizer.md](./design_intent_atomizer.md) | 4 → 5 | 4 → 7 | 305 | Chroma daily_activities INSERT + mapped_history INSERT + retry/batch 가드 | 이전 "코드 변경 없음" 라벨 무효화 — `_format_document` live/backfill 2 모드 신규 + metadata 12→15 필드 + ChromaClient retry 3 + batch 100 split + batch_size 64 + **trade 컬럼 누락 (#A-N3)** |
| forecaster | [design_intent_forecaster.md](./design_intent_forecaster.md) | 22 → 24 | 13 → 17 | 301 | RAG 우선 + Plan fallback 진단 + asyncio.gather + LLM cold start | 이전 "코드 변경 없음" 라벨 무효화 — plan_main_qty atomic distinct SUM (l6 SUM 폭주 fix, 6a89848) + forecast() asyncio.gather + Semaphore 4× (6ba0126) + get_llm_semaphore 흡수 + fetch_pg_actual_cum_qty PG 우회 |
| optimizer | [design_intent_optimizer.md](./design_intent_optimizer.md) | 30+ → 55+ | 17 → 14 (★ 7 신규) | 729 | LLM 조언 + view_builder 9+1 jsonb + scenarios percentile 4 + recovery + ★ 산식 A WV×MH + ★ site_summary LLM JSON | view_builder.py 752 → 1,882 (+1,130) — 산식 A (★★) + site_summary (★★) + MEDIAN fix + 4 시나리오 percentile + v1↔v2 분기 (drift #N19) + quadrant Jaccard 100% + retrieve INCIDENT 9종 + optimize() asyncio.gather + to_thread 4× / working tree 미커밋 1 줄 (#1) |
| reporter | [design_intent_reporter.md](./design_intent_reporter.md) | 5 → 22 | 7 → 14 (★ 8 신규) | 330 | 종합 보고서 + daily_reports + G8/G2 + **exporter 4 시트 xlsx + /export/run + lifespan include** | 이전 "코드 변경 없음" 라벨 무효화 — reporter 자체 변경 0, exporter (render_xlsx + 4 _fill_* + COL dict + timeshift + NoDataError + fetch_sheet_data + consolidated_template.xlsx + /export/run + app.include_router) 신규 흡수. **reporter→exporter rename 미시행 (CLAUDE.md 약속 vs 실 코드, #R-N1)** |

**합계**: T1 ≈ 229+ public 함수/클래스 / T2 ≈ 117 이슈 카드 (이전 93 → +24). 본 cycle design_intent 산출 4,048 줄 (이전 ~3,200 → +800).

---

## T1 — 전 서브시스템 함수 인덱스 (Top hits — 본 cycle 신규/변경 강조)

상세 T1 인덱스는 각 `design_intent_<X>.md` 의 첫 섹션에 있음. 본 INDEX 는 cross-system grep 용 "본 cycle 신규 / 변경" 만 발췌.

### 본 cycle ★ NEW 함수 / 클래스 (전 서브시스템)

| Function/Class | File:Line | 서브시스템 | One-line role |
|---|---|---|---|
| `collector_node` | agents/collector_node.py | orchestration / parser | ★ NEW (55cad9) graph 진입 노드 |
| `parser_node` | agents/parser_node.py | orchestration / parser | ★ NEW (6b9db7c) state-key drift fix wrapper |
| `build_atomized_demo_graph` | graph.py | orchestration | ★ NEW (ef95e02) 15일 backfill 표준 |
| `get_llm_semaphore` | agents/_concurrency.py | orchestration | ★ NEW (1e24dc6) LLM 공용 |
| `idle_loop` / `run_for_attachment` | collector/idle_worker.py | orchestration / parser | ★ NEW IMAP IDLE loop |
| `parse_filename` / `ParsedFilename` | collector/filename_parser.py | parser | ★ NEW YYYYMMDD prefix 분해 |
| `load_collector_config` / `CollectorConfig` | collector/config.py | orchestration / parser | ★ NEW env → dataclass |
| `insert_collector_inbox` / `update_collector_inbox` / `fetch_collector_inbox_*` / `fetch_site_by_id` | db.py | persistence | ★ NEW (7b96b1a) Gmail IMAP dedup |
| `update_run_atomized_count` / `update_run_status` / `update_run_current_node` | db.py | persistence | ★ NEW (D-17) |
| `lifespan` + `app.include_router(exporter_router)` | api.py | persistence | ★ NEW (4b8a955) collector task + exporter mount |
| `router` (exporter) / `export_consolidated` | exporter_routes.py | persistence / reporter | ★ NEW (a7e2465) `POST /export/run` |
| `fetch_sheet_data` / `render_xlsx` / `_fill_op_manning` / `_fill_op_consumed` / `_fill_equipment` / `_fill_qty` / `_fill_timeshift` / `_korean_weekday` / `_coerce` / `NoDataError` / `SheetData` / COL × 4 | exporter.py | reporter | ★ NEW (38399ac + b3010df) xlsx 4 시트 생성 |
| `consolidated_template.xlsx` | exporter_templates/ | reporter | ★ NEW (99ef43b) 4 시트 dummy 헤더 |
| `_format_document` / `_build_metadata` (15 필드) | atomizer.py | atomizer | ★ NEW (9252ac7) live / backfill 2 모드 + l7_5_activity / perperson / productivity_pct |
| `ChromaClient init 3 retry + upsert batch 100 split` | chroma_client.py + atomizer.py | atomizer | ★ NEW (a3db32a) HNSW hang 방어 |
| `plan_main_qty atomic distinct SUM` | forecaster/agent.py | forecaster | ★ NEW (6a89848) l6 SUM 폭주 fix |
| `fetch_pg_actual_cum_qty` | forecaster/agent.py | forecaster | ★ NEW PG 우회 (Chroma actual 부정확) |
| `_build_s_curve` (★★ 산식 A) | optimizer/view_builder.py:880~1021 | optimizer | ★★ NEW (c0a0641) WV × MH 가중 |
| `build_site_summary_payload` / `generate_site_summary` (★★) | optimizer/site_summary.py | optimizer | ★★ NEW (21c10f7) site narrative LLM JSON |
| `_build_kpi delay_days MEDIAN` | optimizer/view_builder.py | optimizer | ★ NEW (e9b66d4) AVG → PERCENTILE_CONT(0.5) |
| `_build_scenarios` percentile 4 | optimizer/view_builder.py | optimizer | ★ NEW (3781e5b) |
| `_build_productivity_views_v2` | optimizer/view_builder.py | optimizer | ★ NEW (drift #N19) |
| `T17 quadrant ↔ by_wp wp_id 매칭` | optimizer/view_builder.py | optimizer | ★ NEW (2c2ba75) Jaccard 11% → 100% |
| `INCIDENT_KEYWORDS` 9종 | optimizer/retrieve.py | optimizer | ★ NEW (d79a438) 5 → 9 |
| `optimize() asyncio.gather + to_thread 4×` | optimizer/agent.py | optimizer | ★ NEW (690c305) |
| `forecast() asyncio.gather + Semaphore 4×` | forecaster/agent.py | forecaster | ★ NEW (6ba0126) |
| `batch_size 16 → 64` | atomizer.py | atomizer | ★ NEW (b560dd4) |
| `insert_mapper_activities_batch` 33 → 37 컬럼 | db.py:639 | persistence / mapper | ★ NEW (d40c84f) l5_disc / l7_sub / l7_5_activity / sub_work_area |

### 본 cycle 변경 (★ NEW 아닌 기존 핸들러)

| Function | 변경 |
|---|---|
| `build_graph` (graph.py) | 진입점 collector 로 이동, 노드 9 개로 확장 |
| `mapper_node` (graph.py) | 5 INSERT 비-atomic (#M1) — 변경 없음, 이슈 신규 발견 |
| `hil_1_node` / `hil_2_node` (graph.py) | CPIA_HIL_AUTO_BYPASS env 활용 (이전 cycle 흡수), prod 가드 부재 #C1 + HIL2 AUTO_BYPASS 없음 #M4 |
| `optimize` (optimizer/agent.py) | asyncio.gather + to_thread 4× + 9 jsonb fan-out 확장 |
| `forecast` (forecaster/agent.py) | asyncio.gather + Semaphore 4× |
| `insert_mapped_history_batch` (db.py) | ON CONFLICT 가 trade 컬럼 누락 #C3 (변경 없음, 이슈 신규 발견) |
| `CPIAState` (state.py) | 16 → 20 필드 (D-12 4 신규), parsed annotation drift #C2 |

---

## 본 cycle Critical / High 이슈 표 (32 신규/갱신)

| ID | 영역 | 심각도 | 설명 |
|---|---|---|---|
| **#C1** | orchestration | **Critical** | `CPIA_HIL_AUTO_BYPASS` env prod 가드 부재 |
| **#C2 (orch)** | orchestration | **Critical** | `CPIAState.parsed` annotation drift (`list[Activity]` 실제는 `ParsedDailyReport`) |
| **#N13** | persistence | **Critical** | `daily_reports.site_summary_text` migration SQL 부재 (fresh rebuild UndefinedColumnError) |
| **#C2 (pers)** | persistence | **Critical** | `/export/run` 매 요청 PGClient 신규 풀 (app.state.pg 미재사용) |
| **#C3** | persistence / atomizer | **Critical** | `mapped_history.trade` 항상 NULL (16f1b88 commit msg 약속 vs 실 코드 mismatch) |
| #N17 | optimizer | M | working tree `view_builder.py:1447` 1 줄 미커밋 (다른 세션) |
| #N18 | optimizer | M | `Optional` 미 import (5+2 곳) |
| #N19 | optimizer | M | `_build_productivity_views` v1 ↔ v2 같은 컬럼 다른 산식 drift |
| #N20 | optimizer | M | `site_summary` production 미연결 (backfill only) |
| #N23 / #R-N1 | reporter | M | reporter → exporter rename 미시행 (CLAUDE.md 약속 vs 실 코드) |
| #R-N2 | reporter | M | B_Track FE swap 미실행 (NEXT_PUBLIC_FASTAPI_BASE) |
| #M1 | orchestration | M | mapper_node 5 INSERT 비-atomic |
| #M4 | orchestration | M | HIL2 AUTO_BYPASS 없음 |
| #N25 | parser | M | parser_warning PG 영속화 미구현 |
| #N26 | forecaster | M | 9-22 outlier 잔존 (`6a89848` 부분 해결) |
| #N27 | mapper | M | wa NULL row forecast bucket 누락 |
| #N28 | persistence | M | `/api/agents/status` N+1 7회 |
| #M2 | persistence | M | init.sql ↔ migrations 11 테이블 누락 |
| #N4 | orchestration | M | `daily_reports.kpi_jsonb / wp_summary_jsonb / quadrant_jsonb` 일부 빈 dict |
| #N1 | optimizer | M | RAG fixture vs synthetic_v2 ±10% (사용자 합의) |
| #A-N5 | atomizer | M | `_format_document` short form fallback |
| Low 10+ | various | L | 상세 = architecture_overview §6 |

---

## 다음 cycle 위임 (future)

| 영역 | 사유 |
|---|---|
| reporter → exporter rename | 파일명 + 13 import + GraphConfig.reporter + _AGENTS_META[4] (CLAUDE.md 약속 vs 실 코드 #R-N1) |
| `daily_reports.site_summary_text` migration | fresh rebuild UndefinedColumnError 위험 #N13 |
| v1↔v2 통일 (`_build_productivity_views`) | drift #N19 — v1 제거 권장 |
| site_summary live `optimize()` 연결 | 현재 backfill_v2 --with-summary 만 호출 #N20 |
| `mapped_history.trade` SQL 추가 | atomizer mh_rows dict + insert_mapped_history_batch SQL 둘 다 #C3 |
| B_Track exporter FE swap | NEXT_PUBLIC_FASTAPI_BASE env + ConsolidatedReportCard.tsx handleExport #R-N2 |
| AUTO_BYPASS prod 가드 | env name suffix + assert #C1 |
| `CPIAState.parsed` 타입 수정 | state.py annotation #C2 |
| 9-22 forecaster outlier | classify.py 조건 강화 #N26 |
| parser_warning PG 영속화 | parser_reports.warnings_jsonb 컬럼 #N25 |
| HIL2 AUTO_BYPASS | env + 가드 #M4 |
| mapper_node atomic INSERT | 5 INSERT 트랜잭션 wrap #M1 |
| /api/agents/status N+1 | join + group by #N28 |
| init.sql ↔ migrations 정합 | 11 테이블 누락 #M2 |

---

*최종 수정: 2026-05-26 (1ba783f) — 70+ commit 흡수, 8 서브시스템 design_intent 갱신 (총 4,048 줄, 이전 ~3,200 +800)*
*이전 수정: 2026-05-20 (ef7c6cd) — parser+mapper refactor + view_builder 752 LOC + FastAPI 12 endpoint*
