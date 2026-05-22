export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";

// /api/mock/report — 좌측 일별 목록만 반환 (페이로드 ~50KB).
// detail jsonb (kpi/s_curve/wp_summary 등 9 컬럼 × 127 dates → 32MB) 는
// /api/mock/report/[date] 로 분리. trend90 슬라이스를 위해 daily 에는
// productivity_today / status / delay_days / recovery_days 만 포함.

export async function GET() {
  const useMock = process.env.CPIA_DEMO_FALLBACK === "on";

  // DISTINCT ON (report_date) — 같은 (site, date) 에 여러 cycle row 있으면 최신만.
  // SELECT 컬럼을 jsonb 전체가 아닌 -> 연산자로 필요 필드만 추출 → 페이로드 600× 축소.
  const rows = await (sql as any)`
    SELECT DISTINCT ON (pr.report_date)
           pr.report_date,
           dr.kpi_jsonb->>'risk_level'                                    AS risk_level,
           (dr.kpi_jsonb->>'productivity_today')::numeric                 AS productivity_today,
           (dr.kpi_jsonb->>'delay_days')::numeric                         AS delay_days,
           (dr.kpi_jsonb->>'recovery_days')::numeric                      AS kpi_recovery_days,
           (dr.scenarios_jsonb->'site'->'base_p50'->>'recovery_days')::numeric
                                                                          AS scen_recovery_days
    FROM daily_reports dr
    JOIN pipeline_runs pr USING (run_id)
    JOIN sites s ON s.site_id = pr.site_id
    WHERE s.is_mock = FALSE
      AND dr.is_mock = ${useMock}
    ORDER BY pr.report_date DESC, dr.created_at DESC
  `;

  const isoDate = (v: any): string =>
    v instanceof Date ? v.toISOString().slice(0, 10) : String(v).slice(0, 10);

  const daily = rows.map((r: any) => ({
    date: isoDate(r.report_date),
    status:
      r.risk_level === "이상" ? "risk"
      : r.risk_level === "주의" ? "caution"
      : "normal",
    productivity_today: r.productivity_today != null ? Number(r.productivity_today) : 0,
    delay_days: r.delay_days != null ? Number(r.delay_days) : 0,
    // reports 상세 페이지와 동일: scenarios.site.base_p50 우선, kpi 는 fallback.
    recovery_days:
      r.scen_recovery_days != null ? Number(r.scen_recovery_days)
      : r.kpi_recovery_days != null ? Number(r.kpi_recovery_days)
      : 0,
  }));

  return NextResponse.json(
    { daily },
    { headers: { "Cache-Control": "s-maxage=30, stale-while-revalidate=60" } },
  );
}
