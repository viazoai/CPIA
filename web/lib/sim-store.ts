/**
 * H1 — 2-페이즈 시뮬레이션 엔진.
 *
 * 업로드 완료 시 startSimulation() 호출 → Phase 1 (Collector → Parser → Mapper, 7.5s)
 *   → HIL 자동 정지 → 사용자가 /review 에서 확정 후 resumeSimulation()
 *   → Phase 2 (Atomizer → Exporter → Forecaster → Optimizer, 8.5s) → completed.
 *
 * 시간 경과는 phase1StartedAt / phase2StartedAt 타임스탬프로 표현 (state 자체에 percent 미저장).
 * useSimTick() hook 이 250ms 마다 re-render + 임계 시각 도달 시 phase 자동 전환.
 * computeSimStages() 가 현재 시각 기준으로 AgentStageProgress[] 8개를 계산.
 *
 * persist(localStorage) — F5 새로고침해도 시뮬 상태 유지.
 * clearSimulation() — H12 reset 버튼에서 함께 호출 (data/upload/ 비울 때 동기).
 */
import { useEffect, useState } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AgentStageProgress } from "@/lib/types";

export type SimPhase = "idle" | "phase1" | "hil_paused" | "phase2" | "completed";

export interface SimFile {
  name: string;
  size: number;
}

interface SimState {
  simDate: string | null;          // "2025-09-25"
  folder: string | null;            // "20260531-040204" (API 응답)
  files: SimFile[];
  phase: SimPhase;
  phase1StartedAt: number | null;   // Date.now()
  phase2StartedAt: number | null;
  startSimulation: (p: { date: string; folder: string; files: SimFile[] }) => void;
  pauseAtHIL: () => void;
  resumeSimulation: () => void;
  completeSimulation: () => void;
  clearSimulation: () => void;
}

const INITIAL = {
  simDate: null,
  folder: null,
  files: [] as SimFile[],
  phase: "idle" as SimPhase,
  phase1StartedAt: null,
  phase2StartedAt: null,
};

export const useSimStore = create<SimState>()(
  persist(
    (set) => ({
      ...INITIAL,
      startSimulation: ({ date, folder, files }) =>
        set({
          simDate: date,
          folder,
          files,
          phase: "phase1",
          phase1StartedAt: Date.now(),
          phase2StartedAt: null,
        }),
      pauseAtHIL: () => set({ phase: "hil_paused" }),
      resumeSimulation: () =>
        set({
          phase: "phase2",
          phase2StartedAt: Date.now(),
        }),
      completeSimulation: () => set({ phase: "completed" }),
      clearSimulation: () => set({ ...INITIAL }),
    }),
    { name: "cpia-sim-store" },
  ),
);

// ---------------------------------------------------------------------------
// Phase 정의 — 1분 압축 시연 cycle (총 16초)
// ---------------------------------------------------------------------------

export const PHASE_1_STAGES = [
  { agent: "Collector", step: 1, ms: 2000 },
  { agent: "Parser", step: 2, ms: 2500 },
  { agent: "Mapper", step: 3, ms: 3000 },
] as const;

export const PHASE_2_STAGES = [
  { agent: "Atomizer", step: 4, ms: 2000 },
  { agent: "Exporter", step: 5, ms: 2500 },
  { agent: "Forecaster", step: 6, ms: 2000 },
  { agent: "Optimizer", step: 7, ms: 2000 },
] as const;

export const PHASE_1_TOTAL_MS = PHASE_1_STAGES.reduce((a, s) => a + s.ms, 0); // 7500
export const PHASE_2_TOTAL_MS = PHASE_2_STAGES.reduce((a, s) => a + s.ms, 0); // 8500

// HIL Review 단계에서 "확정 필요" 카드 개수 (시연 시각화용 상수).
export const HIL_LOW_CONFIDENCE_COUNT = 3;

// ---------------------------------------------------------------------------
// 헬퍼
// ---------------------------------------------------------------------------

/**
 * 업로드된 파일명에서 `_YYYYMMDD.xls(x|m)` 패턴 추출 → "YYYY-MM-DD".
 * 못 찾으면 시스템 today fallback.
 */
export function parseSimDateFromFiles(files: { name: string }[]): string {
  for (const f of files) {
    const m = f.name.match(/_(\d{8})\.[a-z]+$/i);
    if (m) {
      const s = m[1];
      return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
    }
  }
  return new Date().toISOString().slice(0, 10);
}

function makeEmptyStages(): AgentStageProgress[] {
  return [
    { step: 1, agent: "Collector", is_hil: false, received: 0, processed: 0, percent: 0, waiting_hil: false },
    { step: 2, agent: "Parser", is_hil: false, received: 0, processed: 0, percent: 0, waiting_hil: false },
    { step: 3, agent: "Mapper", is_hil: false, received: 0, processed: 0, percent: 0, waiting_hil: false },
    { step: 3.5, agent: "Human Review", is_hil: true, received: 0, processed: 0, percent: 0, waiting_hil: false },
    { step: 4, agent: "Atomizer", is_hil: false, received: 0, processed: 0, percent: 0, waiting_hil: false },
    { step: 5, agent: "Exporter", is_hil: false, received: 0, processed: 0, percent: 0, waiting_hil: false },
    { step: 6, agent: "Forecaster", is_hil: false, received: 0, processed: 0, percent: 0, waiting_hil: false },
    { step: 7, agent: "Optimizer", is_hil: false, received: 0, processed: 0, percent: 0, waiting_hil: false },
  ];
}

/**
 * sim 상태 + 현재 시각 기준으로 AgentWorkflowList 가 그대로 쓸 수 있는 8-stage 배열 반환.
 */
export function computeSimStages(sim: SimState, now: number): AgentStageProgress[] {
  const stages = makeEmptyStages();
  if (sim.phase === "idle" || !sim.phase1StartedAt) return stages;

  const total = sim.files.length || 1;

  // --- Phase 1: 진행 중이면 점진 증가, 이미 지났으면 100% 고정.
  const elapsedP1 = now - sim.phase1StartedAt;
  let acc = 0;
  for (const def of PHASE_1_STAGES) {
    const s = stages.find((x) => x.agent === def.agent)!;
    if (sim.phase === "phase1") {
      const local = Math.max(0, Math.min(def.ms, elapsedP1 - acc));
      const pct = (local / def.ms) * 100;
      s.percent = pct;
      s.received = total;
      s.processed = Math.floor((total * pct) / 100);
    } else {
      s.percent = 100;
      s.received = total;
      s.processed = total;
    }
    acc += def.ms;
  }

  // --- HIL stage
  const hil = stages.find((x) => x.is_hil)!;
  if (sim.phase === "hil_paused") {
    hil.received = HIL_LOW_CONFIDENCE_COUNT;
    hil.processed = 0;
    hil.percent = 0;
    hil.waiting_hil = true;
  } else if (sim.phase === "phase2" || sim.phase === "completed") {
    hil.received = HIL_LOW_CONFIDENCE_COUNT;
    hil.processed = HIL_LOW_CONFIDENCE_COUNT;
    hil.percent = 100;
    hil.waiting_hil = false;
  }

  // --- Phase 2
  if ((sim.phase === "phase2" || sim.phase === "completed") && sim.phase2StartedAt) {
    const elapsedP2 = now - sim.phase2StartedAt;
    let acc2 = 0;
    for (const def of PHASE_2_STAGES) {
      const s = stages.find((x) => x.agent === def.agent)!;
      if (sim.phase === "phase2") {
        const local = Math.max(0, Math.min(def.ms, elapsedP2 - acc2));
        const pct = (local / def.ms) * 100;
        s.percent = pct;
        s.received = total;
        s.processed = Math.floor((total * pct) / 100);
      } else {
        s.percent = 100;
        s.received = total;
        s.processed = total;
      }
      acc2 += def.ms;
    }
  }

  return stages;
}

/**
 * 8개 stage 의 가중 평균으로 sim 카드의 progress_percent 산출.
 * HIL 은 가중치 0.5 (다른 단계의 절반).
 */
export function computeOverallPercent(stages: AgentStageProgress[]): number {
  const weights = stages.map((s) => (s.is_hil ? 0.5 : 1));
  const totalW = weights.reduce((a, w) => a + w, 0);
  const sum = stages.reduce((acc, s, i) => acc + s.percent * weights[i], 0);
  return Math.round(sum / totalW);
}

// ---------------------------------------------------------------------------
// useSimTick — 250ms 마다 re-render 트리거 + phase 자동 전환
// ---------------------------------------------------------------------------

export function useSimTick(): number {
  const phase = useSimStore((s) => s.phase);
  const phase1StartedAt = useSimStore((s) => s.phase1StartedAt);
  const phase2StartedAt = useSimStore((s) => s.phase2StartedAt);
  const pauseAtHIL = useSimStore((s) => s.pauseAtHIL);
  const completeSimulation = useSimStore((s) => s.completeSimulation);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (phase !== "phase1" && phase !== "phase2") return;
    const id = setInterval(() => {
      setTick((t) => t + 1);
      const now = Date.now();
      if (phase === "phase1" && phase1StartedAt && now - phase1StartedAt >= PHASE_1_TOTAL_MS) {
        pauseAtHIL();
      } else if (phase === "phase2" && phase2StartedAt && now - phase2StartedAt >= PHASE_2_TOTAL_MS) {
        completeSimulation();
      }
    }, 250);
    return () => clearInterval(id);
  }, [phase, phase1StartedAt, phase2StartedAt, pauseAtHIL, completeSimulation]);

  return tick;
}
