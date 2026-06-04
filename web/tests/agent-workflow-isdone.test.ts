import { describe, it, expect } from "vitest";
import { computeProgressStages, type ProgressInputs } from "@/lib/progress-stages";

// AgentWorkflowList.tsx 의 판정 로직 (markup 불변 — 여기 복제는 계약 고정용).
const isDone = (s: { received: number; processed: number; waiting_hil: boolean }) =>
  s.received > 0 && s.processed === s.received && !s.waiting_hil;
const isInflight = (s: { received: number; percent: number; waiting_hil: boolean }) =>
  s.received > 0 && s.percent < 100 && !s.waiting_hil;

function inp(o: Partial<ProgressInputs> = {}): ProgressInputs {
  return { status: "running", current_node: "mapper", fileCount: 7,
    parserRows: 330, mapperRows: 330, hilCount: 100, atomizedCount: 0, agentProgress: {}, ...o };
}

describe("AgentWorkflowList 계약 — markup 불변", () => {
  it("completed 단계는 isDone=true (processed===received 보장)", () => {
    const st = computeProgressStages(inp({ status: "completed", current_node: "optimizer", atomizedCount: 330 }));
    expect(st.every(isDone)).toBe(true);
  });
  it("진행중 mapper(50/330)는 isInflight=true, isDone=false", () => {
    const st = computeProgressStages(inp({ agentProgress: { mapper: { processed: 50, total: 330 } } }));
    const m = st.find((s) => s.agent === "Mapper")!;
    expect(isInflight(m)).toBe(true);
    expect(isDone(m)).toBe(false);
  });
  it("active 이전 단계(Parser)는 isDone=true", () => {
    const st = computeProgressStages(inp({ agentProgress: { mapper: { processed: 50, total: 330 } } }));
    expect(isDone(st.find((s) => s.agent === "Parser")!)).toBe(true);
  });
  it("width=`${percent}%` 가 항상 0..100 (NaN/-1 금지 — style 깨짐 방지)", () => {
    const st = computeProgressStages(inp({ agentProgress: { exporter: { processed: 0, total: 0 } } }));
    for (const s of st) { expect(s.percent).toBeGreaterThanOrEqual(0); expect(s.percent).toBeLessThanOrEqual(100); }
  });
});
