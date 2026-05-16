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
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-7xl px-6 py-6">
          <p className="text-xs font-medium uppercase tracking-wider text-indigo-600">CPIA · Layer 1</p>
          <h1 className="mt-1 text-2xl font-semibold text-slate-900">Hi-tech 사업부 현장 현황</h1>
          <p className="mt-1 text-sm text-slate-500">
            6 개 현장 · 작업일보 → AI 파이프라인 → 생산성 진단 · 경영진 액션
          </p>
        </div>
      </header>

      <section className="border-b border-slate-200 bg-white">
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-4 px-6 py-5 md:grid-cols-4">
          <Kpi label="전체 현장" value={`${summary.total}`} sub="실 PoC 1 + mock 5" />
          <Kpi
            label="상태 분포"
            value={`${summary.risk} / ${summary.caution} / ${summary.normal}`}
            sub="위험 / 주의 / 정상"
          />
          <Kpi
            label="월간 Middle Office"
            value={`${summary.hoursNow.toLocaleString()}h`}
            sub={`→ ${summary.hoursTarget.toLocaleString()}h (목표)`}
          />
          <Kpi
            label="재배치 FTE"
            value={`${summary.fteSave.toFixed(1)} 명`}
            sub="신규 충원 없이 Front 전환"
          />
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-6 py-8">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {sites.map((s) => (
            <SiteCard key={s.site_id} site={s} />
          ))}
        </div>
      </section>
    </main>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-slate-900">{value}</p>
      <p className="mt-0.5 text-[11px] text-slate-400">{sub}</p>
    </div>
  );
}
