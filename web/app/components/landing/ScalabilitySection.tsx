import { Building2, Cpu, Globe, Package } from "lucide-react";

const HORIZONS = [
  {
    icon: Building2,
    phase: "Horizon 1",
    period: "0 ~ 6 개월",
    title: "Hi-tech 사업부 전 현장",
    body: "파일럿 6개 현장 → Hi-tech 전체로 순차 확산. 발주처(하이닉스·삼성) 보고 포맷 모듈화, 현장간 생산성 벤치마크 표준화.",
    target: "2,155h / 월 절감",
    active: true,
  },
  {
    icon: Cpu,
    phase: "Horizon 2",
    period: "6 ~ 12 개월",
    title: "AI Solution 사업부 적용",
    body: "에너지사업관리팀 QG 품의 자동 작성 144h/월, AI DC Infra Pre-con 주간보고 35h/월. 에너지 현장 특화 파서 추가.",
    target: "+179h / 월",
  },
  {
    icon: Globe,
    phase: "Horizon 2",
    period: "6 ~ 12 개월",
    title: "글로벌 사업부 적용",
    body: "Indiana Fab HAC(미국) 파일럿 진행. 영문 작업일보 Semantic Mapping 모듈 추가. 글로벌 Deal Sourcing MI 자동화 연계.",
    target: "월 4,200h+ 통합",
  },
  {
    icon: Package,
    phase: "Horizon 3",
    period: "18 개월+",
    title: "AI Solution 상품화",
    body: "CPIA 를 AI Infra Solution Provider 자체 솔루션으로 SaaS 화. 타 건설사·발주처 대상 외부 수익화. Hi-tech 레퍼런스 활용.",
    target: "외부 수익화",
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
            / 04 — Roadmap
          </span>
          <h2 className="mt-3 font-display text-h3 text-ink">
            BP 작업일보 → 공정 관리 패턴은 건설 산업 전체의 공통 Pain
          </h2>
          <p className="mt-6 text-body text-ink-mid">
            Hi-tech 사업부 내재화 후 SK ecosystem · 글로벌 · 상품화로 단계 확장.
          </p>
        </div>

        <ol className="mt-14 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {HORIZONS.map((h, i) => {
            const Icon = h.icon;
            return (
              <li
                key={i}
                className={`relative rounded-card-lg border p-6 transition-all ${
                  h.active
                    ? "border-brand bg-gradient-to-br from-brand-light/60 via-card to-card shadow-md"
                    : "border-border-soft bg-surface-soft/40"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-flex h-9 w-9 items-center justify-center rounded-md ${
                      h.active
                        ? "bg-brand text-white"
                        : "bg-card text-ink-mid"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                  <span
                    className={`text-[11px] font-medium uppercase tracking-[0.12em] ${
                      h.active ? "text-brand-text" : "text-ink-light"
                    }`}
                  >
                    {h.phase}
                  </span>
                </div>
                <div className="mt-5 text-[11px] font-medium uppercase tracking-[0.08em] text-ink-light">
                  {h.period}
                </div>
                <h3 className="mt-2 font-display text-h6 text-ink">{h.title}</h3>
                <p className="mt-3 text-body-sm text-ink-mid">{h.body}</p>
                <div className="mt-5 border-t border-border-soft pt-4">
                  <span className="text-[11px] font-medium uppercase tracking-wider text-ink-light">
                    Target
                  </span>
                  <div
                    className={`mt-0.5 font-display text-base font-semibold ${
                      h.active ? "text-brand-text" : "text-ink"
                    }`}
                  >
                    {h.target}
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
