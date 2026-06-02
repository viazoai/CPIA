import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentTaskItemList } from "@/app/components/tasks/AgentTaskItemList";

describe("AgentTaskItemList", () => {
  it("columns props 로 동적 헤더 + values 렌더, Forecaster 상태헤더=진단", () => {
    render(
      <AgentTaskItemList
        selectedAgent="Forecaster"
        stage={{ step: 6, agent: "Forecaster", is_hil: false, received: 1, processed: 1, percent: 100, waiting_hil: false }}
        columns={[{ key: "warea", label: "Work Area" }, { key: "wbs", label: "WBS" }]}
        rows={[{ id: "001", values: { warea: "FAB", wbs: "C/R 조성공사" }, statusLabel: "이상", statusTone: "risk" }]}
      />
    );
    expect(screen.getByText("Work Area")).toBeDefined();
    expect(screen.getByText("진단")).toBeDefined();      // statusHeader
    expect(screen.getByText("C/R 조성공사")).toBeDefined();
    expect(screen.getByText("이상")).toBeDefined();        // statusLabel
  });
});
