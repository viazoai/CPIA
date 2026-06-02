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
