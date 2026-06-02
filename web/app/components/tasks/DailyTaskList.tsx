"use client";
import { cn } from "@/lib/utils";
import type { DailyTask } from "@/lib/types";

interface Props {
  tasks: DailyTask[];
  selectedDate: string;
  onSelect: (date: string) => void;
}

/** progress 기반 3-상태 점 — 완료(초록) / 작업중(주황) / 미진행(빨강) */
function statusDot(progress: number) {
  if (progress >= 100) return { dot: "bg-mint", text: "완료", tcls: "text-mint-text" };
  if (progress > 0) return { dot: "bg-peach", text: "작업중", tcls: "text-peach-text" };
  return { dot: "bg-rose", text: "미진행", tcls: "text-rose-text" };
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
          const s = statusDot(t.progress_percent);
          return (
            <button
              type="button"
              key={t.date}
              onClick={() => onSelect(t.date)}
              className={cn(
                "relative flex items-center gap-3 border-b border-border-soft px-3 py-2.5 text-left transition-colors",
                active
                  ? "bg-brand-light shadow-inner before:absolute before:inset-y-0 before:left-0 before:w-1 before:bg-brand"
                  : "hover:bg-surface-soft"
              )}
            >
              <span className={cn("h-2 w-2 shrink-0 rounded-full", s.dot)} title={s.text} />
              <span className={cn(
                "font-mono text-[11px] leading-tight shrink-0",
                active ? "text-brand-text font-bold" : "text-ink"
              )}>
                {t.date}
              </span>
              <span className="ml-auto font-mono text-[11px] tabular-nums text-ink-mid">
                {t.total_count.toLocaleString()}건
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
