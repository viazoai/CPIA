"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { KpiStrip, type KpiItem } from "../../../components/reports/KpiStrip";
import { SCurveChart } from "../../../components/charts/SCurveChart";
import { BarChartH } from "../../../components/charts/BarChartH";
import { ImpactTab } from "../../../components/dashboard/ImpactTab";
import type { Site, MiddleOfficeAutomation, ImpactTrendPoint, SitesSummary } from "@/lib/types";
import type { ReportDetail } from "@/lib/fixtures";

interface SiteResponse {
  site: Site;
  detail: ReportDetail | null;
  perSiteAutomation: MiddleOfficeAutomation[];
  trend: ImpactTrendPoint[];
}

export default function SiteDashboardPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<SiteResponse | null>(null);

  useEffect(() => {
    fetch(`/api/mock/dashboard/${id}`).then((r) => r.json()).then(setData);
  }, [id]);

  if (!data) return <div className="px-6 py-10 text-ink-light">Loading...</div>;
  const { site, detail, perSiteAutomation, trend } = data;

  const perfKpi: KpiItem[] = [
    { label: "현재 생산성",  value: `${site.productivity_today}`, unit: "%", sub: "이력 대비",         tone: site.productivity_today < 90 ? "risk" : "normal" },
    { label: "현 추세 공기", value: site.delay_days > 0 ? `D+${site.delay_days}` : "정상", unit: site.delay_days > 0 ? "일 지연" : "", sub: site.expected_completion, tone: site.delay_days > 0 ? "risk" : "normal" },
    { label: "회복 가능 생산성", value: site.recovery_days > 0 ? `+${100 - site.productivity_today + site.recovery_days}` : "0", unit: "%p", sub: "Optimizer 목표", tone: "primary" },
    { label: "최적화 후 공기", value: site.recovery_days > 0 ? `-${site.recovery_days}` : "0", unit: "일 회복", sub: site.recovered_completion, tone: "normal" },
  ];

  const siteImpactSummary: SitesSummary = {
    today_count: 0, review_pending: 0, abnormal_count: site.abnormal_trades, last_updated: "",
    total_hours_saved: site.hours_saved, total_fte_saved: site.fte_saved,
    total_headcount: site.headcount, total_hours: site.total_hours,
    ai_replacement_rate: site.ai_replacement_rate, yearly_saving: 0,
  };

  return (
    <div className="flex flex-col">
      <div className="mx-auto w-full max-w-wrap px-6 py-8 md:px-10">
        <Link href="/dashboard" className="inline-flex items-center gap-1 text-xs font-mono uppercase tracking-wider text-ink-light hover:text-lavender">
          <ChevronLeft className="h-3.5 w-3.5" />
          전사로 돌아가기
        </Link>
        <h1 className="mt-4 font-display text-h3 text-ink">{site.name}</h1>
        <p className="mt-1 text-body-sm text-ink-mid">{site.location} · Hi-tech · 현장 모니터링</p>
      </div>

      <section className="mx-auto w-full max-w-wrap px-6 pb-20 md:px-10">
        <Tabs defaultValue="performance" className="w-full">
          <TabsList className="w-fit">
            <TabsTrigger value="performance">Performance</TabsTrigger>
            <TabsTrigger value="impact">Impact</TabsTrigger>
          </TabsList>

          <TabsContent value="performance" className="mt-6 flex flex-col gap-6">
            <KpiStrip items={perfKpi} />
            {detail ? (
              <>
                <div className="rounded-card border border-border-soft bg-card p-5 shadow-xs">
                  <div className="mb-3 font-mono text-xs uppercase tracking-wider text-ink-light">
                    S-Curve · 4선 시나리오
                  </div>
                  <SCurveChart points={detail.s_curve} showRecovery />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <BarChartH items={detail.contractor_bars} title="업체별 생산성 (이력 평균)" />
                  <BarChartH items={detail.trade_bars} title="공종별 생산성 (이력 평균)" />
                </div>
              </>
            ) : (
              <div className="rounded-card border border-dashed border-border-soft py-12 text-center text-sm text-ink-light">
                이 현장의 상세 데이터는 다음 fixture 갱신 시 추가됩니다.
              </div>
            )}
          </TabsContent>

          <TabsContent value="impact" className="mt-6">
            <ImpactTab
              scope="site"
              summary={siteImpactSummary}
              distribution={[]}
              trend={trend}
              perFunction={perSiteAutomation}
            />
          </TabsContent>
        </Tabs>
      </section>
    </div>
  );
}
