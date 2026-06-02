import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { WPSummaryTable } from "@/app/components/reports/WPSummaryTable";
import type { WPSummaryRow } from "@/lib/types";

const row: WPSummaryRow = {
  wp_id: "cub-철근콘크리트공사-남웅건설", wp_name: "철근콘크리트공사 · CUB",
  trade: "철근콘크리트공사", bp_name: "남웅건설", start_date: "", end_date: "",
  progress_pct: 0, productivity: 10, impact: 36, baseline: 100, status: "caution",
  recovery_days: 5, delay_days: 5,
};

describe("WPSummaryTable", () => {
  it("Impact·Productivity 헤더 없음, Work Area·지연일·단축 가능일 헤더 있음", () => {
    render(<WPSummaryTable rows={[row]} selectedWpId={null} onSelect={() => {}} />);
    expect(screen.queryByText("Impact")).toBeNull();
    expect(screen.queryByText("Productivity")).toBeNull();
    expect(screen.getByText("Work Area")).toBeTruthy();
    expect(screen.getByText("지연일")).toBeTruthy();
    expect(screen.getByText("단축 가능일")).toBeTruthy();
  });
  it("맨 왼쪽 셀이 WA 코드(CUB), 지연일 +5일", () => {
    render(<WPSummaryTable rows={[row]} selectedWpId={null} onSelect={() => {}} />);
    expect(screen.getByText("CUB")).toBeTruthy();
    expect(screen.getByText("+5일")).toBeTruthy();
  });
});
