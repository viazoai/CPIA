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

  // 작업내용 = 해당 날짜의 raw_data. 날짜가 어긋나면(데모 데이터 변경 등)
  // 가장 최근 날짜로 fallback → 라이브 시연 중 테이블이 조용히 비는 것 방지.
  const details = report.details ?? {};
  const latestDate = Object.keys(details).sort().pop() ?? "";
  const rows =
    details[home.site.date]?.raw_data ?? details[latestDate]?.raw_data ?? [];

  return (
    <div className="flex flex-col">
      <HomeGreetingHeader user={home.user} site={home.site} />

      <section className="mx-auto grid w-full max-w-screen-2xl grid-cols-1 gap-6 px-6 pb-10 pt-6 md:px-10 md:pt-8 xl:grid-cols-12">
        {/* 좌 — 처리현황 2×2 + 미제출 */}
        <div className="xl:col-span-5">
          <HomeProcessingSection
            processing={home.processing}
            unsubmitted={home.unsubmitted_companies}
          />
        </div>
        {/* 우 — 작업내용 테이블 */}
        <div className="xl:col-span-7">
          <HomeWorkSummaryCard rows={rows} workSummary={home.work_summary} />
        </div>
      </section>
    </div>
  );
}
