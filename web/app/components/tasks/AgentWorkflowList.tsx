"use client";
import {
  Inbox,
  FileSearch,
  GitBranch,
  Database,
  FileText,
  Activity,
  Sparkles,
  ClipboardCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentStageProgress } from "@/lib/types";

interface Props {
  stages: AgentStageProgress[];
  selectedAgent: string | null;
  onSelect: (agent: string) => void;
}

const STEP_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  Collector: Inbox,
  Parser: FileSearch,
  Mapper: GitBranch,
  "HIL Review": ClipboardCheck,
  Atomizer: Database,
  Reporter: FileText,
  Forecaster: Activity,
  Optimizer: Sparkles,
};

const KOREAN: Record<string, string> = {
  Collector: "수집",
  Parser: "파싱",
  Mapper: "매핑",
  "HIL Review": "사람 검토",
  Atomizer: "DB 적재",
  Reporter: "보고",
  Forecaster: "진단",
  Optimizer: "최적화",
};

export function AgentWorkflowList({ stages, selectedAgent, onSelect }: Props) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-border-soft shrink-0">
        <div className="font-display text-h6 font-bold text-ink">
          Agent Workflow
          <span className="ml-2 text-body-sm font-normal text-ink-mid">단계별 진도율</span>
        </div>
        <div className="mt-0.5 text-xs text-ink-mid">
          단계를 클릭하면 우측에 해당 건이 표시됩니다
        </div>
      </div>

      <ol className="flex-1 overflow-y-auto p-3 flex flex-col">
        {stages.map((s, i) => {
          const Icon = STEP_ICON[s.agent] ?? Sparkles;
          const isHil = s.is_hil;
          const active = selectedAgent === s.agent;
          const isLast = i === stages.length - 1;
          const isDone = s.received > 0 && s.processed === s.received && !s.waiting_hil;
          const barColor = s.waiting_hil ? "bg-sun" : isDone ? "bg-mint" : "bg-sky";

          return (
            <div key={s.agent}>
              <button
                type="button"
                onClick={() => onSelect(s.agent)}
                className={cn(
                  "w-full flex items-center gap-3 rounded-card border px-3 py-2 transition-colors text-left",
                  isHil
                    ? active
                      ? "border-brand bg-brand-light/60"
                      : "border-dashed border-brand/60 bg-brand-light/30 hover:bg-brand-light/50"
                    : active
                      ? "border-brand bg-brand-light/40"
                      : "border-border-soft bg-surface-soft/40 hover:bg-surface-soft"
                )}
              >
                {/* Step + icon */}
                <div className="flex items-center gap-2 shrink-0">
                  <span className={cn(
                    "hidden md:inline font-mono text-[10px] font-semibold uppercase tracking-wider",
                    isHil ? "text-brand-text" : "text-ink-light"
                  )}>
                    {isHil ? "HIL" : String(s.step).padStart(2, "0")}
                  </span>
                  <span className={cn(
                    "inline-flex h-7 w-7 items-center justify-center rounded-md shadow-xs shrink-0",
                    isHil ? "bg-brand text-white" : "bg-card text-ink-mid"
                  )}>
                    <Icon className="h-3.5 w-3.5" />
                  </span>
                </div>

                {/* Name + counts + bar */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2 mb-1">
                    <div className="flex items-baseline gap-1.5 min-w-0">
                      <span className="font-display text-body-sm font-semibold text-ink truncate">
                        {s.agent}
                      </span>
                      <span className="shrink-0 text-[11px] text-ink-mid">
                        {KOREAN[s.agent]}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 tabular-nums">
                      <span className="font-mono text-[10px] text-ink-light">
                        접수 <span className="text-ink font-semibold">{s.received}</span>
                      </span>
                      <span className="font-mono text-[10px] text-ink-light">
                        처리 <span className="text-ink font-semibold">{s.processed}</span>
                      </span>
                      <span className={cn(
                        "font-mono text-[11px] font-bold w-9 text-right",
                        s.waiting_hil ? "text-sun-text" : isDone ? "text-mint-text" : "text-brand-text"
                      )}>
                        {s.percent}%
                      </span>
                    </div>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-card">
                    <div className={cn("h-full transition-all", barColor)} style={{ width: `${s.percent}%` }} />
                  </div>
                </div>
              </button>

              {!isLast && (
                <div aria-hidden className="flex h-3 justify-center">
                  <span className="block h-full w-px bg-border" />
                </div>
              )}
            </div>
          );
        })}
      </ol>
    </div>
  );
}
