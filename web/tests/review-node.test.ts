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
