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

  // work_package wp_id → {wa, l6_main} 룩업. wp_id=safe(wa)-safe(l6_main) 는 역변환 lossy 라
  // remap 시 WBS 노드가 들고 있는 원 wa/l6_main 을 찾아 BE corrections 로 정확히 전달한다.
  const wpIdToWaL6 = useMemo(() => {
    const m = new Map<string, { wa: string | null; l6_main: string | null }>();
    const walk = (n: WBSNode | null) => {
      if (!n) return;
      if (n.type === "work_package") m.set(n.id, { wa: n.wa ?? null, l6_main: n.l6_main ?? null });
      (n.children || []).forEach(walk);
    };
    walk(wbs);
    return m;
  }, [wbs]);

  const handleConfirm = (id: string) => {
    setCards((cs) => cs.map((c) => c.id === id ? { ...c, status: "confirmed" as const } : c));
  };

  const handleRemap = (id: string, newWpId: string, newPath: string) => {
    const wl = wpIdToWaL6.get(newWpId);
    setCards((cs) => cs.map((c) => c.id === id ? {
      ...c,
      ai_mapped_wp_id: newWpId,
      ai_mapped_path: newPath,
      wa: wl?.wa ?? c.wa,
      l6_main: wl?.l6_main ?? c.l6_main,
      confidence: 1.0,
      remapped: true,            // AI 추천과 다르게 수정됨 → corrections 전송 대상
    } : c));
  };

  const handleConfirmAll = () => {
    // 게이트: 검토 대상(저확신) 전부를 확정한다 — 하나도 빠짐없이 처리돼야 다음 단계로 넘어간다.
    // 미확정 카드는 AI 추천대로 일괄 확정(개별 수정한 카드는 그 결정 유지 → corrections).
    setCards((cs) => cs.map((c) => c.status === "unconfirmed" ? { ...c, status: "confirmed" as const } : c));
    // 사용자가 수정(remap)한 카드만 corrections 로 BE 전달(idx 키 = mapper_activities.idx).
    // 수정 안 한 요검토 항목은 BE hil_1_node 가 AI 매핑 그대로 확정(corrections 불필요).
    const corrections: Record<string, { wa: string; l6_main: string }> = {};
    for (const c of cards) {
      if (c.remapped && c.wa && c.l6_main) {
        corrections[String(c.idx)] = { wa: c.wa, l6_main: c.l6_main };
      }
    }
    fetch("/api/hil/resume", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ corrections }),
    })
      .then((r) => r.json())
      .then((d) => console.log("[hil/resume]", d))
      .catch((e) => console.error("[hil/resume] 실패", e));
  };

  if (!wbs) return <div className="px-6 py-10 text-ink-light">Loading...</div>;

  return (
    <div className="flex flex-col">
      <div className="mx-auto w-full max-w-screen-2xl border-b border-border-soft px-6 pt-10 pb-6 md:px-10 md:pt-14">
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          / 03 — Human Review
        </span>
        <h1 className="mt-3 font-display text-h3 text-ink">
          WBS-작업 물량 Mapping
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
            <div className="flex items-center justify-between px-5 py-3 border-b border-border-soft shrink-0">
              <span className="font-display text-h6 font-bold text-ink">작업물량</span>
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-ink">신규 확정 필요만 보기</span>
                <Switch checked={onlyUnconfirmed} onCheckedChange={setOnlyUnconfirmed} />
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
