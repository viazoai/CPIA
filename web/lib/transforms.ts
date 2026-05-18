// web/lib/transforms.ts
// FE↔BE 연결 Phase 4: pure transform 함수 모음 (G1/G11/G12/G17/G18)

export function deriveProgressPercent(
  status: string,
  current_node: string | null,
): number {
  if (status === "completed") return 100;
  if (status === "waiting_hil_1") return 50;
  const NODE_MAP: Record<string, number> = {
    parser: 20,
    mapper: 30,
    atomizer: 60,
    exporter: 70,
    forecaster: 80,
    optimizer: 90,
  };
  return NODE_MAP[current_node ?? ""] ?? 0;
}

export function deriveYearlySaving(
  totalFteSaved: number,
  totalHoursSaved: number,
  hourlyRateKrw: number = 50000,
): number {
  return totalFteSaved * 1.5 + (totalHoursSaved * hourlyRateKrw) / 1e8;
}

export function deriveItemStatus(
  stage: string,
  row: {
    requires_review?: boolean;
    mapping_conf?: number;
    has_correction?: boolean;
    risk_level?: string;
  },
): "done" | "processing" | "received" | "hil_pending" | "blocked" {
  if (row.risk_level === "이상") return "blocked";
  switch (stage) {
    case "Mapper":
      if (row.requires_review) return "hil_pending";
      if ((row.mapping_conf ?? 0) >= 0.7) return "done";
      if ((row.mapping_conf ?? 0) >= 0.4) return "processing";
      return "received";
    case "HIL Review":
      return row.has_correction ? "done" : "hil_pending";
    default:
      return "done";
  }
}

export function deriveWpIdAndPath(
  wa: string | null,
  l6_main: string | null,
  site_name: string,
): { wp_id: string; wp_name: string; path: string } {
  const safe = (s: string | null) => (s ?? "unknown").replace(/\s+/g, "-").toLowerCase();
  const wp_id = `${safe(wa)}-${safe(l6_main)}`;
  const wp_name = `${wa ?? ""} ${l6_main ?? ""}`.trim();
  const path = [site_name, wa ?? "", l6_main ?? ""].filter(Boolean).join(" > ");
  return { wp_id, wp_name, path };
}

export function deriveImpact(
  planTotalQty: number | null,
  planMhRev2: number | null,
  normMax: number = 1e8,
): number {
  if (!planTotalQty || !planMhRev2) return 0;
  const raw = planTotalQty * planMhRev2;
  return Math.min(100, Math.max(0, (raw / normMax) * 100));
}
