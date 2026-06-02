import type { WPSummaryRow } from "@/lib/types";

// status 4분면 필터 + "all". WPSummaryRow.status 에서 파생 — status union 확장 시 SSOT.
export type WPStatusFilter = WPSummaryRow["status"] | "all";

export function wpRowsForStatus(
  rows: WPSummaryRow[],
  statusFilter: WPStatusFilter,
): WPSummaryRow[] {
  return statusFilter === "all" ? rows : rows.filter((w) => w.status === statusFilter);
}
