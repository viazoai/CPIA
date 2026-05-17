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
        if (d.tasks.length > 0) {
          const latest = d.tasks[0].date;
          setSelectedDate(latest);
          // 최신 일자의 현재 처리중 단계 = HIL 대기중 or 첫 미완 단계
          const stages = d.progressByDate[latest] || [];
          const current =
            stages.find((s) => s.waiting_hil) ??
            stages.find((s) => s.received > 0 && s.percent < 100) ??
            stages[stages.length - 1];
          if (current) setSelectedAgent(current.agent);
        }
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
    <div className="flex flex-col lg:h-[calc(100vh-4rem)] lg:overflow-hidden">
      <div className="mx-auto w-full max-w-screen-2xl border-b border-border-soft px-6 pt-10 pb-6 md:px-10 md:pt-14 shrink-0">
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

      <section className="mx-auto w-full max-w-screen-2xl px-6 pt-4 pb-8 md:px-10 flex-1 min-h-0">
        <div className="grid grid-cols-12 gap-3 items-stretch h-full">
          {/* 좌측: Daily Tasks */}
          <div className="col-span-12 md:col-span-3 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col min-h-0">
            <DailyTaskList
              tasks={data.tasks}
              selectedDate={selectedDate}
              onSelect={(d) => {
                setSelectedDate(d);
                const stages = data.progressByDate[d] || [];
                const current =
                  stages.find((s) => s.waiting_hil) ??
                  stages.find((s) => s.received > 0 && s.percent < 100) ??
                  stages[stages.length - 1];
                setSelectedAgent(current ? current.agent : null);
              }}
            />
          </div>
          {/* 중앙: Agent Workflow */}
          <div className="col-span-12 md:col-span-4 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col min-h-0">
            <AgentWorkflowList
              stages={stages}
              selectedAgent={selectedAgent}
              onSelect={setSelectedAgent}
            />
          </div>
          {/* 우측: 단계별 건 목록 */}
          <div className="col-span-12 md:col-span-5 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col min-h-0">
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
