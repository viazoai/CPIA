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

/* ───── 시나리오 곡선 생성 — 부분 만회 (no_action 대비 격차의 일부만 축소) ─────
 *
 * 2026-06-11 정정 (option 1): 이전엔 recoveryDays 만에 plan 에 "도달(따라잡음)" 시켰으나,
 * recoveryDays 는 사실 '과거 생산성 반등 일수'(≤7일)이지 누적 격차를 메우는 일수가 아니다.
 * 48일 뒤처진 현장을 5일에 따라잡는 그림은 거짓이라, plan 도달을 폐기하고 "지연(delayDays)
 * 중 recoveryDays 만큼만 만회" 하는 부분 회복선으로 정정한다.
 *
 * 모델:
 *   gap[i]   = plan[i] − forecast[i]            (forecast = no_action 추세, 격차 평행 유지)
 *   f        = clamp(recoveryDays / delayDays, 0..1)   (만회 비율, delay≤0 이면 1)
 *   AI[i]    = forecast[i] + f · gap[i]          (격차의 f 만큼만 plan 쪽으로 좁힘 — 도달 X)
 * forecast 결측 시 plan−gap0 (today 격차) 평행선으로 fallback. plan 에 도달하지 않으므로
 * catch-up 마커(plan 교차점)는 없다(null).
 */
function buildScenarioCurve(
  s_curve: SCurvePoint[],
  todayIdx: number,
  lastActual: number,
  recoveryDays: number,
  delayDays: number,
): { curve: (number | null)[]; catchUp: { date: string; percent: number } | null } {
  const out: (number | null)[] = [];
  const planAtToday = s_curve[todayIdx]?.planned ?? lastActual;
  const gap0 = Math.max(0, planAtToday - lastActual);
  // 만회 비율 — 지연 중 만회 가능한 몫. delay 없거나 recovery≥delay 면 전량(1).
  const f =
    delayDays > 0 ? Math.max(0, Math.min(1, recoveryDays / delayDays)) : recoveryDays > 0 ? 1 : 0;
  for (let i = 0; i < s_curve.length; i++) {
    if (i < todayIdx) {
      out.push(null); // 과거 — 라인 안 그림
      continue;
    }
    if (i === todayIdx) {
      out.push(lastActual); // 실적선과 연속
      continue;
    }
    const planAtI = s_curve[i]?.planned ?? planAtToday;
    // forecast(no_action): plan 과 today 격차(gap0) 유지하며 평행. 결측 시 평행 fallback.
    const fcAtI = s_curve[i]?.forecast ?? Math.max(0, planAtI - gap0);
    const v = fcAtI + f * (planAtI - fcAtI); // 격차의 f 만큼만 plan 쪽으로
    out.push(Math.max(0, Math.min(100, v)));
  }
  // plan 에 도달하지 않으므로 catch-up 교차 마커 없음.
  return { curve: out, catchUp: null };
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

  // BE scenarios recovery_days = 지연 중 만회 가능한 일수 (부분 회복 — plan 도달 보장 아님).
  // fallback: meanReversion 기반 estimate.
  const beP25 = input.recovery_days_p25 ?? Math.max(1, Math.round(recovery.p25));   // 비관 — 만회 적음
  const beP50 = input.recovery_days_p50 ?? Math.max(1, Math.round(recovery.p50));   // 기본
  const beP75 = input.recovery_days_p75 ?? Math.max(1, Math.round(recovery.p75));   // 낙관 — 만회 많음

  // 부분 만회 비율 산출용 — 현 추세 지연일. 미전달 시 0 (→ recovery>0 이면 전량 회복).
  const delay = Math.max(0, input.delay_days ?? 0);
  const baseRes = buildScenarioCurve(s_curve, todayIdx, lastActual, beP50, delay);
  const optRes  = buildScenarioCurve(s_curve, todayIdx, lastActual, beP75, delay);
  const pessRes = buildScenarioCurve(s_curve, todayIdx, lastActual, beP25, delay);
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
