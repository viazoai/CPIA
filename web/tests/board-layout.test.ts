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
