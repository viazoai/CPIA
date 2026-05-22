"use client";
import { useEffect, useRef, useState } from "react";
import { DailyTaskList } from "@/app/components/tasks/DailyTaskList";
import { AgentWorkflowList } from "@/app/components/tasks/AgentWorkflowList";
import { AgentTaskItemList } from "@/app/components/tasks/AgentTaskItemList";
import type { DailyTask, AgentStageProgress, AgentTaskItem } from "@/lib/types";

interface DetailData {
  stages: AgentStageProgress[];
  items: Record<string, AgentTaskItem[]>;
}

function pickCurrentAgent(stages: AgentStageProgress[]): string | null {
  const current =
    stages.find((s) => s.waiting_hil) ??
    stages.find((s) => s.received > 0 && s.percent < 100) ??
    stages[stages.length - 1];
  return current ? current.agent : null;
}

export default function AgentTasksPage() {
  const [tasks, setTasks] = useState<DailyTask[] | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [detail, setDetail] = useState<DetailData | null>(null);
  // 한번 fetch 한 date 는 메모리 캐시 → 좌측 목록에서 다른 날짜 갔다 돌아와도 즉답.
  const detailCacheRef = useRef<Map<string, DetailData>>(new Map());

  // 1) 진입 즉시 list (1년치 dates) — 단일 쿼리, < 200ms.
  useEffect(() => {
    fetch("/api/mock/agent-tasks")
      .then((r) => r.json())
      .then((d: { tasks: DailyTask[] }) => {
        setTasks(d.tasks);
        if (d.tasks.length > 0) setSelectedDate(d.tasks[0].date);
      });
  }, []);

  // 2) selectedDate 변경 시에만 detail fetch.
  useEffect(() => {
    if (!selectedDate) return;
    const cached = detailCacheRef.current.get(selectedDate);
    if (cached) {
      setDetail(cached);
      setSelectedAgent(pickCurrentAgent(cached.stages));
      return;
    }
    setDetail(null);
    let cancelled = false;
    fetch(`/api/mock/agent-tasks/${selectedDate}`)
      .then((r) => r.json())
      .then((d: DetailData) => {
        if (cancelled) return;
        detailCacheRef.current.set(selectedDate, d);
        setDetail(d);
        setSelectedAgent(pickCurrentAgent(d.stages));
      });
    return () => {
      cancelled = true;
    };
  }, [selectedDate]);

  if (!tasks) {
    return (
      <div className="mx-auto max-w-screen-2xl px-6 py-10 text-ink-light">
        Loading...
      </div>
    );
  }

  const stages = detail?.stages ?? [];
  const itemsForDate = detail?.items ?? {};
  const itemsForAgent = selectedAgent ? itemsForDate[selectedAgent] || [] : [];
  const selectedStage = selectedAgent ? stages.find((s) => s.agent === selectedAgent) ?? null : null;

  return (
    <div className="flex flex-col lg:h-[calc(100vh-4rem)] lg:overflow-hidden">
      <div className="mx-auto w-full max-w-screen-2xl border-b border-border-soft px-6 pt-10 pb-6 md:px-10 md:pt-14 shrink-0">
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          / 02 — Agent Tasks
        </span>
        <h1 className="mt-3 font-display text-h3 text-ink">
          CPIA 작업 현황
        </h1>
        <p className="mt-2 text-body-sm text-ink-mid">
          매일 이메일로 접수되는 업체별 작업일보를 7개 Agent를 통해 업무를 처리하여 Middle Office 업무를 지원합니다.
        </p>
      </div>

      <section className="mx-auto w-full max-w-screen-2xl px-6 pt-4 pb-8 md:px-10 flex-1 min-h-0">
        <div className="grid grid-cols-12 gap-3 items-stretch h-full">
          {/* 좌측: Daily Tasks */}
          <div className="col-span-12 md:col-span-3 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col min-h-0">
            <DailyTaskList
              tasks={tasks}
              selectedDate={selectedDate}
              onSelect={setSelectedDate}
            />
          </div>
          {/* 중앙: Agent Workflow */}
          <div className="col-span-12 md:col-span-4 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col min-h-0">
            {detail ? (
              <AgentWorkflowList
                stages={stages}
                selectedAgent={selectedAgent}
                onSelect={setSelectedAgent}
              />
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-ink-light">
                불러오는 중…
              </div>
            )}
          </div>
          {/* 우측: 단계별 건 목록 */}
          <div className="col-span-12 md:col-span-5 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col min-h-0">
            {detail ? (
              <AgentTaskItemList
                selectedAgent={selectedAgent}
                stage={selectedStage}
                items={itemsForAgent}
              />
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-ink-light">
                불러오는 중…
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
