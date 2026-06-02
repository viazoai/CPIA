"use client";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  Cell,
  Tooltip,
  ReferenceLine,
  Label,
} from "recharts";
import { useId } from "react";
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
  /** 그룹 평균선 (단일 ReferenceLine, 차트 끝~끝 가로선). */
  showAverage?: boolean;
  /** 평균선 라벨 접두어 (예: "업체별 평균"). 기본 "평균". */
  averageLabel?: string;
  /** 각 막대를 baseline 미만(rose)/이상(blue) 으로 색 구분. items 가 baseline 필드를 가져야 함. */
  showBaseline?: boolean;
  /** true 면 카드 chrome·title 없이 차트만 렌더 — 다른 컴포넌트 안에 임베드용. */
  bare?: boolean;
  /**
   * 막대 방향.
   *  - "horizontal" (default): 가로 막대 (라벨 Y축, 값 X축). 항목 수 < 10 권장.
   *  - "vertical": 세로 막대 (라벨 X축, 값 Y축). 수십 개 항목용.
   */
  orientation?: "horizontal" | "vertical";
  /**
   * 그룹 경계로 둘 라벨 값들 — 그 항목 좌측에 vertical divider 표시.
   * vertical 모드 전용. (예: building 단위로 묶을 때)
   */
  groupBoundaries?: string[];
}

export function BarChartH({
  items,
  title,
  showAverage,
  averageLabel = "평균",
  showBaseline,
  bare,
  orientation = "horizontal",
  groupBoundaries,
}: Props) {
  const avg = items.length
    ? items.reduce((sum, it) => sum + it.value, 0) / items.length
    : 0;
  const isVertical = orientation === "vertical";
  const height = isVertical ? 280 : items.length * 36 + 20;
  /* 막대 그라데이션 — 랜딩 LandingHero 의 bg-gradient-to-t from-brand-light to-brand 패턴 차용.
   * SVG <linearGradient> 가 컴포넌트마다 unique id 가 필요해 useId 사용. */
  const gradId = useId().replace(/:/g, "");
  const blueId = `barBlue-${gradId}`;
  const roseId = `barRose-${gradId}`;

  const chart = (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart
        data={items}
        layout={isVertical ? "horizontal" : "vertical"}
        barCategoryGap={isVertical ? "35%" : "20%"}
        margin={
          isVertical
            ? { top: 24, right: 16, left: 0, bottom: 12 }
            : { top: 0, right: 30, left: 50, bottom: 0 }
        }
      >
        <defs>
          {/* 세로 막대: 위 → 짙은 / 아래 → 옅은. 생산성 라인차트(#1a56db)와 동일 톤. */}
          <linearGradient id={blueId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="#1a56db" />
            <stop offset="100%" stopColor="#e8eeff" />
          </linearGradient>
          <linearGradient id={roseId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="#f87171" />
            <stop offset="100%" stopColor="#fee2e2" />
          </linearGradient>
        </defs>
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
          radius={isVertical ? [8, 8, 0, 0] : [0, 6, 6, 0]}
          maxBarSize={isVertical ? 22 : undefined}
          isAnimationActive
          animationBegin={150}
          animationDuration={900}
          animationEasing="ease-out"
        >
          {items.map((it, i) => {
            /* showBaseline 모드: baseline 미만이면 rose 그라데이션, 이상이면 blue.
             * 세로 막대 → 위 짙음 / 아래 옅음 (랜딩 LandingHero 패턴).
             * 미설정 모드(다른 사용처): 기존 status 기반 단색. */
            const fill = showBaseline
              ? (typeof it.baseline === "number" && it.value < it.baseline ? `url(#${roseId})` : `url(#${blueId})`)
              : STATUS_COLOR[it.status];
            return <Cell key={i} fill={fill} />;
          })}
        </Bar>
        {isVertical && groupBoundaries && groupBoundaries.map((label) => (
          <ReferenceLine
            key={`grp-${label}`}
            x={label}
            stroke="#cbd2dc"
            strokeWidth={1.5}
            strokeDasharray="2 3"
          />
        ))}
        {showAverage && items.length > 0 && (
          <ReferenceLine
            {...(isVertical ? { y: avg } : { x: avg })}
            stroke="#9ca3af"
            strokeWidth={2}
            strokeDasharray="5 4"
            ifOverflow="extendDomain"
            className="cpia-ref-fade"
          >
            <Label
              value={`${averageLabel} ${avg.toFixed(1)}%`}
              position="top"
              offset={6}
              fill="#6b7280"
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
