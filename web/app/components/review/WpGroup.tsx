"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight, AlertTriangle, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { ReviewCard } from "./ReviewCard";
import type { WpGroup as WpGroupData } from "@/lib/review-group";
import type { WBSNode } from "@/lib/types";

interface Props {
  group: WpGroupData;
  selectedCardId: string | null;
  wbsRoot: WBSNode;
  onConfirm: (id: string) => void;
  onRemap: (id: string, newWpId: string, newPath: string) => void;
  onSelectCard: (id: string) => void;
  readOnly?: boolean;
}

export function WpGroup({ group, selectedCardId, wbsRoot, onConfirm, onRemap, onSelectCard, readOnly }: Props) {
  const [showConfirmed, setShowConfirmed] = useState(false);

  const unconfirmed = group.items.filter((c) => c.status === "unconfirmed");
  const confirmed = group.items.filter((c) => c.status === "confirmed");
  // readOnly(등록) 모드는 전 항목 노출. HIL 모드는 확정 항목을 토글 뒤로 접음.
  const visibleConfirmed = readOnly || showConfirmed ? confirmed : [];
  const lowTone = !readOnly && group.unconfirmedCount > 0;

  return (
    <div className="mb-3" data-wp-group={group.wpId}>
      {/* 그룹 헤더 */}
      <div
        className={cn(
          "flex items-center gap-2 rounded-t-card px-3 py-2 text-xs font-bold border",
          lowTone ? "bg-sun-light/40 border-sun/40 text-sun-text" : "bg-mint-light/30 border-mint/30 text-mint-text"
        )}
      >
        {lowTone ? <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> : <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />}
        <span className="truncate">{group.wpName}</span>
        {group.path && <span className="truncate font-normal opacity-70 text-[10px]">{group.path}</span>}
        <span className="ml-auto shrink-0 font-mono text-[10px]">
          {readOnly
            ? `등록 ${group.items.length}건`
            : group.unconfirmedCount > 0
              ? `확정 ${group.confirmedCount} · 검토 ${group.unconfirmedCount} · 최저 ${Math.round((group.minUnconfirmedConfidence ?? 0) * 100)}%`
              : `전부 확정 ${group.confirmedCount}건`}
        </span>
      </div>

      {/* 카드 목록 */}
      <div className="flex flex-col gap-2 rounded-b-card border border-t-0 border-border-soft p-2">
        {unconfirmed.map((c) => (
          <ReviewCard
            key={c.id}
            item={c}
            wbsRoot={wbsRoot}
            selected={c.id === selectedCardId}
            onConfirm={onConfirm}
            onRemap={onRemap}
            onSelectCard={onSelectCard}
            readOnly={readOnly}
          />
        ))}

        {/* HIL: 확정 항목 접힘 토글 */}
        {!readOnly && confirmed.length > 0 && (
          <button
            type="button"
            onClick={() => setShowConfirmed((v) => !v)}
            className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[11px] text-mint-text hover:bg-mint-light/30"
          >
            {showConfirmed ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            ✓ 확정 {confirmed.length}건 {showConfirmed ? "접기" : "펼치기"}
          </button>
        )}

        {visibleConfirmed.map((c) => (
          <ReviewCard
            key={c.id}
            item={c}
            wbsRoot={wbsRoot}
            selected={c.id === selectedCardId}
            onConfirm={onConfirm}
            onRemap={onRemap}
            onSelectCard={onSelectCard}
            readOnly={readOnly}
          />
        ))}
      </div>
    </div>
  );
}
