"use client";
import { useCallback } from "react";
import { useSimulation } from "@/lib/use-simulation";
import { Activity, ClipboardCheck, AlertTriangle, RefreshCw } from "lucide-react";
import type { SitesSummary } from "@/lib/types";

interface Props {
  summary: SitesSummary;
}

export function NowStrip({ summary }: Props) {
  // "오늘 처리 87건" ±1 every 5s
  const todayUpdater = useCallback((n: number) => {
    const delta = Math.random() > 0.5 ? 1 : -1;
    const next = n + delta;
    return next < summary.today_count - 3 || next > summary.today_count + 3
      ? summary.today_count
      : next;
  }, [summary.today_count]);
  const todayCount = useSimulation(summary.today_count, todayUpdater, 5000);

  // "09:12 갱신" +1 second per minute
  const tickUpdater = useCallback((t: string) => {
    const [h, m] = t.split(":").map(Number);
    const tm = h * 60 + m + 1;
    return `${String(Math.floor(tm / 60)).padStart(2, "0")}:${String(tm % 60).padStart(2, "0")}`;
  }, []);
  const lastUpdated = useSimulation(summary.last_updated, tickUpdater, 60000);

  return (
    <section className="mx-auto max-w-wrap px-6 mt-8 md:px-10">
      <div className="rounded-card border border-border-soft bg-card p-5 shadow-xs">
        <div className="font-mono text-xs uppercase tracking-wider text-ink-light mb-3">
          NOW · 현재 운영 현황
        </div>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <NowItem icon={<Activity className="h-3.5 w-3.5" />}        tone="info"   label="오늘 처리"    value={`${todayCount}건`} />
          <NowItem icon={<ClipboardCheck className="h-3.5 w-3.5" />}  tone="info"   label="Review 대기"  value={`${summary.review_pending}건`} />
          <NowItem icon={<AlertTriangle className="h-3.5 w-3.5" />}   tone="risk"   label="이상 공종"    value={`${summary.abnormal_count}건`} />
          <NowItem icon={<RefreshCw className="h-3.5 w-3.5" />}       tone="muted"  label="마지막 갱신"  value={lastUpdated} />
        </div>
      </div>
    </section>
  );
}

function NowItem({ icon, tone, label, value }: { icon: React.ReactNode; tone: "info" | "risk" | "muted"; label: string; value: string }) {
  const toneBg = {
    info:  "bg-brand-light text-brand-text",
    risk:  "bg-rose-light text-rose-text",
    muted: "bg-surface-soft text-ink-mid",
  }[tone];
  return (
    <div className="flex items-center gap-3">
      <span className={`inline-flex h-8 w-8 items-center justify-center rounded-md ${toneBg}`}>{icon}</span>
      <div className="min-w-0">
        <div className="font-mono text-[11px] uppercase tracking-wider text-ink-light">{label}</div>
        <div className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">{value}</div>
      </div>
    </div>
  );
}
