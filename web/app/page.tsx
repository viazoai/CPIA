import { promises as fs } from "fs";
import path from "path";
import SiteCard, { type Site } from "./components/SiteCard";

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

  return (
    <main className="relative min-h-screen">
      {/* 상단 nav 바 — v7.1 시안 톤 */}
      <nav className="sticky top-0 z-50 flex h-16 items-center justify-between border-b border-border bg-white/80 px-10 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="relative h-8 w-8 rounded-card bg-gradient-to-br from-lavender to-mint">
            <span className="absolute left-2 top-2 h-2 w-2 rounded-sm bg-white/95" />
          </div>
          <span className="font-display text-lg font-extrabold tracking-tight text-ink">
            CPIA
            <span className="ml-1.5 text-xs font-semibold text-lavender-text">
              v7.1
            </span>
          </span>
        </div>
        <span className="rounded-full bg-peach-light px-3.5 py-1.5 font-display text-[11px] font-bold uppercase tracking-widest text-peach-text">
          Layer 1 · 경영진 뷰
        </span>
      </nav>

      {/* 헤더 영역 */}
      <header className="mx-auto max-w-wrap px-10 pb-2 pt-14">
        <p className="font-mono text-[11px] font-medium uppercase tracking-widest text-lavender-text">
          / 01 — Hi-tech 사업부 현장 현황
        </p>
        <h1 className="mt-3 max-w-3xl font-display text-4xl font-bold leading-tight tracking-tight text-ink">
          작업일보 → AI 파이프라인 → 생산성 진단
          <span className="block text-ink-mid">경영진 액션, 실시간 가시화</span>
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-ink-mid">
          6 개 현장 · 청주 M15X IBL 실 PoC 1 + Hi-tech 사업부 mock 5. 한 화면에서 진척·이상·재배치 임팩트를 확인합니다.
        </p>
      </header>

      {/* KPI 4 칸 */}
      <section className="mx-auto max-w-wrap px-10 pt-8">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Kpi
            label="전체 현장"
            value={`${summary.total}`}
            sub="실 PoC 1 + mock 5"
            tone="lavender"
          />
          <Kpi
            label="상태 분포"
            value={`${summary.risk} · ${summary.caution} · ${summary.normal}`}
            sub="위험 · 주의 · 정상"
            tone="peach"
          />
          <Kpi
            label="월간 Middle Office"
            value={`${summary.hoursNow.toLocaleString()}h`}
            sub={`→ ${summary.hoursTarget.toLocaleString()}h (목표)`}
            tone="sky"
          />
          <Kpi
            label="재배치 FTE"
            value={`${summary.fteSave.toFixed(1)} 명`}
            sub="신규 충원 없이 Front 전환"
            tone="mint"
          />
        </div>
      </section>

      {/* 카드 그리드 */}
      <section className="mx-auto max-w-wrap px-10 py-10">
        <div className="mb-5 flex items-baseline justify-between">
          <h2 className="font-display text-lg font-bold tracking-tight text-ink">
            현장별 진척 · 상태
          </h2>
          <span className="font-mono text-[11px] uppercase tracking-widest text-ink-light">
            {sites.length} sites
          </span>
        </div>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {sites.map((s) => (
            <SiteCard key={s.site_id} site={s} />
          ))}
        </div>
      </section>

      <footer className="mx-auto max-w-wrap px-10 pb-16 pt-6">
        <p className="font-mono text-[10px] uppercase tracking-widest text-ink-light/70">
          CPIA · 2026 FLP Module 2 — AI Design Project · v7.1 design tokens
        </p>
      </footer>
    </main>
  );
}

type Tone = "lavender" | "peach" | "sky" | "mint";
const TONE: Record<Tone, { dot: string; sub: string }> = {
  lavender: { dot: "bg-lavender", sub: "text-lavender-text" },
  peach: { dot: "bg-peach", sub: "text-peach-text" },
  sky: { dot: "bg-sky", sub: "text-sky-text" },
  mint: { dot: "bg-mint", sub: "text-mint-text" },
};

function Kpi({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  tone: Tone;
}) {
  const t = TONE[tone];
  return (
    <div className="rounded-card bg-surface-card p-5 shadow-xs ring-1 ring-border-soft">
      <div className="flex items-center gap-2">
        <span className={`h-1.5 w-1.5 rounded-full ${t.dot}`} />
        <p className="text-[11px] font-medium uppercase tracking-wider text-ink-light">
          {label}
        </p>
      </div>
      <p className="mt-2 font-display text-2xl font-bold leading-none tracking-tight text-ink">
        {value}
      </p>
      <p className={`mt-1.5 text-[11px] ${t.sub}`}>{sub}</p>
    </div>
  );
}
