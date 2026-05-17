import { diagnose } from "@/lib/diagnosis";
import type { DiagnosisInput, SCurvePoint } from "@/lib/types";
import { SpiBandChart } from "@/app/components/charts/SpiBandChart";
import { GapKpiCard } from "@/app/components/reports/GapKpiCard";
import { RecoveryEtaCard } from "@/app/components/reports/RecoveryEtaCard";
import { ConfidenceBadge } from "@/app/components/reports/ConfidenceBadge";

function makeSCurve(actualSlope: number): SCurvePoint[] {
  return Array.from({ length: 20 }, (_, i) => ({
    date: `2026-05-${(i + 1).toString().padStart(2, "0")}`,
    planned: i * 5,
    actual: i < 14 ? Math.round(i * actualSlope * 10) / 10 : undefined,
  }));
}

const SAMPLES: { title: string; input: DiagnosisInput }[] = [
  {
    title: "M15X Ph-3 IBL · 정상 구간",
    input: {
      site_id: "M15X-Ph3-IBL",
      today_progress: 94,
      history_mean: 95,
      history_std: 4,
      sample_size: 32,
      s_curve: makeSCurve(4.7),
    },
  },
  {
    title: "Hi-tech-A 건물 · 주의 구간",
    input: {
      site_id: "Hi-tech-A",
      today_progress: 88,
      history_mean: 95,
      history_std: 4,
      sample_size: 24,
      s_curve: makeSCurve(4.4),
    },
  },
  {
    title: "Indiana HAC · 이상 + 샘플 부족",
    input: {
      site_id: "Indiana-HAC",
      today_progress: 70,
      history_mean: 95,
      history_std: 4,
      sample_size: 8,
      s_curve: makeSCurve(3.5),
    },
  },
];

export default function DiagnosisPreviewPage() {
  const results = SAMPLES.map((s) => ({ ...s, diagnosis: diagnose(s.input) }));
  return (
    <div className="mx-auto max-w-screen-2xl px-6 py-10 md:px-10 md:py-14">
      <header className="border-b border-border-soft pb-6">
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          / preview — Diagnosis Components
        </span>
        <h1 className="mt-3 font-display text-h3 text-ink">진단 모델 컴포넌트 통합 시연</h1>
        <p className="mt-2 text-body-sm text-ink-mid">
          Hybrid 진단 모델 5 컴포넌트 시각 검증. (B) Report 재구성 plan 완료 시 본 라우트는 제거됩니다.
        </p>
      </header>

      {results.map((r, i) => (
        <section key={i} className="mt-10 flex flex-col gap-4">
          <div className="flex items-baseline justify-between">
            <h2 className="font-display text-h5 text-ink">{r.title}</h2>
            <ConfidenceBadge sampleSize={r.diagnosis.sample_size} />
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <GapKpiCard
              gap_pct={r.diagnosis.gap_pct}
              z_score={r.diagnosis.z_score}
              status={r.diagnosis.status}
            />
            <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
              <div className="font-display text-h6 text-ink">현재 생산성</div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="font-display text-3xl font-semibold tracking-[-0.015em] text-ink">
                  {r.diagnosis.productivity_score.toFixed(1)}
                </span>
                <span className="text-sm text-ink-light">%</span>
              </div>
              <div className="mt-3 text-[11px] text-ink-mid">
                today {r.diagnosis.today_progress}% / μ {r.diagnosis.history_mean}%
              </div>
            </div>
            <RecoveryEtaCard scenarios={r.diagnosis.scenarios} />
          </div>

          <SpiBandChart diagnosis={r.diagnosis} />
        </section>
      ))}
    </div>
  );
}
