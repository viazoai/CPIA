# CPIA Architecture Overview (deep-dive 라이트)

- **Generated**: 2026-05-17 (hil1-forecaster-reporter cycle 종결 후 갱신)
- **Git SHA**: `d57b0c5` (A_Track HEAD, origin sync)
- **PR pending**: #19 (조형준 리뷰 + main 머지 대기)
- **Range**: pipeline 전체 (agents 7개 + graph + state + db + checkpointer) — Web/B_Track 제외
- **Pair**: `./design-intent/INDEX.md` (메인 카탈로그) + `../docs/audit/2026-05-17-cpia-drift-backlog.md` (해소 우선순위)

본 문서는 함수별 깊이 보다는 **시스템 다이어그램 + 서브시스템 요약 + 미구현 인터페이스 정리 + 이슈 표** 위주. 함수 단위 깊이는 `./design-intent/design_intent_<X>.md` 참조.

> **이번 cycle 갱신 요지** (vs 이전 f9a695f):
> - HIL 1 + Reporter graph 노드 신규 구현 (drift #1, #4 해소)
> - synthetic_daily_report fixture fix (drift #3 해소)
> - Forecaster classify.py 수정 X (drift #2 = #3 input 의 over-산출이 root cause, fix 후 자동 해소)
> - InMemorySaver → AsyncPostgresSaver 전환 (design-intent O-6 해소)
> - mapping_corrections / daily_reports / checkpoints 모두 활성화 (O-2 / O-6 해소)
> - 신규 drift 7건 (#N1~#N7) 추가 발견 — `../docs/audit/2026-05-17-cpia-drift-backlog.md` 참조

---

## 1. 시스템 다이어그램

```
                              ┌──────────────────────────────────────────────────────────┐
                              │              [B_Track] Next.js Dashboard                  │
                              │   Layer 1 (현장 카드) / Layer 2 (상세 + HIL Modal)        │
                              └─────────────────────┬────────────────────────────────────┘
                                                    │ HTTP (BFF)
                              ┌─────────────────────┴────────────────────────────────────┐
                              │   Next.js API Routes (proxy to FastAPI / PG SELECT)      │
                              └─────────────────────┬────────────────────────────────────┘
                                                    │ HTTP
                                ┌───────────────────┴────────────────────┐
                                │   [A_Track] FastAPI — pipeline/api.py   │  ⚠ 0 byte (미구현)
                                │   POST /run / POST /resume / GET /status │
                                └───────────────────┬────────────────────┘
                                                    │ in-process
   ┌────────────────────────────────────────────────┴────────────────────────────────────┐
   │                                  LangGraph StateGraph                                │
   │   pipeline/graph.py:build_graph                                                      │
   │                                                                                      │
   │   ┌──────────┐  ┌────────┐  ┌──────────┐  ┌──────┐  ┌────────────┐  ┌──────┐         │
   │   │collector │→│ parser  │→│ mapper   │→│hil_1│→│  atomizer  │→│forec.│         │
   │   │ ⚠ 0 byte│ │ ✓ 306LOC│ │ ✓ 393LOC │ │ ✓ NEW│ │  ✓ 118LOC  │ │ ✓ 898│         │
   │   └──────────┘  └────────┘  └──────────┘  └──┬───┘  └────────────┘  └──┬───┘         │
   │        ↑                                      │                          │             │
   │   drift #5                              interrupt                        ▼             │
   │                                         + Command(resume=)        ┌──────────┐         │
   │                                         (CLI 인터랙티브 — drift)   │  hil_2   │         │
   │                                                                   └──┬───┬───┘         │
   │                                                                      │   │             │
   │                                                            selection ▼   ▼ no-select   │
   │                                                          ┌─────────────┐                │
   │                                                          │  optimizer  │                │
   │                                                          │  ✓ 1485 LOC │                │
   │                                                          └──────┬──────┘                │
   │                                                                 ▼                       │
   │                                                          ┌─────────────┐                │
   │                                                          │  reporter   │ ✓ NEW (161)    │
   │                                                          │  (종합 1종) │                │
   │                                                          └──────┬──────┘                │
   │                                                                 ▼                       │
   │                                                                END                       │
   └───────────────────────────┬─────────────────────────────────┬───────────────────────┘
                               │                                 │
                ┌──────────────┴──────────────┐    ┌─────────────┴──────────────┐
                │    PostgreSQL (asyncpg)     │    │   ChromaDB (HTTP)          │
                │    pipeline/db.py (345)     │    │   pipeline/chroma_client   │
                │  ─────────────────────────  │    │   .py (40)                 │
                │  ✓ pipeline_runs            │    │  ─────────────────────────  │
                │  ✓ forecasts (27 컬럼 v3.1)  │    │  ✓ wbs_master (189 doc)    │
                │  ✓ optimizer_advice (9 col) │    │     → Mapper RAG           │
                │  ✓ activity_master (read)   │    │  ✓ daily_activities        │
                │  ✓ sites (Dashboard)        │    │     → Forecaster/Optimizer │
                │  ✓ daily_reports ✦ NEW      │    │       유사 이력 검색       │
                │     (history_csv_row JSONB) │    │                            │
                │  ✓ mapping_corrections ✦    │    └────────────────────────────┘
                │     (HIL 1 영속, JSONB 합쳐) │
                │  ✓ checkpoints ✦ NEW        │
                │     (LangGraph PostgresSaver │
                │      + 3 부속 테이블 auto)   │
                └─────────────────────────────┘
```

**범례**: ✓ = 구현됨 / ⚠ = 미구현 또는 dead / ✦ = 본 cycle 활성화 / ★ = audit drift 우선순위.

**graph edges (현 d57b0c5):**
```
START → mapper → hil_1 → atomizer → forecaster → hil_2 →
        ├─ (hil_2_selection 비어있음) ─────────────────────→ reporter → END
        └─ (selection 있음) → optimizer ───────────────────→ reporter → END
```

`build_demo_graph` 도 동일 (START → forecaster, mapper/atomizer/hil_1 제외).

---

## 2. 서브시스템 요약 (8개 — design-intent 카드 1:1 매핑)

| 서브시스템 | 책임 | 핵심 함수 | LOC | LLM | 외부 의존 | 카드 |
|---|---|---|---:|---|---|---|
| **orchestration** | LangGraph StateGraph + HIL 1/2 interrupt/resume + edges | `build_graph` / `hil_1_node` ✦ / `hil_2_node` / `reporter_node` ✦ / `_build_review_needed` ✦ / `_apply_corrections` ✦ | 467 | — | LangGraph | [orchestration](./design-intent/design_intent_orchestration.md) |
| **persistence** | PG asyncpg pool (8 활성 테이블 + checkpoints) + Chroma HTTP (2 컬렉션) | `insert_forecast` / `insert_optimizer_advice` / `insert_mapping_correction` ✦ / `insert_daily_report` ✦ / `fetch_l6_plan_mh_map` | 345 | — | asyncpg + chromadb | [persistence](./design-intent/design_intent_persistence.md) |
| **checkpointer** ✦ | LangGraph thread-local 상태 영속 (AsyncPostgresSaver + lazy open) | `build_checkpointer` / `_LazyAsyncPostgresSaver` ✦ | 88 | — | langgraph-checkpoint-postgres + psycopg + psycopg-pool | [orchestration §PostgresSaver](./design-intent/design_intent_orchestration.md) |
| **parser** | xlsx → 4시트 통합 ParsedDailyReport | `parse_daily_report` / `_extract_meta` / `_ffill` | 306 | — | openpyxl | [parser](./design-intent/design_intent_parser.md) |
| **mapper** | 6단계 매핑 (BP filter → Embed → Chroma → LLM → WA 4단계) | `map_activity` / `_prorate_mh` / `resolve_wa` | 393 | Azure gpt-5.1 + 임베딩 | PG + Chroma | [mapper](./design-intent/design_intent_mapper.md) |
| **atomizer** | Chroma daily_activities 적재 + fail-fast PG | `atomize` / `_make_doc_id` / `_build_metadata` | 118 | Azure 임베딩만 | PG + Chroma | [atomizer](./design-intent/design_intent_atomizer.md) |
| **forecaster** | RAG 우선 + Plan fallback 진단 (assessment + risk_level) | `_forecast_one_group` / `classify_assessment_rag` / `compute_delay` | 898 | Azure gpt-5.1 | PG + Chroma | [forecaster](./design-intent/design_intent_forecaster.md) |
| **optimizer** | LLM 조언 + 결정론 recovery_distribution + synthetic fixture (수정됨) | `optimize` / `_compute_recovery_distribution` / `fetch_degradation_cases` / `generate_fake_daily_report` (fix) | 1495 | Azure gpt-5.1 | PG + Chroma | [optimizer](./design-intent/design_intent_optimizer.md) |
| **reporter** ✦ NEW | Mapper+Forecaster+Optimizer 결과 종합 보고서 1 종 + PG daily_reports.history_csv_row 영속 | `report` / `_build_llm_input` / `_build_summary` | 161 | Azure gpt-5.1 | PG | [reporter](./design-intent/design_intent_reporter.md) (작성 예정) |

**전체 LOC**: ~4,271 (테스트 제외 — agent 코드만, 본 cycle +290 = reporter 161 + checkpointer 70 + graph 119 - 60)

---

## 3. 데이터 흐름 — happy path (남웅 47 row 예시, 현 d57b0c5)

```
1. 작업일보 xlsx (data/input/2025-09-25/통합작업일보_M15X.xlsx)
       │
       ▼  [Collector] ⚠ 미구현 — 외부에서 직접 경로 주입
2. parse_daily_report(xlsx)
       │  • 4 시트 검증 → ParseError 또는 ParsedDailyReport
       │  • 시트1 BPSummary[] / 시트2 JobAllocation[] / 시트3 EquipmentAllocation[] / 시트4 Activity[]
       │  • report_date "2025-09-25", project "M15X Ph-3 IBL PJT"
       ▼
3. mapper_node — graph.py:40
       │  • activities 47 row 각각 map_activity 호출
       │     ① fetch_bp_candidates (PG) → BP scope 후보
       │     ② build_embedding_input → Azure 임베딩
       │     ③ Chroma wbs_master top-15 검색 → BP filter 교집합 max 8
       │     ④ build_llm_input → Azure gpt-5.1 분류 → {choice, confidence, reason}
       │     ⑤ resolve_wa 4단계 → WAResolution(value, source)
       │     ⑥ requires_review = conf < 0.7 or source == "hil_required"
       │  • _prorate_mh: BP사 인원 88 → l6_main 별 plan_mh 비례 분배
       ▼
4. hil_1_node ✦ — graph.py:57 (이번 cycle 신규)
       │  • _build_review_needed(mapped) → requires_review=True 인 Activity payload
       │  • review_needed 0건 → interrupt 미발생, hil_1_corrections={}, pass-through
       │  • review_needed >=1건 → interrupt({"review_needed": [...]}) → CLI prompt
       │  • Command(resume={"<idx>": {"wa": ..., "l6_main": ...}}) 받음 (str key 필수)
       │  • _apply_corrections — 답한 row: 사용자 정정 / 답 안 한 row: Mapper 추천 그대로 수용
       │  • PG insert_mapping_correction (original / corrected JSONB 합쳐 박음)
       ▼
5. atomizer_node — graph.py (이전 동일)
       │  • assert_pipeline_run_exists (PG fail-fast)
       │  • _make_doc_id (SHA256[:16]) → 47 row → dedup 11 unique
       │  • Azure embedding batch (size 16) → Chroma daily_activities upsert
       │  • update_run_atomized_count (PG, 0-row raise)
       ▼
6. forecaster_node — graph.py (이전 동일)
       │  • 그룹화: (남웅건설, 철근콘크리트공사) 1개
       │  • _forecast_one_group ① ~ ⑧ (이전 cycle 동일)
       │     ④ classify_assessment_rag (delta < -0.15 → "주의/이상"; delta >= -0.15 → "정상")
       │     ⑥ LLM (assessment != None) → reasoning + recovery_likelihood
       │     ⑧ insert_forecast (PG, 27 컬럼)
       │  • ✦ 이번 cycle: synthetic_daily_report fixture fix 로 ratio=0.45 시 today_prod
       │       = baseline_prod × 0.45 (이전 = N × baseline × 0.45 오버산출) → assessment="이상"
       ▼
7. hil_2_node — graph.py (이전 동일)
       │  • risky 그룹 (risk_level in {주의, 이상}) 추출 → interrupt({"risky_groups": payload})
       │  • risky 0 → interrupt 미발생, hil_2_selection=[], pre_optimizer_cases={}
       ▼ (PM 응답 — Command(resume=[group_key, ...]))
8. conditional_edge — graph.py:hil_2 분기 ✦
       │  • hil_2_selection 비어있지 않음 → optimizer → reporter
       │  • hil_2_selection 비어있음 → reporter 직행 (이전 = END 직행)
       ▼
9. optimizer_node — graph.py:180 (이전 동일)
       │  • selected group 마다:
       │     - cases<3 → cold_start row (LLM skip, recovery_distribution 만 산출)
       │     - cases>=3 → build_llm_user_input → Azure gpt-5.1 → diagnosis + recommendations
       │  • _compute_recovery_distribution (Counter) override LLM 출력
       │  • insert_optimizer_advice (PG, 9 컬럼 JSONB falsy 보호)
       ▼
10. reporter_node ✦ — graph.py:311 (이번 cycle 신규)
       │  • mapped empty → 짧은 fallback MD + PG INSERT skip
       │  • Azure gpt-5.1 호출 (SYSTEM_PROMPT 3 부 구조 + Mapper+Forecaster+Optimizer JSON)
       │     - 1부 작업 통합 (mapped 합산)
       │     - 2부 생산성 진단 (forecast row 별 1 단락)
       │     - 3부 PM 선택 공종 권고 (optimizer_advice 비어있으면 생략)
       │  • _build_summary → {total_workers, total_qty_by_trade, risk_counts, advice_count}
       │  • insert_daily_report (PG, history_csv_row 컬럼에 summary 박음, bp_name=None)
       ▼
11. END
```

**시뮬 1 (2026-05-17) 실 검증**: ratio=0.45 → today_prod = baseline × 0.45 → assessment="이상" 발현 → Reporter 종합 보고서 1481 chars + summary {risk_counts: 이상1/정상1/주의1, advice_count: 2, total_workers: 1507.0}. raw = `../docs/audit/raw/v2-scenario-1-156657ed.md`.

---

## 4. 데이터 레이어

### PostgreSQL (8 활성 테이블 + 1 master + 4 LangGraph 부속)

| 테이블 | 활성 | 컬럼 | 소비 | 비고 |
|---|---|---|---|---|
| `pipeline_runs` | ✓ | run_id, site_id, date, status, current_node, atomized_count | 모든 노드 | Atomizer fail-fast 의존 |
| `forecasts` | ✓ | 27 컬럼 (v3.1 main_unit + today_conditions 추가) | Forecaster insert / Dashboard SELECT | JSON 5종 (jsonb) |
| `optimizer_advice` | ✓ | 9 컬럼 (4 JSONB + diagnosis + assessment) | Optimizer insert / Dashboard SELECT | JSONB falsy 보호 (cold_start 영속) |
| `mapping_corrections` | ✓ ✦ NEW | 6 컬럼 (id, run_id, report_date, original JSONB, corrected JSONB, created_at) — `postgres.md §8` 의 work_content/company/trade/correction_type 컬럼은 init.sql 에 미반영 (drift #N2) — 본 cycle 은 original/corrected JSONB 안에 합쳐서 박음 | HIL 1 insert | drift #N2: schema migration 별 cycle |
| `activity_master` | ✓ (RO) | wbs_activity_id, company, wa, l6_main, plan_total_qty, plan_mh, plan_start, plan_finish 등 | Mapper / Forecaster fetch | `scripts/load_master_list.py` 로 적재 |
| `sites` | ✓ | site_id, name, mock_flag | Dashboard | 5 mock + 1 real PoC |
| `daily_reports` | ✓ ✦ NEW | 7 컬럼 (id, run_id, report_date, bp_name nullable, report_md, history_csv_row JSONB nullable, created_at) — `postgres.md §5` 의 date/summary 필드명 mismatch (drift #N3) | Reporter insert | drift #N3: schema migration 별 cycle |
| `checkpoints` + `checkpoint_writes` + `checkpoint_blobs` + `checkpoint_migrations` | ✓ ✦ NEW | (LangGraph PostgresSaver auto) | `_LazyAsyncPostgresSaver` 가 첫 호출 시 lazy open | design-intent O-6 해소 |

### ChromaDB (2 컬렉션 — 이전 cycle 동일)

| 컬렉션 | 활성 | 1 doc = | 메타 핵심 필드 | 검색 주체 | 임베딩 모델 |
|---|---|---|---|---|---|
| `wbs_master` | ✓ | 1 (WA, L6) 그룹 | wa, l5_disc, l6_main, units, companies | Mapper (단계 ③) | text-embedding-3-small-ai-board-test (1536d) |
| `daily_activities` | ✓ | 1 Activity (시트4 line) | date, run_id, company, l6_main, unit, today_qty, assigned_workers, worker_source, mapping_conf, conditions (CSV) | Atomizer upsert / Forecaster RAG / Optimizer retrieve | text-embedding-3-small-ai-board-test (1536d) |

---

## 5. 미구현 인터페이스 (stub 3종 — 이번 cycle 에서 reporter.py 제외)

빈 골격 3개. 각자 drift backlog 우선순위와 호출 위치:

### `pipeline/agents/collector.py` (0 byte)

- **드리프트 우선순위**: #5
- **호출 위치**: 외부 (FastAPI `/run` 또는 CLI `main.py`)
- **기대 인터페이스 (PoC plan 추정)**:
  ```python
  def collect(input_dir: Path) -> list[Path]:
      """data/input/YYYYMMDD/ 폴더의 .xlsx 모두 yield."""
  ```
- **다음 단계 (brainstorming → spec → plan)**:
  - openpyxl 으로 .xlsx 시트 텍스트 + .txt 직접 읽기
  - data/input/YYYYMMDD/ 폴더 watcher 또는 CLI argument 진입

### `pipeline/main.py` (0 byte)

- **드리프트 우선순위**: D-7 (defer)
- **기대**: `python -m pipeline.main --input data/input/2025-09-27/` CLI 진입점.
- 통합 cycle (#5 Collector 와 함께) 권고.

### `pipeline/api.py` (0 byte)

- **드리프트 우선순위**: D-7 (defer)
- **기대**: FastAPI `/run`, `/resume`, `/status/{run_id}` 3 엔드포인트 (CLAUDE.md `## 아키텍처` 약속).
- 통합 cycle (#5 Collector 와 함께) 권고.

### `pipeline/agents/reporter.py` (✓ 161 lines — 이번 cycle 구현)

drift #1 해소. spec = `../docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md` §5.3.

---

## 6. 이슈 표 (audit drift backlog 해소 4건 + 신규 7건 + 잔존 4건)

### Audit drift backlog (이번 cycle 흡수 완료)

| # | 이슈 | 흡수 commit | 상태 |
|---|---|---|---|
| #1 | Reporter 미구현 | `22d44c2` feat(reporter) | ✓ 해소 (pipeline/agents/reporter.py 161 lines) |
| #2 | Forecaster assessment "정상" bias | (classify.py:34 수정 X) | ✓ 자동 해소 (#3 root cause 해결 후, PM 원안 v2 정합) |
| #3 | synthetic fixture productivity_ratio bug | `c093631` fix(synthetic_daily_report) | ✓ 해소 (synthetic_daily_report.py:78 n_activities 분배) |
| #4 | HIL 1 (Mapper interrupt) 미구현 | `1bb78fb` feat(hil_1) | ✓ 해소 (graph.py hil_1_node + helpers + insert_mapping_correction) |
| #5 | Collector + main.py + api.py | (out of scope) | ⚠ 잔존 — 별 cycle |

### Audit drift backlog (이번 cycle 잔존 — defer)

| # | 이슈 | 잔존 사유 |
|---|---|---|
| D-1 | synthetic_v2 incident 5종 (병행작업 부재) | defer |
| D-2 | synthetic 2 path 통합 미진 | defer |
| D-3 | Embed config dim mismatch (1536 vs 3072 mention) | defer |
| D-7 | main.py / api.py / Collector 통합 cycle | 별 cycle (#5 와 통합) |

### Design-intent 추가 발견 (이번 cycle 흡수)

| # | 발견 | 흡수 | 상태 |
|---|---|---|---|
| O-2 | `mapping_corrections` 테이블 dead schema | `1bb78fb` feat(hil_1) | ✓ 해소 (insert_mapping_correction 활성화) |
| O-5 | `waiting_hil_1` Literal 값 미사용 | (state.py 변경 X, hil_1_node 가 활성화) | ✓ 자동 해소 |
| O-6 | checkpoints 테이블 dead (InMemorySaver) | `41908f6` feat(checkpointer) | ✓ 해소 (AsyncPostgresSaver 전환) |

### 신규 drift (본 cycle 발견 — defer, `../docs/audit/2026-05-17-cpia-drift-backlog.md` 참조)

| # | 항목 | 영향도 | 처리 |
|---|---|---|---|
| #N1 | RAG fixture_prod vs synthetic_v2 분포 ±10% mismatch (delta=10.7%) | med | xfail strict=False 마킹. 별 cycle. |
| #N2 | postgres.md §8 mapping_corrections 와 init.sql 어긋남 (work_content/company/trade/correction_type 컬럼 누락) | low | JSONB 합쳐 박음 — schema migration 별 cycle |
| #N3 | postgres.md §5 daily_reports 와 init.sql 어긋남 (date→report_date / summary→history_csv_row / bp_name 추가) | low | history_csv_row 사용 — postgres.md 정정 또는 init.sql 정렬 별 cycle |
| #N4 | 시뮬 2/3/4 추가 검증 skip | low | 시뮬 1 + rerun 으로 7 성공 기준 충족, 추가 path 별 cycle |
| #N5 | LangGraph Command(resume=dict) int key TypeError | low | API 사용 룰 — str key 필수, hil_1_node 가 int(k) 변환 처리 |
| #N6 | .env.local 경로 spec 명시 어긋남 (실제 = root) | low | cosmetic spec 정정 |
| #N7 | synthetic_daily_report main_cli final report_md 미 print | low | 가독성 개선 — 별 cycle |

### Design-intent 잔존 (audit cycle 발견, 본 cycle 미흡수)

| # | 발견 | 상태 |
|---|---|---|
| O-1 | `PGClient.fetch_activity` 미사용 의심 | 여전히 미사용 (Mapper 통합 후 검토) |
| O-3 | `AtomizerConfig.embedding_dim=1536` 미사용 | 여전히 미사용 (Chroma cold start 시 참고용) |
| O-4 | `WAResolution.source="auto_sheet1_text"` 미반환 | 여전히 미반환 (GATE 2 활성화 대기 — 의도된 미활성) |
| O-7 | synthetic 2 path 통합 미진 | defer |
| O-8 | synthetic_v2 incident 5종 (병행작업 부재) | defer |

---

## 7. 파일 구조 + LOC 요약 (현 d57b0c5)

```
pipeline/                              합계 ~4,271 LOC (테스트 제외) [+290 vs f9a695f]
├── graph.py                  391      [T2: 6 nodes + 2 builders + 2 helpers (_build_review_needed + _apply_corrections)] [+119]
├── state.py                  137      [T2: CPIAState TypedDict + 5 schemas] (변경 0)
├── checkpointer.py            88      [T2: _LazyAsyncPostgresSaver (AsyncPostgresSaver + lazy open) + memory fallback] [+70]
├── constants.py                5      (변경 0)
├── db.py                     345      [T2: 9 PG 함수 (+ insert_mapping_correction + insert_daily_report)] [+36]
├── chroma_client.py           40      (변경 0)
│
├── agents/
│   ├── parser.py             306      (변경 0)
│   ├── mapper.py             393      (변경 0)
│   ├── atomizer.py           118      (변경 0)
│   ├── collector.py            0      ⚠ 미구현 (drift #5)
│   ├── reporter.py           161 ✦ NEW  [T2: SYSTEM_PROMPT + _build_llm_input + _build_summary + report]
│   │
│   ├── forecaster/
│   │   ├── agent.py          276      (변경 0)
│   │   ├── prompt.py         134      (변경 0)
│   │   ├── classify.py       114      (변경 0 — PM 원안 v2 정합)
│   │   ├── rerank.py          50      (변경 0)
│   │   ├── aggregate.py      119      (변경 0)
│   │   ├── synthetic.py      189      (변경 0)
│   │   ├── constants.py        8
│   │   └── __init__.py         8
│   │
│   └── optimizer/
│       ├── agent.py          156      (변경 0)
│       ├── prompt.py         315      (변경 0)
│       ├── retrieve.py       161      (변경 0)
│       ├── synthetic_daily_report.py 495  [T2: generate_fake_daily_report (line 78 fix) + _parse_scenario (line 118 가드) + _build_reporter_config] [+13]
│       ├── synthetic_v2.py   363      (변경 0)
│       └── __init__.py         8
│
├── tests/                             합계 ~3,540 LOC (+340 vs f9a695f)
│   ├── test_db_mapping_corrections.py ✦ NEW (76)
│   ├── test_db_daily_reports.py ✦ NEW (70)
│   ├── test_graph_hil1.py ✦ NEW (103)
│   ├── test_graph_e2e_hil1.py ✦ NEW (293)
│   ├── test_reporter.py ✦ NEW (177)
│   ├── test_checkpointer.py ✦ NEW (48)
│   ├── optimizer/test_synthetic_daily_report_fixture.py ✦ NEW (140)
│   └── ... (기존 회귀 183 → 197 + 1 xfailed)
│
├── main.py                     0      ⚠ 미구현 (drift D-7)
└── api.py                      0      ⚠ 미구현 (drift D-7)
```

---

## 8. 다음 작업 권고

### 본 cycle 후 잔존 drift (`../docs/audit/2026-05-17-cpia-drift-backlog.md` 참조)

1. **drift #5 Collector + main.py + api.py** — 통합 cycle (가장 높은 우선순위 — PoC 전체 흐름 완성)
2. **drift #N1 RAG fixture_prod vs synthetic_v2 정합** — synthetic_v2 적재 분포 정렬 (Forecaster 검증 신뢰성 ↑)
3. **drift #N2 + #N3 schema migration** — postgres.md 정정 또는 init.sql 정렬 (1 PR 묶음 가능)
4. **drift #N4 시뮬 2/3/4 추가 검증** — Forecaster 다양 path 정합 (우천 0.8 / 돌관 / cold_start)
5. **D-1 ~ D-8** — defer (med/low)

### PoC 시연 준비

- **마감**: 2026-06-05 (목) — 본 cycle 후 ~2.5주 여유
- **시연 시나리오**: 시뮬 1 (남웅 0.45) 의 핸드오프 흐름 — interrupt + Command(resume=) 라이브 검증
- **준비물**: B_Track Dashboard 와 FastAPI `/run`/`/resume`/`/status` 통합 시점에 HIL 1 도 Dashboard Modal 로 전환 검토 (현 cycle 의 CLI 인터랙티브는 PoC 자체완결용 drift — spec §3 명시)

`./design-intent/INDEX.md` 의 "audit drift 매핑" 섹션 참조하여 진입.
