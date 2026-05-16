type Status = "normal" | "caution" | "risk" | "unknown";

export type Site = {
  site_id: string;
  name: string;
  owner: string;
  plan_progress: number;
  actual_progress: number;
  status: Status;
  is_mock: boolean;
  monthly_hours_now: number;
  monthly_hours_target: number;
  fte_save: number;
  pain_top: string;
  last_run_at: string;
};

const STATUS_STYLE: Record<Status, { label: string; chip: string; bar: string }> = {
  normal:  { label: "정상",   chip: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200", bar: "bg-emerald-500" },
  caution: { label: "주의",   chip: "bg-amber-50 text-amber-800 ring-1 ring-amber-200",       bar: "bg-amber-500" },
  risk:    { label: "위험",   chip: "bg-rose-50 text-rose-700 ring-1 ring-rose-200",          bar: "bg-rose-500" },
  unknown: { label: "—",      chip: "bg-slate-100 text-slate-600 ring-1 ring-slate-200",     bar: "bg-slate-400" },
};

function formatLastRun(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

export default function SiteCard({ site }: { site: Site }) {
  const s = STATUS_STYLE[site.status];
  const gap = site.actual_progress - site.plan_progress;
  const gapText = gap >= 0 ? `+${gap.toFixed(1)}` : gap.toFixed(1);

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:shadow-md">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900">{site.name}</h2>
          <p className="mt-0.5 text-xs text-slate-500">{site.owner}</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${s.chip}`}>
            {s.label}
          </span>
          {site.is_mock ? (
            <span className="text-[10px] text-slate-400">mock</span>
          ) : (
            <span className="text-[10px] font-medium text-indigo-600">실 PoC</span>
          )}
        </div>
      </header>

      <div className="mt-4">
        <div className="flex items-baseline justify-between text-xs text-slate-600">
          <span>Plan {site.plan_progress.toFixed(1)}%</span>
          <span>Actual {site.actual_progress.toFixed(1)}%</span>
        </div>
        <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-slate-100">
          <div className={`h-full ${s.bar}`} style={{ width: `${Math.min(site.actual_progress, 100)}%` }} />
        </div>
        <p className="mt-1 text-[11px] text-slate-500">
          Gap <span className={gap < 0 ? "text-rose-600 font-medium" : "text-emerald-600 font-medium"}>{gapText}%p</span>
        </p>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
        <div>
          <dt className="text-slate-500">월간 Middle Office</dt>
          <dd className="mt-0.5 font-medium text-slate-900">
            {site.monthly_hours_now}h
            <span className="ml-1 text-slate-400">→ {site.monthly_hours_target}h</span>
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">재배치 FTE</dt>
          <dd className="mt-0.5 font-medium text-slate-900">{site.fte_save.toFixed(1)} 명</dd>
        </div>
      </dl>

      <p className="mt-3 line-clamp-2 text-[11px] text-slate-500">
        {site.pain_top}
      </p>

      <footer className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3 text-[11px] text-slate-400">
        <span>마지막 실행 {formatLastRun(site.last_run_at)}</span>
        <span className="font-mono text-slate-300">{site.site_id}</span>
      </footer>
    </article>
  );
}
