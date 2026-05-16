"use client";
import { useCallback } from "react";
import { useSimulation } from "@/lib/use-simulation";
import { cn } from "@/lib/utils";
import type { AgentStatus } from "@/lib/types";

interface Props {
  agent: AgentStatus;
  simInterval?: number;
}

export function AgentCard({ agent, simInterval = 8000 }: Props) {
  const updater = useCallback((n: number) => {
    const variance = [-1, 0, 0, 1][Math.floor(Math.random() * 4)];
    return Math.max(0, n + variance);
  }, []);
  const live = useSimulation(agent.active_count, updater, simInterval);

  const groupClass = agent.group === "collect"
    ? "border-sky/40 bg-sky-light/30"
    : "border-lavender/40 bg-lavender-light/30";
  const stripeClass = agent.group === "collect" ? "bg-sky" : "bg-lavender";
  const stateColor =
    agent.state === "processing" ? "bg-mint" :
    agent.state === "waiting"    ? "bg-sun"  :
                                    "bg-ink-light/30";

  return (
    <div className={cn("relative overflow-hidden rounded-card border bg-card p-4 shadow-xs", groupClass)}>
      <span aria-hidden className={cn("absolute inset-x-0 top-0 h-1", stripeClass)} />
      <div className="font-mono text-[11px] uppercase tracking-wider text-ink-light">
        STEP {String(agent.step).padStart(2, "0")}
      </div>
      <div className="mt-1 font-display text-base font-bold tracking-tight text-ink">{agent.name}</div>
      <div className="mt-0.5 text-xs text-ink-light">{agent.korean_name}</div>
      <p className="mt-2 text-[11px] leading-relaxed text-ink-mid line-clamp-3">{agent.description}</p>
      <div className="mt-3 flex items-center justify-between">
        <span className="font-mono text-xs uppercase tracking-wider text-ink-light">{agent.model}</span>
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-ink">
          <span className={cn("h-1.5 w-1.5 rounded-full", stateColor, agent.state !== "idle" && "animate-pulse")} />
          {live > 0 ? `${live}건` : "idle"}
        </span>
      </div>
    </div>
  );
}
