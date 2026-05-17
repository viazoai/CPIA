"use client";
import { useEffect, useState } from "react";
import { DailyTaskList } from "@/app/components/tasks/DailyTaskList";
import { AgentWorkflowList } from "@/app/components/tasks/AgentWorkflowList";
import { AgentTaskItemList } from "@/app/components/tasks/AgentTaskItemList";
import type { DailyTask, AgentStageProgress, AgentTaskItem } from "@/lib/types";

interface PageData {
  tasks: DailyTask[];
  progressByDate: Record<string, AgentStageProgress[]>;
  itemsByDate: Record<string, Record<string, AgentTaskItem[]>>;
}

export default function AgentTasksPage() {
  const [data, setData] = useState<PageData | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/mock/agent-tasks")
      .then((r) => r.json())
      .then((d: PageData) => {
        setData(d);
        if (d.tasks.length > 0) setSelectedDate(d.tasks[0].date);
      });
  }, []);

  if (!data) {
    return (
      <div className="mx-auto max-w-screen-2xl px-6 py-10 text-ink-light">
        Loading...
      </div>
    );
  }

  const stages = data.progressByDate[selectedDate] || [];
  const itemsForDate = data.itemsByDate[selectedDate] || {};
  const itemsForAgent = selectedAgent ? itemsForDate[selectedAgent] || [] : [];
  const selectedStage = selectedAgent ? stages.find((s) => s.agent === selectedAgent) ?? null : null;

  return (
    <div className="flex flex-col">
      <div className="mx-auto w-full max-w-screen-2xl border-b border-border-soft px-6 pt-10 pb-6 md:px-10 md:pt-14">
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          / 02 — Agent Tasks
        </span>
        <h1 className="mt-3 font-display text-h3 text-ink">
          AI Agent가 처리하는 작업 흐름
        </h1>
        <p className="mt-2 text-body-sm text-ink-mid">
          매일 ~80건의 작업일보를 7개 Agent + Human Review가 협업해 처리합니다.
          일자를 고르고 Agent 단계를 선택하면 해당 건 목록을 확인할 수 있습니다.
        </p>
      </div>

      <section className="mx-auto w-full max-w-screen-2xl px-6 pb-20 md:px-10">
        <div className="grid grid-cols-12 gap-4 items-stretch">
          {/* 좌측: Daily Tasks */}
          <div className="col-span-12 md:col-span-3 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col lg:h-[calc(100vh-260px)]">
            <DailyTaskList
              tasks={data.tasks}
              selectedDate={selectedDate}
              onSelect={(d) => {
                setSelectedDate(d);
                setSelectedAgent(null);
              }}
            />
          </div>
          {/* 중앙: Agent Workflow */}
          <div className="col-span-12 md:col-span-4 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col lg:h-[calc(100vh-260px)]">
            <AgentWorkflowList
              stages={stages}
              selectedAgent={selectedAgent}
              onSelect={setSelectedAgent}
            />
          </div>
          {/* 우측: 단계별 건 목록 */}
          <div className="col-span-12 md:col-span-5 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col lg:h-[calc(100vh-260px)]">
            <AgentTaskItemList
              selectedAgent={selectedAgent}
              stage={selectedStage}
              items={itemsForAgent}
            />
          </div>
        </div>
      </section>
    </div>
  );
}
