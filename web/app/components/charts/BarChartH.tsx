"use client";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Cell, Tooltip } from "recharts";
import type { BarItem } from "@/lib/types";

const STATUS_COLOR = {
  normal:  "#0ea76a",
  caution: "#d97706",
  risk:    "#ef4444",
  unknown: "#7a8494",
};

export function BarChartH({ items, title }: { items: BarItem[]; title?: string }) {
  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
      {title && <div className="mb-3 font-display text-h6 text-ink">{title}</div>}
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
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
