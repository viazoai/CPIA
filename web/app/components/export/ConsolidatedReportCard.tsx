"use client";
import { useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
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
  output_manpower:     "1. 작업사항",
  occupation_manpower: "2. 직종별 인원현황",
  equipment:           "3. 장비현황",
  quantity:            "4. 물량",
};

export function ConsolidatedReportCard({ report }: Props) {
  const [tab, setTab] = useState<SheetTab>("output_manpower");

  const counts = report.sheet_row_counts;

  return (
    <div className="rounded-card border border-border-soft bg-card shadow-xs flex flex-col h-full overflow-hidden">
      <header className="px-5 py-4 border-b border-border-soft shrink-0">
        <div className="font-display text-h5 font-bold text-ink truncate">
          {report.date} 통합 작업일보
        </div>
        <div className="mt-0.5 text-xs text-ink-mid">
          {report.pjt} · 업체별 작업일보 {counts.output_manpower}건을 4 시트로 통합
        </div>
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
