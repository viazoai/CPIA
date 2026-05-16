"use client";
import { useState } from "react";
import { ChevronRight, ChevronDown, AlertTriangle, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { WBSNode, Status } from "@/lib/types";

interface Props {
  root: WBSNode;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDrop?: (cardId: string, wpId: string) => void;
}

export function WBSTree({ root, selectedId, onSelect, onDrop }: Props) {
  return (
    <div className="flex flex-col p-3 text-sm">
      <div className="font-mono text-xs uppercase tracking-wider text-ink-light px-2 pb-2">
        WBS Tree · 건물 &gt; 공종 &gt; Work Package
      </div>
      <Branch node={root} depth={0} selectedId={selectedId} onSelect={onSelect} onDrop={onDrop} />
    </div>
  );
}

function Branch({
  node, depth, selectedId, onSelect, onDrop,
}: { node: WBSNode; depth: number; selectedId: string | null; onSelect: (id: string) => void; onDrop?: (cardId: string, wpId: string) => void }) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = node.children && node.children.length > 0;
  const isSelected = node.id === selectedId;
  const isWP = node.type === "work_package";

  const [dragOver, setDragOver] = useState(false);

  return (
    <div>
      <div
        className={cn(
          "group flex items-center gap-1.5 px-2 py-1.5 rounded-sm cursor-pointer transition-colors",
          isSelected ? "bg-lavender-light text-lavender-text font-semibold" : "hover:bg-surface-soft",
          dragOver && "ring-2 ring-mint"
        )}
        style={{ paddingLeft: `${depth * 14 + 8}px` }}
        onClick={() => {
          if (hasChildren) setOpen(!open);
          onSelect(node.id);
        }}
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
          open ? <ChevronDown className="h-3 w-3 text-ink-light shrink-0" /> : <ChevronRight className="h-3 w-3 text-ink-light shrink-0" />
        ) : (
          <span className="w-3" />
        )}
        <StatusDot status={node.status} />
        <span className="text-xs flex-1">{node.name}</span>
        {node.review_count > 0 && (
          <span className="inline-flex items-center gap-0.5 rounded-sm bg-sun-light px-1.5 py-0.5 text-[11px] font-bold text-sun-text">
            <AlertTriangle className="h-2.5 w-2.5" />
            {node.review_count}
          </span>
        )}
        {isWP && node.review_count === 0 && (
          <CheckCircle2 className="h-3 w-3 text-mint" />
        )}
      </div>
      {open && hasChildren && node.children!.map((c) => (
        <Branch key={c.id} node={c} depth={depth + 1} selectedId={selectedId} onSelect={onSelect} onDrop={onDrop} />
      ))}
    </div>
  );
}

function StatusDot({ status }: { status: Status }) {
  const color = status === "risk" ? "bg-rose" : status === "caution" ? "bg-sun" : status === "normal" ? "bg-mint" : "bg-ink-light/30";
  return <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", color)} />;
}
