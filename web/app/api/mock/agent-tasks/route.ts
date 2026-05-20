export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import { deriveStageProgress, deriveProgressPercent, deriveItemStatus } from "@/lib/transforms";
import type { DailyTask, AgentStageProgress, AgentTaskItem } from "@/lib/types";

export async function GET() {
  const useMock = process.env.CPIA_DEMO_FALLBACK === "on";

  const dateRows = (await (sql as any)`
    SELECT DISTINCT report_date
    FROM pipeline_runs
    WHERE report_date >= CURRENT_DATE - INTERVAL '1 year'
      AND is_mock = ${useMock}
    ORDER BY report_date DESC
  `) as Array<{ report_date: Date | string }>;

  const tasks: DailyTask[] = [];
  const progressByDate: Record<string, AgentStageProgress[]> = {};
  const itemsByDate: Record<string, Record<string, AgentTaskItem[]>> = {};

  for (const row of dateRows) {
    const dStr =
      typeof row.report_date === "string"
        ? row.report_date.slice(0, 10)
        : row.report_date.toISOString().slice(0, 10);

    const runRows = (await (sql as any)`
      SELECT status, current_node
      FROM pipeline_runs
      WHERE report_date = ${dStr}
        AND is_mock = ${useMock}
      ORDER BY started_at DESC
      LIMIT 1
    `) as Array<{ status: string | null; current_node: string | null }>;
    const run = runRows[0];
    const statusRaw = run?.status ?? "";

    const status: DailyTask["status"] =
      statusRaw === "waiting_hil_1"
        ? "review_pending"
        : statusRaw === "completed"
          ? "completed"
          : "running";

    const stages = await deriveStageProgress(dStr);
    progressByDate[dStr] = stages;

    // spec §5.3 — total_count = parser_activities 처리 건수 (parser 가 받아 mapper 로 넘긴 수).
    const totalCount = stages.find((s) => s.agent === "Parser")?.processed ?? 0;
    tasks.push({
      date: dStr,
      total_count: totalCount,
      progress_percent: deriveProgressPercent(statusRaw, run?.current_node ?? null),
      status,
      has_anomaly: false,
    });

    const mapperItems = (await (sql as any)`
      SELECT ma.id, ma.wa, ma.l6_main, ma.company, ma.mapping_conf, ma.requires_review
      FROM mapper_activities ma
      JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${dStr}
        AND ma.is_mock = ${useMock}
      ORDER BY ma.mapping_conf ASC NULLS FIRST
      LIMIT 200
    `) as Array<{
      id: number | string;
      wa: string | null;
      l6_main: string | null;
      company: string | null;
      mapping_conf: number | string | null;
      requires_review: boolean | null;
    }>;

    // spec §5.1 — Parser 클릭 시 빈 화면 fix. parser_activities 그대로 펼침.
    const parserItems = (await (sql as any)`
      SELECT pa.id, pa.trade, pa.company, pa.work_content
      FROM parser_activities pa
      JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${dStr}
        AND pa.is_mock = ${useMock}
      ORDER BY pa.id
      LIMIT 200
    `) as Array<{
      id: number | string;
      trade: string | null;
      company: string | null;
      work_content: string | null;
    }>;

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
    for (const agent of ["Collector", "HIL Review", "Atomizer", "Exporter", "Forecaster", "Optimizer"]) {
      items[agent] = [];
    }
    itemsByDate[dStr] = items;
  }

  return NextResponse.json({ tasks, progressByDate, itemsByDate });
}
