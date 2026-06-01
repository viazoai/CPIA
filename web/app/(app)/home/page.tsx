export const dynamic = "force-dynamic";

import { loadFixture } from "@/lib/fixtures";
import { HomeGreetingHeader } from "@/app/components/home/HomeGreetingHeader";
import { HomeProcessingSection } from "@/app/components/home/HomeProcessingSection";
import { HomeWorkSummaryCard } from "@/app/components/home/HomeWorkSummaryCard";

/**
 * /home — 구성원 운영 홈 (단일 현장 = M15X).
 * spec: docs/superpowers/specs/2026-06-01-cpia-home-member-redesign-design.md
 * 레이아웃 리듬은 Dashboard/Reports 와 동일 (헤더 밴드 border-b → max-w-screen-2xl 섹션).
 */
export default async function HomePage() {
  const home = await loadFixture("home");
  const report = await loadFixture("report");
  const rows = report.details[home.site.date]?.raw_data ?? [];

  return (
    <div className="flex flex-col">
      <HomeGreetingHeader user={home.user} site={home.site} />

      <section className="mx-auto flex w-full max-w-screen-2xl flex-col gap-8 px-6 pb-20 pt-8 md:px-10 md:pt-10">
        <HomeProcessingSection
          processing={home.processing}
          unsubmitted={home.unsubmitted_companies}
        />
        <HomeWorkSummaryCard rows={rows} workSummary={home.work_summary} />
      </section>
    </div>
  );
}
