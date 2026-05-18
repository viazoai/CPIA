"use client";
import { useMemo } from "react";
import { ResponsiveContainer, LineChart, Line } from "recharts";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { generateSiteTrend } from "@/lib/fleet-trend-mock";
import type { Site } from "@/lib/types";

interface Props {
  site: Site;
  /** fixture 의 site_sparklines[site.id] 가 있으면 그대로 사용, 없으면 deterministic 생성. */
  sparkline?: number[];
}

export function SiteOverviewCard({ site, sparkline }: Props) {
  const stripeColor =
    site.status === "risk" ? "bg-rose"
    : site.status === "caution" ? "bg-sun"
    : "bg-mint";

  const statusBg =
    site.status === "risk" ? "bg-rose-light text-rose-text"
    : site.status === "caution" ? "bg-sun-light text-sun-text"
    : "bg-mint-light text-mint-text";

  const sparkColor =
    site.status === "risk" ? "#ef4444"
    : site.status === "caution" ? "#d97706"
    : "#0ea76a";

  const data = useMemo(() => {
    const series = sparkline && sparkline.length > 0
      ? sparkline
      : generateSiteTrend(site.id, site.productivity_today, 90);
    return series.map((v) => ({ v }));
  }, [site.id, site.productivity_today, sparkline]);

  return (
    <article className="relative overflow-hidden rounded-card border border-border-soft bg-card p-4 shadow-xs cursor-default">
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", stripeColor)} />
      <div className="pl-3">
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <div className="truncate font-display text-h6 text-ink">{site.name}</div>
            <div className="font-mono text-xs uppercase tracking-wider text-ink-light mt-0.5">
              {site.location} · Hi-tech
            </div>
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
            <div className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
              {site.productivity_today}%
            </div>
          </div>
          <div>
            <div className="text-ink-light">공기</div>
            <div className={cn(
              "font-display text-lg font-semibold tracking-[-0.01em]",
              site.delay_days > 0 ? "text-rose" : "text-mint",
            )}>
              {site.delay_days > 0 ? `+${site.delay_days}일` : "정상"}
            </div>
          </div>
        </div>

        <div className="mt-2 h-10">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <Line
                type="monotone"
                dataKey="v"
                stroke={sparkColor}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="mt-2 border-t border-border-soft pt-2">
          <span className={cn(
            "inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] font-semibold",
            statusBg,
          )}>
            {site.abnormal_trades > 0 ? `이상 공종 ${site.abnormal_trades}` : "정상"}
          </span>
        </div>
      </div>
    </article>
  );
}
