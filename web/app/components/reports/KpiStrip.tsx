import { cn } from "@/lib/utils";

export interface KpiItem {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  tone: "primary" | "risk" | "caution" | "normal" | "muted";
}

const TONE_BORDER: Record<KpiItem["tone"], string> = {
  primary: "border-t-2 border-t-lavender",
  risk:    "border-t-2 border-t-rose",
  caution: "border-t-2 border-t-sun",
  normal:  "border-t-2 border-t-mint",
  muted:   "border-t-2 border-t-border-soft",
};

export function KpiStrip({ items }: { items: KpiItem[] }) {
  return (
    <div className={cn(
      "grid gap-3",
      items.length === 4 && "grid-cols-2 md:grid-cols-4",
      items.length === 5 && "grid-cols-2 md:grid-cols-5",
    )}>
      {items.map((it, i) => (
        <div key={i} className={cn("rounded-card border border-border-soft bg-card p-4 shadow-xs", TONE_BORDER[it.tone])}>
          <div className="font-mono text-xs uppercase tracking-wider text-ink-light">{it.label}</div>
          <div className="mt-2 font-display text-2xl font-bold tracking-tight text-ink">
            {it.value}
            {it.unit && <span className="ml-1 text-sm font-semibold text-ink-light">{it.unit}</span>}
          </div>
          {it.sub && <div className="mt-1 text-[11px] text-ink-mid">{it.sub}</div>}
        </div>
      ))}
    </div>
  );
}
