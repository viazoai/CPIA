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

  // wbs + cards + 같은공종 유효 l6 집합 병렬 — 셋 다 site_id 만 의존.
  // discRows: 대안(l6)을 같은 공종(l5_disc) 내로 필터하기 위한 화이트리스트 (RAG alternatives 가 타 공종 l6 를 끌어오는 것 차단).
  // LIMIT 50 → 300, site 제약 추가 (wbs 노드 옆 숫자와 클릭 시 카드 수 일치).
  // site 필터 없으면 orphan ma row (pipeline_runs 매칭 없는) 까지 포함되어 wbs review_count 와 mismatch.
  const [wbs, cardRows, discRows] = (await Promise.all([
    wbsTreeBuild(siteId, siteName),
    (sql as any)`
    SELECT
      ma.id, ma.run_id, ma.idx, ma.company, ma.today_qty, ma.unit,
      ma.wa, ma.l5_disc, ma.l6_main, ma.mapping_conf, ma.requires_review,
      ma.l7_5_activity, ma.l7_5_alternatives, ma.alternatives,
      pa.work_content
    FROM mapper_activities ma
    JOIN pipeline_runs pr USING (run_id)
    LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
    WHERE pr.site_id = ${siteId}
      AND pr.status = 'waiting_hil_1'
      AND ma.requires_review = TRUE
      AND ma.is_mock = ${useMock}
      AND ma.trade IN ('건축', '토목')
    ORDER BY ma.mapping_conf ASC NULLS FIRST
    LIMIT 500
  `,
    (sql as any)`
    SELECT DISTINCT l5_disc, l6_main
    FROM activity_master
    WHERE site_id = ${siteId} AND l5_disc IN ('건축', '토목') AND l6_main IS NOT NULL
  `,
  ])) as [
    Awaited<ReturnType<typeof wbsTreeBuild>>,
    Array<{
      id: number | string;
      run_id: string;
      idx: number;
      company: string | null;
      today_qty: number | string | null;
      unit: string | null;
      wa: string | null;
      l5_disc: string | null;
      l6_main: string | null;
      mapping_conf: number | string | null;
      requires_review: boolean;
      l7_5_activity: string | null;
      l7_5_alternatives: unknown;
      alternatives: unknown;
      work_content: string | null;
    }>,
    Array<{ l5_disc: string | null; l6_main: string | null }>,
  ];

  // 같은 공종(l5_disc) 내 유효 l6 화이트리스트 — `${l5_disc}::${l6_main}`.
  const validL6 = new Set(discRows.map((d) => `${d.l5_disc}::${d.l6_main}`));

  const cards: ReviewItem[] = cardRows.map((r) => {
    const aiMapped = deriveWpIdAndPath(r.wa, r.l6_main, siteName);

    const l75AltsRaw = r.l7_5_alternatives;
    const l75Alts: Array<{ label?: string | null; score?: number | string | null }> =
      Array.isArray(l75AltsRaw)
        ? (l75AltsRaw as any[])
        : typeof l75AltsRaw === "string"
          ? (() => { try { const p = JSON.parse(l75AltsRaw); return Array.isArray(p) ? p : []; } catch { return []; } })()
          : [];

    // l6(공종) 후보 — [{wa, l6_main, score}]. (wa,l6_main) 중복 제거 + 현재 매핑 제외.
    const l6AltsRaw = r.alternatives;
    const l6AltsArr: Array<{ wa?: string | null; l6_main?: string | null; score?: number | string | null }> =
      Array.isArray(l6AltsRaw)
        ? (l6AltsRaw as any[])
        : typeof l6AltsRaw === "string"
          ? (() => { try { const p = JSON.parse(l6AltsRaw); return Array.isArray(p) ? p : []; } catch { return []; } })()
          : [];
    const seenL6 = new Set<string>();
    const l6_alternatives = l6AltsArr
      .filter((a) => a.l6_main)
      .filter((a) => a.l6_main !== r.l6_main)                              // 현재 공종 제외
      .filter((a) => validL6.has(`${r.l5_disc}::${a.l6_main}`))           // 같은 공종(l5_disc) 내 l6 만 — 타 공종(예 설비) 차단
      .filter((a) => { const k = `${a.wa}::${a.l6_main}`; if (seenL6.has(k)) return false; seenL6.add(k); return true; })
      .map((a) => ({ wa: a.wa ?? null, l6_main: a.l6_main as string, score: a.score != null ? Number(a.score) : 0 }));

    return {
      id: `r-${r.id}`,
      idx: r.idx,
      bp_name: r.company ?? "",
      work_content: r.work_content ?? "",
      quantity: r.today_qty != null ? Number(r.today_qty) : 0,
      unit: r.unit ?? "",
      ai_mapped_wp_id: aiMapped.wp_id,
      ai_mapped_path: `${aiMapped.path} > ${r.l7_5_activity || "미분류"}`,
      wa: r.wa,
      l5_disc: r.l5_disc,
      l6_main: r.l6_main,
      l7_5_activity: r.l7_5_activity,   // mapper 가 결정론으로 고른 l7.5 — oneshot 카드의 "AI 추천" 마커.
      confidence: r.mapping_conf != null ? Number(r.mapping_conf) : 0,
      status: r.requires_review ? "unconfirmed" : "confirmed",
      alternative_wps: l75Alts.map((a, i) => ({
        id: `l75-${i}`,
        path: a.label ?? "",
        score: a.score != null ? Number(a.score) : 0,
      })),
      l6_alternatives,
    };
  });

  return NextResponse.json(
    { wbs, cards },
    {
      headers: {
        "Cache-Control": "s-maxage=30, stale-while-revalidate=60",
      },
    },
  );
}
