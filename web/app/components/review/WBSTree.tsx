"use client";
import { useState } from "react";
import { AlertCircle, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { WBSNode } from "@/lib/types";

interface Props {
  root: WBSNode;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDrop?: (cardId: string, wpId: string) => void;
}

// 레벨별 들여쓰기 폭 (px). depth 가 깊을수록 누적 indent
const INDENT_STEP = [0, 16, 32, 48, 64, 80] as const;
function indentPx(depth: number): number {
  return INDENT_STEP[Math.min(depth, INDENT_STEP.length - 1)];
}

// 레벨별 타이포 — 깊이가 깊어질수록 작아지고 옅어짐
const LEVEL_TEXT: Record<number, string> = {
  0: "text-body-sm font-bold text-ink",
  1: "text-sm font-semibold text-ink",
  2: "text-xs font-medium text-ink",
  3: "text-xs text-ink-mid",
};
function levelTextClass(depth: number) {
  return LEVEL_TEXT[depth] ?? LEVEL_TEXT[3];
}

export function WBSTree({ root, selectedId, onSelect, onDrop }: Props) {
  return (
    <div className="flex flex-col h-full text-sm">
      <div className="shrink-0 border-b border-border-soft px-5 py-3 font-display text-h6 font-bold text-ink">
        WBS
        <span className="ml-2 text-body-sm font-normal text-ink-mid">(건물 &gt; 공종 &gt; Work Package)</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        <Branch
          node={root}
          depth={0}
          selectedId={selectedId}
          onSelect={onSelect}
          onDrop={onDrop}
        />
      </div>
    </div>
  );
}

interface BranchProps {
  node: WBSNode;
  depth: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDrop?: (cardId: string, wpId: string) => void;
}

function Branch({ node, depth, selectedId, onSelect, onDrop }: BranchProps) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = !!(node.children && node.children.length > 0);
  const isSelected = node.id === selectedId;
  const isWP = node.type === "work_package";
  const [dragOver, setDragOver] = useState(false);

  return (
    <div>
      <div
        className={cn(
          "group flex items-center gap-1.5 py-1.5 pr-2 rounded-sm cursor-pointer transition-colors",
          isSelected ? "bg-brand-light text-brand-text font-semibold" : "hover:bg-surface-soft",
          dragOver && "ring-2 ring-mint"
        )}
        style={{ paddingLeft: 8 + indentPx(depth) }}
        onClick={() => onSelect(node.id)}
        onDragOver={isWP ? (e) => { e.preventDefault(); setDragOver(true); } : undefined}
        onDragLeave={isWP ? () => setDragOver(false) : undefined}
        onDrop={isWP ? (e) => {
          e.preventDefault();
          setDragOver(false);
          const cardId = e.dataTransfer.getData("text/card-id");
          if (cardId && onDrop) onDrop(cardId, node.id);
        } : undefined}
      >
        {hasChildren ? (
          <button
            type="button"
            aria-label={open ? "접기" : "펼치기"}
            aria-expanded={open}
            onClick={(e) => {
              e.stopPropagation();
              setOpen(!open);
            }}
            className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm text-ink-mid hover:bg-surface-soft hover:text-ink"
          >
            {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
        ) : (
          <span className="inline-block h-4 w-4 shrink-0" aria-hidden />
        )}
        <span className={cn("flex-1 truncate", levelTextClass(depth))}>{node.name}</span>
        <div className="ml-auto flex items-center gap-1 shrink-0 tabular-nums">
          {node.review_count > 0 && (
            <AlertCircle
              className="h-3 w-3 text-sun-text"
              aria-label={`미확정 ${node.review_count}건`}
            />
          )}
          <span className="font-mono text-[11px] text-ink-mid">
            {node.total_count}
          </span>
        </div>
      </div>

      {open && hasChildren && node.children!.map((c) => (
        <Branch
          key={c.id}
          node={c}
          depth={depth + 1}
          selectedId={selectedId}
          onSelect={onSelect}
          onDrop={onDrop}
        />
      ))}
    </div>
  );
}

