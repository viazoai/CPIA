import { KpiStrip, type KpiItem } from "../reports/KpiStrip";
import { SiteOverviewCard } from "./SiteOverviewCard";
import type { Site } from "@/lib/types";

interface Props {
  sites: Site[];
  fleetKpi: { avg_productivity: number; avg_delay: number; abnormal_total: number; recoverable_days: number };
}

export function PerformanceTab({ sites, fleetKpi }: Props) {
  const kpi: KpiItem[] = [
    { label: "전사 평균 생산성", value: `${fleetKpi.avg_productivity}`, unit: "%", sub: "이력 대비 평균", tone: "mint" },
    { label: "평균 공기 격차", value: `+${fleetKpi.avg_delay}`, unit: "일", sub: "전사 평균 지연", tone: "rose" },
    { label: "이상 공종 총합", value: `${fleetKpi.abnormal_total}`, unit: "건", sub: "전사 합계", tone: "rose" },
    { label: "회복 가능 공기", value: `-${fleetKpi.recoverable_days}`, unit: "일", sub: "Optimizer 평균", tone: "lavender" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <KpiStrip items={kpi} />
      <div>
        <div className="mb-3 flex items-baseline gap-2">
          <h3 className="font-display text-base font-bold text-ink">현장별 진척 · 상태</h3>
          <span className="font-mono text-[10px] uppercase tracking-widest text-ink-light">{sites.length} sites</span>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {sites.map((s) => <SiteOverviewCard key={s.id} site={s} />)}
        </div>
      </div>
    </div>
  );
}
