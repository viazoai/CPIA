import { KpiStrip, type KpiItem } from "../reports/KpiStrip";
import { HorizontalBarList } from "./HorizontalBarList";
import { TrendLineChart } from "../charts/TrendLineChart";
import type { SitesSummary, ImpactSiteDistribution, ImpactTrendPoint, MiddleOfficeAutomation } from "@/lib/types";

interface Props {
  summary: SitesSummary;
  distribution: ImpactSiteDistribution[];
  trend: ImpactTrendPoint[];
  perFunction?: MiddleOfficeAutomation[];
  scope: "fleet" | "site";
}

export function ImpactTab({ summary, distribution, trend, perFunction, scope }: Props) {
  const kpi: KpiItem[] = scope === "fleet" ? [
    { label: "전체 근무량",  value: `${summary.total_headcount}명`, sub: `${summary.total_hours.toLocaleString()} h/월`, tone: "muted" },
    { label: "월 절감 시간", value: `${summary.total_hours_saved.toLocaleString()}`, unit: "h", sub: "Agent 자동화 효과", tone: "primary" },
    { label: "FTE 환산",     value: `${summary.total_fte_saved}`, unit: "명", sub: "140h/명 기준", tone: "normal" },
    { label: "AI 업무 대체율", value: `${summary.ai_replacement_rate}`, unit: "%", sub: "절감 ÷ 전체 근무시간", tone: "muted" },
  ] : [
    { label: "현장 근무량",  value: `${summary.total_headcount}명`, sub: `${summary.total_hours.toLocaleString()} h/월`, tone: "muted" },
    { label: "월 절감 시간", value: `${summary.total_hours_saved.toLocaleString()}`, unit: "h", sub: "이 현장 Agent 효과", tone: "primary" },
    { label: "FTE 환산",     value: `${summary.total_fte_saved}`, unit: "명", sub: "140h/명 기준", tone: "normal" },
    { label: "AI 업무 대체율", value: `${summary.ai_replacement_rate}`, unit: "%", sub: "이 현장 대체율", tone: "muted" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <KpiStrip items={kpi} />

      {scope === "fleet" && (
        <div className="rounded-card border-2 border-mint/30 bg-mint-light/20 px-5 py-3">
          <span className="text-sm">
            <b className="text-mint-text">★ 연간 환산 효과:</b>{" "}
            충원 비용 절감 약 <b className="text-ink">{summary.yearly_saving}억</b>
            <span className="text-ink-mid"> ({summary.total_fte_saved}명 × 1.5억 + 직접 시간 환산)</span>
          </span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {scope === "fleet" ? (
          <HorizontalBarList
            title="현장별 절감 분포"
            unit=" h"
            items={distribution.map((d) => ({ label: d.site_name, value: d.hours_saved, meta: `FTE ${d.fte_saved}` }))}
          />
        ) : perFunction ? (
          <HorizontalBarList
            title="Middle Office 4기능별 자동화율"
            unit="%"
            items={perFunction.map((f) => ({ label: f.function, value: f.rate, meta: `${f.before_hours}h → ${f.after_hours}h` }))}
          />
        ) : null}

        <TrendLineChart
          title={scope === "fleet" ? "월별 누적 FTE 환산" : "도입 후 자동화율 추세"}
          unit={scope === "fleet" ? "명" : "%"}
          valueLabel={scope === "fleet" ? "누적 FTE" : "자동화율"}
          points={trend.map((t) => ({ month: t.month, value: t.cumulative_fte }))}
        />
      </div>
    </div>
  );
}
