import type { WPSummaryRow } from "@/lib/types";

// status 4분면 필터 + "all". WPSummaryRow.status 에서 파생 — status union 확장 시 SSOT.
export type WPStatusFilter = WPSummaryRow["status"] | "all";

export function wpRowsForStatus(
  rows: WPSummaryRow[],
  statusFilter: WPStatusFilter,
): WPSummaryRow[] {
  const filtered =
    statusFilter === "all" ? rows : rows.filter((w) => w.status === statusFilter);
  // AI 단축일(recovery_days) 큰 순으로 상단 정렬. 동률은 impact(WV) 내림차순 보조.
  return [...filtered].sort(
    (a, b) =>
      (b.recovery_days ?? 0) - (a.recovery_days ?? 0) ||
      (b.impact ?? 0) - (a.impact ?? 0),
  );
}
