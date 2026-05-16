import { SCurveChart } from "../charts/SCurveChart";
import { BarChartH } from "../charts/BarChartH";
import type { ReportDetail } from "@/lib/fixtures";

export function ForecastTab({ detail }: { detail: ReportDetail }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-card border border-border-soft bg-card p-5 shadow-xs">
        <div className="flex items-center justify-between mb-3">
          <div className="font-mono text-xs uppercase tracking-wider text-ink-light">S-Curve · 계획 vs 실적</div>
          <div className="flex items-center gap-4 text-[11px] text-ink-mid">
            <span><span className="text-ink-light">공정률:</span> <b>{detail.kpi.productivity_today}%</b></span>
            <span><span className="text-ink-light">SPI:</span> <b>{(detail.kpi.productivity_today / 100).toFixed(2)}</b></span>
            <span><span className="text-ink-light">잔여:</span> <b>{100 - detail.kpi.productivity_today}%</b></span>
          </div>
        </div>
        <SCurveChart points={detail.s_curve} showRecovery />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <BarChartH items={detail.contractor_bars} title="업체별 생산성 (오늘 평균)" />
        <BarChartH items={detail.trade_bars} title="공종별 생산성 (오늘 평균)" />
      </div>
    </div>
  );
}
