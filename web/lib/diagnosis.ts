import type { DiagStatus, RecoveryEstimate } from "./types";

export function statusFromZ(z: number): DiagStatus {
  const abs = Math.abs(z);
  if (abs < 1) return "normal";
  if (abs < 2) return "caution";
  return "risk";
}

export function meanReversionRecovery(
  shortfall: number,
  mu: number,
  todayRate: number,
): RecoveryEstimate {
  const denom = mu - todayRate;
  if (denom <= 0) {
    return { p25: Infinity, p50: Infinity, p75: Infinity };
  }
  const p50 = shortfall / denom;
  return {
    p25: p50 * 0.7,
    p50,
    p75: p50 * 1.4,
  };
}
