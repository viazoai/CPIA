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
