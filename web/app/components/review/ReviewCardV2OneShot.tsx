"use client";
// 검토 카드 — scope-1: l6(공종) picker (HIL 역할 = l6 매칭).
//   기존 매핑 리랭크(Chroma cosine 유사도) 후보를 그대로 차용 — distinct l6 유사도 순 top-3.
//   · 매핑 경로(site > WA > 분야 > l6) + AI 후보 유사도% (후보 행 %와 동일 출처)
//   · top-3 l6 후보(유사도 칩) + AI 추천 배지/자동선택
//   · 4번째 "다른 공종에서 선택 (분야)" → 같은 분야 전체 l6 카탈로그 펼침(수동)
//   · 하단 전체 승인(page) → AI 추천 l6 일괄
//   적재 매칭(신규/누적)은 (업체,l6,이름,scope) 정확일치로 백엔드 분리 — 카드는 l6 만 정한다.
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
  l6CatalogByDisc: Record<string, { wa: string | null; l6_main: string }[]>;  // 분야(건축/토목) → 전체 l6
  onConfirm: (id: string) => void;
  onSelect: (cardId: string, sel: CardSelection) => void;
  selected?: boolean;
  onSelectCard?: (id: string) => void;
}

const TOP_N = 3;

export function ReviewCardV2OneShot({ item, l6CatalogByDisc, onConfirm, onSelect, selected, onSelectCard }: Props) {
  const pathParts = (item.ai_mapped_path || "").split(" > ");
  const site = pathParts[0] ?? "";
  const disc = item.l5_disc ?? "";
  const aiL6 = item.l6_main;
  const aiPath = [site, item.wa ?? "", disc, aiL6 ?? ""].filter(Boolean).join(" > ");

  // 리랭크(유사도) distinct l6 후보 — route l6_candidates (유사도 desc). top-3 노출.
  const candidates = item.l6_candidates ?? [];
  const top = candidates.slice(0, TOP_N);
  const aiCand = candidates.find((c) => c.is_ai);
  // 매핑 옆 % = AI 후보의 유사도 (후보 행 %와 동일 출처). 후보 없으면 mapping_conf fallback.
  const aiSim = aiCand ? aiCand.score : item.confidence;

  // 4번째 옵션: 같은 분야 전체 l6 중 top 에 없는 나머지 (l6명 dedup, 가나다).
  const moreL6s = useMemo(() => {
    const topSet = new Set(candidates.slice(0, TOP_N).map((c) => c.l6_main));
    const seen = new Set<string>();
    return (l6CatalogByDisc[disc] ?? [])
      .filter((x) => !topSet.has(x.l6_main))
      .filter((x) => { if (seen.has(x.l6_main)) return false; seen.add(x.l6_main); return true; })
      .sort((a, b) => a.l6_main.localeCompare(b.l6_main));
  }, [l6CatalogByDisc, disc, item.l6_candidates]);

  const [choice, setChoice] = useState<string | null>(null);  // 선택된 l6_main
  const [expandMore, setExpandMore] = useState(false);

  // AI 추천 기본 선택(시각). 사용자 클릭에서만 onSelect 보고(미클릭 카드는 BE 가 AI 매핑 수용).
  useEffect(() => {
    setChoice((prev) => (prev !== null ? prev : aiL6 ?? top[0]?.l6_main ?? null));
  }, [aiL6]);

  const choose = (l6: string) => {
    setChoice(l6);
    onSelect(item.id, {
      // 공종(l6)만 바꾼다 — 동(wa)은 활동이 발생한 곳(item.wa)으로 유지(공종 변경이 동을 옮기지 않음).
      wa: item.wa,
      l6_main: l6,
      // l6 가 AI 와 다르면 기존 l7.5 무효화(BE 미분류 → 적재 매칭이 재판단). 같으면 AI l7.5 유지.
      l7_5_activity: l6 === aiL6 ? (item.l7_5_activity ?? null) : null,
    });
  };

  const simChip = (score: number) => (
    <span className="shrink-0 rounded-md bg-sky-light px-1.5 py-0.5 text-[11px] font-bold text-sky-text">
      유사도 {Math.round(score * 100)}%
    </span>
  );

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
      <p className="mt-2 text-sm italic text-ink-mid leading-snug">&ldquo;{item.work_content}&rdquo;</p>

      {/* 매핑 경로 (site > WA > 분야 > l6) + AI 후보 유사도 (후보 행 %와 동일 출처) */}
      <div className="mt-3 flex items-center gap-2 text-xs">
        <span className="text-ink-light">매핑:</span>
        <span className="font-semibold text-ink truncate">{aiPath}</span>
        <span className="ml-auto">{simChip(aiSim)}</span>
      </div>

      {/* 공종(l6) 선택 */}
      <div className="mt-3 rounded-md bg-surface-soft p-2" onClick={(e) => e.stopPropagation()}>
        <div className="mb-1.5 text-[11px] font-mono uppercase tracking-wider text-ink-light">
          공종(l6) 선택 — 유사도 순
        </div>

        <div className="flex flex-col gap-1">
          {top.map((c) => {
            const on = choice === c.l6_main;
            // AI 추천 행: 강조(배지 + 유사도% + 틴트). 나머지 후보: plain(아래 '다른 공종' 목록과 동일 폰트/색).
            if (c.is_ai) {
              return (
                <button
                  key={c.l6_main}
                  type="button"
                  onClick={() => choose(c.l6_main)}
                  className={cn(
                    "flex items-center gap-2 rounded-md border px-2 py-2 text-left text-xs font-semibold transition-colors",
                    on ? "border-brand bg-brand-light/40 text-brand-text ring-1 ring-brand/40" : "border-brand/60 bg-brand-light/20 text-brand-text"
                  )}
                >
                  <span className={cn("h-3 w-3 shrink-0 rounded-full border", on ? "border-brand bg-brand" : "border-brand/60")} />
                  <span className="flex-1 truncate">{c.l6_main}</span>
                  <span className="shrink-0 rounded-sm bg-brand px-1 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white">AI 추천</span>
                  {simChip(c.score)}
                </button>
              );
            }
            return (
              <button
                key={c.l6_main}
                type="button"
                onClick={() => choose(c.l6_main)}
                className={cn(
                  "flex items-center gap-2 rounded-md border bg-white px-2 py-1 text-left text-[11px] transition-colors",
                  on ? "border-brand ring-1 ring-brand/40 text-brand-text" : "border-transparent text-ink-mid hover:border-brand/40"
                )}
              >
                <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full border", on ? "border-brand bg-brand" : "border-ink-light")} />
                <span className="flex-1 truncate font-medium">{c.l6_main}</span>
                {/* 비-AI 후보: 유사도% 는 보이되 무채색·작게(평범) → AI 추천이 상대적으로 강조됨 */}
                <span className="shrink-0 font-mono text-[10px] text-ink-light">유사도 {Math.round(c.score * 100)}%</span>
              </button>
            );
          })}

          {/* 4번째: 다른 공종에서 선택 (분야) */}
          {moreL6s.length > 0 && (
            <button
              type="button"
              onClick={() => setExpandMore((v) => !v)}
              className="flex items-center gap-1.5 rounded-md border border-dashed border-border bg-white px-2 py-1.5 text-left text-xs text-ink-mid hover:border-brand/40"
            >
              {expandMore ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
              <span className="flex-1 font-semibold">다른 공종에서 선택{disc ? ` (${disc})` : ""}</span>
            </button>
          )}
          {expandMore && (
            <div className="flex max-h-56 flex-col gap-1 overflow-y-auto rounded-md border border-border bg-white p-1">
              {moreL6s.map((x) => {
                const on = choice === x.l6_main;
                return (
                  <button
                    key={x.l6_main}
                    type="button"
                    onClick={() => choose(x.l6_main)}
                    className={cn(
                      "flex items-center gap-2 rounded-md border bg-white px-2 py-1 text-left text-[11px] transition-colors",
                      on ? "border-brand ring-1 ring-brand/40 text-brand-text" : "border-transparent text-ink-mid hover:border-brand/40"
                    )}
                  >
                    <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full border", on ? "border-brand bg-brand" : "border-ink-light")} />
                    <span className="flex-1 truncate font-medium">{x.l6_main}</span>
                  </button>
                );
              })}
            </div>
          )}
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
