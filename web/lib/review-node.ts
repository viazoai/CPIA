import type { WBSNode } from "@/lib/types";

export interface RegisteredQuery { wa: string; l5: string | null; l6: string | null; }

/** 선택된 WBS 노드 → registered fetch 파라미터.
 *  WBS 4레벨: building → WA(type:"trade", id="FAB") → l5_disc(type:"trade", id="FAB::골조") → work_package(wa·l6_main 필드).
 *  building/미선택/필드부족 → null(fetch 안 함). */
export function nodeToQuery(node: WBSNode | null): RegisteredQuery | null {
  if (!node) return null;
  if (node.type === "work_package") {
    return node.wa ? { wa: node.wa, l5: null, l6: node.l6_main ?? null } : null;
  }
  if (node.type === "trade") {
    if (node.id.includes("::")) {
      const [wa, l5] = node.id.split("::");
      return { wa, l5, l6: null };
    }
    return { wa: node.id, l5: null, l6: null };
  }
  return null;
}
