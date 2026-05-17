"use client";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
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
  /** 그룹 평균선 (단일 ReferenceLine). 다른 사용처용 — ProductivityBarToggle 은 showBaseline 사용. */
  showAverage?: boolean;
  /** 각 항목의 baseline 값을 Line 시리즈로 연결. items 가 baseline 필드를 가져야 함. */
  showBaseline?: boolean;
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
  showBaseline,
  bare,
  orientation = "horizontal",
}: Props) {
  const avg = items.length
    ? items.reduce((sum, it) => sum + it.value, 0) / items.length
    : 0;
  const isVertical = orientation === "vertical";
  const height = isVertical ? 280 : items.length * 36 + 20;

  const chart = (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart
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
          formatter={(v, name) => [`${v}%`, name === "baseline" ? "이력 평균" : "생산성"]}
        />
        <Bar
          dataKey="value"
          radius={isVertical ? [4, 4, 0, 0] : [0, 4, 4, 0]}
          maxBarSize={isVertical ? 28 : undefined}
          isAnimationActive={false}
        >
          {items.map((it, i) => {
            /* showBaseline 모드: baseline 미만이면 rose, 이상이면 brand.
             * 미설정 모드(다른 사용처): 기존 status 기반 색. */
            const color = showBaseline
              ? (typeof it.baseline === "number" && it.value < it.baseline ? "#ef4444" : "#1a56db")
              : STATUS_COLOR[it.status];
            return <Cell key={i} fill={color} />;
          })}
        </Bar>
        {showBaseline && items.some((it) => typeof it.baseline === "number") && (
          <Line
            dataKey="baseline"
            type="monotone"
            stroke="#ef4444"
            strokeWidth={2.5}
            strokeDasharray="5 4"
            dot={false}
            activeDot={{ r: 5, fill: "#ef4444", stroke: "#ffffff", strokeWidth: 2 }}
            isAnimationActive={false}
            connectNulls
          />
        )}
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
              position="top"
              offset={6}
              fill="#1243a8"
              fontSize={14}
              fontFamily='"Inter Tight", Pretendard, "Noto Sans KR", system-ui, sans-serif'
              fontWeight={700}
            />
          </ReferenceLine>
        )}
      </ComposedChart>
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
