import { cn } from "@/lib/utils";

export interface KpiItem {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  /** tone — 카드 외형은 단일 보더로 통일. 값 강조 색에만 사용. */
  tone: "primary" | "risk" | "caution" | "normal" | "muted";
}

const VALUE_TONE: Record<KpiItem["tone"], string> = {
  primary: "text-ink",
  risk:    "text-rose-text",
  caution: "text-sun-text",
  normal:  "text-ink",
  muted:   "text-ink-mid",
};

export function KpiStrip({ items }: { items: KpiItem[] }) {
  return (
    <div className={cn(
      "grid gap-3",
      items.length === 4 && "grid-cols-2 md:grid-cols-4",
      items.length === 5 && "grid-cols-2 md:grid-cols-5",
    )}>
      {items.map((it, i) => (
        <div key={i} className="rounded-card border border-border-soft bg-card p-4 shadow-xs transition-shadow hover:shadow-sm">
          <div className="font-display text-h6 text-ink">{it.label}</div>
          <div className={cn("mt-2 font-display text-2xl font-semibold tracking-[-0.015em]", VALUE_TONE[it.tone])}>
            {it.value}
            {it.unit && <span className="ml-1 text-sm font-medium text-ink-light">{it.unit}</span>}
          </div>
          {it.sub && <div className="mt-1 text-[11px] text-ink-mid">{it.sub}</div>}
        </div>
      ))}
    </div>
  );
}
