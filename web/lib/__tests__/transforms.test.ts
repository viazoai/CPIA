import { describe, it, expect } from "vitest";
import {
  deriveProgressPercent,
  deriveYearlySaving,
  deriveItemStatus,
  deriveWpIdAndPath,
  deriveImpact,
} from "../transforms";

describe("G12 deriveProgressPercent", () => {
  it.each([
    [{ status: "completed", current_node: null }, 100],
    [{ status: "running", current_node: "optimizer" }, 90],
    [{ status: "running", current_node: "forecaster" }, 80],
    [{ status: "running", current_node: "exporter" }, 70],
    [{ status: "running", current_node: "atomizer" }, 60],
    [{ status: "waiting_hil_1", current_node: "mapper" }, 50],
    [{ status: "running", current_node: "mapper" }, 30],
    [{ status: "running", current_node: "parser" }, 20],
    [{ status: "running", current_node: null }, 0],
  ])("%o → %d", (input, expected) => {
    expect(deriveProgressPercent(input.status, input.current_node)).toBe(expected);
  });
});

describe("G1 deriveYearlySaving", () => {
  it("산식: fte*1.5 + hours*rate/1e8 → 단위 억", () => {
    // 15.4 * 1.5 + 2155 * 50000 / 1e8 = 23.1 + 1.0775 = 24.1775
    expect(deriveYearlySaving(15.4, 2155)).toBeCloseTo(24.18, 1);
  });
  it("custom hourlyRate", () => {
    expect(deriveYearlySaving(10, 1000, 60000)).toBeCloseTo(
      10 * 1.5 + (1000 * 60000) / 1e8,
      3,
    );
  });
});

describe("G11 deriveItemStatus", () => {
  it("Mapper requires_review true → hil_pending", () => {
    expect(
      deriveItemStatus("Mapper", { requires_review: true, mapping_conf: 0.4 }),
    ).toBe("hil_pending");
  });
  it("Mapper mapping_conf >= 0.7 → done", () => {
    expect(
      deriveItemStatus("Mapper", { requires_review: false, mapping_conf: 0.85 }),
    ).toBe("done");
  });
  it("Mapper 0.4 <= mapping_conf < 0.7 → processing", () => {
    expect(
      deriveItemStatus("Mapper", { requires_review: false, mapping_conf: 0.5 }),
    ).toBe("processing");
  });
  it("Mapper mapping_conf < 0.4 → received", () => {
    expect(
      deriveItemStatus("Mapper", { requires_review: false, mapping_conf: 0.2 }),
    ).toBe("received");
  });
  it("HIL Review has_correction → done", () => {
    expect(deriveItemStatus("HIL Review", { has_correction: true })).toBe("done");
  });
  it("HIL Review no correction → hil_pending", () => {
    expect(deriveItemStatus("HIL Review", { has_correction: false })).toBe(
      "hil_pending",
    );
  });
  it("risk_level=='이상' → blocked (모든 stage)", () => {
    expect(
      deriveItemStatus("Mapper", { risk_level: "이상", mapping_conf: 0.9 }),
    ).toBe("blocked");
  });
});

describe("G17 deriveWpIdAndPath", () => {
  it("wa+l6_main 조합", () => {
    expect(deriveWpIdAndPath("FAB", "철근콘크리트공사", "M15X Ph-3 IBL")).toEqual({
      wp_id: "fab-철근콘크리트공사",
      wp_name: "FAB 철근콘크리트공사",
      path: "M15X Ph-3 IBL > FAB > 철근콘크리트공사",
    });
  });
  it("null 입력 시 unknown", () => {
    expect(deriveWpIdAndPath(null, null, "site")).toEqual({
      wp_id: "unknown-unknown",
      wp_name: "",
      path: "site",
    });
  });
});

describe("G18 deriveImpact", () => {
  it("normalize to 0~100", () => {
    expect(deriveImpact(1e4, 1e3)).toBe(10); // 1e7 / 1e8 * 100 = 10
  });
  it("over normMax clamp 100", () => {
    expect(deriveImpact(1e6, 1e3)).toBe(100);
  });
  it("null 입력 → 0", () => {
    expect(deriveImpact(null, 100)).toBe(0);
    expect(deriveImpact(100, null)).toBe(0);
  });
});
