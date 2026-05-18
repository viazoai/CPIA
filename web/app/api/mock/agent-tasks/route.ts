export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import {
  deriveStageProgress,
  deriveItemStatus,
  deriveProgressPercent,
} from "@/lib/transforms";
import type {
  DailyTask,
  AgentStageProgress,
  AgentTaskItem,
} from "@/lib/types";

// Task 5.3: /api/mock/agent-tasks PG swap (1년 윈도우)
// 기존 JSON shape ({ tasks, progressByDate, itemsByDate }) 유지.
// PRNG mock 대신 pipeline_runs 1년 윈도우 + 단계별 진행.
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

    // 해당 일자의 최신 run
    const runRows = (await (sql as any)`
      SELECT status, current_node
      FROM pipeline_runs
      WHERE report_date = ${dStr}
      ORDER BY started_at DESC
      LIMIT 1
    `) as Array<{ status: string | null; current_node: string | null }>;
    const run = runRows[0];

    const totalRows = (await (sql as any)`
      SELECT COUNT(DISTINCT (pa.company, pr.report_date)) AS c
      FROM parser_activities pa
      JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${dStr}
    `) as Array<{ c: number | string }>;
    const totalCount = Number(totalRows[0]?.c ?? 0);

    const anomalyRows = (await (sql as any)`
      SELECT EXISTS(
        SELECT 1
        FROM forecasts f
        JOIN pipeline_runs pr USING (run_id)
        WHERE pr.report_date = ${dStr} AND f.risk_level <> '정상'
      ) AS x
    `) as Array<{ x: boolean }>;

    const statusRaw = run?.status ?? "";
    const status: DailyTask["status"] =
      statusRaw === "waiting_hil_1"
        ? "review_pending"
        : statusRaw === "completed"
          ? "completed"
          : "running";

    tasks.push({
      date: dStr,
      total_count: totalCount,
      progress_percent: deriveProgressPercent(statusRaw, run?.current_node ?? null),
      status,
      has_anomaly: Boolean(anomalyRows[0]?.x),
    });

    progressByDate[dStr] = await deriveStageProgress(dStr);

    // Mapper 단계 sample item (단가 절감 위해 단일 단계만 채움 — 나머지는 빈 배열)
    const mapperItems = (await (sql as any)`
      SELECT
        ma.id, ma.idx, ma.run_id, pa.work_content,
        ma.company, ma.wa, ma.l6_main,
        ma.mapping_conf, ma.requires_review
      FROM mapper_activities ma
      JOIN pipeline_runs pr USING (run_id)
      LEFT JOIN parser_activities pa
        ON pa.run_id = ma.run_id AND pa.idx = ma.idx
      WHERE pr.report_date = ${dStr}
      ORDER BY ma.mapping_conf ASC NULLS FIRST
      LIMIT 12
    `) as Array<{
      id: number | string;
      company: string | null;
      wa: string | null;
      l6_main: string | null;
      mapping_conf: number | string | null;
      requires_review: boolean | null;
    }>;

    const items: Record<string, AgentTaskItem[]> = {};
    items["Mapper"] = mapperItems.map((r) => {
      const conf = r.mapping_conf != null ? Number(r.mapping_conf) : 0;
      return {
        id: `mapper-${r.id}`,
        trade: r.l6_main ?? "—",
        contractor: r.company ?? "—",
        status: deriveItemStatus("Mapper", {
          requires_review: Boolean(r.requires_review),
          mapping_conf: conf,
        }),
      };
    });
    // 나머지 단계는 빈 배열 (FE 가 "데이터 없음" UI 처리)
    for (const agent of [
      "Collector",
      "Parser",
      "HIL Review",
      "Atomizer",
      "Exporter",
      "Forecaster",
      "Optimizer",
    ]) {
      items[agent] = [];
    }
    itemsByDate[dStr] = items;
  }

  return NextResponse.json({ tasks, progressByDate, itemsByDate });
}
