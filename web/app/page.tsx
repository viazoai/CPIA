import { loadFixture } from "@/lib/fixtures";
import { Hero } from "./components/home/Hero";
import { NowStrip } from "./components/home/NowStrip";
import { AgentCard } from "./components/home/AgentCard";
import { HilReviewStage } from "./components/home/HilReviewStage";

export default async function HomePage() {
  const summary = await loadFixture("sites_summary");
  const agents = await loadFixture("agent_status");

  const collectGroup = agents.filter((a) => a.group === "collect");
  const analyzeGroup = agents.filter((a) => a.group === "analyze");

  return (
    <div className="relative bg-[#0a0d1f] text-white overflow-hidden pb-28">
      {/* Subtle film grain overlay for cinematic feel */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.12] mix-blend-overlay"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.6'/></svg>\")",
        }}
      />

      {/* Vignette */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.4) 100%)",
        }}
      />

      <Hero />

      <NowStrip summary={summary} />

      <section className="relative mx-auto max-w-wrap px-6 mt-20 md:px-10">
        <div className="mb-7 flex flex-col items-center text-center md:flex-row md:items-baseline md:justify-between md:text-left">
          <div className="flex flex-col items-center gap-1.5 md:flex-row md:items-baseline md:gap-3">
            <h2 className="font-display text-2xl font-bold tracking-tight text-white md:text-3xl">
              7-Agent 파이프라인
            </h2>
            <span className="font-mono text-xs uppercase tracking-wider text-white/45">
              LangGraph · multi-agent · HIL Review
            </span>
          </div>
          <span className="mt-2 font-mono text-[11px] uppercase tracking-wider text-white/35 md:mt-0">
            / Pipeline overview
          </span>
        </div>

        {/* 수집·매핑 */}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
          {collectGroup.map((a) => (
            <AgentCard key={a.step} agent={a} />
          ))}
        </div>

        {/* HIL Review 단계 */}
        <HilReviewStage />

        {/* 진단·최적화 */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3 md:gap-4">
          {analyzeGroup.map((a) => (
            <AgentCard key={a.step} agent={a} />
          ))}
        </div>
      </section>
    </div>
  );
}
