export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import {
  deriveSCurve,
  deriveBaseline,
  deriveWpIdAndPath,
  deriveImpact,
} from "@/lib/transforms";
import type {
  ReportDaily,
  ReportKpi,
  BarItem,
  QuadrantPoint,
  OptimizerOutput,
  RawDataRow,
  WPSummaryRow,
  Status,
} from "@/lib/types";
import type { ReportDetail } from "@/lib/fixtures";

// Task 5.4: /api/mock/report PG swap (1년 윈도우)
// 기존 JSON shape ({ daily: ReportDaily[], details: Record<date, ReportDetail> }) 유지.
// fixture JSON 대신 PG SELECT 로 채움.
// 보조 함수: 날짜 ISO 변환
function toDateStr(d: Date | string): string {
  return d instanceof Date ? d.toISOString().slice(0, 10) : String(d).slice(0, 10);
}

// risk_level (PG: '정상' | '주의' | '이상') → Status
function riskToStatus(level: string | null | undefined): Status {
  if (level === "이상") return "risk";
  if (level === "주의") return "caution";
  if (level === "정상") return "normal";
  return "unknown";
}

// productivity 0..1 비율 (today_qty / plan_mh) → 0..100 % 변환
function pct(v: number | string | null | undefined): number {
  if (v == null) return 0;
  return Math.round(Number(v) * 100);
}

// quadrant 매핑 (productivity X, impact Y 기준)
function classifyQuadrant(
  productivity: number,
  impact: number,
): "risk" | "caution" | "watch" | "safe" {
  const lowProd = productivity < 80;
  const highImpact = impact >= 50;
  if (lowProd && highImpact) return "risk";
  if (lowProd) return "caution";
  if (highImpact) return "watch";
  return "safe";
}

function statusFromProductivity(p: number): "normal" | "caution" | "risk" {
  if (p < 70) return "risk";
  if (p < 90) return "caution";
  return "normal";
}

// PG optimizer_advice.recommendations 는 [{rank, text}] 또는 string[]. 정규화.
function normalizeRecommendations(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((r) => {
    if (typeof r === "string") return r;
    if (r && typeof r === "object" && "text" in r) return String((r as { text: unknown }).text ?? "");
    return String(r);
  });
}

const SITE_NAME = "M15X Ph-3 IBL";

export async function GET() {
  // 1) 1년 윈도우 일자 리스트 + 일자별 집계 (status / productivity_today / delay_days)
  const dailyRows = (await (sql as any)`
    SELECT
      pr.report_date,
      AVG(f.today_productivity) AS avg_prod,
      AVG(f.delay_days) AS avg_delay,
      MIN(CASE f.risk_level WHEN '이상' THEN 1 WHEN '주의' THEN 2 WHEN '정상' THEN 3 ELSE 4 END) AS worst_risk
    FROM pipeline_runs pr
    LEFT JOIN forecasts f USING (run_id)
    WHERE pr.report_date >= CURRENT_DATE - INTERVAL '1 year'
    GROUP BY pr.report_date
    ORDER BY pr.report_date DESC
  `) as Array<{
    report_date: Date | string;
    avg_prod: number | string | null;
    avg_delay: number | string | null;
    worst_risk: number | null;
  }>;

  const daily: ReportDaily[] = dailyRows.map((r) => {
    const prodPct = pct(r.avg_prod);
    const delayDays = r.avg_delay != null ? Math.round(Number(r.avg_delay)) : 0;
    const worst = r.worst_risk;
    const status: Status =
      worst === 1 ? "risk" : worst === 2 ? "caution" : worst === 3 ? "normal" : "unknown";
    return {
      date: toDateStr(r.report_date),
      status,
      productivity_today: prodPct,
      delay_days: delayDays,
      recovery_days: 0, // optimizer_advice 기반은 단건 detail 에서 계산
    };
  });

  // 2) 각 일자별 ReportDetail 빌드
  const details: Record<string, ReportDetail> = {};
  for (const d of daily) {
    const date = d.date;

    // 2-1) site_id 선택: 해당 일자 가장 많은 row 의 site_id
    const [siteRow] = (await (sql as any)`
      SELECT site_id, COUNT(*) AS n
      FROM pipeline_runs
      WHERE report_date = ${date}
      GROUP BY site_id
      ORDER BY n DESC NULLS LAST
      LIMIT 1
    `) as Array<{ site_id: string | null; n: string | number }>;
    const siteId = siteRow?.site_id ?? "m15x-ph3-ibl";

    // 2-2) KPI 집계
    const [kpiRow] = (await (sql as any)`
      SELECT
        AVG(f.today_productivity) AS today_prod,
        AVG(f.delay_days) AS delay_days,
        MAX(f.expected_completion) AS expected_completion
      FROM forecasts f
      JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${date}
    `) as Array<{
      today_prod: number | string | null;
      delay_days: number | string | null;
      expected_completion: Date | string | null;
    }>;
    const productivityToday = pct(kpiRow?.today_prod);
    const delayDays = kpiRow?.delay_days != null ? Math.round(Number(kpiRow.delay_days)) : 0;
    const expectedCompletion = kpiRow?.expected_completion
      ? toDateStr(kpiRow.expected_completion)
      : "";

    // 2-3) Optimizer (단건). recovery_pattern 평균을 recovery_days 로 활용.
    const [optRow] = (await (sql as any)`
      SELECT oa.l6_main, oa.company, oa.diagnosis, oa.recommendations,
             oa.recovery_distribution, oa.recovery_pattern, oa.degradation_cases
      FROM optimizer_advice oa
      JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${date}
      ORDER BY oa.created_at DESC
      LIMIT 1
    `) as Array<{
      l6_main: string | null;
      company: string | null;
      diagnosis: string | null;
      recommendations: unknown;
      recovery_distribution: unknown;
      recovery_pattern: Array<{ date: string; recovery_days: number | null }> | null;
      degradation_cases: Array<{ date?: string; description?: string; outcome?: string }> | null;
    }>;

    // recovery_pattern 의 평균 일수 (null 제외)
    let recoveryDaysAvg = 0;
    if (optRow?.recovery_pattern && Array.isArray(optRow.recovery_pattern)) {
      const valid = optRow.recovery_pattern
        .map((p) => p?.recovery_days)
        .filter((v): v is number => v != null);
      if (valid.length > 0) {
        recoveryDaysAvg = Math.round(valid.reduce((s, v) => s + v, 0) / valid.length);
      }
    }
    // 일자 리스트의 recovery_days 도 detail 빌드 후 보정
    d.recovery_days = recoveryDaysAvg;

    // 회복 가능 생산성 폭: target − today (target 은 baseline 평균으로 근사)
    const recoverableProductivity = 0; // baseline 기반은 quadrant 빌드 후 보정

    // 2-4) S-curve
    const sCurve = await deriveSCurve(siteId, date, null);

    // 2-5) contractor_bars (업체별 평균 생산성)
    const contractorRows = (await (sql as any)`
      SELECT ma.company AS label,
             AVG(ma.today_qty / NULLIF(ma.plan_mh, 0)) AS productivity
      FROM mapper_activities ma
      JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${date}
        AND ma.company IS NOT NULL
      GROUP BY ma.company
      ORDER BY productivity DESC NULLS LAST
    `) as Array<{ label: string; productivity: number | string | null }>;

    const contractorBars: BarItem[] = await Promise.all(
      contractorRows.map(async (r) => {
        const value = pct(r.productivity);
        // baseline 은 그 업체의 가장 첫 l6_main 기준 (단순화 — page 표시는 라인 dot)
        return {
          label: r.label,
          value,
          status: statusFromProductivity(value),
        };
      }),
    );

    // 2-6) trade_bars (공종별)
    const tradeRows = (await (sql as any)`
      SELECT ma.l6_main AS label,
             AVG(ma.today_qty / NULLIF(ma.plan_mh, 0)) AS productivity
      FROM mapper_activities ma
      JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${date}
        AND ma.l6_main IS NOT NULL
      GROUP BY ma.l6_main
      ORDER BY productivity DESC NULLS LAST
    `) as Array<{ label: string; productivity: number | string | null }>;

    const tradeBars: BarItem[] = tradeRows.map((r) => {
      const value = pct(r.productivity);
      return { label: r.label, value, status: statusFromProductivity(value) };
    });

    // 2-7) quadrant (mapper_activities + forecasts join, WP 단위)
    const quadRows = (await (sql as any)`
      SELECT ma.wa, ma.l6_main, ma.company,
             AVG(f.today_productivity) AS productivity,
             SUM(ma.plan_total_qty) AS plan_total_qty,
             AVG(ma.plan_mh) AS plan_mh
      FROM mapper_activities ma
      JOIN pipeline_runs pr USING (run_id)
      LEFT JOIN forecasts f
        ON f.run_id = ma.run_id
        AND f.l6_main = ma.l6_main
        AND f.company = ma.company
      WHERE pr.report_date = ${date}
      GROUP BY ma.wa, ma.l6_main, ma.company
    `) as Array<{
      wa: string | null;
      l6_main: string | null;
      company: string | null;
      productivity: number | string | null;
      plan_total_qty: number | string | null;
      plan_mh: number | string | null;
    }>;

    const quadrant: QuadrantPoint[] = quadRows.map((r) => {
      const path = deriveWpIdAndPath(r.wa, r.l6_main, SITE_NAME);
      const productivity = pct(r.productivity);
      const impact = deriveImpact(
        r.plan_total_qty != null ? Number(r.plan_total_qty) : null,
        r.plan_mh != null ? Number(r.plan_mh) : null,
      );
      return {
        wp_id: path.wp_id,
        wp_name: path.wp_name || path.wp_id,
        trade: r.l6_main ?? "",
        productivity,
        impact,
        quadrant: classifyQuadrant(productivity, impact),
        size: Math.max(30, Math.min(120, Math.round(impact))),
      };
    });

    // 2-8) wp_summary (mapper_activities aggregated by wa/l6_main/company)
    const wpRows = (await (sql as any)`
      SELECT ma.wa, ma.l6_main, ma.company,
             SUM(ma.today_qty) AS today_total,
             SUM(ma.plan_total_qty) AS plan_total,
             AVG(ma.progress_percent) AS progress_pct,
             AVG(f.today_productivity) AS productivity,
             AVG(ma.plan_mh) AS plan_mh
      FROM mapper_activities ma
      JOIN pipeline_runs pr USING (run_id)
      LEFT JOIN forecasts f
        ON f.run_id = ma.run_id
        AND f.l6_main = ma.l6_main
        AND f.company = ma.company
      WHERE pr.report_date = ${date}
      GROUP BY ma.wa, ma.l6_main, ma.company
    `) as Array<{
      wa: string | null;
      l6_main: string | null;
      company: string | null;
      today_total: number | string | null;
      plan_total: number | string | null;
      progress_pct: number | string | null;
      productivity: number | string | null;
      plan_mh: number | string | null;
    }>;

    const wpSummary: WPSummaryRow[] = await Promise.all(
      wpRows.map(async (r) => {
        const path = deriveWpIdAndPath(r.wa, r.l6_main, SITE_NAME);
        const productivity = pct(r.productivity);
        const impact = deriveImpact(
          r.plan_total != null ? Number(r.plan_total) : null,
          r.plan_mh != null ? Number(r.plan_mh) : null,
        );
        // baseline: 동일 업체+공종 이력 평균 생산성 (G21)
        const baselineRaw =
          r.company && r.l6_main ? await deriveBaseline(r.company, r.l6_main) : 0;
        const baseline = pct(baselineRaw);
        const progressPct = r.progress_pct != null ? Math.round(Number(r.progress_pct)) : 0;
        return {
          wp_id: path.wp_id,
          wp_name: path.wp_name || path.wp_id,
          trade: r.l6_main ?? "",
          bp_name: r.company ?? "",
          start_date: "",
          end_date: "",
          progress_pct: progressPct,
          productivity,
          impact,
          baseline,
          status: statusFromProductivity(productivity),
        };
      }),
    );

    // 2-9) Optimizer output (단건 → OptimizerOutput shape)
    const optWpId = optRow
      ? deriveWpIdAndPath(null, optRow.l6_main ?? null, SITE_NAME).wp_id
      : "";
    const optimizer: OptimizerOutput = {
      wp_id: optWpId,
      diagnosis: optRow?.diagnosis ?? "",
      similar_cases:
        optRow?.degradation_cases?.map((c) => ({
          date: c?.date ?? "",
          description: c?.description ?? "",
          outcome: c?.outcome ?? "",
        })) ?? [],
      recommendations: normalizeRecommendations(optRow?.recommendations),
      details: [],
    };

    // 2-10) raw_data (parser_activities, 표시는 RawDataTab 에서만)
    const rawRows = (await (sql as any)`
      SELECT pa.zone, pa.trade, pa.wbs_mid_name, pa.company, pa.work_content,
             pa.today_qty, pa.unit
      FROM parser_activities pa
      JOIN pipeline_runs pr USING (run_id)
      WHERE pr.report_date = ${date}
      ORDER BY pa.idx
      LIMIT 500
    `) as Array<{
      zone: string | null;
      trade: string | null;
      wbs_mid_name: string | null;
      company: string | null;
      work_content: string | null;
      today_qty: number | string | null;
      unit: string | null;
    }>;

    const rawData: RawDataRow[] = rawRows.map((r) => ({
      building: r.zone ?? "",
      trade: r.trade ?? "",
      wp: r.wbs_mid_name ?? "",
      bp_name: r.company ?? "",
      work_content: r.work_content ?? "",
      quantity: r.today_qty != null ? Number(r.today_qty) : 0,
      unit: r.unit ?? "",
      workers: 0,
      equipment: "",
    }));

    // KPI 보정 (recoverable_productivity, target_productivity, recovered_completion)
    // target_productivity: 전체 wp baseline 평균
    const baselineMean =
      wpSummary.length > 0
        ? Math.round(
            wpSummary.reduce((s, w) => s + (w.baseline ?? 0), 0) / wpSummary.length,
          )
        : 0;
    const targetProductivity = baselineMean > 0 ? baselineMean : productivityToday;
    const recoverable = Math.max(0, targetProductivity - productivityToday);
    // recovered_completion: expected_completion 에서 recovery_days 만큼 당김
    let recoveredCompletion = expectedCompletion;
    if (expectedCompletion && recoveryDaysAvg > 0) {
      const exp = new Date(expectedCompletion + "T00:00:00Z");
      exp.setUTCDate(exp.getUTCDate() - recoveryDaysAvg);
      recoveredCompletion = exp.toISOString().slice(0, 10);
    }

    const kpi: ReportKpi = {
      productivity_today: productivityToday,
      productivity_history_diff: productivityToday - targetProductivity,
      delay_days: delayDays,
      expected_completion: expectedCompletion,
      recoverable_productivity: recoverable,
      target_productivity: targetProductivity,
      recovery_days: recoveryDaysAvg,
      recovered_completion: recoveredCompletion,
    };

    details[date] = {
      kpi,
      s_curve: sCurve,
      contractor_bars: contractorBars,
      trade_bars: tradeBars,
      quadrant,
      optimizer,
      raw_data: rawData,
      wp_summary: wpSummary,
    };
  }

  return NextResponse.json({ daily, details });
}
