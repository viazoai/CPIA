import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";

export function FinalCtaSection() {
  return (
    <section className="px-6 py-24 md:px-10 md:py-32">
      <div className="mx-auto max-w-wrap">
        <div className="relative overflow-hidden rounded-card-xl bg-ink px-8 py-20 text-center md:px-16 md:py-28">
          {/* Decorative halos */}
          <div className="pointer-events-none absolute -right-32 -top-32 h-96 w-96 rounded-full bg-brand/30 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-40 -left-32 h-96 w-96 rounded-full bg-brand/20 blur-3xl" />

          <div className="relative">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-[12px] font-medium text-white/90 backdrop-blur-sm">
              <Sparkles className="h-3 w-3" />
              Ready to start
            </span>

            <h2 className="mx-auto mt-6 max-w-3xl font-display text-h3 text-white md:text-h2">
              AI Agent와 함께 현장의 일을 재정의합니다.
            </h2>

            <p className="mx-auto mt-5 max-w-2xl text-body text-white/70">
              Daily 보고서 자동 생성 · 공정 리스크 D-14 선행 탐지 · 만회 시나리오
              자동 제안. 지금 바로 7-Agent 파이프라인을 둘러보세요.
            </p>

            <Link
              href="/home"
              className="group mt-10 inline-flex items-center gap-2 rounded-full bg-white px-7 py-4 text-btn text-ink transition-transform hover:scale-[1.02]"
            >
              Get Started Now
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
