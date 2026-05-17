"use client";
import { cn } from "@/lib/utils";
import { AlertTriangle, CheckCircle2, Pause } from "lucide-react";
import type { DailyTask } from "@/lib/types";

interface Props {
  tasks: DailyTask[];
  selectedDate: string;
  onSelect: (date: string) => void;
}

export function DailyTaskList({ tasks, selectedDate, onSelect }: Props) {
  const totalReceived = tasks.reduce((sum, t) => sum + t.total_count, 0);
  const totalProcessed = tasks.reduce(
    (sum, t) => sum + Math.round((t.total_count * t.progress_percent) / 100),
    0
  );
  const completionRate = totalReceived === 0 ? 0 : Math.round((totalProcessed / totalReceived) * 100);

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2.5 border-b border-border-soft shrink-0">
        <div className="font-display text-h6 font-bold text-ink">
          Agent 작업 목록
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-ink-mid tabular-nums">
          <span>접수 {totalReceived.toLocaleString()}건</span>
          <span>·</span>
          <span>처리 {totalProcessed.toLocaleString()}건</span>
          <span>·</span>
          <span>완료율 {completionRate}%</span>
        </div>
      </div>
      <div className="flex flex-col flex-1 overflow-y-auto">
        {tasks.map((t) => {
          const active = t.date === selectedDate;
          return (
            <button
              type="button"
              key={t.date}
              onClick={() => onSelect(t.date)}
              className={cn(
                "relative flex items-center gap-2 border-b border-border-soft px-3 py-1.5 text-left transition-colors",
                active
                  ? "bg-brand-light shadow-inner before:absolute before:inset-y-0 before:left-0 before:w-1 before:bg-brand"
                  : "hover:bg-surface-soft"
              )}
            >
              <span className={cn(
                "font-mono text-[11px] leading-tight shrink-0",
                active ? "text-brand-text font-bold" : "text-ink"
              )}>
                {t.date}
              </span>
              <div className="flex-1 h-1.5 overflow-hidden rounded-full bg-surface-soft">
                <div
                  className={cn(
                    "h-full transition-all",
                    t.status === "review_pending" ? "bg-sun" : t.has_anomaly ? "bg-rose" : "bg-mint"
                  )}
                  style={{ width: `${t.progress_percent}%` }}
                />
              </div>
              <span className={cn(
                "font-mono text-[11px] tabular-nums leading-tight w-9 text-right shrink-0",
                active ? "text-brand-text font-bold" : "text-ink-mid"
              )}>
                {t.progress_percent}%
              </span>
              <span className="flex items-center gap-1 w-7 justify-end shrink-0">
                {t.has_anomaly && <AlertTriangle className="h-3 w-3 text-rose-text" />}
                <RunStatusIcon status={t.status} />
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function RunStatusIcon({ status }: { status: DailyTask["status"] }) {
  if (status === "review_pending") return <Pause className="h-3 w-3 text-sun" fill="currentColor" />;
  if (status === "running")        return <span className="h-1.5 w-1.5 rounded-full bg-sky animate-pulse" />;
  return <CheckCircle2 className="h-3 w-3 text-mint" />;
}
