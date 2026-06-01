// /api/mock/agent-tasks/[date] — 특정 날짜의 progress + items.
// list 페이지에서 selectedDate 변경 시에만 호출 → 1년치 N+1 제거.

export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import { deriveStageProgress } from "@/lib/transforms";
import type { AgentStageProgress, AgentTaskRow } from "@/lib/types";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ date: string }> },
) {
  const { date } = await params;
  // YYYY-MM-DD 형식만 허용.
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return NextResponse.json({ error: "invalid date" }, { status: 400 });
  }

  const useMock = process.env.CPIA_DEMO_FALLBACK === "on";

  const [stages, mapperItems, parserCounts] = await Promise.all([
    deriveStageProgress(date),
    (sql as any)`
      SELECT ma.idx, ma.l5_disc, ma.l6_main, ma.company, pa.work_content, ma.requires_review
      FROM mapper_activities ma
      JOIN pipeline_runs pr USING (run_id)
      LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
      WHERE pr.report_date = ${date}
        AND ma.is_mock = ${useMock}
      ORDER BY ma.requires_review DESC, ma.mapping_conf ASC NULLS FIRST, ma.idx
      LIMIT 200
    ` as Promise<Array<{
      idx: number;
      l5_disc: string | null;
      l6_main: string | null;
      company: string | null;
      work_content: string | null;
      requires_review: boolean | null;
    }>>,
    (sql as any)`
      SELECT pa.company, COUNT(*)::int AS c, MAX(pa.l5_disc) AS trade
      FROM parser_activities pa
      JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${date}
        AND pa.is_mock = ${useMock}
      GROUP BY pa.company
    ` as Promise<Array<{ company: string | null; c: number; trade: string | null }>>,
  ]) as [AgentStageProgress[], any[], any[]];

  // 단계 고유 스키마(AgentTaskRow). mock 폴백은 Parser/Mapper 만 채우고,
  // 나머지 단계 실데이터는 /api/runs/items (run_id 기반)가 담당.
  const items: Record<string, AgentTaskRow[]> = {};
  items["Mapper"] = mapperItems.map((r) => ({
    id: `mapper-${r.idx}`,
    values: {
      trade: r.l5_disc ?? "—",
      company: r.company ?? "—",
      work: r.work_content ?? "—",
      wbs: r.l6_main ?? "(미매핑)",
    },
    statusLabel: r.l6_main != null ? "매핑완료" : "검토필요",
    statusTone: (r.l6_main != null ? "done" : "hil_pending") as AgentTaskRow["statusTone"],
  }));
  items["Parser"] = parserCounts.map((r) => ({
    id: `parser-${r.company}`,
    values: { trade: r.trade ?? "—", company: r.company ?? "—", category: "물량 (시트4)", count: String(r.c) },
    statusLabel: "파싱완료",
    statusTone: "done" as AgentTaskRow["statusTone"],
  }));
  for (const agent of ["Collector", "Human Review", "Atomizer", "Exporter", "Forecaster", "Optimizer"]) {
    items[agent] = [];
  }

  return NextResponse.json(
    { stages, items },
    {
      headers: {
        "Cache-Control": "s-maxage=30, stale-while-revalidate=60",
      },
    },
  );
}
