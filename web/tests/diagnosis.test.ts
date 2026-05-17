import { describe, it, expect } from "vitest";
import { statusFromZ, meanReversionRecovery, diagnose } from "@/lib/diagnosis";
import type { DiagnosisInput, SCurvePoint } from "@/lib/types";

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

function sampleInput(overrides: Partial<DiagnosisInput> = {}): DiagnosisInput {
  const s_curve: SCurvePoint[] = Array.from({ length: 20 }, (_, i) => ({
    date: `2026-05-${(i + 1).toString().padStart(2, "0")}`,
    planned: i * 5,
    actual: i < 14 ? i * 4.5 : undefined,
  }));
  return {
    site_id: "site-001",
    today_progress: 88,
    history_mean: 95,
    history_std: 4,
    sample_size: 24,
    s_curve,
    ...overrides,
  };
}

describe("diagnose", () => {
  it("결정적 — 동일 입력 두 번 호출시 동일 출력", () => {
    const a = diagnose(sampleInput());
    const b = diagnose(sampleInput());
    expect(a).toEqual(b);
  });

  it("productivity_score / gap_pct / z_score 산출", () => {
    const d = diagnose(sampleInput());
    expect(d.productivity_score).toBeCloseTo((88 / 95) * 100, 4);
    expect(d.gap_pct).toBeCloseTo(d.productivity_score - 100, 4);
    expect(d.z_score).toBeCloseTo((88 - 95) / 4, 4);
  });

  it("z_score 와 status 일관 (statusFromZ 와 동일)", () => {
    const d = diagnose(sampleInput());
    const abs = Math.abs(d.z_score);
    if (abs < 1) expect(d.status).toBe("normal");
    else if (abs < 2) expect(d.status).toBe("caution");
    else expect(d.status).toBe("risk");
  });

  it("시계열 길이 = s_curve 길이", () => {
    const d = diagnose(sampleInput());
    expect(d.band_p25).toHaveLength(d.s_curve.length);
    expect(d.band_p75).toHaveLength(d.s_curve.length);
    expect(d.ewma_trend).toHaveLength(d.s_curve.length);
    expect(d.scenarios.base.curve).toHaveLength(d.s_curve.length);
    expect(d.scenarios.optimistic.curve).toHaveLength(d.s_curve.length);
    expect(d.scenarios.pessimistic.curve).toHaveLength(d.s_curve.length);
  });

  it("scenarios.base.eta_days === recovery.p50_days", () => {
    const d = diagnose(sampleInput());
    expect(d.scenarios.base.eta_days).toBe(d.recovery.p50_days);
  });

  it("음수 격차 입력 — pessimistic.delta_completion_days > 0 (지연)", () => {
    const d = diagnose(sampleInput({ today_progress: 70 }));
    expect(d.scenarios.pessimistic.delta_completion_days).toBeGreaterThan(0);
  });

  it("today === μ — recovery 무한대 + base eta Infinity", () => {
    const d = diagnose(sampleInput({ today_progress: 95 }));
    expect(d.recovery.p50_days).toBe(Infinity);
    expect(d.scenarios.base.eta_days).toBe(Infinity);
  });
});
