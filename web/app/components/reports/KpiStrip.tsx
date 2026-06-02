import { cn } from "@/lib/utils";

export interface KpiItem {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  /** tone — 카드 외형은 단일 보더로 통일. 값 강조 색에만 사용. */
  tone: "primary" | "risk" | "caution" | "normal" | "muted" | "brand";
}

const VALUE_TONE: Record<KpiItem["tone"], string> = {
  primary: "text-ink",
  risk:    "text-rose-text",
  caution: "text-sun-text",
  normal:  "text-ink",
  muted:   "text-ink-mid",
  brand:   "text-brand-text",
};

/** columns 미지정 시 items 길이로 자동(기존 동작). 지정 시 해당 고정 그리드. */
const COLS: Record<number, string> = {
  2: "grid-cols-2",
  3: "grid-cols-2 md:grid-cols-3",
  4: "grid-cols-2 md:grid-cols-4",
  5: "grid-cols-2 md:grid-cols-5",
};

export function KpiStrip({
  items,
  columns,
  fill,
}: {
  items: KpiItem[];
  columns?: 2 | 3 | 4 | 5;
  /** 부모 높이를 카드가 채우도록 — 2단 레이아웃에서 옆 컬럼과 하단 정렬용 */
  fill?: boolean;
}) {
  const gridCls = columns ? COLS[columns] : COLS[items.length] ?? "";
  return (
    <div
      className={cn(
        "grid gap-3",
        gridCls,
        fill && "h-full auto-rows-fr",
      )}
    >
      {items.map((it, i) => (
        <div
          key={i}
          className={cn(
            "rounded-card border border-border-soft bg-card p-4 shadow-xs transition-shadow hover:shadow-sm",
            fill && "flex min-h-[7rem] flex-col items-center justify-center text-center",
          )}
        >
          <div className="font-display text-h6 text-ink">{it.label}</div>
          <div
            className={cn(
              "mt-2 font-display font-semibold tracking-[-0.015em]",
              fill ? "text-3xl" : "text-2xl",
              VALUE_TONE[it.tone],
            )}
          >
            {it.value}
            {it.unit && (
              <span className={cn("ml-1 font-medium text-ink-light", fill ? "text-base" : "text-sm")}>
                {it.unit}
              </span>
            )}
          </div>
          {it.sub && <div className="mt-1 text-[11px] text-ink-mid">{it.sub}</div>}
        </div>
      ))}
    </div>
  );
}
