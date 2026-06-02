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

/** optimizer.by_wp[wp_id].details 의 "일정 영향" 라벨에서 지연일수 추출.
 *  "5일 지연"→5, "일정 충족"/미매칭/항목없음→0. (옵티마이저 카드와 동일 SSOT.) */
export function parseDelayDays(details: { label: string; value: string }[] | undefined): number {
  if (!details) return 0;
  const d = details.find((x) => x.label === "일정 영향");
  if (!d) return 0;
  const m = /(\d+)\s*일\s*지연/.exec(d.value);
  return m ? Number(m[1]) : 0;
}
