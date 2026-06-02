import type { WPSummaryRow } from "@/lib/types";

export function wpRowsForStatus(
  rows: WPSummaryRow[],
  statusFilter: "normal" | "caution" | "risk" | "all",
): WPSummaryRow[] {
  return statusFilter === "all" ? rows : rows.filter((w) => w.status === statusFilter);
}
