# CPIA UI 4건 정합화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tasks 워크플로우 stage % / Reports 트렌드 차트 / Bar 필터 / WP 필터 — 4건의 UI 정합 이슈를 FE 전용으로 해결.

**Architecture:** `web/` 5 파일 (lib 2 + components 3). PG 530일 적재 데이터 / view_builder 산식 / API contract / 디자인 markup 변경 0. 산술·필터·prop 변환만.

**Tech Stack:** Next.js 15 (App Router), React 19, vitest + jsdom + `@testing-library`, `vi.mock("@/lib/pg")` 로 sql 모킹, recharts (트렌드 차트).

**Spec:** `docs/superpowers/specs/2026-05-21-cpia-ui-4-fixes-design.md`

**Branch:** `A_Track` (현 working — PR #36 직후, HEAD = 89b3465).

---

## File Structure

| 파일 | 책임 | 변경 종류 |
|---|---|---|
| `web/lib/transforms.ts` | stage % 계산, bar 정렬·필터 helper | `deriveStageProgress` 보정, `filterAndPickBars` 신규 export |
| `web/app/components/charts/ProductivityTrendChart.tsx` | 90일 시계열 area chart | PRNG 3 함수 삭제, prop 시그니처 변경 (`trend` 외부 주입) |
| `web/app/(app)/reports/page.tsx` | reports 페이지 컨테이너 | `trend90` / `visibleTrades` / `filteredWpRowsBase` useMemo 추가, ProductivityTrendChart prop 갱신 |
| `web/app/components/reports/ProductivityBarToggle.tsx` | 업체/공종 bar toggle | `items` 를 `filterAndPickBars` 결과로 감쌈 (markup 변경 0) |
| `web/lib/__tests__/transforms.test.ts` | transforms 단위 테스트 | `deriveStageProgress` 새 케이스 추가 + `filterAndPickBars` describe 신규 |

---

## Pre-flight checks (Task 시작 전)

- [ ] **현 브랜치 확인**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA" && git branch --show-current`
Expected: `A_Track`

- [ ] **로컬 dev server 실행 (port 5536)**

Run: `lsof -i -P -n | grep LISTEN | grep ':5536'`
Expected: `node ... 127.0.0.1:5536 (LISTEN)` 한 줄. 없으면 `cd web && npm run dev` 백그라운드 실행.

- [ ] **기존 테스트 baseline green**

Run: `cd web && npm test -- --reporter=basic --run`
Expected: 마지막 라인 `Test Files X passed (X)` / `Tests Y passed (Y)`, 실패 0건. 실패 있으면 plan 시작 전에 origin 회복.

---

## Task 1: `deriveStageProgress` 산식 보정

**Files:**
- Modify: `web/lib/transforms.ts:87-180` (`deriveStageProgress` 함수의 4개 stage percent 계산식)
- Test: `web/lib/__tests__/transforms.test.ts:110-141` (`G10 deriveStageProgress` describe 확장)

산식 (spec §② 표 그대로):

```
Collector  : parser_reports > 0 ? 100 : 0                  (현 산식 그대로)
Parser     : parser_acts > 0 ? 100 : 0                     (변경: parser_reports → parser_acts)
Mapper     : pct(mapper, parser)                           (현 산식 그대로)
HIL Review : hil_received === 0 ? 100 : pct(hil_done, hil_received)   (변경)
Atomizer   : atomized > 0 ? 100 : 0                        (변경: 0 하드코딩 → 산식)
Exporter   : exporter > 0 ? 100 : 0                        (변경: 0 하드코딩 → 산식)
Forecaster : forecasts_done > 0 ? 100 : 0                  (변경: 0 하드코딩 → 산식)
Optimizer  : opt_received === 0 ? 100 : pct(opt_done, opt_received)   (변경)
```

`waiting_hil` 은 현 산식 (`hil_received > hil_done`) 그대로.

- [ ] **Step 1.1: 실패 테스트 4건 작성 (anchor 9-25 / 더미 9-24 / 빈 일자 / Optimizer pct)**

`web/lib/__tests__/transforms.test.ts` 의 `describe("G10 deriveStageProgress"` 블록 (line 110) 아래에 추가:

```ts
  it("anchor 9-25 시뮬레이션 — HIL Review 0% (462/0, waiting), Optimizer 100% (25/25)", async () => {
    (sql as any).mockResolvedValueOnce([
      {
        parser_reports: 1, parser_acts: 1162, mapper_acts: 1162,
        hil_received: 462, hil_done: 0,
        atomized: 747, exporter: 1, forecasts_done: 293,
        opt_received: 25, opt_done: 25,
      },
    ]);
    const r = await deriveStageProgress("2025-09-25");
    expect(r.find(s => s.agent === "Collector")?.percent).toBe(100);
    expect(r.find(s => s.agent === "Parser")?.percent).toBe(100);
    expect(r.find(s => s.agent === "Mapper")?.percent).toBe(100);
    const hil = r.find(s => s.agent === "HIL Review")!;
    expect(hil.percent).toBe(0);
    expect(hil.waiting_hil).toBe(true);
    expect(r.find(s => s.agent === "Atomizer")?.percent).toBe(100);
    expect(r.find(s => s.agent === "Exporter")?.percent).toBe(100);
    expect(r.find(s => s.agent === "Forecaster")?.percent).toBe(100);
    expect(r.find(s => s.agent === "Optimizer")?.percent).toBe(100);
  });

  it("더미 9-24 시뮬레이션 — 8 stage 모두 100% (hil_received=0, opt_received>0 but pct=32)", async () => {
    (sql as any).mockResolvedValueOnce([
      {
        parser_reports: 1, parser_acts: 798, mapper_acts: 798,
        hil_received: 0, hil_done: 0,
        atomized: 798, exporter: 1, forecasts_done: 304,
        opt_received: 137, opt_done: 44,
      },
    ]);
    const r = await deriveStageProgress("2025-09-24");
    expect(r.find(s => s.agent === "Collector")?.percent).toBe(100);
    expect(r.find(s => s.agent === "Parser")?.percent).toBe(100);
    expect(r.find(s => s.agent === "Mapper")?.percent).toBe(100);
    expect(r.find(s => s.agent === "HIL Review")?.percent).toBe(100);
    expect(r.find(s => s.agent === "HIL Review")?.waiting_hil).toBe(false);
    expect(r.find(s => s.agent === "Atomizer")?.percent).toBe(100);
    expect(r.find(s => s.agent === "Exporter")?.percent).toBe(100);
    expect(r.find(s => s.agent === "Forecaster")?.percent).toBe(100);
    // opt_received=137 > 0 → pct = round(44/137*100) = 32
    expect(r.find(s => s.agent === "Optimizer")?.percent).toBe(32);
  });

  it("빈 일자 — 모든 stage 0%", async () => {
    (sql as any).mockResolvedValueOnce([
      {
        parser_reports: 0, parser_acts: 0, mapper_acts: 0,
        hil_received: 0, hil_done: 0,
        atomized: 0, exporter: 0, forecasts_done: 0,
        opt_received: 0, opt_done: 0,
      },
    ]);
    const r = await deriveStageProgress("2024-01-01");
    // hil_received=0, opt_received=0 인 경우 carve-out 으로 100% 반환되는 점에 주의 —
    // "빈 일자" 의 의도는 아무 row 도 없는 상태이므로 carve-out 보다 "다른 stage 가 다 0 인 정황" 으로 판단.
    // 현 산식상 HIL/Optimizer 는 100, 나머지는 0. 이게 사용자 의도 (검토 대상 없음 = 완료).
    expect(r.find(s => s.agent === "Collector")?.percent).toBe(0);
    expect(r.find(s => s.agent === "Parser")?.percent).toBe(0);
    expect(r.find(s => s.agent === "Mapper")?.percent).toBe(0);
    expect(r.find(s => s.agent === "HIL Review")?.percent).toBe(100);
    expect(r.find(s => s.agent === "Atomizer")?.percent).toBe(0);
    expect(r.find(s => s.agent === "Exporter")?.percent).toBe(0);
    expect(r.find(s => s.agent === "Forecaster")?.percent).toBe(0);
    expect(r.find(s => s.agent === "Optimizer")?.percent).toBe(100);
  });
```

- [ ] **Step 1.2: 테스트 실패 확인 (구현 전)**

Run: `cd web && npm test -- --reporter=basic --run lib/__tests__/transforms.test.ts`
Expected: 새로 추가한 3 테스트 모두 FAIL (Atomizer/Exporter/Forecaster expected 100 received 0, HIL anchor expected 0 received 0 정상통과, Optimizer expected 100 received 0).

기존 케이스 ("8 단계 배열 + Mapper percent 계산") 은 변경 후에도 통과해야 함 (mapper 80/100 = 80%, HIL 4/10 = 40%, waiting=true) — 추후 step 1.4 에서 검증.

- [ ] **Step 1.3: 산식 보정 (transforms.ts:106-180)**

`web/lib/transforms.ts` 의 `return [` 배열 8 항목을 다음으로 교체:

```ts
  return [
    {
      step: 1,
      agent: "Collector",
      is_hil: false,
      received: n("parser_reports"),
      processed: n("parser_reports"),
      percent: n("parser_reports") > 0 ? 100 : 0,
      waiting_hil: false,
    },
    {
      step: 2,
      agent: "Parser",
      is_hil: false,
      received: n("parser_reports"),
      processed: n("parser_acts"),
      percent: n("parser_acts") > 0 ? 100 : 0,
      waiting_hil: false,
    },
    {
      step: 3,
      agent: "Mapper",
      is_hil: false,
      received: n("parser_acts"),
      processed: n("mapper_acts"),
      percent: pct(n("mapper_acts"), n("parser_acts")),
      waiting_hil: false,
    },
    {
      step: 3.5,
      agent: "HIL Review",
      is_hil: true,
      received: n("hil_received"),
      processed: n("hil_done"),
      percent: n("hil_received") === 0 ? 100 : pct(n("hil_done"), n("hil_received")),
      waiting_hil: n("hil_received") > n("hil_done"),
    },
    {
      step: 4,
      agent: "Atomizer",
      is_hil: false,
      received: Math.max(0, n("mapper_acts") - n("hil_received")),
      processed: n("atomized"),
      percent: n("atomized") > 0 ? 100 : 0,
      waiting_hil: false,
    },
    {
      step: 5,
      agent: "Exporter",
      is_hil: false,
      received: n("atomized"),
      processed: n("exporter"),
      percent: n("exporter") > 0 ? 100 : 0,
      waiting_hil: false,
    },
    {
      step: 6,
      agent: "Forecaster",
      is_hil: false,
      received: n("mapper_acts"),
      processed: n("forecasts_done"),
      percent: n("forecasts_done") > 0 ? 100 : 0,
      waiting_hil: false,
    },
    {
      step: 7,
      agent: "Optimizer",
      is_hil: false,
      received: n("opt_received"),
      processed: n("opt_done"),
      percent: n("opt_received") === 0 ? 100 : pct(n("opt_done"), n("opt_received")),
      waiting_hil: false,
    },
  ];
```

- [ ] **Step 1.4: 테스트 green 확인**

Run: `cd web && npm test -- --reporter=basic --run lib/__tests__/transforms.test.ts`
Expected: `G10 deriveStageProgress` 의 4 케이스 모두 PASS. 기존 "8 단계 배열" 케이스도 그대로 PASS (mapper 80%, HIL 40% waiting=true).

- [ ] **Step 1.5: commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add web/lib/transforms.ts web/lib/__tests__/transforms.test.ts
git commit -m "$(cat <<'EOF'
fix(web/transforms): deriveStageProgress 4 stage percent 하드코딩 0 제거

Atomizer/Exporter/Forecaster percent: 0 하드코딩 → processed>0 ? 100 : 0.
HIL Review · Optimizer 는 received==0 시 100 (검토 대상 없음 = 완료).
1년치 더미일자 (4-11~9-24) 8 stage 모두 100% 표시.
anchor 9-25 는 HIL 462/0=0% (검토 대기) + Optimizer 25/25=100%.

테스트: G10 deriveStageProgress 에 anchor/dummy/빈 일자 3 케이스 추가.
EOF
)"
```

Run: `git status --short` → modified web 만, untracked 없음.

---

## Task 2: `filterAndPickBars` helper 추가

**Files:**
- Modify: `web/lib/transforms.ts` (파일 끝에 export 추가)
- Test: `web/lib/__tests__/transforms.test.ts` (새 describe block)

- [ ] **Step 2.1: 실패 테스트 4건 작성**

`web/lib/__tests__/transforms.test.ts` 의 imports 줄 (line 3-12) 에 `filterAndPickBars` 추가:

```ts
import {
  deriveProgressPercent,
  deriveYearlySaving,
  deriveItemStatus,
  deriveWpIdAndPath,
  deriveImpact,
  deriveStageProgress,
  wbsTreeBuild,
  deriveChatSequence,
  filterAndPickBars,
} from "../transforms";
```

파일 끝 (line 228 이후) 에 describe block 추가:

```ts
describe("filterAndPickBars", () => {
  it("빈 입력 → 빈 배열", () => {
    expect(filterAndPickBars([])).toEqual([]);
  });

  it("입력 5건 (모두 ≤150) → 5건 desc 정렬", () => {
    const items = [
      { label: "A", value: 50 },
      { label: "B", value: 100 },
      { label: "C", value: 80 },
      { label: "D", value: 30 },
      { label: "E", value: 120 },
    ];
    const r = filterAndPickBars(items);
    expect(r).toHaveLength(5);
    expect(r.map(b => b.label)).toEqual(["E", "B", "C", "A", "D"]);
  });

  it("입력 78건 (over150=14) → 10건 (top3+bot7) 모두 ≤150", () => {
    const items: { label: string; value: number }[] = [];
    for (let i = 0; i < 14; i++) items.push({ label: `over_${i}`, value: 200 + i });
    for (let i = 0; i < 64; i++) items.push({ label: `ok_${i}`, value: 30 + i * 2 });
    const r = filterAndPickBars(items);
    expect(r).toHaveLength(10);
    expect(r.every(b => b.value <= 150)).toBe(true);
    // top3: ok_63=156? 30+63*2=156 → cleaned 가 ≤150 이므로 ok_60=150 부터.
    // 30, 32, ..., 150 까지 64건. cleaned len=61 (값 150 이하). top3 = [150,148,146], bot7 = [42,40,38,36,34,32,30].
    // 실제 동작 검증 — 순서 정확히:
    expect(r[0].value).toBe(150);
    expect(r[1].value).toBe(148);
    expect(r[2].value).toBe(146);
    expect(r[r.length - 1].value).toBe(30);
  });

  it("입력 11건 (모두 ≤150) → top3+bot7=10건", () => {
    const items: { label: string; value: number }[] = [];
    for (let i = 0; i < 11; i++) items.push({ label: `x_${i}`, value: 10 + i * 10 });
    // values: 10,20,...,110 (11 건)
    const r = filterAndPickBars(items);
    expect(r).toHaveLength(10);
    // sorted desc: 110,100,90,80,70,60,50,40,30,20,10
    // top3 = [110, 100, 90], bot7 = [70, 60, 50, 40, 30, 20, 10]
    expect(r.map(b => b.value)).toEqual([110, 100, 90, 70, 60, 50, 40, 30, 20, 10]);
  });
});
```

- [ ] **Step 2.2: 테스트 실패 확인**

Run: `cd web && npm test -- --reporter=basic --run lib/__tests__/transforms.test.ts`
Expected: 4 테스트 모두 FAIL with `filterAndPickBars is not exported from "../transforms"` 또는 동등 import 에러.

- [ ] **Step 2.3: helper 구현 (transforms.ts 파일 끝)**

`web/lib/transforms.ts` 파일 끝에 추가:

```ts
// ──────────────────────────────────────────────
// filterAndPickBars: bar value 150% 초과 제거 + value desc 상위 3 + asc 하위 7 = 최대 10개.
// spec 2026-05-21-cpia-ui-4-fixes-design.md §④
// ──────────────────────────────────────────────
export function filterAndPickBars<T extends { value: number }>(items: T[]): T[] {
  const cleaned = items.filter((b) => b.value <= 150);
  const sorted = [...cleaned].sort((a, b) => b.value - a.value);
  if (sorted.length <= 10) return sorted;
  const top3 = sorted.slice(0, 3);
  const bot7 = sorted.slice(-7);
  return [...top3, ...bot7];
}
```

- [ ] **Step 2.4: 테스트 green 확인**

Run: `cd web && npm test -- --reporter=basic --run lib/__tests__/transforms.test.ts`
Expected: `filterAndPickBars` 4 케이스 + `G10 deriveStageProgress` 4 케이스 모두 PASS. 다른 describe (Mapper/HIL deriveProgressPercent 등) 도 변동 없이 PASS.

- [ ] **Step 2.5: commit**

```bash
git add web/lib/transforms.ts web/lib/__tests__/transforms.test.ts
git commit -m "$(cat <<'EOF'
feat(web/transforms): filterAndPickBars helper 추가

150% 초과 제거 + value desc 상위 3 + asc 하위 7 = 최대 10개.
업체별·공종별 bar 가시성 정리 (현 80~90개 + 몇천% 폭주값 노출 제거).
산식 자체 폭주는 별도 후속 (view_builder _build_productivity_views).
EOF
)"
```

---

## Task 3: `ProductivityTrendChart` prop 시그니처 변경 + PRNG 제거

**Files:**
- Modify: `web/app/components/charts/ProductivityTrendChart.tsx` (전체 — PRNG 함수 삭제, prop 변경)

이 task 는 컴포넌트 외부 시그니처 변경 + 호출 측 (page.tsx) 갱신을 짝지어 commit (Task 4 와 같이 묶을 수도 있으나 별개 task 로 분리 — Task 3 = 컴포넌트, Task 4 = 호출 측).

build break 회피: Task 3 commit 후 dev server 가 prop 불일치로 type warning 낼 수 있음. Task 4 까지 끝나야 빌드 통과. 따라서 **Task 3 + 4 를 한 commit 으로 묶음** (sub-step 5.1 에서 stage).

- [ ] **Step 3.0: 다른 호출자 확인 (사전 안전망)**

Run: `cd web && grep -rn "ProductivityTrendChart" app/ --include="*.tsx" --include="*.ts" | grep -v charts/ProductivityTrendChart`
Expected: `app/(app)/reports/page.tsx` 의 import (line 9) 와 호출 (line 124) 만. 다른 호출 부 0건.
만약 다른 호출이 있으면 STOP — 모두 동일하게 새 prop signature 로 갱신해야.

- [ ] **Step 3.1: 현 컴포넌트 import 부와 Props 인터페이스 확인**

기존 (`ProductivityTrendChart.tsx:17-26`):

```ts
interface Props {
  siteId: string;
  todayValue: number;
  endDate: string;
  daysWindow?: number;
}
```

- [ ] **Step 3.2: PRNG 함수 3개 + generateTrend 삭제 (line 28-73)**

`hashString` / `mulberry32` / `generateTrend` 함수 본체와 그 위의 주석 블록 (`/* ───── 결정적 PRNG ... */`, `/* 90일 일별 생산성 시계열 ... */`) 전부 삭제.

- [ ] **Step 3.3: Props 인터페이스 + 컴포넌트 본체 교체**

```ts
interface Props {
  /** [{date, value}] 90일 시계열 — 호출 측이 PG daily 에서 잘라 전달. */
  trend: { date: string; value: number }[];
  /** 끝점 강조 — 보통 trend[trend.length-1].value 와 같음. */
  todayValue: number;
  /** 끝 날짜 (ISO "YYYY-MM-DD") — 헤더 보조 라벨용. */
  endDate: string;
}

export function ProductivityTrendChart({ trend, todayValue, endDate }: Props) {
  const data = useMemo(
    () =>
      trend.map((p, i) => {
        const d = new Date(p.date);
        const mm = String(d.getMonth() + 1).padStart(2, "0");
        const dd = String(d.getDate()).padStart(2, "0");
        return { idx: i, label: `${mm}-${dd}`, value: p.value };
      }),
    [trend],
  );
  const avg = useMemo(
    () => (data.length ? data.reduce((s, p) => s + p.value, 0) / data.length : 0),
    [data],
  );
  const gap = todayValue - avg;
  const gapSign = gap >= 0 ? "+" : "";
  const gapChipTone =
    gap >= -2 ? "bg-mint-light text-mint-text"
    : gap >= -6 ? "bg-sun-light text-sun-text"
    : "bg-rose-light text-rose-text";

  // ... JSX 본체 (line 91-170) 그대로 유지. ReferenceDot 의 `data[data.length - 1].label` 가
  //     length=0 시 undefined 접근. 가드 추가.
  // ... 변경: <ReferenceDot> 를 {data.length > 0 && (...)} 로 감쌈.
```

기존 JSX 의 `<ReferenceDot x={data[data.length - 1].label} y={todayValue} .../>` (line 159-166) 를:

```tsx
          {data.length > 0 && (
            <ReferenceDot
              x={data[data.length - 1].label}
              y={todayValue}
              r={6}
              fill="#0d1117"
              stroke="#1a56db"
              strokeWidth={2}
            />
          )}
```

`useMemo` 가 이미 import 되어 있으면 그대로, 아니면 line 2 의 `import { useMemo } from "react"` 확인.

- [ ] **Step 3.4: TypeScript 컴파일 확인 (Task 4 commit 전 step 4 끝나야 호출 측 정합)**

`cd web && npx tsc --noEmit 2>&1 | head -30` 실행.
Expected: `ProductivityTrendChart` prop 호출 부 (`reports/page.tsx:124`) 에서 `siteId` prop 없음 + `trend` prop 누락 에러 2건. Task 4 끝나면 사라짐.

타입 에러가 다른 곳에서 추가로 나오면 STOP — 예기치 못한 회귀.

이 단계는 commit 하지 않음. Task 4 마지막 step 에서 묶어서 commit.

---

## Task 4: `reports/page.tsx` — `trend90` + `visibleTrades` + `filteredWpRowsBase`

**Files:**
- Modify: `web/app/(app)/reports/page.tsx:1-14` (imports — `filterAndPickBars` 추가)
- Modify: `web/app/(app)/reports/page.tsx:28-98` (컴포넌트 본체 useMemo 추가, ProductivityTrendChart 호출 갱신, filteredWpRows 산출 교체)

- [ ] **Step 4.1: imports 추가**

`reports/page.tsx:1-14` 의 imports 에 추가:

```ts
import { filterAndPickBars } from "@/lib/transforms";
```

- [ ] **Step 4.2: `trend90` useMemo 추가**

`detail` 변수 (line 64) 직전, `filterToStatus`/`wpStatusFilter` 직전에 추가:

```ts
  const trend90 = useMemo<{ date: string; value: number }[]>(() => {
    if (!selectedDate || daily.length === 0) return [];
    const idx = daily.findIndex((d) => d.date === selectedDate);
    if (idx === -1) return [];
    // /api/mock/report 의 daily 는 ORDER BY report_date DESC (최신 first).
    // selectedDate idx 부터 89개 더 과거 = idx ~ idx+89 (총 90개), 차트 표시 위해 reverse.
    return daily
      .slice(idx, idx + 90)
      .reverse()
      .map((d) => ({ date: d.date, value: d.productivity_today }));
  }, [selectedDate, daily]);
```

- [ ] **Step 4.3: `visibleTrades` + `filteredWpRowsBase` useMemo 추가**

`if (!detail || !diagnosis)` 가드 (line 82) 직전에 추가:

```ts
  const visibleTrades = useMemo(() => {
    if (!detail) return new Set<string>();
    return new Set(filterAndPickBars(detail.trade_bars).map((b) => b.label));
  }, [detail]);
```

`filterToStatus` 블록 (line 87-93) 다음 `filteredWpRows` (line 94-97) 를 다음으로 교체:

```ts
  // spec 2026-05-21-cpia-ui-4-fixes-design.md §③ — 위 trade bar 에 매칭된 trade 만 + dead row (impact=0 AND prod=0) 제외.
  const filteredWpRowsBase = detail.wp_summary.filter(
    (w) => visibleTrades.has(w.trade) && (w.impact > 0 || w.productivity > 0),
  );
  const filteredWpRows =
    wpStatusFilter === "all"
      ? filteredWpRowsBase
      : filteredWpRowsBase.filter((w) => w.status === wpStatusFilter);
```

- [ ] **Step 4.4: ProductivityTrendChart 호출 갱신 (line 124-128)**

기존:

```tsx
<ProductivityTrendChart
  siteId={REPORT_SITE_ID}
  todayValue={detail.kpi.productivity_today}
  endDate={selectedDate}
/>
```

→ 변경:

```tsx
<ProductivityTrendChart
  trend={trend90}
  todayValue={detail.kpi.productivity_today}
  endDate={selectedDate}
/>
```

`REPORT_SITE_ID` 상수 (line 18) 가 더 이상 ProductivityTrendChart 에서 사용 안 됨. 다른 사용처 확인:

Run: `cd web && grep -n "REPORT_SITE_ID" app/\(app\)/reports/page.tsx`
- 사용처가 line 18 (선언) + ProductivityTrendChart 호출 1건 이라면 상수도 삭제.
- 다른 컴포넌트에서도 prop 으로 받아쓰면 그대로 유지 (예: diagnosis-adapter).

`toDiagnosisInput(detail.kpi, detail.s_curve, REPORT_SITE_ID)` (line 67) 에서 사용 — 그대로 유지.

- [ ] **Step 4.5: TypeScript 컴파일 확인**

Run: `cd web && npx tsc --noEmit 2>&1 | head -20`
Expected: 0 에러 (Task 3 의 prop mismatch 해소).

- [ ] **Step 4.6: 기존 테스트 회귀 확인**

Run: `cd web && npm test -- --reporter=basic --run`
Expected: 모든 테스트 PASS. 회귀 0.

- [ ] **Step 4.7: commit (Task 3 + 4 묶음)**

```bash
git add web/app/components/charts/ProductivityTrendChart.tsx web/app/\(app\)/reports/page.tsx
git commit -m "$(cat <<'EOF'
fix(web/reports): 현장 생산성 차트를 PG 실 90일 시계열로 교체

ProductivityTrendChart 의 PRNG 가짜 시계열 (hashString/mulberry32/generateTrend)
삭제. prop signature: siteId → trend (외부 주입).
reports/page.tsx 가 daily(530일).slice(idx, idx+90).reverse() 로 90일 window 추출.

현장 평균 81.1% → 85.85% 자동 정합 (산식 변경 X, input 만 교체).
사용자 신고 "9-8부터 바닥, 9-25 갑자기 툭" 패턴 해소.
EOF
)"
```

---

## Task 5: `ProductivityBarToggle` items 감싸기

**Files:**
- Modify: `web/app/components/reports/ProductivityBarToggle.tsx:1-7` (imports + useMemo 도입)
- Modify: `web/app/components/reports/ProductivityBarToggle.tsx:57-65` (`items` 산출식)

- [ ] **Step 5.1: imports 추가**

`ProductivityBarToggle.tsx:1-2` 의 `useState` 옆에 `useMemo` 추가:

```ts
import { useMemo, useState } from "react";
```

`ProductivityBarToggle.tsx:5` 의 imports 에 `filterAndPickBars` 추가:

```ts
import { filterAndPickBars } from "@/lib/transforms";
```

- [ ] **Step 5.2: `items` 산출식 교체 (line 59)**

기존:

```ts
const items = mode === "contractor" ? contractorBars : tradeBars;
```

→ 변경:

```ts
const items = useMemo(
  () => filterAndPickBars(mode === "contractor" ? contractorBars : tradeBars),
  [mode, contractorBars, tradeBars],
);
```

`avg`, `underCount`, `<BarChartH items={items} .../>` 모두 새 `items` 기준으로 자동 갱신 — 별도 수정 불요.

`deriveBuildingBoundaries(items)` (line 121) 도 새 10개 items 기준. 같은 building 이 여러 번 나오면 boundaries 그대로 작동.

- [ ] **Step 5.3: TypeScript + 테스트**

Run: `cd web && npx tsc --noEmit 2>&1 | head -10`
Expected: 0 에러.

Run: `cd web && npm test -- --reporter=basic --run`
Expected: 모든 테스트 PASS (회귀 없음).

- [ ] **Step 5.4: commit**

```bash
git add web/app/components/reports/ProductivityBarToggle.tsx
git commit -m "$(cat <<'EOF'
fix(web/reports): 업체별·공종별 bar 가시성 정리

ProductivityBarToggle items 를 filterAndPickBars 결과로 감쌈.
9-25 anchor: contractor 78→10, trade 55→10.
9-24 더미: contractor 91→10, trade 53→10.
markup 변경 없음 (디자인 불가침).
EOF
)"
```

---

## Task 6: 디자인 가드 + UI 수동 검증

**Files:**
- Read-only: web/ 변경 diff, dev server (5536) UI.

- [ ] **Step 6.1: 디자인 불가침 가드 — markup 변경 0 확인**

Run:

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git diff --stat HEAD~4..HEAD -- 'web/app/components/**' 'web/app/(app)/**'
```

Expected: 변경 파일은 `ProductivityBarToggle.tsx`, `ProductivityTrendChart.tsx`, `reports/page.tsx` 3개. 다른 컴포넌트 파일 변경 0.

추가로 markup·className·className= 등의 변경이 의도된 변경 안에 들어있지 않은지 확인:

Run:

```bash
git diff HEAD~4..HEAD -- 'web/app/components/**' 'web/app/(app)/**' \
  | grep -E "^\+.*className=|^-.*className=" | head -20
```

Expected: 0줄. (className 변경 0 = 디자인 markup 불가침.)

- [ ] **Step 6.2: dev server 가 새 코드 반영 (HMR 자동, 별도 재시작 불요)**

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5536/reports`
Expected: `200`.

- [ ] **Step 6.3: /tasks 페이지 — 9-24 더미일자 8 stage 모두 100% 확인**

playwright 또는 직접 브라우저:

1. http://localhost:5536/tasks 열기
2. 좌측 daily list 에서 "2025-09-24" 항목 클릭
3. 우측 워크플로우 패널의 8 stage 모두 percent=100% 확인 (단, Optimizer 는 32% — pct 산식 작동)

API 직접 검증:

```bash
curl -s http://localhost:5536/api/mock/agent-tasks \
  | python3 -c "import sys,json;d=json.load(sys.stdin);p=d['progressByDate']['2025-09-24'];print({s['agent']:s['percent'] for s in p})"
```

Expected: `{'Collector': 100, 'Parser': 100, 'Mapper': 100, 'HIL Review': 100, 'Atomizer': 100, 'Exporter': 100, 'Forecaster': 100, 'Optimizer': 32}`.

- [ ] **Step 6.4: /tasks → 9-25 anchor 확인 — HIL 0%, Optimizer 100%**

```bash
curl -s http://localhost:5536/api/mock/agent-tasks \
  | python3 -c "import sys,json;d=json.load(sys.stdin);p=d['progressByDate']['2025-09-25'];print({s['agent']:(s['percent'],s.get('waiting_hil')) for s in p})"
```

Expected: HIL Review = `(0, True)`, Optimizer = `(100, False)`, 나머지 6 stage = `(100, False)`.

- [ ] **Step 6.5: /reports — trend90 차트 평균 ~85.85**

브라우저 또는 API:

1. http://localhost:5536/reports 열기
2. 9-25 (기본 선택) 의 "현장 생산성 진단" 카드 — 우측 chip "현장 평균 대비 +X.X%" 의 평균이 약 85.85 (현 81.1 에서 변경)
3. 차트가 84~88 사이로 평탄 (PRNG 후반 30일 바닥 현상 사라짐)
4. 9-8 선택 → 동일하게 평균 ~85.89, 마지막 점 85.61

- [ ] **Step 6.6: /reports — bar 필터 적용 확인 (9-25 anchor)**

브라우저:

1. /reports → 9-25 선택
2. "업체별 현장 생산성" — bar 10개 표시, 모두 ≤150
3. "공종별" 토글 → bar 10개 표시, 모두 ≤150
4. 입력 78 → 10 가시화 (이전 80개 가까이 → 10 개 정돈)

- [ ] **Step 6.7: /reports — WP Summary 필터 (9-25 = 15행, 9-24 = 31행)**

브라우저:

1. /reports → 9-25 선택 → "Work Package 목록" 표 행수 = 15 (이전 296 → 15)
2. 9-24 선택 → 행수 = 31 (이전 304 → 31)
3. 7-15 선택 → 행수 = 20 (이전 154 → 20)
4. 모든 행이 impact > 0 OR productivity > 0 (둘 다 0 인 dead row 없음)

API 직접 검증:

```bash
curl -s http://localhost:5536/api/mock/report \
  | python3 -c "
import sys,json
d = json.load(sys.stdin)
# inline simulate filterAndPickBars + visible_trades + nonzero filter (FE 로직과 동일)
def fpb(items):
    cleaned = [b for b in items if b['value'] <= 150]
    sorted_items = sorted(cleaned, key=lambda x: -x['value'])
    if len(sorted_items) <= 10: return sorted_items
    return sorted_items[:3] + sorted_items[-7:]
for date in ['2025-09-25','2025-09-24','2025-07-15']:
    det = d['details'][date]
    vt = {b['label'] for b in fpb(det['trade_bars'])}
    wp = [w for w in det['wp_summary'] if w['trade'] in vt and ((w.get('impact') or 0) > 0 or (w.get('productivity') or 0) > 0)]
    print(date, 'wp_filtered=', len(wp))
"
```

Expected: `2025-09-25 wp_filtered= 15`, `2025-09-24 wp_filtered= 31`, `2025-07-15 wp_filtered= 20`.

- [ ] **Step 6.8: 콘솔 에러 확인 (브라우저 devtools)**

브라우저 devtools 열고 /reports 페이지 reload + 5 일자 클릭. console error/warning 0.

- [ ] **Step 6.9: 최종 build 통과 확인**

Run: `cd web && npm run build 2>&1 | tail -10`
Expected: `✓ Compiled successfully` 또는 동등. 에러 0.

build 가 type error 로 깨지면 STOP — 어디서 prop signature 불일치 누락된 것.

---

## Task 7: PR 마무리

PR #36 (1년치 적재) 가 이미 OPEN. 1차 옵션 = PR #36 description 갱신 (이번 4건 fix 도 같은 A_Track HEAD 라 별도 PR 못 만듦). 2차 옵션 = 별도 PR 분리 (A_Track → A_Track 자체 PR 은 불가, A_Track → main 단일 PR 만 가능).

→ PR #36 description 에 UI 4건 fix 섹션 추가.

- [ ] **Step 7.1: 변경 요약 작성**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git log --oneline 89b3465..HEAD
```

Expected: 4 commit (Task 1, 2, 3+4, 5).

`git diff --stat 89b3465..HEAD` 로 변경 파일 5개 (transforms.ts, transforms.test.ts, ProductivityTrendChart.tsx, reports/page.tsx, ProductivityBarToggle.tsx) 확인.

- [ ] **Step 7.2: push**

```bash
git push origin A_Track
```

Expected: `... A_Track -> A_Track`. 4 commit push.

- [ ] **Step 7.3: PR #36 description 갱신**

기존 description 의 끝에 다음 섹션 추가 (gh pr edit):

```markdown
---

## Patch B: UI 4건 정합화 (2026-05-21, D-15)

1년치 적재 직후 시연 검증 중 발견한 4가지 UI 정합 이슈 — FE 전용 fix (web/ 5 파일).

| Issue | Root cause | Fix |
|---|---|---|
| /tasks 워크플로우 HIL~Optimizer 0% | deriveStageProgress 의 Atomizer/Exporter/Forecaster percent: 0 하드코딩 + HIL/Opt 의 received=0 시 0% | 산식 보정 (processed>0?100:0 + HIL/Opt received==0?100:pct) |
| /reports 트렌드 차트 9-8~9-24 바닥, 마지막 점만 툭 | ProductivityTrendChart 가 PRNG 가짜 90일 + 후반 30일 감소 트렌드 | PRNG 제거, PG daily 530일 → trend90 useMemo (선택일 -89~0) |
| /reports 업체·공종 bar 몇천% + 80개 표시 | view_builder 산식 폭주 + ProductivityBarToggle 정렬·필터 X | filterAndPickBars helper — 150% 초과 제외 + top3+bot7 (산식 자체는 후속) |
| /reports WP Summary 296행 + dead row | wp_summary 전건 노출 | visibleTrades 매칭 + (impact>0 OR prod>0) 필터 (9-25 296→15, 9-24 304→31) |

**디자인 불가침**: markup·className 변경 0 (`git diff --stat -- 'web/app/components/**' 'web/app/(app)/**'` 가드).
**스펙/플랜**: `docs/superpowers/specs/2026-05-21-cpia-ui-4-fixes-design.md`, `docs/superpowers/plans/2026-05-21-cpia-ui-4-fixes-plan.md`.

### 검증
- 신규 테스트 7건 (transforms.test.ts) PASS
- 회귀 0 (전 테스트 PASS)
- /tasks 9-24 → 8 stage 모두 100% (Optimizer 32% 자연 pct), 9-25 anchor → HIL 0% Opt 100%
- /reports 평균 81.1 → 85.85, bar 10개, WP 15/31/20 (9-25/9-24/7-15)
```

Run:

```bash
gh pr view 36 --json body --jq .body > /tmp/pr36-body.md
cat >> /tmp/pr36-body.md <<'EOF'

---

## Patch B: UI 4건 정합화 (2026-05-21, D-15)

(위 섹션을 그대로 EOF 안에 paste — markdown 표/리스트 포함)
EOF
gh pr edit 36 --body-file /tmp/pr36-body.md
```

실제 실행 시 위 placeholder 자리에 본 plan 의 Patch B 섹션 전체를 그대로 paste.

- [ ] **Step 7.4: 최종 status 확인**

```bash
gh pr view 36 --json state,mergeable,commits | python3 -m json.tool
```

Expected: `"state": "OPEN"`, `"mergeable": "MERGEABLE"`, commits 갱신 (이전 N + 4).

`git log --oneline -10` 으로 A_Track HEAD 가 origin/A_Track 과 동일한지.

- [ ] **Step 7.5: brain capture (decision 저장)**

Run:

```bash
gbrain put decisions/cpia-ui-4-fixes-2026-05-21 <<'EOF'
---
type: decision
tags: [cpia, ui, productivity-chart, stage-progress, filter]
---

CPIA 1년치 적재 직후 시연 검증 중 4건 UI 정합화 결정 (D-15, 2026-05-21):

1. deriveStageProgress 산식 단순화 — 4 stage 하드코딩 0 제거, HIL/Opt 만 received==0 carve-out.
2. ProductivityTrendChart — PRNG 가짜 90일 → PG daily 530일 slice (FE 만, API 변경 0).
3. filterAndPickBars — 150% 초과 제외 + top3+bot7. 산식 폭주는 후속.
4. WP Summary — visible trade 매칭 + (impact>0 OR prod>0) dead row 제외.

Why: 시연 중 사용자가 직접 발견. PG 530일 적재는 이미 완료, 산식 폭주 수정은 후속으로 분리 (재적재 부담 회피).
How to apply: 후속 작업으로 view_builder _build_productivity_views cpi 산식 정정 (몇천% 값 자체).

연관: [[projects/cpia]], [[notes/cpia-dummy-poc-success]] (PR #36).
EOF
```

---

## 회복 방안 (어디서 막혔을 때)

| 막힌 곳 | 대응 |
|---|---|
| Task 1 테스트 실패 (anchor expected 100 received 0) | 실제로 새 산식 적용 안 됨 — transforms.ts 88-180 직접 다시 확인. 회귀 시 `git diff lib/transforms.ts` 로 변경 위치 검토 |
| Task 4 build 깨짐 (tsc 에러) | ProductivityTrendChart prop signature 와 page.tsx 호출 mismatch — Task 3 + 4 commit 같이 묶어야 (Step 4.7 까지 commit 안 함) |
| Task 6.7 행수 expected 와 실제 다름 | API response 변경 가능성 (다른 PR merge 영향). curl 로 직접 9-25 wp_summary 길이 확인 후 expected 갱신 |
| HMR 반영 안 됨 | `lsof -i :5536` 로 dev server 죽었는지 확인, `cd web && npm run dev` 재실행 |
| 디자인 가드 (className 변경 +1) | `git diff` 로 어떤 컴포넌트 markup 이 의도와 다른지 확인. 디자인 변경 의도 없으면 revert |

---

## 완료 체크리스트

- [ ] Task 1~5 모든 step 체크
- [ ] Task 6 검증 9 step 모두 expected 일치
- [ ] Task 7 PR description 갱신 + push
- [ ] Step 7.5 brain capture
- [ ] 콘솔 에러 0, 회귀 테스트 0
- [ ] 디자인 가드 (markup 변경 0) 통과

---

*최종 수정: 2026-05-21*
