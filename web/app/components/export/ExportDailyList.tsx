"use client";
import { cn } from "@/lib/utils";
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
          // 완료(ready) → 초록, 취합중(draft) → 주황.
          // 시연: 최신 일자(2025-09-25)는 '오늘 취합중' 으로 항상 주황 표기 (status/export 동작은 그대로).
          const inProgress = d.status !== "ready" || d.date === "2025-09-25";
          const dot = inProgress ? "bg-[#f59e0b]" : "bg-[#0ea76a]";
          return (
            <button
              type="button"
              key={d.date}
              onClick={() => onSelect(d.date)}
              className={cn(
                "relative flex items-center gap-2.5 border-b border-border-soft px-3 py-2.5 text-left transition-colors",
                active
                  ? "bg-brand-light shadow-inner before:absolute before:inset-y-0 before:left-0 before:w-1 before:bg-brand"
                  : "hover:bg-surface-soft"
              )}
            >
              <span
                className={cn("h-2 w-2 shrink-0 rounded-full", dot)}
                title={inProgress ? "취합중" : "완료"}
              />
              <span
                className={cn(
                  "font-mono text-[13px] leading-tight shrink-0",
                  active ? "text-brand-text font-bold" : "text-ink"
                )}
              >
                {d.date}
              </span>
              <span className="ml-auto whitespace-nowrap text-xs text-ink-mid tabular-nums">
                <b className="text-ink">{d.bp_count}</b>개 업체
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
