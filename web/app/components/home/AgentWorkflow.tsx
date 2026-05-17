import {
  Inbox,
  FileSearch,
  GitBranch,
  Database,
  FileText,
  Activity,
  Sparkles,
  ClipboardCheck,
} from "lucide-react";
import type { AgentStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

interface AgentWorkflowProps {
  agents: AgentStatus[];
}

/* step → 아이콘 매핑 */
const STEP_ICON: Record<number, React.ComponentType<{ className?: string }>> = {
  1: Inbox,
  2: FileSearch,
  3: GitBranch,
  4: Database,
  5: FileText,
  6: Activity,
  7: Sparkles,
};

/* mock — 시연용 대기/오늘/누적 분배 (Collector 87 → Optimizer 24 로 점진 감소) */
const COUNTS: Record<number, { waiting: number; today: number; total: number }> = {
  1: { waiting: 2,  today: 87, total: 1247 },
  2: { waiting: 4,  today: 87, total: 1247 },
  3: { waiting: 6,  today: 81, total: 1201 },
  4: { waiting: 3,  today: 78, total: 1166 },
  5: { waiting: 1,  today: 78, total: 1166 },
  6: { waiting: 0,  today: 78, total: 1166 },
  7: { waiting: 54, today: 24, total: 824 },
};

const STATE_DOT: Record<AgentStatus["state"], string> = {
  processing: "bg-mint animate-pulse",
  waiting:    "bg-sun",
  idle:       "bg-ink-light/30",
};

const STATE_LABEL: Record<AgentStatus["state"], string> = {
  processing: "processing",
  waiting:    "waiting",
  idle:       "idle",
};

/* HIL 단계 — 시연 시나리오 v1 에 따라 1단계(Mapper Review)만 표시.
 * 2차 H-i-L 은 Forecaster 4분면 자동 라우팅으로 대체. */
interface HilSpec {
  no: 1;
  title: string;
  description: string;
  waiting: number;
  icon: React.ComponentType<{ className?: string }>;
  /** Agent step 다음에 끼움 (3 = Mapper 다음) */
  afterStep: number;
}
const HILS: HilSpec[] = [
  {
    no: 1,
    afterStep: 3,
    title: "Mapping Review",
    description: "확신도 낮은 WBS 매핑 항목을 담당자가 검토·수정",
    waiting: 3,
    icon: ClipboardCheck,
  },
];

export function AgentWorkflow({ agents }: AgentWorkflowProps) {
  const sorted = [...agents].sort((a, b) => a.step - b.step);

  /* render: agent → connector → 다음 agent. 중간에 afterStep 매칭되면 HIL 끼움 */
  const blocks: React.ReactNode[] = [];
  sorted.forEach((agent, i) => {
    blocks.push(<AgentRow key={`a-${agent.step}`} agent={agent} />);
    const isLast = i === sorted.length - 1;
    const hil = HILS.find((h) => h.afterStep === agent.step);
    if (!isLast) {
      blocks.push(<Connector key={`c-${agent.step}`} />);
      if (hil) {
        blocks.push(<HilRow key={`h-${hil.no}`} spec={hil} />);
        blocks.push(<Connector key={`c-${agent.step}-2`} />);
      }
    }
  });

  return (
    <div className="rounded-card-lg border border-border bg-card p-6 md:p-8">
      <div className="mb-5 flex items-baseline justify-between">
        <h2 className="font-display text-h5 text-ink">
          Agent 워크플로우 단계별 처리현황
        </h2>
        <span className="font-mono text-[11px] uppercase tracking-wider text-ink-light">
          LangGraph · 세로 진행
        </span>
      </div>

      <ol className="flex flex-col">{blocks}</ol>
    </div>
  );
}

/* ============================================================== */

function CountCol({
  label,
  value,
  tone = "ink",
}: {
  label: string;
  value: number;
  tone?: "ink" | "ink-mid" | "brand";
}) {
  const valueClass =
    tone === "brand"
      ? "text-brand-text"
      : tone === "ink-mid"
      ? "text-ink-mid"
      : "text-ink";
  return (
    <div className="text-right tabular-nums">
      <div className="font-mono text-[9px] uppercase tracking-wider text-ink-light">
        {label}
      </div>
      <div className={cn("font-display text-base font-semibold leading-none", valueClass)}>
        {value.toLocaleString()}
      </div>
    </div>
  );
}

function AgentRow({ agent }: { agent: AgentStatus }) {
  const Icon = STEP_ICON[agent.step] ?? Sparkles;
  const counts = COUNTS[agent.step];
  return (
    <li className="flex items-center gap-3 rounded-card border border-border-soft bg-surface-soft/40 px-3 py-2 transition-colors hover:bg-surface-soft md:px-4 md:py-2.5">
      {/* Left — STEP + icon */}
      <div className="flex items-center gap-2">
        <span className="hidden font-mono text-[10px] font-semibold uppercase tracking-wider text-ink-light md:inline">
          {String(agent.step).padStart(2, "0")}
        </span>
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-card text-ink-mid shadow-xs">
          <Icon className="h-3.5 w-3.5" />
        </span>
      </div>

      {/* Middle — name + description (1줄) */}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="font-display text-body-sm font-semibold text-ink">
            {agent.name}
          </span>
          <span className="shrink-0 text-xs text-ink-mid">{agent.korean_name}</span>
          <span className="hidden truncate text-xs text-ink-light md:inline">
            · {agent.description}
          </span>
        </div>
      </div>

      {/* Right — 대기 / 오늘 / 누적 + state dot */}
      <div className="hidden items-center gap-4 md:flex">
        <CountCol label="대기" value={counts.waiting} tone={counts.waiting > 0 ? "brand" : "ink-mid"} />
        <CountCol label="오늘" value={counts.today} tone="ink" />
        <CountCol label="누적" value={counts.total} tone="ink-mid" />
        <span
          className={cn("ml-1 h-2 w-2 rounded-full", STATE_DOT[agent.state])}
          title={STATE_LABEL[agent.state]}
        />
      </div>

      {/* mobile compact — 오늘만 */}
      <div className="text-right tabular-nums md:hidden">
        <div className="font-display text-body-sm font-semibold text-ink">
          {counts.today}
        </div>
        <div className="font-mono text-[9px] uppercase tracking-wider text-ink-light">
          대기 {counts.waiting}
        </div>
      </div>
    </li>
  );
}

function HilRow({ spec }: { spec: HilSpec }) {
  const Icon = spec.icon;
  return (
    <li className="flex items-center gap-3 rounded-card border-2 border-dashed border-brand/60 bg-brand-light/40 px-3 py-2 md:px-4 md:py-2.5">
      <div className="flex items-center gap-2">
        <span className="hidden font-mono text-[10px] font-semibold uppercase tracking-wider text-brand-text md:inline">
          H-i-L
        </span>
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-brand text-white shadow-sm">
          <Icon className="h-3.5 w-3.5" />
        </span>
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="inline-flex items-center rounded-sm bg-brand px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-white">
            HIL
          </span>
          <span className="font-display text-body-sm font-semibold text-ink">
            {spec.title}
          </span>
          <span className="hidden truncate text-xs text-ink-light md:inline">
            · {spec.description}
          </span>
        </div>
      </div>

      <div className="text-right tabular-nums">
        <div className="font-mono text-[9px] uppercase tracking-wider text-brand-text">
          대기
        </div>
        <div className="font-display text-base font-semibold leading-none text-brand-text">
          {spec.waiting}
        </div>
      </div>
    </li>
  );
}

function Connector() {
  /* 박스 가운데에 짧은 세로선 — 화살표 대신 단순 라인 */
  return (
    <li aria-hidden className="flex h-4 justify-center">
      <span className="block h-full w-px bg-border" />
    </li>
  );
}
