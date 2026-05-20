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
  const useMock = process.env.CPIA_DEMO_FALLBACK === "on";

  // 실 PoC 현장 1 개 — sites.is_mock = false (useMock 무관, wbs 빌드용 site_id 식별).
  const siteRow = (await (sql as any)`
    SELECT site_id, name FROM sites WHERE is_mock = FALSE ORDER BY site_id LIMIT 1
  `) as Array<{ site_id: string; name: string }>;
  const siteId = siteRow[0]?.site_id ?? "m15x-ph3-ibl";
  const siteName = siteRow[0]?.name ?? siteId;

  const wbs = await wbsTreeBuild(siteId, siteName);

  // LIMIT 50 → 300, site 제약 추가 (wbs 노드 옆 숫자와 클릭 시 카드 수 일치).
  // site 필터 없으면 orphan ma row (pipeline_runs 매칭 없는) 까지 포함되어 wbs review_count 와 mismatch.
  const cardRows = (await (sql as any)`
    SELECT
      ma.id, ma.run_id, ma.idx, ma.company, ma.today_qty, ma.unit,
      ma.wa, ma.l6_main, ma.mapping_conf, ma.requires_review, ma.alternatives,
      pa.work_content
    FROM mapper_activities ma
    JOIN pipeline_runs pr USING (run_id)
    LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
    WHERE pr.site_id = ${siteId}
      AND ma.requires_review = TRUE
      AND ma.is_mock = ${useMock}
    ORDER BY ma.mapping_conf ASC NULLS FIRST
    LIMIT 300
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
