// GET /api/runs/items?run_id=X&agent=Mapper
//
// 단계별 실제 아이템 반환.
//   Collector   — data/input/YYYYMMDD/ 파일 목록 (파이프라인 실행 전부터 존재)
//   Parser      — parser_activities (파싱 완료된 activity 행)
//   Mapper      — parser_activities 전체 vs mapper_activities 교차:
//                  mapped=done / unmapped=received → 실시간 매핑 진행 확인 가능
//   Human Review — mapper_activities.requires_review
//   나머지       — mapper_activities 기반 done
//
// 정렬: received/processing → hil_pending → done (미처리 먼저).
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

import fs from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import type { AgentTaskItem } from "@/lib/types";

const DATA_DIR = path.join(process.cwd(), "..", "data");

const STATUS_SORT: Record<AgentTaskItem["status"], number> = {
  processing:  0,
  received:    1,
  hil_pending: 2,
  blocked:     3,
  done:        4,
};

function sortItems(items: AgentTaskItem[]): AgentTaskItem[] {
  return [...items].sort((a, b) => STATUS_SORT[a.status] - STATUS_SORT[b.status]);
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const runId = url.searchParams.get("run_id");
  const agent = url.searchParams.get("agent");

  if (!runId || !agent) {
    return NextResponse.json({ ok: false, error: "run_id, agent 파라미터 필요" }, { status: 400 });
  }

  try {
    let items: AgentTaskItem[] = [];

    if (agent === "Collector") {
      // pipeline_runs 에서 report_date 조회 → data/input/YYYYMMDD/ 파일 목록
      const runRows = (await (sql as any)`
        SELECT TO_CHAR(report_date, 'YYYYMMDD') AS date_compact
        FROM pipeline_runs WHERE run_id = ${runId} LIMIT 1
      `) as Array<{ date_compact: string }>;

      const dateCompact = runRows[0]?.date_compact ?? "";
      if (dateCompact) {
        const inputDir = path.join(DATA_DIR, "input", dateCompact);
        const all = await fs.readdir(inputDir).catch(() => [] as string[]);
        const xlsxFiles = all.filter((f) => /\.(xlsx|xlsm)$/i.test(f));
        items = xlsxFiles.map((f, i) => ({
          id:         String(i + 1).padStart(3, "0"),
          trade:      "파일",
          contractor: f,
          status:     "done" as const,
        }));
      }
    }

    else if (agent === "Parser") {
      // Parser 단계: wa 아직 없음 → company(층코드) 대신 work_content(작업 설명) 표시
      const rows = (await (sql as any)`
        SELECT idx, l5_disc, trade, company, work_content
        FROM parser_activities
        WHERE run_id = ${runId}
        ORDER BY idx
      `) as Array<{
        idx: number;
        l5_disc: string | null;
        trade: string | null;
        company: string;
        work_content: string | null;
      }>;

      items = rows.map((r) => ({
        id:         String(r.idx).padStart(3, "0"),
        trade:      r.trade ?? r.l5_disc ?? "—",
        contractor: r.work_content ?? r.company ?? "—",
        status:     "done" as const,
      }));
    }

    else if (agent === "Mapper") {
      // parser_activities 전체 vs mapper_activities 교차: mapped=done / unmapped=received
      const parserRows = (await (sql as any)`
        SELECT pa.idx, pa.l5_disc, pa.trade, ma.wa, ma.l6_main
        FROM parser_activities pa
        LEFT JOIN mapper_activities ma ON ma.run_id = pa.run_id AND ma.idx = pa.idx
        WHERE pa.run_id = ${runId}
        ORDER BY pa.idx
      `) as Array<{
        idx: number;
        l5_disc: string | null;
        trade: string | null;
        wa: string | null;
        l6_main: string | null;
      }>;

      items = parserRows.map((r) => ({
        id:         String(r.idx).padStart(3, "0"),
        // l6_main(WBS명) 있으면 매핑 완료, 없으면 미완료
        trade:      r.l6_main ?? r.trade ?? r.l5_disc ?? "—",
        contractor: r.wa ?? "—",
        status:     (r.l6_main != null ? "done" : "received") as AgentTaskItem["status"],
      }));
    }

    else if (agent === "Human Review") {
      const rows = (await (sql as any)`
        SELECT ma.idx, ma.l6_main, ma.trade, ma.wa, ma.requires_review
        FROM mapper_activities ma
        WHERE ma.run_id = ${runId}
        ORDER BY ma.requires_review DESC, ma.idx
      `) as Array<{
        idx: number;
        l6_main: string | null;
        trade: string | null;
        wa: string | null;
        requires_review: boolean;
      }>;

      items = rows.map((r) => ({
        id:         String(r.idx).padStart(3, "0"),
        trade:      r.l6_main ?? r.trade ?? "—",
        contractor: r.wa ?? "—",
        status:     (r.requires_review ? "hil_pending" : "done") as AgentTaskItem["status"],
      }));
    }

    else {
      // Atomizer / Exporter / Forecaster / Optimizer — mapper_activities 기반
      const rows = (await (sql as any)`
        SELECT idx, l6_main, trade, wa
        FROM mapper_activities
        WHERE run_id = ${runId}
        ORDER BY idx
      `) as Array<{ idx: number; l6_main: string | null; trade: string | null; wa: string | null }>;

      items = rows.map((r) => ({
        id:         String(r.idx).padStart(3, "0"),
        trade:      r.l6_main ?? r.trade ?? "—",
        contractor: r.wa ?? "—",
        status:     "done" as const,
      }));
    }

    return NextResponse.json({ ok: true, items: sortItems(items) });
  } catch (e: any) {
    return NextResponse.json(
      { ok: false, error: e?.message ?? "query failed" },
      { status: 500 },
    );
  }
}
