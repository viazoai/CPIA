import { describe, it, expect } from "vitest";
import { wpRowsForStatus } from "@/lib/wp-rows";

const rows = [
  { wp_id: "a", status: "risk", recovery_days: 5 },
  { wp_id: "b", status: "normal", recovery_days: 2 },
] as any;

describe("wpRowsForStatus", () => {
  it("all → 전체 (visibleTrades/impact 필터 없음)", () => {
    expect(wpRowsForStatus(rows, "all")).toHaveLength(2);
  });
  it("risk → status 만 필터", () => {
    expect(wpRowsForStatus(rows, "risk").map((r) => r.wp_id)).toEqual(["a"]);
  });
});
