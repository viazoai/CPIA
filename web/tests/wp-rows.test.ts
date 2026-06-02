import { describe, it, expect } from "vitest";
import { wpRowsForStatus } from "@/lib/wp-rows";

const rows = [
  { wp_id: "a", status: "risk", recovery_days: 5 },
  { wp_id: "b", status: "normal", recovery_days: 2 },
  { wp_id: "c", status: "caution", recovery_days: 1 },
] as any;

describe("wpRowsForStatus", () => {
  it("all → 전체 (visibleTrades/impact 필터 없음)", () => {
    expect(wpRowsForStatus(rows, "all")).toHaveLength(3);
  });
  it("risk → status 만 필터", () => {
    expect(wpRowsForStatus(rows, "risk").map((r) => r.wp_id)).toEqual(["a"]);
  });
  it("caution → status 만 필터", () => {
    expect(wpRowsForStatus(rows, "caution").map((r) => r.wp_id)).toEqual(["c"]);
  });
  it("빈 입력 → 빈 배열", () => {
    expect(wpRowsForStatus([], "risk")).toEqual([]);
  });
});
