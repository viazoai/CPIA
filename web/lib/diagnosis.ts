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

/* ───── 시나리오 곡선 생성 — completion offset 기반 균등 slope ─────
 *
 * 이전: perStepRate (history_mean/4 = 24%) 매 step 누적 → 4일 만에 100% 폭주.
 * 변경: completionOffset (오늘부터 100% 도달까지 일수) 받아 (100-lastActual)/offset slope.
 * 그러면 시나리오 곡선이 lastActual 부터 자연스럽게 100% 까지 이어진다.
 */
function buildScenarioCurve(
  s_curve: SCurvePoint[],
  todayIdx: number,
  lastActual: number,
  completionOffset: number,
): (number | null)[] {
  const out: (number | null)[] = [];
  const slope = completionOffset > 0 ? (100 - lastActual) / completionOffset : 0;
  for (let i = 0; i < s_curve.length; i++) {
    if (i < todayIdx) {
      out.push(null);                       // 과거 — 선 안 그림
    } else if (i === todayIdx) {
      out.push(lastActual);                 // 오늘 — 실적선과 연결되는 시작점
    } else {
      const offset = i - todayIdx;
      const cum = Math.min(100, Math.max(0, lastActual + slope * offset));
      out.push(cum);
    }
  }
  return out;
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

  // completionOffset 산출 — BE scenarios 가 있으면 그 기준, 없으면 planned 100% 도달까지 거리 fallback.
  // 1) planned 가 100% 도달하는 첫 인덱스
  let planned100Idx = s_curve.length - 1;
  for (let i = todayIdx; i < s_curve.length; i++) {
    const p = s_curve[i].planned ?? 0;
    if (p >= 100) { planned100Idx = i; break; }
  }
  const remainingPlanDays = Math.max(1, planned100Idx - todayIdx);
  const beDelay = input.delay_days ?? 0;             // 양수 = 지연
  const beP25 = input.recovery_days_p25 ?? 0;        // 비관 — 만회 적음
  const beP50 = input.recovery_days_p50 ?? 0;        // 기본
  const beP75 = input.recovery_days_p75 ?? 0;        // 낙관 — 만회 많음
  // no_action_offset = 계획 잔여일 + 지연일 (현 추세 연장 시 완공까지)
  const noActionOffset = remainingPlanDays + Math.max(0, beDelay);
  // base/optimistic/pessimistic 각 완공 도달 일수
  const baseOffset        = Math.max(1, noActionOffset - beP50);
  const optimisticOffset  = Math.max(1, noActionOffset - beP75);
  const pessimisticOffset = Math.max(1, noActionOffset - beP25 + Math.max(0, beDelay));

  const baseCurve = buildScenarioCurve(s_curve, todayIdx, lastActual, baseOffset);
  const optCurve  = buildScenarioCurve(s_curve, todayIdx, lastActual, optimisticOffset);
  const pessCurve = buildScenarioCurve(s_curve, todayIdx, lastActual, pessimisticOffset);

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
