# CPIA 생산성 진단 로직 — Hybrid (이력 평균 × 금융공학 시각화) Design

> 진단 로직 정합성 / 시연 신뢰도 확보를 위한 분석 모델·시각화·데이터 계약 정의.
> 본 spec 은 **분석 모델·시각 컴포넌트 계약**까지를 정의한다. Report 화면 재구성(B) · Dashboard 보완(C) · Tasks/Home 재구성(D) 은 본 모델을 입력으로 받아 각각 별도 spec/plan 으로 분기한다.

---

## Context

현재 `/reports` `/dashboard` 는 단순 카드·차트 나열에 머물고 있어 **"왜 이 수치가 나왔고 무엇을 해야 하는가"** 의 인사이트가 약하다. 사용자가 직접 지적한 세 가지:

1. Agent 단계별 결과가 화면에 안 나와 흐름이 가시화 안 됨
2. 진단 보고서가 "현재 생산성 → 평균 격차 → 회복 가능성 → 공기 단축 → 조치" 의 추정 로직 신뢰도가 부족
3. (2) 가 약하니 Dashboard 도 단순 KPI 나열로 보임

본 spec 은 (2)를 정조준한다. 분석 모델을 정통 건설 지표(EVM) + 주식 분석 기법(볼린저 밴드 · EWMA · 평균 회귀) **하이브리드** 로 정립하면 발주처·임원 모두에게 설득력 있는 진단 + 시연 컨셉 어필을 동시에 잡을 수 있다. 정확히 일치하는 시각 컴포넌트 계약을 함께 정의해 (B)·(C)·(D) 가 동일 모델 위에서 빌드되도록 한다.

**컨셉 카피 (시연용)**: "건설 공정에 금융공학을 접목 — 동일 공종 과거 유사 케이스(Vector RAG)를 모집단으로, 주식 분석법으로 현 상태를 해석한다."

---

## 1. 분석 모델

### 1-1. 기준선 — "생산성 100% = 이력 평균"

모든 지표의 기준은 **동일 공종 × 유사 현장 × 유사 단계의 과거 이력 평균** (`μ`) 이다. 절대 기준(품셈) 을 쓰지 않는다는 CLAUDE.md 의 차별점과 정합.

- `μ` (history_mean): 동일 공종 × 유사 케이스 일진척률 평균
- `σ` (history_std): 동일 표본의 표준편차
- `N` (sample_size): 표본 크기 (유사 과거 케이스 수)

### 1-2. 4개 핵심 지표

| # | 지표 | 정의 / 공식 | 차용 |
|---|---|---|---|
| 1 | **현재 생산성** | `productivity = today_progress / μ × 100`. 100 = 이력 평균만큼. | EVM 변형 (계획 → 이력 평균) |
| 2 | **평균 대비 격차** | `gap_pct = productivity − 100` (%p). `Z = (today_progress − μ) / σ` 로 정상/주의/이상 판정. | SPC 관리도 · 볼린저 ±2σ |
| 3 | **회복 가능 폭** | Mean Reversion 가정: `recovery_days = (cumulative_shortfall) / (μ − today_rate)`. **분모 ≤ 0** (오늘 진척이 평균 이하라 격차 확대 중) 이면 `recovery_days = ∞` 로 표시하고 status `risk` 강제. P25·P50·P75. | 평균 회귀 |
| 4 | **공기 단축 예측** | 시나리오 3종 ETA. base 는 (3), optimistic/pessimistic 은 가정 변동. | Monte Carlo light (단일 경로) |

### 1-3. Z-score → 상태 매핑

| `\|Z\|` | 상태 | 색 |
|---|---|---|
| `< 1` | 정상 | mint (status normal) |
| `1 ~ 2` | 주의 | sun (status caution) |
| `≥ 2` | 이상 | rose (status risk) |

볼린저 ±2σ 와 동일 임계.

### 1-4. 시나리오 3종

| 시나리오 | 가정 | 색 | 비고 |
|---|---|---|---|
| **Optimistic** | Optimizer 권고 catch-up 적용 + 평균보다 빠른 회복 | `mint` | "AI 만회 시나리오" |
| **Base** | 현재 추세 + 자연 평균 회귀 (개입 없음) | `lavender` (= primary blue `#1a56db`) | 메인 강조선 |
| **Pessimistic** | 현재 추세 유지 (회귀 없음) | `rose` | 위험 시그널 |

각 시나리오는 다음을 산출:
- `eta_days`: 평균 도달 또는 공기 만회 예상 일수
- `recovery_pct`: 회복 후 예상 진척률
- `delta_completion_days`: 계획 완공일 대비 ±N일

### 1-5. 신뢰도 표현

- **볼린저 밴드** — Base 시나리오 곡선 주변 P25–P75 음영. 밴드 폭 좁을수록 확신↑.
- **EWMA 추세선** — 최근 가중 평균. 최근 며칠 가속/감속 시각화. 보조선(ink-mid).
- **샘플 크기 라벨** — `"N개 유사 케이스 기반"` chip. `N < 20` 일 때 sun 경고 톤.

---

## 2. 색 매핑

본 spec 의 모든 시각 컴포넌트는 다음 매핑을 단일 출처로 따른다. `design-system.md §2-1` 의 status 톤과 일관.

| 용도 | 토큰 | hex |
|---|---|---|
| Base 시나리오 (메인) · 신뢰 밴드 · 강조선 | `lavender` (primary) | `#1a56db` |
| 볼린저 음영 | `lavender-light/40` | `#e8eeff` 40% |
| Optimistic 시나리오 · 정상 상태 | `mint` | `#0ea76a` |
| Pessimistic 시나리오 · 이상 상태 | `rose` | `#ef4444` |
| 주의 상태 · 샘플 부족 경고 | `sun` | `#d97706` |
| EWMA 추세선 · 보조 텍스트 | `ink-mid` | `#444e5e` |
| 샘플 chip 중립 배경 | `surface-soft` | `#f3f5f9` |

색 의미: **메인 컬러(blue)는 Base 시나리오·신뢰 밴드에만**. mint/sun/rose 는 시스템 status 패턴과 정확히 일치하는 의미 톤 (정상/주의/이상). 시연 화면 전체에서 색 의미가 단조롭지 않게 분기.

---

## 3. 데이터 계약

### 3-1. 신규 타입 — `web/lib/types.ts`

```ts
// 진단 모델 핵심 입력·산출물
export interface ProductivityDiagnosis {
  // 기준선
  history_mean: number;          // μ — 이력 평균 일진척률 (%)
  history_std: number;           // σ
  sample_size: number;           // N — 유사 케이스 수

  // 현 상태
  today_progress: number;        // 오늘 진척률 (%)
  productivity_score: number;    // (1) 현재 생산성 = today/μ × 100
  gap_pct: number;               // (2) productivity − 100
  z_score: number;               // (today − μ) / σ
  status: "normal" | "caution" | "risk";   // |Z| < 1 / 1~2 / ≥ 2

  // 시계열 — S-Curve 차트용
  s_curve: SCurvePoint[];        // 기존 fixture 재사용
  band_p25: number[];            // 볼린저 하단 P25
  band_p75: number[];            // 볼린저 상단 P75
  ewma_trend: number[];          // EWMA 추세선

  // 회복·시나리오
  recovery: {
    p25_days: number;
    p50_days: number;
    p75_days: number;
  };
  scenarios: {
    optimistic: ScenarioPoint;
    base:       ScenarioPoint;
    pessimistic:ScenarioPoint;
  };
}

export interface ScenarioPoint {
  eta_days: number;              // 평균 도달 / 만회 예상 일수
  recovery_pct: number;          // 회복 후 진척률
  delta_completion_days: number; // 계획 완공일 대비 ±N. **음수 = 단축**, 양수 = 지연.
  curve: number[];               // S-Curve 시각화용 시계열 (길이 = s_curve)
}
```

### 3-2. fixture 보강

- `data/mock_reports.json` 또는 동등 fixture 에 위 `ProductivityDiagnosis` 한 사이트당 1건씩 추가. **mock** 단계라 수치는 시연용 합리값.
- 기존 `Site.productivity_today` `delay_days` `recovery_days` 는 유지되나 진단 모델 내부에서는 위 새 필드를 사용.
- 신규 fixture 가 추가될 때까지 (B)/(C) 화면은 mock generator 한 곳에서 일괄 산출 가능 — 로직은 `web/lib/diagnosis.ts` (신규) 에 둔다.

### 3-3. 클라이언트 산출 유틸 — `web/lib/diagnosis.ts` (신규)

```ts
/** 단일 진입점 — 동일 입력 → 동일 출력 보장(데모 안정). */
export function diagnose(input: DiagnosisInput): ProductivityDiagnosis;

/** Z-score → status 매핑 */
export function statusFromZ(z: number): "normal" | "caution" | "risk";

/** 평균 회귀 가정 회복 일수 계산 */
export function meanReversionRecovery(
  shortfall: number,
  mu: number,
  todayRate: number,
): { p25: number; p50: number; p75: number };
```

A_Track 실 데이터 도착 시 이 모듈만 교체하면 화면 영향 최소.

---

## 4. 시각 컴포넌트 계약

본 spec 은 컴포넌트 **이름·props·재사용 위치** 까지만 정의. 실제 구현·스타일은 후속 plan.

| 컴포넌트 | 위치 (예정) | 핵심 props | 사용처 |
|---|---|---|---|
| `SpiBandChart` | `web/app/components/charts/SpiBandChart.tsx` | `diagnosis: ProductivityDiagnosis` | (B) Report main, (C) Site 상세 |
| `GapKpiCard` | `web/app/components/reports/GapKpiCard.tsx` | `gap_pct`, `z_score`, `status` | (B) Report KPI strip, (C) Dashboard 카드 |
| `RecoveryEtaCard` | `web/app/components/reports/RecoveryEtaCard.tsx` | `scenarios: { optimistic, base, pessimistic }` | (B) Report, (C) Site 상세 |
| `ConfidenceBadge` | `web/app/components/reports/ConfidenceBadge.tsx` | `sample_size: number` | 모든 진단 카드 공통 |
| `ScenarioLegend` | `web/app/components/charts/ScenarioLegend.tsx` | (none, static) | `SpiBandChart` 하단 |

### 4-1. `SpiBandChart` 시각 구성

레이어 (z-index 낮음 → 높음):
1. 격자 배경
2. 볼린저 음영 (P25–P75) — lavender-light/40
3. Base 시나리오 선 — lavender 굵기 2.5px
4. Optimistic 선 — mint 굵기 2px dashed
5. Pessimistic 선 — rose 굵기 2px dashed
6. EWMA 추세선 — ink-mid 굵기 1.5px dotted
7. 실적 점 (오늘) — ink fill, lavender ring
8. 우상단: `ConfidenceBadge` (N 표시)
9. 하단: `ScenarioLegend` (3색 + 라벨)

x축: 공정 단계 (S-Curve 와 동일 시점). y축: 누적 진척률 0–100%.

### 4-2. `GapKpiCard` 구성

기존 `KpiStrip` 카드 패턴(`rounded-card · border-border-soft · shadow-xs`) 위에:
- 라벨 `text-h6 text-ink`
- 큰 값: `gap_pct` (+/−%p)
- 컬러: `status` 매핑 (mint/sun/rose 텍스트)
- 우측 mini chip: Z-score 값 + 상태 라벨

### 4-3. `RecoveryEtaCard` 구성

세로 3 row (시나리오 별):
- 좌측 컬러 dot · 시나리오명
- 가운데 `eta_days` (font-display)
- 우측 `delta_completion_days` 부호

base 행만 굵게.

### 4-4. `ConfidenceBadge`

```
[●●●●●○] N=24 유사 케이스 기반
```
- N ≥ 50: full dots
- 20 ≤ N < 50: partial
- N < 20: sun 경고 톤

---

## 5. 후속 spec 인터페이스 (이 spec 의 산출물이 어떻게 쓰이는가)

### 5-1. (B) Report 화면 재구성

`/reports` 가 본 모델의 결과를 다음 순서로 보여준다:
1. KPI strip 4개 = 4 핵심 지표 (1·2·3·4 각각 → `GapKpiCard` 1개 + 표준 `KpiStrip` 3개)
2. `SpiBandChart` 메인 (전체 폭)
3. `RecoveryEtaCard` + 조치 권고 카드 2열
4. 기존 RawDataTab 은 유지

### 5-2. (C) Dashboard 보완

`/dashboard` 6 현장 카드:
- 카드 하단에 mini `GapKpiCard` 1개 + base 시나리오 ETA 칩
- 카드 우상단 `ConfidenceBadge` 작은 버전
- 정렬 옵션: `|Z|` 큰 순 / base ETA 짧은 순

### 5-3. (D) Tasks/Home 단계별 결과

각 Agent step 카드 클릭 시 펼침:
- Forecaster step: `SpiBandChart` 압축 버전 (높이 200px)
- Optimizer step: `RecoveryEtaCard` + 권고 1줄

---

## 6. 시연 시나리오 가정

- 데이터는 **mock**. `web/lib/diagnosis.ts` 의 generator 가 결정적(deterministic)으로 산출 — 시연 도중 수치 변하지 않도록 seed 고정.
- 6개 현장 중 2개를 risk(`|Z|≥2`), 1개 caution, 3개 normal 로 분포해 시연 화면에 다양성 확보.
- 시연 발화: "이 현장은 이력 평균 대비 –1.8σ — 주의 구간입니다. 평균 회귀 가정 시 12일 안에 회복 가능, Optimizer 권고 적용 시 7일로 단축됩니다."

---

## 7. 검증 방법

본 spec 의 모델·컴포넌트가 후속 plan 으로 구현된 뒤, 다음 항목으로 검증:

1. **타입 일관성** — `ProductivityDiagnosis` 타입을 모든 컴포넌트가 그대로 받는지. 중간 변환 없이.
2. **결정적 출력** — `diagnose(sameInput)` 두 번 호출 시 동일 결과.
3. **시각 정합** — `SpiBandChart` 의 3 시나리오 색이 spec §2 와 정확히 일치.
4. **색 의미 통일** — Z-score 상태 색이 시스템 status 색과 일치 (`design-system.md §2-1`).
5. **시연 안정성** — 페이지 새로고침해도 모든 수치·곡선이 동일.
6. **샘플 경고** — `N=10` 으로 mock 한 케이스에서 `ConfidenceBadge` 가 sun 경고 톤으로 표시.

---

## 8. 본 spec 의 scope 밖

- 실제 Agent (Forecaster · Optimizer) 의 Python 구현 — A_Track 영역
- Report·Dashboard·Tasks 화면의 picture-perfect 레이아웃 — 후속 spec
- AI 권고 카피 (Optimizer 출력 텍스트) — 별도
- 영문 i18n
- 모바일 반응형 세부

---

## 9. 후속 작업 순서

1. 본 spec 승인 → `writing-plans` 으로 plan 작성
2. plan 에 따라 `lib/types.ts` · `lib/diagnosis.ts` · 5 컴포넌트 구현 + fixture 보강
3. (B) Report 재구성 spec → plan → 구현
4. (C) Dashboard 보완 spec → plan → 구현
5. (D) Tasks/Home 재구성 spec → plan → 구현
