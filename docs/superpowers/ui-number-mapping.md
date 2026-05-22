# UI 숫자 ↔ BE 매핑 점검표

> 목적: 각 화면에 표시되는 숫자가 어느 PG 컬럼/jsonb 키와 어떻게 연결되는지 추적, 오매칭 발견 시 수정 이력 기록.
> 본 문서는 시연 마감 (2026-06-05) 까지 살아있는 점검표 — fix 적용 후 표 갱신.

## 표기

- ✅ = BE↔UI 의미 일치
- ⚠️ = 의미 불일치 (오매칭) — fix 필요
- 🔧 = fix 적용 (날짜 + commit hash)

## 종합 (2026-05-21)

**fix 7건 + 발견·기록 2건**:

| # | 오매칭 | 위치 | Fix 내용 | 검증 |
|---|---|---|---|---|
| 1 | /tasks 접수 94,237건 | `agent-tasks/route.ts:53` total_count | Parser.processed 누적 → 1/일 | UI ✓ "90건" |
| 2 | s_curve lastPlanned 항상 100% | `view_builder.py:_build_s_curve` normalize | max → SUM(plan_total_qty) 분모 | v14 backfill (single-date ✓) |
| 3 | Dashboard 라벨↔산식 mismatch | `PerformanceTab.tsx:33-34` | "전사 합계"→"일평균 이상", "Optimizer 평균"→"전사 평균 단축 가능" | UI ✓ |
| 6 | /export 시트2/3 mock 잔재 | `parser_reports.job/equipment_allocations` | PG UPDATE 530 row, doy 기반 720~879 / 810~969 | UI ✓ |
| 7 | quadrant.impact=0 row 산점도 | `view_builder.py:1518` quadrant | `if impact > 0` filter | v14 backfill (single-date ✓) |
| 8 | kpi.delay/ec/recovery hardcode | `view_builder.py:1567` kpi | forecasts AGG + scenarios.base_p50 매핑 | v14 backfill (single-date ✓) |
| 9 | sites_summary.review_pending 산식 일관성 | `fixtures.ts:133` SQL | today_qty>0 추가 (review WBS fix 와 일치) | FE only |

| # | 오매칭 | 상태 |
|---|---|---|
| 4 | Agent Workflow stage 단위 모호 | 발견·기록 (디자인 가드 영향, fix 대기) |
| 5 | mapped_history.today_qty > plan_total_qty quirk | 발견·기록 (mock 데이터 큰 작업, fix 대기) |

---

## /tasks

| 위치 | 표시 | BE source | 의미 | 상태 |
|---|---|---|---|---|
| 상단 헤더 | "Agent 작업 목록 접수 N건" | `tasks[].total_count` SUM | 표시 의도 = 일자별 작업일보 건수 합 | ⚠️→🔧 (아래) |
| 상단 헤더 | "처리 M건" | `tasks[].total_count × progress_percent / 100` SUM | 위와 동일 분모 | ⚠️→🔧 |
| 일자 리스트 | 일자별 progress bar | `pipeline_runs.status` + `current_node` 매핑 | OK | ✅ |
| 일자별 → 우측 agent 카드 | Parser/Mapper/Atomizer 등 항목 | `agent-tasks API itemsByDate` | OK | ✅ |

### 오매칭 #1 — "접수 94,237건" [🔧 FIXED 2026-05-21]

**위치:** `web/app/components/tasks/DailyTaskList.tsx:27`
`totalReceived = tasks.reduce((s, t) => s + t.total_count, 0)`

**원인:** `web/app/api/mock/agent-tasks/route.ts:53`
```ts
// 변경 전 (오매칭)
const totalCount = stages.find((s) => s.agent === "Parser")?.processed ?? 0;
// → 일자별 parser_activities.processed (~1,047/일) × 90일 = 94,237건
```

**기대값:** 작업일보 = 일자별 1건 → 90일 LIMIT 면 90건

**Fix:**
```ts
// 변경 후
const totalCount = (stages.find((s) => s.agent === "Collector")?.received ?? 0) > 0 ? 1 : 0;
```
검증: "접수 90건 · 처리 90건 · 완료율 100%" ✓

### 추가 점검 항목 — Agent Workflow stage 표시

화면에서 발견:
- **02 Parser**: "접수 1 · 처리 1162" — receive=1 (작업일보 1건), processed=1162 (활동 raw). 단위 불일치.
- **03 Mapper**: "접수 1162 · 처리 349 · 30%" — % 산식이 활동/매핑 비율.
- **04 Atomizer**: "접수 343 · 처리 747" — processed > received (atomized > mapper-hil). 이상.
- **05 Exporter**: "접수 747 · 처리 1" — Exporter 결과는 일자별 1건이 정상. received 747 (Atomizer atomized count) 가 그대로 전달.
- **06 Forecaster**: "접수 349 · 처리 293" — 매핑 후 전달 mismatch.

→ stage 별 "단위 의미" 가 일관성 없음 (어떤 곳은 활동건, 어떤 곳은 보고서건). 후속 검토 필요.

---

## /reports

| 위치 | 표시 | BE source | 상태 |
|---|---|---|---|
| WP 카드 → 상세현황 → "유사 사례 생산성" | "평균 X.XX 단위/인" | `daily_reports.optimizer_view_jsonb.by_wp[wp_id].details` | ✅ (v10b 0.00 hit 2/9401) |
| WP 카드 → "공기 단축" | "−N일 / 계획 동일" | `optimizer_view_jsonb.details` | ✅ |
| 공기 단축 예측 시나리오 → "최적화 공기" | `detail.scenarios.site.base_p50.recovery_days` | `daily_reports.scenarios_jsonb` | ✅ |
| 공기 단축 예측 시나리오 → 곡선 | FE `diagnose()` 산출 | s_curve + BE recovery_days_p25/50/75 (v11 swap + v12 normalize 적용) | ✅ |
| WP 목록 → "Impact %" | `wp_summary_jsonb[].impact` (share-of-total) | view_builder `_normalize_impact` | ✅ (일별 합 = 100%) |
| 업체별 생산성 막대 | `contractor_bars[].value` | view_builder weighted_median per company | ✅ |
| 공종별 생산성 막대 | `trade_bars[].value` | view_builder weighted_median per l6_main | ✅ |
| 4분면 산점도 | `quadrant[].impact` (0 인 row 다수) + `productivity` | view_builder `_build_productivity_views_v2` | ⚠️ quadrant.impact 가 모두 0, wp_summary.impact 와 분리 |
| kpi.expected_completion | "2025-09-01" (9-25 시점에 9-01 과거) | view_builder kpi 산출 | ⚠️ 과거 일자 잘못된 값 |
| kpi.delay_days = 0 ↔ scenarios.base_p50.recovery_days = 6 | mismatch | view_builder | ⚠️ 진단 inconsistent |

### 오매칭 #7 — quadrant.impact 0 row [🔧 FIXED 2026-05-21]

**원인:** `view_builder.py:1518-1539` 의 quadrant list comprehension 이 grouped_items 의 모든 row 포함 → plan_total_qty=0 또는 plan_mh=0 인 row 는 share-of-total 산식 결과 impact=0 → 산점도에 의미 없는 점들.

**Fix:** `if (it.get("impact") or 0) > 0` filter 추가.

검증 (9-25 single-date): quadrant 10 → 5 (의미 있는 점만), wp_summary 10 그대로. quadrant 와 wp_summary 의 impact 값 동일.

### 오매칭 #8 — kpi.expected_completion 9-25 → 9-01 과거 [🔧 FIXED 2026-05-21]

**원인:** `view_builder.py:1578-1583`
```python
"delay_days": 0,                                  # ⚠️ 하드코딩
"expected_completion": str(today.replace(day=1)), # ⚠️ today 의 1일 (의미 없음)
"recovery_days": 0,
"recovered_completion": str(today.replace(day=1)),
```
즉 v2 path 의 kpi 가 **forecasts AGG 값을 무시하고 모든 값을 0 + today 1일** 로 하드코딩.

`forecasts` PG 직접 점검: 9-25 site m15x-ph3-ibl
- MAX(expected_completion) = **2026-03-31**
- AVG(delay_days) = **1.28**

**Fix:**
- `kpi.delay_days` = `round(AVG(forecasts.delay_days))` (forecasts AGG)
- `kpi.expected_completion` = `MAX(forecasts.expected_completion)` (forecasts AGG)
- `kpi.recovery_days` = `scenarios.site.base_p50.recovery_days`
- `kpi.recovered_completion` = `scenarios.site.base_p50.expected_completion`

v13 backfill 후 검증 예정.

---

## /dashboard (전사 모니터링)

| 위치 | 표시 | BE source | 상태 |
|---|---|---|---|
| 전사 평균 생산성 | "86.4%" | `fleet_kpi.avg_productivity` | ✅ |
| 평균 공기 격차 | "+9.9일" | `forecasts.delay_days AVG` | ✅ |
| 이상 공종 총합 | "33.1건" + 라벨 "일평균 이상" | `COUNT/일평균` (라벨 정확) | 🔧 2026-05-21 |
| 회복 가능 공기 | "−17.4일" + 라벨 "전사 평균 단축 가능" | `forecasts.delay_days AVG` | 🔧 2026-05-21 |
| 전사 생산성 추세 (차트 상단) | "83.1% 현장 6개 평균" | fleet_trend 산출 | ✅ |
| 현장별 카드 → 생산성 % | "88% / 96% / 94% ..." | site KPI | ✅ |
| 현장별 카드 → "공기" | "+14일 / 정상 / 정상" | site delay_days | ✅ |
| 현장별 카드 → "이상 공종" | "1 / 정상 / 정상" | site abnormal_trades | ✅ |

### 오매칭 #3 — Dashboard 라벨 ↔ 산식 [🔧 FIXED 2026-05-21]

`PerformanceTab.tsx:33-34` sub 라벨 정정:
- "전사 합계" → "일평균 이상" (산식이 COUNT/일평균이라 합계 라벨 부정확)
- "Optimizer 평균" → "전사 평균 단축 가능" (forecasts 기반, Optimizer 무관)

검증: dashboard 페이지에서 두 라벨 모두 의도와 일치.

---

## /review

| 위치 | 표시 | BE source | 상태 |
|---|---|---|---|
| WBS 좌측 트리 카운트 | FAB/CUB 옆 N | `mapper_activities` requires_review + today_qty>0 | ✅ (PR #39, today_qty 일관화) |
| 우측 카드 헤더 "N / M" | `cards.unconfirmed.length` | 동일 필터 | ✅ |

---

## /home

| 위치 | 표시 | BE source | 상태 |
|---|---|---|---|
| 오늘 처리 | "798건" | 9-25 parser_activities.processed (활동 raw 단위) | ⚠️ "처리" 단위 모호 — 활동/보고서 어느 의미? |
| 자정 이후 입수 일보 | 1건 (암시) | parser_reports | ✅ |
| Review 대기 | `mapper_activities WHERE requires_review` | today_qty>0 필터 누락 → review WBS↔카드 일관성 깨짐 | 🔧 2026-05-21 (today_qty>0 추가) |
| 누적 절감 | "4,715h" | `SUM(sites.hours_saved)` | ✅ |
| "2,506h → 351h 월평균" | sites.hours_saved 변환 | sites 테이블 cum / 월 변환 | ✅ |
| "2,506h → 351h 월평균" | h 표시 | fleet 월간 hours_saved 변화 | ⚠️ 두 숫자 의미 mismatch |
| 현재 처리 중 LIVE | "0건" | 진행 중 run | ⚠️ 9-25 데모 일자에 0건 ? |
| 7 Agent active 합산 | 정성 | — | ✅ |

### 점검 #9 — /home 숫자 매핑 추적

- "오늘 처리 798건" 의 단위 (활동 vs 보고서) 모호. /tasks 의 "접수 90건" 과 다른 단위. 통일 또는 단위 명시 필요.
- "누적 절감 4,715h" / "2,506h → 351h 월평균" 의 산식 추적 + 일관성 점검.
- "LIVE 0건" 의미 명확화.

---

## /export

| 위치 | 표시 | BE source | 상태 |
|---|---|---|---|
| 시트1 (작업사항) | bp_summaries jsonb 펼침 | `parser_reports.bp_summaries` (일자별 131~460) | ✅ |
| 시트2 (직종별 인원) | job_allocations jsonb | `parser_reports.job_allocations` (일자별 720~879) | 🔧 2026-05-21 |
| 시트3 (장비) | equipment_allocations jsonb | `parser_reports.equipment_allocations` (일자별 810~969) | 🔧 2026-05-21 |
| 시트4 (물량) | parser_activities | `parser_activities + mapper_activities` JOIN (일자별 변동) | ✅ |

### 오매칭 #6 — /export 시트2/3 일자 무관 잔재 [🔧 FIXED 2026-05-21]

**원인:** 더미 backfill 스크립트가 시트1 (bp_summaries) 만 일자별 차별화하고 시트2/3 은 cookie-cutter (966 / 1074 고정) 로 채움.

**Fix (PG UPDATE 530 row):** 사용자 명시 "10% 변동성" 부합. day-of-year 기반 결정적 LIMIT 으로 일자별 row 수 다양화.

```sql
UPDATE parser_reports
   SET job_allocations = (
     SELECT jsonb_agg(elem ORDER BY ord)
       FROM (SELECT elem, ord FROM jsonb_array_elements(job_allocations) WITH ORDINALITY AS j(elem, ord)
              WHERE ord <= (720 + (extract(doy from report_date)::int % 160))) sub
   )
 WHERE is_mock = FALSE AND jsonb_array_length(job_allocations) >= 880;
-- equipment_allocations 도 동일 패턴 (810 + doy%160)
```

검증:
- job_allocations: 모든 일자 966 → **720~879** (160 distinct values)
- equipment_allocations: 모든 일자 1074 → **810~969** (160 distinct values)
- 9-25 시트2/3: 966/1074 → 828/918. 다른 일자 (8-15 787/877, 6-15 726/816 등) 모두 다양.

backup_20260521 무변경 (public.parser_reports 만 UPDATE).

---

## 점검 이력

| 날짜 | Fix 요약 | 영향 화면 | Commit |
|---|---|---|---|
| 2026-05-21 | review WBS↔카드 today_qty>0 필터 일관화 | /review, /tasks 진행률 | 04cf77a (PR #39) |
| 2026-05-21 | 유사사례 0.00 sanitize (master ±10%) + s_curve 100 clamp + Impact share-of-total + p25/p75 swap + completionOffset 곡선 | /reports | (WIP) |
| 2026-05-21 | tasks 접수 9만건 → 일자별 1건 (parser_reports 의미) | /tasks 상단 | (WIP — 아래) |
| 2026-05-21 | s_curve normalize 분모 max → SUM(plan_total_qty). 이전 모든 일자 lastPlanned=100% 강제 → completionOffset=1 시나리오 곡선 무의미. 9-25 검증: lastPlanned 76.72%, planned100 도달 2026-03-26 (실 plan_end), remainingPlanDays 182일 | /reports 시나리오 곡선 + ForecastChart | (WIP, v12 backfill 진행) |
| 2026-05-21 | Dashboard sub 라벨 정정 ("전사 합계" → "일평균 이상", "Optimizer 평균" → "전사 평균 단축 가능") | /dashboard KPI | (FE only, 즉시 반영) |
| 2026-05-21 | /export 시트2/3 mock 잔재 발견 (job_allocations 966 / equipment_allocations 1074 모든 일자 동일) | /export 시트2/3 | (점검만, fix 대기) |
| 2026-05-21 | kpi.delay_days/expected_completion/recovery_days/recovered_completion hardcode → forecasts AGG + scenarios.site.base_p50 매핑. 9-25 검증: delay 0→1, ec 2025-09-01→2026-03-31, recovery 0→6, recovered 2025-09-01→2026-03-25 | /reports kpi 4 필드 | (v14 backfill 진행) |
| 2026-05-21 | quadrant.impact=0 row 제외 — plan_total_qty=0 / plan_mh=0 row 의 의미 없는 점 산점도 제거. 9-25 검증: 10 → 5 | /reports 산점도 | (v14 backfill 진행) |
| 2026-05-21 | /export 시트2/3 mock 잔재 fix — PG UPDATE 530 row, job_allocations doy 기반 720~879, equipment_allocations 810~969 (±10% 변동성) | /export 시트2/3 | UI ✓ |
| 2026-05-21 | sites_summary.review_pending 산식에 today_qty>0 추가 — review WBS↔카드 fix (PR #39) 와 일관성 | /home NowStrip "Review 대기" | FE only |
