"use client";
import { useState } from "react";
import { Check, Pencil, AlertTriangle, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatReviewQuantity } from "@/lib/review-format";
import { WPSearchCombobox } from "./WPSearchCombobox";
import type { ReviewItem, WBSNode } from "@/lib/types";

interface Props {
  item: ReviewItem;
  wbsRoot: WBSNode;
  onConfirm: (id: string) => void;
  onRemap: (id: string, newWpId: string, newPath: string) => void;
  readOnly?: boolean;
  selected?: boolean;
  onSelectCard?: (id: string) => void;
}

export function ReviewCard({ item, wbsRoot, onConfirm, onRemap, readOnly, selected, onSelectCard }: Props) {
  const [editMode, setEditMode] = useState(false);
  const isConfirmed = item.status === "confirmed";

  return (
    <div
      data-card-anchor={item.id}
      draggable={!isConfirmed && !readOnly}
      onDragStart={(e) => {
        if (isConfirmed || readOnly) return;
        e.dataTransfer.setData("text/card-id", item.id);
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={() => onSelectCard?.(item.id)}
      className={cn(
        "rounded-card border bg-card p-4 shadow-xs",
        isConfirmed ? "border-mint/30 bg-mint-light/10" : "border-sun/30 cursor-grab",
        selected && "ring-2 ring-brand/50 border-brand"
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {readOnly ? (
            <>
              <CheckCircle2 className="h-4 w-4 text-ink-light" />
              <span className="font-mono text-xs uppercase tracking-wider text-ink-mid font-bold">등록</span>
            </>
          ) : isConfirmed ? (
            <>
              <CheckCircle2 className="h-4 w-4 text-mint" />
              <span className="font-mono text-xs uppercase tracking-wider text-mint-text font-bold">확정</span>
            </>
          ) : (
            <>
              <AlertTriangle className="h-4 w-4 text-sun" />
              <span className="font-mono text-xs uppercase tracking-wider text-sun-text font-bold">미확정</span>
            </>
          )}
          <span className="ml-1 font-semibold text-sm text-ink">{item.bp_name}</span>
        </div>
        <span className="font-mono text-xs font-semibold text-ink-mid">
          {formatReviewQuantity(item.quantity)} {item.unit}
        </span>
      </div>

      <p className="mt-2 text-sm italic text-ink-mid leading-snug">
        &ldquo;{item.work_content}&rdquo;
      </p>

      <div className="mt-3 flex items-center gap-2 text-xs">
        <span className="text-ink-light">매핑:</span>
        <span className="font-semibold text-ink">{item.ai_mapped_path}</span>
        <span className={cn(
          "ml-auto rounded-sm px-1.5 py-0.5 text-xs font-mono font-bold",
          item.confidence >= 0.8 ? "bg-mint-light text-mint-text" : item.confidence >= 0.7 ? "bg-sky-light text-sky-text" : "bg-sun-light text-sun-text"
        )}>
          {Math.round(item.confidence * 100)}%
        </span>
      </div>

      {!isConfirmed && !readOnly && item.alternative_wps && item.alternative_wps.length > 0 && (
        <div className="mt-2 text-[11px] text-ink-light">
          대안: {item.alternative_wps.map((a) => `${a.path.split(" > ").pop()} (${Math.round(a.score * 100)}%)`).join(" · ")}
        </div>
      )}

      {!readOnly && editMode && (
        <div className="mt-3 rounded-md bg-surface-soft p-2" onClick={(e) => e.stopPropagation()}>
          <div className="text-xs font-mono uppercase tracking-wider text-ink-light mb-1.5">
            수정: 검색 또는 좌측 트리로 드래그
          </div>
          <WPSearchCombobox
            wbsRoot={wbsRoot}
            currentWpId={item.ai_mapped_wp_id}
            onSelect={(id, path) => {
              onRemap(item.id, id, path);
              setEditMode(false);
            }}
          />
        </div>
      )}

      {!readOnly && (
        <div className="mt-3 flex items-center justify-end gap-2">
          {!isConfirmed && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onConfirm(item.id); }}
              className="inline-flex items-center gap-1 rounded-md bg-brand px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-text transition-colors"
            >
              <Check className="h-3.5 w-3.5" strokeWidth={2.5} />
              확정
            </button>
          )}
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setEditMode((v) => !v); }}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-white px-3 py-1.5 text-xs font-semibold text-ink-mid hover:bg-surface-soft"
          >
            <Pencil className="h-3.5 w-3.5" />
            {editMode ? "취소" : "수정"}
          </button>
        </div>
      )}
    </div>
  );
}
