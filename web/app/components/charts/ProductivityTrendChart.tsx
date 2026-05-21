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
  /** [{date, value}] 90일 시계열 — 호출 측이 PG daily 에서 잘라 전달. */
  trend: { date: string; value: number }[];
  /** 끝점 강조 — 보통 trend[trend.length-1].value 와 같음. */
  todayValue: number;
  /** 끝 날짜 (ISO "YYYY-MM-DD") — 헤더 보조 라벨용. */
  endDate: string;
}

export function ProductivityTrendChart({ trend, todayValue, endDate }: Props) {
  const data = useMemo(
    () =>
      trend.map((p, i) => {
        const d = new Date(p.date);
        const mm = String(d.getMonth() + 1).padStart(2, "0");
        const dd = String(d.getDate()).padStart(2, "0");
        return { idx: i, label: `${mm}-${dd}`, value: p.value };
      }),
    [trend],
  );
  const avg = useMemo(
    () => (data.length ? data.reduce((s, p) => s + p.value, 0) / data.length : 0),
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
          <div className="font-display text-base font-semibold text-ink">
            현장 생산성{" "}
            <span className="text-sm font-normal text-ink-mid">({endDate} 기준)</span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-display text-h3 font-semibold text-ink">
              {todayValue}
            </span>
            <span className="text-base text-ink-light">%</span>
            <span
              className={cn(
                "ml-1 inline-flex items-center rounded-full px-2.5 py-0.5 font-display text-sm font-medium",
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
            stroke="#ef4444"
            strokeWidth={2}
            strokeDasharray="5 4"
            ifOverflow="extendDomain"
          >
            <Label
              value={`현장 평균 ${avg.toFixed(1)}%`}
              position="top"
              offset={6}
              fill="#b91c1c"
              fontSize={14}
              fontFamily='"Inter Tight", Pretendard, "Noto Sans KR", system-ui, sans-serif'
              fontWeight={700}
            />
          </ReferenceLine>
          {data.length > 0 && (
            <ReferenceDot
              x={data[data.length - 1].label}
              y={todayValue}
              r={6}
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
