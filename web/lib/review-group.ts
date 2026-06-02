import type { ReviewItem } from "@/lib/types";

export interface WpGroup {
  wpId: string;                          // ai_mapped_wp_id (= WBSNode.id, 연결선 타깃)
  wpName: string;                        // ai_mapped_path 마지막 세그먼트
  path: string;                          // 마지막 제외 상위 경로 (예 "M15X > FAB")
  items: ReviewItem[];                   // 미확정(확신도 오름차순) → 확정 순
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
