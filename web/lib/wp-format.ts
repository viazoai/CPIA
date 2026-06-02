import type { WPSummaryRow } from "@/lib/types";

/** 보고서 WP목록 맨 왼쪽 Work Area 코드(CUB/FAB).
 *  wp_name "{trade} · {WA}" 의 마지막 토큰 우선, 없으면 wp_id "{wa}-…" 첫 세그먼트 대문자. (13행 정합 검증됨.) */
export function waCode(row: Pick<WPSummaryRow, "wp_name" | "wp_id">): string {
  if (row.wp_name && row.wp_name.includes(" · ")) {
    return row.wp_name.split(" · ").pop()!.trim();
  }
  if (row.wp_id) return row.wp_id.split("-")[0].toUpperCase();
  return "—";
}
