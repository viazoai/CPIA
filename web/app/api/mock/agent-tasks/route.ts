export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import { deriveStageProgress, deriveProgressPercent, deriveItemStatus } from "@/lib/transforms";
import type { DailyTask, AgentStageProgress, AgentTaskItem } from "@/lib/types";

export async function GET() {
  const dateRows = (await (sql as any)`
    SELECT DISTINCT report_date
    FROM pipeline_runs
    WHERE report_date >= CURRENT_DATE - INTERVAL '1 year'
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

    tasks.push({
      date: dStr,
      total_count: 0,
      progress_percent: deriveProgressPercent(statusRaw, run?.current_node ?? null),
      status,
      has_anomaly: false,
    });

    progressByDate[dStr] = await deriveStageProgress(dStr);

    const mapperItems = (await (sql as any)`
      SELECT ma.id, ma.wa, ma.l6_main, ma.company, ma.mapping_conf, ma.requires_review
      FROM mapper_activities ma
      JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${dStr}
      ORDER BY ma.mapping_conf ASC NULLS FIRST
      LIMIT 12
    `) as Array<{
      id: number | string;
      wa: string | null;
      l6_main: string | null;
      company: string | null;
      mapping_conf: number | string | null;
      requires_review: boolean | null;
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
    for (const agent of ["Collector", "Parser", "HIL Review", "Atomizer", "Exporter", "Forecaster", "Optimizer"]) {
      items[agent] = [];
    }
    itemsByDate[dStr] = items;
  }

  return NextResponse.json({ tasks, progressByDate, itemsByDate });
}
