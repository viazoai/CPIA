import type { AgentItemTone, AgentTaskRow } from "@/lib/types";

/** recovery_distribution(JSONB) → 대표 단축일 "D+N". d+N 키 중 카운트 최다(동률 시 작은 N).
 *  d+N 키가 없으면(전부 미회복) "—". */
export function recoveryRepDays(dist: Record<string, number> | null | undefined): string {
  if (!dist) return "—";
  let bestN = Infinity;
  let bestCount = -1;
  for (const [k, v] of Object.entries(dist)) {
    const m = /^d\+(\d+)$/.exec(k);
    if (!m) continue; // not_recovered 등 제외
    const n = Number(m[1]);
    const c = Number(v) || 0;
    if (c > bestCount || (c === bestCount && n < bestN)) {
      bestCount = c;
      bestN = n;
    }
  }
  return bestCount < 0 ? "—" : `D+${bestN}`;
}

/** forecasts.risk_level("정상|주의|이상") → 진단 톤. */
export function toneFromRisk(risk: string | null | undefined): AgentItemTone {
  return risk === "이상" ? "risk" : risk === "주의" ? "caution" : "normal";
}

/** 시트1/2/3 부속 건수 합 > 0 이면 풀 파싱 run(full), 0 이면 적재 시드(agg). */
export function parserMode(counts: { content: number; job: number; equip: number }): "full" | "agg" {
  return counts.content + counts.job + counts.equip > 0 ? "full" : "agg";
}

/** mapper_activities.conditions(jsonb 배열) → 표시 문자열. 빈값은 "정상". */
export function condText(conds: string[] | null | undefined): string {
  if (!conds || conds.length === 0) return "정상";
  return conds.join(", ");
}

const TONE_SORT: Record<AgentItemTone, number> = {
  processing: 0, received: 1, hil_pending: 2, blocked: 3,
  risk: 4, caution: 5, done: 6, normal: 7,
};

export function sortRows(rows: AgentTaskRow[]): AgentTaskRow[] {
  return [...rows].sort((a, b) => (TONE_SORT[a.statusTone] ?? 9) - (TONE_SORT[b.statusTone] ?? 9));
}
