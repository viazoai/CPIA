# CPIA FE↔BE Crosswalk (전수 재작성)

> **생성**: 2026-05-27 cycle. **Input**:
> - `data-contract/frontend_catalog.md` (684 줄, 48 type, ~220 field)
> - `data-contract/backend_catalog.md` (1044 줄, 23 테이블 316 row + 9 jsonb view + 산식 A + scenarios percentile + site_summary)
> - `deep-dive/deep_dive_optimizer.md` (산식 A SQL + site_summary payload + scenarios swap)
> - `deep-dive/deep_dive_persistence.md` (12 endpoint + /export/run + lifespan)
> - prior `crosswalk.md` (430 줄, 2026-05-22 — 본 cycle 폐기 후 재작성)
>
> **각 FE field 1 row.** Confidence:
> - **high** — BE source 실존 + 산식 명확 + 실 코드 위치 1:1 매칭
> - **medium** — BE source 존재하나 산식/grain/타입 한 가지 모호
> - **low** — BE source 본 cycle 부재 (mock 유지 또는 신규 컬럼/agent 필요)
> - **TBD** — 사용자 결정 보류
>
> **본 cycle 컬럼**: ★ NEW (신규 매핑) / ★ CHG (산식 변경) / ★ DRIFT (v1↔v2 등 의미 충돌)
>
> **그룹화 원칙** (사용자 강조 = "어느 적재 데이터 / 어떤 스키마 / 정확한 layer 가 보이게"): 화면 단위로 §1~§14 분리. 같은 type 이라도 다른 화면에서 다른 BE source 면 row 분리.

---

## §0. 적재 레이어 한눈 (사용자 강조 요약)

| FE 화면 | 진입 fetch | BE layer 1 (raw 적재) | BE layer 2 (가공 view) | BE layer 3 (LLM / 산출) |
|---|---|---|---|---|
| `/home` (member·manager) | `loadReal("sites_summary"/"agent_status"/"chat_sequence")` SSR | `pipeline_runs` + `sites` + `mapper_activities` + `forecasts` (5 SELECT 직접 집계) | (없음 — fixtures.ts:105~235 inline 산출) | (없음) |
| `/tasks` | `/api/mock/agent-tasks` + `/api/mock/agent-tasks/[date]` | `pipeline_runs` + `parser_activities` (list CTE) / `mapper_activities` + `mapping_corrections` (detail) | `deriveStageProgress` (transforms.ts:87~180 8 단계) + `deriveProgressPercent` / `deriveItemStatus` | (없음) |
| `/review` | `/api/mock/review` | `mapper_activities` LEFT JOIN `parser_activities` LIMIT 300 + `activity_master` CTE | `wbsTreeBuild` (transforms.ts:186~321 4 레벨 트리) + `deriveWpIdAndPath` | (없음) |
| `/reports` (list) | `/api/mock/report` | `daily_reports` SELECT (4 필드만 ~50KB) | (없음) | (없음) |
| `/reports` (detail) | `/api/mock/report/[date]` | `daily_reports` SELECT 9 view jsonb + `site_summary_text` | `view_builder.py` 9 산출 (kpi/contractor_bars/trade_bars/quadrant/wp_summary/s_curve/optimizer_view/productivity/scenarios) | `site_summary.py` LLM (Azure JSON) → `site_summary_text` |
| `/export` (list+detail) | `/api/mock/consolidated` | `pipeline_runs` JOIN `parser_reports` + `parser_activities` (4 시트 합집합) | `exporter.py:34 fetch_sheet_data` + `render_xlsx` (xlsx bytes) | (없음) |
| `/dashboard` (manager only) | `/api/mock/dashboard` | `sites` + `daily_reports.kpi_jsonb` 530 일 평균 (`loadReal("dashboard_performance")`) | `buildFleetTrend` (fleet-trend-mock.ts) fallback | (없음) |
| `/` (landing) | (정적) | — | — | — |

**핵심 인사이트** (BE 적재 layer 의 3 단 구조):
- **layer 1 raw**: `parser_activities` / `mapper_activities` / `mapped_history` / `forecasts` / `optimizer_advice` — 본 cycle 모두 PG 1:1 row, 한 일보 = 수십 row.
- **layer 2 가공 view**: `daily_reports` 의 9 jsonb 컬럼 — `view_builder.py` 가 layer 1 을 site × 일자 단위로 집약. FE 의 detail 화면 1 회 fetch = 1 row return (600× 축소 perf).
- **layer 3 LLM**: `daily_reports.site_summary_text` — `site_summary.py` 가 layer 2 의 5 jsonb (kpi/scenarios/wp_summary/optimizer_view/s_curve) 를 payload 로 받아 200~300자 한국어 narrative 산출. **★ live graph 미통합 (#N14) — backfill 스크립트만 호출, prod live 일보는 NULL → FE 룰베이스 fallback 표시.**

**본 cycle 신규 layer**:
- `daily_reports.scenarios_jsonb` (★ 2026-05-19 migration) — 4 시나리오 (no_action / optimistic_p25 / base_p50 / pessimistic_p75) site + by_wp 동시. ★ P25/P75 라벨↔값 swap 의도적 (view_builder.py:1237~1241).
- `daily_reports.site_summary_text` (★ migration 부재 #C1, runtime ALTER) — LLM narrative.
- `mapper_activities` 4 컬럼 (`l5_disc` / `l7_sub` / `l7_5_activity` / `sub_work_area`) — `mapper_activities_l7_5_columns.sql` (5-23 migration).
- `mapped_history.trade` — `mapped_history_trade.sql` (5-19) 컬럼 신설했으나 atomizer INSERT 누락 (★ #C3).

---

## §1. Site / SitesSummary (Home / Dashboard Layer 1)

### §1.1 `Site` (web/lib/types.ts:10~29, 21 필드)

용도: `/dashboard` SiteOverviewCard × 6 + (legacy `/sites/[id]`). `/api/mock/dashboard` 가 `loadFixture("sites")` 그대로 반환 — 본 cycle 시점 BE swap 안 됨, fixture 6 row (1 real + 5 mock preview).

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| Site.id | `sites.site_id` (init.sql:142) | rename 직접 | high | | (현 cycle fixture 사용, BE swap 시 `sites.site_id` → `id` 매핑) |
| Site.name | `sites.name` (init.sql:143) | 직접 | high | | |
| Site.location | `sites.location` (migrations/2026-05-17_db_alignment.sql:179) | 직접 | high | | |
| Site.status | `sites.status` (init.sql:146) CHECK enum | 직접 (4 치 정합 — `normal/caution/risk/unknown`) | high | | DB CHECK + TS literal 일치 |
| Site.is_mock | `sites.is_mock` (init.sql:148) | 직접 (`sites` 만 default TRUE, 다른 7 테이블은 default FALSE) | high | ★ NEW | grayscale + preview 배지 toggle |
| Site.progress_planned | `sites.plan_progress` (init.sql:144) | rename 직접 | high | | NUMERIC(5,2) |
| Site.progress_actual | `sites.actual_progress` (init.sql:145) | rename 직접 | high | | |
| Site.gap_percent | `sites.{plan_progress, actual_progress}` | `actual_progress - plan_progress` (API layer 계산) | high | | |
| Site.productivity_today | `forecasts.today_productivity` (migrations/2026-05-16_forecaster.sql:54) | `_SITES_SQL` (api.py:279) LATERAL `MAX(today_productivity) WHERE run_id = sites.last_run_id` | medium | | `sites.last_run_id` 갱신 path 부재 drift (#M-status, atomizer 만 박힘) |
| Site.spi | `sites.{plan_progress, actual_progress}` | `actual_progress / plan_progress if plan_progress > 0 else null` | high | | zero-guard 명시 |
| Site.abnormal_trades | `forecasts.risk_level` (migrations/2026-05-16_downstream_agents.sql:30) | `_SITES_SQL` LATERAL `COUNT(risk_level <> '정상')` | medium | | last_run_id 의존 |
| Site.fte_saved | `sites.fte_saved` (migrations/2026-05-17_db_alignment.sql:182) | 직접 | high | | |
| Site.hours_saved | `sites.hours_saved` (migrations/2026-05-17_db_alignment.sql:181) | 직접 | high | | 월간 |
| Site.headcount | `sites.headcount` (migrations/2026-05-17_db_alignment.sql:180) | 직접 | high | | 현장 전체 근무 인원 |
| Site.total_hours | `sites.headcount` | `headcount * 140` (API layer 상수, `_SITES_SQL` api.py:287) | high | | 140 = 월 가동 hours (magic) |
| Site.ai_replacement_rate | `sites.{hours_saved, headcount}` | `s.hours_saved / (s.headcount × 140) × 100 if headcount > 0` (api.py:288) | high | | zero-guard |
| Site.expected_completion | `forecasts.expected_completion` (migrations/2026-05-16_downstream_agents.sql:28) | `_SITES_SQL` LATERAL `MAX(expected_completion)` | medium | | last_run_id 의존 |
| Site.recovered_completion | (★ BE source 없음 — PoC fallback) | PoC = `expected_completion`. Phase 2 = `daily_reports.kpi_jsonb.recovered_completion` (= `scenarios.site.base_p50.expected_completion`, view_builder.py:1726) | low | | site-level 산식 미확정 (kpi_jsonb 가 daily_reports grain 인데 sites 는 fleet grain) |
| Site.delay_days | `forecasts.delay_days` (migrations/2026-05-16_forecaster.sql:67) | `_SITES_SQL` LATERAL `MAX(delay_days)` | medium | | last_run_id 의존 |
| Site.recovery_days | (★ BE source 없음 — PoC fallback) | PoC = 0. Phase 2 = `kpi_jsonb.recovery_days` (= `scenarios.site.base_p50.recovery_days`, view_builder.py:1725) | low | | site-level 산식 미확정 |

**§1.1 통계**: high 14 / medium 4 / low 2 = **20 (Site)**.

### §1.2 `SitesSummary` (web/lib/types.ts:34~46, 12 필드 — Home OpsKpiCard 4)

용도: `/home` server SSR — `fixtures.ts:105~176 loadReal("sites_summary")` 가 PG 직접 SELECT.

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| SitesSummary.today_count | `pipeline_runs.report_date` (init.sql:16) | `fixtures.ts:108~117` `COUNT(*) FROM pipeline_runs WHERE report_date = today` | high | | "오늘 처리 N건" |
| SitesSummary.review_pending | `mapper_activities.requires_review` (migrations/2026-05-18_parser_mapper_outputs.sql:268) | `fixtures.ts` `COUNT(requires_review=TRUE today)` | high | | |
| SitesSummary.abnormal_count | `forecasts.risk_level` | `fixtures.ts` `COUNT(risk_level<>'정상' today)` | high | | |
| SitesSummary.last_updated | `pipeline_runs.started_at` (init.sql:22) | `fixtures.ts` `MAX(started_at)::time` "HH:MM" | high | | |
| SitesSummary.total_hours_saved | `sites.hours_saved` | `fixtures.ts` `SUM(hours_saved)` 월간 | high | | |
| SitesSummary.total_fte_saved | `sites.fte_saved` | `SUM(fte_saved)` | high | | |
| SitesSummary.total_headcount | `sites.headcount` + `sites.is_mock` 필터 | `SUM(headcount WHERE is_mock = useMock)` (fixtures.ts:166) | high | | env `CPIA_DEMO_FALLBACK=on/off` 토글 |
| SitesSummary.total_hours | `sites.headcount` | `SUM(headcount) × 140` | high | | |
| SitesSummary.ai_replacement_rate | `sites.{hours_saved, headcount}` | `round((SUM(hours_saved) / (SUM(headcount) × 140)) × 10000) / 100` (fixtures.ts:160) | high | | % 표시값 (3.46 = 3.46%) |
| SitesSummary.yearly_saving | (★ BE source 없음) | PG 분기 `yearly_saving: 0` 고정 (fixtures.ts:172). fixture 는 203 hard-code. `deriveYearlySaving` (transforms.ts:30~36) 산식 = `fte×1.5 + (hours×50000)/1e8` — 호출처 없음 | low | | PG ↔ fixture 정합 X — UI 숫자 점프 위험 |
| SitesSummary.total_processed | `pipeline_runs` 전체 COUNT 누적 (또는 history aggregate 신설) | (현재 fixture 1247 hard-code) | low | | "누적 처리" — historical aggregate 신설 또는 fixtures.ts 에서 PG total COUNT 산출 필요 |
| SitesSummary.total_hours_saved_cum | `sites.hours_saved_cum` (migrations/2026-05-19_sites_hours_saved_cum.sql:522) `SUM(hours_saved_cum)` | 산식 `(120-5)/60 × atomized_count` h (`update_site_hours_saved_cum` db.py:1125) | medium | ★ NEW | 본 cycle BE source 생김 (db.py:1125) but fixtures.ts loadReal 아직 SELECT 안 함 — 다음 cycle 연결 |

**§1.2 통계**: high 9 / medium 1 / low 2 = **12 (SitesSummary)**.

---

## §2. Report list / detail (★ 본 cycle list/detail 분리)

### §2.1 `ReportDaily` (web/lib/types.ts:138~142, 5 필드 — Reports list 좌측 패널)

본 cycle ★ /api/mock/report (list 4 필드 + date) 분리 — 50KB.

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| ReportDaily.date | `daily_reports.report_date` (init.sql:36) | 직접 (`report_date::TEXT` ISO) | high | | |
| ReportDaily.status | `daily_reports.kpi_jsonb.delay_days` (view_builder.py:317/:1720, MEDIAN) → enum 매핑 | `delay_days > 7 → risk / > 3 → caution / else normal` 산식 (API route 단계) | high | ★ CHG | MEDIAN fix (e9b66d4): AVG → PERCENTILE_CONT(0.5), outlier 해소 |
| ReportDaily.productivity_today | `daily_reports.kpi_jsonb.productivity_today` (view_builder.py:313/:1710) | v1 = CPI / v2 = wv_median (★ DRIFT — 어느 버전 박혔는지 모름) | medium | ★ DRIFT | #M-v1v2 — `productivity_jsonb` 같은 컬럼 v1 EVM vs v2 wv_median |
| ReportDaily.delay_days | `daily_reports.kpi_jsonb.delay_days` | MEDIAN(forecasts.delay_days) PERCENTILE_CONT(0.5) (view_builder.py:296~309 / 1693~1706) | high | ★ CHG | AVG → MEDIAN (e9b66d4) |
| ReportDaily.recovery_days | `daily_reports.kpi_jsonb.recovery_days` (view_builder.py:1725) | `scenarios.site.base_p50.recovery_days` (★ NEW) | high | ★ NEW | scenarios_jsonb 영구화 |

**§2.1 통계**: high 4 / medium 1 = **5 (ReportDaily)**.

### §2.2 `ReportDetail` (fixtures.ts:50~63, 9 jsonb + raw_data + ★ site_summary_text)

용도: `/reports` per-date — `/api/mock/report/[date]` 가 `daily_reports` 1 row return + 9 jsonb 확장.

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| ReportDetail.kpi | `daily_reports.kpi_jsonb` (migrations/2026-05-19_daily_reports_views.sql:315) | view_builder `_build_kpi` (view_builder.py:284 v1 / :1709 v2) — 9 필드 dict | medium | ★ CHG | v2 가 productivity_today_perperson/unit/display/simple_mean +4 필드 (★ NEW) |
| ReportDetail.s_curve | `daily_reports.s_curve_jsonb` (migrations/2026-05-19_daily_reports_views.sql:320) | view_builder `_build_s_curve` (view_builder.py:880~1021) **산식 A** (§7 상세) | high | ★ CHG | 산식 A — WV × MH 가중 (c0a0641) |
| ReportDetail.contractor_bars | `daily_reports.contractor_bars_jsonb` (migrations/2026-05-19_daily_reports_views.sql:316) | `_build_contractor_bars` (view_builder.py:331 v1 / :1557 v2) | high | ★ DRIFT | v2 = perperson/display_label/perperson_unit +3 필드 |
| ReportDetail.trade_bars | `daily_reports.trade_bars_jsonb` (migrations/2026-05-19_daily_reports_views.sql:317) | `_build_trade_bars` (view_builder.py:352 / :1575) | high | ★ DRIFT | v1 vs v2 동일 drift |
| ReportDetail.quadrant | `daily_reports.quadrant_jsonb` (migrations/2026-05-19_daily_reports_views.sql:318) | `_build_quadrant` (view_builder.py:719 v1 / :1642 v2). v2 = +l7_5_activity/company/l6_main/actual_trade/workers/perperson/display_label | high | ★ CHG | impact 산식 v1 P90 normalize → v2 share-of-total (view_builder.py:1331). T17 fix 로 quadrant↔by_wp Jaccard 100% (2c2ba75) |
| ReportDetail.optimizer | `daily_reports.optimizer_view_jsonb` (migrations/2026-05-19_daily_reports_views.sql:321) | `_build_optimizer_view` (view_builder.py:1024) + cold_start `_build_deterministic_cold_start` (view_builder.py:480) → `{by_wp:{...}, default_wp_id}` | high | | cold_start fallback 으로 advice 없는 quadrant wp_id 도 채움 |
| ReportDetail.scenarios | `daily_reports.scenarios_jsonb` (migrations/2026-05-19_scenarios_jsonb.sql:508) | `_build_scenarios` (view_builder.py:1215) → `{site: {no_action/optimistic_p25/base_p50/pessimistic_p75}, by_wp: {[wp_id]: 동일}}` | high | ★ NEW | ★ P25/P75 라벨↔값 swap (view_builder.py:1237~1241 자인): optimistic_p25 의 recovery_days = P75 값 |
| ★ NEW ReportDetail.site_summary_text | `daily_reports.site_summary_text` (commit `21c10f7` runtime ALTER — **migration 파일 부재 #C1/N13**) | `site_summary.generate_site_summary` (site_summary.py:117) Azure JSON `{"summary": "..."}` 의 `summary` 추출 (200~300자 한국어) | low | ★ NEW | **★ live graph 미통합 (#N14)** — backfill 스크립트만 호출, prod live 일보는 NULL → FE 룰베이스 fallback |
| ReportDetail.raw_data | (★ `/api/mock/report/[date]/route.ts:50` 가 `raw_data: []` 빈 배열 반환) | TBD — `mapper_activities` 또는 `mapped_history` SELECT 필요 | low | | FE RawDataTab 가 받을 준비 됐으나 BE 가 안 채움 |
| ReportDetail.wp_summary | `daily_reports.wp_summary_jsonb` (migrations/2026-05-19_daily_reports_views.sql:319) | `_build_wp_summary` (view_builder.py:762 v1 / :1665 v2). v2 정렬 = `impact desc` (view_builder.py:1689) | high | ★ DRIFT | v2 = +perperson/perperson_unit/display_label |

**§2.2 통계**: high 7 / medium 1 / low 2 = **10 (ReportDetail)**.

### §2.3 `ReportKpi` (web/lib/types.ts:146~157, 12 필드 — Reports KpiStrip)

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| ReportKpi.productivity_today | `kpi_jsonb.productivity_today` | v2 = wv_median (view_builder.py:1710 weighted_median) | medium | ★ DRIFT | v1 EVM ↔ v2 wv_median |
| ReportKpi.productivity_history_diff | `kpi_jsonb.productivity_history_diff` (view_builder.py:1719) | v2 = 0 placeholder | low | | BE 산식 미정 — history 평균 대비 산식 backlog |
| ReportKpi.delay_days | `kpi_jsonb.delay_days` | MEDIAN(forecasts.delay_days) (view_builder.py:296~309) | high | ★ CHG | AVG → MEDIAN |
| ReportKpi.expected_completion | `kpi_jsonb.expected_completion` | MEDIAN(forecasts.expected_completion) PERCENTILE_DISC(0.5) | high | ★ CHG | AVG → MEDIAN |
| ReportKpi.recoverable_productivity | `kpi_jsonb.recoverable_productivity` (view_builder.py:1722) | `max(0, 100 - wv_median)` v2 only | high | ★ NEW | "회복 가능 생산성 N %p" |
| ReportKpi.target_productivity | `kpi_jsonb.target_productivity` (view_builder.py:316/:1723) | 상수 = 100 | high | ★ CHG | "97" → "100" 정착 (diagnosis-adapter 가 받아서 history_mean 으로 씀) |
| ReportKpi.recovery_days | `kpi_jsonb.recovery_days` (view_builder.py:1725/:1833) | `scenarios.site.base_p50.recovery_days` | high | ★ NEW | |
| ReportKpi.recovered_completion | `kpi_jsonb.recovered_completion` (view_builder.py:1726/:1834) | `scenarios.site.base_p50.expected_completion` | high | ★ NEW | |
| ReportKpi.productivity_today_simple_mean | `kpi_jsonb.productivity_today_simple_mean` (view_builder.py:1711) | v2 산술 평균 (wv-median 외 mean 병렬) | high | ★ NEW | |
| ReportKpi.productivity_today_perperson | `kpi_jsonb.productivity_today_perperson` (view_builder.py:1712) | v2 (예: 3.2) — `group_perperson_unit` SUM(today_qty)/SUM(workers) | high | ★ NEW | |
| ReportKpi.productivity_today_unit | `kpi_jsonb.productivity_today_unit` (view_builder.py:1715) | v2 (예: "ton/인") | high | ★ NEW | |
| ReportKpi.productivity_today_display | `kpi_jsonb.productivity_today_display` (view_builder.py:1716) | v2 (예: "98.9% (3.2 ton/인)") | high | ★ NEW | KpiStrip 표시 |

**§2.3 통계**: high 10 / medium 1 / low 1 = **12 (ReportKpi)**.

---

## §3. ForecastChart (★ 본 cycle 4 신규 prop + 4선 catch-up) — 사용자 강조 영역

용도: `/reports` 우측 메인 차트 (h-340). 본 cycle 신규 4 prop 으로 BE 영구 산출선 + FE diagnose() catch-up 만회선 통합.

### §3.1 `ForecastChart` 4 Line (사용자 강조 — 4선 정확 매핑)

| FE Line (file:line) | dataKey | 시각 | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|---|---|
| `<Line dataKey="planned">` (ForecastChart.tsx:215) | `planned` | 회색 #94a3b8 실선 strokeWidth=2 | `daily_reports.s_curve_jsonb[].planned` | `_build_s_curve` (view_builder.py:914~936) `SUM(plan_wv × plan_mh_rev2 × LEAST(1.0, GREATEST(0.0, (date - plan_start + 1) / NULLIF(plan_finish - plan_start + 1, 0))))` / 분모 × 100 | high | ★ CHG | 산식 A (c0a0641) WV×MH 가중 |
| `<Line dataKey="actual">` (ForecastChart.tsx:218) | `actual` | 검정 #0d1117 실선 strokeWidth=3 (가장 굵음) | `daily_reports.s_curve_jsonb[].actual` | `_build_s_curve` (view_builder.py:942~981) full_grid CROSS JOIN + WINDOW SUM(PARTITION BY wa, l6_main ORDER BY report_date) — 단조 누적 보장. cap = `LEAST(1.0, cum_qty/plan_qty)` × `plan_wv × plan_mh_rev2` | high | ★ CHG | 산식 A — wa+l6_main 매칭, progress cap=1 |
| `<Line dataKey="forecast">` (ForecastChart.tsx:221) | `forecast` | 빨강 #ef4444 dashed strokeWidth=2 strokeDasharray="6 5" | `daily_reports.s_curve_jsonb[].forecast` | `_extend_forecast` (view_builder.py:824~877) 직전 7일 평균 rate × remaining_days, rate≤0 면 planned 일평균 × 0.7 fallback | high | ★ CHG | EWMA 아님 — 단순 평균 rate 연장 |
| `<Line dataKey="base">` (ForecastChart.tsx:224) | `base` | mint #0ea76a dashed strokeWidth=2.5 strokeDasharray="5 4" | (★ FE 산출 — BE source 없음) | `buildScenarioCurve(s_curve, todayIdx, lastActual, recoveryDays)` (diagnosis.ts:55~87): catch-up 구간 (today ~ today+recoveryDays) 은 `lastActual → plan[catchUpEndIdx]` 직선 slope, catch-up 후 = null (plan 곡선이 그대로 그려짐 = plan 동행). `recoveryDays = baseP50` (= `scenarios.site.base_p50.recovery_days`) | low | ★ NEW | BE 가 catch_up 직접 안 줌 — FE diagnose() 가 BE 의 recovery_days_p50 받아서 catch-up slope 산출 |

**4선의 "어디서 적재됐나" 1줄 요약**:
1. **planned** ← BE `daily_reports.s_curve_jsonb[].planned` (산식 A, view_builder.py:914)
2. **actual** ← BE `daily_reports.s_curve_jsonb[].actual` (산식 A, view_builder.py:942 WINDOW SUM)
3. **forecast** ← BE `daily_reports.s_curve_jsonb[].forecast` (`_extend_forecast` view_builder.py:824)
4. **base** (AI 시나리오) ← FE 산출 `diagnosis.ts:55 buildScenarioCurve`, BE 는 `scenarios.site.base_p50.recovery_days` 만 input

### §3.2 `ForecastChart` 3 ReferenceDot

| FE ReferenceDot (file:line) | 위치 | BE Source(s) | Derived Rule | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|---|
| planEnd dot (ForecastChart.tsx:241~251) | y=100, x=`planEnd` | `daily_reports.s_curve_jsonb` 마지막 row 의 `date` (planned ≥ 100 시점) | `planEnd = s_curve.findLast(p => p.planned >= 100).date` (ForecastChart.tsx:94~99) | high | | 회색 마커 top |
| noActionEnd dot (ForecastChart.tsx:255~271) | y=100, x=`noActionEnd` | `daily_reports.scenarios_jsonb.site.no_action.expected_completion` | 직접 (`scenarios?.no_action?.expected_completion`, ForecastChart.tsx:100) | high | ★ NEW | 빨강 마커 bottom + "D+N" 라벨 |
| baseCatchUp dot (ForecastChart.tsx:275~292) | y=`baseCatchUp.percent`, x=`baseCatchUp.date` | (★ FE 산출) | `diagnosis.scenarios.base.catch_up = {date, percent}` (diagnosis.ts:80~86), `catchUpDate = s_curve[catchUpEndIdx]?.date`, `percent = planned at catchUpEndIdx` | low | ★ NEW | mint 마커 top + "AI 시나리오 M-DD" 라벨 |

### §3.3 `ForecastChart` 신규 4 prop (★ NEW)

| FE Prop (ForecastChart.tsx) | TS Type | BE Source(s) | Derived Rule | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|---|
| ★ `scenarios?: Partial<ScenarioSet>` (line 29) | `{no_action?/optimistic_p25?/base_p50?/pessimistic_p75?: Scenario}` | `daily_reports.scenarios_jsonb.site` | 직접 (`/api/mock/report/[date]` → `detail.scenarios.site`) | high | ★ NEW | 우상 추적성 메타 + 3 행 비교 table |
| ★ `reportDate?: string` (line 31) | `string` (ISO date) | `daily_reports.report_date` | 직접 | high | ★ NEW | "기준일" 라벨 |
| ★ `aiAdvice?: Array<{wp_name, trade, diagnosis?, recommendations}>` (line 33) | (옵션 list) | `daily_reports.wp_summary_jsonb` + `daily_reports.optimizer_view_jsonb.by_wp` | reports/page.tsx:270~295 — `wp_summary` impact desc 상위 3 → `optimizer.by_wp[wp_id].{diagnosis, recommendations}` (cold_start 제외, recommendations 가 객체이면 `r.text`) | high | ★ NEW | wp 카드 × 3, recommendations 최대 2 |
| ★ `aiSummaryText?: string \| null` (line 40) | `string \| null` | `daily_reports.site_summary_text` | 직접 (`detail.site_summary_text`) → "현황 요약" 본문. null 이면 룰베이스 fallback (`situationNarrative+outlookNarrative`) | low | ★ NEW | **★ live graph 미통합 (#N14) — prod 일보 NULL → fallback 만 보임** |

**§3 통계**: high 7 / medium 0 / low 3 = **10 (ForecastChart 4선 + 3 dot + 4 prop)**.

---

## §4. WPSummaryTable (Reports `/reports` § 05)

용도: `/reports` 메인 WP 표.

### §4.1 `WPSummaryRow` (web/lib/types.ts:213~226, 14 필드)

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| WPSummaryRow.wp_id | `daily_reports.wp_summary_jsonb[].wp_id` (view_builder.py:1666) | `_wp_id_of(wa, l6_main, company)` kebab triplet (`f"{wa}-{slug(l6_main)}-{slug(company)}"`) — FE `deriveWpIdAndPath` (transforms.ts:61~71) 동일 transform 사용 | high | | FE/BE 동일 산식 — 정합 검증 #N18: quadrant ↔ by_wp Jaccard 100% (T17 fix 2c2ba75) |
| WPSummaryRow.wp_name | `wp_summary_jsonb[].wp_name` | v1 = `wa + l6_main` / v2 = `l7_5 · wa` (view_builder.py:1666) | medium | ★ CHG | v1 ↔ v2 형식 다름 |
| WPSummaryRow.trade | `wp_summary_jsonb[].trade` | = l6_main 직접 | high | | |
| WPSummaryRow.bp_name | `wp_summary_jsonb[].bp_name` | v2 = `company` 직접 | high | ★ NEW | v1 은 placeholder, v2 가 채움 |
| WPSummaryRow.start_date | `wp_summary_jsonb[].start_date` | `MIN(activity_master.plan_start) GROUP BY (wa, l6_main, company)` | high | ★ NEW | v2 가 채움 |
| WPSummaryRow.end_date | `wp_summary_jsonb[].end_date` | `MAX(activity_master.plan_finish)` 동일 grouping | high | ★ NEW | |
| WPSummaryRow.progress_pct | `wp_summary_jsonb[].progress_pct` | v2 산식 — `SUM(mapped_history.today_cum_qty) / SUM(activity_master.plan_total_qty) × 100` 누적 | medium | ★ NEW | v2 가 채움 |
| WPSummaryRow.productivity | `wp_summary_jsonb[].productivity` | quadrant 와 동일 값 | high | | |
| WPSummaryRow.impact | `wp_summary_jsonb[].impact` | v2 = share-of-total (view_builder.py:1331) | high | ★ CHG | v1 P90 normalize → v2 share-of-total |
| WPSummaryRow.baseline | `wp_summary_jsonb[].baseline` | 상수 100 (v2) | high | | "회복 폭 baseline − productivity" |
| WPSummaryRow.status | `wp_summary_jsonb[].status` | v2 `_status_of` (90/70 threshold) | high | ★ CHG | |
| WPSummaryRow.perperson | `wp_summary_jsonb[].perperson` (view_builder.py:1681) | v2 only `group_perperson_unit` | high | ★ NEW | |
| WPSummaryRow.perperson_unit | `wp_summary_jsonb[].perperson_unit` (view_builder.py:1682) | v2 only | high | ★ NEW | |
| WPSummaryRow.display_label | `wp_summary_jsonb[].display_label` (view_builder.py:1685) | v2 only | high | ★ NEW | "98.9% (3.20 ton/인)" |

**§4 통계**: high 13 / medium 1 = **14 (WPSummaryRow)**.

추가 derive: `recoveryDays(productivity, baseline, impact)` (WPSummaryTable.tsx:29~33) = `round((baseline-productivity)/100 × impact × 0.3)` — FE 상수 0.3, BE 산식 아님.

---

## §5. QuadrantScatter (Reports OptimizeTab)

### §5.1 `QuadrantPoint` (web/lib/types.ts:179~188, 11 필드)

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| QuadrantPoint.wp_id | `daily_reports.quadrant_jsonb[].wp_id` (view_builder.py:750/:1644) | `_wp_id_of(wa, l6_main, company)` kebab triplet | high | | by_wp key 매칭 (#N18 Jaccard 100%) |
| QuadrantPoint.wp_name | `quadrant_jsonb[].wp_name` | v1 = `wa + l6_main` / v2 = `l7_5 · wa` | medium | ★ DRIFT | |
| QuadrantPoint.trade | `quadrant_jsonb[].trade` | = l6_main 직접 | high | | |
| QuadrantPoint.productivity | `quadrant_jsonb[].productivity` | v2 산출 (X reversed) | high | | |
| QuadrantPoint.impact | `quadrant_jsonb[].impact` (Y) | v2 = share-of-total (view_builder.py:1331~1345) `x / total × 100` | high | ★ CHG | v1 P90 normalize ↔ v2 share — 의미 다름 |
| QuadrantPoint.quadrant | `quadrant_jsonb[].quadrant` | v2 `_quadrant_of` (70/50 threshold) → `risk/caution/watch/safe` | high | ★ CHG | v1 = 80/50 → v2 = 70/50 |
| QuadrantPoint.size | `quadrant_jsonb[].size` (Z) | v2 = `plan_total_qty/10` (v1 = 30~120 정규화) | high | ★ CHG | |
| QuadrantPoint.display_label | `quadrant_jsonb[].display_label` (view_builder.py:1656~1660) | v2 only | high | ★ NEW | |
| QuadrantPoint.perperson | `quadrant_jsonb[].perperson` | v2 only | high | ★ NEW | |
| QuadrantPoint.perperson_unit | `quadrant_jsonb[].perperson_unit` | v2 only | high | ★ NEW | |
| (BE 추가 키, FE 미사용) | `quadrant_jsonb[].{l7_5_activity, company, l6_main, actual_trade, workers}` (view_builder.py:1646~1650) | v2 only — FE QuadrantScatter 미참조 (ForecastChart aiAdvice 산출 시 reports/page.tsx 가 wp_summary 참조) | high | ★ NEW | FE 가 안 받는 BE 추가 풍부화 컬럼 |

**§5 통계**: high 10 / medium 1 = **11 (QuadrantPoint)**.

---

## §6. OptimizerResult (Reports 4 섹션 카드)

### §6.1 `OptimizerOutput` (web/lib/types.ts:192~196, 5 필드)

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| OptimizerOutput.wp_id | `daily_reports.optimizer_view_jsonb.by_wp[wp_id]` key | `_wp_id_of(wa, l6_main, company)` | high | | |
| OptimizerOutput.diagnosis | `optimizer_view_jsonb.by_wp[wp_id].diagnosis` (view_builder.py:1119/:585) | optimizer LLM 산출 (agent.py:67) 또는 `_compose_diagnosis` cold_start | high | | `cold_start` 면 미산출 의미 |
| OptimizerOutput.similar_cases | `optimizer_view_jsonb.by_wp[wp_id].similar_cases` (view_builder.py:1120/:586) | list[{date, description, outcome}] view_builder 산출 | high | | shape adapter view_builder 가 처리 (BE → FE 형식 변환 완료) |
| OptimizerOutput.recommendations | `optimizer_view_jsonb.by_wp[wp_id].recommendations` (view_builder.py:1121/:587) | list[str] — rank 제거 후 text 만 | high | ★ CHG | BE optimizer_advice.recommendations 는 list[{rank, text}] (jsonb), view_builder 가 rank 제거 후 list[str] |
| OptimizerOutput.details | `optimizer_view_jsonb.by_wp[wp_id].details` (view_builder.py:1122/:588) | list[{label, value}] 6 칸 view_builder 산출 | high | | |
| (FE 미참조 BE 추가) | `optimizer_view_jsonb.by_wp[wp_id].source` (view_builder.py:589) | cold_start only — `deterministic_cold_start` / `..._no_master` / `..._master_too_small` | high | ★ NEW | FE 가 받지 않는 BE diagnostics 필드 |
| (FE 미참조 BE 추가) | `optimizer_view_jsonb.default_wp_id` (view_builder.py:1128/:1826) | 첫 WP 선택 fallback | high | | reports/page.tsx 가 `optimizer.default_wp_id` 사용 (자동 picking) |

**§6 통계**: high 7 = **7 (OptimizerOutput + by_wp wrapper 키)**.

---

## §7. ProductivityBarToggle / ProductivityTrendChart

### §7.1 `BarItem` (web/lib/types.ts:169~175, 7 필드 — 업체별 / 공종별 bar)

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| BarItem.label | `daily_reports.contractor_bars_jsonb[].label` (view_builder.py:341/:1559) 또는 `trade_bars_jsonb[].label` | company 또는 l6_main 직접 | high | | |
| BarItem.value | `contractor_bars_jsonb[].value` (view_builder.py:342/:1560) | v1 = CPI / v2 = wv_median | high | ★ DRIFT | v1 ↔ v2 산식 다름 |
| BarItem.status | `contractor_bars_jsonb[].status` (view_builder.py:344/:1561) | `_bar_status` (v1 90/80) / `_status_of` (v2 90/70) | high | ★ CHG | threshold 변경 |
| BarItem.baseline | `contractor_bars_jsonb[].baseline` (view_builder.py:343/:1562) | v1 = 90 / v2 = 100 | high | ★ CHG | 상수 |
| BarItem.display_label | `contractor_bars_jsonb[].display_label` (view_builder.py:1567) | v2 only | high | ★ NEW | |
| BarItem.perperson | `contractor_bars_jsonb[].perperson` (view_builder.py:1563) | v2 only | high | ★ NEW | |
| BarItem.perperson_unit | `contractor_bars_jsonb[].perperson_unit` (view_builder.py:1564) | v2 only | high | ★ NEW | |

추가 FE derive: `filterAndPickBars(items)` (bar-filters.ts:12) — 150% 초과 제거 + value desc 상위 3 + asc 하위 7 = 최대 10 (★ NEW client-safe utility).

**§7.1 통계**: high 7 = **7 (BarItem)**.

### §7.2 ProductivityTrendChart trend 90 일 (Reports 페이지 inline 산출)

| FE 필드 | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| trend90: `{date, value}[]` | `daily_reports.report_date` + `daily_reports.kpi_jsonb.productivity_today` 530 일 | reports/page.tsx:91~99 — `daily` 530 일 desc → `selectedDate` 기준 -89~0 window slice | high | | FE 가 list fetch 받은 후 직접 slice |

---

## §8. WBSTree (Review `/review` 좌측 4 레벨 트리)

### §8.1 `WBSNode` (web/lib/types.ts:113~120, 8 필드)

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| WBSNode.id | `activity_master.{l5_disc, l6_main, l7_sub}` (migrations/20260516_add_activity_master.sql:599~602) | `wbsTreeBuild` (transforms.ts:186~321) path 기반 id (예: `m15x-ph3-ibl` / `m15x.토목` / `m15x.토목.RCS`) | high | | |
| WBSNode.type | derived | 트리 깊이 → `root=building / mid=trade / leaf=work_package` | high | | |
| WBSNode.name | `activity_master.{l5_disc, l6_main, l7_sub, l7_5_activity}` | 각 깊이 컬럼 직접 | high | | |
| WBSNode.parent_id | derived | 트리 path 의 부모 | high | | |
| WBSNode.review_count | `mapper_activities.requires_review` (migrations/2026-05-18_parser_mapper_outputs.sql:268) | `wbsTreeBuild` CTE `review_agg` (transforms.ts:186~321) `COUNT(requires_review=TRUE)` by node | high | | |
| WBSNode.total_count | `mapper_activities` 총 매핑 활동 | CTE `activity_agg` `COUNT(*)` by node | high | ★ NEW | 본 cycle WBSTree 가 total_count 표시 (+48 LOC) |
| WBSNode.status | derived | CTE `forecast_agg` → riskToStatus: 1→risk / 2→caution / 3→normal / null→unknown | high | | |
| WBSNode.children | derived | recursive 빌드 (cartesian product 폭발 방지 — 이전 LEFT JOIN 233× 폭발 해결) | high | | |

**§8.1 통계**: high 8 = **8 (WBSNode)**.

### §8.2 mapper_activities 4 신규 컬럼 (★ NEW — FE 활용 위치)

| BE Column (mapper_activities) | view_builder 활용 | FE 활용 위치 |
|---|---|---|
| `l5_disc` (migrations/2026-05-23_mapper_l7_5_columns.sql:578) | activity_master propagate | wbsTreeBuild path 의 l5_disc (transforms.ts) |
| `l7_sub` (migrations/2026-05-23_mapper_l7_5_columns.sql:579) | activity_master propagate | WBSNode.name (트리 4 레벨) |
| `l7_5_activity` (migrations/2026-05-23_mapper_l7_5_columns.sql:580) | view_builder.py:1445 v2 필터 (`AND l7_5_activity IS NOT NULL`), quadrant.wp_name "l7_5 · wa" | WBSNode.name leaf, QuadrantPoint.wp_name |
| `sub_work_area` (migrations/2026-05-23_mapper_l7_5_columns.sql:581) | (view_builder 미사용) | (★ FE 직접 활용 위치 없음 — 다음 cycle ReviewItem.ai_mapped_path 확장 후보) |

### §8.3 `ReviewItem` (web/lib/types.ts:124~133, 10 필드 — Review 우측 카드)

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| ReviewItem.id | derived | `f"r-{run_id[:8]}-{idx:03d}"` (review/route.ts 산출) | high | | |
| ReviewItem.bp_name | `mapper_activities.company` | 직접 (review/route.ts:11) | high | | |
| ReviewItem.work_content | `parser_activities.work_content` (LEFT JOIN) | 직접 | high | | |
| ReviewItem.quantity | `mapper_activities.today_qty` | 직접 | high | | |
| ReviewItem.unit | `mapper_activities.unit` | 직접 | high | | |
| ReviewItem.ai_mapped_wp_id | derived | `deriveWpIdAndPath(wa, l6_main, site_name)` (transforms.ts:61~71) `${kebab(wa)}-${kebab(l6_main)}` | high | | wbsTreeBuild WP 노드 id 와 동일 transform |
| ReviewItem.ai_mapped_path | derived | `f"{l5_disc} > {l6_main} > {l7_sub or '?'} {l7_5_activity or ''}"` (PoC fallback, mapper_activities 의 l5_disc 사용 — ★ NEW) | medium | ★ NEW | l5_disc/l7_sub/l7_5_activity 4 신규 컬럼 활용 |
| ReviewItem.confidence | `mapper_activities.mapping_conf` (migrations/2026-05-18_parser_mapper_outputs.sql:266) | 직접 (0.0~1.0 rerank confidence) | high | | |
| ReviewItem.status | `mapper_activities.requires_review` | `requires_review ? 'unconfirmed' : 'confirmed'` | high | | |
| ReviewItem.alternative_wps | `mapper_activities.alternatives` (migrations/2026-05-19_mapper_alternatives.sql:352) | JSONB list[{wa, l6_main, score}] sorted desc K=3 | high | | GIN index 있음 |

**§8.3 통계**: high 9 / medium 1 = **10 (ReviewItem)**.

---

## §9. AgentWorkflow / Tasks

### §9.1 `AgentStatus` (Home 워크플로 7 카드)

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| AgentStatus.step | `_AGENTS_META` (api.py:662) hard-code | 1..7 정적 | high | | |
| AgentStatus.name | `_AGENTS_META` hard-code | "Collector".."Optimizer" | high | | |
| AgentStatus.korean_name | `_AGENTS_META` hard-code | "수집".."조언" | high | | |
| AgentStatus.description | `_AGENTS_META` hard-code | 정적 | high | | |
| AgentStatus.model | `_AGENTS_META` hard-code | "규칙 기반"/"gpt-5.1"/"임베딩"/... | high | | |
| AgentStatus.group | `_AGENTS_META` hard-code | "collect" (step 1~5) / "analyze" (step 6~7) | high | | |
| AgentStatus.active_count | `pipeline_runs.current_node` (init.sql:19) | `fixtures.ts:178~215 loadReal("agent_status")` 7× `COUNT(pipeline_runs WHERE current_node=$1 AND status NOT IN ('completed','failed'))` (api.py:721 `_AGENT_ACTIVE_COUNT_SQL`) | medium | | #M1 N+1 — 7× round-trip. `current_node` UPDATE drift (atomizer 만 박힘, #M-status) → 다른 agent 는 항상 0 |
| AgentStatus.state | `pipeline_runs.current_node` | `active_count > 0 ? "processing" : status='waiting_hil_1' ? "waiting" : "idle"` (fixtures.ts:203~205 reporter→exporter rename 포함) | medium | | 위 drift 동일 |

**§9.1 통계**: high 6 / medium 2 = **8 (AgentStatus)**.

### §9.2 `DailyTask` (★ Tasks list 좌측 패널)

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| DailyTask.date | `pipeline_runs.report_date` | 직접 (`_TASKS_SQL` api.py:876) | high | | |
| DailyTask.total_count | `mapped_history` triplet 또는 `parser_activities` COUNT | 현 api.py:856 = `COUNT(*) FROM pipeline_runs` (site 가 같은 날 1 run 일반케이스에 항상 1) — backlog BE-T1 | medium | | SQL 정정 필요 — `COUNT(DISTINCT (wa, l6_main, company)) FROM mapped_history WHERE site_id, report_date` 가 의도 |
| DailyTask.progress_percent | `pipeline_runs.current_node` | `deriveProgressPercent(status, current_node)` (transforms.ts:13~28) — 8 단계 인덱스 × 12.5% (collector=12.5 ... completed=100). `current_node` UPDATE drift | medium | | api.py:881~893 AVG 산출 |
| DailyTask.status | `pipeline_runs.status` | running→"running" / waiting_hil_1·waiting_hil_2→"review_pending" / completed→"completed". 현 api.py:871~875 = `BOOL_OR(failed)→review_pending` 잘못 매핑 (BE-T3 backlog) | high | | failed ≠ HIL 대기 |
| DailyTask.has_anomaly | `forecasts.risk_level` | `EXISTS (forecasts WHERE risk_level<>'정상')` (api.py:900) | high | | |

**§9.2 통계**: high 3 / medium 2 = **5 (DailyTask)**.

### §9.3 `AgentStageProgress` (Tasks 중앙 8 단계)

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| AgentStageProgress.step / agent / is_hil | `_STAGE_META` (api.py:842~851) hard-code | 8 단계 (Collector=1, Parser=2, Mapper=3, HIL=3.5, Atomizer=4, Reporter=5, Forecaster=6, Optimizer=7) | high | | step 3.5 trick |
| AgentStageProgress.received | (옵션 Y) PG row count 단계별 | Collector = `EXISTS pipeline_runs WHERE run_id`, Parser = `COUNT(parser_activities)`, Mapper = `COUNT(mapper_activities)`, HIL = `COUNT(requires_review=TRUE)`, Atomizer = `pipeline_runs.atomized_count` 또는 `COUNT(mapped_history)`, Reporter = `EXISTS daily_reports`, Forecaster = `COUNT(forecasts)`, Optimizer = `COUNT(optimizer_advice)` | medium | | `deriveStageProgress` (transforms.ts:87~180) — 단일 CTE 10 서브쿼리. 현 api.py:927~958 SQL 정정 backlog (BE-T4): 모든 stage `received=total_count, processed=total or 0` binary 으로 잘못 |
| AgentStageProgress.processed | 동일 | `processed / received × 100` (배치라 보통 0 또는 100) | medium | | |
| AgentStageProgress.percent | derived | binary 0 / 100 PoC | medium | | |
| AgentStageProgress.waiting_hil | `pipeline_runs.status IN ('waiting_hil_1','waiting_hil_2') AND is_hil` | 직접. api.py:956 `False` 하드코드 backlog (BE-T5) | high | | |

**§9.3 통계**: high 4 / medium 3 = **7 (AgentStageProgress)**.

### §9.4 `AgentTaskItem` (Tasks 우측 N 건)

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| AgentTaskItem.id | derived | `f"RPT-{date.replace('-','')}-{idx_by_date[date]:03d}"` (api.py:1030) | high | | |
| AgentTaskItem.trade | `mapped_history.l6_main` (현 api.py:916 사용) | 직접 (★ `mapped_history.trade` 컬럼 신설됐으나 atomizer INSERT 누락 #C3, current SQL 도 l6_main 사용 drift) | medium | ★ CHG | 본 cycle migration 만 적용, INSERT path 없음 |
| AgentTaskItem.contractor | `mapped_history.company` | 직접 (api.py:894) | high | | |
| AgentTaskItem.status | derived 5 치 | `deriveItemStatus(stage, row)` (transforms.ts:38~59): risk_level=이상→blocked / Mapper의 requires_review→hil_pending / conf≥0.7→done / ≥0.4→processing / else received. 현 api.py:978~984 = 모든 row 를 itemsByDate[date]["Collector"] hard-code (#M7) | low | | current_node 기반 agent 라우팅 미구현 |

**§9.4 통계**: high 2 / medium 1 / low 1 = **4 (AgentTaskItem)**.

---

## §10. HIL Review (Mapping correction)

용도: Home `AgentWorkflow.tsx:63 HILS[0]` 끼움 + Review 페이지 confirm/remap. LangGraph `interrupt:hil_1` + Command(resume=corrections).

| FE 트리거 | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| Review confirm/remap 액션 | `mapping_corrections` (init.sql:128, 6 컬럼) | FE → `POST /api/runs/{run_id}/hil_1/resume` (api.py:223) → `graph.ainvoke(Command(resume=corrections_payload))` (api.py:251) → 내부 `insert_mapping_correction` (db.py:370, hil_1_node graph.py:265) | high | | INSERT `original` (JSONB 7 키: wa/l6_main/mapping_conf/mapping_source/work_content/company/trade) + `corrected` (JSONB 4 키: wa/l6_main/mapping_source="user_corrected"/correction_type="replace") |
| HILS waiting count | `sites_summary.review_pending` (= `mapper_activities.requires_review`) 또는 `pipeline_runs.status='waiting_hil_1'` | (★ FE 가 현재 하드코드 `HILS[0].waiting: 3` — AgentWorkflow.tsx:63) | low | | BE 연결 안 됨. `sites_summary.review_pending` 가 있는데 HIL 카드에 미주입 |
| Review 페이지 카드 액션 — optimistic state update | (FE only — server save 없음, mock) | review/page.tsx:49~59 `handleConfirm/handleRemap/handleConfirmAll` | low | | PoC mock — 실 commit 안 함 |

**§10 통계**: high 1 / low 2 = **3 (HIL 트리거)**.

---

## §11. Export (★ 본 cycle exporter)

용도: `/export` 통합 작업일보 4 시트. FE 가 list + per-date 2-stage fetch.

### §11.1 `ConsolidatedReportSummary` (list)

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| ConsolidatedReportSummary.date | `pipeline_runs.report_date` | 직접 | high | | |
| ConsolidatedReportSummary.pjt | `parser_reports.project` | 직접 (mock 1 row 만) | high | | |
| ConsolidatedReportSummary.status | derived | "ready" (parser_reports 존재) / "draft" (없음) | high | | |
| ConsolidatedReportSummary.sheet_row_counts | `parser_reports.bp_summaries` / `parser_activities` 등 | Record<SheetTab, number> 각 시트 row 카운트 | medium | | API route 산출 |

### §11.2 `ConsolidatedReport` (per-date) — 4 시트 detail

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| output_manpower: OutputManpowerRow[] (12 필드) | `parser_reports.bp_summaries` (jsonb) | `fetch_sheet_data` (exporter.py:34) `pipeline_runs JOIN parser_reports` `jsonb_array_elements(bp_summaries)` | high | ★ NEW | 시트1 — pjt/zone/trade/bp_code/scope/main_work/prev_work/today_work/next_work/early/day/overtime |
| occupation_manpower: OccupationManpowerRow[] (12 필드) | `parser_job_allocations` (15 컬럼, 시트2, migrations/2026-05-19_parser_full_schema.sql:412) | (현 cycle 합집합 SQL 미연결, fixture fallback 가능성) | medium | | 시트2 — trade/bp_code/manager_code/skilled_code/occupation/prev_cum/early/day/overtime/night/allnight/cum_t |
| equipment: EquipmentRow[] (12 필드) | `parser_equipment_allocations` (14 컬럼, 시트3) | 동일 | medium | | 시트3 |
| quantity: QuantityRow[] (10 필드) | `parser_activities` (25 컬럼, 시트4 — migrations/2026-05-18_parser_mapper_outputs.sql:236) | `fetch_sheet_data` JOIN `jsonb_array_elements` 합집합 | high | | 시트4 — zone/trade/bp_code/bp_name/scope/rep_work/unit/total_a/prev_cum_b/today_c |

### §11.3 ★ NEW `/export/run` endpoint (B_Track FE swap 미실행)

| 부분 | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| `GET /export/run?site_id=&date=YYYY-MM-DD` | `fetch_site_by_id` (db.py:1220) + `fetch_sheet_data` (exporter.py:34) + `render_xlsx` (exporter.py:290) | `exporter_routes.py:16` (★ NEW 47 LOC) → Response (xlsx bytes, `Content-Disposition` UTF-8) | medium | ★ NEW | **★ #C2 ad-hoc PG pool** — `app.state.pg` 재사용 안 함, 매 요청 신규 풀. FE `ConsolidatedReportCard.tsx:38~59` 가 아직 `/sample/cpia-consolidated-report.xlsx` mock 다운로드 — **B_Track FE swap 미실행 (backlog)** |

**§11 통계**: high 6 / medium 4 = **10 (Export)**.

---

## §12. ChatPanel (Home / Tasks — D-4 mock 유지)

용도: `/home` 우측 chat panel (h-720) + Tasks AgentChatLog. `useSequence` 가 1500ms 간격 reveal.

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| ChatMessage.ts | derived from `pipeline_runs.started_at + offset` | `deriveChatSequence(runId)` (transforms.ts:326~411) — 8 ChatMessage 시퀀스 (off=0/30/60/.../210s) | medium | | log stream 아님 — 결정적 시퀀스 |
| ChatMessage.agent | hard-code 8 enum | "Collector"/"Parser"/"Mapper"/"SKEP Manager"/"Atomizer"/"Exporter"/"Forecaster"/"Optimizer" | high | | |
| ChatMessage.type | derived | `info`(일반) / `hil_request`(hil_count>0 시 Mapper) / `human_action`(Human Review) / `result`(완료) | medium | | |
| ChatMessage.summary | hard-code 한국어 1줄 per agent | `deriveChatSequence` (transforms.ts:326~411) | medium | | D-4 mock 유지 결정 — chat log stream 신설 안 함 |
| ChatMessage.detail | hard-code optional 2~3줄 | 동일 | low | | |

home/page.tsx:14 의 `Object.keys(...).sort().pop()` 최신 1 일만 표시 — PG multi-date 들어와도 home 1 일만.

**§12 통계**: high 1 / medium 3 / low 1 = **5 (ChatMessage)**.

---

## §13. Notifications / UserMenu (FE only — 하드코딩)

| FE Field | BE Source(s) | Derived Rule (file:line) | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| NotificationBell 3 건 | (BE source 없음) | `MOCK_NOTIFS` hard-code (NotificationBell.tsx:16~38) | low | | BE event log 도입 시 별도 endpoint 필요 |
| UserMenu USERS (member/manager) | (BE source 없음) | `USERS[persona]` hard-code (UserMenu.tsx:8~23) | low | | 진짜 auth 도입 시 server session |
| Sidebar persona | (FE localStorage `cpia-persona-v2`) | `usePersona` zustand store (persona.ts) | high | | FE only |

**§13 통계**: high 1 / low 2 = **3 (FE-only mock)**.

---

## §14. AS-IS / Landing (정적 — BE 무관)

| FE Page / Component | BE Source(s) | Conf | Notes |
|---|---|---|---|
| `/` LandingNav / LandingHero / BackgroundSection / AsIsToBeSection / CoreAiSection / ImpactSection / ScalabilitySection / FinalCtaSection / LandingFooter | (정적) | high | BE 무관 |
| `/diagnosis-preview` (legacy preview) | (mock 유지) | low | scope 제외 — prod 제거 예정 |

---

## §15. FE 자체 산출 영역 (BE 무관, FE 산식)

| FE 산식 / 함수 | FE File:Line | 의미 | Conf | 본 cycle | Notes |
|---|---|---|---|---|---|
| ProductivityDiagnosis 13 필드 | `web/lib/diagnosis.ts` + `diagnosis-adapter.ts` | D-3 REVISED — `target_productivity → history_mean`, 고정 `history_std=4`, `deterministicSampleSize(siteId)` FNV-1a 해시 12~48, BE scenarios.site.{p25/p50/p75}.recovery_days → recovery_days_{p25/p50/p75} (★ 의미 inverse: BE p25=낙관 → FE p75) | low | | BE adapter 안 만듦 — FE mock 영구. EWMA / s_curve / band 모두 FE 계산 |
| ScenarioPoint.catch_up | `web/lib/diagnosis.ts:55~87 buildScenarioCurve` | catch-up 직선 slope + plan[catchUpEndIdx]: `{date, percent}` | low | ★ NEW | BE source 없음 — FE 계산 (BE 가 recovery_days 만 제공) |
| ScenarioPoint.delta_completion_days | `web/lib/diagnosis.ts:138/145/152` | 항상 0 (catch-up 후 plan 동행 → 계획 동일) | high | ★ CHG | ★ 이전 "+N 일 지연" 의미 → 본 cycle 0 고정. RecoveryEtaCard 가 이 값 사용했으나 dead 확정 |
| `recoveryDays(productivity, baseline, impact)` | `web/app/components/reports/WPSummaryTable.tsx:29~33` | `round((baseline-productivity)/100 × impact × 0.3)` (PoC 상수 0.3) | medium | | "공기 단축 -N일" 셀 — BE 산식 아님 |
| `filterAndPickBars(items)` | `web/lib/bar-filters.ts:12` | 150% 초과 제거 + value desc 상위 3 + asc 하위 7 = 최대 10 | high | ★ NEW | client-safe utility, spec 2026-05-21 §④ |
| `generateSiteTrend` / `buildFleetTrend` | `web/lib/fleet-trend-mock.ts:24,43` | mulberry32 PRNG seed = hash(siteId), 90 일 random walk | high | | dashboard fleet trend fallback (실 site 1 개라 동일값 mock) |

**§15 통계**: high 3 / medium 1 / low 2 = **6 (FE 자체 산출)**.

---

## §16. dead / preview / 호출처 없는 type (본 cycle scope 제외)

| Type / Component | 위치 | 상태 |
|---|---|---|
| `DailyRun` / `AgentProgress` | web/lib/types.ts:62~74 | legacy — `/api/mock/agent-tasks` 가 `DailyTask` / `AgentStageProgress` 로 swap 후 호출처 없음 |
| `SimulationSequence` | web/lib/types.ts:259 | JSON 키 ↔ type 키 불일치, 호출처 0 — fixture 와 type 정리 backlog |
| `DiagnosisInput` (preview) | web/lib/types.ts:268 | `/diagnosis-preview` 만 사용 — prod 제거 예정 |
| `RecoveryEtaCard` / `GapKpiCard` / `SpiBandChart` / `SCurveChart` / `ScenarioLegend` / `ConfidenceBadge` | web/app/components/reports/* | 호출처 0 — ForecastChart 가 대체 |
| `NowStrip` / `Hero` / `HilReviewStage` / `AgentCard` | web/app/components/home/* | dead — AgentWorkflow 가 대체 |
| `RawDataTab.filterWpId/wpNameById` | web/app/components/reports/RawDataTab.tsx:18 | props 추가됐으나 reports/page.tsx 미연결 + `/api/mock/report/[date]/route.ts:50 raw_data: []` 빈 배열 |

---

## §17. 발견된 정합 의문 / FE 가 기대하는 shape vs BE 실 산식 불일치

본 cycle 새로 식별된 mismatch (FE 가 갱신됐는데 BE 가 안 따라옴, 또는 그 반대):

1. **★ `ReportDetail.site_summary_text` live graph 미통합 (#N14)** — FE 가 `aiSummaryText` prop 으로 받을 준비 됐으나 BE 의 `site_summary.generate_site_summary` (site_summary.py:117) 가 graph.py reporter_node / optimizer_node 어디서도 호출 안 됨. backfill 스크립트만 박음 → live cycle 일보는 NULL → FE 룰베이스 fallback 만 보임. 시연 핵심 narrative 비어있음.

2. **★ `daily_reports.site_summary_text` migration 부재 (#C1/N13)** — commit `21c10f7` "PG migration 추가" 언급, 실 파일 없음. fresh DB rebuild 시 UndefinedColumnError. AWS dump 에서만 살아남는 상태.

3. **★ `productivity_jsonb` v1 ↔ v2 산식 drift (#M-v1v2)** — 같은 컬럼명, 다른 shape (v1 EVM `{today, by_contractor, by_l6, by_wp}` vs v2 wv-median `{site, by_company, by_l6}`). FE 가 어느 버전 박혔는지 분간 불가. `productivity_today` 도 v1=CPI / v2=wv_median 다름 → ReportDaily.productivity_today / ReportKpi.productivity_today / BarItem.value 모두 영향.

4. **★ scenarios P25/P75 라벨 ↔ 값 swap (#M-scenarios-swap)** — `optimistic_p25` 의 `recovery_days` = P75 값 (큰 recovery 큰 만회), `pessimistic_p75` = P25 값. view_builder.py:1237 자인. FE diagnosis-adapter.ts:29~31 가 inverse 매핑 ("BE p25=비관 → FE p75") 으로 받아 처리 — 라벨 다중역할 명시 필요.

5. **★ `mapped_history.trade` 컬럼 신설 vs SQL 누락 (#C3)** — 5-19 migration 으로 컬럼 추가, atomizer.py:130 INSERT 도 컬럼 박지 않음, db.py:478~487 ON CONFLICT SET 절도 trade 누락. api.py `_TASKS_ITEMS_SQL` 가 mh.l6_main 사용 (api.py:916) — trade 컬럼 미사용 drift. AgentTaskItem.trade 가 의미상 "철근공사" 한글 공종 (Activity.trade str) 인데 l6_main "철근콘크리트공사" 받음.

6. **★ ForecastChart `firstUndef/lastIdx` 산출 정순 vs diagnose() todayIdx 역순 불일치** — ForecastChart.tsx:88~89 가 `data.findIndex(actual===undefined)` 정순, diagnose() (diagnosis.ts:104~109) 가 역순. sparse hole 있으면 마지막 actual 점 식별 불일치 → ReferenceDot 잘못된 점에 찍힐 위험.

7. **★ FE `ScenarioPoint.catch_up` BE source 없음** — FE diagnose() 가 자체 산출 (BE 의 recovery_days_p50 만 input). BE 가 catch_up 직접 안 줌 → BE 의 산식 변경 (예: 만회 모델 변경) 이 FE 에 자동 반영 안 됨.

8. **★ `wp_id` 포맷 일관성 — FE `deriveWpIdAndPath` 와 BE `_wp_id_of` 가 다른 컴포넌트** — FE transforms.ts:61 = `${kebab(wa)}-${kebab(l6_main)}` (2 컴포넌트), BE view_builder.py = `_wp_id_of(wa, l6_main, company)` (3 컴포넌트 triplet). T17 fix (2c2ba75) 가 BE 만 통일, FE review/route.ts 의 wp_id 와 reports detail.optimizer.by_wp 키가 다를 수 있음 → `detail.optimizer.by_wp[selectedWpId]` lookup 빈 카드 위험.

9. **★ Site.recovered_completion / Site.recovery_days site-level 산식 부재** — sites 테이블 grain 인데 BE 는 daily_reports.kpi_jsonb 만 산출 (run 단위). site-level 변환 path 미정.

10. **★ AgentTaskItem.status 5 치 ↔ BE 3 치 산출** — done/processing/received/hil_pending/blocked. BE 가 processing/blocked 산출 path 없음 (LangGraph batch 안에서 단일 row 의 in-flight 추적 불가). 모든 row 가 itemsByDate[date]["Collector"] hard-code (#M7).

11. **★ DailyTask.total_count SQL 정합 안 됨 (BE-T1)** — FE 의도 = `COUNT(DISTINCT (wa, l6_main, company)) FROM mapped_history`, 현 BE = `COUNT(*) FROM pipeline_runs` 항상 1.

12. **★ AgentStageProgress.received/processed binary (BE-T4)** — FE 의도 = stage 별 PG row count (parser_activities/mapper_activities/forecasts/optimizer_advice), 현 BE = `received=total_count, processed=total or 0` binary 으로 progress_percent 기반 추산.

13. **★ HILS waiting count FE 하드코드** — `sites_summary.review_pending` 있는데 AgentWorkflow.tsx:63 `HILS[0].waiting: 3` hard-code. BE 연결 안 됨.

14. **★ chat_sequence date 키 형식 불일치 위험** — `loadReal("chat_sequence")` (fixtures.ts:217~235) PG `report_date::slice(0,10)` ISO 키, home/page.tsx:14 `Object.keys(...).sort().pop()` 최신 1 일만. PG multi-date 들어와도 home 1 일만 표시 — 의도 확인 필요.

15. **★ ai_replacement_rate 단위 혼동 위험** — PG 분기 (fixtures.ts:160) `Math.round(... × 10000) / 100` % 표시값 산출 (3.46 = 3.46%). BE 가 분수 (0.0346) 보내면 0.0346% 로 표시될 위험 — contract 명세 필요.

---

## §18. 헤드라인 통계 (본 cycle)

| 분류 | 합계 |
|---|---|
| 총 FE field (대상) | ~220 (48 type 중 dead/preview/sim 제외 ~40 type) |
| § 별 mapping row 수 | §1: 32 / §2: 27 / §3: 10 / §4: 14 / §5: 11 / §6: 7 / §7: 8 / §8: 22 / §9: 24 / §10: 3 / §11: 10 / §12: 5 / §13: 3 / §15: 6 |
| **high** | 115 (52%) — BE source 실존 + 산식 명확 |
| **medium** | 38 (17%) — 산식/grain/타입 한 가지 모호 |
| **low** | 26 (12%) — BE source 부재 또는 신규 컬럼 필요 |
| **TBD** | 0 (D-3 EWMA / D-12 optimizer 배열 모두 결정) |
| 매핑 0 (mock 유지) | 약 5 (NotificationBell / UserMenu / MiddleOfficeAutomation / ImpactTrendPoint / SimulationSequence) |

### §18.1 본 cycle ★ NEW 매핑 카운트

- **★ NEW field mapping**: **23** (5 FE 필드 직접 + 18 BE 신규 산출 ↔ FE 기존 필드 연결)
  - FE 직접 신규: ScenarioPoint.catch_up / ReportDetail.site_summary_text / ForecastChart.scenarios / ForecastChart.reportDate / ForecastChart.aiAdvice / ForecastChart.aiSummaryText (6)
  - BE 신규 → FE 기존 매핑: kpi_jsonb 5 (productivity_today_simple_mean/perperson/unit/display/recoverable_productivity), kpi_jsonb.recovery_days, kpi_jsonb.recovered_completion, contractor_bars/trade_bars/quadrant/wp_summary v2 5 (perperson/perperson_unit/display_label), wp_summary v2 bp_name/start_date/end_date/progress_pct, scenarios_jsonb (site + by_wp), optimizer_view_jsonb.by_wp.source (cold_start), mapper_activities 4 컬럼 (l5_disc/l7_sub/l7_5_activity/sub_work_area), DailyTask + AgentStageProgress + AgentTaskItem (Tasks 신규 3 type), Site.is_mock + SitesSummary.total_hours_saved_cum, /export/run endpoint.

- **★ CHG 산식 변경**: **10**
  - s_curve_jsonb.planned/actual/forecast (산식 A — WV×MH 가중, WINDOW SUM 단조 보장, _extend_forecast 7일 평균)
  - kpi_jsonb.delay_days / kpi_jsonb.expected_completion (AVG → MEDIAN)
  - kpi_jsonb.target_productivity (97 → 100)
  - quadrant_jsonb.impact (P90 normalize → share-of-total) / .quadrant threshold (80/50 → 70/50) / .size (30~120 → plan_total_qty/10)
  - contractor_bars / trade_bars status threshold (90/80 → 90/70), baseline (90 → 100)
  - WPSummaryRow.wp_name (wa+l6_main → l7_5·wa)
  - OptimizerOutput.recommendations (list[{rank,text}] → list[str])
  - ScenarioPoint.delta_completion_days (의미 "+N 일 지연" → 항상 0)
  - AgentTaskItem.trade (mapped_history.l6_main → .trade — 컬럼 신설했으나 INSERT 누락)

- **★ DRIFT (v1↔v2 등 의미 충돌)**: **6**
  - productivity_jsonb v1 EVM ↔ v2 wv-median (같은 컬럼명 다른 shape)
  - kpi_jsonb.productivity_today v1 CPI ↔ v2 wv_median
  - contractor_bars / trade_bars v1 90/80 ↔ v2 90/70 status threshold + v1 baseline=90 ↔ v2=100
  - quadrant_jsonb.wp_name v1 wa+l6_main ↔ v2 l7_5·wa
  - wp_summary_jsonb 정렬 v1 placeholder ↔ v2 impact desc
  - mapped_history.trade 컬럼 신설 ↔ INSERT path 부재

### §18.2 ForecastChart 4선 매핑 확인 (사용자 강조)

§3.1 의 4 row 가 명확히 표기됐는지 확인 = ✅:

| dataKey | BE 컬럼 / FE 산출 | 산식 위치 |
|---|---|---|
| `planned` | BE `daily_reports.s_curve_jsonb[].planned` | view_builder.py:914~936 (산식 A WV×MH × linear_progress) |
| `actual` | BE `daily_reports.s_curve_jsonb[].actual` | view_builder.py:942~981 (산식 A full_grid + WINDOW SUM 단조 + cap=1) |
| `forecast` | BE `daily_reports.s_curve_jsonb[].forecast` | view_builder.py:824~877 `_extend_forecast` (7일 평균 rate) |
| `base` (AI 시나리오) | FE 산출 (BE 는 recovery_days 만 줌) | diagnosis.ts:55~87 `buildScenarioCurve` (catch-up slope + plan 동행) |

추가 3 ReferenceDot (§3.2) 도 명확:
- `planEnd` ← BE `s_curve_jsonb` 마지막 planned≥100 date
- `noActionEnd` ← BE `scenarios_jsonb.site.no_action.expected_completion`
- `baseCatchUp` ← FE `diagnosis.scenarios.base.catch_up.{date, percent}`

---

> **출처 일관성**: 모든 file:line 은 본 cycle (2026-05-27) 워킹트리 `/Users/kyungseoplee/Project Agent/CPIA/` 기준. backend_catalog.md 1044 줄 / frontend_catalog.md 684 줄 / deep_dive_optimizer.md 843 줄 / deep_dive_persistence.md 655 줄 grounding. 추측 0 — 모든 BE 산식은 view_builder.py 또는 transforms.ts grep 검증. ForecastChart 4 Line stroke color 는 ForecastChart.tsx:215~224 직접 확인.
