import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { loadFixture } from "@/lib/fixtures";
import { Hero } from "./components/home/Hero";
import { NowStrip } from "./components/home/NowStrip";
import { AgentCard } from "./components/home/AgentCard";
import { HilReviewStage } from "./components/home/HilReviewStage";

export default async function HomePage() {
  const summary = await loadFixture("sites_summary");
  const agents = await loadFixture("agent_status");

  const collectGroup = agents.filter((a) => a.group === "collect"); // STEP 01~04
  const analyzeGroup = agents.filter((a) => a.group === "analyze"); // STEP 05~07

  return (
    <div className="relative pb-20">
      <Hero />
      <NowStrip summary={summary} />

      <section className="mx-auto max-w-wrap px-6 mt-12 md:px-10">
        <div className="mb-6 flex items-baseline justify-between">
          <div className="flex items-baseline gap-3">
            <h2 className="font-display text-lg font-bold tracking-tight text-ink md:text-xl">
              7-Agent 파이프라인 + HIL Review
            </h2>
            <span className="font-mono text-[10px] uppercase tracking-widest text-ink-light">
              LangGraph · multi-agent pipeline
            </span>
          </div>
        </div>

        {/* 수집·매핑 (sky) */}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {collectGroup.map((a) => <AgentCard key={a.step} agent={a} />)}
        </div>

        {/* HIL Review 단계 */}
        <HilReviewStage />

        {/* 진단·최적화 (lavender) */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {analyzeGroup.map((a) => <AgentCard key={a.step} agent={a} />)}
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-wrap px-6 mt-14 md:px-10">
        <Link
          href="/tasks"
          className="group inline-flex items-center gap-2 rounded-md bg-lavender px-5 py-3 text-sm font-semibold text-white shadow-sm transition-all hover:bg-lavender-text hover:shadow-md"
        >
          Agent Tasks 살펴보기
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" strokeWidth={2.5} />
        </Link>
      </section>
    </div>
  );
}
