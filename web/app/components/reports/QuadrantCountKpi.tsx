"use client";
import { cn } from "@/lib/utils";
import type { WPSummaryRow } from "@/lib/types";

type Filter = "all" | "risk" | "caution" | "safe";

interface Props {
  wpSummary: WPSummaryRow[];
  filter: Filter;
  onFilterChange: (f: Filter) => void;
}

// 2026-05-29: 칩 카운트를 wp_summary.status (forecaster risk_level) 단일 source 로 통일.
// 이전엔 quadrant.quadrant (productivity×impact 4분면) 기반이라 WP 목록 status 와
// 어긋났다 (분포도 "위험 0" 인데 목록 "이상" 표시). 라벨도 정상/주의/이상 통일.
export function QuadrantCountKpi({ wpSummary, filter, onFilterChange }: Props) {
  const counts = {
    risk: wpSummary.filter((w) => w.status === "risk").length,
    caution: wpSummary.filter((w) => w.status === "caution").length,
    safe: wpSummary.filter((w) => w.status === "normal").length,
  };

  return (
    <div className="grid grid-cols-3 gap-2">
      <Chip tone="rose"  active={filter === "risk"}    onClick={() => onFilterChange(filter === "risk" ? "all" : "risk")}       label="이상" count={counts.risk} />
      <Chip tone="sun"   active={filter === "caution"} onClick={() => onFilterChange(filter === "caution" ? "all" : "caution")} label="주의" count={counts.caution} />
      <Chip tone="mint"  active={filter === "safe"}    onClick={() => onFilterChange(filter === "safe" ? "all" : "safe")}       label="정상" count={counts.safe} />
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
      <span className="font-mono text-xs uppercase tracking-wider">{label}</span>
      <span className="font-display text-xl font-bold">{count}</span>
    </button>
  );
}
