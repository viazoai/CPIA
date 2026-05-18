# CPIA Frontend↔Backend 연결 — Design Spec

> Cycle: 2026-05-18 brainstorming (`superpowers:brainstorming`)
> Branch: A_Track (web/ + pipeline/ 양쪽 변경)
> Previous spec: `2026-05-17-cpia-fe-be-bridge-design.md` (참고. base 아님 — 작성 시점에 parser/mapper 가 PG 적재 안 하던 상태 가정이라 §4 매핑 표 패턴이 현 상태와 다름)
> Demo 마감: 2026-06-05 (목)

---

## 1. Context

CPIA 의 web/ (FE Next.js 14, 5 page) 와 pipeline/ (BE LangGraph 7-agent) 가 별 트랙 개발됨. 본 시점:

- **FE**: 5 page (home / dashboard / tasks / reports / review / export) — `/api/mock/*` 또는 `loadFixture()` 호출, 100% mock 데이터.
- **BE**: pipeline/api.py 에 FastAPI endpoint 12+ 이미 구현 (`/api/sites`, `/api/dashboard/performance`, `/api/dashboard/impact`, `/api/agents/status`, `/api/tasks`, `/api/sites/{id}/wbs_tree`, `/api/sites/{id}/reports`, `/api/runs/{id}/optimizer` + `/wp_summary` + `/hil_1/resume`). 단 FE 가 호출 안 함.
- **PG 적재 현황** (2026-05-18 cloudflared 5532 확인):
  - 적재 OK: activity_master 3708, sites 7, pipeline_runs 15, parser_reports 6, parser_activities 380, mapper_activities 380, mapped_history 15, forecasts 32, optimizer_advice 1, daily_reports 2, mapping_corrections 40, checkpoints 994
  - 적재 X (마이그 됐으나 row 0): parser_job_allocations, parser_equipment_allocations, parser_worker_outputs, parser_report_meta
  - 부분 적재 (신규 컬럼 NULL): parser_activities + mapper_activities 의 신규 13 컬럼 (zone/bp_code/scope/누적/진척률/잔여/note/work_location_code/wbs_*_name)
  - 미적재 컬럼: sites.last_run_id 전부 NULL → forecasts LATERAL JOIN 안 됨

본 cycle 의 정직 목표 = **FE 5 페이지가 실제로 렌더링하는 UI 요소** 와 **현재 PG 에 적재된 컬럼** 을 한 줄씩 매핑 → 갭 별 처리 정책 결정 → BE 측 신규 적재 작업 + BFF transform 코드 산출.

---

## 2. Goal + Non-goal

**Goal**
- FE 5 페이지 × 핵심 UI 라벨/컴포넌트 별 PG 매핑 표
- PG 측 신규 적재 작업 6 항목 (G2 / G5 / G8 / G19 / G23 / G24)
- Next.js BFF transform 함수 12 산식 (PG SELECT → FE 기대 shape)
- 데모 시연 가능한 e2e 연결 (`/api/mock/*` → real PG)

**Non-goal**
- Exporter 노드의 통합 xlsx 생성 (backlog task #17 — daily_reports.report_md 만 적재 중)
- Merge 노드 (업체별 → 통합 ParsedDailyReport, backlog task #16)
- 업체별 N 파일 collector → parser×N → merge 흐름 (backlog task #18/19)
- sites 의 월별 fte_saved 시계열 마이그 (별 cycle, mock 유지)
- 7 agent message 시계열 적재 테이블 (자연어 derive 로 본 cycle 처리 가능)
- ProductivityDiagnosis 의 BE EWMA 정합 (별 cycle)

---

## 3. 아키텍처 (연결 방식)

```
[Browser]
   ↓
[Next.js page.tsx]            ← FE 컴포넌트 수정 X 제약
   fetch("/api/mock/<name>")    ← URL 그대로 유지
   ↓
[Next.js BFF route]           ← /api/mock/<name>/route.ts 내부를 mock 발생 → PG SELECT + transform 으로 전환
   - 또는 신규 /api/<resource>/route.ts (mock 라우트와 공존)
   - 12 transform 함수 (G1/G4/G6/G10/G11/G12/G15/G17/G18/G20/G21/G22)
   ↓ HTTP
[FastAPI — pipeline/api.py]    ← 12+ endpoint 이미 구현
   ↓ asyncpg
[PostgreSQL]
   - sites / pipeline_runs / parser_* / mapper_* / mapped_history / forecasts / optimizer_advice / daily_reports / mapping_corrections / activity_master
   ↓ AsyncPostgresSaver
[LangGraph 7-agent — pipeline/graph.py]
```

**핵심 제약** (사용자 명시):
- FE UI 코드 수정 X. fetch URL 도 가능한 한 그대로 (`/api/mock/<name>` 유지 — route 내부만 swap).
- 데이터 shape 조정은 BFF transform 레이어에서만 (FE 기대 type 맞춤).
- PG 신규 적재 항목은 BE node 코드 + 마이그로 처리.

---

## 4. Anchor = 현재 PG 적재 스키마

bridge spec (2026-05-17) 작성 시점엔 parser/mapper 가 LangGraph 자체 PG (PostgresSaver checkpoints) 에만 적재했고, 명시 테이블 (parser_*, mapper_*) 은 없었다. 그래서 §4 매핑 표가 "FastAPI 가 graph state 에서 끌어다 응답" 패턴 가정. 현재는 mapper_activities 380 row / parser_activities 380 row / forecasts 32 row 등 명시 테이블에 적재 중이라 **PG 직접 SELECT 가 가능** — 패턴이 다름.

본 cycle 의 anchor = **현재 PG 19 테이블 + 적재된 컬럼들**. FE 가 "위로 끌어올라가는" 매핑.

핵심 테이블 발췌:

| 테이블 | 핵심 컬럼 | 의미 |
|---|---|---|
| sites | site_id, name, plan_progress, actual_progress, status, **last_run_id (NULL)**, headcount, hours_saved, fte_saved | 현장 마스터. last_run_id 가 forecasts/optimizer 와 LATERAL JOIN 의 anchor |
| pipeline_runs | run_id, site_id, report_date, status, current_node, started_at, completed_at, **atomized_count (0)** | run 이력. status / current_node 로 progress 도출 |
| activity_master | wbs_activity_id, l5_disc, l6_main, l7_5_activity, sub_work_area, company, unit, plan_total_qty, plan_mh_rev2, plan_start/finish, wa, site_id | WBS 마스터 (3708 row, m15x-ph3-ibl) |
| parser_reports | run_id, report_date, project, **bp_summaries** jsonb, **job_allocations** jsonb, **equipment_allocations** jsonb, activity_count | 통합 작업일보 시트 1/2/3 + activity_count 요약 |
| parser_activities | run_id, idx, l5_disc, trade, company, unit, today_qty, work_content, plan_total_qty, **+ 신규 13 컬럼 NULL** | 시트 4 물량. 신규 13 컬럼 (zone, bp_code, scope, yesterday_cum_qty, today_cum_qty, progress_percent, remaining_qty, remaining_percent, note, work_location_code, wbs_mid_name, wbs_sub_name, wbs_detail_name) 미적재 |
| mapper_activities | run_id, idx, company, trade, today_qty, wa, l6_main, mapping_conf, mapping_source, requires_review, assigned_workers, worker_source, plan_total_qty, plan_mh, conditions, **+ 동일 신규 13 컬럼 NULL** | parser_activities + WBS 매핑 enrich. requires_review = HIL 1 대상 |
| mapped_history | run_id, report_date, site_id, wa, l6_main, company, today_qty, today_assigned_workers, unit, trade | 일자별 매핑 결과 누적 (시계열 derive 의 base) |
| forecasts | run_id, company, l6_main, today_qty_by_unit jsonb, today_assigned_workers, plan_total_qty_by_unit jsonb, plan_mh_sum, similar_cases jsonb, assessment, reasoning, expected_completion, delay_days, risk_level, today_productivity, schedule_state, mh_gap, recovery_likelihood, wa | 공종별 생산성 진단 |
| optimizer_advice | run_id, l6_main, company, diagnosis, recovery_pattern jsonb, recommendations jsonb, forecast_assessment, degradation_cases jsonb, recovery_distribution jsonb | 4분면 고위험군 회복 조언 |
| daily_reports | run_id, report_date, bp_name, **report_md** text, history_csv_row jsonb | Exporter 마크다운 (xlsx 미구현) |
| mapping_corrections | run_id, report_date, original jsonb, corrected jsonb | HIL 1 결과 |
| parser_job_allocations | run_id, idx, bp_code, company, disc_abbrev, manager_code, worker_code, job_type, workers_yesterday_cum jsonb, workers_today_incr jsonb, workers_today_cum jsonb, final_flag, workers_cum_t | **시트 2 직종별 인원 (row 0)** |
| parser_equipment_allocations | run_id, idx, bp_code, company, disc_abbrev, equipment_big, equipment_mid, equipment_spec, count_yesterday_cum jsonb, count_today_incr jsonb, count_today_cum jsonb, final_flag, count_cum_t | **시트 3 장비 (row 0)** |
| parser_worker_outputs | (업체별 시트 6) | 통합 작업일보엔 시트 6 없음. 업체별 흐름 (Phase 2 backlog) 에서 적재 |
| parser_report_meta | (업체별 Cover) | 동일. 업체별 흐름에서 |

---

## 5. 페이지별 매핑

### 5.1 home

페이지 = StatusHeader + Ops KPI 4 카드 가로 + AgentWorkflow (col 1~8) + AgentChatLog (col 9~12 sticky).

| UI 라벨 (위치) | FE field | PG 어디서 + 자연어 |
|---|---|---|
| 마지막 갱신 시각 (StatusHeader) | summary.last_updated | `MAX(pipeline_runs.started_at)::time` |
| 누적 처리 (KPI 1, 건) — "시스템 런칭 이후" | summary.total_processed | `SUM(pipeline_runs.atomized_count)` — **G5 적재 의존** |
| 오늘 처리 (KPI 2, 건) — "자정 이후 입수 일보" | summary.today_count | `SUM(atomized_count WHERE report_date=CURRENT_DATE)` — G5 의존 |
| 누적 절감 (KPI 3, h) — "2,506h → 351h 월평균" | summary.total_hours_saved_cum | `sites.hours_saved_cum` — **G2 적재** |
| 현재 처리 중 (KPI 4, 건, live) — "7 Agent active 합산" | `sum(agents.active_count)` | pipeline/api.py:706 `/api/agents/status` 가 이미 산출 |
| 7 agent 카드 (정적 메타 + active_count + state) | agents[] | 동일 `/api/agents/status` 가 정적 메타 + active_count 반환. state 는 derive |
| Agent Chat Log (시계열 자연어 발화) | chat[] | **G4 자연어 템플릿 derive** — agent 별 PG 통계 → 1줄 summary + 보충 detail |

### 5.2 dashboard

탭 2 = Performance + Impact.

**Performance**:
| UI 라벨 (단위) | PG 어디서 + 자연어 |
|---|---|
| 전사 평균 생산성 (%) — "이력 대비 평균" | `AVG(forecasts.today_productivity)` (WHERE run_id IN sites.last_run_id) — **G8 의존** |
| 평균 공기 격차 (일) — "전사 평균 지연" | `AVG(forecasts.delay_days)` — G8 의존 |
| 이상 공종 총합 (건) — "전사 합계" | `COUNT(forecasts WHERE risk_level IN ('이상','주의'))` — G8 의존 |
| 회복 가능 공기 (일) — "Optimizer 평균" | `optimizer_advice.recovery_distribution` jsonb → p50 평균 |
| 전사 생산성 시계열 (mean/min/max, 가능한 한 30일) | **G6 derive** — `mapped_history` 는 productivity 컬럼이 없고 `today_qty` 만 갖고 있어서 `mapper_activities` 와 `(run_id, wa, l6_main, company)` LEFT JOIN 후 `today_qty / NULLIF(plan_mh, 0)` 계산. 일별 GROUP BY (`report_date`) 로 site 마다 daily productivity → mean/min/max 산출. **현재 mapped_history 15 row / 1 site / 2025-09 인근 집중이라 30일 분포는 sparse 가능 — fallback: forecasts.similar_cases jsonb 의 productivity 평균** |
| 현장 카드 grid (sites[]) | sites + forecasts LATERAL JOIN — G8 의존 |
| 카드 sparkline | G6 와 동일 |

**Impact (scope=fleet)**:
| UI 라벨 | PG 어디서 + 자연어 |
|---|---|
| 전체 근무량 (명) — "{total_hours} h/월" | `SUM(sites.headcount)`, 서브 = `total * 140` derive |
| 월 절감 시간 (h) — "Agent 자동화 효과" | `SUM(sites.hours_saved)` — 월간. G2 도 동일 산식 (cum 만 분리) |
| FTE 환산 (명) — "140h/명 기준" | `SUM(sites.fte_saved)` |
| AI 업무 대체율 (%) — "절감 ÷ 전체 근무시간" | derive: `total_hours_saved / total_hours * 100` |
| 연간 환산 효과 strip — "{yearly_saving}억 ({fte}명 × 1.5억 + 직접 시간 환산)" | **G1 derive 산식** — `total_fte_saved * 1.5 + total_hours_saved * 시급 / 1e8`. 상수: 1.5억/FTE, 시급 (e.g. 5만원/h) — 환경변수 |
| 현장별 절감 분포 가로 바 | sites.{site_id, name, hours_saved, fte_saved} 직매핑 |
| 월별 누적 FTE 라인 차트 | **mock 유지 (별 cycle 마이그)** |

### 5.3 tasks

페이지 = 3 컬럼 (좌측 일자 리스트 / 중앙 7+1 agent 단계 / 우측 sample item 12 건). 윈도우 **1년** (사용자 결정 — PoC 데이터 2025-09 라 30일 윈도우 밖).

**좌측 DailyTaskList**:
| UI 요소 | PG 매핑 |
|---|---|
| 일자 행 | `pipeline_runs.report_date` DISTINCT, `>= CURRENT_DATE - INTERVAL '1 year'` |
| 총 작업일보 건수 | `COUNT(DISTINCT (company, report_date) FROM parser_activities)` — BP사 수 기반 |
| 전체 진행률 (0~100) | **G12** — status/current_node → 매핑: completed=100 / optimizer=90 / forecaster=80 / exporter=70 / atomizer=60 / waiting_hil_1=50 / mapper=30 / parser=20 |
| 상태 칩 (running/review_pending/completed) | `pipeline_runs.status` 직매핑. waiting_hil_1 → "review_pending" 라벨 변환 |
| 이상 인디케이터 | `EXISTS(forecasts WHERE risk_level<>'정상' AND run_id 그 일자)` |

**중앙 AgentWorkflowList** (G10 단계별 산식):
| Agent | received | processed |
|---|---|---|
| Collector | 입력 파일 수 (디렉토리 walk) | `COUNT(parser_reports WHERE report_date)` |
| Parser | Collector processed | `COUNT(parser_activities)` |
| Mapper | Parser processed | `COUNT(mapper_activities)` |
| HIL Review | `SUM(mapper_activities.requires_review=true)` | `COUNT(mapping_corrections WHERE report_date)` |
| Atomizer | `COUNT(mapper_activities WHERE not requires_review AND run_id 그 일자)` — HIL 1 통과 row 수 | `pipeline_runs.atomized_count` 값 SELECT — **G5 가 이 컬럼을 UPDATE 하므로 적재 의존** |
| Exporter | Atomizer processed | `COUNT(daily_reports)` |
| Forecaster | `COUNT(DISTINCT (company, l6_main))` | `COUNT(forecasts)` |
| Optimizer | `COUNT(forecasts WHERE risk_level<>'정상')` | `COUNT(optimizer_advice)` |

**우측 AgentTaskItemList**:
| UI 요소 | PG 매핑 |
|---|---|
| 행 ID ("RPT-YYYYMMDD-NNN") | `RPT-<date>-<idx 0pad 3>`. idx = mapper_activities.idx |
| 공종 라벨 | **G15** — `mapper_activities.l6_main` 그대로. mock 의 "철근공사/거푸집공사" 세분화 안 함 |
| BP사 | `mapper_activities.company` 직매핑 |
| 처리 상태 (done/processing/received/hil_pending/blocked) | **G11** agent별 derive: Mapper=requires_review→hil_pending, mapping_conf≥0.7→done. HIL=mapping_corrections 존재→done. Atomizer 이후=atomized_count>0→done. blocked=risk_level='이상' |

### 5.4 reports

페이지 = 좌측 일자 리스트 + § 01 생산성 (트렌드 + BP사/공종 바) + § 02 산점도/WP 테이블/Optimizer + § 03 공정률 추세.

**좌측 ReportDailyList**:
- date / status / productivity_today / delay_days / recovery_days — pipeline_runs + forecasts + optimizer_advice 직매핑/derive

**§ 01 ProductivityTrendChart + Bar Toggle + KPI 8 field**:
- 트렌드: **G6** 일별 시계열
- contractor_bars / trade_bars: `forecasts.today_productivity` GROUP BY company / l6_main + baseline (**G21**)
- KPI 8 field: forecasts + mapped_history + optimizer_advice 조합 derive

**§ 02 4분면 + WP 테이블 + Optimizer**:
| UI 요소 | PG 매핑 |
|---|---|
| WP 식별자 / 이름 | **G17** — wp_id = `<wa>-<l6_main 짧은>`, wp_name = `<wa> <l6_main>` |
| productivity | `forecasts.today_productivity` (해당 wp 단위) |
| impact | **G18** — `mapper_activities.plan_total_qty * activity_master.plan_mh_rev2 / 정규화상수` |
| quadrant (risk/caution/watch/safe) | derive: productivity × impact 임계 |
| size (잔여 물량 비례) | `mapper_activities.remaining_qty` — **G19 적재 의존** |
| WP 테이블 progress_pct / start/end_date / baseline | mapper_activities.progress_percent (G19) + activity_master.plan_start/finish + G21 |
| Optimizer 결과 (diagnosis/similar_cases/recommendations/details) | optimizer_advice 컬럼 직매핑 |

**§ 03 ForecastChart (S 커브 4 라인)**:
- **G20** — `s_curve_derive(site_id, end_date, wp_id)` BFF 함수. planned=activity_master.plan_start~finish 일별 보간, actual=mapped_history.today_qty 누적, forecast=forecasts.today_productivity 외삽, recovery=optimizer_advice 시나리오

### 5.5 review

페이지 = 좌측 WBS 트리 + 우측 ReviewCard 리스트 + 드래그앤드롭 재매핑. HIL 1 UI.

| UI 요소 | PG 매핑 |
|---|---|
| WBS 트리 4 레벨 | **G22** — `wbs_tree_build(site_id)` BFF: site → wa → l5_disc → l6_main GROUP BY. 노드별 review_count=SUM(mapper_activities.requires_review), status=worst(forecasts.risk_level) |
| 카드 id | mapper_activities.id |
| BP사 / 작업내용 / 물량+단위 / 확신도 | mapper_activities.company + parser_activities.work_content + today_qty/unit + mapping_conf |
| 매핑 결과 wp_id / path | **G17 공유** + 트리 경로 텍스트 join |
| 확정 상태 (confirmed/unconfirmed) | mapper_activities.requires_review → 반전 |
| 대안 WP 후보 + score | **G23** — `mapper_activities.alternatives` jsonb 신규 마이그 + mapper_node 가 RAG top-K (K=3) + score 적재 |
| 확정 버튼 / 일괄 확정 / 드래그앤드롭 | `POST /api/runs/{run_id}/hil_1/resume` (pipeline/api.py:200 이미 구현) — BFF proxy |

### 5.6 export

페이지 = 좌측 일자 리스트 + 우측 ConsolidatedReportCard (4 시트 탭). 윈도우 **1년**.

| 시트 | PG 어디서 |
|---|---|
| 1. 출력인원 (BP사 × zone × scope × 작업 × 시간대) | `parser_reports.bp_summaries` jsonb 펼치기 — 모든 컬럼 포함 |
| 2. 직종별 인원 (12 컬럼) | **G24a** — parser_job_allocations (현재 row 0) 적재 코드 추가 |
| 3. 장비 (12 컬럼) | **G24b** — parser_equipment_allocations (현재 row 0) 적재 코드 추가 |
| 4. 물량 (total_a / prev_cum_b / today_c 등) | parser_activities + 신규 13 컬럼 — **G19 공유** |
| 통합 xlsx 다운로드 버튼 | **별 cycle backlog** (task #17 — Exporter 노드). 본 cycle UI = "준비 중" 토스트 또는 시트 raw csv fallback |

---

## 6. PG 측 신규 적재 작업

| ID | 작업 | 어디 노드 + 파일 | 영향 페이지 |
|---|---|---|---|
| **G2** | `sites.hours_saved_cum` (NUMERIC, 단위 = **시간 h**) 컬럼 마이그 + 적재. 산식 = `((AS_IS_MIN - TO_BE_MIN) / 60.0) × atomized_count`. 상수: AS_IS_MIN=120 (일보당 사람 수작업 분), TO_BE_MIN=5 (일보당 AI 처리 분). 분→시간 환산을 `/60.0` 명시. atomized_count 가 G5 로 적재된 이후 reporter→END edge 가 계산해 누적 UPDATE. | `infra/postgres/migrations/2026-05-19_sites_hours_saved_cum.sql` + `pipeline/graph.py` reporter→END edge `update_site_hours_saved_cum()` | home, dashboard |
| **G5** | atomizer 가 그 run 에서 ChromaDB `daily_activities` 에 적재한 row 개수를 `pipeline_runs.atomized_count` 에 `UPDATE` (적재 작업 자체. derive 산식 아님). | `pipeline/agents/atomizer.py` 끝부분 또는 `pipeline/graph.py` atomizer_node 가 `UPDATE pipeline_runs SET atomized_count = <적재 row 수> WHERE run_id = ...` 호출 | home, tasks |
| **G8** | `sites.last_run_id` 갱신 | reporter→END edge `UPDATE sites SET last_run_id=run_id WHERE site_id=state.site_id` | home, dashboard |
| **G19** | parser/mapper INSERT 시 신규 13 컬럼 매핑. `parser_llm.py` LLM 출력 스키마는 `db.py` INSERT 컬럼명과 이미 일치 — 함수 본문에 컬럼 자리만 추가하면 됨. 두 INSERT 함수 모두 `pipeline/graph.py` 의 **mapper_node** (parser_node 가 아님) 에서 호출되는 점 주의 | `pipeline/db.py` 의 `insert_parser_activities_batch()` + `insert_mapper_activities_batch()` 본문 + (참고) graph.py mapper_node 호출부 | reports, export |
| **G23** | `mapper_activities.alternatives` jsonb 마이그 + 적재 | `infra/postgres/migrations/2026-05-19_mapper_alternatives.sql` + `pipeline/agents/mapper.py` 가 RAG top-K (K=3) + score 를 jsonb 으로 적재 | review |
| **G24** | parser_node 가 db.py 신규 INSERT 호출 (job_allocations / equipment_allocations) | `pipeline/graph.py` parser_node 가 `insert_parser_job_allocations_batch(run_id, parsed.job_allocations)` + `insert_parser_equipment_allocations_batch(run_id, parsed.equipment_allocations)` 호출 | export |

---

## 7. BFF transform 함수 (PG 마이그 X, 코드만)

`web/lib/transforms.ts` (또는 각 mock route 안 inline). 12 함수.

| ID | 함수 | 입력 | 출력 (FE type) |
|---|---|---|---|
| G1 | `derive_yearly_saving(total_fte_saved, total_hours_saved, hourly_rate)` | sites SUM | number (억) — `fte * 1.5 + hours * rate / 1e8` |
| G4 | `derive_chat_sequence(run_id)` | pipeline_runs + parser/mapper/forecasts/optimizer 통계 | ChatMessage[] — 7~8 발화 (agent 별 1 줄 summary + detail). 템플릿 7개 |
| G6 | `derive_productivity_timeseries(site_id, days=30)` | `mapped_history` LEFT JOIN `mapper_activities` ON `(run_id, wa, l6_main, company)` → `today_qty / NULLIF(plan_mh, 0)` 일별 GROUP BY. sparse 시 forecasts.similar_cases fallback | FleetTrendPoint[] (date, mean, min, max) + site_sparklines |
| G10 | `derive_stage_progress(date)` | pipeline_runs + 다음 8 테이블 카운트: parser_reports, parser_activities, mapper_activities, mapping_corrections, pipeline_runs.atomized_count (G5 적재값), daily_reports, forecasts, optimizer_advice. 각 stage 의 received/processed 산식은 §5.3 표 참고 | AgentStageProgress[] × 8 stage |
| G11 | `derive_item_status(activity_row, stage)` | mapper_activities row + stage | "done"/"processing"/"received"/"hil_pending"/"blocked" |
| G12 | `derive_progress_percent(status, current_node)` | pipeline_runs row | 0~100 |
| G15 | (산식 X — `mapper_activities.l6_main` 직사용) | l6_main 문자열 | UI trade 라벨 |
| G17 | `derive_wp_id_and_path(wa, l6_main, site_name)` | mapper_activities + sites | wp_id + wp_name + path text |
| G18 | `derive_impact(plan_total_qty, plan_mh)` | mapper_activities + activity_master | 0~100 |
| G20 | `derive_s_curve(site_id, end_date, wp_id)` | activity_master + mapped_history + forecasts + optimizer_advice | SCurvePoint[] (planned/actual/forecast/recovery) |
| G21 | `derive_baseline(company, l6_main)` | mapped_history GROUP BY + forecasts.similar_cases fallback | number |
| G22 | `wbs_tree_build(site_id)` | activity_master + mapper_activities + forecasts | WBSNode (트리, 4 레벨) |

---

## 8. Mock 유지 / 별 cycle backlog

| ID | 항목 | 이유 |
|---|---|---|
| G7 | dashboard impact 의 월별 누적 FTE 시계열 (ImpactTrendPoint[]) | sites.fte_saved 시점값만. 월별 시계열 마이그는 별 cycle. mock 으로 PoC 시각화 충분 |
| backlog F | export 페이지의 통합 xlsx 다운로드 | task #17 — Exporter 노드 backlog. 현재는 daily_reports.report_md 마크다운만 |
| backlog E | Merge 노드 (업체별 N → 통합 ParsedDailyReport) | task #16 backlog |
| backlog G | collector→parser×N→merge→...→exporter 풀 흐름 graph 배선 | task #18 backlog |
| backlog H | 업체별 sample N → 통합 풀 graph 검증 | task #19 backlog |
| ProductivityDiagnosis | reports 페이지의 진단 컴포넌트 (현재 FE 클라이언트 산출) | BE EWMA 정합 별 cycle |

---

## 9. 결정 사항 (브레인스토밍 합의)

| # | 결정 | 영향 |
|---|---|---|
| D-1 | Anchor = 현재 PG 적재 스키마. bridge spec §4 매핑 표는 base 아님 (참고만) | 본 spec 의 §4~§5 |
| D-2 | swap 패턴 = mock route 내부를 PG SELECT + transform 으로 전환. FE 컴포넌트 + fetch URL 수정 X | §3 아키텍처 |
| D-3 | 페이지 단위 매핑 (5 페이지 × 컴포넌트). UI 라벨 기준, 영문 field 만으로 표 만들지 않음 | §5 페이지별 매핑 |
| D-4 | G2 (hours_saved_cum) — sites 마이그 + 적재 코드. mock fallback X | §6 G2 |
| D-5 | G5 (atomized_count) — atomizer_node 적재. KPI "누적 처리" 의 anchor | §6 G5 |
| D-6 | G4 (chat_sequence) — 자연어 템플릿 derive. 별 cycle 위임 안 함 | §7 G4 |
| D-7 | tasks / reports / export 일자 윈도우 = **1년**. PoC 데이터는 2025-09 인근에 집중 적재되어 있어 1년 윈도우 켜도 일자 분포 sparse 가능 — 일자 리스트는 `report_date DESC` 정렬 + 데이터 있는 일자만 표시 | §5.3 / §5.4 / §5.6 |
| D-8 | tasks 의 trade 라벨 = `mapper_activities.l6_main` 그대로 사용. mock 의 15종 세분화 폐기 | §5.3 G15 |
| D-9 | reports/review 의 wp_id = `<wa>-<l6_main>` derive. PG 마이그 X | §5.4 / §5.5 G17 |
| D-10 | review 의 alternative_wps = mapper_activities.alternatives jsonb 마이그 + mapper_node 적재 | §6 G23 |
| D-11 | export 의 통합 xlsx 다운로드 = 본 cycle backlog (task #17). UI 버튼은 "준비 중" 토스트 | §8 backlog F |
| D-12 | dashboard 의 monthly_trend (월별 FTE 시계열) = mock 유지. 별 cycle 마이그 | §8 G7 |
| D-13 | yearly_saving = derive 산식 (`fte * 1.5 + hours * 시급 / 1e8`). 상수 환경변수 | §7 G1 |

---

## 10. 연결 절차 (high-level Phase 골격)

> 자세한 task break-down 은 writing-plans skill 산출.

| Phase | 산출 | 의존 |
|---|---|---|
| 1 | PG 마이그레이션 2종 (G2 sites.hours_saved_cum, G23 mapper_activities.alternatives) | — |
| 2 | BE 노드 코드 수정 — G2/G5/G8 (atomizer + reporter→END edge), G19 (db.py INSERT 컬럼 확장), G23 (mapper RAG top-K 적재), G24 (parser → job/equipment INSERT 호출) | Phase 1 |
| 3 | BE 1cycle prod 호출로 적재 검증 (통합일보 1파일 + 3사 필터). 신규 컬럼/테이블 row count > 0 확인 | Phase 2 |
| 4 | BFF transform 함수 12종 (`web/lib/transforms.ts`) | Phase 3 (실 PG 데이터 확인 후) |
| 5 | mock route 5종 내부 swap (`/api/mock/dashboard`, `/agent-tasks`, `/report`, `/review`, `/consolidated`) — mock 발생 코드 제거 + transform 함수 호출. home 의 `loadFixture()` 호출도 동일 패턴 | Phase 4 |
| 6 | e2e 검증 — 5 페이지 브라우저 + Playwright 시나리오. 데모 시연 리허설 | Phase 5 |

**완료 게이트**: 5 페이지가 mock 없이 PG 데이터로 정상 렌더 + 시연 가능 + Phase 6 e2e 통과.

---

## 11. 참고

- Previous spec (참고만): `docs/superpowers/specs/2026-05-17-cpia-fe-be-bridge-design.md`
- 본 cycle 의 brainstorming 대화 = git 이력 (본 commit 직전 메시지)
- PG anchor 검증 스크립트: `/tmp/cpia_pg_dump.py` (cloudflared 5532 직접 SELECT)
