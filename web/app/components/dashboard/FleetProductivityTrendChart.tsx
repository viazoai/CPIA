"use client";
import { useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  Label,
  CartesianGrid,
} from "recharts";
import { generateSiteTrend, buildFleetTrend } from "@/lib/fleet-trend-mock";
import type { Site, FleetTrendPoint } from "@/lib/types";

/* 진입 연출 — 생산성 차트와 동일: 선/밴드가 좌→우로 그려진 뒤 이력 평균선 페이드인. */
const DRAW_BEGIN_MS = 150;
const DRAW_DURATION_MS = 1400;

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
  // 세로축 0~최대치 — 평균 시계열·이력 평균 중 가장 큰 값에 여유를 두고 10 단위 올림.
  const yMax = useMemo(() => {
    const peak = Math.max(0, historyMean, todayMean, ...chartData.map((p) => p.mean ?? 0));
    return Math.ceil((peak + 5) / 10) * 10;
  }, [chartData, historyMean, todayMean]);

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
          <defs>
            <linearGradient id="cpiaFleetFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#1a56db" stopOpacity={0.28} />
              <stop offset="100%" stopColor="#1a56db" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#eef0f4" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: "#7a8494" }}
            interval={Math.max(1, Math.floor(chartData.length / 8))}
          />
          <YAxis
            domain={[0, yMax]}
            tick={{ fontSize: 10, fill: "#7a8494" }}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
            formatter={(v, key) => [`${v}%`, key === "mean" ? "평균" : key === "max" ? "최고" : "최저"]}
          />
          {/* 평균선 + 선 아래 그라데이션 area — 생산성 차트와 1:1 동일 표현. 좌→우 그리기. */}
          <Area
            dataKey="mean"
            stroke="#1a56db"
            strokeWidth={2.5}
            fill="url(#cpiaFleetFill)"
            dot={false}
            isAnimationActive
            animationBegin={DRAW_BEGIN_MS}
            animationDuration={DRAW_DURATION_MS}
            animationEasing="ease-out"
          />
          {/* 목표 생산성 100% — 이력 기대치(정상 기준) 고정선. 이력 평균과 색으로 구분(초록). */}
          <ReferenceLine
            y={100}
            stroke="#0ea76a"
            strokeWidth={1}
            strokeDasharray="5 4"
            ifOverflow="extendDomain"
            className="cpia-ref-draw"
          >
            <Label
              value="목표 생산성 100%"
              position="top"
              offset={6}
              fill="#067a4e"
              fontSize={14}
              fontFamily='"Inter Tight", Pretendard, "Noto Sans KR", system-ui, sans-serif'
              fontWeight={700}
            />
          </ReferenceLine>
          {/* 이력 평균 ReferenceLine — 회색 점선, 그리기 완료 후 페이드인, 가운데 라벨 */}
          <ReferenceLine
            y={historyMean}
            stroke="#9ca3af"
            strokeWidth={1}
            strokeDasharray="5 4"
            ifOverflow="extendDomain"
            className="cpia-ref-draw"
          >
            <Label
              value={`평균 생산성 ${historyMean}%`}
              position="bottom"
              offset={6}
              fill="#6b7280"
              fontSize={14}
              fontFamily='"Inter Tight", Pretendard, "Noto Sans KR", system-ui, sans-serif'
              fontWeight={700}
            />
          </ReferenceLine>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
