import { AlertCircle } from "lucide-react";
import { KpiStrip, type KpiItem } from "../reports/KpiStrip";
import type { HomeProcessing, HomeUnsubmittedCompany } from "@/lib/types";

interface Props {
  processing: HomeProcessing;
  unsubmitted: HomeUnsubmittedCompany[];
}

/**
 * 처리 현황 — Dashboard/Reports 와 동일한 공용 KpiStrip 재사용.
 *   상단: 생산성 현황(생산성·최적화 공사기간) / "제출 현황" + 제출·미제출 / 미제출 칩 /
 *         처리 현황(누적, QHD 전용 — 처리완료·절감시간).
 *   (처리중은 표시 생략 — 제출 = 처리완료 + 처리중 으로 함의)
 */
export function HomeProcessingSection({ processing, unsubmitted }: Props) {
  // 생산성 현황 — Report 9/24 site 지표를 그대로 노출.
  const prodGap = processing.productivity_today - 100;
  const productivity: KpiItem[] = [
    { label: "생산성", value: processing.productivity_today.toLocaleString(), unit: "%", sub: `목표 대비 ${prodGap >= 0 ? "+" : ""}${prodGap.toFixed(1)}% (9/24 기준)`, tone: "primary" },
    { label: "최적화 공사기간", value: processing.recovery_days.toLocaleString(), unit: "일", sub: "AI 최적화 시 단축 가능", tone: "primary" },
  ];
  const processed: KpiItem[] = [
    { label: "처리완료", value: processing.completed_cum.toLocaleString(), unit: "건", sub: "AI 파이프라인 누적 처리", tone: "primary" },
    { label: "절감시간", value: processing.hours_saved_cum.toLocaleString(), unit: "h", sub: `일 평균 ~${processing.hours_saved_per_day}h 절감`, tone: "primary" },
  ];
  const submission: KpiItem[] = [
    { label: "제출", value: `${processing.submitted} / ${processing.expected}`, unit: "업체", sub: "오늘 일보 제출 / 예정", tone: "normal" },
    { label: "미제출", value: `${processing.unsubmitted}`, unit: "업체", sub: "일보 미제출", tone: "risk" },
  ];

  return (
    <div className="flex h-full flex-col">
      {/* 생산성 현황 (최상단) — Report 9/24 site 지표 */}
      <div className="mb-3 flex items-baseline gap-2">
        <h2 className="font-display text-h5 text-ink">생산성 현황</h2>
        <span className="font-mono text-xs uppercase tracking-wider text-ink-light">
          9/24 기준
        </span>
      </div>
      <div className="flex-1 max-h-[12rem]">
        <KpiStrip items={productivity} columns={2} fill />
      </div>

      {/* 제출 현황 + 미제출 칩 */}
      <div className="mb-3 mt-5 flex items-baseline gap-2">
        <h2 className="font-display text-h5 text-ink">제출 현황</h2>
        <span className="font-mono text-xs uppercase tracking-wider text-ink-light">
          협력업체 일보 단위
        </span>
      </div>
      <div className="flex-1 max-h-[12rem]">
        <KpiStrip items={submission} columns={2} fill />
      </div>

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
          {processing.unsubmitted > unsubmitted.length && (
            <span className="text-xs font-medium text-rose-text/80">
              외 {processing.unsubmitted - unsubmitted.length}개
            </span>
          )}
        </div>
      )}

      {/* Agent 처리 현황 (누적) — QHD 전용 (FHD 에서는 숨김) */}
      <div className="hidden qhd:flex qhd:flex-1 qhd:flex-col qhd:min-h-0">
        <div className="mb-3 mt-5 flex items-baseline gap-2">
          <h2 className="font-display text-h5 text-ink">처리 현황 (누적)</h2>
          <span className="font-mono text-xs uppercase tracking-wider text-ink-light">
            최근 1년
          </span>
        </div>
        <div className="flex-1 max-h-[12rem]">
          <KpiStrip items={processed} columns={2} fill />
        </div>
      </div>
    </div>
  );
}
