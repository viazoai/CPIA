"use client";
import { useEffect, useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ReportDailyList } from "../components/reports/ReportDailyList";
import { KpiStrip, type KpiItem } from "../components/reports/KpiStrip";
import { ForecastTab } from "../components/reports/ForecastTab";
import { OptimizeTab } from "../components/reports/OptimizeTab";
import { RawDataTab } from "../components/reports/RawDataTab";
import type { ReportDetail } from "@/lib/fixtures";
import type { ReportDaily } from "@/lib/types";

export default function ReportPage() {
  const [daily, setDaily] = useState<ReportDaily[]>([]);
  const [details, setDetails] = useState<Record<string, ReportDetail>>({});
  const [selectedDate, setSelectedDate] = useState<string>("2026-05-15");

  useEffect(() => {
    fetch("/api/mock/report")
      .then((r) => r.json())
      .then((d) => { setDaily(d.daily); setDetails(d.details); });
  }, []);

  if (!details[selectedDate]) {
    return <div className="px-6 py-10 text-ink-light">Loading...</div>;
  }
  const detail = details[selectedDate];

  const kpi: KpiItem[] = [
    { label: "현재 생산성", value: `${detail.kpi.productivity_today}`, unit: "%", sub: `이력 ${detail.kpi.productivity_history_diff > 0 ? "+" : ""}${detail.kpi.productivity_history_diff}%`, tone: detail.kpi.productivity_today < 90 ? "rose" : "mint" },
    { label: "현 추세 공기", value: `D+${detail.kpi.delay_days}`, unit: "일 지연", sub: detail.kpi.expected_completion, tone: "rose" },
    { label: "회복 가능 생산성", value: `+${detail.kpi.recoverable_productivity}`, unit: "%p", sub: `${detail.kpi.target_productivity}% 도달`, tone: "lavender" },
    { label: "최적화 후 공기", value: `-${detail.kpi.recovery_days}`, unit: "일 회복", sub: detail.kpi.recovered_completion, tone: "mint" },
  ];

  return (
    <div className="flex flex-col">
      <div className="mx-auto w-full max-w-wrap px-6 py-8 md:px-10">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-lavender-text">
            / 04 — Report
          </span>
          <span className="h-px w-8 bg-border" />
          <span className="font-mono text-[11px] uppercase tracking-wider text-ink-light">
            일별 진단 · 만회 시나리오 · 원본 데이터
          </span>
        </div>
        <h1 className="mt-6 font-display text-3xl font-bold tracking-tight text-ink">
          현장 일일 진단 보고서
        </h1>
      </div>

      <section className="mx-auto w-full max-w-wrap px-6 pb-20 md:px-10">
        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-12 md:col-span-3">
            <div className="rounded-card border border-border-soft bg-card shadow-xs overflow-hidden">
              <ReportDailyList daily={daily} selectedDate={selectedDate} onSelect={setSelectedDate} />
            </div>
          </div>

          <div className="col-span-12 md:col-span-9 flex flex-col gap-4">
            <KpiStrip items={kpi} />
            <Tabs defaultValue="forecast" className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="forecast">Forecast</TabsTrigger>
                <TabsTrigger value="optimize">Optimize</TabsTrigger>
                <TabsTrigger value="raw">Raw Data</TabsTrigger>
              </TabsList>
              <TabsContent value="forecast" className="mt-4">
                <ForecastTab detail={detail} />
              </TabsContent>
              <TabsContent value="optimize" className="mt-4">
                <OptimizeTab detail={detail} />
              </TabsContent>
              <TabsContent value="raw" className="mt-4">
                <RawDataTab rows={detail.raw_data} />
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </section>
    </div>
  );
}
