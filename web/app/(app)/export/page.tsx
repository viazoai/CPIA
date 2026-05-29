"use client";
import { useEffect, useState } from "react";
import { FileSpreadsheet, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { ExportDailyList } from "@/app/components/export/ExportDailyList";
import { ConsolidatedReportCard } from "@/app/components/export/ConsolidatedReportCard";
import { Button } from "@/components/ui/button";
import type {
  ConsolidatedReport,
  ConsolidatedReportSummary,
} from "@/lib/types";

const SITE_ID = "m15x-ph3-ibl";

export default function ExportPage() {
  const [list, setList] = useState<ConsolidatedReportSummary[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [report, setReport] = useState<ConsolidatedReport | null>(null);
  const [busy, setBusy] = useState(false);

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

  async function handleExport() {
    if (busy || !report?.date || report.status !== "ready") return;
    setBusy(true);
    try {
      const base = process.env.NEXT_PUBLIC_FASTAPI_BASE || "http://localhost:8000";
      const url = `${base}/export/run?site_id=${encodeURIComponent(SITE_ID)}&date=${report.date}`;
      const res = await fetch(url);
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Export 실패 (${res.status}): ${text}`);
      }
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `통합작업일보_${report.date}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
    } catch (err) {
      console.error("Export 실패:", err);
      toast.error(`다운로드 실패: ${err instanceof Error ? err.message : "알 수 없는 오류"}`);
    } finally {
      setBusy(false);
    }
  }

  const canExport = !!report && report.status === "ready" && !busy;

  return (
    <div className="flex flex-col lg:h-[calc(100vh-4rem)] lg:overflow-hidden">
      <div className="mx-auto w-full max-w-screen-2xl border-b border-border-soft px-6 pt-10 pb-6 md:px-10 md:pt-14 shrink-0">
        <div className="flex items-end justify-between gap-6">
          <div className="min-w-0">
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
          <Button
            type="button"
            size="sm"
            onClick={handleExport}
            disabled={!canExport}
            title={!report ? "일자를 선택해주세요" : report.status !== "ready" ? "아직 처리 중인 작업일보입니다" : "엑셀 다운로드"}
            className="h-9 shrink-0 gap-1.5"
          >
            {busy ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <FileSpreadsheet className="h-3.5 w-3.5" />
            )}
            Excel 출력
          </Button>
        </div>
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

          {/* 메인: 4 시트 탭 (Export 버튼은 페이지 헤더로 이동) */}
          <div className="col-span-12 md:col-span-9 flex flex-col min-h-0">
            {report ? (
              <ConsolidatedReportCard report={report} />
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
