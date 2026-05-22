// /api/mock/agent-tasks/[date] — 특정 날짜의 progress + items.
// list 페이지에서 selectedDate 변경 시에만 호출 → 1년치 N+1 제거.

export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import { deriveStageProgress, deriveItemStatus } from "@/lib/transforms";
import type { AgentStageProgress, AgentTaskItem } from "@/lib/types";

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

  const [stages, mapperItems, parserItems] = await Promise.all([
    deriveStageProgress(date),
    (sql as any)`
      SELECT ma.id, ma.wa, ma.l6_main, ma.company, ma.mapping_conf, ma.requires_review
      FROM mapper_activities ma
      JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${date}
        AND ma.is_mock = ${useMock}
      ORDER BY ma.mapping_conf ASC NULLS FIRST
      LIMIT 200
    ` as Promise<Array<{
      id: number | string;
      wa: string | null;
      l6_main: string | null;
      company: string | null;
      mapping_conf: number | string | null;
      requires_review: boolean | null;
    }>>,
    (sql as any)`
      SELECT pa.id, pa.trade, pa.company, pa.work_content
      FROM parser_activities pa
      JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${date}
        AND pa.is_mock = ${useMock}
      ORDER BY pa.id
      LIMIT 200
    ` as Promise<Array<{
      id: number | string;
      trade: string | null;
      company: string | null;
      work_content: string | null;
    }>>,
  ]) as [AgentStageProgress[], any[], any[]];

  const items: Record<string, AgentTaskItem[]> = {};
  items["Mapper"] = mapperItems.map((r) => ({
    id: `mapper-${r.id}`,
    trade: r.l6_main ?? "—",
    contractor: r.company ?? "—",
    status: deriveItemStatus("Mapper", {
      requires_review: Boolean(r.requires_review),
      mapping_conf: r.mapping_conf != null ? Number(r.mapping_conf) : 0,
    }),
  }));
  items["Parser"] = parserItems.map((r) => ({
    id: `parser-${r.id}`,
    trade: r.trade ?? r.work_content ?? "—",
    contractor: r.company ?? "—",
    status: "done" as const,
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
