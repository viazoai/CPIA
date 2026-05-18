# CPIA FE↔BE Gaps

> 생성: 2026-05-17. Input = `crosswalk.md` (TBD / low confidence row 추출) + `backend_catalog.md` (BE 만 있는 source 찾기) + 양쪽 shape mismatch.
>
> 각 gap = 옵션 2~3 개 + 본인 권고. 사용자 결정 게이트는 본 파일 끝 §D.

---

## §A. FE only — UI 가 쓰는데 BE source 없음 (또는 산식/source 미확정)

### A-1. SitesSummary 누적 3 필드 (`yearly_saving` / `total_processed` / `total_hours_saved_cum`)

| 필드 | UI 영향 | 옵션 |
|---|---|---|
| yearly_saving | Home Hero "연간 환산 203 억" | (1) hard-code (PoC mock) (2) `SUM(sites.hours_saved) * 12 * 단가` — 단가 결정 필요 (3) 신규 컬럼 |
| total_processed | OpsKpiCard "누적 처리 1,247건" | (1) hard-code (2) `SELECT COUNT(*) FROM pipeline_runs` (3) 신규 카운터 테이블 |
| total_hours_saved_cum | OpsKpiCard "누적 절감 12,840h" | (1) hard-code (2) `SUM(hours_saved) * months_since_launch` (3) historical aggregate |

**권고**: (1) 모두 mock 유지 — PoC 데모 마감 (6/5) 까지 단가/카운터 산식 정하는 비용이 효익 < 데모 영향. mock 값을 .env 또는 sites_summary 별 컬럼으로 두고 운영자가 수동 갱신.

### A-2. AgentProgress.processed / total 산식 (7 agent × 2 = 14 산식)

각 agent 별 progress 산식 정의 필요:
- Parser: `processed = parsed Activity 누적`, `total = parsed count`
- Mapper: `processed = mapped count`, `total = parsed count`
- HIL Review: `processed = state.mapped WHERE !requires_review`, `total = state.mapped 전체`
- Atomizer: `processed = atomized_ids 누적`, `total = mapped count`
- Forecaster: `processed = forecasts row count`, `total = group count (state.mapped GROUP BY company,l6_main)`
- Optimizer: `processed = optimizer_advice count`, `total = hil_2_selection length`
- Reporter: `processed = 0 또는 1`, `total = 1`

**권고**: 위 산식 채택. 단 state.mapped 의 group count / requires_review count 는 checkpoint state 읽기 path 필요 (gap §A-7 와 묶음).

### A-3. ChatMessage 5 필드 — log stream source 부재

UI 영향: Tasks 페이지 우측 채팅 패널 (현재 mock_chat_sequence.json 으로만 굴러감). 데모의 핵심 narrative.

옵션:
- **(1) FE mock 유지** — `mock_chat_sequence.json` 그대로, 데모 단순. 단점: 실 pipeline 흐름과 무관.
- **(2) BE log emit path 신설** — 각 agent 가 logger.info() 박을 때 별도 event_log 테이블 / Redis stream / SSE 로 emit. FastAPI 가 폴링 또는 stream. 비용: 각 agent 코드 + 신규 endpoint + FE polling 또는 SSE.
- **(3) Hybrid** — pipeline_runs.current_node 변경 + forecasts/optimizer_advice INSERT 시 BE 가 정형 ChatMessage 1 줄 합성 (DB INSERT trigger 또는 API layer derive). 비용 중간.

**권고**: (1) PoC 마감 (6/5) 까지 mock 유지. 데모 시 운영자가 실 pipeline 진행에 맞춰 mock_chat_sequence 수동 갱신 또는 1 회 시연용 시나리오 고정. 추후 (옵션 2/3) phase 2.

### A-4. SCurvePoint time-series — BE 에 time-series 없음

UI 영향: Reports `/reports` + Site detail `/dashboard/sites/[id]` 의 S-Curve 차트. ForecastTab + Performance 탭 핵심.

옵션:
- **(1) FE mock 유지** — `mock_report.json` 의 s_curve 그대로. PoC 단순.
- **(2) plan-only derive** — activity_master.{plan_start, plan_finish, plan_total_qty} 기반 일자별 계획 누적 % 만 계산. actual/forecast/recovery 는 null 또는 sites.actual_progress 단일 점.
- **(3) historical accum** — daily_reports row 누적으로 actual 계산, forecasts row 의 expected_completion 으로 forecast 곡선. 비용 큼 (BE 산식 추가 + 매일 일자별 누적 컬럼).

**권고**: (2) plan-only derive — activity_master 의 plan 데이터로 계획 곡선 1 개만 그리고 actual = 단일 점 (sites.actual_progress). 데모에서 충분히 정보 전달.

### A-5. ProductivityDiagnosis 13 필드 — 사용자 명시 결정

**사용자 요청**: "옵티마이저와 포어케스터와 연결해야된다".

옵션 (다시 정리, catalog 기반):
- **(1) FE mock 유지 (diagnosis.ts)** — 현재 prod 5 화면에서 호출 X (preview 라우트만). preview 제거 후 dead.
- **(2) BE adapter — forecaster + optimizer 변환 (권고)** — API layer 가 `forecasts.{rag_n_similar, today_productivity, similar_cases, risk_level, ...} + optimizer_advice.{recovery_distribution} + sites.actual_progress` 를 ProductivityDiagnosis shape 으로 변환. history_std / s_curve / band / scenarios 등 BE 미산출 필드는 API layer 산식 (similar_cases STDDEV, plan-only s_curve, FE diagnosis.ts:115~141 산식 그대로 server-side 이식).
- **(3) 신규 agent (Diagnosis agent)** — pipeline/agents/diagnosis.py 신설. 산식이 forecaster + optimizer 의 출력의 후가공이라 사실상 adapter 와 동일하지만 별 단계로 영속.

**권고**: (2) BE adapter — FE diagnose() 산식 (diagnosis.ts:89-162) 을 API layer 에 그대로 이식. history_std = STDDEV(forecasts.similar_cases[].productivity), s_curve = (A-4 옵션 2 결과 재사용), recovery 부분은 optimizer_advice.recovery_distribution 의 d+N 분포에서 p25/p50/p75 산출. 비용: API layer Python 함수 1 개 (~150 lines, FE 의 mulberry32 부분만 제외하고 결정적 산식 그대로). FE diagnosis.ts 는 fallback 으로 유지하되 prod 호출 X.

### A-6. ReviewItem.alternative_wps — 본 PoC 빈 배열

대안 WP suggestion 은 Phase 2 — Mapper LLM 이 top-3 후보 + score 반환하도록 확장 필요. 본 cycle scope 밖, FE 가 빈 배열 받음.

**권고**: 빈 배열 fallback 유지.

### A-7. checkpoint state 읽기 path — state.mapped / state.hil_1_corrections / state.pre_optimizer_cases

ReviewItem (§8) + SitesSummary.review_pending (§2) + AgentProgress.total (§5) + HIL 2 modal 데이터가 모두 LangGraph checkpoint state 의존. 현재 BE 에 checkpoint state 를 외부에서 읽는 path 없음.

옵션:
- **(1) FastAPI 가 checkpoints 테이블 직접 SELECT 후 deserialize** — LangGraph 의 PostgresSaver 직렬화 포맷 따라야 함 (msgpack 또는 pickle, langgraph 의 serializer 사용). 비용 중간.
- **(2) graph 종료 시 state snapshot 을 별 테이블 (또는 pipeline_runs.state_snapshot JSONB) INSERT** — checkpoint 자체와 별개로 FE 가 읽기 쉬운 정형 데이터 1 row.
- **(3) FE 호출 시 langgraph API 통해 graph state get** — langgraph 의 `graph.aget_state(config)` 호출.

**권고**: (3) FastAPI 가 `graph.aget_state(thread_id=run_id)` 호출 후 state attr (mapped / hil_1_corrections / pre_optimizer_cases) 추출. langgraph 의 공식 API 라 가장 안전. 비용 작음.

### A-8. ai_mapped_path PoC fallback — l7_sub/l7_5_activity always None

PoC 단계 Activity 의 l7_sub / l7_5_activity 가 항상 None (state.py:22~48 docstring). FE 의 path string "M15X > 골조 > WP-3-2 거푸집" 같이 4 깊이 표시.

옵션:
- **(1) `f"{l5_disc} > {l6_main}"` 만 (PoC fallback)** — 2 깊이만 표시. UI 가 약간 빈약.
- **(2) `f"{l5_disc} > {l6_main} > {wa}"`** — wa 코드를 leaf 로 (UI 의 WP-3-2 자리). 3 깊이.

**권고**: (2) — wa 코드가 PoC 단계 실 leaf 역할.

### A-9. recovery_distribution → recovery.p25/p50/p75 산출

optimizer_advice.recovery_distribution 의 key set 은 dynamic (`d+1`~`d+7` + `not_recovered`). 산식 결정 필요.

산식 (권고):
```python
# distribution = {"d+1": 2, "d+5": 1, "d+6": 1, "not_recovered": 1}
days_list = []
for k, v in distribution.items():
    if k == "not_recovered":
        days_list.extend([999] * v)  # 또는 NaN 처리
    else:
        days_list.extend([int(k.replace("d+", ""))] * v)
# numpy.percentile 25/50/75
p25 = np.percentile(days_list, 25)
p50 = np.percentile(days_list, 50)  # median
p75 = np.percentile(days_list, 75)
# not_recovered 가 50%+ 면 p50/p75 = Infinity
```

**권고**: 위 산식 채택. not_recovered 는 999 또는 별도 sentinel.

---

## §B. BE only — DB / agent 산출인데 FE 가 안 씀

### B-1. forecasts 의 잔여 18 컬럼 (today_qty_by_unit / plan_total_qty_by_unit / plan_mh_sum / plan_start / plan_finish / plan_mh_per_day / schedule_state / window_start / window_days / expected_in_window_mh / actual_in_window_mh / mh_gap / reasoning / recovery_likelihood / main_unit / today_conditions / today_assigned_workers / created_at)

FE 가 사용하는 forecasts 컬럼은 5 개 (today_productivity / risk_level / expected_completion / delay_days / similar_cases) 뿐. 나머지 18 컬럼은 FE 가 노출 X.

옵션:
- (1) endpoint 응답에서 모두 drop (band-width 절약)
- (2) `/api/runs/:id/forecasts/raw` endpoint 로 raw row 통째 노출 (디버깅용)

**권고**: (1) 5 컬럼만 노출. raw 는 별 endpoint 필요시.

### B-2. optimizer_advice 의 잔여 5 컬럼 (forecast_assessment / recovery_pattern / company / l6_main / created_at)

FE OptimizerOutput 은 5 field 만 — wp_id / diagnosis / similar_cases / recommendations / details. 일부 BE 컬럼은 derived 의 input 으로만 사용.

**권고**: forecast_assessment 는 details 에 포함, recovery_pattern 은 degradation_cases.recovery 와 중복 → drop.

### B-3. daily_reports.{bp_name, report_md, history_csv_row}

FE ReportDetail.kpi (위 §10) 는 forecasts + optimizer_advice 기반. daily_reports 의 report_md (906 chars 3 부 markdown) 와 history_csv_row (summary dict) 는 FE 가 직접 사용 X.

옵션:
- (1) FE 에 신규 컴포넌트 (markdown viewer) 추가해서 report_md 노출
- (2) daily_reports endpoint 자체를 만들지 않음 (BE only)

**권고**: (2) — 본 cycle scope 밖. 추후 "원본 보고서 보기" 버튼 추가 시 (1).

### B-4. mapping_corrections row — HIL 1 우회로 0 row

현재 prod 시뮬 1 건 (run_id b826e4d9) mapping_corrections = 0 row. HIL 1 우회 시뮬이라 INSERT 안 됨. FE 가 mapping_corrections 자체를 직접 SELECT 할 일 없음 (ReviewItem 산출은 state.mapped 에서).

**권고**: BE 자가학습 cycle 의 input 만, FE 노출 X.

### B-5. activity_master 22 컬럼

WBSNode 트리 빌드 + Mapper bp_context 의 input. FE 가 직접 노출 X (트리 빌드 결과만 노출).

**권고**: 직접 endpoint 없음. WBSNode 트리 산출 시 내부 사용.

### B-6. checkpoints / checkpoint_writes / checkpoint_blobs (LangGraph 자동)

FE 가 직접 SELECT X. graph.aget_state() 만 노출.

---

## §C. Mismatch — 양쪽 다 있는데 shape/산식 다름

### C-1. SitesSummary.today_count 단위 (run 인지 activity 인지)

FE mock: `today_count: 87` (Home NOW strip "오늘 처리 87건").

BE 는 pipeline_runs row N 개 (각 row 가 1 일 1 site 1 run) + 각 run 의 mapped Activity 수 (수십~수백). 의미가 다름.

옵션:
- **(1) run 단위 — `COUNT(pipeline_runs WHERE report_date=CURRENT_DATE)`** — 보통 site 수 (6 이내). "오늘 처리 87건" 과 안 맞음.
- **(2) activity 단위 — `SUM(pipeline_runs.atomized_count WHERE report_date=CURRENT_DATE)`** — 87 등 큰 숫자 매칭.

**권고**: (2) activity 단위. mock 값 87 과 매칭됨.

### C-2. AgentStatus 정적 메타 (step/name/korean_name/description/model/group) — 어디서 채울지

7 agent × 6 정적 field = 42 cell.

옵션:
- (1) BE FastAPI 가 hard-code 반환 (`/api/agents/status` 가 메타+active_count 합쳐 반환)
- (2) FE 가 hard-code (`web/lib/agent-meta.ts` 같은 정적 파일), BE 는 active_count 만 반환
- (3) DB 신규 테이블 `agent_meta`

**권고**: (1) BE 가 hard-code 반환 — 단일 source of truth, FE 변경 0. 비용 작음.

### C-3. ai_mapped_path PoC fallback — 위 §A-8 와 동일 결정.

### C-4. OptimizerOutput.similar_cases shape adapter

FE shape: `{ date: string; description: string; outcome: string }[]`.

BE shape (optimizer_advice.degradation_cases[]): `{ date, conditions, productivity, assigned_workers, activities, recovery }`.

매핑 산식 권고:
- date → date 직접
- description → `f"{conditions} — {activities[0] if activities else '활동 X'}"` (활동 N 개면 first + " 외 N건")
- outcome → `recovery.recovery_days` 있으면 `f"D+{recovery_days} 회복"`, 없으면 "미회복"

### C-5. OptimizerOutput.recommendations shape adapter

FE shape: `string[]`.

BE shape: `{ rank: int, text: string }[]`.

옵션:
- (1) `text` 만 추출 (rank 순서대로 정렬 후 string array)
- (2) `f"[{rank}] {text}"` 포맷
- (3) FE type 변경 (`{rank,text}[]` 로 wide)

**권고**: (1) — FE 변경 0. rank 는 어차피 1~4 순서.

### C-6. RawDataRow.building source

FE 의 building = "건물명" (사용자 도메인). BE 에는 building 직접 컬럼 없음. activity_master.sub_work_area (PoC None) 또는 sites.name 사용 가능.

**권고**: 단일 site run 의 경우 `sites.name` 직접 (예: "M15X Ph-3 IBL"). 추후 multi-building 지원 시 activity_master.sub_work_area 채움.

### C-7. RawDataRow.equipment

state.mapped 에 equipment 없음. Parser EquipmentAllocation 이 별도 state.parsed["equipment_allocations"] 에 있음 (company 별 list).

옵션:
- (1) BE 가 mapped Activity 에 equipment lookup 후 join (company 일치하는 equipment_big list 를 comma-join string 으로)
- (2) FE 가 별 endpoint 호출 (company → equipment_big[] map)

**권고**: (1) API layer 가 한 endpoint 응답에서 join.

### C-8. ReportDetail.optimizer — 1 row 만 노출 vs 전체 list

run 안에 N 개 optimizer_advice 가능 (hil_2_selection 의 selection 수만큼). FE OptimizerOutput 은 단일 obj.

옵션:
- (1) 첫 row 만 노출 (`ORDER BY id DESC LIMIT 1` 또는 첫 selection)
- (2) FE type 변경 (`optimizer: OptimizerOutput[]`)
- (3) endpoint 가 1 row 만 (default) + `?all=true` 로 전체

**권고**: (2) FE type 변경 — multi optimizer_advice 자연 노출. 현 OptimizeTab UI 가 quadrant 클릭 시 1 개 표시인데 advice 가 N 개면 tab 추가하면 됨.

---

## §D. 사용자 결정 게이트 (본 cycle 진행을 위해 결정 필요)

본 gaps 의 12 결정 사항을 5 핵심 + 7 본인 권고 confirm 로 정리.

### D-1. **sites.last_run_id 갱신 path** (drift, 모든 Site/forecasts aggregate 의존)

옵션:
- (1) graph END 노드에서 `UPDATE sites SET last_run_id=run_id WHERE site_id=...`
- (2) Reporter 가 daily_reports INSERT 시 같이 UPDATE
- (3) FastAPI /run 완료 시 (graph 종료 감지) UPDATE

### D-2. **pipeline_runs.status 갱신 path** (drift, DailyRun.status + AgentProgress.waiting_hil 의존)

옵션:
- (1) 각 graph node 진입 시 db.py 의 신규 `update_run_status(run_id, status)` helper 호출 (running → waiting_hil_1 → ... → completed)
- (2) FastAPI 가 polling 으로 graph state 검사 후 status 갱신 (graph.aget_state().next 가 hil_1_node 면 waiting_hil_1)
- (3) LangGraph 의 stream 모드로 node 진입/종료 이벤트 hook + status 갱신

### D-3. **ProductivityDiagnosis** 처리 (사용자 명시 결정 영역)

옵션:
- (1) FE mock 유지 (diagnose() 자체 계산, prod 호출 X — preview 라우트만)
- (2) BE adapter (forecaster + optimizer 변환, FE diagnose 산식을 server-side 이식, 권고)
- (3) BE 신규 agent

### D-4. **ChatMessage source** (Tasks 페이지 chat 패널)

옵션:
- (1) FE mock 유지 (PoC 데모 시 운영자 수동 갱신, 권고)
- (2) BE log emit + FastAPI stream
- (3) Hybrid (DB INSERT trigger 기반 derive)

### D-5. **SitesSummary 누적 3 필드** (yearly_saving / total_processed / total_hours_saved_cum)

옵션:
- (1) 전부 hard-code mock (권고)
- (2) 산식/카운터 신설 (단가, COUNT)
- (3) historical 누적 컬럼

---

### D-6 ~ D-12 본인 권고 confirm only (queue 로 묶음)

각 결정의 권고만 확인하고 별 옵션 표는 §A/B/C 참조.

| # | 결정 | 본인 권고 |
|---|---|---|
| D-6 | A-7 checkpoint state 읽기 path | `graph.aget_state(thread_id=run_id)` 사용 |
| D-7 | A-8 / C-3 ai_mapped_path PoC fallback | `f"{l5_disc} > {l6_main} > {wa}"` (wa 를 leaf) |
| D-8 | C-1 today_count 단위 | activity 단위 — `SUM(atomized_count)` |
| D-9 | C-2 AgentStatus 정적 메타 source | BE FastAPI hard-code 반환 (단일 source) |
| D-10 | C-4 / C-5 OptimizerOutput shape adapter | similar_cases: `desc=conditions+activities`, `outcome=recovery_days`; recommendations: text 만 추출 |
| D-11 | C-7 RawDataRow.equipment | API layer 가 EquipmentAllocation join |
| D-12 | C-8 ReportDetail.optimizer N row | FE type 을 `OptimizerOutput[]` 로 wide |

---

## §E. mock 유지 권고 (BE 신규 산식/source 안 만듦)

| 영역 | 사유 |
|---|---|
| MiddleOfficeAutomation (4 row) | Middle Office 자동화율은 BE pipeline scope 밖 — 정적 메타 |
| ImpactTrendPoint (월별 cumulative_fte) | historical 누적 데이터 미보유, mock 유지 |
| FE 하드코딩 mock 3 종 (AgentWorkflow.COUNTS / NotificationBell / UserMenu) | PoC 단순성, 실 auth/notification 시스템 도입 X |
| SimulationSequence dead fixture | 호출처 없음, 본 cycle scope 제외 |
| DiagnosisInput preview-only | preview 라우트 제거 후 dead |
| daily_reports.report_md (906 chars markdown) | 본 cycle 에 FE 노출 X, 추후 markdown viewer 컴포넌트 추가 시 노출 |

---

## §F. 2026-05-18 갱신 — PR #19/#20/#22 흡수 + 10 gap 결정

> 본 §F = 카탈로그 시점 (ac42255, 2026-05-17) 이후 변경 흡수 + 사용자 결정 9 건.
>
> 사용자 의도: "FE 기획 source of truth / FE 시각화 X / 억지 매핑 금지 — 공식 일원화 / 시연 안 보고 연결 우선 / 자연어 설명".

### §F.1 PR #19/#20/#22 변경 흡수

| PR | 변경 | 카탈로그 영향 |
|---|---|---|
| #19 | HIL 1 + Forecaster fix + Reporter + PostgresSaver 통합 | backend_catalog: Reporter agent (161 lines 신규) + checkpointer.py _LazyAsyncPostgresSaver + db.py helper 2 (insert_mapping_correction / insert_daily_report) |
| #20 | /reports Tabs 폐지 + 6 섹션 단일 흐름 (진단 모델 통합) | frontend_catalog § C-4 갱신 — ForecastTab / OptimizeTab 삭제 |
| #22 | /reports 6 → 5 섹션 인과 흐름 | frontend_catalog § C-4 갱신 — ForecastChart / ProductivityBarToggle / WPSummaryTable 3 신규 component. types.ts +9 신규 type (WPSummaryRow + ProductivityDiagnosis 13 field set + DailyTask + AgentStageProgress + AgentTaskItem) |

### §F.2 10 Gap 표 (페이지 / UI / FE 현재 / BE 연결 / 결정)

| # | 페이지 | UI 표시 | FE 현재 | BE 연결 방향 | 결정 brain slug |
|---|---|---|---|---|---|
| **G-1** | /reports § 3·5 | WPSummaryTable — WP 단위 표 (9 field × N row) | mock 6 row | BE 가 활동 마스터 + mapped_history join 산출. wp_id = `f"{wa}-{l6_main}-{company}"` triplet | [[decisions/cpia-wpsummary-grain-2026-05-18]] + [[cpia-wpsummary-progress-path-2026-05-18]] + [[cpia-wpsummary-wpid-formula-2026-05-18]] |
| **G-2** | /tasks | 좌측 일자 리스트 + 중앙 8 단계 워크플로 + 우측 N 건 목록 | mock route 178 lines deterministic generator (mulberry32 PRNG) | DailyTask + AgentStageProgress 둘 다 BE 산출 (mapped_history + LangGraph state). AgentTaskItem.status 5 치 = BE 산출 (FE 시각화 그대로) | [[cpia-tasks-page-be-formulas-2026-05-18]] + [[cpia-tasks-item-status-2026-05-18]] |
| **G-3** | /review | 좌측 펼침 트리 (현장 → 공종 → 작업 패키지) | 정적 mock 3000 줄 JSON | BE 가 활동 마스터에서 트리 derive + 노드별 review_count 카운트 | [[cpia-six-gaps-decisions-2026-05-18]] |
| **G-4** | /reports 좌측 | 일자별 행 30 일치 (날짜 + 상태 + 생산성 + 지연) | 30 일치 mock 행 | BE 가 그 현장의 cycle 별 일자 집계 (`pipeline_runs JOIN forecasts GROUP BY date`) | [[cpia-six-gaps-decisions-2026-05-18]] |
| **G-5** | /dashboard Performance | 상단 KPI 4 카드 (평균 생산성 / 평균 지연 / 이상 공종 총합 / 회복 가능 일수) | 정적 4 숫자 | BE 가 전 현장 평균/합계 (AVG / SUM) | [[cpia-six-gaps-decisions-2026-05-18]] |
| **G-6** | /dashboard Impact | 현장 별 절감 시간 + 확보 FTE 막대/표 | 정적 분포 mock | BE 가 sites.{hours_saved, fte_saved} 컬럼 직접 — 매우 단순 | [[cpia-six-gaps-decisions-2026-05-18]] |
| **G-7** | /home | 7-Agent 카드의 "지금 처리 중 N 건" + 상태 (처리중/대기/유휴) | 정적 값 박힘 | BE 가 현재 그 agent 단계에 있는 cycle 카운트 산출 (running 상태 cycle 의 current_node 기반) | [[cpia-six-gaps-decisions-2026-05-18]] |
| **G-8** | /reports § 3 | OptimizerResult 4 섹션 (진단/유사 사례/권고/상세) | mock 단일 OptimizerOutput 객체 — D-12 결정 (배열) 미반영 | BE 배열 응답 + FE OptimizerOutput[] 수신. PG row grain 그대로 흐름 | [[cpia-optimizer-array-grain-2026-05-18]] |
| **G-9** | /reports § 4 | ForecastChart S 자 곡선 4 가지 (계획/실적/예측/회복) | mock + FE adapter mock 산식 | 계획 = 활동 마스터 plan_mh 누적, 실적 = mapped_history 누적, 예측/회복 = FE mock 영구 (D-3 EWMA 드랍). **BE 가공 산식 정의 다음 cycle 보류** | [[cpia-six-gaps-decisions-2026-05-18]] (G-9 부분) |
| **G-10** | /review confirm 액션 | "확정" 버튼 / 드래그앤드롭 / "모두 AI 추천대로 확정" 버튼 | local state 만 갱신, API call X | api-contract.md §3.8 명세 그대로 + FE 가 corrections 객체 변환 산식 추가 (~30 lines). BE FastAPI 구현 0 → 신규 | [[cpia-hil1-resume-connection-2026-05-18]] |

### §F.3 TBD (BE 협의 사항)

| TBD | 위치 | 사용자 의도 | 결정 시점 |
|---|---|---|---|
| `AgentTaskItem.status` 의 `processing` 정의 | /tasks 우측 표 | mock = 단계의 첫 미처리 row 1 개. BE 는 LangGraph batch 라 단일 row 특정 X | BE 구현 cycle Phase 0 |
| `AgentTaskItem.status` 의 `blocked` 정의 | /tasks 우측 표 | mock = 6% random. BE 는 LangGraph 자체에 1 activity error 추적 X | BE 구현 cycle Phase 0 |
| `s_curve` 계획 곡선 MH 누적 산식 | /reports § 4 | "계획은 masterlist와 매핑시켜서 mh기준" | BE 구현 cycle Phase 0 |
| `s_curve` 실적 곡선 MH 환산 산식 | /reports § 4 | "actual이 현재 작업일보 매핑된거 기반" | BE 구현 cycle Phase 0 |
| `s_curve` 회복 곡선 가공 산식 | /reports § 4 | "만회나 그런것들은 forecaster 받아야돼" | BE 구현 cycle Phase 0 |
| `mapping_corrections` schema 정합 (drift #N2) | /review confirm | 실 schema 가 spec 과 다름 — work_content/company/trade/correction_type 본문 안에 박힘 | 다음 cycle |

### §F.4 추가 발견 — Forecaster 1 row 원인 trace

본 cycle 의 prod 데이터 검증 시 발견:

- **forecasts 테이블 단 1 row** (prod m15x-ph3-ibl, run b826e4d9)
- Forecaster agent 코드 (`forecaster/agent.py:229~277`) 는 정상 — 모든 group 마다 INSERT 함
- **진짜 원인**: prod 에 graph 성공한 cycle 단 1 회 (b826e4d9, atomized_count=5). 나머지 5 run 모두 mapper 에서 멈춤 (colima Chroma 다운 / cloudflared SSL).
- 그 1 cycle 의 input = 소량 활동 → group_by → 1 group (남웅건설 + 철근콘크리트공사) 만.
- → schema/agent 코드 변경 불필요. **진짜 시연 blocker = graph 새 run 안정성** (ChromaClient 재사용 patch + colima 안정성).

### §F.5 본 cycle 산출 = 카탈로그 + 결정

- INDEX.md / _meta.json / gaps.md §F 갱신 완료 (2026-05-18)
- frontend_catalog / backend_catalog / crosswalk 갱신 = 본 cycle 후속 (~290 line incremental, 다음 step)
- 9 brain decisions + 2 feedback memory 저장 완료
- BE 구현 cycle plan (writing-plans 형식) = 본 cycle 종료 후 작성

---

## §G. 2026-05-19 — tasks scope G-2 정합 검증 cycle

본 cycle 의 사용자 의도: "main pull 최신 FE 기반으로 data contract 업데이트. tasks 부터." 본인 stash 의 `data-contract/db-runtime-catalog.md` (stale FE 기반 진단) 는 보존 + 새 데이터 = A_Track `/api/tasks` (api.py:1022, Phase 4 11/11 GREEN) vs G-2 카탈로그 결정 정합 검증.

### §G.1 검증 결과 — 6 mismatch + 2 정합 + 카탈로그 모르는 사실

| 필드 | 카탈로그 (crosswalk §F.4-F.6) | A_Track 실 구현 | 정합 |
|---|---|---|---|
| `DailyTask.date` | `pipeline_runs.report_date` | 동일 | ✓ |
| `DailyTask.total_count` | `COUNT(DISTINCT (wa,l6_main,company)) FROM mapped_history` | `COUNT(*) FROM pipeline_runs` (= 보통 1) | ❌ 의미 다름 |
| `DailyTask.progress_percent` | current_node × 12.5% | 동일 (AVG 추가) | ✓ |
| `DailyTask.status` | waiting_hil_1 → review_pending | failed → review_pending (HIL 누락) | ❌ enum 매핑 오 |
| `DailyTask.has_anomaly` | EXISTS forecasts risk_level<>정상 | 동일 | ✓ |
| `AgentStageProgress.received/processed` | LangGraph state checkpoint 단계별 array size | 모든 stage = total_count binary 추산 | ❌ source 다름 |
| `AgentStageProgress.percent` | processed/received × 100 | binary 0/100 | ❌ |
| `AgentStageProgress.waiting_hil` | status='waiting_hil_1' AND is_hil | False 하드코드 | ❌ |
| `AgentTaskItem.id` | `RPT-{date}-{idx:03d}` | 동일 | ✓ |
| `AgentTaskItem.trade` | state.mapped[i].trade (한글 공종) | mapped_history.l6_main (WBS 매핑 후) | ❌ 의미 위반 |
| `AgentTaskItem.contractor` | state.mapped[i].company | mapped_history.company | ✓ |
| `AgentTaskItem.status` | BE 가 3 치 (done/received/hil_pending) state binary + 2 치 BE 협의 | run 단위 status 를 row 단위에 박음 + 모든 row 가 Collector key | ❌ 분배 로직 부재 |

### §G.2 본 cycle 3 신규 결정

| # | 결정 | 사유 | brain slug |
|---|---|---|---|
| **D-15** | **AgentStageProgress.received/processed source = 옵션 Y (PG row count)** | ① stash 의 parser_reports/parser_activities/mapper_activities 3 테이블 신설로 옵션 Y 인프라 마련. ② BI / 대시보드 친화적 (외부 SELECT 가능). ③ FastAPI 구현 간단 (checkpoint state query 까다로움 회피). G-2 의 옵션 X → Y evolve | [[decisions/cpia-tasks-stage-source-y-2026-05-19]] |
| **D-16** | **mapped_history.trade 컬럼 신설** | AgentTaskItem.trade FE 의도 = 한글 공종 (예: "철근공사", Activity.trade str). 현 BE 가 mapped_history.l6_main (예: "철근콘크리트공사", WBS 매핑 후 카테고리) 으로 박음 = 사용자 "억지 매핑 금지" feedback 직접 위반. trade 컬럼 추가 + Atomizer INSERT 변경 | [[decisions/cpia-mapped-history-trade-column-2026-05-19]] |
| **D-17** | **pipeline_runs.status / current_node UPDATE path 신설** (D-2 구현) | backend_catalog §A drift 명시: status / current_node UPDATE helper 0 개 (atomizer 만 current_node 박음). progress_percent / waiting_hil / DailyTask.status 의 BE 소스가 다 이 컬럼 의존 → helper 신설 필요 | [[decisions/cpia-run-status-update-path-2026-05-19]] |

### §G.3 BE 구현 cycle backlog (BE-T1 ~ BE-T7)

`crosswalk.md §F.4-§F.6` + `backend_catalog.md §G.3` 에 명시. 7 항목, schema 변경 1 + BE 코드 변경 6.

| ID | 작업 | scope |
|---|---|---|
| BE-T1 | `_TASKS_SQL.total_count` 산식 정정 | api.py:853-887 |
| BE-T2 | `current_node` UPDATE path 신설 | db.py + graph.py 모든 노드 (D-17) |
| BE-T3 | `_TASKS_SQL.status` enum 매핑 fix | api.py:871-875 |
| BE-T4 | `_build_progress_by_date` 옵션 Y SQL 정정 | api.py:922-960 (D-15) |
| BE-T5 | `waiting_hil` hard-code 정정 | api.py:956 |
| BE-T6 | mapped_history.trade migration + atomizer INSERT | `infra/postgres/migrations/2026-05-19_mapped_history_trade.sql` 신규 + atomizer.py:130 (D-16) |
| BE-T7 | `_build_items_by_date` agent 분배 + status 3 치 산출 | api.py:963-1019 |

### §G.4 본 cycle 산출 = 카탈로그 갱신 + 결정 + migration sql

- `crosswalk.md §F.4-§F.6` 갱신 ✓ (옵션 Y / mapped_history.trade / 6 BE-T 명시)
- `backend_catalog.md §G` 신설 ✓ (11 endpoint 인지 / stash 인프라 / 3 결정 / 7 BE-T)
- `gaps.md §G` 신설 (본 섹션)
- `INDEX.md` 헤드라인 + 결정 누계 갱신
- `_meta.json` 갱신
- `infra/postgres/migrations/2026-05-19_mapped_history_trade.sql` 신규 (D-16 의 schema 변경 1)
- 본 cycle 종료 후: 3 brain decision 페이지 + BE 구현 cycle plan (writing-plans 형식)
