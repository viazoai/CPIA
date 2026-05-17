"use client";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Cell,
  Tooltip,
  ReferenceLine,
  Label,
} from "recharts";
import type { BarItem } from "@/lib/types";

const STATUS_COLOR = {
  normal:  "#0ea76a",
  caution: "#d97706",
  risk:    "#ef4444",
  unknown: "#7a8494",
};

interface Props {
  items: BarItem[];
  title?: string;
  /** 평균선 표시 (가로 막대 차트에 수직 ReferenceLine). 단순 평균 자동 계산. */
  showAverage?: boolean;
  /** true 면 카드 chrome·title 없이 차트만 렌더 — 다른 컴포넌트 안에 임베드용. */
  bare?: boolean;
}

export function BarChartH({ items, title, showAverage, bare }: Props) {
  const avg = items.length
    ? items.reduce((sum, it) => sum + it.value, 0) / items.length
    : 0;

  const chart = (
    <ResponsiveContainer width="100%" height={items.length * 36 + 20}>
      <BarChart data={items} layout="vertical" margin={{ top: 0, right: 30, left: 50, bottom: 0 }}>
        <XAxis type="number" domain={[0, 110]} tick={{ fontSize: 10, fill: "#7a8494" }} tickFormatter={(v) => `${v}%`} />
        <YAxis type="category" dataKey="label" tick={{ fontSize: 11, fill: "#0d1117" }} width={50} />
        <Tooltip
          contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
          formatter={(v) => [`${v}%`, "생산성"]}
        />
        <Bar dataKey="value" radius={[0, 4, 4, 0]}>
          {items.map((it, i) => <Cell key={i} fill={STATUS_COLOR[it.status]} />)}
        </Bar>
        {showAverage && items.length > 0 && (
          <ReferenceLine
            x={avg}
            stroke="#1a56db"
            strokeWidth={1.5}
            strokeDasharray="3 3"
            ifOverflow="extendDomain"
          >
            <Label
              value={`평균 ${avg.toFixed(1)}%`}
              position="top"
              fill="#1243a8"
              fontSize={10}
              fontFamily="JetBrains Mono, ui-monospace, monospace"
            />
          </ReferenceLine>
        )}
      </BarChart>
    </ResponsiveContainer>
  );

  if (bare) return chart;

  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
      {title && <div className="mb-3 font-display text-h6 text-ink">{title}</div>}
      {chart}
    </div>
  );
}
