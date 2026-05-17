"use client";
import { useEffect, useRef } from "react";
import {
  Inbox,
  FileSearch,
  GitBranch,
  Database,
  FileText,
  Activity,
  Sparkles,
  User,
} from "lucide-react";
import { useSequence } from "@/lib/use-simulation";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/types";

interface Props {
  messages: ChatMessage[];
  intervalMs?: number;
}

/* Agent → icon + tone(아바타 배경) */
const AGENT_META: Record<
  string,
  { icon: React.ComponentType<{ className?: string }>; bg: string; text: string }
> = {
  Collector:  { icon: Inbox,      bg: "bg-sky-light",      text: "text-sky-text" },
  Parser:     { icon: FileSearch, bg: "bg-sky-light",      text: "text-sky-text" },
  Mapper:     { icon: GitBranch,  bg: "bg-sky-light",      text: "text-sky-text" },
  Atomizer:   { icon: Database,   bg: "bg-sky-light",      text: "text-sky-text" },
  Reporter:   { icon: FileText,   bg: "bg-brand-light", text: "text-brand-text" },
  Forecaster: { icon: Activity,   bg: "bg-brand-light", text: "text-brand-text" },
  Optimizer:  { icon: Sparkles,   bg: "bg-mint-light",     text: "text-mint-text" },
  Human:      { icon: User,       bg: "bg-brand",       text: "text-white" },
};

export function AgentChatLog({ messages, intervalMs = 1500 }: Props) {
  const revealed = useSequence(messages, intervalMs);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [revealed.length]);

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b border-border-soft px-4 py-3">
        <div className="font-display text-h6 text-ink">
          Agent Chat Log
          <span className="ml-2 text-body-sm font-normal text-ink-mid">처리 흐름</span>
        </div>
      </div>

      <div ref={scrollRef} className="flex flex-1 flex-col gap-4 overflow-y-auto p-5">
        {revealed.map((m, i) => {
          const isHuman = m.type === "human_action";
          const isHilRequest = m.type === "hil_request";
          return (
            <ChatBubble
              key={`${m.ts}-${i}`}
              message={m}
              align={isHuman ? "right" : "left"}
              highlight={isHilRequest}
            />
          );
        })}
        {revealed.length < messages.length && (
          <div className="animate-pulse py-2 text-center text-xs text-ink-light/70">
            · · · 처리 중 · · ·
          </div>
        )}
      </div>
    </div>
  );
}

/* ============================================================== */

interface BubbleProps {
  message: ChatMessage;
  align: "left" | "right";
  highlight?: boolean;
}

function ChatBubble({ message, align, highlight }: BubbleProps) {
  const meta = AGENT_META[message.agent] || AGENT_META.Collector;
  const Icon = meta.icon;
  const right = align === "right";

  return (
    <div
      className={cn(
        "flex animate-in fade-in slide-in-from-bottom-1 duration-300",
        right ? "justify-end" : "justify-start"
      )}
    >
      <div className={cn("flex max-w-[80%] gap-2.5", right && "flex-row-reverse")}>
        {/* Avatar */}
        <span
          className={cn(
            "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
            meta.bg,
            meta.text
          )}
        >
          <Icon className="h-4 w-4" />
        </span>

        {/* Bubble + meta */}
        <div className={cn("flex min-w-0 flex-col gap-1", right ? "items-end" : "items-start")}>
          {/* Agent name + HIL chip (좌측만) */}
          {!right && (
            <div className="flex items-center gap-2 px-1">
              <span className="text-body-sm font-semibold text-ink">{message.agent}</span>
              {highlight && (
                <span className="rounded-full bg-sun-light px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-sun-text">
                  HIL 요청
                </span>
              )}
            </div>
          )}

          {/* Bubble */}
          <div
            className={cn(
              "rounded-2xl px-4 py-2.5 text-body-sm leading-relaxed",
              right
                ? "rounded-tr-sm bg-brand text-white"
                : highlight
                ? "rounded-tl-sm border border-sun/40 bg-sun-light/40 text-ink"
                : "rounded-tl-sm bg-surface-soft text-ink"
            )}
          >
            <div className="font-medium">{message.summary}</div>
            {message.detail && (
              <div
                className={cn(
                  "mt-1 text-xs leading-relaxed",
                  right ? "text-white/80" : "text-ink-mid"
                )}
              >
                {message.detail}
              </div>
            )}
          </div>

          {/* Timestamp */}
          <span className="px-1 font-mono text-[10px] text-ink-light">
            {right ? `${message.ts} · ${message.agent}` : message.ts}
          </span>
        </div>
      </div>
    </div>
  );
}
