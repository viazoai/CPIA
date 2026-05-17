# `/reports` Tabs 폐지 + 단일 흐름 재구성 Design

> 진단 모델 spec (`2026-05-17-cpia-productivity-diagnosis-design.md`) 의 §5-1 (B) Report 재구성을 본격 정의한다.
> 진단 모델·5 시각 컴포넌트는 PR #18 로 이미 머지됨 — 본 spec 은 그것을 실제 시연 경로 `/reports` 에 끼우는 작업.

---

## Context

PR #18 로 진단 모델(`diagnose()`, `SpiBandChart`/`GapKpiCard`/`RecoveryEtaCard`/`ConfidenceBadge`/`ScenarioLegend`) 가 완성됐지만 사용처는 임시 `/diagnosis-preview` 뿐. 임원·발주처 시연에서 핵심 가치 화면은 `/reports` 이므로 진단 산출물이 거기에 들어가지 않으면 PR #18 의 효과가 안 보인다.

**문제**: 현재 `/reports` 는 Forecast / Optimize / RawData 3 Tabs 구조. "이 현장 어떻게 돌아가나" 를 한눈에 받으려면 임원이 Tab 을 3번 클릭해야 한다. 진단·만회·근거 자료가 분리돼 있어 의사결정 스토리가 끊긴다.

**해법**: Tabs 폐지, 좌측 `ReportDailyList` (일별 선택) + 우측 **단일 세로 흐름**:
1. **현재 상태** (KPI 4 — `GapKpiCard` + 표준 KPI 3)
2. **진단** (`SpiBandChart` 메인 + `ConfidenceBadge`)
3. **회복 시나리오 · 권고** (`RecoveryEtaCard` + `OptimizerResult`)
4. **공정 분해** (업체별 / 공종별 `BarChartH` 2개)
5. **최적화 대상** (`QuadrantScatter` + `QuadrantCountKpi` + 선택 시 `OptimizerResult` 갱신)
6. **원본 데이터** (`RawDataTab`, collapsible)

**핵심 변경 정신**: 기존 모든 기능 보존, 단지 Tab 클릭 없이 한 흐름으로. "Quadrant 보고 → 다른 Tab 갈 필요 없이 그 자리에서 권고까지" 가 자연스러워진다.

---

## 1. 페이지 구조

### 1-1. 레이아웃 골격

```
┌───────────────────────────────────────────────────────────────┐
│  TopBar (셸)                                                  │
├──────────┬────────────────────────────────────────────────────┤
│ Sidebar  │ Page Header  (Operations Console 같은 헤더 + LIVE) │
│          ├────────────────────────────────────────────────────┤
│          │ ┌──────────────┬───────────────────────────────┐   │
│          │ │              │ § 1. 현재 상태 KPI 4          │   │
│          │ │              ├───────────────────────────────┤   │
│          │ │ ReportDaily  │ § 2. 진단 (SpiBandChart)      │   │
│          │ │ List         ├───────────────────────────────┤   │
│          │ │  (좌측 sticky│ § 3. 회복 시나리오 · 권고     │   │
│          │ │   일별 선택) │     RecoveryEtaCard | Optimizer│  │
│          │ │              ├───────────────────────────────┤   │
│          │ │              │ § 4. 공정 분해 (Bar 2개)      │   │
│          │ │              ├───────────────────────────────┤   │
│          │ │              │ § 5. 최적화 대상 (Quadrant)   │   │
│          │ │              ├───────────────────────────────┤   │
│          │ │              │ § 6. 원본 (RawData, collapsible)│ │
│          │ └──────────────┴───────────────────────────────┘   │
└──────────┴────────────────────────────────────────────────────┘
```

`max-w-screen-2xl` 컨테이너 유지. 좌측 `ReportDailyList` 폭은 기존 그대로(~280px).

### 1-2. 페이지 헤더

기존 `/home` `StatusHeader` 와 같은 패턴:
- eyebrow `/ 03 — Daily Report`
- 타이틀 `{site_name} · 일일 진단 보고서` (`text-h3`)
- 우측: 선택된 날짜 (mono uppercase) + 현장 status chip (mint/sun/rose)

### 1-3. § 1 — KPI 4 (현재 상태)

`grid-cols-2 xl:grid-cols-4` (모바일 2 × 2). 카드 순서:

| # | 컴포넌트 | 라벨 | 값 | tone |
|---|---|---|---|---|
| 1 | `KpiStrip` 1 카드 | 현재 생산성 | `kpi.productivity_today` % | primary 또는 |Z| 기반 |
| 2 | **`GapKpiCard`** | 평균 대비 격차 | `gap_pct` %p + Z chip | status 기반 (mint/sun/rose) |
| 3 | `KpiStrip` 1 카드 | 예상 지연 | `kpi.delay_days` 일 | `delay_days > 0 ? risk : normal` |
| 4 | `KpiStrip` 1 카드 | 회복 가능 | `kpi.recovery_days` 일 | `recovery_days > 0 ? primary : muted` |

→ 기존 `KpiStrip` 한 줄에 4 KPI 였던 것을 GapKpiCard 1개로 swap. 시각 일관성 유지 (직전 PR `KpiStrip` · `GapKpiCard` 모두 동일한 `rounded-card border-border-soft shadow-xs` 패턴).

### 1-4. § 2 — 진단 (SpiBandChart 메인)

`SpiBandChart` 단독 카드 (전체 폭). 우상단 `ConfidenceBadge` 가 이미 차트 헤더에 내장돼 있어 별도 배치 불필요. 하단 `ScenarioLegend` 도 차트 안에서 자동.

### 1-5. § 3 — 회복 시나리오 · 권고

2열 그리드 (`md:grid-cols-2`):

```
┌────────────────────────┬──────────────────────────────┐
│ RecoveryEtaCard         │ OptimizerResult              │
│  (시나리오 3 row + ETA) │  (진단·유사사례·권고·상세)   │
└────────────────────────┴──────────────────────────────┘
```

`OptimizerResult` 는 기존 컴포넌트 그대로. `RecoveryEtaCard` 신규 배치. 두 컴포넌트가 한 row 에서 "시나리오 분포 + 권고 텍스트" 짝을 이룸.

### 1-6. § 4 — 공정 분해 (BarChartH × 2)

기존 ForecastTab 의 하단 영역 그대로 분리:
- 좌: `BarChartH` items=`detail.contractor_bars` title="업체별 생산성"
- 우: `BarChartH` items=`detail.trade_bars` title="공종별 생산성"

`md:grid-cols-2` 2열.

### 1-7. § 5 — 최적화 대상 (Quadrant + Count chips + Optimizer 갱신)

기존 OptimizeTab 의 콘텐츠 그대로:
- 상단: `QuadrantCountKpi` (위험·경고·관찰·안전 4 chip, 클릭 시 filter)
- 본문: `QuadrantScatter` (selected WP id 관리)
- Quadrant 의 점 클릭 시 `selectedWpId` 갱신 → § 3 의 `OptimizerResult` 가 그 WP 의 권고로 자동 전환

→ § 3 의 OptimizerResult 가 § 5 의 Quadrant 선택과 연동. 기존 OptimizeTab 의 selection 흐름을 유지하되, 두 섹션이 떨어져 있어도 같은 state 를 공유.

### 1-8. § 6 — 원본 데이터 (RawDataTab)

`<details>` HTML 태그 또는 사용자 직접 토글 가능한 collapsible 컨테이너:

```
▼ 원본 데이터 보기 (N rows)
  ────────────────────────
  RawDataTab 콘텐츠
```

기본 접힘. 임원 의사결정 시 안 보고 넘어갈 수 있도록.

---

## 2. 데이터 흐름

### 2-1. 클라이언트 호출 패턴

`/reports/page.tsx` 는 client component (현재 그대로). 흐름:

```
fetch /api/mock/report → { daily[], details[date] }
                           ↓
       selectedDate 선택 → details[selectedDate] = ReportDetail
                           ↓
       ReportDetail.kpi + s_curve →  toDiagnosisInput()  → DiagnosisInput
                                                              ↓
                                       diagnose(input)  →  ProductivityDiagnosis
                                                              ↓
                                          (5 진단 컴포넌트에 props 로 전달)
```

### 2-2. 신규 어댑터 — `lib/diagnosis-adapter.ts`

```ts
import type { ReportKpi, SCurvePoint, Site } from "./types";
import type { DiagnosisInput } from "./types";

/** ReportDetail 기반 → DiagnosisInput 변환.
 *  history_mean/std/sample_size 는 mock 합리값.
 *  A_Track 도착 시 본 함수만 교체 (또는 본 함수 우회).
 */
export function toDiagnosisInput(
  reportKpi: ReportKpi,
  s_curve: SCurvePoint[],
  siteId: string,
): DiagnosisInput;
```

mock 값:
- `history_mean`: `reportKpi.target_productivity` (보통 ~97)
- `history_std`: 4 (고정)
- `sample_size`: `siteId` 해시 기반 12~48 균등 분포 (결정적)
- `today_progress`: `reportKpi.productivity_today`

→ A_Track 실 데이터가 `history_mean/std/sample_size` 를 직접 제공할 때 이 어댑터를 그대로 교체.

### 2-3. Quadrant ↔ OptimizerResult 연동

기존 OptimizeTab.tsx 에 `selectedWp` state 있음. /reports 페이지 레벨로 끌어올려 다음 두 컴포넌트가 공유:
- § 5 의 QuadrantScatter (`selectedWpId` prop + onSelect)
- § 3 의 OptimizerResult (선택된 WP 의 `OptimizerOutput` 표시)

기본 선택 WP: `detail.quadrant[0]` (또는 status=risk 첫 항목).

---

## 3. 신규/수정 파일

| 종류 | 경로 | 책임 |
|---|---|---|
| 수정 (대규모) | `web/app/(app)/reports/page.tsx` | Tabs 제거 + 단일 흐름 6 섹션 조립 + 진단 어댑터 호출 + Quadrant 상태 끌어올림 |
| 신규 | `web/lib/diagnosis-adapter.ts` | `toDiagnosisInput(reportKpi, s_curve, siteId)` |
| 수정 | `web/app/components/reports/ForecastTab.tsx` | **삭제** — § 2·§ 4 가 대체 |
| 수정 | `web/app/components/reports/OptimizeTab.tsx` | **삭제** — § 5 가 인라인 흡수, OptimizerResult 는 § 3 으로 분리 사용 |
| 신규 | `web/app/components/reports/SectionHeader.tsx` (선택) | 각 § 의 작은 헤더 ("/ N — 섹션명") — 신규 mini 컴포넌트로 빼서 재사용. 또는 page 내부 인라인 |
| 제거 | `web/app/(app)/diagnosis-preview/` | 본 plan 완료와 동시에 폴더 삭제 |

`ForecastTab` `OptimizeTab` 파일 자체 제거 — 다른 곳에서 import 하지 않음 (확인 필요). 만약 다른 page (예: `/dashboard/sites/[id]`) 에서 사용 중이면 그 페이지의 영향도도 spec 에 적어야 함.

---

## 4. 시각·디자인 토큰 일관성

- 모든 섹션 헤더: `font-display text-h6 text-ink` + 보조 한글 `text-body-sm text-ink-mid` (직전 PR 의 카드 헤더 통일 패턴)
- 섹션 구분: `border-t border-border-soft pt-8 mt-8` (각 § 사이 명확)
- 각 § 의 eyebrow: `text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text` (`/ N — 섹션명`)
- 카드 외형: 직전 PR 표준 `rounded-card border-border-soft bg-card shadow-xs`
- `text-h*` 의미 토큰만 사용. 임의 픽셀 금지.

---

## 5. 모바일 / 좁은 화면

- xl(1280px) 이상: 좌측 `ReportDailyList` 가 sticky side, 우측 메인 6 섹션
- md(768px) 미만: 좌측 `ReportDailyList` 가 상단으로 collapse (가로 스크롤 가능한 chip strip 또는 dropdown — 본 spec scope 밖, 기본 hidden md:block 유지)
- KPI 4 → 모바일에서 2×2

---

## 6. 검증 방법

1. `cd web && npm run build` — 15 routes 중 `/diagnosis-preview` 제거 → 14 routes
2. `cd web && npx vitest run` — 기존 26 tests 그대로 (diagnosis-adapter 단위 테스트 1~2개 추가 권장)
3. `/reports` 접속:
   - 좌측 ReportDailyList 정상 표시 + 날짜 선택 시 우측 갱신
   - § 1 KPI 4 중 2번이 GapKpiCard (status 컬러)
   - § 2 SpiBandChart — 볼린저 음영 + 시나리오 3선 + EWMA + 실적 강조 dot + ConfidenceBadge
   - § 3 RecoveryEtaCard (좌) + OptimizerResult (우) 2열
   - § 4 업체별 + 공종별 BarChartH 2열
   - § 5 QuadrantCountKpi + QuadrantScatter — 점 클릭 시 § 3 OptimizerResult 가 그 WP 권고로 갱신
   - § 6 RawData collapsible — 기본 접힘, 클릭 시 펼침
4. 다른 페이지 회귀 — `/` `/home` `/tasks` `/review` `/dashboard` 영향 없음 (단 `/dashboard/sites/[id]` 가 ForecastTab/OptimizeTab 을 쓰고 있다면 별도 처리)

---

## 7. 본 spec scope 밖

- (C) `/dashboard` 6 현장 카드 진단 지표 보강 — 별도 spec
- (D) `/home` `/tasks` 단계별 결과 보강 — 별도 spec
- `/dashboard/sites/[id]` 의 ForecastTab/OptimizeTab 의존 영향 (있다면) — 본 spec 구현 시작 시점에 별도 plan task 로 처리 결정
- 모바일 ReportDailyList collapse 패턴
- A_Track 실 데이터 연결 (`toDiagnosisInput` 교체)

---

## 8. 후속 작업

1. 본 spec 승인 → `writing-plans` plan 작성
2. plan task 단위로 subagent-driven 실행
3. 머지 후 (C) Dashboard 보완 spec 진입
