import { describe, it, expect } from "vitest";
import { AGENT_COLUMNS, PARSER_COLUMNS_FULL, PARSER_COLUMNS_AGG, statusHeaderFor } from "@/lib/agent-task-schema";

describe("AGENT_COLUMNS", () => {
  it("8단계 키가 모두 존재", () => {
    for (const a of ["Collector", "Parser", "Mapper", "Human Review", "Atomizer", "Exporter", "Forecaster", "Optimizer"]) {
      expect(AGENT_COLUMNS[a], a).toBeDefined();
    }
  });
  it("Forecaster 데이터 컬럼 4개(WA·WBS·업체·지연일, 진단은 상태칩)", () => {
    expect(AGENT_COLUMNS.Forecaster.map((c) => c.key)).toEqual(["warea", "wbs", "company", "delay"]);
  });
  it("Optimizer 데이터 컬럼 5개(+단축가능일)", () => {
    expect(AGENT_COLUMNS.Optimizer.map((c) => c.key)).toEqual(["warea", "wbs", "company", "delay", "recover"]);
  });
  it("Atomizer 에 조건 컬럼", () => {
    expect(AGENT_COLUMNS.Atomizer.map((c) => c.key)).toContain("cond");
  });
});

describe("PARSER 변형", () => {
  it("FULL=카테고리·건수, AGG=활동건수", () => {
    expect(PARSER_COLUMNS_FULL.map((c) => c.key)).toEqual(["trade", "company", "category", "count"]);
    expect(PARSER_COLUMNS_AGG.map((c) => c.key)).toEqual(["trade", "company", "count"]);
  });
});

describe("statusHeaderFor", () => {
  it("Forecaster/Optimizer=진단, Human Review=검토, 기타=상태", () => {
    expect(statusHeaderFor("Forecaster")).toBe("진단");
    expect(statusHeaderFor("Optimizer")).toBe("진단");
    expect(statusHeaderFor("Human Review")).toBe("검토");
    expect(statusHeaderFor("Mapper")).toBe("상태");
  });
});
