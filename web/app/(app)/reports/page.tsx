"use client";
import { useEffect, useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { ReportDailyList } from "@/app/components/reports/ReportDailyList";
import { KpiStrip, type KpiItem } from "@/app/components/reports/KpiStrip";
import { GapKpiCard } from "@/app/components/reports/GapKpiCard";
import { OptimizerResult } from "@/app/components/reports/OptimizerResult";
import { QuadrantCountKpi } from "@/app/components/reports/QuadrantCountKpi";
import { RawDataTab } from "@/app/components/reports/RawDataTab";
import { WPSummaryTable, STATUS_DOT, STATUS_LABEL, recoveryDays } from "@/app/components/reports/WPSummaryTable";
import { ForecastChart } from "@/app/components/charts/ForecastChart";
import { ProductivityBarToggle } from "@/app/components/reports/ProductivityBarToggle";
import { ProductivityTrendChart } from "@/app/components/charts/ProductivityTrendChart";
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
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedWpId, setSelectedWpId] = useState<string | null>(null);
  const [rawOpen, setRawOpen] = useState(false);

  useEffect(() => {
    fetch("/api/mock/report")
      .then((r) => r.json())
      .then((d) => {
        setDaily(d.daily);
        setDetails(d.details);
        if (d.daily.length > 0) setSelectedDate(d.daily[0].date);
      });
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

  const wpNameById = useMemo(() => {
    if (!detail) return {};
    return Object.fromEntries(detail.wp_summary.map((w) => [w.wp_id, w.wp_name]));
  }, [detail]);

  if (!detail || !diagnosis) {
    return <div className="px-6 py-10 text-ink-light">Loading...</div>;
  }

  const kpiRest: KpiItem[] = [
    { label: "현재 생산성", value: `${detail.kpi.productivity_today}`, unit: "%", sub: `이력 ${detail.kpi.productivity_history_diff > 0 ? "+" : ""}${detail.kpi.productivity_history_diff}%`, tone: detail.kpi.productivity_today < 90 ? "risk" : "normal" },
    { label: "현 추세 공기", value: `D+${detail.kpi.delay_days}`, unit: "일 지연", sub: detail.kpi.expected_completion, tone: "risk" },
    { label: "회복 후 공기", value: `-${detail.kpi.recovery_days}`, unit: "일 회복", sub: detail.kpi.recovered_completion, tone: "normal" },
  ];

  // § 3 4분면 필터 → WP 리스트 필터 (safe ↔ normal 매핑)
  const filterToStatus: Record<Filter, "normal" | "caution" | "risk" | "all"> = {
    all: "all",
    risk: "risk",
    caution: "caution",
    safe: "normal",
  };
  const wpStatusFilter = filterToStatus[filter];
  const filteredWpRows =
    wpStatusFilter === "all"
      ? detail.wp_summary
      : detail.wp_summary.filter((w) => w.status === wpStatusFilter);

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
          생산성 분석을 기반으로 한 리스크 검토 및 예측 시나리오를 통해 공사기간 최적화를 제안합니다. 
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

            <Section eyebrow="/ 01 — 생산성 지표" title="현장 생산성 진단">
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
              <ProductivityTrendChart
                siteId={REPORT_SITE_ID}
                todayValue={detail.kpi.productivity_today}
                endDate={selectedDate}
              />
              <ProductivityBarToggle
                contractorBars={detail.contractor_bars}
                tradeBars={detail.trade_bars}
                historyMean={detail.kpi.target_productivity}
                date={selectedDate}
              />
            </Section>

            <Section eyebrow="/ 02 — 4분면 산점도" title="리스크 및 대안 검토">
              <div className="grid grid-cols-12 items-stretch gap-4">
                {/* 좌측: 산점도 + 테이블 (세로 stack, 마지막 자식 flex-1 로 컬럼 끝까지) */}
                <div className="col-span-12 flex h-full flex-col gap-3 md:col-span-6">
                  <QuadrantCountKpi points={detail.quadrant} filter={filter} onFilterChange={setFilter} />
                  <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
                    <div className="mb-2 font-display text-h6 text-ink">Impact × Productivity 분포도</div>
                    <QuadrantScatter
                      points={detail.quadrant}
                      selectedWpId={selectedWpId}
                      onSelect={setSelectedWpId}
                      filter={filter}
                    />
                  </div>
                  <div className="flex-1">
                    <WPSummaryTable
                      rows={filteredWpRows}
                      selectedWpId={selectedWpId}
                      onSelect={setSelectedWpId}
                    />
                  </div>
                </div>

                {/* 우측: 진단 결과 (단일 박스, 항목별 구분선) */}
                <div className="col-span-12 flex h-full flex-col gap-3 md:col-span-6">
                  <div className="rounded-card border border-border-soft bg-card px-4 py-3 shadow-xs">
                    {(() => {
                      const wpRow = detail.wp_summary.find((w) => w.wp_id === selectedWpId);
                      if (!wpRow) {
                        return (
                          <div className="text-body-sm text-ink-mid">
                            WP 미선택 — 산점도에서 점을 클릭하세요
                          </div>
                        );
                      }
                      const days = recoveryDays(wpRow.productivity, wpRow.baseline, wpRow.impact);
                      return (
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-body-sm">
                            <span className="font-semibold text-ink">{wpRow.wp_name}</span>
                            <span className="ml-2 text-ink-light">({wpRow.trade})</span>
                          </div>
                          <div className="flex items-center gap-4">
                            <span className="text-[12px] text-ink-mid">
                              공기 단축{" "}
                              {days > 0 ? (
                                <span className="font-semibold text-mint-text">-{days}일</span>
                              ) : (
                                <span className="text-ink-light">—</span>
                              )}
                            </span>
                            <span className="inline-flex items-center gap-1.5">
                              <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[wpRow.status]}`} />
                              <span className="text-[10px] font-semibold text-ink-mid">
                                {STATUS_LABEL[wpRow.status]}
                              </span>
                            </span>
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                  <div className="flex-1">
                    <OptimizerResult output={detail.optimizer} />
                  </div>
                </div>
              </div>
            </Section>

            <Section eyebrow="/ 03 — 공정률 추세" title="공기 단축 예측 시나리오">
              <ForecastChart
                diagnosis={diagnosis}
                recoveryActive={selectedWpId !== null}
              />
            </Section>

            <Section eyebrow="/ 04 — 원본 데이터" title="작업일보 상세">
              <button
                type="button"
                onClick={() => setRawOpen((v) => !v)}
                className="flex w-full items-center justify-between rounded-card border border-border-soft bg-card px-5 py-4 shadow-xs transition-shadow hover:shadow-sm"
                aria-expanded={rawOpen}
              >
                <span className="text-body-sm text-ink">
                  {rawOpen ? "원본 데이터 접기" : `원본 데이터 펼치기 · 작업일보 ${detail.raw_data.length} rows`}
                </span>
                <ChevronDown
                  className={`h-4 w-4 text-ink-mid transition-transform ${rawOpen ? "rotate-180" : ""}`}
                />
              </button>
              {rawOpen && (
                <div className="mt-3">
                  <RawDataTab
                    rows={detail.raw_data}
                    filterWpId={selectedWpId}
                    wpNameById={wpNameById}
                  />
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
  subtitle,
  children,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          {eyebrow}
        </span>
        <h2 className="mt-1 font-display text-h5 text-ink">{title}</h2>
        {subtitle && (
          <p className="mt-0.5 text-body-sm text-ink-mid">{subtitle}</p>
        )}
      </div>
      {children}
    </section>
  );
}

function SingleKpi({ item }: { item: KpiItem }) {
  return <KpiStrip items={[item]} />;
}
