# `/reports` v2 (5 섹션 인과 흐름) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** spec `2026-05-17-cpia-report-redesign-design.md` (v2) 의 5 섹션 inverted-pyramid 흐름을 PR #20 의 6 섹션 코드 위에 재구성한다. § 3 ForecastChart 단순화 + § 4 통합(4분면+Optimizer+Recovery) + § 5 WPSummaryTable 추가.

**Architecture:** PR #20 의 `/reports/page.tsx` 와 컴포넌트들을 기반으로 다음을 추가/수정:
- 신규 `ForecastChart` (SpiBandChart 의 단순화 버전 — 4 default layer + 3 toggle chip + 자연어 1줄 + `recoveryActive` overlay)
- 신규 `WPSummaryTable` (WP 단위 행 + 클릭 시 onSelect)
- `RawDataTab` 에 `filterWpId?` prop 추가
- `WPSummaryRow` 타입 + `ReportDetail.wp_summary` 필드 + `data/mock_report.json` 보강
- `page.tsx` 6 → 5 섹션 재구성 (§ 3 ForecastChart, § 4 통합, § 5 WPSummary stack)

기존 `SpiBandChart` 는 삭제하지 않음 — 후속 (C)/(D) 화면에서 재사용 가능. /reports 에서만 사용 안 함.

**Tech Stack:** Next.js · React · recharts · Vitest · Tailwind

**Scope 밖 (별도 plan):**
- (C) `/dashboard` 6 현장 보강
- (D) `/home` `/tasks` 단계별 결과
- `detail.optimizer` WP 별 분리 — 본 plan 도 단일 OptimizerOutput 유지, 헤더 라벨만 갱신
- A_Track 실 데이터 연결

---

## 파일 구조

| 종류 | 경로 | 책임 |
|---|---|---|
| 수정 | `web/lib/types.ts` | `WPSummaryRow` interface 추가 |
| 수정 | `web/lib/fixtures.ts` | `ReportDetail` 에 `wp_summary: WPSummaryRow[]` 필드 추가 |
| 수정 | `data/mock_report.json` | 각 date detail 에 `wp_summary` 배열 보강 (quadrant 의 6 WP 1:1 매칭) |
| 신규 | `web/app/components/reports/WPSummaryTable.tsx` | WP 단위 행 테이블 + 행 클릭 onSelect |
| 신규 | `web/app/components/charts/ForecastChart.tsx` | 단순화된 추세 차트 — 4 default + 3 toggle + 자연어 1줄 + recoveryActive |
| 수정 | `web/app/components/reports/RawDataTab.tsx` | `filterWpId?: string` prop 추가 — 그 wp 만 표시 |
| 수정 (재작성) | `web/app/(app)/reports/page.tsx` | 6 → 5 섹션 재구성. § 3 = ForecastChart, § 4 = 통합, § 5 = WPSummary+RawData stack |

---

## Task 1: `WPSummaryRow` 타입 + `ReportDetail.wp_summary` 필드

**Files:**
- Modify: `web/lib/types.ts` (파일 끝에 추가)
- Modify: `web/lib/fixtures.ts` (`ReportDetail` 인터페이스 필드 추가)

- [ ] **Step 1: types.ts 끝에 WPSummaryRow 추가**

`web/lib/types.ts` 끝에 추가:

```ts
// ────── /reports § 5 — WP 단위 요약 (작업일보 상세의 컨텍스트) ──────
export interface WPSummaryRow {
  wp_id: string;
  wp_name: string;       // "WP-3-2 거푸집"
  trade: string;         // "골조"
  bp_name: string;       // "A건설"
  start_date: string;    // "2026-05-08"
  end_date: string;      // "2026-05-22"
  progress_pct: number;  // 0..100
  productivity: number;  // 0..100 — Quadrant 의 productivity 와 동일 값
  status: "normal" | "caution" | "risk";
}
```

- [ ] **Step 2: fixtures.ts ReportDetail 에 wp_summary 추가**

`web/lib/fixtures.ts` 의 `ReportDetail` 인터페이스에 필드 한 줄 추가. 현재 정의:

```ts
export interface ReportDetail {
  kpi: ReportKpi;
  s_curve: SCurvePoint[];
  contractor_bars: BarItem[];
  trade_bars: BarItem[];
  quadrant: QuadrantPoint[];
  optimizer: OptimizerOutput;
  raw_data: RawDataRow[];
}
```

→ 다음으로 변경:

```ts
import type {
  ReportKpi,
  SCurvePoint,
  BarItem,
  QuadrantPoint,
  OptimizerOutput,
  RawDataRow,
  WPSummaryRow,
} from "./types";

export interface ReportDetail {
  kpi: ReportKpi;
  s_curve: SCurvePoint[];
  contractor_bars: BarItem[];
  trade_bars: BarItem[];
  quadrant: QuadrantPoint[];
  optimizer: OptimizerOutput;
  raw_data: RawDataRow[];
  wp_summary: WPSummaryRow[];
}
```

기존 import 라인에 `WPSummaryRow` 만 추가하면 됨.

- [ ] **Step 3: type-check (이 시점에 mock_report.json 갱신 전이라 fixture 로딩 타입 불일치 가능 → Task 2 에서 해결)**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors. (fixture JSON 은 런타임 객체로 로드되어 TS 컴파일과 무관 — 타입 정의만 추가됐으므로 통과)

- [ ] **Step 4: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/lib/types.ts web/lib/fixtures.ts
git commit -m "feat(B): WPSummaryRow 타입 + ReportDetail.wp_summary 필드"
```

---

## Task 2: `data/mock_report.json` 에 wp_summary 보강

**Files:**
- Modify: `data/mock_report.json` — `details["2026-05-15"]` 에 `wp_summary` 배열 추가

기존 quadrant 의 6 WP 와 1:1 매칭하는 행 6개. status 와 productivity 는 quadrant 와 동일 값 사용. bp_name 은 raw_data 행에서 wp 별 첫 bp 를 가져오는 게 자연스러우나 시연용 합리값으로 직접 명시.

- [ ] **Step 1: mock_report.json 의 `details["2026-05-15"]` 에 wp_summary 필드 추가**

`details["2026-05-15"]` 의 `raw_data` 배열 뒤에 다음 필드 추가 (마지막 `}` 직전):

```json
,
"wp_summary": [
  {
    "wp_id": "wp-3-3",
    "wp_name": "WP-3-3 철근",
    "trade": "골조",
    "bp_name": "B건설",
    "start_date": "2026-05-04",
    "end_date": "2026-05-28",
    "progress_pct": 54,
    "productivity": 54,
    "status": "risk"
  },
  {
    "wp_id": "wp-3-2",
    "wp_name": "WP-3-2 거푸집",
    "trade": "골조",
    "bp_name": "A건설",
    "start_date": "2026-05-08",
    "end_date": "2026-05-22",
    "progress_pct": 68,
    "productivity": 68,
    "status": "risk"
  },
  {
    "wp_id": "wp-5-1",
    "wp_name": "WP-5-1 방수",
    "trade": "마감",
    "bp_name": "C건설",
    "start_date": "2026-05-10",
    "end_date": "2026-06-05",
    "progress_pct": 41,
    "productivity": 82,
    "status": "caution"
  },
  {
    "wp_id": "wp-3-4",
    "wp_name": "WP-3-4 콘크리트",
    "trade": "골조",
    "bp_name": "F건설",
    "start_date": "2026-05-05",
    "end_date": "2026-05-15",
    "progress_pct": 92,
    "productivity": 96,
    "status": "caution"
  },
  {
    "wp_id": "wp-7-1",
    "wp_name": "WP-7-1 전기",
    "trade": "MEP",
    "bp_name": "D건설",
    "start_date": "2026-05-12",
    "end_date": "2026-06-20",
    "progress_pct": 22,
    "productivity": 95,
    "status": "normal"
  },
  {
    "wp_id": "wp-1-1",
    "wp_name": "WP-1-1 터파기",
    "trade": "토공사",
    "bp_name": "E건설",
    "start_date": "2026-04-20",
    "end_date": "2026-05-18",
    "progress_pct": 88,
    "productivity": 92,
    "status": "normal"
  }
]
```

JSON 유효성에 유의 — 직전 `raw_data` 배열 끝 `]` 뒤에 `,` 가 있어야 한다.

- [ ] **Step 2: JSON 유효성 검증**

Run: `cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project" && python3 -c "import json; d=json.load(open('data/mock_report.json')); print('wp_summary rows:', len(d['details']['2026-05-15']['wp_summary']))"`
Expected: `wp_summary rows: 6`

- [ ] **Step 3: 회귀 — vitest + tsc + build**

Run: `cd web && npx vitest run && npx tsc --noEmit`
Expected: 34 tests pass, 0 errors

- [ ] **Step 4: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add data/mock_report.json
git commit -m "feat(B): mock_report.json — wp_summary 6 행 보강 (quadrant 1:1 매칭)"
```

---

## Task 3: `WPSummaryTable` 컴포넌트

**Files:**
- Create: `web/app/components/reports/WPSummaryTable.tsx`

행 클릭 시 onSelect 콜백, 선택된 wp 는 강조. status 컬러 dot + 진척률 bar 시각.

- [ ] **Step 1: 컴포넌트 작성**

`web/app/components/reports/WPSummaryTable.tsx`:

```tsx
"use client";
import { cn } from "@/lib/utils";
import type { WPSummaryRow } from "@/lib/types";

interface Props {
  rows: WPSummaryRow[];
  selectedWpId: string | null;
  onSelect: (wpId: string) => void;
}

const STATUS_DOT = {
  normal:  "bg-mint",
  caution: "bg-sun",
  risk:    "bg-rose",
} as const;

const STATUS_LABEL = {
  normal:  "정상",
  caution: "주의",
  risk:    "이상",
} as const;

export function WPSummaryTable({ rows, selectedWpId, onSelect }: Props) {
  return (
    <div className="rounded-card border border-border-soft bg-card shadow-xs overflow-hidden">
      <div className="border-b border-border-soft px-4 py-3">
        <div className="font-display text-h6 text-ink">
          WP 요약
          <span className="ml-2 text-body-sm font-normal text-ink-mid">{rows.length} 개 · 행 클릭 시 작업일보 필터</span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-body-sm">
          <thead>
            <tr className="border-b border-border-soft bg-surface-soft/40 text-left">
              <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-light">WP명</th>
              <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-light">공종</th>
              <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-light">BP사</th>
              <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-light">시작</th>
              <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-light">종료</th>
              <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-light">진척</th>
              <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-light">생산성</th>
              <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-light">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const selected = row.wp_id === selectedWpId;
              return (
                <tr
                  key={row.wp_id}
                  onClick={() => onSelect(row.wp_id)}
                  className={cn(
                    "cursor-pointer border-b border-border-soft transition-colors hover:bg-surface-soft",
                    selected && "bg-brand-light/40",
                  )}
                >
                  <td className="px-3 py-2 font-semibold text-ink">{row.wp_name}</td>
                  <td className="px-3 py-2 text-ink-mid">{row.trade}</td>
                  <td className="px-3 py-2 text-ink-mid">{row.bp_name}</td>
                  <td className="px-3 py-2 font-mono text-[11px] text-ink-mid">{row.start_date}</td>
                  <td className="px-3 py-2 font-mono text-[11px] text-ink-mid">{row.end_date}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-20 rounded-full bg-border">
                        <div
                          className="h-full rounded-full bg-brand"
                          style={{ width: `${Math.min(100, row.progress_pct)}%` }}
                        />
                      </div>
                      <span className="font-mono text-[11px] text-ink-mid">{row.progress_pct}%</span>
                    </div>
                  </td>
                  <td className="px-3 py-2 font-display font-semibold text-ink">{row.productivity}%</td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1.5">
                      <span className={cn("h-1.5 w-1.5 rounded-full", STATUS_DOT[row.status])} />
                      <span className="font-mono text-[10px] uppercase tracking-wider text-ink-mid">
                        {STATUS_LABEL[row.status]}
                      </span>
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: type-check**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/app/components/reports/WPSummaryTable.tsx
git commit -m "feat(B): WPSummaryTable — WP 단위 요약 (시작·종료·진척·생산성·status) + 행 클릭"
```

---

## Task 4: `ForecastChart` 컴포넌트 (단순화된 추세 차트)

**Files:**
- Create: `web/app/components/charts/ForecastChart.tsx`

SpiBandChart 의 단순화 — default 4 layer (planned · actual · base scenario · 신뢰 밴드) + toggle chip 3 (Optimistic / Pessimistic / EWMA) + 자연어 1줄 + recoveryActive 가 true 일 때 만회 곡선 강조.

- [ ] **Step 1: 컴포넌트 작성**

`web/app/components/charts/ForecastChart.tsx`:

```tsx
"use client";
import { useState } from "react";
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
import { cn } from "@/lib/utils";
import type { ProductivityDiagnosis } from "@/lib/types";
import { ConfidenceBadge } from "../reports/ConfidenceBadge";

interface Props {
  diagnosis: ProductivityDiagnosis;
  /** Optimizer 권고 시나리오를 강조 표시. § 4 에서 WP 선택 시 true. */
  recoveryActive?: boolean;
}

interface ToggleState {
  optimistic: boolean;
  pessimistic: boolean;
  ewma: boolean;
}

export function ForecastChart({ diagnosis, recoveryActive = false }: Props) {
  const [toggles, setToggles] = useState<ToggleState>({
    optimistic: false,
    pessimistic: false,
    ewma: false,
  });

  /* recoveryActive 가 true 면 Optimistic 시나리오를 강제 표시 (만회 곡선) */
  const showOptimistic = toggles.optimistic || recoveryActive;

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

  const firstUndef = data.findIndex((d) => d.actual === undefined);
  const lastIdx = firstUndef === -1 ? data.length - 1 : firstUndef - 1;
  const lastPoint = lastIdx >= 0 ? data[lastIdx] : null;

  return (
    <div className="rounded-card border border-border-soft bg-card p-5 shadow-xs">
      {/* 헤더 + 자연어 해석 */}
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <div className="font-display text-h6 text-ink">Forecast</div>
          <div className="text-body-sm text-ink-mid">현 추세 + 신뢰 밴드</div>
        </div>
        <ConfidenceBadge sampleSize={diagnosis.sample_size} />
      </div>

      {/* 자연어 해석 1줄 (recoveryActive 면 한 줄 추가) */}
      <div className="mb-3 space-y-1 text-body-sm text-ink-mid">
        <p>📊 {baseNarrative(diagnosis)}</p>
        {recoveryActive && (
          <p>⚡ {recoveryNarrative(diagnosis)}</p>
        )}
      </div>

      {/* 토글 chip 3 */}
      <div className="mb-3 flex flex-wrap gap-1.5">
        <ToggleChip
          label="만회 시나리오"
          color="mint"
          active={showOptimistic}
          forced={recoveryActive}
          onClick={() => setToggles((s) => ({ ...s, optimistic: !s.optimistic }))}
        />
        <ToggleChip
          label="현 추세 유지"
          color="rose"
          active={toggles.pessimistic}
          onClick={() => setToggles((s) => ({ ...s, pessimistic: !s.pessimistic }))}
        />
        <ToggleChip
          label="최근 추세 (EWMA)"
          color="ink"
          active={toggles.ewma}
          onClick={() => setToggles((s) => ({ ...s, ewma: !s.ewma }))}
        />
      </div>

      {/* Chart */}
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
            labelFormatter={(v) => String(v)}
          />

          {/* 신뢰 밴드 — default */}
          <Area dataKey="band_high" stroke="none" fill="#e8eeff" fillOpacity={0.4} activeDot={false} isAnimationActive={false} />
          <Area dataKey="band_low"  stroke="none" fill="#ffffff" fillOpacity={1}   activeDot={false} isAnimationActive={false} />

          {/* 계획선 — default */}
          <Line dataKey="planned" stroke="#7a8494" strokeWidth={1.5} dot={false} isAnimationActive={false} />

          {/* 현 추세 (base scenario) — default 메인 */}
          <Line dataKey="base" stroke="#1a56db" strokeWidth={2.5} dot={false} isAnimationActive={false} />

          {/* 실적 — default */}
          <Line dataKey="actual" stroke="#0d1117" strokeWidth={2} dot={false} isAnimationActive={false} />

          {/* Toggle: Optimistic (만회) */}
          {showOptimistic && (
            <Line dataKey="optimistic" stroke="#0ea76a" strokeWidth={2.5} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
          )}

          {/* Toggle: Pessimistic */}
          {toggles.pessimistic && (
            <Line dataKey="pessimistic" stroke="#ef4444" strokeWidth={2} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
          )}

          {/* Toggle: EWMA */}
          {toggles.ewma && (
            <Line dataKey="ewma" stroke="#444e5e" strokeWidth={1.5} strokeDasharray="2 2" dot={false} isAnimationActive={false} />
          )}

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
    </div>
  );
}

/* ── 자연어 해석 ── */

function baseNarrative(d: ProductivityDiagnosis): string {
  const sign = d.z_score >= 0 ? "+" : "−";
  const absZ = Math.abs(d.z_score).toFixed(1);
  const within = Math.abs(d.z_score) < 1.5;
  const range = within ? "정상 변동 범위 안" : "정상 변동 범위 밖";
  const eta = d.scenarios.base.eta_days;
  const etaText = Number.isFinite(eta) ? `자연 회귀 시 ${eta}일 회복` : "자연 회귀 불가";
  return `이력 평균 ${sign}${absZ}σ — ${range}, ${etaText}.`;
}

function recoveryNarrative(d: ProductivityDiagnosis): string {
  const opt = d.scenarios.optimistic;
  const baseEta = d.scenarios.base.eta_days;
  if (!Number.isFinite(opt.eta_days)) {
    return `AI 권고 적용 시에도 회복 불가.`;
  }
  if (!Number.isFinite(baseEta)) {
    return `AI 권고 적용 시 ${opt.eta_days}일에 회복 가능.`;
  }
  const cut = baseEta - opt.eta_days;
  return `AI 권고 적용 시 ${cut}일 단축 (${opt.eta_days}일에 회복).`;
}

/* ── 토글 chip ── */

interface ToggleChipProps {
  label: string;
  color: "mint" | "rose" | "ink";
  active: boolean;
  forced?: boolean;
  onClick: () => void;
}

function ToggleChip({ label, color, active, forced, onClick }: ToggleChipProps) {
  const dot = {
    mint: "bg-mint",
    rose: "bg-rose",
    ink:  "bg-ink-mid",
  }[color];
  return (
    <button
      type="button"
      onClick={forced ? undefined : onClick}
      disabled={forced}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-mono uppercase tracking-wider transition-colors",
        active
          ? "border-brand bg-brand-light text-brand-text"
          : "border-border bg-card text-ink-light hover:border-ink-light/40 hover:text-ink-mid",
        forced && "cursor-default opacity-90",
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", dot)} />
      {label}
      {forced && <span className="ml-0.5 text-[9px]">●</span>}
    </button>
  );
}
```

- [ ] **Step 2: type-check**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/app/components/charts/ForecastChart.tsx
git commit -m "feat(B): ForecastChart — 4 default + 3 toggle chip + 자연어 1줄 + recoveryActive"
```

---

## Task 5: `RawDataTab` 에 `filterWpId` prop 추가

**Files:**
- Modify: `web/app/components/reports/RawDataTab.tsx`

선택된 WP 가 있으면 그 WP 의 wp_name 으로 행을 필터링. wp_name 은 raw_data 의 `wp` 필드와 매칭.

- [ ] **Step 1: 현재 RawDataTab 구조 점검**

Run: `cd web && grep -n "interface\|RawDataRow\|filterWpId" app/components/reports/RawDataTab.tsx | head -10`

- [ ] **Step 2: filterWpId prop 추가 + 필터 로직**

`web/app/components/reports/RawDataTab.tsx` 의 컴포넌트 시그너처와 필터 부분 수정. 변경 양:

```tsx
interface Props {
  rows: RawDataRow[];
  filterWpId?: string | null;   // 선택된 WP — wp_name 으로 raw_data.wp 와 매칭
  wpNameById?: Record<string, string>;  // wp_id → wp_name lookup (page 가 wp_summary 에서 만들어 전달)
}

export function RawDataTab({ rows, filterWpId, wpNameById }: Props) {
  // 기존 search/CSV state ...
  // 기존 검색 필터링 로직 외에 wp filter 추가:
  const wpName = filterWpId && wpNameById ? wpNameById[filterWpId] : null;
  const filteredRows = wpName
    ? rows.filter((r) => r.wp === wpName)
    : rows;
  // 이후 filteredRows 로 검색/CSV/표시 ...
}
```

실제 구현 시 기존 search 변수와 결합:

```tsx
const wpName = filterWpId && wpNameById ? wpNameById[filterWpId] : null;
const filteredRows = rows.filter((r) => {
  if (wpName && r.wp !== wpName) return false;
  if (search) {
    const q = search.toLowerCase();
    if (
      !r.bp_name.toLowerCase().includes(q) &&
      !r.wp.toLowerCase().includes(q) &&
      !r.work_content.toLowerCase().includes(q)
    ) return false;
  }
  return true;
});
```

기존 search 변수명·필터 로직은 파일을 읽어 확인 후 보존. 헤더에 "현재 필터: {wp_name}" 표시 추가 권장:

```tsx
{wpName && (
  <span className="rounded-full bg-brand-light px-2 py-0.5 font-mono text-[10px] text-brand-text">
    WP: {wpName}
  </span>
)}
```

- [ ] **Step 3: type-check + build**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/app/components/reports/RawDataTab.tsx
git commit -m "feat(B): RawDataTab — filterWpId/wpNameById prop 추가 → WP 선택 시 자동 필터"
```

---

## Task 6: `/reports/page.tsx` 5 섹션 재작성

**Files:**
- Modify (재작성): `web/app/(app)/reports/page.tsx`

PR #20 의 6 섹션 구조를 5 섹션 v2 로 교체. SpiBandChart import 제거, ForecastChart 사용. § 4 통합 (Quadrant + Optimizer + Recovery). § 5 WPSummaryTable + RawDataTab stack.

- [ ] **Step 1: 새 page.tsx 작성 (전체 교체)**

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
import { WPSummaryTable } from "@/app/components/reports/WPSummaryTable";
import { ForecastChart } from "@/app/components/charts/ForecastChart";
import { BarChartH } from "@/app/components/charts/BarChartH";
import { QuadrantScatter } from "@/app/components/charts/QuadrantScatter";
import { diagnose } from "@/lib/diagnosis";
import { toDiagnosisInput } from "@/lib/diagnosis-adapter";
import type { ReportDaily } from "@/lib/types";
import type { ReportDetail } from "@/lib/fixtures";

type Filter = "all" | "risk" | "caution" | "safe";

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

  /* wp_id → wp_name lookup (RawDataTab 필터용) */
  const wpNameById = useMemo(() => {
    if (!detail) return {};
    return Object.fromEntries(detail.wp_summary.map((w) => [w.wp_id, w.wp_name]));
  }, [detail]);

  if (!detail || !diagnosis) {
    return <div className="px-6 py-10 text-ink-light">Loading...</div>;
  }

  const kpiRest: KpiItem[] = [
    { label: "현재 생산성", value: `${detail.kpi.productivity_today}`, unit: "%", sub: `이력 ${detail.kpi.productivity_history_diff > 0 ? "+" : ""}${detail.kpi.productivity_history_diff}%`, tone: detail.kpi.productivity_today < 90 ? "risk" : "normal" },
    { label: "현 추세 공기", value: `D+${detail.kpi.delay_days}`, unit: "일 지연", sub: detail.kpi.expected_completion, tone: "risk" },
    { label: "회복 후 공기", value: `-${detail.kpi.recovery_days}`, unit: "일 회복", sub: detail.kpi.recovered_completion, tone: "normal" },
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
          결론 → 현재 상태 → 추세 → 이슈+권고 → 원본의 인과 흐름으로 확인합니다.
        </p>
      </div>

      <section className="mx-auto w-full max-w-screen-2xl px-6 pb-20 md:px-10">
        <div className="mt-6 grid grid-cols-12 gap-4">
          {/* Left — DailyList sticky */}
          <div className="col-span-12 md:col-span-3">
            <div className="flex flex-col overflow-hidden rounded-card border border-border-soft bg-card shadow-xs lg:sticky lg:top-6 lg:h-[calc(100vh-220px)]">
              <ReportDailyList daily={daily} selectedDate={selectedDate} onSelect={setSelectedDate} />
            </div>
          </div>

          {/* Right — 5 sections */}
          <div className="col-span-12 flex flex-col gap-10 md:col-span-9">

            {/* § 1 — 결론 */}
            <Section eyebrow="/ 01 — 결론" title="KPI 요약" subtitle="아래에서 도출된 결과">
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

            {/* § 2 — 현재 상태 */}
            <Section eyebrow="/ 02 — 현재 상태" title="업체 · 공종 생산성" subtitle="KPI #1·#2 의 근거">
              <div className="grid gap-4 md:grid-cols-2">
                <BarChartH items={detail.contractor_bars} title="업체별 생산성 (오늘 평균)" />
                <BarChartH items={detail.trade_bars} title="공종별 생산성 (오늘 평균)" />
              </div>
            </Section>

            {/* § 3 — Forecasting */}
            <Section eyebrow="/ 03 — Forecasting" title="현 추세 + 신뢰 밴드" subtitle="KPI #3 의 근거 · § 4 클릭 시 만회 곡선 추가">
              <ForecastChart
                diagnosis={diagnosis}
                recoveryActive={selectedWpId !== null}
              />
            </Section>

            {/* § 4 — 이슈 + 권고 */}
            <Section eyebrow="/ 04 — 이슈 + 권고" title="4분면 + Optimizer" subtitle="Forecasting → Optimizer 브릿지 · KPI #4 의 근거">
              <div className="grid grid-cols-12 gap-4">
                {/* 좌: Quadrant + filter */}
                <div className="col-span-12 md:col-span-6 flex flex-col gap-3">
                  <QuadrantCountKpi points={detail.quadrant} filter={filter} onFilterChange={setFilter} />
                  <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
                    <div className="mb-2 font-display text-h6 text-ink">Impact × Productivity 산점도</div>
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

                {/* 우: Optimizer + Recovery */}
                <div className="col-span-12 md:col-span-6 flex flex-col gap-3">
                  <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
                    <div className="text-body-sm text-ink-mid">
                      {selectedWp ? (
                        <>선택된 WP: <span className="font-semibold text-ink">{selectedWp.wp_name}</span> <span className="text-ink-light">({selectedWp.trade})</span></>
                      ) : (
                        <>WP 미선택 — 산점도에서 점을 클릭하세요</>
                      )}
                    </div>
                  </div>
                  <OptimizerResult output={detail.optimizer} />
                  <RecoveryEtaCard scenarios={diagnosis.scenarios} />
                </div>
              </div>
            </Section>

            {/* § 5 — 원본 데이터 (WP 요약 + 작업일보 상세) */}
            <Section eyebrow="/ 05 — 원본 데이터" title="WP 요약 + 작업일보 상세" subtitle="근거 자료 (기본 접힘)">
              <button
                type="button"
                onClick={() => setRawOpen((v) => !v)}
                className="flex w-full items-center justify-between rounded-card border border-border-soft bg-card px-5 py-4 shadow-xs transition-shadow hover:shadow-sm"
                aria-expanded={rawOpen}
              >
                <span className="text-body-sm text-ink">
                  {rawOpen ? "원본 데이터 접기" : `원본 데이터 펼치기 · WP ${detail.wp_summary.length}개 · 작업일보 ${detail.raw_data.length} rows`}
                </span>
                <ChevronDown
                  className={`h-4 w-4 text-ink-mid transition-transform ${rawOpen ? "rotate-180" : ""}`}
                />
              </button>
              {rawOpen && (
                <div className="mt-3 flex flex-col gap-4">
                  <WPSummaryTable
                    rows={detail.wp_summary}
                    selectedWpId={selectedWpId}
                    onSelect={setSelectedWpId}
                  />
                  <RawDataTab
                    rows={detail.raw_data}
                    filterWpId={selectedWpId}
                    wpNameById={wpNameById}
                  />
                </div>
              )}
            </Section>

          </div>
        </div>
      </section>
    </div>
  );
}

/* ── 헬퍼 ── */

function Section({
  eyebrow,
  title,
  subtitle,
  children,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          {eyebrow}
        </span>
        <h2 className="mt-1 font-display text-h5 text-ink">{title}</h2>
        {subtitle && (
          <p className="mt-0.5 text-body-sm text-ink-mid">{subtitle}</p>
        )}
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
Expected: 13 routes 통과, `/reports` size 정상

- [ ] **Step 4: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add 'web/app/(app)/reports/page.tsx'
git commit -m "feat(B): /reports 5 섹션 v2 — 결론·현재·추세·이슈+권고·원본 인과 흐름"
```

---

## Task 7: 최종 통합 검증 + push + PR

**Files:** 없음 — 검증만

- [ ] **Step 1: 전체 단위 테스트**

Run: `cd web && npx vitest run`
Expected: 34 tests pass

- [ ] **Step 2: 타입 체크 + build**

Run: `cd web && npx tsc --noEmit && npx next build`
Expected: 0 errors, 13 routes

- [ ] **Step 3: 시각 회귀 (dev 서버)**

`http://127.0.0.1:5535/reports` 접속해서 다음 확인:

- [ ] § 1 KPI 4 (eyebrow "/ 01 — 결론", subtitle "아래에서 도출된 결과")
- [ ] § 2 BarChartH 2 (업체별 + 공종별)
- [ ] § 3 ForecastChart — default 4 layer (계획선 회색 · 실적 검정 · base 파란 · 신뢰 밴드 음영). 자연어 1줄 "이력 평균 -1.8σ ..." 노출. 토글 chip 3 (만회/현추세유지/EWMA). 만회 시나리오 chip 은 active 강조 (recoveryActive=true 가 자동 적용)
- [ ] § 3 자연어 2번째 줄 "AI 권고 적용 시 ..." 도 노출 (recoveryActive 가 true 이므로)
- [ ] § 4 Quadrant + OptimizerResult + RecoveryEtaCard — WP 클릭 시 차트 위 "선택된 WP" 라벨 갱신
- [ ] § 5 collapsible. 펼치면 WPSummaryTable (6 행) + RawDataTab. § 4 의 selectedWpId 가 WPSummaryTable 의 선택 row + RawDataTab 의 wp 필터 모두 동기화
- [ ] § 5 WPSummary 행 클릭 → § 4 산점도 점도 동기 강조 (양방향)
- [ ] 다른 페이지 회귀 — `/` `/home` `/tasks` `/review` `/dashboard` 정상

- [ ] **Step 4: push**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git push origin B_Track
```

- [ ] **Step 5: PR 생성**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
gh pr create --base main --head B_Track \
  --title "feat(B v2): /reports 5 섹션 인과 흐름 — 결론·현재·추세·이슈+권고·원본" \
  --body "$(cat <<'EOF'
## Summary

spec v2 (`docs/superpowers/specs/2026-05-17-cpia-report-redesign-design.md`) 의 5 섹션 inverted-pyramid 흐름. PR #20 의 6 섹션 \"분석 도구 패널\" 구조를 임원 의사결정 흐름에 맞춰 재정의.

- § 1 결론 (KPI 4) — 아래 도출 결과 요약
- § 2 현재 상태 (BarChartH 업체·공종) — KPI #1·#2 의 근거
- § 3 Forecasting (신규 ForecastChart) — 4 default layer + 3 toggle chip + 자연어 1줄, § 4 클릭 시 만회 곡선 추가
- § 4 이슈 + 권고 (4분면 + Optimizer + RecoveryEtaCard 한 row) — Forecasting → Optimizer 브릿지
- § 5 원본 (WPSummaryTable + RawDataTab stack) — WP 단위 시작·종료·진척·생산성 + 작업일보 상세 자동 필터

신규: ForecastChart, WPSummaryTable, WPSummaryRow 타입, mock_report.json wp_summary 6 행.
SpiBandChart 는 /reports 에서 사용 안 함 (후속 화면 재사용 가능).

## Test plan
- [x] vitest 34 pass
- [x] next build 13 routes
- [ ] /reports 5 섹션 시각 회귀
- [ ] § 4 WP 클릭 → § 3 만회 곡선 + § 5 WPSummary/RawData 동기화
EOF
)"
```

---

## 검증 요약

각 task 끝날 때마다:
1. `npx tsc --noEmit` — 0 errors
2. `npx vitest run` — 회귀 없음 (34 tests)
3. Task 6 부터 `npx next build` — 13 routes 정상
4. Task 7 에서 dev 서버 시각 검증

## 후속 plan 후보

1. **`detail.optimizer` WP 별 분리** — WP 클릭 시 실제 권고 전환
2. **(C) /dashboard 6 현장 카드 보강**
3. **(D) /home /tasks 단계별 결과**
4. **차트 color 토큰화** (SpiBandChart · ForecastChart 의 hex 8개)
5. **모바일 DailyList collapse 패턴**
