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
  ReferenceDot,
  Label,
  CartesianGrid,
} from "recharts";
import { cn } from "@/lib/utils";

interface Props {
  /** PRNG 시드 — 같은 site 면 같은 트렌드. */
  siteId: string;
  /** 금일 생산성 (KPI #1 productivity_today). 차트 마지막 점에 강제 매핑. */
  todayValue: number;
  /** 표현 일수 (default 90). */
  daysWindow?: number;
}

/* ───── 결정적 PRNG (lib/diagnosis.ts 와 동일 패턴, 사본) ───── */
function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number): () => number {
  return () => {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* 90일 일별 생산성 시계열 — base 92 random walk + 후반 30일 감소 trend.
 *  결과의 마지막 값을 todayValue 로 강제. 같은 siteId+todayValue → 같은 시계열. */
function generateTrend(siteId: string, days: number, todayValue: number) {
  const rand = mulberry32(hashString(siteId));
  const data: { idx: number; label: string; value: number }[] = [];
  let v = 92;
  for (let i = 0; i < days; i++) {
    const drift = (rand() - 0.5) * 4;
    const trend = i > days - 30 ? -(i - (days - 30)) * 0.2 : 0;
    v = Math.max(70, Math.min(105, v + drift + trend));
    data.push({
      idx: i,
      label: i === days - 1 ? "Today" : `D-${days - 1 - i}`,
      value: Math.round(v * 10) / 10,
    });
  }
  if (data.length > 0) {
    data[data.length - 1].value = todayValue;
  }
  return data;
}

export function ProductivityTrendChart({ siteId, todayValue, daysWindow = 90 }: Props) {
  const data = useMemo(
    () => generateTrend(siteId, daysWindow, todayValue),
    [siteId, daysWindow, todayValue],
  );
  const avg = useMemo(
    () => data.reduce((s, p) => s + p.value, 0) / data.length,
    [data],
  );
  const gap = todayValue - avg;
  const gapSign = gap >= 0 ? "+" : "";
  const gapChipTone =
    gap >= -2 ? "bg-mint-light text-mint-text"
    : gap >= -6 ? "bg-sun-light text-sun-text"
    : "bg-rose-light text-rose-text";

  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="font-display text-h6 text-ink">
            공사 전 기간 생산성 트렌드
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-display text-3xl font-semibold tracking-[-0.015em] text-ink">
              {todayValue}
            </span>
            <span className="text-sm text-ink-light">%</span>
            <span
              className={cn(
                "ml-1 inline-flex items-center rounded-full px-2 py-0.5 font-display text-xs font-medium",
                gapChipTone,
              )}
            >
              현장 평균 대비 {gapSign}{gap.toFixed(1)}%
            </span>
          </div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={data} margin={{ top: 16, right: 32, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#eef0f4" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: "#7a8494" }}
            interval={Math.max(1, Math.floor(data.length / 8))}
          />
          <YAxis
            domain={[70, 105]}
            tick={{ fontSize: 10, fill: "#7a8494" }}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
            formatter={(v) => [`${v}%`, "생산성"]}
          />
          <Area
            dataKey="value"
            stroke="#1a56db"
            strokeWidth={2}
            fill="#e8eeff"
            fillOpacity={0.5}
            dot={false}
            isAnimationActive={false}
          />
          <ReferenceLine
            y={avg}
            stroke="#1a56db"
            strokeWidth={1.5}
            strokeDasharray="3 3"
            ifOverflow="extendDomain"
          >
            <Label
              value={`현장 평균 ${avg.toFixed(1)}%`}
              position="insideLeft"
              fill="#1243a8"
              fontSize={10}
              fontFamily="JetBrains Mono, ui-monospace, monospace"
            />
          </ReferenceLine>
          <ReferenceDot
            x={data[data.length - 1].label}
            y={todayValue}
            r={6}
            fill="#0d1117"
            stroke="#1a56db"
            strokeWidth={2}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
