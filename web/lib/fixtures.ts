import { promises as fs } from "fs";
import path from "path";
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

export interface ReportDetail {
  kpi: ReportKpi;
  s_curve: SCurvePoint[];
  contractor_bars: BarItem[];
  trade_bars: BarItem[];
  quadrant: QuadrantPoint[];
  optimizer: OptimizerOutput;
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
