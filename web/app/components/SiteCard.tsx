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

const STATUS_STYLE: Record<Status, { label: string; chip: string; bar: string; ring: string }> = {
  normal: {
    label: "정상",
    chip: "bg-mint-light text-mint-text ring-1 ring-mint/20",
    bar: "bg-mint",
    ring: "ring-mint/30",
  },
  caution: {
    label: "주의",
    chip: "bg-sun-light text-sun-text ring-1 ring-sun/20",
    bar: "bg-sun",
    ring: "ring-sun/30",
  },
  risk: {
    label: "위험",
    chip: "bg-rose-light text-rose-text ring-1 ring-rose/20",
    bar: "bg-rose",
    ring: "ring-rose/30",
  },
  unknown: {
    label: "—",
    chip: "bg-surface-soft text-ink-light ring-1 ring-border",
    bar: "bg-ink-light",
    ring: "ring-border",
  },
};

function formatLastRun(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("ko-KR", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function SiteCard({ site }: { site: Site }) {
  const s = STATUS_STYLE[site.status];
  const gap = site.actual_progress - site.plan_progress;
  const gapText = gap >= 0 ? `+${gap.toFixed(1)}` : gap.toFixed(1);
  const gapTone = gap < 0 ? "text-rose-text" : "text-mint-text";

  return (
    <article
      className={`group relative rounded-card bg-surface-card p-6 shadow-xs ring-1 ring-border-soft transition hover:shadow-md hover:-translate-y-0.5 hover:ring-border`}
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight text-ink">
            {site.name}
          </h2>
          <p className="mt-0.5 text-xs text-ink-light">{site.owner}</p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <span
            className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${s.chip}`}
          >
            {s.label}
          </span>
          {site.is_mock ? (
            <span className="font-mono text-[10px] uppercase tracking-wider text-ink-light/70">
              mock
            </span>
          ) : (
            <span className="rounded-full bg-lavender-light px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-lavender-text">
              실 PoC
            </span>
          )}
        </div>
      </header>

      <div className="mt-5">
        <div className="flex items-baseline justify-between text-[11px] font-medium uppercase tracking-wider text-ink-light">
          <span>Plan {site.plan_progress.toFixed(1)}%</span>
          <span>Actual {site.actual_progress.toFixed(1)}%</span>
        </div>
        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-surface-soft">
          <div
            className={`h-full ${s.bar} transition-all`}
            style={{ width: `${Math.min(site.actual_progress, 100)}%` }}
          />
        </div>
        <p className="mt-1.5 text-[11px] text-ink-light">
          Gap{" "}
          <span className={`font-mono font-semibold ${gapTone}`}>
            {gapText}%p
          </span>
        </p>
      </div>

      <dl className="mt-5 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <div>
          <dt className="text-ink-light">월간 Middle Office</dt>
          <dd className="mt-0.5 font-mono font-semibold text-ink">
            {site.monthly_hours_now}h
            <span className="ml-1 text-ink-light/80">
              → {site.monthly_hours_target}h
            </span>
          </dd>
        </div>
        <div>
          <dt className="text-ink-light">재배치 FTE</dt>
          <dd className="mt-0.5 font-mono font-semibold text-ink">
            {site.fte_save.toFixed(1)} 명
          </dd>
        </div>
      </dl>

      <p className="mt-4 line-clamp-2 rounded-card bg-surface-soft px-3 py-2 text-[11px] leading-relaxed text-ink-mid">
        {site.pain_top}
      </p>

      <footer className="mt-4 flex items-center justify-between border-t border-border-soft pt-3 text-[10px] text-ink-light">
        <span>마지막 실행 {formatLastRun(site.last_run_at)}</span>
        <span className="font-mono uppercase tracking-wider text-ink-light/70">
          {site.site_id}
        </span>
      </footer>
    </article>
  );
}
