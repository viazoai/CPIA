import { Clock4, UsersRound, CalendarClock, Gauge } from "lucide-react";

const KPIS = [
  {
    icon: Clock4,
    label: "월간 절감",
    value: "2,155",
    unit: "h / 월",
    body: "2,506h → 351h · 대체율 86%",
  },
  {
    icon: UsersRound,
    label: "FTE 대체",
    value: "15.4",
    unit: "명",
    body: "2,155h ÷ 140h/명 기준",
  },
  {
    icon: Gauge,
    label: "보고 리드타임",
    value: "D+0",
    unit: "당일",
    body: "D+2~3일 → 동일한 날 보고",
  },
  {
    icon: CalendarClock,
    label: "공기 단축",
    value: "3~7",
    unit: "일 / 현장",
    body: "보고 가속 + D-14 탐지 + 만회 조기 착수",
  },
];

const PATHS = [
  {
    no: "01",
    title: "보고 사이클 D+2~3일 → D+0",
    body: "보고 가속만으로 현장 1개당 공기 단축 3~5일 직접 기여",
  },
  {
    no: "02",
    title: "D-14 선행 탐지",
    body: "지연의 50~70% 가 2주 전 탐지 시 예방 가능",
  },
  {
    no: "03",
    title: "자재 수급 선제 대응",
    body: "월 15~30일분 현장 손실 제거 (자재 부족 대기 월 5~10건 × 3일)",
  },
  {
    no: "04",
    title: "보고 해방 인력 → 공정 최적화",
    body: "보고 업무 해방 인력 재배치로 공정 품질 5~10% 간접 개선",
  },
];

export function ImpactSection() {
  return (
    <section
      id="impact"
      className="border-t border-border-soft bg-surface-soft/50 py-24 md:py-32"
    >
      <div className="mx-auto max-w-wrap px-6 md:px-10">
        <div className="max-w-3xl">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
            / 03 — Impact
          </span>
          <h2 className="mt-3 font-display text-h3 text-ink">
            Hi-tech 6 현장 321 Activity 전수 분석 기반 정량 효과
          </h2>
          <p className="mt-6 text-body text-ink-mid">
            Activity 321개 · 월 8,133h 데이터로 산출. 시연용 추정이 아닌 실측
            기반 수치입니다.
          </p>
        </div>

        {/* KPI grid */}
        <div className="mt-14 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {KPIS.map((k) => {
            const Icon = k.icon;
            return (
              <div
                key={k.label}
                className="group relative overflow-hidden rounded-card-lg border border-border bg-card p-7 transition-shadow hover:shadow-md"
              >
                <span className="absolute right-5 top-5 inline-flex h-10 w-10 items-center justify-center rounded-md bg-brand-light text-brand-text">
                  <Icon className="h-5 w-5" />
                </span>
                <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-light">
                  {k.label}
                </div>
                <div className="mt-4 flex items-baseline gap-1.5">
                  <span className="font-display text-h2 leading-none text-ink">
                    {k.value}
                  </span>
                  <span className="text-body text-ink-light">{k.unit}</span>
                </div>
                <p className="mt-3 text-body-sm text-ink-mid">{k.body}</p>
              </div>
            );
          })}
        </div>

        {/* 공기 단축 4 경로 */}
        <div className="mt-16">
          <h3 className="font-display text-h5 text-ink">
            공기 단축으로 이어지는 4가지 경로
          </h3>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {PATHS.map((p) => (
              <div
                key={p.no}
                className="flex gap-4 rounded-card border border-border-soft bg-card p-5"
              >
                <span className="font-mono text-h5 leading-none text-brand">
                  {p.no}
                </span>
                <div>
                  <div className="font-semibold text-ink">{p.title}</div>
                  <p className="mt-1 text-body-sm text-ink-mid">{p.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
