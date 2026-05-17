import { cn } from "@/lib/utils";
import type { ScenarioPoint } from "@/lib/types";

interface Props {
  scenarios: {
    optimistic: ScenarioPoint;
    base: ScenarioPoint;
    pessimistic: ScenarioPoint;
  };
}

const ROWS: { key: keyof Props["scenarios"]; label: string; dot: string }[] = [
  { key: "optimistic",  label: "Optimistic",  dot: "bg-mint" },
  { key: "base",        label: "Base",        dot: "bg-brand" },
  { key: "pessimistic", label: "Pessimistic", dot: "bg-rose" },
];

function formatEta(days: number): string {
  if (!Number.isFinite(days)) return "회복 불가";
  return `D-${days}`;
}

function formatDelta(days: number): string {
  if (days === 0) return "변동 없음";
  if (days > 0) return `+${days}일 지연`;
  return `${days}일 단축`;
}

export function RecoveryEtaCard({ scenarios }: Props) {
  return (
    <div className="rounded-card border border-border-soft bg-card p-5 shadow-xs">
      <div className="font-display text-h6 text-ink">회복 ETA · 시나리오 3종</div>
      <ul className="mt-3 flex flex-col">
        {ROWS.map((row) => {
          const s = scenarios[row.key];
          const isBase = row.key === "base";
          return (
            <li
              key={row.key}
              className={cn(
                "flex items-center gap-3 border-b border-border-soft py-2 last:border-b-0",
                isBase && "font-semibold",
              )}
            >
              <span className={`h-2 w-2 shrink-0 rounded-full ${row.dot}`} aria-hidden />
              <span className="w-24 text-body-sm text-ink">{row.label}</span>
              <span className="flex-1 font-display text-h6 text-ink">{formatEta(s.eta_days)}</span>
              <span className="font-mono text-[11px] text-ink-mid">{formatDelta(s.delta_completion_days)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
