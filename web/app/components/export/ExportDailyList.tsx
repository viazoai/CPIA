"use client";
import { cn } from "@/lib/utils";
import { CheckCircle2, Pause } from "lucide-react";
import type { ConsolidatedReportSummary } from "@/lib/types";

interface Props {
  list: ConsolidatedReportSummary[];
  selectedDate: string;
  onSelect: (date: string) => void;
}

export function ExportDailyList({ list, selectedDate, onSelect }: Props) {
  const readyCount = list.filter((d) => d.status === "ready").length;

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2.5 border-b border-border-soft shrink-0">
        <div className="font-display text-h6 font-bold text-ink">
          통합 작업일보 목록
        </div>
        <div className="mt-0.5 text-xs text-ink-mid">
          총 {list.length}건 · 출력 가능 {readyCount}건
        </div>
      </div>

      <div className="flex flex-col flex-1 overflow-y-auto">
        {list.map((d) => {
          const active = d.date === selectedDate;
          const isReady = d.status === "ready";
          return (
            <button
              type="button"
              key={d.date}
              onClick={() => onSelect(d.date)}
              className={cn(
                "relative flex items-center gap-2 border-b border-border-soft px-3 py-2 text-left transition-colors",
                active
                  ? "bg-brand-light shadow-inner before:absolute before:inset-y-0 before:left-0 before:w-1 before:bg-brand"
                  : "hover:bg-surface-soft"
              )}
            >
              <span
                className={cn(
                  "font-mono text-[11px] leading-tight shrink-0",
                  active ? "text-brand-text font-bold" : "text-ink"
                )}
              >
                {d.date}
              </span>

              <span className="flex-1" />

              <span
                className={cn(
                  "inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                  isReady ? "bg-mint-light text-mint-text" : "bg-surface-soft text-ink-light"
                )}
              >
                {isReady ? "ready" : "draft"}
              </span>

              <span className="flex items-center w-5 justify-end shrink-0">
                {isReady ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-mint" />
                ) : (
                  <Pause className="h-3 w-3 text-ink-light" fill="currentColor" />
                )}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
