// /api/mock/report/[date] — 특정 날짜의 detail jsonb 전체.
// list 진입 시 fetch 안 함 → selectedDate 변경 시에만 호출.

export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ date: string }> },
) {
  const { date } = await params;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return NextResponse.json({ error: "invalid date" }, { status: 400 });
  }

  const useMock = process.env.CPIA_DEMO_FALLBACK === "on";

  const rows = (await (sql as any)`
    SELECT dr.kpi_jsonb, dr.contractor_bars_jsonb, dr.trade_bars_jsonb,
           dr.quadrant_jsonb, dr.wp_summary_jsonb, dr.s_curve_jsonb,
           dr.optimizer_view_jsonb, dr.productivity_jsonb,
           dr.scenarios_jsonb
    FROM daily_reports dr
    JOIN pipeline_runs pr USING (run_id)
    JOIN sites s ON s.site_id = pr.site_id
    WHERE s.is_mock = FALSE
      AND dr.is_mock = ${useMock}
      AND pr.report_date = ${date}
    ORDER BY dr.created_at DESC
    LIMIT 1
  `) as Array<any>;

  if (rows.length === 0) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  const r = rows[0];

  const detail = {
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

  return NextResponse.json(detail, {
    headers: { "Cache-Control": "s-maxage=30, stale-while-revalidate=60" },
  });
}
