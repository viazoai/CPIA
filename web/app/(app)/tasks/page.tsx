"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { Upload } from "lucide-react";
import { DailyTaskList } from "@/app/components/tasks/DailyTaskList";
import { AgentWorkflowList } from "@/app/components/tasks/AgentWorkflowList";
import { AgentTaskItemList } from "@/app/components/tasks/AgentTaskItemList";
import { UploadDailyReportDialog } from "@/app/components/tasks/UploadDailyReportDialog";
import { Button } from "@/components/ui/button";
import type { DailyTask, AgentStageProgress, AgentTaskItem } from "@/lib/types";
import {
  useSimStore,
  useSimTick,
  computeSimStages,
  computeOverallPercent,
  parseSimDateFromFiles,
} from "@/lib/sim-store";

interface DetailData {
  stages: AgentStageProgress[];
  items: Record<string, AgentTaskItem[]>;
}

interface ProgressData {
  ok: true;
  run_id: string;
  date: string;
  status: string;
  current_node: string | null;
  started_at: string;
  completed_at: string | null;
  stages: AgentStageProgress[];
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
  const [uploadOpen, setUploadOpen] = useState(false);
  // 한번 fetch 한 date 는 메모리 캐시 → 좌측 목록에서 다른 날짜 갔다 돌아와도 즉답.
  const detailCacheRef = useRef<Map<string, DetailData>>(new Map());

  // 실시간 progress (Step 4) — DB 의 pipeline_runs.current_node 를 2초마다 polling.
  // 있으면 sim/detail 보다 최우선 사용.
  const [progress, setProgress] = useState<ProgressData | null>(null);

  // DB progress 게이지 애니메이션 — percent=-1 (진행중) 단계를 0→90% 부드럽게 채움.
  // 각 단계가 "진행중" 으로 처음 감지된 시각을 기록, 60초에 걸쳐 90% 까지 선형 증가.
  const stageActiveAtRef = useRef<Map<string, number>>(new Map());
  const [animTick, setAnimTick] = useState(0);

  // selectedDate 변경 시 stage 타이머 초기화.
  useEffect(() => {
    stageActiveAtRef.current.clear();
  }, [selectedDate]);

  // progress 가 running 상태일 때만 250ms 틱.
  useEffect(() => {
    const isRunning = progress?.status === "running" || progress?.status === "waiting_hil_1";
    if (!isRunning) return;
    const id = setInterval(() => setAnimTick((t) => t + 1), 250);
    return () => clearInterval(id);
  }, [progress?.status]);

  // H1 — 시뮬레이션 상태. useSimTick 이 250ms 마다 re-render + phase 자동 전환.
  const sim = useSimStore();
  useSimTick();

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
  //    sim 활성 + sim date 선택 중이면 fetch 건너뛰기 (sim store 가 stages 제공).
  useEffect(() => {
    if (!selectedDate) return;
    if (sim.simDate && selectedDate === sim.simDate && sim.phase !== "idle") {
      // sim 우선 — fetch 안 함. detail 은 null 로 둬도 isSimSelected 분기에서 sim stages 사용.
      return;
    }
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
  }, [selectedDate, sim.simDate, sim.phase]);

  // 3) progress polling — selectedDate 가 바뀔 때마다 2초 간격으로 /api/runs/progress.
  //    sim 보다 우선 사용. status='completed' 또는 4xx 응답이면 polling 중단.
  //    업로드 직후 race condition 방어: 404 연속 5회(10초) 까지는 재시도.
  useEffect(() => {
    if (!selectedDate) return;
    let cancelled = false;
    let timerId: ReturnType<typeof setTimeout> | null = null;
    let notFoundCount = 0;
    const NOT_FOUND_GIVE_UP = 5;

    const tick = async () => {
      if (cancelled) return;
      try {
        const res = await fetch(`/api/runs/progress?date=${selectedDate}`);
        if (cancelled) return;
        if (res.status === 404) {
          notFoundCount++;
          if (notFoundCount >= NOT_FOUND_GIVE_UP) {
            // 10초 간 run 없으면 sim fallback 확정.
            setProgress(null);
            return; // polling 중단
          }
          // 재시도 — 업로드 직후 DB write 전일 수 있음.
        } else if (!res.ok) {
          // 기타 서버 오류 — 재시도
        } else {
          notFoundCount = 0;
          const data = (await res.json()) as ProgressData;
          if (cancelled) return;
          setProgress(data);
          if (data.status === "completed" || data.status === "failed") {
            return; // polling 중단
          }
        }
      } catch {
        // network error — 재시도
      }
      timerId = setTimeout(tick, 2000);
    };
    tick();
    return () => {
      cancelled = true;
      if (timerId) clearTimeout(timerId);
    };
  }, [selectedDate]);

  // --- H1: 아래 useMemo / useEffect 들은 모두 early-return *위* 에 위치해야 함.
  //         조기 반환 후 hook 호출 → "Rendered more hooks than during the previous render" 위반.

  // sim 카드 stages 계산.
  const simStages = useMemo(() => {
    if (sim.phase === "idle" || !sim.simDate) return null;
    return computeSimStages(sim, Date.now());
    // sim 의 phase / startedAt 이 바뀔 때 + useSimTick 의 250ms tick 이 re-render 트리거.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sim.phase, sim.simDate, sim.phase1StartedAt, sim.phase2StartedAt, sim.files.length]);

  // sim 카드 합성 — sim 활성 시 좌측 list 최상단에 prepend.
  // 이미 같은 date 가 list 에 있으면(드물게 DB 와 충돌) sim 카드로 교체.
  const augmentedTasks: DailyTask[] = useMemo(() => {
    if (!tasks) return [];
    if (!sim.simDate || !simStages) return tasks;
    const simCard: DailyTask = {
      date: sim.simDate,
      total_count: sim.files.length,
      progress_percent: computeOverallPercent(simStages),
      status:
        sim.phase === "completed"
          ? "completed"
          : sim.phase === "hil_paused"
          ? "review_pending"
          : "running",
      has_anomaly: sim.phase === "hil_paused",
    };
    const existingIdx = tasks.findIndex((t) => t.date === sim.simDate);
    if (existingIdx >= 0) {
      return tasks.map((t, i) => (i === existingIdx ? simCard : t));
    }
    return [simCard, ...tasks];
  }, [tasks, sim.simDate, sim.phase, sim.files.length, simStages]);

  // sim 시작 (idle → phase1) 전이 시점에만 sim 카드 자동 선택.
  const prevSimPhaseRef = useRef<string>("idle");
  useEffect(() => {
    if (prevSimPhaseRef.current === "idle" && sim.phase === "phase1" && sim.simDate) {
      setSelectedDate(sim.simDate);
    }
    prevSimPhaseRef.current = sim.phase;
  }, [sim.phase, sim.simDate]);

  // 진짜 DB progress 가 selectedDate 에 있으면 그것 우선 — sim 무시.
  const hasProgress = !!(progress && progress.date === selectedDate);

  // sim 활성 중에는 current agent 도 sim stages 기준으로 자동 갱신.
  const isSimSelected = !hasProgress && !!(sim.simDate && selectedDate === sim.simDate && simStages);
  useEffect(() => {
    if (hasProgress && progress) {
      setSelectedAgent(pickCurrentAgent(progress.stages));
    } else if (isSimSelected && simStages) {
      setSelectedAgent(pickCurrentAgent(simStages));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    hasProgress,
    progress?.current_node,
    progress?.status,
    isSimSelected,
    sim.phase,
    simStages?.map((s) => s.percent).join(","),
  ]);

  // ========== 이후부터는 render 분기 (hook 호출 없음) ==========

  if (!tasks) {
    return (
      <div className="mx-auto max-w-screen-2xl px-6 py-10 text-ink-light">
        Loading...
      </div>
    );
  }

  // 화면용 stages 결정 우선순위: DB progress > sim > mock detail.
  // DB progress 의 percent=-1 (진행중) 단계는 로컬 타이머로 0→90% 애니메이션.
  const ANIM_DURATION_MS = 60_000; // 60초에 걸쳐 90% 까지 (실 파이프라인 속도 반영)
  const rawProgressStages = hasProgress ? (progress as ProgressData).stages : null;
  const animatedProgressStages: AgentStageProgress[] | null = rawProgressStages
    ? rawProgressStages.map((s) => {
        if (s.percent !== -1) return s;
        const now = Date.now();
        if (!stageActiveAtRef.current.has(s.agent)) {
          stageActiveAtRef.current.set(s.agent, now);
        }
        const elapsed = now - stageActiveAtRef.current.get(s.agent)!;
        const pct = Math.min(90, Math.round((elapsed / ANIM_DURATION_MS) * 90));
        return { ...s, percent: pct, processed: Math.floor((s.received * pct) / 100) };
      })
    : null;

  const stages: AgentStageProgress[] = animatedProgressStages
    ?? (isSimSelected ? (simStages as AgentStageProgress[]) : detail?.stages ?? []);
  const itemsForDate = detail?.items ?? {};
  const itemsForAgent = selectedAgent ? itemsForDate[selectedAgent] || [] : [];
  const selectedStage = selectedAgent ? stages.find((s) => s.agent === selectedAgent) ?? null : null;

  return (
    <div className="flex flex-col lg:h-[calc(100vh-4rem)] lg:overflow-hidden">
      <div className="mx-auto w-full max-w-screen-2xl border-b border-border-soft px-6 pt-10 pb-6 md:px-10 md:pt-14 shrink-0">
        <div className="flex items-end justify-between gap-6">
          <div className="min-w-0">
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
          <Button
            type="button"
            size="sm"
            onClick={() => setUploadOpen(true)}
            className="h-9 shrink-0 gap-1.5"
          >
            <Upload className="h-3.5 w-3.5" />
            작업일보 업로드
          </Button>
        </div>
      </div>

      <UploadDailyReportDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={({ folder, files }) => {
          // 파일명에서 _YYYYMMDD 추출 → 시뮬 카드의 "오늘" 일자.
          const date = parseSimDateFromFiles(files);
          sim.startSimulation({ date, folder, files });
        }}
      />

      <section className="mx-auto w-full max-w-screen-2xl px-6 pt-4 pb-8 md:px-10 flex-1 min-h-0">
        <div className="grid grid-cols-12 gap-3 items-stretch h-full">
          {/* 좌측: Daily Tasks */}
          <div className="col-span-12 md:col-span-3 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col min-h-0">
            <DailyTaskList
              tasks={augmentedTasks}
              selectedDate={selectedDate}
              onSelect={setSelectedDate}
            />
          </div>
          {/* 중앙: Agent Workflow */}
          <div className="col-span-12 md:col-span-4 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col min-h-0">
            {detail || isSimSelected || hasProgress ? (
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
            {detail || isSimSelected || hasProgress ? (
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
