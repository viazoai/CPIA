# CPIA FE↔BE Crosswalk

> 생성: 2026-05-17. Input = `frontend_catalog.md` (28 type / ~150 field) + `backend_catalog.md` (105 DB column + 33 JSONB key + 15 state attr + 75 agent field + 14 db.py helper).
>
> 각 FE field 1 row. **Confidence**:
> - **high** = BE source 실재 + 산식 명확
> - **medium** = BE source 또는 산식 1 개 모호 (예: aggregate key 모호, last_run_id 의존 등)
> - **low** = BE source 본 cycle 에 없음 (mock 유지 또는 신규 컬럼/agent 필요)
> - **TBD** = 사용자 결정 보류 (gaps.md 의 옵션 결정 후 확정)

---

## §1. Site (Dashboard `/dashboard`, Site detail `/dashboard/sites/[id]`)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| id | sites.site_id | 직접 (rename id ← site_id) | high | |
| name | sites.name | 직접 | high | |
| location | sites.location | 직접 | high | 본 cycle 신규 컬럼 (migration 2026-05-17_db_alignment.sql:7) |
| status | sites.status | 직접 (CHECK enum 4값 정합) | high | DB CHECK + TS literal 모두 `{normal,caution,risk,unknown}` 일치 |
| progress_planned | sites.plan_progress | 직접 (rename) | high | NUMERIC(5,2) % |
| progress_actual | sites.actual_progress | 직접 (rename) | high | NUMERIC(5,2) % |
| gap_percent | sites.{plan_progress, actual_progress} | `actual_progress - plan_progress` | high | API layer 계산 |
| productivity_today | forecasts.today_productivity | `MAX(... WHERE run_id = sites.last_run_id)` | medium | **sites.last_run_id 갱신 path 없음** (drift §1.A) |
| spi | sites.{plan_progress, actual_progress} | `actual_progress / plan_progress if plan_progress > 0 else null` | high | zero-guard 명시 |
| abnormal_trades | forecasts.risk_level | `COUNT(forecasts WHERE risk_level <> '정상' AND run_id = sites.last_run_id)` | medium | last_run_id 의존 |
| fte_saved | sites.fte_saved | 직접 | high | 본 cycle 신규 컬럼 |
| hours_saved | sites.hours_saved | 직접 | high | 본 cycle 신규 컬럼 |
| headcount | sites.headcount | 직접 | high | 본 cycle 신규 컬럼 |
| total_hours | sites.headcount | `headcount * 140` | high | 140 = 월 가동 hours (magic, API layer 상수) |
| ai_replacement_rate | sites.{hours_saved, headcount} | `hours_saved / (headcount * 140) * 100 if headcount > 0 else 0` | high | zero-guard |
| expected_completion | forecasts.expected_completion | `MAX(... WHERE run_id = sites.last_run_id)` | medium | last_run_id 의존 |
| recovered_completion | (PoC: = expected_completion) | PoC fallback, Phase 2 = optimizer recovery 반영 | low | gap §A — 산식 미확정 |
| delay_days | forecasts.delay_days | `MAX(... WHERE run_id = sites.last_run_id)` | medium | last_run_id 의존 |
| recovery_days | (PoC: 0) | PoC fallback, Phase 2 = optimizer.recovery_distribution.p50 | low | gap §A — 산식 미확정 |

**Site 통계**: high 11 / medium 5 / low 2 / TBD 0 = 18 (recovered_completion 제외 19 - 1)

---

## §2. SitesSummary (Home `/home` NOW strip + Hero)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| today_count | pipeline_runs.report_date | `COUNT(pipeline_runs WHERE report_date = CURRENT_DATE)` | medium | 단순 COUNT, but "오늘 처리 87건" 의 단위가 run 인지 activity 인지 결정 필요 (gap §C-1) |
| review_pending | mapping_corrections OR state.mapped | `COUNT(state.mapped WHERE requires_review=true)` — state attr 이므로 checkpoints 에서 추출 필요 | low | 별 path 필요 (checkpoint state 읽기 — pipeline_runs WHERE status='waiting_hil_1' COUNT 로 fallback?) |
| abnormal_count | forecasts.risk_level | `SUM(forecasts WHERE risk_level <> '정상' GROUP BY run_id)` 의 sum | medium | run_id 결정 (last per site) 후 sum |
| last_updated | pipeline_runs.started_at | `MAX(pipeline_runs.started_at)::time` (HH:MM 포맷) | high | |
| total_hours_saved | sites.hours_saved | `SUM(sites.hours_saved)` (월간) | high | |
| total_fte_saved | sites.fte_saved | `SUM(sites.fte_saved)` | high | |
| total_headcount | sites.headcount | `SUM(sites.headcount)` | high | |
| total_hours | sites.headcount | `SUM(sites.headcount) * 140` | high | |
| ai_replacement_rate | sites.{hours_saved, headcount} | `SUM(hours_saved) / (SUM(headcount) * 140) * 100` | high | fleet level |
| yearly_saving | (BE source 없음) | `SUM(hours_saved) * 12 * 단가` — 단가 미정 | low | gap §A — 단가 결정 필요 (PoC mock 유지 또는 hard-code 단가) |
| total_processed | (BE source 없음) | 런칭 이후 누적 — pipeline_runs 전체 COUNT 또는 historical 누적 카운터 신설 | low | gap §A — 산식/source 미확정 |
| total_hours_saved_cum | (BE source 없음) | 런칭 이후 누적 시간 — historical aggregate 신설 | low | gap §A — 산식/source 미확정 |

**SitesSummary 통계**: high 6 / medium 2 / low 4 = 12

---

## §3. AgentStatus (Home `/home` AgentWorkflow)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| step | (정적) | 1~7, hard-code | high | 메타데이터 |
| name | (정적) | "Collector"..."Optimizer", hard-code | high | |
| korean_name | (정적) | "수집"..."최적화", hard-code | high | |
| description | (정적) | "작업일보 자동 수집" 등, hard-code | high | |
| model | (정적) | "규칙 기반" / "gpt-5.1" / "임베딩" — 정적 매핑 | high | CLAUDE.md "Agent 역할 요약" 표 인용 |
| group | (정적) | "collect" (step 1~5) / "analyze" (step 6~7) | high | |
| active_count | pipeline_runs.current_node + forecasts/optimizer row count | `COUNT(pipeline_runs WHERE current_node = agent.name AND status NOT IN ('completed','failed'))` 또는 polling 으로 진행 중 run 카운트 | medium | current_node 갱신 path 미존재 drift (atomizer 만 갱신) — gap §B |
| state | derived | `current_node` 와 agent.name 비교 → processing / waiting / idle | medium | 위 drift 와 동일 |

**AgentStatus 통계**: high 6 / medium 2 = 8

→ **AgentStatus 는 BE 7 agent 정적 메타 + active_count/state 만 동적**. 정적 부분은 BE FastAPI 가 hard-code 반환 또는 FE 가 직접 hard-code. **결정 필요 (gap §C-2)**.

---

## §4. DailyRun (Tasks `/tasks`)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| date | pipeline_runs.report_date | 직접 | high | |
| total_count | state.mapped 또는 pipeline_runs.atomized_count | `pipeline_runs.atomized_count` (atomized doc 수, run 별 1 row) | high | |
| status | pipeline_runs.status | 직접 매핑 (running / completed / waiting_hil_1 → review_pending) | medium | status 갱신 path drift (gap §B) — `completed_at IS NULL AND status='running'` → 'running', `completed_at IS NOT NULL` → 'completed', `status='waiting_hil_1'` → 'review_pending' |
| has_anomaly | forecasts.risk_level | `EXISTS(forecasts WHERE risk_level <> '정상' AND run_id = pipeline_runs.run_id)` | high | |
| bar_value | (없음) | `atomized_count / target_count` — target_count 미정 | low | gap §A — 의미상 진행률 0~1, 산식 결정 필요 |

**DailyRun 통계**: high 3 / medium 1 / low 1 = 5

---

## §5. AgentProgress (Tasks `/tasks` 중앙 패널)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| agent | (정적 enum 8 종) | "Collector" / "Parser" / ... / "HIL Review" / "Optimizer" | high | type 상 string 인데 실값 닫힘 |
| unit | (정적) | per_report (Parser/Mapper) / per_review (HIL Review) / per_run (Reporter/Forecaster/Optimizer) | high | |
| processed | pipeline_runs.current_node + (atomized_count, mapped count, forecast count, etc.) | agent 별로 다른 source — Parser 는 parsed Activity count, Mapper 는 mapped count, Atomizer 는 atomized_count, Forecaster 는 forecasts row count, Reporter 는 1 (있/없), Optimizer 는 optimizer_advice count | medium | agent 별 매핑 산식 7 종 결정 필요 (gap §A-2) |
| total | (없음) | 예상 총 (agent 별 target) — Parser/Mapper 는 parsed count, Atomizer 는 mapped count, Forecaster 는 group count, Reporter 는 1, Optimizer 는 hil_2_selection length | medium | 위와 동일 |
| waiting_hil | pipeline_runs.status | `status IN ('waiting_hil_1','waiting_hil_2')` AND agent IN ('Mapper','HIL Review','Forecaster','Optimizer') | medium | status 갱신 drift |

**AgentProgress 통계**: high 2 / medium 3 = 5

---

## §6. ChatMessage (Tasks `/tasks` 우측 chat 패널)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| ts | pipeline_runs.started_at + delta 또는 log timestamp | log stream — BE 가 log 를 시간순으로 dump | low | log stream 산출 path 미존재 (gap §A-3) |
| agent | (정적 매핑 from log source) | Collector/Parser/Mapper/Atomizer/Reporter/Forecaster/Optimizer/시스템 | low | |
| type | derived | `info` (일반) / `hil_request` (interrupt 발생) / `human_action` (resume payload) / `result` (각 agent 완료) | low | |
| summary | (없음) | 한국어 1줄 — 각 agent 가 log emit 시 박은 메시지 | low | 신규 logging path 필요 |
| detail | (없음) | optional 2~3줄 보충 | low | |

**ChatMessage 통계**: low 5 = 5 — **현 PoC 에 가장 큰 gap**. FE 가 데모용 narrative chat 으로 쓰고 있는데, BE 는 log stream / event stream 없음. **gap §A-3 결정 필요**.

---

## §7. WBSNode (Review `/review` 좌측 트리)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| id | activity_master.{l5_disc, l6_main, l7_sub} 또는 PK | 트리 path 기반 ID (예: `m15x-ph3-ibl` / `m15x.토목` / `m15x.토목.RCS` 등) | medium | path 산식 결정 필요 |
| type | derived | root=building / mid=trade / leaf=work_package | high | 트리 깊이로 분기 |
| name | activity_master.{l5_disc, l6_main, l7_sub, l7_5_activity} | 각 깊이의 컬럼 직접 | high | |
| parent_id | derived | 트리 path 의 부모 | high | |
| review_count | state.mapped | `COUNT(state.mapped WHERE requires_review=true AND l5_disc=node.l5_disc AND ...)` | medium | checkpoint state 읽기 path 필요 |
| status | derived | review_count 와 forecasts.risk_level 종합 (subtree 의 모든 risk_level 의 worst) | medium | |
| children | derived | recursive 트리 빌드 | high | |

**WBSNode 통계**: high 4 / medium 3 = 7

→ activity_master 가 트리 source (1059 row). review_count 만 checkpoint state 의존.

---

## §8. ReviewItem (Review `/review` 우측 카드)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| id | derived | `f"r-{run_id[:8]}-{idx:03d}"` (idx = state.mapped 배열 index) | high | |
| bp_name | state.mapped[i].company | 직접 | high | |
| work_content | state.mapped[i].work_content | 직접 | high | |
| quantity | state.mapped[i].today_qty | 직접 | high | |
| unit | state.mapped[i].unit | 직접 | high | |
| ai_mapped_wp_id | state.mapped[i].wa | 직접 | high | |
| ai_mapped_path | state.mapped[i].{l5_disc, l6_main, l7_sub, l7_5_activity} | `f"{l5_disc} > {l6_main} > {l7_sub or '?'} {l7_5_activity or ''}"` (PoC 의 l7_sub/l7_5_activity 가 항상 None — fallback 결정 필요) | medium | gap §C-3 — PoC fallback 산식 |
| confidence | state.mapped[i].mapping_conf | 직접 (0~1) | high | |
| status | state.mapped[i].requires_review | `requires_review ? 'unconfirmed' : 'confirmed'` | high | |
| alternative_wps | (Phase 2) | 본 PoC 빈 배열 `[]` | low | gap §A |

**ReviewItem 통계**: high 7 / medium 1 / low 1 + (id derived high 1) = 10

→ checkpoint state 의 mapped attr 읽기 path 가 필수. FastAPI 가 LangGraph checkpoint 에서 state 추출 필요.

---

## §9. ReportDaily (Reports `/reports` 좌측 sticky 패널)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| date | pipeline_runs.report_date | 직접 | high | |
| status | forecasts.risk_level | run 내 모든 forecasts.risk_level 의 worst (이상 > 주의 > 정상) | high | |
| productivity_today | forecasts.today_productivity | `MAX(forecasts.today_productivity WHERE run_id = ...)` | high | |
| delay_days | forecasts.delay_days | `MAX(forecasts.delay_days WHERE run_id = ...)` | high | |
| recovery_days | (PoC: 0) | PoC fallback, Phase 2 = optimizer | low | gap §A |

**ReportDaily 통계**: high 4 / low 1 = 5

---

## §10. ReportKpi (Reports `/reports` KpiStrip)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| productivity_today | forecasts.today_productivity | `MAX(...)` 또는 group productivity 의 weighted avg | medium | 단일 값 산출 산식 결정 필요 |
| productivity_history_diff | (BE source 없음) | 이력 평균 대비 (forecasts.similar_cases.productivity 평균과 차이) | low | gap §A — 산식 결정 |
| delay_days | forecasts.delay_days | `MAX(...)` | high | |
| expected_completion | forecasts.expected_completion | `MAX(...)` | high | |
| recoverable_productivity | (PoC: 9 hard-code) | optimizer recovery 산출 X 직접 — 산식 결정 필요 | low | gap §A |
| target_productivity | (BE source 없음) | "97%" hard-code 또는 forecasts.assessment + 산식 | low | gap §A — PoC 는 target 개념 자체가 BE 에 없음 |
| recovery_days | (PoC: 0) | optimizer.recovery_distribution 의 p50 | medium | recovery_distribution dynamic key set (d+1~d+7 + not_recovered) 에서 p50 산출 |
| recovered_completion | (PoC: = expected_completion) | `expected_completion + recovery_days` | medium | recovery_days 결정 후 derived |

**ReportKpi 통계**: high 2 / medium 3 / low 3 = 8

---

## §11. SCurvePoint (Reports / Site detail S-Curve chart)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| date | (time-series 없음) | 산출 path — activity_master.{plan_start, plan_finish} 사이 일자별 보간 또는 pipeline_runs 누적 | low | gap §A — time-series source 미존재 |
| planned | (계산) | activity_master plan_total_qty 누적 진척률 | low | |
| actual (optional) | (계산) | pipeline_runs 의 누적 atomized_count 또는 sites.actual_progress (단일 값) | low | |
| forecast (optional) | (계산) | Forecaster expected_completion 기반 추정 곡선 | low | |
| recovery (optional) | (계산) | Optimizer recovery 시나리오 곡선 | low | |

**SCurvePoint 통계**: low 5 = 5 — **time-series source 자체가 BE 에 없음**. **gap §A-4 결정 필요** (mock 유지 / plan 만 derive / 신규 컬럼 누적).

---

## §12. BarItem (Reports `/reports` 업체별·공종별 BarChartH)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| label | state.mapped[i].company (contractor_bars) 또는 trade (trade_bars) | 직접 GROUP BY | high | |
| value | forecasts.today_productivity 또는 derived | `AVG(forecasts.today_productivity WHERE company=label)` (contractor) 또는 `AVG(... WHERE l6_main=label)` (trade) | high | |
| status | forecasts.risk_level | derived from value (또는 risk_level worst) | medium | 단순 산식: value ≥ 90 → normal, 70~90 → caution, < 70 → risk |

**BarItem 통계**: high 2 / medium 1 = 3

---

## §13. QuadrantPoint (Reports `/reports` OptimizeTab QuadrantScatter)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| wp_id | forecasts.{company, l6_main} | `f"{company}|{l6_main}"` (hil_2 key 와 동일) | high | |
| wp_name | forecasts.l6_main | 직접 | high | |
| trade | forecasts.l6_main | (PoC = l6_main 동일) | high | |
| productivity | forecasts.today_productivity | 직접 (X 축, 0~100 정규화 필요) | medium | 값 범위 결정 — forecasts.today_productivity 는 % 또는 0~100 (산식 검증 필요) |
| impact | forecasts.{plan_mh_sum, mh_gap} | derived — 잔여 물량 또는 mh_gap 기반 (산식 결정) | low | gap §A — impact 산식 미정 |
| quadrant | derived | 4 분면 분류 (risk/caution/watch/safe) — productivity + impact 임계값 | medium | 임계값 결정 필요 |
| size | forecasts.plan_mh_sum 또는 plan_total_qty_by_unit | scaling (잔여 물량 비례) | medium | |

**QuadrantPoint 통계**: high 3 / medium 3 / low 1 = 7

---

## §14. OptimizerOutput (FE) ↔ optimizer_advice row (BE) — shape 변환

FE shape (5 field) 와 BE shape (10 field) 가 다름 — adapter 필요.

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| wp_id | optimizer_advice.{company, l6_main} | `f"{company}|{l6_main}"` | high | |
| diagnosis | optimizer_advice.diagnosis | 직접 (LLM 산출 또는 "cold_start") | high | |
| similar_cases | optimizer_advice.degradation_cases | **shape adapter 필요**: BE dict (date/conditions/productivity/assigned_workers/activities/recovery) → FE {date, description, outcome} | medium | FE 의 description/outcome 가 무엇으로 mapping 되는지 결정 (gap §C-4) |
| recommendations | optimizer_advice.recommendations | **shape adapter 필요**: BE list of {rank,text} → FE list of string (text 만 추출하거나 "[rank] text" 포맷) | medium | FE 가 ranked list 받을지 string list 받을지 결정 (gap §C-5) |
| details | optimizer_advice.{recovery_distribution, recovery_pattern, ...} | derived — recovery_distribution 의 key 별 카운트 표 등 | medium | label/value 쌍으로 변환 산식 결정 |

**OptimizerOutput 통계**: high 2 / medium 3 = 5

---

## §15. RawDataRow (Reports `/reports` RawDataTab)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| building | (BE source 없음 직접) | sites.name 또는 sub_work_area | low | gap §C-6 — building 의 source 결정 |
| trade | state.mapped[i].trade (= l5_disc 한글) | 직접 | high | |
| wp | state.mapped[i].wa | 직접 (wa = WP code) | high | |
| bp_name | state.mapped[i].company | 직접 | high | |
| work_content | state.mapped[i].work_content | 직접 | high | |
| quantity | state.mapped[i].today_qty | 직접 | high | |
| unit | state.mapped[i].unit | 직접 | high | |
| workers | state.mapped[i].assigned_workers | 직접 | high | |
| equipment | (state.mapped 에 없음) | Parser EquipmentAllocation 의 equipment_big 매핑 — BP별 가용 장비 list | medium | EquipmentAllocation 가 state.parsed 에만 있고 mapped 에 안 들어감 — 별도 lookup 필요 |

**RawDataRow 통계**: high 6 / medium 1 / low 1 = 8

---

## §16. ImpactSiteDistribution (Dashboard ImpactTab)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| site_id | sites.site_id | 직접 | high | |
| site_name | sites.name | 직접 | high | |
| hours_saved | sites.hours_saved | 직접 | high | |
| fte_saved | sites.fte_saved | 직접 | high | |

**ImpactSiteDistribution 통계**: high 4 = 4 ✅

---

## §17. ImpactTrendPoint (Dashboard ImpactTab 월별 누적 FTE)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| month | (BE source 없음) | 월별 historical aggregate — 산출 path 없음 | low | gap §A — historical 누적 데이터 미보유, mock 유지 |
| cumulative_fte | (BE source 없음) | 위와 동일 | low | |

**ImpactTrendPoint 통계**: low 2 = 2 — mock 유지 권고.

---

## §18. MiddleOfficeAutomation (Dashboard ImpactTab "Middle Office 4기능")

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| function | (정적) | "Data Stewardship" / "P&L Reporting" / "Risk Management" / "Deal Support" hard-code | high | 메타데이터 |
| rate | (BE source 없음) | (정적) — 산출 path 없음 | low | gap §A — 정의 자체가 BE scope 밖, mock 유지 |
| before_hours | (BE source 없음) | 정적 | low | |
| after_hours | (BE source 없음) | 정적 | low | |

**MiddleOfficeAutomation 통계**: high 1 / low 3 = 4 — mock 유지 권고.

---

## §19. SimulationSequence (dead fixture, 호출처 없음)

→ 본 cycle scope 제외. mock 유지 또는 fixture 자체 삭제.

---

## §20. DiagnosisInput (diagnosis-preview `/diagnosis-preview` only — preview 라우트, prod 제외 예정)

→ 본 cycle scope 제외. preview 라우트 제거 후 ProductivityDiagnosis 만 prod 에 사용.

---

## §21. ProductivityDiagnosis (사용자 요청 — forecaster/optimizer 연결)

**핵심**: FE 의 13 필드 ↔ BE 의 forecaster.row + optimizer_advice.row 양쪽 매핑.

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| history_mean | forecasts.similar_cases[].productivity 또는 optimizer_advice.degradation_cases[].productivity | `AVG(similar_cases[].productivity)` (forecaster rerank.py 가 이미 top-k 선별 후 박음) | medium | source 둘 중 결정 필요 — forecasts 가 우선 (group 별 산출, 항상 있음) |
| history_std | (BE 미산출) | `STDDEV(similar_cases[].productivity)` — API layer 계산 또는 신규 컬럼 | low | 산출 위치 결정 필요 (gap §A-5) |
| sample_size | forecasts.rag_n_similar | 직접 | high | |
| today_progress | forecasts.today_productivity 또는 sites.actual_progress | `forecasts.today_productivity` (group level) 또는 `sites.actual_progress` (site level) | medium | 단위 결정 — % 인지 productivity score (qty/worker) 인지 |
| productivity_score | forecasts.today_productivity | `(today / history_mean) * 100` (API layer derived) | medium | history_mean 결정 후 |
| gap_pct | derived | `productivity_score - 100` | medium | |
| z_score | derived | `(today - history_mean) / history_std` | low | history_std 결정 후 |
| status | forecasts.risk_level | 직접 매핑 ("정상" → "normal", "주의" → "caution", "이상" → "risk") | high | |
| s_curve | (time-series 없음) | gap §A-4 와 동일 — SCurvePoint source 미존재 | low | |
| band_p25 | derived | `s_curve[i].planned - history_std * 1.5` (FE diagnosis.ts:98 산식) | low | s_curve + history_std 둘 다 결정 후 |
| band_p75 | derived | `s_curve[i].planned + history_std * 1.5` | low | |
| ewma_trend | derived | EWMA(s_curve.actual, lambda=0.3) (FE diagnosis.ts:101 산식) | low | s_curve 결정 후 |
| recovery (p25/p50/p75 days) | optimizer_advice.recovery_distribution | dynamic key set (d+1~d+7 + not_recovered) 의 분포에서 p25/p50/p75 산출 | medium | recovery_distribution 의 distribution → percentile 산식 결정 |
| scenarios (optimistic/base/pessimistic) | optimizer_advice.recovery_distribution + (계산) | base = recovery.p50 기준, optimistic = p25 * 0.7, pessimistic = p50 * 1.6 (FE diagnosis.ts:115~141 산식) | medium | curve 부분은 s_curve 결정 후 |

**ProductivityDiagnosis 통계**: high 2 / medium 6 / low 5 = 13

→ **사용자 명시 결정 필요 영역**. 매핑 방향:
- **옵션 1 (FE mock 유지)**: 13 필드 전체를 FE 의 diagnose() 가 site_id 시드로 결정적 mock 생산. 본 cycle 추가 작업 0. PoC 데모 단순.
- **옵션 2 (BE adapter — 권고)**: forecaster.row + optimizer_advice.row + sites.actual_progress 을 API layer 가 ProductivityDiagnosis shape 으로 변환. history_std / s_curve 등 BE 에 없는 4~5 필드는 산식으로 derive (history_std = STDDEV(similar_cases), s_curve = sites.actual_progress 단일 점 또는 plan 기반 보간).
- **옵션 3 (신규 agent)**: BE 에 ProductivityDiagnosis 전용 agent 추가. scope blowing.

**gap §C-7 — 사용자 결정 필요**.

---

## §22. ReportDetail (fixtures.ts 만의 type — `/reports/{date}` 응답 wrapper)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| kpi | (위 §10 ReportKpi 와 동일) | run_id 기반 forecasts + optimizer 합성 | medium | |
| s_curve | (위 §11 와 동일) | gap §A-4 | low | |
| contractor_bars | (위 §12 BarItem) | state.mapped GROUP BY company → forecasts.today_productivity AVG | high | |
| trade_bars | (위 §12 BarItem) | state.mapped GROUP BY l5_disc → forecasts.today_productivity AVG | high | |
| quadrant | (위 §13 QuadrantPoint) | forecasts 각 row | medium | |
| optimizer | (위 §14 OptimizerOutput) | optimizer_advice rows (1 row 만 노출?) | medium | run 안에 N 개 optimizer_advice 있을 때 어떤 걸 noun 으로 보낼지 결정 (gap §C-8) |
| raw_data | (위 §15 RawDataRow) | state.mapped 직접 | high | |

→ ReportDetail = 위 7 type 의 합. 본 §은 group reference 만.

---

## §23. DashboardFixture (fixtures.ts 만의 type — `/dashboard` 응답 wrapper)

| FE Field | BE Source(s) | Derived Rule | Conf | Notes |
|---|---|---|---|---|
| performance.fleet_kpi.avg_productivity | forecasts.today_productivity | `AVG(MAX(forecasts.today_productivity WHERE run_id=sites.last_run_id) FOR EACH site)` | medium | |
| performance.fleet_kpi.avg_delay | forecasts.delay_days | `AVG(...)` | medium | |
| performance.fleet_kpi.abnormal_total | forecasts.risk_level | `SUM(...)` | medium | |
| performance.fleet_kpi.recoverable_days | (계산) | `SUM(site.recovery_days)` | low | recovery_days 결정 후 |
| impact.fleet_kpi | (= §2 SitesSummary) | 직접 reference | medium | |
| impact.site_distribution | (= §16) | sites 직접 | high | |
| impact.monthly_trend | (= §17) | mock 유지 | low | |
| impact.per_site_automation | (= §18 record) | mock 유지 (per site) | low | |

---

## §24. FE-내 hard-coded mock 3 종 (BE 전환 시 신규 endpoint 필요)

| Source | 의미 | 옵션 |
|---|---|---|
| `web/app/components/home/AgentWorkflow.tsx:32~40 COUNTS` | step 1~7 별 today/total 카운트 (AgentRow 우측 숫자) | (1) AgentStatus 에 today/total 추가 (2) 별 endpoint `/api/agents/counts` (3) FE mock 유지 |
| `web/app/components/NotificationBell.tsx:16~38 MOCK_NOTIFS` | 알림 3 건 (HIL 대기, 회복 완료 등) | (1) BE 가 event log 에서 derive (2) FE mock 유지 |
| `web/app/components/UserMenu.tsx:8~23 USERS` | persona 별 user info (member/manager 의 avatar/이름/롤) | (1) 진짜 auth 도입 시 server session (2) FE mock 유지 (PoC) |

→ gap §C-9 — 본 cycle 결정 필요 (전부 FE mock 유지 권고, PoC 단순성).

---

## 헤드라인 통계

| 분류 | 통계 |
|---|---|
| 총 FE field (대상) | ~150 (28 type 중 22 type, dead/preview/sim 제외) |
| **high confidence** | 약 70 (47%) |
| **medium confidence** | 약 45 (30%) |
| **low confidence** | 약 30 (20%) |
| **TBD (사용자 결정)** | 약 5 (3%) — 주로 ProductivityDiagnosis + ChatMessage |
| 매핑 0 (mock 유지 권고) | 약 10 (SimulationSequence + MiddleOfficeAutomation + ImpactTrendPoint + 일부 SitesSummary cum) |

**핵심 derive 영역** (API layer 가 채워야 할 것):
- Site derived 4 (gap_percent / spi / total_hours / ai_replacement_rate)
- SitesSummary derived 5 (today_count / abnormal_count / total_hours / ai_replacement_rate 등 SUM/AVG)
- ReviewItem.id (run_id + idx) + ai_mapped_path (`l5_disc > l6_main > l7_sub?`)
- WBSNode 트리 빌드 (activity_master 1059 row 의 4-깊이 트리)
- OptimizerOutput.{similar_cases, recommendations} shape adapter
- ProductivityDiagnosis 13 필드 (옵션 2 채택 시)

**checkpoint state 읽기 path 필요** (현재 BE 에 없음):
- state.mapped (ReviewItem 산출)
- state.hil_1_corrections (review_pending 카운트)
- state.pre_optimizer_cases (HIL 2 modal 데이터)

**sites.last_run_id 갱신 path 필요** (Site / forecasts aggregate 의 모든 매핑이 의존):
- pipeline 종료 시 UPDATE sites SET last_run_id = run_id WHERE site_id = ...
- 위치 결정 필요 (graph END node / Reporter / FastAPI /run 완료 시)

---

## §F. 2026-05-18 갱신 — PR #20/#22 신규 type + 본 cycle 결정 반영

### §F.1 § 14 OptimizerOutput 실 구현 확정 (D-12 / G-8 결정)

| FE field | BE source | 산식 / shape | 2026-05-18 갱신 |
|---|---|---|---|
| `optimizer: OptimizerOutput[]` (배열) | `optimizer_advice` PG row 전체 | `SELECT * FROM optimizer_advice WHERE run_id = :id` → row N → `OptimizerOutput[]` 직접 매핑 | **D-12 결정 실 구현 확정**. FE type 단일 → 배열 변경. mock_report.json 갱신 필요 [[cpia-optimizer-array-grain-2026-05-18]] |

### §F.2 § 21 ProductivityDiagnosis EWMA 드랍 (D-3 REVISED)

| FE field (13) | 상태 |
|---|---|
| `history_mean / history_std / sample_size / today_progress / productivity_score / gap_pct / z_score / status / s_curve / band_p25 / band_p75 / ewma_trend / recovery / scenarios` | **D-3 REVISED 2026-05-18 — EWMA 드랍**. BE adapter 안 만듦. FE diagnosis-adapter.ts:13~26 `toDiagnosisInput()` mock 어댑터 영구. `history_mean=reportKpi.target_productivity / history_std=4 고정 / sample_size=FNV-1a 해시 12~48` [[cpia-d3-ewma-drop-2026-05-18]] |

### §F.3 § 25 WPSummaryRow (PR #22 § 5 신규 표)

UI 위치: `/reports § 03 § 05` 의 WPSummaryTable — WP 단위 N row 표.

| FE field | BE source | 산식 | Confidence |
|---|---|---|---|
| `wp_id` | derive | `f"{wa}-{slug(l6_main)}-{slug(company)}"` triplet [[cpia-wpsummary-wpid-formula-2026-05-18]] | high |
| `wp_name` | `activity_master.l6_main` 그대로 (D-7 fallback) | 직접 | medium |
| `trade` | `activity_master.l5_disc` (한글) | 직접 | high |
| `bp_name` | `activity_master.company` | 직접 | high |
| `start_date` | `MIN(activity_master.plan_start) GROUP BY (wa, l6_main, company)` | 직접 | high |
| `end_date` | `MAX(activity_master.plan_finish) GROUP BY (wa, l6_main, company)` | 직접 | high |
| `progress_pct` | mapped_history + activity_master join | `SUM(mh.today_qty) / SUM(am.plan_total_qty) × 100` 누적 30 일 [[cpia-wpsummary-progress-path-2026-05-18]] | medium |
| `productivity` | `forecasts.today_productivity` | 직접 (단 forecasts.wa 컬럼 추가 후) [[cpia-wpsummary-grain-2026-05-18]] | high (grain 변경 필요) |
| `status` | `forecasts.risk_level` 3 치 매핑 | "정상"→"normal", "주의"→"caution", "이상"→"risk" | high |

### §F.4 § 26 DailyTask (PR #20 신규) — 2026-05-19 evolve

UI 위치: `/tasks` 좌측 패널 30 일 행 리스트.

> **2026-05-19 갱신**: A_Track Phase 4 11 endpoint GREEN cycle 후 `/api/tasks` (api.py:1022) 와 정합 검증 → 3 개 SQL 산식 정정 + 옵션 Y (PG row count) path 확정.

| FE field | BE source | 산식 | Confidence |
|---|---|---|---|
| `date` | `pipeline_runs.report_date` | 직접 | high |
| `total_count` | mapped_history triplet 카운트 | `COUNT(DISTINCT (wa, l6_main, company)) FROM mapped_history WHERE site_id=:id AND report_date=:d`. **A_Track api.py:856 현 구현은 `COUNT(*) FROM pipeline_runs` — site 가 같은 날 1 run 인 일반 케이스에 항상 1. 작업일보 행 의미 매칭 안 됨 → SQL 정정 backlog (BE-T1)** | medium |
| `progress_percent` | `pipeline_runs.current_node` 기반 | 8 단계 인덱스 × 12.5% (collector=12.5, parser=25, mapper/hil_1=37.5, atomizer=50, reporter=62.5, forecaster=75, optimizer=87.5, completed=100). **현 api.py:858-870 SQL 산식 정합 (AVG 만 추가). 단 pipeline_runs.current_node UPDATE path 가 atomizer 만 박는 drift (backend_catalog §A 다음 단계 P-1) → 다른 노드도 박도록 D-2 helper 신설 backlog (BE-T2)** | medium |
| `status` | `pipeline_runs.status` 매핑 | running → "running" / **waiting_hil_1/waiting_hil_2 → "review_pending"** / completed → "completed". **A_Track api.py:871-875 현 구현은 `BOOL_OR(failed)→review_pending` 으로 잘못 매핑 (failed 는 HIL 대기 아님). HIL waiting 상태 누락 → SQL 정정 backlog (BE-T3)** | high |
| `has_anomaly` | forecasts 조회 | `EXISTS (forecasts WHERE risk_level != '정상')` | high |

### §F.5 § 27 AgentStageProgress (PR #20 신규) — 2026-05-19 evolve

UI 위치: `/tasks` 중앙 8 단계 워크플로 박스.

> **2026-05-19 갱신**: G-2 의 received/processed source 가 **옵션 X (LangGraph state checkpoint) → 옵션 Y (PG row count, parser_reports/parser_activities/mapper_activities + 기존 atomized_count/forecasts/optimizer_advice)** 로 evolve. 사유: ① BI / 대시보드 친화적, ② FastAPI 구현 간단 (checkpoint state 외부 query 까다로움), ③ stash 가 parser_reports/parser_activities/mapper_activities 3 테이블 신설로 인프라 마련. PoC 단순화 = LangGraph batch 안 % 추적 불가 → percent binary 0 또는 100.

| FE field | BE source | 산식 | Confidence |
|---|---|---|---|
| `step` / `agent` / `is_hil` | BE FastAPI hard-code (D-9 정합) | static 8 단계 (Collector=1, Parser=2, Mapper=3, HIL=3.5, Atomizer=4, Reporter=5, Forecaster=6, Optimizer=7). **api.py:842-851 `_STAGE_META` 정합** | high |
| `received` / `processed` | **PG row count 단계별 (옵션 Y)** | Collector reached = `EXISTS pipeline_runs WHERE run_id` (run row 생성 = 진입). Parser = `COUNT(parser_activities WHERE run_id) = N` (stash 신설). Mapper = `COUNT(mapper_activities WHERE run_id) = N` (stash 신설). HIL Review received = `COUNT(mapper_activities WHERE requires_review=TRUE)`, processed = `COUNT(mapping_corrections WHERE run_id)`. Atomizer = `pipeline_runs.atomized_count` 또는 `COUNT(mapped_history WHERE run_id)`. Reporter = `EXISTS daily_reports WHERE run_id ? 1 : 0`. Forecaster = `COUNT(forecasts WHERE run_id)`. Optimizer = `COUNT(optimizer_advice WHERE run_id)`. **A_Track api.py:927-958 현 구현은 모든 stage `received=total_count`, `processed=total or 0` binary — PG row count 가 아닌 progress_percent 기반 추산 → SQL 정정 backlog (BE-T4)** | medium |
| `percent` | derived | `processed / received × 100` (배치라 보통 0 또는 100). PoC 단순화 명시 | medium |
| `waiting_hil` | `pipeline_runs.status IN ('waiting_hil_1','waiting_hil_2')` AND `is_hil` | 직접. **A_Track api.py:956 현 구현은 `False` 하드코드 → SQL 정정 backlog (BE-T5)** | high |

### §F.6 § 28 AgentTaskItem (PR #20 신규) — 2026-05-19 evolve

UI 위치: `/tasks` 우측 패널 N 건 목록 표.

> **2026-05-19 갱신**: `trade` 컬럼 의미 일원화 — FE 의도 = 한글 공종 (예: "철근공사", Activity.trade str), BE 가 현재 mapped_history.l6_main (예: "철근콘크리트공사", WBS 매핑 후 카테고리) 으로 박음. 사용자 "억지 매핑 금지" feedback 직접 위반. → **schema 변경: mapped_history.trade 컬럼 추가 + atomizer.py:130 의 mh_rows 생성 시 trade 박기** (cpia-mapped-history-trade-column-2026-05-19 결정).

| FE field | BE source | 산식 | Confidence |
|---|---|---|---|
| `id` | derive | `f"RPT-{date_yyyymmdd}-{idx:03d}"`. **api.py:1006 정합** | high |
| `trade` | `mapped_history.trade` (신규 컬럼) | 직접. Atomizer 가 `Activity.trade` (Parser 가 채운 한글 공종) 박음. **현재 컬럼 미존재 → migration sql 신규 backlog (BE-T6)** | medium (schema 변경 필요) |
| `contractor` | `mapped_history.company` | 직접. **api.py:894 정합** | high |
| `status` (5 치) | BE 가 3 치 산출 (PoC) + 2 치 mock (BE 협의) | done = run.completed / received = mapped_history row 생성 안 됨 / hil_pending = run.status IN waiting_hil_*. **processing / blocked = BE 협의 사항 — LangGraph batch 안에서 단일 row 의 in-flight 상태 추적 불가** [[cpia-tasks-item-status-2026-05-18]]. **A_Track api.py:978-984 현 구현은 run 단위 status 를 row 단위에 그대로 박음 + 모든 row 를 itemsByDate[date]["Collector"] 에 배치 (다른 agent key 비어있음) → SQL + 분배 로직 정정 backlog (BE-T7). current_node 별 agent key 라우팅 필요** | low (협의 사항) |

### §F.7 §1 Site 신규 매핑 추가 — fleet_kpi (G-5)

| FE field | BE source | 산식 |
|---|---|---|
| `avg_productivity` | 전 site forecasts AVG | `AVG(forecasts.today_productivity) WHERE run_id=last_run_id` |
| `avg_delay` | 전 site forecasts AVG | `AVG(forecasts.delay_days)` |
| `abnormal_total` | 전 site forecasts COUNT | `COUNT(forecasts WHERE risk_level <> '정상')` 전 site |
| `recoverable_days` | 전 site optimizer_advice agg | `SUM(recovery_distribution 가중)` — 산식 BE Phase 0 합의 |

### §F.8 ImpactSiteDistribution / AgentStatus 동적 (G-6 / G-7)

| FE field | BE source | 산식 |
|---|---|---|
| `ImpactSiteDistribution.{site_id, name, hours_saved, fte_saved}` | `sites` 컬럼 직접 | `SELECT site_id, name, hours_saved, fte_saved FROM sites` 매우 단순 |
| `AgentStatus.active_count` | pipeline_runs 집계 | `COUNT(pipeline_runs WHERE status='running' AND current_node=:agent)` |
| `AgentStatus.state` | derive | active_count > 0 → "processing" / waiting_hil_1 → "waiting" / 그 외 → "idle" |

### §F.9 WBSNode / ReportDaily / s_curve (G-3 / G-4 / G-9)

| Type | BE source | 산식 | 상태 |
|---|---|---|---|
| WBSNode (recursive) | activity_master | `GROUP BY l5_disc → l6_main` 트리 derive. 노드별 review_count = ReviewItem 매칭 카운트 | ✅ 결정 |
| ReportDaily | pipeline_runs JOIN forecasts | `SELECT date, status, MAX(productivity), MAX(delay_days), MAX(recovery_days) GROUP BY date` | ✅ 결정 |
| s_curve (계획 + 실적) | activity_master.plan_mh + mapped_history | **MH 누적 + MH 환산 산식 BE Phase 0 합의** | ⚠️ 보류 |
| s_curve (예측 + 회복) | FE adapter mock (D-3 정합) | FE diagnose() mock 영구 | ✅ mock 영구 |

### §F.10 confidence 재산정

| 분류 | ac42255 시점 | d9eb603 갱신 후 (목표) |
|---|---|---|
| 총 FE field | ~150 (28 type) | ~190 (33 type) |
| high | 70 (47%) | 80 (42%) |
| medium | 45 (30%) | 50 (26%) |
| low | 30 (20%) | 25 (13%) |
| TBD | 5 (3%) | 35 (18%) — G-9 s_curve 산식 + processing/blocked + recoverable_days 산식 + total_count 산식 등 BE Phase 0 합의 사항 |

→ TBD 18% 까지 ↑ = 본 cycle 의 결정이 BE 산식 정의를 다음 cycle (BE 구현 cycle Phase 0) 로 위임한 결과. 단 카탈로그가 stale 한 것 아니라, 결정 명확화로 인한 "BE 가공 산식 정의 작업" 의 명시화.
