import type { DiagnosisInput, ReportKpi, SCurvePoint } from "./types";
import type { ReportDetail } from "./fixtures";

/**
 * ReportDetail (mock fixture) 의 ReportKpi + s_curve 를 진단 모델 입력으로 변환.
 * A_Track 실 데이터 도착 시 본 함수만 교체하면 화면 영향 없음.
 *
 * mock 합리값:
 *   history_mean = ReportKpi.target_productivity (보통 97)
 *   history_std  = 4 (고정)
 *   sample_size  = site_id 해시 기반 12~48 균등 (결정적)
 *   today_progress = ReportKpi.productivity_today
 *
 * scenarios 전달 시: diagnose 는 buildScenarioCurve 의 completionOffset 을 BE recovery_days 기준으로 산출.
 */
export function toDiagnosisInput(
  reportKpi: ReportKpi,
  s_curve: SCurvePoint[],
  siteId: string,
  scenariosSite?: NonNullable<ReportDetail["scenarios"]>["site"],
): DiagnosisInput {
  return {
    site_id: siteId,
    today_progress: reportKpi.productivity_today,
    history_mean: reportKpi.target_productivity,
    history_std: 4,
    sample_size: deterministicSampleSize(siteId),
    s_curve,
    recovery_days_p25: scenariosSite?.pessimistic_p75?.recovery_days,
    recovery_days_p50: scenariosSite?.base_p50?.recovery_days,
    recovery_days_p75: scenariosSite?.optimistic_p25?.recovery_days,
    delay_days: reportKpi.delay_days,
  };
}

/** site_id 해시 → 12 ~ 48 범위 균등. 같은 siteId 면 항상 같은 값. */
function deterministicSampleSize(siteId: string): number {
  let h = 2166136261;
  for (let i = 0; i < siteId.length; i++) {
    h ^= siteId.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const unsigned = h >>> 0;
  return 12 + (unsigned % 37);
}
