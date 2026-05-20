export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";

export async function GET() {
  const useMock = process.env.CPIA_DEMO_FALLBACK === "on";

  const rows = await (sql as any)`
    SELECT pr.report_date,
           dr.kpi_jsonb, dr.contractor_bars_jsonb, dr.trade_bars_jsonb,
           dr.quadrant_jsonb, dr.wp_summary_jsonb, dr.s_curve_jsonb,
           dr.optimizer_view_jsonb, dr.productivity_jsonb,
           dr.scenarios_jsonb
    FROM daily_reports dr
    JOIN pipeline_runs pr USING (run_id)
    JOIN sites s ON s.site_id = pr.site_id
    WHERE s.is_mock = FALSE
      AND dr.is_mock = ${useMock}
    ORDER BY pr.report_date DESC
  `;

  const isoDate = (v: any): string =>
    v instanceof Date ? v.toISOString().slice(0, 10) : String(v).slice(0, 10);

  const daily = rows.map((r: any) => ({
    date: isoDate(r.report_date),
    status:
      r.kpi_jsonb?.risk_level === "이상" ? "risk"
      : r.kpi_jsonb?.risk_level === "주의" ? "caution"
      : "normal",
    productivity_today: r.kpi_jsonb?.productivity_today ?? 0,
    delay_days: r.kpi_jsonb?.delay_days ?? 0,
    recovery_days: r.kpi_jsonb?.recovery_days ?? 0,
  }));

  const details: Record<string, any> = {};
  for (const r of rows) {
    const date = isoDate(r.report_date);
    details[date] = {
      kpi: r.kpi_jsonb || {},
      s_curve: r.s_curve_jsonb || [],
      contractor_bars: r.contractor_bars_jsonb || [],
      trade_bars: r.trade_bars_jsonb || [],
      quadrant: r.quadrant_jsonb || [],
      optimizer: r.optimizer_view_jsonb || { by_wp: {}, default_wp_id: null },
      scenarios: r.scenarios_jsonb || { site: {}, by_wp: {} },
      wp_summary: r.wp_summary_jsonb || [],
      raw_data: [],
    };
  }
  return NextResponse.json({ daily, details });
}
