import type { ReviewItem } from "@/lib/types";

export interface WpGroup {
  wpId: string;                          // groupCardsByWp: ai_mapped_wp_id (= WBSNode.id, 연결선 타깃). groupCardsByL7: "ai_mapped_wp_id::l7_label" 합성 (React key·(wa,l6) 스코프 — 그래프 노드 id 아님)
  wpName: string;                        // ai_mapped_path 마지막 세그먼트
  path: string;                          // 마지막 제외 상위 경로 (예 "M15X > FAB")
  items: ReviewItem[];                   // 정렬은 producer별 상이 — groupCardsByWp: 미확정(확신도 오름차순)→확정, groupCardsByL7: quantity DESC
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
  byId.forEach((raw, wpId) => {
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
  });

  return groups.sort((a, b) => {
    if (a.allConfirmed !== b.allConfirmed) return a.allConfirmed ? 1 : -1;
    if (!a.allConfirmed && !b.allConfirmed) {
      return (a.minUnconfirmedConfidence ?? 1) - (b.minUnconfirmedConfidence ?? 1);
    }
    return a.wpName.localeCompare(b.wpName);
  });
}

// 등록(누적) 카드 전용 — l7(l7_sub) 라벨로 묶는다. wpId 는 (wa,l6) 스코프를 포함한 합성키.
// (key 충돌·동명 l7 오병합 방지. 연결선 타깃은 카드의 ai_mapped_wp_id 별개로 유지.)
export function groupCardsByL7(cards: ReviewItem[]): WpGroup[] {
  const l7Of = (c: ReviewItem) => (c.l7_label && c.l7_label.trim() ? c.l7_label : "기타");
  const byKey = new Map<string, ReviewItem[]>();
  for (const c of cards) {
    const wpId = `${c.ai_mapped_wp_id}::${l7Of(c)}`;
    const arr = byKey.get(wpId) ?? [];
    arr.push(c);
    byKey.set(wpId, arr);
  }

  const groups: WpGroup[] = [];
  byKey.forEach((raw, wpId) => {
    const items = [...raw].sort((a, b) => b.quantity - a.quantity);
    const unconfirmed = items.filter((c) => c.status === "unconfirmed");
    const confirmed = items.filter((c) => c.status === "confirmed");
    const { path } = splitPath(raw[0].ai_mapped_path);
    groups.push({
      wpId,
      wpName: l7Of(raw[0]),
      path,
      items,
      confirmedCount: confirmed.length,
      unconfirmedCount: unconfirmed.length,
      minUnconfirmedConfidence: unconfirmed.length
        ? Math.min(...unconfirmed.map((c) => c.confidence))
        : null,
      allConfirmed: unconfirmed.length === 0,
    });
  });

  // 그룹 정렬: Σquantity DESC, 동률 wpName localeCompare(결정론).
  return groups.sort((a, b) => {
    const sa = a.items.reduce((s, c) => s + c.quantity, 0);
    const sb = b.items.reduce((s, c) => s + c.quantity, 0);
    if (sb !== sa) return sb - sa;
    return a.wpName.localeCompare(b.wpName);
  });
}
