# Review 보드 뷰 (WBS·작업물량 노드-링크 마인드맵) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/review` 에 탭으로 추가되는 두 번째 뷰 — 프로젝트›건물›공종›WP›작업물량을 React Flow 노드-링크 마인드맵으로 시각화하고, 검토 대상 작업물량만 강조, 노드 접기/펼치기, 작업물량 필터, 드래그 리맵 + 확정을 제공.

**Architecture:** 순수 로직(그래프 빌드·트리 레이아웃)과 프레젠테이션 노드 바디를 RF 무관 모듈로 분리해 vitest 로 TDD. `ReviewBoard` 가 `@xyflow/react` 캔버스에서 이들을 조립하고 collapsed/reviewOnly 상태·드래그 리맵·확정을 배선. 데이터는 리스트 뷰가 이미 가진 `wbs` 트리 + `cards` 를 그대로 재사용(신규 API 없음).

**Tech Stack:** Next.js 14 (App Router, client), React 18, TypeScript, Tailwind, **@xyflow/react v12 (신규)**, vitest + @testing-library/react (jsdom).

**대상 파일:**
- Create: `web/lib/board-graph.ts`, `web/lib/board-layout.ts`, `web/app/components/review/board/HierBox.tsx`, `web/app/components/review/board/QtyCard.tsx`, `web/app/components/review/board/HierNode.tsx`, `web/app/components/review/board/QtyNode.tsx`, `web/app/components/review/ReviewBoard.tsx`
- Create(test): `web/tests/board-graph.test.ts`, `web/tests/board-layout.test.ts`, `web/tests/board-nodes.test.tsx`
- Modify: `web/app/(app)/review/page.tsx`, `web/package.json`

**검증 규약:** `cd web && npx vitest run <file>` (vitest). 타입: `cd web && npx tsc --noEmit 2>&1 | grep -vE "\.next/" | grep "error TS"` → src-level 0 기대(로컬 `next build` 는 `.next` 권한으로 불가). 런타임: dev 컨테이너(cpia-web-dev, 5537, `../web` 바인드마운트, HMR).

**커밋 규약:** B_Track 직접 커밋. 메시지 말미 한 줄 공백 후 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

**프로젝트 제약:** tsconfig 에 `target` 미지정 → **Set 스프레드(`[...set]`)·Map for-of 금지**. `Array.from`/`.forEach`/`new Set(array)` 사용(배열 스프레드 `[...arr]` 는 OK).

---

## 도메인 사실 (구현 전 숙지)

- `WBSNode { id, type:"building"|"trade"|"work_package", name, parent_id, review_count, total_count, status, children?, wa?, l6_main? }`.
- 트리: root(`building`, id=siteId=프로젝트) → `trade`(id=wa, 예 "FAB") → `trade`(id="FAB::골조") → `work_package`(id=`safe(wa)-safe(l6)`, `wa`·`l6_main` 보유). 깊이 0,1,2,3.
- `ReviewItem { id, idx, bp_name, work_content, quantity, unit, ai_mapped_wp_id, ai_mapped_path, wa, l6_main, confidence, status:"confirmed"|"unconfirmed", remapped?, alternative_wps? }`.
- **`card.ai_mapped_wp_id === work_package 노드.id`** (둘 다 `safe(wa)-safe(l6)`). → 작업물량을 WP 에 매달 때 id 동등 비교.
- 검토 대상 = `status === "unconfirmed"`.

---

## File Structure

- `lib/board-graph.ts` — `BoardNode`/`BoardEdge` 타입 + `buildBoardGraph(wbs, cards, opts)`: WBS 트리(항상 전부) + 작업물량(reviewOnly 시 미확정만)을 노드/엣지로. collapsed 하위 제외. UI·RF 무관 순수.
- `lib/board-layout.ts` — `layoutBoard(nodes, edges)`: 좌→우 트리 좌표. depth→x, 리프 순서→y, 부모=자식 평균 y. 순수.
- `board/HierBox.tsx` — 위계 노드 시각(흰색 박스 + 캐럿 + 집계). RF 무관, 테스트 대상.
- `board/QtyCard.tsx` — 작업물량 노드 시각(흰색/검토 sun + 확정 버튼). RF 무관, 테스트 대상.
- `board/HierNode.tsx` / `board/QtyNode.tsx` — RF 커스텀 노드(Handle + Box/Card 조립). 얇음.
- `ReviewBoard.tsx` — RF 캔버스 + collapsed/reviewOnly + 툴바 + onNodeDragStop 리맵 + 확정 배선.
- `(app)/review/page.tsx` — `view` 탭 토글 + 보드 분기(리스트 경로 불변).

---

## Task 1: @xyflow/react 의존성 추가

**Files:** Modify `web/package.json` (+ lockfile)

- [ ] **Step 1: 설치 (호스트 — vitest/tsc 가 해석하도록)**

Run:
```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01 AI Design Project/web" 2>/dev/null || cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project/web"
npm install @xyflow/react@^12
```
Expected: `package.json` dependencies 에 `"@xyflow/react": "^12.x"` 추가, 설치 성공.

- [ ] **Step 2: import 해석 확인**

Run: `cd web && node -e "require.resolve('@xyflow/react'); console.log('ok')"`
Expected: `ok`

- [ ] **Step 3: 커밋**

```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/package.json web/package-lock.json
git commit -m "$(printf 'chore(web): @xyflow/react v12 추가 — review 보드 뷰 노드-링크\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

> **런타임 주의(수동 QA 태스크에서 처리):** dev 컨테이너는 named volume `web_dev_modules` 에 자체 `npm install` 한다. 새 의존성 반영하려면 컨테이너 재기동 필요(`make dev2` 또는 `docker restart cpia-web-dev` 후 install 로그 확인). 호스트 install 은 vitest/tsc 용.

---

## Task 2: 그래프 빌드 순수 로직 (`lib/board-graph.ts`)

**Files:** Create `web/lib/board-graph.ts`; Test `web/tests/board-graph.test.ts`

- [ ] **Step 1: 실패 테스트**

`web/tests/board-graph.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { buildBoardGraph } from "@/lib/board-graph";
import type { WBSNode, ReviewItem } from "@/lib/types";

const wp = (id: string, name: string): WBSNode => ({
  id, type: "work_package", name, parent_id: "FAB::골조",
  review_count: 0, total_count: 0, status: "normal", children: [], wa: "FAB", l6_main: name,
});
const wbs: WBSNode = {
  id: "M15X", type: "building", name: "M15X", parent_id: null, review_count: 0, total_count: 0, status: "normal",
  children: [{
    id: "FAB", type: "trade", name: "FAB", parent_id: "M15X", review_count: 0, total_count: 0, status: "normal",
    children: [{
      id: "FAB::골조", type: "trade", name: "골조", parent_id: "FAB", review_count: 0, total_count: 0, status: "normal",
      children: [wp("fab-기둥", "기둥"), wp("fab-슬래브", "슬래브")],
    }],
  }],
};
const card = (id: string, wpId: string, status: ReviewItem["status"]): ReviewItem => ({
  id, idx: 0, bp_name: "BP", work_content: "w", quantity: 1, unit: "EA",
  ai_mapped_wp_id: wpId, ai_mapped_path: "M15X > FAB > 기둥", wa: "FAB", l6_main: "기둥",
  confidence: 0.6, status,
});

describe("buildBoardGraph", () => {
  const cards = [card("c1", "fab-기둥", "unconfirmed"), card("c2", "fab-기둥", "confirmed"), card("c3", "fab-슬래브", "unconfirmed")];

  it("위계 노드(깊이 0~3) 전부 + 작업물량 노드, kind/depth 부여", () => {
    const { nodes } = buildBoardGraph(wbs, cards, { collapsed: new Set(), reviewOnly: false });
    const byId = new Map(nodes.map((n) => [n.id, n]));
    expect(byId.get("M15X")?.kind).toBe("hier");
    expect(byId.get("M15X")?.depth).toBe(0);
    expect(byId.get("FAB")?.depth).toBe(1);
    expect(byId.get("FAB::골조")?.depth).toBe(2);
    expect(byId.get("fab-기둥")?.depth).toBe(3);
    expect(byId.get("c1")?.kind).toBe("qty");
    expect(byId.get("c1")?.depth).toBe(4);
    expect(nodes.filter((n) => n.kind === "qty")).toHaveLength(3);
  });

  it("엣지: 위계 부모-자식 + WP→작업물량, 검토 엣지 review=true", () => {
    const { edges } = buildBoardGraph(wbs, cards, { collapsed: new Set(), reviewOnly: false });
    expect(edges).toContainEqual(expect.objectContaining({ source: "M15X", target: "FAB" }));
    expect(edges).toContainEqual(expect.objectContaining({ source: "FAB::골조", target: "fab-기둥" }));
    const e = edges.find((x) => x.target === "c1");
    expect(e).toMatchObject({ source: "fab-기둥", review: true });
    const e2 = edges.find((x) => x.target === "c2"); // confirmed
    expect(e2?.review).toBe(false);
  });

  it("reviewOnly=true 면 미확정 작업물량만, WBS 위계는 전부 유지", () => {
    const { nodes } = buildBoardGraph(wbs, cards, { collapsed: new Set(), reviewOnly: true });
    const qty = nodes.filter((n) => n.kind === "qty").map((n) => n.id);
    expect(qty.sort()).toEqual(["c1", "c3"]); // c2(confirmed) 제외
    // 작업물량 0 인 WP(없음) 포함 — 위계 4개 전부 존재
    expect(nodes.filter((n) => n.kind === "hier")).toHaveLength(4);
  });

  it("collapsed 에 노드 id 있으면 그 하위(자식 위계 + 작업물량) 제외", () => {
    const { nodes, edges } = buildBoardGraph(wbs, cards, { collapsed: new Set(["FAB::골조"]), reviewOnly: false });
    expect(nodes.find((n) => n.id === "fab-기둥")).toBeUndefined();
    expect(nodes.find((n) => n.id === "c1")).toBeUndefined();
    expect(nodes.find((n) => n.id === "FAB::골조")).toBeDefined(); // 자신은 남음
    expect(edges.find((e) => e.source === "FAB::골조")).toBeUndefined();
  });

  it("hier 노드는 hasChildren·reviewCount 노출", () => {
    const { nodes } = buildBoardGraph(wbs, cards, { collapsed: new Set(), reviewOnly: false });
    const disc = nodes.find((n) => n.id === "FAB::골조")!;
    expect(disc.hasChildren).toBe(true);
    const wpNode = nodes.find((n) => n.id === "fab-기둥")!;
    expect(wpNode.reviewCount).toBe(1); // c1 미확정 1건
  });
});
```

- [ ] **Step 2: 실패 확인** — `cd web && npx vitest run tests/board-graph.test.ts` → FAIL(모듈 없음).

- [ ] **Step 3: 구현** `web/lib/board-graph.ts`:
```ts
import type { WBSNode, ReviewItem } from "@/lib/types";

export interface BoardNode {
  id: string;
  kind: "hier" | "qty";
  depth: number;              // hier: 트리 깊이(0~), qty: maxHierDepth+1
  label: string;
  parentId: string | null;    // 그래프상 부모(hier=트리부모, qty=ai_mapped_wp_id)
  hasChildren: boolean;       // hier 전용 — 접기 캐럿 표시
  reviewCount: number;        // hier: 하위 미확정 수(WP 직속), qty: 0
  // qty 전용 원본 데이터
  item?: ReviewItem;
  review?: boolean;           // qty 가 검토 대상(미확정)인지
}

export interface BoardEdge {
  id: string;
  source: string;
  target: string;
  review: boolean;            // 검토 작업물량으로 가는 엣지면 강조
}

interface Opts { collapsed: Set<string>; reviewOnly: boolean; }

export function buildBoardGraph(wbs: WBSNode | null, cards: ReviewItem[], opts: Opts): { nodes: BoardNode[]; edges: BoardEdge[] } {
  const nodes: BoardNode[] = [];
  const edges: BoardEdge[] = [];
  if (!wbs) return { nodes, edges };

  // WP id → 그 WP 에 매달 작업물량(reviewOnly 반영)
  const cardsByWp = new Map<string, ReviewItem[]>();
  for (const c of cards) {
    if (opts.reviewOnly && c.status !== "unconfirmed") continue;
    const arr = cardsByWp.get(c.ai_mapped_wp_id) ?? [];
    arr.push(c);
    cardsByWp.set(c.ai_mapped_wp_id, arr);
  }

  let maxDepth = 0;
  const walk = (node: WBSNode, depth: number) => {
    if (depth > maxDepth) maxDepth = depth;
    const children = node.children ?? [];
    const isWP = node.type === "work_package";
    const wpCards = isWP ? (cardsByWp.get(node.id) ?? []) : [];
    nodes.push({
      id: node.id,
      kind: "hier",
      depth,
      label: node.name,
      parentId: node.parent_id,
      hasChildren: children.length > 0 || wpCards.length > 0,
      reviewCount: isWP ? wpCards.filter((c) => c.status === "unconfirmed").length : node.review_count,
    });
    if (node.parent_id) {
      edges.push({ id: `${node.parent_id}->${node.id}`, source: node.parent_id, target: node.id, review: false });
    }
    // collapsed 면 하위(자식 위계 + 작업물량) 중단
    if (opts.collapsed.has(node.id)) return;
    for (const c of children) walk(c, depth + 1);
    // WP 의 작업물량 노드
    if (isWP) {
      for (const c of wpCards) {
        const review = c.status === "unconfirmed";
        nodes.push({
          id: c.id, kind: "qty", depth: depth + 1, label: c.work_content,
          parentId: node.id, hasChildren: false, reviewCount: 0, item: c, review,
        });
        edges.push({ id: `${node.id}->${c.id}`, source: node.id, target: c.id, review });
      }
    }
  };
  walk(wbs, 0);

  // qty depth 를 maxHierDepth+1 로 통일(컬럼 정렬)
  const qtyDepth = maxDepth + 1;
  for (const n of nodes) if (n.kind === "qty") n.depth = qtyDepth;

  return { nodes, edges };
}
```

- [ ] **Step 4: 통과 확인** — `cd web && npx vitest run tests/board-graph.test.ts` → PASS(5).

- [ ] **Step 5: 커밋**
```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/lib/board-graph.ts web/tests/board-graph.test.ts
git commit -m "$(printf 'feat(board): buildBoardGraph — WBS+작업물량 노드/엣지 빌드(필터·collapse 반영)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 3: 트리 레이아웃 순수 로직 (`lib/board-layout.ts`)

**Files:** Create `web/lib/board-layout.ts`; Test `web/tests/board-layout.test.ts`

- [ ] **Step 1: 실패 테스트**

`web/tests/board-layout.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { layoutBoard, COL_GAP, ROW_GAP } from "@/lib/board-layout";
import type { BoardNode, BoardEdge } from "@/lib/board-graph";

const n = (id: string, kind: "hier" | "qty", depth: number, parentId: string | null): BoardNode => ({
  id, kind, depth, label: id, parentId, hasChildren: false, reviewCount: 0,
});

describe("layoutBoard", () => {
  // root(0) → A(1) → [L1(2), L2(2)]  (L1,L2 리프)
  const nodes = [n("root", "hier", 0, null), n("A", "hier", 1, "root"), n("L1", "hier", 2, "A"), n("L2", "hier", 2, "A")];
  const edges: BoardEdge[] = [
    { id: "e1", source: "root", target: "A", review: false },
    { id: "e2", source: "A", target: "L1", review: false },
    { id: "e3", source: "A", target: "L2", review: false },
  ];

  it("x 는 depth*COL_GAP", () => {
    const pos = layoutBoard(nodes, edges);
    expect(pos.get("root")!.x).toBe(0);
    expect(pos.get("A")!.x).toBe(COL_GAP);
    expect(pos.get("L1")!.x).toBe(2 * COL_GAP);
  });

  it("리프는 ROW_GAP 간격으로 세로 배치", () => {
    const pos = layoutBoard(nodes, edges);
    expect(pos.get("L2")!.y - pos.get("L1")!.y).toBe(ROW_GAP);
  });

  it("부모 y = 자식 y 평균(가운데 정렬)", () => {
    const pos = layoutBoard(nodes, edges);
    expect(pos.get("A")!.y).toBe((pos.get("L1")!.y + pos.get("L2")!.y) / 2);
    expect(pos.get("root")!.y).toBe(pos.get("A")!.y);
  });
});
```

- [ ] **Step 2: 실패 확인** — `cd web && npx vitest run tests/board-layout.test.ts` → FAIL.

- [ ] **Step 3: 구현** `web/lib/board-layout.ts`:
```ts
import type { BoardNode, BoardEdge } from "@/lib/board-graph";

export const COL_GAP = 240;   // 컬럼(깊이) 간 x 간격
export const ROW_GAP = 56;    // 리프 간 y 간격

/** 좌→우 트리 배치. x=depth*COL_GAP. 리프는 등장 순서대로 ROW_GAP 누적,
 *  부모는 자식 y 평균(가운데). nodes/edges 는 buildBoardGraph 출력. */
export function layoutBoard(nodes: BoardNode[], edges: BoardEdge[]): Map<string, { x: number; y: number }> {
  const pos = new Map<string, { x: number; y: number }>();
  const childrenOf = new Map<string, string[]>();
  const has = new Set(nodes.map((nd) => nd.id));
  for (const e of edges) {
    if (!has.has(e.source) || !has.has(e.target)) continue;
    const arr = childrenOf.get(e.source) ?? [];
    arr.push(e.target);
    childrenOf.set(e.source, arr);
  }
  const depthOf = new Map(nodes.map((nd) => [nd.id, nd.depth]));
  const roots = nodes.filter((nd) => nd.parentId === null || !has.has(nd.parentId)).map((nd) => nd.id);

  let nextLeafY = 0;
  // post-order: 리프면 다음 y 슬롯, 아니면 자식 평균
  const place = (id: string): number => {
    const x = (depthOf.get(id) ?? 0) * COL_GAP;
    const kids = childrenOf.get(id) ?? [];
    let y: number;
    if (kids.length === 0) {
      y = nextLeafY;
      nextLeafY += ROW_GAP;
    } else {
      const ys = kids.map((k) => place(k));
      y = ys.reduce((a, b) => a + b, 0) / ys.length;
    }
    pos.set(id, { x, y });
    return y;
  };
  for (const r of roots) place(r);
  return pos;
}
```

- [ ] **Step 4: 통과 확인** — `cd web && npx vitest run tests/board-layout.test.ts` → PASS(3).

- [ ] **Step 5: 커밋**
```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/lib/board-layout.ts web/tests/board-layout.test.ts
git commit -m "$(printf 'feat(board): layoutBoard — 좌→우 트리 좌표(depth=x, 리프 누적, 부모 가운데)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 4: 프레젠테이션 노드 바디 (`board/HierBox.tsx`, `board/QtyCard.tsx`)

**Files:** Create `web/app/components/review/board/HierBox.tsx`, `web/app/components/review/board/QtyCard.tsx`; Test `web/tests/board-nodes.test.tsx`

RF 무관 순수 표현 컴포넌트(테스트 대상). RF 노드 래퍼(Task 5)가 Handle 과 함께 감싼다.

- [ ] **Step 1: 실패 테스트**

`web/tests/board-nodes.test.tsx`:
```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { HierBox } from "@/app/components/review/board/HierBox";
import { QtyCard } from "@/app/components/review/board/QtyCard";
import type { ReviewItem } from "@/lib/types";

describe("HierBox", () => {
  it("라벨·미확정 배지 표시, 자식 있으면 캐럿(▾/▸)", () => {
    render(<HierBox label="골조" reviewCount={2} hasChildren collapsed={false} onToggle={() => {}} />);
    expect(screen.getByText("골조")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("▾")).toBeTruthy();
  });
  it("collapsed 면 ▸, 클릭 시 onToggle", () => {
    const onToggle = vi.fn();
    render(<HierBox label="골조" reviewCount={0} hasChildren collapsed onToggle={onToggle} />);
    expect(screen.getByText("▸")).toBeTruthy();
    fireEvent.click(screen.getByText("골조"));
    expect(onToggle).toHaveBeenCalled();
  });
  it("자식 없으면 캐럿 없음", () => {
    render(<HierBox label="WP" reviewCount={0} hasChildren={false} collapsed={false} onToggle={() => {}} />);
    expect(screen.queryByText("▾")).toBeNull();
    expect(screen.queryByText("▸")).toBeNull();
  });
});

const item: ReviewItem = {
  id: "c1", idx: 0, bp_name: "대성철근", work_content: "기둥 주근 D25", quantity: 12, unit: "ton",
  ai_mapped_wp_id: "fab-기둥", ai_mapped_path: "p", wa: "FAB", l6_main: "기둥", confidence: 0.62, status: "unconfirmed",
};

describe("QtyCard", () => {
  it("검토(미확정) 카드는 강조 클래스 + 확정 버튼, 클릭 시 onConfirm", () => {
    const onConfirm = vi.fn();
    const { container } = render(<QtyCard item={item} onConfirm={onConfirm} />);
    expect(screen.getByText("대성철근")).toBeTruthy();
    expect(container.querySelector("[data-review='true']")).toBeTruthy();
    fireEvent.click(screen.getByText("확정"));
    expect(onConfirm).toHaveBeenCalledWith("c1");
  });
  it("확정 카드는 강조·확정버튼 없음", () => {
    render(<QtyCard item={{ ...item, status: "confirmed" }} onConfirm={() => {}} />);
    expect(screen.queryByText("확정")).toBeNull();
  });
});
```

- [ ] **Step 2: 실패 확인** — `cd web && npx vitest run tests/board-nodes.test.tsx` → FAIL.

- [ ] **Step 3: 구현**

`web/app/components/review/board/HierBox.tsx`:
```tsx
"use client";
import { cn } from "@/lib/utils";

interface Props {
  label: string;
  reviewCount: number;
  hasChildren: boolean;
  collapsed: boolean;
  onToggle: () => void;
}

/** 위계 노드(프로젝트/건물/공종/WP) — 전부 흰색. 자식 있으면 캐럿, 클릭 시 접기/펼치기. */
export function HierBox({ label, reviewCount, hasChildren, collapsed, onToggle }: Props) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex w-[180px] items-center gap-1.5 rounded-lg border border-border-soft bg-card px-2.5 py-2 text-left shadow-xs hover:bg-surface-soft"
    >
      {hasChildren && <span className="shrink-0 text-[10px] text-ink-light">{collapsed ? "▸" : "▾"}</span>}
      <span className="min-w-0 flex-1 truncate text-xs font-semibold text-ink-mid">{label}</span>
      {reviewCount > 0 && (
        <span className="shrink-0 rounded-full bg-sun-light px-1.5 py-0.5 font-mono text-[9px] font-bold text-sun-text">
          {reviewCount}
        </span>
      )}
    </button>
  );
}
```

`web/app/components/review/board/QtyCard.tsx`:
```tsx
"use client";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ReviewItem } from "@/lib/types";

interface Props {
  item: ReviewItem;
  onConfirm: (id: string) => void;
}

/** 작업물량 노드 — 흰색, 검토(미확정)면 sun 강조 + 확정 버튼. */
export function QtyCard({ item, onConfirm }: Props) {
  const review = item.status === "unconfirmed";
  return (
    <div
      data-review={review}
      className={cn(
        "w-[260px] rounded-lg border px-3 py-2 shadow-xs",
        review ? "border-sun bg-sun-light" : "border-border-soft bg-card"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={cn("text-xs font-bold", review ? "text-sun-text" : "text-ink")}>{item.bp_name}</span>
        <span className="font-mono text-[10px] text-ink-light">{Math.round(item.confidence * 100)}%</span>
      </div>
      <div className="mt-0.5 truncate text-[11px] text-ink-mid">{item.work_content}</div>
      {review && (
        <div className="mt-1.5 flex justify-end">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onConfirm(item.id); }}
            className="inline-flex items-center gap-1 rounded-md bg-brand px-2 py-1 text-[10px] font-semibold text-white hover:bg-brand-text"
          >
            <Check className="h-3 w-3" strokeWidth={2.5} /> 확정
          </button>
        </div>
      )}
    </div>
  );
}
```

> 색 토큰(tailwind.config 매핑 확인 완료): `bg-sun-light`(#fef3c7)·`text-sun-text`·`border-sun`(=sun-deep #d97706), `bg-card`(흰색)·`border-border-soft`·`text-ink/ink-mid/ink-light`, `bg-brand`(=deep royal)·`text-white`·`hover:bg-brand-text`, `bg-surface-soft`, `bg-mint`(=deep green)·`text-mint-text`·`border-mint`·`bg-mint-light`. **주의:** `sun`/`mint`/`brand` 의 DEFAULT 는 deep 색이고 light 는 `-light` 접미사다 (`bg-sun` = 진한 주황 ≠ 강조 배경). `border-border-c`·`bg-bg-soft`·`*-deep` 클래스는 존재하지 않음 — 위 토큰만 사용.

- [ ] **Step 4: 통과 확인** — `cd web && npx vitest run tests/board-nodes.test.tsx` → PASS(5).

- [ ] **Step 5: 커밋**
```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/app/components/review/board/HierBox.tsx web/app/components/review/board/QtyCard.tsx web/tests/board-nodes.test.tsx
git commit -m "$(printf 'feat(board): HierBox·QtyCard — 위계 흰색 노드/작업물량 검토강조 표현 컴포넌트\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 5: RF 커스텀 노드 래퍼 (`board/HierNode.tsx`, `board/QtyNode.tsx`)

**Files:** Create `web/app/components/review/board/HierNode.tsx`, `web/app/components/review/board/QtyNode.tsx`. (단위테스트 없음 — RF Handle 은 캔버스 컨텍스트 필요. tsc + 수동 QA 로 검증)

- [ ] **Step 1: 구현**

`web/app/components/review/board/HierNode.tsx`:
```tsx
"use client";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { HierBox } from "./HierBox";

export interface HierNodeData {
  label: string;
  reviewCount: number;
  hasChildren: boolean;
  collapsed: boolean;
  onToggle: (id: string) => void;
  [key: string]: unknown;
}

export function HierNode({ id, data }: NodeProps) {
  const d = data as HierNodeData;
  return (
    <>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <HierBox
        label={d.label}
        reviewCount={d.reviewCount}
        hasChildren={d.hasChildren}
        collapsed={d.collapsed}
        onToggle={() => d.onToggle(id)}
      />
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </>
  );
}
```

`web/app/components/review/board/QtyNode.tsx`:
```tsx
"use client";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { QtyCard } from "./QtyCard";
import type { ReviewItem } from "@/lib/types";

export interface QtyNodeData {
  item: ReviewItem;
  onConfirm: (id: string) => void;
  [key: string]: unknown;
}

export function QtyNode({ data }: NodeProps) {
  const d = data as QtyNodeData;
  return (
    <>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <QtyCard item={d.item} onConfirm={d.onConfirm} />
    </>
  );
}
```

- [ ] **Step 2: 타입 확인**

Run: `cd web && npx tsc --noEmit 2>&1 | grep -vE "\.next/" | grep -E "board/(HierNode|QtyNode)"` 
Expected: 출력 없음(에러 없음). (전체 src 에러도 `... | grep "error TS"` 로 0 확인)

- [ ] **Step 3: 커밋**
```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/app/components/review/board/HierNode.tsx web/app/components/review/board/QtyNode.tsx
git commit -m "$(printf 'feat(board): HierNode·QtyNode — React Flow 커스텀 노드 래퍼(Handle+Box/Card)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 6: ReviewBoard 캔버스 (`ReviewBoard.tsx`)

**Files:** Create `web/app/components/review/ReviewBoard.tsx`. (단위테스트 없음 — RF 캔버스. tsc + 수동 QA)

- [ ] **Step 1: 구현** `web/app/components/review/ReviewBoard.tsx`:
```tsx
"use client";
import { useMemo, useState, useCallback } from "react";
import {
  ReactFlow, ReactFlowProvider, Background, Controls,
  useReactFlow, type Node, type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { CheckCheck } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { buildBoardGraph } from "@/lib/board-graph";
import { layoutBoard } from "@/lib/board-layout";
import { HierNode } from "./board/HierNode";
import { QtyNode } from "./board/QtyNode";
import type { WBSNode, ReviewItem } from "@/lib/types";

interface Props {
  wbs: WBSNode;
  cards: ReviewItem[];
  onConfirm: (id: string) => void;
  onConfirmHighConf: () => void;
  onConfirmAll: () => void;
  onRemap: (id: string, newWpId: string, newPath: string) => void;
}

const nodeTypes = { hier: HierNode, qty: QtyNode };

function BoardInner({ wbs, cards, onConfirm, onConfirmHighConf, onConfirmAll, onRemap }: Props) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [reviewOnly, setReviewOnly] = useState(true);
  const { getIntersectingNodes } = useReactFlow();

  const toggle = useCallback((id: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const { rfNodes, rfEdges } = useMemo(() => {
    const { nodes, edges } = buildBoardGraph(wbs, cards, { collapsed, reviewOnly });
    const pos = layoutBoard(nodes, edges);
    const rfNodes: Node[] = nodes.map((n) => ({
      id: n.id,
      type: n.kind === "qty" ? "qty" : "hier",
      position: pos.get(n.id) ?? { x: 0, y: 0 },
      draggable: n.kind === "qty",          // 작업물량만 드래그(리맵)
      data:
        n.kind === "qty"
          ? { item: n.item!, onConfirm }
          : { label: n.label, reviewCount: n.reviewCount, hasChildren: n.hasChildren, collapsed: collapsed.has(n.id), onToggle: toggle },
    }));
    const rfEdges: Edge[] = edges.map((e) => ({
      id: e.id, source: e.source, target: e.target, type: "default",
      style: { stroke: e.review ? "#d97706" : "#cbd5e1", strokeWidth: e.review ? 2 : 1.5 },
    }));
    return { rfNodes, rfEdges };
  }, [wbs, cards, collapsed, reviewOnly, onConfirm, toggle]);

  // 작업물량 노드를 WP(hier) 노드 위에 드롭 → 리맵
  const onNodeDragStop = useCallback(
    (_e: React.MouseEvent, node: Node) => {
      if (node.type !== "qty") return;
      const hits = getIntersectingNodes(node).filter((n) => n.type === "hier");
      if (hits.length === 0) return;
      const target = hits[0];
      const item = (node.data as { item: ReviewItem }).item;
      if (target.id !== item.ai_mapped_wp_id) {
        onRemap(item.id, target.id, (target.data as { label?: string }).label ?? "");
      }
    },
    [getIntersectingNodes, onRemap]
  );

  return (
    <div className="relative h-full w-full">
      <div className="absolute right-3 top-3 z-10 flex items-center gap-3 rounded-lg border border-border-soft bg-card/90 px-3 py-1.5 shadow-sm backdrop-blur">
        <span className="text-xs font-medium text-ink">검토만</span>
        <Switch checked={reviewOnly} onCheckedChange={setReviewOnly} />
        <button type="button" onClick={onConfirmHighConf} className="inline-flex items-center gap-1 rounded-md border border-mint bg-card px-2.5 py-1 text-[11px] font-semibold text-mint-text hover:bg-mint-light/40">
          <CheckCheck className="h-3.5 w-3.5" /> 0.8↑ 확정
        </button>
        <button type="button" onClick={onConfirmAll} className="inline-flex items-center gap-1 rounded-md bg-mint px-2.5 py-1 text-[11px] font-semibold text-white hover:opacity-90">
          <CheckCheck className="h-3.5 w-3.5" /> 모두 확정
        </button>
      </div>
      <ReactFlow nodes={rfNodes} edges={rfEdges} nodeTypes={nodeTypes} onNodeDragStop={onNodeDragStop} fitView proOptions={{ hideAttribution: true }}>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}

export function ReviewBoard(props: Props) {
  return (
    <ReactFlowProvider>
      <BoardInner {...props} />
    </ReactFlowProvider>
  );
}
```

- [ ] **Step 2: 타입 확인**

Run: `cd web && npx tsc --noEmit 2>&1 | grep -vE "\.next/" | grep "error TS"`
Expected: 출력 없음. (RF 타입 `Node`/`Edge`/`NodeProps` 해석 — Task 1 설치 전제)

- [ ] **Step 3: 커밋**
```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add web/app/components/review/ReviewBoard.tsx
git commit -m "$(printf 'feat(board): ReviewBoard — React Flow 캔버스(그래프·레이아웃·툴바·드래그 리맵)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

> `Switch` 는 `@/components/ui/switch` (리스트 뷰에서 사용 중). `getIntersectingNodes` 는 RF v12 `useReactFlow()` 제공. `fitView` 로 초기 화면맞춤.

---

## Task 7: page.tsx 뷰 토글 탭 + 보드 분기

**Files:** Modify `web/app/(app)/review/page.tsx`

리스트 경로는 100% 보존하고, 헤더에 탭을 추가해 `view==="board"` 일 때 `ReviewBoard` 를 렌더. `ReviewBoard` 는 페이지가 이미 가진 데이터·핸들러를 받는다.

- [ ] **Step 1: import + 상태 추가**

`page.tsx` 상단 import 에 추가:
```tsx
import { ReviewBoard } from "@/app/components/review/ReviewBoard";
```
다른 useState 들 근처에 추가:
```tsx
  const [view, setView] = useState<"list" | "board">("list");
```

- [ ] **Step 2: 헤더에 탭 UI**

`page.tsx` 의 헤더 영역(제목 `WBS-작업 물량 관계 검토` 가 있는 `<div>` 블록) 안, 제목 아래 또는 우측에 세그먼트 토글 추가:
```tsx
        <div className="mt-3 inline-flex rounded-lg border border-border-soft bg-surface-soft p-0.5">
          <button
            type="button"
            onClick={() => setView("list")}
            className={view === "list" ? "rounded-md bg-card px-3 py-1 text-xs font-semibold text-ink shadow-xs" : "px-3 py-1 text-xs text-ink-light"}
          >
            리스트
          </button>
          <button
            type="button"
            onClick={() => setView("board")}
            className={view === "board" ? "rounded-md bg-card px-3 py-1 text-xs font-semibold text-ink shadow-xs" : "px-3 py-1 text-xs text-ink-light"}
          >
            보드
          </button>
        </div>
```

- [ ] **Step 3: 보드 분기 렌더**

기존 `<section>...</section>`(리스트 본문 — grid 가 들어있는 블록) 을 `view` 로 분기. 리스트 블록 전체를 `{view === "list" && ( ...기존 section... )}` 로 감싸고, 그 뒤에 보드 블록 추가:
```tsx
      {view === "board" && (
        <section className="mx-auto w-full max-w-screen-2xl px-6 pb-10 md:px-10" style={{ height: "calc(100vh - 220px)" }}>
          <div className="h-full rounded-card border border-border-soft bg-card overflow-hidden">
            <ReviewBoard
              wbs={wbs}
              cards={onlyUnconfirmed ? cards : registered}
              onConfirm={handleConfirm}
              onConfirmHighConf={handleConfirmHighConf}
              onConfirmAll={handleConfirmAll}
              onRemap={handleRemap}
            />
          </div>
        </section>
      )}
```
(리스트 `<section>` 은 `{view === "list" && (` 로 여는 것 외에 내용 변경 없음. `wbs`·`cards`·`registered`·`onlyUnconfirmed`·`handleConfirm`·`handleConfirmHighConf`·`handleConfirmAll`·`handleRemap` 은 이미 페이지에 존재.)

- [ ] **Step 4: 타입·src 빌드 확인**

Run: `cd web && npx tsc --noEmit 2>&1 | grep -vE "\.next/" | grep "error TS"`
Expected: 출력 없음.

- [ ] **Step 5: 전체 단위테스트 회귀**

Run: `cd web && npx vitest run tests/board-graph.test.ts tests/board-layout.test.ts tests/board-nodes.test.tsx tests/review-group.test.ts tests/review-tree.test.ts tests/wbs-tree-reveal.test.tsx tests/review-card-readonly.test.tsx tests/wp-group.test.tsx tests/review-connector.test.tsx`
Expected: 전부 PASS.

- [ ] **Step 6: 커밋**
```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git add "web/app/(app)/review/page.tsx"
git commit -m "$(printf 'feat(review): /review 리스트·보드 탭 토글 + 보드 뷰 배선\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 8: 수동 검증(HMR) + 최종 점검

**Files:** 없음(실행·확인)

- [ ] **Step 1: dev 컨테이너에 새 의존성 반영**

`@xyflow/react` 는 컨테이너 named volume 에 없으므로 재기동해 install:
```bash
docker restart cpia-web-dev
docker logs -f cpia-web-dev   # "added ... packages" + "Ready" 확인 후 Ctrl-C
```
(또는 레포 루트 `make dev2`.)

- [ ] **Step 2: 보드 탭 확인** — http://localhost:5537/review

체크리스트:
- [ ] 상단 `리스트 / 보드` 탭, 기본 리스트(기존 화면 정상)
- [ ] `보드` 클릭 → 프로젝트›건물›공종›WP›작업물량 노드-링크 마인드맵
- [ ] WBS 위계 4단계 전부 흰색, 검토(미확정) 작업물량만 노랑 강조 + 그 엣지 강조
- [ ] 위계 노드 클릭 → 하위 가지 접힘/펼침
- [ ] `검토만` 토글 ON → 우측 작업물량은 미확정만, **WBS 위계 노드는 그대로 유지**
- [ ] 작업물량 노드를 다른 WP 노드 위로 드래그 → 엣지가 새 WP 로 재연결(리맵)
- [ ] 작업물량 `확정` 버튼 / 툴바 `0.8↑ 확정`·`모두 확정` 동작, 미확정 0 시 resume
- [ ] 팬/줌(Controls) 동작, 리스트 탭으로 복귀 시 기존 화면 정상

- [ ] **Step 3: 최종 코드리뷰 (전체 보드 피처)**

`buildBoardGraph`·`layoutBoard`·노드·`ReviewBoard`·page 토글의 응집성, 데이터 흐름(드래그 리맵 → handleRemap → 카드 ai_mapped_wp_id 갱신 → 그래프 재빌드 → 엣지 이동), Set/Map downlevel-iteration 부재, 리스트 경로 무손상 확인.

- [ ] **Step 4: 최종 커밋(잔여 정리 시)**
```bash
cd "/home/zoai/Projects/2026_FLP/Module2/01_AI Design Project"
git status --short   # 내 변경만 확인
```

---

## Self-Review (작성자 점검)

**Spec 커버리지:**
- 탭 위치(/review 리스트·보드) → Task 7 ✅
- 좌→우 마인드맵 5열(프로젝트›건물›공종›WP›작업물량) → Task 2(depth)·3(x=depth*COL_GAP) ✅
- React Flow 렌더 → Task 1·5·6 ✅
- 위계 전부 흰색 / 검토 작업물량만 sun 강조 → Task 4(HierBox 흰색, QtyCard review=sun) ✅
- 접기/펼치기(노드 클릭) → Task 4(onToggle)·6(collapsed state)·2(collapsed 제외) ✅
- 필터는 작업물량만 / WBS 항상 표시 → Task 2(reviewOnly 는 qty 만 거름, hier 전부 push) ✅
- 드래그 리맵 → Task 6(onNodeDragStop + getIntersectingNodes → onRemap) ✅
- 확정(노드+툴바) + resume → Task 4·6(onConfirm/onConfirmHighConf/onConfirmAll = page 핸들러) ✅
- 데이터 재사용(신규 API 없음) → Task 6·7(props 로 wbs/cards 전달) ✅

**비목표 준수:** dagre 없음(커스텀 layout), 등록 모드 정교화 후순위(board 는 cards 받음 — onlyUnconfirmed 시 cards, 아니면 registered 전달), 실데이터 변경 없음 ✅

**타입 일관성:** `BoardNode`/`BoardEdge`(board-graph) ↔ layoutBoard 입력 ↔ ReviewBoard 소비 일치. `HierNodeData`/`QtyNodeData` ↔ 노드 data 매핑 일치. `onConfirm`/`onConfirmHighConf`/`onConfirmAll`/`onRemap` 시그니처 page 핸들러와 일치(handleConfirmHighConf 는 2026-06-02 리스트 작업에서 이미 page 에 존재) ✅

**플레이스홀더:** 없음(모든 코드 블록 실체 포함). Tailwind 토큰은 tailwind.config 매핑 확인 후 정정 완료(`bg-sun-light`/`border-sun`/`bg-mint`/`bg-surface-soft`/`border-border-soft` — deep/light 구분 주의, Task 4 노트) ✅

**알려진 한계:** RF 노드/캔버스는 jsdom 단위테스트 어려움 → 순수 로직·바디만 TDD, 캔버스는 tsc+수동 QA(의도적). `getIntersectingNodes` 히트테스트는 노드 박스 겹침 기준 — 드롭 정밀도는 수동 QA 에서 확인.
