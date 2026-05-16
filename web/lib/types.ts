// web/lib/types.ts
// 모든 5 화면에서 공유하는 도메인 타입.
// fixture JSON 의 shape 과 1:1 매칭. A_Track API 응답 shape 과도 일치.

export type Status = "normal" | "caution" | "risk" | "unknown";
export type Persona = "member" | "manager";

// ────── Sites (Dashboard / Home Hero) ──────
export interface Site {
  id: string;
  name: string;
  location: string;
  status: Status;
  progress_planned: number;     // 계획 공정률 %
  progress_actual: number;      // 실적 공정률 %
  gap_percent: number;          // 격차 %p
  productivity_today: number;   // 오늘 생산성 %
  spi: number;                  // SPI 지수
  abnormal_trades: number;      // 이상 공종 수
  fte_saved: number;            // 확보 FTE
  hours_saved: number;          // 월 절감 시간
  headcount: number;            // 현장 전체 근무 인원 (Impact 분모)
  total_hours: number;          // 현장 전체 근무 h/월 (headcount × 140)
  ai_replacement_rate: number;  // AI 업무 대체율 (hours_saved / total_hours)
  expected_completion: string;  // 현 추세 완료일 ISO date
  recovered_completion: string; // 최적화 후 완료일 ISO date
  delay_days: number;           // 지연 일수
  recovery_days: number;        // 회복 가능 일수
}

// ────── Home NOW strip + Hero ──────
export interface SitesSummary {
  today_count: number;          // 오늘 처리 87건
  review_pending: number;       // Review 대기 2건
  abnormal_count: number;       // 이상 1건
  last_updated: string;         // "09:12"
  total_hours_saved: number;    // 2155
  total_fte_saved: number;      // 15.4
  total_headcount: number;      // 480
  total_hours: number;          // 67200
  ai_replacement_rate: number;  // 3.2
  yearly_saving: number;        // 203 (억)
}

// ────── 7-Agent 카드 status (Home) ──────
export interface AgentStatus {
  step: number;                 // 1..7
  name: string;                 // "Collector"
  korean_name: string;          // "수집"
  description: string;          // "작업일보 자동 수집"
  model: string;                // "규칙 기반" | "Sonnet 4.6" | "Opus 4.7" | "임베딩 모델"
  group: "collect" | "analyze"; // sky | lavender
  active_count: number;         // 시뮬 base 값
  state: "processing" | "waiting" | "idle";
}

// ────── Agent Tasks ──────
export interface DailyRun {
  date: string;                 // "2026-05-15"
  total_count: number;          // 87
  status: "running" | "completed" | "review_pending";
  has_anomaly: boolean;
  bar_value: number;            // 0..1 (mini bar 비율)
}

export interface AgentProgress {
  agent: string;                // "Collector" | "Parser" | "Mapper" | "HIL Review" | "Atomizer" | "Reporter" | "Forecaster" | "Optimizer"
  unit: "per_report" | "per_review" | "per_run";
  processed: number;
  total: number;
  waiting_hil: boolean;
}

export interface ChatMessage {
  ts: string;                   // "09:01:18"
  agent: string;
  type: "info" | "hil_request" | "human_action" | "result";
  summary: string;              // 자연어 1줄
  detail?: string;              // 자연어 보충 2~3줄
}

// ────── Human Review ──────
export interface WBSNode {
  id: string;
  type: "building" | "trade" | "work_package";
  name: string;
  parent_id: string | null;
  review_count: number;         // 검토 필요 건수 (집계)
  status: Status;
  children?: WBSNode[];
}

export interface ReviewItem {
  id: string;
  bp_name: string;              // "A건설"
  work_content: string;         // 작업내용 원문
  quantity: number;
  unit: string;                 // "㎡" | "ton" | "m³" | "EA"
  ai_mapped_wp_id: string;      // 매핑된 WP id
  ai_mapped_path: string;       // "M15X > 골조 > WP-3-2 거푸집"
  confidence: number;           // 0.0~1.0
  status: "confirmed" | "unconfirmed";
  alternative_wps?: { id: string; path: string; score: number }[];
}

// ────── Report ──────
export interface ReportDaily {
  date: string;
  status: Status;
  productivity_today: number;
  delay_days: number;
  recovery_days: number;
}

export interface ReportKpi {
  productivity_today: number;       // 88
  productivity_history_diff: number; // -12 (이력 대비)
  delay_days: number;                // 14
  expected_completion: string;       // 2026-08-12
  recoverable_productivity: number;  // 9 (%p)
  target_productivity: number;       // 97
  recovery_days: number;             // 9
  recovered_completion: string;      // 2026-08-03
}

export interface SCurvePoint {
  date: string;
  planned: number;          // 계획 누적 %
  actual?: number;          // 실적 누적 % (오늘까지)
  forecast?: number;        // 예측선 (오늘 이후)
  recovery?: number;        // 만회선 (Optimizer 시나리오)
}

export interface BarItem {
  label: string;            // BP사명 또는 공종명
  value: number;            // 생산성 %
  status: Status;
}

export interface QuadrantPoint {
  wp_id: string;
  wp_name: string;
  trade: string;
  productivity: number;     // 0..100 (X축)
  impact: number;           // 0..100 (Y축)
  quadrant: "risk" | "caution" | "watch" | "safe";
  size: number;             // 잔여 물량 비례
}

export interface OptimizerOutput {
  wp_id: string;
  diagnosis: string;                              // 진단 (자연어)
  similar_cases: { date: string; description: string; outcome: string }[];
  recommendations: string[];                      // 권고사항 (배열)
  details: { label: string; value: string }[];   // 상세 현황 (key-value)
}

export interface RawDataRow {
  building: string;
  trade: string;
  wp: string;
  bp_name: string;
  work_content: string;
  quantity: number;
  unit: string;
  workers: number;
  equipment: string;
}

// ────── Dashboard Impact ──────
export interface ImpactSiteDistribution {
  site_id: string;
  site_name: string;
  hours_saved: number;
  fte_saved: number;
}

export interface ImpactTrendPoint {
  month: string;       // "2026-01"
  cumulative_fte: number;
}

export interface MiddleOfficeAutomation {
  function: string;     // "Data Stewardship" | "P&L Reporting" | "Risk Management" | "Deal Support"
  rate: number;         // 0..100
  before_hours: number;
  after_hours: number;
}

// ────── Simulation ──────
export interface SimulationSequence {
  home_now_strip: { interval_ms: number; variance: number }[];
  agent_card_status: Record<string, number[]>; // agent name → values array
  chat_log: ChatMessage[];                     // sequenced reveals
}
