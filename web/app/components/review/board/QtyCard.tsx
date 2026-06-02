"use client";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ReviewItem } from "@/lib/types";

interface Props {
  item: ReviewItem;
  onConfirm: (id: string) => void;
}

/** 작업물량 노드 — 흰색, 검토(미확정)면 sun 강조 + 확정 버튼. */
export function QtyCard({ item, onConfirm }: Props) {
  const review = item.status === "unconfirmed";
  return (
    <div
      data-review={review}
      className={cn(
        "w-[260px] rounded-lg border px-3 py-2 shadow-xs",
        review ? "border-sun bg-sun-light" : "border-border-soft bg-card"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={cn("text-xs font-bold", review ? "text-sun-text" : "text-ink")}>{item.bp_name}</span>
        <span className="font-mono text-[10px] text-ink-light">{Math.round(item.confidence * 100)}%</span>
      </div>
      <div className="mt-0.5 truncate text-[11px] text-ink-mid">{item.work_content}</div>
      {review && (
        <div className="mt-1.5 flex justify-end">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onConfirm(item.id); }}
            className="inline-flex items-center gap-1 rounded-md bg-brand px-2 py-1 text-[10px] font-semibold text-white hover:bg-brand-text"
          >
            <Check className="h-3 w-3" strokeWidth={2.5} /> 확정
          </button>
        </div>
      )}
    </div>
  );
}
