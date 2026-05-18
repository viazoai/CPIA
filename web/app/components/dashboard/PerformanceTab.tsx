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

export function PerformanceTab({
  sites,
  fleetKpi,
  fleetTrend,
  siteSparklines,
  endDate,
}: Props) {
  const today = endDate ?? new Date().toISOString().slice(0, 10);

  const kpi: KpiItem[] = [
    { label: "전사 평균 생산성", value: `${fleetKpi.avg_productivity}`, unit: "%", sub: "이력 대비 평균", tone: "normal" },
    { label: "평균 공기 격차",   value: `+${fleetKpi.avg_delay}`, unit: "일", sub: "전사 평균 지연", tone: "risk" },
    { label: "이상 공종 총합",   value: `${fleetKpi.abnormal_total}`, unit: "건", sub: "전사 합계", tone: "risk" },
    { label: "회복 가능 공기",   value: `-${fleetKpi.recoverable_days}`, unit: "일", sub: "Optimizer 평균", tone: "primary" },
  ];

  return (
    <div className="flex flex-col gap-6">
      {/* § 01 — Fleet KPI */}
      <KpiStrip items={kpi} />

      {/* § 02 — 전사 생산성 시계열 (평균선 + 분포 밴드) */}
      <FleetProductivityTrendChart
        sites={sites}
        endDate={today}
        historyMean={fleetKpi.avg_productivity}
        fleetTrend={fleetTrend}
        siteSparklines={siteSparklines}
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
