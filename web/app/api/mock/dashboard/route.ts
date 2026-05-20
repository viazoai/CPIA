export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";

export async function GET() {
  const useMock = process.env.CPIA_DEMO_FALLBACK === "on";

  // DISTINCT ON (report_date) — 같은 date 의 중복 cycle row 정리 (report 와 동일 패턴)
  const trend = await (sql as any)`
    SELECT DISTINCT ON (pr.report_date)
           pr.report_date,
           (dr.kpi_jsonb->>'cpi')::float AS cpi
    FROM daily_reports dr
    JOIN pipeline_runs pr USING (run_id)
    JOIN sites s ON s.site_id = pr.site_id
    WHERE s.is_mock = FALSE
      AND dr.is_mock = ${useMock}
    ORDER BY pr.report_date DESC, dr.created_at DESC
    LIMIT 90
  `;

  const isoDate = (v: any): string =>
    v instanceof Date ? v.toISOString().slice(0, 10) : String(v).slice(0, 10);

  const trendOut = trend.map((r: any) => ({
    date: isoDate(r.report_date),
    cpi: r.cpi ?? 0,
  }));

  const latest = trendOut[0];
  return NextResponse.json({
    fleet: {
      kpi: { productivity_today: latest?.cpi ?? 0 },
      trend: trendOut,
    },
    sites: [
      { site_id: "m15x-ph3-ibl", name: "M15X Ph-3 IBL", status: "normal" },
    ],
  });
}
