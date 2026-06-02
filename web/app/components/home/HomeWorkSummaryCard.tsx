import { Building2, Users, Truck, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import type { HomeWorkRow, HomeWorkSummary, HomeWorkBrief } from "@/lib/types";

interface Props {
  rows: HomeWorkRow[];
  workSummary: HomeWorkSummary;
  brief: HomeWorkBrief;
}

/**
 * 작업내용 — 제출 업체별 작업 행(통합작업일보 기반) 스크롤 테이블.
 *   외부 헤더: 제목 + 총 투입 인원·장비
 *   컬럼: 공종 · 업체 · 작업내용(요약) · 인원 · 장비
 *   행이 많아(≈제출 업체 수) 카드 내부 세로 스크롤 (sticky 헤더).
 */
export function HomeWorkSummaryCard({ rows, workSummary, brief }: Props) {
  // 인원 내림차순 정렬 (표시용 — 원본 불변)
  const sorted = [...rows].sort((a, b) => b.workers - a.workers);
  return (
    <div className="flex flex-col xl:h-full">
      {/* 블록 밖 헤더 */}
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-display text-h5 text-ink">오늘 작업내용</h2>
        <div className="flex items-center gap-4">
          <Stat icon={<Building2 className="h-4 w-4" />} label="총 업체" value={rows.length} unit="개" />
          <span className="h-6 w-px bg-border-soft" />
          <Stat icon={<Users className="h-4 w-4" />} label="총 투입 인원" value={workSummary.total_workers} unit="명" />
          <span className="h-6 w-px bg-border-soft" />
          <Stat icon={<Truck className="h-4 w-4" />} label="투입 장비" value={workSummary.total_equipment} unit="대" />
        </div>
      </div>

      {/* AI 동별 작업 요약 (FAB·CUB) */}
      <div className="mb-3 rounded-card border border-border-soft bg-surface-soft/50 px-4 py-3">
        <div className="mb-2 inline-flex items-center gap-1.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-brand-text">
          <Sparkles className="h-3.5 w-3.5" />
          AI 작업 요약
        </div>
        <ul className="space-y-1.5 text-xs leading-relaxed text-ink-mid">
          <li className="flex gap-2">
            <span className="mt-px shrink-0 rounded bg-brand-light px-1.5 font-mono text-[10px] font-semibold text-brand-text">FAB</span>
            <span>{brief.fab}</span>
          </li>
          <li className="flex gap-2">
            <span className="mt-px shrink-0 rounded bg-mint-light px-1.5 font-mono text-[10px] font-semibold text-mint-text">CUB</span>
            <span>{brief.cub}</span>
          </li>
        </ul>
      </div>

      {/* 테이블 카드 — 내부 스크롤 (제출 업체 수만큼 행) */}
      <div className="overflow-hidden rounded-card border border-border-soft bg-card shadow-xs xl:min-h-0 xl:flex-1">
        <div className="max-h-[19rem] overflow-y-auto xl:max-h-none xl:h-full">
          <table className="w-full text-xs">
            <thead className="sticky top-0 z-10 bg-surface-soft">
              <tr>
                <Th className="w-[10%]">Area</Th>
                <Th className="w-[11%]">공종</Th>
                <Th className="w-[19%]">업체</Th>
                <Th>작업내용(요약)</Th>
                <Th className="w-[9%] text-right">인원</Th>
                <Th className="w-[9%] text-right">장비</Th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, i) => (
                <tr key={i} className="border-t border-border-soft transition-colors hover:bg-surface-soft/40">
                  <td className="px-5 py-2.5">
                    <span
                      className={cn(
                        "inline-flex rounded px-1.5 font-mono text-[10px] font-semibold",
                        r.work_area === "FAB" ? "bg-brand-light text-brand-text" : "bg-mint-light text-mint-text",
                      )}
                    >
                      {r.work_area}
                    </span>
                  </td>
                  <td className="px-5 py-2.5 font-medium text-ink-mid">{r.trade}</td>
                  <td className="px-5 py-2.5 font-medium text-ink">{r.bp_name}</td>
                  <td className="px-5 py-2.5 text-ink-mid">{r.work_content}</td>
                  <td className="px-5 py-2.5 text-right font-display tabular-nums text-ink">
                    {r.workers}
                    <span className="ml-0.5 text-xs text-ink-light">명</span>
                  </td>
                  <td className="px-5 py-2.5 text-right font-display tabular-nums text-ink">
                    {r.equipment}
                    <span className="ml-0.5 text-xs text-ink-light">대</span>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-10 text-center text-ink-light">
                    오늘 접수된 작업일보가 없습니다
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th
      className={cn(
        "px-5 py-2.5 text-left font-mono text-[11px] font-medium uppercase tracking-wider text-ink-light",
        className,
      )}
    >
      {children}
    </th>
  );
}

function Stat({ icon, label, value, unit }: { icon: React.ReactNode; label: string; value: number; unit: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-ink-light">{icon}</span>
      <span className="text-xs text-ink-mid">{label}</span>
      <span className="font-display text-h6 tabular-nums text-ink">
        {value.toLocaleString()}
        <span className="ml-0.5 text-xs font-normal text-ink-light">{unit}</span>
      </span>
    </div>
  );
}
