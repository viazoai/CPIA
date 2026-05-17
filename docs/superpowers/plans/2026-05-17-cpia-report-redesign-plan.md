# `/reports` Tabs 폐지 + 단일 흐름 재구성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** spec `2026-05-17-cpia-report-redesign-design.md` 의 6 섹션 단일 흐름을 `/reports` 에 구현하고, ForecastTab/OptimizeTab/`/diagnosis-preview` 를 정리해 진단 컴포넌트를 실제 시연 경로의 메인 콘텐츠로 끌어올린다.

**Architecture:** `/reports` page.tsx 가 `loadFixture("report")` 의 `ReportDetail` 을 받아 `lib/diagnosis-adapter.ts` 를 통해 `DiagnosisInput` 으로 변환 → `diagnose()` 호출 → 5 진단 컴포넌트(`GapKpiCard`/`SpiBandChart`/`ConfidenceBadge`/`RecoveryEtaCard`/`ScenarioLegend`) 와 기존 컴포넌트들(`KpiStrip`/`BarChartH`/`QuadrantScatter`/`QuadrantCountKpi`/`OptimizerResult`/`RawDataTab`/`ReportDailyList`) 을 한 페이지에서 세로 6 섹션으로 조립. ForecastTab/OptimizeTab 는 삭제(인라인 흡수), `/diagnosis-preview` 임시 라우트도 제거.

**Tech Stack:** Next.js App Router · React · Vitest · 기존 디자인 토큰 (`text-h6` · `rounded-card border-border-soft shadow-xs`)

**Scope 밖 (별도 plan):**
- `detail.optimizer` 를 WP 별로 분리한 fixture 보강 — 본 plan 에서는 단일 OptimizerOutput 유지하고 OptimizerResult 헤더에 "선택된 WP" 라벨만 추가
- (C) `/dashboard` 6 현장 카드 보강
- (D) `/home` `/tasks` 단계별 결과
- A_Track 실 데이터 연결 (`toDiagnosisInput` 교체)
- `/dashboard/sites/[id]` 도 진단 모델 통합 — `SCurveChart`/`BarChartH` 만 사용 중이라 본 plan 영향 없음

---

## 파일 구조

| 종류 | 경로 | 책임 |
|---|---|---|
| 신규 | `web/lib/diagnosis-adapter.ts` | `toDiagnosisInput(reportKpi, s_curve, siteId): DiagnosisInput` — ReportDetail → DiagnosisInput 변환 |
| 신규 | `web/tests/diagnosis-adapter.test.ts` | 결정성·범위·매핑 단위 테스트 |
| 수정 (재작성) | `web/app/(app)/reports/page.tsx` | Tabs 제거, 6 섹션 단일 흐름, page-level selectedWp/filter state, adapter+diagnose 호출 |
| 삭제 | `web/app/components/reports/ForecastTab.tsx` | § 2·§ 4 가 직접 흡수 |
| 삭제 | `web/app/components/reports/OptimizeTab.tsx` | § 5 가 직접 흡수, OptimizerResult 는 § 3 에 분리 사용 |
| 삭제 | `web/app/(app)/diagnosis-preview/` (폴더 전체) | 임시 시연 종료 — `/reports` 가 메인 사용처가 됨 |

---

## Task 1: `lib/diagnosis-adapter.ts` + TDD

**Files:**
- Create: `web/lib/diagnosis-adapter.ts`
- Create: `web/tests/diagnosis-adapter.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

`web/tests/diagnosis-adapter.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { toDiagnosisInput } from "@/lib/diagnosis-adapter";
import type { ReportKpi, SCurvePoint } from "@/lib/types";

function sampleKpi(overrides: Partial<ReportKpi> = {}): ReportKpi {
  return {
    productivity_today: 88,
    productivity_history_diff: -7,
    delay_days: 14,
    expected_completion: "2026-08-12",
    recoverable_productivity: 9,
    target_productivity: 97,
    recovery_days: 9,
    recovered_completion: "2026-08-03",
    ...overrides,
  };
}

function sampleSCurve(): SCurvePoint[] {
  return Array.from({ length: 20 }, (_, i) => ({
    date: `2026-05-${(i + 1).toString().padStart(2, "0")}`,
    planned: i * 5,
    actual: i < 14 ? i * 4.5 : undefined,
  }));
}

describe("toDiagnosisInput", () => {
  it("결정적 — 동일 입력 두 번 호출시 동일 출력", () => {
    const a = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-001");
    const b = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-001");
    expect(a).toEqual(b);
  });

  it("history_mean = target_productivity (보통 97)", () => {
    const input = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-001");
    expect(input.history_mean).toBe(97);
  });

  it("today_progress = productivity_today", () => {
    const input = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-001");
    expect(input.today_progress).toBe(88);
  });

  it("history_std 가 고정값 4", () => {
    const input = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-001");
    expect(input.history_std).toBe(4);
  });

  it("sample_size 가 12~48 범위 (결정적)", () => {
    const input = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-001");
    expect(input.sample_size).toBeGreaterThanOrEqual(12);
    expect(input.sample_size).toBeLessThanOrEqual(48);
  });

  it("다른 site_id 면 다른 sample_size 가능 (시드 차이)", () => {
    const a = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-001");
    const b = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-OTHER");
    /* 결정성 보장 — 두 입력은 site_id 외 동일하므로 sample_size 만 달라질 수 있음 */
    expect(a.history_mean).toBe(b.history_mean);
    expect(a.today_progress).toBe(b.today_progress);
  });

  it("s_curve 가 그대로 전달", () => {
    const s = sampleSCurve();
    const input = toDiagnosisInput(sampleKpi(), s, "site-001");
    expect(input.s_curve).toBe(s);
  });

  it("site_id 가 그대로 전달", () => {
    const input = toDiagnosisInput(sampleKpi(), sampleSCurve(), "M15X-Ph3");
    expect(input.site_id).toBe("M15X-Ph3");
  });
});
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `cd web && npx vitest run tests/diagnosis-adapter.test.ts`
Expected: FAIL — "Cannot resolve @/lib/diagnosis-adapter"

- [ ] **Step 3: 최소 구현**

`web/lib/diagnosis-adapter.ts`:

```ts
import type { DiagnosisInput, ReportKpi, SCurvePoint } from "./types";

/**
 * ReportDetail (mock fixture) 의 ReportKpi + s_curve 를 진단 모델 입력으로 변환.
 * A_Track 실 데이터 도착 시 본 함수만 교체하면 화면 영향 없음.
 *
 * mock 합리값:
 *   history_mean = ReportKpi.target_productivity (보통 97)
 *   history_std  = 4 (고정)
 *   sample_size  = site_id 해시 기반 12~48 균등 (결정적)
 *   today_progress = ReportKpi.productivity_today
 */
export function toDiagnosisInput(
  reportKpi: ReportKpi,
  s_curve: SCurvePoint[],
  siteId: string,
): DiagnosisInput {
  return {
    site_id: siteId,
    today_progress: reportKpi.productivity_today,
    history_mean: reportKpi.target_productivity,
    history_std: 4,
    sample_size: deterministicSampleSize(siteId),
    s_curve,
  };
}

/** site_id 해시 → 12 ~ 48 범위 균등. 같은 siteId 면 항상 같은 값. */
function deterministicSampleSize(siteId: string): number {
  let h = 2166136261;
  for (let i = 0; i < siteId.length; i++) {
    h ^= siteId.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const unsigned = h >>> 0;
  return 12 + (unsigned % 37); /* 0..36 → 12..48 */
}
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `cd web && npx vitest run tests/diagnosis-adapter.test.ts`
Expected: 8 passed

- [ ] **Step 5: 전체 vitest 회귀 확인**

Run: `cd web && npx vitest run`
Expected: 34 passed (기존 26 + 신규 8) — 기존 회귀 없음

- [ ] **Step 6: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/lib/diagnosis-adapter.ts web/tests/diagnosis-adapter.test.ts
git commit -m "feat(B): diagnosis-adapter — ReportDetail → DiagnosisInput 변환 + 결정성 테스트"
```

---

## Task 2: `/reports` page.tsx 재작성 (6 섹션 단일 흐름)

**Files:**
- Modify: `web/app/(app)/reports/page.tsx` (전체 재작성)

- [ ] **Step 1: 새 page.tsx 코드 작성**

`web/app/(app)/reports/page.tsx`:

```tsx
"use client";
import { useEffect, useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { ReportDailyList } from "@/app/components/reports/ReportDailyList";
import { KpiStrip, type KpiItem } from "@/app/components/reports/KpiStrip";
import { GapKpiCard } from "@/app/components/reports/GapKpiCard";
import { RecoveryEtaCard } from "@/app/components/reports/RecoveryEtaCard";
import { OptimizerResult } from "@/app/components/reports/OptimizerResult";
import { QuadrantCountKpi } from "@/app/components/reports/QuadrantCountKpi";
import { RawDataTab } from "@/app/components/reports/RawDataTab";
import { SpiBandChart } from "@/app/components/charts/SpiBandChart";
import { BarChartH } from "@/app/components/charts/BarChartH";
import { QuadrantScatter } from "@/app/components/charts/QuadrantScatter";
import { diagnose } from "@/lib/diagnosis";
import { toDiagnosisInput } from "@/lib/diagnosis-adapter";
import type { ReportDaily } from "@/lib/types";
import type { ReportDetail } from "@/lib/fixtures";

type Filter = "all" | "risk" | "caution" | "safe";

/* 시연용 site_id — fixture 에 site 식별자가 없어 고정값 사용. (B/C/D) 이후
 * /dashboard/sites/[id]/reports 형태로 분리할 때 URL 파라미터에서 가져온다. */
const REPORT_SITE_ID = "M15X-Ph3-IBL";

export default function ReportPage() {
  const [daily, setDaily] = useState<ReportDaily[]>([]);
  const [details, setDetails] = useState<Record<string, ReportDetail>>({});
  const [selectedDate, setSelectedDate] = useState<string>("2026-05-15");
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedWpId, setSelectedWpId] = useState<string | null>(null);
  const [rawOpen, setRawOpen] = useState(false);

  useEffect(() => {
    fetch("/api/mock/report")
      .then((r) => r.json())
      .then((d) => { setDaily(d.daily); setDetails(d.details); });
  }, []);

  /* 날짜 변경 시 selectedWp 초기화 — 첫 risk 점으로 자동 선택. */
  useEffect(() => {
    const detail = details[selectedDate];
    if (!detail) return;
    const riskPoint = detail.quadrant.find((p) => p.quadrant === "risk");
    setSelectedWpId(riskPoint?.wp_id ?? detail.quadrant[0]?.wp_id ?? null);
  }, [selectedDate, details]);

  const detail = details[selectedDate];
  const diagnosis = useMemo(() => {
    if (!detail) return null;
    return diagnose(toDiagnosisInput(detail.kpi, detail.s_curve, REPORT_SITE_ID));
  }, [detail]);

  if (!detail || !diagnosis) {
    return <div className="px-6 py-10 text-ink-light">Loading...</div>;
  }

  const kpiRest: KpiItem[] = [
    { label: "현재 생산성", value: `${detail.kpi.productivity_today}`, unit: "%", sub: `이력 ${detail.kpi.productivity_history_diff > 0 ? "+" : ""}${detail.kpi.productivity_history_diff}%`, tone: detail.kpi.productivity_today < 90 ? "risk" : "normal" },
    { label: "현 추세 공기", value: `D+${detail.kpi.delay_days}`, unit: "일 지연", sub: detail.kpi.expected_completion, tone: "risk" },
    { label: "최적화 후 공기", value: `-${detail.kpi.recovery_days}`, unit: "일 회복", sub: detail.kpi.recovered_completion, tone: "normal" },
  ];

  const selectedWp = detail.quadrant.find((p) => p.wp_id === selectedWpId) ?? null;

  return (
    <div className="flex flex-col">
      {/* Header */}
      <div className="mx-auto w-full max-w-screen-2xl border-b border-border-soft px-6 pt-10 pb-6 md:px-10 md:pt-14">
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          / 04 — Daily Report
        </span>
        <h1 className="mt-3 font-display text-h3 text-ink">
          현장 일일 진단 보고서
        </h1>
        <p className="mt-2 text-body-sm text-ink-mid">
          진단 · 시나리오 · 최적화 대상 · 원본 데이터를 한 흐름에서 확인합니다.
        </p>
      </div>

      <section className="mx-auto w-full max-w-screen-2xl px-6 pb-20 md:px-10">
        <div className="mt-6 grid grid-cols-12 gap-4">
          {/* Left — Daily list (sticky) */}
          <div className="col-span-12 md:col-span-3">
            <div className="flex flex-col overflow-hidden rounded-card border border-border-soft bg-card shadow-xs lg:sticky lg:top-6 lg:h-[calc(100vh-220px)]">
              <ReportDailyList daily={daily} selectedDate={selectedDate} onSelect={setSelectedDate} />
            </div>
          </div>

          {/* Right — 6 sections */}
          <div className="col-span-12 flex flex-col gap-10 md:col-span-9">
            {/* § 1 — 현재 상태 KPI 4 */}
            <Section eyebrow="/ 01 — 현재 상태" title="KPI 스냅샷">
              <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                <SingleKpi item={kpiRest[0]} />
                <GapKpiCard
                  gap_pct={diagnosis.gap_pct}
                  z_score={diagnosis.z_score}
                  status={diagnosis.status}
                />
                <SingleKpi item={kpiRest[1]} />
                <SingleKpi item={kpiRest[2]} />
              </div>
            </Section>

            {/* § 2 — 진단 (SpiBandChart) */}
            <Section eyebrow="/ 02 — 진단" title="이력 평균 대비 추세">
              <SpiBandChart diagnosis={diagnosis} />
            </Section>

            {/* § 3 — 회복 시나리오 · 권고 */}
            <Section eyebrow="/ 03 — 회복 시나리오 · 권고" title="시나리오 ETA + Optimizer">
              <div className="grid gap-4 md:grid-cols-2">
                <RecoveryEtaCard scenarios={diagnosis.scenarios} />
                <div>
                  <div className="mb-2 text-body-sm text-ink-mid">
                    {selectedWp ? (
                      <>선택된 WP: <span className="font-semibold text-ink">{selectedWp.wp_name}</span> <span className="text-ink-light">({selectedWp.trade})</span></>
                    ) : (
                      <>WP 미선택 — 아래 산점도에서 점을 클릭하세요</>
                    )}
                  </div>
                  <OptimizerResult output={detail.optimizer} />
                </div>
              </div>
            </Section>

            {/* § 4 — 공정 분해 (BarChartH × 2) */}
            <Section eyebrow="/ 04 — 공정 분해" title="업체 · 공종 생산성">
              <div className="grid gap-4 md:grid-cols-2">
                <BarChartH items={detail.contractor_bars} title="업체별 생산성 (오늘 평균)" />
                <BarChartH items={detail.trade_bars} title="공종별 생산성 (오늘 평균)" />
              </div>
            </Section>

            {/* § 5 — 최적화 대상 (Quadrant) */}
            <Section eyebrow="/ 05 — 최적화 대상" title="Impact × Productivity 산점도">
              <div className="grid grid-cols-12 gap-4">
                <div className="col-span-12 md:col-span-6">
                  <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
                    <QuadrantScatter
                      points={detail.quadrant}
                      selectedWpId={selectedWpId}
                      onSelect={setSelectedWpId}
                      filter={filter}
                    />
                    <div className="mt-3 text-center text-xs text-ink-light">
                      점 크기 = 잔여 물량. 좌상 = 고 Impact · 저 Productivity (위험군).
                    </div>
                  </div>
                </div>
                <div className="col-span-12 md:col-span-6">
                  <QuadrantCountKpi points={detail.quadrant} filter={filter} onFilterChange={setFilter} />
                </div>
              </div>
            </Section>

            {/* § 6 — 원본 데이터 (collapsible) */}
            <Section eyebrow="/ 06 — 원본 데이터" title="작업일보 매핑 결과">
              <button
                type="button"
                onClick={() => setRawOpen((v) => !v)}
                className="flex w-full items-center justify-between rounded-card border border-border-soft bg-card px-5 py-4 shadow-xs transition-shadow hover:shadow-sm"
                aria-expanded={rawOpen}
              >
                <span className="text-body-sm text-ink">
                  {rawOpen ? "원본 데이터 접기" : `원본 데이터 펼치기 · ${detail.raw_data.length} rows`}
                </span>
                <ChevronDown
                  className={`h-4 w-4 text-ink-mid transition-transform ${rawOpen ? "rotate-180" : ""}`}
                />
              </button>
              {rawOpen && (
                <div className="mt-3">
                  <RawDataTab rows={detail.raw_data} />
                </div>
              )}
            </Section>
          </div>
        </div>
      </section>
    </div>
  );
}

/* ── 헬퍼 컴포넌트 ── */

function Section({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          {eyebrow}
        </span>
        <h2 className="mt-1 font-display text-h5 text-ink">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function SingleKpi({ item }: { item: KpiItem }) {
  return <KpiStrip items={[item]} />;
}
```

- [ ] **Step 2: type-check**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: build 검증**

Run: `cd web && npx next build`
Expected: 14 routes (`/reports` size 변화 정상 — Tabs 제거 + 새 컴포넌트들 추가). `/diagnosis-preview` 는 아직 살아있음 — Task 4 에서 제거.

- [ ] **Step 4: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add 'web/app/(app)/reports/page.tsx'
git commit -m "feat(B): /reports Tabs 폐지 + 6 섹션 단일 흐름 — 진단·시나리오·최적화·원본"
```

---

## Task 3: 미사용 ForecastTab / OptimizeTab 삭제

**Files:**
- Delete: `web/app/components/reports/ForecastTab.tsx`
- Delete: `web/app/components/reports/OptimizeTab.tsx`

- [ ] **Step 1: 미사용 확인**

Run: `cd web && grep -rn "ForecastTab\|OptimizeTab" app/ lib/ tests/ | grep -v -E "ForecastTab\.tsx|OptimizeTab\.tsx"`
Expected: 출력 없음 (Task 2 의 새 page.tsx 가 두 컴포넌트를 더 이상 import 하지 않음)

만약 출력이 나오면 그 위치의 import 도 함께 정리.

- [ ] **Step 2: 파일 삭제**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git rm web/app/components/reports/ForecastTab.tsx
git rm web/app/components/reports/OptimizeTab.tsx
```

- [ ] **Step 3: type-check + build**

Run: `cd web && npx tsc --noEmit && npx next build`
Expected: 0 errors, 14 routes

- [ ] **Step 4: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git commit -m "refactor(B): ForecastTab/OptimizeTab 삭제 — /reports 단일 흐름이 인라인 흡수"
```

---

## Task 4: `/diagnosis-preview` 라우트 제거

**Files:**
- Delete: `web/app/(app)/diagnosis-preview/` (폴더 전체)

- [ ] **Step 1: 폴더 삭제**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git rm -r 'web/app/(app)/diagnosis-preview'
```

- [ ] **Step 2: 다른 곳에서 참조 없음 확인**

Run: `cd web && grep -rn "diagnosis-preview" app/ lib/`
Expected: 출력 없음

- [ ] **Step 3: type-check + build**

Run: `cd web && npx tsc --noEmit && npx next build`
Expected: 0 errors, **13 routes** (15 - `/diagnosis-preview` -1)

> 주: route 수 = 기존 (B_Track 머지 직후) 14 + Task 2 신규 진입 -1(diagnosis-preview 제거). 13 이면 정확. 14 가 나오면 어딘가 라우트가 안 정리된 것 — 점검.

- [ ] **Step 4: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git commit -m "refactor(B): /diagnosis-preview 라우트 제거 — /reports 가 진단 메인 사용처"
```

---

## Task 5: 최종 통합 검증

**Files:** 없음 — 검증만

- [ ] **Step 1: 전체 단위 테스트**

Run: `cd web && npx vitest run`
Expected: 34 tests pass (기존 26 + Task 1 의 8)

- [ ] **Step 2: 타입 체크**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: Production build**

Run: `cd web && npx next build`
Expected: 13 routes 통과, `/reports` size 정상 (기존 12.7~13.6 kB 정도)

- [ ] **Step 4: 시각 회귀 (dev 서버에서 사용자 확인)**

`http://127.0.0.1:5535/reports` 접속해서 다음 확인:

- [ ] 좌측 ReportDailyList 정상 — 날짜 선택 시 우측 갱신
- [ ] § 1 KPI 4 — 2번 자리가 GapKpiCard (mint/sun/rose 컬러)
- [ ] § 2 SpiBandChart — 볼린저 음영(brand) · 시나리오 3 선 · EWMA 점선 · 실적 강조 dot · 우상단 ConfidenceBadge
- [ ] § 3 RecoveryEtaCard(좌) + OptimizerResult(우) — Quadrant 점 클릭 시 "선택된 WP: {name}" 라벨 갱신
- [ ] § 4 BarChartH 2 (업체·공종)
- [ ] § 5 QuadrantScatter + QuadrantCountKpi — 필터 chip 클릭, 점 클릭 → § 3 의 WP 라벨 갱신
- [ ] § 6 RawData collapsible — 기본 접힘, 클릭 시 펼침
- [ ] 다른 페이지 회귀 — `/` `/home` `/tasks` `/review` `/dashboard` 모두 정상

- [ ] **Step 5: PR 생성**

본 plan 의 5 task 완료 후 push + PR:

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git push origin B_Track
gh pr create --base main --head B_Track \
  --title "feat(B): /reports Tabs 폐지 + 6 섹션 단일 흐름 (진단 모델 통합)" \
  --body "본 plan 4 task — diagnosis-adapter + page.tsx 재작성 + 정리. Test plan 은 plan §Task 5 참조."
```

---

## 검증 방법 요약

각 task 가 끝날 때마다:
1. `npx tsc --noEmit` — 0 errors
2. `npx vitest run` — 회귀 없음
3. Task 2 이후부터: `npx next build` — routes 수 일치
4. Task 5 에서 dev 서버 시각 검증

## 후속 plan 후보

1. **fixture 보강** — `detail.optimizer` 를 WP 별로 분리해 Quadrant 점 클릭 시 실제 권고도 전환
2. **(C) `/dashboard` 보완** — 6 현장 카드에 GapKpiCard mini + ConfidenceBadge
3. **(D) `/home` `/tasks` 단계별 결과** — Forecaster step 안 SpiBandChart 압축
4. **diagnose magic number 토큰화** — A_Track 연결 전 cleanup
