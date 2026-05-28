"use client";
import { useEffect, useState } from "react";
import { ExportDailyList } from "@/app/components/export/ExportDailyList";
import { ConsolidatedReportCard } from "@/app/components/export/ConsolidatedReportCard";
import type {
  ConsolidatedReport,
  ConsolidatedReportSummary,
} from "@/lib/types";

const SITE_ID = "m15x-ph3-ibl";

export default function ExportPage() {
  const [list, setList] = useState<ConsolidatedReportSummary[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [report, setReport] = useState<ConsolidatedReport | null>(null);

  // 1) 목록 fetch — 첫 항목을 자동 선택
  useEffect(() => {
    fetch("/api/mock/consolidated")
      .then((r) => r.json())
      .then((d: ConsolidatedReportSummary[]) => {
        setList(d);
        if (d.length > 0) setSelectedDate(d[0].date);
      });
  }, []);

  // 2) 단건 fetch — 선택 일자 변경 시
  useEffect(() => {
    if (!selectedDate) return;
    setReport(null);
    fetch(`/api/mock/consolidated?date=${selectedDate}`)
      .then((r) => r.json())
      .then((d: ConsolidatedReport) => setReport(d));
  }, [selectedDate]);

  return (
    <div className="flex flex-col lg:h-[calc(100vh-4rem)] lg:overflow-hidden">
      <div className="mx-auto w-full max-w-screen-2xl border-b border-border-soft px-6 pt-10 pb-6 md:px-10 md:pt-14 shrink-0">
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          / 04 — Export
        </span>
        <h1 className="mt-3 font-display text-h3 text-ink">
          통합 작업일보 출력
        </h1>
        <p className="mt-2 text-body-sm text-ink-mid">
          7개 Agent 가 처리한 업체별 작업일보를 한 화면에서 확인하고, Exporter 에이전트로 통합 엑셀을 출력합니다.
        </p>
      </div>

      <section className="mx-auto w-full max-w-screen-2xl px-6 pt-4 pb-8 md:px-10 flex-1 min-h-0">
        <div className="grid grid-cols-12 gap-3 items-stretch h-full">
          {/* 좌측: 일자별 통합작업일보 리스트 */}
          <div className="col-span-12 md:col-span-3 rounded-card border border-border-soft bg-card shadow-xs overflow-hidden flex flex-col min-h-0">
            <ExportDailyList
              list={list}
              selectedDate={selectedDate}
              onSelect={setSelectedDate}
            />
          </div>

          {/* 메인: 4 시트 탭 + Export 버튼 */}
          <div className="col-span-12 md:col-span-9 flex flex-col min-h-0">
            {report ? (
              <ConsolidatedReportCard report={report} siteId={SITE_ID} />
            ) : (
              <div className="h-full rounded-card border border-border-soft bg-card shadow-xs flex items-center justify-center text-ink-light">
                {selectedDate ? "통합 작업일보 불러오는 중…" : "일자를 선택해주세요"}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
