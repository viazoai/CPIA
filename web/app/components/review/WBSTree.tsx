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

const RAIL_WIDTH = 24; // px per indent slot
const LINE_COLOR = "#9aa3b2"; // tree branch line color
const LINE_THICKNESS = 1.5; // px

export function WBSTree({ root, selectedId, onSelect, onDrop }: Props) {
  return (
    <div className="flex flex-col h-full text-sm">
      <div className="shrink-0 border-b border-border-soft px-5 py-3 font-display text-h6 text-ink">
        WBS
        <span className="ml-2 text-body-sm font-normal text-ink-mid">(건물 &gt; 공종 &gt; Work Package)</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        <Branch
          node={root}
          ancestorsLast={[]}
          isLast
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
  ancestorsLast: boolean[];
  isLast: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDrop?: (cardId: string, wpId: string) => void;
}

function Branch({ node, ancestorsLast, isLast, selectedId, onSelect, onDrop }: BranchProps) {
  const depth = ancestorsLast.length;
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = !!(node.children && node.children.length > 0);
  const isSelected = node.id === selectedId;
  const isWP = node.type === "work_package";
  const isRoot = depth === 0;

  const [dragOver, setDragOver] = useState(false);

  return (
    <div>
      <div
        className={cn(
          "group relative flex items-stretch rounded-sm cursor-pointer transition-colors",
          isSelected ? "bg-brand-light text-brand-text font-semibold" : "hover:bg-surface-soft",
          dragOver && "ring-2 ring-mint"
        )}
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
        {/* Ancestor rail slots — vertical line continues only where an ancestor wasn't the last child */}
        {ancestorsLast.map((wasLast, i) => (
          <div
            key={i}
            aria-hidden
            className="relative shrink-0 self-stretch"
            style={{ width: RAIL_WIDTH, minHeight: 28 }}
          >
            {!wasLast && (
              <div
                className="pointer-events-none absolute"
                style={{
                  top: 0,
                  bottom: 0,
                  left: RAIL_WIDTH / 2 - LINE_THICKNESS / 2,
                  width: LINE_THICKNESS,
                  backgroundColor: LINE_COLOR,
                }}
              />
            )}
          </div>
        ))}

        {/* Immediate connector slot — └ if last child, ├ otherwise */}
        {!isRoot && (
          <div
            aria-hidden
            className="relative shrink-0 self-stretch"
            style={{ width: RAIL_WIDTH, minHeight: 28 }}
          >
            {/* vertical: full height if not last, else only top half */}
            <div
              className="pointer-events-none absolute"
              style={{
                top: 0,
                ...(isLast ? { height: "50%" } : { bottom: 0 }),
                left: RAIL_WIDTH / 2 - LINE_THICKNESS / 2,
                width: LINE_THICKNESS,
                backgroundColor: LINE_COLOR,
              }}
            />
            {/* horizontal connector at row midline */}
            <div
              className="pointer-events-none absolute"
              style={{
                top: `calc(50% - ${LINE_THICKNESS / 2}px)`,
                left: RAIL_WIDTH / 2,
                width: RAIL_WIDTH / 2,
                height: LINE_THICKNESS,
                backgroundColor: LINE_COLOR,
              }}
            />
          </div>
        )}

        {/* Node row content */}
        <div className={cn("flex flex-1 min-w-0 items-center gap-1.5 py-1.5 pr-2", isRoot ? "pl-2" : "pl-1.5")}>
          {hasChildren ? (
            open ? <ChevronDown className="h-3 w-3 text-ink-light shrink-0" /> : <ChevronRight className="h-3 w-3 text-ink-light shrink-0" />
          ) : (
            <span className="w-3 shrink-0" />
          )}
          <StatusDot status={node.status} />
          <span className={cn("text-xs flex-1 truncate", isWP ? "text-ink-mid" : "text-ink")}>{node.name}</span>
          {node.review_count > 0 && (
            <span className="inline-flex items-center gap-0.5 rounded-sm bg-sun-light px-1.5 py-0.5 text-[11px] font-bold text-sun-text shrink-0">
              <AlertTriangle className="h-2.5 w-2.5" />
              {node.review_count}
            </span>
          )}
          {isWP && node.review_count === 0 && (
            <CheckCircle2 className="h-3 w-3 text-mint/70 shrink-0" />
          )}
        </div>
      </div>

      {open && hasChildren && node.children!.map((c, i, arr) => (
        <Branch
          key={c.id}
          node={c}
          ancestorsLast={isRoot ? [] : [...ancestorsLast, isLast]}
          isLast={i === arr.length - 1}
          selectedId={selectedId}
          onSelect={onSelect}
          onDrop={onDrop}
        />
      ))}
    </div>
  );
}

function StatusDot({ status }: { status: Status }) {
  const color = status === "risk" ? "bg-rose" : status === "caution" ? "bg-sun" : status === "normal" ? "bg-mint" : "bg-ink-light/30";
  return <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", color)} />;
}
