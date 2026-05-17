import { cn } from "@/lib/utils";
import type { DiagStatus } from "@/lib/types";

interface Props {
  gap_pct: number;
  z_score: number;
  status: DiagStatus;
}

const STATUS_TEXT: Record<DiagStatus, string> = {
  normal:  "text-mint-text",
  caution: "text-sun-text",
  risk:    "text-rose-text",
};

const STATUS_CHIP: Record<DiagStatus, string> = {
  normal:  "bg-mint-light text-mint-text",
  caution: "bg-sun-light text-sun-text",
  risk:    "bg-rose-light text-rose-text",
};

const STATUS_LABEL: Record<DiagStatus, string> = {
  normal:  "정상",
  caution: "주의",
  risk:    "이상",
};

export function GapKpiCard({ gap_pct, z_score, status }: Props) {
  const sign = gap_pct >= 0 ? "+" : "";
  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs transition-shadow hover:shadow-sm">
      <div className="font-display text-h6 text-ink">평균 대비 격차</div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className={cn("font-display text-3xl font-semibold tracking-[-0.015em]", STATUS_TEXT[status])}>
          {sign}{gap_pct.toFixed(1)}
        </span>
        <span className="text-sm text-ink-light">%p</span>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <span className={cn(
          "inline-flex items-center rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider",
          STATUS_CHIP[status],
        )}>
          {STATUS_LABEL[status]}
        </span>
        <span className="font-mono text-[11px] text-ink-light">Z = {z_score.toFixed(2)}</span>
      </div>
    </div>
  );
}
