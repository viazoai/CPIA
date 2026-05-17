import { cn } from "@/lib/utils";
import { Pause } from "lucide-react";
import type { AgentProgress } from "@/lib/types";

interface Props {
  progress: AgentProgress[];
}

export function AgentProgressList({ progress }: Props) {
  return (
    <div className="flex flex-col gap-3 p-4 h-full overflow-y-auto">
      <div className="font-display text-h6 text-ink">
        Process Progress
        <span className="ml-2 text-body-sm font-normal text-ink-mid">단계별 진행</span>
      </div>
      <div className="flex flex-col gap-2">
        {progress.map((p, i) => {
          const isHil = p.agent === "HIL Review";
          const isDone = p.processed === p.total && !p.waiting_hil;
          const percent = p.total === 0 ? 0 : (p.processed / p.total) * 100;
          const barColor = p.waiting_hil ? "bg-sun" : isDone ? "bg-mint" : "bg-sky";

          return (
            <div key={i} className={cn("flex items-center gap-3", isHil && "px-2 py-1.5 rounded-sm bg-peach-light/30")}>
              <div className="w-24 flex items-center gap-1.5 shrink-0">
                {isHil && <Pause className="h-3 w-3 text-peach-text" fill="currentColor" />}
                <span className={cn("text-xs font-semibold", isHil ? "text-peach-text" : "text-ink")}>
                  {p.agent}
                </span>
              </div>
              <div className="flex-1 h-2 overflow-hidden rounded-full bg-surface-soft">
                <div className={cn("h-full transition-all", barColor)} style={{ width: `${percent}%` }} />
              </div>
              <div className="w-16 text-right font-mono text-[11px] text-ink-mid">
                {p.processed}/{p.total}
              </div>
              <div className="w-6 flex justify-end">
                {p.waiting_hil && <span className="text-sun-text text-sm font-bold">⏸</span>}
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex items-center gap-3 text-xs text-ink-light">
        <span>per_report = 작업일보 87건 단위</span>
        <span>·</span>
        <span>per_review = 검토 항목 단위</span>
        <span>·</span>
        <span>per_run = Daily Run 1회</span>
      </div>
    </div>
  );
}
