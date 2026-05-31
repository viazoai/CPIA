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

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import type { AgentStageProgress } from "@/lib/types";

const STAGE_ORDER: Array<{
  step: number;
  agent: string;
  currentNode: string;
  is_hil: boolean;
}> = [
  { step: 1, agent: "Collector", currentNode: "collector", is_hil: false },
  { step: 2, agent: "Parser", currentNode: "parser", is_hil: false },
  { step: 3, agent: "Mapper", currentNode: "mapper", is_hil: false },
  { step: 3.5, agent: "Human Review", currentNode: "hil_1", is_hil: true },
  { step: 4, agent: "Atomizer", currentNode: "atomizer", is_hil: false },
  { step: 5, agent: "Exporter", currentNode: "exporter", is_hil: false },
  { step: 6, agent: "Forecaster", currentNode: "forecaster", is_hil: false },
  { step: 7, agent: "Optimizer", currentNode: "optimizer", is_hil: false },
];

// hil_2 / reporter / null 도 atomizer 이후 단계로 처리 (UI 표기상 Atomizer 이후 자동).
const POST_HIL1_NODES = new Set([
  "atomizer",
  "exporter",
  "forecaster",
  "hil_2",
  "optimizer",
  "reporter",
]);

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
    SELECT run_id, report_date, status, current_node, started_at, completed_at,
           atomized_count
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
  const isCompleted = run.status === "completed";
  const isWaitingHil = run.status === "waiting_hil_1";

  // 입력 파일 수 추정: parser_activities 의 distinct (company) — 정확히 매핑되진 않지만 시각화용.
  // 보다 정확히는 collector_inbox 의 file count 가 적합하나 시연용 단순화.
  const countRows = (await (sql as any)`
    SELECT
      (SELECT COUNT(*)::int FROM parser_activities WHERE run_id = ${run.run_id}) AS parser_rows,
      (SELECT COUNT(*)::int FROM mapper_activities WHERE run_id = ${run.run_id}) AS mapper_rows
  `) as Array<{ parser_rows: number; mapper_rows: number }>;
  const parserRows = countRows[0]?.parser_rows ?? 0;
  const mapperRows = countRows[0]?.mapper_rows ?? 0;

  // 단계 진행 위치 결정.
  // null (시작 직후) 이면 collector 진행중으로 간주.
  // hil_2/reporter 같은 후속 단계는 optimizer 까지 모두 done 으로 표시.
  const cn = run.current_node ?? "collector";
  let activeIdx = STAGE_ORDER.findIndex((s) => s.currentNode === cn);
  if (activeIdx < 0) {
    // hil_2, reporter, 또는 unknown → atomizer 이후로 간주
    activeIdx = POST_HIL1_NODES.has(cn) ? STAGE_ORDER.length - 1 : 0;
  }

  // 단계별 received 추정 — Parser 이후 단계는 parser 행 수 기준, 이전은 단순 10건 가정.
  // 시연용 단순화: 모든 stage 의 received = 처리량 추정 (parser_rows 가 가장 신뢰성 있음).
  const totalUnits = Math.max(parserRows, 10);

  const stages: AgentStageProgress[] = STAGE_ORDER.map((def, i) => {
    let percent: number;
    let received: number;
    let processed: number;
    let waiting_hil = false;

    if (isCompleted) {
      percent = 100;
      received = totalUnits;
      processed = totalUnits;
    } else if (i < activeIdx) {
      percent = 100;
      received = totalUnits;
      processed = totalUnits;
    } else if (i === activeIdx) {
      // 현재 진행중. HIL 정지 케이스면 waiting_hil=true, percent=0 (대기).
      if (def.is_hil && isWaitingHil) {
        percent = 0;
        received = mapperRows || totalUnits;
        processed = 0;
        waiting_hil = true;
      } else {
        // 진행중 — 단계 진입했지만 미완료. 시각적으로 50% 표시.
        percent = 50;
        received = totalUnits;
        processed = Math.floor(totalUnits * 0.5);
      }
    } else {
      percent = 0;
      received = 0;
      processed = 0;
    }

    return {
      step: def.step,
      agent: def.agent,
      is_hil: def.is_hil,
      received,
      processed,
      percent,
      waiting_hil,
    };
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
