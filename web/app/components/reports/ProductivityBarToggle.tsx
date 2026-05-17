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

export function ProductivityBarToggle({ contractorBars, tradeBars }: Props) {
  const [mode, setMode] = useState<Mode>("contractor");
  const items = mode === "contractor" ? contractorBars : tradeBars;
  const title = mode === "contractor" ? "업체별 생산성 (오늘 평균)" : "공종별 생산성 (오늘 평균)";

  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="font-display text-h6 text-ink">{title}</div>
        <div className="inline-flex rounded-md border border-border bg-white p-0.5">
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

      <BarChartH items={items} showAverage bare />
    </div>
  );
}
