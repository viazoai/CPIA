"use client";
import { cn } from "@/lib/utils";
import type { WPSummaryRow } from "@/lib/types";

interface Props {
  rows: WPSummaryRow[];
  selectedWpId: string | null;
  onSelect: (wpId: string) => void;
}

const STATUS_DOT = {
  normal:  "bg-mint",
  caution: "bg-sun",
  risk:    "bg-rose",
} as const;

const STATUS_LABEL = {
  normal:  "정상",
  caution: "주의",
  risk:    "이상",
} as const;

export function WPSummaryTable({ rows, selectedWpId, onSelect }: Props) {
  return (
    <div className="rounded-card border border-border-soft bg-card shadow-xs overflow-hidden">
      <div className="border-b border-border-soft px-4 py-3">
        <div className="font-display text-h6 text-ink">
          WP 요약
          <span className="ml-2 text-body-sm font-normal text-ink-mid">{rows.length} 개 · 행 클릭 시 작업일보 필터</span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead className="bg-surface-soft/80 text-[11px] text-ink-mid">
            <tr className="border-b border-border-soft text-left">
              <th className="px-3 py-1.5 font-medium">WP명</th>
              <th className="px-3 py-1.5 font-medium">공종</th>
              <th className="px-3 py-1.5 font-medium">BP사</th>
              <th className="px-3 py-1.5 font-medium">시작</th>
              <th className="px-3 py-1.5 font-medium">종료</th>
              <th className="px-3 py-1.5 font-medium">진척</th>
              <th className="px-3 py-1.5 font-medium">생산성</th>
              <th className="px-3 py-1.5 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const selected = row.wp_id === selectedWpId;
              return (
                <tr
                  key={row.wp_id}
                  onClick={() => onSelect(row.wp_id)}
                  className={cn(
                    "cursor-pointer border-b border-border-soft transition-colors hover:bg-surface-soft/50",
                    selected && "bg-brand-light/40",
                  )}
                >
                  <td className="px-3 py-1 text-[12px] font-semibold text-ink">{row.wp_name}</td>
                  <td className="px-3 py-1 text-[12px] text-ink">{row.trade}</td>
                  <td className="px-3 py-1 text-[12px] text-ink-mid">{row.bp_name}</td>
                  <td className="px-3 py-1 font-mono text-[11px] text-ink-mid">{row.start_date}</td>
                  <td className="px-3 py-1 font-mono text-[11px] text-ink-mid">{row.end_date}</td>
                  <td className="px-3 py-1">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-20 rounded-full bg-border">
                        <div
                          className="h-full rounded-full bg-brand"
                          style={{ width: `${Math.min(100, row.progress_pct)}%` }}
                        />
                      </div>
                      <span className="font-mono text-[11px] text-ink-mid">{row.progress_pct}%</span>
                    </div>
                  </td>
                  <td className="px-3 py-1 text-[12px] font-semibold text-ink tabular-nums">{row.productivity}%</td>
                  <td className="px-3 py-1">
                    <span className="inline-flex items-center gap-1.5">
                      <span className={cn("h-1.5 w-1.5 rounded-full", STATUS_DOT[row.status])} />
                      <span className="text-[10px] font-semibold text-ink-mid">
                        {STATUS_LABEL[row.status]}
                      </span>
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
