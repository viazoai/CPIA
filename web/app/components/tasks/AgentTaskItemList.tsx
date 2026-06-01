"use client";
import { cn } from "@/lib/utils";
import { CheckCircle2, Loader2, Inbox, Pause, AlertOctagon } from "lucide-react";
import type { AgentTaskItem, AgentStageProgress } from "@/lib/types";

interface Props {
  selectedAgent: string | null;
  stage: AgentStageProgress | null;
  items: AgentTaskItem[];
}

const STATUS_META: Record<AgentTaskItem["status"], { label: string; cls: string; Icon: React.ComponentType<{ className?: string }> }> = {
  done:        { label: "처리완료",  cls: "text-mint-text bg-mint-light",   Icon: CheckCircle2 },
  processing:  { label: "처리중",    cls: "text-sky-text bg-sky-light",     Icon: Loader2 },
  received:    { label: "접수",      cls: "text-ink-mid bg-surface-soft",   Icon: Inbox },
  hil_pending: { label: "검토대기",  cls: "text-brand-text bg-brand-light", Icon: Pause },
  blocked:     { label: "차단",      cls: "text-rose-text bg-rose-light",   Icon: AlertOctagon },
};

export function AgentTaskItemList({ selectedAgent, stage, items }: Props) {
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

        {selectedAgent && items.length === 0 && (
          <div className="flex h-full items-center justify-center text-body-sm text-ink-light">
            해당 단계에 표시할 건이 없습니다
          </div>
        )}

        {selectedAgent && items.length > 0 && (
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface-soft/80 backdrop-blur text-[11px] text-ink-mid">
              <tr className="border-b border-border-soft">
                <th className="px-3 py-1.5 text-left font-mono font-medium">ID</th>
                <th className="px-3 py-1.5 text-left font-medium">공종</th>
                <th className="px-3 py-1.5 text-left font-medium">BP사</th>
                <th className="px-3 py-1.5 text-right font-medium">상태</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => {
                const meta = STATUS_META[it.status];
                return (
                  <tr key={it.id} className="border-b border-border-soft hover:bg-surface-soft/50">
                    <td className="px-3 py-1 font-mono text-[11px] text-ink">{it.id}</td>
                    <td className="px-3 py-1 text-[12px] text-ink">{it.trade}</td>
                    <td className="px-3 py-1 text-[12px] text-ink-mid">{it.contractor}</td>
                    <td className="px-3 py-1 text-right">
                      <span className={cn(
                        "inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[10px] font-semibold",
                        meta.cls
                      )}>
                        <meta.Icon className={cn("h-2.5 w-2.5", it.status === "processing" && "animate-spin")} />
                        {meta.label}
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
