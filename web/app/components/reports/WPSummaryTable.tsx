"use client";
import { cn } from "@/lib/utils";
import type { WPSummaryRow } from "@/lib/types";

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

/**
 * WP 단위 공기 단축 추정 — baseline 까지 회복했을 때 전체 공기에 주는 영향.
 *   days = max(0, round((baseline − productivity)/100 × impact × scale))
 * scale 은 시연 합산이 적절한 폭(약 10~15일)이 되도록 조정한 PoC 상수.
 * A_Track 의 Optimizer 가 산출하는 실 회복일 수로 대체 예정.
 */
export function recoveryDays(productivity: number, baseline: number, impact: number): number {
  const gap = baseline - productivity;
  if (gap <= 0) return 0;
  return Math.max(0, Math.round((gap / 100) * impact * 0.3));
}

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
              <th className="px-3 py-1.5 font-medium">WP명</th>
              <th className="px-3 py-1.5 font-medium">공종</th>
              <th className="px-3 py-1.5 font-medium">BP사</th>
              <th className="px-3 py-1.5 font-medium">Impact</th>
              <th className="px-3 py-1.5 font-medium">Productivity</th>
              <th className="px-3 py-1.5 font-medium">공기 단축</th>
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
                    {row.wp_name}
                  </td>
                  <td className="px-3 py-1 text-[12px] text-ink">{row.trade}</td>
                  <td className="px-3 py-1 text-[12px] text-ink-mid">{row.bp_name}</td>
                  <td className="px-3 py-1 text-[12px] font-semibold text-ink tabular-nums">
                    {row.impact}%
                  </td>
                  <td className="px-3 py-1 text-[12px] font-semibold text-ink tabular-nums">
                    {row.productivity}%
                  </td>
                  <td className="px-3 py-1 text-[12px] tabular-nums">
                    {(() => {
                      const days = recoveryDays(row.productivity, row.baseline, row.impact);
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
