# CPIA Architecture Overview (deep-dive 라이트)

- **Generated**: 2026-05-17
- **Git SHA**: `f9a695f5315eba97b2686f55a72bc91ef6cae6b2` (A_Track)
- **Range**: pipeline 전체 (agents 7개 + graph + state + db + 미구현 stubs) — Web/B_Track 제외
- **Pair**: `./design-intent/INDEX.md` (메인 카탈로그) + `../docs/audit/2026-05-17-cpia-drift-backlog.md` (해소 우선순위)

본 문서는 함수별 깊이 보다는 **시스템 다이어그램 + 서브시스템 요약 + 미구현 인터페이스 정리 + 이슈 표** 위주. 함수 단위 깊이는 `./design-intent/design_intent_<X>.md` 참조.

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
   │   ┌──────────┐  ┌────────┐  ┌──────────┐  ┌────────────┐  ┌──────┐  ┌───────────┐   │
   │   │collector │→│ parser  │→│ mapper   │→│  atomizer  │→│forec.│→│  hil_2    │   │
   │   │ ⚠ 0 byte│ │ ✓ 306LOC│ │ ✓ 393LOC │ │  ✓ 118LOC  │ │ ✓ 898│ │ ✓ in graph│   │
   │   └──────────┘  └────────┘  └──────────┘  └────────────┘  └──────┘  └─────┬─────┘   │
   │        ↑                          ↑                                          │       │
   │   drift #5                  HIL 1 자리                          conditional ▼        │
   │                            ⚠ 노드 없음                          edge                  │
   │                            (drift #4)                  ┌─────────────┐                │
   │                                                        │  optimizer  │                │
   │                                                        │  ✓ 1485 LOC │                │
   │                                                        └──────┬──────┘                │
   │                                                               ↓                       │
   │   ┌──────────┐                                              END                       │
   │   │ reporter │  ← graph에 노드 없음. drift #1                                          │
   │   │ ⚠ 0 byte│                                                                        │
   │   └──────────┘                                                                        │
   └───────────────────────────┬─────────────────────────────────┬───────────────────────┘
                               │                                 │
                ┌──────────────┴──────────────┐    ┌─────────────┴──────────────┐
                │    PostgreSQL (asyncpg)     │    │   ChromaDB (HTTP)          │
                │    pipeline/db.py (309)     │    │   pipeline/chroma_client   │
                │  ─────────────────────────  │    │   .py (40)                 │
                │  ✓ pipeline_runs            │    │  ─────────────────────────  │
                │  ✓ forecasts (27 컬럼 v3.1)  │    │  ✓ wbs_master (189 doc)    │
                │  ✓ optimizer_advice (9 col) │    │     → Mapper RAG           │
                │  ✓ activity_master (read)   │    │  ✓ daily_activities        │
                │  ✓ sites (Dashboard)        │    │     → Forecaster/Optimizer │
                │  ✓ daily_reports            │    │       유사 이력 검색       │
                │  ⚠ mapping_corrections      │    │                            │
                │     (dead schema — HIL 1)   │    │                            │
                │  ⚠ checkpoints              │    └────────────────────────────┘
                │     (LangGraph auto, 현재    │
                │      InMemorySaver 사용 →   │
                │      PostgresSaver 미활성)  │
                └─────────────────────────────┘
```

**범례**: ✓ = 구현됨 / ⚠ = 미구현 또는 dead / ★ = audit drift 우선순위.

---

## 2. 서브시스템 요약 (7개 — design-intent 카드 별로 1:1 매핑)

| 서브시스템 | 책임 | 핵심 함수 | LOC | LLM | 외부 의존 | 카드 |
|---|---|---|---:|---|---|---|
| **orchestration** | LangGraph StateGraph + HIL interrupt/resume + checkpoint | `build_graph` / `hil_2_node` / `build_checkpointer` | 432 | — | LangGraph | [orchestration](./design-intent/design_intent_orchestration.md) |
| **persistence** | PG asyncpg pool (7 테이블) + Chroma HTTP (2 컬렉션) | `insert_forecast` / `insert_optimizer_advice` / `fetch_l6_plan_mh_map` | 349 | — | asyncpg + chromadb | [persistence](./design-intent/design_intent_persistence.md) |
| **parser** | xlsx → 4시트 통합 ParsedDailyReport | `parse_daily_report` / `_extract_meta` / `_ffill` | 306 | — | openpyxl | [parser](./design-intent/design_intent_parser.md) |
| **mapper** | 6단계 매핑 (BP filter → Embed → Chroma → LLM → WA 4단계) | `map_activity` / `_prorate_mh` / `resolve_wa` | 393 | Azure gpt-5.1 + 임베딩 | PG + Chroma | [mapper](./design-intent/design_intent_mapper.md) |
| **atomizer** | Chroma daily_activities 적재 + fail-fast PG | `atomize` / `_make_doc_id` / `_build_metadata` | 118 | Azure 임베딩만 | PG + Chroma | [atomizer](./design-intent/design_intent_atomizer.md) |
| **forecaster** | RAG 우선 + Plan fallback 진단 (assessment + risk_level) | `_forecast_one_group` / `classify_assessment` / `compute_delay` | 898 | Azure gpt-5.1 | PG + Chroma | [forecaster](./design-intent/design_intent_forecaster.md) |
| **optimizer** | LLM 조언 + 결정론 recovery_distribution + synthetic fixture | `optimize` / `_compute_recovery_distribution` / `fetch_degradation_cases` | 1485 | Azure gpt-5.1 | PG + Chroma | [optimizer](./design-intent/design_intent_optimizer.md) |

**전체 LOC**: ~3,981 (테스트 제외 — agent 코드만)

---

## 3. 데이터 흐름 — happy path (남웅 47 row 예시)

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
       │     ④ build_llm_input (BP사 + 시트1/2/3 풍부 컨텍스트)
       │     ⑤ LLM 분류 (gpt-5.1) → {choice, confidence, reason}
       │     ⑥ resolve_wa 4단계 → WAResolution(value, source)
       │     ⑦ requires_review = conf < 0.7 or source == "hil_required"
       │  • _prorate_mh: BP사 인원 88 → l6_main 별 plan_mh 비례 분배
       ▼
4. atomizer_node — graph.py:57
       │  • assert_pipeline_run_exists (PG fail-fast)
       │  • _make_doc_id (SHA256[:16]) → 47 row → dedup 11 unique
       │  • Azure embedding batch (size 16) → Chroma daily_activities upsert
       │  • update_run_atomized_count (PG, 0-row raise)
       ▼
5. forecaster_node — graph.py:64
       │  • 그룹화: (남웅건설, 철근콘크리트공사) 1개
       │  • _forecast_one_group ① ~ ⑧
       │     ① aggregate_today_by_unit
       │     ② fetch_plan_for_group (PG)
       │     ③ Chroma daily_activities RAG → rerank_cases
       │     ④ classify_assessment (RAG ≥3건 → RAG / else Plan / else None)
       │     ⑤ fetch_chroma_actual + compute_delay
       │     ⑥ LLM (assessment != None) → reasoning + recovery_likelihood
       │     ⑦ classify_risk_level (assessment + recovery + delay + state)
       │     ⑧ insert_forecast (PG, 27 컬럼)
       ▼
6. hil_2_node — graph.py:71
       │  • risky 그룹 (risk_level in {주의, 이상}) 추출
       │  • 그룹별 coll.get(...) 1회 → _group_baseline + fetch_degradation_cases + fetch_recovery_trajectory
       │  • pre_optimizer_cases 영속 (state) + interrupt({"risky_groups": payload})
       │  • risky 0 → interrupt 미발생, hil_2_selection=[] → conditional edge END
       ▼ (PM 응답 — Command(resume=[group_key, ...]))
7. optimizer_node — graph.py:180
       │  • selected group 마다:
       │     - cases<3 → cold_start row (LLM skip, recovery_distribution 만 산출)
       │     - cases>=3 → build_llm_user_input → Azure gpt-5.1 → diagnosis + recommendations
       │  • _compute_recovery_distribution (Counter) override LLM 출력
       │  • insert_optimizer_advice (PG, 9 컬럼 JSONB falsy 보호)
       ▼
8. END
```

**HIL 1 미구현** — 현재 mapper → atomizer 직결. 이상적 흐름은 `mapper → hil_1_node (requires_review=True row 큐) → atomizer`. drift backlog #4 참조.

**Reporter 미구현** — graph 에 노드 없음. 이상적 흐름은 forecaster 후 분기 (`reporter || forecaster` 병렬 또는 atomizer 다음). drift backlog #1 참조.

---

## 4. 데이터 레이어

### PostgreSQL (7 테이블 + 1 master)

| 테이블 | 활성 | 컬럼 | 소비 | 비고 |
|---|---|---|---|---|
| `pipeline_runs` | ✓ | run_id, site_id, date, status, current_node, atomized_count | 모든 노드 | Atomizer fail-fast 의존 |
| `forecasts` | ✓ | 27 컬럼 (v3.1 main_unit + today_conditions 추가) | Forecaster insert / Dashboard SELECT | JSON 5종 (jsonb) |
| `optimizer_advice` | ✓ | 9 컬럼 (4 JSONB + diagnosis + assessment) | Optimizer insert / Dashboard SELECT | JSONB falsy 보호 (cold_start 영속) |
| `mapping_corrections` | ⚠ schema only | (HIL 1 영속) | 코드에 INSERT/SELECT 없음 | drift backlog #4 |
| `activity_master` | ✓ (RO) | wbs_activity_id, company, wa, l6_main, plan_total_qty, plan_mh, plan_start, plan_finish 등 | Mapper / Forecaster fetch | `scripts/load_master_list.py` 로 적재 |
| `sites` | ✓ | site_id, name, mock_flag | Dashboard | 5 mock + 1 real PoC |
| `daily_reports` | ✓ schema | (Reporter 출력) | Reporter insert | drift #1 — 본체 미구현 |
| `checkpoints` | ⚠ | (LangGraph PostgresSaver auto) | 현재 InMemorySaver 사용 — PG 비활성 | Reporter cycle 시 전환 |

### ChromaDB (2 컬렉션)

| 컬렉션 | 활성 | 1 doc = | 메타 핵심 필드 | 검색 주체 | 임베딩 모델 |
|---|---|---|---|---|---|
| `wbs_master` | ✓ | 1 (WA, L6) 그룹 | wa, l5_disc, l6_main, units, companies | Mapper (단계 ③) | text-embedding-3-small-ai-board-test (1536d) |
| `daily_activities` | ✓ | 1 Activity (시트4 line) | date, run_id, company, l6_main, unit, today_qty, assigned_workers, worker_source, mapping_conf, conditions (CSV) | Atomizer upsert / Forecaster RAG / Optimizer retrieve | text-embedding-3-small-ai-board-test (1536d) |

---

## 5. 미구현 인터페이스 (stub 4종)

빈 골격 4개. 각자 drift backlog 우선순위와 호출 위치:

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

### `pipeline/agents/reporter.py` (0 byte)

- **드리프트 우선순위**: #1 — PoC 성공 기준 #1 직접 미충족
- **호출 위치**: graph 에 노드 없음. mapper/atomizer 직후 또는 forecaster 병렬 분기 후보.
- **기대 인터페이스**:
  ```python
  async def generate_report(mapped: list[Activity], parsed_report: ParsedDailyReport, cfg) -> str:
      """통합 Daily Report (markdown) + PG daily_reports INSERT."""
  ```
- **다음 단계**:
  - Azure gpt-5.1 호출 (Mapper 확정 JSON → 통합 Daily Report)
  - 사내 + 발주처용 2종 또는 1종 통합
  - PG `daily_reports` 또는 `data/output/reports/YYYYMMDD.md`
  - Next.js Dashboard 연동 (B_Track)

### `pipeline/main.py` (0 byte)

- **드리프트 우선순위**: D-7 (defer)
- **기대**: `python -m pipeline.main --input data/input/2025-09-27/` CLI 진입점.
- 통합 cycle (#5 Collector 와 함께) 권고.

### `pipeline/api.py` (0 byte)

- **드리프트 우선순위**: D-7 (defer)
- **기대**: FastAPI `/run`, `/resume`, `/status/{run_id}` 3 엔드포인트 (CLAUDE.md `## 아키텍처` 약속).
- 통합 cycle (#5 Collector 와 함께) 권고.

---

## 6. 이슈 표 (audit drift backlog 5건 + design-intent 발견 8건)

### Audit drift backlog (2026-05-17 — 우선순위순)

| # | 이슈 | 위치 | 영향도 | 다음 cycle | 진입점 (design-intent) |
|---|---|---|---|---|---|
| #1 | Reporter 미구현 | `pipeline/agents/reporter.py` (0 byte) | Critical | brainstorming → spec → plan | (없음 — 신규 카드 필요) |
| #2 | Forecaster assessment "정상" bias | `classify_assessment` + RAG/Plan 임계값 | Critical | debugging (loop first) | [forecaster.classify_assessment](./design-intent/design_intent_forecaster.md#classify_assessment) |
| #3 | synthetic fixture productivity_ratio bug | `generate_fake_daily_report` + `_load_baseline_inputs` | Critical | debugging (산술 trace) | [optimizer.generate_fake_daily_report](./design-intent/design_intent_optimizer.md#generate_fake_daily_report) |
| #4 | HIL 1 (Mapper interrupt) 미구현 | `mapper.requires_review` set 됨, `graph.build_graph` 노드 없음 | Critical | brainstorming → spec → plan | [orchestration.hil_2_node](./design-intent/design_intent_orchestration.md#hil_2_node) 패턴 재사용 |
| #5 | Collector + 파일 드롭 + main.py / api.py | 4 stub | Critical | brainstorming → spec → plan | (없음 — 신규 카드 필요) |

### Design-intent 추가 발견 (Low/Medium)

| # | 발견 | 위치 | 심각도 | 비고 |
|---|---|---|---|---|
| O-1 | `PGClient.fetch_activity` 미사용 의심 | db.py:56 | Low | `grep -rn` 결과 `test_db.py` 만. Mapper 통합 후 dead 가능. |
| O-2 | `mapping_corrections` 테이블 dead schema | infra/postgres/init.sql + db.py 함수 없음 | Medium | drift #4 (HIL 1) 진입 시 INSERT 함수 추가 자연 해소. |
| O-3 | `AtomizerConfig.embedding_dim=1536` 미사용 | atomizer.py:34 | Low | 코드 내 소비처 grep 결과 없음. 향후 Chroma cold start 시 참고용. |
| O-4 | `WAResolution.source="auto_sheet1_text"` 미반환 | mapper.py:74 | Low | GATE 2 활성화 (WA 3단계 LLM 추론) 대기. 의도된 미활성. |
| O-5 | `waiting_hil_1` Literal 값 미사용 | state.py:133 | Low | drift #4 진입 시 활성화. |
| O-6 | checkpoints 테이블 dead (InMemorySaver 사용 중) | checkpointer.py + postgres.md | Medium | Reporter cycle 시 PostgresSaver 전환 (drift #1 cycle 통합). |
| O-7 | synthetic 2 path 통합 미진 | `forecaster/synthetic.py:_main_cli` + `optimizer/synthetic_daily_report.py` | Medium | drift D-2 (audit) 와 동일 — defer. |
| O-8 | synthetic_v2 incident 5종 (병행작업 부재) | `optimizer/synthetic_v2.py:generate_synthetic_v2_group` | Medium | drift D-1 (audit) 와 동일 — defer. |

---

## 7. 파일 구조 + LOC 요약

```
pipeline/                              합계 ~3,981 LOC (테스트 제외)
├── graph.py                  272      [T2: 5 nodes + 2 builders]
├── state.py                  137      [T2: CPIAState TypedDict + 5 schemas]
├── checkpointer.py            18      [T2: build_checkpointer (InMemorySaver)]
├── constants.py                5      [WORK_HOURS_PER_DAY=8]
├── db.py                     309      [T2: 7 PG 함수 (fetch + insert + assert + update)]
├── chroma_client.py           40      [T2: 2 collection getter]
│
├── agents/
│   ├── parser.py             306      [T2: 11 (정규화 + ffill + 4 sheet parser + meta)]
│   ├── mapper.py             393      [T2: 9 (build_input × 3 + resolve_wa + map_activity + _prorate_mh)]
│   ├── atomizer.py           118      [T2: 4 (atomize + _make_doc_id + _build_metadata + Config)]
│   ├── collector.py            0      ⚠ 미구현 (drift #5)
│   ├── reporter.py             0      ⚠ 미구현 (drift #1)
│   │
│   ├── forecaster/
│   │   ├── agent.py          276      [T2: _forecast_one_group + forecast]
│   │   ├── prompt.py         134      [T2: build_llm_user_input]
│   │   ├── classify.py       114      [T2: classify_* 4 함수 + 4 임계값 상수]
│   │   ├── rerank.py          50      [T2: rerank_cases + _normalize_chroma_metadata]
│   │   ├── aggregate.py      119      [T2: aggregate_today + compute_delay + fetch_chroma_actual]
│   │   ├── synthetic.py      189      [T2: generate_synthetic_day]
│   │   ├── constants.py        8
│   │   └── __init__.py         8
│   │
│   └── optimizer/
│       ├── agent.py          156      [T2: optimize + _compute_recovery_distribution]
│       ├── prompt.py         315      [T2: SYSTEM_PROMPT + build_llm_user_input]
│       ├── retrieve.py       161      [T2: _group_baseline + fetch_degradation_cases]
│       ├── synthetic_daily_report.py 482  [T2: generate_fake_daily_report — drift #3]
│       ├── synthetic_v2.py   363      [T2: generate_synthetic_v2_group — drift D-1]
│       └── __init__.py         8
│
├── synthetic/
│   └── generate_history.py            (자료 없음 — 별도 cycle 가능)
│
├── tests/                             합계 ~3,200 LOC (분석 대상 외 — 카운트만)
│   ├── test_parser.py
│   ├── test_mapper_node.py / _golden.py / _helpers.py
│   ├── test_atomizer.py
│   ├── test_chroma_client.py / test_db.py / test_state.py
│   ├── test_graph_e2e.py / _hil2.py
│   ├── test_stubs_e2e.py
│   ├── test_prorate_mh.py / test_load_master.py / test_each_agent.py
│   ├── forecaster/                  9 파일 (~1,470 LOC)
│   └── optimizer/                   6 파일 (~1,500 LOC)
│
├── main.py                     0      ⚠ 미구현 (drift D-7)
└── api.py                      0      ⚠ 미구현 (drift D-7)
```

---

## 8. 다음 작업 권고 (drift backlog 순서)

drift backlog `docs/audit/2026-05-17-cpia-drift-backlog.md` 의 우선순위 그대로:

1. **drift #2 또는 #3 먼저** — audit raw 신뢰성 향상 (다른 cycle 진단 정확도 ↑)
   - #2: `loop first` — fixture 다양성 입력 vs assessment 출력 비교 (debugging skill)
   - #3: 산술 재현 (synthetic_daily_report 와 _load_baseline_inputs)
2. **drift #1 Reporter** — PoC 시연 단독 산출물 (병렬 가능)
3. **drift #4 HIL 1** — 상태 필드 이미 있음, hil_2_node 패턴 재사용
4. **drift #5 Collector + main.py + api.py** — 통합 cycle

`./design-intent/INDEX.md` 의 "audit drift 매핑" 섹션 참조하여 진입.
