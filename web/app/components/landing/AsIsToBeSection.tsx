import { ArrowRight } from "lucide-react";

const AS_IS = [
  "BP 이메일·카톡 수동 열람 (1~2h/일)",
  "엑셀 복붙·집계 수작업 (2~3h/일)",
  "이상치 발견 시 업체 유선 확인 (1h/일)",
  "공정표 항목 수작업 매핑",
  "PPT·엑셀 보고서 수기 작성 (2h/일)",
  "발주처 이메일 수동 발송 (D+2~3일)",
  "PM 경험칙으로 공정 이상 판단",
];

const TO_BE = [
  "이메일·카톡 자동 수집·파싱 (0분)",
  "비정형 일보 → WBS 구조화 JSON (0분)",
  "공정표 의미 기반 자동 매핑 (검증 10분)",
  "작업 기록 현장 지식 DB 적재 (0분)",
  "통합 보고서 자동 생성·발송 (검토 10분)",
  "오늘 생산성 현장 이력 대비 진단",
  "AI 권장 catch-up 시나리오 자동 생성",
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
            AS-IS 수작업 7단계 → TO-BE 7-Agent 자동화
          </h2>
          <p className="mt-6 text-body text-ink-mid">
            담당자 1~3명이 전일 매달리던 보고 사이클을 7개 Agent + 2개 H-i-L
            검증 포인트로 분해. 담당자의 역할이{" "}
            <span className="font-semibold text-ink">보고서 작성자</span> 에서{" "}
            <span className="font-semibold text-ink">의사결정자</span> 로 전환됩니다.
          </p>
        </div>

        <div className="mt-14 grid gap-6 md:grid-cols-[1fr_auto_1fr]">
          {/* AS-IS */}
          <div className="rounded-card-lg border border-border bg-surface-soft p-8">
            <div className="flex items-center gap-2">
              <span className="inline-flex h-7 items-center rounded-full bg-ink/10 px-3 text-[11px] font-medium uppercase tracking-wider text-ink-mid">
                AS-IS
              </span>
              <span className="text-body-sm text-ink-light">
                담당자 1~3명 · D+2~3일
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
          </div>

          {/* Arrow */}
          <div className="flex items-center justify-center md:px-2">
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-brand text-white shadow-md md:h-12 md:w-12">
              <ArrowRight className="h-5 w-5" />
            </span>
          </div>

          {/* TO-BE */}
          <div className="rounded-card-lg border border-brand/30 bg-gradient-to-br from-brand-light/60 via-card to-card p-8 shadow-sm">
            <div className="flex items-center gap-2">
              <span className="inline-flex h-7 items-center rounded-full bg-brand px-3 text-[11px] font-semibold uppercase tracking-wider text-white">
                TO-BE
              </span>
              <span className="text-body-sm text-brand-text">
                7 Agent · D+0 당일
              </span>
            </div>
            <h3 className="mt-3 font-display text-h5 text-ink">
              7-Agent 자동화
            </h3>
            <ol className="mt-6 flex flex-col gap-3">
              {TO_BE.map((step, i) => (
                <li key={i} className="flex gap-3 text-body-sm text-ink">
                  <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand font-mono text-[10px] font-semibold text-white">
                    {i + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    </section>
  );
}
