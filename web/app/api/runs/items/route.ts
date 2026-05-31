// GET /api/runs/items?run_id=X&agent=Mapper
//
// 단계별 실제 DB 아이템 반환. 현재 지원 단계:
//   Collector   — parser_report_meta 에서 bp_name(업체) 목록
//   Parser      — parser_activities 행 (처리완료된 것들)
//   Mapper      — parser_activities 전체 vs mapper_activities 교차:
//                  mapper_activities 있음 → done / 없음 → received
//                  이를 통해 "아직 매핑 안 된 항목"을 실시간으로 표시 가능
//   Human Review — mapper_activities 중 requires_review=true
//   Atomizer/Exporter/Forecaster/Optimizer — mapper_activities 를 기반으로 done 표시
//
// 정렬: received/processing → hil_pending → done 순 (미처리 먼저).
export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import type { AgentTaskItem } from "@/lib/types";

const STATUS_SORT: Record<AgentTaskItem["status"], number> = {
  processing:  0,
  received:    1,
  hil_pending: 2,
  blocked:     3,
  done:        4,
};

function sortItems(items: AgentTaskItem[]): AgentTaskItem[] {
  return [...items].sort(
    (a, b) => STATUS_SORT[a.status] - STATUS_SORT[b.status],
  );
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const runId = url.searchParams.get("run_id");
  const agent = url.searchParams.get("agent");

  if (!runId || !agent) {
    return NextResponse.json(
      { ok: false, error: "run_id, agent 파라미터 필요" },
      { status: 400 },
    );
  }

  try {
    let items: AgentTaskItem[] = [];

    if (agent === "Collector") {
      // parser_report_meta 의 bp_name 목록 → 업체(파일) 단위 표시
      const rows = (await (sql as any)`
        SELECT bp_name
        FROM parser_report_meta
        WHERE run_id = ${runId}
        ORDER BY bp_name
      `) as Array<{ bp_name: string }>;

      items = rows.map((r, i) => ({
        id: String(i + 1).padStart(3, "0"),
        trade:      "—",
        contractor: r.bp_name,
        status:     "done" as const,
      }));
    }

    else if (agent === "Parser") {
      const rows = (await (sql as any)`
        SELECT idx, trade, company
        FROM parser_activities
        WHERE run_id = ${runId}
        ORDER BY idx
      `) as Array<{ idx: number; trade: string | null; company: string }>;

      items = rows.map((r) => ({
        id:         String(r.idx).padStart(3, "0"),
        trade:      r.trade ?? "—",
        contractor: r.company,
        status:     "done" as const,
      }));
    }

    else if (agent === "Mapper") {
      // parser_activities 전체 목록 조회 후 mapper_activities 와 교차.
      // mapper_activities 에 있으면 done, 없으면 received.
      const [parserRows, mapperRows] = await Promise.all([
        (sql as any)`
          SELECT idx, trade, company
          FROM parser_activities
          WHERE run_id = ${runId}
          ORDER BY idx
        ` as Promise<Array<{ idx: number; trade: string | null; company: string }>>,
        (sql as any)`
          SELECT idx
          FROM mapper_activities
          WHERE run_id = ${runId}
        ` as Promise<Array<{ idx: number }>>,
      ]);

      const mappedIdx = new Set(mapperRows.map((r: { idx: number }) => r.idx));

      items = parserRows.map((r: { idx: number; trade: string | null; company: string }) => ({
        id:         String(r.idx).padStart(3, "0"),
        trade:      r.trade ?? "—",
        contractor: r.company,
        status:     (mappedIdx.has(r.idx) ? "done" : "received") as AgentTaskItem["status"],
      }));
    }

    else if (agent === "Human Review") {
      const rows = (await (sql as any)`
        SELECT idx, trade, company, requires_review
        FROM mapper_activities
        WHERE run_id = ${runId}
        ORDER BY requires_review DESC, idx
      `) as Array<{ idx: number; trade: string | null; company: string; requires_review: boolean }>;

      items = rows.map((r) => ({
        id:         String(r.idx).padStart(3, "0"),
        trade:      r.trade ?? "—",
        contractor: r.company,
        status:     (r.requires_review ? "hil_pending" : "done") as AgentTaskItem["status"],
      }));
    }

    else {
      // Atomizer / Exporter / Forecaster / Optimizer — mapper_activities 기반
      const rows = (await (sql as any)`
        SELECT idx, trade, company
        FROM mapper_activities
        WHERE run_id = ${runId}
        ORDER BY idx
      `) as Array<{ idx: number; trade: string | null; company: string }>;

      items = rows.map((r) => ({
        id:         String(r.idx).padStart(3, "0"),
        trade:      r.trade ?? "—",
        contractor: r.company,
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
