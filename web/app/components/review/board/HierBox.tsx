"use client";

interface Props {
  label: string;
  reviewCount: number;
  hasChildren: boolean;
  collapsed: boolean;
  onToggle: () => void;
}

/** 위계 노드(프로젝트/건물/공종/WP) — 전부 흰색. 자식 있으면 캐럿, 클릭 시 접기/펼치기. */
export function HierBox({ label, reviewCount, hasChildren, collapsed, onToggle }: Props) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex w-[180px] items-center gap-1.5 rounded-lg border border-border-soft bg-card px-2.5 py-2 text-left shadow-xs hover:bg-surface-soft"
    >
      {hasChildren && <span aria-hidden className="shrink-0 text-[10px] text-ink-light">{collapsed ? "▸" : "▾"}</span>}
      <span className="min-w-0 flex-1 truncate text-xs font-semibold text-ink-mid">{label}</span>
      {reviewCount > 0 && (
        <span className="shrink-0 rounded-full bg-sun-light px-1.5 py-0.5 font-mono text-[9px] font-bold text-sun-text">
          {reviewCount}
        </span>
      )}
    </button>
  );
}
