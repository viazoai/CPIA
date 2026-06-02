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
