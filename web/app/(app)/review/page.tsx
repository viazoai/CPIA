"use client";
import { useEffect, useState, useMemo, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Switch } from "@/components/ui/switch";
import { CheckCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { WBSTree } from "@/app/components/review/WBSTree";
import { WpGroup } from "@/app/components/review/WpGroup";
import { ReviewConnector } from "@/app/components/review/ReviewConnector";
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
  const router = useRouter();
  // '모두 확정' 후 Task 화면 복귀 확인 팝업.
  const [returnDialogOpen, setReturnDialogOpen] = useState(false);
  const [wbs, setWbs] = useState<WBSNode | null>(null);
  const [cards, setCards] = useState<ReviewItem[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [onlyUnconfirmed, setOnlyUnconfirmed] = useState(false);
  const [registered, setRegistered] = useState<ReviewItem[]>([]);
  const [registeredTotal, setRegisteredTotal] = useState(0);
  const [registeredError, setRegisteredError] = useState(false);
  const [confirmedNotice, setConfirmedNotice] = useState<string | null>(null);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  // HIL l6 picker: 카드별 l6 선택(모두 확정 corrections). 분야별 전체 l6 카탈로그는 wbs 파생(아래 useMemo).
  const [selections, setSelections] = useState<Record<string, { wa: string | null; l6_main: string | null; l7_5_activity: string | null }>>({});

  useEffect(() => {
    fetch("/api/mock/review")
      .then((r) => r.json())
      .then(({ wbs, cards }) => {
        setWbs(wbs);
        setCards(cards);
        // 최상위(root) 노드를 디폴트 선택 → 전체 목록이 보이도록(nodeToQuery: root=전체).
        setSelectedNodeId(wbs?.id ?? null);
        // '신규 검토 필요' 토글 디폴트 ON.
        setOnlyUnconfirmed(true);
      });
  }, []);

  // HIL l6 picker 4번째 옵션용 — 분야(건축/토목)별 전체 l6 카탈로그. WBS 트리에서 파생(추가 fetch 없음).
  //   트리: building > wa(trade) > l5(trade, id=`wa::l5`, name=분야) > work_package(l6). l6명 dedup.
  const l6CatalogByDisc = useMemo(() => {
    const map: Record<string, { wa: string | null; l6_main: string }[]> = {};
    const seen: Record<string, Set<string>> = {};
    const walk = (n: WBSNode | null, wa: string | null, disc: string | null) => {
      if (!n) return;
      let curWa = wa, curDisc = disc;
      if (n.type === "trade") {
        if (n.id.includes("::")) curDisc = n.name;
        else curWa = n.id;
      }
      if (n.type === "work_package" && curDisc) {
        const l6 = n.l6_main ?? n.name;
        (seen[curDisc] ??= new Set());
        if (!seen[curDisc].has(l6)) {
          seen[curDisc].add(l6);
          (map[curDisc] ??= []).push({ wa: n.wa ?? curWa, l6_main: l6 });
        }
      }
      (n.children || []).forEach((c) => walk(c, curWa, curDisc));
    };
    walk(wbs, null, null);
    return map;
  }, [wbs]);

  // 좌측 트리 경고(미확정 건수)는 live cards 에서 재계산 — 확정/재매핑 시 즉시 반영.
  //   WP 노드 review_count = 그 WP 로 매핑된 unconfirmed 카드 수, 상위 노드는 자식 합.
  //   (트리의 정적 review_count 는 fetch 시점 값이라 확정해도 안 바뀌어 경고가 남던 문제 수정)
  const wbsWithCounts = useMemo(() => {
    if (!wbs) return null;
    const pending = new Map<string, number>();
    for (const c of cards) {
      if (c.status === "unconfirmed") {
        pending.set(c.ai_mapped_wp_id, (pending.get(c.ai_mapped_wp_id) ?? 0) + 1);
      }
    }
    const rebuild = (n: WBSNode): WBSNode => {
      if (n.children && n.children.length > 0) {
        const children = n.children.map(rebuild);
        return { ...n, children, review_count: children.reduce((s, c) => s + c.review_count, 0) };
      }
      // 리프(work_package) — 직접 매핑된 미확정 카드 수
      return { ...n, review_count: pending.get(n.id) ?? 0 };
    };
    return rebuild(wbs);
  }, [wbs, cards]);

  // 카드별 l6 선택 보고 — 사용자가 바꾼 카드만 기록(미선택 카드는 BE 가 AI 매핑 수용).
  const handleCardSelect = useCallback(
    (cardId: string, sel: { wa: string | null; l6_main: string | null; l7_5_activity: string | null }) => {
      setSelections((s) => ({ ...s, [cardId]: sel }));
    },
    [],
  );

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

  // 좌측 트리 노드 선택 → 우측 카드 필터 (HIL 모드). 단방향: 트리 클릭만 필터를 바꾼다.
  //   nodeToQuery: building(root)→{null,null,null}=전체 · wa→{wa} · wa::l5→{wa,l5} · wp→{wa,l6}.
  //   M15X(root) 클릭 시 전체, CUB/FAB 클릭 시 그 동(棟)만, 공종(l6) 클릭 시 그 공종만.
  const filteredCards = useMemo(() => {
    if (!selectedNodeId || !wbs) return cards;
    const q = nodeToQuery(find(wbs, selectedNodeId));
    if (!q) return cards;
    return cards.filter((c) =>
      (q.wa == null || c.wa === q.wa) &&
      (q.l5 == null || c.l5_disc === q.l5) &&
      (q.l6 == null || c.l6_main === q.l6)
    );
  }, [selectedNodeId, wbs, cards]);

  // HIL 은 (필터된) cards 를 (wa,l6) 그룹핑. 등록은 registered 를 l7(l7_sub) 그룹핑.
  const groups = useMemo(
    () => (onlyUnconfirmed ? groupCardsByWp(filteredCards) : groupCardsByL7(registered)),
    [onlyUnconfirmed, filteredCards, registered]
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
    () => (wbsWithCounts && selectedNodeId ? (find(wbsWithCounts, selectedNodeId)?.review_count ?? 0) : 0),
    [wbsWithCounts, selectedNodeId],
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
    // corrections: 사용자가 AI 추천과 다르게 고른 카드만 전송(idx 키 = mapper_activities.idx).
    //   - oneshot 선택(selections): 기존 항목 선택 → 그 {wa,l6,l7.5}, 신규 → AI l7.5 그대로.
    //   - AI 추천 그대로인 카드(selections 미기록 or AI 기본값과 동일)는 미전송 → BE 가 AI 매핑 수용(= AI 추천 일괄 적용).
    //   - 구 remap(트리 드래그)도 흡수: c.remapped 면 그 wa/l6 + l7.5 무효화.
    const corrections: Record<string, { wa: string | null; l6_main: string; l7_5_activity?: string | null }> = {};
    for (const c of cards) {
      const sel = selections[c.id];
      if (sel && sel.l6_main) {
        const sameAsAi =
          (sel.wa ?? null) === (c.wa ?? null) &&
          (sel.l6_main ?? null) === (c.l6_main ?? null) &&
          (sel.l7_5_activity ?? null) === (c.l7_5_activity ?? null);
        if (!sameAsAi) corrections[String(c.idx)] = { wa: sel.wa, l6_main: sel.l6_main, l7_5_activity: sel.l7_5_activity ?? null };
      } else if (c.remapped && c.l6_main) {
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
    // 확정·재개 후 Task 화면 복귀 여부를 묻는 팝업 표시.
    setReturnDialogOpen(true);
  };

  // 카드 선택 → 연결선 + 트리 자동 펼침/스크롤(revealNodeId=selectedCard).
  //   필터(selectedNodeId)는 건드리지 않는다 — 좌측→우측 단방향 필터 유지(카드 클릭이 우측을 1건으로 좁히지 않게).
  const handleSelectCard = (id: string) => {
    setSelectedCardId(id);
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
    <div className="flex flex-col lg:h-[calc(100vh-4rem)] lg:overflow-hidden">
      <div className="mx-auto w-full max-w-screen-2xl border-b border-border-soft px-6 pt-10 pb-6 md:px-10 md:pt-14 shrink-0">
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

      <section className="mx-auto w-full max-w-screen-2xl px-6 pt-4 pb-8 md:px-10 flex-1 min-h-0">
        <div ref={gridRef} className="relative grid grid-cols-12 gap-4 items-stretch h-full">
          <ReviewConnector
            containerRef={gridRef}
            selectedCardId={selectedCardId}
            targetNodeId={selectedCard?.ai_mapped_wp_id ?? null}
            tone={connectorTone}
            redrawKey={redrawKey}
          />
          <div className="col-span-12 md:col-span-4 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col min-h-0 lg:h-full">
            <WBSTree root={wbsWithCounts ?? wbs} selectedId={selectedNodeId} onSelect={setSelectedNodeId} revealNodeId={selectedCard?.ai_mapped_wp_id ?? null} onDrop={(cardId, wpId) => {
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

          <div className="col-span-12 md:col-span-8 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col min-h-0 lg:h-full">
            <div className="flex items-center justify-between px-5 py-3 border-b border-border-soft shrink-0">
              <span className="font-display text-h6 font-bold text-ink">작업물량</span>
              <div className="flex items-center gap-2">
                {!onlyUnconfirmed && selectedNodeId && registered.length > 0 && (
                  <span className="text-[11px] text-ink-light">확정 {registeredTotal}건{selectedPending > 0 ? ` · 검토대기 ${selectedPending}건` : ""}</span>
                )}
                {confirmedNotice && <span className="text-[11px] font-semibold text-mint-text">{confirmedNotice}</span>}
                <span className="text-xs font-medium text-ink">신규 검토 필요</span>
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
                  l6CatalogByDisc={l6CatalogByDisc}
                  onCardSelect={handleCardSelect}
                />
              ))}
              {groups.length === 0 && (
                <div className="rounded-card border border-dashed border-border-soft py-12 text-center text-sm text-ink-light">
                  {onlyUnconfirmed
                    ? (selectedNodeId ? "이 공종에는 검토할 항목이 없습니다. (좌측 최상위 노드 클릭 시 전체)" : "검토할 신규 매핑이 없습니다.")
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

      {/* 모두 확정 → Task 화면 복귀 확인 팝업. 확인 시 /tasks 로 이동, 취소 시 현재 화면 유지. */}
      <Dialog open={returnDialogOpen} onOpenChange={setReturnDialogOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold tracking-tight text-ink">
              Task 화면으로 돌아가시겠습니까?
            </DialogTitle>
            <DialogDescription className="text-sm text-ink-mid">
              매핑 검토를 모두 확정했습니다. 작업 처리 현황(Task) 화면으로 이동합니다.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setReturnDialogOpen(false)}
              className="h-9"
            >
              취소
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => router.push("/tasks")}
              className="h-9"
            >
              확인
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
