import { describe, it, expect } from "vitest";
import { recoveryRepDays, toneFromRisk, parserMode, condText, sortRows } from "@/lib/agent-task-rows";
import type { AgentTaskRow } from "@/lib/types";

describe("recoveryRepDays", () => {
  it("d+N 최다 카운트의 N 을 D+N 으로", () => {
    expect(recoveryRepDays({ "d+1": 3, not_recovered: 2 })).toBe("D+1");
    expect(recoveryRepDays({ "d+2": 3, "d+1": 1 })).toBe("D+2");
  });
  it("동률이면 작은 N", () => {
    expect(recoveryRepDays({ "d+1": 1, "d+2": 1 })).toBe("D+1");
  });
  it("d+N 키 없으면 — (전부 미회복)", () => {
    expect(recoveryRepDays({ not_recovered: 5 })).toBe("—");
  });
  it("null/빈 객체 → —", () => {
    expect(recoveryRepDays(null)).toBe("—");
    expect(recoveryRepDays({})).toBe("—");
  });
});

describe("toneFromRisk", () => {
  it("이상→risk, 주의→caution, 그외→normal", () => {
    expect(toneFromRisk("이상")).toBe("risk");
    expect(toneFromRisk("주의")).toBe("caution");
    expect(toneFromRisk("정상")).toBe("normal");
    expect(toneFromRisk(null)).toBe("normal");
  });
});

describe("parserMode", () => {
  it("부속 합>0 → full, 0 → agg", () => {
    expect(parserMode({ content: 0, job: 0, equip: 0 })).toBe("agg");
    expect(parserMode({ content: 5, job: 0, equip: 0 })).toBe("full");
    expect(parserMode({ content: 0, job: 12, equip: 3 })).toBe("full");
  });
});

describe("condText", () => {
  it("jsonb 배열을 comma-join, 빈값은 정상", () => {
    expect(condText(["자재미입고"])).toBe("자재미입고");
    expect(condText(["정상"])).toBe("정상");
    expect(condText([])).toBe("정상");
    expect(condText(null)).toBe("정상");
  });
});

describe("sortRows", () => {
  it("미처리/위험 먼저, normal 마지막", () => {
    const mk = (tone: AgentTaskRow["statusTone"], id: string): AgentTaskRow =>
      ({ id, values: {}, statusLabel: "", statusTone: tone });
    const out = sortRows([mk("normal", "a"), mk("risk", "b"), mk("hil_pending", "c")]);
    // 결정 #8 TONE_SORT: hil_pending(2) < risk(4) < normal(7) → c, b, a
    expect(out.map((r) => r.id)).toEqual(["c", "b", "a"]);
  });
});
