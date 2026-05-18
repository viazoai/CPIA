# CPIA Frontend Data Catalog (web/ B_Track)

> 본 카탈로그는 다음 단계 (FE↔BE crosswalk) 의 input. 현재 FE 는 100% mock fixture 로 동작 — Postgres / FastAPI 미연결.
> Grep 출처: `/Users/kyungseoplee/Project Agent/CPIA/web/lib/`, `web/app/`, `data/mock_*.json`.

---

## §A — Type 인벤토리 (모든 type × 모든 field)

> Grep 출처: `web/lib/types.ts` (전수 1~251 라인) + `web/lib/fixtures.ts` 의 별도 type 3 종 (`FixtureMap`, `ReportDetail`, `DashboardFixture`).
> 모든 field 가 `?` 가 붙지 않은 한 required 로 표시.

| Type | Field | TS Type | Optional | Source File:Line |
|---|---|---|---|---|
| **Status** (alias) | (value) | `"normal" \| "caution" \| "risk" \| "unknown"` | N | web/lib/types.ts:5 |
| **Persona** (alias) | (value) | `"member" \| "manager"` | N | web/lib/types.ts:6 |
| **Site** | id | `string` | N | web/lib/types.ts:10 |
| Site | name | `string` | N | web/lib/types.ts:11 |
| Site | location | `string` | N | web/lib/types.ts:12 |
| Site | status | `Status` | N | web/lib/types.ts:13 |
| Site | progress_planned | `number` | N | web/lib/types.ts:14 |
| Site | progress_actual | `number` | N | web/lib/types.ts:15 |
| Site | gap_percent | `number` | N | web/lib/types.ts:16 |
| Site | productivity_today | `number` | N | web/lib/types.ts:17 |
| Site | spi | `number` | N | web/lib/types.ts:18 |
| Site | abnormal_trades | `number` | N | web/lib/types.ts:19 |
| Site | fte_saved | `number` | N | web/lib/types.ts:20 |
| Site | hours_saved | `number` | N | web/lib/types.ts:21 |
| Site | headcount | `number` | N | web/lib/types.ts:22 |
| Site | total_hours | `number` | N | web/lib/types.ts:23 |
| Site | ai_replacement_rate | `number` | N | web/lib/types.ts:24 |
| Site | expected_completion | `string` (ISO date) | N | web/lib/types.ts:25 |
| Site | recovered_completion | `string` (ISO date) | N | web/lib/types.ts:26 |
| Site | delay_days | `number` | N | web/lib/types.ts:27 |
| Site | recovery_days | `number` | N | web/lib/types.ts:28 |
| **SitesSummary** | today_count | `number` | N | web/lib/types.ts:33 |
| SitesSummary | review_pending | `number` | N | web/lib/types.ts:34 |
| SitesSummary | abnormal_count | `number` | N | web/lib/types.ts:35 |
| SitesSummary | last_updated | `string` | N | web/lib/types.ts:36 |
| SitesSummary | total_hours_saved | `number` | N | web/lib/types.ts:37 |
| SitesSummary | total_fte_saved | `number` | N | web/lib/types.ts:38 |
| SitesSummary | total_headcount | `number` | N | web/lib/types.ts:39 |
| SitesSummary | total_hours | `number` | N | web/lib/types.ts:40 |
| SitesSummary | ai_replacement_rate | `number` | N | web/lib/types.ts:41 |
| SitesSummary | yearly_saving | `number` | N | web/lib/types.ts:42 |
| SitesSummary | total_processed | `number` | N | web/lib/types.ts:43 |
| SitesSummary | total_hours_saved_cum | `number` | N | web/lib/types.ts:44 |
| **AgentStatus** | step | `number` (1..7) | N | web/lib/types.ts:49 |
| AgentStatus | name | `string` | N | web/lib/types.ts:50 |
| AgentStatus | korean_name | `string` | N | web/lib/types.ts:51 |
| AgentStatus | description | `string` | N | web/lib/types.ts:52 |
| AgentStatus | model | `string` | N | web/lib/types.ts:53 |
| AgentStatus | group | `"collect" \| "analyze"` | N | web/lib/types.ts:54 |
| AgentStatus | active_count | `number` | N | web/lib/types.ts:55 |
| AgentStatus | state | `"processing" \| "waiting" \| "idle"` | N | web/lib/types.ts:56 |
| **DailyRun** | date | `string` | N | web/lib/types.ts:61 |
| DailyRun | total_count | `number` | N | web/lib/types.ts:62 |
| DailyRun | status | `"running" \| "completed" \| "review_pending"` | N | web/lib/types.ts:63 |
| DailyRun | has_anomaly | `boolean` | N | web/lib/types.ts:64 |
| DailyRun | bar_value | `number` (0..1) | N | web/lib/types.ts:65 |
| **AgentProgress** | agent | `string` | N | web/lib/types.ts:69 |
| AgentProgress | unit | `"per_report" \| "per_review" \| "per_run"` | N | web/lib/types.ts:70 |
| AgentProgress | processed | `number` | N | web/lib/types.ts:71 |
| AgentProgress | total | `number` | N | web/lib/types.ts:72 |
| AgentProgress | waiting_hil | `boolean` | N | web/lib/types.ts:73 |
| **ChatMessage** | ts | `string` | N | web/lib/types.ts:77 |
| ChatMessage | agent | `string` | N | web/lib/types.ts:78 |
| ChatMessage | type | `"info" \| "hil_request" \| "human_action" \| "result"` | N | web/lib/types.ts:79 |
| ChatMessage | summary | `string` | N | web/lib/types.ts:80 |
| ChatMessage | detail | `string` | **Y** | web/lib/types.ts:81 |
| **WBSNode** | id | `string` | N | web/lib/types.ts:86 |
| WBSNode | type | `"building" \| "trade" \| "work_package"` | N | web/lib/types.ts:87 |
| WBSNode | name | `string` | N | web/lib/types.ts:88 |
| WBSNode | parent_id | `string \| null` | N | web/lib/types.ts:89 |
| WBSNode | review_count | `number` | N | web/lib/types.ts:90 |
| WBSNode | status | `Status` | N | web/lib/types.ts:91 |
| WBSNode | children | `WBSNode[]` | **Y** | web/lib/types.ts:92 |
| **ReviewItem** | id | `string` | N | web/lib/types.ts:96 |
| ReviewItem | bp_name | `string` | N | web/lib/types.ts:97 |
| ReviewItem | work_content | `string` | N | web/lib/types.ts:98 |
| ReviewItem | quantity | `number` | N | web/lib/types.ts:99 |
| ReviewItem | unit | `string` | N | web/lib/types.ts:100 |
| ReviewItem | ai_mapped_wp_id | `string` | N | web/lib/types.ts:101 |
| ReviewItem | ai_mapped_path | `string` | N | web/lib/types.ts:102 |
| ReviewItem | confidence | `number` (0~1) | N | web/lib/types.ts:103 |
| ReviewItem | status | `"confirmed" \| "unconfirmed"` | N | web/lib/types.ts:104 |
| ReviewItem | alternative_wps | `{ id: string; path: string; score: number }[]` | **Y** | web/lib/types.ts:105 |
| **ReportDaily** | date | `string` | N | web/lib/types.ts:110 |
| ReportDaily | status | `Status` | N | web/lib/types.ts:111 |
| ReportDaily | productivity_today | `number` | N | web/lib/types.ts:112 |
| ReportDaily | delay_days | `number` | N | web/lib/types.ts:113 |
| ReportDaily | recovery_days | `number` | N | web/lib/types.ts:114 |
| **ReportKpi** | productivity_today | `number` | N | web/lib/types.ts:118 |
| ReportKpi | productivity_history_diff | `number` | N | web/lib/types.ts:119 |
| ReportKpi | delay_days | `number` | N | web/lib/types.ts:120 |
| ReportKpi | expected_completion | `string` | N | web/lib/types.ts:121 |
| ReportKpi | recoverable_productivity | `number` | N | web/lib/types.ts:122 |
| ReportKpi | target_productivity | `number` | N | web/lib/types.ts:123 |
| ReportKpi | recovery_days | `number` | N | web/lib/types.ts:124 |
| ReportKpi | recovered_completion | `string` | N | web/lib/types.ts:125 |
| **SCurvePoint** | date | `string` | N | web/lib/types.ts:129 |
| SCurvePoint | planned | `number` | N | web/lib/types.ts:130 |
| SCurvePoint | actual | `number` | **Y** | web/lib/types.ts:131 |
| SCurvePoint | forecast | `number` | **Y** | web/lib/types.ts:132 |
| SCurvePoint | recovery | `number` | **Y** | web/lib/types.ts:133 |
| **BarItem** | label | `string` | N | web/lib/types.ts:137 |
| BarItem | value | `number` | N | web/lib/types.ts:138 |
| BarItem | status | `Status` | N | web/lib/types.ts:139 |
| **QuadrantPoint** | wp_id | `string` | N | web/lib/types.ts:143 |
| QuadrantPoint | wp_name | `string` | N | web/lib/types.ts:144 |
| QuadrantPoint | trade | `string` | N | web/lib/types.ts:145 |
| QuadrantPoint | productivity | `number` (0..100) | N | web/lib/types.ts:146 |
| QuadrantPoint | impact | `number` (0..100) | N | web/lib/types.ts:147 |
| QuadrantPoint | quadrant | `"risk" \| "caution" \| "watch" \| "safe"` | N | web/lib/types.ts:148 |
| QuadrantPoint | size | `number` | N | web/lib/types.ts:149 |
| **OptimizerOutput** | wp_id | `string` | N | web/lib/types.ts:153 |
| OptimizerOutput | diagnosis | `string` | N | web/lib/types.ts:154 |
| OptimizerOutput | similar_cases | `{ date: string; description: string; outcome: string }[]` | N | web/lib/types.ts:155 |
| OptimizerOutput | recommendations | `string[]` | N | web/lib/types.ts:156 |
| OptimizerOutput | details | `{ label: string; value: string }[]` | N | web/lib/types.ts:157 |
| **RawDataRow** | building | `string` | N | web/lib/types.ts:161 |
| RawDataRow | trade | `string` | N | web/lib/types.ts:162 |
| RawDataRow | wp | `string` | N | web/lib/types.ts:163 |
| RawDataRow | bp_name | `string` | N | web/lib/types.ts:164 |
| RawDataRow | work_content | `string` | N | web/lib/types.ts:165 |
| RawDataRow | quantity | `number` | N | web/lib/types.ts:166 |
| RawDataRow | unit | `string` | N | web/lib/types.ts:167 |
| RawDataRow | workers | `number` | N | web/lib/types.ts:168 |
| RawDataRow | equipment | `string` | N | web/lib/types.ts:169 |
| **ImpactSiteDistribution** | site_id | `string` | N | web/lib/types.ts:174 |
| ImpactSiteDistribution | site_name | `string` | N | web/lib/types.ts:175 |
| ImpactSiteDistribution | hours_saved | `number` | N | web/lib/types.ts:176 |
| ImpactSiteDistribution | fte_saved | `number` | N | web/lib/types.ts:177 |
| **ImpactTrendPoint** | month | `string` (YYYY-MM) | N | web/lib/types.ts:181 |
| ImpactTrendPoint | cumulative_fte | `number` | N | web/lib/types.ts:182 |
| **MiddleOfficeAutomation** | function | `string` | N | web/lib/types.ts:186 |
| MiddleOfficeAutomation | rate | `number` (0..100) | N | web/lib/types.ts:187 |
| MiddleOfficeAutomation | before_hours | `number` | N | web/lib/types.ts:188 |
| MiddleOfficeAutomation | after_hours | `number` | N | web/lib/types.ts:189 |
| **SimulationSequence** | home_now_strip | `{ interval_ms: number; variance: number }[]` | N | web/lib/types.ts:194 |
| SimulationSequence | agent_card_status | `Record<string, number[]>` | N | web/lib/types.ts:195 |
| SimulationSequence | chat_log | `ChatMessage[]` | N | web/lib/types.ts:196 |
| **DiagStatus** (alias) | (value) | `Exclude<Status, "unknown">` = `"normal" \| "caution" \| "risk"` | N | web/lib/types.ts:200 |
| **DiagnosisInput** | site_id | `string` | N | web/lib/types.ts:203 |
| DiagnosisInput | today_progress | `number` | N | web/lib/types.ts:204 |
| DiagnosisInput | history_mean | `number` | N | web/lib/types.ts:205 |
| DiagnosisInput | history_std | `number` | N | web/lib/types.ts:206 |
| DiagnosisInput | sample_size | `number` | N | web/lib/types.ts:207 |
| DiagnosisInput | s_curve | `SCurvePoint[]` | N | web/lib/types.ts:208 |
| **RecoveryEstimate** | p25 | `number` | N | web/lib/types.ts:212 |
| RecoveryEstimate | p50 | `number` | N | web/lib/types.ts:213 |
| RecoveryEstimate | p75 | `number` | N | web/lib/types.ts:214 |
| **ScenarioPoint** | eta_days | `number` (Infinity 허용) | N | web/lib/types.ts:218 |
| ScenarioPoint | recovery_pct | `number` | N | web/lib/types.ts:219 |
| ScenarioPoint | delta_completion_days | `number` | N | web/lib/types.ts:220 |
| ScenarioPoint | curve | `number[]` | N | web/lib/types.ts:221 |
| **ProductivityDiagnosis** | history_mean | `number` | N | web/lib/types.ts:226 |
| ProductivityDiagnosis | history_std | `number` | N | web/lib/types.ts:227 |
| ProductivityDiagnosis | sample_size | `number` | N | web/lib/types.ts:228 |
| ProductivityDiagnosis | today_progress | `number` | N | web/lib/types.ts:231 |
| ProductivityDiagnosis | productivity_score | `number` | N | web/lib/types.ts:232 |
| ProductivityDiagnosis | gap_pct | `number` | N | web/lib/types.ts:233 |
| ProductivityDiagnosis | z_score | `number` | N | web/lib/types.ts:234 |
| ProductivityDiagnosis | status | `DiagStatus` | N | web/lib/types.ts:235 |
| ProductivityDiagnosis | s_curve | `SCurvePoint[]` | N | web/lib/types.ts:238 |
| ProductivityDiagnosis | band_p25 | `number[]` | N | web/lib/types.ts:239 |
| ProductivityDiagnosis | band_p75 | `number[]` | N | web/lib/types.ts:240 |
| ProductivityDiagnosis | ewma_trend | `number[]` | N | web/lib/types.ts:241 |
| ProductivityDiagnosis | recovery | `{ p25_days: number; p50_days: number; p75_days: number }` | N | web/lib/types.ts:244 |
| ProductivityDiagnosis | scenarios | `{ optimistic: ScenarioPoint; base: ScenarioPoint; pessimistic: ScenarioPoint }` | N | web/lib/types.ts:245~249 |
| **FixtureMap** (type-only) | sites | `Site[]` | N | web/lib/fixtures.ts:16 |
| FixtureMap | sites_summary | `SitesSummary` | N | web/lib/fixtures.ts:17 |
| FixtureMap | agent_status | `AgentStatus[]` | N | web/lib/fixtures.ts:18 |
| FixtureMap | agent_tasks | `{ daily_runs: DailyRun[]; progress_by_date: Record<string, AgentProgress[]> }` | N | web/lib/fixtures.ts:19 |
| FixtureMap | chat_sequence | `Record<string, ChatMessage[]>` | N | web/lib/fixtures.ts:20 |
| FixtureMap | review_cards | `ReviewItem[]` | N | web/lib/fixtures.ts:21 |
| FixtureMap | wbs_tree | `WBSNode` | N | web/lib/fixtures.ts:22 |
| FixtureMap | report | `{ daily: ReportDaily[]; details: Record<string, ReportDetail> }` | N | web/lib/fixtures.ts:23 |
| FixtureMap | dashboard | `DashboardFixture` | N | web/lib/fixtures.ts:24 |
| FixtureMap | simulation | `SimulationSequence` | N | web/lib/fixtures.ts:25 |
| **ReportDetail** | kpi | `ReportKpi` | N | web/lib/fixtures.ts:29 |
| ReportDetail | s_curve | `SCurvePoint[]` | N | web/lib/fixtures.ts:30 |
| ReportDetail | contractor_bars | `BarItem[]` | N | web/lib/fixtures.ts:31 |
| ReportDetail | trade_bars | `BarItem[]` | N | web/lib/fixtures.ts:32 |
| ReportDetail | quadrant | `QuadrantPoint[]` | N | web/lib/fixtures.ts:33 |
| ReportDetail | optimizer | `OptimizerOutput` | N | web/lib/fixtures.ts:34 |
| ReportDetail | raw_data | `RawDataRow[]` | N | web/lib/fixtures.ts:35 |
| **DashboardFixture** | performance.fleet_kpi.avg_productivity | `number` | N | web/lib/fixtures.ts:41 |
| DashboardFixture | performance.fleet_kpi.avg_delay | `number` | N | web/lib/fixtures.ts:42 |
| DashboardFixture | performance.fleet_kpi.abnormal_total | `number` | N | web/lib/fixtures.ts:43 |
| DashboardFixture | performance.fleet_kpi.recoverable_days | `number` | N | web/lib/fixtures.ts:44 |
| DashboardFixture | impact.fleet_kpi | `SitesSummary` | N | web/lib/fixtures.ts:48 |
| DashboardFixture | impact.site_distribution | `ImpactSiteDistribution[]` | N | web/lib/fixtures.ts:49 |
| DashboardFixture | impact.monthly_trend | `ImpactTrendPoint[]` | N | web/lib/fixtures.ts:50 |
| DashboardFixture | impact.per_site_automation | `Record<string, MiddleOfficeAutomation[]>` | N | web/lib/fixtures.ts:51 |

---

### §A.2 신규 type (2026-05-18 PR #20 / #22 흡수)

| Type | Field | TS Type | Optional | Source File:Line |
|---|---|---|---|---|
| **DiagStatus** (alias) | (value) | `Exclude<Status, "unknown">` (= `"normal" \| "caution" \| "risk"`) | N | web/lib/types.ts:239 |
| **DiagnosisInput** | site_id | `string` | N | web/lib/types.ts:242 |
| DiagnosisInput | today_progress | `number` (%) | N | web/lib/types.ts:243 |
| DiagnosisInput | history_mean | `number` (μ) | N | web/lib/types.ts:244 |
| DiagnosisInput | history_std | `number` (σ) | N | web/lib/types.ts:245 |
| DiagnosisInput | sample_size | `number` (N) | N | web/lib/types.ts:246 |
| DiagnosisInput | s_curve | `SCurvePoint[]` | N | web/lib/types.ts:247 |
| **RecoveryEstimate** | p25 / p50 / p75 | `number` × 3 | N | web/lib/types.ts:251~253 |
| **ScenarioPoint** | eta_days | `number` (∞ 허용) | N | web/lib/types.ts:257 |
| ScenarioPoint | recovery_pct | `number` (%) | N | web/lib/types.ts:258 |
| ScenarioPoint | delta_completion_days | `number` (±) | N | web/lib/types.ts:259 |
| ScenarioPoint | curve | `(number \| null)[]` (시계열, today 이전 null) | N | web/lib/types.ts:260 |
| **ProductivityDiagnosis** | history_mean / history_std / sample_size | `number` × 3 | N | web/lib/types.ts:265~267 |
| ProductivityDiagnosis | today_progress | `number` (%) | N | web/lib/types.ts:270 |
| ProductivityDiagnosis | productivity_score | `number` (today/μ × 100) | N | web/lib/types.ts:271 |
| ProductivityDiagnosis | gap_pct | `number` (%p) | N | web/lib/types.ts:272 |
| ProductivityDiagnosis | z_score | `number` (σ 기준) | N | web/lib/types.ts:273 |
| ProductivityDiagnosis | status | `DiagStatus` | N | web/lib/types.ts:274 |
| ProductivityDiagnosis | s_curve | `SCurvePoint[]` | N | web/lib/types.ts:277 |
| ProductivityDiagnosis | band_p25 / band_p75 | `number[]` × 2 (볼린저 밴드) | N | web/lib/types.ts:278~279 |
| ProductivityDiagnosis | ewma_trend | `number[]` | N | web/lib/types.ts:280 |
| ProductivityDiagnosis | recovery | `{ p25_days, p50_days, p75_days }` | N | web/lib/types.ts:283 |
| ProductivityDiagnosis | scenarios | `{ optimistic, base, pessimistic: ScenarioPoint }` | N | web/lib/types.ts:284~288 |
| **WPSummaryRow** | wp_id | `string` | N | web/lib/types.ts:200 |
| WPSummaryRow | wp_name | `string` (예: "WP-3-2 거푸집") | N | web/lib/types.ts:201 |
| WPSummaryRow | trade | `string` (예: "골조") | N | web/lib/types.ts:202 |
| WPSummaryRow | bp_name | `string` (예: "A건설") | N | web/lib/types.ts:203 |
| WPSummaryRow | start_date / end_date | `string` (ISO) × 2 | N | web/lib/types.ts:204~205 |
| WPSummaryRow | progress_pct | `number` (0..100) | N | web/lib/types.ts:206 |
| WPSummaryRow | productivity | `number` (0..100) — Quadrant 와 동일 값 | N | web/lib/types.ts:207 |
| WPSummaryRow | status | `"normal" \| "caution" \| "risk"` | N | web/lib/types.ts:208 |
| **DailyTask** | date | `string` (ISO) | N | web/lib/types.ts:78 |
| DailyTask | total_count | `number` (작업일보 건수) | N | web/lib/types.ts:79 |
| DailyTask | progress_percent | `number` (0..100) | N | web/lib/types.ts:80 |
| DailyTask | status | `"running" \| "completed" \| "review_pending"` | N | web/lib/types.ts:81 |
| DailyTask | has_anomaly | `boolean` | N | web/lib/types.ts:82 |
| **AgentStageProgress** | step | `number` (1..7 + HIL=3.5) | N | web/lib/types.ts:86 |
| AgentStageProgress | agent | `string` (Collector ... Optimizer + HIL Review) | N | web/lib/types.ts:87 |
| AgentStageProgress | is_hil | `boolean` | N | web/lib/types.ts:88 |
| AgentStageProgress | received / processed | `number` × 2 | N | web/lib/types.ts:89~90 |
| AgentStageProgress | percent | `number` (0..100) | N | web/lib/types.ts:91 |
| AgentStageProgress | waiting_hil | `boolean` | N | web/lib/types.ts:92 |
| **AgentTaskItem** | id | `string` (예: "RPT-20260515-001") | N | web/lib/types.ts:96 |
| AgentTaskItem | trade | `string` (공종) | N | web/lib/types.ts:97 |
| AgentTaskItem | contractor | `string` (BP사) | N | web/lib/types.ts:98 |
| AgentTaskItem | status | `"done" \| "processing" \| "received" \| "hil_pending" \| "blocked"` | N | web/lib/types.ts:99 |

**§A.2 추가**:
- ReportDetail (fixtures.ts:36) 의 `wp_summary: WPSummaryRow[]` 신규 field (PR #22 § 5 원본 데이터 표)

**총 row 수 갱신 (2026-05-18): 약 190 row** (33 type 중 dead/preview/internal 7 제외 = 26 scoped).

---

### §A 발견된 패턴

- **Optional field 가 극히 적다** — 전체 ~150 field 중 단 6 개만 optional: `ChatMessage.detail`, `WBSNode.children`, `ReviewItem.alternative_wps`, `SCurvePoint.{actual, forecast, recovery}`. 백엔드는 거의 모든 field 를 non-null 로 반환해야 함.
- **enum 이 모두 닫혀있다** — `Status` 4 값, `Persona` 2 값, `AgentStatus.group` 2 값, `AgentStatus.state` 3 값, `DailyRun.status` 3 값, `AgentProgress.unit` 3 값, `ChatMessage.type` 4 값, `WBSNode.type` 3 값, `ReviewItem.status` 2 값, `QuadrantPoint.quadrant` 4 값. 새 값 추가는 FE 코드 (switch / Record<>) 수정 동반.
- **`DiagStatus` 는 Status 의 closed subset** — `unknown` 만 제거. Diagnosis 출력에 `unknown` 은 절대 안 나온다는 계약.
- **숫자 단위가 type 에 없다** — `progress_planned: number` 가 % 인지 0~1 인지 주석만으로 표시 (`%`). 백엔드 매핑 시 단위 정렬 필수.
- **날짜는 전부 `string`** — `expected_completion`, `recovered_completion`, `SCurvePoint.date`, `ChatMessage.ts` 모두 `string`. ISO/시각 format 은 주석 또는 호출처에서 가공.
- **Site 가 사실상 join 결과** — Site 단일 entity 안에 진척률 / 생산성 / FTE / 공기 / 임팩트 가 모두 박혀있음. BE 에서는 `sites` + `daily_reports` + `forecasts` + `optimizer_advice` 다중 테이블 join 결과로 만들어야 함 (`docs/schema/postgres.md` 참조).

---

## §B — Mock fixture 인벤토리

> Grep 출처: `ls data/mock_*.json` + `web/lib/fixtures.ts:55 DATA_DIR = path.join(process.cwd(), "..", "data")` (Next.js `web/` cwd 기준 부모의 `data/`).
> Sample row count = `/usr/bin/python3` 로 직접 JSON 파싱한 실측값.

| Fixture name | data/ file | FixtureMap key | Type | Sample row count |
|---|---|---|---|---|
| sites | data/mock_sites.json | `sites` | `Site[]` | 6 sites |
| sites_summary | data/mock_sites_summary.json | `sites_summary` | `SitesSummary` | 1 obj (12 scalar fields) |
| agent_status | data/mock_agent_status.json | `agent_status` | `AgentStatus[]` | 7 agents (step 1~7) |
| agent_tasks | data/mock_agent_tasks.json | `agent_tasks` | `{ daily_runs: DailyRun[]; progress_by_date: Record<string, AgentProgress[]> }` | `daily_runs` 7개, `progress_by_date` 2 dates (2026-05-15, 2026-05-14), 각 8 progress rows |
| chat_sequence | data/mock_chat_sequence.json | `chat_sequence` | `Record<string, ChatMessage[]>` | 1 date (2026-05-15), 8 messages |
| review_cards | data/mock_review_cards.json | `review_cards` | `ReviewItem[]` | 13 cards |
| wbs_tree | data/mock_wbs_tree.json | `wbs_tree` | `WBSNode` (root) | 1 root (m15x-ph3-ibl) → 4 children → 재귀 트리 |
| report | data/mock_report.json | `report` | `{ daily: ReportDaily[]; details: Record<string, ReportDetail> }` | `daily` 5 entries, `details` 1 date (2026-05-15) — 단일 상세만 채워짐 |
| dashboard | data/mock_dashboard.json | `dashboard` | `DashboardFixture` | `performance.fleet_kpi` 4 scalar, `impact.fleet_kpi` SitesSummary, `site_distribution` 6, `monthly_trend` 5, `per_site_automation` 1 site (m15x-ph3-ibl) |
| simulation | data/mock_simulation.json | `simulation` | `SimulationSequence` (실제 JSON 은 wider — `home`/`tasks`/`report`/`dashboard` 키) | TBD — JSON shape (`home`/`tasks`/`report`/`dashboard`) 가 `SimulationSequence` type 과 어긋남, 현재 어디서도 `loadFixture("simulation")` 으로 읽히지 않음 |

**총 row 수: 10 fixture.**

### §B 발견된 패턴

- **fixture ↔ type 1:1 매핑** — `FixtureMap` key 가 `mock_<key>.json` 파일명과 정확히 1:1 (`web/lib/fixtures.ts:58` `path.join(DATA_DIR, "mock_${name}.json")`).
- **details 가 단일 날짜만 채워짐** — `mock_report.json` 의 `details` 는 `2026-05-15` 한 날짜만 풀로 채워져 있고 다른 날 선택 시 Loading 상태 (`web/app/(app)/reports/page.tsx:23`).
- **simulation 파일 shape 불일치** — `mock_simulation.json` 실 shape (`home`/`tasks`/`report`/`dashboard`) 가 `SimulationSequence` type 정의 (`home_now_strip`/`agent_card_status`/`chat_log`) 와 다름. 현재 코드에서 `loadFixture("simulation")` 호출처 없음 → dead fixture / 다음 plan 의 reference 파라미터.
- **per_site_automation 도 단일 site 만** — `mock_dashboard.json` 의 `per_site_automation` 도 `m15x-ph3-ibl` 만 채워져 있어 다른 site 클릭 시 fallback 처리 (`web/app/api/mock/dashboard/[id]/route.ts:15`).
- **`fixtures.ts` 는 server-only** — `import { promises as fs }` 사용 → 클라이언트 컴포넌트에서 직접 호출 불가, API Route 또는 server component 경유.
- **API Route 가 얇은 BFF** — `web/app/api/mock/{dashboard,review,report,agent-tasks}/route.ts` 4 종 + `dashboard/[id]/route.ts`. 모두 `loadFixture` 를 호출해 그대로 JSON 반환.

---

## §C — UI consumer 매핑 (page → component → field → UI element)

> Grep 출처: `web/app/(app)/{home,dashboard,tasks,review,reports,diagnosis-preview}/page.tsx` + `web/app/(landing)/page.tsx` + `web/app/components/**/*.tsx`.
> File:line 은 destructure 또는 JSX 사용 라인을 가리킴.

### C-1. Home (`/home`)

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| home | (page) | web/app/(app)/home/page.tsx:8 | `SitesSummary` 전체 (loadFixture("sites_summary")) | Server fetch |
| home | (page) | web/app/(app)/home/page.tsx:9 | `AgentStatus[]` 전체 (loadFixture("agent_status")) | Server fetch |
| home | (page) | web/app/(app)/home/page.tsx:12 | `agents[i].active_count` (reduce 합산) | `processingNow` 숫자 → OpsKpiCard "현재 처리 중" value |
| home | StatusHeader | web/app/components/home/StatusHeader.tsx:39 | `summary.last_updated` | "LIVE · 마지막 동기화 Ns 전 (HH:MM)" 인라인 텍스트 |
| home | OpsKpiCard | web/app/components/home/OpsKpiCard.tsx:38~62 | `value`/`unit`/`label`/`description`/`live` props | rounded-card 4 칸 (누적 처리 / 오늘 처리 / 누적 절감 / 현재 처리 중) |
| home | (page) | web/app/(app)/home/page.tsx:24 | `summary.total_processed` | OpsKpiCard "누적 처리" value (`toLocaleString()`) |
| home | (page) | web/app/(app)/home/page.tsx:32 | `summary.today_count` | OpsKpiCard "오늘 처리" value |
| home | (page) | web/app/(app)/home/page.tsx:40 | `summary.total_hours_saved_cum` | OpsKpiCard "누적 절감" value (단위 `h`) |
| home | AgentWorkflow | web/app/components/home/AgentWorkflow.tsx:83~99 | `agents[]` 전체, `.step`, `.state`, `.name`, `.korean_name`, `.description`, `.model` | 세로 워크플로 ol/li, AgentRow + HilRow + Connector |
| home | AgentWorkflow→AgentRow | web/app/components/home/AgentWorkflow.tsx:130 | `agent.step` (padStart) | "STEP NN" 라벨 |
| home | AgentWorkflow→AgentRow | web/app/components/home/AgentWorkflow.tsx:137~143 | `agent.name`/`agent.korean_name`/`agent.description`/`agent.model` | h6 + body-sm + 본문 + mono 모델명 |
| home | AgentWorkflow→AgentRow | web/app/components/home/AgentWorkflow.tsx:150,154 | `COUNTS[agent.step].today` / `.total` (FE-내 mock 상수) | 우측 오늘/누적 숫자 (※ 실 BE 연결 시 source 필요) |
| home | AgentWorkflow→AgentRow | web/app/components/home/AgentWorkflow.tsx:157~159 | `agent.state` → `STATE_DOT`/`STATE_LABEL` map | 상태 dot + 텍스트 (processing/waiting/idle) |
| home | (legacy) NowStrip | web/app/components/home/NowStrip.tsx:20,28,37~40 | `summary.today_count`, `summary.review_pending`, `summary.abnormal_count`, `summary.last_updated` | NOW strip 4 칸 (현재 `/home` 에서 미사용, design fallback 컴포넌트) |
| home | (legacy) Hero | web/app/components/home/Hero.tsx:62~65 | hard-coded ("2,155", "15.4", "D-14", "3~7") | HeroStat 4 카드 (미사용 — Home 페이지에서 import 안 됨) |
| home | (legacy) HilReviewStage | web/app/components/home/HilReviewStage.tsx:1~31 | (props 없음, 정적 카피) | HIL 스테이지 정적 카드 (현재 import 처 없음) |
| home | (legacy) AgentCard | web/app/components/home/AgentCard.tsx:17,34~42 | `agent.active_count`, `.step`, `.name`, `.korean_name`, `.description`, `.model`, `.state`, `.group` | AgentCard 카드 (현재 AgentWorkflow 가 대체 — import 처 없음) |

### C-2. Agent Tasks (`/tasks`)

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| tasks | (page) | web/app/(app)/tasks/page.tsx:19 | `fetch("/api/mock/agent-tasks")` → `{ daily_runs, progress_by_date }` + `chat_sequence` 합본 | Client fetch (※ route.ts 가 두 fixture 합칠 듯 — 미검증) |
| tasks | DailyRunList | web/app/components/tasks/DailyRunList.tsx:13,27~63 | `runs[].date`, `.total_count`, `.status`, `.has_anomaly` | 좌측 패널 일별 버튼 + status icon + 이상 chip + 진행 bar |
| tasks | DailyRunList→RunStatusIcon | web/app/components/tasks/DailyRunList.tsx:69~73 | `run.status` → icon 분기 | Pause / pulse dot / CheckCircle2 |
| tasks | AgentProgressList | web/app/components/tasks/AgentProgressList.tsx:17~42 | `progress[].agent`, `.processed`, `.total`, `.waiting_hil` | 중앙 패널 진행 bar 리스트 (per agent) |
| tasks | AgentChatLog | web/app/components/tasks/AgentChatLog.tsx:38,55~67 | `messages[]` (`ts`/`agent`/`type`/`summary`/`detail`) | 우측 chat 패널, `useSequence` 로 순차 reveal |
| tasks | AgentChatLog→ChatBubble | web/app/components/tasks/AgentChatLog.tsx:86~155 | `message.agent` (AGENT_META lookup), `.type`, `.summary`, `.detail`, `.ts` | avatar + bubble + meta (좌/우 정렬: `human_action` → right, `hil_request` → highlight) |

### C-3. Human Review (`/review`)

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| review | (page) | web/app/(app)/review/page.tsx:16 | `fetch("/api/mock/review")` → `{ wbs: WBSNode, cards: ReviewItem[] }` | Client fetch |
| review | WBSTree | web/app/components/review/WBSTree.tsx:14~25 | `root: WBSNode` 전체 | 좌측 트리 패널 |
| review | WBSTree→Branch | web/app/components/review/WBSTree.tsx:60~75 | `node.children`, `.status`, `.name`, `.review_count`, `.type` (work_package = drop target) | Branch 행: chevron + status dot + 이름 + review_count chip / WP CheckCircle |
| review | WBSTree→Branch | web/app/components/review/WBSTree.tsx:52~58 | drag-drop: `onDrop(cardId, node.id)` (WP only) | 드롭 → 상위 review 페이지의 `handleRemap` |
| review | ReviewCard | web/app/components/review/ReviewCard.tsx:32~50 | `item.status`, `.bp_name`, `.quantity`, `.unit` | header: 상태 chip + BP사 + 수량/단위 |
| review | ReviewCard | web/app/components/review/ReviewCard.tsx:52~54 | `item.work_content` | italic 작업내용 인용 |
| review | ReviewCard | web/app/components/review/ReviewCard.tsx:56~65 | `item.ai_mapped_path`, `item.confidence` | "매핑:" + path + 우측 confidence 퍼센트 chip |
| review | ReviewCard | web/app/components/review/ReviewCard.tsx:67~71 | `item.alternative_wps[]` (path/score) | "대안:" 라인 (split path 끝 + 퍼센트) |
| review | ReviewCard | web/app/components/review/ReviewCard.tsx:89~108 | actions: `onConfirm(id)`, `onRemap` (edit mode) | 확정 / 수정 버튼 |
| review | WPSearchCombobox | web/app/components/review/WPSearchCombobox.tsx:18~24 | `wbsRoot` 평탄화 → WP `{id, path}[]` | 검색 input + 자동완성 ul (WP 옵션) |
| review | WPSearchCombobox | web/app/components/review/WPSearchCombobox.tsx:56~67 | `onSelect(id, path)` | WP 선택 → 상위 ReviewCard `onRemap` |

### C-4. Report (`/reports`)

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| reports | (page) | web/app/(app)/reports/page.tsx:18 | `fetch("/api/mock/report")` → `{ daily: ReportDaily[], details: Record<date, ReportDetail> }` | Client fetch |
| reports | (page) | web/app/(app)/reports/page.tsx:28~33 | `detail.kpi.productivity_today`, `.productivity_history_diff`, `.delay_days`, `.expected_completion`, `.recoverable_productivity`, `.target_productivity`, `.recovery_days`, `.recovered_completion` | KpiItem[] 4 개 → KpiStrip |
| reports | ReportDailyList | web/app/components/reports/ReportDailyList.tsx:22~46 | `daily[].date`, `.status`, `.productivity_today`, `.delay_days` | 좌측 sticky 패널 일별 버튼 + status icon + 생산성/지연 텍스트 |
| reports | KpiStrip | web/app/components/reports/KpiStrip.tsx:27~37 | `items[].label`, `.value`, `.unit`, `.sub`, `.tone` | 4~5 칸 KPI 카드 그리드 |
| reports | ~~ForecastTab~~ | **[DELETED 2026-05-18 PR #20]** — Tabs 구조 폐지 | (대체) ForecastChart + ProductivityBarToggle |
| reports | ~~OptimizeTab~~ | **[DELETED 2026-05-18 PR #20]** — Tabs 구조 폐지 | (대체) QuadrantCountKpi + OptimizerResult 가 § 03 직접 배치 |
| reports | **GapKpiCard** | web/app/components/reports/GapKpiCard.tsx:28~49 | `diagnosis.gap_pct`, `.z_score`, `.status` (FE diagnose adapter mock) | **[ADDED PR #22]** § 01 결론 4 KPI 카드 중 1 — 3xl 숫자 + status chip + Z 텍스트 |
| reports | **ProductivityBarToggle** | web/app/components/reports/ProductivityBarToggle.tsx:1~51 | `detail.contractor_bars[]`, `.trade_bars[]` | **[ADDED PR #22]** § 02 업체↔공종 toggle bar chart |
| reports | **QuadrantCountKpi** | web/app/components/reports/QuadrantCountKpi.tsx:14~25 | `points[].quadrant` → counts.risk/caution/safe(+watch) | § 03 좌상 3 chip 버튼 (필터링) |
| reports | **QuadrantScatter** | web/app/components/charts/QuadrantScatter.tsx | `points: QuadrantPoint[]`, `selectedWpId`, `onSelect`, `filter` | § 03 좌하 Impact × Productivity 산점도 |
| reports | **WPSummaryTable** | web/app/components/reports/WPSummaryTable.tsx:1~92 | `rows: WPSummaryRow[]`, `selectedWpId`, `onSelect` | **[ADDED PR #22]** § 03 하단 WP 단위 표 (wp_id/wp_name/trade/bp_name/start_date/end_date/progress_pct/productivity/status). **G-1 gap — BE 산식 신규 (activity_master + mapped_history)** |
| reports | **OptimizerResult** | web/app/components/reports/OptimizerResult.tsx:1~54 | `output: OptimizerOutput` 단일 객체 (mock — D-12 결정 미반영 = mismatch) | § 03 우측 4 섹션 카드 (진단/유사사례/권고/상세). **G-8 결정 — BE 배열 응답 + FE OptimizerOutput[] 수신** [[decisions/cpia-optimizer-array-grain-2026-05-18]] |
| reports | **ForecastChart** | web/app/components/charts/ForecastChart.tsx:1~195 | `diagnosis: ProductivityDiagnosis`, `recoveryActive` | **[ADDED PR #22]** § 04 추세 차트 — Plan/Actual/Forecast/Optimistic/Pessimistic 5 선 + 볼린저 밴드 + ConfidenceBadge. **G-9 gap — 계획 MH 누적 + 실적 mapped_history + 회복 forecaster 가공 BE 산식 미정의** |
| reports | RawDataTab | web/app/components/reports/RawDataTab.tsx:18~93 | `rows: RawDataRow[]` 전체 9 컬럼 + `filterWpId` + `wpNameById` (PR #22 신규 prop) | § 05 검색 + CSV 내보내기 + 테이블 + WP 필터 |

> **§ C-4 구조 변경 (2026-05-18 PR #20 + #22)**: Tabs (ForecastTab / OptimizeTab) 폐지 → 5 섹션 인과 흐름:
>
> - § 01 결론 — SingleKpi × 3 + GapKpiCard (4 카드 grid)
> - § 02 현재 상태 — ProductivityBarToggle (업체 ↔ 공종 toggle)
> - § 03 리스크 및 대안 검토 — QuadrantCountKpi + QuadrantScatter + OptimizerResult + WPSummaryTable
> - § 04 공기 단축 예측 시나리오 — ForecastChart (diagnose() FE adapter mock 입력)
> - § 05 원본 데이터 — RawDataTab (toggle 펼침)
>
> ProductivityDiagnosis 입력 = `web/lib/diagnosis-adapter.ts:13~26` 의 `toDiagnosisInput()` mock 어댑터 (D-3 EWMA 드랍 후 영구 mock). 데이터 흐름: detail.kpi + detail.s_curve → toDiagnosisInput → diagnose() → ProductivityDiagnosis → GapKpiCard / ForecastChart.

### C-5. Dashboard fleet (`/dashboard`)

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| dashboard | (page) | web/app/(app)/dashboard/page.tsx:14 | `fetch("/api/mock/dashboard")` → `{ sites: Site[], dashboard: DashboardFixture }` | Client fetch |
| dashboard | PerformanceTab | web/app/components/dashboard/PerformanceTab.tsx:11~16 | `fleetKpi.avg_productivity`, `.avg_delay`, `.abnormal_total`, `.recoverable_days` | KpiStrip 4 칸 |
| dashboard | PerformanceTab→SiteOverviewCard | web/app/components/dashboard/SiteOverviewCard.tsx:11~62 | `site.id`, `.name`, `.location`, `.status`, `.productivity_today`, `.delay_days`, `.progress_actual`, `.abnormal_trades` | Link 카드: 좌측 status stripe + 이름/위치 + 생산성/공기 + sparkline (recharts) + 이상 chip + arrow |
| dashboard | ImpactTab (scope="fleet") | web/app/components/dashboard/ImpactTab.tsx:15~25 | `summary.total_headcount`, `.total_hours`, `.total_hours_saved`, `.total_fte_saved`, `.ai_replacement_rate` | KpiStrip 4 칸 |
| dashboard | ImpactTab | web/app/components/dashboard/ImpactTab.tsx:32~38 | `summary.yearly_saving`, `.total_fte_saved` | "★ 연간 환산 효과" 강조 배너 |
| dashboard | ImpactTab→HorizontalBarList | web/app/components/dashboard/HorizontalBarList.tsx:14~35 | `items[].label`, `.value`, `.meta` | 좌측 가로 막대 리스트 (현장별 절감 분포) |
| dashboard | ImpactTab→TrendLineChart | web/app/components/charts/TrendLineChart.tsx:16~42 | `trend[].month`, `.cumulative_fte` (→ `value`) | 우측 월별 누적 FTE area chart (recharts) |

### C-6. Dashboard site detail (`/dashboard/sites/[id]`)

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| sites/[id] | (page) | web/app/(app)/dashboard/sites/[id]/page.tsx:26 | `fetch("/api/mock/dashboard/${id}")` → `{ site, detail, perSiteAutomation, trend }` | Client fetch |
| sites/[id] | (page) | web/app/(app)/dashboard/sites/[id]/page.tsx:54~55 | `site.name`, `site.location` | h1 + sub-header |
| sites/[id] | (page) | web/app/(app)/dashboard/sites/[id]/page.tsx:32~37 | `site.productivity_today`, `.delay_days`, `.recovery_days`, `.expected_completion`, `.recovered_completion` | KpiItem[] 4 (Performance 탭) |
| sites/[id] | KpiStrip + SCurveChart | web/app/(app)/dashboard/sites/[id]/page.tsx:66~74 | `detail.s_curve[]` | S-Curve 4선 카드 |
| sites/[id] | BarChartH x 2 | web/app/(app)/dashboard/sites/[id]/page.tsx:77~78 | `detail.contractor_bars[]`, `detail.trade_bars[]` | 업체별 / 공종별 생산성 막대 |
| sites/[id] | ImpactTab (scope="site") | web/app/(app)/dashboard/sites/[id]/page.tsx:88~95 | `siteImpactSummary` (Site → SitesSummary 변환), `perSiteAutomation`, `trend` | Impact 탭 (4기능별 자동화율 + 추세) |
| sites/[id] | ImpactTab→HorizontalBarList (perFunction) | web/app/components/dashboard/ImpactTab.tsx:49~54 | `perFunction[].function`, `.rate`, `.before_hours`, `.after_hours` | "Middle Office 4기능별 자동화율" |

### C-7. Diagnosis Preview (`/diagnosis-preview`) — 임시 라우트

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| diagnosis-preview | (page) | web/app/(app)/diagnosis-preview/page.tsx:53 | `SAMPLES[].input` (하드코딩 DiagnosisInput 3 종) → `diagnose(input)` | FE-내 결정적 계산 결과 카드 3 set |
| diagnosis-preview | ConfidenceBadge | web/app/components/reports/ConfidenceBadge.tsx:10~42 | `sampleSize` | dot 6 개 + "N=N 유사 케이스" |
| diagnosis-preview | GapKpiCard | web/app/components/reports/GapKpiCard.tsx:28~49 | `gap_pct`, `z_score`, `status` | 3xl 숫자 + status chip + Z 텍스트 |
| diagnosis-preview | RecoveryEtaCard | web/app/components/reports/RecoveryEtaCard.tsx:29~55 | `scenarios.{optimistic, base, pessimistic}` (`.eta_days`, `.delta_completion_days`) | 3 row 시나리오 리스트 (D-N + 단축/지연) |
| diagnosis-preview | SpiBandChart | web/app/components/charts/SpiBandChart.tsx:22~92 | `diagnosis.s_curve[]`, `.band_p25[]`, `.band_p75[]`, `.ewma_trend[]`, `.scenarios.{base,optimistic,pessimistic}.curve[]`, `.sample_size` | ComposedChart: 볼린저 음영 + 시나리오 3 선 + EWMA + 오늘 dot + ConfidenceBadge |
| diagnosis-preview | SpiBandChart→ScenarioLegend | web/app/components/charts/ScenarioLegend.tsx:1~19 | (정적 상수 ITEMS) | 차트 하단 legend 3 dot |

### C-8. Landing (`/`)

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| (landing) | LandingNav | web/app/components/landing/LandingNav.tsx | (정적 카피, 데이터 없음) | 상단 nav |
| (landing) | LandingHero | web/app/components/landing/LandingHero.tsx | (정적 카피) | hero 섹션 |
| (landing) | BackgroundSection | web/app/components/landing/BackgroundSection.tsx | (정적 카피) | 배경 섹션 |
| (landing) | AsIsToBeSection | web/app/components/landing/AsIsToBeSection.tsx | (정적 카피) | AS-IS / TO-BE 비교 |
| (landing) | ImpactSection | web/app/components/landing/ImpactSection.tsx | (정적 카피) | impact 섹션 |
| (landing) | ScalabilitySection | web/app/components/landing/ScalabilitySection.tsx | (정적 카피) | 확장성 섹션 |
| (landing) | FinalCtaSection | web/app/components/landing/FinalCtaSection.tsx | (정적 카피) | 최종 CTA |
| (landing) | LandingFooter | web/app/components/landing/LandingFooter.tsx | (정적 카피) | 푸터 |

### C-9. 공통 layout (TopBar / Sidebar / NotificationBell / UserMenu)

| Page | Component | File:Line | Field consumed | UI Element |
|---|---|---|---|---|
| (전 페이지) | TopBar | web/app/components/TopBar.tsx:5~25 | (정적) | sticky 상단 헤더 (CPIA 로고 + 우측 액션) |
| (전 페이지) | Sidebar | web/app/components/Sidebar.tsx:26~123 | `usePersona`, `useUiStore` (zustand) | 좌측 nav 5 메뉴 (persona 별 visibility 필터 — `MENU_VISIBILITY`) |
| (전 페이지) | PersonaToggle | web/app/components/PersonaToggle.tsx:12~64 | `usePersona` 상태 | member/manager 토글 (compact mode = 단일 아이콘) |
| (전 페이지) | NotificationBell | web/app/components/NotificationBell.tsx:16~141 | `MOCK_NOTIFS` (FE-내 하드코딩 3 건) | bell + 빨간 dot + 드롭다운 알림 리스트 |
| (전 페이지) | UserMenu | web/app/components/UserMenu.tsx:8~143 | `usePersona` → `USERS[persona]` (FE-내 하드코딩 2 명) | 우측 user avatar + 드롭다운 (프로필/환경설정/로그아웃) |

### §C 발견된 패턴

- **fetch 패턴이 균일** — Home 만 server component (`loadFixture` 직접), 나머지 5 화면 (dashboard / sites / tasks / review / reports) 모두 `useEffect + fetch("/api/mock/...")` client 컴포넌트 패턴. BE 전환 시 `/api/mock/` → `/api/runs` 또는 직접 BFF route 로 swap 만 하면 됨.
- **재사용 컴포넌트 dual-use** — `KpiStrip`, `BarChartH`, `SCurveChart`, `ImpactTab` 이 Report / Dashboard / Site detail 3 화면에 걸쳐 공유. props shape (특히 `KpiItem`) 이 FE↔BE 매핑 시 중간 추상 layer 가 된다.
- **legacy / dead component 다수** — `home/AgentCard.tsx`, `home/Hero.tsx`, `home/HilReviewStage.tsx`, `home/NowStrip.tsx` 4 개 모두 어디서도 import 되지 않음 (이전 design iteration 잔재). `AgentWorkflow` 가 이들을 흡수.
- **FE-내 하드코딩 mock** — `home/AgentWorkflow.tsx:32~40 COUNTS` 객체 (step → today/total 매핑), `NotificationBell.tsx:16~38 MOCK_NOTIFS`, `UserMenu.tsx:8~23 USERS`. BE 전환 시 이 셋은 별도 endpoint 필요 (notifications / users / agent_step_counts).
- **Site detail Impact 변환** — `web/app/(app)/dashboard/sites/[id]/page.tsx:39~45` 에서 `Site` 7 field → `SitesSummary` 12 field 로 zero-fill 변환. BE 가 site detail 전용 `SitesSummary` 변형을 따로 내려주거나 FE 변환 layer 유지.
- **drag-drop / 검색 가공 로직 FE side** — Review 페이지의 WBS flatten / WBS path 추적 / 카드 필터링 (`web/app/(app)/review/page.tsx:24~47`) 이 모두 FE 에서 계산. BE 는 raw 트리 + raw 카드만 주면 충분.
- **하드코딩된 default date** — `reports/page.tsx:15`, `tasks/page.tsx:16` 둘 다 `"2026-05-15"` default. BE 연동 시 `today` 또는 `latest_run_date` 로 대체.

---

## §D — 특별 분류 (lib/ utility & state)

### D-1. `web/lib/diagnosis.ts` (163 lines) — FE 자체 진단 엔진

- 역할: FE 측에서 결정론적 진단 결과를 만들기 위한 순수 함수 모듈. `mulberry32` PRNG + `hashString(site_id)` 시드로 동일 input → 동일 output 보장. EWMA, 볼린저 ±1.5σ band, 평균회귀 (mean reversion) 회복 추정, 3 시나리오 (optimistic / base / pessimistic) curve 생성.
- 노출 함수 4 개: `statusFromZ(z)` (line 10), `meanReversionRecovery(shortfall, mu, todayRate)` (line 17), `buildScenarioCurve(...)` (line 66, internal), `diagnose(input)` (line 89, **핵심**).
- input: `DiagnosisInput` (web/lib/types.ts:202)
- output: `ProductivityDiagnosis` (web/lib/types.ts:224)
- 호출 path (grep `diagnose\b` 결과):
  - `web/app/(app)/diagnosis-preview/page.tsx:1` — import
  - `web/app/(app)/diagnosis-preview/page.tsx:53` — `SAMPLES.map((s) => ({ ...s, diagnosis: diagnose(s.input) }))` 가 유일한 실 호출처. 즉 현재 **prod 라우트에서는 호출되지 않음**. preview 라우트는 자체 카피에 "Report 재구성 plan 완료 시 본 라우트는 제거됩니다" 명시 (line 63).
  - `web/tests/diagnosis.test.ts:2,57~90` — 결정성/단조성 회귀 테스트 (5 케이스).
- BE 연동 의미: `Forecaster` agent (`docs/architecture/stack.md` 참조) 가 이 함수의 출력 shape (`ProductivityDiagnosis`) 를 그대로 반환해야 FE 가 `SpiBandChart`, `GapKpiCard`, `RecoveryEtaCard`, `ConfidenceBadge` 4 컴포넌트를 변경 없이 사용 가능. FE 함수 자체는 fallback / 데모 fallback 으로 유지될 가능성 높음.

### D-2. `web/lib/use-simulation.ts` (49 lines) — Client setInterval 추상화

- 역할: 라이브 인상 (live impression) 을 만들기 위한 client-only React hook 2 종.
  - `useSimulation<T>(seed, updater, intervalMs)` (line 11) — 주기적으로 `updater(prev)` 적용한 값 반환.
  - `useSequence<T>(seq, intervalMs)` (line 31) — 배열을 1 item 씩 누적 노출.
- input type: 제네릭 `T` (호출처에서 결정).
- 호출처 (grep `useSimulation|useSequence` 결과):
  - `web/app/components/home/AgentCard.tsx:17` — `useSimulation(agent.active_count, ±1 updater, 8000)` (현재 dead component).
  - `web/app/components/home/NowStrip.tsx:20` — `useSimulation(summary.today_count, ±1 updater, 5000)` (현재 dead component).
  - `web/app/components/home/NowStrip.tsx:28` — `useSimulation(summary.last_updated, +1min updater, 60000)` (dead).
  - `web/app/components/tasks/AgentChatLog.tsx:38` — `useSequence(messages, 1500)` (**현재 사용 중**, 채팅 점진 reveal).
- BE 연동 의미: `useSequence` 는 demo polish 용이라 BE 와 무관. `useSimulation` 은 BE 가 polling 또는 SSE 로 실데이터 push 하면 대부분 제거 가능.

### D-3. `web/lib/persona.ts` (31 lines) — Persona zustand store

- 역할: 데모용 페르소나 (member / manager) 토글 + persist (localStorage key `cpia-persona`). 메뉴 visibility 정책 함께 노출.
- export: `usePersona` zustand store (line 12), `MENU_VISIBILITY` constant (line 24), `isMenuVisible(persona, menu)` helper (line 29).
- input/output type: `Persona` (web/lib/types.ts:6) — `"member" | "manager"`.
- 호출처 (grep `usePersona` 결과):
  - `web/app/components/Sidebar.tsx:28` — 메뉴 5 개를 persona 별 filter (member 는 dashboard 제외).
  - `web/app/components/PersonaToggle.tsx:12,13,14` — 토글 UI.
  - `web/app/components/UserMenu.tsx:26` — `USERS[persona]` lookup 으로 avatar/이름/롤 변경.
- BE 연동 의미: 진짜 auth 도입 시 이 store 는 server session (cookie) 으로 대체. 단 메뉴 visibility 정책은 FE-only 정책이라 유지.

### D-4. `web/lib/ui-store.ts` (20 lines) — Sidebar collapse zustand store

- 역할: Sidebar 접힘/펼침 상태 + persist (localStorage key `cpia-ui`).
- export: `useUiStore` zustand store (line 11) — `{ sidebarCollapsed, toggleSidebar, setSidebarCollapsed }`.
- 호출처 (grep `useUiStore` 결과):
  - `web/app/components/Sidebar.tsx:29,30` — `collapsed` 상태 읽기 + `toggle` 호출.
- BE 와 완전 무관 — 순수 UI preference. BE 전환 시 손댈 일 없음.

---

## 모호한 부분 / TBD

- **`mock_simulation.json` shape vs `SimulationSequence` type 불일치** — JSON 은 `home`/`tasks`/`report`/`dashboard` 4 키, type 은 `home_now_strip`/`agent_card_status`/`chat_log` 3 키. 현재 `loadFixture("simulation")` 호출처 없음. 둘 중 어느 쪽이 source-of-truth 인지 확정 필요.
- **`mock_agent_tasks.json` ↔ `chat_sequence`** — `tasks/page.tsx` 가 fetch 하는 `/api/mock/agent-tasks` route 의 응답 구조 (특히 `chatByDate` 가 어디서 오는지) 는 route.ts 를 안 열어봐서 미검증. agent_tasks fixture 에는 chat 정보 없고, chat 은 별도 `mock_chat_sequence.json` 에 있음 — route 가 둘을 merge 한다고 추정.
- **`AgentProgress.agent` 의 값 도메인** — type 상 `string` 인데 실 데이터는 `"Collector" | "Parser" | "Mapper" | "HIL Review" | "Atomizer" | "Reporter" | "Forecaster" | "Optimizer"` 8 종 (types.ts:69 주석). `"HIL Review"` 만 보통 Agent 가 아님 — BE 응답에서 이 enum 유지 필요.
- **`per_site_automation` 누락 site fallback** — `web/app/api/mock/dashboard/[id]/route.ts:15` 가 fallback 으로 항상 `m15x-ph3-ibl` 데이터 반환. BE 가 모든 site 데이터를 보장하지 않으면 빈 배열 처리 필요.
