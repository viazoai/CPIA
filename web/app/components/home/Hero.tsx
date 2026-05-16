import Link from "next/link";
import { Clock4, UsersRound, AlarmClock, CalendarClock, Play, ArrowRight, Sparkles } from "lucide-react";

interface HeroStatProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  unit?: string;
  description: string;
  tone: "violet" | "mint" | "sky" | "amber";
}

const TONE_DOT: Record<HeroStatProps["tone"], string> = {
  violet: "bg-[#a78bfa]",
  mint:   "bg-emerald-400",
  sky:    "bg-sky-400",
  amber:  "bg-amber-400",
};

const TONE_GLOW: Record<HeroStatProps["tone"], string> = {
  violet: "shadow-[0_0_40px_-12px_rgba(167,139,250,0.5)]",
  mint:   "shadow-[0_0_40px_-12px_rgba(52,211,153,0.4)]",
  sky:    "shadow-[0_0_40px_-12px_rgba(56,189,248,0.4)]",
  amber:  "shadow-[0_0_40px_-12px_rgba(251,191,36,0.4)]",
};

function HeroStat({ icon, label, value, unit, description, tone }: HeroStatProps) {
  return (
    <div
      className={`group relative rounded-xl border border-white/10 bg-white/[0.04] backdrop-blur-md p-5 transition-all hover:bg-white/[0.07] hover:border-white/20 ${TONE_GLOW[tone]}`}
    >
      <div className="flex items-center gap-2.5">
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-white/5 text-white/80">
          {icon}
        </span>
        <span className={`h-1.5 w-1.5 rounded-full ${TONE_DOT[tone]} animate-pulse`} />
      </div>
      <div className="mt-4 font-mono text-[11px] uppercase tracking-wider text-white/40">{label}</div>
      <div className="mt-1 font-display text-3xl font-bold tracking-tight text-white md:text-4xl">
        {value}
        {unit && <span className="ml-1 text-base font-medium text-white/50">{unit}</span>}
      </div>
      <div className="mt-1.5 text-xs text-white/50 leading-relaxed">{description}</div>
    </div>
  );
}

export function Hero() {
  return (
    <section className="relative isolate overflow-hidden">
      {/* Violet bloom — center */}
      <div
        aria-hidden
        className="absolute left-1/2 -translate-x-1/2 top-[30%] h-[700px] w-[900px] pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(124,92,255,0.45) 0%, rgba(124,92,255,0.18) 30%, transparent 65%)",
          filter: "blur(24px)",
        }}
      />

      {/* Secondary mint bloom — bottom right */}
      <div
        aria-hidden
        className="absolute right-[10%] bottom-[10%] h-[400px] w-[400px] pointer-events-none"
        style={{
          background: "radial-gradient(circle, rgba(52,211,153,0.18) 0%, transparent 60%)",
          filter: "blur(40px)",
        }}
      />

      {/* Dot grid pattern with radial mask */}
      <div
        aria-hidden
        className="absolute inset-0 opacity-60 pointer-events-none"
        style={{
          backgroundImage:
            "radial-gradient(circle, rgba(255,255,255,0.08) 1.2px, transparent 1.2px)",
          backgroundSize: "28px 28px",
          maskImage: "radial-gradient(ellipse at 50% 40%, black 25%, transparent 75%)",
          WebkitMaskImage: "radial-gradient(ellipse at 50% 40%, black 25%, transparent 75%)",
        }}
      />

      {/* Content */}
      <div className="relative mx-auto max-w-wrap px-6 pt-16 pb-12 md:px-10 md:pt-24 md:pb-20 text-center">
        {/* Announcement pill */}
        <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-3 py-1.5 backdrop-blur-md">
          <span className="inline-flex items-center gap-1 rounded-full bg-[#7c5cff]/20 px-2 py-0.5">
            <Sparkles className="h-3 w-3 text-[#a78bfa]" strokeWidth={2.5} />
            <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-[#c4b5fd]">
              v0.1 Live
            </span>
          </span>
          <span className="text-xs text-white/70">
            7개 AI Agent · Vector RAG · 2026.05 PoC
          </span>
        </div>

        {/* Headline */}
        <h1 className="mt-8 font-display text-5xl font-extrabold leading-[1.05] tracking-tight text-white md:text-7xl">
          현장 데이터 자동화로
          <br />
          <span className="bg-gradient-to-r from-[#c4b5fd] via-[#a78bfa] to-[#34d399] bg-clip-text text-transparent">
            공기 리스크를 미리
          </span>{" "}
          탐지합니다.
        </h1>

        <p className="mx-auto mt-6 max-w-2xl text-base text-white/65 md:text-lg">
          7개 전문 Agent + Vector RAG 기반 현장 실적 이력 판단 체계.
          <br className="hidden md:block" />
          Hi-tech 6 현장 자동 분석 · 2026.05 PoC.
        </p>

        {/* CTAs */}
        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            className="group inline-flex items-center gap-2 rounded-md border border-white/15 bg-white/[0.05] px-5 py-3 text-sm font-semibold text-white backdrop-blur-md transition-all hover:bg-white/[0.10] hover:border-white/25"
          >
            <Play className="h-3.5 w-3.5 fill-white" strokeWidth={2.5} />
            Demo 영상
          </button>
          <Link
            href="/tasks"
            className="group inline-flex items-center gap-2 rounded-md bg-[#7c5cff] px-5 py-3 text-sm font-semibold text-white shadow-[0_0_30px_-5px_rgba(124,92,255,0.7)] transition-all hover:bg-[#6d4ee5] hover:shadow-[0_0_45px_-5px_rgba(124,92,255,0.9)]"
          >
            Agent Tasks 살펴보기
            <ArrowRight
              className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
              strokeWidth={2.5}
            />
          </Link>
        </div>

        {/* Stat cards */}
        <div className="mt-16 grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
          <HeroStat tone="violet" icon={<Clock4 className="h-4 w-4" />}        label="월간 절감"  value="2,155" unit="h/월" description="2,506h → 351h (86% 절감)" />
          <HeroStat tone="mint"   icon={<UsersRound className="h-4 w-4" />}    label="대체 규모"  value="15.4"  unit="명"   description="2,155h ÷ 140h/명 기준" />
          <HeroStat tone="sky"    icon={<AlarmClock className="h-4 w-4" />}    label="선행 탐지"  value="D-14"              description="공기 리스크 선행 탐지" />
          <HeroStat tone="amber"  icon={<CalendarClock className="h-4 w-4" />} label="공기 단축"  value="3~7"   unit="일"   description="현장 1개당 단축 추정" />
        </div>
      </div>
    </section>
  );
}
