const ITEMS: { dot: string; label: string; note: string }[] = [
  { dot: "bg-mint", label: "Optimistic", note: "Optimizer 권고 적용" },
  { dot: "bg-brand", label: "Base", note: "자연 평균 회귀" },
  { dot: "bg-rose", label: "Pessimistic", note: "현 추세 유지" },
];

export function ScenarioLegend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-mid">
      {ITEMS.map((it) => (
        <li key={it.label} className="inline-flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${it.dot}`} aria-hidden />
          <span className="font-semibold text-ink">{it.label}</span>
          <span className="text-ink-light">— {it.note}</span>
        </li>
      ))}
    </ul>
  );
}
