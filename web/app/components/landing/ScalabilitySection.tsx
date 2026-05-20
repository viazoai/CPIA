import { Cpu, Globe, Layers } from "lucide-react";

const AXES = [
  {
    icon: Cpu,
    axis: "AXIS 01",
    category: "MODULAR ADAPTATION",
    title: "현장별 양식이 달라도, 노드 교체로 즉시 적용",
    body:
      "유지보수가 간편한 LangGraph 기술로 설계하여 현장마다 다른 작업일보 양식에 Parser·Exporter 같은 일부 노드만 교체하면 그 현장에 맞춰 즉시 동작.",
    target: "2~3일 내 신속한 커스터마이징 가능",
    active: true,
  },
  {
    icon: Globe,
    axis: "AXIS 02",
    category: "CROSS-PRODUCT REACH",
    title: "Hi-tech → AI DC · 인프라 · 주택 까지",
    body:
      "작업일보와 생산성 분석은 현장 종류와 무관한 공통 업무로 Hi-tech 에서 검증한 동일 Agent 를 모든 사업 프로덕트에 그대로 적용.",
    target: "전 EPC 사업 프로덕트 공통 적용",
    active: true,
  },
  {
    icon: Layers,
    axis: "AXIS 03",
    category: "VALUE CHAIN EXPANSION",
    title: "MPRS 관점에서의 확장 가능성",
    body:
      "CPIA는 시공(P) 단계의 최적화를 지향하고 있으나, 누적 데이터·패턴을 설계(R)과 구매/조달(S) 단계로 확장해 예측 가능성을 높히고, 전체 EPC value chain 의 공기 단축 레버 확보.",
    target: "PRS 영역의 예상공기 검토시간 50% 절감",
    active: true,
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
            조직의 변화로 이어지는 확장 가능성
          </h2>
          <p className="mt-6 text-body text-ink-mid">
            현장별 양식엔 노드 교체로 즉시 대응. 동일 Agent 는 모든 사업 프로덕트에 그대로 적용. 시공의 학습은 설계·구매 영역까지 확장되어 EPC value chain 전반의 공기 단축으로 이어집니다.
          </p>
        </div>

        <ol className="mt-14 grid gap-4 md:grid-cols-3">
          {AXES.map((a) => {
            const Icon = a.icon;
            return (
              <li
                key={a.axis}
                className={`relative flex h-full flex-col rounded-card-lg border p-6 transition-all ${
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
                <p className="mt-3 grow text-body-sm text-ink-mid">{a.body}</p>
                <div className="mt-5 border-t border-border-soft pt-4">
                  <span className="text-[11px] font-medium uppercase tracking-wider text-ink-light">
                    Impact
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
