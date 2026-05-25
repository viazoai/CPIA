// /api/mock/agent-tasks — 좌측 일별 목록만 반환.
// progress / items 는 /api/mock/agent-tasks/[date] 에서 lazy load.
// 1년치 N+1 (date × 4 쿼리) 제거: list 는 단일 CTE 쿼리.

export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import { deriveProgressPercent } from "@/lib/transforms";
import type { DailyTask } from "@/lib/types";

export async function GET() {
  const useMock = process.env.CPIA_DEMO_FALLBACK === "on";

  // latest_runs: 같은 (date) 에 여러 run 이 있으면 최신 started_at 만.
  // parser_counts: 날짜별 parser_activities 총건수 (Daily 카드 우상단 숫자).
  const rows = (await (sql as any)`
    WITH latest_runs AS (
      SELECT DISTINCT ON (report_date)
        report_date, status, current_node
      FROM pipeline_runs
      WHERE report_date >= CURRENT_DATE - INTERVAL '1 year'
        AND is_mock = ${useMock}
      ORDER BY report_date DESC, started_at DESC
    ),
    parser_counts AS (
      SELECT pr.report_date, COUNT(*)::int AS parser_count
      FROM parser_activities pa
      JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date >= CURRENT_DATE - INTERVAL '1 year'
        AND pa.is_mock = ${useMock}
      GROUP BY pr.report_date
    )
    SELECT lr.report_date, lr.status, lr.current_node,
           COALESCE(pc.parser_count, 0) AS parser_count
    FROM latest_runs lr
    LEFT JOIN parser_counts pc USING (report_date)
    ORDER BY lr.report_date DESC
  `) as Array<{
    report_date: Date | string;
    status: string | null;
    current_node: string | null;
    parser_count: number;
  }>;

  const tasks: DailyTask[] = rows.map((r) => {
    const dStr =
      typeof r.report_date === "string"
        ? r.report_date.slice(0, 10)
        : r.report_date.toISOString().slice(0, 10);
    const statusRaw = r.status ?? "";
    const status: DailyTask["status"] =
      statusRaw === "waiting_hil_1"
        ? "review_pending"
        : statusRaw === "completed"
          ? "completed"
          : "running";
    return {
      date: dStr,
      total_count: r.parser_count,
      progress_percent: deriveProgressPercent(statusRaw, r.current_node ?? null),
      status,
      has_anomaly: false,
    };
  });

  return NextResponse.json(
    { tasks },
    {
      headers: {
        "Cache-Control": "s-maxage=30, stale-while-revalidate=60",
      },
    },
  );
}
