// web/lib/progress-stages.ts
// progress/route.ts 의 percent 산출 순수 코어 (import sql 없음 — 단위테스트 가능).
// spec §6.5: agent_progress per-(run,agent) 행 기반, 각 stage 독립 계산.
// -1 sentinel + index 기반 prev/current/after 폐기.
import type { AgentStageProgress } from "@/lib/types";

export const STAGE_ORDER: Array<{
  step: number;
  agent: string;
  currentNode: string;
  is_hil: boolean;
}> = [
  { step: 1, agent: "Collector", currentNode: "collector", is_hil: false },
  { step: 2, agent: "Parser", currentNode: "parser", is_hil: false },
  { step: 3, agent: "Mapper", currentNode: "mapper", is_hil: false },
  { step: 3.5, agent: "Human Review", currentNode: "hil_1", is_hil: true },
  { step: 4, agent: "Atomizer", currentNode: "atomizer", is_hil: false },
  { step: 5, agent: "Exporter", currentNode: "exporter", is_hil: false },
  { step: 6, agent: "Forecaster", currentNode: "forecaster", is_hil: false },
  { step: 7, agent: "Optimizer", currentNode: "optimizer", is_hil: false },
];

export const UI_TO_AGENT_KEY: Record<string, string> = {
  Parser: "parser",
  Mapper: "mapper",
  Atomizer: "atomizer",
  Exporter: "exporter",
  Forecaster: "forecaster",
  Optimizer: "optimizer",
};

const POST_HIL1_NODES = new Set([
  "atomizer", "exporter", "forecaster", "hil_2", "optimizer", "reporter",
]);

export interface ProgressInputs {
  status: string;
  current_node: string | null;
  fileCount: number;
  parserRows: number;
  mapperRows: number;
  atomizedCount: number;
  agentProgress: Record<string, { processed: number; total: number }>;
}

function pct(processed: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((processed / total) * 100);
}

export function computeProgressStages(inp: ProgressInputs): AgentStageProgress[] {
  const isCompleted = inp.status === "completed";
  const isWaitingHil = inp.status === "waiting_hil_1";

  const FALLBACK_TOTAL: Record<string, number> = {
    Collector: inp.fileCount,
    Parser: inp.parserRows,
    Mapper: inp.mapperRows,
    "Human Review": inp.mapperRows,
    Atomizer: inp.atomizedCount,
    Exporter: inp.mapperRows,
    Forecaster: inp.mapperRows,
    Optimizer: inp.mapperRows,
  };

  const cn = inp.current_node ?? "collector";
  let activeIdx = STAGE_ORDER.findIndex((s) => s.currentNode === cn);
  if (activeIdx < 0) {
    activeIdx = POST_HIL1_NODES.has(cn) ? STAGE_ORDER.length - 1 : 0;
  }

  const maxRowIdx = STAGE_ORDER.reduce((acc, def, i) => {
    const key = UI_TO_AGENT_KEY[def.agent];
    return key && inp.agentProgress[key] ? Math.max(acc, i) : acc;
  }, -1);

  return STAGE_ORDER.map((def, i): AgentStageProgress => {
    const key = UI_TO_AGENT_KEY[def.agent];
    const row = key ? inp.agentProgress[key] : undefined;
    const fallbackTotal = FALLBACK_TOTAL[def.agent] ?? 0;

    let received: number;
    let processed: number;
    let percent: number;
    let waiting_hil = false;

    if (isCompleted) {
      received = row?.total ?? fallbackTotal;
      processed = received;
      percent = 100;
    } else if (def.is_hil && isWaitingHil && i === activeIdx) {
      received = fallbackTotal;
      processed = 0;
      percent = 0;
      waiting_hil = true;
    } else if (row) {
      received = row.total;
      processed = row.processed;
      percent = pct(row.processed, row.total);
    } else if (i < maxRowIdx || i < activeIdx) {
      received = fallbackTotal;
      processed = fallbackTotal;
      percent = 100;
    } else {
      received = 0;
      processed = 0;
      percent = 0;
    }

    return {
      step: def.step,
      agent: def.agent,
      is_hil: def.is_hil,
      received,
      processed,
      percent,
      waiting_hil,
    };
  });
}
