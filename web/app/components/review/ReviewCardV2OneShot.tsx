"use client";
// 검토 카드 — 방식 2 (한 번에). HIL 검토의 실제 카드.
//   AI 가 추천한 공종(l6)을 현황으로 두되, 같은 분야(건축/토목)의 "후보 공종 전체"에
//   이미 적재된 작업종류(l7.5)를 공종별 접이식으로 펼친다. mapper 가 결정론으로 고른
//   (l6, l7.5) 와 일치하는 항목을 "AI 추천"으로 배지+맨위+기본선택. 항목을 고르면 그
//   항목의 l6+l7.5 로, '신규'면 AI 가 제안한 l7.5 로 그 공종 밑 새 적재.
//
//   선택은 onSelect 로 page 에 보고된다(모두 확정 시 corrections 구성). 후보 인벤토리는
//   page 가 1회 받아 inventory prop 으로 내려준다(카드별 fetch 폭주 방지).
import { useEffect, useMemo, useState } from "react";
import { Check, AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatReviewQuantity } from "@/lib/review-format";
import type { ReviewItem } from "@/lib/types";

export interface CardSelection {
  wa: string | null;
  l6_main: string | null;
  l7_5_activity: string | null;
}

interface Props {
  item: ReviewItem;
  inventory: Record<string, ReviewItem[]>;   // l5_disc(건축/토목) → 누적 적재 항목 (page 가 1회 fetch)
  onConfirm: (id: string) => void;
  onSelect: (cardId: string, sel: CardSelection) => void;
  selected?: boolean;
  onSelectCard?: (id: string) => void;
}

const NEW = "__NEW__";

export function ReviewCardV2OneShot({ item, inventory, onConfirm, onSelect, selected, onSelectCard }: Props) {
  const pathParts = (item.ai_mapped_path || "").split(" > ");
  const site = pathParts[0] ?? "";
  const disc = item.l5_disc ?? "";
  const aiPath = [site, item.wa ?? "", disc, item.l6_main ?? ""].filter(Boolean).join(" > ");
  // mapper 가 결정론으로 고른 (l6, l7.5) — 이 조합과 일치하는 기존 항목이 "AI 추천".
  const aiL6 = item.l6_main;
  const aiL75 = item.l7_5_activity ?? null;
  const isAi = (l6: string | null, l75: string) => !!aiL75 && l6 === aiL6 && l75 === aiL75;

  const [choice, setChoice] = useState<string | null>(null);     // 후보 항목 id | NEW | null
  const [open, setOpen] = useState<Set<string>>(() => new Set(item.l6_main ? [item.l6_main] : []));

  // 같은 분야 후보 공종 전체 — 카드 wa 가 있으면 그 wa 로, 없으면 분야 전체.
  const candidates = useMemo(() => {
    const pool = inventory[disc] ?? [];
    return item.wa ? pool.filter((x) => x.wa === item.wa) : pool;
  }, [inventory, disc, item.wa]);

  // l6(공종)별 그룹 — 현재 AI 공종 먼저, 그 다음 건수 많은 순. 그룹 안에선 AI 추천 l7.5 가 맨 위.
  const groups = useMemo(() => {
    const byL6 = new Map<string, ReviewItem[]>();
    for (const it of candidates) {
      const k = it.l6_main ?? "기타";
      const arr = byL6.get(k) ?? [];
      arr.push(it);
      byL6.set(k, arr);
    }
    return Array.from(byL6.entries())
      .map(([l6, its]) => {
        const ai = its.filter((x) => isAi(l6, x.work_content));
        const rest = its.filter((x) => !isAi(l6, x.work_content));
        return { l6, items: [...ai, ...rest] };
      })
      .sort((a, b) => {
        if (a.l6 === item.l6_main) return -1;
        if (b.l6 === item.l6_main) return 1;
        return b.items.length - a.items.length;
      });
  }, [candidates, item.l6_main, aiL6, aiL75]);

  // AI 추천 = 기본 선택(시각). 후보가 준비되면 AI 매칭 항목(없으면 신규)을 선택 표시만 한다.
  // 사용자가 이미 고른 경우(prev !== null) 덮지 않는다. onSelect 보고는 사용자 클릭에서만(아래 choose).
  useEffect(() => {
    setChoice((prev) => {
      if (prev !== null) return prev;
      const aiCand = aiL75 ? candidates.find((c) => c.l6_main === aiL6 && c.work_content === aiL75) : undefined;
      return aiCand ? aiCand.id : NEW;
    });
  }, [candidates, aiL6, aiL75]);

  const selFrom = (val: string): CardSelection => {
    if (val === NEW) return { wa: item.wa, l6_main: item.l6_main, l7_5_activity: aiL75 };
    const c = candidates.find((x) => x.id === val);
    return c ? { wa: c.wa, l6_main: c.l6_main, l7_5_activity: c.work_content }
             : { wa: item.wa, l6_main: item.l6_main, l7_5_activity: aiL75 };
  };

  const choose = (val: string) => {
    setChoice(val);
    onSelect(item.id, selFrom(val));   // 사용자 선택을 page 로 보고 (모두 확정 시 corrections).
  };

  const toggle = (l6: string) =>
    setOpen((prev) => { const n = new Set(prev); n.has(l6) ? n.delete(l6) : n.add(l6); return n; });

  return (
    <div
      data-card-anchor={item.id}
      onClick={() => onSelectCard?.(item.id)}
      className={cn(
        "rounded-card border bg-card p-4 shadow-xs border-sun/30",
        selected && "ring-2 ring-brand/50 border-brand"
      )}
    >
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-sun" />
          <span className="font-mono text-xs uppercase tracking-wider text-sun-text font-bold">미확정</span>
          <span className="ml-1 font-semibold text-sm text-ink">{item.bp_name}</span>
        </div>
        <span className="font-mono text-xs font-semibold text-ink-mid">
          {formatReviewQuantity(item.quantity)} {item.unit}
        </span>
      </div>

      <p className="mt-2 text-sm italic text-ink-mid leading-snug">
        &ldquo;{item.work_content}&rdquo;
      </p>

      {/* AI 추천 공종 (현황) */}
      <div className="mt-3 flex items-center gap-2 text-xs">
        <span className="text-ink-light">AI 추천:</span>
        <span className="font-semibold text-ink">{aiPath}</span>
        <span className={cn(
          "ml-auto rounded-sm px-1.5 py-0.5 text-xs font-mono font-bold",
          item.confidence >= 0.8 ? "bg-mint-light text-mint-text" : item.confidence >= 0.7 ? "bg-sky-light text-sky-text" : "bg-sun-light text-sun-text"
        )}>
          {Math.round(item.confidence * 100)}%
        </span>
      </div>

      {/* 후보 공종 전체 — 공종별 접이식 + 신규 */}
      <div className="mt-3 rounded-md bg-surface-soft p-2" onClick={(e) => e.stopPropagation()}>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-[11px] font-mono uppercase tracking-wider text-ink-light">
            기존 적재 항목 · {candidates.length}건
          </span>
          <span className="text-[10px] text-ink-light">{disc} 후보 공종 전체</span>
        </div>

        <div className="flex max-h-72 flex-col gap-1 overflow-y-auto pr-1">
          {groups.map((g) => {
            const isOpen = open.has(g.l6);
            const isCur = g.l6 === item.l6_main;
            return (
              <div key={g.l6} className="rounded-md border border-border bg-white">
                <button
                  type="button"
                  onClick={() => toggle(g.l6)}
                  className={cn(
                    "flex w-full items-center gap-1.5 px-2 py-1.5 text-left text-xs font-semibold",
                    isCur ? "text-brand-text" : "text-ink"
                  )}
                >
                  {isOpen ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
                  <span className="flex-1 truncate">{g.l6}{isCur ? " (AI 추천 공종)" : ""}</span>
                  <span className="shrink-0 font-mono text-[10px] text-ink-light">{g.items.length}건</span>
                </button>
                {isOpen && (
                  <div className="flex flex-col gap-1 border-t border-border-soft p-1.5">
                    {g.items.map((ex) => {
                      const on = choice === ex.id;
                      return (
                        <button
                          key={ex.id}
                          type="button"
                          onClick={() => choose(ex.id)}
                          className={cn(
                            "flex items-center gap-2 rounded-md border px-2 py-1 text-left text-[11px] transition-colors",
                            on ? "border-brand bg-brand-light/40 text-brand-text" : "border-transparent bg-surface-soft text-ink-mid hover:border-brand/40"
                          )}
                        >
                          <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full border", on ? "border-brand bg-brand" : "border-ink-light")} />
                          <span className="flex-1 truncate font-medium">{ex.work_content}</span>
                          {isAi(g.l6, ex.work_content) && (
                            <span className="shrink-0 rounded-sm bg-brand px-1 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white">AI 추천</span>
                          )}
                          <span className="shrink-0 font-mono text-[10px] text-ink-light">
                            {formatReviewQuantity(ex.quantity)} {ex.unit}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}

          {/* 신규 */}
          <button
            type="button"
            onClick={() => choose(NEW)}
            className={cn(
              "flex items-center gap-2 rounded-md border px-2 py-1.5 text-left text-xs transition-colors",
              choice === NEW ? "border-mint bg-mint-light/40 text-mint-text" : "border-dashed border-border bg-white text-ink-mid hover:border-mint/50"
            )}
          >
            <span className={cn("h-3 w-3 shrink-0 rounded-full border", choice === NEW ? "border-mint bg-mint" : "border-ink-light")} />
            <span className="flex-1 font-semibold">
              신규 — 기존에 없는 새 작업{item.l6_main ? ` (${item.l6_main})` : ""}
            </span>
          </button>
        </div>
      </div>

      {/* 확정 */}
      <div className="mt-3 flex items-center justify-end gap-2">
        <button
          type="button"
          disabled={choice === null}
          onClick={(e) => { e.stopPropagation(); onConfirm(item.id); }}
          className={cn(
            "inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-xs font-semibold text-white transition-colors",
            choice === null ? "bg-ink-light/40 cursor-not-allowed" : "bg-brand hover:bg-brand-text"
          )}
        >
          <Check className="h-3.5 w-3.5" strokeWidth={2.5} />
          확정
        </button>
      </div>
    </div>
  );
}
