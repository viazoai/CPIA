"use client";
import { Fragment } from "react";
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
  Exporter: FileText,
  Forecaster: Activity,
  Optimizer: Sparkles,
};

const KOREAN: Record<string, string> = {
  Collector: "수집",
  Parser: "파싱",
  Mapper: "매핑",
  "HIL Review": "사람 검토",
  Atomizer: "DB 적재",
  Exporter: "출력",
  Forecaster: "진단",
  Optimizer: "최적화",
};

export function AgentWorkflowList({ stages, selectedAgent, onSelect }: Props) {
  // 현재 작업중 단계 — HIL 대기 우선 → 첫 미완 단계 → 모두 완료면 마지막 단계
  const waitingStage = stages.find((s) => s.waiting_hil);
  const inflightStage = stages.find((s) => s.received > 0 && s.percent < 100 && !s.waiting_hil);
  const allDone = stages.length > 0 && stages.every((s) => s.percent === 100 && !s.waiting_hil);
  const currentStage = waitingStage ?? inflightStage ?? (allDone ? stages[stages.length - 1] : null);

  let statusLabel = "대기 없음";
  if (waitingStage) statusLabel = "검토 대기중";
  else if (inflightStage) statusLabel = "처리중";
  else if (allDone) statusLabel = "전 단계 완료";

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-border-soft shrink-0">
        <div className="font-display text-h6 font-bold text-ink">
          Agent Workflow
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-ink-mid tabular-nums">
          <span>현재 단계 {currentStage ? currentStage.agent : "—"}</span>
          <span>·</span>
          <span>상태 {statusLabel}</span>
        </div>
      </div>

      <ol className="flex-1 min-h-0 p-3 flex flex-col">
        {stages.map((s, i) => {
          const Icon = STEP_ICON[s.agent] ?? Sparkles;
          const isHil = s.is_hil;
          const active = selectedAgent === s.agent;
          const isLast = i === stages.length - 1;
          const isDone = s.received > 0 && s.processed === s.received && !s.waiting_hil;
          const barColor = s.waiting_hil ? "bg-sun" : "bg-mint";

          return (
            <Fragment key={s.agent}>
              <button
                type="button"
                onClick={() => onSelect(s.agent)}
                className={cn(
                  "w-full shrink-0 flex items-center gap-3 rounded-card border px-3 py-3 transition-all text-left",
                  isHil
                    ? active
                      ? "border-brand bg-brand-light ring-2 ring-brand/40 shadow-sm"
                      : "border-dashed border-brand/60 bg-brand-light/30 hover:bg-brand-light/50"
                    : active
                      ? "border-brand bg-brand-light ring-2 ring-brand/40 shadow-sm"
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
                    "inline-flex h-8 w-8 items-center justify-center rounded-md shadow-xs shrink-0",
                    isHil ? "bg-brand text-white" : "bg-card text-ink-mid"
                  )}>
                    <Icon className="h-4 w-4" />
                  </span>
                </div>

                {/* Name + counts + bar */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2 mb-1.5">
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
                        s.waiting_hil ? "text-sun-text" : "text-mint-text"
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
                <div aria-hidden className="flex flex-1 min-h-[6px] justify-center">
                  <span className="block h-full w-px bg-border" />
                </div>
              )}
            </Fragment>
          );
        })}
      </ol>
    </div>
  );
}
