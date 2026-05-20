import { ArrowRight, Sparkles } from "lucide-react";

/* AS-IS · TO-BE 는 인덱스 기준 1:1 로 매핑되도록 순서를 맞춘다.
 * 각 행은 (BP 수신 → Collector), (엑셀 집계 → Parser), (공정표 매핑 → Mapper),
 * (현장 이력 비축적 → Atomizer), (PPT 보고 → Exporter),
 * (PM 경험칙 판단 → Forecaster), (만회 대책 임시 수립 → Optimizer) 의 대응. */
const AS_IS = [
  "BP 이메일·카톡 수동 열람 (1~2h/일)",
  "엑셀 복붙·집계 수작업 (2~3h/일)",
  "공정표 항목 수작업 매핑 (1h/일)",
  "현장 이력 축적 없이 매번 재취합 (1h/일)",
  "PPT·엑셀 보고서 수기 작성 (2h/일)",
  "PM 경험칙으로 공정 이상 판단 (D+2~3일 사후 인지)",
  "공기 만회 대책 사후 임시 수립 (만회 불가 구간 진입 후)",
];

const TO_BE: { agent: string; step: string; ai?: boolean }[] = [
  { agent: "Collector",  step: "이메일·카톡 자동 수집·파싱 (0분)" },
  { agent: "Parser",     step: "비정형 작업일보 → WBS 구조화 (0분)" },
  { agent: "Mapper",     step: "공정표 의미 기반 자동 매핑 (검증 10분)", ai: true },
  { agent: "Atomizer",   step: "작업 기록 현장 지식 DB 적재 (0분)" },
  { agent: "Exporter",   step: "통합 작업일보 자동 생성·출력 (검토 10분)" },
  { agent: "Forecaster", step: "생산성 현장 이력 대비 진단", ai: true },
  { agent: "Optimizer",  step: "atch-up 시나리오 자동 생성", ai: true },
];

export function AsIsToBeSection() {
  return (
    <section
      id="process"
      className="border-t border-border-soft bg-card py-24 md:py-32"
    >
      <div className="mx-auto max-w-wrap px-6 md:px-10">
        <div className="max-w-3xl">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
            / 02 — Process
          </span>
          <h2 className="mt-3 font-display text-h3 text-ink">
            수작업 7단계 → 7-Agent 자동화
          </h2>
          <p className="mt-6 text-body text-ink-mid">
            담당자 1~3명이 전일 매달리던 취합·보고·분석 사이클을 7개 Agent의 업무로 대체하고,
            <br />
            담당자의 역할이{" "}
            <span className="font-semibold text-ink">보고서 작성자</span> 에서{" "}
            <span className="font-semibold text-ink">의사결정자</span> 로 전환됩니다.
          </p>
        </div>

        <div className="mt-14 grid gap-6 md:grid-cols-[1fr_auto_1fr]">
          {/* AS-IS */}
          <div className="rounded-card-lg border border-border bg-surface-soft/40 p-8">
            <div className="flex items-center gap-2">
              <span className="inline-flex h-7 items-center rounded-full bg-ink-mid px-3 text-[11px] font-semibold uppercase tracking-wider text-white">
                AS-IS
              </span>
            </div>
            <h3 className="mt-3 font-display text-h5 text-ink-mid">
              수작업 7단계
            </h3>
            <ol className="mt-6 flex flex-col gap-3">
              {AS_IS.map((step, i) => (
                <li key={i} className="flex gap-3 text-body-sm text-ink-mid">
                  <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-border bg-white font-mono text-[10px] text-ink-light">
                    {i + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
            <div className="mt-6 rounded-md bg-rose-light px-4 py-3 text-center text-body-sm font-medium text-rose-text">
              담당자 1~3명 전일 투입 · 보고 D+2~3일 · 지연 사후 인지
            </div>
          </div>

          {/* Arrow */}
          <div className="flex items-center justify-center md:px-2">
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-brand text-white shadow-md md:h-12 md:w-12">
              <ArrowRight className="h-5 w-5" />
            </span>
          </div>

          {/* TO-BE */}
          <div className="rounded-card-lg border border-brand/30 bg-brand-light/60 p-8 shadow-sm">
            <div className="flex items-center gap-2">
              <span className="inline-flex h-7 items-center rounded-full bg-brand px-3 text-[11px] font-semibold uppercase tracking-wider text-white">
                TO-BE
              </span>
            </div>
            <h3 className="mt-3 font-display text-h5 text-ink">
              7-Agent 자동화 (LangGraph 기반)
            </h3>
            <ol className="mt-6 flex flex-col gap-3">
              {TO_BE.map((it, i) => (
                <li key={i} className="flex items-start gap-3 text-body-sm text-ink">
                  <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand font-mono text-[10px] font-semibold text-white">
                    {i + 1}
                  </span>
                  <span className="flex-1">
                    <span className="font-semibold text-brand-text">{it.agent}</span>
                    <span className="text-ink-light"> · </span>
                    {it.step}
                  </span>
                  {it.ai && (
                    <span
                      title="Core AI — 핵심 판단"
                      className="mt-0.5 inline-flex h-5 shrink-0 items-center gap-1 rounded-full bg-sky px-2 font-mono text-[10px] font-semibold uppercase tracking-wider text-white shadow-sm"
                    >
                      <Sparkles className="h-3 w-3" />
                      CORE AI
                    </span>
                  )}
                </li>
              ))}
            </ol>
            <div className="mt-6 rounded-md bg-mint-light px-4 py-3 text-center text-body-sm font-medium text-mint-text">
              담당자 30분/일 투입 · 보고 D+0 (당일) · 공기 위험 D-14 선제 대응
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
