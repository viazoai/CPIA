"use client";
import { useState } from "react";
import { BarChartH } from "@/app/components/charts/BarChartH";
import { cn } from "@/lib/utils";
import type { BarItem } from "@/lib/types";

type Mode = "contractor" | "trade";

interface Props {
  contractorBars: BarItem[];
  tradeBars: BarItem[];
}

const MODES: { key: Mode; label: string }[] = [
  { key: "contractor", label: "업체별" },
  { key: "trade",      label: "공종별" },
];

/* 평균값 → status tone — KPI 카드 색 톤. */
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

export function ProductivityBarToggle({ contractorBars, tradeBars }: Props) {
  const [mode, setMode] = useState<Mode>("contractor");
  const items = mode === "contractor" ? contractorBars : tradeBars;
  const title = mode === "contractor" ? "업체별 생산성 (오늘 평균)" : "공종별 생산성 (오늘 평균)";

  const avg = items.length
    ? items.reduce((s, it) => s + it.value, 0) / items.length
    : 0;
  const status = avgStatus(avg);
  const subLabel = mode === "contractor" ? "BP사 평균" : "공종 평균";

  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="font-display text-h6 text-ink">{title}</div>
          <div className="mt-1.5 flex items-baseline gap-2">
            <span className="font-mono text-[10px] uppercase tracking-wider text-ink-light">
              현재 생산성 KPI
            </span>
            <span
              className={cn(
                "font-display text-3xl font-semibold tracking-[-0.015em]",
                STATUS_VALUE_COLOR[status],
              )}
            >
              {avg.toFixed(1)}
            </span>
            <span className="text-sm text-ink-light">%</span>
            <span className="text-[11px] text-ink-mid">· {items.length}개 {subLabel}</span>
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

      <BarChartH items={items} showAverage bare orientation="vertical" />
    </div>
  );
}
