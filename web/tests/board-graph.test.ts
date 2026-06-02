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
    expect(nodes.filter((n) => n.kind === "hier")).toHaveLength(5); // M15X, FAB, FAB::골조, fab-기둥, fab-슬래브
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
