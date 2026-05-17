# CPIA 생산성 진단 — Hybrid 모델 1차 구현 Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** spec `2026-05-17-cpia-productivity-diagnosis-design.md` 의 모델·데이터 계약·5개 시각 컴포넌트를 결정적 mock 위에서 작동시키고, 임시 시연 페이지(`/diagnosis-preview`) 한 곳에서 5개 컴포넌트가 통합 동작함을 시각·테스트로 확인한다.

**Architecture:** 순수 함수 `diagnose(input)` 가 `DiagnosisInput → ProductivityDiagnosis` 를 **결정적 PRNG(mulberry32, site_id 시드)** 로 산출 — 화면 새로고침해도 같은 수치. 5개 컴포넌트(`SpiBandChart`·`GapKpiCard`·`RecoveryEtaCard`·`ConfidenceBadge`·`ScenarioLegend`) 는 이 산출물 하나를 props 로 받아 spec §2 색 매핑(`brand`/mint/sun/rose)을 그대로 따른다. (B)/(C)/(D) 화면 재구성은 본 plan scope 밖 — 통합 검증용 임시 라우트로 분리.

**Tech Stack:** TypeScript · Vitest · React · recharts 3.x (기존 `BarChartH.tsx` 와 동일) · Tailwind CSS · Next.js App Router

**Scope 밖 (별도 plan):**
- `/reports` `/dashboard` `/home` 화면 본격 재구성
- A_Track 실 데이터 연결 (mock generator 교체)
- `diagnose` 시드/공식 추가 튜닝 후 임원 시연 가이드 카피

---

## 파일 구조

| 종류 | 경로 | 책임 |
|---|---|---|
| 수정 | `web/lib/types.ts` | `DiagnosisInput` · `ProductivityDiagnosis` · `ScenarioPoint` · `DiagStatus` · `RecoveryEstimate` 추가 |
| 신규 | `web/lib/diagnosis.ts` | `statusFromZ` · `meanReversionRecovery` · `diagnose` + 결정적 PRNG helper |
| 신규 | `web/tests/diagnosis.test.ts` | 위 3개 함수 단위 테스트 (결정성·경계값 포함) |
| 신규 | `web/app/components/reports/ConfidenceBadge.tsx` | dot 진행도 + `N=N` 라벨 + 샘플 부족 경고 |
| 신규 | `web/app/components/charts/ScenarioLegend.tsx` | 시나리오 3색 + 라벨 (정적) |
| 신규 | `web/app/components/reports/GapKpiCard.tsx` | 격차 %p + Z-score chip |
| 신규 | `web/app/components/reports/RecoveryEtaCard.tsx` | 시나리오별 ETA 3행 |
| 신규 | `web/app/components/charts/SpiBandChart.tsx` | recharts `ComposedChart` — 음영 + 3선 + EWMA + 실적점 |
| 신규 | `web/app/(app)/diagnosis-preview/page.tsx` | 통합 시연 (임시) |

---

## Task 1: 신규 타입 정의

**Files:**
- Modify: `web/lib/types.ts` (파일 끝에 신규 섹션 추가)

- [ ] **Step 1: types.ts 끝에 새 섹션 추가**

`web/lib/types.ts` 파일 끝에 아래 블록을 추가한다.

```ts
// ────── Productivity Diagnosis (Hybrid 모델) ──────
export type DiagStatus = "normal" | "caution" | "risk";

export interface DiagnosisInput {
  site_id: string;            // 결정적 mock 산출 시드
  today_progress: number;     // 오늘 누적 진척률 (%)
  history_mean: number;       // μ — 이력 평균 일진척률 (%)
  history_std: number;        // σ
  sample_size: number;        // N — 유사 과거 케이스 수
  s_curve: SCurvePoint[];     // 기존 시계열 재사용
}

export interface RecoveryEstimate {
  p25: number;
  p50: number;
  p75: number;
}

export interface ScenarioPoint {
  eta_days: number;              // 평균 도달 / 만회 예상 일수 (∞ 허용)
  recovery_pct: number;          // 회복 후 누적 진척률 (%)
  delta_completion_days: number; // 계획 완공일 대비. 음수 = 단축, 양수 = 지연
  curve: number[];               // 시각화용 시계열 (길이 = s_curve.length)
}

export interface ProductivityDiagnosis {
  // 기준선
  history_mean: number;
  history_std: number;
  sample_size: number;

  // 현 상태
  today_progress: number;
  productivity_score: number;   // today / μ × 100
  gap_pct: number;              // productivity − 100
  z_score: number;              // (today − μ) / σ
  status: DiagStatus;

  // 시계열
  s_curve: SCurvePoint[];
  band_p25: number[];           // 볼린저 하단
  band_p75: number[];           // 볼린저 상단
  ewma_trend: number[];         // EWMA

  // 회복·시나리오
  recovery: { p25_days: number; p50_days: number; p75_days: number };
  scenarios: {
    optimistic: ScenarioPoint;
    base: ScenarioPoint;
    pessimistic: ScenarioPoint;
  };
}
```

- [ ] **Step 2: 타입 컴파일 확인**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/lib/types.ts
git commit -m "feat(B): 진단 모델 타입 추가 — DiagnosisInput·ProductivityDiagnosis·ScenarioPoint"
```

---

## Task 2: `statusFromZ` (Z-score → status) — TDD

**Files:**
- Create: `web/lib/diagnosis.ts`
- Create: `web/tests/diagnosis.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

`web/tests/diagnosis.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { statusFromZ } from "@/lib/diagnosis";

describe("statusFromZ", () => {
  it("|Z| < 1 → normal", () => {
    expect(statusFromZ(0)).toBe("normal");
    expect(statusFromZ(0.99)).toBe("normal");
    expect(statusFromZ(-0.99)).toBe("normal");
  });
  it("1 ≤ |Z| < 2 → caution", () => {
    expect(statusFromZ(1)).toBe("caution");
    expect(statusFromZ(-1.5)).toBe("caution");
    expect(statusFromZ(1.99)).toBe("caution");
  });
  it("|Z| ≥ 2 → risk", () => {
    expect(statusFromZ(2)).toBe("risk");
    expect(statusFromZ(-3)).toBe("risk");
  });
});
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `cd web && npx vitest run tests/diagnosis.test.ts`
Expected: FAIL — `Cannot resolve "@/lib/diagnosis"` 또는 `statusFromZ is not exported`

- [ ] **Step 3: 최소 구현**

`web/lib/diagnosis.ts`:

```ts
import type { DiagStatus } from "./types";

export function statusFromZ(z: number): DiagStatus {
  const abs = Math.abs(z);
  if (abs < 1) return "normal";
  if (abs < 2) return "caution";
  return "risk";
}
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `cd web && npx vitest run tests/diagnosis.test.ts`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/lib/diagnosis.ts web/tests/diagnosis.test.ts
git commit -m "feat(B): statusFromZ — Z-score → 정상/주의/이상 매핑 + 단위 테스트"
```

---

## Task 3: `meanReversionRecovery` — TDD

**Files:**
- Modify: `web/lib/diagnosis.ts`
- Modify: `web/tests/diagnosis.test.ts`

- [ ] **Step 1: 실패 테스트 추가**

`web/tests/diagnosis.test.ts` 끝에 추가:

```ts
import { meanReversionRecovery } from "@/lib/diagnosis";

describe("meanReversionRecovery", () => {
  it("정상 분모 — P50 = shortfall / (μ − today)", () => {
    const r = meanReversionRecovery(50, 1.0, 0.5);
    expect(r.p50).toBe(100);                // 50 / 0.5
    expect(r.p25).toBeLessThan(r.p50);      // 낙관 — 더 빠르게
    expect(r.p75).toBeGreaterThan(r.p50);   // 보수 — 더 늦게
  });
  it("분모 = 0 (today === μ) → Infinity", () => {
    const r = meanReversionRecovery(50, 1.0, 1.0);
    expect(r.p25).toBe(Infinity);
    expect(r.p50).toBe(Infinity);
    expect(r.p75).toBe(Infinity);
  });
  it("분모 < 0 (격차 확대 중) → Infinity", () => {
    expect(meanReversionRecovery(50, 1.0, 1.2).p50).toBe(Infinity);
  });
});
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `cd web && npx vitest run tests/diagnosis.test.ts`
Expected: 3 failed (meanReversionRecovery is not exported)

- [ ] **Step 3: 구현 추가**

`web/lib/diagnosis.ts` 에 추가:

```ts
import type { RecoveryEstimate } from "./types";

/**
 * Mean Reversion 가정 회복 일수 P25·P50·P75.
 * 분모(μ − todayRate) ≤ 0 이면 격차 확대 중 → Infinity.
 */
export function meanReversionRecovery(
  shortfall: number,
  mu: number,
  todayRate: number,
): RecoveryEstimate {
  const denom = mu - todayRate;
  if (denom <= 0) {
    return { p25: Infinity, p50: Infinity, p75: Infinity };
  }
  const p50 = shortfall / denom;
  return {
    p25: p50 * 0.7,   // 낙관 30% 단축
    p50,
    p75: p50 * 1.4,   // 보수 40% 연장
  };
}
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `cd web && npx vitest run tests/diagnosis.test.ts`
Expected: 6 passed (Task 2 의 3 + Task 3 의 3)

- [ ] **Step 5: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/lib/diagnosis.ts web/tests/diagnosis.test.ts
git commit -m "feat(B): meanReversionRecovery — 평균 회귀 회복 일수 P25/P50/P75 + ∞ 경계"
```

---

## Task 4: `diagnose` 메인 + 결정적 mock generator — TDD

**Files:**
- Modify: `web/lib/diagnosis.ts`
- Modify: `web/tests/diagnosis.test.ts`

- [ ] **Step 1: 실패 테스트 추가**

`web/tests/diagnosis.test.ts` 끝에 추가:

```ts
import { diagnose } from "@/lib/diagnosis";
import type { DiagnosisInput, SCurvePoint } from "@/lib/types";

function sampleInput(overrides: Partial<DiagnosisInput> = {}): DiagnosisInput {
  const s_curve: SCurvePoint[] = Array.from({ length: 20 }, (_, i) => ({
    date: `2026-05-${(i + 1).toString().padStart(2, "0")}`,
    planned: i * 5,
    actual: i < 14 ? i * 4.5 : undefined,
  }));
  return {
    site_id: "site-001",
    today_progress: 88,
    history_mean: 95,
    history_std: 4,
    sample_size: 24,
    s_curve,
    ...overrides,
  };
}

describe("diagnose", () => {
  it("결정적 — 동일 입력 두 번 호출시 동일 출력", () => {
    const a = diagnose(sampleInput());
    const b = diagnose(sampleInput());
    expect(a).toEqual(b);
  });

  it("productivity_score / gap_pct / z_score 산출", () => {
    const d = diagnose(sampleInput());
    expect(d.productivity_score).toBeCloseTo((88 / 95) * 100, 4);
    expect(d.gap_pct).toBeCloseTo(d.productivity_score - 100, 4);
    expect(d.z_score).toBeCloseTo((88 - 95) / 4, 4);
  });

  it("z_score 와 status 일관 (statusFromZ 와 동일)", () => {
    const d = diagnose(sampleInput());
    const abs = Math.abs(d.z_score);
    if (abs < 1) expect(d.status).toBe("normal");
    else if (abs < 2) expect(d.status).toBe("caution");
    else expect(d.status).toBe("risk");
  });

  it("시계열 길이 = s_curve 길이", () => {
    const d = diagnose(sampleInput());
    expect(d.band_p25).toHaveLength(d.s_curve.length);
    expect(d.band_p75).toHaveLength(d.s_curve.length);
    expect(d.ewma_trend).toHaveLength(d.s_curve.length);
    expect(d.scenarios.base.curve).toHaveLength(d.s_curve.length);
    expect(d.scenarios.optimistic.curve).toHaveLength(d.s_curve.length);
    expect(d.scenarios.pessimistic.curve).toHaveLength(d.s_curve.length);
  });

  it("scenarios.base.eta_days === recovery.p50_days", () => {
    const d = diagnose(sampleInput());
    expect(d.scenarios.base.eta_days).toBe(d.recovery.p50_days);
  });

  it("음수 격차 입력 — pessimistic.delta_completion_days > 0 (지연)", () => {
    const d = diagnose(sampleInput({ today_progress: 70 }));
    expect(d.scenarios.pessimistic.delta_completion_days).toBeGreaterThan(0);
  });

  it("today === μ — recovery 무한대 + status normal 또는 caution", () => {
    const d = diagnose(sampleInput({ today_progress: 95 }));
    expect(d.recovery.p50_days).toBe(Infinity);
    expect(d.scenarios.base.eta_days).toBe(Infinity);
  });
});
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `cd web && npx vitest run tests/diagnosis.test.ts`
Expected: 새 7 tests FAIL — `diagnose is not exported`

- [ ] **Step 3: 구현 추가**

`web/lib/diagnosis.ts` 에 아래 블록을 추가 (기존 statusFromZ / meanReversionRecovery 아래):

```ts
import type {
  DiagnosisInput,
  ProductivityDiagnosis,
  SCurvePoint,
  ScenarioPoint,
} from "./types";

/* ───── 결정적 PRNG ───── */
function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number): () => number {
  return () => {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ───── EWMA ───── */
function ewma(values: (number | undefined)[], lambda: number): number[] {
  const out: number[] = [];
  let prev = values.find((v) => v !== undefined) ?? 0;
  for (const v of values) {
    const cur = v ?? prev;
    prev = lambda * cur + (1 - lambda) * prev;
    out.push(prev);
  }
  return out;
}

/* ───── 시나리오 곡선 생성 ───── */
function buildScenarioCurve(
  s_curve: SCurvePoint[],
  todayIdx: number,
  lastActual: number,
  perStepRate: number,    // 한 단계당 진척률 추가분 (%)
  rand: () => number,
  noise: number,          // -1 ~ +1, 분포 폭
): number[] {
  const out: number[] = [];
  let cum = lastActual;
  for (let i = 0; i < s_curve.length; i++) {
    if (i <= todayIdx) {
      out.push(s_curve[i].actual ?? 0);
    } else {
      const jitter = (rand() - 0.5) * noise;
      cum = Math.min(100, Math.max(0, cum + perStepRate * (1 + jitter)));
      out.push(cum);
    }
  }
  return out;
}

/* ───── 진단 메인 ───── */
export function diagnose(input: DiagnosisInput): ProductivityDiagnosis {
  const { site_id, today_progress, history_mean, history_std, sample_size, s_curve } = input;
  const rand = mulberry32(hashString(site_id));

  const productivity_score = (today_progress / history_mean) * 100;
  const gap_pct = productivity_score - 100;
  const z_score = (today_progress - history_mean) / history_std;
  const status = statusFromZ(z_score);

  /* 볼린저 ±1.5σ 음영 (S-Curve planned 기준) */
  const band_p25 = s_curve.map((p) => Math.max(0, p.planned - history_std * 1.5));
  const band_p75 = s_curve.map((p) => Math.min(100, p.planned + history_std * 1.5));

  /* EWMA — actual 기반, λ = 0.3 */
  const ewma_trend = ewma(s_curve.map((p) => p.actual), 0.3);

  /* 현재 시점 = 마지막 actual 데이터 인덱스 */
  const firstUndef = s_curve.findIndex((p) => p.actual === undefined);
  const todayIdx = firstUndef === -1 ? s_curve.length - 1 : firstUndef - 1;
  const lastActual = todayIdx >= 0 ? (s_curve[todayIdx].actual ?? 0) : 0;
  const lastPlanned = todayIdx >= 0 ? s_curve[todayIdx].planned : 0;
  const shortfall = Math.max(0, lastPlanned - lastActual);

  /* 평균 회귀 회복 추정 (rate 는 %/단계 기준) */
  const muStep = history_mean / 100;          // 단계당 평균 진척률 (0~1)
  const todayStep = today_progress / 100;     // 단계당 현재 진척률 (0~1)
  const recovery = meanReversionRecovery(shortfall / 100, muStep, todayStep);
  const finite = Number.isFinite(recovery.p50);

  /* 시나리오 별 한 단계당 진척률 */
  const baseStep = history_mean / 4;          // 단계당 ~24% 진척 (튠 가능)
  const optimisticStep = baseStep * 1.18;
  const pessimisticStep = (today_progress / 4);

  const baseCurve = buildScenarioCurve(s_curve, todayIdx, lastActual, baseStep, rand, 0.05);
  const optCurve  = buildScenarioCurve(s_curve, todayIdx, lastActual, optimisticStep, rand, 0.08);
  const pessCurve = buildScenarioCurve(s_curve, todayIdx, lastActual, pessimisticStep, rand, 0.05);

  /* ScenarioPoint 산출 */
  const base: ScenarioPoint = {
    eta_days: finite ? Math.round(recovery.p50) : Infinity,
    recovery_pct: 100,
    delta_completion_days: finite ? Math.round(recovery.p50) : 999,
    curve: baseCurve,
  };
  const optimistic: ScenarioPoint = {
    eta_days: finite ? Math.round(recovery.p25) : Infinity,
    recovery_pct: 102,
    delta_completion_days: finite ? -Math.max(1, Math.round((recovery.p50 - recovery.p25) * 0.6)) : 0,
    curve: optCurve,
  };
  const pessimistic: ScenarioPoint = {
    eta_days: Infinity,
    recovery_pct: status === "risk" ? 85 : 92,
    delta_completion_days: status === "risk"
      ? Math.max(20, Math.round((finite ? recovery.p50 : 30) * 1.6))
      : Math.max(10, Math.round((finite ? recovery.p50 : 20) * 1.4)),
    curve: pessCurve,
  };

  return {
    history_mean,
    history_std,
    sample_size,
    today_progress,
    productivity_score,
    gap_pct,
    z_score,
    status,
    s_curve,
    band_p25,
    band_p75,
    ewma_trend,
    recovery: {
      p25_days: Number.isFinite(recovery.p25) ? Math.round(recovery.p25) : Infinity,
      p50_days: Number.isFinite(recovery.p50) ? Math.round(recovery.p50) : Infinity,
      p75_days: Number.isFinite(recovery.p75) ? Math.round(recovery.p75) : Infinity,
    },
    scenarios: { optimistic, base, pessimistic },
  };
}
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `cd web && npx vitest run tests/diagnosis.test.ts`
Expected: 13 passed (Task 2 의 3 + Task 3 의 3 + Task 4 의 7)

- [ ] **Step 5: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/lib/diagnosis.ts web/tests/diagnosis.test.ts
git commit -m "feat(B): diagnose 메인 + mulberry32 결정적 PRNG + EWMA + 시나리오 3종"
```

---

## Task 5: `ConfidenceBadge`

**Files:**
- Create: `web/app/components/reports/ConfidenceBadge.tsx`

- [ ] **Step 1: 컴포넌트 작성**

`web/app/components/reports/ConfidenceBadge.tsx`:

```tsx
import { cn } from "@/lib/utils";

interface Props {
  sampleSize: number;
}

const TONE_OK   = "bg-surface-soft text-ink-mid";
const TONE_LOW  = "bg-sun-light text-sun-text";

export function ConfidenceBadge({ sampleSize }: Props) {
  const low = sampleSize < 20;
  /* dot fill 비율 — N≥50 full, 30~ 5, 20~ 4, 10~ 3, 그 아래 2 */
  const filled =
    sampleSize >= 50 ? 6 :
    sampleSize >= 30 ? 5 :
    sampleSize >= 20 ? 4 :
    sampleSize >= 10 ? 3 : 2;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full px-2.5 py-1",
        low ? TONE_LOW : TONE_OK,
      )}
    >
      <span className="flex gap-0.5" aria-hidden>
        {Array.from({ length: 6 }).map((_, i) => (
          <span
            key={i}
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              i < filled
                ? low ? "bg-sun" : "bg-brand"
                : "bg-border",
            )}
          />
        ))}
      </span>
      <span className="font-mono text-[10px] font-medium uppercase tracking-wider">
        N={sampleSize} 유사 케이스
      </span>
    </span>
  );
}
```

- [ ] **Step 2: 빌드 검증**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/app/components/reports/ConfidenceBadge.tsx
git commit -m "feat(B): ConfidenceBadge — N 진행 dot + 샘플 부족(N<20) sun 경고 톤"
```

---

## Task 6: `ScenarioLegend`

**Files:**
- Create: `web/app/components/charts/ScenarioLegend.tsx`

- [ ] **Step 1: 컴포넌트 작성**

`web/app/components/charts/ScenarioLegend.tsx`:

```tsx
const ITEMS: { dot: string; label: string; note: string }[] = [
  { dot: "bg-mint",  label: "Optimistic",  note: "Optimizer 권고 적용" },
  { dot: "bg-brand", label: "Base",        note: "자연 평균 회귀" },
  { dot: "bg-rose",  label: "Pessimistic", note: "현 추세 유지" },
];

export function ScenarioLegend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-mid">
      {ITEMS.map((it) => (
        <li key={it.label} className="inline-flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${it.dot}`} aria-hidden />
          <span className="font-semibold text-ink">{it.label}</span>
          <span className="text-ink-light">— {it.note}</span>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 2: 빌드 검증**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/app/components/charts/ScenarioLegend.tsx
git commit -m "feat(B): ScenarioLegend — 시나리오 3종 정적 범례 (mint/brand/rose)"
```

---

## Task 7: `GapKpiCard`

**Files:**
- Create: `web/app/components/reports/GapKpiCard.tsx`

- [ ] **Step 1: 컴포넌트 작성**

`web/app/components/reports/GapKpiCard.tsx`:

```tsx
import { cn } from "@/lib/utils";
import type { DiagStatus } from "@/lib/types";

interface Props {
  gap_pct: number;
  z_score: number;
  status: DiagStatus;
}

const STATUS_TEXT: Record<DiagStatus, string> = {
  normal:  "text-mint-text",
  caution: "text-sun-text",
  risk:    "text-rose-text",
};
const STATUS_CHIP: Record<DiagStatus, string> = {
  normal:  "bg-mint-light text-mint-text",
  caution: "bg-sun-light text-sun-text",
  risk:    "bg-rose-light text-rose-text",
};
const STATUS_LABEL: Record<DiagStatus, string> = {
  normal:  "정상",
  caution: "주의",
  risk:    "이상",
};

export function GapKpiCard({ gap_pct, z_score, status }: Props) {
  const sign = gap_pct >= 0 ? "+" : "";
  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs transition-shadow hover:shadow-sm">
      <div className="font-display text-h6 text-ink">평균 대비 격차</div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className={cn("font-display text-3xl font-semibold tracking-[-0.015em]", STATUS_TEXT[status])}>
          {sign}{gap_pct.toFixed(1)}
        </span>
        <span className="text-sm text-ink-light">%p</span>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <span className={cn(
          "inline-flex items-center rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider",
          STATUS_CHIP[status],
        )}>
          {STATUS_LABEL[status]}
        </span>
        <span className="font-mono text-[11px] text-ink-light">Z = {z_score.toFixed(2)}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 빌드 검증**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/app/components/reports/GapKpiCard.tsx
git commit -m "feat(B): GapKpiCard — 격차 %p + status 컬러 + Z-score chip"
```

---

## Task 8: `RecoveryEtaCard`

**Files:**
- Create: `web/app/components/reports/RecoveryEtaCard.tsx`

- [ ] **Step 1: 컴포넌트 작성**

`web/app/components/reports/RecoveryEtaCard.tsx`:

```tsx
import { cn } from "@/lib/utils";
import type { ScenarioPoint } from "@/lib/types";

interface Props {
  scenarios: {
    optimistic: ScenarioPoint;
    base: ScenarioPoint;
    pessimistic: ScenarioPoint;
  };
}

const ROWS: { key: keyof Props["scenarios"]; label: string; dot: string }[] = [
  { key: "optimistic",  label: "Optimistic",  dot: "bg-mint" },
  { key: "base",        label: "Base",        dot: "bg-brand" },
  { key: "pessimistic", label: "Pessimistic", dot: "bg-rose" },
];

function formatEta(days: number): string {
  if (!Number.isFinite(days)) return "회복 불가";
  return `D-${days}`;
}

function formatDelta(days: number): string {
  if (days === 0) return "변동 없음";
  if (days > 0) return `+${days}일 지연`;
  return `${days}일 단축`;
}

export function RecoveryEtaCard({ scenarios }: Props) {
  return (
    <div className="rounded-card border border-border-soft bg-card p-5 shadow-xs">
      <div className="font-display text-h6 text-ink">회복 ETA · 시나리오 3종</div>
      <ul className="mt-3 flex flex-col">
        {ROWS.map((row) => {
          const s = scenarios[row.key];
          const isBase = row.key === "base";
          return (
            <li
              key={row.key}
              className={cn(
                "flex items-center gap-3 border-b border-border-soft py-2 last:border-b-0",
                isBase && "font-semibold",
              )}
            >
              <span className={`h-2 w-2 shrink-0 rounded-full ${row.dot}`} aria-hidden />
              <span className="w-24 text-body-sm text-ink">{row.label}</span>
              <span className="flex-1 font-display text-h6 text-ink">{formatEta(s.eta_days)}</span>
              <span className="font-mono text-[11px] text-ink-mid">{formatDelta(s.delta_completion_days)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: 빌드 검증**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/app/components/reports/RecoveryEtaCard.tsx
git commit -m "feat(B): RecoveryEtaCard — 시나리오 3 row (Optimistic/Base/Pessimistic) ETA + 완공 delta"
```

---

## Task 9: `SpiBandChart`

**Files:**
- Create: `web/app/components/charts/SpiBandChart.tsx`

- [ ] **Step 1: 컴포넌트 작성**

`web/app/components/charts/SpiBandChart.tsx`:

```tsx
"use client";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceDot,
  CartesianGrid,
} from "recharts";
import type { ProductivityDiagnosis } from "@/lib/types";
import { ConfidenceBadge } from "../reports/ConfidenceBadge";
import { ScenarioLegend } from "./ScenarioLegend";

interface Props {
  diagnosis: ProductivityDiagnosis;
}

export function SpiBandChart({ diagnosis }: Props) {
  const data = diagnosis.s_curve.map((p, i) => ({
    date: p.date,
    planned: p.planned,
    actual: p.actual,
    band_low:  diagnosis.band_p25[i],
    band_high: diagnosis.band_p75[i],
    ewma:      diagnosis.ewma_trend[i],
    base:      diagnosis.scenarios.base.curve[i],
    optimistic:  diagnosis.scenarios.optimistic.curve[i],
    pessimistic: diagnosis.scenarios.pessimistic.curve[i],
  }));

  /* 실적 마지막 점 — 강조 dot */
  const firstUndef = data.findIndex((d) => d.actual === undefined);
  const lastIdx = firstUndef === -1 ? data.length - 1 : firstUndef - 1;
  const lastPoint = lastIdx >= 0 ? data[lastIdx] : null;

  return (
    <div className="rounded-card border border-border-soft bg-card p-5 shadow-xs">
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <div className="font-display text-h6 text-ink">SPI Band Chart</div>
          <div className="text-body-sm text-ink-mid">
            볼린저 ±1.5σ 음영 + 시나리오 3종 + EWMA 추세
          </div>
        </div>
        <ConfidenceBadge sampleSize={diagnosis.sample_size} />
      </div>

      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={data} margin={{ top: 12, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#eef0f4" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#7a8494" }}
            tickFormatter={(v: string) => v.slice(5)}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 10, fill: "#7a8494" }}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
            labelFormatter={(v: string) => v}
          />

          {/* 볼린저 음영 (P25-P75) — high - low 두 Area stacking */}
          <Area dataKey="band_high" stroke="none" fill="#e8eeff" fillOpacity={0.4} activeDot={false} isAnimationActive={false} />
          <Area dataKey="band_low"  stroke="none" fill="#ffffff" fillOpacity={1}   activeDot={false} isAnimationActive={false} />

          {/* 시나리오 3선 */}
          <Line dataKey="optimistic"  stroke="#0ea76a" strokeWidth={2}   strokeDasharray="4 3" dot={false} isAnimationActive={false} />
          <Line dataKey="base"        stroke="#1a56db" strokeWidth={2.5} dot={false} isAnimationActive={false} />
          <Line dataKey="pessimistic" stroke="#ef4444" strokeWidth={2}   strokeDasharray="4 3" dot={false} isAnimationActive={false} />

          {/* EWMA 추세선 (보조) */}
          <Line dataKey="ewma" stroke="#444e5e" strokeWidth={1.5} strokeDasharray="2 2" dot={false} isAnimationActive={false} />

          {/* 오늘 실적 점 */}
          {lastPoint && lastPoint.actual !== undefined && (
            <ReferenceDot
              x={lastPoint.date}
              y={lastPoint.actual}
              r={5}
              fill="#0d1117"
              stroke="#1a56db"
              strokeWidth={2}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>

      <div className="mt-3">
        <ScenarioLegend />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 빌드 검증**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/app/components/charts/SpiBandChart.tsx
git commit -m "feat(B): SpiBandChart — 볼린저 음영 + 시나리오 3선 + EWMA + 실적 강조 dot"
```

---

## Task 10: 통합 시연 페이지 `/diagnosis-preview`

**Files:**
- Create: `web/app/(app)/diagnosis-preview/page.tsx`

- [ ] **Step 1: 페이지 작성**

`web/app/(app)/diagnosis-preview/page.tsx`:

```tsx
import { diagnose } from "@/lib/diagnosis";
import type { DiagnosisInput, SCurvePoint } from "@/lib/types";
import { SpiBandChart } from "@/app/components/charts/SpiBandChart";
import { GapKpiCard } from "@/app/components/reports/GapKpiCard";
import { RecoveryEtaCard } from "@/app/components/reports/RecoveryEtaCard";
import { ConfidenceBadge } from "@/app/components/reports/ConfidenceBadge";

/* 시연용 mock 입력 — 시각 검증의 다양성 확보 (정상 1 · 주의 1 · 이상 1) */
function makeSCurve(actualSlope: number): SCurvePoint[] {
  return Array.from({ length: 20 }, (_, i) => ({
    date: `2026-05-${(i + 1).toString().padStart(2, "0")}`,
    planned: i * 5,
    actual: i < 14 ? Math.round(i * actualSlope * 10) / 10 : undefined,
  }));
}

const SAMPLES: { title: string; input: DiagnosisInput }[] = [
  {
    title: "M15X Ph-3 IBL · 정상 구간",
    input: {
      site_id: "M15X-Ph3-IBL",
      today_progress: 94,
      history_mean: 95,
      history_std: 4,
      sample_size: 32,
      s_curve: makeSCurve(4.7),
    },
  },
  {
    title: "Hi-tech-A 건물 · 주의 구간",
    input: {
      site_id: "Hi-tech-A",
      today_progress: 88,
      history_mean: 95,
      history_std: 4,
      sample_size: 24,
      s_curve: makeSCurve(4.4),
    },
  },
  {
    title: "Indiana HAC · 이상 + 샘플 부족",
    input: {
      site_id: "Indiana-HAC",
      today_progress: 70,
      history_mean: 95,
      history_std: 4,
      sample_size: 8,
      s_curve: makeSCurve(3.5),
    },
  },
];

export default function DiagnosisPreviewPage() {
  const results = SAMPLES.map((s) => ({ ...s, diagnosis: diagnose(s.input) }));
  return (
    <div className="mx-auto max-w-screen-2xl px-6 py-10 md:px-10 md:py-14">
      <header className="border-b border-border-soft pb-6">
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          / preview — Diagnosis Components
        </span>
        <h1 className="mt-3 font-display text-h3 text-ink">진단 모델 컴포넌트 통합 시연</h1>
        <p className="mt-2 text-body-sm text-ink-mid">
          Hybrid 진단 모델 5 컴포넌트 시각 검증. (B) Report 재구성 plan 완료 시 본 라우트는 제거됩니다.
        </p>
      </header>

      {results.map((r, i) => (
        <section key={i} className="mt-10 flex flex-col gap-4">
          <div className="flex items-baseline justify-between">
            <h2 className="font-display text-h5 text-ink">{r.title}</h2>
            <ConfidenceBadge sampleSize={r.diagnosis.sample_size} />
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <GapKpiCard
              gap_pct={r.diagnosis.gap_pct}
              z_score={r.diagnosis.z_score}
              status={r.diagnosis.status}
            />
            <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
              <div className="font-display text-h6 text-ink">현재 생산성</div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="font-display text-3xl font-semibold tracking-[-0.015em] text-ink">
                  {r.diagnosis.productivity_score.toFixed(1)}
                </span>
                <span className="text-sm text-ink-light">%</span>
              </div>
              <div className="mt-3 text-[11px] text-ink-mid">
                today {r.diagnosis.today_progress}% / μ {r.diagnosis.history_mean}%
              </div>
            </div>
            <RecoveryEtaCard scenarios={r.diagnosis.scenarios} />
          </div>

          <SpiBandChart diagnosis={r.diagnosis} />
        </section>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: 빌드 검증**

Run: `cd web && npx next build`
Expected: build succeeded, `/diagnosis-preview` route 추가됨

- [ ] **Step 3: dev 서버 시각 검증**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project/web"
npm run dev  # 백그라운드 또는 별도 터미널
```

브라우저로 `http://127.0.0.1:5535/diagnosis-preview` 접속해 다음 확인:
- Sample 1 (정상): GapKpi mint 톤, status chip "정상"
- Sample 2 (주의): GapKpi sun 톤, status chip "주의"
- Sample 3 (이상): GapKpi rose 톤, status chip "이상", N=8 sun 경고 톤
- 모든 SpiBandChart 에 brand 음영 + 3 시나리오 선 + EWMA 점선 + 실적 강조 dot
- Recovery ETA 카드 — base 행 굵게, pessimistic 의 `+N일 지연`

- [ ] **Step 4: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add 'web/app/(app)/diagnosis-preview/page.tsx'
git commit -m "feat(B): /diagnosis-preview — 5 컴포넌트 통합 시연 (정상/주의/이상 3 sample)"
```

---

## Task 11: 최종 통합 검증

**Files:** (없음 — 검증만)

- [ ] **Step 1: 전체 단위 테스트**

Run: `cd web && npx vitest run`
Expected: 13+ tests pass (Task 2/3/4 의 13 + 기존 fixtures/persona/sanity/use-simulation)

- [ ] **Step 2: Production build**

Run: `cd web && npx next build`
Expected: 15 routes (기존 14 + `/diagnosis-preview`) 통과

- [ ] **Step 3: type-check**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 4: 시각 회귀 점검**

`http://127.0.0.1:5535/` 부터 모든 기존 페이지(`/home` `/tasks` `/review` `/reports` `/dashboard`) 가 정상 노출되는지 빠르게 클릭 점검 — 본 plan 의 변경은 신규 파일 위주라 회귀 위험 적지만 확인.

- [ ] **Step 5: 최종 commit (필요 시)**

위에서 모든 task 별 commit 이 끝났다면 추가 작업 없음. 변경된 누적 파일 목록:

```
A web/lib/diagnosis.ts
A web/tests/diagnosis.test.ts
A web/app/components/reports/ConfidenceBadge.tsx
A web/app/components/reports/GapKpiCard.tsx
A web/app/components/reports/RecoveryEtaCard.tsx
A web/app/components/charts/ScenarioLegend.tsx
A web/app/components/charts/SpiBandChart.tsx
A web/app/(app)/diagnosis-preview/page.tsx
M web/lib/types.ts
```

---

## 후속 plan 후보 (이 plan 의 scope 밖)

1. **(B) `/reports` 재구성** — 본 컴포넌트들을 메인 콘텐츠로 끼우고 `/diagnosis-preview` 제거
2. **(C) `/dashboard` 6 현장 카드 보강** — `GapKpiCard` mini + `ConfidenceBadge` 작은 버전
3. **(D) `/home` Agent step 펼침 / `/tasks` 진단 결과 표시** — Forecaster step → `SpiBandChart` 압축 버전
4. **fixture → 실 데이터 마이그레이션** — `data/mock_reports.json` 에 `diagnosis_input` 필드 추가, `loadFixture("report")` 결과를 `diagnose()` 에 통과시키는 어댑터 작성
