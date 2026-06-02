// GET /api/mock/review/registered?wa=&l5=&l6=&limit=500
// 선택 WBS 노드(WA/trade/WP)의 site 누적 등록 mapper_activities 를 노드 스코프로 반환.
// 전역 캡(빈칸 버그) 폐기 — 노드 단위 lazy fetch. ORDER BY started_at(실 timestamp), run_id(UUID) 아님.
export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import { deriveWpIdAndPath } from "@/lib/transforms";
import type { ReviewItem } from "@/lib/types";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const wa = url.searchParams.get("wa");
  const l5 = url.searchParams.get("l5");
  const l6 = url.searchParams.get("l6");
  const limit = Math.min(Number(url.searchParams.get("limit") ?? 500) || 500, 1000);
  if (!wa) return NextResponse.json({ error: "wa required" }, { status: 400 });

  const useMock = process.env.CPIA_DEMO_FALLBACK === "on";
  const siteRow = (await (sql as any)`
    SELECT site_id, name FROM sites WHERE is_mock = FALSE ORDER BY site_id LIMIT 1`) as Array<{ site_id: string; name: string }>;
  const siteId = siteRow[0]?.site_id ?? "m15x-ph3-ibl";
  const siteName = siteRow[0]?.name ?? siteId;

  const rows = (await (sql as any)`
    SELECT ma.id, ma.idx, ma.company, ma.today_qty, ma.unit, ma.wa, ma.l6_main, ma.mapping_conf,
           pa.work_content, COUNT(*) OVER() AS total
    FROM mapper_activities ma
    JOIN pipeline_runs pr USING (run_id)
    LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
    WHERE pr.site_id = ${siteId} AND ma.is_mock = ${useMock}
      AND ma.l6_main IS NOT NULL
      AND ma.wa = ${wa}
      AND (${l6}::text IS NULL OR ma.l6_main = ${l6})
      AND (${l5}::text IS NULL OR ma.l5_disc = ${l5})
    ORDER BY pr.started_at DESC NULLS LAST, ma.mapping_conf DESC NULLS LAST
    LIMIT ${limit}
  `) as Array<{
    id: number | string; idx: number; company: string | null;
    today_qty: number | string | null; unit: string | null;
    wa: string | null; l6_main: string | null; mapping_conf: number | string | null;
    work_content: string | null; total: number | string;
  }>;

  const total = rows[0] ? Number(rows[0].total) : 0;
  const items: ReviewItem[] = rows.map((r) => {
    const m = deriveWpIdAndPath(r.wa, r.l6_main, siteName);
    return {
      id: `reg-${r.id}`, idx: r.idx, bp_name: r.company ?? "",
      work_content: r.work_content ?? "", quantity: r.today_qty != null ? Number(r.today_qty) : 0,
      unit: r.unit ?? "", ai_mapped_wp_id: m.wp_id, ai_mapped_path: m.path,
      wa: r.wa, l6_main: r.l6_main,
      confidence: r.mapping_conf != null ? Number(r.mapping_conf) : 0,
      status: "confirmed", alternative_wps: [],
    };
  });
  return NextResponse.json({ items, total }, {
    headers: { "Cache-Control": "s-maxage=30, stale-while-revalidate=60" },
  });
}
