// /api/mock/agent-tasks/[date] — 특정 날짜의 progress + items.
// list 페이지에서 selectedDate 변경 시에만 호출 → 1년치 N+1 제거.

export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import { deriveStageProgress, deriveItemStatus } from "@/lib/transforms";
import type { AgentStageProgress, AgentColumn, AgentTaskRow } from "@/lib/types";
import { AGENT_COLUMNS, PARSER_COLUMNS_AGG } from "@/lib/agent-task-schema";

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
      SELECT ma.id, COALESCE(ma.l5_disc, ma.trade) AS trade, ma.l6_main, ma.company,
             pa.work_content, ma.mapping_conf, ma.requires_review
      FROM mapper_activities ma
      JOIN pipeline_runs pr USING (run_id)
      LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
      WHERE pr.report_date = ${date}
        AND ma.is_mock = ${useMock}
      ORDER BY ma.mapping_conf ASC NULLS FIRST
      LIMIT 500
    ` as Promise<Array<{
      id: number | string;
      trade: string | null;
      l6_main: string | null;
      company: string | null;
      work_content: string | null;
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
      LIMIT 500
    ` as Promise<Array<{
      id: number | string;
      trade: string | null;
      company: string | null;
      work_content: string | null;
    }>>,
  ]) as [AgentStageProgress[], any[], any[]];

  type AgentShape = { columns: AgentColumn[]; rows: AgentTaskRow[] };
  const items: Record<string, AgentShape> = {};

  items["Mapper"] = {
    columns: AGENT_COLUMNS["Mapper"] ?? [],
    rows: mapperItems.map((r) => {
      const tone = deriveItemStatus("Mapper", {
        requires_review: Boolean(r.requires_review),
        mapping_conf: r.mapping_conf != null ? Number(r.mapping_conf) : 0,
      });
      const labelMap: Record<string, string> = {
        done: "완료",
        processing: "처리중",
        received: "접수",
        hil_pending: "검토필요",
        blocked: "차단",
      };
      return {
        id: `mapper-${r.id}`,
        values: {
          trade: r.trade ?? "—",
          company: r.company ?? "—",
          work: r.work_content ?? "—",
          wbs: r.l6_main ?? "—",
        },
        statusLabel: labelMap[tone] ?? tone,
        statusTone: tone,
      };
    }),
  };

  // Parser: AGG 컬럼 (공종 / 업체명 / 활동건수) — 행별 count=1 (개별 활동)
  items["Parser"] = {
    columns: PARSER_COLUMNS_AGG,
    rows: parserItems.map((r) => ({
      id: `parser-${r.id}`,
      values: {
        trade: r.trade ?? r.work_content ?? "—",
        company: r.company ?? "—",
        count: "1",
      },
      statusLabel: "완료",
      statusTone: "done",
    })),
  };

  for (const agent of ["Collector", "Human Review", "Atomizer", "Exporter", "Forecaster", "Optimizer"]) {
    items[agent] = { columns: AGENT_COLUMNS[agent] ?? [], rows: [] };
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
