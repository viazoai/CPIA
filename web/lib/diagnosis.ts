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

/* ───── 시나리오 곡선 생성 — catch-up + plan 동행 ─────
 *
 * 의미: AI 만회 시나리오 = recoveryDays 만에 plan 따라잡고, 그 후 plan 곡선 동행.
 * 1) catch-up 구간 (today ~ today+recoveryDays): lastActual → plan[today+recoveryDays] 직선 slope
 * 2) catch-up 이후: plan 그대로 동행 (별도 100% 도달이 아니라 plan 의 완공일에 함께 도달)
 *
 * 이전 산식 (completionOffset 기반 lastActual→100% 직진) 은 "AI 만회 = 더 늦게 완공" 처럼
 * 보였음. 사용자 의도 = "중간에 plan 따라잡음" 으로 정정.
 */
function buildScenarioCurve(
  s_curve: SCurvePoint[],
  todayIdx: number,
  lastActual: number,
  recoveryDays: number,
): { curve: (number | null)[]; catchUp: { date: string; percent: number } | null } {
  const out: (number | null)[] = [];
  const catchUpEndIdx = Math.min(s_curve.length - 1, todayIdx + Math.max(1, recoveryDays));
  const planAtCatchUp = s_curve[catchUpEndIdx]?.planned ?? 100;
  const span = Math.max(1, catchUpEndIdx - todayIdx);
  const catchUpSlope = (planAtCatchUp - lastActual) / span;
  for (let i = 0; i < s_curve.length; i++) {
    if (i < todayIdx) {
      out.push(null); // 과거 — 라인 안 그림
    } else if (i === todayIdx) {
      out.push(lastActual);
    } else if (i <= catchUpEndIdx) {
      // catch-up 구간만 dashed slope
      const offset = i - todayIdx;
      out.push(Math.max(0, Math.min(100, lastActual + catchUpSlope * offset)));
    } else {
      // catch-up 후 plan 따라잡았으니 라인 안 그림 (plan 곡선이 대신 그려짐)
      out.push(null);
    }
  }
  const catchUpDate = s_curve[catchUpEndIdx]?.date ?? "";
  return {
    curve: out,
    catchUp: catchUpDate
      ? { date: catchUpDate, percent: Math.max(0, Math.min(100, planAtCatchUp)) }
      : null,
  };
}

/* ───── 진단 메인 ───── */
export function diagnose(input: DiagnosisInput): ProductivityDiagnosis {
  const { today_progress, history_mean, history_std, sample_size, s_curve } = input;

  const productivity_score = (today_progress / history_mean) * 100;
  const gap_pct = productivity_score - 100;
  const z_score = (today_progress - history_mean) / history_std;
  const status = statusFromZ(z_score);

  const band_p25 = s_curve.map((p) => Math.max(0, p.planned - history_std * 1.5));
  const band_p75 = s_curve.map((p) => Math.min(100, p.planned + history_std * 1.5));

  const ewma_trend = ewma(s_curve.map((p) => p.actual), 0.3);

  // todayIdx — actual 가 채워진 마지막 위치. 기존 findIndex(undefined) 는 sparse hole 잡아 0 됨.
  let todayIdx = -1;
  for (let i = s_curve.length - 1; i >= 0; i--) {
    const v = s_curve[i].actual;
    if (v !== undefined && v !== null) { todayIdx = i; break; }
  }
  if (todayIdx < 0) todayIdx = s_curve.length - 1;
  const lastActual = todayIdx >= 0 ? (s_curve[todayIdx].actual ?? 0) : 0;
  const lastPlanned = todayIdx >= 0 ? (s_curve[todayIdx].planned ?? 0) : 0;
  const shortfall = Math.max(0, lastPlanned - lastActual);

  const muStep = history_mean / 100;
  const todayStep = today_progress / 100;
  const recovery = meanReversionRecovery(shortfall / 100, muStep, todayStep);
  const finite = Number.isFinite(recovery.p50);

  // BE scenarios recovery_days = plan 따라잡는 데 걸리는 일수 (catch-up 일수).
  // fallback: meanReversion 기반 estimate.
  const beP25 = input.recovery_days_p25 ?? Math.max(1, Math.round(recovery.p25));   // 비관 — 만회 적음
  const beP50 = input.recovery_days_p50 ?? Math.max(1, Math.round(recovery.p50));   // 기본
  const beP75 = input.recovery_days_p75 ?? Math.max(1, Math.round(recovery.p75));   // 낙관 — 만회 많음

  const baseRes = buildScenarioCurve(s_curve, todayIdx, lastActual, beP50);
  const optRes  = buildScenarioCurve(s_curve, todayIdx, lastActual, beP75);
  const pessRes = buildScenarioCurve(s_curve, todayIdx, lastActual, beP25);
  const baseCurve = baseRes.curve;
  const optCurve  = optRes.curve;
  const pessCurve = pessRes.curve;
  const baseCatchUp = baseRes.catchUp ?? undefined;
  const optCatchUp = optRes.catchUp ?? undefined;
  const pessCatchUp = pessRes.catchUp ?? undefined;

  const base: ScenarioPoint = {
    eta_days: beP50,
    recovery_pct: 100,
    delta_completion_days: 0,                  // catch-up 후 plan 동행 → 계획 동일
    curve: baseCurve,
    catch_up: baseCatchUp,
  };
  const optimistic: ScenarioPoint = {
    eta_days: beP75,
    recovery_pct: 102,
    delta_completion_days: 0,
    curve: optCurve,
    catch_up: optCatchUp,
  };
  const pessimistic: ScenarioPoint = {
    eta_days: beP25,
    recovery_pct: 100,
    delta_completion_days: 0,
    curve: pessCurve,
    catch_up: pessCatchUp,
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
