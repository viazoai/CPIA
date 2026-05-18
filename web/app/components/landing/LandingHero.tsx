"use client";
import Link from "next/link";
import { Sparkles, ArrowRight, TrendingUp, Clock4 } from "lucide-react";

export function LandingHero() {
  return (
    <section className="relative flex min-h-[calc(100vh-4rem)] items-center overflow-hidden">
      {/* ── 시작페이지 그라데이션 backdrop — 흰색 → 하늘색 (상단 white, 하단 sky) ── */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b from-white via-white to-sky-light"
      />
      {/* 큰 sky halo — 상단 중앙에서 옅게 확산 */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 left-1/2 -z-10 h-[640px] w-[1100px] -translate-x-1/2 rounded-full bg-sky/25 blur-3xl"
      />
      {/* 우측 상단 보조 톤 — brand-light 살짝 */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-24 -right-24 -z-10 h-[460px] w-[460px] rounded-full bg-brand/15 blur-3xl"
      />
      {/* 좌측 하단 보조 톤 — sky-light 마무리 (다음 섹션 경계 흐리기) */}
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-40 -left-20 -z-10 h-[480px] w-[480px] rounded-full bg-sky-light/80 blur-3xl"
      />

      <div className="mx-auto max-w-wrap px-6 pb-40 pt-28 md:px-10 md:pb-56 md:pt-36">
        <div className="grid items-center gap-12 md:grid-cols-2 md:gap-16">
        {/* LEFT — copy */}
        <div className="relative z-10">
          {/* Badge */}
          <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-light px-3 py-1 text-[12px] font-medium text-brand-text">
            <Sparkles className="h-3 w-3" />
            Welcome to CPIA
          </span>

          <h1 className="mt-6 font-display text-h2 text-ink md:text-h2">
            현장 운영 구조 전환을 위한,{" "}
            <span className="text-brand">생산성 최적화 AI Agent</span>
          </h1>

          <p className="mt-6 max-w-xl text-body text-ink-mid">
            Middle Office의 작업일보 집계·검증·보고 업무를 자동화하고, 현장관리자의 공정 분석·리스크 예측을
            지원하여 현장의 공사기간 단축을 기여합니다.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link
              href="/home"
              className="group inline-flex items-center gap-2 rounded-full bg-ink px-6 py-3.5 text-btn text-white transition-colors hover:bg-ink-mid"
            >
              Get Started Now
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Link>
          </div>

          {/* Trust strip */}
        </div>

        {/* RIGHT — floating mockup stack */}
        <div className="relative hidden md:block">
          {/* Soft halo */}
          <div className="absolute -inset-8 rounded-card-xl bg-gradient-to-tr from-brand-light via-white to-brand-light/40 blur-2xl" />

          {/* Main KPI mockup */}
          <div className="relative rotate-1 rounded-card-lg border border-border bg-card p-6 shadow-lg">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-light">
                Monthly Saving
              </span>
              <span className="inline-flex items-center gap-1 rounded-full bg-mint-light px-2 py-0.5 text-[11px] font-medium text-mint-text">
                <TrendingUp className="h-3 w-3" />
                +86%
              </span>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="font-display text-h2 text-ink">2,155</span>
              <span className="text-body text-ink-light">h / 월</span>
            </div>
            <p className="mt-2 text-body-sm text-ink-mid">
              2,506h 수작업 → 351h AI 자동화
            </p>

            {/* Mini bar visual */}
            <div className="mt-5 flex items-end gap-1.5">
              {[40, 55, 48, 70, 62, 88, 76, 95, 82, 100, 92, 98].map((h, i) => (
                <span
                  key={i}
                  className="flex-1 rounded-sm bg-gradient-to-t from-brand-light to-brand"
                  style={{ height: `${h * 0.6}px` }}
                />
              ))}
            </div>
          </div>

          {/* Floating sub-card */}
          <div className="absolute -bottom-6 -left-8 w-56 -rotate-2 rounded-card border border-border bg-card p-4 shadow-md">
            <div className="flex items-center gap-2">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-sun-light text-sun-text">
                <Clock4 className="h-4 w-4" />
              </span>
              <div>
                <div className="text-[11px] font-medium uppercase tracking-wider text-ink-light">
                  공기 단축
                </div>
                <div className="font-display text-lg font-semibold text-ink">
                  3 ~ 7 일/현장
                </div>
              </div>
            </div>
          </div>

          {/* Top-right sub-card */}
          <div className="absolute -top-6 -right-6 w-48 rotate-3 rounded-card border border-border bg-card p-4 shadow-md">
            <div className="text-[11px] font-medium uppercase tracking-wider text-ink-light">
              FTE 대체
            </div>
            <div className="mt-1 font-display text-2xl font-semibold text-ink">
              15.4명
            </div>
            <div className="mt-1 text-[11px] text-ink-mid">2,155h ÷ 140h/명</div>
          </div>
        </div>
        </div>
      </div>
    </section>
  );
}
