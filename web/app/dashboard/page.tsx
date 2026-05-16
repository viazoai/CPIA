import { promises as fs } from "fs";
import path from "path";
import {
  AlertOctagon,
  Building2,
  Clock4,
  TrendingUp,
  UsersRound,
} from "lucide-react";

import { cn } from "@/lib/utils";
import SiteCard, { type Site } from "../components/SiteCard";

async function loadMockSites(): Promise<Site[]> {
  const p = path.join(process.cwd(), "..", "data", "mock_sites.json");
  const text = await fs.readFile(p, "utf-8");
  return JSON.parse(text) as Site[];
}

export default async function Page() {
  const sites = await loadMockSites();

  const summary = {
    total: sites.length,
    risk: sites.filter((s) => s.status === "risk").length,
    caution: sites.filter((s) => s.status === "caution").length,
    normal: sites.filter((s) => s.status === "normal").length,
    hoursNow: sites.reduce((a, s) => a + s.monthly_hours_now, 0),
    hoursTarget: sites.reduce((a, s) => a + s.monthly_hours_target, 0),
    fteSave: sites.reduce((a, s) => a + s.fte_save, 0),
  };
  const hoursReduce = Math.round(
    (1 - summary.hoursTarget / summary.hoursNow) * 100,
  );

  return (
    <div className="relative min-h-screen">
      {/* ── HEADER ──────────────────────────────────────────── */}
      <header className="mx-auto max-w-wrap px-6 pb-2 pt-14 md:px-10 md:pt-20">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-lavender-text">
            Performance · Site Overview
          </span>
          <Separator />
          <span className="font-mono text-[11px] uppercase tracking-widest text-ink-light">
            Hi-tech 사업부
          </span>
        </div>
        <h1 className="mt-4 max-w-3xl font-display text-4xl font-bold leading-[1.15] tracking-tight text-ink md:text-5xl">
          <span className="text-ink">작업일보 →</span>{" "}
          <span className="bg-gradient-to-r from-lavender to-mint bg-clip-text text-transparent">
            AI 파이프라인
          </span>{" "}
          <span className="text-ink">→ 생산성 진단</span>
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-ink-mid md:text-base">
          청주 M15X IBL Phase 3 실 PoC 1 + Hi-tech 사업부 mock 5. 한 화면에서 진척·이상·재배치 임팩트를 확인합니다.
        </p>
      </header>

      {/* ── KPI 4 ───────────────────────────────────────────── */}
      <section className="mx-auto max-w-wrap px-6 pt-8 md:px-10">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Kpi
            tone="lavender"
            icon={Building2}
            label="전체 현장"
            value={`${summary.total}`}
            sub="실 PoC 1 + mock 5"
          />
          <Kpi
            tone="rose"
            icon={AlertOctagon}
            label="상태 분포"
            value={`${summary.risk} / ${summary.caution} / ${summary.normal}`}
            sub="위험 · 주의 · 정상"
          />
          <Kpi
            tone="sky"
            icon={Clock4}
            label="월간 Middle Office"
            value={`${summary.hoursNow.toLocaleString()}h`}
            sub={`→ ${summary.hoursTarget.toLocaleString()}h · ${hoursReduce}% 절감`}
          />
          <Kpi
            tone="mint"
            icon={UsersRound}
            label="재배치 FTE"
            value={`${summary.fteSave.toFixed(1)}명`}
            sub="신규 충원 없이 Front 전환"
          />
        </div>
      </section>

      {/* ── 카드 그리드 ──────────────────────────────────────── */}
      <section className="mx-auto max-w-wrap px-6 py-10 md:px-10 md:py-12">
        <div className="mb-6 flex items-baseline justify-between">
          <div className="flex items-baseline gap-3">
            <h2 className="font-display text-lg font-bold tracking-tight text-ink md:text-xl">
              현장별 진척 · 상태
            </h2>
            <span className="font-mono text-[10px] uppercase tracking-widest text-ink-light">
              {sites.length} sites
            </span>
          </div>
          <div className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-ink-light">
            <TrendingUp className="h-3 w-3" />
            Plan vs Actual
          </div>
        </div>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {sites.map((s) => (
            <SiteCard key={s.site_id} site={s} />
          ))}
        </div>
      </section>

      <footer className="mx-auto max-w-wrap border-t border-border-soft px-6 pb-16 pt-6 md:px-10">
        <p className="font-mono text-[10px] uppercase tracking-widest text-ink-light/70">
          CPIA · 2026 FLP Module 2 — AI Design Project · v7.1 design system
        </p>
      </footer>
    </div>
  );
}

/* ── KPI Card ──────────────────────────────────────────── */

type Tone = "lavender" | "peach" | "sky" | "mint" | "sun" | "rose";

const TONE: Record<Tone, { stripe: string; iconBg: string; iconColor: string; sub: string }> = {
  lavender: {
    stripe: "from-lavender to-lavender",
    iconBg: "bg-lavender-light",
    iconColor: "text-lavender-text",
    sub: "text-lavender-text",
  },
  peach: {
    stripe: "from-peach to-peach",
    iconBg: "bg-peach-light",
    iconColor: "text-peach-text",
    sub: "text-peach-text",
  },
  sky: {
    stripe: "from-sky to-sky",
    iconBg: "bg-sky-light",
    iconColor: "text-sky-text",
    sub: "text-sky-text",
  },
  mint: {
    stripe: "from-mint to-mint",
    iconBg: "bg-mint-light",
    iconColor: "text-mint-text",
    sub: "text-mint-text",
  },
  sun: {
    stripe: "from-sun to-sun",
    iconBg: "bg-sun-light",
    iconColor: "text-sun-text",
    sub: "text-sun-text",
  },
  rose: {
    stripe: "from-rose to-rose",
    iconBg: "bg-rose-light",
    iconColor: "text-rose-text",
    sub: "text-rose-text",
  },
};

function Kpi({
  tone,
  icon: Icon,
  label,
  value,
  sub,
}: {
  tone: Tone;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  sub: string;
}) {
  const t = TONE[tone];
  return (
    <div className="relative overflow-hidden rounded-card border border-border-soft bg-card p-5 shadow-xs transition hover:shadow-sm">
      <span
        aria-hidden
        className={cn(
          "absolute inset-x-0 top-0 h-1 bg-gradient-to-r opacity-90",
          t.stripe,
        )}
      />
      <div className="flex items-start justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-light">
          {label}
        </p>
        <span
          className={cn(
            "grid h-8 w-8 place-items-center rounded-md",
            t.iconBg,
          )}
        >
          <Icon className={cn("h-4 w-4", t.iconColor)} />
        </span>
      </div>
      <p className="mt-3 font-display text-2xl font-bold leading-none tracking-tight text-ink md:text-3xl">
        {value}
      </p>
      <p className={cn("mt-1.5 text-[11px] font-medium", t.sub)}>{sub}</p>
    </div>
  );
}

/* ── tiny Separator (header eyebrow 용) ───────────────── */

function Separator() {
  return <span className="h-px w-8 bg-border" />;
}
