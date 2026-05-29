import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";

export function FinalCtaSection() {
  return (
    <section className="px-6 py-24 md:px-10 md:py-32">
      <div className="mx-auto w-full max-w-wrap">
        <div className="relative overflow-hidden rounded-card-xl bg-gradient-to-br from-brand-text via-brand to-sky-text px-8 py-20 text-center md:px-16 md:py-28">
          {/* Decorative halos */}
          <div className="pointer-events-none absolute -right-32 -top-32 h-96 w-96 rounded-full bg-white/20 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-40 -left-32 h-96 w-96 rounded-full bg-sky/30 blur-3xl" />

          <div className="relative">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-[12px] font-medium text-white/95 backdrop-blur-sm ring-1 ring-white/20">
              <Sparkles className="h-3 w-3" />
              Operational Shift
            </span>

            <h2 className="mx-auto mt-6 max-w-3xl font-display text-h3 text-white md:text-h2">
              단순 AI 도구 적용이 아닌,
              <br className="hidden md:block" />
              <span className="text-white"> 현장 운영 구조의 전환</span>입니다.
            </h2>

            <p className="mx-auto mt-6 max-w-2xl text-body text-white/80">
              사람 손을 떠나 작업일보 취합 · 진도 보고 · 만회 계획 수립을 이제는
              7개의 Agent 가 수행함으로써, 현장을 최적화 해나가고 운영 구조를 변화시키는 첫걸음이 될 것입니다.
            </p>

            <Link
              href="/home"
              className="group mt-10 inline-flex items-center gap-2 rounded-full bg-white px-7 py-4 text-btn text-brand-text shadow-lg shadow-brand-text/20 transition-transform hover:scale-[1.02]"
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
