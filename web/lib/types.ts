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
  is_mock?: boolean;             // true = 데이터 미적재, 회색 + preview 배지
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
  total_hours_saved: number;    // 2155 (월간)
  total_fte_saved: number;      // 15.4
  total_headcount: number;      // 480
  total_hours: number;          // 67200
  ai_replacement_rate: number;  // 3.2
  yearly_saving: number;        // 203 (억)
  total_processed: number;          // 누적 처리 건수 (런칭 이후) — 1247
  total_hours_saved_cum: number;    // 누적 절감 시간 (런칭 이후) — 12840
}

// ────── 7-Agent 카드 status (Home) ──────
export interface AgentStatus {
  step: number;                 // 1..7
  name: string;                 // "Collector"
  korean_name: string;          // "수집"
  description: string;          // "작업일보 자동 수집"
  model: string;                // "규칙 기반" | "Sonnet 4.6" | "Opus 4.7" | "임베딩 모델"
  group: "collect" | "analyze"; // sky | brand
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
  agent: string;                // "Collector" | "Parser" | "Mapper" | "Human Review" | "Atomizer" | "Exporter" | "Forecaster" | "Optimizer"
  unit: "per_report" | "per_review" | "per_run";
  processed: number;
  total: number;
  waiting_hil: boolean;
}

// ────── Daily Tasks (rebuilt) ──────
export interface DailyTask {
  date: string;                 // "2026-05-15"
  total_count: number;          // 작업일보 건수
  progress_percent: number;     // 0..100 — 파이프라인 전체 진행률
  status: "running" | "completed" | "review_pending";
  has_anomaly: boolean;
}

export interface AgentStageProgress {
  step: number;                 // 1..7 + HIL은 3.5
  agent: string;                // "Collector" ... "Optimizer" | "Human Review"
  is_hil: boolean;
  received: number;             // 접수 건수
  processed: number;            // 처리 건수
  percent: number;              // 0..100
  waiting_hil: boolean;
}

export interface AgentTaskItem {
  id: string;                   // "RPT-20260515-001"
  trade: string;                // "철근공사"
  contractor: string;           // "(주)A건설"
  status: "done" | "processing" | "received" | "hil_pending" | "blocked";
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
  review_count: number;         // 검토 필요(미확정) 건수 — 집계
  total_count: number;          // 총 작업(매핑 활동) 건수 — 집계
  status: Status;
  children?: WBSNode[];
  wa?: string;                  // work_package 노드의 원 wa (remap 역매핑용)
  l6_main?: string;             // work_package 노드의 원 l6_main (remap 역매핑용)
}

export interface ReviewItem {
  id: string;
  idx: number;                  // mapper_activities.idx — BE corrections key (= mapped 리스트 위치)
  bp_name: string;              // "A건설"
  work_content: string;         // 작업내용 원문
  quantity: number;
  unit: string;                 // "㎡" | "ton" | "m³" | "EA"
  ai_mapped_wp_id: string;      // 매핑된 WP id (remap 시 갱신)
  ai_mapped_path: string;       // "M15X > 골조 > WP-3-2 거푸집"
  wa: string | null;            // 현재 매핑 wa (remap 시 갱신) — resume corrections 전달용
  l6_main: string | null;       // 현재 매핑 l6_main (remap 시 갱신)
  confidence: number;           // 0.0~1.0
  status: "confirmed" | "unconfirmed";
  remapped?: boolean;           // 사용자가 AI 추천과 다르게 수정했는지 (corrections 전송 대상)
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
  productivity_today_simple_mean?: number; // Phase 1 — wv-median 외 simple mean 병렬
  productivity_today_perperson?: number;   // 인당 원본값 (예: 3.2)
  productivity_today_unit?: string;        // 단위 (예: "ton/인")
  productivity_today_display?: string;     // 합본 라벨 (예: "98.9% (3.2 ton/인)")
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
  baseline?: number;        // 자체 기준값 (이력 평균 등). showBaseline 시 Line 시리즈 dot 으로 표시.
  display_label?: string;   // Phase 1 (2026-05-21) BE 산출 — 예: "98.9% (3.20 ton/인)"
  perperson?: number;       // 인당 원본값 (예: 3.20)
  perperson_unit?: string;  // 단위 (예: "ton/인")
}

export interface QuadrantPoint {
  wp_id: string;
  wp_name: string;
  trade: string;
  productivity: number;     // 0..100 (X축)
  impact: number;           // 0..100 (Y축)
  quadrant: "risk" | "caution" | "watch" | "safe";  // cpi×impact 4분면 (점 위치)
  // 2026-05-29 SSOT: 점 색은 status (forecaster risk_level) 기준 — 목록·카드와 통일.
  status?: "risk" | "caution" | "normal";
  risk_level?: string | null;
  size: number;             // 잔여 물량 비례
  display_label?: string;
  perperson?: number;
  perperson_unit?: string;
  units_detail?: UnitDetail[];  // 2026-05-29 Task 4.3: 혼재 WP 단위별 분리 (m³/인·ton/인)
}

// 2026-05-29 Task 4.3: 혼재 WP 의 단위별 생산성 detail (group 내부 unit 별 집계).
export interface UnitDetail {
  unit: string | null;
  perperson: number;
  productivity: number;
  plan_mh: number;
}

// 권고사항 schema — V10 BE 가 string → {keyword, action, reason} 객체로 변경.
// FE 는 두 schema 모두 렌더 (옛 string 형식 backwards-compat).
export type OptimizerRecommendation =
  | string
  | {
      rank?: number;
      keyword: string;
      action: string;
      reason: string;
    };

export interface SimilarCase {
  date: string;
  condition?: string;        // 조건 태그 (인력부족/자재미입고…)
  degraded?: string;         // 저하일 work_content
  recovered?: string;        // 회복일(D+1) work_content
  recovery_days?: number | null;
  // legacy 호환 (옛 데이터)
  description?: string;
  outcome?: string;
}

export interface OptimizerOutput {
  wp_id: string;
  diagnosis: string;                              // 진단 (개조식 — '\n' 줄바꿈)
  similar_cases: SimilarCase[];
  recovery_distribution_text?: string;            // "5건 중 5건 회복 | D+1 회복 5건" (유사사례 밑)
  recommendations: OptimizerRecommendation[];     // 권고사항 — string (구) 또는 object (V10 신)
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

// ────── /home — 구성원 운영 홈 (단일 현장) ──────
// spec: docs/superpowers/specs/2026-06-01-cpia-home-member-redesign-design.md
export interface HomeWeather {
  /** lucide 아이콘 키 (sun / cloud / cloud-rain …) */
  icon: string;
  label: string;
  temp_c: number;
}

export interface HomeSiteInfo {
  id: string;
  name: string;
  /** 시연 고정 날짜 (YYYY-MM-DD) — report.details 키와 일치 */
  date: string;
  location?: string;
  weather: HomeWeather;
}

/**
 * 협력업체 일보 처리/제출 지표.
 *  - 제출 현황(오늘): expected / submitted / unsubmitted
 *  - Agent 처리 현황(최근 1년 누적): completed_cum / hours_saved_cum (+ 일평균 rate)
 */
export interface HomeProcessing {
  /** 오늘 예정 업체 수 */
  expected: number;
  /** 오늘 제출 업체 수 */
  submitted: number;
  /** 오늘 미제출 업체 수 */
  unsubmitted: number;
  /** 최근 1년 누적 처리완료 건수 */
  completed_cum: number;
  /** 최근 1년 누적 절감 시간(h) — 일평균 절감 × 가동일 */
  hours_saved_cum: number;
  /** 일 평균 절감 시간(h) — 설명용 (M15X 월 ~221h ÷ 가동일 기준) */
  hours_saved_per_day: number;
}

export interface HomeUnsubmittedCompany {
  trade: string;
  name: string;
}

export interface HomeWorkSummary {
  /** Σ raw_data.workers 와 일치 */
  total_workers: number;
  /** 중장비 기준 명시값 (equipment 문자열 파싱 불안정 회피) */
  total_equipment: number;
}

export interface HomeFixture {
  site: HomeSiteInfo;
  user: { name: string };
  processing: HomeProcessing;
  unsubmitted_companies: HomeUnsubmittedCompany[];
  work_summary: HomeWorkSummary;
}

// ────── /reports § 5 — WP 단위 요약 (작업일보 상세의 컨텍스트) ──────
export interface WPSummaryRow {
  wp_id: string;
  wp_name: string;       // "WP-3-2 거푸집"
  trade: string;         // "골조"
  bp_name: string;       // "A건설"
  start_date: string;    // "2026-05-08"
  end_date: string;      // "2026-05-22"
  progress_pct: number;  // 0..100
  productivity: number;  // 0..100 — Quadrant 의 productivity 와 동일 값
  impact: number;        // 0..100 — WV (Work Volume), Quadrant 의 impact 와 동일 값
  baseline: number;      // 이력 평균 (목표 productivity). 회복 폭 = baseline − productivity.
  status: "normal" | "caution" | "risk";
  display_label?: string;
  perperson?: number;
  perperson_unit?: string;
  recovery_days?: number;  // 2026-05-29 BE 단일 source (scenarios.by_wp base_p50). FE 결정론 폐기.
  units_detail?: UnitDetail[];  // 2026-05-29 Task 4.3: 혼재 WP 단위별 분리
}

// ────── Dashboard Fleet Performance ──────
export interface FleetTrendPoint {
  date: string;   // ISO "YYYY-MM-DD"
  mean: number;   // 0..100 — 6 현장 평균 생산성
  min: number;    // 0..100 — 가장 낮은 현장
  max: number;    // 0..100 — 가장 높은 현장
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

// ────── Productivity Diagnosis (Hybrid 모델) ──────
export type DiagStatus = Exclude<Status, "unknown">;

export interface DiagnosisInput {
  site_id: string;            // 결정적 mock 산출 시드
  today_progress: number;     // 오늘 누적 진척률 (%)
  history_mean: number;       // μ — 이력 평균 일진척률 (%)
  history_std: number;        // σ
  sample_size: number;        // N — 유사 과거 케이스 수
  s_curve: SCurvePoint[];     // 기존 시계열 재사용
  // BE scenarios.site 산출값 — 곡선 slope 계산용 (recovery_days_p25/p50/p75, delay_days).
  // 미전달 시 deterministic fallback (이전 동작).
  recovery_days_p25?: number;
  recovery_days_p50?: number;
  recovery_days_p75?: number;
  delay_days?: number;
}

export interface RecoveryEstimate {
  p25: number;
  p50: number;
  p75: number;
}

export interface ScenarioPoint {
  eta_days: number;              // 평균 도달 / 만회 예상 일수 (∞ 허용)
  recovery_pct: number;          // 회복 후 누적 진척률 (%)
  delta_completion_days: number; // 계획 완공일 대비. 음수 = 단축, 양수 = 지연
  curve: (number | null)[];      // 시각화용 시계열 (길이 = s_curve.length). today 이전은 null — 차트에서 선 안 그리도록
  catch_up?: { date: string; percent: number };  // catch-up intersection (plan 따라잡는 시점)
}

// ────── /export — 통합 작업일보 (Exporter agent 산출물) ──────
// 엑셀 4 시트(출력인원 현황 / 직종별 인원현황 / 장비현황 / 물량)를 그대로 매핑.
// 현 PG 스키마(daily_reports) 는 raw 행을 담지 않으므로 B_Track 은 mock fixture 로 진행.
// A_Track 이 staging 테이블 + GET 엔드포인트를 추가하면 fetch URL 만 swap.
export type SheetTab =
  | "output_manpower"
  | "occupation_manpower"
  | "equipment"
  | "quantity";

export interface ConsolidatedReportSummary {
  date: string;                                // YYYY-MM-DD
  pjt: string;                                 // "M15X Ph-3 IBL"
  status: "ready" | "draft";                   // 엑셀 다운로드 가능 여부
  sheet_row_counts: Record<SheetTab, number>;
}

export interface OutputManpowerRow {
  pjt: string;
  zone: string;
  trade: string;
  bp_code: string;
  scope: string;
  main_work: string;
  prev_work: string;
  today_work: string;
  next_work: string;
  early: number;
  day: number;
  overtime: number;
}

export interface OccupationManpowerRow {
  trade: string;
  bp_code: string;
  manager_code: string;
  skilled_code: string;
  occupation: string;
  prev_cum: number;
  early: number;
  day: number;
  overtime: number;
  night: number;
  allnight: number;
  cum_t: number;
}

export interface EquipmentRow {
  trade: string;
  bp_code: string;
  eq_major: string;
  eq_mid: string;
  eq_spec: string;
  prev_cum: number;
  early: number;
  day: number;
  overtime: number;
  night: number;
  allnight: number;
  cum_t: number;
}

export interface QuantityRow {
  zone: string;
  trade: string;
  bp_code: string;
  bp_name: string;
  scope: string;
  rep_work: string;
  unit: string;
  total_a: number;       // 총물량 [A]
  prev_cum_b: number;    // 전일누적 [B]
  today_c: number;       // 금일실적 [C]
}

export interface ConsolidatedReport extends ConsolidatedReportSummary {
  output_manpower: OutputManpowerRow[];
  occupation_manpower: OccupationManpowerRow[];
  equipment: EquipmentRow[];
  quantity: QuantityRow[];
}

export interface ProductivityDiagnosis {
  // 기준선
  history_mean: number;
  history_std: number;
  sample_size: number;

  // 현 상태
  today_progress: number;
  productivity_score: number;   // today / μ × 100
  gap_pct: number;              // productivity − 100
  z_score: number;              // (today − μ) / σ
  status: DiagStatus;

  // 시계열
  s_curve: SCurvePoint[];
  band_p25: number[];           // 볼린저 하단
  band_p75: number[];           // 볼린저 상단
  ewma_trend: number[];         // EWMA

  // 회복·시나리오
  recovery: { p25_days: number; p50_days: number; p75_days: number };
  scenarios: {
    optimistic: ScenarioPoint;
    base: ScenarioPoint;
    pessimistic: ScenarioPoint;
  };
}
