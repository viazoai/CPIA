"use client";
import { cn } from "@/lib/utils";
import type { QuadrantPoint } from "@/lib/types";

type Filter = "all" | "risk" | "caution" | "safe";

interface Props {
  points: QuadrantPoint[];
  filter: Filter;
  onFilterChange: (f: Filter) => void;
}

export function QuadrantCountKpi({ points, filter, onFilterChange }: Props) {
  const counts = {
    risk: points.filter((p) => p.quadrant === "risk").length,
    caution: points.filter((p) => p.quadrant === "caution").length,
    safe: points.filter((p) => p.quadrant === "safe" || p.quadrant === "watch").length,
  };

  return (
    <div className="grid grid-cols-3 gap-2">
      <Chip tone="rose"  active={filter === "risk"}    onClick={() => onFilterChange(filter === "risk" ? "all" : "risk")}       label="위험" count={counts.risk} />
      <Chip tone="sun"   active={filter === "caution"} onClick={() => onFilterChange(filter === "caution" ? "all" : "caution")} label="경고" count={counts.caution} />
      <Chip tone="mint"  active={filter === "safe"}    onClick={() => onFilterChange(filter === "safe" ? "all" : "safe")}       label="안전" count={counts.safe} />
    </div>
  );
}

function Chip({ tone, active, onClick, label, count }: { tone: "rose" | "sun" | "mint"; active: boolean; onClick: () => void; label: string; count: number }) {
  const bg = tone === "rose" ? "bg-rose-light" : tone === "sun" ? "bg-sun-light" : "bg-mint-light";
  const text = tone === "rose" ? "text-rose-text" : tone === "sun" ? "text-sun-text" : "text-mint-text";
  const ring = tone === "rose" ? "ring-rose" : tone === "sun" ? "ring-sun" : "ring-mint";
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex flex-col items-center justify-center rounded-md px-2 py-2 transition-all",
        bg, text,
        active ? `ring-2 ${ring}` : "hover:opacity-80"
      )}
    >
      <span className="font-mono text-[10px] uppercase tracking-widest">{label}</span>
      <span className="font-display text-xl font-bold">{count}</span>
    </button>
  );
}
