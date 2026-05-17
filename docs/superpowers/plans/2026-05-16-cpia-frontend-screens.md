# CPIA Frontend 5 화면 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** spec 2026-05-16-cpia-frontend-screens-design.md 에 합의된 5 화면(Home / Agent Tasks / Human Review / Report / Dashboard) + 페르소나 토글 + scripted simulation 을 `web/` 디렉토리에 구현하여 영상 시연용 PoC 프론트엔드를 완성한다. Phase 1 (mock fixture 단독 모드)로 A_Track 대기 없이 빠르게 시각 피드백 가능한 상태까지 도달.

**Architecture:**
- Next.js 14 App Router · TypeScript · Tailwind · shadcn/ui · lucide-react · recharts
- 페르소나 상태는 Zustand store (구성원/관리자 토글)
- 데이터는 `data/mock_*.json` fixture (project root) + `web/lib/fixtures.ts` 로더
- 시뮬레이션은 클라이언트 사이드 `useSimulation` hook (`setInterval` 기반, 백엔드 polling 없음)
- 모든 시각 토큰·컴포넌트 패턴은 `docs/ui/design-system.md` 단일 출처

**Tech Stack:**
- Existing: Next.js 14.2.35, React 18, TypeScript 5, Tailwind 3.4, shadcn (button/card/badge/separator), lucide-react
- Add: shadcn `dialog`/`sheet`/`tabs`/`switch`/`sonner`, recharts (차트), zustand (페르소나 store), `@dnd-kit/core` (Human Review 드래그앤드롭), vitest + @testing-library/react (테스트)

---

## File Structure

새로 생성되거나 수정되는 파일 매핑. Task 분해는 이 구조를 따른다.

### 새로 생성

```
web/
├── app/
│   ├── page.tsx                      ← (수정) 새 Home 컨텐츠로 교체
│   ├── tasks/page.tsx                ← (신규) Agent Tasks
│   ├── review/page.tsx               ← (신규) Human Review
│   ├── reports/page.tsx              ← (신규) Report
│   ├── dashboard/
│   │   ├── page.tsx                  ← (신규) 전사 Dashboard (기존 Layer 1 코드 이동·발전)
│   │   └── sites/[id]/page.tsx       ← (신규) 현장 드릴다운
│   ├── components/
│   │   ├── TopBar.tsx                ← (신규) 페르소나 토글 + 브랜드
│   │   ├── Sidebar.tsx               ← (신규) 5 메뉴 + 페르소나별 필터
│   │   ├── PersonaToggle.tsx         ← (신규) 구성원/관리자 switch
│   │   ├── home/
│   │   │   ├── Hero.tsx              ← (신규) Hero strip
│   │   │   ├── NowStrip.tsx          ← (신규) 시뮬 live strip
│   │   │   ├── AgentCard.tsx         ← (신규) 7-Agent 카드 1개 단위
│   │   │   └── HilReviewStage.tsx    ← (신규) HIL Review 단계 카드
│   │   ├── tasks/
│   │   │   ├── DailyRunList.tsx
│   │   │   ├── AgentProgressList.tsx
│   │   │   └── AgentChatLog.tsx
│   │   ├── review/
│   │   │   ├── WBSTree.tsx
│   │   │   ├── ReviewCard.tsx
│   │   │   └── WPSearchCombobox.tsx
│   │   ├── reports/
│   │   │   ├── ReportDailyList.tsx
│   │   │   ├── KpiStrip.tsx
│   │   │   ├── ForecastTab.tsx
│   │   │   ├── OptimizeTab.tsx
│   │   │   ├── OptimizerResult.tsx
│   │   │   ├── QuadrantCountKpi.tsx
│   │   │   └── RawDataTab.tsx
│   │   ├── dashboard/
│   │   │   ├── PerformanceTab.tsx
│   │   │   ├── ImpactTab.tsx
│   │   │   ├── SiteOverviewCard.tsx
│   │   │   └── HorizontalBarList.tsx
│   │   └── charts/
│   │       ├── SCurveChart.tsx
│   │       ├── BarChartH.tsx
│   │       ├── QuadrantScatter.tsx
│   │       └── TrendLineChart.tsx
├── lib/
│   ├── persona.ts                    ← (신규) Zustand store
│   ├── fixtures.ts                   ← (신규) JSON 로더 (server-only)
│   ├── types.ts                      ← (신규) 공유 TypeScript types
│   └── use-simulation.ts             ← (신규) 시뮬레이션 hook
├── components/ui/                    ← (수정) shadcn 추가
│   ├── dialog.tsx
│   ├── sheet.tsx
│   ├── tabs.tsx
│   ├── switch.tsx
│   └── sonner.tsx
├── tests/
│   ├── use-simulation.test.ts        ← (신규) Vitest unit test
│   └── fixtures.test.ts              ← (신규) Vitest unit test
├── vitest.config.ts                  ← (신규)
└── package.json                      ← (수정) deps 추가

data/                                 ← (project root)
├── mock_sites.json                   ← 기존
├── mock_sites_summary.json           ← (신규)
├── mock_agent_status.json            ← (신규)
├── mock_agent_tasks.json             ← (신규)
├── mock_chat_sequence.json           ← (신규)
├── mock_review_cards.json            ← (신규)
├── mock_wbs_tree.json                ← (신규)
├── mock_report.json                  ← (신규)
├── mock_dashboard.json               ← (신규)
└── mock_simulation.json              ← (신규)

docs/ui/design-system.md              ← (수정) §3-2·§3-3·§9에 신규 컴포넌트·차트 등록
```

### 기존 파일 변경

- `web/app/page.tsx` — 기존 Layer 1 코드는 `web/app/dashboard/page.tsx`로 이동 후, 새 Home 컨텐츠로 재작성
- `web/app/layout.tsx` — TopBar + Sidebar 통합한 새 layout
- `web/app/components/SiteCard.tsx` — Dashboard 전사 카드용으로 확장 (mini S-curve 추가)
- `web/package.json` — 의존성 추가
- `docs/ui/design-system.md` — §9 "다음 세션 작업할 곳" 갱신, 신규 컴포넌트 등록

---

## Conventions

- **TDD 적용 범위:** 비-시각 로직(`use-simulation.ts`, `fixtures.ts`, `persona.ts`)은 Vitest 단위 테스트. 시각 컴포넌트는 dev 서버 시각 review (사용자가 직접 확인)
- **Component 패턴:** 모두 `<Card>`/`<Badge>`/`cn()` 등 design-system 토큰 사용. raw `<div className="bg-red-500">` 금지
- **Commit 단위:** 각 Task 끝에 1 commit (`feat(B): <topic>` 또는 `chore(B): <topic>`)
- **Dev 서버:** `cd web && npm run dev` → `http://127.0.0.1:5535`. 시각 review 시점마다 켜진 상태 가정

---

## Phase 0 — Project Setup (Task 1~5)

### Task 1: 의존성 추가 + shadcn 컴포넌트 install

**Files:**
- Modify: `web/package.json`
- Create: `web/components/ui/dialog.tsx`, `web/components/ui/sheet.tsx`, `web/components/ui/tabs.tsx`, `web/components/ui/switch.tsx`, `web/components/ui/sonner.tsx`

- [ ] **Step 1: 의존성 install (recharts·zustand·dnd-kit·sonner)**

```bash
cd web
npm install recharts zustand @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities sonner
```

- [ ] **Step 2: shadcn 컴포넌트 5종 add**

```bash
cd web
npx shadcn@latest add dialog sheet tabs switch sonner
```

- [ ] **Step 3: 설치 확인**

Run: `cd web && cat package.json | grep -E "recharts|zustand|dnd-kit|sonner"`
Expected: 4개 패키지 모두 `dependencies`에 있음

Run: `cd web && ls components/ui/`
Expected: `badge.tsx button.tsx card.tsx dialog.tsx separator.tsx sheet.tsx sonner.tsx switch.tsx tabs.tsx`

- [ ] **Step 4: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/package.json web/package-lock.json web/components/ui/
git commit -m "$(cat <<'EOF'
chore(B): 의존성 추가 — recharts·zustand·dnd-kit·sonner + shadcn dialog/sheet/tabs/switch

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Vitest 셋업

**Files:**
- Create: `web/vitest.config.ts`
- Modify: `web/package.json` (script + devDependencies)

- [ ] **Step 1: Vitest devDependency install**

```bash
cd web
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom @vitejs/plugin-react
```

- [ ] **Step 2: `vitest.config.ts` 작성**

Create `web/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./"),
    },
  },
});
```

- [ ] **Step 3: package.json scripts 추가**

Modify `web/package.json` `scripts`:
```json
{
  "scripts": {
    "dev": "next dev -H 127.0.0.1 -p 5535",
    "build": "next build",
    "start": "next start -H 127.0.0.1 -p 5535",
    "lint": "next lint",
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

- [ ] **Step 4: 동작 확인 (빈 테스트)**

Create `web/tests/sanity.test.ts`:
```ts
import { describe, it, expect } from "vitest";

describe("sanity", () => {
  it("1 + 1 = 2", () => {
    expect(1 + 1).toBe(2);
  });
});
```

Run: `cd web && npm test`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/vitest.config.ts web/package.json web/package-lock.json web/tests/sanity.test.ts
git commit -m "$(cat <<'EOF'
chore(B): Vitest + RTL 셋업

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 공유 TypeScript types 정의

**Files:**
- Create: `web/lib/types.ts`

- [ ] **Step 1: `lib/types.ts` 작성**

```ts
// web/lib/types.ts
// 모든 5 화면에서 공유하는 도메인 타입.
// fixture JSON 의 shape 과 1:1 매칭. A_Track API 응답 shape 과도 일치.

export type Status = "normal" | "caution" | "risk" | "unknown";
export type Persona = "member" | "manager";

// ────── Sites (Dashboard / Home Hero) ──────
export interface Site {
  id: string;
  name: string;
  location: string;
  status: Status;
  progress_planned: number;     // 계획 공정률 %
  progress_actual: number;      // 실적 공정률 %
  gap_percent: number;          // 격차 %p
  productivity_today: number;   // 오늘 생산성 %
  spi: number;                  // SPI 지수
  abnormal_trades: number;      // 이상 공종 수
  fte_saved: number;            // 확보 FTE
  hours_saved: number;          // 월 절감 시간
  headcount: number;            // 현장 전체 근무 인원 (Impact 분모)
  total_hours: number;          // 현장 전체 근무 h/월 (headcount × 140)
  ai_replacement_rate: number;  // AI 업무 대체율 (hours_saved / total_hours)
  expected_completion: string;  // 현 추세 완료일 ISO date
  recovered_completion: string; // 최적화 후 완료일 ISO date
  delay_days: number;           // 지연 일수
  recovery_days: number;        // 회복 가능 일수
}

// ────── Home NOW strip + Hero ──────
export interface SitesSummary {
  today_count: number;          // 오늘 처리 87건
  review_pending: number;       // Review 대기 2건
  abnormal_count: number;       // 이상 1건
  last_updated: string;         // "09:12"
  total_hours_saved: number;    // 2155
  total_fte_saved: number;      // 15.4
  total_headcount: number;      // 480
  total_hours: number;          // 67200
  ai_replacement_rate: number;  // 3.2
  yearly_saving: number;        // 203 (억)
}

// ────── 7-Agent 카드 status (Home) ──────
export interface AgentStatus {
  step: number;                 // 1..7
  name: string;                 // "Collector"
  korean_name: string;          // "수집"
  description: string;          // "작업일보 자동 수집"
  model: string;                // "규칙 기반" | "Sonnet 4.6" | "Opus 4.7" | "임베딩 모델"
  group: "collect" | "analyze"; // sky | lavender
  active_count: number;         // 시뮬 base 값
  state: "processing" | "waiting" | "idle";
}

// ────── Agent Tasks ──────
export interface DailyRun {
  date: string;                 // "2026-05-15"
  total_count: number;          // 87
  status: "running" | "completed" | "review_pending";
  has_anomaly: boolean;
  bar_value: number;            // 0..1 (mini bar 비율)
}

export interface AgentProgress {
  agent: string;                // "Collector" | "Parser" | "Mapper" | "HIL Review" | "Atomizer" | "Reporter" | "Forecaster" | "Optimizer"
  unit: "per_report" | "per_review" | "per_run";
  processed: number;
  total: number;
  waiting_hil: boolean;
}

export interface ChatMessage {
  ts: string;                   // "09:01:18"
  agent: string;
  type: "info" | "hil_request" | "human_action" | "result";
  summary: string;              // 자연어 1줄
  detail?: string;              // 자연어 보충 2~3줄
}

// ────── Human Review ──────
export interface WBSNode {
  id: string;
  type: "building" | "trade" | "work_package";
  name: string;
  parent_id: string | null;
  review_count: number;         // 검토 필요 건수 (집계)
  status: Status;
  children?: WBSNode[];
}

export interface ReviewItem {
  id: string;
  bp_name: string;              // "A건설"
  work_content: string;         // 작업내용 원문
  quantity: number;
  unit: string;                 // "㎡" | "ton" | "m³" | "EA"
  ai_mapped_wp_id: string;      // 매핑된 WP id
  ai_mapped_path: string;       // "M15X > 골조 > WP-3-2 거푸집"
  confidence: number;           // 0.0~1.0
  status: "confirmed" | "unconfirmed";
  alternative_wps?: { id: string; path: string; score: number }[];
}

// ────── Report ──────
export interface ReportDaily {
  date: string;
  status: Status;
  productivity_today: number;
  delay_days: number;
  recovery_days: number;
}

export interface ReportKpi {
  productivity_today: number;       // 88
  productivity_history_diff: number; // -12 (이력 대비)
  delay_days: number;                // 14
  expected_completion: string;       // 2026-08-12
  recoverable_productivity: number;  // 9 (%p)
  target_productivity: number;       // 97
  recovery_days: number;             // 9
  recovered_completion: string;      // 2026-08-03
}

export interface SCurvePoint {
  date: string;
  planned: number;          // 계획 누적 %
  actual?: number;          // 실적 누적 % (오늘까지)
  forecast?: number;        // 예측선 (오늘 이후)
  recovery?: number;        // 만회선 (Optimizer 시나리오)
}

export interface BarItem {
  label: string;            // BP사명 또는 공종명
  value: number;            // 생산성 %
  status: Status;
}

export interface QuadrantPoint {
  wp_id: string;
  wp_name: string;
  trade: string;
  productivity: number;     // 0..100 (X축)
  impact: number;           // 0..100 (Y축)
  quadrant: "risk" | "caution" | "watch" | "safe";
  size: number;             // 잔여 물량 비례
}

export interface OptimizerOutput {
  wp_id: string;
  diagnosis: string;                              // 진단 (자연어)
  similar_cases: { date: string; description: string; outcome: string }[];
  recommendations: string[];                      // 권고사항 (배열)
  details: { label: string; value: string }[];   // 상세 현황 (key-value)
}

export interface RawDataRow {
  building: string;
  trade: string;
  wp: string;
  bp_name: string;
  work_content: string;
  quantity: number;
  unit: string;
  workers: number;
  equipment: string;
}

// ────── Dashboard Impact ──────
export interface ImpactSiteDistribution {
  site_id: string;
  site_name: string;
  hours_saved: number;
  fte_saved: number;
}

export interface ImpactTrendPoint {
  month: string;       // "2026-01"
  cumulative_fte: number;
}

export interface MiddleOfficeAutomation {
  function: string;     // "Data Stewardship" | "P&L Reporting" | "Risk Management" | "Deal Support"
  rate: number;         // 0..100
  before_hours: number;
  after_hours: number;
}

// ────── Simulation ──────
export interface SimulationSequence {
  home_now_strip: { interval_ms: number; variance: number }[];
  agent_card_status: Record<string, number[]>; // agent name → values array
  chat_log: ChatMessage[];                     // sequenced reveals
}
```

- [ ] **Step 2: TypeScript 컴파일 확인**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add web/lib/types.ts
git commit -m "$(cat <<'EOF'
feat(B): 공유 TypeScript types — 5 화면 + Dashboard + 시뮬레이션 도메인 정의

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Persona Zustand store

**Files:**
- Create: `web/lib/persona.ts`

- [ ] **Step 1: Persona store 작성**

Create `web/lib/persona.ts`:
```ts
"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Persona } from "./types";

interface PersonaState {
  persona: Persona;
  setPersona: (p: Persona) => void;
  toggle: () => void;
}

export const usePersona = create<PersonaState>()(
  persist(
    (set, get) => ({
      persona: "member",
      setPersona: (p) => set({ persona: p }),
      toggle: () => set({ persona: get().persona === "member" ? "manager" : "member" }),
    }),
    { name: "cpia-persona" }
  )
);

// 페르소나별 메뉴 노출 정책
export const MENU_VISIBILITY: Record<Persona, readonly string[]> = {
  member: ["home", "tasks", "review", "reports"],
  manager: ["home", "tasks", "review", "reports", "dashboard"],
} as const;

export function isMenuVisible(persona: Persona, menu: string): boolean {
  return MENU_VISIBILITY[persona].includes(menu);
}
```

- [ ] **Step 2: 단위 테스트 작성**

Create `web/tests/persona.test.ts`:
```ts
import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { usePersona, isMenuVisible } from "@/lib/persona";

describe("persona store", () => {
  beforeEach(() => {
    usePersona.setState({ persona: "member" });
  });

  it("default is member", () => {
    const { result } = renderHook(() => usePersona());
    expect(result.current.persona).toBe("member");
  });

  it("toggle swaps persona", () => {
    const { result } = renderHook(() => usePersona());
    act(() => result.current.toggle());
    expect(result.current.persona).toBe("manager");
    act(() => result.current.toggle());
    expect(result.current.persona).toBe("member");
  });

  it("setPersona sets directly", () => {
    const { result } = renderHook(() => usePersona());
    act(() => result.current.setPersona("manager"));
    expect(result.current.persona).toBe("manager");
  });
});

describe("menu visibility", () => {
  it("member sees 4 menus, no dashboard", () => {
    expect(isMenuVisible("member", "home")).toBe(true);
    expect(isMenuVisible("member", "tasks")).toBe(true);
    expect(isMenuVisible("member", "review")).toBe(true);
    expect(isMenuVisible("member", "reports")).toBe(true);
    expect(isMenuVisible("member", "dashboard")).toBe(false);
  });

  it("manager sees all 5 menus", () => {
    expect(isMenuVisible("manager", "dashboard")).toBe(true);
    expect(isMenuVisible("manager", "home")).toBe(true);
  });
});
```

- [ ] **Step 3: 테스트 실행**

Run: `cd web && npm test -- persona`
Expected: `5 passed`

- [ ] **Step 4: Commit**

```bash
git add web/lib/persona.ts web/tests/persona.test.ts
git commit -m "$(cat <<'EOF'
feat(B): 페르소나 Zustand store + 메뉴 노출 정책 (구성원 4 / 관리자 5)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: useSimulation hook (TDD)

**Files:**
- Create: `web/lib/use-simulation.ts`
- Create: `web/tests/use-simulation.test.ts`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `web/tests/use-simulation.test.ts`:
```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSimulation, useSequence } from "@/lib/use-simulation";

describe("useSimulation", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("returns initial seed value", () => {
    const { result } = renderHook(() => useSimulation(10, (n) => n + 1, 1000));
    expect(result.current).toBe(10);
  });

  it("updates on interval", () => {
    const { result } = renderHook(() => useSimulation(10, (n) => n + 1, 1000));
    act(() => { vi.advanceTimersByTime(1000); });
    expect(result.current).toBe(11);
    act(() => { vi.advanceTimersByTime(2000); });
    expect(result.current).toBe(13);
  });

  it("cleans up on unmount", () => {
    const { result, unmount } = renderHook(() => useSimulation(10, (n) => n + 1, 1000));
    unmount();
    act(() => { vi.advanceTimersByTime(5000); });
    // Initial value unchanged (test passes if no error from setState after unmount)
    expect(result.current).toBe(10);
  });
});

describe("useSequence", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("reveals items one by one", () => {
    const seq = ["a", "b", "c"];
    const { result } = renderHook(() => useSequence(seq, 1000));
    expect(result.current).toEqual([]);

    act(() => { vi.advanceTimersByTime(1000); });
    expect(result.current).toEqual(["a"]);

    act(() => { vi.advanceTimersByTime(1000); });
    expect(result.current).toEqual(["a", "b"]);

    act(() => { vi.advanceTimersByTime(1000); });
    expect(result.current).toEqual(["a", "b", "c"]);
  });

  it("stops at end of sequence", () => {
    const seq = ["a"];
    const { result } = renderHook(() => useSequence(seq, 1000));
    act(() => { vi.advanceTimersByTime(5000); });
    expect(result.current).toEqual(["a"]);
  });
});
```

- [ ] **Step 2: Run test — should FAIL**

Run: `cd web && npm test -- use-simulation`
Expected: FAIL (module not found)

- [ ] **Step 3: Implementation 작성**

Create `web/lib/use-simulation.ts`:
```ts
"use client";
import { useEffect, useState } from "react";

/**
 * Periodic transformation of a seed value.
 * Updates `value` every `intervalMs` ms by applying `updater(prev)`.
 *
 * Use for: counters that drift up/down (Home NOW strip "오늘 N건"),
 *          status that changes with time (Agent card processing count).
 */
export function useSimulation<T>(
  seed: T,
  updater: (prev: T) => T,
  intervalMs: number
): T {
  const [value, setValue] = useState(seed);
  useEffect(() => {
    const id = setInterval(() => setValue((p) => updater(p)), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, updater]);
  return value;
}

/**
 * Sequential reveal: incrementally exposes more items from `seq` over time.
 * After `intervalMs` ms, `revealed` has 1 item; after 2*intervalMs, 2 items; etc.
 *
 * Use for: Agent Tasks chat log new-message push,
 *          Forecast S-curve point-by-point reveal.
 */
export function useSequence<T>(seq: readonly T[], intervalMs: number): T[] {
  const [revealed, setRevealed] = useState<T[]>([]);
  useEffect(() => {
    setRevealed([]);
    if (seq.length === 0) return;
    let i = 0;
    const id = setInterval(() => {
      if (i >= seq.length) {
        clearInterval(id);
        return;
      }
      setRevealed((prev) => [...prev, seq[i]]);
      i++;
    }, intervalMs);
    return () => clearInterval(id);
  }, [seq, intervalMs]);
  return revealed;
}
```

- [ ] **Step 4: Run test — should PASS**

Run: `cd web && npm test -- use-simulation`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add web/lib/use-simulation.ts web/tests/use-simulation.test.ts
git commit -m "$(cat <<'EOF'
feat(B): useSimulation + useSequence hooks — 클라이언트 사이드 scripted simulation 기반

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 1 — Mock Fixtures (Task 6~10)

> **사용자 1순위 요청:** *"우선 데이터가 없더라도 그럴듯한 데이터로 채워놔주면 좋을것 같아"* — 이 Phase에서 그럴듯한 fixture를 박아 빠른 시각 피드백 가능 상태로.
>
> 모든 fixture 는 `data/mock_*.json`에 작성. `web/lib/fixtures.ts` 가 server-only loader 역할.
> 수치 일관성 원칙: 한 fixture 세트 안에서 `hours_saved / 140 = fte_saved`, `hours_saved / total_hours = ai_replacement_rate` 등 산수 맞물려야 함.

### Task 6: fixtures.ts 로더 (TDD)

**Files:**
- Create: `web/lib/fixtures.ts`
- Create: `web/tests/fixtures.test.ts`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `web/tests/fixtures.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { loadFixture } from "@/lib/fixtures";

describe("loadFixture", () => {
  it("loads existing mock_sites.json", async () => {
    const sites = await loadFixture("sites");
    expect(Array.isArray(sites)).toBe(true);
    expect(sites.length).toBeGreaterThan(0);
  });

  it("throws on missing fixture", async () => {
    await expect(loadFixture("nonexistent" as any)).rejects.toThrow();
  });
});
```

- [ ] **Step 2: Run test — FAIL**

Run: `cd web && npm test -- fixtures`
Expected: FAIL (module not found)

- [ ] **Step 3: Implementation**

Create `web/lib/fixtures.ts`:
```ts
import { promises as fs } from "fs";
import path from "path";
import type {
  Site, SitesSummary, AgentStatus, DailyRun, AgentProgress, ChatMessage,
  WBSNode, ReviewItem, ReportDaily, ReportKpi, SCurvePoint, BarItem,
  QuadrantPoint, OptimizerOutput, RawDataRow,
  ImpactSiteDistribution, ImpactTrendPoint, MiddleOfficeAutomation,
  SimulationSequence,
} from "./types";

/**
 * Map of fixture name → expected return type.
 * Phase 2 전환 시 이 매핑을 그대로 두고 fetch 레이어만 swap.
 */
type FixtureMap = {
  sites: Site[];
  sites_summary: SitesSummary;
  agent_status: AgentStatus[];
  agent_tasks: { daily_runs: DailyRun[]; progress_by_date: Record<string, AgentProgress[]> };
  chat_sequence: Record<string, ChatMessage[]>;  // keyed by date
  review_cards: ReviewItem[];
  wbs_tree: WBSNode;
  report: { daily: ReportDaily[]; details: Record<string, ReportDetail> };
  dashboard: DashboardFixture;
  simulation: SimulationSequence;
};

export interface ReportDetail {
  kpi: ReportKpi;
  s_curve: SCurvePoint[];
  contractor_bars: BarItem[];
  trade_bars: BarItem[];
  quadrant: QuadrantPoint[];
  optimizer: OptimizerOutput;
  raw_data: RawDataRow[];
}

export interface DashboardFixture {
  performance: { fleet_kpi: { avg_productivity: number; avg_delay: number; abnormal_total: number; recoverable_days: number; } };
  impact: {
    fleet_kpi: SitesSummary;
    site_distribution: ImpactSiteDistribution[];
    monthly_trend: ImpactTrendPoint[];
    per_site_automation: Record<string, MiddleOfficeAutomation[]>;
  };
}

const DATA_DIR = path.join(process.cwd(), "..", "data");

export async function loadFixture<K extends keyof FixtureMap>(name: K): Promise<FixtureMap[K]> {
  const file = path.join(DATA_DIR, `mock_${name}.json`);
  const raw = await fs.readFile(file, "utf-8");
  return JSON.parse(raw) as FixtureMap[K];
}
```

- [ ] **Step 4: Run test — PASS (1번째 케이스만)**

Run: `cd web && npm test -- fixtures`
Expected: 1 passed (sites), 1 fail (nonexistent — expected behavior)

- [ ] **Step 5: Commit**

```bash
git add web/lib/fixtures.ts web/tests/fixtures.test.ts
git commit -m "$(cat <<'EOF'
feat(B): fixtures.ts 로더 — server-only JSON 로드, A_Track 전환 시 swap 포인트

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Sites fixture 보강 + sites_summary 작성

**Files:**
- Modify: `data/mock_sites.json` (6 현장에 spec §9-3 필드 추가)
- Create: `data/mock_sites_summary.json`

- [ ] **Step 1: 기존 `data/mock_sites.json` 읽기**

Run: `cat "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project/data/mock_sites.json" | head -40`
→ 기존 구조 파악 후 필드 추가 (id/name/location/status 등은 이미 있을 것)

- [ ] **Step 2: 6 현장 데이터 spec §9-3 표에 맞춰 보강**

Replace `data/mock_sites.json` 내용을 다음과 일치하도록 작성 (기존 필드는 유지하면서 spec 필드 추가):

```json
[
  {
    "id": "m15x-ph3-ibl",
    "name": "M15X Ph-3 IBL",
    "location": "청주",
    "status": "risk",
    "progress_planned": 38.5,
    "progress_actual": 34.2,
    "gap_percent": -4.3,
    "productivity_today": 88,
    "spi": 0.89,
    "abnormal_trades": 1,
    "fte_saved": 1.6,
    "hours_saved": 221,
    "headcount": 65,
    "total_hours": 9100,
    "ai_replacement_rate": 2.4,
    "expected_completion": "2026-08-12",
    "recovered_completion": "2026-08-03",
    "delay_days": 14,
    "recovery_days": 9
  },
  {
    "id": "y1-ph1-obl",
    "name": "Y-1 Ph-1 OBL",
    "location": "평택",
    "status": "normal",
    "progress_planned": 62.1,
    "progress_actual": 62.5,
    "gap_percent": 0.4,
    "productivity_today": 96,
    "spi": 1.01,
    "abnormal_trades": 0,
    "fte_saved": 5.9,
    "hours_saved": 832,
    "headcount": 130,
    "total_hours": 18200,
    "ai_replacement_rate": 4.6,
    "expected_completion": "2026-09-04",
    "recovered_completion": "2026-09-04",
    "delay_days": 0,
    "recovery_days": 0
  },
  {
    "id": "indiana-hac",
    "name": "Indiana Fab HAC",
    "location": "미국",
    "status": "normal",
    "progress_planned": 48.7,
    "progress_actual": 48.6,
    "gap_percent": -0.1,
    "productivity_today": 94,
    "spi": 0.99,
    "abnormal_trades": 0,
    "fte_saved": 2.5,
    "hours_saved": 353,
    "headcount": 60,
    "total_hours": 8400,
    "ai_replacement_rate": 4.2,
    "expected_completion": "2026-10-15",
    "recovered_completion": "2026-10-15",
    "delay_days": 0,
    "recovery_days": 0
  },
  {
    "id": "pt3-extension",
    "name": "P&T 3 증축",
    "location": "이천",
    "status": "normal",
    "progress_planned": 71.4,
    "progress_actual": 72.6,
    "gap_percent": 1.2,
    "productivity_today": 102,
    "spi": 1.03,
    "abnormal_trades": 0,
    "fte_saved": 1.8,
    "hours_saved": 255,
    "headcount": 50,
    "total_hours": 7000,
    "ai_replacement_rate": 3.6,
    "expected_completion": "2026-07-22",
    "recovered_completion": "2026-07-22",
    "delay_days": 0,
    "recovery_days": 0
  },
  {
    "id": "m15x-obl-pt7",
    "name": "M15X OBL & PT7",
    "location": "청주",
    "status": "normal",
    "progress_planned": 22.8,
    "progress_actual": 22.5,
    "gap_percent": -0.3,
    "productivity_today": 95,
    "spi": 0.99,
    "abnormal_trades": 0,
    "fte_saved": 1.7,
    "hours_saved": 246,
    "headcount": 50,
    "total_hours": 7000,
    "ai_replacement_rate": 3.5,
    "expected_completion": "2026-12-10",
    "recovered_completion": "2026-12-10",
    "delay_days": 0,
    "recovery_days": 0
  },
  {
    "id": "y1-ph1-ibl",
    "name": "Y-1 Ph-1 IBL",
    "location": "평택",
    "status": "normal",
    "progress_planned": 55.6,
    "progress_actual": 55.8,
    "gap_percent": 0.2,
    "productivity_today": 98,
    "spi": 1.00,
    "abnormal_trades": 0,
    "fte_saved": 1.8,
    "hours_saved": 248,
    "headcount": 90,
    "total_hours": 12600,
    "ai_replacement_rate": 2.0,
    "expected_completion": "2026-09-28",
    "recovered_completion": "2026-09-28",
    "delay_days": 0,
    "recovery_days": 0
  }
]
```

- [ ] **Step 3: sites_summary 작성 (전사 집계)**

Create `data/mock_sites_summary.json`:
```json
{
  "today_count": 87,
  "review_pending": 12,
  "abnormal_count": 1,
  "last_updated": "09:12",
  "total_hours_saved": 2155,
  "total_fte_saved": 15.4,
  "total_headcount": 480,
  "total_hours": 67200,
  "ai_replacement_rate": 3.2,
  "yearly_saving": 203
}
```

- [ ] **Step 4: 산수 검증**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
# headcount 합산: 65+130+60+50+50+90 = 445 (spec은 약 480 — 가정치 약간 조정 또는 그대로 둠)
# hours_saved 합산: 221+832+353+255+246+248 = 2155 ✓
# fte_saved 합산: 1.6+5.9+2.5+1.8+1.7+1.8 = 15.3 (≈ 15.4 ✓)
```

> 합산 headcount(445) vs sites_summary(480)에 차이가 있으면 sites_summary의 `total_headcount`를 합산값(445)로 맞추고 `total_hours = 445×140 = 62,300`, `ai_replacement_rate = 2155/62300 = 3.46%` 로 재계산해서 일관성 유지. **또는** 6 현장 외 미반영 인원이 있다고 가정하고 sites_summary 그대로 유지 (현실적 시연용 fixture라서 약간의 여유 OK).

이 plan에서는 **합산 일치** 방향으로 가서 검증 가능성 ↑. sites_summary 값 수정:

Update `data/mock_sites_summary.json`:
```json
{
  "today_count": 87,
  "review_pending": 12,
  "abnormal_count": 1,
  "last_updated": "09:12",
  "total_hours_saved": 2155,
  "total_fte_saved": 15.4,
  "total_headcount": 445,
  "total_hours": 62300,
  "ai_replacement_rate": 3.46,
  "yearly_saving": 203
}
```

- [ ] **Step 5: Commit**

```bash
git add data/mock_sites.json data/mock_sites_summary.json
git commit -m "$(cat <<'EOF'
feat(B): fixture — sites 6 현장 보강(spec §9-3 필드 추가) + sites_summary 전사 집계

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Agent status + Agent tasks fixture

**Files:**
- Create: `data/mock_agent_status.json`
- Create: `data/mock_agent_tasks.json`

- [ ] **Step 1: agent_status 작성 (Home 7-Agent 카드)**

Create `data/mock_agent_status.json`:
```json
[
  { "step": 1, "name": "Collector", "korean_name": "수집", "description": "작업일보 파일 자동 수집", "model": "규칙 기반", "group": "collect", "active_count": 3, "state": "processing" },
  { "step": 2, "name": "Parser", "korean_name": "파싱", "description": "비정형 텍스트 → 구조화 JSON 변환", "model": "Sonnet 4.6", "group": "collect", "active_count": 2, "state": "waiting" },
  { "step": 3, "name": "Mapper", "korean_name": "매핑", "description": "WBS Work Package 의미 기반 매핑", "model": "Sonnet 4.6", "group": "collect", "active_count": 1, "state": "waiting" },
  { "step": 4, "name": "Atomizer", "korean_name": "DB 적재", "description": "Vector DB 임베딩 적재", "model": "임베딩 모델", "group": "collect", "active_count": 0, "state": "idle" },
  { "step": 5, "name": "Reporter", "korean_name": "보고", "description": "Daily 보고서 자동 생성·발송", "model": "Sonnet 4.6", "group": "analyze", "active_count": 0, "state": "idle" },
  { "step": 6, "name": "Forecaster", "korean_name": "진단", "description": "과거 이력 대비 생산성 진단·이상 원인 추론", "model": "Opus 4.7", "group": "analyze", "active_count": 0, "state": "idle" },
  { "step": 7, "name": "Optimizer", "korean_name": "최적화", "description": "Vector RAG 기반 만회 시나리오·권고", "model": "Opus 4.7", "group": "analyze", "active_count": 0, "state": "idle" }
]
```

- [ ] **Step 2: agent_tasks 작성 (Daily 목록 + Process progress)**

Create `data/mock_agent_tasks.json`:
```json
{
  "daily_runs": [
    { "date": "2026-05-15", "total_count": 87, "status": "review_pending", "has_anomaly": true,  "bar_value": 0.91 },
    { "date": "2026-05-14", "total_count": 95, "status": "completed",      "has_anomaly": false, "bar_value": 1.00 },
    { "date": "2026-05-13", "total_count": 82, "status": "completed",      "has_anomaly": false, "bar_value": 0.86 },
    { "date": "2026-05-12", "total_count": 89, "status": "completed",      "has_anomaly": true,  "bar_value": 0.94 },
    { "date": "2026-05-11", "total_count": 78, "status": "completed",      "has_anomaly": false, "bar_value": 0.82 },
    { "date": "2026-05-10", "total_count": 91, "status": "completed",      "has_anomaly": false, "bar_value": 0.96 },
    { "date": "2026-05-09", "total_count": 84, "status": "completed",      "has_anomaly": false, "bar_value": 0.88 }
  ],
  "progress_by_date": {
    "2026-05-15": [
      { "agent": "Collector",  "unit": "per_report", "processed": 87, "total": 87, "waiting_hil": false },
      { "agent": "Parser",     "unit": "per_report", "processed": 87, "total": 87, "waiting_hil": false },
      { "agent": "Mapper",     "unit": "per_report", "processed": 87, "total": 87, "waiting_hil": false },
      { "agent": "HIL Review", "unit": "per_review", "processed": 0,  "total": 12, "waiting_hil": true  },
      { "agent": "Atomizer",   "unit": "per_report", "processed": 0,  "total": 87, "waiting_hil": false },
      { "agent": "Reporter",   "unit": "per_run",    "processed": 0,  "total": 1,  "waiting_hil": false },
      { "agent": "Forecaster", "unit": "per_run",    "processed": 0,  "total": 1,  "waiting_hil": false },
      { "agent": "Optimizer",  "unit": "per_run",    "processed": 0,  "total": 1,  "waiting_hil": false }
    ],
    "2026-05-14": [
      { "agent": "Collector",  "unit": "per_report", "processed": 95, "total": 95, "waiting_hil": false },
      { "agent": "Parser",     "unit": "per_report", "processed": 95, "total": 95, "waiting_hil": false },
      { "agent": "Mapper",     "unit": "per_report", "processed": 95, "total": 95, "waiting_hil": false },
      { "agent": "HIL Review", "unit": "per_review", "processed": 8,  "total": 8,  "waiting_hil": false },
      { "agent": "Atomizer",   "unit": "per_report", "processed": 95, "total": 95, "waiting_hil": false },
      { "agent": "Reporter",   "unit": "per_run",    "processed": 1,  "total": 1,  "waiting_hil": false },
      { "agent": "Forecaster", "unit": "per_run",    "processed": 1,  "total": 1,  "waiting_hil": false },
      { "agent": "Optimizer",  "unit": "per_run",    "processed": 1,  "total": 1,  "waiting_hil": false }
    ]
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add data/mock_agent_status.json data/mock_agent_tasks.json
git commit -m "$(cat <<'EOF'
feat(B): fixture — agent_status (7 Agent) + agent_tasks (Daily run + Process progress)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Chat sequence + Review cards + WBS tree fixtures

**Files:**
- Create: `data/mock_chat_sequence.json`
- Create: `data/mock_review_cards.json`
- Create: `data/mock_wbs_tree.json`

- [ ] **Step 1: chat_sequence 작성 (2026-05-15 시퀀스, 영상 시연용)**

Create `data/mock_chat_sequence.json`:
```json
{
  "2026-05-15": [
    { "ts": "09:00:12", "agent": "Collector", "type": "info",
      "summary": "87건의 작업일보를 수집했습니다.",
      "detail": "Excel 75건 · 텍스트 12건. 모든 BP사 일보가 정상 수신됐어요." },
    { "ts": "09:00:45", "agent": "Parser", "type": "info",
      "summary": "87건 모두 구조화 JSON 변환을 마쳤습니다.",
      "detail": "추출: 인원 1,247명 / 거푸집 3,200㎡ / 철근 18t / 콘크리트 280㎥." },
    { "ts": "09:01:18", "agent": "Mapper", "type": "hil_request",
      "summary": "WBS 매핑을 진행했는데, 12건은 확신도가 낮아 직접 확인이 필요해 보입니다.",
      "detail": "특히 '방수 시트 정리작업' 같은 표현은 두 공종에 걸쳐 있어요. Human Review 요청 ⏸" },
    { "ts": "09:18:34", "agent": "Human", "type": "human_action",
      "summary": "12건 검토를 완료했어요.",
      "detail": "8건은 AI 추천대로 확정, 4건은 다른 WP로 수정했습니다." },
    { "ts": "09:18:40", "agent": "Atomizer", "type": "info",
      "summary": "검토 결과를 반영해 87건 모두 Vector DB에 적재했습니다.",
      "detail": "오늘의 작업 기록이 현장 지식 DB에 추가됐어요." },
    { "ts": "09:19:02", "agent": "Reporter", "type": "result",
      "summary": "Daily Report를 자동 생성하고 발송했습니다.",
      "detail": "사내·발주처용 두 버전 발송 완료. 엑셀 보고서는 다운로드 가능합니다." },
    { "ts": "09:19:48", "agent": "Forecaster", "type": "result",
      "summary": "공종별 생산성을 진단했습니다.",
      "detail": "거푸집·콘크리트는 정상 범위. 철근은 -28% 이상 — 작업내용에 '장비 대기' 기재." },
    { "ts": "09:20:15", "agent": "Optimizer", "type": "result",
      "summary": "철근 공종에 대해 만회 시나리오를 도출했습니다.",
      "detail": "유사 과거 3건 분석 결과 다음날 정상 복귀 가능성 높음. 권고: 타워크레인 스케줄 확인." }
  ]
}
```

- [ ] **Step 2: wbs_tree 작성 (Human Review 좌측 트리)**

Create `data/mock_wbs_tree.json`:
```json
{
  "id": "m15x-ph3-ibl",
  "type": "building",
  "name": "M15X Ph-3 IBL",
  "parent_id": null,
  "review_count": 12,
  "status": "caution",
  "children": [
    {
      "id": "trade-civil",
      "type": "trade",
      "name": "토공사",
      "parent_id": "m15x-ph3-ibl",
      "review_count": 2,
      "status": "caution",
      "children": [
        { "id": "wp-1-1", "type": "work_package", "name": "WP-1-1 터파기", "parent_id": "trade-civil", "review_count": 1, "status": "caution" },
        { "id": "wp-1-2", "type": "work_package", "name": "WP-1-2 되메우기", "parent_id": "trade-civil", "review_count": 1, "status": "caution" }
      ]
    },
    {
      "id": "trade-structure",
      "type": "trade",
      "name": "골조",
      "parent_id": "m15x-ph3-ibl",
      "review_count": 5,
      "status": "caution",
      "children": [
        { "id": "wp-3-2", "type": "work_package", "name": "WP-3-2 거푸집", "parent_id": "trade-structure", "review_count": 3, "status": "caution" },
        { "id": "wp-3-3", "type": "work_package", "name": "WP-3-3 철근",   "parent_id": "trade-structure", "review_count": 2, "status": "risk"    },
        { "id": "wp-3-4", "type": "work_package", "name": "WP-3-4 콘크리트", "parent_id": "trade-structure", "review_count": 0, "status": "normal"  }
      ]
    },
    {
      "id": "trade-finish",
      "type": "trade",
      "name": "마감",
      "parent_id": "m15x-ph3-ibl",
      "review_count": 5,
      "status": "caution",
      "children": [
        { "id": "wp-5-1", "type": "work_package", "name": "WP-5-1 방수",   "parent_id": "trade-finish", "review_count": 2, "status": "caution" },
        { "id": "wp-5-2", "type": "work_package", "name": "WP-5-2 타일",   "parent_id": "trade-finish", "review_count": 1, "status": "caution" },
        { "id": "wp-5-3", "type": "work_package", "name": "WP-5-3 페인트", "parent_id": "trade-finish", "review_count": 2, "status": "caution" }
      ]
    },
    {
      "id": "trade-mep",
      "type": "trade",
      "name": "MEP",
      "parent_id": "m15x-ph3-ibl",
      "review_count": 0,
      "status": "normal",
      "children": [
        { "id": "wp-7-1", "type": "work_package", "name": "WP-7-1 전기", "parent_id": "trade-mep", "review_count": 0, "status": "normal" },
        { "id": "wp-7-2", "type": "work_package", "name": "WP-7-2 배관", "parent_id": "trade-mep", "review_count": 0, "status": "normal" }
      ]
    }
  ]
}
```

- [ ] **Step 3: review_cards 작성 (12 검토 카드, spec §3-3 형식)**

Create `data/mock_review_cards.json`:
```json
[
  { "id": "r-001", "bp_name": "A건설", "work_content": "FAB 2층 벽체 거푸집 설치 / 우천 대응 작업 병행", "quantity": 320, "unit": "㎡", "ai_mapped_wp_id": "wp-3-2", "ai_mapped_path": "M15X > 골조 > WP-3-2 거푸집", "confidence": 0.87, "status": "unconfirmed",
    "alternative_wps": [{ "id": "wp-3-3", "path": "M15X > 골조 > WP-3-3 철근", "score": 0.34 }] },
  { "id": "r-002", "bp_name": "B건설", "work_content": "지하 1층 철근 받침대 설치 / 정리작업", "quantity": 18, "unit": "ton", "ai_mapped_wp_id": "wp-3-2", "ai_mapped_path": "M15X > 골조 > WP-3-2 거푸집", "confidence": 0.62, "status": "unconfirmed",
    "alternative_wps": [{ "id": "wp-3-3", "path": "M15X > 골조 > WP-3-3 철근", "score": 0.58 }] },
  { "id": "r-003", "bp_name": "C건설", "work_content": "방수 시트 정리작업 (재시공 준비)", "quantity": 45, "unit": "㎡", "ai_mapped_wp_id": "wp-5-1", "ai_mapped_path": "M15X > 마감 > WP-5-1 방수", "confidence": 0.71, "status": "unconfirmed",
    "alternative_wps": [{ "id": "wp-5-2", "path": "M15X > 마감 > WP-5-2 타일", "score": 0.41 }] },
  { "id": "r-004", "bp_name": "D건설", "work_content": "타일 부착 작업 (욕실)", "quantity": 28, "unit": "㎡", "ai_mapped_wp_id": "wp-5-2", "ai_mapped_path": "M15X > 마감 > WP-5-2 타일", "confidence": 0.74, "status": "unconfirmed" },
  { "id": "r-005", "bp_name": "E건설", "work_content": "터파기 보강 작업 / 토류판 설치", "quantity": 12, "unit": "EA", "ai_mapped_wp_id": "wp-1-1", "ai_mapped_path": "M15X > 토공사 > WP-1-1 터파기", "confidence": 0.68, "status": "unconfirmed" },
  { "id": "r-006", "bp_name": "F건설", "work_content": "되메우기 다짐 작업", "quantity": 85, "unit": "㎥", "ai_mapped_wp_id": "wp-1-2", "ai_mapped_path": "M15X > 토공사 > WP-1-2 되메우기", "confidence": 0.79, "status": "unconfirmed" },
  { "id": "r-007", "bp_name": "G건설", "work_content": "철근 결속 및 배근 작업 (벽체)", "quantity": 14, "unit": "ton", "ai_mapped_wp_id": "wp-3-3", "ai_mapped_path": "M15X > 골조 > WP-3-3 철근", "confidence": 0.72, "status": "unconfirmed" },
  { "id": "r-008", "bp_name": "H건설", "work_content": "거푸집 해체 및 청소", "quantity": 180, "unit": "㎡", "ai_mapped_wp_id": "wp-3-2", "ai_mapped_path": "M15X > 골조 > WP-3-2 거푸집", "confidence": 0.75, "status": "unconfirmed" },
  { "id": "r-009", "bp_name": "I건설", "work_content": "방수 우레탄 도포 작업", "quantity": 32, "unit": "㎡", "ai_mapped_wp_id": "wp-5-1", "ai_mapped_path": "M15X > 마감 > WP-5-1 방수", "confidence": 0.69, "status": "unconfirmed" },
  { "id": "r-010", "bp_name": "J건설", "work_content": "내부 페인트 도장 - 천정", "quantity": 56, "unit": "㎡", "ai_mapped_wp_id": "wp-5-3", "ai_mapped_path": "M15X > 마감 > WP-5-3 페인트", "confidence": 0.77, "status": "unconfirmed" },
  { "id": "r-011", "bp_name": "K건설", "work_content": "외벽 페인트 - 정리·재도장", "quantity": 38, "unit": "㎡", "ai_mapped_wp_id": "wp-5-3", "ai_mapped_path": "M15X > 마감 > WP-5-3 페인트", "confidence": 0.78, "status": "unconfirmed" },
  { "id": "r-012", "bp_name": "L건설", "work_content": "거푸집 설치 - 코너 보강", "quantity": 22, "unit": "㎡", "ai_mapped_wp_id": "wp-3-2", "ai_mapped_path": "M15X > 골조 > WP-3-2 거푸집", "confidence": 0.81, "status": "unconfirmed" },
  { "id": "r-100", "bp_name": "M건설", "work_content": "FAB 2층 철근 조립 (이미 검토 완료 예시)", "quantity": 18, "unit": "ton", "ai_mapped_wp_id": "wp-3-3", "ai_mapped_path": "M15X > 골조 > WP-3-3 철근", "confidence": 0.92, "status": "confirmed" }
]
```

- [ ] **Step 4: Commit**

```bash
git add data/mock_chat_sequence.json data/mock_review_cards.json data/mock_wbs_tree.json
git commit -m "$(cat <<'EOF'
feat(B): fixture — chat_sequence (Agent 대화 8턴) + review_cards (12 미확정 + 1 확정 예시) + wbs_tree (4 공종·9 WP)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Report + Dashboard + Simulation fixtures

**Files:**
- Create: `data/mock_report.json`
- Create: `data/mock_dashboard.json`
- Create: `data/mock_simulation.json`

- [ ] **Step 1: report 작성 (M15X 현장의 최근 일자별 보고서)**

Create `data/mock_report.json`. 큰 파일이므로 핵심 구조만 풀고 details에 2026-05-15 한 일자만 채움 (시연용으로 충분):

```json
{
  "daily": [
    { "date": "2026-05-15", "status": "risk",    "productivity_today": 88, "delay_days": 14, "recovery_days": 9 },
    { "date": "2026-05-14", "status": "normal",  "productivity_today": 94, "delay_days": 6,  "recovery_days": 4 },
    { "date": "2026-05-13", "status": "normal",  "productivity_today": 96, "delay_days": 3,  "recovery_days": 2 },
    { "date": "2026-05-12", "status": "caution", "productivity_today": 87, "delay_days": 9,  "recovery_days": 6 },
    { "date": "2026-05-11", "status": "normal",  "productivity_today": 95, "delay_days": 4,  "recovery_days": 3 }
  ],
  "details": {
    "2026-05-15": {
      "kpi": {
        "productivity_today": 88, "productivity_history_diff": -12,
        "delay_days": 14, "expected_completion": "2026-08-12",
        "recoverable_productivity": 9, "target_productivity": 97,
        "recovery_days": 9, "recovered_completion": "2026-08-03"
      },
      "s_curve": [
        { "date": "2026-04-01", "planned": 10,  "actual": 10 },
        { "date": "2026-04-15", "planned": 18,  "actual": 17 },
        { "date": "2026-05-01", "planned": 28,  "actual": 26 },
        { "date": "2026-05-15", "planned": 38.5,"actual": 34.2 },
        { "date": "2026-06-01", "planned": 50,  "forecast": 43, "recovery": 47 },
        { "date": "2026-06-15", "planned": 62,  "forecast": 53, "recovery": 60 },
        { "date": "2026-07-01", "planned": 74,  "forecast": 63, "recovery": 72 },
        { "date": "2026-07-15", "planned": 86,  "forecast": 74, "recovery": 86 },
        { "date": "2026-08-01", "planned": 96,  "forecast": 85, "recovery": 97 },
        { "date": "2026-08-03", "planned": 100, "forecast": 87, "recovery": 100 },
        { "date": "2026-08-12", "planned": 100, "forecast": 100, "recovery": 100 }
      ],
      "contractor_bars": [
        { "label": "A건설", "value": 92, "status": "normal" },
        { "label": "B건설", "value": 78, "status": "caution" },
        { "label": "C건설", "value": 71, "status": "risk" },
        { "label": "D건설", "value": 88, "status": "normal" },
        { "label": "E건설", "value": 84, "status": "normal" },
        { "label": "F건설", "value": 95, "status": "normal" }
      ],
      "trade_bars": [
        { "label": "거푸집", "value": 68, "status": "caution" },
        { "label": "철근",   "value": 54, "status": "risk" },
        { "label": "콘크리트","value": 96, "status": "normal" },
        { "label": "방수",   "value": 82, "status": "normal" },
        { "label": "MEP",    "value": 85, "status": "normal" }
      ],
      "quadrant": [
        { "wp_id": "wp-3-3", "wp_name": "WP-3-3 철근",   "trade": "골조",   "productivity": 54, "impact": 86, "quadrant": "risk",    "size": 80 },
        { "wp_id": "wp-3-2", "wp_name": "WP-3-2 거푸집", "trade": "골조",   "productivity": 68, "impact": 78, "quadrant": "risk",    "size": 75 },
        { "wp_id": "wp-5-1", "wp_name": "WP-5-1 방수",   "trade": "마감",   "productivity": 82, "impact": 62, "quadrant": "caution", "size": 50 },
        { "wp_id": "wp-3-4", "wp_name": "WP-3-4 콘크리트","trade": "골조",   "productivity": 96, "impact": 88, "quadrant": "caution", "size": 70 },
        { "wp_id": "wp-7-1", "wp_name": "WP-7-1 전기",   "trade": "MEP",    "productivity": 95, "impact": 28, "quadrant": "safe",    "size": 35 },
        { "wp_id": "wp-1-1", "wp_name": "WP-1-1 터파기", "trade": "토공사", "productivity": 92, "impact": 18, "quadrant": "safe",    "size": 22 }
      ],
      "optimizer": {
        "wp_id": "wp-3-3",
        "diagnosis": "철근 공종의 오늘 생산성이 이력 평균 대비 -28%. 작업내용에 '타워크레인 대기'가 기재되어 장비 스케줄 충돌로 인한 인원 분산이 원인으로 추정됩니다.",
        "similar_cases": [
          { "date": "2026-04-22", "description": "타워크레인 대기로 오전 작업 지연", "outcome": "다음날 정상 복귀, 만회 없음" },
          { "date": "2026-04-10", "description": "장비 스케줄 충돌 (2호기 점검)",   "outcome": "당일 인원 재집중으로 만회" },
          { "date": "2026-03-28", "description": "크레인 대기 → 야간 연장 투입",   "outcome": "2일 후 정상 복귀" }
        ],
        "recommendations": [
          "내일 오전 타워크레인 스케줄 확인 필수",
          "장비 확보 후 인원 재집중 투입 검토 (과거 04-10 패턴)",
          "잔여 물량 기준 D+3 이내 정상화 시 공기 영향 없음",
          "D+3 초과 시 야간 연장 또는 주말 투입 검토"
        ],
        "details": [
          { "label": "오늘 투입 인원", "value": "14명" },
          { "label": "오늘 물량", "value": "18 ton" },
          { "label": "생산성", "value": "1.29 ton/인 (이력 평균 1.79)" },
          { "label": "잔여 물량", "value": "245 ton" },
          { "label": "계획 완료일", "value": "2026-08-12" }
        ]
      },
      "raw_data": [
        { "building": "M15X", "trade": "골조", "wp": "WP-3-2 거푸집", "bp_name": "A건설", "work_content": "FAB 2층 벽체 거푸집 설치 / 우천 대응", "quantity": 320, "unit": "㎡", "workers": 14, "equipment": "타워크레인 1호기" },
        { "building": "M15X", "trade": "골조", "wp": "WP-3-3 철근",   "bp_name": "B건설", "work_content": "지하 1층 철근 받침대 설치 / 정리작업", "quantity": 18,  "unit": "ton", "workers": 14, "equipment": "타워크레인 2호기 (대기)" },
        { "building": "M15X", "trade": "골조", "wp": "WP-3-4 콘크리트","bp_name": "F건설","work_content": "FAB 2층 슬래브 콘크리트 타설",     "quantity": 75,  "unit": "㎥", "workers": 16, "equipment": "펌프카 2대" },
        { "building": "M15X", "trade": "마감", "wp": "WP-5-1 방수",   "bp_name": "C건설", "work_content": "방수 시트 정리작업 (재시공 준비)",    "quantity": 45,  "unit": "㎡", "workers": 8,  "equipment": "토치" },
        { "building": "M15X", "trade": "마감", "wp": "WP-5-2 타일",   "bp_name": "D건설", "work_content": "타일 부착 작업 (욕실)",            "quantity": 28,  "unit": "㎡", "workers": 6,  "equipment": "-" },
        { "building": "M15X", "trade": "토공사","wp": "WP-1-1 터파기","bp_name": "E건설", "work_content": "터파기 보강 작업 / 토류판 설치",    "quantity": 12,  "unit": "EA", "workers": 5,  "equipment": "굴삭기 0.7t" },
        { "building": "M15X", "trade": "MEP",  "wp": "WP-7-1 전기",   "bp_name": "G건설", "work_content": "1층 전기 트레이 설치",            "quantity": 38,  "unit": "m",  "workers": 6,  "equipment": "고소작업차" }
      ]
    }
  }
}
```

- [ ] **Step 2: dashboard 작성**

Create `data/mock_dashboard.json`:
```json
{
  "performance": {
    "fleet_kpi": { "avg_productivity": 95, "avg_delay": 4, "abnormal_total": 1, "recoverable_days": 3 }
  },
  "impact": {
    "fleet_kpi": {
      "today_count": 87, "review_pending": 12, "abnormal_count": 1, "last_updated": "09:12",
      "total_hours_saved": 2155, "total_fte_saved": 15.4,
      "total_headcount": 445, "total_hours": 62300,
      "ai_replacement_rate": 3.46, "yearly_saving": 203
    },
    "site_distribution": [
      { "site_id": "y1-ph1-obl",  "site_name": "Y-1 Ph-1 OBL",    "hours_saved": 832, "fte_saved": 5.9 },
      { "site_id": "indiana-hac", "site_name": "Indiana Fab HAC", "hours_saved": 353, "fte_saved": 2.5 },
      { "site_id": "pt3-extension","site_name": "P&T 3 증축",     "hours_saved": 255, "fte_saved": 1.8 },
      { "site_id": "y1-ph1-ibl",  "site_name": "Y-1 Ph-1 IBL",    "hours_saved": 248, "fte_saved": 1.8 },
      { "site_id": "m15x-obl-pt7","site_name": "M15X OBL & PT7",  "hours_saved": 246, "fte_saved": 1.7 },
      { "site_id": "m15x-ph3-ibl","site_name": "M15X Ph-3 IBL",   "hours_saved": 221, "fte_saved": 1.6 }
    ],
    "monthly_trend": [
      { "month": "2026-01", "cumulative_fte": 3.2 },
      { "month": "2026-02", "cumulative_fte": 7.8 },
      { "month": "2026-03", "cumulative_fte": 11.5 },
      { "month": "2026-04", "cumulative_fte": 14.1 },
      { "month": "2026-05", "cumulative_fte": 15.4 }
    ],
    "per_site_automation": {
      "m15x-ph3-ibl": [
        { "function": "Data Stewardship",  "rate": 88, "before_hours": 28, "after_hours": 3.4 },
        { "function": "P&L Reporting",     "rate": 86, "before_hours": 35, "after_hours": 4.9 },
        { "function": "Risk Management",   "rate": 71, "before_hours": 31, "after_hours": 9   },
        { "function": "Deal Support",      "rate": 47, "before_hours": 17, "after_hours": 9   }
      ]
    }
  }
}
```

- [ ] **Step 3: simulation 작성 (각 페이지 시뮬 시퀀스)**

Create `data/mock_simulation.json`:
```json
{
  "home": {
    "now_strip_today_count": { "base": 87, "variance": 1, "interval_ms": 5000 },
    "last_updated_tick_ms": 60000,
    "agent_card_status": {
      "Collector":  [3, 2, 4, 3, 5, 3],
      "Parser":     [2, 3, 2, 1, 2, 3],
      "Mapper":     [1, 2, 1, 0, 1, 2],
      "Atomizer":   [0, 0, 1, 0, 0, 0],
      "Reporter":   [0, 0, 0, 0, 0, 0],
      "Forecaster": [0, 0, 0, 0, 0, 0],
      "Optimizer":  [0, 0, 0, 0, 0, 0]
    },
    "agent_card_interval_ms": 8000
  },
  "tasks": {
    "daily_today_count": { "base": 87, "variance": 1, "interval_ms": 5000 },
    "mapper_progress_step_ms": 2000,
    "chat_reveal_interval_ms": 1500
  },
  "report": {
    "s_curve_endpoint_jitter_ms": 60000,
    "quadrant_jitter_ms": 10000
  },
  "dashboard": {
    "kpi_strip_jitter_ms": 30000,
    "site_card_sparkline_ms": 60000
  }
}
```

- [ ] **Step 4: 산수 검증 (수치 일관성)**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
# Sites total_hours_saved 합산 = 2155 (각 현장 hours_saved 합과 일치)
# Sites total_fte_saved 합산 ≈ 15.3 (반올림으로 15.4 표기)
# AI 업무 대체율 = 2155 / 62300 = 3.46% ✓
# monthly_trend 마지막 = 15.4 ✓
node -e "
  const s = require('./data/mock_sites.json');
  const h = s.reduce((a,b) => a + b.hours_saved, 0);
  const f = s.reduce((a,b) => a + b.fte_saved, 0);
  const hc = s.reduce((a,b) => a + b.headcount, 0);
  console.log('hours_saved sum:', h, '(expect 2155)');
  console.log('fte_saved sum:',   f.toFixed(1), '(expect ~15.4)');
  console.log('headcount sum:',   hc, '(expect 445)');
"
```

Expected output:
```
hours_saved sum: 2155 (expect 2155)
fte_saved sum: 15.3 (expect ~15.4)
headcount sum: 445 (expect 445)
```

- [ ] **Step 5: Commit**

```bash
git add data/mock_report.json data/mock_dashboard.json data/mock_simulation.json
git commit -m "$(cat <<'EOF'
feat(B): fixture — report·dashboard·simulation 시퀀스 (M15X 2026-05-15 상세 + 전사 ROI)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2 — Common Infrastructure (Task 11~14)

### Task 11: Sidebar 컴포넌트 (페르소나별 메뉴)

**Files:**
- Create: `web/app/components/Sidebar.tsx`

- [ ] **Step 1: Sidebar 작성**

Create `web/app/components/Sidebar.tsx`:
```tsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, Bot, ClipboardCheck, FileBarChart, LayoutDashboard } from "lucide-react";
import { usePersona, isMenuVisible } from "@/lib/persona";
import { cn } from "@/lib/utils";

const MENUS = [
  { key: "home",      label: "Home",          href: "/",           icon: Home },
  { key: "tasks",     label: "Agent Tasks",   href: "/tasks",      icon: Bot },
  { key: "review",    label: "Human Review",  href: "/review",     icon: ClipboardCheck },
  { key: "reports",   label: "Report",        href: "/reports",    icon: FileBarChart },
  { key: "dashboard", label: "Dashboard",     href: "/dashboard",  icon: LayoutDashboard },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const persona = usePersona((s) => s.persona);

  return (
    <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-border bg-white/60 backdrop-blur-sm">
      <div className="px-5 py-6">
        <span className="font-mono text-[10px] uppercase tracking-widest text-ink-light">
          Navigation
        </span>
      </div>
      <nav className="flex flex-col gap-1 px-3">
        {MENUS.filter((m) => isMenuVisible(persona, m.key)).map((m) => {
          const active = pathname === m.href || (m.href !== "/" && pathname?.startsWith(m.href));
          const Icon = m.icon;
          return (
            <Link
              key={m.key}
              href={m.href}
              className={cn(
                "group flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors",
                active
                  ? "bg-lavender-light text-lavender-text font-semibold"
                  : "text-ink-mid hover:bg-surface-soft"
              )}
            >
              <Icon className="h-4 w-4" strokeWidth={active ? 2.5 : 2} />
              {m.label}
              {m.key === "dashboard" && persona === "manager" && (
                <span className="ml-auto rounded-sm bg-lavender px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-white">
                  Mgmt
                </span>
              )}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto px-5 py-4 text-[10px] font-mono uppercase tracking-widest text-ink-light/70">
        v0.1 · PoC · B_Track
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Dev 서버 시각 확인**

Run: `cd web && npm run dev`
Open: `http://127.0.0.1:5535`
Expected: Sidebar는 아직 layout에 박히지 않아 안 보임 (다음 task). 컴파일 에러만 없으면 OK.

Run: `cd web && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add web/app/components/Sidebar.tsx
git commit -m "$(cat <<'EOF'
feat(B): Sidebar 컴포넌트 — 5 메뉴 페르소나별 노출(구성원 4 / 관리자 5)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: PersonaToggle + TopBar

**Files:**
- Create: `web/app/components/PersonaToggle.tsx`
- Create: `web/app/components/TopBar.tsx`

- [ ] **Step 1: PersonaToggle 작성**

Create `web/app/components/PersonaToggle.tsx`:
```tsx
"use client";
import { Users, UserCog } from "lucide-react";
import { usePersona } from "@/lib/persona";
import { cn } from "@/lib/utils";

export function PersonaToggle() {
  const persona = usePersona((s) => s.persona);
  const setPersona = usePersona((s) => s.setPersona);

  return (
    <div className="inline-flex rounded-md border border-border bg-white p-0.5">
      <button
        type="button"
        onClick={() => setPersona("member")}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-[5px] px-3 py-1.5 text-xs font-semibold transition-colors",
          persona === "member"
            ? "bg-lavender text-white"
            : "text-ink-mid hover:text-ink"
        )}
      >
        <Users className="h-3.5 w-3.5" />
        구성원
      </button>
      <button
        type="button"
        onClick={() => setPersona("manager")}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-[5px] px-3 py-1.5 text-xs font-semibold transition-colors",
          persona === "manager"
            ? "bg-lavender text-white"
            : "text-ink-mid hover:text-ink"
        )}
      >
        <UserCog className="h-3.5 w-3.5" />
        관리자
      </button>
    </div>
  );
}
```

- [ ] **Step 2: TopBar 작성**

Create `web/app/components/TopBar.tsx`:
```tsx
import { Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { PersonaToggle } from "./PersonaToggle";

export function TopBar() {
  return (
    <header className="sticky top-0 z-50 flex h-16 items-center justify-between border-b border-border bg-white/85 px-6 backdrop-blur-md md:px-10">
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-gradient-to-br from-lavender to-mint">
          <Sparkles className="h-4 w-4 text-white" strokeWidth={2.5} />
        </div>
        <span className="font-display text-base font-bold tracking-tight text-ink">
          CPIA
        </span>
        <Badge
          variant="outline"
          className="ml-2 gap-1 border-border bg-white px-2.5 py-1 font-mono text-[10px] uppercase tracking-widest text-ink-mid"
        >
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-mint" />
          live · v0.1
        </Badge>
      </div>
      <PersonaToggle />
    </header>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add web/app/components/TopBar.tsx web/app/components/PersonaToggle.tsx
git commit -m "$(cat <<'EOF'
feat(B): TopBar + PersonaToggle — 상단 페르소나 전환 (구성원/관리자)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: Root Layout 재구성

**Files:**
- Modify: `web/app/layout.tsx`

- [ ] **Step 1: 현재 layout.tsx 확인**

Run: `cat web/app/layout.tsx`
→ 기존 폰트 설정 등이 있음. 그대로 유지하고 TopBar + Sidebar 추가만.

- [ ] **Step 2: Layout 재작성 (TopBar + Sidebar 통합)**

Modify `web/app/layout.tsx`:
```tsx
import type { Metadata } from "next";
import "./globals.css";
import { TopBar } from "./components/TopBar";
import { Sidebar } from "./components/Sidebar";

export const metadata: Metadata = {
  title: "CPIA · Construction Productivity Intelligence Agent",
  description: "AI Agent 기반 현장 생산성 분석 + 공기 최적화",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-surface text-ink antialiased">
        <TopBar />
        <div className="flex">
          <Sidebar />
          <main className="flex-1 min-w-0">{children}</main>
        </div>
      </body>
    </html>
  );
}
```

> 기존 layout.tsx에 Pretendard/Geist 폰트 import가 있다면 그대로 유지하고 className만 추가. 폰트 설정은 `globals.css`에 박혀 있다면 별도 import 불필요.

- [ ] **Step 3: Dev 서버 확인**

Run: `cd web && npm run dev`
Open: `http://127.0.0.1:5535`
Expected:
- 상단에 TopBar (CPIA 로고 + live 뱃지 + 구성원/관리자 토글)
- 좌측에 Sidebar (4 메뉴 — 구성원 모드)
- 토글 클릭 시 사이드바에 Dashboard 메뉴 페이드인 (관리자 모드)

- [ ] **Step 4: Commit**

```bash
git add web/app/layout.tsx
git commit -m "$(cat <<'EOF'
feat(B): Root layout — TopBar + Sidebar 통합, 페르소나 토글 즉시 메뉴 반영

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: 기존 Layer 1 코드를 Dashboard로 이동

**Files:**
- Create: `web/app/dashboard/page.tsx` (기존 page.tsx 컨텐츠 복사)
- Modify: `web/app/page.tsx` (다음 Task에서 새 Home 컨텐츠로 교체)

- [ ] **Step 1: 기존 page.tsx 백업·복사**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
mkdir -p web/app/dashboard
cp web/app/page.tsx web/app/dashboard/page.tsx
```

- [ ] **Step 2: Dashboard로 옮긴 page.tsx 정리 (헤더 텍스트 변경 정도)**

Modify `web/app/dashboard/page.tsx`:
- 화면 상단 eyebrow나 h1 텍스트가 "Home"·"현장 현황" 등이면 "Dashboard / Performance"로 변경
- 나머지 로직(KPI strip, SiteCard 그리드 등)은 그대로 유지
- 컴포넌트 import 경로 확인 (`./components/SiteCard` → 기존 그대로 정상)

세부 텍스트 조정 예시:
- eyebrow: `현장 현황` → `Performance · Site Overview`
- h1: `Hi-tech 사업부` 유지 또는 `현장 생산성 & 공기 최적화 — 전사 모니터링`

> 기존 SiteCard 컴포넌트는 spec §3-5에서 "확장형 (미니 S-curve 추가)" 표시. 이 확장은 Phase 7 (Dashboard) Task에서 처리. 지금은 그대로 둠.

- [ ] **Step 3: Dev 서버 확인**

Run: `cd web && npm run dev`
Open: `http://127.0.0.1:5535/dashboard` (관리자 모드로 토글 후)
Expected: 기존 Layer 1 화면이 `/dashboard`에서 그대로 보임

- [ ] **Step 4: Commit**

```bash
git add web/app/dashboard/page.tsx
git commit -m "$(cat <<'EOF'
chore(B): 기존 Layer 1 → /dashboard 라우트로 이동 (Home 자리 비움)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3 — Home (Task 15~19)

> Home 화면은 시연 영상의 첫 컷. v7.1 Hero + NOW live strip + 7-Agent 카드 + HIL Review 단계 + CTA.

### Task 15: Hero 컴포넌트

**Files:**
- Create: `web/app/components/home/Hero.tsx`

- [ ] **Step 1: Hero 작성**

Create `web/app/components/home/Hero.tsx`:
```tsx
import { Clock4, UsersRound, AlarmClock, CalendarClock } from "lucide-react";

interface HeroStatProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  unit?: string;
  description: string;
  tone: "lavender" | "mint" | "sky" | "peach";
}

function HeroStat({ icon, label, value, unit, description, tone }: HeroStatProps) {
  const toneClass = {
    lavender: "from-lavender to-lavender-light",
    mint:     "from-mint     to-mint-light",
    sky:      "from-sky      to-sky-light",
    peach:    "from-peach    to-peach-light",
  }[tone];
  const iconBg = {
    lavender: "bg-lavender text-white",
    mint:     "bg-mint     text-white",
    sky:      "bg-sky      text-white",
    peach:    "bg-peach    text-white",
  }[tone];

  return (
    <div className="relative overflow-hidden rounded-card border border-border-soft bg-card p-5 shadow-xs">
      <span aria-hidden className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${toneClass}`} />
      <div className={`mb-3 inline-flex h-9 w-9 items-center justify-center rounded-md ${iconBg}`}>
        {icon}
      </div>
      <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light">{label}</div>
      <div className="mt-1 font-display text-3xl font-bold tracking-tight text-ink">
        {value}
        {unit && <span className="ml-1 text-base font-semibold text-ink-light">{unit}</span>}
      </div>
      <div className="mt-1 text-xs text-ink-mid">{description}</div>
    </div>
  );
}

export function Hero() {
  return (
    <section className="mx-auto max-w-wrap px-6 pt-14 pb-2 md:px-10 md:pt-20">
      <div className="flex items-center gap-3">
        <span className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-lavender-text">
          / 01 — Hi-tech Division
        </span>
        <span className="h-px w-8 bg-border" />
        <span className="font-mono text-[11px] uppercase tracking-widest text-ink-light">
          System Active · 6 Sites · 2026.05
        </span>
      </div>

      <h1 className="mt-6 font-display text-4xl font-bold leading-[1.15] tracking-tight text-ink md:text-5xl">
        현장 공정 데이터 자동화 및{" "}
        <span className="bg-gradient-to-r from-lavender to-mint bg-clip-text text-transparent">
          공기 리스크 선행 탐지
        </span>{" "}
        Agent
      </h1>

      <p className="mt-4 max-w-3xl text-base text-ink-mid md:text-lg">
        7개 전문 Agent + Vector RAG 기반 현장 실적 이력 판단 체계.
      </p>

      <div className="mt-10 grid grid-cols-2 gap-4 md:grid-cols-4">
        <HeroStat tone="lavender" icon={<Clock4 className="h-4 w-4" />}      label="월간 절감"     value="2,155" unit="h/월"  description="2,506h → 351h (86% 절감)" />
        <HeroStat tone="mint"     icon={<UsersRound className="h-4 w-4" />}  label="대체 규모"     value="15.4"  unit="명"    description="2,155h ÷ 140h/명 기준" />
        <HeroStat tone="sky"      icon={<AlarmClock className="h-4 w-4" />}  label="선행 탐지"     value="D-14"               description="공기 리스크 선행 탐지 목표" />
        <HeroStat tone="peach"    icon={<CalendarClock className="h-4 w-4" />} label="공기 단축"   value="3~7"   unit="일"    description="현장 1개당 공기 단축 추정" />
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/home/Hero.tsx
git commit -m "$(cat <<'EOF'
feat(B): Home Hero — v7.1 발췌 (slogan + 4 stats: 2155h·15.4명·D-14·3~7일)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 16: NowStrip (시뮬레이션 적용)

**Files:**
- Create: `web/app/components/home/NowStrip.tsx`

- [ ] **Step 1: NowStrip 작성**

Create `web/app/components/home/NowStrip.tsx`:
```tsx
"use client";
import { useCallback } from "react";
import { useSimulation } from "@/lib/use-simulation";
import { Activity, ClipboardCheck, AlertTriangle, RefreshCw } from "lucide-react";
import type { SitesSummary } from "@/lib/types";

interface Props {
  summary: SitesSummary;
}

export function NowStrip({ summary }: Props) {
  // "오늘 처리 87건" ±1 every 5s
  const todayUpdater = useCallback((n: number) => {
    const delta = Math.random() > 0.5 ? 1 : -1;
    const next = n + delta;
    return next < summary.today_count - 3 || next > summary.today_count + 3
      ? summary.today_count
      : next;
  }, [summary.today_count]);
  const todayCount = useSimulation(summary.today_count, todayUpdater, 5000);

  // "09:12 갱신" +1 second per minute
  const tickUpdater = useCallback((t: string) => {
    const [h, m] = t.split(":").map(Number);
    const tm = h * 60 + m + 1;
    return `${String(Math.floor(tm / 60)).padStart(2, "0")}:${String(tm % 60).padStart(2, "0")}`;
  }, []);
  const lastUpdated = useSimulation(summary.last_updated, tickUpdater, 60000);

  return (
    <section className="mx-auto max-w-wrap px-6 mt-8 md:px-10">
      <div className="rounded-card border border-border-soft bg-card p-5 shadow-xs">
        <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light mb-3">
          NOW · 현재 운영 현황
        </div>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <NowItem icon={<Activity className="h-3.5 w-3.5" />}        tone="sky"     label="오늘 처리"        value={`${todayCount}건`} />
          <NowItem icon={<ClipboardCheck className="h-3.5 w-3.5" />}  tone="peach"   label="Review 대기"     value={`${summary.review_pending}건`} />
          <NowItem icon={<AlertTriangle className="h-3.5 w-3.5" />}   tone="rose"    label="이상 공종"        value={`${summary.abnormal_count}건`} />
          <NowItem icon={<RefreshCw className="h-3.5 w-3.5" />}       tone="lavender" label="마지막 갱신"     value={lastUpdated} />
        </div>
      </div>
    </section>
  );
}

function NowItem({ icon, tone, label, value }: { icon: React.ReactNode; tone: "sky" | "peach" | "rose" | "lavender"; label: string; value: string }) {
  const toneBg = {
    sky: "bg-sky-light text-sky-text",
    peach: "bg-peach-light text-peach-text",
    rose: "bg-rose-light text-rose-text",
    lavender: "bg-lavender-light text-lavender-text",
  }[tone];
  return (
    <div className="flex items-center gap-3">
      <span className={`inline-flex h-8 w-8 items-center justify-center rounded-md ${toneBg}`}>{icon}</span>
      <div className="min-w-0">
        <div className="font-mono text-[9px] uppercase tracking-widest text-ink-light">{label}</div>
        <div className="font-display text-lg font-bold tracking-tight text-ink">{value}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/home/NowStrip.tsx
git commit -m "$(cat <<'EOF'
feat(B): Home NowStrip — 시뮬 적용 (오늘 처리 ±1 / 5s, 마지막 갱신 +1s / 60s)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 17: AgentCard + HilReviewStage

**Files:**
- Create: `web/app/components/home/AgentCard.tsx`
- Create: `web/app/components/home/HilReviewStage.tsx`

- [ ] **Step 1: AgentCard 작성**

Create `web/app/components/home/AgentCard.tsx`:
```tsx
"use client";
import { useCallback } from "react";
import { useSimulation } from "@/lib/use-simulation";
import { cn } from "@/lib/utils";
import type { AgentStatus } from "@/lib/types";

interface Props {
  agent: AgentStatus;
  simInterval?: number;
}

export function AgentCard({ agent, simInterval = 8000 }: Props) {
  const updater = useCallback((n: number) => {
    const variance = [-1, 0, 0, 1][Math.floor(Math.random() * 4)];
    return Math.max(0, n + variance);
  }, []);
  const live = useSimulation(agent.active_count, updater, simInterval);

  const groupClass = agent.group === "collect"
    ? "border-sky/40 bg-sky-light/30"
    : "border-lavender/40 bg-lavender-light/30";
  const stripeClass = agent.group === "collect" ? "bg-sky" : "bg-lavender";
  const stateColor =
    agent.state === "processing" ? "bg-mint" :
    agent.state === "waiting"    ? "bg-sun"  :
                                    "bg-ink-light/30";

  return (
    <div className={cn("relative overflow-hidden rounded-card border bg-card p-4 shadow-xs", groupClass)}>
      <span aria-hidden className={cn("absolute inset-x-0 top-0 h-1", stripeClass)} />
      <div className="font-mono text-[9px] uppercase tracking-widest text-ink-light">
        STEP {String(agent.step).padStart(2, "0")}
      </div>
      <div className="mt-1 font-display text-base font-bold tracking-tight text-ink">{agent.name}</div>
      <div className="mt-0.5 text-xs text-ink-light">{agent.korean_name}</div>
      <p className="mt-2 text-[11px] leading-relaxed text-ink-mid line-clamp-3">{agent.description}</p>
      <div className="mt-3 flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-widest text-ink-light">{agent.model}</span>
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-ink">
          <span className={cn("h-1.5 w-1.5 rounded-full", stateColor, agent.state !== "idle" && "animate-pulse")} />
          {live > 0 ? `${live}건` : "idle"}
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: HilReviewStage 작성 (Mapper와 Atomizer 사이 사람 개입 단계)**

Create `web/app/components/home/HilReviewStage.tsx`:
```tsx
import { Pause, UserCheck } from "lucide-react";

export function HilReviewStage() {
  return (
    <div className="relative my-4 flex flex-col items-center">
      <span aria-hidden className="h-6 w-px bg-border" />
      <div className="relative w-full max-w-xl rounded-card border-2 border-peach/50 bg-peach-light/40 p-4 shadow-xs">
        <div className="flex items-start gap-3">
          <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-peach text-white">
            <Pause className="h-4 w-4" strokeWidth={2.5} fill="currentColor" />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <UserCheck className="h-3.5 w-3.5 text-peach-text" strokeWidth={2.5} />
              <span className="font-mono text-[10px] uppercase tracking-widest text-peach-text font-bold">
                HIL REVIEW · 사람 개입
              </span>
            </div>
            <div className="mt-1 font-display text-base font-bold tracking-tight text-ink">
              확신도 낮은 매핑을 담당자가 검토·확정
            </div>
            <p className="mt-1 text-xs text-ink-mid">
              Mapper의 출력 중 확신도가 낮은 항목만 Human Review 화면으로 전달 — 빠른 확인 후 Atomizer로 진행 (시연 시연 1단계로 단순화).
            </p>
          </div>
        </div>
      </div>
      <span aria-hidden className="h-6 w-px bg-border" />
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add web/app/components/home/AgentCard.tsx web/app/components/home/HilReviewStage.tsx
git commit -m "$(cat <<'EOF'
feat(B): Home — AgentCard (7-Agent 카드, 시뮬 active count) + HilReviewStage (Mapper 뒤 사람 개입 단계)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 18: Home page.tsx 작성

**Files:**
- Modify: `web/app/page.tsx`

- [ ] **Step 1: page.tsx 새 컨텐츠로 교체**

Replace `web/app/page.tsx`:
```tsx
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { loadFixture } from "@/lib/fixtures";
import { Hero } from "./components/home/Hero";
import { NowStrip } from "./components/home/NowStrip";
import { AgentCard } from "./components/home/AgentCard";
import { HilReviewStage } from "./components/home/HilReviewStage";

export default async function HomePage() {
  const summary = await loadFixture("sites_summary");
  const agents = await loadFixture("agent_status");

  const collectGroup = agents.filter((a) => a.group === "collect"); // STEP 01~04
  const analyzeGroup = agents.filter((a) => a.group === "analyze"); // STEP 05~07

  return (
    <div className="relative pb-20">
      <Hero />
      <NowStrip summary={summary} />

      <section className="mx-auto max-w-wrap px-6 mt-12 md:px-10">
        <div className="mb-6 flex items-baseline justify-between">
          <div className="flex items-baseline gap-3">
            <h2 className="font-display text-lg font-bold tracking-tight text-ink md:text-xl">
              7-Agent 파이프라인 + HIL Review
            </h2>
            <span className="font-mono text-[10px] uppercase tracking-widest text-ink-light">
              LangGraph · multi-agent pipeline
            </span>
          </div>
        </div>

        {/* 수집·매핑 (sky) */}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {collectGroup.map((a) => <AgentCard key={a.step} agent={a} />)}
        </div>

        {/* HIL Review 단계 */}
        <HilReviewStage />

        {/* 진단·최적화 (lavender) */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {analyzeGroup.map((a) => <AgentCard key={a.step} agent={a} />)}
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-wrap px-6 mt-14 md:px-10">
        <Link
          href="/tasks"
          className="group inline-flex items-center gap-2 rounded-md bg-lavender px-5 py-3 text-sm font-semibold text-white shadow-sm transition-all hover:bg-lavender-text hover:shadow-md"
        >
          Agent Tasks 살펴보기
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" strokeWidth={2.5} />
        </Link>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Dev 서버 시각 확인**

Run: `cd web && npm run dev`
Open: `http://127.0.0.1:5535/`
Expected:
- Hero strip (CPIA 슬로건 + 4 stats: 2,155h · 15.4명 · D-14 · 3~7일)
- NOW strip (오늘 87건 ±1 변동 / Review 12건 / 이상 1건 / 마지막 갱신 09:12+1)
- 4×1 카드 그리드 (Collector·Parser·Mapper·Atomizer) + HIL Review 박스 + 3×1 카드 그리드 (Reporter·Forecaster·Optimizer)
- Agent 카드 status dot이 mint(processing) / sun(waiting) / 회색(idle)
- 하단 "Agent Tasks 살펴보기" 버튼

- [ ] **Step 3: 사용자 시각 review (피드백 사이클)**

> 이 단계에서 dev 서버 켠 상태로 사용자에게 화면 확인 요청. 톤·간격·시뮬 속도 등 시각 피드백 수렴 후 다음 task로.

- [ ] **Step 4: Commit**

```bash
git add web/app/page.tsx
git commit -m "$(cat <<'EOF'
feat(B): Home page — Hero + NOW strip + 7-Agent 카드 + HIL Review 단계 + CTA

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 19: Home dev 서버 통합 확인 + 페르소나 토글 테스트

**Files:** (수정 없음 — 통합 시점 검증)

- [ ] **Step 1: 페르소나 토글 동작 확인**

Run: `cd web && npm run dev`
Open: `http://127.0.0.1:5535/`
- 페르소나가 "구성원"일 때 → Sidebar 메뉴 4개 (Home·Agent Tasks·Human Review·Report)
- 토글 클릭 → "관리자" → Dashboard 메뉴 추가됨
- 브라우저 refresh 후에도 상태 유지 (localStorage persist)

- [ ] **Step 2: 시뮬 동작 확인**

5초 ~ 1분 동안 화면 켜둔 채:
- NOW strip "오늘 87건"이 ±1 변동 (예: 87 → 88 → 87 → 86 → ...)
- "마지막 갱신 09:12"가 1분 뒤 09:13으로
- 7-Agent 카드들의 active count가 8초마다 변동
- TopBar의 `live` dot이 점멸

- [ ] **Step 3: lint·타입 체크**

```bash
cd web
npx tsc --noEmit
npm run lint
```
Expected: No errors

- [ ] **Step 4: Commit (체크포인트 — 화면 변경 없으면 skip)**

> 코드 변경 없으면 commit 생략. 통합 확인만 진행.

---

## Phase 4 — Agent Tasks (Task 20~24)

> 3-column 화면: 좌 Daily list + 중 Process progress + 우 Chat log (하이브리드 톤).
> Reporter/Forecaster/Optimizer는 daily run 단위 (1/1), HIL Review는 검토 항목 단위 (12/12).

### Task 20: DailyRunList 컴포넌트

**Files:**
- Create: `web/app/components/tasks/DailyRunList.tsx`

- [ ] **Step 1: DailyRunList 작성**

Create `web/app/components/tasks/DailyRunList.tsx`:
```tsx
"use client";
import { cn } from "@/lib/utils";
import { AlertTriangle, CheckCircle2, Pause } from "lucide-react";
import type { DailyRun } from "@/lib/types";

interface Props {
  runs: DailyRun[];
  selectedDate: string;
  onSelect: (date: string) => void;
}

export function DailyRunList({ runs, selectedDate, onSelect }: Props) {
  const max = Math.max(...runs.map((r) => r.total_count));

  return (
    <div className="flex flex-col">
      <div className="px-3 py-3 border-b border-border-soft">
        <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light">
          Daily Runs · 일별 실행
        </div>
        <div className="mt-1 text-xs text-ink-mid">{runs.length}일치 누적</div>
      </div>
      <div className="flex flex-col">
        {runs.map((run) => {
          const active = run.date === selectedDate;
          return (
            <button
              type="button"
              key={run.date}
              onClick={() => onSelect(run.date)}
              className={cn(
                "group flex flex-col gap-1 border-b border-border-soft px-3 py-3 text-left transition-colors",
                active ? "bg-lavender-light/50" : "hover:bg-surface-soft"
              )}
            >
              <div className="flex items-center justify-between">
                <span className={cn("font-mono text-xs", active ? "text-lavender-text font-bold" : "text-ink")}>
                  {run.date}
                </span>
                <RunStatusIcon status={run.status} />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-ink-mid">{run.total_count}건</span>
                {run.has_anomaly && (
                  <span className="inline-flex items-center gap-0.5 rounded-sm bg-rose-light px-1.5 py-0.5 text-[9px] font-semibold text-rose-text">
                    <AlertTriangle className="h-2.5 w-2.5" />
                    이상
                  </span>
                )}
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-soft">
                <div
                  className={cn(
                    "h-full transition-all",
                    run.status === "review_pending" ? "bg-sun" : run.has_anomaly ? "bg-rose" : "bg-mint"
                  )}
                  style={{ width: `${(run.total_count / max) * 100}%` }}
                />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function RunStatusIcon({ status }: { status: DailyRun["status"] }) {
  if (status === "review_pending") return <Pause className="h-3.5 w-3.5 text-sun" fill="currentColor" />;
  if (status === "running")        return <span className="h-2 w-2 rounded-full bg-sky animate-pulse" />;
  return <CheckCircle2 className="h-3.5 w-3.5 text-mint" />;
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/tasks/DailyRunList.tsx
git commit -m "$(cat <<'EOF'
feat(B): Agent Tasks — DailyRunList (날짜·처리 건수·미니 bar·상태 뱃지)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 21: AgentProgressList 컴포넌트

**Files:**
- Create: `web/app/components/tasks/AgentProgressList.tsx`

- [ ] **Step 1: AgentProgressList 작성**

Create `web/app/components/tasks/AgentProgressList.tsx`:
```tsx
import { cn } from "@/lib/utils";
import { Pause } from "lucide-react";
import type { AgentProgress } from "@/lib/types";

interface Props {
  progress: AgentProgress[];
}

export function AgentProgressList({ progress }: Props) {
  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light">
        Process Progress · 단계별 진행
      </div>
      <div className="flex flex-col gap-2">
        {progress.map((p, i) => {
          const isHil = p.agent === "HIL Review";
          const isDone = p.processed === p.total && !p.waiting_hil;
          const percent = p.total === 0 ? 0 : (p.processed / p.total) * 100;
          const barColor = p.waiting_hil ? "bg-sun" : isDone ? "bg-mint" : "bg-sky";

          return (
            <div key={i} className={cn("flex items-center gap-3", isHil && "px-2 py-1.5 rounded-sm bg-peach-light/30")}>
              <div className="w-24 flex items-center gap-1.5 shrink-0">
                {isHil && <Pause className="h-3 w-3 text-peach-text" fill="currentColor" />}
                <span className={cn("text-xs font-semibold", isHil ? "text-peach-text" : "text-ink")}>
                  {p.agent}
                </span>
              </div>
              <div className="flex-1 h-2 overflow-hidden rounded-full bg-surface-soft">
                <div className={cn("h-full transition-all", barColor)} style={{ width: `${percent}%` }} />
              </div>
              <div className="w-16 text-right font-mono text-[11px] text-ink-mid">
                {p.processed}/{p.total}
              </div>
              <div className="w-6 flex justify-end">
                {p.waiting_hil && <span className="text-sun-text text-sm font-bold">⏸</span>}
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex items-center gap-3 text-[10px] text-ink-light">
        <span>per_report = 작업일보 87건 단위</span>
        <span>·</span>
        <span>per_review = 검토 항목 단위</span>
        <span>·</span>
        <span>per_run = Daily Run 1회</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/tasks/AgentProgressList.tsx
git commit -m "$(cat <<'EOF'
feat(B): Agent Tasks — AgentProgressList (8 단계 progress, Reporter+는 1/1 단위)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 22: AgentChatLog 컴포넌트 (시뮬 시퀀스)

**Files:**
- Create: `web/app/components/tasks/AgentChatLog.tsx`

- [ ] **Step 1: AgentChatLog 작성**

Create `web/app/components/tasks/AgentChatLog.tsx`:
```tsx
"use client";
import { useSequence } from "@/lib/use-simulation";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/types";

interface Props {
  messages: ChatMessage[];
  intervalMs?: number;
}

const AGENT_TONE: Record<string, { bg: string; text: string; ring: string }> = {
  Collector:  { bg: "bg-sky-light",      text: "text-sky-text",      ring: "ring-sky/30" },
  Parser:     { bg: "bg-sky-light",      text: "text-sky-text",      ring: "ring-sky/30" },
  Mapper:     { bg: "bg-sky-light",      text: "text-sky-text",      ring: "ring-sky/30" },
  Atomizer:   { bg: "bg-sky-light",      text: "text-sky-text",      ring: "ring-sky/30" },
  Human:      { bg: "bg-peach-light",    text: "text-peach-text",    ring: "ring-peach/30" },
  Reporter:   { bg: "bg-lavender-light", text: "text-lavender-text", ring: "ring-lavender/30" },
  Forecaster: { bg: "bg-lavender-light", text: "text-lavender-text", ring: "ring-lavender/30" },
  Optimizer:  { bg: "bg-mint-light",     text: "text-mint-text",     ring: "ring-mint/30" },
};

export function AgentChatLog({ messages, intervalMs = 1500 }: Props) {
  const revealed = useSequence(messages, intervalMs);

  return (
    <div className="flex flex-col">
      <div className="px-4 py-3 border-b border-border-soft">
        <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light">
          Agent Chat Log · 처리 흐름
        </div>
      </div>
      <div className="flex flex-col gap-2.5 p-4 max-h-[640px] overflow-y-auto">
        {revealed.map((m, i) => {
          const tone = AGENT_TONE[m.agent] || AGENT_TONE.Collector;
          const isHilRequest = m.type === "hil_request";
          const isHuman = m.type === "human_action";
          return (
            <div
              key={`${m.ts}-${i}`}
              className={cn(
                "rounded-card border border-border-soft p-3 shadow-xs animate-in fade-in slide-in-from-bottom-1 duration-300",
                isHilRequest && "ring-2 ring-sun/40 border-sun/40",
                isHuman && "border-peach/40"
              )}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={cn("inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider", tone.bg, tone.text)}>
                    {m.agent}
                  </span>
                  <span className="font-mono text-[10px] text-ink-light">{m.ts}</span>
                </div>
                {isHilRequest && (
                  <span className="rounded-sm bg-sun-light px-1.5 py-0.5 text-[9px] font-semibold text-sun-text">
                    HIL Review 요청
                  </span>
                )}
              </div>
              <div className="mt-2 text-sm font-medium text-ink leading-snug">{m.summary}</div>
              {m.detail && (
                <div className="mt-1.5 text-xs text-ink-mid leading-relaxed">{m.detail}</div>
              )}
            </div>
          );
        })}
        {revealed.length < messages.length && (
          <div className="text-center text-[10px] text-ink-light/70 py-2 animate-pulse">
            · · · 처리 중 · · ·
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/tasks/AgentChatLog.tsx
git commit -m "$(cat <<'EOF'
feat(B): Agent Tasks — AgentChatLog (하이브리드 톤, 시퀀스 reveal, HIL 강조)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 23: Agent Tasks page.tsx

**Files:**
- Create: `web/app/tasks/page.tsx`

- [ ] **Step 1: tasks/page.tsx 작성**

Create `web/app/tasks/page.tsx`:
```tsx
"use client";
import { useEffect, useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { DailyRunList } from "../components/tasks/DailyRunList";
import { AgentProgressList } from "../components/tasks/AgentProgressList";
import { AgentChatLog } from "../components/tasks/AgentChatLog";
import type { DailyRun, AgentProgress, ChatMessage } from "@/lib/types";

interface PageData {
  runs: DailyRun[];
  progressByDate: Record<string, AgentProgress[]>;
  chatByDate: Record<string, ChatMessage[]>;
}

export default function AgentTasksPage() {
  const [data, setData] = useState<PageData | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>("2026-05-15");

  useEffect(() => {
    fetch("/api/mock/agent-tasks")
      .then((r) => r.json())
      .then(setData);
  }, []);

  if (!data) {
    return (
      <div className="mx-auto max-w-wrap px-6 py-10 text-ink-light">
        Loading...
      </div>
    );
  }

  const progress = data.progressByDate[selectedDate] || [];
  const chat = data.chatByDate[selectedDate] || [];

  return (
    <div className="flex flex-col">
      <div className="mx-auto w-full max-w-wrap px-6 py-8 md:px-10">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-lavender-text">
            / 02 — Agent Tasks
          </span>
          <span className="h-px w-8 bg-border" />
          <span className="font-mono text-[11px] uppercase tracking-widest text-ink-light">
            Daily Run · Process Progress · Chat
          </span>
        </div>
        <h1 className="mt-6 font-display text-3xl font-bold tracking-tight text-ink">
          AI Agent가 처리하는 작업 흐름
        </h1>
        <p className="mt-2 text-sm text-ink-mid">
          매일 ~100건의 작업일보를 7개 Agent + Human Review가 협업해 처리합니다. Daily run을 선택하면 단계별 진행과 Agent 대화를 볼 수 있습니다.
        </p>
      </div>

      <section className="mx-auto w-full max-w-wrap px-6 pb-20 md:px-10">
        <div className="grid grid-cols-12 gap-4 rounded-card border border-border-soft bg-card shadow-xs">
          {/* 좌측: Daily List */}
          <div className="col-span-12 md:col-span-3 border-r border-border-soft">
            <DailyRunList
              runs={data.runs}
              selectedDate={selectedDate}
              onSelect={setSelectedDate}
            />
          </div>
          {/* 중앙: Process Progress */}
          <div className="col-span-12 md:col-span-4 border-r border-border-soft">
            <AgentProgressList progress={progress} />
          </div>
          {/* 우측: Chat Log */}
          <div className="col-span-12 md:col-span-5">
            <AgentChatLog messages={chat} />
          </div>
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: API 라우트 작성 (서버에서 fixture 로드)**

Create `web/app/api/mock/agent-tasks/route.ts`:
```ts
import { NextResponse } from "next/server";
import { loadFixture } from "@/lib/fixtures";

export async function GET() {
  const data = await loadFixture("agent_tasks");
  const chat = await loadFixture("chat_sequence");
  return NextResponse.json({
    runs: data.daily_runs,
    progressByDate: data.progress_by_date,
    chatByDate: chat,
  });
}
```

- [ ] **Step 3: Dev 서버 시각 확인**

Run: `cd web && npm run dev`
Open: `http://127.0.0.1:5535/tasks`
Expected:
- 3-column layout (좌 일별 list / 중 Agent progress / 우 Chat log)
- 좌측에서 2026-05-15가 디폴트 선택 (강조)
- 중앙에 8개 진행 bar — Collector~Atomizer는 N/87, HIL Review는 12/12 ⏸, Reporter~Optimizer는 0/1
- 우측 Chat log가 1.5초 간격으로 1개씩 페이드인 (Collector → Parser → Mapper → Human → Atomizer → Reporter → Forecaster → Optimizer)
- 다른 날짜 클릭 시 중앙·우측 갱신

- [ ] **Step 4: Commit**

```bash
git add web/app/tasks/page.tsx web/app/api/mock/agent-tasks/route.ts
git commit -m "$(cat <<'EOF'
feat(B): Agent Tasks page — 3-column (Daily list + Progress + Chat log) + mock API

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 24: Agent Tasks 사용자 시각 review 체크포인트

**Files:** (수정 없음)

- [ ] **Step 1: Dev 서버 켜고 화면 확인**

Run: `cd web && npm run dev`

- [ ] **Step 2: 다음 항목 확인 후 사용자 피드백 수렴**

- Chat log 시퀀스 속도 (1.5초 간격이 적절한가?)
- 메시지 본문 톤이 "사람처럼" 자연스러운가?
- HIL Review 강조 (sun/peach 색)가 한눈에 보이는가?
- Reporter/Forecaster/Optimizer의 `1/1` 표기가 명확한가?
- 일별 list의 mini bar 색이 의미를 잘 전달하는가?

- [ ] **Step 3: 피드백 반영 후 필요 시 추가 commit**

> Chat 톤/색/속도 등은 fixture·컴포넌트 props로 튜닝 가능. 작은 변경이면 같은 task에서 처리.

---

## Phase 5 — Human Review (Task 25~29)

> 좌 WBS 트리(건물 > 공종 > WP) + 우 카드 list. 카드 동작: 미확정=[확정][수정] / 확정=[수정만].
> 수정 UX: 검색 입력(autocomplete) + 트리 드래그앤드롭 (둘 다 지원).

### Task 25: WBSTree 컴포넌트

**Files:**
- Create: `web/app/components/review/WBSTree.tsx`

- [ ] **Step 1: WBSTree 작성**

Create `web/app/components/review/WBSTree.tsx`:
```tsx
"use client";
import { useState } from "react";
import { ChevronRight, ChevronDown, AlertTriangle, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { WBSNode, Status } from "@/lib/types";

interface Props {
  root: WBSNode;
  selectedId: string | null;
  onSelect: (id: string) => void;
  // Drop 시 처리 (드래그앤드롭 매핑 수정)
  onDrop?: (cardId: string, wpId: string) => void;
}

export function WBSTree({ root, selectedId, onSelect, onDrop }: Props) {
  return (
    <div className="flex flex-col p-3 text-sm">
      <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light px-2 pb-2">
        WBS Tree · 건물 &gt; 공종 &gt; Work Package
      </div>
      <Branch node={root} depth={0} selectedId={selectedId} onSelect={onSelect} onDrop={onDrop} />
    </div>
  );
}

function Branch({
  node, depth, selectedId, onSelect, onDrop,
}: { node: WBSNode; depth: number; selectedId: string | null; onSelect: (id: string) => void; onDrop?: (cardId: string, wpId: string) => void }) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = node.children && node.children.length > 0;
  const isSelected = node.id === selectedId;
  const isWP = node.type === "work_package";

  const [dragOver, setDragOver] = useState(false);

  return (
    <div>
      <div
        className={cn(
          "group flex items-center gap-1.5 px-2 py-1.5 rounded-sm cursor-pointer transition-colors",
          isSelected ? "bg-lavender-light text-lavender-text font-semibold" : "hover:bg-surface-soft",
          dragOver && "ring-2 ring-mint"
        )}
        style={{ paddingLeft: `${depth * 14 + 8}px` }}
        onClick={() => {
          if (hasChildren) setOpen(!open);
          onSelect(node.id);
        }}
        // 드롭 처리 (Work Package 노드에만)
        onDragOver={isWP ? (e) => { e.preventDefault(); setDragOver(true); } : undefined}
        onDragLeave={isWP ? () => setDragOver(false) : undefined}
        onDrop={isWP ? (e) => {
          e.preventDefault();
          setDragOver(false);
          const cardId = e.dataTransfer.getData("text/card-id");
          if (cardId && onDrop) onDrop(cardId, node.id);
        } : undefined}
      >
        {hasChildren ? (
          open ? <ChevronDown className="h-3 w-3 text-ink-light shrink-0" /> : <ChevronRight className="h-3 w-3 text-ink-light shrink-0" />
        ) : (
          <span className="w-3" />
        )}
        <StatusDot status={node.status} />
        <span className="text-xs flex-1">{node.name}</span>
        {node.review_count > 0 && (
          <span className="inline-flex items-center gap-0.5 rounded-sm bg-sun-light px-1.5 py-0.5 text-[9px] font-bold text-sun-text">
            <AlertTriangle className="h-2.5 w-2.5" />
            {node.review_count}
          </span>
        )}
        {isWP && node.review_count === 0 && (
          <CheckCircle2 className="h-3 w-3 text-mint" />
        )}
      </div>
      {open && hasChildren && node.children!.map((c) => (
        <Branch key={c.id} node={c} depth={depth + 1} selectedId={selectedId} onSelect={onSelect} onDrop={onDrop} />
      ))}
    </div>
  );
}

function StatusDot({ status }: { status: Status }) {
  const color = status === "risk" ? "bg-rose" : status === "caution" ? "bg-sun" : status === "normal" ? "bg-mint" : "bg-ink-light/30";
  return <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", color)} />;
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/review/WBSTree.tsx
git commit -m "$(cat <<'EOF'
feat(B): Human Review — WBSTree (3단 계층, 검토 건수 뱃지, 드롭 zone for WP 노드)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 26: WPSearchCombobox 컴포넌트 (검색 입력 수정 UX)

**Files:**
- Create: `web/app/components/review/WPSearchCombobox.tsx`

- [ ] **Step 1: WPSearchCombobox 작성**

Create `web/app/components/review/WPSearchCombobox.tsx`:
```tsx
"use client";
import { useState, useMemo } from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";
import type { WBSNode } from "@/lib/types";

interface WPOption {
  id: string;
  path: string;  // "M15X > 골조 > WP-3-2 거푸집"
}

interface Props {
  wbsRoot: WBSNode;
  currentWpId: string;
  onSelect: (wpId: string, path: string) => void;
}

// WBS tree 를 flat options 로 변환 (WP 노드만, path 누적)
function flattenWPs(node: WBSNode, ancestors: string[] = []): WPOption[] {
  const path = [...ancestors, node.name];
  if (node.type === "work_package") {
    return [{ id: node.id, path: path.join(" > ") }];
  }
  return (node.children || []).flatMap((c) => flattenWPs(c, path));
}

export function WPSearchCombobox({ wbsRoot, currentWpId, onSelect }: Props) {
  const allOptions = useMemo(() => flattenWPs(wbsRoot), [wbsRoot]);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const filtered = useMemo(() => {
    if (!query.trim()) return allOptions;
    const q = query.toLowerCase();
    return allOptions.filter((o) => o.path.toLowerCase().includes(q));
  }, [allOptions, query]);

  return (
    <div className="relative">
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-light" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder="WP 이름 또는 코드로 검색 (예: 철근)"
          className="w-full rounded-md border border-border bg-white pl-8 pr-2 py-1.5 text-xs text-ink placeholder:text-ink-light focus:border-lavender focus:outline-none"
        />
      </div>
      {open && filtered.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-border-soft bg-white shadow-md">
          {filtered.slice(0, 12).map((o) => (
            <li
              key={o.id}
              onMouseDown={() => {
                onSelect(o.id, o.path);
                setQuery("");
                setOpen(false);
              }}
              className={cn(
                "cursor-pointer px-3 py-1.5 text-xs hover:bg-lavender-light/40",
                o.id === currentWpId && "bg-mint-light/50 font-semibold"
              )}
            >
              {o.path}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/review/WPSearchCombobox.tsx
git commit -m "$(cat <<'EOF'
feat(B): Human Review — WPSearchCombobox (autocomplete 검색, WBS flat 변환)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 27: ReviewCard 컴포넌트 (상태별 액션 분리 + draggable)

**Files:**
- Create: `web/app/components/review/ReviewCard.tsx`

- [ ] **Step 1: ReviewCard 작성**

Create `web/app/components/review/ReviewCard.tsx`:
```tsx
"use client";
import { useState } from "react";
import { Check, Pencil, AlertTriangle, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { WPSearchCombobox } from "./WPSearchCombobox";
import type { ReviewItem, WBSNode } from "@/lib/types";

interface Props {
  item: ReviewItem;
  wbsRoot: WBSNode;
  onConfirm: (id: string) => void;
  onRemap: (id: string, newWpId: string, newPath: string) => void;
}

export function ReviewCard({ item, wbsRoot, onConfirm, onRemap }: Props) {
  const [editMode, setEditMode] = useState(false);
  const isConfirmed = item.status === "confirmed";

  return (
    <div
      draggable={!isConfirmed}
      onDragStart={(e) => {
        if (isConfirmed) return;
        e.dataTransfer.setData("text/card-id", item.id);
        e.dataTransfer.effectAllowed = "move";
      }}
      className={cn(
        "rounded-card border bg-card p-4 shadow-xs",
        isConfirmed ? "border-mint/30 bg-mint-light/10" : "border-sun/30 cursor-grab"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isConfirmed ? (
            <>
              <CheckCircle2 className="h-4 w-4 text-mint" />
              <span className="font-mono text-[10px] uppercase tracking-widest text-mint-text font-bold">확정</span>
            </>
          ) : (
            <>
              <AlertTriangle className="h-4 w-4 text-sun" />
              <span className="font-mono text-[10px] uppercase tracking-widest text-sun-text font-bold">미확정</span>
            </>
          )}
          <span className="ml-1 font-semibold text-sm text-ink">{item.bp_name}</span>
        </div>
        <span className="font-mono text-xs font-semibold text-ink-mid">
          {item.quantity} {item.unit}
        </span>
      </div>

      {/* Work content */}
      <p className="mt-2 text-sm italic text-ink-mid leading-snug">
        &ldquo;{item.work_content}&rdquo;
      </p>

      {/* Mapping */}
      <div className="mt-3 flex items-center gap-2 text-xs">
        <span className="text-ink-light">매핑:</span>
        <span className="font-semibold text-ink">{item.ai_mapped_path}</span>
        <span className={cn(
          "ml-auto rounded-sm px-1.5 py-0.5 text-[10px] font-mono font-bold",
          item.confidence >= 0.8 ? "bg-mint-light text-mint-text" : item.confidence >= 0.7 ? "bg-sky-light text-sky-text" : "bg-sun-light text-sun-text"
        )}>
          {Math.round(item.confidence * 100)}%
        </span>
      </div>

      {/* Alternatives (only for unconfirmed) */}
      {!isConfirmed && item.alternative_wps && item.alternative_wps.length > 0 && (
        <div className="mt-2 text-[11px] text-ink-light">
          대안: {item.alternative_wps.map((a) => `${a.path.split(" > ").pop()} (${Math.round(a.score * 100)}%)`).join(" · ")}
        </div>
      )}

      {/* Edit panel */}
      {editMode && (
        <div className="mt-3 rounded-md bg-surface-soft p-2">
          <div className="text-[10px] font-mono uppercase tracking-widest text-ink-light mb-1.5">
            수정: 검색 또는 좌측 트리로 드래그
          </div>
          <WPSearchCombobox
            wbsRoot={wbsRoot}
            currentWpId={item.ai_mapped_wp_id}
            onSelect={(id, path) => {
              onRemap(item.id, id, path);
              setEditMode(false);
            }}
          />
        </div>
      )}

      {/* Actions */}
      <div className="mt-3 flex items-center justify-end gap-2">
        {!isConfirmed && (
          <button
            type="button"
            onClick={() => onConfirm(item.id)}
            className="inline-flex items-center gap-1 rounded-md bg-lavender px-3 py-1.5 text-xs font-semibold text-white hover:bg-lavender-text transition-colors"
          >
            <Check className="h-3.5 w-3.5" strokeWidth={2.5} />
            확정
          </button>
        )}
        <button
          type="button"
          onClick={() => setEditMode((v) => !v)}
          className="inline-flex items-center gap-1 rounded-md border border-border bg-white px-3 py-1.5 text-xs font-semibold text-ink-mid hover:bg-surface-soft"
        >
          <Pencil className="h-3.5 w-3.5" />
          {editMode ? "취소" : "수정"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/review/ReviewCard.tsx
git commit -m "$(cat <<'EOF'
feat(B): Human Review — ReviewCard (상태별 액션 분리: 미확정=[확정][수정] / 확정=[수정만], 드래그 가능)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 28: Human Review page.tsx

**Files:**
- Create: `web/app/review/page.tsx`
- Create: `web/app/api/mock/review/route.ts`

- [ ] **Step 1: API 라우트**

Create `web/app/api/mock/review/route.ts`:
```ts
import { NextResponse } from "next/server";
import { loadFixture } from "@/lib/fixtures";

export async function GET() {
  const wbs = await loadFixture("wbs_tree");
  const cards = await loadFixture("review_cards");
  return NextResponse.json({ wbs, cards });
}
```

- [ ] **Step 2: review/page.tsx 작성**

Create `web/app/review/page.tsx`:
```tsx
"use client";
import { useEffect, useState, useMemo } from "react";
import { Switch } from "@/components/ui/switch";
import { CheckCheck } from "lucide-react";
import { WBSTree } from "../components/review/WBSTree";
import { ReviewCard } from "../components/review/ReviewCard";
import type { WBSNode, ReviewItem } from "@/lib/types";

export default function HumanReviewPage() {
  const [wbs, setWbs] = useState<WBSNode | null>(null);
  const [cards, setCards] = useState<ReviewItem[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [onlyUnconfirmed, setOnlyUnconfirmed] = useState(true);

  useEffect(() => {
    fetch("/api/mock/review")
      .then((r) => r.json())
      .then(({ wbs, cards }) => {
        setWbs(wbs);
        setCards(cards);
      });
  }, []);

  // selectedNodeId 가 WP면 그 WP만, trade면 그 하위 WP들, building이면 전체
  const visibleCards = useMemo(() => {
    let filtered = cards;
    if (onlyUnconfirmed) filtered = filtered.filter((c) => c.status === "unconfirmed");
    if (selectedNodeId) {
      const collect = (n: WBSNode | null): string[] => {
        if (!n) return [];
        if (n.type === "work_package") return [n.id];
        return (n.children || []).flatMap(collect);
      };
      const find = (n: WBSNode | null, id: string): WBSNode | null => {
        if (!n) return null;
        if (n.id === id) return n;
        for (const c of n.children || []) {
          const f = find(c, id);
          if (f) return f;
        }
        return null;
      };
      const node = find(wbs, selectedNodeId);
      const wpIds = collect(node);
      if (wpIds.length > 0) filtered = filtered.filter((c) => wpIds.includes(c.ai_mapped_wp_id));
    }
    return filtered;
  }, [cards, wbs, selectedNodeId, onlyUnconfirmed]);

  const totalUnconfirmed = cards.filter((c) => c.status === "unconfirmed").length;

  const handleConfirm = (id: string) => {
    setCards((cs) => cs.map((c) => c.id === id ? { ...c, status: "confirmed" } : c));
  };

  const handleRemap = (id: string, newWpId: string, newPath: string) => {
    setCards((cs) => cs.map((c) => c.id === id ? { ...c, ai_mapped_wp_id: newWpId, ai_mapped_path: newPath, confidence: 1.0 } : c));
  };

  const handleConfirmAll = () => {
    setCards((cs) => cs.map((c) => c.confidence >= 0.8 && c.status === "unconfirmed" ? { ...c, status: "confirmed" } : c));
  };

  if (!wbs) return <div className="px-6 py-10 text-ink-light">Loading...</div>;

  return (
    <div className="flex flex-col">
      <div className="mx-auto w-full max-w-wrap px-6 py-8 md:px-10">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-lavender-text">
            / 03 — Human Review
          </span>
          <span className="h-px w-8 bg-border" />
          <span className="font-mono text-[11px] uppercase tracking-widest text-ink-light">
            확신도 낮은 매핑 검토
          </span>
        </div>
        <h1 className="mt-6 font-display text-3xl font-bold tracking-tight text-ink">
          작업 물량 Mapping
        </h1>
        <p className="mt-2 text-sm text-ink-mid">
          좌측 WBS 트리에서 공종을 선택하거나, 검색 입력·드래그앤드롭으로 매핑을 수정·확정합니다.
        </p>
      </div>

      <section className="mx-auto w-full max-w-wrap px-6 pb-20 md:px-10">
        <div className="grid grid-cols-12 gap-4 rounded-card border border-border-soft bg-card shadow-xs">
          {/* WBS Tree */}
          <div className="col-span-12 md:col-span-4 border-r border-border-soft">
            <WBSTree root={wbs} selectedId={selectedNodeId} onSelect={setSelectedNodeId} onDrop={(cardId, wpId) => {
              const find = (n: WBSNode | null, id: string): WBSNode | null => {
                if (!n) return null;
                if (n.id === id) return n;
                for (const c of n.children || []) { const f = find(c, id); if (f) return f; }
                return null;
              };
              const collectPath = (n: WBSNode | null, id: string, path: string[] = []): string[] | null => {
                if (!n) return null;
                const next = [...path, n.name];
                if (n.id === id) return next;
                for (const c of n.children || []) { const r = collectPath(c, id, next); if (r) return r; }
                return null;
              };
              const path = collectPath(wbs, wpId)?.join(" > ") || "";
              handleRemap(cardId, wpId, path);
            }} />
          </div>

          {/* Cards */}
          <div className="col-span-12 md:col-span-8 p-4">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Switch checked={onlyUnconfirmed} onCheckedChange={setOnlyUnconfirmed} />
                <span className="text-xs font-medium text-ink">신규 확정 필요만 보기</span>
              </div>
              <div className="font-mono text-xs text-ink-mid">
                {visibleCards.filter((c) => c.status === "unconfirmed").length} / {totalUnconfirmed}
              </div>
            </div>

            <div className="flex flex-col gap-3">
              {visibleCards.map((c) => (
                <ReviewCard key={c.id} item={c} wbsRoot={wbs} onConfirm={handleConfirm} onRemap={handleRemap} />
              ))}
              {visibleCards.length === 0 && (
                <div className="rounded-card border border-dashed border-border-soft py-12 text-center text-sm text-ink-light">
                  표시할 항목이 없습니다.
                </div>
              )}
            </div>

            <div className="mt-6 pt-4 border-t border-border-soft flex justify-end">
              <button
                type="button"
                onClick={handleConfirmAll}
                className="inline-flex items-center gap-1.5 rounded-md bg-mint px-4 py-2 text-xs font-semibold text-white hover:bg-mint-text transition-colors"
              >
                <CheckCheck className="h-4 w-4" strokeWidth={2.5} />
                모두 AI 추천대로 확정 (확신도 ≥ 0.8)
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Dev 서버 시각 확인**

Run: `cd web && npm run dev`
Open: `http://127.0.0.1:5535/review`
Expected:
- 좌측 WBS 트리 (M15X > 토공사·골조·마감·MEP, 각 노드에 검토 건수 뱃지)
- 우측 카드 list (12개 미확정 카드, 토글로 1개 확정 카드 표시 가능)
- 카드 [확정] 클릭 시 카드 상태가 "확정"으로 변경되며 [수정만] 표시
- 카드 [수정] 클릭 시 검색 입력 펼침, 검색 결과 클릭 시 매핑 변경
- 카드를 좌측 트리의 다른 WP 노드로 드래그 가능 (mint ring 표시 후 drop)
- 상단 토글 "신규 확정 필요만 보기" 작동

- [ ] **Step 4: Commit**

```bash
git add web/app/review/page.tsx web/app/api/mock/review/route.ts
git commit -m "$(cat <<'EOF'
feat(B): Human Review page — WBSTree + 카드 list + 검색 + 드래그앤드롭 + 일괄 확정

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 29: Human Review 사용자 시각 review 체크포인트

**Files:** (수정 없음)

- [ ] **Step 1: Dev 서버 시각 review**

Open: `http://127.0.0.1:5535/review`

확인:
- 카드 동작 (미확정/확정 액션 분리 정상)
- 검색 입력 autocomplete (한국어 입력 잘 작동)
- 드래그앤드롭 (Work Package 노드에 drop 가능, trade 노드에는 drop 불가)
- 일괄 확정 버튼 효과
- 트리 노드 선택 시 우측 필터링

- [ ] **Step 2: 피드백 반영**

## Phase 6 — Report (Task 30~37)

> 좌 Daily 목록 + 우 (KPI strip + 3 탭). KPI 흐름형 4지표. Optimize 탭 분면 카운트 KPI + 자동 선택.

### Task 30: KpiStrip (재사용 가능)

**Files:**
- Create: `web/app/components/reports/KpiStrip.tsx`

- [ ] **Step 1: KpiStrip 작성**

Create `web/app/components/reports/KpiStrip.tsx`:
```tsx
import { cn } from "@/lib/utils";

export interface KpiItem {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  tone: "lavender" | "mint" | "sky" | "peach" | "rose" | "sun";
}

const TONE_STRIPE: Record<KpiItem["tone"], string> = {
  lavender: "from-lavender to-lavender-light",
  mint:     "from-mint to-mint-light",
  sky:      "from-sky to-sky-light",
  peach:    "from-peach to-peach-light",
  rose:     "from-rose to-rose-light",
  sun:      "from-sun to-sun-light",
};

export function KpiStrip({ items }: { items: KpiItem[] }) {
  return (
    <div className={cn(
      "grid gap-3",
      items.length === 4 && "grid-cols-2 md:grid-cols-4",
      items.length === 5 && "grid-cols-2 md:grid-cols-5",
    )}>
      {items.map((it, i) => (
        <div key={i} className="relative overflow-hidden rounded-card border border-border-soft bg-card p-4 shadow-xs">
          <span aria-hidden className={cn("absolute inset-x-0 top-0 h-1 bg-gradient-to-r", TONE_STRIPE[it.tone])} />
          <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light">{it.label}</div>
          <div className="mt-2 font-display text-2xl font-bold tracking-tight text-ink">
            {it.value}
            {it.unit && <span className="ml-1 text-sm font-semibold text-ink-light">{it.unit}</span>}
          </div>
          {it.sub && <div className="mt-1 text-[11px] text-ink-mid">{it.sub}</div>}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/reports/KpiStrip.tsx
git commit -m "$(cat <<'EOF'
feat(B): Report — KpiStrip 재사용 컴포넌트 (4·5 칸, tone 매핑, gradient stripe)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 31: SCurveChart (recharts)

**Files:**
- Create: `web/app/components/charts/SCurveChart.tsx`

- [ ] **Step 1: SCurveChart 작성**

Create `web/app/components/charts/SCurveChart.tsx`:
```tsx
"use client";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceDot } from "recharts";
import type { SCurvePoint } from "@/lib/types";

interface Props {
  points: SCurvePoint[];
  showRecovery?: boolean;
}

export function SCurveChart({ points, showRecovery = true }: Props) {
  // 마지막 실적 포인트 찾기
  const lastActualIdx = points.reduce((acc, p, i) => p.actual !== undefined ? i : acc, -1);
  const lastActualPoint = lastActualIdx >= 0 ? points[lastActualIdx] : null;

  return (
    <div className="w-full h-72">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" />
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#7a8494" }} tickFormatter={(d) => d.slice(5)} />
          <YAxis tick={{ fontSize: 10, fill: "#7a8494" }} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
            formatter={(v: number, n: string) => {
              const labels: Record<string, string> = { planned: "계획", actual: "실적", forecast: "예측 (현 추세)", recovery: "만회 (Optimizer)" };
              return [`${v}%`, labels[n] || n];
            }}
          />
          <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
            formatter={(v) => {
              const labels: Record<string, string> = { planned: "계획선", actual: "실적선", forecast: "예측선 (현 추세)", recovery: "만회선 (Optimizer 시나리오)" };
              return labels[v] || v;
            }}
          />
          <Line type="monotone" dataKey="planned"  stroke="#7a8494" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="actual"   stroke="#0ea76a" strokeWidth={2.5} dot={{ r: 3 }} connectNulls />
          <Line type="monotone" dataKey="forecast" stroke="#ef4444" strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls />
          {showRecovery && (
            <Line type="monotone" dataKey="recovery" stroke="#1a56db" strokeWidth={2} strokeDasharray="2 3" dot={false} connectNulls />
          )}
          {lastActualPoint && (
            <ReferenceDot x={lastActualPoint.date} y={lastActualPoint.actual!} r={6} fill="#0ea76a" stroke="#fff" strokeWidth={2} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/charts/SCurveChart.tsx
git commit -m "$(cat <<'EOF'
feat(B): chart — SCurveChart (recharts, 4선: 계획·실적·예측·만회, 실적 끝점 강조)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 32: BarChartH (업체별·공종별 막대)

**Files:**
- Create: `web/app/components/charts/BarChartH.tsx`

- [ ] **Step 1: BarChartH 작성**

Create `web/app/components/charts/BarChartH.tsx`:
```tsx
"use client";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Cell, Tooltip } from "recharts";
import type { BarItem } from "@/lib/types";

const STATUS_COLOR = {
  normal:  "#0ea76a",
  caution: "#d97706",
  risk:    "#ef4444",
  unknown: "#7a8494",
};

export function BarChartH({ items, title }: { items: BarItem[]; title?: string }) {
  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
      {title && <div className="mb-3 font-mono text-[10px] uppercase tracking-widest text-ink-light">{title}</div>}
      <ResponsiveContainer width="100%" height={items.length * 36 + 20}>
        <BarChart data={items} layout="vertical" margin={{ top: 0, right: 30, left: 50, bottom: 0 }}>
          <XAxis type="number" domain={[0, 110]} tick={{ fontSize: 10, fill: "#7a8494" }} tickFormatter={(v) => `${v}%`} />
          <YAxis type="category" dataKey="label" tick={{ fontSize: 11, fill: "#0d1117" }} width={50} />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
            formatter={(v: number) => [`${v}%`, "생산성"]}
          />
          <Bar dataKey="value" radius={[0, 4, 4, 0]}>
            {items.map((it, i) => <Cell key={i} fill={STATUS_COLOR[it.status]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/charts/BarChartH.tsx
git commit -m "$(cat <<'EOF'
feat(B): chart — BarChartH (수평 막대, STATUS 색 매핑)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 33: ForecastTab + QuadrantScatter + QuadrantCountKpi

**Files:**
- Create: `web/app/components/reports/ForecastTab.tsx`
- Create: `web/app/components/charts/QuadrantScatter.tsx`
- Create: `web/app/components/reports/QuadrantCountKpi.tsx`

- [ ] **Step 1: ForecastTab 작성**

Create `web/app/components/reports/ForecastTab.tsx`:
```tsx
import { SCurveChart } from "../charts/SCurveChart";
import { BarChartH } from "../charts/BarChartH";
import type { ReportDetail } from "@/lib/fixtures";

export function ForecastTab({ detail }: { detail: ReportDetail }) {
  return (
    <div className="flex flex-col gap-4">
      {/* S-curve 상단 요약 */}
      <div className="rounded-card border border-border-soft bg-card p-5 shadow-xs">
        <div className="flex items-center justify-between mb-3">
          <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light">S-Curve · 계획 vs 실적</div>
          <div className="flex items-center gap-4 text-[11px] text-ink-mid">
            <span><span className="text-ink-light">공정률:</span> <b>{detail.kpi.productivity_today}%</b></span>
            <span><span className="text-ink-light">SPI:</span> <b>{(detail.kpi.productivity_today / 100).toFixed(2)}</b></span>
            <span><span className="text-ink-light">잔여:</span> <b>{100 - detail.kpi.productivity_today}%</b></span>
          </div>
        </div>
        <SCurveChart points={detail.s_curve} showRecovery />
      </div>

      {/* 막대 2종 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <BarChartH items={detail.contractor_bars} title="업체별 생산성 (오늘 평균)" />
        <BarChartH items={detail.trade_bars} title="공종별 생산성 (오늘 평균)" />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: QuadrantScatter 작성**

Create `web/app/components/charts/QuadrantScatter.tsx`:
```tsx
"use client";
import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, Cell, ReferenceLine, ReferenceArea } from "recharts";
import type { QuadrantPoint } from "@/lib/types";

const QUADRANT_COLOR = { risk: "#ef4444", caution: "#d97706", watch: "#7a8494", safe: "#0ea76a" };

interface Props {
  points: QuadrantPoint[];
  selectedWpId: string | null;
  onSelect: (wpId: string) => void;
  filter?: "all" | "risk" | "caution" | "safe";
}

export function QuadrantScatter({ points, selectedWpId, onSelect, filter = "all" }: Props) {
  const visible = filter === "all" ? points : points.filter((p) => p.quadrant === filter);

  return (
    <div className="w-full h-96">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 20, right: 20, bottom: 50, left: 50 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" />
          {/* 4 quadrant background */}
          <ReferenceArea x1={0}  x2={70} y1={70} y2={100} fill="#ef4444" fillOpacity={0.05} />
          <ReferenceArea x1={70} x2={100} y1={70} y2={100} fill="#d97706" fillOpacity={0.05} />
          <ReferenceArea x1={0}  x2={70} y1={0}  y2={70}  fill="#7a8494" fillOpacity={0.03} />
          <ReferenceArea x1={70} x2={100} y1={0}  y2={70}  fill="#0ea76a" fillOpacity={0.05} />
          <ReferenceLine x={70} stroke="#cbd5e1" strokeDasharray="4 4" />
          <ReferenceLine y={70} stroke="#cbd5e1" strokeDasharray="4 4" />
          <XAxis type="number" dataKey="productivity" domain={[0, 100]} name="Productivity"
            label={{ value: "Productivity →", position: "bottom", offset: 0, style: { fontSize: 11, fill: "#7a8494" } }}
            tick={{ fontSize: 10, fill: "#7a8494" }} tickFormatter={(v) => `${v}%`} />
          <YAxis type="number" dataKey="impact" domain={[0, 100]} name="Impact"
            label={{ value: "Impact ↑", angle: -90, position: "left", offset: 0, style: { fontSize: 11, fill: "#7a8494" } }}
            tick={{ fontSize: 10, fill: "#7a8494" }} tickFormatter={(v) => `${v}%`} />
          <ZAxis type="number" dataKey="size" range={[60, 300]} />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
            formatter={(v: number, n: string, p: any) => {
              if (n === "size") return ["", ""];
              return [v, n];
            }}
            labelFormatter={() => ""}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as QuadrantPoint;
              return (
                <div className="rounded-md border border-border bg-white px-3 py-2 shadow-md text-[11px]">
                  <div className="font-bold text-ink">{p.wp_name}</div>
                  <div className="text-ink-light">{p.trade}</div>
                  <div className="mt-1 grid grid-cols-2 gap-x-3">
                    <span>Productivity:</span><b>{p.productivity}%</b>
                    <span>Impact:</span><b>{p.impact}%</b>
                  </div>
                </div>
              );
            }}
          />
          <Scatter data={visible} onClick={(e: any) => onSelect(e.wp_id)}>
            {visible.map((p, i) => (
              <Cell key={i} fill={QUADRANT_COLOR[p.quadrant]}
                stroke={p.wp_id === selectedWpId ? "#0d1117" : "transparent"}
                strokeWidth={p.wp_id === selectedWpId ? 2.5 : 0} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 3: QuadrantCountKpi 작성**

Create `web/app/components/reports/QuadrantCountKpi.tsx`:
```tsx
"use client";
import { cn } from "@/lib/utils";
import type { QuadrantPoint } from "@/lib/types";

type Filter = "all" | "risk" | "caution" | "safe";

interface Props {
  points: QuadrantPoint[];
  filter: Filter;
  onFilterChange: (f: Filter) => void;
}

export function QuadrantCountKpi({ points, filter, onFilterChange }: Props) {
  const counts = {
    risk: points.filter((p) => p.quadrant === "risk").length,
    caution: points.filter((p) => p.quadrant === "caution").length,
    safe: points.filter((p) => p.quadrant === "safe" || p.quadrant === "watch").length,
  };

  return (
    <div className="grid grid-cols-3 gap-2">
      <Chip tone="rose"  active={filter === "risk"}    onClick={() => onFilterChange(filter === "risk" ? "all" : "risk")}       label="위험" count={counts.risk} />
      <Chip tone="sun"   active={filter === "caution"} onClick={() => onFilterChange(filter === "caution" ? "all" : "caution")} label="경고" count={counts.caution} />
      <Chip tone="mint"  active={filter === "safe"}    onClick={() => onFilterChange(filter === "safe" ? "all" : "safe")}       label="안전" count={counts.safe} />
    </div>
  );
}

function Chip({ tone, active, onClick, label, count }: { tone: "rose" | "sun" | "mint"; active: boolean; onClick: () => void; label: string; count: number }) {
  const bg = tone === "rose" ? "bg-rose-light" : tone === "sun" ? "bg-sun-light" : "bg-mint-light";
  const text = tone === "rose" ? "text-rose-text" : tone === "sun" ? "text-sun-text" : "text-mint-text";
  const ring = tone === "rose" ? "ring-rose" : tone === "sun" ? "ring-sun" : "ring-mint";
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex flex-col items-center justify-center rounded-md px-2 py-2 transition-all",
        bg, text,
        active ? `ring-2 ${ring}` : "hover:opacity-80"
      )}
    >
      <span className="font-mono text-[10px] uppercase tracking-widest">{label}</span>
      <span className="font-display text-xl font-bold">{count}</span>
    </button>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add web/app/components/reports/ForecastTab.tsx web/app/components/charts/QuadrantScatter.tsx web/app/components/reports/QuadrantCountKpi.tsx
git commit -m "$(cat <<'EOF'
feat(B): Report — ForecastTab + QuadrantScatter (4분면) + QuadrantCountKpi (위험/경고/안전 chip)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 34: OptimizerResult + OptimizeTab

**Files:**
- Create: `web/app/components/reports/OptimizerResult.tsx`
- Create: `web/app/components/reports/OptimizeTab.tsx`

- [ ] **Step 1: OptimizerResult 작성**

Create `web/app/components/reports/OptimizerResult.tsx`:
```tsx
import { Brain, History, Lightbulb, Database } from "lucide-react";
import type { OptimizerOutput } from "@/lib/types";

export function OptimizerResult({ output }: { output: OptimizerOutput }) {
  return (
    <div className="flex flex-col gap-3">
      <Section icon={<Brain className="h-4 w-4" />} tone="lavender" title="진단">
        <p className="text-sm text-ink-mid leading-relaxed">{output.diagnosis}</p>
      </Section>
      <Section icon={<History className="h-4 w-4" />} tone="sky" title="유사 과거 사례">
        <ul className="space-y-1.5">
          {output.similar_cases.map((c, i) => (
            <li key={i} className="text-xs">
              <span className="font-mono font-semibold text-ink">{c.date}</span> · <span className="text-ink-mid">{c.description}</span>
              <div className="mt-0.5 ml-1 text-[11px] text-mint-text">→ {c.outcome}</div>
            </li>
          ))}
        </ul>
      </Section>
      <Section icon={<Lightbulb className="h-4 w-4" />} tone="peach" title="권고사항">
        <ul className="space-y-1 list-decimal list-inside marker:text-peach-text marker:font-semibold">
          {output.recommendations.map((r, i) => (
            <li key={i} className="text-xs text-ink-mid">{r}</li>
          ))}
        </ul>
      </Section>
      <Section icon={<Database className="h-4 w-4" />} tone="mint" title="상세 현황">
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
          {output.details.map((d, i) => (
            <div key={i} className="contents">
              <dt className="text-ink-light">{d.label}</dt>
              <dd className="font-semibold text-ink">{d.value}</dd>
            </div>
          ))}
        </dl>
      </Section>
    </div>
  );
}

function Section({ icon, tone, title, children }: { icon: React.ReactNode; tone: "lavender" | "sky" | "peach" | "mint"; title: string; children: React.ReactNode }) {
  const bg = { lavender: "bg-lavender-light", sky: "bg-sky-light", peach: "bg-peach-light", mint: "bg-mint-light" }[tone];
  const text = { lavender: "text-lavender-text", sky: "text-sky-text", peach: "text-peach-text", mint: "text-mint-text" }[tone];
  return (
    <div className="rounded-card border border-border-soft bg-card p-3 shadow-xs">
      <div className="flex items-center gap-2 mb-2">
        <span className={`inline-flex h-6 w-6 items-center justify-center rounded-sm ${bg} ${text}`}>{icon}</span>
        <span className={`font-mono text-[10px] uppercase tracking-widest font-bold ${text}`}>{title}</span>
      </div>
      {children}
    </div>
  );
}
```

- [ ] **Step 2: OptimizeTab 작성 (4분면 + 우측 결과, 자동 선택)**

Create `web/app/components/reports/OptimizeTab.tsx`:
```tsx
"use client";
import { useEffect, useState } from "react";
import { QuadrantScatter } from "../charts/QuadrantScatter";
import { QuadrantCountKpi } from "./QuadrantCountKpi";
import { OptimizerResult } from "./OptimizerResult";
import type { ReportDetail } from "@/lib/fixtures";

type Filter = "all" | "risk" | "caution" | "safe";

export function OptimizeTab({ detail }: { detail: ReportDetail }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedWp, setSelectedWp] = useState<string | null>(null);

  // 진입 시 좌상단 위험군 자동 선택
  useEffect(() => {
    const riskPoint = detail.quadrant.find((p) => p.quadrant === "risk");
    const timer = setTimeout(() => {
      if (riskPoint) setSelectedWp(riskPoint.wp_id);
    }, 500);
    return () => clearTimeout(timer);
  }, [detail.quadrant]);

  // selected의 optimizer 결과 (fixture는 1개만 가지고 있으므로 그대로 사용)
  const optimizer = detail.optimizer;

  return (
    <div className="grid grid-cols-12 gap-4">
      {/* 좌: 4분면 */}
      <div className="col-span-12 md:col-span-6">
        <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
          <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light mb-2">
            Impact × Productivity 산점도
          </div>
          <QuadrantScatter
            points={detail.quadrant}
            selectedWpId={selectedWp}
            onSelect={setSelectedWp}
            filter={filter}
          />
          <div className="mt-3 text-[10px] text-ink-light text-center">
            점 크기 = 잔여 물량. 좌상 = 고Impact·저Productivity (위험군).
          </div>
        </div>
      </div>

      {/* 우: 카운트 KPI + Optimizer 결과 */}
      <div className="col-span-12 md:col-span-6 flex flex-col gap-3">
        <QuadrantCountKpi points={detail.quadrant} filter={filter} onFilterChange={setFilter} />
        <OptimizerResult output={optimizer} />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add web/app/components/reports/OptimizerResult.tsx web/app/components/reports/OptimizeTab.tsx
git commit -m "$(cat <<'EOF'
feat(B): Report — OptimizeTab (4분면 + KPI chip + Optimizer 4요소, 위험군 자동 선택 0.5s)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 35: RawDataTab

**Files:**
- Create: `web/app/components/reports/RawDataTab.tsx`

- [ ] **Step 1: RawDataTab 작성 (검색·정렬 가능 테이블)**

Create `web/app/components/reports/RawDataTab.tsx`:
```tsx
"use client";
import { useState, useMemo } from "react";
import { Search, Download } from "lucide-react";
import type { RawDataRow } from "@/lib/types";

const COLUMNS: { key: keyof RawDataRow; label: string }[] = [
  { key: "building",     label: "건물" },
  { key: "trade",        label: "공종" },
  { key: "wp",           label: "WP" },
  { key: "bp_name",      label: "BP사" },
  { key: "work_content", label: "작업내용" },
  { key: "quantity",     label: "물량" },
  { key: "unit",         label: "단위" },
  { key: "workers",      label: "인원" },
  { key: "equipment",    label: "장비" },
];

export function RawDataTab({ rows }: { rows: RawDataRow[] }) {
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    if (!q.trim()) return rows;
    const needle = q.toLowerCase();
    return rows.filter((r) =>
      Object.values(r).some((v) => String(v).toLowerCase().includes(needle))
    );
  }, [rows, q]);

  const exportCsv = () => {
    const header = COLUMNS.map((c) => c.label).join(",");
    const body = filtered.map((r) => COLUMNS.map((c) => JSON.stringify(r[c.key] ?? "")).join(",")).join("\n");
    const csv = `${header}\n${body}`;
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "raw_data.csv"; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="rounded-card border border-border-soft bg-card shadow-xs overflow-hidden">
      <div className="flex items-center justify-between p-3 border-b border-border-soft">
        <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light">
          작업일보 매핑 결과 · {rows.length} rows
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-light" />
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="검색..."
              className="rounded-md border border-border bg-white pl-7 pr-2 py-1 text-xs text-ink placeholder:text-ink-light focus:border-lavender focus:outline-none"
            />
          </div>
          <button
            type="button"
            onClick={exportCsv}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-white px-2.5 py-1 text-xs font-semibold text-ink-mid hover:bg-surface-soft"
          >
            <Download className="h-3 w-3" />
            CSV
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead className="bg-surface-soft">
            <tr>
              {COLUMNS.map((c) => (
                <th key={c.key} className="px-2 py-2 text-left font-mono uppercase tracking-widest text-ink-light text-[10px]">{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((r, i) => (
              <tr key={i} className="border-t border-border-soft hover:bg-surface-soft/50">
                {COLUMNS.map((c) => (
                  <td key={c.key} className="px-2 py-1.5 text-ink-mid">
                    {String(r[c.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={COLUMNS.length} className="px-2 py-8 text-center text-ink-light">검색 결과 없음</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/reports/RawDataTab.tsx
git commit -m "$(cat <<'EOF'
feat(B): Report — RawDataTab (9 컬럼: 건물·공종·WP·BP사·작업내용·물량·단위·인원·장비, 검색·CSV)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 36: ReportDailyList + Report page.tsx

**Files:**
- Create: `web/app/components/reports/ReportDailyList.tsx`
- Create: `web/app/reports/page.tsx`
- Create: `web/app/api/mock/report/route.ts`

- [ ] **Step 1: ReportDailyList 작성**

Create `web/app/components/reports/ReportDailyList.tsx`:
```tsx
"use client";
import { cn } from "@/lib/utils";
import { AlertTriangle, CheckCircle2, AlertCircle } from "lucide-react";
import type { ReportDaily } from "@/lib/types";

interface Props {
  daily: ReportDaily[];
  selectedDate: string;
  onSelect: (date: string) => void;
}

export function ReportDailyList({ daily, selectedDate, onSelect }: Props) {
  return (
    <div className="flex flex-col">
      <div className="px-3 py-3 border-b border-border-soft">
        <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light">
          Daily Reports · 일별 보고서
        </div>
      </div>
      {daily.map((d) => {
        const active = d.date === selectedDate;
        const Icon = d.status === "risk" ? AlertTriangle : d.status === "caution" ? AlertCircle : CheckCircle2;
        const iconColor = d.status === "risk" ? "text-rose" : d.status === "caution" ? "text-sun" : "text-mint";
        return (
          <button
            type="button"
            key={d.date}
            onClick={() => onSelect(d.date)}
            className={cn(
              "flex flex-col gap-1 border-b border-border-soft px-3 py-3 text-left transition-colors",
              active ? "bg-lavender-light/50" : "hover:bg-surface-soft"
            )}
          >
            <div className="flex items-center justify-between">
              <span className={cn("font-mono text-xs", active ? "text-lavender-text font-bold" : "text-ink")}>{d.date}</span>
              <Icon className={cn("h-3.5 w-3.5", iconColor)} />
            </div>
            <div className="text-[11px] text-ink-mid">
              생산성 <b className="text-ink">{d.productivity_today}%</b>
              {d.delay_days > 0 && <span> · D+{d.delay_days} 지연</span>}
            </div>
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: API 라우트**

Create `web/app/api/mock/report/route.ts`:
```ts
import { NextResponse } from "next/server";
import { loadFixture } from "@/lib/fixtures";

export async function GET() {
  const data = await loadFixture("report");
  return NextResponse.json(data);
}
```

- [ ] **Step 3: reports/page.tsx 작성**

Create `web/app/reports/page.tsx`:
```tsx
"use client";
import { useEffect, useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ReportDailyList } from "../components/reports/ReportDailyList";
import { KpiStrip, type KpiItem } from "../components/reports/KpiStrip";
import { ForecastTab } from "../components/reports/ForecastTab";
import { OptimizeTab } from "../components/reports/OptimizeTab";
import { RawDataTab } from "../components/reports/RawDataTab";
import type { ReportDetail } from "@/lib/fixtures";
import type { ReportDaily } from "@/lib/types";

export default function ReportPage() {
  const [daily, setDaily] = useState<ReportDaily[]>([]);
  const [details, setDetails] = useState<Record<string, ReportDetail>>({});
  const [selectedDate, setSelectedDate] = useState<string>("2026-05-15");

  useEffect(() => {
    fetch("/api/mock/report")
      .then((r) => r.json())
      .then((d) => { setDaily(d.daily); setDetails(d.details); });
  }, []);

  if (!details[selectedDate]) {
    return <div className="px-6 py-10 text-ink-light">Loading...</div>;
  }
  const detail = details[selectedDate];

  const kpi: KpiItem[] = [
    { label: "현재 생산성", value: `${detail.kpi.productivity_today}`, unit: "%", sub: `이력 ${detail.kpi.productivity_history_diff > 0 ? "+" : ""}${detail.kpi.productivity_history_diff}%`, tone: detail.kpi.productivity_today < 90 ? "rose" : "mint" },
    { label: "현 추세 공기", value: `D+${detail.kpi.delay_days}`, unit: "일 지연", sub: detail.kpi.expected_completion, tone: "rose" },
    { label: "회복 가능 생산성", value: `+${detail.kpi.recoverable_productivity}`, unit: "%p", sub: `${detail.kpi.target_productivity}% 도달`, tone: "lavender" },
    { label: "최적화 후 공기", value: `-${detail.kpi.recovery_days}`, unit: "일 회복", sub: detail.kpi.recovered_completion, tone: "mint" },
  ];

  return (
    <div className="flex flex-col">
      <div className="mx-auto w-full max-w-wrap px-6 py-8 md:px-10">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-lavender-text">
            / 04 — Report
          </span>
          <span className="h-px w-8 bg-border" />
          <span className="font-mono text-[11px] uppercase tracking-widest text-ink-light">
            일별 진단 · 만회 시나리오 · 원본 데이터
          </span>
        </div>
        <h1 className="mt-6 font-display text-3xl font-bold tracking-tight text-ink">
          현장 일일 진단 보고서
        </h1>
      </div>

      <section className="mx-auto w-full max-w-wrap px-6 pb-20 md:px-10">
        <div className="grid grid-cols-12 gap-4">
          {/* 좌측: Daily 목록 */}
          <div className="col-span-12 md:col-span-3">
            <div className="rounded-card border border-border-soft bg-card shadow-xs overflow-hidden">
              <ReportDailyList daily={daily} selectedDate={selectedDate} onSelect={setSelectedDate} />
            </div>
          </div>

          {/* 우측: KPI strip + 탭 */}
          <div className="col-span-12 md:col-span-9 flex flex-col gap-4">
            <KpiStrip items={kpi} />
            <Tabs defaultValue="forecast" className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="forecast">Forecast</TabsTrigger>
                <TabsTrigger value="optimize">Optimize</TabsTrigger>
                <TabsTrigger value="raw">Raw Data</TabsTrigger>
              </TabsList>
              <TabsContent value="forecast" className="mt-4">
                <ForecastTab detail={detail} />
              </TabsContent>
              <TabsContent value="optimize" className="mt-4">
                <OptimizeTab detail={detail} />
              </TabsContent>
              <TabsContent value="raw" className="mt-4">
                <RawDataTab rows={detail.raw_data} />
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Dev 서버 시각 확인**

Run: `cd web && npm run dev`
Open: `http://127.0.0.1:5535/reports`
Expected:
- 좌측에 5개 일별 row, 2026-05-15가 디폴트 선택 (이상 ⚠ 마크)
- 우측 상단 KPI strip 4 칸 (현재 생산성 / 현 추세 공기 / 회복 가능 / 최적화 후)
- Forecast 탭: S-curve (4선) + 업체별 막대 + 공종별 막대
- Optimize 탭: 좌 4분면 (진입 0.5초 후 위험군 점 자동 선택) + 우 카운트 chip + Optimizer 4 섹션
- Raw Data 탭: 7 row 테이블 (9 컬럼), 검색·CSV 작동

- [ ] **Step 5: Commit**

```bash
git add web/app/reports/page.tsx web/app/components/reports/ReportDailyList.tsx web/app/api/mock/report/route.ts
git commit -m "$(cat <<'EOF'
feat(B): Report page — Daily list + KPI strip + 3 탭 (Forecast / Optimize / Raw Data)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 37: Report 사용자 시각 review 체크포인트

**Files:** (수정 없음)

- [ ] **Step 1: Dev 서버 시각 review**

Open: `http://127.0.0.1:5535/reports`

확인:
- KPI strip 4지표 흐름 (생산성 → 공기 → 회복 가능 → 만회 공기)
- S-curve 4선 가독성, 만회선이 점선으로 잘 구분되는가
- Optimize 탭 진입 시 위험군 점 자동 선택 효과
- 분면 카운트 chip 클릭 시 필터링 작동
- Raw Data 9 컬럼 가독성

- [ ] **Step 2: 피드백 반영**

## Phase 7 — Dashboard (Task 38~44)

> Performance ↔ Impact 2 탭. 디폴트 전사 → 현장 카드 클릭 → 현장 드릴다운 (`/dashboard/sites/[id]`).
> Performance: 전사 6 카드 + 현장 4선 S-curve + 업체별/공종별 막대 (이미 작성한 컴포넌트 재사용).
> Impact: KPI strip (전체 근무량 흐름) + 현장별 분포 + 월별 추세 + 4기능 자동화율.

### Task 38: SiteOverviewCard (mini S-curve 포함)

**Files:**
- Create: `web/app/components/dashboard/SiteOverviewCard.tsx`

- [ ] **Step 1: SiteOverviewCard 작성**

Create `web/app/components/dashboard/SiteOverviewCard.tsx`:
```tsx
import Link from "next/link";
import { ResponsiveContainer, LineChart, Line } from "recharts";
import { AlertTriangle, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Site } from "@/lib/types";

// Mini S-curve sparkline data (가짜 - actual progress trend)
function makeSparkline(actual: number): { v: number }[] {
  return Array.from({ length: 7 }, (_, i) => ({ v: actual * (0.4 + i * 0.1) }));
}

export function SiteOverviewCard({ site }: { site: Site }) {
  const stripeColor = site.status === "risk" ? "bg-rose" : site.status === "caution" ? "bg-sun" : "bg-mint";
  const statusBg = site.status === "risk" ? "bg-rose-light text-rose-text" : site.status === "caution" ? "bg-sun-light text-sun-text" : "bg-mint-light text-mint-text";
  const data = makeSparkline(site.progress_actual);

  return (
    <Link
      href={`/dashboard/sites/${site.id}`}
      className="group relative overflow-hidden rounded-card border border-border-soft bg-card p-4 shadow-xs hover:shadow-sm transition-shadow"
    >
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", stripeColor)} />
      <div className="pl-3">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <div className="font-display text-base font-bold tracking-tight text-ink truncate">{site.name}</div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light mt-0.5">{site.location} · Hi-tech</div>
          </div>
          {site.status === "risk" && (
            <span className="inline-flex items-center gap-0.5 rounded-sm bg-rose-light px-1.5 py-0.5 text-[9px] font-bold text-rose-text">
              <AlertTriangle className="h-2.5 w-2.5" />
              이상
            </span>
          )}
        </div>

        {/* KPI row */}
        <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
          <div>
            <div className="text-ink-light">생산성</div>
            <div className="font-display text-lg font-bold text-ink">{site.productivity_today}%</div>
          </div>
          <div>
            <div className="text-ink-light">공기</div>
            <div className={cn("font-display text-lg font-bold", site.delay_days > 0 ? "text-rose" : "text-mint")}>
              {site.delay_days > 0 ? `+${site.delay_days}일` : "정상"}
            </div>
          </div>
        </div>

        {/* Mini sparkline */}
        <div className="mt-2 h-8">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <Line type="monotone" dataKey="v" stroke={site.status === "risk" ? "#ef4444" : site.status === "caution" ? "#d97706" : "#0ea76a"} strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Footer */}
        <div className="mt-2 flex items-center justify-between border-t border-border-soft pt-2">
          <span className={cn("inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[9px] font-semibold", statusBg)}>
            {site.abnormal_trades > 0 ? `이상 공종 ${site.abnormal_trades}` : "정상"}
          </span>
          <ArrowRight className="h-3.5 w-3.5 text-ink-light group-hover:text-lavender group-hover:translate-x-0.5 transition-all" />
        </div>
      </div>
    </Link>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/dashboard/SiteOverviewCard.tsx
git commit -m "$(cat <<'EOF'
feat(B): Dashboard — SiteOverviewCard (status stripe, 생산성·공기 KPI, mini sparkline, 드릴다운 링크)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 39: HorizontalBarList + TrendLineChart

**Files:**
- Create: `web/app/components/dashboard/HorizontalBarList.tsx`
- Create: `web/app/components/charts/TrendLineChart.tsx`

- [ ] **Step 1: HorizontalBarList 작성 (현장별 절감 분포)**

Create `web/app/components/dashboard/HorizontalBarList.tsx`:
```tsx
import { cn } from "@/lib/utils";

interface Item {
  label: string;
  value: number;
  meta?: string;
}

interface Props {
  items: Item[];
  unit: string;
  title?: string;
}

export function HorizontalBarList({ items, unit, title }: Props) {
  const max = Math.max(...items.map((i) => i.value));
  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
      {title && <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light mb-3">{title}</div>}
      <div className="flex flex-col gap-2">
        {items.map((it, i) => (
          <div key={i} className="flex items-center gap-3">
            <div className="w-32 shrink-0 text-xs font-medium text-ink truncate">{it.label}</div>
            <div className="flex-1 h-5 rounded-sm bg-surface-soft overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-lavender to-mint flex items-center justify-end pr-2"
                style={{ width: `${(it.value / max) * 100}%` }}
              >
                <span className="font-mono text-[10px] font-semibold text-white">{it.value}{unit}</span>
              </div>
            </div>
            {it.meta && <div className="w-20 text-right font-mono text-[11px] text-ink-mid">{it.meta}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TrendLineChart 작성 (월별 추세)**

Create `web/app/components/charts/TrendLineChart.tsx`:
```tsx
"use client";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Area, AreaChart } from "recharts";

interface Point {
  month: string;
  value: number;
}

interface Props {
  points: Point[];
  unit: string;
  title?: string;
  valueLabel?: string;
}

export function TrendLineChart({ points, unit, title, valueLabel = "value" }: Props) {
  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
      {title && <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light mb-3">{title}</div>}
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"  stopColor="#1a56db" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#1a56db" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" />
            <XAxis dataKey="month" tick={{ fontSize: 10, fill: "#7a8494" }} />
            <YAxis tick={{ fontSize: 10, fill: "#7a8494" }} tickFormatter={(v) => `${v}${unit}`} />
            <Tooltip
              contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
              formatter={(v: number) => [`${v}${unit}`, valueLabel]}
            />
            <Area type="monotone" dataKey="value" stroke="#1a56db" strokeWidth={2.5} fill="url(#trendGradient)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add web/app/components/dashboard/HorizontalBarList.tsx web/app/components/charts/TrendLineChart.tsx
git commit -m "$(cat <<'EOF'
feat(B): Dashboard — HorizontalBarList (현장별 분포) + TrendLineChart (월별 누적, gradient area)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 40: Dashboard PerformanceTab + ImpactTab (전사)

**Files:**
- Create: `web/app/components/dashboard/PerformanceTab.tsx`
- Create: `web/app/components/dashboard/ImpactTab.tsx`

- [ ] **Step 1: PerformanceTab 작성 (전사용)**

Create `web/app/components/dashboard/PerformanceTab.tsx`:
```tsx
import { KpiStrip, type KpiItem } from "../reports/KpiStrip";
import { SiteOverviewCard } from "./SiteOverviewCard";
import type { Site } from "@/lib/types";

interface Props {
  sites: Site[];
  fleetKpi: { avg_productivity: number; avg_delay: number; abnormal_total: number; recoverable_days: number };
}

export function PerformanceTab({ sites, fleetKpi }: Props) {
  const kpi: KpiItem[] = [
    { label: "전사 평균 생산성", value: `${fleetKpi.avg_productivity}`, unit: "%", sub: "이력 대비 평균", tone: "mint" },
    { label: "평균 공기 격차", value: `+${fleetKpi.avg_delay}`, unit: "일", sub: "전사 평균 지연", tone: "rose" },
    { label: "이상 공종 총합", value: `${fleetKpi.abnormal_total}`, unit: "건", sub: "전사 합계", tone: "rose" },
    { label: "회복 가능 공기", value: `-${fleetKpi.recoverable_days}`, unit: "일", sub: "Optimizer 평균", tone: "lavender" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <KpiStrip items={kpi} />
      <div>
        <div className="mb-3 flex items-baseline gap-2">
          <h3 className="font-display text-base font-bold text-ink">현장별 진척 · 상태</h3>
          <span className="font-mono text-[10px] uppercase tracking-widest text-ink-light">{sites.length} sites</span>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {sites.map((s) => <SiteOverviewCard key={s.id} site={s} />)}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: ImpactTab 작성 (전사용)**

Create `web/app/components/dashboard/ImpactTab.tsx`:
```tsx
import { KpiStrip, type KpiItem } from "../reports/KpiStrip";
import { HorizontalBarList } from "./HorizontalBarList";
import { TrendLineChart } from "../charts/TrendLineChart";
import type { SitesSummary, ImpactSiteDistribution, ImpactTrendPoint, MiddleOfficeAutomation } from "@/lib/types";

interface Props {
  summary: SitesSummary;
  distribution: ImpactSiteDistribution[];
  trend: ImpactTrendPoint[];
  // 현장 레벨일 때만 사용. 전사일 때는 undefined.
  perFunction?: MiddleOfficeAutomation[];
  // 현장 레벨일 때 props 다르게 — 전사용은 summary, 현장용은 단일 site Impact 변환 필요
  scope: "fleet" | "site";
}

export function ImpactTab({ summary, distribution, trend, perFunction, scope }: Props) {
  const kpi: KpiItem[] = scope === "fleet" ? [
    { label: "전체 근무량",  value: `${summary.total_headcount}명`, sub: `${summary.total_hours.toLocaleString()} h/월`, tone: "sky" },
    { label: "월 절감 시간", value: `${summary.total_hours_saved.toLocaleString()}`, unit: "h", sub: "Agent 자동화 효과", tone: "lavender" },
    { label: "FTE 환산",     value: `${summary.total_fte_saved}`, unit: "명", sub: "140h/명 기준", tone: "mint" },
    { label: "AI 업무 대체율", value: `${summary.ai_replacement_rate}`, unit: "%", sub: "절감 ÷ 전체 근무시간", tone: "peach" },
  ] : [
    { label: "현장 근무량",  value: `${summary.total_headcount}명`, sub: `${summary.total_hours.toLocaleString()} h/월`, tone: "sky" },
    { label: "월 절감 시간", value: `${summary.total_hours_saved.toLocaleString()}`, unit: "h", sub: "이 현장 Agent 효과", tone: "lavender" },
    { label: "FTE 환산",     value: `${summary.total_fte_saved}`, unit: "명", sub: "140h/명 기준", tone: "mint" },
    { label: "AI 업무 대체율", value: `${summary.ai_replacement_rate}`, unit: "%", sub: "이 현장 대체율", tone: "peach" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <KpiStrip items={kpi} />

      {scope === "fleet" && (
        <div className="rounded-card border-2 border-mint/30 bg-mint-light/20 px-5 py-3">
          <span className="text-sm">
            <b className="text-mint-text">★ 연간 환산 효과:</b>{" "}
            충원 비용 절감 약 <b className="text-ink">{summary.yearly_saving}억</b>
            <span className="text-ink-mid"> ({summary.total_fte_saved}명 × 1.5억 + 직접 시간 환산)</span>
          </span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {scope === "fleet" ? (
          <HorizontalBarList
            title="현장별 절감 분포"
            unit=" h"
            items={distribution.map((d) => ({ label: d.site_name, value: d.hours_saved, meta: `FTE ${d.fte_saved}` }))}
          />
        ) : perFunction ? (
          <HorizontalBarList
            title="Middle Office 4기능별 자동화율"
            unit="%"
            items={perFunction.map((f) => ({ label: f.function, value: f.rate, meta: `${f.before_hours}h → ${f.after_hours}h` }))}
          />
        ) : null}

        <TrendLineChart
          title={scope === "fleet" ? "월별 누적 FTE 환산" : "도입 후 자동화율 추세"}
          unit={scope === "fleet" ? "명" : "%"}
          valueLabel={scope === "fleet" ? "누적 FTE" : "자동화율"}
          points={
            scope === "fleet"
              ? trend.map((t) => ({ month: t.month, value: t.cumulative_fte }))
              // 현장 레벨에선 trend.cumulative_fte 자리에 자동화율 (fixture는 동일 구조 사용)
              : trend.map((t) => ({ month: t.month, value: t.cumulative_fte }))
          }
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add web/app/components/dashboard/PerformanceTab.tsx web/app/components/dashboard/ImpactTab.tsx
git commit -m "$(cat <<'EOF'
feat(B): Dashboard — PerformanceTab + ImpactTab (전사·현장 scope 분기, 4지표 KPI strip)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 41: Dashboard 전사 page.tsx (기존 코드 교체)

**Files:**
- Modify: `web/app/dashboard/page.tsx`
- Create: `web/app/api/mock/dashboard/route.ts`

- [ ] **Step 1: API 라우트**

Create `web/app/api/mock/dashboard/route.ts`:
```ts
import { NextResponse } from "next/server";
import { loadFixture } from "@/lib/fixtures";

export async function GET() {
  const sites = await loadFixture("sites");
  const dashboard = await loadFixture("dashboard");
  return NextResponse.json({ sites, dashboard });
}
```

- [ ] **Step 2: 기존 dashboard/page.tsx 교체**

Replace `web/app/dashboard/page.tsx`:
```tsx
"use client";
import { useEffect, useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PerformanceTab } from "../components/dashboard/PerformanceTab";
import { ImpactTab } from "../components/dashboard/ImpactTab";
import type { Site } from "@/lib/types";
import type { DashboardFixture } from "@/lib/fixtures";

export default function DashboardPage() {
  const [sites, setSites] = useState<Site[]>([]);
  const [dashboard, setDashboard] = useState<DashboardFixture | null>(null);

  useEffect(() => {
    fetch("/api/mock/dashboard")
      .then((r) => r.json())
      .then(({ sites, dashboard }) => { setSites(sites); setDashboard(dashboard); });
  }, []);

  if (!dashboard) return <div className="px-6 py-10 text-ink-light">Loading...</div>;

  return (
    <div className="flex flex-col">
      <div className="mx-auto w-full max-w-wrap px-6 py-8 md:px-10">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-lavender-text">
            / 05 — Dashboard · Fleet
          </span>
          <span className="h-px w-8 bg-border" />
          <span className="font-mono text-[11px] uppercase tracking-widest text-ink-light">
            Top Mgmt 전용
          </span>
        </div>
        <h1 className="mt-6 font-display text-3xl font-bold tracking-tight text-ink">
          전사 현장 모니터링
        </h1>
        <p className="mt-2 text-sm text-ink-mid">
          현장별 카드를 클릭하면 해당 현장의 상세 대시보드로 이동합니다.
        </p>
      </div>

      <section className="mx-auto w-full max-w-wrap px-6 pb-20 md:px-10">
        <Tabs defaultValue="performance" className="w-full">
          <TabsList className="w-fit">
            <TabsTrigger value="performance">Performance</TabsTrigger>
            <TabsTrigger value="impact">Impact</TabsTrigger>
          </TabsList>
          <TabsContent value="performance" className="mt-6">
            <PerformanceTab sites={sites} fleetKpi={dashboard.performance.fleet_kpi} />
          </TabsContent>
          <TabsContent value="impact" className="mt-6">
            <ImpactTab
              scope="fleet"
              summary={dashboard.impact.fleet_kpi}
              distribution={dashboard.impact.site_distribution}
              trend={dashboard.impact.monthly_trend}
            />
          </TabsContent>
        </Tabs>
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Dev 서버 확인 (관리자 모드로)**

Run: `cd web && npm run dev`
Open: `http://127.0.0.1:5535/` → 페르소나 토글 → 관리자 → Sidebar Dashboard 클릭
Or: `http://127.0.0.1:5535/dashboard`
Expected:
- 상단 탭 (Performance / Impact)
- Performance: 4지표 KPI + 6 현장 카드 그리드 (M15X가 빨간 stripe + ⚠ 이상)
- Impact: 4지표 (480명 / 2,155h / 15.4명 / 3.46%) + 연간 203억 박스 + 현장별 막대 + 월별 추세

- [ ] **Step 4: Commit**

```bash
git add web/app/dashboard/page.tsx web/app/api/mock/dashboard/route.ts
git commit -m "$(cat <<'EOF'
feat(B): Dashboard 전사 page — Performance/Impact 2 탭, 6 SiteOverviewCard 그리드

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 42: Dashboard 현장 드릴다운 page (`/dashboard/sites/[id]`)

**Files:**
- Create: `web/app/dashboard/sites/[id]/page.tsx`
- Create: `web/app/api/mock/dashboard/[id]/route.ts`

- [ ] **Step 1: API 라우트 (현장별 데이터)**

Create `web/app/api/mock/dashboard/[id]/route.ts`:
```ts
import { NextResponse } from "next/server";
import { loadFixture } from "@/lib/fixtures";

export async function GET(_req: Request, { params }: { params: { id: string } }) {
  const sites = await loadFixture("sites");
  const dashboard = await loadFixture("dashboard");
  const report = await loadFixture("report");

  const site = sites.find((s) => s.id === params.id);
  if (!site) return NextResponse.json({ error: "not found" }, { status: 404 });

  // 현장의 S-curve·막대는 report fixture 의 가장 최신 detail 에서 가져옴
  // (PoC: M15X 만 detail 채워져 있음; 다른 현장은 빈 S-curve 로 fallback)
  const latestDate = report.daily[0]?.date;
  const detail = latestDate ? report.details[latestDate] : null;

  const perSiteAutomation = dashboard.impact.per_site_automation[params.id] || dashboard.impact.per_site_automation["m15x-ph3-ibl"] || [];

  return NextResponse.json({ site, detail, perSiteAutomation, trend: dashboard.impact.monthly_trend });
}
```

- [ ] **Step 2: site/[id] page 작성**

Create `web/app/dashboard/sites/[id]/page.tsx`:
```tsx
"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { KpiStrip, type KpiItem } from "../../../components/reports/KpiStrip";
import { SCurveChart } from "../../../components/charts/SCurveChart";
import { BarChartH } from "../../../components/charts/BarChartH";
import { ImpactTab } from "../../../components/dashboard/ImpactTab";
import type { Site, MiddleOfficeAutomation, ImpactTrendPoint, SitesSummary } from "@/lib/types";
import type { ReportDetail } from "@/lib/fixtures";

interface SiteResponse {
  site: Site;
  detail: ReportDetail | null;
  perSiteAutomation: MiddleOfficeAutomation[];
  trend: ImpactTrendPoint[];
}

export default function SiteDashboardPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<SiteResponse | null>(null);

  useEffect(() => {
    fetch(`/api/mock/dashboard/${id}`).then((r) => r.json()).then(setData);
  }, [id]);

  if (!data) return <div className="px-6 py-10 text-ink-light">Loading...</div>;
  const { site, detail, perSiteAutomation, trend } = data;

  const perfKpi: KpiItem[] = [
    { label: "현재 생산성",  value: `${site.productivity_today}`, unit: "%", sub: "이력 대비",         tone: site.productivity_today < 90 ? "rose" : "mint" },
    { label: "현 추세 공기", value: site.delay_days > 0 ? `D+${site.delay_days}` : "정상", unit: site.delay_days > 0 ? "일 지연" : "", sub: site.expected_completion, tone: site.delay_days > 0 ? "rose" : "mint" },
    { label: "회복 가능 생산성", value: site.recovery_days > 0 ? `+${100 - site.productivity_today + site.recovery_days}` : "0", unit: "%p", sub: "Optimizer 목표", tone: "lavender" },
    { label: "최적화 후 공기", value: site.recovery_days > 0 ? `-${site.recovery_days}` : "0", unit: "일 회복", sub: site.recovered_completion, tone: "mint" },
  ];

  const siteImpactSummary: SitesSummary = {
    today_count: 0, review_pending: 0, abnormal_count: site.abnormal_trades, last_updated: "",
    total_hours_saved: site.hours_saved, total_fte_saved: site.fte_saved,
    total_headcount: site.headcount, total_hours: site.total_hours,
    ai_replacement_rate: site.ai_replacement_rate, yearly_saving: 0,
  };

  return (
    <div className="flex flex-col">
      <div className="mx-auto w-full max-w-wrap px-6 py-8 md:px-10">
        <Link href="/dashboard" className="inline-flex items-center gap-1 text-xs font-mono uppercase tracking-widest text-ink-light hover:text-lavender">
          <ChevronLeft className="h-3.5 w-3.5" />
          전사로 돌아가기
        </Link>
        <h1 className="mt-4 font-display text-3xl font-bold tracking-tight text-ink">{site.name}</h1>
        <p className="mt-1 text-sm text-ink-mid">{site.location} · Hi-tech · 현장 모니터링</p>
      </div>

      <section className="mx-auto w-full max-w-wrap px-6 pb-20 md:px-10">
        <Tabs defaultValue="performance" className="w-full">
          <TabsList className="w-fit">
            <TabsTrigger value="performance">Performance</TabsTrigger>
            <TabsTrigger value="impact">Impact</TabsTrigger>
          </TabsList>

          <TabsContent value="performance" className="mt-6 flex flex-col gap-6">
            <KpiStrip items={perfKpi} />
            {detail ? (
              <>
                <div className="rounded-card border border-border-soft bg-card p-5 shadow-xs">
                  <div className="mb-3 font-mono text-[10px] uppercase tracking-widest text-ink-light">
                    S-Curve · 4선 시나리오
                  </div>
                  <SCurveChart points={detail.s_curve} showRecovery />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <BarChartH items={detail.contractor_bars} title="업체별 생산성 (이력 평균)" />
                  <BarChartH items={detail.trade_bars} title="공종별 생산성 (이력 평균)" />
                </div>
              </>
            ) : (
              <div className="rounded-card border border-dashed border-border-soft py-12 text-center text-sm text-ink-light">
                이 현장의 상세 데이터는 다음 fixture 갱신 시 추가됩니다.
              </div>
            )}
          </TabsContent>

          <TabsContent value="impact" className="mt-6">
            <ImpactTab
              scope="site"
              summary={siteImpactSummary}
              distribution={[]}
              trend={trend}
              perFunction={perSiteAutomation}
            />
          </TabsContent>
        </Tabs>
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Dev 서버 확인**

Run: `cd web && npm run dev`
Open (관리자 모드): `http://127.0.0.1:5535/dashboard` → M15X 카드 클릭
Expected: `/dashboard/sites/m15x-ph3-ibl` 로 이동, KPI strip + 4선 S-curve + 막대 + Impact 탭 (자동화 4기능)

- [ ] **Step 4: Commit**

```bash
git add web/app/dashboard/sites web/app/api/mock/dashboard/[id]
git commit -m "$(cat <<'EOF'
feat(B): Dashboard 현장 드릴다운 — Performance(4선 S-curve+막대) + Impact(4기능 자동화율)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 43: 기존 SiteCard 컴포넌트 정리

**Files:**
- Modify: `web/app/components/SiteCard.tsx` (deprecate)

- [ ] **Step 1: 기존 SiteCard 사용처 확인**

Run: `cd web && grep -rn "from.*SiteCard" app/`
Expected: 만약 기존 `dashboard/page.tsx` (옛 Layer 1)에서만 import 됐다면, Task 41에서 page를 다시 작성했으니 미사용. 다른 곳에서 import 됐다면 해당 location 확인.

- [ ] **Step 2: SiteOverviewCard로 대체 완료된 경우 SiteCard 제거**

기존 `web/app/components/SiteCard.tsx`가 더 이상 사용되지 않으면 제거:
```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git rm web/app/components/SiteCard.tsx
```

> 다른 곳에서 여전히 import 한다면 Task 41/42 page를 다시 점검해 SiteOverviewCard로 교체.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore(B): SiteCard.tsx 제거 (Dashboard SiteOverviewCard 로 대체)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 44: Dashboard 사용자 시각 review 체크포인트

**Files:** (수정 없음)

- [ ] **Step 1: Dev 서버 시각 review**

Open: `http://127.0.0.1:5535/dashboard` (관리자 모드)

확인:
- Performance 탭: 6 카드 그리드, M15X가 빨강 stripe + sparkline (rose)
- M15X 클릭 → `/dashboard/sites/m15x-ph3-ibl` 드릴다운, 4선 S-curve + 막대
- 전사 Impact 탭: KPI 4개 (480명 · 2,155h · 15.4명 · 3.46%) + 연간 203억 mint 박스 + 현장별 막대 + 추세
- 현장 Impact 탭: KPI 4개 (현장 단위) + 4기능 자동화율 막대 + 추세

- [ ] **Step 2: 피드백 반영 + 후속 commit**

---

## Phase 8 — Polish + Self-Review (Task 45~47)

### Task 45: 영상 시연 흐름 라이브 시연 점검

**Files:** (수정 없음 — 통합 검증)

- [ ] **Step 1: 영상 흐름 전체 실행**

`cd web && npm run dev` 켜고 다음 흐름 그대로 클릭:

1. http://127.0.0.1:5535/ — Home (Hero · NOW · 7-Agent · CTA)
2. 좌측 사이드바 "Agent Tasks" 클릭 → /tasks
3. 좌측 2026-05-15 선택 (디폴트), 중·우측 진행·Chat 확인
4. 사이드바 "Human Review" → /review, 카드 확정·수정 시연
5. 사이드바 "Report" → /reports, KPI · Forecast · Optimize · Raw Data 탭 순회
6. 상단 페르소나 토글 클릭 (구성원 → 관리자) — Dashboard 메뉴 페이드인
7. 사이드바 "Dashboard" → /dashboard
8. M15X 카드 클릭 → 현장 Dashboard
9. Performance ↔ Impact 탭 전환

각 단계마다 전환·시뮬·반응성이 영상 친화적인지 확인. 한 박자 늦거나 어색하면 메모.

- [ ] **Step 2: 누락 항목 보강**

자주 발견되는 보강 항목:
- 페이지 로딩 시 짧은 깜빡임 → `loading.tsx` 또는 skeleton
- 사이드바 active 표시 누락
- 그라데이션 색 너무 강함 → opacity 조정

피드백 반영 후 추가 commit:
```bash
git commit -m "fix(B): 영상 시연 흐름 폴리싱 — <변경 내용>"
```

---

### Task 46: lint + 타입 체크 + 빌드

**Files:** (검증 단계)

- [ ] **Step 1: 전체 lint**

Run: `cd web && npm run lint`
Expected: No errors. Warning이 있으면 review.

- [ ] **Step 2: TypeScript 컴파일 체크**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: 테스트 실행**

Run: `cd web && npm test`
Expected: 모든 테스트 PASS (Phase 0 useSimulation, persona, fixtures + sanity)

- [ ] **Step 4: Production 빌드**

Run: `cd web && npm run build`
Expected: Build succeed (정적 generation 또는 SSR 페이지 모두)

- [ ] **Step 5: 빌드 결과 dev 모드 비교 점검**

Run: `cd web && npm run start`
Open: `http://127.0.0.1:5535/`
Expected: dev 모드와 시각 동일

- [ ] **Step 6: Commit (변경 없으면 skip)**

만약 빌드 중 발견된 이슈가 있으면 수정 후:
```bash
git commit -m "fix(B): 빌드 호환성 정리"
```

---

### Task 47: design-system.md 갱신

**Files:**
- Modify: `docs/ui/design-system.md`

- [ ] **Step 1: design-system.md §3-3 도메인 컴포넌트 표 갱신**

`docs/ui/design-system.md` §3-3 "우리가 만든 도메인 컴포넌트" 표에 본 plan 에서 작성한 컴포넌트 16종 추가.

기존:
```markdown
| `<SiteCard>` | `app/components/SiteCard.tsx` | ... |
| `<Kpi>` | `app/page.tsx` 내부 | ... |
```

추가할 행 (위치: §3-3 표 안에 append):
```markdown
| `<TopBar>` | `app/components/TopBar.tsx` | 페르소나 토글 + 브랜드 |
| `<Sidebar>` | `app/components/Sidebar.tsx` | 5 메뉴, 페르소나별 필터 |
| `<PersonaToggle>` | `app/components/PersonaToggle.tsx` | 구성원/관리자 switch |
| `<Hero>` `<NowStrip>` `<AgentCard>` `<HilReviewStage>` | `app/components/home/` | Home 4 컴포넌트 |
| `<DailyRunList>` `<AgentProgressList>` `<AgentChatLog>` | `app/components/tasks/` | Agent Tasks 3 컴포넌트 |
| `<WBSTree>` `<ReviewCard>` `<WPSearchCombobox>` | `app/components/review/` | Human Review 3 컴포넌트 |
| `<ReportDailyList>` `<KpiStrip>` `<ForecastTab>` `<OptimizeTab>` `<OptimizerResult>` `<QuadrantCountKpi>` `<RawDataTab>` | `app/components/reports/` | Report 7 컴포넌트 |
| `<PerformanceTab>` `<ImpactTab>` `<SiteOverviewCard>` `<HorizontalBarList>` | `app/components/dashboard/` | Dashboard 4 컴포넌트 |
| `<SCurveChart>` `<BarChartH>` `<QuadrantScatter>` `<TrendLineChart>` | `app/components/charts/` | recharts 차트 4종 |
```

- [ ] **Step 2: §9 "다음 작업 영역" 갱신 — 모두 완료된 시점**

기존 §9 표 (Layer 2 / H-i-L Modal / ProductivityChart 등)을 다음으로 교체:

```markdown
## 9. 후속 작업 (Phase 2 — A_Track 연결)

| 영역 | 현재 | 다음 단계 |
|---|---|---|
| Mock fixture → 실 API | `web/lib/fixtures.ts` 가 `data/mock_*.json` 로드 | A_Track GATE 통과 시 `web/app/api/mock/*` 라우트의 `loadFixture` 호출을 실제 Postgres SELECT / FastAPI proxy 로 swap. mock 과 실 API 의 응답 shape 이 같으므로 컴포넌트는 변경 없음. |
| 현장별 detail 확장 | M15X 만 fixture 채워짐 (PoC 시연 우선) | 다른 5 현장의 detail 도 fixture 또는 실 데이터로 보강 |
| Dashboard 14일 히트맵 | 보류 (spec §10-2) | 사용자 요청 시 wireframe v2 |
| Daily Report 풀스크린 페이지 | 보류 (엑셀 산출물로 충분) | 사용자 요청 시 추가 |
```

- [ ] **Step 3: §10 최종 수정 일자 갱신**

기존 footer:
```
*최종 수정: 2026-05-16 · B_Track ef08ff4 기준*
*다음 갱신: shadcn Dialog/Sheet/Tabs/Sonner add 시점 + Layer 2 골격 도입 시점*
```

다음으로 교체:
```
*최종 수정: 2026-05-16 · 5 화면 구현 완료 + 신규 컴포넌트 30+개 등록*
*다음 갱신: A_Track 데이터 연결 (Phase 2 진입) 시점*
```

- [ ] **Step 4: Commit**

```bash
git add docs/ui/design-system.md
git commit -m "$(cat <<'EOF'
docs(B): design-system.md 갱신 — 5 화면 신규 컴포넌트 30+개 등록 + §9 후속 작업 재정의

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

### Spec Coverage Check

spec `docs/superpowers/specs/2026-05-16-cpia-frontend-screens-design.md` 의 각 섹션이 plan 의 task 로 모두 매핑되는지 확인:

| Spec § | 내용 | Plan 매핑 |
|---|---|---|
| §1 개요 | 영상 시연 + scripted simulation 원칙 | Phase 0 (Task 5 useSimulation hook) + Phase 1 (Task 10 simulation fixture) + 모든 화면 task 의 시뮬 step |
| §2 네비게이션 | 사이드바 + 페르소나 토글 + 5 메뉴 | Task 11 (Sidebar), Task 12 (TopBar + PersonaToggle), Task 4 (persona store) |
| §3-1 Home | Hero + NOW + 7-Agent + HIL Review + CTA | Tasks 15~19 |
| §3-2 Agent Tasks | 3-column + Reporter 1/1 + Chat log | Tasks 20~24 |
| §3-3 Human Review | WBS 트리 + 카드 (상태별 액션) + 검색 + 드래그앤드롭 | Tasks 25~29 |
| §3-4 Report | Daily list + KPI strip + 3 탭 | Tasks 30~37 |
| §3-5 Dashboard | Performance + Impact 2 탭, 전사·현장 드릴다운 | Tasks 38~44 |
| §4 데이터 의존성 매트릭스 | 화면별 🟢/🟡/🔵 분류 | 각 화면 task의 "데이터 소스" 단계 + Phase 1 fixture 작성 |
| §5 점진 연결 전략 (3 Phase) | Phase 1 mock → 2 실 API → 3 snapshot | Phase 1 (Task 6 fixtures.ts) 가 swap 포인트. 본 plan = Phase 1 완수. Phase 2/3 는 Task 47 §9 후속 작업으로 명시 |
| §6 시뮬레이션 시퀀스 | 페이지별 변화 요소·주기 | Task 5 useSimulation/useSequence + Task 10 mock_simulation.json + 각 컴포넌트 task |
| §7 영상 시연 스토리보드 | 컷 흐름 | Task 45 영상 시연 흐름 라이브 시연 점검 |
| §8 디자인 시스템 적용 | design-system.md 단일 출처 | 모든 컴포넌트 task에 명시 + Task 47 (design-system.md 갱신) |
| §9 PoC fixture 정의 | 10개 mock 파일 + 분모 가정치 | Phase 1 전체 (Tasks 6~10) |
| §10 결정 이력 Q1~Q25 | 각 결정이 plan 에 반영 | 모든 task 에 결정 사항 반영 |
| §11 다음 단계 | spec→plan→구현 | 본 plan 이 §11-2 단계. §11-3 (mock 1순위) = Phase 1 |

→ **모든 spec 섹션이 task 로 매핑됨. 누락 없음.**

### Placeholder Scan

- "TBD" / "TODO" / "FIXME": 본 plan 텍스트에는 없음 (예시 코드의 인용·문자열 외)
- "implement later" / "add appropriate error handling": 없음
- "similar to Task N (without code)": 없음 — 모든 task 가 self-contained
- Type 일관성: `Site`, `WBSNode`, `ChatMessage` 등 Task 3 (types.ts) 에서 정의된 타입을 모든 후속 task 가 같은 이름·signature 로 사용

### Scope Check

본 plan 은 5 화면 + 공통 인프라 + fixture + 시뮬 + 차트 = 단일 implementation cycle 범위. 분리 불필요.

---

## 실행 옵션

Plan complete and saved to `docs/superpowers/plans/2026-05-16-cpia-frontend-screens.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 각 task 별로 fresh subagent 가 구현하고 task 간 review 진행. 빠른 반복.

**2. Inline Execution** — 현재 세션에서 task 를 순차 실행 (executing-plans 스킬, checkpoint 단위 review).

**Which approach?**
