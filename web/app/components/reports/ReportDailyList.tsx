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
        const Icon = d.status === "risk" ? AlertTriangle : d.status === "caution" ? AlertCircle : CheckCircle2;
        const iconColor = d.status === "risk" ? "text-rose" : d.status === "caution" ? "text-sun" : "text-mint";
        return (
          <button
            type="button"
            key={d.date}
            onClick={() => onSelect(d.date)}
            className={cn(
              "relative flex flex-col gap-1 border-b border-border-soft px-3 py-3 text-left transition-colors",
              active
                ? "bg-brand-light shadow-inner before:absolute before:inset-y-0 before:left-0 before:w-1 before:bg-brand"
                : "hover:bg-surface-soft"
            )}
          >
            <div className="flex items-center justify-between">
              <span className={cn("font-mono text-sm", active ? "text-brand-text font-bold" : "text-ink")}>{d.date}</span>
              <Icon className={cn("h-4 w-4", iconColor)} />
            </div>
            <div className="text-body-sm text-ink-mid">
              생산성 <b className="text-ink">{d.productivity_today}%</b>
              {d.recovery_days > 0 && (
                <span>
                  {" · 최적화 공기 "}
                  <b className="text-mint-text">-{d.recovery_days}일</b>
                </span>
              )}
              {d.delay_days > 0 && <span> · D+{d.delay_days} 지연</span>}
            </div>
          </button>
        );
      })}
      </div>
    </div>
  );
}
