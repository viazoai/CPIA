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

  return (
    <div className="flex flex-col xl:h-[calc(100dvh-4rem)]">
      <HomeGreetingHeader user={home.user} site={home.site} />

      <section className="mx-auto grid w-full max-w-screen-2xl grid-cols-1 items-start gap-6 px-6 pb-10 pt-6 md:px-10 md:pt-8 xl:grid-cols-12 xl:grid-rows-1 xl:flex-1 xl:items-stretch xl:min-h-0">
        {/* 좌 — 처리현황 2×2 + 미제출 (FHD 크기 고정, 상단 정렬) */}
        <div className="xl:col-span-5 xl:min-h-0">
          <HomeProcessingSection
            processing={home.processing}
            unsubmitted={home.unsubmitted_companies}
          />
        </div>
        {/* 우 — 작업내용 테이블 */}
        <div className="xl:col-span-7 xl:min-h-0">
          <HomeWorkSummaryCard rows={home.work_rows} workSummary={home.work_summary} brief={home.work_brief} />
        </div>
      </section>
    </div>
  );
}
