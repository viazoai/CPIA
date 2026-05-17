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
  /** 평균선 표시 (단순 평균 자동 계산 + ReferenceLine). */
  showAverage?: boolean;
  /** true 면 카드 chrome·title 없이 차트만 렌더 — 다른 컴포넌트 안에 임베드용. */
  bare?: boolean;
  /**
   * 막대 방향.
   *  - "horizontal" (default): 가로 막대 (라벨 Y축, 값 X축). 항목 수 < 10 권장.
   *  - "vertical": 세로 막대 (라벨 X축, 값 Y축). 수십 개 항목용.
   */
  orientation?: "horizontal" | "vertical";
}

export function BarChartH({
  items,
  title,
  showAverage,
  bare,
  orientation = "horizontal",
}: Props) {
  const avg = items.length
    ? items.reduce((sum, it) => sum + it.value, 0) / items.length
    : 0;
  const isVertical = orientation === "vertical";

  /* 동적 높이/폭:
   *  - horizontal: 항목 수에 비례한 세로 길이
   *  - vertical: 고정 높이 280, 항목 많을 때 라벨 회전 */
  const height = isVertical ? 280 : items.length * 36 + 20;

  const chart = (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={items}
        layout={isVertical ? "horizontal" : "vertical"}
        margin={
          isVertical
            ? { top: 24, right: 16, left: 0, bottom: 48 }
            : { top: 0, right: 30, left: 50, bottom: 0 }
        }
      >
        {isVertical ? (
          <>
            <XAxis
              type="category"
              dataKey="label"
              tick={{ fontSize: 10, fill: "#0d1117" }}
              interval={0}
              angle={-30}
              textAnchor="end"
              height={48}
            />
            <YAxis
              type="number"
              domain={[0, 110]}
              tick={{ fontSize: 10, fill: "#7a8494" }}
              tickFormatter={(v) => `${v}%`}
            />
          </>
        ) : (
          <>
            <XAxis type="number" domain={[0, 110]} tick={{ fontSize: 10, fill: "#7a8494" }} tickFormatter={(v) => `${v}%`} />
            <YAxis type="category" dataKey="label" tick={{ fontSize: 11, fill: "#0d1117" }} width={50} />
          </>
        )}
        <Tooltip
          contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
          formatter={(v) => [`${v}%`, "생산성"]}
        />
        <Bar
          dataKey="value"
          radius={isVertical ? [4, 4, 0, 0] : [0, 4, 4, 0]}
          maxBarSize={isVertical ? 28 : undefined}
        >
          {items.map((it, i) => <Cell key={i} fill={STATUS_COLOR[it.status]} />)}
        </Bar>
        {showAverage && items.length > 0 && (
          <ReferenceLine
            {...(isVertical ? { y: avg } : { x: avg })}
            stroke="#1a56db"
            strokeWidth={1.5}
            strokeDasharray="3 3"
            ifOverflow="extendDomain"
          >
            <Label
              value={`평균 ${avg.toFixed(1)}%`}
              position={isVertical ? "right" : "top"}
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
