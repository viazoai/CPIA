import type { WBSNode, ReviewItem } from "@/lib/types";

export interface BoardNode {
  id: string;
  kind: "hier" | "qty";
  depth: number;              // hier: 트리 깊이(0~), qty: maxHierDepth+1
  label: string;
  parentId: string | null;    // 그래프상 부모(hier=트리부모, qty=ai_mapped_wp_id)
  hasChildren: boolean;       // hier 전용 — 접기 캐럿 표시
  reviewCount: number;        // hier: 하위 미확정 수(WP 직속), qty: 0
  isWp?: boolean;            // hier 노드가 work_package 인지 (보드 드롭 타깃 판정용)
  item?: ReviewItem;          // qty 전용 원본
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
      isWp: isWP,
    });
    if (node.parent_id) {
      edges.push({ id: `${node.parent_id}->${node.id}`, source: node.parent_id, target: node.id, review: false });
    }
    if (opts.collapsed.has(node.id)) return;
    for (const c of children) walk(c, depth + 1);
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

  const qtyDepth = maxDepth + 1;
  for (const n of nodes) if (n.kind === "qty") n.depth = qtyDepth;

  return { nodes, edges };
}
