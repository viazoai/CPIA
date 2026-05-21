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
        AND ma.trade IN ('건축', '토목')
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

    // Collector — 통합 작업일보 수신 1건.
    const collectorItems = (await (sql as any)`
      SELECT id, report_date
      FROM parser_reports
      WHERE report_date = ${dStr} AND is_mock = ${useMock}
      ORDER BY created_at DESC LIMIT 1
    `) as Array<{ id: number | string; report_date: Date | string }>;
    items["Collector"] = collectorItems.map((r) => ({
      id: `collector-${r.id}`,
      trade: "통합 작업일보",
      contractor: "—",
      status: "done" as const,
    }));

    // HIL Review — mapper_activities WHERE requires_review = TRUE + 건축+토목.
    const hilItems = (await (sql as any)`
      SELECT ma.id, ma.l6_main, ma.company, ma.requires_review
      FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${dStr} AND ma.is_mock = ${useMock}
        AND ma.requires_review = TRUE
        AND ma.trade IN ('건축', '토목')
      ORDER BY ma.mapping_conf ASC NULLS FIRST
      LIMIT 200
    `) as Array<{ id: number | string; l6_main: string | null; company: string | null }>;
    items["HIL Review"] = hilItems.map((r) => ({
      id: `hil-${r.id}`,
      trade: r.l6_main ?? "—",
      contractor: r.company ?? "—",
      status: "hil_pending" as const,
    }));

    // Atomizer — 매핑 완료 (l7_5_activity 있음) row.
    const atomItems = (await (sql as any)`
      SELECT ma.id, ma.l6_main, ma.company
      FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${dStr} AND ma.is_mock = ${useMock}
        AND ma.l7_5_activity IS NOT NULL
        AND ma.trade IN ('건축', '토목')
      ORDER BY ma.id
      LIMIT 200
    `) as Array<{ id: number | string; l6_main: string | null; company: string | null }>;
    items["Atomizer"] = atomItems.map((r) => ({
      id: `atom-${r.id}`,
      trade: r.l6_main ?? "—",
      contractor: r.company ?? "—",
      status: "done" as const,
    }));

    // Exporter — 통합 작업일보 출력 (daily_reports 1건).
    const exportItems = (await (sql as any)`
      SELECT dr.id
      FROM daily_reports dr JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${dStr} AND dr.is_mock = ${useMock}
      ORDER BY dr.created_at DESC LIMIT 1
    `) as Array<{ id: number | string }>;
    items["Exporter"] = exportItems.map((r) => ({
      id: `export-${r.id}`,
      trade: "통합 작업일보",
      contractor: "—",
      status: "done" as const,
    }));

    // Forecaster — forecasts row 별 (company × l6_main 단위 진단).
    const forecasterItems = (await (sql as any)`
      SELECT f.id, f.l6_main, f.company, f.risk_level
      FROM forecasts f JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${dStr} AND f.is_mock = ${useMock}
      ORDER BY (CASE f.risk_level WHEN '이상' THEN 1 WHEN '주의' THEN 2 ELSE 3 END), f.id
      LIMIT 200
    `) as Array<{ id: number | string; l6_main: string | null; company: string | null; risk_level: string | null }>;
    items["Forecaster"] = forecasterItems.map((r) => ({
      id: `forecaster-${r.id}`,
      trade: r.l6_main ?? "—",
      contractor: r.company ?? "—",
      status: "done" as const,
    }));

    // Optimizer — optimizer_advice row 별 (조언 생성된 그룹).
    const optimizerItems = (await (sql as any)`
      SELECT oa.id, oa.l6_main, oa.company
      FROM optimizer_advice oa JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${dStr} AND oa.is_mock = ${useMock}
      ORDER BY oa.id
      LIMIT 200
    `) as Array<{ id: number | string; l6_main: string | null; company: string | null }>;
    items["Optimizer"] = optimizerItems.map((r) => ({
      id: `optimizer-${r.id}`,
      trade: r.l6_main ?? "—",
      contractor: r.company ?? "—",
      status: "done" as const,
    }));

    itemsByDate[dStr] = items;
  }

  return NextResponse.json({ tasks, progressByDate, itemsByDate });
}
