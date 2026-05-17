"use client";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceDot,
  CartesianGrid,
} from "recharts";
import type { ProductivityDiagnosis } from "@/lib/types";
import { ConfidenceBadge } from "../reports/ConfidenceBadge";
import { ScenarioLegend } from "./ScenarioLegend";

interface Props {
  diagnosis: ProductivityDiagnosis;
}

export function SpiBandChart({ diagnosis }: Props) {
  const data = diagnosis.s_curve.map((p, i) => ({
    date: p.date,
    planned: p.planned,
    actual: p.actual,
    band_low:  diagnosis.band_p25[i],
    band_high: diagnosis.band_p75[i],
    ewma:      diagnosis.ewma_trend[i],
    base:      diagnosis.scenarios.base.curve[i],
    optimistic:  diagnosis.scenarios.optimistic.curve[i],
    pessimistic: diagnosis.scenarios.pessimistic.curve[i],
  }));

  const firstUndef = data.findIndex((d) => d.actual === undefined);
  const lastIdx = firstUndef === -1 ? data.length - 1 : firstUndef - 1;
  const lastPoint = lastIdx >= 0 ? data[lastIdx] : null;

  return (
    <div className="rounded-card border border-border-soft bg-card p-5 shadow-xs">
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <div className="font-display text-h6 text-ink">SPI Band Chart</div>
          <div className="text-body-sm text-ink-mid">
            볼린저 ±1.5σ 음영 + 시나리오 3종 + EWMA 추세
          </div>
        </div>
        <ConfidenceBadge sampleSize={diagnosis.sample_size} />
      </div>

      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={data} margin={{ top: 12, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#eef0f4" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#7a8494" }}
            tickFormatter={(v: string) => v.slice(5)}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 10, fill: "#7a8494" }}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
            labelFormatter={(v) => String(v)}
          />

          {/* 볼린저 음영 (P25-P75) */}
          <Area dataKey="band_high" stroke="none" fill="#e8eeff" fillOpacity={0.4} activeDot={false} isAnimationActive={false} />
          <Area dataKey="band_low"  stroke="none" fill="#ffffff" fillOpacity={1}   activeDot={false} isAnimationActive={false} />

          {/* 시나리오 3선 */}
          <Line dataKey="optimistic"  stroke="#0ea76a" strokeWidth={2}   strokeDasharray="4 3" dot={false} isAnimationActive={false} />
          <Line dataKey="base"        stroke="#1a56db" strokeWidth={2.5} dot={false} isAnimationActive={false} />
          <Line dataKey="pessimistic" stroke="#ef4444" strokeWidth={2}   strokeDasharray="4 3" dot={false} isAnimationActive={false} />

          {/* EWMA 추세선 */}
          <Line dataKey="ewma" stroke="#444e5e" strokeWidth={1.5} strokeDasharray="2 2" dot={false} isAnimationActive={false} />

          {/* 오늘 실적 점 */}
          {lastPoint && lastPoint.actual !== undefined && (
            <ReferenceDot
              x={lastPoint.date}
              y={lastPoint.actual}
              r={5}
              fill="#0d1117"
              stroke="#1a56db"
              strokeWidth={2}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>

      <div className="mt-3">
        <ScenarioLegend />
      </div>
    </div>
  );
}
