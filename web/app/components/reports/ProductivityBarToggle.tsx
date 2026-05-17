"use client";
import { useState } from "react";
import { BarChartH } from "@/app/components/charts/BarChartH";
import { cn } from "@/lib/utils";
import type { BarItem } from "@/lib/types";

type Mode = "contractor" | "trade";

interface Props {
  contractorBars: BarItem[];
  tradeBars: BarItem[];
  /** 이력 평균 — 격차 산출 기준 (보통 ReportKpi.target_productivity). */
  historyMean: number;
  /** 기준 날짜 (ISO "YYYY-MM-DD"). 헤더 보조 라벨 'YYYY-MM-DD 기준'. */
  date: string;
}

const MODES: { key: Mode; label: string }[] = [
  { key: "contractor", label: "업체별" },
  { key: "trade",      label: "건물·공종별" },
];

function avgStatus(avg: number): "normal" | "caution" | "risk" {
  if (avg < 80) return "risk";
  if (avg < 90) return "caution";
  return "normal";
}

const STATUS_VALUE_COLOR = {
  normal:  "text-mint-text",
  caution: "text-sun-text",
  risk:    "text-rose-text",
} as const;

const STATUS_CHIP = {
  normal:  "bg-mint-light text-mint-text",
  caution: "bg-sun-light text-sun-text",
  risk:    "bg-rose-light text-rose-text",
} as const;

export function ProductivityBarToggle({ contractorBars, tradeBars, historyMean, date }: Props) {
  const [mode, setMode] = useState<Mode>("contractor");
  const items = mode === "contractor" ? contractorBars : tradeBars;
  const modeLabel = mode === "contractor" ? "업체별" : "건물·공종별";

  const avg = items.length
    ? items.reduce((s, it) => s + it.value, 0) / items.length
    : 0;
  const status = avgStatus(avg);
  const subLabel = mode === "contractor" ? "BP사 평균" : "공종 평균";

  const gap = avg - historyMean;
  const gapSign = gap >= 0 ? "+" : "";
  const gapChipTone = gap >= -3 ? STATUS_CHIP.normal : gap >= -8 ? STATUS_CHIP.caution : STATUS_CHIP.risk;

  /* baseline 미만 항목 수 — 자체 기준 도달 못한 항목들 */
  const underCount = items.filter(
    (it) => typeof it.baseline === "number" && it.value < it.baseline,
  ).length;
  const underUnit = mode === "contractor" ? "BP사" : "건물·공종";

  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="font-display text-base font-semibold text-ink">
            {modeLabel} 현장 생산성{" "}
            <span className="text-sm font-normal text-ink-mid">({date} 기준)</span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-display text-h3 font-semibold tracking-[-0.015em] text-ink">
              {underCount}
            </span>
            <span className="text-base text-ink-mid">
              {underUnit} 평균 미만
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

      <BarChartH items={items} showBaseline bare orientation="vertical" />
    </div>
  );
}
