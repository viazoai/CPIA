"use client";
import { useMemo, useState } from "react";
import { BarChartH } from "@/app/components/charts/BarChartH";
import { cn } from "@/lib/utils";
import { filterAndPickBars } from "@/lib/bar-filters";
import type { BarItem } from "@/lib/types";

type Mode = "contractor" | "wp";

interface Props {
  contractorBars: BarItem[];
  wpBars: BarItem[];
  /** 목표 생산성 — 격차 산출 기준 (보통 ReportKpi.target_productivity, 100%). */
  historyMean: number;
  /** 기준 날짜 (ISO "YYYY-MM-DD"). 헤더 보조 라벨 'YYYY-MM-DD 기준'. */
  date: string;
}

const MODES: { key: Mode; label: string }[] = [
  { key: "wp",         label: "공사별" },
  { key: "contractor", label: "업체별" },
];

export function ProductivityBarToggle({ contractorBars, wpBars, historyMean, date }: Props) {
  const [mode, setMode] = useState<Mode>("wp");
  // spec 2026-05-21-cpia-ui-4-fixes-design.md §④ — 150% 초과 제거 + top3+bot7 (최대 10).
  const items = useMemo(
    () => filterAndPickBars(mode === "contractor" ? contractorBars : wpBars),
    [mode, contractorBars, wpBars],
  );
  // 오늘 평균 생산성 — 표시 막대들의 평균.
  const avg = items.length
    ? items.reduce((s, it) => s + it.value, 0) / items.length
    : 0;

  // 목표 생산성(100%) 대비 격차 — 생산성 라인차트 KPI 칩과 동일 기준(>100 정상 / 75~100 주의 / ≤75 위험).
  const gap = avg - historyMean;
  const gapSign = gap >= 0 ? "+" : "";
  const gapChipTone =
    gap > 0 ? "bg-mint-light text-mint-text"
    : gap > -25 ? "bg-sun-light text-sun-text"
    : "bg-rose-light text-rose-text";

  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="font-display text-base font-semibold text-ink">
            공사/업체별 현장 생산성{" "}
            <span className="text-sm font-normal text-ink-mid">({date} 기준)</span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-display text-h3 font-semibold tracking-[-0.015em] text-ink">
              {avg.toFixed(1)}
            </span>
            <span className="text-base text-ink-light">%</span>
            <span
              className={cn(
                "ml-1 inline-flex items-center rounded-full px-2.5 py-0.5 font-display text-sm font-medium",
                gapChipTone,
              )}
            >
              목표 대비 {gapSign}{gap.toFixed(1)}%
            </span>
          </div>
        </div>

        <div className="inline-flex shrink-0 rounded-md border border-border bg-white p-0.5">
          {MODES.map((m) => {
            const active = mode === m.key;
            return (
              <button
                key={m.key}
                type="button"
                onClick={() => setMode(m.key)}
                className={cn(
                  "rounded-[5px] px-3 py-1 text-xs font-semibold transition-colors",
                  active ? "bg-brand text-white" : "text-ink-mid hover:text-ink",
                )}
              >
                {m.label}
              </button>
            );
          })}
        </div>
      </div>

      <BarChartH
        items={items}
        showBaseline
        showAverage
        bare
        orientation="vertical"
      />
    </div>
  );
}
