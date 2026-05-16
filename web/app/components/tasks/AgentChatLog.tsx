"use client";
import { useSequence } from "@/lib/use-simulation";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/types";

interface Props {
  messages: ChatMessage[];
  intervalMs?: number;
}

const AGENT_TONE: Record<string, { bg: string; text: string; ring: string }> = {
  Collector:  { bg: "bg-sky-light",      text: "text-sky-text",      ring: "ring-sky/30" },
  Parser:     { bg: "bg-sky-light",      text: "text-sky-text",      ring: "ring-sky/30" },
  Mapper:     { bg: "bg-sky-light",      text: "text-sky-text",      ring: "ring-sky/30" },
  Atomizer:   { bg: "bg-sky-light",      text: "text-sky-text",      ring: "ring-sky/30" },
  Human:      { bg: "bg-peach-light",    text: "text-peach-text",    ring: "ring-peach/30" },
  Reporter:   { bg: "bg-lavender-light", text: "text-lavender-text", ring: "ring-lavender/30" },
  Forecaster: { bg: "bg-lavender-light", text: "text-lavender-text", ring: "ring-lavender/30" },
  Optimizer:  { bg: "bg-mint-light",     text: "text-mint-text",     ring: "ring-mint/30" },
};

export function AgentChatLog({ messages, intervalMs = 1500 }: Props) {
  const revealed = useSequence(messages, intervalMs);

  return (
    <div className="flex flex-col">
      <div className="px-4 py-3 border-b border-border-soft">
        <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light">
          Agent Chat Log · 처리 흐름
        </div>
      </div>
      <div className="flex flex-col gap-2.5 p-4 max-h-[640px] overflow-y-auto">
        {revealed.map((m, i) => {
          const tone = AGENT_TONE[m.agent] || AGENT_TONE.Collector;
          const isHilRequest = m.type === "hil_request";
          const isHuman = m.type === "human_action";
          return (
            <div
              key={`${m.ts}-${i}`}
              className={cn(
                "rounded-card border border-border-soft p-3 shadow-xs animate-in fade-in slide-in-from-bottom-1 duration-300",
                isHilRequest && "ring-2 ring-sun/40 border-sun/40",
                isHuman && "border-peach/40"
              )}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={cn("inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider", tone.bg, tone.text)}>
                    {m.agent}
                  </span>
                  <span className="font-mono text-[10px] text-ink-light">{m.ts}</span>
                </div>
                {isHilRequest && (
                  <span className="rounded-sm bg-sun-light px-1.5 py-0.5 text-[9px] font-semibold text-sun-text">
                    HIL Review 요청
                  </span>
                )}
              </div>
              <div className="mt-2 text-sm font-medium text-ink leading-snug">{m.summary}</div>
              {m.detail && (
                <div className="mt-1.5 text-xs text-ink-mid leading-relaxed">{m.detail}</div>
              )}
            </div>
          );
        })}
        {revealed.length < messages.length && (
          <div className="text-center text-[10px] text-ink-light/70 py-2 animate-pulse">
            · · · 처리 중 · · ·
          </div>
        )}
      </div>
    </div>
  );
}
