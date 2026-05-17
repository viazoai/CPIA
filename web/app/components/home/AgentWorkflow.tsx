import {
  ChevronDown,
  Inbox,
  FileSearch,
  GitBranch,
  Database,
  FileText,
  Activity,
  Sparkles,
  ClipboardCheck,
  Users,
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

/* mock — 시연용 오늘/누적 분배 (Collector 87 → Optimizer 24 로 점진 감소) */
const COUNTS: Record<number, { today: number; total: number }> = {
  1: { today: 87, total: 1247 },
  2: { today: 87, total: 1247 },
  3: { today: 81, total: 1201 },
  4: { today: 78, total: 1166 },
  5: { today: 78, total: 1166 },
  6: { today: 78, total: 1166 },
  7: { today: 24, total: 824 },
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

/* 2개의 HIL 단계 — step 3 다음(=index after Mapper), step 6 다음(=after Forecaster) */
interface HilSpec {
  no: 1 | 2;
  title: string;
  description: string;
  waiting: number;
  icon: React.ComponentType<{ className?: string }>;
  /** Agent step 다음에 끼움 (3 = Mapper 다음, 6 = Forecaster 다음) */
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
  {
    no: 2,
    afterStep: 6,
    title: "Trade Selection",
    description: "Optimizer 조언을 받을 이상 공종을 PM 이 선택",
    waiting: 1,
    icon: Users,
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
      <div className="mb-6 flex items-baseline justify-between">
        <h2 className="font-display text-h5 text-ink">7-Agent + H-i-L 워크플로우</h2>
        <span className="font-mono text-[11px] uppercase tracking-wider text-ink-light">
          LangGraph · 세로 진행
        </span>
      </div>

      <ol className="flex flex-col">{blocks}</ol>
    </div>
  );
}

/* ============================================================== */

function AgentRow({ agent }: { agent: AgentStatus }) {
  const Icon = STEP_ICON[agent.step] ?? Sparkles;
  const counts = COUNTS[agent.step];
  return (
    <li className="flex items-center gap-4 rounded-card border border-border-soft bg-surface-soft/40 p-4 transition-colors hover:bg-surface-soft md:p-5">
      {/* Left — STEP badge + icon */}
      <div className="flex items-center gap-3">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-card text-ink-mid shadow-xs">
          <Icon className="h-4 w-4" />
        </span>
        <div className="hidden font-mono text-[10px] font-semibold uppercase tracking-wider text-ink-light md:block">
          STEP
          <br />
          <span className="text-base text-ink">{String(agent.step).padStart(2, "0")}</span>
        </div>
      </div>

      {/* Middle — name + description */}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="font-display text-h6 text-ink">{agent.name}</span>
          <span className="text-body-sm text-ink-mid">{agent.korean_name}</span>
        </div>
        <p className="mt-0.5 truncate text-body-sm text-ink-mid">{agent.description}</p>
        <span className="mt-1 inline-block font-mono text-[10px] uppercase tracking-wider text-ink-light">
          {agent.model}
        </span>
      </div>

      {/* Right — today / total counts + state dot */}
      <div className="hidden items-center gap-6 md:flex">
        <div className="text-right">
          <div className="font-mono text-[10px] uppercase tracking-wider text-ink-light">오늘</div>
          <div className="font-display text-h5 text-ink">{counts.today}</div>
        </div>
        <div className="text-right">
          <div className="font-mono text-[10px] uppercase tracking-wider text-ink-light">누적</div>
          <div className="font-display text-h5 text-ink-mid">{counts.total.toLocaleString()}</div>
        </div>
        <div className="flex flex-col items-center gap-1">
          <span className={cn("h-2 w-2 rounded-full", STATE_DOT[agent.state])} />
          <span className="font-mono text-[9px] uppercase tracking-wider text-ink-light">
            {STATE_LABEL[agent.state]}
          </span>
        </div>
      </div>

      {/* mobile compact counts */}
      <div className="text-right md:hidden">
        <div className="font-display text-h5 text-ink">{counts.today}</div>
        <div className="font-mono text-[9px] uppercase tracking-wider text-ink-light">
          / {counts.total.toLocaleString()}
        </div>
      </div>
    </li>
  );
}

function HilRow({ spec }: { spec: HilSpec }) {
  const Icon = spec.icon;
  return (
    <li className="flex items-center gap-4 rounded-card border-2 border-dashed border-lavender/60 bg-lavender-light/40 p-4 md:p-5">
      <div className="flex items-center gap-3">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-lavender text-white shadow-sm">
          <Icon className="h-4 w-4" />
        </span>
        <div className="hidden font-mono text-[10px] font-semibold uppercase tracking-wider text-lavender-text md:block">
          H-i-L
          <br />
          <span className="text-base">{`0${spec.no}`}</span>
        </div>
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center rounded-sm bg-lavender px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-white">
            HIL
          </span>
          <span className="font-display text-h6 text-ink">{spec.title}</span>
        </div>
        <p className="mt-0.5 truncate text-body-sm text-ink-mid">{spec.description}</p>
      </div>

      <div className="text-right">
        <div className="font-mono text-[10px] uppercase tracking-wider text-lavender-text">대기</div>
        <div className="font-display text-h5 text-lavender-text">{spec.waiting}</div>
      </div>
    </li>
  );
}

function Connector() {
  return (
    <li
      aria-hidden
      className="relative my-1 flex h-8 justify-start pl-[19px] md:pl-5"
    >
      <span className="block h-full w-px border-l-2 border-dashed border-border" />
      <span className="absolute -bottom-1.5 left-3 inline-flex items-center justify-center md:left-[13px]">
        <ChevronDown className="h-3.5 w-3.5 text-ink-light" />
      </span>
    </li>
  );
}
