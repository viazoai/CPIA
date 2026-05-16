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

  const isCollect = agent.group === "collect";
  const accent = isCollect ? "#60a5fa" : "#a78bfa"; // sky-400 / violet-400
  const accentGlow = isCollect ? "rgba(96,165,250,0.20)" : "rgba(167,139,250,0.20)";

  const stateDot =
    agent.state === "processing" ? "bg-emerald-400" :
    agent.state === "waiting"    ? "bg-amber-400"   :
                                    "bg-white/20";
  const stateGlow =
    agent.state === "processing" ? "shadow-[0_0_10px_rgba(52,211,153,0.7)]" :
    agent.state === "waiting"    ? "shadow-[0_0_10px_rgba(251,191,36,0.6)]" : "";

  return (
    <div
      className="group relative overflow-hidden rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-sm p-4 transition-all hover:bg-white/[0.06] hover:border-white/20"
      style={{ boxShadow: `0 0 30px -14px ${accentGlow}` }}
    >
      {/* Top accent line (glowing) */}
      <span
        aria-hidden
        className="absolute inset-x-0 top-0 h-px"
        style={{
          background: `linear-gradient(90deg, transparent 5%, ${accent} 50%, transparent 95%)`,
        }}
      />

      <div className="flex items-center justify-between">
        <span className="font-mono text-[11px] uppercase tracking-wider text-white/40">
          STEP {String(agent.step).padStart(2, "0")}
        </span>
        <span className={cn("h-1.5 w-1.5 rounded-full", stateDot, stateGlow, agent.state !== "idle" && "animate-pulse")} />
      </div>

      <div className="mt-3 font-display text-base font-bold tracking-tight text-white md:text-lg">
        {agent.name}
      </div>
      <div className="mt-0.5 text-xs text-white/40">{agent.korean_name}</div>
      <p className="mt-2.5 text-[11px] leading-relaxed text-white/55 line-clamp-3">
        {agent.description}
      </p>

      <div className="mt-4 pt-3 border-t border-white/[0.08] flex items-center justify-between">
        <span className="font-mono text-[11px] uppercase tracking-wider text-white/40">{agent.model}</span>
        <span className="text-[11px] font-semibold tabular-nums">
          {live > 0 ? <span className="text-white">{live}건</span> : <span className="text-white/25">idle</span>}
        </span>
      </div>
    </div>
  );
}
