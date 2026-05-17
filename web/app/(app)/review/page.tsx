"use client";
import { useEffect, useState, useMemo } from "react";
import { Switch } from "@/components/ui/switch";
import { CheckCheck } from "lucide-react";
import { WBSTree } from "@/app/components/review/WBSTree";
import { ReviewCard } from "@/app/components/review/ReviewCard";
import type { WBSNode, ReviewItem } from "@/lib/types";

export default function HumanReviewPage() {
  const [wbs, setWbs] = useState<WBSNode | null>(null);
  const [cards, setCards] = useState<ReviewItem[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [onlyUnconfirmed, setOnlyUnconfirmed] = useState(true);

  useEffect(() => {
    fetch("/api/mock/review")
      .then((r) => r.json())
      .then(({ wbs, cards }) => {
        setWbs(wbs);
        setCards(cards);
      });
  }, []);

  const visibleCards = useMemo(() => {
    let filtered = cards;
    if (onlyUnconfirmed) filtered = filtered.filter((c) => c.status === "unconfirmed");
    if (selectedNodeId) {
      const collect = (n: WBSNode | null): string[] => {
        if (!n) return [];
        if (n.type === "work_package") return [n.id];
        return (n.children || []).flatMap(collect);
      };
      const find = (n: WBSNode | null, id: string): WBSNode | null => {
        if (!n) return null;
        if (n.id === id) return n;
        for (const c of n.children || []) {
          const f = find(c, id);
          if (f) return f;
        }
        return null;
      };
      const node = find(wbs, selectedNodeId);
      const wpIds = collect(node);
      if (wpIds.length > 0) filtered = filtered.filter((c) => wpIds.includes(c.ai_mapped_wp_id));
    }
    return filtered;
  }, [cards, wbs, selectedNodeId, onlyUnconfirmed]);

  const totalUnconfirmed = cards.filter((c) => c.status === "unconfirmed").length;

  const handleConfirm = (id: string) => {
    setCards((cs) => cs.map((c) => c.id === id ? { ...c, status: "confirmed" as const } : c));
  };

  const handleRemap = (id: string, newWpId: string, newPath: string) => {
    setCards((cs) => cs.map((c) => c.id === id ? { ...c, ai_mapped_wp_id: newWpId, ai_mapped_path: newPath, confidence: 1.0 } : c));
  };

  const handleConfirmAll = () => {
    setCards((cs) => cs.map((c) => c.confidence >= 0.8 && c.status === "unconfirmed" ? { ...c, status: "confirmed" as const } : c));
  };

  if (!wbs) return <div className="px-6 py-10 text-ink-light">Loading...</div>;

  return (
    <div className="flex flex-col">
      <div className="mx-auto w-full max-w-screen-2xl px-6 py-8 md:px-10">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-lavender-text">
            / 03 — Human Review
          </span>
          <span className="h-px w-8 bg-border" />
          <span className="font-mono text-[11px] uppercase tracking-wider text-ink-light">
            확신도 낮은 매핑 검토
          </span>
        </div>
        <h1 className="mt-6 font-display text-h3 text-ink">
          작업 물량 Mapping
        </h1>
        <p className="mt-2 text-body-sm text-ink-mid">
          좌측 WBS 트리에서 공종을 선택하거나, 검색 입력·드래그앤드롭으로 매핑을 수정·확정합니다.
        </p>
      </div>

      <section className="mx-auto w-full max-w-screen-2xl px-6 pb-20 md:px-10">
        <div className="grid grid-cols-12 gap-4 items-stretch">
          <div className="col-span-12 md:col-span-4 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col lg:h-[calc(100vh-260px)]">
            <WBSTree root={wbs} selectedId={selectedNodeId} onSelect={setSelectedNodeId} onDrop={(cardId, wpId) => {
              const collectPath = (n: WBSNode | null, id: string, path: string[] = []): string[] | null => {
                if (!n) return null;
                const next = [...path, n.name];
                if (n.id === id) return next;
                for (const c of n.children || []) { const r = collectPath(c, id, next); if (r) return r; }
                return null;
              };
              const path = collectPath(wbs, wpId)?.join(" > ") || "";
              handleRemap(cardId, wpId, path);
            }} />
          </div>

          <div className="col-span-12 md:col-span-8 rounded-card border border-border-soft bg-card shadow-xs flex flex-col lg:h-[calc(100vh-260px)]">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border-soft shrink-0">
              <div className="flex items-center gap-2">
                <Switch checked={onlyUnconfirmed} onCheckedChange={setOnlyUnconfirmed} />
                <span className="text-xs font-medium text-ink">신규 확정 필요만 보기</span>
              </div>
              <div className="font-mono text-xs text-ink-mid">
                {visibleCards.filter((c) => c.status === "unconfirmed").length} / {totalUnconfirmed}
              </div>
            </div>

            <div className="flex flex-col gap-3 p-4 flex-1 overflow-y-auto">
              {visibleCards.map((c) => (
                <ReviewCard key={c.id} item={c} wbsRoot={wbs} onConfirm={handleConfirm} onRemap={handleRemap} />
              ))}
              {visibleCards.length === 0 && (
                <div className="rounded-card border border-dashed border-border-soft py-12 text-center text-sm text-ink-light">
                  표시할 항목이 없습니다.
                </div>
              )}
            </div>

            <div className="px-4 py-3 border-t border-border-soft flex justify-end shrink-0">
              <button
                type="button"
                onClick={handleConfirmAll}
                className="inline-flex items-center gap-1.5 rounded-md bg-mint px-4 py-2 text-xs font-semibold text-white hover:bg-mint-text transition-colors"
              >
                <CheckCheck className="h-4 w-4" strokeWidth={2.5} />
                모두 AI 추천대로 확정 (확신도 ≥ 0.8)
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
