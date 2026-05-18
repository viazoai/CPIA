"use client";
import { useState } from "react";
import { FileSpreadsheet, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { ConsolidatedReport, SheetTab } from "@/lib/types";
import {
  SheetTable,
  OUTPUT_MANPOWER_COLS,
  OCCUPATION_COLS,
  EQUIPMENT_COLS,
  QUANTITY_COLS,
} from "./SheetTable";

interface Props {
  report: ConsolidatedReport;
}

const TAB_LABELS: Record<SheetTab, string> = {
  output_manpower:     "1. 출력인원 현황",
  occupation_manpower: "2. 직종별 인원현황",
  equipment:           "3. 장비현황",
  quantity:            "4. 물량",
};

export function ConsolidatedReportCard({ report }: Props) {
  const [tab, setTab] = useState<SheetTab>("output_manpower");
  const [busy, setBusy] = useState(false);

  const counts = report.sheet_row_counts;

  /**
   * PoC: Exporter 에이전트 호출은 A_Track 구현 대기.
   * 시연 fallback — 약 1.5초 로딩 토스트 후 docs/sample 의 통합 작업일보 그대로 다운로드.
   * 추후 A_Track FastAPI POST /export/run?date= 가 준비되면 a.href 를 그 응답 URL 로 swap.
   */
  const handleExport = async () => {
    if (busy) return;
    setBusy(true);
    const id = toast.loading(
      `Exporter 에이전트 작동 중… (${report.date} 통합 작업일보 생성)`,
      { description: "업체별 작업일보 4 시트를 한 파일로 통합하고 있습니다." }
    );
    try {
      await new Promise((r) => setTimeout(r, 1500));
      const a = document.createElement("a");
      a.href = "/sample/cpia-consolidated-report.xlsx";
      a.download = `통합작업일보_${report.date}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      toast.success(`통합 작업일보 다운로드 완료 (${report.date})`, { id });
    } catch {
      toast.error("Exporter 실행에 실패했습니다.", { id });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-card border border-border-soft bg-card shadow-xs flex flex-col h-full overflow-hidden">
      <header className="flex items-start justify-between gap-4 px-5 py-4 border-b border-border-soft shrink-0">
        <div className="min-w-0">
          <div className="font-display text-h5 font-bold text-ink truncate">
            {report.date} 통합 작업일보
          </div>
          <div className="mt-0.5 text-xs text-ink-mid">
            {report.pjt} · 업체별 작업일보 {counts.output_manpower}건을 4 시트로 통합
          </div>
        </div>

        <button
          type="button"
          onClick={handleExport}
          disabled={busy || report.status !== "ready"}
          title={report.status !== "ready" ? "아직 처리 중인 작업일보입니다" : "엑셀 다운로드"}
          className={cn(
            "shrink-0 inline-flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-xs font-semibold text-white shadow-sm transition-colors",
            "hover:bg-brand-dark focus:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            "disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-brand"
          )}
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FileSpreadsheet className="h-4 w-4" />
          )}
          Export 엑셀
        </button>
      </header>

      <Tabs
        value={tab}
        onValueChange={(v) => setTab(v as SheetTab)}
        className="flex-1 flex flex-col min-h-0"
      >
        <TabsList className="mx-5 mt-3 mb-2 h-9 shrink-0 self-start bg-surface-soft/70">
          {(Object.keys(TAB_LABELS) as SheetTab[]).map((k) => (
            <TabsTrigger
              key={k}
              value={k}
              className="data-[state=active]:bg-card data-[state=active]:text-brand-text data-[state=active]:shadow-sm text-xs"
            >
              {TAB_LABELS[k]}
              <span className="ml-1.5 font-mono text-[10px] text-ink-light data-[state=active]:text-brand-text/70">
                {counts[k]}
              </span>
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="output_manpower" className="flex-1 overflow-auto min-h-0 m-0">
          <SheetTable cols={OUTPUT_MANPOWER_COLS} rows={report.output_manpower} />
        </TabsContent>
        <TabsContent value="occupation_manpower" className="flex-1 overflow-auto min-h-0 m-0">
          <SheetTable cols={OCCUPATION_COLS} rows={report.occupation_manpower} />
        </TabsContent>
        <TabsContent value="equipment" className="flex-1 overflow-auto min-h-0 m-0">
          <SheetTable cols={EQUIPMENT_COLS} rows={report.equipment} />
        </TabsContent>
        <TabsContent value="quantity" className="flex-1 overflow-auto min-h-0 m-0">
          <SheetTable cols={QUANTITY_COLS} rows={report.quantity} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
