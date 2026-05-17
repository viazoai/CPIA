"use client";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } from "recharts";

interface Point {
  month: string;
  value: number;
}

interface Props {
  points: Point[];
  unit: string;
  title?: string;
  valueLabel?: string;
}

export function TrendLineChart({ points, unit, title, valueLabel = "value" }: Props) {
  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
      {title && <div className="font-mono text-xs uppercase tracking-wider text-ink-light mb-3">{title}</div>}
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"  stopColor="#1a56db" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#1a56db" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" />
            <XAxis dataKey="month" tick={{ fontSize: 10, fill: "#7a8494" }} />
            <YAxis tick={{ fontSize: 10, fill: "#7a8494" }} tickFormatter={(v) => `${v}${unit}`} />
            <Tooltip
              contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
              formatter={(v) => [`${v}${unit}`, valueLabel]}
            />
            <Area type="monotone" dataKey="value" stroke="#1a56db" strokeWidth={2.5} fill="url(#trendGradient)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
