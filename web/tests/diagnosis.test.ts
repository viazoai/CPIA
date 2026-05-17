import { describe, it, expect } from "vitest";
import { statusFromZ, meanReversionRecovery } from "@/lib/diagnosis";

describe("statusFromZ", () => {
  it("|Z| < 1 → normal", () => {
    expect(statusFromZ(0)).toBe("normal");
    expect(statusFromZ(0.99)).toBe("normal");
    expect(statusFromZ(-0.99)).toBe("normal");
  });
  it("1 ≤ |Z| < 2 → caution", () => {
    expect(statusFromZ(1)).toBe("caution");
    expect(statusFromZ(-1.5)).toBe("caution");
    expect(statusFromZ(1.99)).toBe("caution");
  });
  it("|Z| ≥ 2 → risk", () => {
    expect(statusFromZ(2)).toBe("risk");
    expect(statusFromZ(-3)).toBe("risk");
  });
});

describe("meanReversionRecovery", () => {
  it("정상 분모 — P50 = shortfall / (μ − today)", () => {
    const r = meanReversionRecovery(50, 1.0, 0.5);
    expect(r.p50).toBe(100);
    expect(r.p25).toBeLessThan(r.p50);
    expect(r.p75).toBeGreaterThan(r.p50);
  });
  it("분모 = 0 (today === μ) → Infinity", () => {
    const r = meanReversionRecovery(50, 1.0, 1.0);
    expect(r.p25).toBe(Infinity);
    expect(r.p50).toBe(Infinity);
    expect(r.p75).toBe(Infinity);
  });
  it("분모 < 0 (격차 확대 중) → Infinity", () => {
    expect(meanReversionRecovery(50, 1.0, 1.2).p50).toBe(Infinity);
  });
});
