// GET /api/runs/progress?date=YYYY-MM-DD
//
// pipeline_runs 의 해당 date 최신 row 를 SELECT, current_node + status + sub-table
// count 로 AgentStageProgress[] 8개를 구성해 반환.
// tasks/page.tsx 가 2초 간격으로 polling 해 게이지 실시간 갱신.
//
// stage 매핑 (current_node → 8-stage UI):
//   collector  → Collector
//   parser     → Parser
//   mapper     → Mapper
//   hil_1      → Human Review (status='waiting_hil_1' 이면 waiting_hil=true)
//   atomizer   → Atomizer
//   exporter   → Exporter
//   forecaster → Forecaster
//   optimizer  → Optimizer
//   hil_2 / reporter → UI 미노출 단계 (시연 v1 에선 atomizer 이후 자동 진행으로 간주)
//
// percent 산출: current_node 위치 기준 직전 stages=100%, current=50%, 이후=0%.
// status='completed' 면 모든 stages=100%.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

import fs from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import type { AgentStageProgress } from "@/lib/types";
import { computeProgressStages } from "@/lib/progress-stages";

const DATA_DIR = process.env.DATA_DIR ?? path.join(process.cwd(), "data");

async function countInputFiles(dateCompact: string): Promise<number> {
  try {
    const dir = path.join(DATA_DIR, "input", dateCompact);
    const files = await fs.readdir(dir);
    return files.filter((f) => /\.(xlsx|xlsm)$/i.test(f)).length;
  } catch {
    return 0;
  }
}


export async function GET(req: Request) {
  const url = new URL(req.url);
  const date = url.searchParams.get("date");
  if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return NextResponse.json(
      { ok: false, error: "date query (YYYY-MM-DD) 필요" },
      { status: 400 },
    );
  }

  const rows = (await (sql as any)`
    SELECT run_id, TO_CHAR(report_date, 'YYYYMMDD') AS report_date,
           status, current_node, started_at, completed_at, atomized_count
    FROM pipeline_runs
    WHERE report_date = ${date}
    ORDER BY started_at DESC
    LIMIT 1
  `) as Array<{
    run_id: string;
    report_date: Date | string;
    status: string;
    current_node: string | null;
    started_at: Date | string;
    completed_at: Date | string | null;
    atomized_count: number | null;
  }>;

  if (rows.length === 0) {
    return NextResponse.json({ ok: false, error: "no run for date" }, { status: 404 });
  }

  const run = rows[0];

  // 단계별 실제 카운트 + agent_progress 조회.
  // Collector = data/input/YYYYMMDD/ 파일 수 (DB 보다 먼저 존재)
  // Parser    = parser_activities 행 수
  // Mapper    = mapper_activities 행 수
  // Atomizer+ = agent_progress per-(run,agent) 행 기반
  const dateCompact = String(run.report_date ?? "").replace(/-/g, "").slice(0, 8);
  const [fileCount, countRows, progressRows] = await Promise.all([
    countInputFiles(dateCompact),
    (sql as any)`
      SELECT
        (SELECT COUNT(*)::int FROM parser_activities WHERE run_id = ${run.run_id}) AS parser_rows,
        (SELECT COUNT(*)::int FROM mapper_activities WHERE run_id = ${run.run_id}) AS mapper_rows
    ` as Promise<Array<{ parser_rows: number; mapper_rows: number }>>,
    (sql as any)`
      SELECT agent, processed, total
      FROM agent_progress
      WHERE run_id = ${run.run_id}
    ` as Promise<Array<{ agent: string; processed: number; total: number }>>,
  ]);
  const parserRows    = countRows[0]?.parser_rows ?? 0;
  const mapperRows    = countRows[0]?.mapper_rows ?? 0;
  const atomizedCount = run.atomized_count ?? 0;

  const agentProgress: Record<string, { processed: number; total: number }> = {};
  for (const r of progressRows) {
    agentProgress[r.agent] = {
      processed: Math.max(0, Number(r.processed) || 0),
      total: Math.max(0, Number(r.total) || 0),
    };
  }

  const stages: AgentStageProgress[] = computeProgressStages({
    status: run.status,
    current_node: run.current_node,
    fileCount,
    parserRows,
    mapperRows,
    atomizedCount,
    agentProgress,
  });

  return NextResponse.json({
    ok: true,
    run_id: run.run_id,
    date,
    status: run.status,
    current_node: run.current_node,
    started_at: run.started_at,
    completed_at: run.completed_at,
    stages,
  });
}
