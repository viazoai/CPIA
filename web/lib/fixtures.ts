import { promises as fs } from "fs";
import path from "path";
import sql from "./pg";
import { deriveChatSequence } from "./transforms";
import type {
  Site, SitesSummary, AgentStatus, DailyRun, AgentProgress, ChatMessage,
  WBSNode, ReviewItem, ReportDaily, ReportKpi, SCurvePoint, BarItem,
  QuadrantPoint, OptimizerOutput, RawDataRow, WPSummaryRow,
  ImpactSiteDistribution, ImpactTrendPoint, MiddleOfficeAutomation,
  SimulationSequence, FleetTrendPoint,
} from "./types";

/**
 * Map of fixture name → expected return type.
 * Phase 2 전환 시 이 매핑을 그대로 두고 fetch 레이어만 swap.
 */
type FixtureMap = {
  sites: Site[];
  sites_summary: SitesSummary;
  agent_status: AgentStatus[];
  agent_tasks: { daily_runs: DailyRun[]; progress_by_date: Record<string, AgentProgress[]> };
  chat_sequence: Record<string, ChatMessage[]>; // keyed by date
  review_cards: ReviewItem[];
  wbs_tree: WBSNode;
  report: { daily: ReportDaily[]; details: Record<string, ReportDetail> };
  dashboard: DashboardFixture;
  simulation: SimulationSequence;
};

export type Scenario = {
  expected_completion: string | null;
  recovery_days: number;
  delta_days: number;
  case_count: number;
};

export type ScenarioSet = {
  no_action: Scenario;
  optimistic_p25: Scenario;
  base_p50: Scenario;
  pessimistic_p75: Scenario;
};

export type OptimizerByWp = {
  by_wp: Record<string, OptimizerOutput>;
  default_wp_id: string | null;
};

export interface ReportDetail {
  kpi: ReportKpi;
  s_curve: SCurvePoint[];
  contractor_bars: BarItem[];
  trade_bars: BarItem[];
  quadrant: QuadrantPoint[];
  optimizer: OptimizerByWp;
  scenarios?: {
    site?: Partial<ScenarioSet>;
    by_wp?: Record<string, ScenarioSet>;
  };
  /** BE Optimizer LLM 산출 site 수준 narrative (없을 수 있음 — 룰베이스 fallback). */
  site_summary_text?: string | null;
  raw_data: RawDataRow[];
  wp_summary: WPSummaryRow[];
}

export interface DashboardFixture {
  performance: {
    fleet_kpi: {
      avg_productivity: number;
      avg_delay: number;
      abnormal_total: number;
      recoverable_days: number;
    };
    /** 시연 안정성: fixture 가 비어있으면 컴포넌트가 mulberry32 로 deterministic 생성. */
    fleet_trend?: FleetTrendPoint[];
    site_sparklines?: Record<string, number[]>;
  };
  impact: {
    fleet_kpi: SitesSummary;
    site_distribution: ImpactSiteDistribution[];
    monthly_trend: ImpactTrendPoint[];
    per_site_automation: Record<string, MiddleOfficeAutomation[]>;
  };
}

const DATA_DIR = path.join(process.cwd(), "..", "data");

export async function loadFixture<K extends keyof FixtureMap>(name: K): Promise<FixtureMap[K]> {
  const file = path.join(DATA_DIR, `mock_${name}.json`);
  const raw = await fs.readFile(file, "utf-8");
  return JSON.parse(raw) as FixtureMap[K];
}

/**
 * Home 페이지용 PG 실 데이터 로더 (Task 5.1).
 * loadFixture 와 동일한 시그니처를 따르되, mock JSON 대신 PG SELECT 결과를 반환.
 * 다른 페이지는 loadFixture 를 계속 사용.
 */
export async function loadReal(name: "sites_summary"): Promise<SitesSummary>;
export async function loadReal(name: "agent_status"): Promise<AgentStatus[]>;
export async function loadReal(name: "chat_sequence"): Promise<Record<string, ChatMessage[]>>;
export async function loadReal(name: "dashboard_performance"): Promise<DashboardFixture["performance"]>;
export async function loadReal(name: string): Promise<unknown> {
  switch (name) {
    case "sites_summary": {
      const useMock = process.env.CPIA_DEMO_FALLBACK === "on";

      const [agg] = (await (sql as any)`
        SELECT
          COALESCE(SUM(atomized_count), 0) AS total_processed,
          MAX(started_at) AS last_started
        FROM pipeline_runs
        WHERE is_mock = ${useMock}
      `) as Array<{ total_processed: string | number; last_started: Date | string | null }>;

      const [today] = (await (sql as any)`
        SELECT COALESCE(atomized_count, 0) AS today_count
        FROM pipeline_runs
        WHERE status = 'completed'
          AND is_mock = ${useMock}
        ORDER BY started_at DESC
        LIMIT 1
      `) as Array<{ today_count: string | number }>;

      const [siteAgg] = (await (sql as any)`
        SELECT
          COALESCE(SUM(hours_saved), 0) AS total_hours_saved,
          COALESCE(SUM(fte_saved), 0) AS total_fte_saved,
          COALESCE(SUM(hours_saved_cum), 0) AS total_hours_saved_cum,
          COALESCE(SUM(headcount), 0) AS total_headcount
        FROM sites
        WHERE is_mock = ${useMock}
      `) as Array<Record<string, string | number>>;

      const [review] = (await (sql as any)`
        SELECT COUNT(*) AS review_pending
        FROM mapper_activities ma
        WHERE ma.requires_review = true
          AND ma.is_mock = ${useMock}
          AND ma.trade IN ('건축', '토목')
          AND ma.today_qty > 0
      `) as Array<{ review_pending: string | number }>;

      const [abnormal] = (await (sql as any)`
        SELECT COUNT(*) AS abnormal_count
        FROM forecasts
        WHERE risk_level <> '정상'
          AND is_mock = ${useMock}
      `) as Array<{ abnormal_count: string | number }>;

      const lastStarted = agg?.last_started ?? null;
      const lastUpdated = lastStarted
        ? (lastStarted instanceof Date ? lastStarted : new Date(lastStarted))
            .toISOString()
            .slice(11, 16)
        : "—";

      const totalHours = Number(siteAgg?.total_headcount ?? 0) * 140;
      const hoursSaved = Number(siteAgg?.total_hours_saved ?? 0);
      const aiRate = totalHours > 0 ? Math.round((hoursSaved / totalHours) * 10000) / 100 : 0;

      return {
        today_count: Number(today?.today_count ?? 0),
        review_pending: Number(review?.review_pending ?? 0),
        abnormal_count: Number(abnormal?.abnormal_count ?? 0),
        last_updated: lastUpdated,
        total_hours_saved: hoursSaved,
        total_fte_saved: Number(siteAgg?.total_fte_saved ?? 0),
        total_headcount: Number(siteAgg?.total_headcount ?? 0),
        total_hours: totalHours,
        ai_replacement_rate: aiRate,
        yearly_saving: 0,
        total_processed: Number(agg?.total_processed ?? 0),
        total_hours_saved_cum: Number(siteAgg?.total_hours_saved_cum ?? 0),
      } as SitesSummary;
    }

    case "agent_status": {
      const useMock = process.env.CPIA_DEMO_FALLBACK === "on";
      const AGENT_META: Array<Omit<AgentStatus, "active_count" | "state">> = [
        { step: 1, name: "Collector",  korean_name: "수집", description: "작업일보 자동 수집",      model: "규칙 기반",     group: "collect" },
        { step: 2, name: "Parser",     korean_name: "파싱", description: "엑셀 → 구조화 JSON",       model: "gpt-5.1",       group: "collect" },
        { step: 3, name: "Mapper",     korean_name: "매핑", description: "WBS 매핑 + 확신도 산출",   model: "gpt-5.1 + RAG", group: "collect" },
        { step: 4, name: "Atomizer",   korean_name: "적재", description: "Vector DB 적재",           model: "임베딩 모델",   group: "analyze" },
        { step: 5, name: "Exporter",   korean_name: "출력", description: "통합 작업일보 생성",       model: "gpt-5.1",       group: "analyze" },
        { step: 6, name: "Forecaster", korean_name: "진단", description: "생산성 진단",              model: "Sonnet 4.6",    group: "analyze" },
        { step: 7, name: "Optimizer",  korean_name: "조언", description: "회복 조언",                model: "Opus 4.7",      group: "analyze" },
      ];

      const counts = (await (sql as any)`
        SELECT current_node, COUNT(*) AS n
        FROM pipeline_runs
        WHERE status = 'running'
          AND is_mock = ${useMock}
        GROUP BY current_node
      `) as Array<{ current_node: string | null; n: string | number }>;

      const activeMap: Record<string, number> = {};
      for (const r of counts) {
        if (r.current_node) activeMap[String(r.current_node).toLowerCase()] = Number(r.n);
      }
      // pipeline_runs.current_node 의 'reporter' 는 web 의 Exporter agent 와 동일.
      if (activeMap.reporter !== undefined) {
        activeMap.exporter = (activeMap.exporter ?? 0) + activeMap.reporter;
      }

      return AGENT_META.map((a) => {
        const n = activeMap[a.name.toLowerCase()] ?? 0;
        return {
          ...a,
          active_count: n,
          state: n > 0 ? "processing" : "idle",
        } as AgentStatus;
      });
    }

    case "chat_sequence": {
      const useMock = process.env.CPIA_DEMO_FALLBACK === "on";
      const [latest] = (await (sql as any)`
        SELECT run_id, report_date
        FROM pipeline_runs
        WHERE status = 'completed'
          AND is_mock = ${useMock}
        ORDER BY started_at DESC
        LIMIT 1
      `) as Array<{ run_id: string; report_date: Date | string }>;

      if (!latest) return {} as Record<string, ChatMessage[]>;

      const messages = await deriveChatSequence(latest.run_id);
      const dStr = typeof latest.report_date === "string"
        ? latest.report_date.slice(0, 10)
        : latest.report_date.toISOString().slice(0, 10);
      return { [dStr]: messages };
    }

    case "dashboard_performance": {
      const useMock = process.env.CPIA_DEMO_FALLBACK === "on";
      // fleet_kpi — 530일 daily_reports 의 kpi_jsonb 평균/카운트.
      // fleet 평균/일평균 의미. 누적 합 X (530일 × N 개 합산은 비현실적 표시).
      const [agg] = (await (sql as any)`
        SELECT
          (SELECT ROUND(COALESCE(AVG((dr.kpi_jsonb->>'productivity_today')::numeric), 0), 1)::float
            FROM daily_reports dr WHERE dr.is_mock = ${useMock})                              AS avg_productivity,
          (SELECT ROUND(COALESCE(AVG(f.delay_days), 0)::numeric, 1)::float
            FROM forecasts f WHERE f.is_mock = ${useMock})                                    AS avg_delay,
          (SELECT ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT pr.report_date), 0), 1)::float
            FROM forecasts f JOIN pipeline_runs pr USING (run_id)
            WHERE f.is_mock = ${useMock} AND f.risk_level <> '정상')                          AS abnormal_total,
          (SELECT ROUND(COALESCE(AVG(CASE WHEN f.delay_days > 0 THEN f.delay_days ELSE 0 END), 0)::numeric, 1)::float
            FROM forecasts f WHERE f.is_mock = ${useMock})                                    AS recoverable_days
      `) as Array<{ avg_productivity: number; avg_delay: number; abnormal_total: number; recoverable_days: number }>;

      // fleet_trend — 최근 60일 (mean = 평균 productivity, min/max 는 실 site 1개라 동일 값으로 placeholder).
      const trendRows = (await (sql as any)`
        SELECT pr.report_date,
               (dr.kpi_jsonb->>'productivity_today')::numeric AS productivity
        FROM daily_reports dr JOIN pipeline_runs pr USING (run_id)
        WHERE dr.is_mock = ${useMock}
        ORDER BY pr.report_date DESC LIMIT 60
      `) as Array<{ report_date: Date | string; productivity: number }>;
      const fleet_trend = trendRows
        .reverse()
        .map((r) => {
          const v = Number(r.productivity ?? 0);
          const dateStr = r.report_date instanceof Date
            ? r.report_date.toISOString().slice(0, 10)
            : String(r.report_date).slice(0, 10);
          return { date: dateStr, mean: v, min: v, max: v };
        });

      // site_sparklines — m15x-ph3-ibl 최근 30일.
      const sparkRows = (await (sql as any)`
        SELECT pr.report_date,
               (dr.kpi_jsonb->>'productivity_today')::numeric AS productivity
        FROM daily_reports dr JOIN pipeline_runs pr USING (run_id)
        WHERE dr.is_mock = ${useMock}
          AND pr.site_id = 'm15x-ph3-ibl'
        ORDER BY pr.report_date DESC LIMIT 30
      `) as Array<{ report_date: Date | string; productivity: number }>;
      const sparkValues = sparkRows.reverse().map((r) => Number(r.productivity ?? 0));

      return {
        fleet_kpi: agg ?? {
          avg_productivity: 0, avg_delay: 0, abnormal_total: 0, recoverable_days: 0,
        },
        fleet_trend,
        site_sparklines: { "m15x-ph3-ibl": sparkValues },
      };
    }

    default:
      throw new Error(`loadReal: unknown name ${name}`);
  }
}
