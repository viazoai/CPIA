interface Item {
  label: string;
  value: number;
  meta?: string;
}

interface Props {
  items: Item[];
  unit: string;
  title?: string;
}

export function HorizontalBarList({ items, unit, title }: Props) {
  const max = Math.max(...items.map((i) => i.value));
  return (
    <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
      {title && <div className="mb-3 font-display text-h6 text-ink">{title}</div>}
      <div className="flex flex-col gap-2">
        {items.map((it, i) => (
          <div key={i} className="flex items-center gap-3">
            <div className="w-32 shrink-0 text-xs font-medium text-ink truncate">{it.label}</div>
            <div className="flex-1 h-5 rounded-sm bg-surface-soft overflow-hidden">
              <div
                className="h-full bg-lavender flex items-center justify-end pr-2"
                style={{ width: `${(it.value / max) * 100}%` }}
              >
                <span className="font-mono text-xs font-semibold text-white">{it.value}{unit}</span>
              </div>
            </div>
            {it.meta && <div className="w-20 text-right font-mono text-[11px] text-ink-mid">{it.meta}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
