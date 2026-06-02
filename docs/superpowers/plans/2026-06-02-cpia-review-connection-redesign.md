# Human Review 연결 표현 재설계 (C·하이브리드) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/review`(H-i-L 1) 화면에서 작업물량을 WP로 그룹핑(1:N 집계 노출)하고, 선택 카드↔WBS 트리 노드를 연결선으로 이어 좌↔우 시선 이동을 없앤다. HIL 검토 모드·등록 열람 모드 양쪽에 적용.

**Architecture:** 순수 로직(그룹핑·트리 조상 탐색)은 `lib/`로 분리해 vitest로 TDD. `WBSTree`의 펼침 상태를 controlled 로 끌어올려 "조상 자동 펼침+스크롤"을 지원하고 각 노드에 `data-wbs-node-id` 를 부여. 신규 `ReviewConnector` 오버레이가 grid 컨테이너 기준으로 카드 앵커·트리 노드 앵커의 `getBoundingClientRect()` 를 읽어 SVG 베지어를 그리고 스크롤·리사이즈 시 다시 그린다. `page.tsx` 는 그룹 렌더·`selectedCardId`·footer 2버튼을 배선.

**Tech Stack:** Next.js 14 (App Router, client component), React 18, TypeScript, Tailwind, vitest + @testing-library/react (jsdom), lucide-react.

**대상 파일:**
- Create: `web/lib/review-group.ts`, `web/lib/review-tree.ts`, `web/app/components/review/WpGroup.tsx`, `web/app/components/review/ReviewConnector.tsx`
- Create(test): `web/tests/review-group.test.ts`, `web/tests/review-tree.test.ts`, `web/tests/wbs-tree-reveal.test.tsx`, `web/tests/review-connector.test.tsx`
- Modify: `web/app/components/review/WBSTree.tsx`, `web/app/components/review/ReviewCard.tsx`, `web/app/(app)/review/page.tsx`

**검증 규약:** 테스트는 `web/` 에서 `npm run test -- <file>` (vitest run). 타입·빌드는 `npm run build`. 시각/인터랙션은 5536(`npm run dev`) HMR 수동 확인.

**커밋 규약:** B_Track 직접 커밋. 메시지 말미에 한 줄 공백 후
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## File Structure

- `lib/review-group.ts` — `WpGroup` 타입 + `groupCardsByWp(cards)`: 카드를 `ai_mapped_wp_id` 로 묶고 집계·정렬. UI 무관 순수 함수.
- `lib/review-tree.ts` — `ancestorIds(root, id)`, `idsByMaxDepth(root, n)`: WBS 트리 조상/초기펼침 계산. 순수 함수.
- `components/review/WpGroup.tsx` — 한 WP 그룹의 헤더(집계 배지)+카드 목록. HIL 은 확정 항목 접힘 토글, 등록(readOnly)은 전 항목 노출.
- `components/review/ReviewConnector.tsx` — grid 위 절대배치 SVG 오버레이. 선택 카드↔트리 노드 베지어.
- `components/review/WBSTree.tsx` — 펼침 controlled 화 + `revealNodeId` 자동 펼침·스크롤 + `data-wbs-node-id`.
- `components/review/ReviewCard.tsx` — `data-card-anchor` + `selected` 하이라이트 + 클릭 콜백.
- `(app)/review/page.tsx` — 그룹 렌더·`selectedCardId`·트리클릭 모드분기·footer 2버튼 배선.

---

## Task 1: 그룹핑 순수 로직 (`lib/review-group.ts`)

**Files:**
- Create: `web/lib/review-group.ts`
- Test: `web/tests/review-group.test.ts`

- [ ] **Step 1: 실패하는 테스트 작성**

`web/tests/review-group.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { groupCardsByWp } from "@/lib/review-group";
import type { ReviewItem } from "@/lib/types";

const mk = (over: Partial<ReviewItem>): ReviewItem => ({
  id: "x", idx: 0, bp_name: "BP", work_content: "w", quantity: 1, unit: "EA",
  ai_mapped_wp_id: "wp1", ai_mapped_path: "M15X > FAB > 기둥배근",
  wa: "FAB", l6_main: "기둥배근", confidence: 0.9, status: "unconfirmed",
  ...over,
});

describe("groupCardsByWp", () => {
  it("같은 wp_id 끼리 한 그룹으로 묶고 wpName/path 를 path 에서 분리", () => {
    const groups = groupCardsByWp([
      mk({ id: "a", ai_mapped_wp_id: "wp1" }),
      mk({ id: "b", ai_mapped_wp_id: "wp1" }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].wpId).toBe("wp1");
    expect(groups[0].wpName).toBe("기둥배근");
    expect(groups[0].path).toBe("M15X > FAB");
    expect(groups[0].items).toHaveLength(2);
  });

  it("집계: 확정/미확정 카운트 + 미확정 최저 확신도", () => {
    const [g] = groupCardsByWp([
      mk({ id: "a", status: "unconfirmed", confidence: 0.62 }),
      mk({ id: "b", status: "unconfirmed", confidence: 0.58 }),
      mk({ id: "c", status: "confirmed", confidence: 0.95 }),
    ]);
    expect(g.unconfirmedCount).toBe(2);
    expect(g.confirmedCount).toBe(1);
    expect(g.minUnconfirmedConfidence).toBeCloseTo(0.58);
    expect(g.allConfirmed).toBe(false);
  });

  it("정렬: 미확정 포함 그룹이 위(최저확신도 오름차순), 전부확정 그룹은 아래(이름순)", () => {
    const groups = groupCardsByWp([
      mk({ id: "z", ai_mapped_wp_id: "wpZ", ai_mapped_path: "M15X > Z", status: "confirmed" }),
      mk({ id: "a", ai_mapped_wp_id: "wpA", ai_mapped_path: "M15X > A", status: "unconfirmed", confidence: 0.7 }),
      mk({ id: "b", ai_mapped_wp_id: "wpB", ai_mapped_path: "M15X > B", status: "unconfirmed", confidence: 0.5 }),
    ]);
    expect(groups.map((g) => g.wpId)).toEqual(["wpB", "wpA", "wpZ"]);
  });

  it("그룹 내 항목은 미확정(확신도 오름차순) 먼저, 그다음 확정", () => {
    const [g] = groupCardsByWp([
      mk({ id: "c1", status: "confirmed", confidence: 0.99 }),
      mk({ id: "u1", status: "unconfirmed", confidence: 0.8 }),
      mk({ id: "u2", status: "unconfirmed", confidence: 0.6 }),
    ]);
    expect(g.items.map((i) => i.id)).toEqual(["u2", "u1", "c1"]);
  });

  it("path 에 구분자 없으면 wpName=path, path=''", () => {
    const [g] = groupCardsByWp([mk({ ai_mapped_path: "단일" })]);
    expect(g.wpName).toBe("단일");
    expect(g.path).toBe("");
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd web && npm run test -- tests/review-group.test.ts`
Expected: FAIL — `groupCardsByWp` is not defined / 모듈 없음.

- [ ] **Step 3: 최소 구현**

`web/lib/review-group.ts`:

```ts
import type { ReviewItem } from "@/lib/types";

export interface WpGroup {
  wpId: string;                          // ai_mapped_wp_id (= WBSNode.id, 연결선 타깃)
  wpName: string;                        // ai_mapped_path 마지막 세그먼트
  path: string;                          // 마지막 제외 상위 경로 (예 "M15X > FAB")
  items: ReviewItem[];                   // 미확정(확신도 오름차순) → 확정 순
  confirmedCount: number;
  unconfirmedCount: number;
  minUnconfirmedConfidence: number | null;
  allConfirmed: boolean;
}

const SEP = " > ";

function splitPath(p: string): { wpName: string; path: string } {
  const parts = p.split(SEP);
  if (parts.length <= 1) return { wpName: p, path: "" };
  return { wpName: parts[parts.length - 1], path: parts.slice(0, -1).join(SEP) };
}

export function groupCardsByWp(cards: ReviewItem[]): WpGroup[] {
  const byId = new Map<string, ReviewItem[]>();
  for (const c of cards) {
    const arr = byId.get(c.ai_mapped_wp_id) ?? [];
    arr.push(c);
    byId.set(c.ai_mapped_wp_id, arr);
  }

  const groups: WpGroup[] = [];
  for (const [wpId, raw] of byId) {
    const unconfirmed = raw
      .filter((c) => c.status === "unconfirmed")
      .sort((a, b) => a.confidence - b.confidence);
    const confirmed = raw.filter((c) => c.status === "confirmed");
    const { wpName, path } = splitPath(raw[0].ai_mapped_path);
    groups.push({
      wpId,
      wpName,
      path,
      items: [...unconfirmed, ...confirmed],
      confirmedCount: confirmed.length,
      unconfirmedCount: unconfirmed.length,
      minUnconfirmedConfidence: unconfirmed.length ? unconfirmed[0].confidence : null,
      allConfirmed: unconfirmed.length === 0,
    });
  }

  return groups.sort((a, b) => {
    if (a.allConfirmed !== b.allConfirmed) return a.allConfirmed ? 1 : -1;
    if (!a.allConfirmed && !b.allConfirmed) {
      return (a.minUnconfirmedConfidence ?? 1) - (b.minUnconfirmedConfidence ?? 1);
    }
    return a.wpName.localeCompare(b.wpName);
  });
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd web && npm run test -- tests/review-group.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: 커밋**

```bash
git add web/lib/review-group.ts web/tests/review-group.test.ts
git commit -m "$(printf 'feat(review): groupCardsByWp — WP 그룹핑·집계·정렬 순수 로직\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 2: 트리 조상/초기펼침 순수 로직 (`lib/review-tree.ts`)

**Files:**
- Create: `web/lib/review-tree.ts`
- Test: `web/tests/review-tree.test.ts`

- [ ] **Step 1: 실패하는 테스트 작성**

`web/tests/review-tree.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { ancestorIds, idsByMaxDepth } from "@/lib/review-tree";
import type { WBSNode } from "@/lib/types";

const n = (id: string, type: WBSNode["type"], children: WBSNode[] = []): WBSNode => ({
  id, type, name: id, parent_id: null, review_count: 0, total_count: 0, status: "normal", children,
});

const tree = n("site", "building", [
  n("FAB", "trade", [
    n("FAB::골조", "trade", [n("wp1", "work_package"), n("wp2", "work_package")]),
  ]),
  n("CUB", "trade", []),
]);

describe("ancestorIds", () => {
  it("WP 의 조상(자신 제외) 을 root→부모 순으로", () => {
    expect(ancestorIds(tree, "wp1")).toEqual(["site", "FAB", "FAB::골조"]);
  });
  it("없는 id → 빈 배열", () => {
    expect(ancestorIds(tree, "none")).toEqual([]);
  });
  it("root id → 빈 배열(조상 없음)", () => {
    expect(ancestorIds(tree, "site")).toEqual([]);
  });
  it("null root → 빈 배열", () => {
    expect(ancestorIds(null, "wp1")).toEqual([]);
  });
});

describe("idsByMaxDepth", () => {
  it("depth < 2 인 노드 ids (root=0, FAB=1)", () => {
    expect(idsByMaxDepth(tree, 2).sort()).toEqual(["CUB", "FAB", "site"].sort());
  });
  it("null root → 빈 배열", () => {
    expect(idsByMaxDepth(null, 2)).toEqual([]);
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd web && npm run test -- tests/review-tree.test.ts`
Expected: FAIL — 모듈/함수 없음.

- [ ] **Step 3: 최소 구현**

`web/lib/review-tree.ts`:

```ts
import type { WBSNode } from "@/lib/types";

/** target 의 조상 id 들을 root→부모 순으로 (target 자신 제외). 못 찾으면 []. */
export function ancestorIds(root: WBSNode | null, targetId: string): string[] {
  if (!root) return [];
  const path: string[] = [];
  const dfs = (node: WBSNode, trail: string[]): boolean => {
    if (node.id === targetId) {
      path.push(...trail);
      return true;
    }
    for (const c of node.children ?? []) {
      if (dfs(c, [...trail, node.id])) return true;
    }
    return false;
  };
  dfs(root, []);
  return path;
}

/** depth < maxDepthExclusive 인 노드들의 id (root depth=0). 초기 펼침 집합용. */
export function idsByMaxDepth(root: WBSNode | null, maxDepthExclusive: number): string[] {
  if (!root) return [];
  const out: string[] = [];
  const walk = (node: WBSNode, depth: number) => {
    if (depth < maxDepthExclusive) out.push(node.id);
    for (const c of node.children ?? []) walk(c, depth + 1);
  };
  walk(root, 0);
  return out;
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd web && npm run test -- tests/review-tree.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 5: 커밋**

```bash
git add web/lib/review-tree.ts web/tests/review-tree.test.ts
git commit -m "$(printf 'feat(review): ancestorIds·idsByMaxDepth — 트리 조상/초기펼침 순수 로직\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 3: WBSTree — 펼침 controlled 화 + revealNodeId 자동 펼침·스크롤 + 노드 앵커

**Files:**
- Modify: `web/app/components/review/WBSTree.tsx`
- Test: `web/tests/wbs-tree-reveal.test.tsx`

기존 `Branch` 의 로컬 `open` 상태를 WBSTree 레벨 `expanded: Set<string>` 로 끌어올린다. `revealNodeId` 가 바뀌면 조상을 펼치고 해당 노드로 스크롤. 각 노드 행에 `data-wbs-node-id` 부여(연결선 앵커).

- [ ] **Step 1: 실패하는 테스트 작성**

`web/tests/wbs-tree-reveal.test.tsx`:

```tsx
import { describe, it, expect, beforeAll, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { WBSTree } from "@/app/components/review/WBSTree";
import type { WBSNode } from "@/lib/types";

beforeAll(() => {
  // jsdom 미구현 — no-op 으로 보강
  (Element.prototype as any).scrollIntoView = vi.fn();
});

const n = (id: string, type: WBSNode["type"], children: WBSNode[] = []): WBSNode => ({
  id, type, name: id, parent_id: null, review_count: 0, total_count: 0, status: "normal", children,
});
const tree = n("site", "building", [
  n("FAB", "trade", [n("FAB::골조", "trade", [n("wp1", "work_package")])]),
]);

describe("WBSTree revealNodeId", () => {
  it("기본은 depth<2 만 펼침 → 깊은 WP(wp1) 행은 처음엔 없음", () => {
    render(<WBSTree root={tree} selectedId={null} onSelect={() => {}} />);
    expect(screen.queryByText("wp1")).toBeNull();
  });

  it("revealNodeId 주면 조상 펼쳐져 wp1 행이 렌더되고 data-wbs-node-id 부여", () => {
    render(<WBSTree root={tree} selectedId={null} onSelect={() => {}} revealNodeId="wp1" />);
    const row = screen.getByText("wp1").closest("[data-wbs-node-id]");
    expect(row).toBeTruthy();
    expect(row?.getAttribute("data-wbs-node-id")).toBe("wp1");
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd web && npm run test -- tests/wbs-tree-reveal.test.tsx`
Expected: FAIL — `revealNodeId` prop 미지원 / 두 번째 테스트에서 wp1 못 찾음.

- [ ] **Step 3: 구현 — WBSTree.tsx 전체 교체**

`web/app/components/review/WBSTree.tsx`:

```tsx
"use client";
import { useEffect, useRef, useState } from "react";
import { AlertCircle, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { ancestorIds, idsByMaxDepth } from "@/lib/review-tree";
import type { WBSNode } from "@/lib/types";

interface Props {
  root: WBSNode;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDrop?: (cardId: string, wpId: string) => void;
  /** 이 노드를 화면에 들인다 — 조상 자동 펼침 + 스크롤. */
  revealNodeId?: string | null;
}

const INDENT_STEP = [0, 16, 32, 48, 64, 80] as const;
function indentPx(depth: number): number {
  return INDENT_STEP[Math.min(depth, INDENT_STEP.length - 1)];
}

const LEVEL_TEXT: Record<number, string> = {
  0: "text-body-sm font-bold text-ink",
  1: "text-sm font-semibold text-ink",
  2: "text-xs font-medium text-ink",
  3: "text-xs text-ink-mid",
};
function levelTextClass(depth: number) {
  return LEVEL_TEXT[depth] ?? LEVEL_TEXT[3];
}

export function WBSTree({ root, selectedId, onSelect, onDrop, revealNodeId }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(idsByMaxDepth(root, 2)));
  const scrollRef = useRef<HTMLDivElement>(null);

  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  // revealNodeId → 조상 펼침 + 스크롤 (펼침 반영 후 다음 프레임).
  useEffect(() => {
    if (!revealNodeId) return;
    const anc = ancestorIds(root, revealNodeId);
    if (anc.length) setExpanded((prev) => new Set([...prev, ...anc]));
    const raf = requestAnimationFrame(() => {
      const el = scrollRef.current?.querySelector(`[data-wbs-node-id="${CSS.escape(revealNodeId)}"]`);
      const fn = (el as any)?.scrollIntoView;
      if (typeof fn === "function") fn.call(el, { block: "nearest", behavior: "smooth" });
    });
    return () => cancelAnimationFrame(raf);
  }, [revealNodeId, root]);

  return (
    <div className="flex flex-col h-full text-sm">
      <div className="shrink-0 border-b border-border-soft px-5 py-3 font-display text-h6 font-bold text-ink">
        WBS
        <span className="ml-2 text-body-sm font-normal text-ink-mid">(건물 &gt; 공종 &gt; Work Package)</span>
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3">
        <Branch
          node={root}
          depth={0}
          selectedId={selectedId}
          expanded={expanded}
          onToggle={toggle}
          onSelect={onSelect}
          onDrop={onDrop}
        />
      </div>
    </div>
  );
}

interface BranchProps {
  node: WBSNode;
  depth: number;
  selectedId: string | null;
  expanded: Set<string>;
  onToggle: (id: string) => void;
  onSelect: (id: string) => void;
  onDrop?: (cardId: string, wpId: string) => void;
}

function Branch({ node, depth, selectedId, expanded, onToggle, onSelect, onDrop }: BranchProps) {
  const open = expanded.has(node.id);
  const hasChildren = !!(node.children && node.children.length > 0);
  const isSelected = node.id === selectedId;
  const isWP = node.type === "work_package";
  const [dragOver, setDragOver] = useState(false);

  return (
    <div>
      <div
        data-wbs-node-id={node.id}
        className={cn(
          "group flex items-center gap-1.5 py-1.5 pr-2 rounded-sm cursor-pointer transition-colors",
          isSelected ? "bg-brand-light text-brand-text font-semibold" : "hover:bg-surface-soft",
          dragOver && "ring-2 ring-mint"
        )}
        style={{ paddingLeft: 8 + indentPx(depth) }}
        onClick={() => onSelect(node.id)}
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
          <button
            type="button"
            aria-label={open ? "접기" : "펼치기"}
            aria-expanded={open}
            onClick={(e) => {
              e.stopPropagation();
              onToggle(node.id);
            }}
            className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm text-ink-mid hover:bg-surface-soft hover:text-ink"
          >
            {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
        ) : (
          <span className="inline-block h-4 w-4 shrink-0" aria-hidden />
        )}
        <span className={cn("flex-1 truncate", levelTextClass(depth))}>{node.name}</span>
        <div className="ml-auto flex items-center gap-1 shrink-0 tabular-nums">
          {node.review_count > 0 && (
            <AlertCircle className="h-3 w-3 text-sun-text" aria-label={`미확정 ${node.review_count}건`} />
          )}
          <span className="font-mono text-[11px] text-ink-mid">{node.total_count}</span>
        </div>
      </div>

      {open && hasChildren && node.children!.map((c) => (
        <Branch
          key={c.id}
          node={c}
          depth={depth + 1}
          selectedId={selectedId}
          expanded={expanded}
          onToggle={onToggle}
          onSelect={onSelect}
          onDrop={onDrop}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd web && npm run test -- tests/wbs-tree-reveal.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: 회귀 확인 — 기존 review 테스트**

Run: `cd web && npm run test -- tests/review-node.test.ts tests/review-card-readonly.test.tsx`
Expected: PASS (변경 없음 확인).

- [ ] **Step 6: 커밋**

```bash
git add web/app/components/review/WBSTree.tsx web/tests/wbs-tree-reveal.test.tsx
git commit -m "$(printf 'feat(review): WBSTree 펼침 controlled + revealNodeId 자동펼침·스크롤 + data-wbs-node-id\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 4: ReviewCard — 연결선 앵커 + 선택 하이라이트 + 클릭 콜백

**Files:**
- Modify: `web/app/components/review/ReviewCard.tsx`
- Test: `web/tests/review-card-readonly.test.tsx` (기존 파일에 케이스 추가)

카드 root 에 `data-card-anchor={item.id}` 를 부여(연결선 시작점), `selected`·`onSelectCard` prop 추가. 카드 본문 클릭(버튼 제외) 시 `onSelectCard(item.id)`. 버튼은 이미 `justify-end` 우측 정렬 — 유지.

- [ ] **Step 1: 실패하는 테스트 작성 — 기존 파일에 describe 추가**

`web/tests/review-card-readonly.test.tsx` 끝(마지막 `});` 뒤)에 추가:

```tsx
import { fireEvent } from "@testing-library/react";

describe("ReviewCard 선택/앵커", () => {
  it("data-card-anchor 에 item.id 부여", () => {
    const { container } = render(
      <ReviewCard item={item} wbsRoot={wbs} onConfirm={() => {}} onRemap={() => {}} />
    );
    expect(container.querySelector(`[data-card-anchor="r1"]`)).toBeTruthy();
  });

  it("본문 클릭 시 onSelectCard(item.id) 호출", () => {
    const onSelectCard = vi.fn();
    render(
      <ReviewCard item={item} wbsRoot={wbs} onConfirm={() => {}} onRemap={() => {}} onSelectCard={onSelectCard} />
    );
    fireEvent.click(screen.getByText(/작업/));
    expect(onSelectCard).toHaveBeenCalledWith("r1");
  });
});
```

파일 상단 import 에 `vi` 추가: `import { describe, it, expect, vi } from "vitest";`

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd web && npm run test -- tests/review-card-readonly.test.tsx`
Expected: FAIL — `data-card-anchor` 없음 / `onSelectCard` 미호출.

- [ ] **Step 3: 구현 — ReviewCard.tsx 수정**

(1) Props 인터페이스에 추가 (`readOnly?: boolean;` 아래):

```tsx
  readOnly?: boolean;
  selected?: boolean;
  onSelectCard?: (id: string) => void;
```

(2) 시그니처 구조분해에 추가:

```tsx
export function ReviewCard({ item, wbsRoot, onConfirm, onRemap, readOnly, selected, onSelectCard }: Props) {
```

(3) root `<div>` 에 `data-card-anchor`·클릭·선택 링 추가. 기존:

```tsx
    <div
      draggable={!isConfirmed && !readOnly}
      onDragStart={(e) => {
        if (isConfirmed || readOnly) return;
        e.dataTransfer.setData("text/card-id", item.id);
        e.dataTransfer.effectAllowed = "move";
      }}
      className={cn(
        "rounded-card border bg-card p-4 shadow-xs",
        isConfirmed ? "border-mint/30 bg-mint-light/10" : "border-sun/30 cursor-grab"
      )}
    >
```

를 다음으로 교체:

```tsx
    <div
      data-card-anchor={item.id}
      draggable={!isConfirmed && !readOnly}
      onDragStart={(e) => {
        if (isConfirmed || readOnly) return;
        e.dataTransfer.setData("text/card-id", item.id);
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={() => onSelectCard?.(item.id)}
      className={cn(
        "rounded-card border bg-card p-4 shadow-xs",
        isConfirmed ? "border-mint/30 bg-mint-light/10" : "border-sun/30 cursor-grab",
        selected && "ring-2 ring-brand/50 border-brand"
      )}
    >
```

> 주의: 카드 내부 버튼(`확정`/`수정`)·검색 입력의 클릭이 카드 선택과 겹치지 않도록, 각 `<button>`·콤보박스 wrapper 의 `onClick` 은 그대로 두되, 카드 root onClick 은 버블링으로 함께 호출돼도 무방(선택만 추가됨). 별도 stopPropagation 불필요.

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd web && npm run test -- tests/review-card-readonly.test.tsx`
Expected: PASS (기존 2 + 신규 2 = 4 tests).

- [ ] **Step 5: 커밋**

```bash
git add web/app/components/review/ReviewCard.tsx web/tests/review-card-readonly.test.tsx
git commit -m "$(printf 'feat(review): ReviewCard data-card-anchor + selected 하이라이트 + onSelectCard\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 5: WpGroup 컴포넌트 — 그룹 헤더 + 확정 접힘

**Files:**
- Create: `web/app/components/review/WpGroup.tsx`
- Test: `web/tests/wp-group.test.tsx`

한 `WpGroup` 을 렌더: 헤더(집계 배지)+ 미확정 카드 풀 노출. HIL 모드는 확정 항목을 `✓ 확정 N건 — 펼치기` 토글 뒤로 접음. readOnly(등록) 모드는 전 항목 노출 + 헤더 `등록 N건`.

- [ ] **Step 1: 실패하는 테스트 작성**

`web/tests/wp-group.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WpGroup } from "@/app/components/review/WpGroup";
import { groupCardsByWp } from "@/lib/review-group";
import type { ReviewItem, WBSNode } from "@/lib/types";

const wbs: WBSNode = { id: "s", type: "building", name: "s", parent_id: null, review_count: 0, total_count: 0, status: "normal", children: [] };
const mk = (over: Partial<ReviewItem>): ReviewItem => ({
  id: "x", idx: 0, bp_name: "BP", work_content: "작업내용", quantity: 1, unit: "EA",
  ai_mapped_wp_id: "wp1", ai_mapped_path: "M15X > FAB > 기둥배근",
  wa: "FAB", l6_main: "기둥배근", confidence: 0.6, status: "unconfirmed", ...over,
});
const noop = () => {};

describe("WpGroup (HIL)", () => {
  it("헤더에 확정·미확정 집계 표기, 미확정 카드 풀 노출", () => {
    const [g] = groupCardsByWp([
      mk({ id: "u1", status: "unconfirmed", confidence: 0.6 }),
      mk({ id: "c1", status: "confirmed", confidence: 0.95 }),
    ]);
    render(<WpGroup group={g} selectedCardId={null} wbsRoot={wbs} onConfirm={noop} onRemap={noop} onSelectCard={noop} />);
    expect(screen.getByText(/미확정/)).toBeTruthy();
    expect(screen.getByText("기둥배근")).toBeTruthy();
    // 확정 1건은 접혀 있음 → 토글 텍스트 존재, 카드 본문은 우선 숨김
    expect(screen.getByText(/확정 1건/)).toBeTruthy();
  });

  it("확정 접힘 토글 클릭 시 확정 카드 노출", () => {
    const [g] = groupCardsByWp([
      mk({ id: "u1", status: "unconfirmed" }),
      mk({ id: "c1", status: "confirmed", bp_name: "확정BP" }),
    ]);
    render(<WpGroup group={g} selectedCardId={null} wbsRoot={wbs} onConfirm={noop} onRemap={noop} onSelectCard={noop} />);
    expect(screen.queryByText("확정BP")).toBeNull();
    fireEvent.click(screen.getByText(/확정 1건/));
    expect(screen.getByText("확정BP")).toBeTruthy();
  });
});

describe("WpGroup (등록/readOnly)", () => {
  it("readOnly 면 헤더 '등록 N건', 전 항목 노출(접힘 없음)", () => {
    const [g] = groupCardsByWp([
      mk({ id: "r1", status: "confirmed", bp_name: "등록BP1" }),
      mk({ id: "r2", status: "confirmed", bp_name: "등록BP2" }),
    ]);
    render(<WpGroup group={g} selectedCardId={null} wbsRoot={wbs} onConfirm={noop} onRemap={noop} onSelectCard={noop} readOnly />);
    expect(screen.getByText(/등록 2건/)).toBeTruthy();
    expect(screen.getByText("등록BP1")).toBeTruthy();
    expect(screen.getByText("등록BP2")).toBeTruthy();
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd web && npm run test -- tests/wp-group.test.tsx`
Expected: FAIL — 모듈 없음.

- [ ] **Step 3: 구현**

`web/app/components/review/WpGroup.tsx`:

```tsx
"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight, AlertTriangle, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { ReviewCard } from "./ReviewCard";
import type { WpGroup as WpGroupData } from "@/lib/review-group";
import type { WBSNode } from "@/lib/types";

interface Props {
  group: WpGroupData;
  selectedCardId: string | null;
  wbsRoot: WBSNode;
  onConfirm: (id: string) => void;
  onRemap: (id: string, newWpId: string, newPath: string) => void;
  onSelectCard: (id: string) => void;
  readOnly?: boolean;
}

export function WpGroup({ group, selectedCardId, wbsRoot, onConfirm, onRemap, onSelectCard, readOnly }: Props) {
  const [showConfirmed, setShowConfirmed] = useState(false);

  const unconfirmed = group.items.filter((c) => c.status === "unconfirmed");
  const confirmed = group.items.filter((c) => c.status === "confirmed");
  // readOnly(등록) 모드는 전 항목 노출. HIL 모드는 확정 항목을 토글 뒤로 접음.
  const visibleConfirmed = readOnly || showConfirmed ? confirmed : [];
  const lowTone = !readOnly && group.unconfirmedCount > 0;

  return (
    <div className="mb-3">
      {/* 그룹 헤더 */}
      <div
        className={cn(
          "flex items-center gap-2 rounded-t-card px-3 py-2 text-xs font-bold border",
          lowTone ? "bg-sun-light/40 border-sun/40 text-sun-text" : "bg-mint-light/30 border-mint/30 text-mint-text"
        )}
      >
        {lowTone ? <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> : <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />}
        <span className="truncate">{group.wpName}</span>
        {group.path && <span className="truncate font-normal opacity-70 text-[10px]">{group.path}</span>}
        <span className="ml-auto shrink-0 font-mono text-[10px]">
          {readOnly
            ? `등록 ${group.items.length}건`
            : group.unconfirmedCount > 0
              ? `확정 ${group.confirmedCount} · 미확정 ${group.unconfirmedCount} · 최저 ${Math.round((group.minUnconfirmedConfidence ?? 0) * 100)}%`
              : `전부 확정 ${group.confirmedCount}건`}
        </span>
      </div>

      {/* 카드 목록 */}
      <div className="flex flex-col gap-2 rounded-b-card border border-t-0 border-border-soft p-2">
        {unconfirmed.map((c) => (
          <ReviewCard
            key={c.id}
            item={c}
            wbsRoot={wbsRoot}
            selected={c.id === selectedCardId}
            onConfirm={onConfirm}
            onRemap={onRemap}
            onSelectCard={onSelectCard}
            readOnly={readOnly}
          />
        ))}

        {/* HIL: 확정 항목 접힘 토글 */}
        {!readOnly && confirmed.length > 0 && (
          <button
            type="button"
            onClick={() => setShowConfirmed((v) => !v)}
            className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[11px] text-mint-text hover:bg-mint-light/30"
          >
            {showConfirmed ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            ✓ 확정 {confirmed.length}건 {showConfirmed ? "접기" : "펼치기"}
          </button>
        )}

        {visibleConfirmed.map((c) => (
          <ReviewCard
            key={c.id}
            item={c}
            wbsRoot={wbsRoot}
            selected={c.id === selectedCardId}
            onConfirm={onConfirm}
            onRemap={onRemap}
            onSelectCard={onSelectCard}
            readOnly={readOnly}
          />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd web && npm run test -- tests/wp-group.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: 커밋**

```bash
git add web/app/components/review/WpGroup.tsx web/tests/wp-group.test.tsx
git commit -m "$(printf 'feat(review): WpGroup — 그룹 헤더(집계)+확정 접힘 토글, 등록 모드 분기\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 6: ReviewConnector — 연결선 오버레이

**Files:**
- Create: `web/app/components/review/ReviewConnector.tsx`
- Test: `web/tests/review-connector.test.tsx`

grid 컨테이너 기준 절대배치 SVG. `selectedCardId`·`targetNodeId` 가 있으면 컨테이너 안에서 `[data-card-anchor]`·`[data-wbs-node-id]` 를 찾아 베지어를 그린다. 스크롤(capture)·리사이즈 시 다시 그린다. jsdom 은 layout 이 없어 좌표는 0 이지만 **렌더 분기**(선택 없으면 path 없음, 있으면 path 1개)는 검증 가능.

- [ ] **Step 1: 실패하는 테스트 작성**

`web/tests/review-connector.test.tsx`:

```tsx
import { describe, it, expect, useRef as _ } from "vitest";
import { render } from "@testing-library/react";
import { createRef } from "react";
import { ReviewConnector } from "@/app/components/review/ReviewConnector";

function Harness(props: { selectedCardId: string | null; targetNodeId: string | null }) {
  const ref = createRef<HTMLDivElement>();
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <div data-card-anchor="c1">card</div>
      <div data-wbs-node-id="n1">node</div>
      <ReviewConnector
        containerRef={ref}
        selectedCardId={props.selectedCardId}
        targetNodeId={props.targetNodeId}
        tone="sun"
        redrawKey={0}
      />
    </div>
  );
}

describe("ReviewConnector", () => {
  it("선택 없으면 path 미렌더", () => {
    const { container } = render(<Harness selectedCardId={null} targetNodeId={null} />);
    expect(container.querySelector("path")).toBeNull();
  });
  it("선택+타깃 있으면 path 1개 렌더", () => {
    const { container } = render(<Harness selectedCardId="c1" targetNodeId="n1" />);
    expect(container.querySelector("path")).toBeTruthy();
  });
});
```

> 참고: 첫 줄 `useRef as _` import 는 vitest 에서 불필요 — 아래 Step 3 확정본에서는 쓰지 않는다. 테스트 파일 그대로 사용(미사용 import 는 lint 경고만, 테스트 실행엔 무해). 깔끔히 하려면 그 import 절을 지워도 된다.

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd web && npm run test -- tests/review-connector.test.tsx`
Expected: FAIL — 모듈 없음.

- [ ] **Step 3: 구현**

`web/app/components/review/ReviewConnector.tsx`:

```tsx
"use client";
import { useEffect, useLayoutEffect, useState } from "react";

interface Props {
  containerRef: React.RefObject<HTMLElement>;
  selectedCardId: string | null;
  targetNodeId: string | null;        // = 선택 카드의 ai_mapped_wp_id
  tone: "mint" | "sun";
  /** 외부에서 강제 재드로잉 (펼침·모드 전환 등). */
  redrawKey: number;
}

export function ReviewConnector({ containerRef, selectedCardId, targetNodeId, tone, redrawKey }: Props) {
  const [path, setPath] = useState<string | null>(null);

  useLayoutEffect(() => {
    const compute = () => {
      const container = containerRef.current;
      if (!container || !selectedCardId || !targetNodeId) {
        setPath(null);
        return;
      }
      const cardEl = container.querySelector(`[data-card-anchor="${CSS.escape(selectedCardId)}"]`);
      const nodeEl = container.querySelector(`[data-wbs-node-id="${CSS.escape(targetNodeId)}"]`);
      if (!cardEl || !nodeEl) {
        setPath(null);
        return;
      }
      const c = container.getBoundingClientRect();
      const cr = cardEl.getBoundingClientRect();
      const nr = nodeEl.getBoundingClientRect();
      const x1 = cr.left - c.left;                 // 카드 왼쪽 가장자리
      const y1 = cr.top - c.top + cr.height / 2;   // 카드 세로 중앙
      const x2 = nr.right - c.left;                // 노드 오른쪽 가장자리
      const y2 = nr.top - c.top + nr.height / 2;   // 노드 세로 중앙
      const dx = Math.max(40, (x1 - x2) * 0.5);
      setPath(`M ${x1} ${y1} C ${x1 - dx} ${y1}, ${x2 + dx} ${y2}, ${x2} ${y2}`);
    };

    compute();

    let raf = 0;
    const schedule = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(compute);
    };
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true); // capture: 내부 스크롤 컨테이너 포함
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(schedule) : null;
    if (ro && containerRef.current) ro.observe(containerRef.current);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
      ro?.disconnect();
    };
  }, [containerRef, selectedCardId, targetNodeId, redrawKey]);

  if (!path) return null;
  const stroke = tone === "sun" ? "var(--sun, #d8a93a)" : "var(--mint, #16a34a)";

  return (
    <svg
      aria-hidden
      className="pointer-events-none absolute inset-0 h-full w-full"
      style={{ overflow: "visible", zIndex: 5 }}
    >
      <path d={path} fill="none" stroke={stroke} strokeWidth={2} strokeLinecap="round" />
      <circle cx={path.split(" ")[1]} cy={path.split(" ")[2]} r={3} fill={stroke} />
    </svg>
  );
}
```

> `useLayoutEffect` 는 SSR 경고를 낼 수 있으나 이 파일은 `"use client"` + 부모가 클라이언트에서만 마운트(데이터 fetch 후 렌더)하므로 안전. 경고가 거슬리면 `useEffect` 로 교체해도 동작 동일(첫 페인트 직후 1프레임 그려짐).

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd web && npm run test -- tests/review-connector.test.tsx`
Expected: PASS (2 tests). (jsdom 에서 rect 는 0 이지만 path 문자열은 생성되어 `<path>` 렌더됨.)

- [ ] **Step 5: 커밋**

```bash
git add web/app/components/review/ReviewConnector.tsx web/tests/review-connector.test.tsx
git commit -m "$(printf 'feat(review): ReviewConnector — 카드↔트리 노드 SVG 연결선 오버레이\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 7: page.tsx 배선 — 그룹 렌더 · selectedCardId · 트리클릭 모드분기 · footer 2버튼

**Files:**
- Modify: `web/app/(app)/review/page.tsx`
- Test: 없음(통합은 빌드+수동). 로직 회귀는 Task 1·2 단위테스트가 커버.

핵심 변경:
1. `selectedCardId` state 신설. 카드 클릭 → `setSelectedCardId` + 그 카드의 `ai_mapped_wp_id` 를 `revealNodeId` 로 WBSTree 에 전달(조상 펼침+스크롤).
2. 우측 리스트를 `groupCardsByWp(visibleCards)` 로 그룹 렌더(`WpGroup`). HIL 은 `cards` 전체(미확정+확정) 그룹핑, 등록은 `registered` 그룹핑(readOnly).
3. HIL 트리 노드 클릭 → 기존 wpIds 필터 폐지, 해당 WP 그룹으로 스크롤+선택. 등록 트리 클릭 → 기존 노드 스코프 fetch 유지.
4. grid 를 `relative` + `ReviewConnector` 마운트.
5. footer: `확신도 0.8↑ 일괄 확정`(신규) + `모두 확정`(기존 handleConfirmAll) 두 버튼.

- [ ] **Step 1: import 추가**

상단 import 블록(`import { WPSearchCombobox }` 등 근처)에 추가:

```tsx
import { useRef } from "react";
import { WpGroup } from "@/app/components/review/WpGroup";
import { ReviewConnector } from "@/app/components/review/ReviewConnector";
import { groupCardsByWp } from "@/lib/review-group";
```

> 이미 `import { useEffect, useState, useMemo } from "react";` 가 있으므로 `useRef` 만 그 줄에 합쳐도 된다: `import { useEffect, useState, useMemo, useRef } from "react";`

- [ ] **Step 2: state·파생값 추가** (다른 useState 들 아래)

```tsx
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  // HIL 은 cards 전체(확정 포함)를 그룹핑해 집계 노출. 등록은 registered.
  const groups = useMemo(
    () => groupCardsByWp(onlyUnconfirmed ? cards : registered),
    [onlyUnconfirmed, cards, registered]
  );

  // 선택 카드 → 연결선 타깃(WP id)·색(확신도)
  const selectedCard = useMemo(
    () => (onlyUnconfirmed ? cards : registered).find((c) => c.id === selectedCardId) ?? null,
    [onlyUnconfirmed, cards, registered, selectedCardId]
  );
  const connectorTone: "mint" | "sun" =
    selectedCard && selectedCard.status === "unconfirmed" && selectedCard.confidence < 0.8 ? "sun" : "mint";
  // 연결선 재드로잉 nudge — 모드/선택노드/그룹수 변할 때.
  const redrawKey = useMemo(
    () => (onlyUnconfirmed ? 1 : 0) * 1000 + groups.length,
    [onlyUnconfirmed, groups.length]
  );
```

- [ ] **Step 3: 카드 선택 핸들러** (handleConfirmAll 근처)

```tsx
  // 카드 선택 → 연결선 + 트리 자동 펼침/스크롤(해당 WP 노드).
  const handleSelectCard = (id: string) => {
    setSelectedCardId(id);
    const card = (onlyUnconfirmed ? cards : registered).find((c) => c.id === id);
    if (card) setSelectedNodeId(card.ai_mapped_wp_id);
  };

  // 확신도 0.8↑ 미확정만 일괄 확정 (저확신은 남김 → resume 보류).
  const handleConfirmHighConf = () => {
    setCards((cs) =>
      cs.map((c) =>
        c.status === "unconfirmed" && c.confidence >= 0.8 ? { ...c, status: "confirmed" as const } : c
      )
    );
  };
```

- [ ] **Step 4: 트리 onSelect 모드분기 + revealNodeId 전달**

기존 `<WBSTree root={wbs} selectedId={selectedNodeId} onSelect={setSelectedNodeId} onDrop={...} />` 의 `onSelect`·`revealNodeId` 를 교체:

```tsx
            <WBSTree
              root={wbs}
              selectedId={selectedNodeId}
              revealNodeId={selectedCard?.ai_mapped_wp_id ?? null}
              onSelect={(id) => {
                setSelectedNodeId(id);
                // HIL: 필터 폐지 → 선택만(그룹 스크롤은 selectedNodeId 기반 효과로 처리).
                //      등록: 기존 노드 스코프 fetch effect 가 selectedNodeId 변경에 반응(유지).
              }}
              onDrop={(cardId, wpId) => {
                const collectPath = (n: WBSNode | null, id: string, path: string[] = []): string[] | null => {
                  if (!n) return null;
                  const next = [...path, n.name];
                  if (n.id === id) return next;
                  for (const c of n.children || []) { const r = collectPath(c, id, next); if (r) return r; }
                  return null;
                };
                const path = collectPath(wbs, wpId)?.join(" > ") || "";
                handleRemap(cardId, wpId, path);
                setSelectedCardId(cardId);   // 리맵 직후 그 카드 선택 → 연결선이 새 노드로
              }}
            />
```

> HIL 필터 폐지: Step 6 에서 `visibleCards` 의 wpIds 필터를 제거한다. 트리 클릭 시 그룹 스크롤은 "선택 노드의 첫 그룹으로 스크롤" 효과(Step 7)로 처리.

- [ ] **Step 5: 우측 리스트를 그룹 렌더로 교체 + grid relative + Connector**

기존 `<section>` 내부의 `<div className="grid grid-cols-12 gap-4 items-stretch">` 를 `relative` 추가 + `ref` 부여:

```tsx
        <div ref={gridRef} className="relative grid grid-cols-12 gap-4 items-stretch">
```

그 grid 의 **첫 자식으로** Connector 추가(트리 div 위):

```tsx
          <ReviewConnector
            containerRef={gridRef}
            selectedCardId={selectedCardId}
            targetNodeId={selectedCard?.ai_mapped_wp_id ?? null}
            tone={connectorTone}
            redrawKey={redrawKey}
          />
```

우측 패널의 카드 목록 영역(기존 `visibleCards.map((c) => <ReviewCard .../>)` 블록)을 그룹 렌더로 교체:

```tsx
            <div className="flex flex-col gap-3 p-4 flex-1 overflow-y-auto">
              {groups.map((g) => (
                <WpGroup
                  key={g.wpId}
                  group={g}
                  selectedCardId={selectedCardId}
                  wbsRoot={wbs}
                  onConfirm={handleConfirm}
                  onRemap={handleRemap}
                  onSelectCard={handleSelectCard}
                  readOnly={!onlyUnconfirmed}
                />
              ))}
              {groups.length === 0 && (
                <div className="rounded-card border border-dashed border-border-soft py-12 text-center text-sm text-ink-light">
                  {onlyUnconfirmed ? "검토할 신규 매핑이 없습니다."
                    : registeredError ? "등록 작업을 불러오지 못했습니다. 잠시 후 다시 시도하세요."
                    : !selectedNodeId ? "좌측에서 공종 또는 WP를 선택하면 누적 등록 작업을 볼 수 있습니다."
                    : "이 공종에 등록된 작업이 없습니다."}
                </div>
              )}
            </div>
```

- [ ] **Step 6: visibleCards 의 HIL wpIds 필터 제거**

기존 `visibleCards` useMemo 에서 HIL 분기의 `selectedNodeId` 필터(약 89–100행) 를 제거하고, HIL 은 미확정·확정 **전체**를 반환하도록 단순화:

```tsx
  const visibleCards = useMemo(() => {
    // HIL 모드: cards 전체(미확정+확정) — 그룹 헤더 집계를 위해 필터하지 않음.
    //           (트리 노드 클릭은 필터가 아니라 그룹 스크롤로 동작)
    // 등록 모드: 서버가 노드 스코프로 준 registered 그대로.
    return onlyUnconfirmed ? cards : registered;
  }, [cards, registered, onlyUnconfirmed]);
```

> `visibleCards` 가 더 이상 직접 map 되지 않고 `groups` 의 소스이지만, `groups` 는 Step 2 에서 `onlyUnconfirmed ? cards : registered` 로 직접 계산하므로 `visibleCards` 는 미사용이 된다. **`visibleCards` useMemo 와 그 안의 `find`/`collect` 보조선언을 통째로 삭제**한다(미사용 변수 lint 에러 방지). `find` 는 등록 fetch effect(Step: 기존 line 49 `const node = find(wbs, selectedNodeId);`)에서도 쓰이므로, 파일 상단의 모듈 레벨 `find`(10–19행)는 **유지**한다. (page 내부 useMemo 안에 있던 지역 `collect`/`find` 만 제거)

- [ ] **Step 7: HIL 트리클릭 → 그룹 스크롤 효과 추가** (useEffect 들 근처)

```tsx
  // HIL: 트리 노드 선택 시 해당 노드 하위의 첫 그룹으로 우측 스크롤(+카드 선택은 안 함).
  useEffect(() => {
    if (!onlyUnconfirmed || !selectedNodeId || !gridRef.current) return;
    // 선택 노드가 work_package 면 그 그룹, 아니면 첫 매칭 그룹.
    const target = groups.find((g) => g.wpId === selectedNodeId) ?? null;
    if (!target) return;
    const el = gridRef.current.querySelector(`[data-wp-group="${CSS.escape(target.wpId)}"]`);
    const fn = (el as any)?.scrollIntoView;
    if (typeof fn === "function") fn.call(el, { block: "nearest", behavior: "smooth" });
  }, [onlyUnconfirmed, selectedNodeId, groups]);
```

그리고 `WpGroup.tsx` 의 최상위 `<div className="mb-3">` 에 `data-wp-group={group.wpId}` 를 추가(스크롤 타깃):

```tsx
    <div className="mb-3" data-wp-group={group.wpId}>
```

- [ ] **Step 8: footer 2버튼**

기존 footer 블록(`{onlyUnconfirmed && ( ... 모두 AI 추천대로 확정 ... )}`) 을 교체:

```tsx
            {onlyUnconfirmed && (
              <div className="px-4 py-3 border-t border-border-soft flex justify-end gap-2 shrink-0">
                <button
                  type="button"
                  onClick={handleConfirmHighConf}
                  className="inline-flex items-center gap-1.5 rounded-md border border-mint bg-white px-4 py-2 text-xs font-semibold text-mint-text hover:bg-mint-light/30 transition-colors"
                >
                  <CheckCheck className="h-4 w-4" strokeWidth={2.5} />
                  확신도 0.8↑ 일괄 확정
                </button>
                <button
                  type="button"
                  onClick={handleConfirmAll}
                  className="inline-flex items-center gap-1.5 rounded-md bg-mint px-4 py-2 text-xs font-semibold text-white hover:bg-mint-text transition-colors"
                >
                  <CheckCheck className="h-4 w-4" strokeWidth={2.5} />
                  모두 확정
                </button>
              </div>
            )}
```

- [ ] **Step 9: 타입·빌드 통과 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공(타입 에러 0). 미사용 변수/임포트 에러가 나면 Step 6 의 안내대로 `visibleCards`·지역 `collect` 잔재를 제거.

- [ ] **Step 10: 전체 테스트 회귀**

Run: `cd web && npm run test`
Expected: 전 테스트 PASS (기존 + Task 1·2·3·4·5·6 신규).

- [ ] **Step 11: 커밋**

```bash
git add "web/app/(app)/review/page.tsx" web/app/components/review/WpGroup.tsx
git commit -m "$(printf 'feat(review): page 배선 — WP 그룹 렌더·selectedCardId·연결선·트리클릭 그룹스크롤·footer 2버튼\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 8: 수동 검증 (HMR) + 최종 점검

**Files:** 없음(실행·확인만)

- [ ] **Step 1: dev 서버 기동**

Run: `cd web && npm run dev` (http://localhost:5536/review)
> DB 는 `.env` 의 `DEV_DB_URL`(AWS) 또는 로컬 — 현재 세션 설정 그대로. `pg` fetch 가 되는 환경이어야 카드가 보임.

- [ ] **Step 2: HIL 검토 모드 확인**

체크리스트:
- [ ] 우측이 WP 그룹으로 묶이고, 헤더에 `확정 N · 미확정 M · 최저 XX%` 표기
- [ ] 미확정 포함 그룹이 위로(최저 확신도 오름차순), 전부 확정 그룹은 아래
- [ ] 확정 항목은 `✓ 확정 N건 펼치기` 토글 뒤로 접힘, 클릭 시 노출
- [ ] 카드 클릭 → 좌측 트리의 해당 WP 노드가 자동 펼쳐지고 스크롤되며 연결선(주황/민트)이 그려짐
- [ ] 우측/좌측 스크롤·창 리사이즈 시 연결선이 따라 다시 그려짐
- [ ] 카드를 좌측 트리 WP 노드로 드래그&드롭 → 리맵되고 연결선이 새 노드로 이동
- [ ] 트리 노드 클릭 → 우측 해당 WP 그룹으로 스크롤(필터로 목록이 줄지 않음)
- [ ] footer `확신도 0.8↑ 일괄 확정` → 고확신 미확정이 확정으로 접힘(저확신 남음), `모두 확정` → 전부 확정 후 등록 모드 복귀 + `confirmedNotice` + resume

- [ ] **Step 3: 등록 열람 모드 확인**

- [ ] 토글 OFF → 좌측 노드 선택 시 노드 스코프 등록 항목이 WP 그룹으로 묶여 보임(헤더 `등록 N건`)
- [ ] 카드 read-only(확정/수정 버튼 없음, 배지 `등록`), 클릭 시 연결선만 표시
- [ ] 트리 노드 변경 시 기존대로 새 스코프 fetch

- [ ] **Step 4: 시연 빌드(선택) — 5535 갱신**

리뷰/시연 직전에만:
Run: 레포 루트에서 `make build` → `docker logs cpia-web --tail 10` 로 `✓ Ready` 확인.

- [ ] **Step 5: 최종 커밋(잔여 정리 있으면)**

```bash
git status --short   # 내 변경만 있는지 확인
# 잔여가 있으면:
git add -A && git commit -m "$(printf 'chore(review): 수동 검증 후 정리\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-Review (작성자 점검 결과)

**Spec 커버리지:**
- 레이아웃 4/8 + 연결선 오버레이(두 칼럼) → Task 6·7 ✅
- WP 그룹핑(집계 헤더, 정렬) 두 모드 → Task 1·5·7 ✅
- 확정 접힘(HIL only, 안 A) → Task 5 ✅
- 연결선 트리거(카드 클릭) + 조상 자동 펼침·스크롤 → Task 3·7 ✅
- 트리클릭 모드분기(HIL 스크롤 / 등록 fetch) → Task 7 ✅
- 리맵 드래그&드롭 + 연결선 전환 → Task 7(onDrop) ✅
- 검색 콤보박스 보조 → 기존 ReviewCard 유지(Task 4 비파괴) ✅
- footer 2버튼(0.8↑ / 모두 확정) + resume 의미 → Task 7 ✅
- 색=확신도 → Task 7 connectorTone ✅
- 보존(registered·confirmedNotice·nodeToQuery·readOnly) → Task 6·7 비파괴 ✅

**비목표 준수:** rewire 끝점 드래그·임계 슬라이더·너비 변경·실데이터 연결 없음 ✅

**타입 일관성:** `WpGroup`(타입, review-group.ts) ↔ `WpGroup`(컴포넌트, WpGroup.tsx) 동명이나 import alias(`WpGroup as WpGroupData`)로 충돌 회피(Task 5) ✅. `groupCardsByWp`·`ancestorIds`·`idsByMaxDepth`·`ReviewConnector` props·`onSelectCard` 시그니처 태스크 간 일치 ✅.

**플레이스홀더:** 없음(모든 코드 블록 실체 포함) ✅
