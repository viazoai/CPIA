// 결정적 mock 생성기 — 같은 siteIds + endDate + todayValues 면 같은 시계열.
// /reports ProductivityTrendChart 의 mulberry32 패턴을 fleet 레벨로 확장.
import type { FleetTrendPoint } from "./types";

function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number): () => number {
  return () => {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** 단일 현장 90일 시계열 — base 92 random walk + 후반 30일 감소 trend, 마지막 값은 todayValue 로 강제. */
export function generateSiteTrend(
  siteId: string,
  todayValue: number,
  days = 90,
): number[] {
  const rand = mulberry32(hashString(siteId));
  const out: number[] = [];
  let v = 92;
  for (let i = 0; i < days; i++) {
    const drift = (rand() - 0.5) * 4;
    const trend = i > days - 30 ? -(i - (days - 30)) * 0.2 : 0;
    v = Math.max(70, Math.min(105, v + drift + trend));
    out.push(Math.round(v * 10) / 10);
  }
  if (out.length > 0) out[out.length - 1] = todayValue;
  return out;
}

/** N 사이트의 시계열을 모아 평균/min/max FleetTrendPoint[] 도출. endDate 기준 절대 날짜 ISO 라벨. */
export function buildFleetTrend(
  perSite: Record<string, number[]>,
  endDate: string,
  days = 90,
): FleetTrendPoint[] {
  const endMs = new Date(endDate).getTime();
  const series = Object.values(perSite);
  const len = series[0]?.length ?? days;
  const out: FleetTrendPoint[] = [];
  for (let i = 0; i < len; i++) {
    const values = series.map((s) => s[i]).filter((v): v is number => typeof v === "number");
    if (values.length === 0) continue;
    const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const ms = endMs - (len - 1 - i) * 86400000;
    const d = new Date(ms);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    out.push({
      date: iso,
      mean: Math.round(mean * 10) / 10,
      min: Math.round(min * 10) / 10,
      max: Math.round(max * 10) / 10,
    });
  }
  return out;
}
