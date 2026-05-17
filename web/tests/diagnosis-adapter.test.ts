import { describe, it, expect } from "vitest";
import { toDiagnosisInput } from "@/lib/diagnosis-adapter";
import type { ReportKpi, SCurvePoint } from "@/lib/types";

function sampleKpi(overrides: Partial<ReportKpi> = {}): ReportKpi {
  return {
    productivity_today: 88,
    productivity_history_diff: -7,
    delay_days: 14,
    expected_completion: "2026-08-12",
    recoverable_productivity: 9,
    target_productivity: 97,
    recovery_days: 9,
    recovered_completion: "2026-08-03",
    ...overrides,
  };
}

function sampleSCurve(): SCurvePoint[] {
  return Array.from({ length: 20 }, (_, i) => ({
    date: `2026-05-${(i + 1).toString().padStart(2, "0")}`,
    planned: i * 5,
    actual: i < 14 ? i * 4.5 : undefined,
  }));
}

describe("toDiagnosisInput", () => {
  it("결정적 — 동일 입력 두 번 호출시 동일 출력", () => {
    const a = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-001");
    const b = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-001");
    expect(a).toEqual(b);
  });

  it("history_mean = target_productivity (보통 97)", () => {
    const input = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-001");
    expect(input.history_mean).toBe(97);
  });

  it("today_progress = productivity_today", () => {
    const input = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-001");
    expect(input.today_progress).toBe(88);
  });

  it("history_std 가 고정값 4", () => {
    const input = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-001");
    expect(input.history_std).toBe(4);
  });

  it("sample_size 가 12~48 범위 (결정적)", () => {
    const input = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-001");
    expect(input.sample_size).toBeGreaterThanOrEqual(12);
    expect(input.sample_size).toBeLessThanOrEqual(48);
  });

  it("다른 site_id 면 다른 sample_size 가능 (시드 차이)", () => {
    const a = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-001");
    const b = toDiagnosisInput(sampleKpi(), sampleSCurve(), "site-OTHER");
    expect(a.history_mean).toBe(b.history_mean);
    expect(a.today_progress).toBe(b.today_progress);
  });

  it("s_curve 가 그대로 전달", () => {
    const s = sampleSCurve();
    const input = toDiagnosisInput(sampleKpi(), s, "site-001");
    expect(input.s_curve).toBe(s);
  });

  it("site_id 가 그대로 전달", () => {
    const input = toDiagnosisInput(sampleKpi(), sampleSCurve(), "M15X-Ph3");
    expect(input.site_id).toBe("M15X-Ph3");
  });
});
