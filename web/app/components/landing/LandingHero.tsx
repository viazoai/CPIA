"use client";
import Link from "next/link";
import { Sparkles, ArrowRight, TrendingUp, Clock4 } from "lucide-react";

export function LandingHero() {
  return (
    <section className="relative mx-auto max-w-wrap px-6 pb-24 pt-20 md:px-10 md:pb-32 md:pt-28">
      <div className="grid items-center gap-12 md:grid-cols-2 md:gap-16">
        {/* LEFT — copy */}
        <div className="relative z-10">
          {/* Badge */}
          <span className="inline-flex items-center gap-1.5 rounded-full bg-lavender-light px-3 py-1 text-[12px] font-medium text-lavender-text">
            <Sparkles className="h-3 w-3" />
            Welcome to CPIA
          </span>

          <h1 className="mt-6 font-display text-h2 text-ink md:text-h1">
            현장 보고 업무를 줄이는 게 아니라,{" "}
            <span className="text-lavender">현장의 일을 재정의합니다.</span>
          </h1>

          <p className="mt-6 max-w-xl text-body text-ink-mid">
            7개 전문 AI Agent + Vector RAG 기반 현장 실적 이력 판단 체계.
            Middle Office 보고 업무를 자동화하고, 담당자가 Front Office 본연의
            공정 판단·리스크 실행에 집중하도록 합니다.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link
              href="/home"
              className="group inline-flex items-center gap-2 rounded-full bg-ink px-6 py-3.5 text-btn text-white transition-colors hover:bg-ink-mid"
            >
              Get Started Now
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Link>
            <a
              href="#impact"
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-white px-5 py-3.5 text-body-sm font-medium text-ink-mid transition-colors hover:border-lavender hover:text-ink"
            >
              임팩트 보기
            </a>
          </div>

          {/* Trust strip */}
          <div className="mt-10 flex flex-wrap items-center gap-6 text-[12px] text-ink-light">
            <span className="font-mono uppercase tracking-wider">
              Hi-tech 6 sites · 321 activities · 월 8,133h
            </span>
          </div>
        </div>

        {/* RIGHT — floating mockup stack */}
        <div className="relative hidden md:block">
          {/* Soft halo */}
          <div className="absolute -inset-8 rounded-card-xl bg-gradient-to-tr from-lavender-light via-white to-lavender-light/40 blur-2xl" />

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
                  className="flex-1 rounded-sm bg-gradient-to-t from-lavender-light to-lavender"
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
    </section>
  );
}
