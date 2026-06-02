"use client";
import { cn } from "@/lib/utils";
import type { WPSummaryRow } from "@/lib/types";
import { waCode } from "@/lib/wp-format";

interface Props {
  rows: WPSummaryRow[];
  selectedWpId: string | null;
  onSelect: (wpId: string) => void;
}

export const STATUS_DOT = {
  normal:  "bg-mint",
  caution: "bg-sun",
  risk:    "bg-rose",
} as const;

export const STATUS_LABEL = {
  normal:  "정상",
  caution: "주의",
  risk:    "이상",
} as const;

// 2026-05-29: 결정론 recoveryDays() 폐기 — BE wp_summary.recovery_days (scenarios.by_wp
// base_p50) 단일 source 로 대체. site = Σ(wp recovery_days) 정합 보장.

export function WPSummaryTable({ rows, selectedWpId, onSelect }: Props) {
  return (
    <div className="flex h-full flex-col rounded-card border border-border-soft bg-card shadow-xs overflow-hidden">
      <div className="border-b border-border-soft px-4 py-3 shrink-0">
        <div className="font-display text-h6 text-ink">Work Package 목록</div>
      </div>

      <div className="flex-1 overflow-auto">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-10 bg-surface-soft/95 text-[11px] text-ink-mid backdrop-blur-sm">
            <tr className="border-b border-border-soft text-left">
              <th className="px-3 py-1.5 font-medium">Work Area</th>
              <th className="px-3 py-1.5 font-medium">공종</th>
              <th className="px-3 py-1.5 font-medium">BP사</th>
              <th className="px-3 py-1.5 font-medium">지연일</th>
              <th className="px-3 py-1.5 font-medium">AI 단축</th>
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
                    selected && "bg-brand-light shadow-inner",
                  )}
                >
                  <td
                    className={cn(
                      "relative px-3 py-1 text-[12px] font-semibold text-ink",
                      selected &&
                        "before:absolute before:inset-y-0 before:left-0 before:w-1 before:bg-brand",
                    )}
                  >
                    {waCode(row)}
                  </td>
                  <td className="px-3 py-1 text-[12px] text-ink">{row.trade}</td>
                  <td className="px-3 py-1 text-[12px] text-ink-mid">{row.bp_name}</td>
                  <td className="px-3 py-1 text-[12px] tabular-nums">
                    {(() => {
                      const d = row.delay_days ?? 0;
                      return d > 0
                        ? <span className="font-semibold text-rose-text">+{d}일</span>
                        : <span className="text-ink-light">일정 충족</span>;
                    })()}
                  </td>
                  <td className="px-3 py-1 text-[12px] tabular-nums">
                    {(() => {
                      // 2026-05-29: BE 단일 source (wp_summary.recovery_days = scenarios.by_wp).
                      // FE 결정론 recoveryDays() 폐기 — site = Σ(wp recovery_days) 정합.
                      const days = row.recovery_days ?? 0;
                      return days > 0
                        ? <span className="font-semibold text-mint-text">-{days}일</span>
                        : <span className="text-ink-light">—</span>;
                    })()}
                  </td>
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
