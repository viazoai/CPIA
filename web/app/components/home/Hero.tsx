import { Clock4, UsersRound, AlarmClock, CalendarClock } from "lucide-react";

interface HeroStatProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  unit?: string;
  description: string;
  // lavender = 도미넌트 강조 (Hero stat 4개 중 1개만 권장).
  // neutral = 흑백 카드, stripe 없음.
  tone: "lavender" | "neutral";
}

function HeroStat({ icon, label, value, unit, description, tone }: HeroStatProps) {
  const isAccent = tone === "lavender";
  const iconBg = isAccent ? "bg-lavender text-white" : "bg-ink text-white";

  return (
    <div className="relative overflow-hidden rounded-card border border-border-soft bg-card p-5 shadow-xs">
      {isAccent && (
        <span aria-hidden className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-lavender to-lavender-light" />
      )}
      <div className={`mb-3 inline-flex h-9 w-9 items-center justify-center rounded-md ${iconBg}`}>
        {icon}
      </div>
      <div className="font-mono text-xs uppercase tracking-wider text-ink-light">{label}</div>
      <div className="mt-1 font-display text-3xl font-bold tracking-tight text-ink">
        {value}
        {unit && <span className="ml-1 text-base font-semibold text-ink-light">{unit}</span>}
      </div>
      <div className="mt-1 text-xs text-ink-mid">{description}</div>
    </div>
  );
}

export function Hero() {
  return (
    <section className="mx-auto max-w-wrap px-6 pt-14 pb-2 md:px-10 md:pt-20">
      <div className="flex items-center gap-3">
        <span className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-lavender-text">
          / 01 — Hi-tech Division
        </span>
        <span className="h-px w-8 bg-border" />
        <span className="font-mono text-[11px] uppercase tracking-wider text-ink-light">
          System Active · 6 Sites · 2026.05
        </span>
      </div>

      <h1 className="mt-6 font-display text-4xl font-bold leading-[1.15] tracking-tight text-ink md:text-5xl">
        현장 공정 데이터 자동화 및{" "}
        <span className="bg-gradient-to-r from-lavender to-lavender-text bg-clip-text text-transparent">
          공기 리스크 선행 탐지
        </span>{" "}
        Agent
      </h1>

      <p className="mt-4 max-w-3xl text-base text-ink-mid md:text-lg">
        7개 전문 Agent + Vector RAG 기반 현장 실적 이력 판단 체계.
      </p>

      <div className="mt-10 grid grid-cols-2 gap-4 md:grid-cols-4">
        <HeroStat tone="lavender" icon={<Clock4 className="h-4 w-4" />}      label="월간 절감"     value="2,155" unit="h/월"  description="2,506h → 351h (86% 절감)" />
        <HeroStat tone="neutral"  icon={<UsersRound className="h-4 w-4" />}  label="대체 규모"     value="15.4"  unit="명"    description="2,155h ÷ 140h/명 기준" />
        <HeroStat tone="neutral"  icon={<AlarmClock className="h-4 w-4" />}  label="선행 탐지"     value="D-14"               description="공기 리스크 선행 탐지 목표" />
        <HeroStat tone="neutral"  icon={<CalendarClock className="h-4 w-4" />} label="공기 단축"   value="3~7"   unit="일"    description="현장 1개당 공기 단축 추정" />
      </div>
    </section>
  );
}
