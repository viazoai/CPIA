export const dynamic = "force-dynamic";

import { Layers, Calendar, Clock4, Activity } from "lucide-react";
import { loadReal } from "@/lib/fixtures";
import { StatusHeader } from "@/app/components/home/StatusHeader";
import { OpsKpiCard } from "@/app/components/home/OpsKpiCard";
import { AgentWorkflow } from "@/app/components/home/AgentWorkflow";
import { AgentChatLog } from "@/app/components/tasks/AgentChatLog";

export default async function HomePage() {
  const summary = await loadReal("sites_summary");
  const agents = await loadReal("agent_status");
  const chatByDate = await loadReal("chat_sequence");
  const latestDate = Object.keys(chatByDate).sort().pop() ?? "";
  const chat = chatByDate[latestDate] ?? [];

  /* 현재 처리 중 = 7 Agent active_count 합 (LIVE 인상) */
  const processingNow = agents.reduce((sum, a) => sum + a.active_count, 0);

  return (
    <div className="mx-auto max-w-screen-2xl px-6 py-10 md:px-10 md:py-14">
      <StatusHeader lastUpdated={summary.last_updated} />

      {/* Ops KPI 4 */}
      <section className="mt-8 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <OpsKpiCard
          tone="brand"
          icon={<Layers className="h-4 w-4" />}
          label="누적 처리"
          value={summary.total_processed.toLocaleString()}
          unit="건"
          description="시스템 런칭 이후"
        />
        <OpsKpiCard
          tone="mint"
          icon={<Calendar className="h-4 w-4" />}
          label="오늘 처리"
          value={summary.today_count.toLocaleString()}
          unit="건"
          description="자정 이후 입수 일보"
        />
        <OpsKpiCard
          tone="sun"
          icon={<Clock4 className="h-4 w-4" />}
          label="누적 절감"
          value={summary.total_hours_saved_cum.toLocaleString()}
          unit="h"
          description="2,506h → 351h 월평균"
        />
        <OpsKpiCard
          tone="sky"
          icon={<Activity className="h-4 w-4" />}
          label="현재 처리 중"
          value={processingNow.toString()}
          unit="건"
          description="7 Agent active 합산"
          live
        />
      </section>

      {/* Agent + HIL 세로 워크플로우 + Agent Chat Log */}
      <section className="mt-10 grid grid-cols-12 gap-6">
        <div className="col-span-12 xl:col-span-8">
          <AgentWorkflow agents={agents} />
        </div>
        <div className="col-span-12 xl:relative xl:col-span-4">
          <div className="flex h-[720px] flex-col overflow-hidden rounded-card-lg border border-border bg-card xl:absolute xl:inset-0 xl:h-auto">
            <AgentChatLog messages={chat} />
          </div>
        </div>
      </section>
    </div>
  );
}
