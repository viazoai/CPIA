import { cn } from "@/lib/utils";

export interface KpiItem {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  tone: "lavender" | "mint" | "sky" | "peach" | "rose" | "sun";
}

const TONE_STRIPE: Record<KpiItem["tone"], string> = {
  lavender: "from-lavender to-lavender-light",
  mint:     "from-mint to-mint-light",
  sky:      "from-sky to-sky-light",
  peach:    "from-peach to-peach-light",
  rose:     "from-rose to-rose-light",
  sun:      "from-sun to-sun-light",
};

export function KpiStrip({ items }: { items: KpiItem[] }) {
  return (
    <div className={cn(
      "grid gap-3",
      items.length === 4 && "grid-cols-2 md:grid-cols-4",
      items.length === 5 && "grid-cols-2 md:grid-cols-5",
    )}>
      {items.map((it, i) => (
        <div key={i} className="relative overflow-hidden rounded-card border border-border-soft bg-card p-4 shadow-xs">
          <span aria-hidden className={cn("absolute inset-x-0 top-0 h-1 bg-gradient-to-r", TONE_STRIPE[it.tone])} />
          <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light">{it.label}</div>
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
