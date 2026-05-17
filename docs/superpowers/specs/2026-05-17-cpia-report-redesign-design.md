# `/reports` 인과 흐름 5 섹션 재구성 Design

> 진단 모델 spec (`2026-05-17-cpia-productivity-diagnosis-design.md`) 의 §5-1 (B) Report 재구성을 정의한다.
> 본 spec 의 **v2 (2026-05-17 PM)**: PR #20 의 6 섹션 "분석 도구 패널" 구조를 임원·발주처 의사결정 흐름에 맞춘 **5 섹션 inverted-pyramid 인과 흐름**으로 재정의.

---

## Context

PR #18 의 진단 모델·5 시각 컴포넌트는 머지됨. PR #20 으로 `/reports` 가 6 섹션 단일 흐름 (KPI / SpiBandChart / Recovery+Optimizer / BarChart / Quadrant / Raw) 으로 재구성됨.

**v2 재정의 필요성**: PR #20 의 구조는 "분석 도구 패널을 한 화면에 모았다" 에 가깝다. 한 화면에 시나리오 3종·볼린저 밴드·EWMA·4분면이 동시에 등장해 임원이 한눈에 받기 무겁고, 4분면과 SPI Band 가 시각적으로만 같은 페이지에 있을 뿐 **서로 연결되지 않았다**.

**v2 핵심 통찰**:
- 임원 의사결정은 **결론 → 근거 → 처방** 의 inverted pyramid 흐름.
- 4분면은 "Optimize 대상 픽업" 이 아니라 **"Forecasting → Optimizer 의 브릿지"** — "왜 이 시나리오?" 의 근거.
- 시나리오 3종을 한 차트에 욱여넣는 대신 **§ 3 = 현 추세, § 4 = 만회 시나리오** 로 시간상 분리.
- KPI 4 는 "운영 지표" 가 아니라 **"§ 2·§ 3·§ 4 에서 도출된 결론의 요약"**.

---

## 1. 페이지 구조 (5 섹션)

```
┌─────────────────────────────────────────────────────────────┐
│ 좌측 ReportDailyList (sticky)                                │
├─────────────────────────────────────────────────────────────┤
│ § 1 — 결론 (KPI 4)                                            │
│   "현재 84% / 평균 -12%p / 현추세 D+14 / 회복 후 -7일"         │
│   ↑ "아래에서 도출됨"                                          │
├─────────────────────────────────────────────────────────────┤
│ § 2 — 현재 상태                                                │
│   BarChartH(업체별) ‖ BarChartH(공종별)                       │
│   여기서 도출: 가중평균 → KPI #1, 이력 비교 → KPI #2           │
├─────────────────────────────────────────────────────────────┤
│ § 3 — Forecasting (현 추세)                                    │
│   단순화된 추세 차트:                                          │
│     · 계획선, 실적 점, 현 추세 1선, 신뢰 밴드 (default)         │
│     · EWMA / 시나리오 3종 = toggle off                         │
│   여기서 도출: 현 추세 공기 (KPI #3)                           │
│   차트 위 자연어 1줄 자동 해석                                 │
├─────────────────────────────────────────────────────────────┤
│ § 4 — 이슈 + 권고 (브릿지)                                     │
│   4분면 산점도 ‖ OptimizerResult                              │
│   · 4분면 = "어느 WP 가 격차 만드나" (§ 3 시나리오의 근거)     │
│   · OptimizerResult = "조치별 회복 폭"                         │
│   · WP 클릭 → § 3 차트에 만회 시나리오(mint) 추가 + Optimizer  │
│     라벨 갱신 + RecoveryEtaCard 노출                           │
│   여기서 도출: 회복 후 공기 (KPI #4)                           │
├─────────────────────────────────────────────────────────────┤
│ § 5 — 원본 데이터 (collapsible, default 접힘)                  │
│   [1] WP 요약 (시작·종료·진척·생산성·status)                   │
│   [2] 작업일보 상세 (선택 WP 로 필터)                          │
└─────────────────────────────────────────────────────────────┘
```

### 1-1. § 1 — 결론 KPI 4

기존 PR #20 KPI 4 그대로 유지 (구성 변경 없음):

| # | 라벨 | 값 | tone | 도출 위치 |
|---|---|---|---|---|
| 1 | 현재 생산성 | `kpi.productivity_today` % | `<90 risk` else normal | § 2 가중평균 |
| 2 | 평균 대비 격차 (`GapKpiCard`) | `gap_pct` %p + Z chip | status 기반 | § 2 이력 비교 |
| 3 | 현 추세 공기 | `D+{delay_days}` 일 지연 | risk | § 3 추세 |
| 4 | 회복 후 공기 | `−{recovery_days}` 일 회복 | normal | § 4 Optimizer |

KPI 위 eyebrow 에 `/ 01 — 결론` 라벨. "도출 결과" 임을 명시.

### 1-2. § 2 — 현재 상태 (BarChartH 2)

PR #20 의 § 4 그대로 위치만 이동:
- 좌: `BarChartH` items=`detail.contractor_bars` title="업체별 생산성"
- 우: `BarChartH` items=`detail.trade_bars` title="공종별 생산성"

`md:grid-cols-2` 2열. eyebrow `/ 02 — 현재 상태`, 헤더 "업체 · 공종 생산성".

산출 결과(현장 평균 / 평균 대비 격차)는 별도 카드로 표시하지 않는다 — § 1 KPI 가 그 결과. 임원이 "이 KPI 어디서 왔나" 물으면 § 2 BarChart 자체를 가리킨다.

### 1-3. § 3 — Forecasting (단순화된 추세 차트)

신규 컴포넌트 — **`ForecastChart`** (`SpiBandChart` 의 다이어트 버전).

#### Default 레이어 (4개)
1. 계획선 (planned) — `ink-light` 굵기 1.5
2. 실적 점·선 (actual) — `ink` 굵기 2 + 마지막 실적점 강조
3. 현 추세 1선 (base scenario = mean reversion) — `brand` 굵기 2.5
4. 신뢰 밴드 (P25-P75) — `brand-light/40` 음영

#### Toggle 레이어 (default off)
- EWMA 추세선
- Optimistic 시나리오 (mint)
- Pessimistic 시나리오 (rose)

토글 chip 3개 차트 우상단. 클릭 시 layer on/off.

#### 차트 위 자연어 1줄 해석

차트 헤더 옆에 한국어 한 줄로 자동 해석:

> 📊 *"이력 평균 −1.8σ — 정상 변동 범위 밖, 자연 회귀 시 12일 회복."*

생성 로직:
```
"이력 평균 {sign}{|Z|.toFixed(1)}σ — {정상 변동 범위 안|밖},
 자연 회귀 시 {base.eta_days}일 회복."
```

Z-score 같은 통계 용어를 한국어 라벨로 풀어 노출. ConfidenceBadge 는 차트 우상단 그대로.

### 1-4. § 4 — 이슈 + 권고 (4분면 + Optimizer)

PR #20 의 § 5 (4분면) + § 3 (RecoveryEtaCard + OptimizerResult) 를 **하나로 통합**.

레이아웃 (`grid-cols-12 gap-4`):
- 좌 (`col-span-6`): `QuadrantScatter` + `QuadrantCountKpi` 필터 chip
- 우 (`col-span-6`): 
  - 상단: 선택된 WP 라벨 + status chip
  - `OptimizerResult` (진단·유사사례·권고·상세)
  - `RecoveryEtaCard` (시나리오 3 ETA — 메인 만회 시나리오 강조)

#### § 3 차트와의 연동 (브릿지)

§ 4 의 위험 WP 점 클릭 시:
- `selectedWpId` 갱신 (page-level state)
- § 3 차트에 `만회 시나리오` 곡선이 mint 색으로 **추가 그려짐** (지금까지 1선이던 차트에 2번째 선)
- OptimizerResult 헤더의 "선택된 WP" 라벨 갱신
- 추가로 § 3 차트 위 자연어 해석에 한 줄 더:
  > 📊 *"이력 평균 −1.8σ — 정상 변동 범위 밖, 자연 회귀 시 12일 회복."*
  > 📊 *"AI 권고 적용 시 7일 단축 가능 (WP-3-2 거푸집 만회)."*

→ 4분면이 § 3 의 시나리오 가정의 근거가 되고, OptimizerResult 가 가능성을 정량화하는 **인과 흐름** 완성.

### 1-5. § 5 — 원본 데이터 (WP 요약 + 작업일보 상세)

`<details>` collapsible. default 접힘. 펼치면 2단 stack:

#### [1] WP 요약 테이블 — `WPSummaryTable` (신규)

```
WP명             공종   BP사     시작     종료     진척    생산성   Status
─────────────────────────────────────────────────────────────────────────
거푸집-3F        골조   A건설   05-08   05-22   78%    84%      🟡 caution
철근-3F          골조   B건설   05-10   05-25   62%    72%      🔴 risk
콘크리트-2F      골조   A건설   05-05   05-15   98%    101%     🟢 normal
...
```

행 클릭 시 `selectedWpId` 갱신 (§ 4 Quadrant 선택과 동일). 따라서 § 4 와 § 5 가 양방향 연동.

#### [2] 작업일보 상세 — 기존 `RawDataTab` 유지

선택된 WP 가 있으면 그 WP 의 행으로 자동 필터 (search 입력에 wp 코드 자동 채움 또는 별도 filter prop).

`RawDataTab` 자체 코드는 가능한 그대로 두고, page 가 필터 prop 만 추가 전달.

---

## 2. 데이터 계약

### 2-1. 기존 타입 — `web/lib/types.ts`

그대로 사용:
- `ReportKpi`, `ReportDaily`, `SCurvePoint`, `BarItem`, `QuadrantPoint`, `RawDataRow`, `OptimizerOutput`, `ProductivityDiagnosis`, `ScenarioPoint`, `DiagnosisInput`, `DiagStatus`

### 2-2. 신규 타입 — `WPSummaryRow`

`web/lib/types.ts` 에 추가:

```ts
export interface WPSummaryRow {
  wp_id: string;
  wp_name: string;       // "거푸집-3F"
  trade: string;         // "골조"
  bp_name: string;       // "A건설"
  start_date: string;    // "2026-05-08"
  end_date: string;      // "2026-05-22"
  progress_pct: number;  // 78
  productivity: number;  // 84 (Quadrant 와 동일 값)
  status: "normal" | "caution" | "risk";
}
```

### 2-3. fixture 보강

`data/mock_report.json` 의 각 date 에 `wp_summary: WPSummaryRow[]` 추가. 기존 `quadrant: QuadrantPoint[]` 와 wp_id 1:1 매칭. 4분면의 status 와 일치.

10~20 rows 정도. 시연용 일관성 (risk 2~3개, caution 4~6개, 나머지 normal).

### 2-4. 진단 어댑터 — 변경 없음

`lib/diagnosis-adapter.ts` (PR #20 신규) 그대로 사용. `diagnose()` 출력의 `scenarios.optimistic.curve` 가 § 3 차트의 "만회 시나리오" 곡선으로 사용됨.

---

## 3. 신규/수정 파일

| 종류 | 경로 | 책임 |
|---|---|---|
| 수정 (대규모) | `web/app/(app)/reports/page.tsx` | PR #20 의 6 섹션 → 5 섹션 재구성. § 3 ForecastChart 사용, § 4 통합 (Quadrant + OptimizerResult + Recovery), § 5 WPSummary stack |
| 신규 | `web/app/components/charts/ForecastChart.tsx` | SpiBandChart 의 단순화 버전 — 4 default layer + 3 toggle chip + 자연어 1줄 해석 + 클릭 시 만회 곡선 추가 |
| 신규 | `web/app/components/reports/WPSummaryTable.tsx` | WP 단위 요약 테이블 — 행 클릭 시 onSelect 콜백 |
| 수정 | `web/app/components/reports/RawDataTab.tsx` | 선택된 WP 로 자동 필터링 — `filterWpId?: string` prop 추가 |
| 수정 | `web/lib/types.ts` | `WPSummaryRow` interface 추가 |
| 수정 | `web/lib/fixtures.ts` | `ReportDetail` 에 `wp_summary: WPSummaryRow[]` 필드 추가 |
| 수정 | `data/mock_report.json` | 각 date 의 detail 에 `wp_summary` 데이터 추가 (4분면 wp_id 와 매칭) |

SpiBandChart 는 그대로 두되 본 spec 에서 사용 안 함 (후속 (D) 또는 (C) 에서 다른 화면에 재사용 가능).

---

## 4. 시각·디자인 토큰

- 모든 섹션 헤더: `font-display text-h6 text-ink` + 보조 한글 `text-body-sm text-ink-mid` + 상단 eyebrow `text-[11px] uppercase tracking-[0.12em] text-brand-text`
- 카드 외형: `rounded-card border-border-soft bg-card shadow-xs`
- 자연어 해석 줄: `text-body-sm text-ink-mid` + 좌측 이모지 📊 또는 ⚡
- 토글 chip (§ 3): `inline-flex rounded-full border px-2.5 py-1 text-[10px]`. on 일 때 `bg-brand-light text-brand-text border-brand`, off 일 때 `bg-card text-ink-light border-border`

---

## 5. 모바일 / 좁은 화면

- xl(1280px) 이상: 좌측 sticky DailyList + 우측 5 섹션
- md(768px) 미만: 좌측 hidden, 5 섹션만 (Daily 선택은 별도 dropdown 영역 — 본 spec scope 밖)

---

## 6. 검증 방법

1. `cd web && npx tsc --noEmit` — 0 errors
2. `cd web && npx vitest run` — 회귀 없음 (기존 34 tests + 신규 ForecastChart/WPSummaryTable unit test 가능하면 추가)
3. `cd web && npx next build` — 13 routes (PR #20 과 동일)
4. `/reports` 접속:
   - § 1 KPI 4 정상 (eyebrow "/ 01 — 결론")
   - § 2 BarChartH 2 (좌 업체 / 우 공종)
   - § 3 ForecastChart 4 default layer + 토글 chip 3 + 자연어 1줄
   - § 4 Quadrant + OptimizerResult + RecoveryEtaCard — WP 클릭 시 § 3 차트에 만회 곡선 추가 + § 3 자연어 한 줄 추가
   - § 5 WPSummary 테이블 + RawData 상세, 행 클릭 시 § 4 selectedWp 동기화
5. 다른 페이지 회귀 — `/` `/home` `/tasks` `/review` `/dashboard` 정상

---

## 7. 본 spec scope 밖

- (C) `/dashboard` 6 현장 카드 보강
- (D) `/home` `/tasks` 단계별 결과
- A_Track 실 데이터 연결 (`toDiagnosisInput` 교체)
- 모바일 DailyList collapse 패턴
- `detail.optimizer` 를 WP 별로 분리 — 본 spec 도 단일 OptimizerOutput 유지. WP 클릭 시 OptimizerResult body 는 그대로, 헤더 "선택된 WP" 라벨만 갱신.

---

## 8. PR #20 대비 변경 요약

| 영역 | PR #20 (v1, 6 섹션) | v2 (5 섹션) |
|---|---|---|
| KPI 의미 | 운영 지표 | **§ 2~4 에서 도출된 결론 요약** (eyebrow "결론") |
| 진단 차트 위치 | § 2 SpiBandChart (메인) | § 3 ForecastChart (단순화) |
| 시나리오 3종 | 한 차트에 3선 모두 | § 3 = base 1선 default + toggle, § 4 클릭 시 mint 추가 |
| EWMA | default 노출 | toggle off |
| 자연어 해석 | 없음 | 차트 위 1줄 자동, 한국어 |
| 4분면 위치 | § 5 (Optimizer 와 분리) | § 4 — Optimizer 와 한 row, 브릿지 역할 |
| OptimizerResult | § 3 | § 4 (Quadrant 와 짝) |
| BarChartH 2 | § 4 | § 2 (KPI 도출의 근거) |
| 원본 데이터 | § 6 RawDataTab 단독 | § 5 WP 요약 + RawData 상세 stack |
| 섹션 수 | 6 | 5 |
| 인과 흐름 | "분석 도구 패널" | **결론 → 근거 → 처방 inverted pyramid** |
| 4분면 ↔ 차트 연결 | 없음 | § 4 WP 클릭 → § 3 차트에 만회 곡선 추가 |
| 양방향 연동 | § 4·§ 5 (Quadrant ↔ OptimizerResult 라벨) | § 3·§ 4·§ 5 (Quadrant ↔ Forecast ↔ WPSummary 모두 selectedWpId 공유) |

---

## 9. 후속 작업

1. 본 spec 승인 → `writing-plans` plan 작성
2. plan task 단위로 subagent-driven 실행
3. PR 생성 (PR #20 위 추가 변경)
4. 머지 후 (C) Dashboard 보완 spec 진입
