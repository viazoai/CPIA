import { Cpu, Globe, Layers } from "lucide-react";

const AXES = [
  {
    icon: Cpu,
    axis: "AXIS 01",
    category: "FOUNDATION",
    title: "LangGraph 기반 — 쉽게 교체할 수 있도록 설계",
    body:
      "7개 Agent 가 독립 모듈로 구성되어, 현장 특성에 맞춰 일부 노드만 교체하면 동작. 새 현장·새 영역으로 옮길 때 코어 재학습 없이 빠르게 적용할 수 있도록 LangGraph 기술로 설계.",
    target: "노드 교체 only · 코어 재학습 불요",
    active: true,
  },
  {
    icon: Globe,
    axis: "AXIS 02",
    category: "HORIZONTAL SCALE-OUT",
    title: "Hi-tech 6개 → SK ecosystem 전체",
    body:
      "Hi-tech 사업부 6개 현장 내재화 후, AI Solution·글로벌 사업부로 동일 LangGraph 베이스 확산. 발주처 포맷·언어 모듈만 교체하여 신규 현장 적용.",
    target: "월 4,200h+ 통합 절감 (사업부 누적)",
  },
  {
    icon: Layers,
    axis: "AXIS 03",
    category: "MPRS DOMAIN EXPANSION",
    title: "P-Construction → R-Engineering · P-Procurement · M / PM",
    body:
      "현재 P-Construction 한정. 동일 패턴으로 R-Engineering (VE·Clash Detection·예상공기 검토), P-Procurement (자재 수급 예측), M / PM 까지 확장하여 전 EPC 단계 공기 단축에 기여.",
    target: "예상공기 검토시간 50% 절감 (Hi-tech 정보화 과제 요청 기준)",
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
            LangGraph 기반 노드 모듈 구조로 — 현장 다양성과 MPRS 전 영역을 같은 베이스에서 흡수. Hi-tech P-Construction 의 학습을 SK ecosystem 전체로 전이.
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
