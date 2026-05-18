export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import type {
  DailyTask,
  AgentStageProgress,
  AgentTaskItem,
} from "@/lib/types";

const TRADES = [
  "철근공사", "거푸집공사", "콘크리트공사", "토공사", "방수공사",
  "조적공사", "미장공사", "타일공사", "도장공사", "마감공사",
  "전기공사", "기계설비", "소방설비", "건축철물", "비계공사",
];

const CONTRACTORS = [
  "(주)A건설", "(주)B건설", "동방건설", "대명E&C", "성진건설",
  "유진산업", "한주ENG", "선진건설", "광명건설", "건명산업",
];

const STAGE_DEFS: Array<{ step: number; name: string; is_hil: boolean }> = [
  { step: 1,   name: "Collector",  is_hil: false },
  { step: 2,   name: "Parser",     is_hil: false },
  { step: 3,   name: "Mapper",     is_hil: false },
  { step: 3.5, name: "HIL Review", is_hil: true  },
  { step: 4,   name: "Atomizer",   is_hil: false },
  { step: 5,   name: "Exporter",   is_hil: false },
  { step: 6,   name: "Forecaster", is_hil: false },
  { step: 7,   name: "Optimizer",  is_hil: false },
];

// 결정적 PRNG (mulberry32) — 날짜 기반 시드
function mulberry32(seed: number) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function seedFromDate(dateStr: string): number {
  // YYYY-MM-DD → 숫자
  return parseInt(dateStr.replace(/-/g, ""), 10);
}

function pick<T>(rnd: () => number, arr: T[]): T {
  return arr[Math.floor(rnd() * arr.length)];
}

function dateOffset(baseISO: string, daysAgo: number): string {
  const d = new Date(baseISO + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

interface DayBundle {
  task: DailyTask;
  progress: AgentStageProgress[];
  items: Record<string, AgentTaskItem[]>;  // by agent name
}

function generateDay(date: string, daysAgo: number): DayBundle {
  const rnd = mulberry32(seedFromDate(date));
  const total = 70 + Math.floor(rnd() * 30); // 70..99

  // 최근 day = running/review_pending, 그 외 completed
  let progressPercent: number;
  let status: DailyTask["status"];
  let hasAnomaly = rnd() < 0.18;

  if (daysAgo === 0) {
    progressPercent = 35 + Math.floor(rnd() * 35); // 35..69
    status = rnd() < 0.5 ? "review_pending" : "running";
  } else if (daysAgo === 1) {
    progressPercent = 88 + Math.floor(rnd() * 12); // 88..99
    status = "review_pending";
    hasAnomaly = rnd() < 0.5;
  } else {
    progressPercent = 100;
    status = "completed";
  }

  // 단계별 진행 계산 — 전체 진행률 progressPercent 를 8 단계에 골고루 흘림
  const stages: AgentStageProgress[] = [];
  STAGE_DEFS.forEach((def, idx) => {
    // 단계 시작 임계점 — 0..100 사이 (총 8단계)
    const stageStart = (idx / STAGE_DEFS.length) * 100;
    const stageEnd = ((idx + 1) / STAGE_DEFS.length) * 100;
    const stageReceivedFraction = Math.min(1, Math.max(0, (progressPercent - stageStart) / (stageEnd - stageStart)));

    // 이전 단계에서 흘러들어온 received
    const prevStageEndFraction = idx === 0 ? 1 : Math.min(1, Math.max(0, (progressPercent - (idx - 1) * 100 / STAGE_DEFS.length) / (100 / STAGE_DEFS.length)));
    const received = def.is_hil
      ? Math.round(total * 0.14 * prevStageEndFraction) // HIL은 일부만 (확신도 낮은 항목)
      : Math.round(total * prevStageEndFraction);

    const processed = def.is_hil
      ? Math.round(received * stageReceivedFraction)
      : Math.round(received * stageReceivedFraction);

    const percent = received === 0 ? 0 : Math.round((processed / received) * 100);
    const waitingHil = def.is_hil && processed < received && daysAgo === 0;

    stages.push({
      step: def.step,
      agent: def.name,
      is_hil: def.is_hil,
      received,
      processed,
      percent,
      waiting_hil: waitingHil,
    });
  });

  // 단계별 items 생성 — 단계당 sample 12개
  const items: Record<string, AgentTaskItem[]> = {};
  stages.forEach((s) => {
    const sampleCount = Math.min(12, s.received);
    const arr: AgentTaskItem[] = [];
    const itemRnd = mulberry32(seedFromDate(date) + Math.floor(s.step * 10));
    for (let i = 0; i < sampleCount; i++) {
      const idx = i + 1;
      const isProcessed = i < Math.round(sampleCount * (s.percent / 100));
      let st: AgentTaskItem["status"];
      if (s.is_hil) {
        st = isProcessed ? "done" : "hil_pending";
      } else if (isProcessed) {
        st = "done";
      } else if (i === Math.round(sampleCount * (s.percent / 100))) {
        st = "processing";
      } else {
        st = "received";
      }
      // 가끔 blocked 섞기 (이상 데이터)
      if (!s.is_hil && hasAnomaly && itemRnd() < 0.06) st = "blocked";

      arr.push({
        id: `RPT-${date.replace(/-/g, "")}-${String(idx).padStart(3, "0")}`,
        trade: pick(itemRnd, TRADES),
        contractor: pick(itemRnd, CONTRACTORS),
        status: st,
      });
    }
    items[s.agent] = arr;
  });

  return {
    task: { date, total_count: total, progress_percent: progressPercent, status, has_anomaly: hasAnomaly },
    progress: stages,
    items,
  };
}

export async function GET() {
  const BASE = "2026-05-15"; // 시연 기준일
  const DAYS = 30;

  const tasks: DailyTask[] = [];
  const progressByDate: Record<string, AgentStageProgress[]> = {};
  const itemsByDate: Record<string, Record<string, AgentTaskItem[]>> = {};

  for (let i = 0; i < DAYS; i++) {
    const date = dateOffset(BASE, i);
    const bundle = generateDay(date, i);
    tasks.push(bundle.task);
    progressByDate[date] = bundle.progress;
    itemsByDate[date] = bundle.items;
  }

  return NextResponse.json({
    tasks,
    progressByDate,
    itemsByDate,
  });
}
