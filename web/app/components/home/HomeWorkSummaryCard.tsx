import { Users, Truck } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RawDataRow, HomeWorkSummary } from "@/lib/types";

interface Props {
  rows: RawDataRow[];
  workSummary: HomeWorkSummary;
}

/** 공종별 배지 톤 — 색은 디자인 토큰 팔레트 내에서. */
const TRADE_TONE: Record<string, string> = {
  골조: "bg-brand-light text-brand-text",
  마감: "bg-sun-light text-sun-text",
  토공사: "bg-peach-light text-peach-text",
  MEP: "bg-sky-light text-sky-text",
};
const TRADE_FALLBACK = "bg-surface-soft text-ink-mid";

/**
 * 작업내용 — 처리현황과 동일하게 헤더를 블록 밖으로.
 *   외부 헤더: 제목 + 처리완료 건수(좌) · 총 투입 인원·장비(우)
 *   카드: 협력업체별 테이블 (업체·공종·작업내용·인원). 장비는 컬럼 없이 총 대수만.
 */
export function HomeWorkSummaryCard({ rows, workSummary }: Props) {
  return (
    <div>
      {/* 블록 밖 헤더 */}
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <h2 className="font-display text-h5 text-ink">오늘 작업내용</h2>
          <span className="font-mono text-xs uppercase tracking-wider text-ink-light">
            처리완료 {rows.length}건
          </span>
        </div>
        <div className="flex items-center gap-4">
          <Stat icon={<Users className="h-4 w-4" />} label="총 투입 인원" value={workSummary.total_workers} unit="명" />
          <span className="h-6 w-px bg-border-soft" />
          <Stat icon={<Truck className="h-4 w-4" />} label="투입 장비" value={workSummary.total_equipment} unit="대" />
        </div>
      </div>

      {/* 테이블 카드 */}
      <div className="overflow-hidden rounded-card border border-border-soft bg-card shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-body-sm">
            <thead className="bg-surface-soft/60">
              <tr>
                <Th className="w-[18%]">업체</Th>
                <Th className="w-[14%]">공종</Th>
                <Th>작업내용</Th>
                <Th className="w-[10%] text-right">인원</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-border-soft transition-colors hover:bg-surface-soft/40">
                  <td className="px-5 py-3 font-medium text-ink">{r.bp_name}</td>
                  <td className="px-5 py-3">
                    <span
                      className={cn(
                        "inline-flex rounded-md px-2 py-0.5 text-xs font-medium",
                        TRADE_TONE[r.trade] ?? TRADE_FALLBACK,
                      )}
                    >
                      {r.trade}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-ink-mid">{r.work_content}</td>
                  <td className="px-5 py-3 text-right font-display tabular-nums text-ink">
                    {r.workers}
                    <span className="ml-0.5 text-xs text-ink-light">명</span>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-5 py-10 text-center text-ink-light">
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
        {value}
        <span className="ml-0.5 text-xs font-normal text-ink-light">{unit}</span>
      </span>
    </div>
  );
}
