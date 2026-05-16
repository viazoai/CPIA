"use client";
import { useCallback } from "react";
import { useSimulation } from "@/lib/use-simulation";
import { Activity, ClipboardCheck, AlertTriangle, RefreshCw } from "lucide-react";
import type { SitesSummary } from "@/lib/types";

interface Props {
  summary: SitesSummary;
}

export function NowStrip({ summary }: Props) {
  const todayUpdater = useCallback(
    (n: number) => {
      const delta = Math.random() > 0.5 ? 1 : -1;
      const next = n + delta;
      return next < summary.today_count - 3 || next > summary.today_count + 3
        ? summary.today_count
        : next;
    },
    [summary.today_count],
  );
  const todayCount = useSimulation(summary.today_count, todayUpdater, 5000);

  const tickUpdater = useCallback((t: string) => {
    const [h, m] = t.split(":").map(Number);
    const tm = h * 60 + m + 1;
    return `${String(Math.floor(tm / 60)).padStart(2, "0")}:${String(tm % 60).padStart(2, "0")}`;
  }, []);
  const lastUpdated = useSimulation(summary.last_updated, tickUpdater, 60000);

  return (
    <section className="relative mx-auto max-w-wrap px-6 md:px-10">
      <div className="rounded-2xl border border-white/10 bg-white/[0.04] backdrop-blur-md p-6 shadow-[0_0_60px_-30px_rgba(124,92,255,0.4)]">
        <div className="mb-5 flex items-center gap-2">
          <span className="relative inline-flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
          </span>
          <span className="font-mono text-xs uppercase tracking-wider text-white/50">
            NOW · 현재 운영 현황
          </span>
        </div>
        <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
          <NowItem icon={<Activity className="h-3.5 w-3.5" />}        tone="violet" label="오늘 처리"    value={`${todayCount}건`} />
          <NowItem icon={<ClipboardCheck className="h-3.5 w-3.5" />}  tone="amber"  label="Review 대기" value={`${summary.review_pending}건`} />
          <NowItem icon={<AlertTriangle className="h-3.5 w-3.5" />}   tone="rose"   label="이상 공종"    value={`${summary.abnormal_count}건`} />
          <NowItem icon={<RefreshCw className="h-3.5 w-3.5" />}       tone="mint"   label="마지막 갱신" value={lastUpdated} />
        </div>
      </div>
    </section>
  );
}

function NowItem({
  icon, tone, label, value,
}: {
  icon: React.ReactNode;
  tone: "violet" | "amber" | "rose" | "mint";
  label: string;
  value: string;
}) {
  const iconClass = {
    violet: "text-[#a78bfa] bg-[#7c5cff]/15 ring-[#7c5cff]/25",
    amber:  "text-amber-300 bg-amber-400/15 ring-amber-400/25",
    rose:   "text-rose-300 bg-rose-400/15 ring-rose-400/25",
    mint:   "text-emerald-300 bg-emerald-400/15 ring-emerald-400/25",
  }[tone];
  return (
    <div className="flex items-center gap-3">
      <span className={`inline-flex h-10 w-10 items-center justify-center rounded-lg ring-1 ${iconClass}`}>
        {icon}
      </span>
      <div className="min-w-0">
        <div className="font-mono text-[11px] uppercase tracking-wider text-white/40">{label}</div>
        <div className="font-display text-xl font-bold tracking-tight text-white md:text-2xl">{value}</div>
      </div>
    </div>
  );
}
