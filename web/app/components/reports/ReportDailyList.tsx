"use client";
import { cn } from "@/lib/utils";
import { AlertTriangle, CheckCircle2, AlertCircle } from "lucide-react";
import type { ReportDaily } from "@/lib/types";

interface Props {
  daily: ReportDaily[];
  selectedDate: string;
  onSelect: (date: string) => void;
}

export function ReportDailyList({ daily, selectedDate, onSelect }: Props) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-3 border-b border-border-soft shrink-0">
        <div className="font-mono text-xs uppercase tracking-wider text-ink-light">
          Daily Reports · 일별 보고서
        </div>
      </div>
      <div className="flex flex-col flex-1 overflow-y-auto">
      {daily.map((d) => {
        const active = d.date === selectedDate;
        const Icon = d.status === "risk" ? AlertTriangle : d.status === "caution" ? AlertCircle : CheckCircle2;
        const iconColor = d.status === "risk" ? "text-rose" : d.status === "caution" ? "text-sun" : "text-mint";
        return (
          <button
            type="button"
            key={d.date}
            onClick={() => onSelect(d.date)}
            className={cn(
              "flex flex-col gap-1 border-b border-border-soft px-3 py-3 text-left transition-colors",
              active ? "bg-lavender-light/50" : "hover:bg-surface-soft"
            )}
          >
            <div className="flex items-center justify-between">
              <span className={cn("font-mono text-xs", active ? "text-lavender-text font-bold" : "text-ink")}>{d.date}</span>
              <Icon className={cn("h-3.5 w-3.5", iconColor)} />
            </div>
            <div className="text-[11px] text-ink-mid">
              생산성 <b className="text-ink">{d.productivity_today}%</b>
              {d.delay_days > 0 && <span> · D+{d.delay_days} 지연</span>}
            </div>
          </button>
        );
      })}
      </div>
    </div>
  );
}
