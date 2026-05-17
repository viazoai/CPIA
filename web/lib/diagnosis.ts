import type {
  DiagStatus,
  DiagnosisInput,
  ProductivityDiagnosis,
  RecoveryEstimate,
  SCurvePoint,
  ScenarioPoint,
} from "./types";

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

/* ───── 결정적 PRNG ───── */
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

/* ───── EWMA ───── */
function ewma(values: (number | undefined)[], lambda: number): number[] {
  const out: number[] = [];
  let prev = values.find((v) => v !== undefined) ?? 0;
  for (const v of values) {
    const cur = v ?? prev;
    prev = lambda * cur + (1 - lambda) * prev;
    out.push(prev);
  }
  return out;
}

/* ───── 시나리오 곡선 생성 ───── */
function buildScenarioCurve(
  s_curve: SCurvePoint[],
  todayIdx: number,
  lastActual: number,
  perStepRate: number,
  rand: () => number,
  noise: number,
): (number | null)[] {
  const out: (number | null)[] = [];
  let cum = lastActual;
  for (let i = 0; i < s_curve.length; i++) {
    if (i < todayIdx) {
      out.push(null);                       // 과거 — 선 안 그림
    } else if (i === todayIdx) {
      out.push(lastActual);                 // 오늘 — 실적선과 연결되는 시작점
    } else {
      const jitter = (rand() - 0.5) * noise;
      cum = Math.min(100, Math.max(0, cum + perStepRate * (1 + jitter)));
      out.push(cum);
    }
  }
  return out;
}

/* ───── 진단 메인 ───── */
export function diagnose(input: DiagnosisInput): ProductivityDiagnosis {
  const { site_id, today_progress, history_mean, history_std, sample_size, s_curve } = input;
  const rand = mulberry32(hashString(site_id));

  const productivity_score = (today_progress / history_mean) * 100;
  const gap_pct = productivity_score - 100;
  const z_score = (today_progress - history_mean) / history_std;
  const status = statusFromZ(z_score);

  const band_p25 = s_curve.map((p) => Math.max(0, p.planned - history_std * 1.5));
  const band_p75 = s_curve.map((p) => Math.min(100, p.planned + history_std * 1.5));

  const ewma_trend = ewma(s_curve.map((p) => p.actual), 0.3);

  const firstUndef = s_curve.findIndex((p) => p.actual === undefined);
  const todayIdx = firstUndef === -1 ? s_curve.length - 1 : firstUndef - 1;
  const lastActual = todayIdx >= 0 ? (s_curve[todayIdx].actual ?? 0) : 0;
  const lastPlanned = todayIdx >= 0 ? s_curve[todayIdx].planned : 0;
  const shortfall = Math.max(0, lastPlanned - lastActual);

  const muStep = history_mean / 100;
  const todayStep = today_progress / 100;
  const recovery = meanReversionRecovery(shortfall / 100, muStep, todayStep);
  const finite = Number.isFinite(recovery.p50);

  const baseStep = history_mean / 4;
  const optimisticStep = baseStep * 1.18;
  const pessimisticStep = today_progress / 4;

  const baseCurve = buildScenarioCurve(s_curve, todayIdx, lastActual, baseStep, rand, 0.05);
  const optCurve  = buildScenarioCurve(s_curve, todayIdx, lastActual, optimisticStep, rand, 0.08);
  const pessCurve = buildScenarioCurve(s_curve, todayIdx, lastActual, pessimisticStep, rand, 0.05);

  const base: ScenarioPoint = {
    eta_days: finite ? Math.round(recovery.p50) : Infinity,
    recovery_pct: 100,
    delta_completion_days: finite ? Math.round(recovery.p50) : 999,
    curve: baseCurve,
  };
  const optimistic: ScenarioPoint = {
    eta_days: finite ? Math.round(recovery.p25) : Infinity,
    recovery_pct: 102,
    delta_completion_days: finite ? -Math.max(1, Math.round((recovery.p50 - recovery.p25) * 0.6)) : 0,
    curve: optCurve,
  };
  const pessimistic: ScenarioPoint = {
    eta_days: Infinity,
    recovery_pct: status === "risk" ? 85 : 92,
    delta_completion_days: status === "risk"
      ? Math.max(20, Math.round((finite ? recovery.p50 : 30) * 1.6))
      : Math.max(10, Math.round((finite ? recovery.p50 : 20) * 1.4)),
    curve: pessCurve,
  };

  return {
    history_mean,
    history_std,
    sample_size,
    today_progress,
    productivity_score,
    gap_pct,
    z_score,
    status,
    s_curve,
    band_p25,
    band_p75,
    ewma_trend,
    recovery: {
      p25_days: Number.isFinite(recovery.p25) ? Math.round(recovery.p25) : Infinity,
      p50_days: Number.isFinite(recovery.p50) ? Math.round(recovery.p50) : Infinity,
      p75_days: Number.isFinite(recovery.p75) ? Math.round(recovery.p75) : Infinity,
    },
    scenarios: { optimistic, base, pessimistic },
  };
}
