# CPIA Frontend Data Catalog (web/ B_Track)

> 본 cycle 갱신 (2026-05-27): `web/lib/diagnosis.ts` buildScenarioCurve catch-up 모델 영구화, `ReportDetail.site_summary_text` LLM narrative, `ScenarioPoint.catch_up` 신규 optional, `ForecastChart` 4 신규 prop (`scenarios` / `reportDate` / `aiAdvice` / `aiSummaryText`) + 4선 차트 (검정 actual / 빨강 dashed forecast / 회색 plan / mint dashed AI), `/api/mock/report` list-only + `/api/mock/report/[date]` 분리, `/api/mock/agent-tasks` list-only + `/api/mock/agent-tasks/[date]` 분리, `web/lib/bar-filters.ts` 신규.
>
> Grep 출처: `web/lib/` (12 파일 1,533 LOC), `web/app/(app)/{home,tasks,review,reports,export,dashboard}/page.tsx` (6 페이지), `web/app/(landing)/page.tsx`, `web/app/api/mock/*/route.ts` (7 routes), `web/app/components/**/*.tsx` (53 components 5,873 LOC), `data/mock_*.json` (10 fixture).
>
> 본 cycle 부터 fixture → PG SELECT swap 거의 완료: `/api/mock/*` 7 route 중 6 route 가 100% PG, `dashboard` 만 partial (performance=PG / impact=fixture). `loadReal()` (fixtures.ts:99) 가 `sites_summary` / `agent_status` / `chat_sequence` / `dashboard_performance` 4 종을 PG 로 채움. `loadFixture()` 는 dashboard.impact + sites + simulation(dead) 에만 남음.

---

## §A — Type 인벤토리 (모든 type × 모든 field)

> 모든 field 는 `?` 가 없는 한 required. 본 cycle 신규/변경은 ★ NEW 또는 ★ CHG.
> 출처: `web/lib/types.ts` (404 라인) + `web/lib/fixtures.ts` 51~84 별도 type 5 종 (`Scenario`, `ScenarioSet`, `OptimizerByWp`, `ReportDetail`, `DashboardFixture`) + 컴포넌트 내부 helper 4 종 (`KpiItem`, `SheetColumn`, `OpsKpiCardProps`, `HilSpec`).

### §A.1 Core types (`web/lib/types.ts`, 404 라인)

| Type | Field | TS Type | Optional | Source File:Line |
|---|---|---|---|---|
| **Status** (alias) | (value) | `"normal" \| "caution" \| "risk" \| "unknown"` | N | web/lib/types.ts:5 |
| **Persona** (alias) | (value) | `"member" \| "manager"` | N | web/lib/types.ts:6 |
| **Site** | id | `string` | N | web/lib/types.ts:10 |
| Site | name | `string` | N | web/lib/types.ts:11 |
| Site | location | `string` | N | web/lib/types.ts:12 |
| Site | status | `Status` | N | web/lib/types.ts:13 |
| Site | is_mock | `boolean` (true=회색 + preview 배지) | Y | web/lib/types.ts:14 |
| Site | progress_planned | `number` (%) | N | web/lib/types.ts:15 |
| Site | progress_actual | `number` (%) | N | web/lib/types.ts:16 |
| Site | gap_percent | `number` (%p) | N | web/lib/types.ts:17 |
| Site | productivity_today | `number` (%) | N | web/lib/types.ts:18 |
| Site | spi | `number` | N | web/lib/types.ts:19 |
| Site | abnormal_trades | `number` | N | web/lib/types.ts:20 |
| Site | fte_saved | `number` | N | web/lib/types.ts:21 |
| Site | hours_saved | `number` (월) | N | web/lib/types.ts:22 |
| Site | headcount | `number` (현장 전체 근무 인원) | N | web/lib/types.ts:23 |
| Site | total_hours | `number` (headcount × 140) | N | web/lib/types.ts:24 |
| Site | ai_replacement_rate | `number` (hours_saved / total_hours) | N | web/lib/types.ts:25 |
| Site | expected_completion | `string` (ISO date) | N | web/lib/types.ts:26 |
| Site | recovered_completion | `string` (ISO date) | N | web/lib/types.ts:27 |
| Site | delay_days | `number` | N | web/lib/types.ts:28 |
| Site | recovery_days | `number` | N | web/lib/types.ts:29 |
| **SitesSummary** | today_count | `number` (오늘 처리 87 건) | N | web/lib/types.ts:34 |
| SitesSummary | review_pending | `number` | N | web/lib/types.ts:35 |
| SitesSummary | abnormal_count | `number` | N | web/lib/types.ts:36 |
| SitesSummary | last_updated | `string` (HH:MM 또는 "—") | N | web/lib/types.ts:37 |
| SitesSummary | total_hours_saved | `number` (월간) | N | web/lib/types.ts:38 |
| SitesSummary | total_fte_saved | `number` | N | web/lib/types.ts:39 |
| SitesSummary | total_headcount | `number` | N | web/lib/types.ts:40 |
| SitesSummary | total_hours | `number` | N | web/lib/types.ts:41 |
| SitesSummary | ai_replacement_rate | `number` (%) | N | web/lib/types.ts:42 |
| SitesSummary | yearly_saving | `number` (억) | N | web/lib/types.ts:43 |
| SitesSummary | total_processed | `number` (누적 — 런칭 이후) | N | web/lib/types.ts:44 |
| SitesSummary | total_hours_saved_cum | `number` (누적 절감 h) | N | web/lib/types.ts:45 |
| **AgentStatus** | step | `number` (1..7) | N | web/lib/types.ts:50 |
| AgentStatus | name | `string` ("Collector".."Optimizer") | N | web/lib/types.ts:51 |
| AgentStatus | korean_name | `string` ("수집".."조언") | N | web/lib/types.ts:52 |
| AgentStatus | description | `string` | N | web/lib/types.ts:53 |
| AgentStatus | model | `string` ("규칙 기반" \| "gpt-5.1" \| "gpt-5.1 + RAG" \| "임베딩 모델" \| "Sonnet 4.6" \| "Opus 4.7") | N | web/lib/types.ts:54 |
| AgentStatus | group | `"collect" \| "analyze"` | N | web/lib/types.ts:55 |
| AgentStatus | active_count | `number` | N | web/lib/types.ts:56 |
| AgentStatus | state | `"processing" \| "waiting" \| "idle"` | N | web/lib/types.ts:57 |
| **DailyRun** (legacy) | date | `string` ("2026-05-15") | N | web/lib/types.ts:62 |
| DailyRun | total_count | `number` | N | web/lib/types.ts:63 |
| DailyRun | status | `"running" \| "completed" \| "review_pending"` | N | web/lib/types.ts:64 |
| DailyRun | has_anomaly | `boolean` | N | web/lib/types.ts:65 |
| DailyRun | bar_value | `number` (0..1) | N | web/lib/types.ts:66 |
| **AgentProgress** (legacy) | agent | `string` (Collector~Optimizer + "Human Review") | N | web/lib/types.ts:70 |
| AgentProgress | unit | `"per_report" \| "per_review" \| "per_run"` | N | web/lib/types.ts:71 |
| AgentProgress | processed | `number` | N | web/lib/types.ts:72 |
| AgentProgress | total | `number` | N | web/lib/types.ts:73 |
| AgentProgress | waiting_hil | `boolean` | N | web/lib/types.ts:74 |
| **DailyTask** | date | `string` (ISO) | N | web/lib/types.ts:79 |
| DailyTask | total_count | `number` (작업일보 건수) | N | web/lib/types.ts:80 |
| DailyTask | progress_percent | `number` (0..100, 파이프라인 진행률) | N | web/lib/types.ts:81 |
| DailyTask | status | `"running" \| "completed" \| "review_pending"` | N | web/lib/types.ts:82 |
| DailyTask | has_anomaly | `boolean` | N | web/lib/types.ts:83 |
| **AgentStageProgress** | step | `number` (1..7, HIL=3.5) | N | web/lib/types.ts:87 |
| AgentStageProgress | agent | `string` (Collector..Optimizer + "Human Review") | N | web/lib/types.ts:88 |
| AgentStageProgress | is_hil | `boolean` | N | web/lib/types.ts:89 |
| AgentStageProgress | received | `number` (접수 건수) | N | web/lib/types.ts:90 |
| AgentStageProgress | processed | `number` (처리 건수) | N | web/lib/types.ts:91 |
| AgentStageProgress | percent | `number` (0..100) | N | web/lib/types.ts:92 |
| AgentStageProgress | waiting_hil | `boolean` | N | web/lib/types.ts:93 |
| **AgentTaskItem** | id | `string` ("mapper-123" / "parser-456") | N | web/lib/types.ts:97 |
| AgentTaskItem | trade | `string` (l6_main 또는 trade) | N | web/lib/types.ts:98 |
| AgentTaskItem | contractor | `string` (BP 사) | N | web/lib/types.ts:99 |
| AgentTaskItem | status | `"done" \| "processing" \| "received" \| "hil_pending" \| "blocked"` | N | web/lib/types.ts:100 |
| **ChatMessage** | ts | `string` ("09:01:18") | N | web/lib/types.ts:104 |
| ChatMessage | agent | `string` (8 agent + "SKEP Manager") | N | web/lib/types.ts:105 |
| ChatMessage | type | `"info" \| "hil_request" \| "human_action" \| "result"` | N | web/lib/types.ts:106 |
| ChatMessage | summary | `string` (1줄) | N | web/lib/types.ts:107 |
| ChatMessage | detail | `string` (2~3줄) | Y | web/lib/types.ts:108 |
| **WBSNode** | id | `string` | N | web/lib/types.ts:113 |
| WBSNode | type | `"building" \| "trade" \| "work_package"` | N | web/lib/types.ts:114 |
| WBSNode | name | `string` | N | web/lib/types.ts:115 |
| WBSNode | parent_id | `string \| null` | N | web/lib/types.ts:116 |
| WBSNode | review_count | `number` (미확정 집계, AlertCircle 표시) | N | web/lib/types.ts:117 |
| WBSNode | total_count | `number` (총 매핑 활동 집계) | N | web/lib/types.ts:118 |
| WBSNode | status | `Status` | N | web/lib/types.ts:119 |
| WBSNode | children | `WBSNode[]` | Y | web/lib/types.ts:120 |
| **ReviewItem** | id | `string` ("r-001") | N | web/lib/types.ts:124 |
| ReviewItem | bp_name | `string` ("A건설") | N | web/lib/types.ts:125 |
| ReviewItem | work_content | `string` (원문) | N | web/lib/types.ts:126 |
| ReviewItem | quantity | `number` | N | web/lib/types.ts:127 |
| ReviewItem | unit | `string` ("㎡" / "ton" / "m³" / "EA") | N | web/lib/types.ts:128 |
| ReviewItem | ai_mapped_wp_id | `string` (deriveWpIdAndPath 산출) | N | web/lib/types.ts:129 |
| ReviewItem | ai_mapped_path | `string` ("M15X > 골조 > WP-3-2 거푸집") | N | web/lib/types.ts:130 |
| ReviewItem | confidence | `number` (0.0~1.0) | N | web/lib/types.ts:131 |
| ReviewItem | status | `"confirmed" \| "unconfirmed"` | N | web/lib/types.ts:132 |
| ReviewItem | alternative_wps | `{ id: string; path: string; score: number }[]` | Y | web/lib/types.ts:133 |
| **ReportDaily** | date | `string` | N | web/lib/types.ts:138 |
| ReportDaily | status | `Status` | N | web/lib/types.ts:139 |
| ReportDaily | productivity_today | `number` | N | web/lib/types.ts:140 |
| ReportDaily | delay_days | `number` | N | web/lib/types.ts:141 |
| ReportDaily | recovery_days | `number` | N | web/lib/types.ts:142 |
| **ReportKpi** | productivity_today | `number` (88) | N | web/lib/types.ts:146 |
| ReportKpi | productivity_history_diff | `number` (-12) | N | web/lib/types.ts:147 |
| ReportKpi | delay_days | `number` (14) | N | web/lib/types.ts:148 |
| ReportKpi | expected_completion | `string` ("2026-08-12") | N | web/lib/types.ts:149 |
| ReportKpi | recoverable_productivity | `number` (9 %p) | N | web/lib/types.ts:150 |
| ReportKpi | target_productivity | `number` (97 — diagnosis history_mean 입력) | N | web/lib/types.ts:151 |
| ReportKpi | recovery_days | `number` (9) | N | web/lib/types.ts:152 |
| ReportKpi | recovered_completion | `string` ("2026-08-03") | N | web/lib/types.ts:153 |
| ReportKpi | productivity_today_simple_mean | `number` (wv-median 외 mean 병렬) | Y | web/lib/types.ts:154 |
| ReportKpi | productivity_today_perperson | `number` (3.2) | Y | web/lib/types.ts:155 |
| ReportKpi | productivity_today_unit | `string` ("ton/인") | Y | web/lib/types.ts:156 |
| ReportKpi | productivity_today_display | `string` ("98.9% (3.2 ton/인)") | Y | web/lib/types.ts:157 |
| **SCurvePoint** | date | `string` | N | web/lib/types.ts:161 |
| SCurvePoint | planned | `number` (계획 누적 %) | N | web/lib/types.ts:162 |
| SCurvePoint | actual | `number` (실적 누적 %, 오늘까지) | Y | web/lib/types.ts:163 |
| SCurvePoint | forecast | `number` (BE 예측선 — actual trend 연장, plan 과 평행 격차 유지) | Y | web/lib/types.ts:164 |
| SCurvePoint | recovery | `number` (Optimizer 만회선 — 현재 미사용) | Y | web/lib/types.ts:165 |
| **BarItem** | label | `string` (BP사 또는 공종명) | N | web/lib/types.ts:169 |
| BarItem | value | `number` (생산성 %) | N | web/lib/types.ts:170 |
| BarItem | status | `Status` | N | web/lib/types.ts:171 |
| BarItem | baseline | `number` (자체 이력 평균 — showBaseline Line dot) | Y | web/lib/types.ts:172 |
| BarItem | display_label | `string` ("98.9% (3.20 ton/인)") | Y | web/lib/types.ts:173 |
| BarItem | perperson | `number` | Y | web/lib/types.ts:174 |
| BarItem | perperson_unit | `string` ("ton/인") | Y | web/lib/types.ts:175 |
| **QuadrantPoint** | wp_id | `string` | N | web/lib/types.ts:179 |
| QuadrantPoint | wp_name | `string` | N | web/lib/types.ts:180 |
| QuadrantPoint | trade | `string` | N | web/lib/types.ts:181 |
| QuadrantPoint | productivity | `number` (0..100, X reversed) | N | web/lib/types.ts:182 |
| QuadrantPoint | impact | `number` (0..100, Y) | N | web/lib/types.ts:183 |
| QuadrantPoint | quadrant | `"risk" \| "caution" \| "watch" \| "safe"` | N | web/lib/types.ts:184 |
| QuadrantPoint | size | `number` (Z, 잔여 물량) | N | web/lib/types.ts:185 |
| QuadrantPoint | display_label | `string` | Y | web/lib/types.ts:186 |
| QuadrantPoint | perperson | `number` | Y | web/lib/types.ts:187 |
| QuadrantPoint | perperson_unit | `string` | Y | web/lib/types.ts:188 |
| **OptimizerOutput** | wp_id | `string` | N | web/lib/types.ts:192 |
| OptimizerOutput | diagnosis | `string` (자연어 — "cold_start" 면 미산출 의미) | N | web/lib/types.ts:193 |
| OptimizerOutput | similar_cases | `{ date: string; description: string; outcome: string }[]` | N | web/lib/types.ts:194 |
| OptimizerOutput | recommendations | `string[]` | N | web/lib/types.ts:195 |
| OptimizerOutput | details | `{ label: string; value: string }[]` | N | web/lib/types.ts:196 |
| **RawDataRow** | building | `string` | N | web/lib/types.ts:200 |
| RawDataRow | trade | `string` | N | web/lib/types.ts:201 |
| RawDataRow | wp | `string` | N | web/lib/types.ts:202 |
| RawDataRow | bp_name | `string` | N | web/lib/types.ts:203 |
| RawDataRow | work_content | `string` | N | web/lib/types.ts:204 |
| RawDataRow | quantity | `number` | N | web/lib/types.ts:205 |
| RawDataRow | unit | `string` | N | web/lib/types.ts:206 |
| RawDataRow | workers | `number` | N | web/lib/types.ts:207 |
| RawDataRow | equipment | `string` | N | web/lib/types.ts:208 |
| **WPSummaryRow** | wp_id | `string` | N | web/lib/types.ts:213 |
| WPSummaryRow | wp_name | `string` ("WP-3-2 거푸집") | N | web/lib/types.ts:214 |
| WPSummaryRow | trade | `string` ("골조") | N | web/lib/types.ts:215 |
| WPSummaryRow | bp_name | `string` | N | web/lib/types.ts:216 |
| WPSummaryRow | start_date | `string` (ISO) | N | web/lib/types.ts:217 |
| WPSummaryRow | end_date | `string` (ISO) | N | web/lib/types.ts:218 |
| WPSummaryRow | progress_pct | `number` (0..100) | N | web/lib/types.ts:219 |
| WPSummaryRow | productivity | `number` (Quadrant 와 동일 값) | N | web/lib/types.ts:220 |
| WPSummaryRow | impact | `number` (WV — Quadrant 와 동일 값) | N | web/lib/types.ts:221 |
| WPSummaryRow | baseline | `number` (이력 평균 — 회복 폭 baseline−productivity) | N | web/lib/types.ts:222 |
| WPSummaryRow | status | `"normal" \| "caution" \| "risk"` (Status \ "unknown") | N | web/lib/types.ts:223 |
| WPSummaryRow | display_label | `string` | Y | web/lib/types.ts:224 |
| WPSummaryRow | perperson | `number` | Y | web/lib/types.ts:225 |
| WPSummaryRow | perperson_unit | `string` | Y | web/lib/types.ts:226 |
| **FleetTrendPoint** | date | `string` (ISO "YYYY-MM-DD") | N | web/lib/types.ts:231 |
| FleetTrendPoint | mean | `number` (0..100, 평균) | N | web/lib/types.ts:232 |
| FleetTrendPoint | min | `number` (0..100, 최저 현장) | N | web/lib/types.ts:233 |
| FleetTrendPoint | max | `number` (0..100, 최고 현장) | N | web/lib/types.ts:234 |
| **ImpactSiteDistribution** | site_id | `string` | N | web/lib/types.ts:239 |
| ImpactSiteDistribution | site_name | `string` | N | web/lib/types.ts:240 |
| ImpactSiteDistribution | hours_saved | `number` | N | web/lib/types.ts:241 |
| ImpactSiteDistribution | fte_saved | `number` | N | web/lib/types.ts:242 |
| **ImpactTrendPoint** | month | `string` ("2026-01") | N | web/lib/types.ts:246 |
| ImpactTrendPoint | cumulative_fte | `number` | N | web/lib/types.ts:247 |
| **MiddleOfficeAutomation** | function | `string` (4 기능) | N | web/lib/types.ts:251 |
| MiddleOfficeAutomation | rate | `number` (0..100) | N | web/lib/types.ts:252 |
| MiddleOfficeAutomation | before_hours | `number` | N | web/lib/types.ts:253 |
| MiddleOfficeAutomation | after_hours | `number` | N | web/lib/types.ts:254 |
| **SimulationSequence** (dead) | home_now_strip | `{ interval_ms: number; variance: number }[]` | N | web/lib/types.ts:259 |
| SimulationSequence | agent_card_status | `Record<string, number[]>` | N | web/lib/types.ts:260 |
| SimulationSequence | chat_log | `ChatMessage[]` | N | web/lib/types.ts:261 |
| **DiagStatus** (alias) | (value) | `Exclude<Status, "unknown">` (`"normal" \| "caution" \| "risk"`) | N | web/lib/types.ts:265 |
| **DiagnosisInput** | site_id | `string` (결정성 mock 시드) | N | web/lib/types.ts:268 |
| DiagnosisInput | today_progress | `number` (오늘 누적 진척률 %) | N | web/lib/types.ts:269 |
| DiagnosisInput | history_mean | `number` (μ) | N | web/lib/types.ts:270 |
| DiagnosisInput | history_std | `number` (σ) | N | web/lib/types.ts:271 |
| DiagnosisInput | sample_size | `number` (N) | N | web/lib/types.ts:272 |
| DiagnosisInput | s_curve | `SCurvePoint[]` | N | web/lib/types.ts:273 |
| DiagnosisInput | recovery_days_p25 | `number` (BE scenarios.site 산출, slope 계산용) | Y | web/lib/types.ts:276 |
| DiagnosisInput | recovery_days_p50 | `number` | Y | web/lib/types.ts:277 |
| DiagnosisInput | recovery_days_p75 | `number` | Y | web/lib/types.ts:278 |
| DiagnosisInput | delay_days | `number` | Y | web/lib/types.ts:279 |
| **RecoveryEstimate** | p25 | `number` | N | web/lib/types.ts:283 |
| RecoveryEstimate | p50 | `number` | N | web/lib/types.ts:284 |
| RecoveryEstimate | p75 | `number` | N | web/lib/types.ts:285 |
| **ScenarioPoint** | eta_days | `number` (∞ 허용) | N | web/lib/types.ts:289 |
| ScenarioPoint | recovery_pct | `number` (회복 후 누적 %) | N | web/lib/types.ts:290 |
| ScenarioPoint | delta_completion_days | `number` (★ CHG — 항상 0, plan 동행 의미) | N | web/lib/types.ts:291 |
| ScenarioPoint | curve | `(number \| null)[]` (시계열, today 이전 + catch-up 이후 null) | N | web/lib/types.ts:292 |
| ★ NEW ScenarioPoint | catch_up | `{ date: string; percent: number }` (plan 따라잡는 시점) | Y | web/lib/types.ts:293 |
| **SheetTab** (alias) | (value) | `"output_manpower" \| "occupation_manpower" \| "equipment" \| "quantity"` | N | web/lib/types.ts:300~304 |
| **ConsolidatedReportSummary** | date | `string` (YYYY-MM-DD) | N | web/lib/types.ts:307 |
| ConsolidatedReportSummary | pjt | `string` ("M15X Ph-3 IBL") | N | web/lib/types.ts:308 |
| ConsolidatedReportSummary | status | `"ready" \| "draft"` | N | web/lib/types.ts:309 |
| ConsolidatedReportSummary | sheet_row_counts | `Record<SheetTab, number>` | N | web/lib/types.ts:310 |
| **OutputManpowerRow** | pjt | `string` | N | web/lib/types.ts:314 |
| OutputManpowerRow | zone | `string` | N | web/lib/types.ts:315 |
| OutputManpowerRow | trade | `string` | N | web/lib/types.ts:316 |
| OutputManpowerRow | bp_code | `string` | N | web/lib/types.ts:317 |
| OutputManpowerRow | scope | `string` | N | web/lib/types.ts:318 |
| OutputManpowerRow | main_work | `string` | N | web/lib/types.ts:319 |
| OutputManpowerRow | prev_work | `string` (전일 작업) | N | web/lib/types.ts:320 |
| OutputManpowerRow | today_work | `string` (금일 작업) | N | web/lib/types.ts:321 |
| OutputManpowerRow | next_work | `string` (명일 작업) | N | web/lib/types.ts:322 |
| OutputManpowerRow | early | `number` (조출) | N | web/lib/types.ts:323 |
| OutputManpowerRow | day | `number` (주간) | N | web/lib/types.ts:324 |
| OutputManpowerRow | overtime | `number` (연장) | N | web/lib/types.ts:325 |
| **OccupationManpowerRow** | trade | `string` | N | web/lib/types.ts:329 |
| OccupationManpowerRow | bp_code | `string` | N | web/lib/types.ts:330 |
| OccupationManpowerRow | manager_code | `string` | N | web/lib/types.ts:331 |
| OccupationManpowerRow | skilled_code | `string` | N | web/lib/types.ts:332 |
| OccupationManpowerRow | occupation | `string` | N | web/lib/types.ts:333 |
| OccupationManpowerRow | prev_cum | `number` | N | web/lib/types.ts:334 |
| OccupationManpowerRow | early | `number` | N | web/lib/types.ts:335 |
| OccupationManpowerRow | day | `number` | N | web/lib/types.ts:336 |
| OccupationManpowerRow | overtime | `number` | N | web/lib/types.ts:337 |
| OccupationManpowerRow | night | `number` | N | web/lib/types.ts:338 |
| OccupationManpowerRow | allnight | `number` (철야) | N | web/lib/types.ts:339 |
| OccupationManpowerRow | cum_t | `number` (Cum. T) | N | web/lib/types.ts:340 |
| **EquipmentRow** | trade | `string` | N | web/lib/types.ts:344 |
| EquipmentRow | bp_code | `string` | N | web/lib/types.ts:345 |
| EquipmentRow | eq_major | `string` (대분류) | N | web/lib/types.ts:346 |
| EquipmentRow | eq_mid | `string` (중분류) | N | web/lib/types.ts:347 |
| EquipmentRow | eq_spec | `string` (규격) | N | web/lib/types.ts:348 |
| EquipmentRow | prev_cum | `number` | N | web/lib/types.ts:349 |
| EquipmentRow | early | `number` | N | web/lib/types.ts:350 |
| EquipmentRow | day | `number` | N | web/lib/types.ts:351 |
| EquipmentRow | overtime | `number` | N | web/lib/types.ts:352 |
| EquipmentRow | night | `number` | N | web/lib/types.ts:353 |
| EquipmentRow | allnight | `number` | N | web/lib/types.ts:354 |
| EquipmentRow | cum_t | `number` | N | web/lib/types.ts:355 |
| **QuantityRow** | zone | `string` | N | web/lib/types.ts:359 |
| QuantityRow | trade | `string` | N | web/lib/types.ts:360 |
| QuantityRow | bp_code | `string` | N | web/lib/types.ts:361 |
| QuantityRow | bp_name | `string` | N | web/lib/types.ts:362 |
| QuantityRow | scope | `string` | N | web/lib/types.ts:363 |
| QuantityRow | rep_work | `string` (대표 작업내용) | N | web/lib/types.ts:364 |
| QuantityRow | unit | `string` | N | web/lib/types.ts:365 |
| QuantityRow | total_a | `number` (총물량 [A]) | N | web/lib/types.ts:366 |
| QuantityRow | prev_cum_b | `number` (전일누적 [B]) | N | web/lib/types.ts:367 |
| QuantityRow | today_c | `number` (금일실적 [C]) | N | web/lib/types.ts:368 |
| **ConsolidatedReport** | (extends ConsolidatedReportSummary) | + output_manpower / occupation_manpower / equipment / quantity 배열 4 종 | N | web/lib/types.ts:371~376 |
| **ProductivityDiagnosis** | history_mean | `number` | N | web/lib/types.ts:380 |
| ProductivityDiagnosis | history_std | `number` | N | web/lib/types.ts:381 |
| ProductivityDiagnosis | sample_size | `number` | N | web/lib/types.ts:382 |
| ProductivityDiagnosis | today_progress | `number` | N | web/lib/types.ts:385 |
| ProductivityDiagnosis | productivity_score | `number` (today/μ × 100) | N | web/lib/types.ts:386 |
| ProductivityDiagnosis | gap_pct | `number` (%p) | N | web/lib/types.ts:387 |
| ProductivityDiagnosis | z_score | `number` | N | web/lib/types.ts:388 |
| ProductivityDiagnosis | status | `DiagStatus` | N | web/lib/types.ts:389 |
| ProductivityDiagnosis | s_curve | `SCurvePoint[]` | N | web/lib/types.ts:392 |
| ProductivityDiagnosis | band_p25 | `number[]` (볼린저 하단 — planned − 1.5σ) | N | web/lib/types.ts:393 |
| ProductivityDiagnosis | band_p75 | `number[]` (볼린저 상단 — planned + 1.5σ) | N | web/lib/types.ts:394 |
| ProductivityDiagnosis | ewma_trend | `number[]` (λ=0.3) | N | web/lib/types.ts:395 |
| ProductivityDiagnosis | recovery | `{ p25_days; p50_days; p75_days }` | N | web/lib/types.ts:398 |
| ProductivityDiagnosis | scenarios | `{ optimistic: ScenarioPoint; base: ScenarioPoint; pessimistic: ScenarioPoint }` | N | web/lib/types.ts:399~403 |

### §A.2 Fixture-side types (`web/lib/fixtures.ts`)

| Type | Field | TS Type | Optional | Source File:Line |
|---|---|---|---|---|
| **FixtureMap** (internal) | sites | `Site[]` | N | web/lib/fixtures.ts:18 |
| FixtureMap | sites_summary | `SitesSummary` | N | web/lib/fixtures.ts:19 |
| FixtureMap | agent_status | `AgentStatus[]` | N | web/lib/fixtures.ts:20 |
| FixtureMap | agent_tasks | `{ daily_runs: DailyRun[]; progress_by_date: Record<string, AgentProgress[]> }` | N | web/lib/fixtures.ts:21 |
| FixtureMap | chat_sequence | `Record<string, ChatMessage[]>` | N | web/lib/fixtures.ts:22 |
| FixtureMap | review_cards | `ReviewItem[]` | N | web/lib/fixtures.ts:23 |
| FixtureMap | wbs_tree | `WBSNode` | N | web/lib/fixtures.ts:24 |
| FixtureMap | report | `{ daily: ReportDaily[]; details: Record<string, ReportDetail> }` | N | web/lib/fixtures.ts:25 |
| FixtureMap | dashboard | `DashboardFixture` | N | web/lib/fixtures.ts:26 |
| FixtureMap | simulation | `SimulationSequence` | N | web/lib/fixtures.ts:27 |
| **Scenario** | expected_completion | `string \| null` | N | web/lib/fixtures.ts:31 |
| Scenario | recovery_days | `number` (catch-up 일수) | N | web/lib/fixtures.ts:32 |
| Scenario | delta_days | `number` | N | web/lib/fixtures.ts:33 |
| Scenario | case_count | `number` (LLM 유사 case 수 — ForecastChart 권고 푸터 참조) | N | web/lib/fixtures.ts:34 |
| **ScenarioSet** | no_action | `Scenario` (현 추세 연장 — ForecastChart noActionEnd) | N | web/lib/fixtures.ts:38 |
| ScenarioSet | optimistic_p25 | `Scenario` | N | web/lib/fixtures.ts:39 |
| ScenarioSet | base_p50 | `Scenario` | N | web/lib/fixtures.ts:40 |
| ScenarioSet | pessimistic_p75 | `Scenario` | N | web/lib/fixtures.ts:41 |
| **OptimizerByWp** | by_wp | `Record<string, OptimizerOutput>` | N | web/lib/fixtures.ts:45 |
| OptimizerByWp | default_wp_id | `string \| null` | N | web/lib/fixtures.ts:46 |
| **ReportDetail** | kpi | `ReportKpi` | N | web/lib/fixtures.ts:50 |
| ReportDetail | s_curve | `SCurvePoint[]` | N | web/lib/fixtures.ts:51 |
| ReportDetail | contractor_bars | `BarItem[]` | N | web/lib/fixtures.ts:52 |
| ReportDetail | trade_bars | `BarItem[]` | N | web/lib/fixtures.ts:53 |
| ReportDetail | quadrant | `QuadrantPoint[]` | N | web/lib/fixtures.ts:54 |
| ReportDetail | optimizer | `OptimizerByWp` (wp_id 키 dict + default_wp_id) | N | web/lib/fixtures.ts:55 |
| ReportDetail | scenarios | `{ site?: Partial<ScenarioSet>; by_wp?: Record<string, ScenarioSet> }` | Y | web/lib/fixtures.ts:56~59 |
| ★ NEW ReportDetail | site_summary_text | `string \| null` (BE Optimizer LLM site 1~2 단락 narrative, 없으면 룰베이스 fallback) | Y | web/lib/fixtures.ts:60~61 |
| ReportDetail | raw_data | `RawDataRow[]` | N | web/lib/fixtures.ts:62 |
| ReportDetail | wp_summary | `WPSummaryRow[]` | N | web/lib/fixtures.ts:63 |
| **DashboardFixture** | performance.fleet_kpi.avg_productivity | `number` | N | web/lib/fixtures.ts:69 |
| DashboardFixture | performance.fleet_kpi.avg_delay | `number` | N | web/lib/fixtures.ts:70 |
| DashboardFixture | performance.fleet_kpi.abnormal_total | `number` | N | web/lib/fixtures.ts:71 |
| DashboardFixture | performance.fleet_kpi.recoverable_days | `number` | N | web/lib/fixtures.ts:72 |
| DashboardFixture | performance.fleet_trend | `FleetTrendPoint[]` | Y | web/lib/fixtures.ts:75 |
| DashboardFixture | performance.site_sparklines | `Record<string, number[]>` | Y | web/lib/fixtures.ts:76 |
| DashboardFixture | impact.fleet_kpi | `SitesSummary` | N | web/lib/fixtures.ts:79 |
| DashboardFixture | impact.site_distribution | `ImpactSiteDistribution[]` | N | web/lib/fixtures.ts:80 |
| DashboardFixture | impact.monthly_trend | `ImpactTrendPoint[]` | N | web/lib/fixtures.ts:81 |
| DashboardFixture | impact.per_site_automation | `Record<string, MiddleOfficeAutomation[]>` | N | web/lib/fixtures.ts:82 |

### §A.3 Sub-component / helper shapes (UI types)

| Type | Field | TS Type | Optional | Source File:Line |
|---|---|---|---|---|
| **KpiItem** | label | `string` | N | web/app/components/reports/KpiStrip.tsx:4 |
| KpiItem | value | `string` | N | web/app/components/reports/KpiStrip.tsx:5 |
| KpiItem | unit | `string` | Y | web/app/components/reports/KpiStrip.tsx:6 |
| KpiItem | sub | `string` | Y | web/app/components/reports/KpiStrip.tsx:7 |
| KpiItem | tone | `"primary" \| "risk" \| "caution" \| "normal" \| "muted"` | N | web/app/components/reports/KpiStrip.tsx:9 |
| **SheetColumn\<T\>** | key | `keyof T` | N | web/app/components/export/SheetTable.tsx:11 |
| SheetColumn | label | `string` | N | web/app/components/export/SheetTable.tsx:12 |
| SheetColumn | align | `"left" \| "right" \| "center"` | Y | web/app/components/export/SheetTable.tsx:13 |
| SheetColumn | width | `string` (Tailwind class) | Y | web/app/components/export/SheetTable.tsx:14 |
| SheetColumn | format | `(v, row) => ReactNode` | Y | web/app/components/export/SheetTable.tsx:16 |
| SheetColumn | cellClass | `string` | Y | web/app/components/export/SheetTable.tsx:18 |
| **OpsKpiCardProps** | tone | `"brand" \| "mint" \| "sun" \| "sky"` | N | web/app/components/home/OpsKpiCard.tsx:6 |
| OpsKpiCardProps | icon / label / value | `ReactNode / string / string` | N | web/app/components/home/OpsKpiCard.tsx:7~9 |
| OpsKpiCardProps | unit / description / live | `string / string / boolean` | Y | web/app/components/home/OpsKpiCard.tsx:10~12 |
| **HilSpec** (Home 하드코딩) | no / afterStep / title / description / waiting / icon | 1 / 3 / "Mapping Review" / ... / 3 | N | web/app/components/home/AgentWorkflow.tsx:54~62 |

### §A 합계

- 본 cycle type 총 **48 (이전 cycle 45 → +3)**: ★ NEW = (1) `ScenarioPoint.catch_up` 필드 (type 자체는 기존), (2) `ReportDetail.site_summary_text` 필드 (type 자체는 기존), (3) helper `OpsKpiCardProps` / `HilSpec` 두 type 명시 인벤토리 추가. + (deprecate 표시 추가) `DailyRun` / `AgentProgress` 는 legacy — `/api/mock/agent-tasks` 가 `DailyTask` / `AgentStageProgress` 로 swap 됐지만 type 정의는 보존 (호환).
- 본 cycle field 총 **약 220 (이전 218 → +2 ★ NEW field)**.
- ★ NEW 본 cycle field: **5** (요구사양과 일치)
  1. `ScenarioPoint.catch_up: { date: string; percent: number } \| undefined` — `web/lib/diagnosis.ts:55~87 buildScenarioCurve` 가 채움 (plan 따라잡는 좌표).
  2. `ReportDetail.site_summary_text: string \| null \| undefined` — Optimizer LLM site narrative (룰베이스 fallback 대체) (`web/lib/fixtures.ts:60`, `/api/mock/report/[date]/route.ts:24,49`).
  3. `ForecastChart` props `scenarios?: Partial<ScenarioSet>` — 우상 추적성 메타 + 3 행 비교 table 의 데이터 소스 (`web/app/components/charts/ForecastChart.tsx:29`).
  4. `ForecastChart` props `reportDate?: string` — 기준일 메타 + 현황 행 라벨 (line 31).
  5. `ForecastChart` props `aiAdvice?: Array<{wp_name, trade, diagnosis?, recommendations}>` + `aiSummaryText?: string \| null` — LLM 권고 카드 × 3 + 본문 narrative (line 33~40).
- ★ CHG (의미 변경): `ScenarioPoint.delta_completion_days` — 이전 cycle "+N 일 지연 / -N 일 단축" → 본 cycle "항상 0" (catch-up 후 plan 동행, `web/lib/diagnosis.ts:138/145/152`).

### §A 발견된 패턴

- **per-person 단위 4 필드 (display_label/perperson/perperson_unit + value/baseline) 가 ReportKpi · BarItem · QuadrantPoint · WPSummaryRow 에 동형 반복** — BE 가 wv-median 외 단순 mean / 인당 원본 단위 동시 전달. FE 는 모두 `?` optional 로 받음, 미전달 시 % 표시 fallback.
- **`scenarios` 가 2 위치에 존재** — (a) `ReportDetail.scenarios.site` (BE `Partial<ScenarioSet>` — 4 시나리오 expected_completion + recovery_days + case_count + delta_days), (b) `ProductivityDiagnosis.scenarios.{optimistic/base/pessimistic}` (FE diagnose 산출 `ScenarioPoint` — curve + catch_up + delta_completion_days). 전자가 후자의 `recovery_days_*` 입력 (`web/lib/diagnosis-adapter.ts:29~31`, optimistic_p25 → p75, pessimistic_p75 → p25 매핑 주의).
- **enum 닫혀있음** — `Status` 4 / `Persona` 2 / `AgentStatus.group` 2 / `AgentStatus.state` 3 / `DailyRun.status` 3 / `AgentProgress.unit` 3 / `ChatMessage.type` 4 / `WBSNode.type` 3 / `ReviewItem.status` 2 / `QuadrantPoint.quadrant` 4 / `AgentTaskItem.status` 5 / `ConsolidatedReportSummary.status` 2 / `SheetTab` 4 / `DiagStatus` 3 / `DailyTask.status` 3. 신규 값은 FE switch + Record<> 수정 동반.
- **`forecast` 필드가 SCurvePoint 의 optional 추가 키로 BE 에서 채워짐** — type 라인 164 `forecast?: number` 명시. `ForecastChart.tsx:72` 에서 `(p as any).forecast` 캐스팅 사용 (타입에 있어도 spread 가 any 처리됨).
- **`SCurvePoint.actual` sparse hole 가능** — `diagnose()` 의 `todayIdx` 산출이 **역순 탐색** (`web/lib/diagnosis.ts:104~109`). 단순 `findIndex(undefined)` 사용 금지. ★ 단 `ForecastChart.tsx:88~89` 의 `firstUndef`/`lastIdx` 는 정순 `findIndex(actual===undefined)` — sparse hole 있는 경우 diagnose() todayIdx 와 불일치 가능 (E 섹션 참조).
- **catch-up 모델 도입으로 `delta_completion_days` 가 항상 0** — `diagnose()` 의 모든 시나리오 `delta_completion_days: 0` (line 138/145/152). plan 동행 의미상 plan 완공일과 동일. (이전 cycle 의 의미와 다름 — ★ CHG, RecoveryEtaCard 가 이 값을 "+N 일 지연" 로 표시함, 호출처 없어 dead 됐는지 확인 필요.)
- **`DailyRun` / `AgentProgress` 는 legacy** — type 은 남아있고 `FixtureMap.agent_tasks` 가 reference 하지만, `/api/mock/agent-tasks` 가 `DailyTask` / `AgentStageProgress` 로 swap 후 호출처 없음. data/mock_agent_tasks.json 의 `daily_runs` / `progress_by_date` 는 더 이상 로드되지 않음.

---

## §B — Mock fixture 인벤토리

> 경로: `web/lib/fixtures.ts:86 DATA_DIR = path.join(process.cwd(), "..", "data")` (web/ cwd 기준 부모 `data/`).
> 실측: `python3 -c "import json; ..."` 직접 파싱.

| Fixture name | data/ file | Type | Sample row count | 본 cycle 실 로드 |
|---|---|---|---|---|
| sites | data/mock_sites.json | `Site[]` | 6 sites (1 real PoC `m15x-ph3-ibl` is_mock=false + 5 mock preview). 실 PoC row 인용: `productivity_today: 88`, `delay_days: 14`, `recovery_days: 9`, `expected_completion: "2026-08-12"`, `headcount: 65`, `hours_saved: 221`, `fte_saved: 1.6` | ✅ /api/mock/dashboard 가 그대로 반환 |
| sites_summary | data/mock_sites_summary.json | `SitesSummary` | 1 obj (12 scalar). 실측: `today_count: 87`, `review_pending: 12`, `abnormal_count: 1`, `last_updated: "09:12"`, `total_hours_saved: 2155`, `total_fte_saved: 15.4`, `total_headcount: 445`, `total_hours: 62300`, `ai_replacement_rate: 3.46`, `yearly_saving: 203`, `total_processed: 1247`, `total_hours_saved_cum: 12840` | ❌ home/page.tsx 가 `loadReal("sites_summary")` PG SELECT 사용 (fixtures.ts:105~176) |
| agent_status | data/mock_agent_status.json | `AgentStatus[]` | 7 agents (step 1..7) | ❌ home/page.tsx 가 `loadReal("agent_status")` 사용 (fixtures.ts:178~215, AGENT_META 7 종 × pipeline_runs.current_node 매칭) |
| agent_tasks | data/mock_agent_tasks.json | `{ daily_runs: DailyRun[]; progress_by_date: Record<string, AgentProgress[]> }` | 7 daily_runs + 2 dates progress | ❌ (legacy) `/api/mock/agent-tasks` 는 PG `pipeline_runs` + `parser_activities` 단일 CTE SELECT → `DailyTask[]` shape 반환. `daily_runs` / `progress_by_date` 호출처 없음 |
| chat_sequence | data/mock_chat_sequence.json | `Record<string, ChatMessage[]>` | 1 date (2026-05-15) × 8 msgs (Collector, Parser, Mapper, SKEP Manager, Atomizer, Exporter, Forecaster, Optimizer) | ❌ home/page.tsx 가 `loadReal("chat_sequence")` → `deriveChatSequence(run_id)` 사용 (fixtures.ts:217~235) |
| review_cards | data/mock_review_cards.json | `ReviewItem[]` | 13 cards. 실측 첫 행: `bp_name: "A건설"`, `quantity: 320`, `unit: "㎡"`, `confidence: 0.87`, `ai_mapped_wp_id: "wp-3-3-19"`, `status: "unconfirmed"`. | ❌ /api/mock/review 는 PG `mapper_activities` JOIN `parser_activities` LEFT JOIN, LIMIT 300, `requires_review = TRUE`, `trade IN ('건축','토목')`, `today_qty > 0` |
| wbs_tree | data/mock_wbs_tree.json | `WBSNode` | 1 root (3 레벨 — type/name/parent_id/review_count/status/children) | ❌ /api/mock/review 가 `wbsTreeBuild(siteId)` 로 PG `activity_master` CTE 빌드 (4 레벨 트리) |
| report | data/mock_report.json | `{ daily; details }` | 5 daily + 1 detail | ❌ /api/mock/report (list 4 필드만) + /api/mock/report/[date] (9 jsonb + site_summary_text) 가 PG `daily_reports` JOIN |
| dashboard | data/mock_dashboard.json | `DashboardFixture` | `performance.fleet_kpi {avg_productivity:95, avg_delay:4, abnormal_total:1, recoverable_days:3}` (PG swap 됨), `impact.fleet_kpi` (SitesSummary, `total_processed`/`total_hours_saved_cum` 누락), `impact.site_distribution` 6 site, `impact.monthly_trend` 5 month, `per_site_automation` 1 site | ⚠️ partial — performance 는 PG (`loadReal("dashboard_performance")` 530 일 평균 + 60 일 trend + 30 일 sparkline), impact 는 fixture 그대로 |
| simulation | data/mock_simulation.json | (dict `home`/`tasks`/`report`/`dashboard`) | shape 이 `SimulationSequence` type 과 불일치 (type 키: `home_now_strip` / `agent_card_status` / `chat_log`) | ❌ dead — `loadFixture("simulation")` 호출처 grep 0 건 |

총 fixture **10 (이전 cycle 동일)**. 단 본 cycle 실 로드되는 fixture 는 dashboard.impact + sites 만. 8 fixture 는 PG SELECT 로 swap. 본 cycle 변경: fixture 자체 추가/제거 없음.

### §B 발견된 패턴

- **fixture → PG swap 거의 완료** — `loadReal()` (fixtures.ts:99) 가 sites_summary / agent_status / chat_sequence / dashboard_performance 4 종을 PG 로 채움. `/api/mock/*` 7 route 중 dashboard 만 partial fixture (impact), 나머지는 100% PG SELECT.
- **`CPIA_DEMO_FALLBACK=on` env 가 mock 토글** — 모든 PG SELECT 에서 `WHERE is_mock = ${useMock}` 분기. off 면 실 PoC 데이터 (`m15x-ph3-ibl` 530 일치) 만, on 이면 synthetic mock row 만 보임. wbsTreeBuild 의 `sites.is_mock = FALSE` 는 항상 real (실 site_id 식별).
- **`simulation` fixture dead** — JSON 키 (`home`/`tasks`/`report`/`dashboard`) 와 type 키 불일치, 호출처 0 건. 다음 cycle 에 둘 중 하나 정리.
- **`mock_sites_summary.json` 의 headcount/hours/yearly_saving 와 PG `loadReal("sites_summary")` 산출은 다름** — PG 분기에서 `yearly_saving: 0` 고정 (line 172), `total_headcount` 는 sites.is_mock=true 합계. PG 분기와 fixture 가 값 정합 X — `CPIA_DEMO_FALLBACK` 토글 시 UI 숫자 점프.

---

## §C — UI consumer 매핑 (페이지 × 컴포넌트 × field × UI element)

> File:line 은 destructure / JSX 사용 라인. ★ NEW = 본 cycle 신규 또는 시그니처 변경.

### C-0. Data fetch 진입점 표

| Page | URL | Component fetch | Receives type | Source |
|---|---|---|---|---|
| home | /home | `loadReal("sites_summary")` server-side | `SitesSummary` | web/app/(app)/home/page.tsx:11 |
| home | /home | `loadReal("agent_status")` server-side | `AgentStatus[]` | web/app/(app)/home/page.tsx:12 |
| home | /home | `loadReal("chat_sequence")` server-side | `Record<string, ChatMessage[]>` | web/app/(app)/home/page.tsx:13 |
| ★ NEW tasks | /tasks (list) | `fetch("/api/mock/agent-tasks")` | `{ tasks: DailyTask[] }` (list-only, 1 년 윈도우) | web/app/(app)/tasks/page.tsx:31 |
| ★ NEW tasks | /tasks (per date) | `fetch("/api/mock/agent-tasks/${date}")` | `{ stages: AgentStageProgress[]; items: Record<string, AgentTaskItem[]> }` | web/app/(app)/tasks/page.tsx:50 |
| review | /review | `fetch("/api/mock/review")` | `{ wbs: WBSNode; cards: ReviewItem[] }` | web/app/(app)/review/page.tsx:16 |
| ★ NEW reports | /reports (list) | `fetch("/api/mock/report")` | `{ daily: ReportDaily[] }` (list-only 4 필드, ~50KB) | web/app/(app)/reports/page.tsx:40 |
| ★ NEW reports | /reports (per date) | `fetch("/api/mock/report/${date}")` | `ReportDetail` (9 jsonb + site_summary_text) | web/app/(app)/reports/page.tsx:57 |
| export | /export (list) | `fetch("/api/mock/consolidated")` | `ConsolidatedReportSummary[]` (1 년 윈도우) | web/app/(app)/export/page.tsx:17 |
| export | /export (per date) | `fetch("/api/mock/consolidated?date=...")` | `ConsolidatedReport` | web/app/(app)/export/page.tsx:29 |
| dashboard | /dashboard | `fetch("/api/mock/dashboard")` | `{ sites: Site[]; dashboard: DashboardFixture }` | web/app/(app)/dashboard/page.tsx:14 |
| (landing) | / | (정적, fetch 없음) | — | web/app/(landing)/page.tsx |

### C-1. Home (`/home`) — server component (SSR)

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| home | (page server) | web/app/(app)/home/page.tsx:11~13 | `loadReal()` 3 종 server fetch | SSR composition |
| home | (page) | web/app/(app)/home/page.tsx:18 | `agents.reduce((s,a)=>s+a.active_count,0)` | `processingNow` → OpsKpiCard "현재 처리 중" value |
| home | StatusHeader | web/app/components/home/StatusHeader.tsx:9, 38 | `summary.last_updated` | "LIVE · 마지막 동기화 Ns 전 (HH:MM)" 우상 chip |
| home | OpsKpiCard (× 4) | web/app/components/home/OpsKpiCard.tsx:28~62 | `tone/icon/label/value/unit/description/live` | rounded-card 4 칸 |
| home | (page) | web/app/(app)/home/page.tsx:30 | `summary.total_processed.toLocaleString()` | OpsKpiCard "누적 처리" value |
| home | (page) | web/app/(app)/home/page.tsx:38 | `summary.today_count.toLocaleString()` | OpsKpiCard "오늘 처리" value |
| home | (page) | web/app/(app)/home/page.tsx:46 | `summary.total_hours_saved_cum.toLocaleString()` | OpsKpiCard "누적 절감" value (h) |
| home | (page) | web/app/(app)/home/page.tsx:54 | `processingNow.toString()` | OpsKpiCard "현재 처리 중" (live) |
| home | AgentWorkflow | web/app/components/home/AgentWorkflow.tsx:74~106 | `agents: AgentStatus[]` 전체 | 세로 워크플로 7 카드 + HIL 끼움 (HILS[0] afterStep=3) |
| home | AgentWorkflow→AgentRow | web/app/components/home/AgentWorkflow.tsx:137~187 | `agent.step/name/korean_name/description/model/state` + `COUNTS[step]` 하드코딩 (line 30~38) | STEP 라벨 + icon + 이름/한글/설명 + 대기/오늘/누적 + state dot |
| home | AgentWorkflow→HilRow | web/app/components/home/AgentWorkflow.tsx:189~226 | `HILS[0]` 하드코딩 (afterStep:3, waiting:3, title "Mapping Review") | 점선 brand 보더 카드 |
| home | AgentChatLog | web/app/components/tasks/AgentChatLog.tsx:37~76 | `messages: ChatMessage[]` → `useSequence(messages, 1500)` reveal | 우측 chat 패널 (h-720px) |
| home | AgentChatLog→ChatBubble | web/app/components/tasks/AgentChatLog.tsx:86~155 | `m.agent/type/summary/detail/ts` + `AGENT_META[agent]` (8 agent — Collector/Parser/Mapper/Atomizer/Exporter/Forecaster/Optimizer + SKEP Manager) | avatar + bubble (좌/우 — human_action=우측 brand, hil_request=sun highlight) |
| home (dead) | NowStrip | web/app/components/home/NowStrip.tsx:11~45 | (legacy, 미사용) | 4 칸 NOW strip |
| home (dead) | Hero | web/app/components/home/Hero.tsx:36~69 | (하드코딩 HeroStat 4 종 — 2155h / 15.4명 / D-14 / 3~7일) | hero 카드 |
| home (dead) | HilReviewStage | web/app/components/home/HilReviewStage.tsx:1~31 | (정적) | HIL 단일 카드 |
| home (dead) | AgentCard | web/app/components/home/AgentCard.tsx:12~46 | (AgentWorkflow 가 대체) | 미 import |

### C-2. Agent Tasks (`/tasks`) — client component + 2-stage fetch

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| ★ NEW tasks | (page) | web/app/(app)/tasks/page.tsx:30~37 | list-only fetch → `tasks: DailyTask[]` | 첫 항목 자동 선택 |
| ★ NEW tasks | (page) | web/app/(app)/tasks/page.tsx:39~61 | per-date fetch → `{stages, items}` + `pickCurrentAgent(stages)` (waiting_hil 우선 → 미완 → 마지막) | 캐시 (`detailCacheRef`) 로 재진입 즉답 |
| tasks | DailyTaskList | web/app/components/tasks/DailyTaskList.tsx:20~80 | `tasks[].date/total_count/progress_percent/status/has_anomaly` | 좌측 일별 버튼 + bar (review_pending=sun / has_anomaly=rose / else=mint) + % + status icon (Pause/Loader/Check) |
| tasks | DailyTaskList | web/app/components/tasks/DailyTaskList.tsx:13~18 | `tasks.reduce ...` (총 접수/처리/완료율 헤더 산출) | 좌측 헤더 "접수 N건 · 처리 N건 · 완료율 N%" |
| ★ NEW tasks | AgentWorkflowList (★ +33 라인) | web/app/components/tasks/AgentWorkflowList.tsx:56~170 | `stages: AgentStageProgress[]`, `selectedAgent`, `onSelect` | 중앙 8 단계 stage 카드 (1..7+HIL=3.5), 현재 단계 라벨, HIL waiting 우선 |
| ★ NEW tasks | AgentWorkflowList | web/app/components/tasks/AgentWorkflowList.tsx:82~157 | `s.agent/step/is_hil/received/processed/percent/waiting_hil` + DESCRIPTION/KOREAN/STEP_ICON map | icon + STEP/HIL 라벨 + 접수/처리/% + description + progress bar (waiting_hil=sun / else=mint) |
| tasks | AgentTaskItemList | web/app/components/tasks/AgentTaskItemList.tsx:20~83 | `items: AgentTaskItem[]`, `stage: AgentStageProgress` | 우측 단계별 건 table (ID/공종/BP사/상태) |
| tasks | AgentTaskItemList | web/app/components/tasks/AgentTaskItemList.tsx:12~18 | `STATUS_META[it.status]` (5 종 — done/processing/received/hil_pending/blocked) | 상태 chip + icon |
| tasks (legacy) | AgentProgressList / DailyRunList | (삭제됨) | — | 이전 cycle, AgentWorkflowList / DailyTaskList 가 대체 |

### C-3. Human Review (`/review`) — client component

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| review | (page) | web/app/(app)/review/page.tsx:15~22 | `fetch("/api/mock/review")` → `{wbs, cards}` | client fetch + state |
| review | (page) | web/app/(app)/review/page.tsx:24~47 | `wbs/cards/selectedNodeId/onlyUnconfirmed` | `visibleCards` 메모 — WP 하위 카드만 + unconfirmed 필터 |
| ★ NEW review | WBSTree (★ +48 라인) | web/app/components/review/WBSTree.tsx:31~127 | `root: WBSNode`, `selectedId`, `onSelect`, `onDrop` | 좌측 트리 (4 레벨 — root/wa/disc/wp). `INDENT_STEP` 깊이별 indent, `LEVEL_TEXT` 깊이별 typo (text-body-sm.bold → text-xs.text-ink-mid) |
| review | WBSTree→Branch | web/app/components/review/WBSTree.tsx:59~127 | `node.children/.status/.name/.review_count/.total_count/.type` | 행 expand/collapse + drop target (WP만) + AlertCircle (review_count>0) + total_count 수치 |
| review | ReviewCard | web/app/components/review/ReviewCard.tsx:15~111 | `item: ReviewItem`, `wbsRoot`, `onConfirm`, `onRemap` | 카드: 상태 chip + bp_name + quantity/unit + work_content + ai_mapped_path + confidence% + alternative_wps + 확정/수정 버튼. draggable (unconfirmed만) |
| review | WPSearchCombobox | web/app/components/review/WPSearchCombobox.tsx:18~73 | `wbsRoot → flatten WPs` (work_package leaf 만), `currentWpId`, `onSelect(wpId, path)` | 검색 input + 자동완성 ul (최대 12) |
| review | (page) | web/app/(app)/review/page.tsx:49~59 | `handleConfirm/handleRemap/handleConfirmAll` 3 액션 | optimistic state update (server save 없음, mock) |
| review | (page) | web/app/(app)/review/page.tsx:113~122 | 확정 버튼 — `confidence ≥ 0.8 && unconfirmed` 일괄 confirm | "모두 AI 추천대로 확정" 버튼 |

### C-4. Report (`/reports`) — client component + 2-stage fetch

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| ★ NEW reports | (page) | web/app/(app)/reports/page.tsx:39~46 | list fetch → `daily: ReportDaily[]` (4 필드만, 50KB) | 첫 항목 자동 선택 |
| ★ NEW reports | (page) | web/app/(app)/reports/page.tsx:49~67 | per-date fetch → `ReportDetail` (9 jsonb + site_summary_text) | `detailCacheRef` 캐시 |
| reports | (page) | web/app/(app)/reports/page.tsx:69~86 | `wp_summary` → impact desc filter (status='risk' > 'caution' > 첫 row > default_wp_id) | `selectedWpId` 자동 picking |
| reports | (page) | web/app/(app)/reports/page.tsx:91~99 | `daily` 530 일 desc → `selectedDate` 기준 -89~0 window | `trend90` slice → ProductivityTrendChart |
| ★ NEW reports | (page) | web/app/(app)/reports/page.tsx:102~105 | `filterAndPickBars(detail.trade_bars).map(b=>b.label)` | `visibleTrades` — WP 표 필터 |
| reports | (page) | web/app/(app)/reports/page.tsx:107~122 | `diagnose(toDiagnosisInput(...))` + BE `scenarios.site.{p25,p50,p75}_recovery_days` overlay | `diagnosis` memo |
| reports | ReportDailyList | web/app/components/reports/ReportDailyList.tsx:12~60 | `daily[].date/status/productivity_today/delay_days/recovery_days` | 좌측 sticky 패널 (상단 "총 N개 리포트 생성됨") |
| reports | ProductivityTrendChart | web/app/components/charts/ProductivityTrendChart.tsx:26~131 | `trend: {date,value}[]`, `todayValue`, `endDate` | 90 일 area chart + 현장 평균 ReferenceLine + todayDot + gapChip |
| reports | ProductivityBarToggle | web/app/components/reports/ProductivityBarToggle.tsx:58~130 | `contractorBars/tradeBars/historyMean/date` | toggle (업체별/공종별) + 평균 미만 카운트 + BarChartH (vertical, baseline gradient blue/rose) |
| reports | ProductivityBarToggle | web/app/components/reports/ProductivityBarToggle.tsx:61~64 | `filterAndPickBars(...)` (bar-filters.ts) | items 가공 (150% 초과 제거 + top3+bot7, 최대 10) |
| reports | QuadrantCountKpi | web/app/components/reports/QuadrantCountKpi.tsx:13~26 | `points: QuadrantPoint[]`, `filter`, `onFilterChange` | 3 chip (위험 rose / 경고 sun / 안전 mint = safe+watch) + counts + 토글 |
| reports | QuadrantScatter | web/app/components/charts/QuadrantScatter.tsx:14~63 | `points`, `selectedWpId`, `onSelect`, `filter` | recharts ScatterChart (X=Productivity reversed, Y=Impact, Z=size) + 4 ReferenceArea (risk/caution/watch/safe) + 70 ReferenceLine 가로/세로 |
| reports | WPSummaryTable | web/app/components/reports/WPSummaryTable.tsx:35~108 | `rows: WPSummaryRow[]`, `selectedWpId`, `onSelect` | sticky table — wp_name/trade/bp_name/Impact/Productivity/공기단축/Status |
| reports | WPSummaryTable | web/app/components/reports/WPSummaryTable.tsx:29~33 | `recoveryDays(productivity, baseline, impact)` 산식 = `round((baseline−productivity)/100 × impact × 0.3)` (PoC 상수) | 행별 "공기 단축 -N일" 셀 |
| reports | (page inline WP detail) | web/app/(app)/reports/page.tsx:208~244 | `wp_row.wp_name/trade/status` + `recoveryDays(...)` | 우측 상단 단일 행 (WP 이름 + 공기 단축 + 상태 chip) |
| reports | OptimizerResult | web/app/components/reports/OptimizerResult.tsx:8~60 | `output: OptimizerOutput` (`optimizer.by_wp[selectedWpId]` 또는 `default_wp_id` 또는 EMPTY) | 4 섹션 카드 (진단/유사사례/권고/상세) |
| ★ NEW reports | ForecastChart (★ +4 props) | web/app/components/charts/ForecastChart.tsx:48~526 | `diagnosis`, `recoveryActive`, `delayDays`, `recoveryDays`, ★ `scenarios?`, ★ `reportDate?`, ★ `aiAdvice?`, ★ `aiSummaryText?` | 메인 추세 차트 (h-340) |
| ★ NEW reports | ForecastChart | web/app/components/charts/ForecastChart.tsx:215~224 | 4 Line: planned(회색 #94a3b8 실선) + actual(검정 #0d1117 굵음) + forecast(빨강 #ef4444 dashed) + base(mint #0ea76a dashed, catch-up + plan 동행) | 4 선 추세 차트 |
| ★ NEW reports | ForecastChart | web/app/components/charts/ForecastChart.tsx:241~292 | ReferenceDot 3 종: planEnd(회색 top) + noActionEnd(빨강 bottom, D+N) + baseCatchUp(mint top) | 마커 분산 — 라벨 겹침 회피 |
| ★ NEW reports | ForecastChart | web/app/components/charts/ForecastChart.tsx:137~170 | 추적성 메타 (기준일/계획 완공/현황 D+N/AI Nd 만에 따라잡음) | 우상 dl 박스 |
| ★ NEW reports | ForecastChart | web/app/components/charts/ForecastChart.tsx:299~373 | 3 행 비교 table (현황/플랜/AI 시나리오 + 완공 예정일) | 차트 아래 요약표 |
| ★ NEW reports | ForecastChart | web/app/components/charts/ForecastChart.tsx:375~422 | `aiSummaryText` (LLM site_summary) → 본문 narrative; 없으면 `situationNarrative+outlookNarrative` 룰베이스 | "현황 요약" 본문 |
| ★ NEW reports | ForecastChart | web/app/components/charts/ForecastChart.tsx:389~421 | `aiAdvice[].wp_name/trade/diagnosis?/recommendations[]` (impact desc 상위 3, cold_start 제외) | "AI 권고" 리스트 (wp 카드 × 3, recommendations 최대 2) + 푸터 (`scenarios.base_p50.case_count` 건 기반) |
| reports | (page) | web/app/(app)/reports/page.tsx:270~295 | `wp_summary` impact desc 상위 3 → `optimizer.by_wp[wp_id].diagnosis/recommendations` (cold_start 제외) | `aiAdvice` 산출 inline 후 ForecastChart 에 전달 |
| reports (dead) | RawDataTab (PR — `filterWpId/wpNameById` props 추가) | web/app/components/reports/RawDataTab.tsx:18~112 | `rows: RawDataRow[]`, `filterWpId?`, `wpNameById?` (현재 reports page 미연결) | 9 컬럼 table + 검색 + WP filter + CSV 내보내기 |
| reports (dead) | RecoveryEtaCard / GapKpiCard / SpiBandChart / SCurveChart / ScenarioLegend / ConfidenceBadge | various | (이전 cycle) | 호출처 0 — ForecastChart 가 대체 |

### C-5. Export (`/export`) — client component + 2-stage fetch

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| export | (page) | web/app/(app)/export/page.tsx:16~32 | list + per-date fetch | 첫 항목 자동 선택, 일자 변경 시 단건 fetch |
| export | ExportDailyList | web/app/components/export/ExportDailyList.tsx:12~75 | `list[].date/status` | 좌측 일자 리스트 + "ready/draft" chip + icon (ready=mint Check, draft=ink-light Pause) |
| export | ConsolidatedReportCard | web/app/components/export/ConsolidatedReportCard.tsx:27~128 | `report: ConsolidatedReport` 전체 | 메인 카드 + 4 tab + Export 버튼 |
| export | ConsolidatedReportCard | web/app/components/export/ConsolidatedReportCard.tsx:38~59 | `handleExport()` — `/sample/cpia-consolidated-report.xlsx` mock 다운로드 (1.5s toast) | Export 버튼 |
| export | ConsolidatedReportCard | web/app/components/export/ConsolidatedReportCard.tsx:67~70 | `counts.output_manpower` (`report.sheet_row_counts`) | 헤더 "{date} 통합 작업일보 · pjt · {N}건을 4 시트로 통합" |
| export | SheetTable (× 4) | web/app/components/export/SheetTable.tsx:26~81 | `cols: SheetColumn<T>[]`, `rows: T[]` | 제네릭 table (sticky thead, align, format, cellClass) |
| export | SheetTable / OUTPUT_MANPOWER_COLS | web/app/components/export/SheetTable.tsx:86~95 | `OutputManpowerRow` 8 컬럼 (PJT/Zone/공종/BP사/Scope/전일/금일/명일) | 1. 작업사항 시트 |
| export | SheetTable / OCCUPATION_COLS | web/app/components/export/SheetTable.tsx:97~110 | `OccupationManpowerRow` 12 컬럼 | 2. 직종별 인원현황 시트 |
| export | SheetTable / EQUIPMENT_COLS | web/app/components/export/SheetTable.tsx:112~125 | `EquipmentRow` 12 컬럼 | 3. 장비현황 시트 |
| export | SheetTable / QUANTITY_COLS | web/app/components/export/SheetTable.tsx:127~138 | `QuantityRow` 10 컬럼 (`total_a` / `prev_cum_b` / `today_c`) | 4. 물량 시트 |

### C-6. Dashboard (`/dashboard`) — client component

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| dashboard | (page) | web/app/(app)/dashboard/page.tsx:13~17 | `fetch("/api/mock/dashboard")` → `{sites, dashboard}` | Tabs (Performance / Impact) |
| dashboard | PerformanceTab | web/app/components/dashboard/PerformanceTab.tsx:21~71 | `sites: Site[]`, `fleetKpi`, `fleetTrend?`, `siteSparklines?`, `endDate?` | 3 단 컬럼 |
| dashboard | PerformanceTab | web/app/components/dashboard/PerformanceTab.tsx:30~35 | `fleetKpi.avg_productivity/avg_delay/abnormal_total/recoverable_days` | KpiStrip 4 칸 |
| dashboard | FleetProductivityTrendChart | web/app/components/dashboard/FleetProductivityTrendChart.tsx:32~133 | `sites/endDate/historyMean/fleetTrend?/siteSparklines?/daysWindow=90` | 90 일 면적(min~max 밴드) + 평균 line + 이력 평균 ReferenceLine + todayDot |
| dashboard | FleetProductivityTrendChart | web/app/components/dashboard/FleetProductivityTrendChart.tsx:40~48 | `fleetTrend` 우선, 없으면 `siteSparklines` → `buildFleetTrend()` (`web/lib/fleet-trend-mock.ts:43~69`) | 시연 안정성 — fallback chain |
| dashboard | SiteOverviewCard (× 6) | web/app/components/dashboard/SiteOverviewCard.tsx:22~140 | `site: Site`, `sparkline?: number[]` | 카드: status stripe + 이름/위치 + 생산성/공기 + sparkline + 이상 chip + is_mock 시 grayscale + preview Dialog |
| dashboard | ImpactTab (scope="fleet") | web/app/components/dashboard/ImpactTab.tsx:14~65 | `summary: SitesSummary`, `distribution`, `trend`, `scope` | KpiStrip 4 칸 + 연간 환산 강조 + HorizontalBarList + TrendLineChart |
| dashboard | ImpactTab | web/app/components/dashboard/ImpactTab.tsx:32~38 | `summary.yearly_saving/total_fte_saved` | "★ 연간 환산 효과" 배너 |
| dashboard | HorizontalBarList | web/app/components/dashboard/HorizontalBarList.tsx:13~36 | `items[].label/value/meta`, `unit`, `title?` | 가로 bar 리스트 (max 정규화) |
| dashboard | TrendLineChart | web/app/components/charts/TrendLineChart.tsx:16~42 | `points: {month,value}[]`, `unit`, `valueLabel?` | 월별 area chart (gradient) |

### C-7. Landing (`/`) — static

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| (landing) | LandingNav | web/app/components/landing/LandingNav.tsx (35) | (정적) | 상단 nav |
| (landing) | LandingHero | web/app/components/landing/LandingHero.tsx (130) | (정적) | hero |
| (landing) | BackgroundSection | web/app/components/landing/BackgroundSection.tsx (305) | (정적) | 배경 섹션 |
| (landing) | AsIsToBeSection | web/app/components/landing/AsIsToBeSection.tsx (124) | (정적) | AS-IS/TO-BE |
| (landing) | CoreAiSection | web/app/components/landing/CoreAiSection.tsx (356) | (정적) | core AI |
| (landing) | ImpactSection | web/app/components/landing/ImpactSection.tsx (247) | (정적) | impact |
| (landing) | ScalabilitySection | web/app/components/landing/ScalabilitySection.tsx (107) | (정적) | 확장성 |
| (landing) | FinalCtaSection | web/app/components/landing/FinalCtaSection.tsx (42) | (정적) | CTA |
| (landing) | LandingFooter | web/app/components/landing/LandingFooter.tsx (11) | (정적) | 푸터 |

### C-8. 공통 layout

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| 전 (app)/* | TopBar | web/app/components/TopBar.tsx:6~34 | (정적) | sticky 상단 (CPIA 로고 + NotificationBell + UserMenu) |
| 전 (app)/* | Sidebar | web/app/components/Sidebar.tsx:38~143 | `usePersona`, `useUiStore` | 좌측 nav (Main Menu × 4 + Analysis × 2, persona 별 visibility — manager 만 dashboard) |
| 전 (app)/* | PersonaToggle | web/app/components/PersonaToggle.tsx:11~66 | `usePersona` | member/manager 토글 (compact = 단일 아이콘) |
| 전 | NotificationBell | web/app/components/NotificationBell.tsx:16~141 | `MOCK_NOTIFS` 3 건 하드코딩 (warning/danger/info) | bell + red dot + 드롭다운 |
| 전 | UserMenu | web/app/components/UserMenu.tsx:8~143 | `USERS[persona]` 2 명 하드코딩 (김 현장 / 이 본부) | user avatar + 드롭다운 (프로필/환경설정/로그아웃) |

### §C 발견된 패턴

- **2-stage fetch (list + per-date) 가 본 cycle 표준** — reports / tasks / export 가 모두 list 만 먼저 받고, selectedDate 변경 시 detail fetch + 메모리 캐시. 이전 cycle 의 단일 fixture (32MB) → 50KB + on-demand.
- **`detailCacheRef` Map 으로 같은 date 재방문 즉답** — reports/page.tsx:36, tasks/page.tsx:27. cancelled flag (line 49/64) 로 race 방지.
- **Home 만 server component (SSR)** — `loadReal()` 직접 호출. 나머지 5 화면은 client component + `useEffect+fetch`. demo 시연 안정성 우선.
- **`useSequence` (use-simulation.ts) 가 본 cycle 에서 chat 외 1 곳 더 활용** — `web/app/components/tasks/AgentChatLog.tsx:38` 가 유일 호출처. `useSimulation` 은 dead component (`home/AgentCard`, `home/NowStrip`) 에만 잔존.
- **mock 하드코딩 3 곳 잔존** — `web/app/components/home/AgentWorkflow.tsx:30 COUNTS` (step → 대기/오늘/누적), `NotificationBell.tsx:16 MOCK_NOTIFS` (3 건), `UserMenu.tsx:8 USERS` (member/manager 2 인). BE 전환 시 별도 endpoint 필요.
- **WBSTree 가 본 cycle 에서 4 레벨 (root/wa/disc/wp) 명시 + 깊이별 typo/indent + total_count 표시** — 이전 cycle 의 단순 3 레벨에서 +48 LOC (`INDENT_STEP`, `LEVEL_TEXT`, `indentPx`, `levelTextClass`).
- **`aiAdvice` 산출 inline** — reports/page.tsx:270~295 에서 `wp_summary` impact desc 상위 3 → `optimizer.by_wp[wp_id]` 의 `diagnosis`/`recommendations` 추출 (cold_start 제외, recommendations 가 객체이면 `r.text` 또는 string 분기). ForecastChart 가 받아 카드 렌더.
- **AgentWorkflowList 의 step=3.5 가 trick** — sort 시 자연수처럼 끼움. `AgentStageProgress.step` 이 `number` 라서 (`StringList` 아님) 정상 정렬. AgentWorkflow (home) 의 HILS afterStep 과는 별개 경로.
- **persona member 는 dashboard 미가시** — `MENU_VISIBILITY` (persona.ts:24~27) 가 정의. 직접 URL 진입 시는 별도 guard 없음 (페이지 fetch 그대로 동작).

---

## §D — Library functions (transforms / diagnosis / bar-filters / fleet-trend / etc.)

### D-1. `web/lib/diagnosis.ts` (177 lines) — FE 자체 진단 엔진

- 노출 함수 3 개 + 2 internal:
  - `statusFromZ(z)` (line 10) — |z|<1 normal / <2 caution / else risk.
  - `meanReversionRecovery(shortfall, mu, todayRate)` (line 17) — denom = mu − todayRate, p50 = shortfall/denom, p25 = 0.7·p50, p75 = 1.4·p50, denom ≤ 0 면 모두 Infinity.
  - `ewma(values, lambda)` (line 35, internal) — λ=0.3 호출.
  - **★ `buildScenarioCurve(s_curve, todayIdx, lastActual, recoveryDays)` (line 55, internal)** — catch-up + plan 동행 모델:
    - 1) catch-up 구간 (today ~ todayIdx+recoveryDays): lastActual → plan[catchUpEndIdx] 직선 slope
    - 2) catch-up 이후: `null` 반환 (plan 곡선이 그대로 그려짐)
    - 반환: `{ curve: (number|null)[], catchUp: {date, percent} | null }`
  - `diagnose(input)` (line 90) — 본 cycle 동작:
    - todayIdx 역순 탐색 (sparse hole 회피)
    - `recovery_days_p25/p50/p75` 전달 시 직접 사용, 없으면 meanReversion fallback. 매핑: BE p25/p50/p75 = 비관/기본/낙관 = pessimistic/base/optimistic.
    - 모든 시나리오 `delta_completion_days: 0` 고정 (plan 동행).
- 호출처:
  - `web/app/(app)/reports/page.tsx:109` (prod 진입)
  - `web/lib/__tests__/diagnosis.test.ts` (회귀 테스트)
- BE 연동 의미: `Forecaster` 가 `scenarios.site.{p25,p50,p75}_recovery_days` 보내면 FE 의 catch-up slope 결정 + ForecastChart `base` 라인 + `catch_up` 마커.

### D-2. ★ NEW `web/lib/bar-filters.ts` (12 lines)

- 노출 함수 1 개: `filterAndPickBars<T extends {value:number}>(items): T[]`
  - 150% 초과 제거 + value desc 상위 3 + asc 하위 7 = 최대 10 개.
  - spec `2026-05-21-cpia-ui-4-fixes-design.md §④` 출처.
- client-safe (transforms.ts 의 `postgres` import 회피).
- 호출처:
  - `web/app/components/reports/ProductivityBarToggle.tsx:62` — contractor/trade bar pre-filter.
  - `web/app/(app)/reports/page.tsx:104` — `trade_bars` filter 후 `visibleTrades` 추출 → WP table 동기.

### D-3. `web/lib/diagnosis-adapter.ts` (45 lines) — D-3 REVISED mock 영구

- 노출 함수 1 + helper 1:
  - `toDiagnosisInput(reportKpi, s_curve, siteId, scenariosSite?)` (line 16)
  - `deterministicSampleSize(siteId)` (line 37) — site_id FNV-1a 해시 → 12~48 균등.
- input → output 매핑:
  - `reportKpi.target_productivity` → `history_mean` (보통 97)
  - 고정 `4` → `history_std`
  - `reportKpi.productivity_today` → `today_progress`
  - BE `scenarios.site.{pessimistic_p75/base_p50/optimistic_p25}.recovery_days` → `recovery_days_{p25/p50/p75}` (★ 의미 inverse 주의 — p25=비관, p75=낙관)
  - `reportKpi.delay_days` → `delay_days`
- 호출처: `web/app/(app)/reports/page.tsx:109`.

### D-4. `web/lib/transforms.ts` (412 lines) — 8 transform 함수

| Function | LOC | Spec | 호출처 |
|---|---|---|---|
| `deriveProgressPercent(status, current_node)` | 13~28 | G1 — pipeline_runs status/current_node → 0..100. status=completed→100, waiting_hil_1→50, parser=20/mapper=30/atomizer=60/exporter=70/forecaster=80/optimizer=90 | `/api/mock/agent-tasks/route.ts:9, 61` |
| `deriveYearlySaving(fte, hours, hourlyRate=50000)` | 30~36 | G11 — yearly_saving (억) = fte×1.5 + (hours×50000)/1e8 | (호출처 없음 — fixture 가 yearly_saving 직접 포함, PG 분기는 0 고정) |
| `deriveItemStatus(stage, row)` | 38~59 | G12 — mapper_activities → AgentTaskItem status. risk_level=이상→blocked, Mapper 의 requires_review→hil_pending, conf≥0.7→done, ≥0.4→processing, else received | `/api/mock/agent-tasks/[date]/route.ts:8, 62` |
| `deriveWpIdAndPath(wa, l6_main, site_name)` | 61~71 | G17 — wp_id = `${kebab(wa)}-${kebab(l6_main)}` | `/api/mock/review/route.ts:11, 64, 91`, transforms.ts:302 |
| `deriveImpact(planTotalQty, planMhRev2, normMax=1e8)` | 73~81 | G18 — Quadrant impact (0..100) = clamp(qty×mh/normMax × 100) | (BE-side 산출, FE 호출처 없음) |
| `deriveStageProgress(date)` | 87~180 | G10 — 8 단계 진행률 (1..7+HIL=3.5), PG 단일 CTE SELECT (parser_reports / parser_activities / mapper_activities / mapping_corrections / daily_reports / forecasts / optimizer_advice 10 서브쿼리) | `/api/mock/agent-tasks/[date]/route.ts:8, 24` |
| `wbsTreeBuild(siteId, siteName?)` | 186~321 | G22 — 4 레벨 WBS 트리. CTE 3 종 (am_combos / review_agg / activity_agg / forecast_agg) JOIN. cartesian product 폭발 방지 (이전 LEFT JOIN 체인은 233× 폭발). riskToStatus: 1→risk / 2→caution / 3→normal / null→unknown | `/api/mock/review/route.ts:11, 28` |
| `deriveChatSequence(runId)` | 326~411 | G4 — pipeline_runs → 8 ChatMessage 시퀀스 (Collector~Optimizer, off=0/30/60/.../210s). hil_count>0 면 Mapper type=hil_request + Human Review type=human_action | `web/lib/fixtures.ts:4, 230` (`loadReal("chat_sequence")` 내부) |

### D-5. `web/lib/fixtures.ts` (295 lines)

- `loadFixture<K>(name)` (line 88) — `data/mock_{name}.json` 직접 읽기 (Node fs).
- `loadReal(name)` (line 99~295) — 4 케이스 PG SELECT (overload signature):
  - `"sites_summary"` (line 105~176) — pipeline_runs + sites + mapper_activities + forecasts 5 SELECT (오늘 처리/누적/리뷰 대기/이상/AI 대체율). `yearly_saving: 0` 고정.
  - `"agent_status"` (line 178~215) — AGENT_META 7 종 × pipeline_runs.current_node 매칭. `reporter` → `exporter` rename (line 203~205).
  - `"chat_sequence"` (line 217~235) — 최근 completed run → `deriveChatSequence(run_id)`.
  - `"dashboard_performance"` (line 237~290) — daily_reports.kpi_jsonb 530 일 평균 + 60 일 trend (mean/min/max 동일 — 실 site 1 개) + 30 일 sparkline.
- export type 5 종: `Scenario`, `ScenarioSet`, `OptimizerByWp`, `ReportDetail`, `DashboardFixture`.

### D-6. `web/lib/fleet-trend-mock.ts` (69 lines) — 결정적 mock 생성기

- 노출 함수 2 + 2 helper:
  - `hashString(s)` (line 5), `mulberry32(seed)` (line 14) — PRNG.
  - `generateSiteTrend(siteId, todayValue, days=90)` (line 24) — 90 일 random walk + 후반 30 일 감소 trend, 마지막 값 todayValue 강제.
  - `buildFleetTrend(perSite, endDate, days=90)` (line 43) — N 사이트 → mean/min/max FleetTrendPoint[]. endDate 기준 ISO 절대 날짜.
- 호출처: FleetProductivityTrendChart (line 16), SiteOverviewCard (line 6).

### D-7. `web/lib/persona.ts` (31 lines) — zustand persona store + MENU_VISIBILITY

- `usePersona` (default `manager`, `cpia-persona-v2` localStorage), `MENU_VISIBILITY` (`member` = home/tasks/review/export/reports, `manager` = + dashboard), `isMenuVisible(persona, menu)`.
- 호출처: Sidebar, PersonaToggle, UserMenu.

### D-8. `web/lib/pg.ts` (9 lines) — postgres BFF singleton

- `postgres` (npm `postgres` driver) 인스턴스. max:5, idle_timeout:30. `POSTGRES_URL` env.
- 호출처: transforms.ts, fixtures.ts, 모든 `/api/mock/*` route 6 종 (review/report/report[date]/agent-tasks/agent-tasks[date]/consolidated).

### D-9. `web/lib/ui-store.ts` (20 lines), `web/lib/use-simulation.ts` (49 lines), `web/lib/utils.ts` (10 lines) — UI helpers

- `useUiStore` — zustand `sidebarCollapsed` + persist `cpia-ui`.
- `useSimulation(seed, updater, ms)` — setInterval 으로 seed 갱신 (dead — NowStrip/AgentCard 만 사용).
- `useSequence(seq, ms)` — 1 step 씩 reveal (AgentChatLog 가 유일 호출처).
- `cn(...)` — clsx + tailwind-merge.

### D-10. `web/lib/__tests__/` — vitest 회귀

- `diagnosis.test.ts`, `diagnosis-adapter.test.ts`, `fixtures.test.ts`, `persona.test.ts`, `sanity.test.ts`, `use-simulation.test.ts`, `transforms.test.ts`. 본 cycle 전수 통과 가정 (직접 실행 미수).

---

## §E — 모호한 부분 / 의문점 / FE 단독 이슈

- **`mock_simulation.json` shape ≠ `SimulationSequence` type — 본 cycle 동일.** JSON 키 (`home`/`tasks`/`report`/`dashboard`) 와 type 키 (`home_now_strip`/`agent_card_status`/`chat_log`) 불일치, grep 호출처 0. 다음 cycle 에 둘 중 하나 정리.
- **★ `delta_completion_days: 0` 항상 0 — type 의미 변경** — `diagnose()` 가 catch-up 후 plan 동행 가정으로 모든 시나리오 `delta_completion_days = 0` 고정. `RecoveryEtaCard` (web/app/components/reports/RecoveryEtaCard.tsx:48 `formatDelta`) 는 이 값으로 "+N 일 지연 / -N 일 단축" 표시 — 호출처 grep 0 — dead 확정.
- **★ `RawDataTab` 의 `filterWpId/wpNameById` props 가 신설됐으나 reports/page.tsx 가 미연결** — 컴포넌트는 받을 준비 됐으나 호출 측이 안 보냄. 또한 `/api/mock/report/[date]/route.ts:50` 가 `raw_data: []` 빈 배열 반환 → 표 자체가 호출되어도 빈 상태. 다음 cycle 에 BE raw_data 채우기 + reports/page 에서 RawDataTab 호출 필요.
- **★ ForecastChart 내부 `firstUndef`/`lastIdx` 산출 (line 88~89) 이 `data.findIndex(actual===undefined)` 정순 → diagnose() 의 todayIdx 역순 탐색과 다름** — sparse hole 있는 경우 마지막 actual 점 식별 불일치 가능. lastPoint 가 ReferenceDot 위치 결정 (line 226~234), 잘못된 점에 dot 찍힐 위험.
- **★ `mock_dashboard.json` 의 `impact.fleet_kpi` 가 `SitesSummary` 형이지만 `total_processed`/`total_hours_saved_cum` 누락** — type 정의는 required 인데 fixture 에 없음. ImpactTab 은 이 값을 직접 사용하지는 않으나 (`yearly_saving`/`total_fte_saved`/`total_headcount`/`total_hours`/`total_hours_saved`/`ai_replacement_rate` 만 사용), 다른 곳에서 spread 시 undefined 가능.
- **★ HIL 단계 fixture 누락** — `mock_agent_status.json` 은 7 agent 만, HIL 은 `AgentWorkflow.tsx:63 HILS[]` 하드코딩 (`afterStep: 3`, `waiting: 3`). BE 가 hil 대기 수를 별도 endpoint 또는 sites_summary.review_pending 으로 줘야 함 (이미 review_pending 있음 — 연결 안 됨).
- **★ wp_id 포맷 일관성** — `deriveWpIdAndPath` (`transforms.ts:61~71`) 가 `${safe(wa)}-${safe(l6_main)}` 산출 → review/route.ts cards.ai_mapped_wp_id + wbsTreeBuild 의 WP 노드 id 동일 transform. 단, `mock_report.json` (PG `daily_reports`) 의 `quadrant[].wp_id` / `wp_summary[].wp_id` / `optimizer.by_wp` 키 — BE 가 별도 산출이라 정합 검증 필요 (`detail.optimizer.by_wp[selectedWpId]` lookup 의존). 다른 transform 쓰면 선택해도 빈 카드.
- **dashboard 의 `endDate` 미전달** — PerformanceTab 의 `endDate` prop optional (line 18), dashboard/page.tsx (line 41~48) 에서 prop 안 보내 `new Date().toISOString().slice(0,10)` (오늘) fallback. PoC 데이터가 2026-05-22 까지인데 오늘 2026-05-27 면 시계열 마지막 5 일이 empty 가능.
- **`/api/mock/dashboard` 의 fleet_trend min/max placeholder** — fixtures.ts:269 주석 "실 site 1 개라 동일 값". FleetProductivityTrendChart 의 분포 밴드 면적이 0 으로 보일 가능성.
- **`ai_replacement_rate` PG vs fixture 단위 혼동 위험** — PG 분기 (`fixtures.ts:160`) 는 `Math.round(... × 10000) / 100` 으로 % 표시값 산출 (예: 3.46 = 3.46%). 그러나 mock fixture 의 `3.46` 도 동일. ImpactTab.tsx:19 는 `value: \`${summary.ai_replacement_rate}\`` 그대로 + `unit: "%"` → 일관. 단 BE 가 분수 (0.0346) 보내면 0.0346% 로 표시될 위험 — contract 명세 필요.
- **chat_sequence date 키 형식 불일치 위험** — `loadReal("chat_sequence")` (fixtures.ts:217~235) 는 PG `report_date` 를 `slice(0,10)` 한 ISO 키, home/page.tsx:14 의 `Object.keys(...).sort().pop()` 최신 1 일만 선택. PG 에 multi-date 들어와도 home 은 1 일만 표시 — 의도된 동작 확인 필요.
- **review/route.ts 의 LIMIT 300 + `today_qty > 0` 필터** — wbsTreeBuild 의 same 필터 (transforms.ts:206) 와 일치 보장 — 카드 수 ↔ WBS review_count 합 매칭. trade IN ('건축','토목') 외 trade (전기/통신/소방 등) 은 영구 제외 → 전 공종 확장 시 양쪽 동시 수정 필요.

---

> 출처 일관성: 모든 file:line 은 본 cycle (2026-05-27) 워킹트리 `/Users/kyungseoplee/Project Agent/CPIA/web/` 기준. fixture 실측치는 `python3 -c "import json; ..."` 직접 파싱. type / fixture / API / page / component grep 으로 전수 — 누락 없음 가정.
