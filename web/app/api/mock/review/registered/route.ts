// GET /api/mock/review/registered?wa=&l5=&l6=
// 선택 WBS 노드(WA/trade/WP/building)의 site 누적 등록 mapper_activities 를 l7.5 단위로 GROUP BY.
// wa 없으면 전체(building 집계). requires_review=FALSE 인 확정 행만 포함.
export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import { deriveWpIdAndPath } from "@/lib/transforms";
import type { ReviewItem } from "@/lib/types";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const wa = url.searchParams.get("wa");
  const waParam = (wa && wa !== "null") ? wa : null;
  const l5 = url.searchParams.get("l5");
  const l6 = url.searchParams.get("l6");

  const useMock = process.env.CPIA_DEMO_FALLBACK === "on";
  const siteRow = (await (sql as any)`
    SELECT site_id, name FROM sites WHERE is_mock = FALSE ORDER BY site_id LIMIT 1`) as Array<{ site_id: string; name: string }>;
  const siteId = siteRow[0]?.site_id ?? "m15x-ph3-ibl";
  const siteName = siteRow[0]?.name ?? siteId;

  const rows = (await (sql as any)`
    WITH master_l7 AS (
      SELECT wa, l6_main, l7_5_activity, MAX(NULLIF(l7_sub,'')) AS m_l7
      FROM activity_master WHERE site_id = ${siteId}
      GROUP BY wa, l6_main, l7_5_activity
    )
    SELECT ma.wa, ma.l6_main,
           COALESCE(NULLIF(ma.l7_5_activity,''),'미분류') AS l75_label,
           COALESCE(MAX(NULLIF(ma.l7_sub,'')), MAX(ml.m_l7), '기타') AS l7_label,
           ROUND(SUM(ma.today_qty)::numeric,2) AS cum_qty,
           MAX(ma.unit) AS unit,
           MAX(ma.company) AS company,
           COUNT(DISTINCT ma.company) AS company_n
    FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id)
    LEFT JOIN master_l7 ml
      ON ml.wa = ma.wa AND ml.l6_main = ma.l6_main AND ml.l7_5_activity = ma.l7_5_activity
    WHERE pr.site_id = ${siteId} AND ma.is_mock = ${useMock}
      AND ma.l6_main IS NOT NULL AND ma.trade IN ('건축','토목') AND ma.requires_review = FALSE
      AND (${waParam}::text IS NULL OR ma.wa = ${waParam})
      AND (${l6}::text IS NULL OR ma.l6_main = ${l6})
      AND (${l5}::text IS NULL OR ma.l5_disc = ${l5})
    GROUP BY ma.wa, ma.l6_main, l75_label
    ORDER BY cum_qty DESC
  `) as Array<{
    wa: string | null; l6_main: string | null; l75_label: string; l7_label: string;
    cum_qty: number | string | null; unit: string | null;
    company: string | null; company_n: number | string;
  }>;

  const items: ReviewItem[] = rows.map((r) => {
    const m = deriveWpIdAndPath(r.wa, r.l6_main, siteName);
    return {
      id: `reg-${r.wa}-${r.l6_main}-${r.l75_label}`, idx: -1,
      bp_name: Number(r.company_n) > 1 ? `${r.company_n}개사` : (r.company ?? ""),
      work_content: r.l75_label,
      quantity: r.cum_qty != null ? Number(r.cum_qty) : 0,
      unit: r.unit ?? "",
      ai_mapped_wp_id: m.wp_id, ai_mapped_path: `${m.path} > ${r.l75_label}`,
      wa: r.wa, l6_main: r.l6_main, l7_label: r.l7_label, confidence: 1.0,
      status: "confirmed", alternative_wps: [],
    };
  });
  const total = items.length;
  return NextResponse.json({ items, total }, {
    headers: { "Cache-Control": "s-maxage=30, stale-while-revalidate=60" },
  });
}
