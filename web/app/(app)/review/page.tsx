"use client";
import { useEffect, useState, useMemo } from "react";
import { Switch } from "@/components/ui/switch";
import { CheckCheck } from "lucide-react";
import { WBSTree } from "@/app/components/review/WBSTree";
import { ReviewCard } from "@/app/components/review/ReviewCard";
import { nodeToQuery } from "@/lib/review-node";
import type { WBSNode, ReviewItem } from "@/lib/types";

// WBS 트리에서 id 로 노드 탐색. visibleCards useMemo 와 registered lazy fetch effect 가 공용.
const find = (n: WBSNode | null, id: string): WBSNode | null => {
  if (!n) return null;
  if (n.id === id) return n;
  for (const c of n.children || []) {
    const f = find(c, id);
    if (f) return f;
  }
  return null;
};

export default function HumanReviewPage() {
  const [wbs, setWbs] = useState<WBSNode | null>(null);
  const [cards, setCards] = useState<ReviewItem[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [onlyUnconfirmed, setOnlyUnconfirmed] = useState(false);
  const [registered, setRegistered] = useState<ReviewItem[]>([]);
  const [registeredTotal, setRegisteredTotal] = useState(0);
  const [registeredError, setRegisteredError] = useState(false);
  const [confirmedNotice, setConfirmedNotice] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/mock/review")
      .then((r) => r.json())
      .then(({ wbs, cards }) => {
        setWbs(wbs);
        setCards(cards);
        setOnlyUnconfirmed(cards.length > 0);
      });
  }, []);

  // A4: 등록 모드(HIL off)에서 선택 노드의 누적 등록 작업을 노드 스코프로 lazy fetch.
  useEffect(() => {
    if (onlyUnconfirmed || !selectedNodeId || !wbs) {
      setRegistered([]);
      setRegisteredTotal(0);
      setRegisteredError(false);
      return;
    }
    const node = find(wbs, selectedNodeId);
    const q = nodeToQuery(node);
    if (!q) {
      setRegistered([]);
      setRegisteredTotal(0);
      return;
    }
    const params = new URLSearchParams({ wa: q.wa });
    if (q.l5) params.set("l5", q.l5);
    if (q.l6) params.set("l6", q.l6);
    let cancelled = false;
    setRegisteredError(false);
    fetch(`/api/mock/review/registered?${params}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => {
        if (!cancelled) {
          setRegistered(d.items ?? []);
          setRegisteredTotal(d.total ?? 0);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRegistered([]);
          setRegisteredError(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [onlyUnconfirmed, selectedNodeId, wbs]);

  // 노드 선택 시 직전 확정 알림을 비운다 (onlyUnconfirmed 토글은 deps 에서 제외 — handleConfirmAll 이 토글과 알림을 동시에 세트하므로 토글 변경으로 알림을 즉시 지우면 알림이 flash 없이 사라짐).
  useEffect(() => {
    setConfirmedNotice(null);
  }, [selectedNodeId]);

  const visibleCards = useMemo(() => {
    // 베이스: HIL 모드면 신규 카드, 등록 모드면 서버 노드-스코프 registered.
    let filtered = onlyUnconfirmed ? cards : registered;
    // selectedNode wp_id 필터는 HIL 모드에서만 — registered 는 서버가 노드 스코프로 줘서 중복 필터 X.
    if (onlyUnconfirmed) {
      filtered = filtered.filter((c) => c.status === "unconfirmed");
      if (selectedNodeId) {
        const collect = (n: WBSNode | null): string[] => {
          if (!n) return [];
          if (n.type === "work_package") return [n.id];
          return (n.children || []).flatMap(collect);
        };
        const node = find(wbs, selectedNodeId);
        const wpIds = collect(node);
        if (wpIds.length > 0) filtered = filtered.filter((c) => wpIds.includes(c.ai_mapped_wp_id));
      }
    }
    return filtered;
  }, [cards, registered, wbs, selectedNodeId, onlyUnconfirmed]);

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
    const n = cards.filter((c) => c.status === "unconfirmed").length;
    setCards((cs) => cs.map((c) => c.status === "unconfirmed" ? { ...c, status: "confirmed" as const } : c));
    // 미확정 0 도달 → 등록 모드로 자동 복귀 + 알림.
    setOnlyUnconfirmed(false);
    setConfirmedNotice(`${n}건 확정 완료`);
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
          WBS-작업 물량 관계 검토
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
                {!onlyUnconfirmed && selectedNodeId && registered.length > 0 && (
                  <span className="text-[11px] text-ink-light">총 {registeredTotal}건 중 최근 {registered.length}건</span>
                )}
                {confirmedNotice && <span className="text-[11px] font-semibold text-mint-text">{confirmedNotice}</span>}
                <span className="text-xs font-medium text-ink">신규 확정 필요만 보기</span>
                <Switch checked={onlyUnconfirmed} onCheckedChange={setOnlyUnconfirmed} />
              </div>
            </div>

            <div className="flex flex-col gap-3 p-4 flex-1 overflow-y-auto">
              {visibleCards.map((c) => (
                <ReviewCard key={c.id} item={c} wbsRoot={wbs} onConfirm={handleConfirm} onRemap={handleRemap} readOnly={!onlyUnconfirmed} />
              ))}
              {visibleCards.length === 0 && (
                <div className="rounded-card border border-dashed border-border-soft py-12 text-center text-sm text-ink-light">
                  {onlyUnconfirmed ? "검토할 신규 매핑이 없습니다."
                    : registeredError ? "등록 작업을 불러오지 못했습니다. 잠시 후 다시 시도하세요."
                    : !selectedNodeId ? "좌측에서 공종 또는 WP를 선택하면 누적 등록 작업을 볼 수 있습니다."
                    : "이 공종에 등록된 작업이 없습니다."}
                </div>
              )}
            </div>

            {onlyUnconfirmed && (
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
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
