"use client";
import { useEffect, useState } from "react";
import { DailyRunList } from "@/app/components/tasks/DailyRunList";
import { AgentProgressList } from "@/app/components/tasks/AgentProgressList";
import { AgentChatLog } from "@/app/components/tasks/AgentChatLog";
import type { DailyRun, AgentProgress, ChatMessage } from "@/lib/types";

interface PageData {
  runs: DailyRun[];
  progressByDate: Record<string, AgentProgress[]>;
  chatByDate: Record<string, ChatMessage[]>;
}

export default function AgentTasksPage() {
  const [data, setData] = useState<PageData | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>("2026-05-15");

  useEffect(() => {
    fetch("/api/mock/agent-tasks")
      .then((r) => r.json())
      .then(setData);
  }, []);

  if (!data) {
    return (
      <div className="mx-auto max-w-wrap px-6 py-10 text-ink-light">
        Loading...
      </div>
    );
  }

  const progress = data.progressByDate[selectedDate] || [];
  const chat = data.chatByDate[selectedDate] || [];

  return (
    <div className="flex flex-col">
      <div className="mx-auto w-full max-w-wrap px-6 py-8 md:px-10">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-lavender-text">
            / 02 — Agent Tasks
          </span>
          <span className="h-px w-8 bg-border" />
          <span className="font-mono text-[11px] uppercase tracking-wider text-ink-light">
            Daily Run · Process Progress · Chat
          </span>
        </div>
        <h1 className="mt-6 font-display text-h3 text-ink">
          AI Agent가 처리하는 작업 흐름
        </h1>
        <p className="mt-2 text-body-sm text-ink-mid">
          매일 ~100건의 작업일보를 7개 Agent + Human Review가 협업해 처리합니다. Daily run을 선택하면 단계별 진행과 Agent 대화를 볼 수 있습니다.
        </p>
      </div>

      <section className="mx-auto w-full max-w-wrap px-6 pb-20 md:px-10">
        <div className="grid grid-cols-12 gap-4 items-stretch">
          {/* 좌측: Daily List */}
          <div className="col-span-12 md:col-span-3 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col lg:h-[calc(100vh-260px)]">
            <DailyRunList
              runs={data.runs}
              selectedDate={selectedDate}
              onSelect={setSelectedDate}
            />
          </div>
          {/* 중앙: Process Progress */}
          <div className="col-span-12 md:col-span-4 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col lg:h-[calc(100vh-260px)]">
            <AgentProgressList progress={progress} />
          </div>
          {/* 우측: Chat Log */}
          <div className="col-span-12 md:col-span-5 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col lg:h-[calc(100vh-260px)]">
            <AgentChatLog messages={chat} />
          </div>
        </div>
      </section>
    </div>
  );
}
