export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import {
  deriveYearlySaving,
  deriveProductivityTimeseries,
} from "@/lib/transforms";

// Task 5.2: /api/mock/dashboard PG swap
// 기존 JSON shape ({ sites: Site[], dashboard: DashboardFixture }) 유지.
// 내부 PRNG mock 대신 PG SELECT 로 채움.
export async function GET() {
  // 1) sites + 최신 forecasts LATERAL JOIN (각 site 의 last_run_id 의 worst forecast)
  const sitesRows = (await (sql as any)`
    SELECT
      s.site_id, s.name, s.location, s.is_mock, s.last_run_id,
      s.headcount, s.hours_saved, s.fte_saved, s.hours_saved_cum,
      f.today_productivity, f.delay_days, f.risk_level
    FROM sites s
    LEFT JOIN LATERAL (
      SELECT today_productivity, delay_days, risk_level
      FROM forecasts
      WHERE run_id = s.last_run_id
      ORDER BY today_productivity ASC NULLS LAST
      LIMIT 1
    ) f ON TRUE
  `) as Array<Record<string, unknown>>;

  // 2) Performance KPI
  const perfRows = (await (sql as any)`
    SELECT
      AVG(today_productivity) AS avg_productivity,
      AVG(delay_days) AS avg_delay,
      COUNT(*) FILTER (WHERE risk_level <> '정상') AS abnormal_total
    FROM forecasts
    WHERE run_id IN (SELECT last_run_id FROM sites WHERE last_run_id IS NOT NULL)
  `) as Array<Record<string, unknown>>;
  const perf = perfRows[0] ?? {};

  const recoverableRows = (await (sql as any)`
    SELECT AVG((recovery_distribution->>'p50')::numeric) AS recoverable_days
    FROM optimizer_advice
    WHERE run_id IN (SELECT last_run_id FROM sites WHERE last_run_id IS NOT NULL)
  `) as Array<{ recoverable_days: number | string | null }>;
  const recoverable = recoverableRows[0] ?? {};

  // 3) Impact KPI
  const impactRows = (await (sql as any)`
    SELECT
      COALESCE(SUM(headcount), 0) AS total_headcount,
      COALESCE(SUM(hours_saved_cum), 0) AS total_hours_saved,
      COALESCE(SUM(fte_saved), 0) AS total_fte_saved,
      COALESCE(SUM(headcount), 0) * 140 AS total_hours
    FROM sites
  `) as Array<Record<string, unknown>>;
  const impact = impactRows[0] ?? {};

  // 4) fleet 시계열 + sparklines (G6)
  const { trend, sparklines } = await deriveProductivityTimeseries("fleet", 30);

  // 5) site_distribution (mock 유지 — backlog: monthly_trend)
  const site_distribution = sitesRows.map((s) => ({
    site_id: String(s.site_id),
    site_name: String(s.name),
    hours_saved: Number(s.hours_saved ?? 0),
    fte_saved: Number(s.fte_saved ?? 0),
  }));

  // Site[] — types.ts Site shape 매핑.
  // PG 미보유 필드 (progress_planned/actual, gap_percent, spi, fte_saved 외 일부) 는 안전 기본값.
  // SiteOverviewCard 가 실제 의존하는 필드만 정확히 채움: id, name, location, status,
  // productivity_today, delay_days, abnormal_trades.
  const sites = sitesRows.map((s) => {
    const tp = s.today_productivity;
    const productivity = tp != null ? Number(tp) : 0;
    const delay = s.delay_days != null ? Number(s.delay_days) : 0;
    const risk = (s.risk_level as string | null) ?? "정상";
    const status: "normal" | "caution" | "risk" =
      risk === "이상" ? "risk" : risk === "주의" ? "caution" : "normal";
    const headcount = Number(s.headcount ?? 0);
    const hoursSaved = Number(s.hours_saved ?? 0);
    const fteSaved = Number(s.fte_saved ?? 0);
    const totalHours = headcount * 140;
    const aiRate = totalHours > 0 ? (hoursSaved / totalHours) * 100 : 0;
    return {
      id: String(s.site_id),
      name: String(s.name),
      location: (s.location as string | null) ?? (s.is_mock ? "Mock" : "—"),
      status,
      progress_planned: 0,
      progress_actual: 0,
      gap_percent: 0,
      productivity_today: Math.round(productivity),
      spi: 0,
      abnormal_trades: status === "normal" ? 0 : 1,
      fte_saved: fteSaved,
      hours_saved: hoursSaved,
      headcount,
      total_hours: totalHours,
      ai_replacement_rate: Math.round(aiRate * 10) / 10,
      expected_completion: "",
      recovered_completion: "",
      delay_days: delay,
      recovery_days: 0,
    };
  });

  const totalHeadcount = Number(impact.total_headcount ?? 0);
  const totalHoursSaved = Number(impact.total_hours_saved ?? 0);
  const totalFteSaved = Number(impact.total_fte_saved ?? 0);
  const totalHours = Number(impact.total_hours ?? 0);

  return NextResponse.json({
    sites,
    dashboard: {
      performance: {
        fleet_kpi: {
          avg_productivity: perf.avg_productivity != null ? Number(perf.avg_productivity) : 0,
          avg_delay: perf.avg_delay != null ? Number(perf.avg_delay) : 0,
          abnormal_total: Number(perf.abnormal_total ?? 0),
          recoverable_days:
            recoverable.recoverable_days != null ? Number(recoverable.recoverable_days) : 0,
        },
        fleet_trend: trend,
        site_sparklines: sparklines,
      },
      impact: {
        fleet_kpi: {
          today_count: 0,
          review_pending: 0,
          abnormal_count: Number(perf.abnormal_total ?? 0),
          last_updated: "—",
          total_headcount: totalHeadcount,
          total_hours_saved: totalHoursSaved,
          total_fte_saved: totalFteSaved,
          total_hours: totalHours,
          ai_replacement_rate:
            totalHours > 0
              ? Math.round((totalHoursSaved / totalHours) * 1000) / 10
              : 0,
          yearly_saving: deriveYearlySaving(totalFteSaved, totalHoursSaved),
          total_processed: 0,
          total_hours_saved_cum: totalHoursSaved,
        },
        site_distribution,
        monthly_trend: [], // G7 — backlog (다음 PR)
        per_site_automation: {},
      },
    },
  });
}
