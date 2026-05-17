import Link from "next/link";
import { ResponsiveContainer, LineChart, Line } from "recharts";
import { AlertTriangle, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Site } from "@/lib/types";

function makeSparkline(actual: number): { v: number }[] {
  return Array.from({ length: 7 }, (_, i) => ({ v: actual * (0.4 + i * 0.1) }));
}

export function SiteOverviewCard({ site }: { site: Site }) {
  const stripeColor = site.status === "risk" ? "bg-rose" : site.status === "caution" ? "bg-sun" : "bg-mint";
  const statusBg = site.status === "risk" ? "bg-rose-light text-rose-text" : site.status === "caution" ? "bg-sun-light text-sun-text" : "bg-mint-light text-mint-text";
  const data = makeSparkline(site.progress_actual);

  return (
    <Link
      href={`/dashboard/sites/${site.id}`}
      className="group relative overflow-hidden rounded-card border border-border-soft bg-card p-4 shadow-xs hover:shadow-sm transition-shadow"
    >
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", stripeColor)} />
      <div className="pl-3">
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <div className="truncate font-display text-h6 text-ink">{site.name}</div>
            <div className="font-mono text-xs uppercase tracking-wider text-ink-light mt-0.5">{site.location} · Hi-tech</div>
          </div>
          {site.status === "risk" && (
            <span className="inline-flex items-center gap-0.5 rounded-sm bg-rose-light px-1.5 py-0.5 text-[11px] font-bold text-rose-text">
              <AlertTriangle className="h-2.5 w-2.5" />
              이상
            </span>
          )}
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
          <div>
            <div className="text-ink-light">생산성</div>
            <div className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">{site.productivity_today}%</div>
          </div>
          <div>
            <div className="text-ink-light">공기</div>
            <div className={cn("font-display text-lg font-semibold tracking-[-0.01em]", site.delay_days > 0 ? "text-rose" : "text-mint")}>
              {site.delay_days > 0 ? `+${site.delay_days}일` : "정상"}
            </div>
          </div>
        </div>

        <div className="mt-2 h-8">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <Line type="monotone" dataKey="v" stroke={site.status === "risk" ? "#ef4444" : site.status === "caution" ? "#d97706" : "#0ea76a"} strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="mt-2 flex items-center justify-between border-t border-border-soft pt-2">
          <span className={cn("inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] font-semibold", statusBg)}>
            {site.abnormal_trades > 0 ? `이상 공종 ${site.abnormal_trades}` : "정상"}
          </span>
          <ArrowRight className="h-3.5 w-3.5 text-ink-light group-hover:text-brand group-hover:translate-x-0.5 transition-all" />
        </div>
      </div>
    </Link>
  );
}
