# CPIA UI 개선 (Review 탭 + 보고서 탭) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Review 탭의 공종-클릭-빈칸 버그를 누적 등록 노드별 lazy fetch + HIL/등록 토글 자동전환으로 고치고, 보고서 탭 WP목록·권고·시나리오 그래프를 데모용으로 다듬는다.

**Architecture:** 전부 `web/`(Next.js 14 App Router) 안. 신규 API 라우트 1개(노드별 누적 등록)와 순수 헬퍼 2개(`wp-format`, `review-node`)를 TDD로 만들고, 기존 컴포넌트(WPSummaryTable·OptimizerResult·ReviewCard·ForecastChart·review/page·reports/page)를 수술적으로 수정한다. 순수 로직은 vitest 단위테스트, 컴포넌트는 @testing-library, 라우트는 curl 통합검증, 인터랙션(줌·라인클릭)은 typecheck + 5537 수동 e2e.

**Tech Stack:** Next.js 14, TypeScript, React 18, recharts 3.8.1, vitest + @testing-library/react(jsdom), porsager `postgres`(`@/lib/pg`).

**근거 spec:** `docs/superpowers/specs/2026-06-02-cpia-ui-review-report-refinement-design.md` (5-렌즈 리뷰 2회전 통과, 실 코드 file:line + 실 데이터 검증).

---

## 공통 규칙 (모든 task)

- **테스트:** 단일 파일 `npx vitest run <path>`, 전체 `npm test`. (vitest.config.ts: jsdom·globals·`@`→루트 alias·`vitest.setup.ts`가 `@/lib/pg`를 전역 mock.)
- **⚠️ 선재(pre-existing) 실패 baseline:** 작업 시작 전 `npm test`는 이미 4건 실패 — `tests/persona.test.ts`(3, `storage.setItem` jsdom), `tests/diagnosis.test.ts`(1, pessimistic 단언), 그리고 `e2e/*.spec.ts`(Playwright 파일이 vitest에 잡혀 컬렉션 실패). **이건 본 작업과 무관.** 게이트는 "내가 만든/수정한 테스트 파일이 그린" + "선재 실패 외에 새 실패를 추가하지 않음"으로 판정한다. 선재 실패를 고치려 들지 말 것(스코프 밖).
- **타입체크:** `npx tsc --noEmit`. **`npm run build`(next build) 금지** — dev 서버와 `.next`를 공유해 실행 중 dev(5537)를 깬다. 데모 반영은 사용자 지시 시 루트에서 `make build`.
- **dev 서버:** `npm run dev2`(127.0.0.1:5537)에서 수동 e2e. 이미 떠 있으면 재사용.
- **커밋:** 작은 단위. 메시지 끝에 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. **push 안 함**(사용자 명시 지시 시에만).
- **스타일/디자인 불가침:** spec에 적힌 컬럼·KPI·인터랙션·문구 외 markup/스타일 골격 보존. 한자 금지.
- **두 wp 컨벤션 주의:** 보고서 `wp_summary`는 `wp_id="{wa}-{trade}-{company}"`·`wp_name="{trade} · {WA}"`. Review는 `deriveWpIdAndPath`(transforms.ts:61)로 `wp_id="{wa}-{l6_main}"`·`wp_name="{wa} {l6_main}"`. `waCode` 헬퍼는 **보고서 전용**, registered 라우트는 raw `ma.wa/l5_disc/l6_main` 필터.

## File Structure

| 파일 | 책임 | task |
|------|------|------|
| `web/lib/wp-format.ts` (신규) | 보고서 WP 표시 순수함수: `waCode`, `parseDelayDays` | 1 |
| `web/lib/types.ts` | `WPSummaryRow.delay_days?` 추가 | 2 |
| `web/app/components/reports/WPSummaryTable.tsx` | WP목록 컬럼 재구성(B1/B2/B4) | 2 |
| `web/app/(app)/reports/page.tsx` | delay_days FE 주입(B3) | 3 |
| `web/app/components/reports/OptimizerResult.tsx` | 권고 줄바꿈 수정(B5) | 4 |
| `web/app/components/charts/ForecastChart.tsx` | KPI/카드 정리·줌·라인클릭(C1-C4) | 5,6,7 |
| `web/app/api/mock/review/registered/route.ts` (신규) | 노드별 누적 등록 fetch(A1) | 8 |
| `web/lib/review-node.ts` (신규) | `nodeToQuery` 순수함수(A4) | 9 |
| `web/app/components/review/ReviewCard.tsx` | `readOnly` prop(A5) | 10 |
| `web/app/(app)/review/page.tsx` | 토글 자동전환·registered 배선·빈상태(A2/A3/A4/A6) | 11 |
| `web/lib/__tests__/` 또는 `web/tests/` | 각 신규 테스트 | 1,2,4,9,10 |

---

# Phase 1 — 보고서 탭

### Task 1: 순수 헬퍼 `lib/wp-format.ts` (B3·B4 기반)

**Files:**
- Create: `web/lib/wp-format.ts`
- Test: `web/tests/wp-format.test.ts`

- [ ] **Step 1: 실패 테스트 작성** — `web/tests/wp-format.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { waCode, parseDelayDays } from "@/lib/wp-format";

describe("waCode", () => {
  it("wp_name '{trade} · {WA}' 에서 WA 추출", () => {
    expect(waCode({ wp_name: "철근콘크리트공사 · CUB", wp_id: "cub-철근콘크리트공사-남웅건설" })).toBe("CUB");
    expect(waCode({ wp_name: "배수 공사 · FAB", wp_id: "fab-배수-공사-장평건설" })).toBe("FAB");
  });
  it("wp_name 에 ' · ' 없으면 wp_id 첫 세그먼트 대문자 폴백", () => {
    expect(waCode({ wp_name: "이상한이름", wp_id: "fab-x-y" })).toBe("FAB");
  });
});

describe("parseDelayDays", () => {
  it("'N일 지연' → N", () => {
    expect(parseDelayDays([{ label: "일정 영향", value: "5일 지연" }])).toBe(5);
  });
  it("'일정 충족' / 라벨없음 / undefined → 0", () => {
    expect(parseDelayDays([{ label: "일정 영향", value: "일정 충족" }])).toBe(0);
    expect(parseDelayDays([{ label: "다른", value: "3일 지연" }])).toBe(0);
    expect(parseDelayDays(undefined)).toBe(0);
  });
});
```

- [ ] **Step 2: 실패 확인** — `npx vitest run tests/wp-format.test.ts` → FAIL ("Cannot find module '@/lib/wp-format'").

- [ ] **Step 3: 구현** — `web/lib/wp-format.ts`

```ts
import type { WPSummaryRow } from "@/lib/types";

/** 보고서 WP목록 맨 왼쪽 Work Area 코드(CUB/FAB).
 *  wp_name "{trade} · {WA}" 의 마지막 토큰 우선, 없으면 wp_id "{wa}-…" 첫 세그먼트 대문자. (13행 정합 검증됨.) */
export function waCode(row: Pick<WPSummaryRow, "wp_name" | "wp_id">): string {
  if (row.wp_name && row.wp_name.includes(" · ")) {
    return row.wp_name.split(" · ").pop()!.trim();
  }
  if (row.wp_id) return row.wp_id.split("-")[0].toUpperCase();
  return "—";
}

/** optimizer.by_wp[wp_id].details 의 "일정 영향" 라벨에서 지연일수 추출.
 *  "5일 지연"→5, "일정 충족"/미매칭/항목없음→0. (옵티마이저 카드와 동일 SSOT.) */
export function parseDelayDays(details: { label: string; value: string }[] | undefined): number {
  if (!details) return 0;
  const d = details.find((x) => x.label === "일정 영향");
  if (!d) return 0;
  const m = /(\d+)\s*일\s*지연/.exec(d.value);
  return m ? Number(m[1]) : 0;
}
```

- [ ] **Step 4: 통과 확인** — `npx vitest run tests/wp-format.test.ts` → PASS (4 tests).

- [ ] **Step 5: 커밋**

```bash
git add web/lib/wp-format.ts web/tests/wp-format.test.ts
git commit -m "feat(report): WP 표시 순수헬퍼 waCode·parseDelayDays (B3/B4)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: WP목록 컬럼 재구성 (B1·B2·B4)

`WPSummaryTable.tsx`: 컬럼을 **Work Area · 공종 · BP사 · 지연일 · 단축가능일 · Status** 로. `lib/types.ts`에 `delay_days?` 추가.

**Files:**
- Modify: `web/lib/types.ts` (WPSummaryRow, 337-356 부근)
- Modify: `web/app/components/reports/WPSummaryTable.tsx` (헤더 37-43, 본문 58-92)
- Test: `web/tests/wp-summary-table.test.tsx`

- [ ] **Step 1: 타입 추가** — `lib/types.ts` `WPSummaryRow` 인터페이스에 한 줄:

```ts
  recovery_days?: number;  // 기존
  delay_days?: number;     // FE-augment (reports/page.tsx 가 optimizer 에서 주입, B3). BE jsonb 아님.
```

- [ ] **Step 2: 실패 테스트 작성** — `web/tests/wp-summary-table.test.tsx`

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { WPSummaryTable } from "@/app/components/reports/WPSummaryTable";
import type { WPSummaryRow } from "@/lib/types";

const row: WPSummaryRow = {
  wp_id: "cub-철근콘크리트공사-남웅건설", wp_name: "철근콘크리트공사 · CUB",
  trade: "철근콘크리트공사", bp_name: "남웅건설", start_date: "", end_date: "",
  progress_pct: 0, productivity: 10, impact: 36, baseline: 100, status: "caution",
  recovery_days: 5, delay_days: 5,
};

describe("WPSummaryTable", () => {
  it("Impact·Productivity 헤더 없음, Work Area·지연일·단축 가능일 헤더 있음", () => {
    render(<WPSummaryTable rows={[row]} selectedWpId={null} onSelect={() => {}} />);
    expect(screen.queryByText("Impact")).toBeNull();
    expect(screen.queryByText("Productivity")).toBeNull();
    expect(screen.getByText("Work Area")).toBeTruthy();
    expect(screen.getByText("지연일")).toBeTruthy();
    expect(screen.getByText("단축 가능일")).toBeTruthy();
  });
  it("맨 왼쪽 셀이 WA 코드(CUB), 지연일 +5일", () => {
    render(<WPSummaryTable rows={[row]} selectedWpId={null} onSelect={() => {}} />);
    expect(screen.getByText("CUB")).toBeTruthy();
    expect(screen.getByText("+5일")).toBeTruthy();
  });
});
```

- [ ] **Step 3: 실패 확인** — `npx vitest run tests/wp-summary-table.test.tsx` → FAIL (Impact 헤더 존재 / "Work Area" 없음).

- [ ] **Step 4: 구현** — `WPSummaryTable.tsx`
  - import 추가: `import { waCode } from "@/lib/wp-format";`
  - 헤더(`:37-43`) 교체:
    ```tsx
    <th className="px-3 py-1.5 font-medium">Work Area</th>
    <th className="px-3 py-1.5 font-medium">공종</th>
    <th className="px-3 py-1.5 font-medium">BP사</th>
    <th className="px-3 py-1.5 font-medium">지연일</th>
    <th className="px-3 py-1.5 font-medium">단축 가능일</th>
    <th className="px-3 py-1.5 font-medium">Status</th>
    ```
  - 본문에서 **Impact 셀(`:69-71`)·Productivity 셀(`:72-74`) 삭제**. 맨 왼쪽 셀(`:58-66`)의 `{row.wp_name}` → `{waCode(row)}`. Impact/Productivity 자리에 **지연일 셀** 신규 삽입(공기단축=단축가능일 셀 앞):
    ```tsx
    <td className="px-3 py-1 text-[12px] tabular-nums">
      {(() => {
        const d = row.delay_days ?? 0;
        return d > 0
          ? <span className="font-semibold text-rose-text">+{d}일</span>
          : <span className="text-ink-light">0일</span>;
      })()}
    </td>
    ```
  - 기존 "공기 단축" 셀(`:75-84`)은 그대로 두되 헤더만 "단축 가능일"로(위에서 처리). 값 로직(`recovery_days` → `-N일`/`—`) 유지.

- [ ] **Step 5: 통과 확인** — `npx vitest run tests/wp-summary-table.test.tsx` → PASS. 이어서 `npx tsc --noEmit` → 에러 0.

- [ ] **Step 6: 커밋**

```bash
git add web/lib/types.ts web/app/components/reports/WPSummaryTable.tsx web/tests/wp-summary-table.test.tsx
git commit -m "feat(report): WP목록 컬럼 Work Area·지연일·단축가능일 재구성 (B1/B2/B4)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 지연일 FE 주입 (B3)

`reports/page.tsx`에서 filteredWpRows 빌드 시 각 row에 `delay_days`를 optimizer details에서 계산해 주입.

**Files:**
- Modify: `web/app/(app)/reports/page.tsx` (`filteredWpRows`, 143-149)

- [ ] **Step 1: 구현**
  - import: `import { parseDelayDays } from "@/lib/wp-format";`
  - `filteredWpRows`(`:143-149`)를 `.map`으로 augment. 예:
    ```tsx
    const byWp = detail.optimizer?.by_wp ?? {};
    const filteredWpRowsBase = detail.wp_summary
      .filter((w) => visibleTrades.has(w.trade) && (w.impact > 0 || w.productivity > 0))
      .map((w) => ({ ...w, delay_days: parseDelayDays(byWp[w.wp_id]?.details) }));
    ```
    (기존 base 필터는 유지, `.map`만 체이닝. `wpStatusFilter` 분기는 그대로.)

- [ ] **Step 2: 타입체크** — `npx tsc --noEmit` → 에러 0 (delay_days 는 Task 2에서 옵셔널 추가됨).

- [ ] **Step 3: 수동 확인** — dev2(5537)에서 `/reports` 열어 WP목록 "지연일" 컬럼이 `+5일`/`0일` 등으로 채워지는지 육안. (옵티마이저 카드 "일정 영향"과 동일 값.)
  - 또는 비파괴 검증: `curl -s "http://127.0.0.1:5537/api/mock/report/2025-09-24"` 의 `optimizer.by_wp[<wp_id>].details` "일정 영향"과 표 값 대조.

- [ ] **Step 4: 커밋**

```bash
git add web/app/\(app\)/reports/page.tsx
git commit -m "feat(report): WP목록 지연일을 optimizer 일정영향에서 FE 주입 (B3)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: 권고사항 줄바꿈 수정 (B5)

근본 원인: `OptimizerResult.tsx:49` `list-decimal list-inside` 마커가 `:58` 블록 `<div>` 앞에서 자체 줄을 차지 → 번호와 본문 분리. 수정: 그 `<div>`를 inline `<span>`으로.

**Files:**
- Modify: `web/app/components/reports/OptimizerResult.tsx` (`:58`)
- Test: `web/tests/optimizer-result.test.tsx`

- [ ] **Step 1: 버그 재현(수동)** — dev2(5537) `/reports`에서 우측 카드 "권고사항"의 번호(1.)와 `[키워드]…`가 서로 다른 줄에 있는지 확인(있어야 함).

- [ ] **Step 2: 실패 테스트 작성** — `web/tests/optimizer-result.test.tsx`

```tsx
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { OptimizerResult } from "@/app/components/reports/OptimizerResult";
import type { OptimizerOutput } from "@/lib/types";

const out: OptimizerOutput = {
  wp_id: "x", diagnosis: "진단", similar_cases: [],
  recommendations: [{ rank: 1, keyword: "교대근무", action: "인력 추가 배치", reason: "이유" }],
  details: [],
};

describe("OptimizerResult 권고 마커", () => {
  it("li 의 첫 자식이 블록 div 가 아니라 inline (마커와 본문 동일 라인)", () => {
    const { container } = render(<OptimizerResult output={out} />);
    const li = container.querySelector("li");
    expect(li).toBeTruthy();
    // 첫 element 자식이 SPAN(inline) 이어야 한다 (DIV 면 마커가 줄바꿈됨)
    const firstEl = li!.querySelector(":scope > *");
    expect(firstEl?.tagName).toBe("SPAN");
  });
});
```

- [ ] **Step 3: 실패 확인** — `npx vitest run tests/optimizer-result.test.tsx` → FAIL (firstEl 이 DIV).

- [ ] **Step 4: 구현** — `OptimizerResult.tsx:58` `<div className="text-ink">` → `<span className="text-ink">`, 닫는 `</div>`(:61) → `</span>`. (내부 inline span 2개 그대로. reason 블록 `:62-66`은 그대로 둠 — 별도 줄.) `text-ink`는 색상 전용이라 spacing 조정 불요.

- [ ] **Step 5: 통과 확인** — `npx vitest run tests/optimizer-result.test.tsx` → PASS. dev2에서 번호와 본문이 같은 줄인지 육안 재확인.

- [ ] **Step 6: 커밋**

```bash
git add web/app/components/reports/OptimizerResult.tsx web/tests/optimizer-result.test.tsx
git commit -m "fix(report): 권고 번호-본문 줄바꿈 — li 첫 자식 div→span (B5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Phase 2 — ForecastChart

### Task 5: 예상공기 KPI 숨김 + 긴 AI 권고 카드 리스트 제거 (C1·C2)

**Files:**
- Modify: `web/app/components/charts/ForecastChart.tsx` (KPI 113-123, aiAdvice 블록 389-433)

- [ ] **Step 1: 구현**
  - **C1:** "예상 공기" KPI 블록(`:113-123`, `<div>…예상 공기…</div>`) 삭제. "최적화 공기" 블록(`:124-134`)만 남김.
  - **C2:** 하단 `{aiAdvice && aiAdvice.length > 0 ? (…)}` 블록(`:389-433`) 전체 삭제. `aiSummaryText` 단락(`:376-387`)·3선 요약 테이블(`:299-374`) 유지. `aiAdvice` prop은 **삭제하지 말 것**(Task 7 컴팩트 카드에서 재사용).

- [ ] **Step 2: 타입체크** — `npx tsc --noEmit` → 에러 0. (`aiAdvice` 미사용 경고가 나면 Task 7에서 곧 쓰므로 무시하거나 eslint-disable 대신 그대로 둠 — prop 시그니처 유지.)

- [ ] **Step 3: 수동 확인** — dev2 `/reports` 하단 "공기 단축 예측 시나리오"에 예상공기 KPI 없음·긴 카드 리스트 없음.

- [ ] **Step 4: 커밋**

```bash
git add web/app/components/charts/ForecastChart.tsx
git commit -m "feat(report): 예상공기 KPI·긴 AI권고 카드 리스트 숨김 (C1/C2)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: 마우스 스크롤 줌 (C3)

`PresentationShell.tsx:56-77` 패턴 차용하되 **차트 래퍼 div에만** wheel 바인딩(window 아님 — 페이지 스크롤 트랩 회피).

**Files:**
- Modify: `web/app/components/charts/ForecastChart.tsx` (data 슬라이스 69-87, ResponsiveContainer 래퍼 194)

- [ ] **Step 1: 구현** — (참고: `allData`(`:69`), `todayIdx`, `windowStart`/`windowEnd`(`:85-86`), `data = allData.slice(...)`(`:87`)는 **이미 컴포넌트에 존재**. 줌은 이걸 재정의하지 않고 슬라이스 경계만 `view` state로 덮어쓴다.)
  - 상단 import에 `useRef, useEffect` 추가(이미 `useState` 있음).
  - 윈도우 state: `const [view, setView] = useState<{ s: number; e: number } | null>(null);`
  - 기존 `windowStart/windowEnd`(`:85-86`) 계산 직후, 기존 `data` 슬라이스(`:87`)를 view 우선으로 교체:
    ```tsx
    const defStart = windowStart, defEnd = windowEnd;
    const vs = view?.s ?? defStart;
    const ve = view?.e ?? defEnd;
    const data = allData.slice(vs, ve);
    ```
  - 차트 래퍼 ref + wheel 핸들러:
    ```tsx
    const zoomRef = useRef<HTMLDivElement | null>(null);
    useEffect(() => {
      const el = zoomRef.current;
      if (!el) return;
      const onWheel = (ev: WheelEvent) => {
        ev.preventDefault();
        const rect = el.getBoundingClientRect();
        const frac = rect.width ? (ev.clientX - rect.left) / rect.width : 0.5;
        const cs = view?.s ?? defStart, ce = view?.e ?? defEnd;
        const width = ce - cs;
        const factor = ev.deltaY > 0 ? 1.15 : 0.87;          // down=축소(넓힘), up=확대(좁힘)
        let nw = Math.round(width * factor);
        nw = Math.max(14, Math.min(allData.length, nw));     // clamp: 최소 14, 최대 전체
        const pivot = cs + Math.round(width * frac);
        let ns = Math.max(0, pivot - Math.round(nw * frac));
        let ne = Math.min(allData.length, ns + nw);
        ns = Math.max(0, ne - nw);
        setView({ s: ns, e: ne });
      };
      el.addEventListener("wheel", onWheel, { passive: false });   // React 합성 onWheel 금지(passive no-op)
      return () => el.removeEventListener("wheel", onWheel);
    }, [view, defStart, defEnd, allData.length]);
    ```
  - `<ResponsiveContainer>`(`:194`)를 `<div ref={zoomRef} onDoubleClick={() => setView(null)}>` 로 감싸기. 더블클릭=초기화.
  - 차트 아래 보조 hint 1줄 추가(범례 근처): `스크롤 확대 · 더블클릭 초기화`.

- [ ] **Step 2: 타입체크** — `npx tsc --noEmit` → 에러 0.

- [ ] **Step 3: 수동 e2e(필수, jsdom 불가)** — dev2 `/reports`에서 그래프 위 휠 위로→구간 확대, 아래로→축소, 커서 위치 중심 이동, 더블클릭→원복. 그래프 **밖** 커서로는 페이지 정상 스크롤되는지 확인.

- [ ] **Step 4: 커밋**

```bash
git add web/app/components/charts/ForecastChart.tsx
git commit -m "feat(report): 공정률 그래프 마우스 스크롤 줌 + 더블클릭 리셋 (C3)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: AI 시나리오 라인 클릭 → 컴팩트 카드 + 강조 (C4)

**Files:**
- Modify: `web/app/components/charts/ForecastChart.tsx` (라인 216/219/222/225, 범례 188-191, 카드 신규)

- [ ] **Step 1: 구현** — (참고: 카드가 쓰는 `recoveryDays`·`aiSummaryText`·`aiAdvice`는 **이미 ForecastChart의 props**(`:25,:33-41`, reports/page.tsx:274-281에서 전달). 새로 정의·fetch 안 함.)
  - state: `const [activeLine, setActiveLine] = useState<"base" | null>(null);`
  - cold_start 가드: `const hasBase = (diagnosis.scenarios?.base?.curve ?? []).some((v) => v != null);`
  - 각 `<Line>`에 `strokeOpacity` 추가 — base 활성 시 forecast/planned/band만 흐림, **actual·base는 full 유지**:
    ```tsx
    const dim = (key: string) => (activeLine === "base" && key !== "base" && key !== "actual") ? 0.25 : 1;
    // planned(:216): strokeOpacity={dim("planned")}
    // actual(:219):  strokeOpacity={1}            // 항상 full (최중요 실적선)
    // forecast(:222):strokeOpacity={dim("forecast")}
    // base(:225):    strokeOpacity={1} onClick={() => hasBase && setActiveLine(a => a === "base" ? null : "base")} style={{ cursor: hasBase ? "pointer" : "default" }}
    // 두 Area(band, :212-213) 에도 fillOpacity 를 activeLine==="base" 시 0.15 로 낮춤(선택).
    ```
  - mint 범례 항목(`:188-191`)에 클릭 핸들러 + `cursor-pointer`: `onClick={() => hasBase && setActiveLine(a => a === "base" ? null : "base")}`.
  - 컴팩트 카드: `<ResponsiveContainer>` 닫힌 직후, `activeLine === "base"` 일 때만 렌더:
    ```tsx
    {activeLine === "base" && (
      <div className="mt-3 max-w-md rounded-md bg-mint-light/40 px-3 py-2 text-[12.5px] ring-1 ring-mint/30">
        <div className="font-semibold text-mint-text">AI 시나리오 · {recoveryDays > 0 ? `${recoveryDays}일 만에 plan 따라잡음` : "회복 제한적"}</div>
        {(() => {
          const top = (aiAdvice ?? []).filter((w) => typeof w.recovery_days === "number")
            .sort((a, b) => (b.recovery_days ?? 0) - (a.recovery_days ?? 0))[0];
          const recs = top?.recommendations?.slice(0, 2) ?? [];
          if (recs.length) return <ul className="mt-1 ml-3 list-disc space-y-0.5 text-ink-mid">{recs.map((r, i) => <li key={i}>{r}</li>)}</ul>;
          if (aiSummaryText) return <p className="mt-1 text-ink-mid line-clamp-2">{aiSummaryText}</p>;
          return null;
        })()}
        <button type="button" onClick={() => setActiveLine(null)} className="mt-1 text-[11px] text-ink-light hover:text-ink-mid">닫기</button>
      </div>
    )}
    ```

- [ ] **Step 2: 타입체크** — `npx tsc --noEmit` → 에러 0. (`aiAdvice`가 여기서 다시 쓰여 Task 5의 미사용 경고 해소.)

- [ ] **Step 3: 수동 e2e** — dev2 `/reports`에서 mint "AI 시나리오" 라인/범례 클릭 → 그 선·실적선만 진하고 plan/forecast 흐려짐 + 아래 컴팩트 카드 표시. 다시 클릭/닫기 → 해제. base 없는 날짜(cold_start)면 클릭 무반응 확인.

- [ ] **Step 4: 커밋**

```bash
git add web/app/components/charts/ForecastChart.tsx
git commit -m "feat(report): AI 시나리오 라인 클릭 강조 + 컴팩트 권고 카드 (C4)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Phase 3 — Review 탭

### Task 8: 노드별 누적 등록 API 라우트 (A1)

**Files:**
- Create: `web/app/api/mock/review/registered/route.ts`

- [ ] **Step 1: 구현** — 신규 라우트

```ts
// GET /api/mock/review/registered?wa=&l5=&l6=&limit=500
// 선택 WBS 노드(WA/trade/WP)의 site 누적 등록 mapper_activities 를 노드 스코프로 반환.
// 전역 캡(빈칸 버그) 폐기 — 노드 단위 lazy fetch. ORDER BY started_at(실 timestamp), run_id(UUID) 아님.
export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import { deriveWpIdAndPath } from "@/lib/transforms";
import type { ReviewItem } from "@/lib/types";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const wa = url.searchParams.get("wa");
  const l5 = url.searchParams.get("l5");
  const l6 = url.searchParams.get("l6");
  const limit = Math.min(Number(url.searchParams.get("limit") ?? 500) || 500, 1000);
  if (!wa) return NextResponse.json({ error: "wa required" }, { status: 400 });

  const useMock = process.env.CPIA_DEMO_FALLBACK === "on";
  const siteRow = (await (sql as any)`
    SELECT site_id, name FROM sites WHERE is_mock = FALSE ORDER BY site_id LIMIT 1`) as Array<{ site_id: string; name: string }>;
  const siteId = siteRow[0]?.site_id ?? "m15x-ph3-ibl";
  const siteName = siteRow[0]?.name ?? siteId;

  const rows = (await (sql as any)`
    SELECT ma.id, ma.idx, ma.company, ma.today_qty, ma.unit, ma.wa, ma.l6_main, ma.mapping_conf,
           pa.work_content, COUNT(*) OVER() AS total
    FROM mapper_activities ma
    JOIN pipeline_runs pr USING (run_id)
    LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
    WHERE pr.site_id = ${siteId} AND ma.is_mock = ${useMock}
      AND ma.l6_main IS NOT NULL
      AND ma.wa = ${wa}
      AND (${l6}::text IS NULL OR ma.l6_main = ${l6})
      AND (${l5}::text IS NULL OR ma.l5_disc = ${l5})
    ORDER BY pr.started_at DESC NULLS LAST, ma.mapping_conf DESC NULLS LAST
    LIMIT ${limit}
  `) as Array<{
    id: number | string; idx: number; company: string | null;
    today_qty: number | string | null; unit: string | null;
    wa: string | null; l6_main: string | null; mapping_conf: number | string | null;
    work_content: string | null; total: number | string;
  }>;

  const total = rows[0] ? Number(rows[0].total) : 0;
  const items: ReviewItem[] = rows.map((r) => {
    const m = deriveWpIdAndPath(r.wa, r.l6_main, siteName);
    return {
      id: `reg-${r.id}`, idx: r.idx, bp_name: r.company ?? "",
      work_content: r.work_content ?? "", quantity: r.today_qty != null ? Number(r.today_qty) : 0,
      unit: r.unit ?? "", ai_mapped_wp_id: m.wp_id, ai_mapped_path: m.path,
      wa: r.wa, l6_main: r.l6_main,
      confidence: r.mapping_conf != null ? Number(r.mapping_conf) : 0,
      status: "confirmed", alternative_wps: [],
    };
  });
  return NextResponse.json({ items, total }, {
    headers: { "Cache-Control": "s-maxage=30, stale-while-revalidate=60" },
  });
}
```

- [ ] **Step 2: 타입체크** — `npx tsc --noEmit` → 에러 0.

- [ ] **Step 3: curl 통합검증(필수 — 라우트 SQL은 실 DB로 검증)** — dev2(5537) 떠 있는 상태에서:
  ```bash
  # WA 레벨 (대량) — items + total 반환
  curl -s "http://127.0.0.1:5537/api/mock/review/registered?wa=FAB&limit=500" | python3 -c 'import sys,json;d=json.load(sys.stdin);print("items",len(d["items"]),"total",d["total"])'
  # WP 레벨 — 특정 l6
  curl -s "http://127.0.0.1:5537/api/mock/review/registered?wa=FAB&l6=PC공사&limit=500" | python3 -c 'import sys,json;d=json.load(sys.stdin);print("items",len(d["items"]),"total",d["total"],"첫행",d["items"][0]["ai_mapped_path"] if d["items"] else None)'
  ```
  Expected: 두 호출 모두 `items` ≥ 1, `total` ≥ items, 에러 없음. (고건수 노드도 빈칸 아님 — A1 목표.)

- [ ] **Step 4: 커밋**

```bash
git add web/app/api/mock/review/registered/route.ts
git commit -m "feat(review): 노드별 누적 등록 API — 전역캡 폐기·lazy fetch (A1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: `nodeToQuery` 순수헬퍼 (A4)

**Files:**
- Create: `web/lib/review-node.ts`
- Test: `web/tests/review-node.test.ts`

- [ ] **Step 1: 실패 테스트 작성** — `web/tests/review-node.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { nodeToQuery } from "@/lib/review-node";
import type { WBSNode } from "@/lib/types";

const base = { name: "", parent_id: null, review_count: 0, total_count: 0, status: "normal" as const };

describe("nodeToQuery", () => {
  it("work_package → wa+l6", () => {
    const n: WBSNode = { ...base, id: "fab-pc공사", type: "work_package", wa: "FAB", l6_main: "PC공사" };
    expect(nodeToQuery(n)).toEqual({ wa: "FAB", l5: null, l6: "PC공사" });
  });
  it("trade(l5_disc) id 'FAB::골조' → wa+l5", () => {
    const n: WBSNode = { ...base, id: "FAB::골조", type: "trade" };
    expect(nodeToQuery(n)).toEqual({ wa: "FAB", l5: "골조", l6: null });
  });
  it("trade(WA) id 'FAB' → wa만", () => {
    const n: WBSNode = { ...base, id: "FAB", type: "trade" };
    expect(nodeToQuery(n)).toEqual({ wa: "FAB", l5: null, l6: null });
  });
  it("building / null → null", () => {
    expect(nodeToQuery({ ...base, id: "site", type: "building" })).toBeNull();
    expect(nodeToQuery(null)).toBeNull();
  });
});
```

- [ ] **Step 2: 실패 확인** — `npx vitest run tests/review-node.test.ts` → FAIL (module 없음).

- [ ] **Step 3: 구현** — `web/lib/review-node.ts`

```ts
import type { WBSNode } from "@/lib/types";

export interface RegisteredQuery { wa: string; l5: string | null; l6: string | null; }

/** 선택된 WBS 노드 → registered fetch 파라미터.
 *  WBS 4레벨: building → WA(type:"trade", id="FAB") → l5_disc(type:"trade", id="FAB::골조") → work_package(wa·l6_main 필드).
 *  building/미선택/필드부족 → null(fetch 안 함). */
export function nodeToQuery(node: WBSNode | null): RegisteredQuery | null {
  if (!node) return null;
  if (node.type === "work_package") {
    return node.wa ? { wa: node.wa, l5: null, l6: node.l6_main ?? null } : null;
  }
  if (node.type === "trade") {
    if (node.id.includes("::")) {
      const [wa, l5] = node.id.split("::");
      return { wa, l5, l6: null };
    }
    return { wa: node.id, l5: null, l6: null };
  }
  return null;
}
```

- [ ] **Step 4: 통과 확인** — `npx vitest run tests/review-node.test.ts` → PASS (4 tests).

- [ ] **Step 5: 커밋**

```bash
git add web/lib/review-node.ts web/tests/review-node.test.ts
git commit -m "feat(review): WBS 노드→등록 쿼리 파라미터 nodeToQuery (A4)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: ReviewCard `readOnly` prop (A5)

**Files:**
- Modify: `web/app/components/review/ReviewCard.tsx`
- Test: `web/tests/review-card-readonly.test.tsx`

- [ ] **Step 1: 실패 테스트 작성** — `web/tests/review-card-readonly.test.tsx`

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReviewCard } from "@/app/components/review/ReviewCard";
import type { ReviewItem, WBSNode } from "@/lib/types";

const wbs: WBSNode = { id: "s", type: "building", name: "s", parent_id: null, review_count: 0, total_count: 0, status: "normal", children: [] };
const item: ReviewItem = {
  id: "r1", idx: 1, bp_name: "A건설", work_content: "작업", quantity: 10, unit: "m3",
  ai_mapped_wp_id: "w", ai_mapped_path: "s > FAB > PC", wa: "FAB", l6_main: "PC공사",
  confidence: 0.9, status: "confirmed",
};

describe("ReviewCard readOnly", () => {
  it("readOnly 면 확정·수정 버튼 없고 배지 '등록'", () => {
    render(<ReviewCard item={item} wbsRoot={wbs} onConfirm={() => {}} onRemap={() => {}} readOnly />);
    expect(screen.queryByText("수정")).toBeNull();
    expect(screen.queryByText("확정")).toBeNull();
    expect(screen.getByText("등록")).toBeTruthy();
  });
  it("readOnly 아니면 수정 버튼 있음", () => {
    render(<ReviewCard item={{ ...item, status: "unconfirmed" }} wbsRoot={wbs} onConfirm={() => {}} onRemap={() => {}} />);
    expect(screen.getByText("수정")).toBeTruthy();
  });
});
```

- [ ] **Step 2: 실패 확인** — `npx vitest run tests/review-card-readonly.test.tsx` → FAIL (readOnly prop 없음 → "수정" 존재).

- [ ] **Step 3: 구현** — `ReviewCard.tsx`
  - Props에 `readOnly?: boolean` 추가(`:8-13`). 함수 시그니처 분해에 `readOnly`.
  - `:21` `draggable={!isConfirmed && !readOnly}`, `:22-26` onDragStart 가드에 `if (isConfirmed || readOnly) return;`.
  - 배지(`:34-44`): `readOnly` 분기 추가 — readOnly 면 중립 배지:
    ```tsx
    {readOnly ? (
      <>
        <CheckCircle2 className="h-4 w-4 text-ink-light" />
        <span className="font-mono text-xs uppercase tracking-wider text-ink-mid font-bold">등록</span>
      </>
    ) : isConfirmed ? (/* 기존 확정 */) : (/* 기존 미확정 */)}
    ```
  - editMode 콤보(`:73-87`): `{!readOnly && editMode && (…)}`.
  - 버튼 블록(`:89-108`): 전체를 `{!readOnly && (…)}` 로 감쌈. (확정 버튼 기존 `!isConfirmed` 게이트는 유지.)
  - 대안 표시(`:67-71`)도 `!isConfirmed && !readOnly` 로(선택, 열람 일관성).

- [ ] **Step 4: 통과 확인** — `npx vitest run tests/review-card-readonly.test.tsx` → PASS. `npx tsc --noEmit` → 에러 0.

- [ ] **Step 5: 커밋**

```bash
git add web/app/components/review/ReviewCard.tsx web/tests/review-card-readonly.test.tsx
git commit -m "feat(review): ReviewCard readOnly — 등록 카드 열람전용·배지 등록 (A5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: review/page.tsx 통합 — 토글 자동전환·registered 배선·빈상태 (A2/A3/A4/A6)

가장 큰 통합 task. jsdom 단위테스트 어려운 부분(fetch·인터랙션)은 typecheck + 5537 수동 e2e로 검증.

**Files:**
- Modify: `web/app/(app)/review/page.tsx`

- [ ] **Step 1: 구현**
  - import 추가: `import { nodeToQuery } from "@/lib/review-node";`
  - state 추가(`:10-13` 부근):
    ```tsx
    const [registered, setRegistered] = useState<ReviewItem[]>([]);
    const [registeredTotal, setRegisteredTotal] = useState(0);
    const [registeredError, setRegisteredError] = useState(false);
    const [confirmedNotice, setConfirmedNotice] = useState<string | null>(null);
    ```
    `onlyUnconfirmed` 초기값 `useState(true)` → `useState(false)`.
  - **A2:** 초기 fetch(`:15-22`) `.then(({ wbs, cards }) => { setWbs(wbs); setCards(cards); setOnlyUnconfirmed(cards.length > 0); })`.
  - **A4 lazy fetch:** 새 `useEffect`:
    ```tsx
    useEffect(() => {
      if (onlyUnconfirmed || !selectedNodeId || !wbs) { setRegistered([]); setRegisteredTotal(0); setRegisteredError(false); return; }
      const node = find(wbs, selectedNodeId);          // 기존 find 헬퍼(:33-41) 를 컴포넌트 스코프로 끌어올리거나 재사용
      const q = nodeToQuery(node);
      if (!q) { setRegistered([]); setRegisteredTotal(0); return; }
      const params = new URLSearchParams({ wa: q.wa });
      if (q.l5) params.set("l5", q.l5);
      if (q.l6) params.set("l6", q.l6);
      let cancelled = false;
      setRegisteredError(false);
      fetch(`/api/mock/review/registered?${params}`)
        .then((r) => r.ok ? r.json() : Promise.reject())
        .then((d) => { if (!cancelled) { setRegistered(d.items ?? []); setRegisteredTotal(d.total ?? 0); } })
        .catch(() => { if (!cancelled) { setRegistered([]); setRegisteredError(true); } });
      return () => { cancelled = true; };
    }, [onlyUnconfirmed, selectedNodeId, wbs]);
    ```
    (참고: 현재 `find`는 visibleCards useMemo 내부 지역함수. 모듈 최상위 또는 컴포넌트 내 공용 함수로 추출해 재사용.)
  - **A4 visibleCards(`:24-47`):** 베이스 분기 — `let filtered = onlyUnconfirmed ? cards : registered;`. 이어서 **onlyUnconfirmed 일 때만** 기존 selectedNode wp_id 필터 적용(registered는 서버 노드-스코프라 건너뜀).
  - **A3 handleConfirmAll(`:79-99`):** setCards 후 미확정 0 도달 시 자동 복귀 + 알림:
    ```tsx
    const n = cards.filter((c) => c.status === "unconfirmed").length;
    setCards((cs) => cs.map((c) => c.status === "unconfirmed" ? { ...c, status: "confirmed" as const } : c));
    setOnlyUnconfirmed(false);
    setConfirmedNotice(`${n}건 확정 완료`);
    // 기존 corrections 수집 + /api/hil/resume 그대로
    ```
  - **A5 wiring:** `<ReviewCard … readOnly={!onlyUnconfirmed} />`(`:143-145`).
  - **A6 빈 상태(`:146-150`):** 조건 분기:
    ```tsx
    {visibleCards.length === 0 && (
      <div className="rounded-card border border-dashed border-border-soft py-12 text-center text-sm text-ink-light">
        {onlyUnconfirmed ? "검토할 신규 매핑이 없습니다."
          : registeredError ? "등록 작업을 불러오지 못했습니다. 잠시 후 다시 시도하세요."
          : !selectedNodeId ? "좌측에서 공종 또는 WP를 선택하면 누적 등록 작업을 볼 수 있습니다."
          : "이 공종에 등록된 작업이 없습니다."}
      </div>
    )}
    ```
  - **헤더(`:134-140`):** 등록 모드일 때 "총 N건 중 최근 M건"(registeredTotal vs registered.length) + `confirmedNotice` 표기(토글 옆). 예:
    ```tsx
    {!onlyUnconfirmed && selectedNodeId && registered.length > 0 && (
      <span className="text-[11px] text-ink-light">총 {registeredTotal}건 중 최근 {registered.length}건</span>
    )}
    {confirmedNotice && <span className="text-[11px] font-semibold text-mint-text">{confirmedNotice}</span>}
    ```
  - **"모두 확정" 버튼(`:153-162`):** HIL 모드에서만 — `{onlyUnconfirmed && (…버튼…)}`.
  - `confirmedNotice`는 다음 인터랙션에 사라지게: selectedNodeId/onlyUnconfirmed 변경 useEffect에서 `setConfirmedNotice(null)`.

- [ ] **Step 2: 타입체크** — `npx tsc --noEmit` → 에러 0.

- [ ] **Step 3: 수동 e2e(필수)** — dev2(5537) `/review`:
  - 진입 시 cards=0(현재 completed run)이면 토글 OFF·등록뷰·"좌측에서 선택" 안내.
  - 좌측 트리에서 **토목/건축/승강기공사** 등 클릭 → 우측에 누적 등록 카드(읽기전용·배지 "등록") + "총 N건 중 최근 M건". (고건수 노드도 빈칸 아님 = A1 목표 달성.)
  - (waiting_hil_1 데이터가 있는 환경이면) 진입 시 토글 ON·요검토 카드 → "모두 확정" → 토글 자동 OFF·"N건 확정 완료"·트리 배지 0.
  - 노드 0건/에러 시 각 문구 구분 표시.

- [ ] **Step 4: 회귀** — `npm test` 실행 후, 선재 실패 4건(persona 3·diagnosis 1·e2e 2파일) **외에 새 실패가 없는지** 확인(신규/수정 테스트는 그린). `npx tsc --noEmit` → 0.

- [ ] **Step 5: 커밋**

```bash
git add web/app/\(app\)/review/page.tsx
git commit -m "feat(review): HIL/등록 토글 자동전환 + 노드별 누적 등록 lazy fetch + 빈상태 (A2/A3/A4/A6)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## 완료 게이트 (전 task 후)

- [ ] `npm test`에서 신규/수정 테스트 그린 + 선재 실패 4건(persona·diagnosis·e2e) 외 새 실패 0. `npx tsc --noEmit` 에러 0.
- [ ] dev2(5537) 수동 e2e 체크리스트: 보고서 WP목록(Work Area·지연일·단축가능일, Impact/Prod 없음), 권고 번호-본문 한 줄, 예상공기 KPI 없음·긴 카드 없음, 그래프 스크롤 줌·더블클릭·라인클릭 카드, review 토글 자동전환·노드 클릭 카드(고건수 포함)·빈상태 문구.
- [ ] 데모 반영은 사용자 지시 시 루트에서 `make build`(5535). push는 사용자 명시 지시 시에만.

## 주의/한계 (정직)

- ForecastChart 줌·라인클릭(C3/C4)과 review 통합(Task 11)은 jsdom에서 layout/wheel/fetch 검증이 불가 → typecheck + 5537 수동 e2e가 1차 검증. 자동 단위테스트는 순수 헬퍼(Task 1/9)·컴포넌트 구조(Task 2/4/10)에 집중.
- registered 라우트는 vitest의 `@/lib/pg` 전역 mock 때문에 단위 단언보다 **curl 통합검증**이 SQL 정확성을 보장(Task 8 Step 3).
- trade 레벨 `total`(헤더)과 좌측 트리 배지(activity_agg는 wa·l6_main GROUP BY)는 집계축이 달라 약간 다를 수 있음. WP 레벨은 정확. 데모 무영향.
