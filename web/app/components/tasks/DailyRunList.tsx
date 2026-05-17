"use client";
import { cn } from "@/lib/utils";
import { AlertTriangle, CheckCircle2, Pause } from "lucide-react";
import type { DailyRun } from "@/lib/types";

interface Props {
  runs: DailyRun[];
  selectedDate: string;
  onSelect: (date: string) => void;
}

export function DailyRunList({ runs, selectedDate, onSelect }: Props) {
  const max = Math.max(...runs.map((r) => r.total_count));

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-3 border-b border-border-soft shrink-0">
        <div className="font-display text-h6 text-ink">
          Daily Runs
          <span className="ml-2 text-body-sm font-normal text-ink-mid">일별 실행</span>
        </div>
        <div className="mt-1 text-xs text-ink-mid">{runs.length}일치 누적</div>
      </div>
      <div className="flex flex-col flex-1 overflow-y-auto">
        {runs.map((run) => {
          const active = run.date === selectedDate;
          return (
            <button
              type="button"
              key={run.date}
              onClick={() => onSelect(run.date)}
              className={cn(
                "group flex flex-col gap-1 border-b border-border-soft px-3 py-3 text-left transition-colors",
                active ? "bg-lavender-light/50" : "hover:bg-surface-soft"
              )}
            >
              <div className="flex items-center justify-between">
                <span className={cn("font-mono text-xs", active ? "text-lavender-text font-bold" : "text-ink")}>
                  {run.date}
                </span>
                <RunStatusIcon status={run.status} />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-ink-mid">{run.total_count}건</span>
                {run.has_anomaly && (
                  <span className="inline-flex items-center gap-0.5 rounded-sm bg-rose-light px-1.5 py-0.5 text-[11px] font-semibold text-rose-text">
                    <AlertTriangle className="h-2.5 w-2.5" />
                    이상
                  </span>
                )}
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-soft">
                <div
                  className={cn(
                    "h-full transition-all",
                    run.status === "review_pending" ? "bg-sun" : run.has_anomaly ? "bg-rose" : "bg-mint"
                  )}
                  style={{ width: `${(run.total_count / max) * 100}%` }}
                />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function RunStatusIcon({ status }: { status: DailyRun["status"] }) {
  if (status === "review_pending") return <Pause className="h-3.5 w-3.5 text-sun" fill="currentColor" />;
  if (status === "running")        return <span className="h-2 w-2 rounded-full bg-sky animate-pulse" />;
  return <CheckCircle2 className="h-3.5 w-3.5 text-mint" />;
}
