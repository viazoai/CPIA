"use client";
import { useEffect, useState } from "react";
import { QuadrantScatter } from "../charts/QuadrantScatter";
import { QuadrantCountKpi } from "./QuadrantCountKpi";
import { OptimizerResult } from "./OptimizerResult";
import type { ReportDetail } from "@/lib/fixtures";

type Filter = "all" | "risk" | "caution" | "safe";

export function OptimizeTab({ detail }: { detail: ReportDetail }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedWp, setSelectedWp] = useState<string | null>(null);

  useEffect(() => {
    const riskPoint = detail.quadrant.find((p) => p.quadrant === "risk");
    const timer = setTimeout(() => {
      if (riskPoint) setSelectedWp(riskPoint.wp_id);
    }, 500);
    return () => clearTimeout(timer);
  }, [detail.quadrant]);

  const optimizer = detail.optimizer;

  return (
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12 md:col-span-6">
        <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
          <div className="font-mono text-[10px] uppercase tracking-widest text-ink-light mb-2">
            Impact × Productivity 산점도
          </div>
          <QuadrantScatter
            points={detail.quadrant}
            selectedWpId={selectedWp}
            onSelect={setSelectedWp}
            filter={filter}
          />
          <div className="mt-3 text-[10px] text-ink-light text-center">
            점 크기 = 잔여 물량. 좌상 = 고Impact·저Productivity (위험군).
          </div>
        </div>
      </div>

      <div className="col-span-12 md:col-span-6 flex flex-col gap-3">
        <QuadrantCountKpi points={detail.quadrant} filter={filter} onFilterChange={setFilter} />
        <OptimizerResult output={optimizer} />
      </div>
    </div>
  );
}
