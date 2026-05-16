import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Flame,
  TrendingDown,
  TrendingUp,
  Users,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

type Status = "normal" | "caution" | "risk" | "unknown";

export type Site = {
  site_id: string;
  name: string;
  owner: string;
  plan_progress: number;
  actual_progress: number;
  status: Status;
  is_mock: boolean;
  monthly_hours_now: number;
  monthly_hours_target: number;
  fte_save: number;
  pain_top: string;
  last_run_at: string;
};

const STATUS_STYLE: Record<
  Status,
  {
    label: string;
    icon: typeof CheckCircle2;
    chip: string;
    bar: string;
    stripe: string;
    accent: string;
  }
> = {
  normal: {
    label: "정상",
    icon: CheckCircle2,
    chip: "bg-mint-light text-mint-text border-transparent",
    bar: "bg-mint",
    stripe: "bg-gradient-to-b from-mint/80 to-mint",
    accent: "text-mint-text",
  },
  caution: {
    label: "주의",
    icon: AlertTriangle,
    chip: "bg-sun-light text-sun-text border-transparent",
    bar: "bg-sun",
    stripe: "bg-gradient-to-b from-sun/80 to-sun",
    accent: "text-sun-text",
  },
  risk: {
    label: "위험",
    icon: Flame,
    chip: "bg-rose-light text-rose-text border-transparent",
    bar: "bg-rose",
    stripe: "bg-gradient-to-b from-rose/80 to-rose",
    accent: "text-rose-text",
  },
  unknown: {
    label: "—",
    icon: CheckCircle2,
    chip: "bg-surface-soft text-ink-light border-transparent",
    bar: "bg-ink-light",
    stripe: "bg-surface-soft",
    accent: "text-ink-light",
  },
};

function formatLastRun(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("ko-KR", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function SiteCard({ site }: { site: Site }) {
  const s = STATUS_STYLE[site.status];
  const StatusIcon = s.icon;
  const gap = site.actual_progress - site.plan_progress;
  const GapIcon = gap < 0 ? TrendingDown : TrendingUp;
  const gapText = gap >= 0 ? `+${gap.toFixed(1)}` : gap.toFixed(1);
  const gapTone = gap < 0 ? "text-rose-text" : "text-mint-text";

  return (
    <Card className="group relative overflow-hidden rounded-card border-border-soft bg-card shadow-xs transition-all duration-200 hover:-translate-y-0.5 hover:border-border hover:shadow-md">
      {/* 좌측 status stripe */}
      <span
        aria-hidden
        className={cn("absolute inset-y-0 left-0 w-1", s.stripe)}
      />

      <CardHeader className="space-y-3 pl-7 pr-5 pt-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate font-display text-base font-bold tracking-tight text-ink">
              {site.name}
            </h3>
            <p className="mt-0.5 truncate text-xs text-ink-light">
              {site.owner}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1.5">
            <Badge
              variant="outline"
              className={cn(
                "inline-flex h-6 items-center gap-1 px-2 text-[11px] font-semibold",
                s.chip,
              )}
            >
              <StatusIcon className="h-3 w-3" />
              {s.label}
            </Badge>
            {site.is_mock ? (
              <span className="font-mono text-[9px] uppercase tracking-widest text-ink-light/60">
                mock
              </span>
            ) : (
              <Badge className="border-transparent bg-lavender-light px-2 text-[9px] font-bold uppercase tracking-widest text-lavender-text hover:bg-lavender-light">
                실 PoC
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 pl-7 pr-5">
        {/* 진행률 */}
        <div>
          <div className="flex items-baseline justify-between text-[10px] font-medium uppercase tracking-widest text-ink-light">
            <span>Plan {site.plan_progress.toFixed(1)}%</span>
            <span>Actual {site.actual_progress.toFixed(1)}%</span>
          </div>
          <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-soft">
            <div
              className={cn("h-full transition-all", s.bar)}
              style={{ width: `${Math.min(site.actual_progress, 100)}%` }}
            />
          </div>
          <p
            className={cn(
              "mt-1.5 inline-flex items-center gap-1 font-mono text-[11px] font-semibold",
              gapTone,
            )}
          >
            <GapIcon className="h-3 w-3" />
            Gap {gapText}%p
          </p>
        </div>

        <Separator className="bg-border-soft" />

        {/* KPI 2 칸 */}
        <dl className="grid grid-cols-2 gap-3 text-xs">
          <div className="space-y-1">
            <dt className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-ink-light">
              <Clock className="h-3 w-3" />
              월간 시간
            </dt>
            <dd className="font-mono text-sm font-bold text-ink">
              {site.monthly_hours_now}
              <span className="text-ink-light">h</span>
              <span className="ml-1 text-[10px] font-medium text-ink-light/80">
                → {site.monthly_hours_target}h
              </span>
            </dd>
          </div>
          <div className="space-y-1">
            <dt className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-ink-light">
              <Users className="h-3 w-3" />
              재배치 FTE
            </dt>
            <dd className="font-mono text-sm font-bold text-ink">
              {site.fte_save.toFixed(1)}
              <span className="text-ink-light"> 명</span>
            </dd>
          </div>
        </dl>

        {/* Pain 한 줄 — 색 배경 박스 */}
        <p className="line-clamp-2 rounded-md bg-surface-soft px-3 py-2 text-[11px] leading-relaxed text-ink-mid">
          {site.pain_top}
        </p>
      </CardContent>

      <CardFooter className="flex items-center justify-between border-t border-border-soft bg-surface-soft/40 py-3 pl-7 pr-3">
        <div className="flex items-center gap-1.5 text-[10px] text-ink-light">
          <Clock className="h-3 w-3" />
          {formatLastRun(site.last_run_at)}
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1 px-2 text-[11px] font-semibold text-lavender-text hover:bg-lavender-light hover:text-lavender-text"
        >
          상세
          <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
        </Button>
      </CardFooter>
    </Card>
  );
}
