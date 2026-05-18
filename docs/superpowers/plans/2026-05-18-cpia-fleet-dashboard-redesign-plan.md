# Fleet Dashboard 재구성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/dashboard` Performance 탭을 /reports v3 의 정보 위계(KPI → 시계열 → 개별 카드)에 맞춰 재구성하고, 프로젝트별 대시보드(`/dashboard/sites/[id]`)는 제거한다.

**Architecture:** Performance 탭 안에 § 02 로 새 시계열(`FleetProductivityTrendChart`, 평균선 + min~max 분포 밴드)을 끼우고, § 03 의 `SiteOverviewCard` 에 90일 mini sparkline 을 추가하고 카드 자체의 클릭(Link) 동작을 비활성한다. 시계열·sparkline 데이터는 결정적 PRNG(mulberry32) 로 client-side 생성하는 공용 util (`lib/fleet-trend-mock.ts`) 로 통일. Impact 탭은 손대지 않는다.

**Tech Stack:** Next.js 14 App Router, React, TypeScript, recharts 3.x (`ComposedChart`/`Area`/`Line`/`ReferenceLine`/`LineChart`), Tailwind 의미 토큰 (`text-h*`/`text-body*`).

**Spec:** `docs/superpowers/specs/2026-05-18-cpia-fleet-dashboard-redesign-design.md`

**Branch:** `B_Track`

---

## 파일 구조

| 종류 | 경로 | 역할 |
|---|---|---|
| 신규 | `web/lib/fleet-trend-mock.ts` | mulberry32 기반 deterministic generator. site 별 90일 sparkline + fleet 평균/min/max 시계열 도출. |
| 신규 | `web/app/components/dashboard/FleetProductivityTrendChart.tsx` | § 02 — 전사 평균선 + 분포 밴드 + ReferenceLine. /reports `ProductivityTrendChart` 와 동일 톤. |
| 수정 | `web/lib/types.ts` | `FleetTrendPoint` 인터페이스 추가. |
| 수정 | `web/lib/fixtures.ts` | `DashboardFixture.performance` 에 optional `fleet_trend`, `site_sparklines` 필드 추가 (fixture 없으면 컴포넌트가 fallback 으로 mock 생성). |
| 수정 | `web/app/components/dashboard/SiteOverviewCard.tsx` | mini sparkline 90일로 교체, `<Link>` 제거 → `<article>`, hover/translate 효과 제거, `cursor-default`. |
| 수정 | `web/app/components/dashboard/PerformanceTab.tsx` | § 02 `FleetProductivityTrendChart` 끼움, § 03 SiteOverviewCard 그대로 6개 grid. |
| 삭제 | `web/app/(app)/dashboard/sites/` | `[id]` 디렉토리 전체. |
| 삭제 | `web/app/api/mock/dashboard/[id]/` | 동반 API route. |
| 영향 | sidebar/링크 grep — `dashboard/sites` 참조 SiteOverviewCard 외 없음(확인됨). |

---

## Task 1 — Types · Fixture interface · trend mock util

**Files:**
- Modify: `web/lib/types.ts`
- Modify: `web/lib/fixtures.ts`
- Create: `web/lib/fleet-trend-mock.ts`

### Step 1.1 — `FleetTrendPoint` type 추가

- [ ] Edit `web/lib/types.ts` — 파일 끝쪽 `// ────── Dashboard Impact ──────` 섹션 바로 위에 다음 블록을 삽입.

```ts
// ────── Dashboard Fleet Performance ──────
export interface FleetTrendPoint {
  date: string;   // ISO "YYYY-MM-DD"
  mean: number;   // 0..100 — 6 현장 평균 생산성
  min: number;    // 0..100 — 가장 낮은 현장
  max: number;    // 0..100 — 가장 높은 현장
}
```

### Step 1.2 — `DashboardFixture.performance` 확장

- [ ] Edit `web/lib/fixtures.ts` — `import type { ... } from "./types";` 줄에 `FleetTrendPoint` 를 추가하고, `DashboardFixture.performance` 인터페이스를 다음으로 교체.

```ts
import type {
  Site, SitesSummary, AgentStatus, DailyRun, AgentProgress, ChatMessage,
  WBSNode, ReviewItem, ReportDaily, ReportKpi, SCurvePoint, BarItem,
  QuadrantPoint, OptimizerOutput, RawDataRow, WPSummaryRow,
  ImpactSiteDistribution, ImpactTrendPoint, MiddleOfficeAutomation,
  SimulationSequence, FleetTrendPoint,
} from "./types";
```

```ts
export interface DashboardFixture {
  performance: {
    fleet_kpi: {
      avg_productivity: number;
      avg_delay: number;
      abnormal_total: number;
      recoverable_days: number;
    };
    /** 시연 안정성: fixture 가 비어있으면 컴포넌트가 mulberry32 로 deterministic 생성. */
    fleet_trend?: FleetTrendPoint[];
    site_sparklines?: Record<string, number[]>;
  };
  impact: {
    fleet_kpi: SitesSummary;
    site_distribution: ImpactSiteDistribution[];
    monthly_trend: ImpactTrendPoint[];
    per_site_automation: Record<string, MiddleOfficeAutomation[]>;
  };
}
```

### Step 1.3 — `lib/fleet-trend-mock.ts` 신규 작성

- [ ] Create `web/lib/fleet-trend-mock.ts` 전체 내용:

```ts
// 결정적 mock 생성기 — 같은 siteIds + endDate + todayValues 면 같은 시계열.
// /reports ProductivityTrendChart 의 mulberry32 패턴을 fleet 레벨로 확장.
import type { FleetTrendPoint } from "./types";

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

/** 단일 현장 90일 시계열 — base 92 random walk + 후반 30일 감소 trend, 마지막 값은 todayValue 로 강제. */
export function generateSiteTrend(
  siteId: string,
  todayValue: number,
  days = 90,
): number[] {
  const rand = mulberry32(hashString(siteId));
  const out: number[] = [];
  let v = 92;
  for (let i = 0; i < days; i++) {
    const drift = (rand() - 0.5) * 4;
    const trend = i > days - 30 ? -(i - (days - 30)) * 0.2 : 0;
    v = Math.max(70, Math.min(105, v + drift + trend));
    out.push(Math.round(v * 10) / 10);
  }
  if (out.length > 0) out[out.length - 1] = todayValue;
  return out;
}

/** N 사이트의 시계열을 모아 평균/min/max FleetTrendPoint[] 도출. endDate 기준 절대 날짜 ISO 라벨. */
export function buildFleetTrend(
  perSite: Record<string, number[]>,
  endDate: string,
  days = 90,
): FleetTrendPoint[] {
  const endMs = new Date(endDate).getTime();
  const series = Object.values(perSite);
  const len = series[0]?.length ?? days;
  const out: FleetTrendPoint[] = [];
  for (let i = 0; i < len; i++) {
    const values = series.map((s) => s[i]).filter((v): v is number => typeof v === "number");
    if (values.length === 0) continue;
    const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const ms = endMs - (len - 1 - i) * 86400000;
    const d = new Date(ms);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    out.push({
      date: iso,
      mean: Math.round(mean * 10) / 10,
      min: Math.round(min * 10) / 10,
      max: Math.round(max * 10) / 10,
    });
  }
  return out;
}
```

### Step 1.4 — 타입 컴파일 검증

- [ ] Run: `cd web && npx tsc --noEmit`
- Expected: 오류 없음. (변경된 파일 외에 다른 코드가 깨지지 않음.)

### Step 1.5 — Commit

- [ ] Run:

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/lib/types.ts web/lib/fixtures.ts web/lib/fleet-trend-mock.ts
git commit -m "$(cat <<'EOF'
feat(B): fleet trend mock util + DashboardFixture.performance 확장

- types.ts: FleetTrendPoint 인터페이스 추가
- fixtures.ts: DashboardFixture.performance 에 fleet_trend·site_sparklines optional 필드
- lib/fleet-trend-mock.ts: mulberry32 기반 deterministic 생성기
  (generateSiteTrend / buildFleetTrend)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — `FleetProductivityTrendChart` 신규

**Files:**
- Create: `web/app/components/dashboard/FleetProductivityTrendChart.tsx`

### Step 2.1 — 컴포넌트 작성

- [ ] Create `web/app/components/dashboard/FleetProductivityTrendChart.tsx` 전체 내용:

```tsx
"use client";
import { useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ReferenceDot,
  Label,
  CartesianGrid,
} from "recharts";
import { generateSiteTrend, buildFleetTrend } from "@/lib/fleet-trend-mock";
import type { Site, FleetTrendPoint } from "@/lib/types";

interface Props {
  sites: Site[];
  /** "YYYY-MM-DD" — 시계열 마지막 날짜. */
  endDate: string;
  /** 이력 평균(목표 생산성). ReferenceLine 으로 rose dashed 표시. */
  historyMean: number;
  /** fixture 에 fleet_trend 가 들어있으면 우선 사용. */
  fleetTrend?: FleetTrendPoint[];
  /** fixture 에 site_sparklines 가 들어있으면 평균/min/max 도 거기서 도출. */
  siteSparklines?: Record<string, number[]>;
  daysWindow?: number;
}

export function FleetProductivityTrendChart({
  sites,
  endDate,
  historyMean,
  fleetTrend,
  siteSparklines,
  daysWindow = 90,
}: Props) {
  const data = useMemo<FleetTrendPoint[]>(() => {
    if (fleetTrend && fleetTrend.length > 0) return fleetTrend;
    const perSite = siteSparklines && Object.keys(siteSparklines).length > 0
      ? siteSparklines
      : Object.fromEntries(
          sites.map((s) => [s.id, generateSiteTrend(s.id, s.productivity_today, daysWindow)]),
        );
    return buildFleetTrend(perSite, endDate, daysWindow);
  }, [sites, endDate, fleetTrend, siteSparklines, daysWindow]);

  const todayMean = data.length > 0 ? data[data.length - 1].mean : 0;
  const chartData = data.map((p) => ({ ...p, label: p.date.slice(5) }));

  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="font-display text-base font-semibold text-ink">
            전사 생산성 추세{" "}
            <span className="text-sm font-normal text-ink-mid">({endDate} 기준)</span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-display text-h3 font-semibold tracking-[-0.015em] text-ink">
              {todayMean.toFixed(1)}
            </span>
            <span className="text-base text-ink-light">%</span>
            <span className="ml-1 text-sm text-ink-mid">
              현장 {sites.length}개 평균
            </span>
          </div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={chartData} margin={{ top: 16, right: 32, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#eef0f4" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: "#7a8494" }}
            interval={Math.max(1, Math.floor(chartData.length / 8))}
          />
          <YAxis
            domain={[70, 105]}
            tick={{ fontSize: 10, fill: "#7a8494" }}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
            formatter={(v: number, key) => [`${v}%`, key === "mean" ? "평균" : key === "max" ? "최고" : "최저"]}
          />
          {/* 분포 밴드: max area 채우고 min area 를 흰색으로 덮어 min~max 영역만 보이게. */}
          <Area dataKey="max" stroke="none" fill="#e8eeff" fillOpacity={0.6} isAnimationActive={false} />
          <Area dataKey="min" stroke="none" fill="#ffffff" fillOpacity={1} isAnimationActive={false} />
          {/* 평균선 */}
          <Line
            dataKey="mean"
            stroke="#1a56db"
            strokeWidth={2.5}
            dot={false}
            isAnimationActive={false}
          />
          {/* 이력 평균 ReferenceLine */}
          <ReferenceLine
            y={historyMean}
            stroke="#ef4444"
            strokeWidth={2}
            strokeDasharray="5 4"
            ifOverflow="extendDomain"
          >
            <Label
              value={`이력 평균 ${historyMean}%`}
              position="top"
              offset={6}
              fill="#b91c1c"
              fontSize={13}
              fontWeight={700}
            />
          </ReferenceLine>
          {/* 오늘 평균 dot */}
          {chartData.length > 0 && (
            <ReferenceDot
              x={chartData[chartData.length - 1].label}
              y={todayMean}
              r={5}
              fill="#0d1117"
              stroke="#1a56db"
              strokeWidth={2}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
```

### Step 2.2 — 타입 컴파일 검증

- [ ] Run: `cd web && npx tsc --noEmit`
- Expected: 오류 없음.

### Step 2.3 — Commit

- [ ] Run:

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/app/components/dashboard/FleetProductivityTrendChart.tsx
git commit -m "$(cat <<'EOF'
feat(B): FleetProductivityTrendChart 신규 — 평균선 + 분포 밴드

전사 생산성 90일 시계열. 평균선(파랑) + min~max 분포 밴드(연파랑 영역)
+ 이력 평균 ReferenceLine(rose dashed). /reports ProductivityTrendChart 톤
일관. 데이터는 fixture 우선, 없으면 fleet-trend-mock.ts 로 derive.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — `SiteOverviewCard` sparkline 교체 + 클릭 비활성

**Files:**
- Modify: `web/app/components/dashboard/SiteOverviewCard.tsx`

### Step 3.1 — 컴포넌트 전체 교체

- [ ] Replace 전체 파일 `web/app/components/dashboard/SiteOverviewCard.tsx` 내용:

```tsx
"use client";
import { useMemo } from "react";
import { ResponsiveContainer, LineChart, Line } from "recharts";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { generateSiteTrend } from "@/lib/fleet-trend-mock";
import type { Site } from "@/lib/types";

interface Props {
  site: Site;
  /** fixture 의 site_sparklines[site.id] 가 있으면 그대로 사용, 없으면 deterministic 생성. */
  sparkline?: number[];
}

export function SiteOverviewCard({ site, sparkline }: Props) {
  const stripeColor =
    site.status === "risk" ? "bg-rose"
    : site.status === "caution" ? "bg-sun"
    : "bg-mint";

  const statusBg =
    site.status === "risk" ? "bg-rose-light text-rose-text"
    : site.status === "caution" ? "bg-sun-light text-sun-text"
    : "bg-mint-light text-mint-text";

  const sparkColor =
    site.status === "risk" ? "#ef4444"
    : site.status === "caution" ? "#d97706"
    : "#0ea76a";

  const data = useMemo(() => {
    const series = sparkline && sparkline.length > 0
      ? sparkline
      : generateSiteTrend(site.id, site.productivity_today, 90);
    return series.map((v) => ({ v }));
  }, [site.id, site.productivity_today, sparkline]);

  return (
    <article className="relative overflow-hidden rounded-card border border-border-soft bg-card p-4 shadow-xs cursor-default">
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", stripeColor)} />
      <div className="pl-3">
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <div className="truncate font-display text-h6 text-ink">{site.name}</div>
            <div className="font-mono text-xs uppercase tracking-wider text-ink-light mt-0.5">
              {site.location} · Hi-tech
            </div>
          </div>
          {site.status === "risk" && (
            <span className="inline-flex items-center gap-0.5 rounded-sm bg-rose-light px-1.5 py-0.5 text-[11px] font-bold text-rose-text">
              <AlertTriangle className="h-2.5 w-2.5" />
              이상
            </span>
          )}
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
          <div>
            <div className="text-ink-light">생산성</div>
            <div className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
              {site.productivity_today}%
            </div>
          </div>
          <div>
            <div className="text-ink-light">공기</div>
            <div className={cn(
              "font-display text-lg font-semibold tracking-[-0.01em]",
              site.delay_days > 0 ? "text-rose" : "text-mint",
            )}>
              {site.delay_days > 0 ? `+${site.delay_days}일` : "정상"}
            </div>
          </div>
        </div>

        <div className="mt-2 h-10">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <Line
                type="monotone"
                dataKey="v"
                stroke={sparkColor}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="mt-2 border-t border-border-soft pt-2">
          <span className={cn(
            "inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] font-semibold",
            statusBg,
          )}>
            {site.abnormal_trades > 0 ? `이상 공종 ${site.abnormal_trades}` : "정상"}
          </span>
        </div>
      </div>
    </article>
  );
}
```

**변경 요점:**
- `next/link Link` import 제거, `ArrowRight` lucide-react import 제거.
- 외곽 `<Link href=...>` → `<article className="... cursor-default">` (클릭 비활성, hover transform 제거).
- `makeSparkline` 7-point 가짜 함수 삭제 → `generateSiteTrend(...)` 또는 prop 사용으로 90-point 실 추세.
- sparkline 영역 높이 `h-8` → `h-10` (더 잘 보이게).
- 우하단 화살표 + group-hover 효과 제거 — 클릭 안 되므로 시각적 어포던스 정리.

### Step 3.2 — 타입 컴파일 검증

- [ ] Run: `cd web && npx tsc --noEmit`
- Expected: 오류 없음.

### Step 3.3 — Commit

- [ ] Run:

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/app/components/dashboard/SiteOverviewCard.tsx
git commit -m "$(cat <<'EOF'
refactor(B): SiteOverviewCard — 90일 sparkline + 클릭 비활성

- Link wrap 제거 → article + cursor-default (PoC 에서 카드 자체로 종료)
- 가짜 7-point makeSparkline 삭제 → generateSiteTrend(90 point)
- ArrowRight·group-hover 효과 제거 (어포던스 정리)
- sparkline 높이 h-8 → h-10, isAnimationActive=false

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — `PerformanceTab` 재조립

**Files:**
- Modify: `web/app/components/dashboard/PerformanceTab.tsx`

### Step 4.1 — 파일 전체 교체

- [ ] Replace 전체 파일 `web/app/components/dashboard/PerformanceTab.tsx` 내용:

```tsx
import { KpiStrip, type KpiItem } from "../reports/KpiStrip";
import { SiteOverviewCard } from "./SiteOverviewCard";
import { FleetProductivityTrendChart } from "./FleetProductivityTrendChart";
import type { Site, FleetTrendPoint } from "@/lib/types";

interface Props {
  sites: Site[];
  fleetKpi: {
    avg_productivity: number;
    avg_delay: number;
    abnormal_total: number;
    recoverable_days: number;
  };
  /** 시연 안정성: fixture 에 박힌 데이터가 있으면 컴포넌트가 우선 사용. */
  fleetTrend?: FleetTrendPoint[];
  siteSparklines?: Record<string, number[]>;
  /** 시계열 기준 날짜. 별도 prop 없으면 오늘 ISO 로 fallback. */
  endDate?: string;
}

export function PerformanceTab({
  sites,
  fleetKpi,
  fleetTrend,
  siteSparklines,
  endDate,
}: Props) {
  const today = endDate ?? new Date().toISOString().slice(0, 10);

  const kpi: KpiItem[] = [
    { label: "전사 평균 생산성", value: `${fleetKpi.avg_productivity}`, unit: "%", sub: "이력 대비 평균", tone: "normal" },
    { label: "평균 공기 격차",   value: `+${fleetKpi.avg_delay}`, unit: "일", sub: "전사 평균 지연", tone: "risk" },
    { label: "이상 공종 총합",   value: `${fleetKpi.abnormal_total}`, unit: "건", sub: "전사 합계", tone: "risk" },
    { label: "회복 가능 공기",   value: `-${fleetKpi.recoverable_days}`, unit: "일", sub: "Optimizer 평균", tone: "primary" },
  ];

  return (
    <div className="flex flex-col gap-6">
      {/* § 01 — Fleet KPI */}
      <KpiStrip items={kpi} />

      {/* § 02 — 전사 생산성 시계열 (평균선 + 분포 밴드) */}
      <FleetProductivityTrendChart
        sites={sites}
        endDate={today}
        historyMean={fleetKpi.avg_productivity}
        fleetTrend={fleetTrend}
        siteSparklines={siteSparklines}
      />

      {/* § 03 — 현장 카드 grid */}
      <div>
        <div className="mb-3 flex items-baseline gap-2">
          <h3 className="font-display text-h5 text-ink">현장별 진척 · 상태</h3>
          <span className="font-mono text-xs uppercase tracking-wider text-ink-light">
            {sites.length} sites
          </span>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {sites.map((s) => (
            <SiteOverviewCard
              key={s.id}
              site={s}
              sparkline={siteSparklines?.[s.id]}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
```

### Step 4.2 — `dashboard/page.tsx` 에 신규 props 전달

- [ ] Edit `web/app/(app)/dashboard/page.tsx` — `<PerformanceTab ...>` 호출부를 다음으로 교체.

```tsx
          <TabsContent value="performance" className="mt-6">
            <PerformanceTab
              sites={sites}
              fleetKpi={dashboard.performance.fleet_kpi}
              fleetTrend={dashboard.performance.fleet_trend}
              siteSparklines={dashboard.performance.site_sparklines}
            />
          </TabsContent>
```

### Step 4.3 — 타입 컴파일 검증

- [ ] Run: `cd web && npx tsc --noEmit`
- Expected: 오류 없음.

### Step 4.4 — Commit

- [ ] Run:

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/app/components/dashboard/PerformanceTab.tsx 'web/app/(app)/dashboard/page.tsx'
git commit -m "$(cat <<'EOF'
feat(B): PerformanceTab 재조립 — § 01 KPI / § 02 시계열 / § 03 카드 grid

- § 02 FleetProductivityTrendChart 끼움 (sites + endDate + historyMean)
- § 03 SiteOverviewCard 에 sparkline prop 전달 (fixture 우선, fallback derive)
- page.tsx 의 <PerformanceTab> 호출부에 fleetTrend·siteSparklines prop 전달

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 — `/dashboard/sites/[id]` 제거 + 빌드 검증

**Files:**
- Delete: `web/app/(app)/dashboard/sites/` (디렉토리 전체)
- Delete: `web/app/api/mock/dashboard/[id]/` (route 전체)

### Step 5.1 — 잔존 참조 grep

- [ ] Run:

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
grep -rn "dashboard/sites" web/app web/components 2>/dev/null
```

- Expected: 결과 없음 (Task 3 에서 SiteOverviewCard 의 Link 가 제거됐기 때문). 만약 결과가 있으면 해당 파일에서 참조 제거 후 진행.

### Step 5.2 — 디렉토리 삭제

- [ ] Run:

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
rm -rf 'web/app/(app)/dashboard/sites'
rm -rf 'web/app/api/mock/dashboard/[id]'
git status | head -20
```

- Expected: `deleted:` 항목으로 두 디렉토리의 파일들이 모두 staged 가능 상태.

### Step 5.3 — 빌드 (`.next` 캐시 클리어 필수)

- [ ] Run:

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
rm -rf web/.next
cd web && npm run build
```

- Expected: 빌드 성공. 라우트 목록에서 `/dashboard/sites/[id]` 와 `/api/mock/dashboard/[id]` 가 사라지고 나머지는 그대로.

### Step 5.4 — Commit

- [ ] Run:

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add -A 'web/app/(app)/dashboard' 'web/app/api/mock/dashboard'
git commit -m "$(cat <<'EOF'
refactor(B): /dashboard/sites/[id] 페이지 + API route 제거

PoC 범위에서 프로젝트별 대시보드 제외 결정. SiteOverviewCard 의
Link 가 이미 비활성 (Task 3) 되어 외부 참조 없음.

- web/app/(app)/dashboard/sites/[id]/page.tsx + 디렉토리 삭제
- web/app/api/mock/dashboard/[id]/route.ts + 디렉토리 삭제

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Step 5.5 — 시각 검증 (수동)

- [ ] Run dev server: `cd web && npm run dev` (별도 터미널)
- [ ] Browser 에서 `http://localhost:3000/dashboard` 진입
  - § 01 Fleet KPI 4 노출 확인
  - § 02 시계열: 평균선 + 분포 밴드 + rose 점선 이력평균 + 오늘 dot 확인
  - § 03 카드 grid: 6개 현장, 각 카드 안 sparkline 6개가 모두 다른 형상, 카드 hover 시 클릭 어포던스 없음 (cursor-default)
- [ ] `http://localhost:3000/dashboard/sites/M15X-Ph3-IBL` 직접 진입 → 404 표시 확인
- [ ] Impact 탭 클릭 → 기존 내용(KPI + 연간환산 chip + HorizontalBarList + TrendLineChart) 동일 동작 확인

---

## 최종 검증

- [ ] Run: `cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project" && git log --oneline main..B_Track | head -10`
  - Expected: Task 1~5 의 5 commit 이 순서대로 쌓여 있음.

- [ ] Run: `cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project" && rm -rf web/.next && cd web && npm run build 2>&1 | tail -20`
  - Expected: 빌드 성공, 라우트 11개 (`/dashboard/sites/[id]` 와 `/api/mock/dashboard/[id]` 사라짐, 나머지 그대로).

- [ ] PR 업데이트 (B_Track push) 또는 새 PR — 별도 명령으로 사용자가 결정.

```bash
git push origin B_Track
```
