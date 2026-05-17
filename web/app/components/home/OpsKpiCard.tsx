import { cn } from "@/lib/utils";

type Tone = "lavender" | "mint" | "sun" | "sky";

export interface OpsKpiCardProps {
  tone: Tone;
  icon: React.ReactNode;
  label: string;
  value: string;
  unit?: string;
  description?: string;
  live?: boolean;
}

const CHIP: Record<Tone, string> = {
  lavender: "bg-lavender-light text-lavender-text",
  mint:     "bg-mint-light text-mint-text",
  sun:      "bg-sun-light text-sun-text",
  sky:      "bg-sky-light text-sky-text",
};

/**
 * 운영 현황 KPI 카드 — Hero.tsx 의 HeroStat 디자인 패턴 차용.
 *  - rounded-card-lg + shadow-sm hover:shadow-md
 *  - 톤별 아이콘 칩 + mono uppercase 라벨 + font-display 값 + 설명
 *  - live=true 시 라벨 옆 LIVE pulse dot
 */
export function OpsKpiCard({
  tone,
  icon,
  label,
  value,
  unit,
  description,
  live,
}: OpsKpiCardProps) {
  return (
    <div className="group rounded-card border border-border-soft bg-card p-4 shadow-xs transition-shadow hover:shadow-sm">
      <div className={cn("mb-3 inline-flex h-10 w-10 items-center justify-center rounded-lg", CHIP[tone])}>
        {icon}
      </div>

      <div className="flex items-center gap-2">
        <span className="font-display text-h6 text-ink">{label}</span>
        {live && (
          <span className="inline-flex items-center gap-1 rounded-full bg-mint-light px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-mint-text">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-mint" />
            LIVE
          </span>
        )}
      </div>

      <div className="mt-1 font-display text-3xl font-medium tracking-[-0.02em] text-ink">
        {value}
        {unit && <span className="ml-1 text-base font-medium text-ink-light">{unit}</span>}
      </div>

      {description && (
        <div className="mt-1 text-xs text-ink-mid">{description}</div>
      )}
    </div>
  );
}
