import { Cpu, Globe, Layers } from "lucide-react";

const AXES = [
  {
    icon: Cpu,
    axis: "AXIS 01",
    category: "FOUNDATION",
    title: "노드만 교체하면 새 현장에 적용",
    body:
      "Agent 가 독립 노드로 구성되어, 현장 특성에 맞는 일부만 교체하면 동작. LangGraph 로 설계해 재학습 없이 빠르게 확장.",
    target: "노드 교체 only · 코어 재학습 불요",
    active: true,
  },
  {
    icon: Globe,
    axis: "AXIS 02",
    category: "HORIZONTAL SCALE-OUT",
    title: "Hi-tech 6개 → SK ecosystem 전체",
    body:
      "Hi-tech 6개 현장에서 검증 후 AI Solution·글로벌 사업부로 확산. 발주처 포맷·언어만 맞추면 신규 적용.",
    target: "월 4,200h+ 통합 절감",
  },
  {
    icon: Layers,
    axis: "AXIS 03",
    category: "UPSTREAM IMPACT",
    title: "시공 진단이 설계·지원 의사결정으로 사전 이동",
    body:
      "지금까지의 P-시공 단계는 사후 진단. 누적 데이터·패턴을 R-설계와 S-지원 단계로 환류해 사후 발견을 사전 차단으로 전환 → 전체 EPC value chain 의 공기 단축 레버 확보.",
    target: "예상공기 검토시간 50% 절감 (R-설계 첫 진입)",
  },
];

export function ScalabilitySection() {
  return (
    <section
      id="roadmap"
      className="border-t border-border-soft bg-card py-24 md:py-32"
    >
      <div className="mx-auto max-w-wrap px-6 md:px-10">
        <div className="max-w-3xl">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
            / 04 — Scalability · 확장성
          </span>
          <h2 className="mt-3 font-display text-h3 text-ink">
            하나의 현장 패턴이, 다른 현장·다른 영역의 출발점이 된다
          </h2>
          <p className="mt-6 text-body text-ink-mid">
            Hi-tech 시공 현장에서 검증한 패턴을, 다른 현장과 다른 사업 영역으로 빠르게 확장합니다.
          </p>
        </div>

        <ol className="mt-14 grid gap-4 md:grid-cols-3">
          {AXES.map((a) => {
            const Icon = a.icon;
            return (
              <li
                key={a.axis}
                className={`relative rounded-card-lg border p-6 transition-all ${
                  a.active
                    ? "border-brand bg-gradient-to-br from-brand-light/60 via-card to-card shadow-md"
                    : "border-border-soft bg-surface-soft/40"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-flex h-9 w-9 items-center justify-center rounded-md ${
                      a.active ? "bg-brand text-white" : "bg-card text-ink-mid"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                  <span
                    className={`text-[11px] font-medium uppercase tracking-[0.12em] ${
                      a.active ? "text-brand-text" : "text-ink-light"
                    }`}
                  >
                    {a.axis}
                  </span>
                </div>
                <div className="mt-5 text-[11px] font-medium uppercase tracking-[0.08em] text-ink-light">
                  {a.category}
                </div>
                <h3 className="mt-2 font-display text-h6 text-ink">{a.title}</h3>
                <p className="mt-3 text-body-sm text-ink-mid">{a.body}</p>
                <div className="mt-5 border-t border-border-soft pt-4">
                  <span className="text-[11px] font-medium uppercase tracking-wider text-ink-light">
                    Target
                  </span>
                  <div
                    className={`mt-0.5 font-display text-base font-semibold ${
                      a.active ? "text-brand-text" : "text-ink"
                    }`}
                  >
                    {a.target}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
