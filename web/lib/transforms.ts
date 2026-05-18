// web/lib/transforms.ts
// FE↔BE 연결 Phase 4: pure transform 함수 모음 (G1/G11/G12/G17/G18)
// + PG 의존 transform 함수 (G4/G6/G10/G21/G22)

import sql from "@/lib/pg";
import type {
  FleetTrendPoint,
  AgentStageProgress,
  WBSNode,
  ChatMessage,
  Status,
} from "./types";

export function deriveProgressPercent(
  status: string,
  current_node: string | null,
): number {
  if (status === "completed") return 100;
  if (status === "waiting_hil_1") return 50;
  const NODE_MAP: Record<string, number> = {
    parser: 20,
    mapper: 30,
    atomizer: 60,
    exporter: 70,
    forecaster: 80,
    optimizer: 90,
  };
  return NODE_MAP[current_node ?? ""] ?? 0;
}

export function deriveYearlySaving(
  totalFteSaved: number,
  totalHoursSaved: number,
  hourlyRateKrw: number = 50000,
): number {
  return totalFteSaved * 1.5 + (totalHoursSaved * hourlyRateKrw) / 1e8;
}

export function deriveItemStatus(
  stage: string,
  row: {
    requires_review?: boolean;
    mapping_conf?: number;
    has_correction?: boolean;
    risk_level?: string;
  },
): "done" | "processing" | "received" | "hil_pending" | "blocked" {
  if (row.risk_level === "이상") return "blocked";
  switch (stage) {
    case "Mapper":
      if (row.requires_review) return "hil_pending";
      if ((row.mapping_conf ?? 0) >= 0.7) return "done";
      if ((row.mapping_conf ?? 0) >= 0.4) return "processing";
      return "received";
    case "HIL Review":
      return row.has_correction ? "done" : "hil_pending";
    default:
      return "done";
  }
}

export function deriveWpIdAndPath(
  wa: string | null,
  l6_main: string | null,
  site_name: string,
): { wp_id: string; wp_name: string; path: string } {
  const safe = (s: string | null) => (s ?? "unknown").replace(/\s+/g, "-").toLowerCase();
  const wp_id = `${safe(wa)}-${safe(l6_main)}`;
  const wp_name = `${wa ?? ""} ${l6_main ?? ""}`.trim();
  const path = [site_name, wa ?? "", l6_main ?? ""].filter(Boolean).join(" > ");
  return { wp_id, wp_name, path };
}

export function deriveImpact(
  planTotalQty: number | null,
  planMhRev2: number | null,
  normMax: number = 1e8,
): number {
  if (!planTotalQty || !planMhRev2) return 0;
  const raw = planTotalQty * planMhRev2;
  return Math.min(100, Math.max(0, (raw / normMax) * 100));
}

// ──────────────────────────────────────────────
// G6: 현장별 생산성 시계열
// mapped_history × mapper_activities → AVG(today_qty / NULLIF(plan_mh, 0))
// ──────────────────────────────────────────────
export async function deriveProductivityTimeseries(
  siteId: string,
  days: number = 30,
): Promise<{ trend: FleetTrendPoint[]; sparklines: Record<string, number[]> }> {
  const rows = (await (sql as any)`
    SELECT
      mh.report_date,
      mh.site_id,
      AVG(mh.today_qty / NULLIF(ma.plan_mh, 0)) AS productivity
    FROM mapped_history mh
    LEFT JOIN mapper_activities ma USING (run_id, wa, l6_main, company)
    WHERE mh.report_date >= CURRENT_DATE - ${days}::integer
      AND (${siteId} = 'fleet' OR mh.site_id = ${siteId})
    GROUP BY mh.report_date, mh.site_id
    ORDER BY mh.report_date
  `) as Array<{ report_date: Date; site_id: string; productivity: number | null }>;

  const byDate = new Map<string, number[]>();
  const sparklines: Record<string, number[]> = {};
  for (const r of rows) {
    const dStr =
      r.report_date instanceof Date
        ? r.report_date.toISOString().slice(0, 10)
        : String(r.report_date).slice(0, 10);
    const v = r.productivity != null ? Number(r.productivity) : 0;
    if (!byDate.has(dStr)) byDate.set(dStr, []);
    byDate.get(dStr)!.push(v);
    if (!sparklines[r.site_id]) sparklines[r.site_id] = [];
    sparklines[r.site_id].push(v);
  }
  const trend: FleetTrendPoint[] = Array.from(byDate.entries()).map(([date, vals]) => ({
    date,
    mean: vals.reduce((s, v) => s + v, 0) / vals.length,
    min: Math.min(...vals),
    max: Math.max(...vals),
  }));
  return { trend, sparklines };
}

// ──────────────────────────────────────────────
// G10: 8 단계 (1..7 + 3.5 HIL) 진행률
// ──────────────────────────────────────────────
export async function deriveStageProgress(date: string): Promise<AgentStageProgress[]> {
  const counts = (await (sql as any)`
    SELECT
      (SELECT COUNT(*) FROM parser_reports WHERE report_date = ${date}) AS parser_reports,
      (SELECT COUNT(*) FROM parser_activities pa JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date}) AS parser_acts,
      (SELECT COUNT(*) FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date}) AS mapper_acts,
      (SELECT COUNT(*) FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date} AND ma.requires_review) AS hil_received,
      (SELECT COUNT(*) FROM mapping_corrections WHERE report_date = ${date}) AS hil_done,
      (SELECT COALESCE(SUM(atomized_count), 0) FROM pipeline_runs WHERE report_date = ${date}) AS atomized,
      (SELECT COUNT(*) FROM daily_reports WHERE report_date = ${date}) AS exporter,
      (SELECT COUNT(*) FROM forecasts f JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date}) AS forecasts_done,
      (SELECT COUNT(*) FROM forecasts f JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date} AND f.risk_level <> '정상') AS opt_received,
      (SELECT COUNT(*) FROM optimizer_advice oa JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date}) AS opt_done
  `) as Array<Record<string, number | string | null>>;

  const c = counts[0] ?? {};
  const n = (k: string) => Number(c[k] ?? 0);
  const pct = (a: number, b: number) => (b > 0 ? Math.round((a / b) * 100) : 0);

  return [
    {
      step: 1,
      agent: "Collector",
      is_hil: false,
      received: n("parser_reports"),
      processed: n("parser_reports"),
      percent: n("parser_reports") > 0 ? 100 : 0,
      waiting_hil: false,
    },
    {
      step: 2,
      agent: "Parser",
      is_hil: false,
      received: n("parser_reports"),
      processed: n("parser_acts"),
      percent: n("parser_reports") > 0 ? 100 : 0,
      waiting_hil: false,
    },
    {
      step: 3,
      agent: "Mapper",
      is_hil: false,
      received: n("parser_acts"),
      processed: n("mapper_acts"),
      percent: pct(n("mapper_acts"), n("parser_acts")),
      waiting_hil: false,
    },
    {
      step: 3.5,
      agent: "HIL Review",
      is_hil: true,
      received: n("hil_received"),
      processed: n("hil_done"),
      percent: pct(n("hil_done"), n("hil_received")),
      waiting_hil: n("hil_received") > n("hil_done"),
    },
    {
      step: 4,
      agent: "Atomizer",
      is_hil: false,
      received: Math.max(0, n("mapper_acts") - n("hil_received")),
      processed: n("atomized"),
      percent: 0,
      waiting_hil: false,
    },
    {
      step: 5,
      agent: "Exporter",
      is_hil: false,
      received: n("atomized"),
      processed: n("exporter"),
      percent: 0,
      waiting_hil: false,
    },
    {
      step: 6,
      agent: "Forecaster",
      is_hil: false,
      received: n("mapper_acts"),
      processed: n("forecasts_done"),
      percent: 0,
      waiting_hil: false,
    },
    {
      step: 7,
      agent: "Optimizer",
      is_hil: false,
      received: n("opt_received"),
      processed: n("opt_done"),
      percent: 0,
      waiting_hil: false,
    },
  ];
}

// ──────────────────────────────────────────────
// G21: 업체×공종 이력 평균 생산성 (Baseline)
// ──────────────────────────────────────────────
export async function deriveBaseline(
  company: string,
  l6_main: string,
): Promise<number> {
  const rows = (await (sql as any)`
    SELECT AVG(mh.today_qty / NULLIF(ma.plan_mh, 0)) AS baseline
    FROM mapped_history mh
    LEFT JOIN mapper_activities ma USING (run_id, wa, l6_main, company)
    WHERE mh.company = ${company} AND mh.l6_main = ${l6_main}
  `) as Array<{ baseline: number | null }>;
  const baseline = rows[0]?.baseline;
  if (baseline != null) return Number(baseline);

  const fb = (await (sql as any)`
    SELECT AVG((c->>'productivity')::numeric) AS baseline
    FROM forecasts, jsonb_array_elements(similar_cases) c
    WHERE company = ${company} AND l6_main = ${l6_main}
  `) as Array<{ baseline: number | null }>;
  return Number(fb[0]?.baseline ?? 0);
}

// ──────────────────────────────────────────────
// G22: WBS 4 레벨 트리 (site → wa → l5_disc → l6_main)
// ──────────────────────────────────────────────
export async function wbsTreeBuild(siteId: string): Promise<WBSNode> {
  const rows = (await (sql as any)`
    SELECT
      am.site_id, am.wa, am.l5_disc, am.l6_main,
      COUNT(*) FILTER (WHERE ma.requires_review) AS review_count,
      MIN(CASE f.risk_level WHEN '이상' THEN 1 WHEN '주의' THEN 2 ELSE 3 END) AS worst_risk
    FROM activity_master am
    LEFT JOIN mapper_activities ma USING (wa)
    LEFT JOIN forecasts f USING (run_id, l6_main, company)
    WHERE am.site_id = ${siteId}
    GROUP BY am.site_id, am.wa, am.l5_disc, am.l6_main
  `) as Array<{
    wa: string;
    l5_disc: string;
    l6_main: string;
    review_count: number | string;
    worst_risk: number | null;
  }>;

  const root: WBSNode = {
    id: siteId,
    type: "building",
    name: siteId,
    parent_id: null,
    review_count: 0,
    status: "normal",
    children: [],
  };
  const waMap = new Map<string, WBSNode>();
  const discMap = new Map<string, WBSNode>();

  const riskToStatus = (worst: number | null): Status => {
    if (worst === 1) return "risk";
    if (worst === 2) return "caution";
    if (worst === 3) return "normal";
    return "unknown";
  };

  for (const r of rows) {
    const reviewCount = Number(r.review_count);

    let waNode = waMap.get(r.wa);
    if (!waNode) {
      waNode = {
        id: r.wa,
        type: "trade",
        name: r.wa,
        parent_id: root.id,
        review_count: 0,
        status: "normal",
        children: [],
      };
      waMap.set(r.wa, waNode);
      root.children!.push(waNode);
    }

    const discKey = `${r.wa}::${r.l5_disc}`;
    let discNode = discMap.get(discKey);
    if (!discNode) {
      discNode = {
        id: discKey,
        type: "trade",
        name: r.l5_disc,
        parent_id: waNode.id,
        review_count: 0,
        status: "normal",
        children: [],
      };
      discMap.set(discKey, discNode);
      waNode.children!.push(discNode);
    }

    const l6Node: WBSNode = {
      id: `${discKey}::${r.l6_main}`,
      type: "work_package",
      name: r.l6_main,
      parent_id: discNode.id,
      review_count: reviewCount,
      status: riskToStatus(r.worst_risk),
      children: [],
    };
    discNode.children!.push(l6Node);
    discNode.review_count += reviewCount;
    waNode.review_count += reviewCount;
    root.review_count += reviewCount;
  }

  return root;
}

// ──────────────────────────────────────────────
// G4: 파이프라인 run → Agent 자연어 메시지 시퀀스
// ──────────────────────────────────────────────
export async function deriveChatSequence(runId: string): Promise<ChatMessage[]> {
  const stats = (await (sql as any)`
    SELECT
      pr.started_at, pr.status,
      (SELECT COUNT(*) FROM parser_activities WHERE run_id = pr.run_id) AS parser_count,
      (SELECT COUNT(*) FROM mapper_activities WHERE run_id = pr.run_id) AS mapper_count,
      (SELECT COUNT(*) FROM mapper_activities WHERE run_id = pr.run_id AND requires_review) AS hil_count,
      pr.atomized_count,
      (SELECT COUNT(*) FROM daily_reports WHERE run_id = pr.run_id) AS reporter_count,
      (SELECT COUNT(*) FROM forecasts WHERE run_id = pr.run_id) AS forecast_count,
      (SELECT COUNT(*) FROM forecasts WHERE run_id = pr.run_id AND risk_level <> '정상') AS abnormal_count,
      (SELECT COUNT(*) FROM optimizer_advice WHERE run_id = pr.run_id) AS optimizer_count
    FROM pipeline_runs pr WHERE pr.run_id = ${runId}
  `) as Array<Record<string, unknown>>;

  if (!stats || stats.length === 0) return [];

  const s = stats[0];
  const startedRaw = s.started_at as Date | string;
  const base = startedRaw instanceof Date ? startedRaw : new Date(startedRaw);
  const off = (sec: number) =>
    new Date(base.getTime() + sec * 1000).toISOString().slice(11, 19);

  const n = (k: string) => Number(s[k] ?? 0);
  const parserCount = n("parser_count");
  const mapperCount = n("mapper_count");
  const hilCount = n("hil_count");
  const atomized = n("atomized_count");
  const reporter = n("reporter_count");
  const forecastCount = n("forecast_count");
  const abnormal = n("abnormal_count");
  const optimizer = n("optimizer_count");

  return [
    {
      ts: off(0),
      agent: "Collector",
      type: "info",
      summary: "1건의 통합 작업일보 수신 완료.",
    },
    {
      ts: off(30),
      agent: "Parser",
      type: "info",
      summary: `${parserCount}건의 활동 구조화 완료.`,
    },
    {
      ts: off(60),
      agent: "Mapper",
      type: hilCount > 0 ? "hil_request" : "info",
      summary: `WBS 매핑 ${mapperCount}건 완료. ${
        hilCount > 0 ? `${hilCount}건 확신도 낮아 검토 필요.` : "전건 자동 매핑."
      }`,
    },
    {
      ts: off(90),
      agent: "HIL Review",
      type: hilCount > 0 ? "human_action" : "info",
      summary: hilCount > 0 ? `${hilCount}건 검토 대기.` : "HIL 검토 없음.",
    },
    {
      ts: off(120),
      agent: "Atomizer",
      type: "info",
      summary: `Vector DB 적재 ${atomized}건 완료.`,
    },
    {
      ts: off(150),
      agent: "Exporter",
      type: "info",
      summary: `통합 작업일보 ${reporter}건 출력.`,
    },
    {
      ts: off(180),
      agent: "Forecaster",
      type: abnormal > 0 ? "result" : "info",
      summary: `생산성 진단 ${forecastCount}건. 이상/주의 ${abnormal}건.`,
    },
    {
      ts: off(210),
      agent: "Optimizer",
      type: "info",
      summary: `회복 조언 ${optimizer}건 생성.`,
    },
  ];
}
