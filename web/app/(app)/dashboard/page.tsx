"use client";
import { useEffect, useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PerformanceTab } from "@/app/components/dashboard/PerformanceTab";
import { ImpactTab } from "@/app/components/dashboard/ImpactTab";
import type { Site } from "@/lib/types";
import type { DashboardFixture } from "@/lib/fixtures";

export default function DashboardPage() {
  const [sites, setSites] = useState<Site[]>([]);
  const [dashboard, setDashboard] = useState<DashboardFixture | null>(null);

  useEffect(() => {
    fetch("/api/mock/dashboard")
      .then((r) => r.json())
      .then(({ sites, dashboard }) => { setSites(sites); setDashboard(dashboard); });
  }, []);

  if (!dashboard) return <div className="px-6 py-10 text-ink-light">Loading...</div>;

  return (
    <div className="flex flex-col">
      <div className="mx-auto w-full max-w-screen-2xl px-6 py-8 md:px-10">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-brand-text">
            / 05 — Dashboard · Fleet
          </span>
          <span className="h-px w-8 bg-border" />
          <span className="font-mono text-[11px] uppercase tracking-wider text-ink-light">
            Top Mgmt 전용
          </span>
        </div>
        <h1 className="mt-6 font-display text-h3 text-ink">
          전사 현장 모니터링
        </h1>
        <p className="mt-2 text-body-sm text-ink-mid">
          현장별 카드를 클릭하면 해당 현장의 상세 대시보드로 이동합니다.
        </p>
      </div>

      <section className="mx-auto w-full max-w-screen-2xl px-6 pb-20 md:px-10">
        <Tabs defaultValue="performance" className="w-full">
          <TabsList className="w-fit">
            <TabsTrigger value="performance">Performance</TabsTrigger>
            <TabsTrigger value="impact">Impact</TabsTrigger>
          </TabsList>
          <TabsContent value="performance" className="mt-6">
            <PerformanceTab sites={sites} fleetKpi={dashboard.performance.fleet_kpi} />
          </TabsContent>
          <TabsContent value="impact" className="mt-6">
            <ImpactTab
              scope="fleet"
              summary={dashboard.impact.fleet_kpi}
              distribution={dashboard.impact.site_distribution}
              trend={dashboard.impact.monthly_trend}
            />
          </TabsContent>
        </Tabs>
      </section>
    </div>
  );
}
