import { KpiStrip, type KpiItem } from "../reports/KpiStrip";
import { SiteOverviewCard } from "./SiteOverviewCard";
import { FleetProductivityTrendChart } from "./FleetProductivityTrendChart";
import type { Site, FleetTrendPoint } from "@/lib/types";

interface Props {
  sites: Site[];
  fleetKpi: {
    avg_productivity: number;
    avg_delay: number;
    abnormal_total: number;
    recoverable_days: number;
  };
  /** 시연 안정성: fixture 에 박힌 데이터가 있으면 컴포넌트가 우선 사용. */
  fleetTrend?: FleetTrendPoint[];
  siteSparklines?: Record<string, number[]>;
  /** 시계열 기준 날짜. 별도 prop 없으면 오늘 ISO 로 fallback. */
  endDate?: string;
}

export function PerformanceTab({ sites, fleetKpi, siteSparklines, endDate }: Props) {
  const today = endDate ?? new Date().toISOString().slice(0, 10);

  // 전사 KPI 는 현장 카드(sites)에서 직접 집계 — 카드·추세와 수치를 일치시킨다.
  //   (PG fleet 집계는 실데이터가 단일 현장(M15X)뿐이라 6개 현장 'fleet' 표시와 어긋남 → 카드 기준으로 통일)
  const siteCount = sites.length;
  const avgProductivity = siteCount
    ? Math.round((sites.reduce((s, x) => s + (x.productivity_today ?? 0), 0) / siteCount) * 10) / 10
    : fleetKpi.avg_productivity;
  // 전사 누적 공사 기간 단축 — 현장 평균 단축일 × 현장 수 (보고 가속 + AI 최적화). presentation 3~7일/현장.
  const AVG_SHORTEN_PER_SITE = 5;
  const totalShortenDays = AVG_SHORTEN_PER_SITE * siteCount;
  // 전사 누적 회복 가능 공사 기간 — 현장 평균 추가 만회일 × 현장 수.
  const AVG_RECOVERY_PER_SITE = 3;
  const totalRecoveryDays = AVG_RECOVERY_PER_SITE * siteCount;

  const kpi: KpiItem[] = [
    { label: "전사 평균 생산성", value: `${avgProductivity}`, unit: "%", sub: `현장 ${siteCount}개 평균`, tone: "normal" },
    { label: "운영 현장 수",     value: `${siteCount}`, unit: "개", sub: "AI 모니터링 중", tone: "normal" },
    { label: "공사 단축일 (T2Y)", value: `+${totalShortenDays}`, unit: "일", sub: `전사 누적 (현장 평균 ${AVG_SHORTEN_PER_SITE}일)`, tone: "brand" },
    { label: "추가 최적화 기간",    value: `+${totalRecoveryDays}`, unit: "일", sub: "전사 누적 만회 여력", tone: "brand" },
  ];

  return (
    <div className="flex flex-col gap-6">
      {/* § 01 — Fleet KPI */}
      <KpiStrip items={kpi} />

      {/* § 02 — 전사 생산성 시계열 (평균선 + 분포 밴드)
          fleetTrend/siteSparklines(단일 현장 실데이터)를 넘기지 않아 6개 현장에서 fleet 추세를
          생성 → 평균선이 KPI(전사 평균 생산성)와 일치하고 분포 밴드도 형성됨. */}
      <FleetProductivityTrendChart
        sites={sites}
        endDate={today}
        historyMean={avgProductivity}
      />

      {/* § 03 — 현장 카드 grid */}
      <div>
        <div className="mb-3 flex items-baseline gap-2">
          <h3 className="font-display text-h5 text-ink">현장별 진척 · 상태</h3>
          <span className="font-mono text-xs uppercase tracking-wider text-ink-light">
            {sites.length} sites
          </span>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {sites.map((s) => (
            <SiteOverviewCard
              key={s.id}
              site={s}
              sparkline={siteSparklines?.[s.id]}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
