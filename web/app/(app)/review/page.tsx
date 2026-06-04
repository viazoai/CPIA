"use client";
import { useEffect, useState, useMemo, useRef } from "react";
import { Switch } from "@/components/ui/switch";
import { CheckCheck } from "lucide-react";
import { WBSTree } from "@/app/components/review/WBSTree";
import { WpGroup } from "@/app/components/review/WpGroup";
import { ReviewConnector } from "@/app/components/review/ReviewConnector";
import { ReviewBoard } from "@/app/components/review/ReviewBoard";
import { groupCardsByWp, groupCardsByL7 } from "@/lib/review-group";
import { nodeToQuery } from "@/lib/review-node";
import type { WBSNode, ReviewItem } from "@/lib/types";

// WBS 트리에서 id 로 노드 탐색. registered lazy fetch effect 와 drag onDrop 핸들러가 사용.
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
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const [view, setView] = useState<"list" | "board">("list");
  const gridRef = useRef<HTMLDivElement>(null);

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
    const params = new URLSearchParams();
    if (q.wa) params.set("wa", q.wa);
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

  // HIL 은 cards 전체(확정 포함)를 (wa,l6) 그룹핑. 등록은 registered 를 l7(l7_sub) 그룹핑.
  const groups = useMemo(
    () => (onlyUnconfirmed ? groupCardsByWp(cards) : groupCardsByL7(registered)),
    [onlyUnconfirmed, cards, registered]
  );
  const selectedCard = useMemo(
    () => (onlyUnconfirmed ? cards : registered).find((c) => c.id === selectedCardId) ?? null,
    [onlyUnconfirmed, cards, registered, selectedCardId]
  );
  const connectorTone: "mint" | "sun" =
    selectedCard && selectedCard.status === "unconfirmed" && selectedCard.confidence < 0.8 ? "sun" : "mint";
  // Task 8: 선택 노드의 검토대기(요검토) 건수 — 누적(확정)은 requires_review=FALSE 만이라
  // 이 만큼이 아직 누적에 미반영(과소표시). 좌측 트리 요검토와 동일 review_count.
  const selectedPending = useMemo(
    () => (wbs && selectedNodeId ? (find(wbs, selectedNodeId)?.review_count ?? 0) : 0),
    [wbs, selectedNodeId],
  );
  // 연결선 재드로잉 nonce — 모드·그룹수·선택노드(트리 펼침/스크롤) 변할 때 bump.
  const [redrawKey, setRedrawKey] = useState(0);
  useEffect(() => {
    setRedrawKey((k) => k + 1);
  }, [onlyUnconfirmed, groups.length, selectedNodeId, selectedCardId]);

  // HIL: 트리 노드 선택 시 해당 WP 그룹으로 우측 스크롤 (필터 아님).
  //   deps 를 selectedNodeId 로 한정 — groups 참조 변경(확정 등)에 재발화하지 않게.
  //   그룹 DOM(data-wp-group) 을 직접 쿼리하므로 groups 클로저가 필요 없다.
  useEffect(() => {
    if (!onlyUnconfirmed || !selectedNodeId || !gridRef.current) return;
    const el = gridRef.current.querySelector(`[data-wp-group="${CSS.escape(selectedNodeId)}"]`);
    const fn = (el as HTMLElement | null)?.scrollIntoView;
    if (typeof fn === "function") fn.call(el, { block: "nearest", behavior: "smooth" });
  }, [onlyUnconfirmed, selectedNodeId]);

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
    const corrections: Record<string, { wa: string; l6_main: string; l7_5_activity?: string | null }> = {};
    for (const c of cards) {
      if (c.remapped && c.wa && c.l6_main) {
        // l6 재매핑 → 기존 l7.5 무효화(BE 에서 미분류 처리, D9)
        corrections[String(c.idx)] = { wa: c.wa, l6_main: c.l6_main, l7_5_activity: null };
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

  // 카드 선택 → 연결선 + 트리 자동 펼침/스크롤(해당 WP 노드).
  const handleSelectCard = (id: string) => {
    setSelectedCardId(id);
    const card = (onlyUnconfirmed ? cards : registered).find((c) => c.id === id);
    if (card) setSelectedNodeId(card.ai_mapped_wp_id);
  };
  // 확신도 0.8↑ 미확정만 일괄 확정 (저확신은 남김 → resume 보류).
  const handleConfirmHighConf = () => {
    setCards((cs) =>
      cs.map((c) =>
        c.status === "unconfirmed" && c.confidence >= 0.8 ? { ...c, status: "confirmed" as const } : c
      )
    );
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
        <div className="mt-3 inline-flex rounded-lg border border-border-soft bg-surface-soft p-0.5">
          <button
            type="button"
            onClick={() => setView("list")}
            className={view === "list" ? "rounded-md bg-card px-3 py-1 text-xs font-semibold text-ink shadow-xs" : "px-3 py-1 text-xs text-ink-light"}
          >
            리스트
          </button>
          <button
            type="button"
            onClick={() => setView("board")}
            className={view === "board" ? "rounded-md bg-card px-3 py-1 text-xs font-semibold text-ink shadow-xs" : "px-3 py-1 text-xs text-ink-light"}
          >
            보드
          </button>
        </div>
      </div>

      {view === "list" && (
      <section className="mx-auto w-full max-w-screen-2xl px-6 pb-20 md:px-10">
        <div ref={gridRef} className="relative grid grid-cols-12 gap-4 items-stretch">
          <ReviewConnector
            containerRef={gridRef}
            selectedCardId={selectedCardId}
            targetNodeId={selectedCard?.ai_mapped_wp_id ?? null}
            tone={connectorTone}
            redrawKey={redrawKey}
          />
          <div className="col-span-12 md:col-span-4 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col lg:h-[calc(100vh-260px)]">
            <WBSTree root={wbs} selectedId={selectedNodeId} onSelect={setSelectedNodeId} revealNodeId={selectedCard?.ai_mapped_wp_id ?? null} onDrop={(cardId, wpId) => {
              const collectPath = (n: WBSNode | null, id: string, path: string[] = []): string[] | null => {
                if (!n) return null;
                const next = [...path, n.name];
                if (n.id === id) return next;
                for (const c of n.children || []) { const r = collectPath(c, id, next); if (r) return r; }
                return null;
              };
              const path = collectPath(wbs, wpId)?.join(" > ") || "";
              handleRemap(cardId, wpId, path);
              setSelectedCardId(cardId);
            }} />
          </div>

          <div className="col-span-12 md:col-span-8 rounded-card border border-border-soft bg-card shadow-xs flex flex-col lg:h-[calc(100vh-260px)]">
            <div className="flex items-center justify-between px-5 py-3 border-b border-border-soft shrink-0">
              <span className="font-display text-h6 font-bold text-ink">작업물량</span>
              <div className="flex items-center gap-2">
                {!onlyUnconfirmed && selectedNodeId && registered.length > 0 && (
                  <span className="text-[11px] text-ink-light">확정 {registeredTotal}건{selectedPending > 0 ? ` · 검토대기 ${selectedPending}건` : ""}</span>
                )}
                {confirmedNotice && <span className="text-[11px] font-semibold text-mint-text">{confirmedNotice}</span>}
                <span className="text-xs font-medium text-ink">신규 확정 필요만 보기</span>
                <Switch checked={onlyUnconfirmed} onCheckedChange={setOnlyUnconfirmed} />
              </div>
            </div>

            <div className="flex flex-col gap-3 p-4 flex-1 overflow-y-auto">
              {groups.map((g) => (
                <WpGroup
                  key={g.wpId}
                  group={g}
                  selectedCardId={selectedCardId}
                  wbsRoot={wbs}
                  onConfirm={handleConfirm}
                  onRemap={handleRemap}
                  onSelectCard={handleSelectCard}
                  readOnly={!onlyUnconfirmed}
                />
              ))}
              {groups.length === 0 && (
                <div className="rounded-card border border-dashed border-border-soft py-12 text-center text-sm text-ink-light">
                  {onlyUnconfirmed ? "검토할 신규 매핑이 없습니다."
                    : registeredError ? "등록 작업을 불러오지 못했습니다. 잠시 후 다시 시도하세요."
                    : !selectedNodeId ? "좌측에서 공종 또는 WP를 선택하면 누적 등록 작업을 볼 수 있습니다."
                    : "이 공종에 등록된 작업이 없습니다."}
                </div>
              )}
            </div>

            {onlyUnconfirmed && (
              <div className="px-4 py-3 border-t border-border-soft flex justify-end gap-2 shrink-0">
                <button
                  type="button"
                  onClick={handleConfirmHighConf}
                  className="inline-flex items-center gap-1.5 rounded-md border border-mint bg-white px-4 py-2 text-xs font-semibold text-mint-text hover:bg-mint-light/30 transition-colors"
                >
                  <CheckCheck className="h-4 w-4" strokeWidth={2.5} />
                  확신도 0.8↑ 일괄 확정
                </button>
                <button
                  type="button"
                  onClick={handleConfirmAll}
                  className="inline-flex items-center gap-1.5 rounded-md bg-mint px-4 py-2 text-xs font-semibold text-white hover:bg-mint-text transition-colors"
                >
                  <CheckCheck className="h-4 w-4" strokeWidth={2.5} />
                  모두 확정
                </button>
              </div>
            )}
          </div>
        </div>
      </section>
      )}

      {view === "board" && (
        <section className="mx-auto w-full max-w-screen-2xl px-6 pb-10 md:px-10 h-[calc(100vh-220px)]">
          <div className="h-full rounded-card border border-border-soft bg-card overflow-hidden">
            <ReviewBoard
              wbs={wbs}
              cards={onlyUnconfirmed ? cards : registered}
              onConfirm={handleConfirm}
              onConfirmHighConf={handleConfirmHighConf}
              onConfirmAll={handleConfirmAll}
              onRemap={handleRemap}
            />
          </div>
        </section>
      )}
    </div>
  );
}
