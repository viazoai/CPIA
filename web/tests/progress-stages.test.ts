import { describe, it, expect } from "vitest";
import {
  computeProgressStages,
  STAGE_ORDER,
  UI_TO_AGENT_KEY,
  type ProgressInputs,
} from "@/lib/progress-stages";
import type { AgentStageProgress } from "@/lib/types";

function base(overrides: Partial<ProgressInputs> = {}): ProgressInputs {
  return {
    status: "running",
    current_node: "parser",
    fileCount: 7,
    parserRows: 0,
    mapperRows: 0,
    hilCount: 0,
    atomizedCount: 0,
    agentProgress: {},
    ...overrides,
  };
}
const by = (st: AgentStageProgress[], a: string) => st.find((s) => s.agent === a)!;

describe("computeProgressStages", () => {
  it("8 stages 고정 순서/step/agent/is_hil (markup 계약)", () => {
    const st = computeProgressStages(base());
    expect(st.map((s) => s.agent)).toEqual([
      "Collector", "Parser", "Mapper", "Human Review",
      "Atomizer", "Exporter", "Forecaster", "Optimizer",
    ]);
    expect(st.map((s) => s.step)).toEqual([1, 2, 3, 3.5, 4, 5, 6, 7]);
    expect(by(st, "Human Review").is_hil).toBe(true);
    expect(st.filter((s) => s.is_hil).length).toBe(1);
  });

  it("절대 percent=-1 을 내지 않는다 (sentinel 폐기)", () => {
    for (const cn of [null, "collector", "parser", "mapper", "atomizer", "forecaster", "optimizer"]) {
      const st = computeProgressStages(base({ current_node: cn }));
      expect(st.every((s) => s.percent !== -1), `cn=${cn}`).toBe(true);
      expect(st.every((s) => s.percent >= 0 && s.percent <= 100)).toBe(true);
    }
  });

  it("자기 agent_progress 행: received=total, processed=processed, percent=round(p/t*100)", () => {
    const st = computeProgressStages(
      base({ current_node: "parser", agentProgress: { parser: { processed: 3, total: 7 } } }),
    );
    const p = by(st, "Parser");
    expect(p.received).toBe(7);
    expect(p.processed).toBe(3);
    expect(p.percent).toBe(43);
  });

  it("division 가드: total=0 행이면 percent=0 (NaN/Infinity 금지)", () => {
    const st = computeProgressStages(
      base({ current_node: "exporter", agentProgress: { exporter: { processed: 0, total: 0 } } }),
    );
    const e = by(st, "Exporter");
    expect(e.percent).toBe(0);
    expect(Number.isFinite(e.percent)).toBe(true);
  });

  it("나중 단계 행 존재 → 그 이전 단계는 100% (자기 행 없어도)", () => {
    const st = computeProgressStages(
      base({ current_node: "forecaster", agentProgress: { forecaster: { processed: 2, total: 10 } } }),
    );
    expect(by(st, "Parser").percent).toBe(100);
    expect(by(st, "Mapper").percent).toBe(100);
    expect(by(st, "Forecaster").percent).toBe(20);
  });

  it("status=completed → 전 단계 100% + processed===received (isDone 정합)", () => {
    const st = computeProgressStages(
      base({ status: "completed", current_node: "optimizer", fileCount: 7, parserRows: 330, mapperRows: 330 }),
    );
    for (const s of st) {
      expect(s.percent, s.agent).toBe(100);
      expect(s.processed, s.agent).toBe(s.received);
    }
  });

  it("행 없고 active 이전 단계 → fallback count(received=processed=count, percent=100)", () => {
    const st = computeProgressStages(
      base({ current_node: "mapper", parserRows: 330, agentProgress: { mapper: { processed: 50, total: 330 } } }),
    );
    const p = by(st, "Parser");
    expect(p.received).toBe(330);
    expect(p.processed).toBe(330);
    expect(p.percent).toBe(100);
  });

  it("행 없고 active 이후 단계 → 0 (received=processed=0)", () => {
    const st = computeProgressStages(
      base({ current_node: "mapper", agentProgress: { mapper: { processed: 5, total: 330 } } }),
    );
    for (const a of ["Atomizer", "Exporter", "Forecaster", "Optimizer"]) {
      const s = by(st, a);
      expect(s.percent, a).toBe(0);
      expect(s.received, a).toBe(0);
      expect(s.processed, a).toBe(0);
    }
  });

  it("Collector=fileCount(파일수), Human Review=hilCount fallback (총 mapperRows 아님)", () => {
    const st = computeProgressStages(
      base({ current_node: "atomizer", fileCount: 7, mapperRows: 330, hilCount: 51,
             agentProgress: { atomizer: { processed: 1, total: 5 } } }),
    );
    expect(by(st, "Collector").received).toBe(7);
    expect(by(st, "Collector").percent).toBe(100);
    const hr = by(st, "Human Review");
    expect(hr.received).toBe(51); // 검토 대상(requires_review)만 — 총 활동 330 아님
    expect(hr.percent).toBe(100);
  });

  it("waiting_hil_1 분기 유지: Human Review waiting_hil=true, percent=0, received=hilCount(검토대상)", () => {
    const st = computeProgressStages(
      base({ status: "waiting_hil_1", current_node: "hil_1", mapperRows: 115, hilCount: 49 }),
    );
    const hr = by(st, "Human Review");
    expect(hr.waiting_hil).toBe(true);
    expect(hr.percent).toBe(0);
    expect(hr.received).toBe(49); // 115(총) 아님 — 게이트 통과 못한 49건만
    expect(hr.processed).toBe(0);
  });

  it("UI명→agent키 매핑 테이블 (parser 등 6개 + Collector/Human Review 제외)", () => {
    expect(UI_TO_AGENT_KEY).toEqual({
      Parser: "parser",
      Mapper: "mapper",
      Atomizer: "atomizer",
      Exporter: "exporter",
      Forecaster: "forecaster",
      Optimizer: "optimizer",
    });
  });

  it("결정성: 동일 입력 2회 → 동일 출력", () => {
    const inp = base({ current_node: "mapper", agentProgress: { mapper: { processed: 50, total: 330 } } });
    expect(computeProgressStages(inp)).toEqual(computeProgressStages(inp));
  });
});
