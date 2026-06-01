"use client";
import { cn } from "@/lib/utils";
import { CheckCircle2, Loader2, Inbox, Pause, AlertOctagon } from "lucide-react";
import type { AgentTaskRow, AgentItemTone, AgentStageProgress } from "@/lib/types";
import { AGENT_COLUMNS, statusHeaderFor } from "@/lib/agent-task-schema";

interface Props {
  selectedAgent: string | null;
  stage: AgentStageProgress | null;
  rows: AgentTaskRow[];
}

const TONE_META: Record<AgentItemTone, { cls: string; Icon: React.ComponentType<{ className?: string }> }> = {
  done:        { cls: "text-mint-text bg-mint-light",   Icon: CheckCircle2 },
  processing:  { cls: "text-sky-text bg-sky-light",     Icon: Loader2 },
  received:    { cls: "text-ink-mid bg-surface-soft",   Icon: Inbox },
  hil_pending: { cls: "text-brand-text bg-brand-light", Icon: Pause },
  blocked:     { cls: "text-rose-text bg-rose-light",   Icon: AlertOctagon },
  // 진단 톤 (Forecaster/Optimizer status 칩에 쓰일 경우 대비)
  normal:      { cls: "text-mint-text bg-mint-light",   Icon: CheckCircle2 },
  caution:     { cls: "text-sun-text bg-sun-light",     Icon: Pause },
  risk:        { cls: "text-rose-text bg-rose-light",   Icon: AlertOctagon },
};

export function AgentTaskItemList({ selectedAgent, stage, rows }: Props) {
  const columns = selectedAgent ? AGENT_COLUMNS[selectedAgent] ?? [] : [];
  const statusHeader = statusHeaderFor(selectedAgent);

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-border-soft shrink-0">
        <div className="font-display text-h6 font-bold text-ink">
          {selectedAgent ? `${selectedAgent} 건 목록` : "단계별 건 목록"}
        </div>
        <div className="mt-0.5 text-xs text-ink-mid">
          {selectedAgent && stage
            ? `접수 ${stage.received}건 · 처리 ${stage.processed}건 · ${stage.percent}%`
            : "좌측 Agent Workflow 에서 단계를 선택하세요"}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {!selectedAgent && (
          <div className="flex h-full items-center justify-center text-body-sm text-ink-light">
            단계 미선택
          </div>
        )}

        {selectedAgent && rows.length === 0 && (
          <div className="flex h-full items-center justify-center text-body-sm text-ink-light">
            해당 단계에 표시할 건이 없습니다
          </div>
        )}

        {selectedAgent && rows.length > 0 && (
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface-soft/80 backdrop-blur text-[11px] text-ink-mid">
              <tr className="border-b border-border-soft">
                {columns.map((col) => (
                  <th
                    key={col.key}
                    className={cn(
                      "px-3 py-1.5 font-medium",
                      col.align === "right" ? "text-right" : "text-left",
                      col.mono && "font-mono",
                    )}
                  >
                    {col.label}
                  </th>
                ))}
                <th className="px-3 py-1.5 text-right font-medium">{statusHeader}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const meta = TONE_META[row.statusTone] ?? TONE_META.done;
                return (
                  <tr key={row.id} className="border-b border-border-soft hover:bg-surface-soft/50">
                    {columns.map((col, ci) => (
                      <td
                        key={col.key}
                        className={cn(
                          "px-3 py-1 text-[12px]",
                          col.align === "right" ? "text-right" : "text-left",
                          col.mono && "font-mono",
                          // 첫 컬럼만 진하게, 나머지는 보조색 — 기존 공종/BP사 위계 유지
                          ci === 0 ? "text-ink" : "text-ink-mid",
                        )}
                      >
                        {row.values[col.key] ?? "—"}
                      </td>
                    ))}
                    <td className="px-3 py-1 text-right">
                      <span className={cn(
                        "inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[10px] font-semibold",
                        meta.cls,
                      )}>
                        <meta.Icon className={cn("h-2.5 w-2.5", row.statusTone === "processing" && "animate-spin")} />
                        {row.statusLabel}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
