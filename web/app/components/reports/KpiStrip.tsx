import { cn } from "@/lib/utils";

export interface KpiItem {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  // neutral = stripe 미렌더(흑백 카드). lavender = 도미넌트 강조. rose = 위험 신호.
  // 그 외 색은 차트·status 한정으로 격하 — 본 strip 에선 권장하지 않음.
  tone: "lavender" | "rose" | "neutral";
}

const TONE_STRIPE: Record<KpiItem["tone"], string | null> = {
  lavender: "from-lavender to-lavender-light",
  rose:     "from-rose to-rose-light",
  neutral:  null,
};

export function KpiStrip({ items }: { items: KpiItem[] }) {
  return (
    <div className={cn(
      "grid gap-3",
      items.length === 4 && "grid-cols-2 md:grid-cols-4",
      items.length === 5 && "grid-cols-2 md:grid-cols-5",
    )}>
      {items.map((it, i) => {
        const stripe = TONE_STRIPE[it.tone];
        return (
          <div key={i} className="relative overflow-hidden rounded-card border border-border-soft bg-card p-4 shadow-xs">
            {stripe && (
              <span aria-hidden className={cn("absolute inset-x-0 top-0 h-1 bg-gradient-to-r", stripe)} />
            )}
            <div className="font-mono text-xs uppercase tracking-wider text-ink-light">{it.label}</div>
            <div className="mt-2 font-display text-2xl font-bold tracking-tight text-ink">
              {it.value}
              {it.unit && <span className="ml-1 text-sm font-semibold text-ink-light">{it.unit}</span>}
            </div>
            {it.sub && <div className="mt-1 text-[11px] text-ink-mid">{it.sub}</div>}
          </div>
        );
      })}
    </div>
  );
}
