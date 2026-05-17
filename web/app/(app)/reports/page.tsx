"use client";
import { useEffect, useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { ReportDailyList } from "@/app/components/reports/ReportDailyList";
import { KpiStrip, type KpiItem } from "@/app/components/reports/KpiStrip";
import { GapKpiCard } from "@/app/components/reports/GapKpiCard";
import { RecoveryEtaCard } from "@/app/components/reports/RecoveryEtaCard";
import { OptimizerResult } from "@/app/components/reports/OptimizerResult";
import { QuadrantCountKpi } from "@/app/components/reports/QuadrantCountKpi";
import { RawDataTab } from "@/app/components/reports/RawDataTab";
import { SpiBandChart } from "@/app/components/charts/SpiBandChart";
import { BarChartH } from "@/app/components/charts/BarChartH";
import { QuadrantScatter } from "@/app/components/charts/QuadrantScatter";
import { diagnose } from "@/lib/diagnosis";
import { toDiagnosisInput } from "@/lib/diagnosis-adapter";
import type { ReportDaily } from "@/lib/types";
import type { ReportDetail } from "@/lib/fixtures";

type Filter = "all" | "risk" | "caution" | "safe";

const REPORT_SITE_ID = "M15X-Ph3-IBL";

export default function ReportPage() {
  const [daily, setDaily] = useState<ReportDaily[]>([]);
  const [details, setDetails] = useState<Record<string, ReportDetail>>({});
  const [selectedDate, setSelectedDate] = useState<string>("2026-05-15");
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedWpId, setSelectedWpId] = useState<string | null>(null);
  const [rawOpen, setRawOpen] = useState(false);

  useEffect(() => {
    fetch("/api/mock/report")
      .then((r) => r.json())
      .then((d) => { setDaily(d.daily); setDetails(d.details); });
  }, []);

  useEffect(() => {
    const detail = details[selectedDate];
    if (!detail) return;
    const riskPoint = detail.quadrant.find((p) => p.quadrant === "risk");
    setSelectedWpId(riskPoint?.wp_id ?? detail.quadrant[0]?.wp_id ?? null);
  }, [selectedDate, details]);

  const detail = details[selectedDate];
  const diagnosis = useMemo(() => {
    if (!detail) return null;
    return diagnose(toDiagnosisInput(detail.kpi, detail.s_curve, REPORT_SITE_ID));
  }, [detail]);

  if (!detail || !diagnosis) {
    return <div className="px-6 py-10 text-ink-light">Loading...</div>;
  }

  const kpiRest: KpiItem[] = [
    { label: "현재 생산성", value: `${detail.kpi.productivity_today}`, unit: "%", sub: `이력 ${detail.kpi.productivity_history_diff > 0 ? "+" : ""}${detail.kpi.productivity_history_diff}%`, tone: detail.kpi.productivity_today < 90 ? "risk" : "normal" },
    { label: "현 추세 공기", value: `D+${detail.kpi.delay_days}`, unit: "일 지연", sub: detail.kpi.expected_completion, tone: "risk" },
    { label: "최적화 후 공기", value: `-${detail.kpi.recovery_days}`, unit: "일 회복", sub: detail.kpi.recovered_completion, tone: "normal" },
  ];

  const selectedWp = detail.quadrant.find((p) => p.wp_id === selectedWpId) ?? null;

  return (
    <div className="flex flex-col">
      <div className="mx-auto w-full max-w-screen-2xl border-b border-border-soft px-6 pt-10 pb-6 md:px-10 md:pt-14">
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          / 04 — Daily Report
        </span>
        <h1 className="mt-3 font-display text-h3 text-ink">
          현장 일일 진단 보고서
        </h1>
        <p className="mt-2 text-body-sm text-ink-mid">
          진단 · 시나리오 · 최적화 대상 · 원본 데이터를 한 흐름에서 확인합니다.
        </p>
      </div>

      <section className="mx-auto w-full max-w-screen-2xl px-6 pb-20 md:px-10">
        <div className="mt-6 grid grid-cols-12 gap-4">
          <div className="col-span-12 md:col-span-3">
            <div className="flex flex-col overflow-hidden rounded-card border border-border-soft bg-card shadow-xs lg:sticky lg:top-6 lg:h-[calc(100vh-220px)]">
              <ReportDailyList daily={daily} selectedDate={selectedDate} onSelect={setSelectedDate} />
            </div>
          </div>

          <div className="col-span-12 flex flex-col gap-10 md:col-span-9">
            <Section eyebrow="/ 01 — 현재 상태" title="KPI 스냅샷">
              <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                <SingleKpi item={kpiRest[0]} />
                <GapKpiCard
                  gap_pct={diagnosis.gap_pct}
                  z_score={diagnosis.z_score}
                  status={diagnosis.status}
                />
                <SingleKpi item={kpiRest[1]} />
                <SingleKpi item={kpiRest[2]} />
              </div>
            </Section>

            <Section eyebrow="/ 02 — 진단" title="이력 평균 대비 추세">
              <SpiBandChart diagnosis={diagnosis} />
            </Section>

            <Section eyebrow="/ 03 — 회복 시나리오 · 권고" title="시나리오 ETA + Optimizer">
              <div className="grid gap-4 md:grid-cols-2">
                <RecoveryEtaCard scenarios={diagnosis.scenarios} />
                <div>
                  <div className="mb-2 text-body-sm text-ink-mid">
                    {selectedWp ? (
                      <>선택된 WP: <span className="font-semibold text-ink">{selectedWp.wp_name}</span> <span className="text-ink-light">({selectedWp.trade})</span></>
                    ) : (
                      <>WP 미선택 — 아래 산점도에서 점을 클릭하세요</>
                    )}
                  </div>
                  <OptimizerResult output={detail.optimizer} />
                </div>
              </div>
            </Section>

            <Section eyebrow="/ 04 — 공정 분해" title="업체 · 공종 생산성">
              <div className="grid gap-4 md:grid-cols-2">
                <BarChartH items={detail.contractor_bars} title="업체별 생산성 (오늘 평균)" />
                <BarChartH items={detail.trade_bars} title="공종별 생산성 (오늘 평균)" />
              </div>
            </Section>

            <Section eyebrow="/ 05 — 최적화 대상" title="Impact × Productivity 산점도">
              <div className="grid grid-cols-12 gap-4">
                <div className="col-span-12 md:col-span-6">
                  <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
                    <QuadrantScatter
                      points={detail.quadrant}
                      selectedWpId={selectedWpId}
                      onSelect={setSelectedWpId}
                      filter={filter}
                    />
                    <div className="mt-3 text-center text-xs text-ink-light">
                      점 크기 = 잔여 물량. 좌상 = 고 Impact · 저 Productivity (위험군).
                    </div>
                  </div>
                </div>
                <div className="col-span-12 md:col-span-6">
                  <QuadrantCountKpi points={detail.quadrant} filter={filter} onFilterChange={setFilter} />
                </div>
              </div>
            </Section>

            <Section eyebrow="/ 06 — 원본 데이터" title="작업일보 매핑 결과">
              <button
                type="button"
                onClick={() => setRawOpen((v) => !v)}
                className="flex w-full items-center justify-between rounded-card border border-border-soft bg-card px-5 py-4 shadow-xs transition-shadow hover:shadow-sm"
                aria-expanded={rawOpen}
              >
                <span className="text-body-sm text-ink">
                  {rawOpen ? "원본 데이터 접기" : `원본 데이터 펼치기 · ${detail.raw_data.length} rows`}
                </span>
                <ChevronDown
                  className={`h-4 w-4 text-ink-mid transition-transform ${rawOpen ? "rotate-180" : ""}`}
                />
              </button>
              {rawOpen && (
                <div className="mt-3">
                  <RawDataTab rows={detail.raw_data} />
                </div>
              )}
            </Section>
          </div>
        </div>
      </section>
    </div>
  );
}

function Section({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          {eyebrow}
        </span>
        <h2 className="mt-1 font-display text-h5 text-ink">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function SingleKpi({ item }: { item: KpiItem }) {
  return <KpiStrip items={[item]} />;
}
