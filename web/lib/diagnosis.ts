import type { DiagStatus } from "./types";

export function statusFromZ(z: number): DiagStatus {
  const abs = Math.abs(z);
  if (abs < 1) return "normal";
  if (abs < 2) return "caution";
  return "risk";
}
