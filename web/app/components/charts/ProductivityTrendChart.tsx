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
import { cn } from "@/lib/utils";

/* 진입 연출 타이밍 — 선이 좌→우로 그려지는 시간. 끝점/평균선은 이 뒤에 등장. */
const DRAW_BEGIN_MS = 150;
const DRAW_DURATION_MS = 1400;

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
  // 세로축 0~최대치 — 데이터 최대값에 여유를 두고 10 단위로 올림.
  const yMax = useMemo(() => {
    const peak = Math.max(0, todayValue, avg, ...data.map((p) => p.value));
    return Math.ceil((peak + 5) / 10) * 10;
  }, [data, todayValue, avg]);
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
          <defs>
            <linearGradient id="cpiaProdFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#1a56db" stopOpacity={0.28} />
              <stop offset="100%" stopColor="#1a56db" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#eef0f4" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: "#7a8494" }}
            interval={Math.max(1, Math.floor(data.length / 8))}
          />
          <YAxis
            domain={[0, yMax]}
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
            fill="url(#cpiaProdFill)"
            dot={false}
            isAnimationActive
            animationBegin={DRAW_BEGIN_MS}
            animationDuration={DRAW_DURATION_MS}
            animationEasing="ease-out"
          />
          <ReferenceLine
            y={avg}
            stroke="#9ca3af"
            strokeWidth={2}
            strokeDasharray="5 4"
            ifOverflow="extendDomain"
            className="cpia-ref-fade"
          >
            <Label
              value={`현장 평균 ${avg.toFixed(1)}%`}
              position="top"
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
