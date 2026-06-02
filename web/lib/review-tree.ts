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
