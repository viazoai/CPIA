"use client";
import { useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ReferenceDot,
  Label,
  CartesianGrid,
} from "recharts";
import { generateSiteTrend, buildFleetTrend } from "@/lib/fleet-trend-mock";
import type { Site, FleetTrendPoint } from "@/lib/types";

interface Props {
  sites: Site[];
  /** "YYYY-MM-DD" — 시계열 마지막 날짜. */
  endDate: string;
  /** 이력 평균(목표 생산성). ReferenceLine 으로 rose dashed 표시. */
  historyMean: number;
  /** fixture 에 fleet_trend 가 들어있으면 우선 사용. */
  fleetTrend?: FleetTrendPoint[];
  /** fixture 에 site_sparklines 가 들어있으면 평균/min/max 도 거기서 도출. */
  siteSparklines?: Record<string, number[]>;
  daysWindow?: number;
}

export function FleetProductivityTrendChart({
  sites,
  endDate,
  historyMean,
  fleetTrend,
  siteSparklines,
  daysWindow = 90,
}: Props) {
  const data = useMemo<FleetTrendPoint[]>(() => {
    if (fleetTrend && fleetTrend.length > 0) return fleetTrend;
    const perSite = siteSparklines && Object.keys(siteSparklines).length > 0
      ? siteSparklines
      : Object.fromEntries(
          sites.map((s) => [s.id, generateSiteTrend(s.id, s.productivity_today, daysWindow)]),
        );
    return buildFleetTrend(perSite, endDate, daysWindow);
  }, [sites, endDate, fleetTrend, siteSparklines, daysWindow]);

  const todayMean = data.length > 0 ? data[data.length - 1].mean : 0;
  const chartData = data.map((p) => ({ ...p, label: p.date.slice(5) }));

  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="font-display text-base font-semibold text-ink">
            전사 생산성 추세{" "}
            <span className="text-sm font-normal text-ink-mid">({endDate} 기준)</span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-display text-h3 font-semibold tracking-[-0.015em] text-ink">
              {todayMean.toFixed(1)}
            </span>
            <span className="text-base text-ink-light">%</span>
            <span className="ml-1 text-sm text-ink-mid">
              현장 {sites.length}개 평균
            </span>
          </div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={chartData} margin={{ top: 16, right: 32, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#eef0f4" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: "#7a8494" }}
            interval={Math.max(1, Math.floor(chartData.length / 8))}
          />
          <YAxis
            domain={[70, 105]}
            tick={{ fontSize: 10, fill: "#7a8494" }}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
            formatter={(v, key) => [`${v}%`, key === "mean" ? "평균" : key === "max" ? "최고" : "최저"]}
          />
          {/* 분포 밴드: max area 채우고 min area 를 흰색으로 덮어 min~max 영역만 보이게. */}
          <Area dataKey="max" stroke="none" fill="#e8eeff" fillOpacity={0.6} isAnimationActive={false} />
          <Area dataKey="min" stroke="none" fill="#ffffff" fillOpacity={1} isAnimationActive={false} />
          {/* 평균선 */}
          <Line
            dataKey="mean"
            stroke="#1a56db"
            strokeWidth={2.5}
            dot={false}
            isAnimationActive={false}
          />
          {/* 이력 평균 ReferenceLine */}
          <ReferenceLine
            y={historyMean}
            stroke="#ef4444"
            strokeWidth={2}
            strokeDasharray="5 4"
            ifOverflow="extendDomain"
          >
            <Label
              value={`이력 평균 ${historyMean}%`}
              position="top"
              offset={6}
              fill="#b91c1c"
              fontSize={13}
              fontWeight={700}
            />
          </ReferenceLine>
          {/* 오늘 평균 dot */}
          {chartData.length > 0 && (
            <ReferenceDot
              x={chartData[chartData.length - 1].label}
              y={todayMean}
              r={5}
              fill="#0d1117"
              stroke="#1a56db"
              strokeWidth={2}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
