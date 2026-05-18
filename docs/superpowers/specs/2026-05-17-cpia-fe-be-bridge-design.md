# CPIA Frontend↔Backend Bridge — Design Spec

> Cycle: 2026-05-17 brainstorming (`superpowers:brainstorming` + `data-contract-mapping` skill 첫 적용)
> Status: design 단계. Implementation plan 은 별 cycle (writing-plans 산출).
> Input: `data-contract/` 6 파일 (INDEX + frontend_catalog + backend_catalog + crosswalk + gaps + _meta).
> Branch: A_Track (FE/BE 동일), git SHA: ac42255.

---

## 1. Context

CPIA 의 web/ (B_Track 산출) 와 pipeline/ (A_Track 산출) 가 각각 별 트랙으로 개발됐다. 본 시점:

- **FE**: Next.js App Router, 8 page, 28 type. 100% mock fixture 로 동작 — `web/app/api/mock/<5종>/route.ts` 가 `data/mock_*.json` 9 파일을 그대로 serve. PostgreSQL / FastAPI 미연결.
- **BE**: LangGraph 7-agent pipeline. 7 사용자 PG 테이블 (105 col) + 4 LangGraph 자동 테이블 (12 col). 시뮬 1 건 e2e 통과 (prod run_id b826e4d9). `pipeline/api.py` = **0 byte** (FastAPI 명세는 CLAUDE.md 에 있지만 실 구현 0).
- **위 cycle 결과물**: `docs/architecture/api-contract.md` (본인이 본 cycle 직전 작성) — Site / ReviewItem / ReportDetail / OptimizerOutput **4 type 만** 매핑. web/lib/types.ts 실 25 type 중 21 type 미정의. **불완전 spec**.

PoC 데모 마감 = 2026-06-05 (목), 2.5 주 남음.

본 cycle 의 정직 목표 = **FE 가 진짜로 쓰는 데이터** 와 **BE 가 진짜로 산출하는 데이터** 를 양쪽 카탈로그로 빌드 → 매핑 + gap 정리 → spec 으로 영속. 다음 cycle 의 writing-plans + implementation 의 input.

## 2. Goal + Non-goal

**Goal (본 cycle)**:
- FE 28 type 전수 + BE 117 column / 75 agent field 전수 카탈로그
- 22 type × ~150 field 의 FE↔BE 매핑 (high/medium/low/TBD confidence)
- gap 3 분류 (FE only / BE only / shape mismatch) + 옵션 + 권고
- 12 결정 사용자 confirm (+ 2 future cycle 위임)
- 매핑 + gap 의 spec 화 — 다음 cycle 진입 input

**Non-goal**:
- FastAPI 실 구현 (다음 cycle)
- Next.js BFF route 실 구현 (다음 cycle)
- fixtures → 실 fetch swap (다음 cycle)
- ProductivityDiagnosis BE adapter (future cycle, BE EWMA 정합 후)
- ChatMessage 실시간 stream (future cycle, 본 cycle 완결 후)

## 3. Architecture (연결 방식)

```
[Browser — 경영진]
       ↓
[Next.js Dashboard]
   8 page × N component
   28 type × ~150 field 소비
       ↓ fetch
[Next.js BFF — web/app/api/<bff>/route.ts]
   • GET /api/sites              ─┐
   • GET /api/sites/summary       │
   • GET /api/agents/status       │
   • GET /api/runs/[id]/...       │── proxy or PG direct
   • GET /api/tasks/daily-runs    │
   • GET /api/dashboard           ─┘
   • POST /api/pipeline/run       ─┐
   • POST /api/hil/resume         ─┘── FastAPI proxy
       ↓ HTTP
[FastAPI — pipeline/api.py]
   • POST /run        (graph.ainvoke 백그라운드, run_id 즉시 반환)
   • POST /resume     (Command(resume=...) 으로 hil_1/2 재개)
   • GET  /status/{run_id}     (pipeline_runs + graph.aget_state)
   • GET  /api/sites             (db.fetch_sites_with_forecasts)
   • GET  /api/sites/summary     (db.fetch_sites_summary)
   • GET  /api/agents/status     (BE hard-code 정적 메타 + active_count)
   • GET  /api/runs/{id}         (pipeline_runs row + state.next)
   • GET  /api/runs/{id}/report  (daily_reports + forecasts + optimizer_advice 합성)
   • GET  /api/runs/{id}/forecasts
   • GET  /api/runs/{id}/optimizer
   • GET  /api/runs/{id}/review  (graph.aget_state → state.mapped 필터)
   • GET  /api/runs/{id}/wbs     (activity_master 트리)
   • GET  /api/tasks/daily-runs  (pipeline_runs 최근 14일)
       ↓ in-process
[LangGraph + AsyncPostgresSaver]
       ↓ 결과 저장
[PostgreSQL — 7 사용자 + 4 LangGraph 자동]
```

**핵심 변경 (drift 해소)** — D-1 + D-2 결정 반영:
- `pipeline/db.py` 에 `update_site_last_run(site_id, run_id)` 신규
- `pipeline/db.py` 에 `update_run_status(run_id, status, current_node, completed_at)` 신규
- `pipeline/graph.py` 의 각 agent node 가 진입/종료 시 `update_run_status` 호출
- reporter → END edge 에 `update_site_last_run` + `update_run_status('completed')` 호출

**API layer 타입 변환** (시뮬 발견 R-2):
- asyncpg 는 PG NUMERIC 을 `decimal.Decimal` 로 반환 — JSON 직렬화 시 string 화됨
- API layer 가 `float()` 변환 후 반환 (FE TS `number` 타입 정합)
- 적용 대상: forecasts.{today_productivity, delay_days, ...}, sites.{plan_progress, actual_progress, hours_saved, fte_saved}, derived (gap_percent, spi, ai_replacement_rate)

**포트** (시뮬 발견 R-1): FastAPI = **8001** (포트 8000 ssh tunnel 점유). `.env.local` 의 `FASTAPI_URL=http://localhost:8001`.

---

## 4. FE↔BE 매핑 (어떤거랑 어떤거 연결할건지)

> 전체 ~150 field 매핑 표는 `data-contract/crosswalk.md` 참조. 본 §은 type 별 핵심만.

### 4.1 Site (Dashboard `/dashboard` Layer 1 카드, 19 field)

| FE field | ← | BE source | 산식 |
|---|---|---|---|
| id, name, location, status | ← | sites.{site_id, name, location, status} | 직접 |
| progress_planned, progress_actual | ← | sites.{plan_progress, actual_progress} | 직접 (rename) |
| gap_percent | ← | derived | `actual - plan` (API layer) |
| spi | ← | derived | `actual / plan` (zero-guard) |
| productivity_today | ← | forecasts.today_productivity | `MAX(... WHERE run_id=sites.last_run_id)` |
| abnormal_trades | ← | forecasts.risk_level | `COUNT(WHERE risk_level<>'정상')` |
| fte_saved, hours_saved, headcount | ← | sites.{fte_saved, hours_saved, headcount} | 직접 (본 cycle 신규 컬럼) |
| total_hours | ← | derived | `headcount * 140` |
| ai_replacement_rate | ← | derived | `hours_saved / total_hours * 100` |
| expected_completion, delay_days | ← | forecasts.{expected_completion, delay_days} | `MAX(...)` |
| recovered_completion | ← | (PoC = expected_completion fallback) | future: optimizer recovery 반영 |
| recovery_days | ← | (PoC = 0 fallback) | future: optimizer.recovery_distribution.p50 |

→ **연결**: `GET /api/sites` (BFF) → FastAPI `GET /api/sites` → `db.fetch_sites_with_forecasts()` (sites + forecasts LATERAL JOIN). last_run_id 가 핵심 — D-1 결정으로 graph END node 가 update.

### 4.2 SitesSummary (Home `/home` NOW strip + Hero, 12 field)

| FE field | ← | BE source | 산식 |
|---|---|---|---|
| today_count | ← | pipeline_runs.atomized_count | `SUM(atomized_count WHERE report_date=CURRENT_DATE)` (D-8 — activity 단위) |
| review_pending | ← | pipeline_runs.status | `COUNT(WHERE status='waiting_hil_1')` |
| abnormal_count | ← | forecasts.risk_level | run 별 SUM |
| last_updated | ← | pipeline_runs.started_at | `MAX(...)::time` |
| total_hours_saved, total_fte_saved, total_headcount | ← | sites.* | `SUM(...)` |
| total_hours, ai_replacement_rate | ← | derived | (위 SUM 결과) |
| yearly_saving | ← | **mock 유지** (D-5) | hard-code |
| total_processed | ← | **mock 유지** (D-5) | hard-code |
| total_hours_saved_cum | ← | **mock 유지** (D-5) | hard-code |

→ **연결**: `GET /api/sites/summary`.

### 4.3 AgentStatus (Home AgentWorkflow, 8 field)

| FE field | ← | BE source |
|---|---|---|
| step, name, korean_name, description, model, group | ← | **BE FastAPI hard-code** (D-9) — 7 agent 정적 메타 단일 source |
| active_count | ← | `COUNT(pipeline_runs WHERE current_node=agent.name AND status NOT IN ('completed','failed'))` |
| state | ← | derived (current_node 와 agent.name 비교 → processing / waiting / idle) |

→ **연결**: `GET /api/agents/status`.

### 4.4 DailyRun (Tasks `/tasks` 좌측, 5 field)

| FE field | ← | BE source |
|---|---|---|
| date | ← | pipeline_runs.report_date |
| total_count | ← | pipeline_runs.atomized_count |
| status | ← | pipeline_runs.status (running / completed / waiting_hil_1→review_pending) |
| has_anomaly | ← | `EXISTS(forecasts WHERE risk_level<>'정상')` |
| bar_value | ← | `atomized_count / target_count` (target_count 미정 — gap §A-1) |

→ **연결**: `GET /api/tasks/daily-runs`.

### 4.5 AgentProgress + ChatMessage (Tasks 중앙/우측)

| Type | 처리 |
|---|---|
| AgentProgress (5 field) | 각 agent 별 `processed` / `total` 산식 (Parser/Mapper/HIL/Atomizer/Forecaster/Reporter/Optimizer 7 산식, gap §A-2). **연결**: `GET /api/runs/{id}/progress` |
| ChatMessage (5 field) | **본 cycle mock 유지** (D-4). future cycle 에 Hybrid (DB derive). |

### 4.6 WBSNode + ReviewItem (Review `/review`)

| Type | 처리 |
|---|---|
| WBSNode (7 field) | activity_master 1059 row 의 l5_disc → l6_main → l7_sub 트리 빌드. review_count 는 state.mapped (checkpoint) 의존. **연결**: `GET /api/runs/{id}/wbs`. 시뮬 발견 R-5: 현 prod 데이터 = 4 trade (설비 479 / 전기 307 / 건축 179 / 소방 94) 만, 토목/구조/통신/기계 0 row. PoC 데모는 4 trade 만 표시. 전 trade 확장은 별 cycle. |
| ReviewItem (10 field) | state.mapped (checkpoint state) → `graph.aget_state()` (D-6). ai_mapped_path = `f"{l5_disc} > {l6_main} > {wa}"` (D-7). status = `requires_review ? 'unconfirmed' : 'confirmed'`. **연결**: `GET /api/runs/{id}/review` |

### 4.7 ReportDaily + ReportKpi + ReportDetail (Reports `/reports`)

| Type | 처리 |
|---|---|
| ReportDaily (5 field) | pipeline_runs + forecasts (worst risk_level / MAX) |
| ReportKpi (8 field) | forecasts + optimizer_advice 합성. productivity_history_diff / recoverable_productivity / target_productivity 는 mock (gap §A) |
| ReportDetail | wrapper. optimizer 는 `OptimizerOutput[]` 로 wide (D-12) |
| SCurvePoint | **plan-only derive** (gap §A-4 옵션 2) — activity_master.plan_*. actual = sites.actual_progress 단일 점. 또는 mock 유지 |
| BarItem (contractor/trade bars) | state.mapped GROUP BY company/l5_disc + forecasts.today_productivity AVG |
| QuadrantPoint | forecasts row 1:1. productivity = today_productivity, impact = derived (mh_gap or plan_mh_sum 기반, 산식 결정 필요) |
| OptimizerOutput | shape adapter (D-10): similar_cases description = conditions+activities, outcome = `D+{recovery_days}` or `미회복`. recommendations text 만 추출 |
| RawDataRow | state.mapped 직접 + equipment 는 EquipmentAllocation join (D-11) |

→ **연결**: `GET /api/runs/{id}/report`.

### 4.8 Dashboard tab + Site detail

| Type | 처리 |
|---|---|
| ImpactSiteDistribution | sites.{site_id,name,hours_saved,fte_saved} 직접 |
| ImpactTrendPoint, MiddleOfficeAutomation | **mock 유지** (historical 미보유 / BE scope 밖) |
| DashboardFixture | `GET /api/dashboard` 가 위 3 + SitesSummary 합성 |

### 4.9 ProductivityDiagnosis (13 field) — 본 cycle scope 밖 (D-3)

- 현재: FE `diagnose()` 가 mulberry32 결정적 mock 산출. `diagnosis-preview` 1 페이지에서만 호출.
- 본 cycle: 연결 안 함. preview 라우트 살려둠. crosswalk §21 의 매핑 후보는 future cycle 의 input.
- Future cycle: BE Forecaster 에 EWMA 로직 정합 → BE adapter (`GET /api/runs/{id}/diagnosis`) 추가.

### 4.10 mock 유지 (BE 연결 안 함)

- SimulationSequence (dead fixture, 호출처 없음)
- DiagnosisInput (preview-only)
- AgentWorkflow.COUNTS (FE 하드코딩)
- NotificationBell.MOCK_NOTIFS (FE 하드코딩)
- UserMenu.USERS (FE 하드코딩)

---

## 5. Gap 분석 (조사 결과)

### 5.A FE 가 쓰는데 BE 에 없음 (또는 산식 미확정)

| FE 필드 | UI 영향 | 결정 |
|---|---|---|
| SitesSummary.yearly_saving / total_processed / total_hours_saved_cum (3) | Home Hero "연간 203억" + OpsKpiCard "누적 1,247건" | **mock 유지** (D-5) |
| AgentProgress.processed/total 7 agent 산식 | Tasks 중앙 패널 진행 bar | 산식 결정 — Parser=parsed count, Mapper=mapped count, ... |
| ChatMessage 5 필드 | Tasks 우측 채팅 패널 (데모 핵심) | **mock 유지** (D-4) + future cycle 연결 |
| SCurvePoint time-series | Reports / Site detail S-Curve 차트 | plan-only derive (activity_master.plan_*) 또는 mock |
| ProductivityDiagnosis 13 field | diagnosis-preview (prod 5 화면 아님) | **본 cycle scope 밖** (D-3), future |
| ReviewItem.alternative_wps | Review 카드 "대안 WP" | 빈 배열 (Phase 2 — Mapper LLM top-3 확장 필요) |
| checkpoint state 읽기 path | ReviewItem / WBSNode.review_count / SitesSummary.review_pending / HIL 2 modal | `graph.aget_state()` (D-6) |
| ai_mapped_path PoC fallback (l7_sub None) | Review 카드 "M15X > 골조 > WP-3-2" | `f"{l5_disc} > {l6_main} > {wa}"` (D-7) |
| recovery_distribution → p25/p50/p75 산식 | ReportKpi.recovery_days, Site.recovery_days | dynamic key (d+1~d+7+not_recovered) 의 percentile (gap §A-9 의 numpy 산식) |
| FE 하드코딩 mock 3 종 (AgentWorkflow.COUNTS / NotificationBell / UserMenu) | Home / 알림 / user menu | **FE mock 유지** (PoC) |

### 5.B BE 에 있는데 FE 안 쓰는 데이터 (소비처 필요한지)

| BE source | 의미 | 본 cycle 처리 |
|---|---|---|
| forecasts 의 잔여 18 컬럼 (today_qty_by_unit / plan_total_qty_by_unit / plan_mh_sum / plan_start / plan_finish / plan_mh_per_day / schedule_state / window_start / window_days / expected_in_window_mh / actual_in_window_mh / mh_gap / reasoning / recovery_likelihood / main_unit / today_conditions / today_assigned_workers / created_at) | Forecaster 내부 계산용 + 일부 reasoning | endpoint 응답에서 drop (5 컬럼만 노출 — today_productivity / risk_level / expected_completion / delay_days / similar_cases). 디버깅용 raw endpoint 필요시 별도 |
| optimizer_advice 의 잔여 5 컬럼 (forecast_assessment / recovery_pattern / company / l6_main / created_at) | derived input 또는 중복 | forecast_assessment 는 OptimizerOutput.details 에 포함, recovery_pattern 은 degradation_cases.recovery 와 중복 → drop |
| daily_reports.report_md (906 chars 3 부 markdown) | 본 cycle FE 노출 X | future 에 markdown viewer 컴포넌트 추가 시 노출 |
| daily_reports.bp_name / history_csv_row | Reporter summary | FE ReportKpi 가 forecasts + optimizer 기반이라 직접 사용 X — 응답에 포함 안 함 |
| mapping_corrections (HIL 1 우회로 본 시뮬 0 row) | BE 자가학습 cycle input | FE 직접 노출 X (ReviewItem 산출은 state.mapped 에서) |
| activity_master 22 컬럼 | WBSNode 트리 + Mapper bp_context input | 직접 endpoint 없음. WBSNode 트리 빌드 시 내부 사용 |
| checkpoints / writes / blobs (LangGraph 자동) | graph state 영속 | FE 직접 SELECT X. `graph.aget_state()` 만 노출 |

→ **소비처 추가 필요 없음** — BE 의 추가 컬럼들은 모두 derived 의 input 또는 디버깅용. 본 cycle 에 FE 가 추가로 노출할 데이터 없음.

### 5.C 양쪽 있는데 shape / 산식 mismatch

| 영역 | FE 기대 | BE 실제 | 해소 |
|---|---|---|---|
| SitesSummary.today_count 단위 | 87 (활동 수) | run 수 또는 활동 수 | activity 단위 — `SUM(atomized_count)` (D-8) |
| AgentStatus 정적 메타 | 7 agent × 6 필드 | DB 안에 없음 | BE FastAPI hard-code 반환 (D-9) |
| ai_mapped_path | "M15X > 골조 > WP-3-2" | activity 의 l7_sub/l7_5_activity always None | `f"{l5_disc} > {l6_main} > {wa}"` (D-7) |
| OptimizerOutput.similar_cases shape | `{date, description, outcome}[]` | `{date, conditions, productivity, assigned_workers, activities, recovery}[]` | API layer adapter (D-10) |
| OptimizerOutput.recommendations shape | `string[]` | `{rank, text}[]` | API layer adapter — text 만 추출 sorted (D-10) |
| RawDataRow.building source | "건물명" | sites.name 또는 sub_work_area (None) | 단일 site = sites.name 직접 |
| RawDataRow.equipment | string (장비명) | state.mapped 에 없음 (Parser EquipmentAllocation 만) | API layer join — company 일치 equipment_big list (D-11) |
| ReportDetail.optimizer | 단일 OptimizerOutput | optimizer_advice N row 가능 | FE type 변경 → `OptimizerOutput[]` (D-12) |

---

## 6. 결정 사항 (12 확정 + 2 future)

본 spec 의 모든 결정은 `data-contract/_meta.json.decisions_resolved` 에 영속. 본 §은 참조 요약.

| # | 결정 |
|---|---|
| D-1 | sites.last_run_id 갱신 = graph END node + `db.update_site_last_run` helper 신규 |
| D-2 | pipeline_runs.status 갱신 = 각 agent node 진입 시 `db.update_run_status` 호출 |
| D-3 | ProductivityDiagnosis = **본 cycle scope 밖** (future cycle, BE EWMA 후 BE adapter) |
| D-4 | ChatMessage = 본 cycle mock 유지 (future cycle, Hybrid DB derive) |
| D-5 | SitesSummary 누적 3 필드 = mock 유지 |
| D-6 | checkpoint state 읽기 = `graph.aget_state({"configurable": {"thread_id": <thread_id>}})`. **thread_id 형식**: FastAPI `/run` = `run_id` 그대로 (uuid str). synthetic 시뮬 = `demo-{run_id}` prefix (현 hard-code 유지, synthetic_daily_report.py:424). |
| D-7 | ai_mapped_path PoC fallback = `f"{l5_disc} > {l6_main} > {wa}"` |
| D-8 | today_count 단위 = activity (`SUM(atomized_count)`) |
| D-9 | AgentStatus 정적 메타 = BE FastAPI hard-code 반환 |
| D-10 | OptimizerOutput shape adapter — similar_cases (conditions+activities, recovery_days), recommendations (text 만 sorted) |
| D-11 | RawDataRow.equipment = API layer 가 EquipmentAllocation join |
| D-12 | ReportDetail.optimizer = `OptimizerOutput[]` (FE type 변경) |
| D-13 | SCurvePoint = plan-only derive (activity_master.plan_* 기반 일자별 계획 누적 %). actual = sites.actual_progress 단일 점. historical 누적은 future cycle |
| D-14 | forecasts 엔드포인트 응답에 `risk_level` 만 노출 (assessment 와 의미 중복 — Forecaster 가 둘 다 채우지만 spec 전반에 `risk_level` 일관 사용). 시뮬 발견: 같은 row 두 값 mismatch ("주의" vs "정상") — Forecaster 코드 정합 별 backlog. |

**Future cycle (본 cycle scope 밖)**:
- D-3 followup: ProductivityDiagnosis BE adapter (BE EWMA 후)
- D-4 followup: ChatMessage Hybrid (본 cycle 완결 후)

---

## 7. 연결 절차 (high-level 6 phase)

> 자세한 task break-down 은 writing-plans skill 산출. 본 §은 phase 골격만.

| Phase | 산출 | 의존 |
|---|---|---|
| 0 | **데이터 backfill** (시뮬 발견 R-3) — 본 cycle 시뮬 1 건 (run_id b826e4d9) 의 site 매핑 UPDATE: `UPDATE sites SET last_run_id='b826e4d9-...' WHERE site_id='m15x-ph3-ibl'`. 안 박으면 D-1 graph END 패치 후에도 historical API 응답에 안 잡힘. | (prod PG 접근) |
| 1 | `pipeline/api.py` FastAPI 기반 + 3 endpoint (`POST /run`, `POST /resume`, `GET /status/{run_id}`) — **포트 8001**. fastapi/uvicorn 이미 import 가능 (시뮬 발견 R-7), pyproject.toml 의 `[project] dependencies` 에 `fastapi>=0.115` + `uvicorn[standard]>=0.32` 명시 추가 (lock 정합) | AsyncPostgresSaver 기존 |
| 2 | `pipeline/db.py` helper 추가 — `update_site_last_run` / `update_run_status` (D-1+D-2), `fetch_sites_with_forecasts` (§4.1 SQL), `fetch_sites_summary` (§4.2), WBSNode 트리 빌드 (§4.6), state.mapped → ReviewItem 변환 (D-6+D-7) | Phase 1 |
| 3 | `pipeline/graph.py` 의 각 agent node 가 `update_run_status` 호출 (D-2), reporter → END edge 에 `update_site_last_run` (D-1) | Phase 2 |
| 4 | FastAPI GET endpoint 10 종 (`/api/sites`, `/api/sites/summary`, `/api/agents/status`, `/api/runs/{id}` + `/report` + `/forecasts` + `/optimizer` + `/review` + `/wbs` = 6, `/api/tasks/daily-runs`, `/api/dashboard`) | Phase 2, 3 |
| 5 | Next.js BFF route 8+ 종 (proxy 또는 PG direct) + `web/lib/api.ts` wrapper + `USE_MOCK` env | Phase 4 |
| 6 | `web/app/(app)/<page>/page.tsx` 의 fetch 경로 `/api/mock/*` → `/api/*` swap + e2e 검증 (페이지 5 종 + 시뮬 1 건) | Phase 5 |

**완료 게이트**: 모든 Phase 1~6 통과 + mock 유지 결정 사항 (D-3 / D-4 / D-5 / FE 하드코딩 3 종) 그대로 동작.

---

## 8. Out of scope

**본 cycle scope 밖 (future cycle)**:
- ProductivityDiagnosis BE adapter
- ChatMessage Hybrid (실시간 DB derive)
- SCurvePoint historical 누적 (daily_reports 30 일+ 운영 후)
- ReviewItem.alternative_wps Phase 2 (Mapper LLM top-3 확장)
- `/diagnosis-preview` 라우트 제거 (D-3 BE adapter 완성 후)
- `mock_simulation.json` shape 정정 또는 삭제
- 진짜 auth (UserMenu / NotificationBell)
- SSE / WebSocket 진행 상태 stream

**영원히 mock 유지 (PoC scope 밖)**:
- MiddleOfficeAutomation (4 row, BE pipeline scope 밖)
- ImpactTrendPoint (월별 cumulative_fte historical 미보유)

---

## 9. 본 cycle 산출

- `data-contract/INDEX.md` — 헤드라인 + 14 결정 + 다음 cycle 위임
- `data-contract/frontend_catalog.md` — FE 카탈로그 432 lines
- `data-contract/backend_catalog.md` — BE 카탈로그 412 lines
- `data-contract/crosswalk.md` — 3 면 매핑 419 lines
- `data-contract/gaps.md` — gap 3 분류 + 옵션 310 lines
- `data-contract/_meta.json` — 결정 영속
- **`data-contract/sim_results.md`** — writing-plans 진입 전 sanity check 시뮬 (7 risk 발견 → spec 반영)
- **`docs/superpowers/specs/2026-05-17-cpia-fe-be-bridge-design.md`** — 본 spec (시뮬 반영 정정)
- (다음 cycle 산출) `docs/superpowers/plans/2026-05-17-cpia-fe-be-bridge-plan.md` — writing-plans 의 task break-down
- (다음 cycle 산출) 실 구현 (FastAPI + BFF + fixtures swap)

---

## 10. 다음 단계

본 spec 사용자 review 후 → `superpowers:writing-plans` skill 진입 → implementation plan 작성 → `superpowers:subagent-driven-development` 또는 수동 실행 → 실 코드 변경.

PoC 마감 = 2026-06-05. 2.5 주 남음. main 머지는 조형준 프로님 (본인 권한 X).
