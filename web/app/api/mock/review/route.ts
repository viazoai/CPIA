// /api/mock/review — A_Track PG 직접 SELECT 로 swap (Task 5.5).
// 기존 fixture shape 유지: { wbs: WBSNode, cards: ReviewItem[] }.
//
// wbs: wbsTreeBuild(siteId) — site → wa → l5_disc → l6_main 4 레벨 트리.
// cards: mapper_activities WHERE requires_review = TRUE ORDER BY mapping_conf ASC, LIMIT 50.

export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import { wbsTreeBuild, deriveWpIdAndPath } from "@/lib/transforms";
import type { ReviewItem } from "@/lib/types";

export async function GET() {
  // 실 PoC 현장 1 개 — sites.is_mock = false.
  const siteRow = (await (sql as any)`
    SELECT site_id, name FROM sites WHERE is_mock = FALSE ORDER BY site_id LIMIT 1
  `) as Array<{ site_id: string; name: string }>;
  const siteId = siteRow[0]?.site_id ?? "m15x-ph3-ibl";
  const siteName = siteRow[0]?.name ?? siteId;

  const wbs = await wbsTreeBuild(siteId);

  const cardRows = (await (sql as any)`
    SELECT
      ma.id, ma.run_id, ma.idx, ma.company, ma.today_qty, ma.unit,
      ma.wa, ma.l6_main, ma.mapping_conf, ma.requires_review, ma.alternatives,
      pa.work_content
    FROM mapper_activities ma
    LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
    WHERE ma.requires_review = TRUE
    ORDER BY ma.mapping_conf ASC NULLS FIRST
    LIMIT 50
  `) as Array<{
    id: number | string;
    run_id: string;
    idx: number;
    company: string | null;
    today_qty: number | string | null;
    unit: string | null;
    wa: string | null;
    l6_main: string | null;
    mapping_conf: number | string | null;
    requires_review: boolean;
    alternatives: unknown;
    work_content: string | null;
  }>;

  const cards: ReviewItem[] = cardRows.map((r) => {
    const aiMapped = deriveWpIdAndPath(r.wa, r.l6_main, siteName);
    const altsRaw = r.alternatives;
    const alts: Array<{ wa?: string | null; l6_main?: string | null; score?: number | string | null }> =
      Array.isArray(altsRaw)
        ? (altsRaw as any[])
        : typeof altsRaw === "string"
          ? (() => {
              try {
                const parsed = JSON.parse(altsRaw);
                return Array.isArray(parsed) ? parsed : [];
              } catch {
                return [];
              }
            })()
          : [];

    return {
      id: `r-${r.id}`,
      bp_name: r.company ?? "",
      work_content: r.work_content ?? "",
      quantity: r.today_qty != null ? Number(r.today_qty) : 0,
      unit: r.unit ?? "",
      ai_mapped_wp_id: aiMapped.wp_id,
      ai_mapped_path: aiMapped.path,
      confidence: r.mapping_conf != null ? Number(r.mapping_conf) : 0,
      status: r.requires_review ? "unconfirmed" : "confirmed",
      alternative_wps: alts.map((a) => {
        const ap = deriveWpIdAndPath(a.wa ?? null, a.l6_main ?? null, siteName);
        return {
          id: ap.wp_id,
          path: ap.path,
          score: a.score != null ? Number(a.score) : 0,
        };
      }),
    };
  });

  return NextResponse.json({ wbs, cards });
}
