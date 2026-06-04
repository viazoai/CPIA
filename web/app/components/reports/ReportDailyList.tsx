"use client";
import { cn } from "@/lib/utils";
import type { ReportDaily } from "@/lib/types";

interface Props {
  daily: ReportDaily[];
  selectedDate: string;
  onSelect: (date: string) => void;
}

/** 생산성 기반 상태 점 — 75% 이하 위험(빨강), 75~100% 주의(노랑·앰버), 100% 초과 정상(초록).
 * 주의·위험이 작은 점에서 구별되도록 주의는 짙은 앰버(#d97706) 대신 밝은 옐로앰버(#f59e0b)로 띄운다. */
function dotClass(productivity: number): string {
  if (productivity <= 75) return "bg-[#ef4444]";
  if (productivity <= 100) return "bg-[#f59e0b]";
  return "bg-[#0ea76a]";
}

export function ReportDailyList({ daily, selectedDate, onSelect }: Props) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2.5 border-b border-border-soft shrink-0">
        <div className="font-display text-h6 font-bold text-ink">
          일별 보고서
        </div>
        <div className="mt-0.5 text-xs text-ink-mid">
          총 {daily.length}개 리포트 생성됨
        </div>
      </div>
      <div className="flex flex-col flex-1 overflow-y-auto">
        {daily.map((d) => {
          const active = d.date === selectedDate;
          const dot = dotClass(d.productivity_today);
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
              <span className={cn("h-2 w-2 shrink-0 rounded-full", dot)} />
              <span className={cn(
                "font-mono text-[13px] leading-tight shrink-0",
                active ? "text-brand-text font-bold" : "text-ink"
              )}>
                {d.date}
              </span>
              <span className="ml-auto whitespace-nowrap text-xs text-ink-mid tabular-nums">
                생산성 <b className="text-ink">{d.productivity_today}%</b>
                {d.recovery_days > 0 && (
                  <>
                    {" · 최적화 공기 "}
                    <b className="text-mint-text">-{d.recovery_days}일</b>
                  </>
                )}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
