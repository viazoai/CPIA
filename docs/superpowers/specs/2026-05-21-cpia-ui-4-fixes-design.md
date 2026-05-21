# CPIA UI 4건 정합화 — Tasks 워크플로우·Reports 차트·Bar 필터·WP 필터 설계

> 2026-05-21 작성. PoC 데모 D-15 (마감 2026-06-05). A_Track 브랜치, 디자인 불가침.

---

## Goal

1년치 더미 적재 (530일, PR #36) 직후 사용자가 UI 시연 중 발견한 4건의 데이터·렌더링 정합 이슈를 **FE 레이어 전용 수정** 으로 해결한다. BE view_builder 산식·PG 적재 데이터 재생성 없이, `web/` 4 파일만 변경.

데모 시점 (조형준 프로 시연) 에서 다음이 성립해야 한다:
- /tasks 우측 워크플로우 패널의 HIL Review ~ Optimizer 단계가 더미일자에서 100% 표시
- /reports 현장 생산성 트렌드 차트가 PG 의 실 90일 시계열로 렌더 (PRNG 가짜 곡선 제거)
- /reports 업체별·공종별 bar 가 150% 초과 제외 + 상위 3 + 하위 7 = 최대 10개로 정리
- /reports WP Summary 표가 위 bar 에 보이는 공종 + impact·productivity 둘 다 0 인 dead row 제외

---

## Non-goals

- view_builder.py `_build_productivity_views` 의 by_contractor / by_l6 cpi 산식 폭주 (몇천%) **수정 자체는 후속**. 본 spec 은 필터링·정렬로 가시성만 회복.
- PG 530일 또는 Chroma 6.8K doc 재적재 없음.
- 디자인 변경 (markup·layout·style 변경) 없음. 데이터 핸들링·필터만.
- AgentWorkflowList / WPSummaryTable 의 표시 구조 (열·바·아이콘) 변경 없음.
- Forecaster·Optimizer 의 더미 일자 산출량 자체 보정 (옵션 3 — `seed_dummy_year.py` 에서 mapping_corrections·optimizer_advice 추가 INSERT) 없음. 산식 단순화로 100% 표시.

---

## Architecture

| Layer | 변경 여부 | 비고 |
|---|---|---|
| PostgreSQL (530일 적재 데이터) | 없음 | `daily_reports`, `pipeline_runs`, `mapper_activities`, `forecasts`, `optimizer_advice` 그대로 사용 |
| `pipeline/` (LangGraph, view_builder.py 등) | 없음 | 산식 폭주는 후속 |
| FastAPI / API contract | 없음 | |
| Next.js API Routes (`/api/mock/report`, `/api/mock/agent-tasks`) | 없음 | 이미 필요한 데이터 다 노출 (`daily` 530건, `kpi_jsonb`, `contractor_bars`, `trade_bars`, `wp_summary`) |
| **Next.js FE 컴포넌트·transforms** | **변경** | 본 spec 의 전체 |

본 spec 의 변경은 **단방향 데이터 변환**. server-side 상태나 schema 변경 없음. 디자인 불가침 가드 (web/components/** markup) 도 모두 통과 — 산술·필터링·prop signature 변경만.

---

## Components — 변경 4건 + 보완 1건

### ① `web/lib/transforms.ts` — `deriveStageProgress` 산식 단순화

현 산식 (transforms.ts:87-180) 의 4개 stage 가 `percent: 0` 하드코딩이라 더미일자 (4-11 ~ 9-24) 에서도 0% 표시 → 사용자가 "다 됐다 치고 한 1년치인데 안 보임" 으로 본 원인.

**새 산식 (각 stage 에 `processed > 0 ? 100 : 0` 단순 룰, 단 HIL·Optimizer 는 검토 대기 있을 때만 pct)**:

| step | agent | percent | waiting_hil |
|---|---|---|---|
| 1 | Collector | `parser_reports > 0 ? 100 : 0` | false |
| 2 | Parser | `parser_acts > 0 ? 100 : 0` | false |
| 3 | Mapper | `pct(mapper, parser)` (현 산식 유지) | false |
| 3.5 | HIL Review | `hil_received === 0 ? 100 : pct(hil_done, hil_received)` | `hil_received > hil_done` (현 산식 유지) |
| 4 | Atomizer | `atomized > 0 ? 100 : 0` | false |
| 5 | Exporter | `exporter > 0 ? 100 : 0` | false |
| 6 | Forecaster | `forecasts_done > 0 ? 100 : 0` | false |
| 7 | Optimizer | `opt_received === 0 ? 100 : pct(opt_done, opt_received)` | false |

**기대 결과**:
- 4-11 ~ 9-24 더미 528일: 모든 stage 100%. (HIL 은 hil_received=0 → 100, Optimizer 도 opt_received<137 이지만 received=0 일 때 100 — anchor 외 더미일자 대부분 opt_received 가 작음, 9-24 처럼 137 > 0 인 일자는 pct 적용해도 32% 등 자연 분포)
- 9-25 anchor: HIL Review 0% (실 462건 검토 대기 노출), Optimizer 100% (25/25). 시연 시 "오늘 들어온 1162건 중 LLM 확신도 낮은 462건이 검토 대기 중" 으로 자연스럽게 설명 가능.

**검증 케이스 (transforms.test.ts 신규)**:
- 9-25 anchor: HIL Review percent=0 waiting_hil=true, Optimizer percent=100
- 9-24 더미: 모든 stage percent=100
- 9-24 처럼 opt_received>0 인 더미: Optimizer 산식이 pct 로 작동 (강제 100 안 됨)
- 빈 일자 (parser_reports=0): 전부 0

---

### ② `web/app/components/charts/ProductivityTrendChart.tsx` — PRNG 제거, 외부 prop

현 코드 (line 50-73) `generateTrend` 가 PRNG (mulberry32, hashString) 으로 90일 가짜 곡선 생성 + 마지막 점만 `todayValue` 강제. 평균 81.1% 도 이 가짜 곡선의 산술 평균이라 PG 실 90일 평균 85.85 와 5pp 어긋남.

**Prop signature 변경**:

```ts
interface Props {
  /** [{date, value}] 90일 시계열 (호출 측이 PG daily 에서 잘라 전달). */
  trend: { date: string; value: number }[];
  /** 끝점 강조용 (마지막 ReferenceDot). 보통 trend[trend.length-1].value 와 같음. */
  todayValue: number;
  endDate: string;
}
```

`siteId` / `daysWindow` prop 삭제. 내부:

```tsx
const data = useMemo(
  () => trend.map((p, i) => {
    const d = new Date(p.date);
    const label = `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return { idx: i, label, value: p.value };
  }),
  [trend],
);
```

`hashString`, `mulberry32`, `generateTrend` 함수 본체 삭제. `avg` 계산식 그대로 유지 (input 만 PRNG → 실 90일로 교체, 자동으로 81.1 → 85.85 표시).

**Edge case**: `trend.length === 0` 시 (selectedDate 가 daily 에 없거나 적재 시작일 근처) 빈 곡선 — `ResponsiveContainer` 안 빈 그래프 + "데이터 부족" 텍스트 X (그대로 빈 차트 노출, 디자인 불가침).

---

### ③ `web/app/(app)/reports/page.tsx` — `trend90` 슬라이스 + `trade_bars` 필터 결과 공유

**`trend90` derivation (page.tsx 헤더 useMemo 추가)**:

```ts
const trend90 = useMemo<{ date: string; value: number }[]>(() => {
  if (!selectedDate || daily.length === 0) return [];
  const idx = daily.findIndex(d => d.date === selectedDate);
  if (idx === -1) return [];
  // /api/mock/report 의 daily 는 ORDER BY report_date DESC (최신 first).
  // selectedDate idx 부터 89개 더 과거 = idx ~ idx+89 (총 90개), 차트 표시 위해 reverse.
  return daily.slice(idx, idx + 90).reverse().map(d => ({
    date: d.date,
    value: d.productivity_today,
  }));
}, [selectedDate, daily]);
```

ProductivityTrendChart 호출 부 (line 124-128) 수정:

```tsx
<ProductivityTrendChart
  trend={trend90}
  todayValue={detail.kpi.productivity_today}
  endDate={selectedDate}
/>
```

**필터 결과 공유 (WP 필터링용)**:

`ProductivityBarToggle` 내부의 `filterAndPickBars` 헬퍼를 외부 함수로 분리 (`web/lib/transforms.ts` 또는 `reports/page.tsx` 내 helper). page.tsx 가 같은 함수로 `visibleTrades` 산출:

```ts
const visibleTrades = useMemo(() => {
  const filtered = filterAndPickBars(detail.trade_bars);
  return new Set(filtered.map(b => b.label));
}, [detail.trade_bars]);

const filteredWpRowsBase = detail.wp_summary.filter(w =>
  visibleTrades.has(w.trade) && (w.impact > 0 || w.productivity > 0)
);

const filteredWpRows = wpStatusFilter === "all"
  ? filteredWpRowsBase
  : filteredWpRowsBase.filter(w => w.status === wpStatusFilter);
```

기존 `filteredWpRows` 로직 (page.tsx:94-97) 교체.

---

### ④ `web/app/components/reports/ProductivityBarToggle.tsx` — 150% 초과 제거 + 상위 3 + 하위 7

`web/lib/transforms.ts` 에 helper 추가:

```ts
// 150% 초과 제거 + value desc 상위 3 + asc 하위 7 = 최대 10개.
// 입력이 10개 이하면 그대로 desc 정렬만.
export function filterAndPickBars<T extends { value: number }>(items: T[]): T[] {
  const cleaned = items.filter(b => b.value <= 150);
  const sorted = [...cleaned].sort((a, b) => b.value - a.value);
  if (sorted.length <= 10) return sorted;
  const top3 = sorted.slice(0, 3);
  const bot7 = sorted.slice(-7);
  return [...top3, ...bot7];
}
```

`ProductivityBarToggle.tsx:59` 의 `items = mode === "contractor" ? contractorBars : tradeBars` 를:

```ts
const items = useMemo(
  () => filterAndPickBars(mode === "contractor" ? contractorBars : tradeBars),
  [mode, contractorBars, tradeBars],
);
```

`avg`, `underCount`, `BarChartH` props (`items`, `groupBoundaries`) 모두 새 `items` 기준. **markup·layout 변경 0**.

**Edge case**:
- 입력 0건: avg=0, underCount=0, BarChartH 빈 상태 그대로 (현 동작과 동일)
- 입력 1~10건 (필터 후): top3+bot7 슬라이스 대신 desc 전체 — 중복 없이 자연스러움
- 모든 항목이 >150 (가능성 낮지만): 결과 0건 → BarChartH 빈 상태

**검증 케이스 (필요시 test 추가)**:
- 9-25 trade_bars (55개, over150=18) → 결과 10개 (top3+bot7), 모두 value ≤ 150
- 9-25 contractor_bars (78개, over150=14) → 결과 10개

---

## Data flow

```
PG daily_reports (530일, anchor 9-25 포함)
   │
   ▼
/api/mock/report → daily[] (530), details[date].{kpi, contractor_bars, trade_bars, wp_summary, ...}
   │
   ▼
reports/page.tsx
   ├─ trend90 = daily.slice(idx, idx+90).reverse() ──► ProductivityTrendChart
   ├─ filterAndPickBars(contractor_bars/trade_bars) ──► ProductivityBarToggle (내부 useMemo)
   ├─ visibleTrades = filterAndPickBars(trade_bars) ──► filteredWpRowsBase = wp_summary.filter(in trade && nonzero)
   └─ filteredWpRows = filteredWpRowsBase + status filter ──► WPSummaryTable
```

```
PG (parser_reports, parser_acts, mapper, hil_received, hil_done, atomized, exporter, forecasts_done, opt_received, opt_done)
   │
   ▼
/api/mock/agent-tasks → progressByDate[date] (stages[] with new percent rules)
   │
   ▼
tasks/page.tsx → AgentWorkflowList (변경 없음, props 그대로)
```

---

## Testing

### transforms.test.ts (신규 또는 기존 파일 확장)

```ts
describe("deriveStageProgress", () => {
  // 더미 일자 시뮬레이션
  test("dummy date (4-11 ~ 9-24): 모든 stage 100%", async () => {
    // mock sql: parser_reports=1, parser_acts=N, mapper=N, hil_received=0, atomized=N, exporter=1, forecasts_done=M, opt_received=K, opt_done=K
    const stages = await deriveStageProgress("2025-09-24");
    expect(stages.map(s => s.percent)).toEqual([100, 100, 100, 100, 100, 100, 100, 100]);
  });

  test("anchor 9-25: HIL Review 0%, Optimizer 100%", async () => {
    const stages = await deriveStageProgress("2025-09-25");
    expect(stages.find(s => s.agent === "HIL Review")?.percent).toBe(0);
    expect(stages.find(s => s.agent === "HIL Review")?.waiting_hil).toBe(true);
    expect(stages.find(s => s.agent === "Optimizer")?.percent).toBe(100);
  });

  test("Optimizer 부분 완료 (opt_d=44/opt_r=137): pct=32", async () => {
    // mock sql 로 9-24 시나리오 (opt_d=44, opt_r=137)
    const stages = await deriveStageProgress("2025-09-24");
    expect(stages.find(s => s.agent === "Optimizer")?.percent).toBe(32);
  });

  test("빈 일자 (parser_reports=0): 모든 stage 0%", async () => { ... });
});
```

### filterAndPickBars (단위 테스트)

```ts
describe("filterAndPickBars", () => {
  test("입력 0건 → 빈 배열", () => expect(filterAndPickBars([])).toEqual([]));
  test("입력 5건 (모두 ≤150) → 5건 desc 정렬", () => { ... });
  test("입력 78건 (over150=14) → 10건 (top3+bot7) 모두 ≤150", () => { ... });
  test("입력 11건 (over150=0) → top3+bot7=10건", () => { ... });
});
```

### UI 검증 (수동 — playwright 캡처)

1. `npm run dev` (5536) → /tasks → 9-24 클릭 → 우측 워크플로우 8 stage 모두 100% 또는 자연 pct
2. /tasks → 9-25 anchor 클릭 → HIL Review = "462건 검토 대기 / 0%", Optimizer = "25건 / 100%"
3. /reports → 9-25 클릭 → 현장 생산성 차트 평탄 (84~88 사이), 평균 85.x%
4. /reports → 9-25 → 업체별 bar 10개 표시, 모두 ≤ 150
5. /reports → 9-25 → 공종별 bar 10개 표시 → WP Summary 약 10~30 행 (impact·prod 0 제외)

콘솔 에러 0 / 타입 체크 통과.

---

## Files touched

| 파일 | 변경 종류 |
|---|---|
| `web/lib/transforms.ts` | `deriveStageProgress` 산식 보정 (4 stage 산식 변경) + `filterAndPickBars` helper 추가 |
| `web/app/components/charts/ProductivityTrendChart.tsx` | PRNG 3 함수 삭제, prop signature 변경 (trend 외부 주입) |
| `web/app/(app)/reports/page.tsx` | `trend90` useMemo 추가, `visibleTrades` 산출, `filteredWpRows` 로직 교체, ProductivityTrendChart prop 갱신 |
| `web/app/components/reports/ProductivityBarToggle.tsx` | `items` 를 `filterAndPickBars` 결과로 감쌈 |
| `web/lib/__tests__/transforms.test.ts` (or 동등) | 신규 또는 확장 |

디자인 가드 확인 명령: `git diff --stat -- 'web/app/components/**' 'web/app/(app)/**'` → markup·className·layout 변경 0. props 변경만.

---

## Decision log

| ID | 결정 | 사용자 답 |
|---|---|---|
| D1 | Stage 산식 — 단순 룰 vs 강제 100 vs 더미 재적재 | **단순 룰** (received>0\|\|processed>0 → 100) |
| D2 | Trend 차트 — PG 실 90일 vs ±45일 vs 차트 제거 | **PG 실 90일** |
| D3 | Bar 필터 — 150% 제거 + top3+bot7 vs 전체 desc vs 4분면만 | **150% 제거 + top3+bot7** |
| D4 | WP 필터 — bar 매칭+nonzero vs nonzero만 vs bar 정확일치 | **bar 매칭 trade AND (impact>0 OR prod>0)** |
| D5 | Trend fetch 방식 — 별도 endpoint vs daily 재활용 | **daily 재활용** (추론, API 변경 0) |
| D6 | 현장 평균 81.1 → 85.85 정합 | **avg 산식 그대로, input 만 PG 실 90일로 교체** (자동 정합) |

---

## Out of scope (후속 작업 후보)

- view_builder `_build_productivity_views` cpi 산식 폭주 수정 (몇천% 값 자체 정정)
- Forecaster·Optimizer 더미 일자 row 채움 (mapping_corrections, optimizer_advice 추가 INSERT — 산식 단순화로 우회 됨)
- 현장 트렌드 차트 변동성 보강 (실 데이터 ±1.5% 평탄 → noise scale 조정)
- BarChartH 자체에 group divider · top3·bot7 시각적 강조 (현재 단순 BarChartH 그대로 사용)
- HIL Review anchor 462건 시연 매크로 (한 번 클릭으로 다 처리되는 데모 흐름)

---

## 참고

- 1년치 적재 PR: #36 (https://github.com/viazoai/CPIA/pull/36)
- 적재 결과: KPI prod 평균 86.01%, 530/530 모두 70~110% 안
- view_builder EVM 산식: `progress = cum_actual_qty/plan_qty_full`, `ev = progress × plan_mh_full`, `ac = cum_actual_mh`, `cpi = ev/ac × 100`
- ANCHOR_SITE_MH_PER_QTY = 5.1747 (anchor 9-25 site mh/qty 실측 상수)

*최종 수정: 2026-05-21*
