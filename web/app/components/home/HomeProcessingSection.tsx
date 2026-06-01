import { AlertCircle } from "lucide-react";
import { KpiStrip, type KpiItem } from "../reports/KpiStrip";
import type { HomeProcessing, HomeUnsubmittedCompany } from "@/lib/types";

interface Props {
  processing: HomeProcessing;
  unsubmitted: HomeUnsubmittedCompany[];
}

/**
 * 처리 현황 — Dashboard/Reports 와 동일한 공용 KpiStrip(KPI 블록 그리드) 재사용.
 *   상단: 5개 KPI 카드(제출 / 처리완료 / 처리중 / 미제출 / 오늘 절감)
 *   하단: 미제출 업체 슬림 행 (행동 정보 — 클릭 없이 노출)
 */
export function HomeProcessingSection({ processing, unsubmitted }: Props) {
  const kpi: KpiItem[] = [
    { label: "제출", value: `${processing.submitted} / ${processing.expected}`, unit: "업체", sub: "오늘 일보 제출 / 예정", tone: "normal" },
    { label: "처리완료", value: `${processing.completed}`, unit: "건", sub: "AI 파이프라인 처리 완료", tone: "primary" },
    { label: "처리중", value: `${processing.in_progress}`, unit: "건", sub: "AI 처리 진행 중", tone: "caution" },
    { label: "미제출", value: `${processing.unsubmitted}`, unit: "업체", sub: "일보 미제출", tone: "risk" },
    { label: "오늘 절감", value: `~${processing.hours_saved_today}`, unit: "h", sub: "수작업 대비 절감", tone: "primary" },
  ];

  return (
    <div>
      <div className="mb-3 flex items-baseline gap-2">
        <h2 className="font-display text-h5 text-ink">오늘 처리 현황</h2>
        <span className="font-mono text-xs uppercase tracking-wider text-ink-light">
          협력업체 일보 단위
        </span>
      </div>

      <KpiStrip items={kpi} />

      {unsubmitted.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-card border border-border-soft bg-card px-4 py-3 shadow-xs">
          <span className="inline-flex items-center gap-1.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-rose-text">
            <AlertCircle className="h-3.5 w-3.5" />
            미제출 업체
          </span>
          <span className="h-3.5 w-px bg-border-soft" />
          {unsubmitted.map((c) => (
            <span
              key={`${c.trade}-${c.name}`}
              className="inline-flex items-center gap-1.5 rounded-full bg-rose-light px-2.5 py-1 text-xs"
            >
              <span className="font-mono text-[10px] uppercase tracking-wider text-rose-text/70">
                {c.trade}
              </span>
              <span className="font-medium text-rose-text">{c.name}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
