"use client";
import {
  Inbox,
  FileSearch,
  GitBranch,
  Database,
  FileText,
  Activity,
  Sparkles,
  UserCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentStageProgress } from "@/lib/types";

interface Props {
  stages: AgentStageProgress[];
  selectedAgent: string | null;
  onSelect: (agent: string) => void;
}

const STEP_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  Collector: Inbox,
  Parser: FileSearch,
  Mapper: GitBranch,
  "Human Review": UserCheck, // 사람 단계 — 사람 아이콘으로 구분
  Atomizer: Database,
  Exporter: FileText,
  Forecaster: Activity,
  Optimizer: Sparkles,
};

const KOREAN: Record<string, string> = {
  Collector: "수집",
  Parser: "파싱",
  Mapper: "매핑",
  "Human Review": "사람 검토",
  Atomizer: "적재",
  Exporter: "출력",
  Forecaster: "진단",
  Optimizer: "조언",
};

/* Home 화면(AgentWorkflow.tsx)과 동일 description — fixtures.ts AGENT_META 출처. */
const DESCRIPTION: Record<string, string> = {
  Collector: "작업일보 자동 수집",
  Parser: "엑셀 → 구조화 JSON",
  Mapper: "WBS 매핑 + 확신도 산출",
  "Human Review": "확신도 낮은 WBS 매핑 항목을 담당자가 검토·수정",
  Atomizer: "Vector DB 적재",
  Exporter: "통합 작업일보 생성",
  Forecaster: "생산성 진단",
  Optimizer: "회복 조언",
};

/** 단계 상태 — 레일 색·노드 모양을 결정. */
type StageState = "done" | "active" | "pending";
function stageState(s: AgentStageProgress): StageState {
  if (s.waiting_hil) return "active";
  if (s.percent >= 100) return "done";
  if (s.percent === -1 || (s.percent > 0 && s.percent < 100)) return "active";
  return "pending";
}

export function AgentWorkflowList({ stages, selectedAgent, onSelect }: Props) {
  // 현재 작업중 단계 — HIL 대기 우선 → 첫 미완 단계 → 모두 완료면 마지막 단계
  const waitingStage = stages.find((s) => s.waiting_hil);
  const inflightStage = stages.find((s) => s.received > 0 && s.percent < 100 && !s.waiting_hil);
  const allDone = stages.length > 0 && stages.every((s) => s.percent === 100 && !s.waiting_hil);
  const currentStage = waitingStage ?? inflightStage ?? (allDone ? stages[stages.length - 1] : null);

  let statusLabel = "대기 없음";
  if (waitingStage) statusLabel = "검토 대기중";
  else if (inflightStage) statusLabel = "처리중";
  else if (allDone) statusLabel = "전 단계 완료";

  return (
    <div className="flex flex-col h-full">
      {/* ── 헤더 + 범례 ── */}
      <div className="px-4 py-2.5 border-b border-border-soft shrink-0">
        <div className="flex items-baseline justify-between gap-2">
          <div className="font-display text-h6 font-bold text-ink">Agent Workflow</div>
          <div className="flex items-center gap-2.5 text-[10px] text-ink-light">
            <Legend dotClass="bg-mint" label="완료" />
            <Legend dotClass="bg-brand" label="진행" ping />
            <Legend dotClass="bg-card border border-border" label="대기" />
            <span className="inline-flex items-center gap-1">
              <span className="inline-flex h-2.5 w-2.5 items-center justify-center rounded-full bg-peach text-white">
                <UserCheck className="h-1.5 w-1.5" />
              </span>
              사람
            </span>
          </div>
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-ink-mid tabular-nums">
          <span>현재 단계 {currentStage ? currentStage.agent : "—"}</span>
          <span>·</span>
          <span>상태 {statusLabel}</span>
        </div>
      </div>

      {/* ── 세로 레일 타임라인 — 행을 동일 높이 밴드로 펴서 해상도에 따라 간격 분배 ── */}
      <ol className="flex flex-1 min-h-0 flex-col overflow-y-auto px-3 py-2">
        {stages.map((s, i) => {
          const Icon = STEP_ICON[s.agent] ?? Sparkles;
          const isHil = s.is_hil;
          const selected = selectedAgent === s.agent;
          const isLast = i === stages.length - 1;
          const isFirst = i === 0;
          const state = stageState(s);
          const isDone = state === "done";
          const isActive = state === "active";
          const isPending = state === "pending";

          // 연결선 — 노드 중앙 기준 위/아래 세그먼트로 분리해 끊김 없는 스파인.
          // 색: 통과한(완료) 노드 쪽이 mint. 사람(HIL) 노드에 인접한 세그먼트는 점선(수동 핸드오프).
          const prev = stages[i - 1];
          const next = stages[i + 1];
          const segAboveDone = !!prev && stageState(prev) === "done";
          const segAboveDashed = isHil || (!!prev && prev.is_hil);
          const segBelowDone = isDone;
          const segBelowDashed = isHil || (!!next && next.is_hil);

          // 우측 백분율 라벨
          const pctLabel = s.waiting_hil
            ? "검토 대기"
            : s.percent === -1
              ? "처리중"
              : isPending
                ? "대기"
                : `${s.percent}%`;
          const pctTone = s.waiting_hil
            ? "text-sun-text"
            : isDone
              ? "text-mint-text"
              : isActive
                ? "text-brand-text"
                : "text-ink-light";

          // 진행 막대 폭 — -1(진행중·미상)은 보조 애니메이션.
          const barPct = s.percent === -1 ? 40 : Math.max(0, s.percent);

          return (
            <li key={s.agent} className="relative flex flex-1 gap-3">
              {/* ── 왼쪽 레일: 끊김 없는 스파인 + 세로 중앙 정렬된 메달리온 노드 ── */}
              <div className="relative flex w-11 shrink-0 items-center justify-center">
                {/* 위 세그먼트 — 컨테이너 top → 노드 상단(중앙-22px) */}
                {!isFirst &&
                  (segAboveDashed ? (
                    <span
                      aria-hidden
                      className={cn(
                        "absolute left-1/2 top-0 bottom-[calc(50%+22px)] -translate-x-1/2 border-l-2 border-dashed",
                        segAboveDone ? "border-mint/70" : "border-peach/50",
                      )}
                    />
                  ) : (
                    <span
                      aria-hidden
                      className={cn(
                        "absolute left-1/2 top-0 bottom-[calc(50%+22px)] w-[3px] -translate-x-1/2 rounded-full",
                        segAboveDone ? "bg-mint" : "bg-border",
                      )}
                    />
                  ))}

                {/* 아래 세그먼트 — 노드 하단(중앙+22px) → 다음 노드 상단(pb 만큼 연장) */}
                {!isLast &&
                  (segBelowDashed ? (
                    <span
                      aria-hidden
                      className={cn(
                        "absolute left-1/2 top-[calc(50%+22px)] bottom-0 -translate-x-1/2 border-l-2 border-dashed",
                        segBelowDone ? "border-mint/70" : "border-peach/50",
                      )}
                    />
                  ) : (
                    <span
                      aria-hidden
                      className={cn(
                        "absolute left-1/2 top-[calc(50%+22px)] bottom-0 w-[3px] -translate-x-1/2 rounded-full",
                        segBelowDone ? "bg-mint" : "bg-border",
                      )}
                    />
                  ))}

                {/* 메달리온 노드 — 카드 높이 기준 세로 중앙 */}
                <div className="relative z-10">
                  {/* 진행중 펄스 링 */}
                  {isActive && (
                    <span
                      aria-hidden
                      className={cn(
                        "absolute inset-0 animate-ping",
                        isHil ? "rounded-full bg-peach/40" : "rounded-2xl bg-brand/40",
                      )}
                    />
                  )}
                  <span
                    className={cn(
                      "relative inline-flex h-11 w-11 items-center justify-center shadow-sm transition-all",
                      isHil
                        // 사람 단계 = 항상 주황 원형 (상태 무관 — 사람임을 표기)
                        ? cn("rounded-full bg-peach text-white", s.waiting_hil && "shadow-md ring-2 ring-peach/30")
                        // 에이전트 = 둥근 사각, 상태별 색
                        : cn(
                            "rounded-2xl",
                            isDone
                              ? "bg-mint text-white"
                              : isActive
                                ? "bg-brand text-white shadow-md ring-2 ring-brand/30"
                                : "border border-border-soft bg-surface-soft text-ink-light",
                          ),
                    )}
                  >
                    <Icon className="h-5 w-5" />
                  </span>
                </div>
              </div>

              {/* ── 오른쪽 카드 ── */}
              <button
                type="button"
                onClick={() => onSelect(s.agent)}
                className={cn(
                  "min-w-0 flex-1 self-center rounded-card px-3 py-2.5 text-left transition-all",
                  isHil
                    // 사람 단계 = 박스 제거 (테두리·배경 없음), 선택 시 옅은 주황 틴트만
                    ? selected
                      ? "bg-peach-light/50"
                      : "hover:bg-peach-light/30"
                    : selected
                      ? "border border-brand bg-brand-light ring-2 ring-brand/40 shadow-sm"
                      : isActive
                        ? "border border-brand/40 bg-brand-light/30 hover:bg-brand-light/50"
                        : "border border-border-soft bg-surface-soft/40 hover:bg-surface-soft",
                )}
              >
                {/* eyebrow: 사람 검토 단계 칩 (HIL 만) */}
                {isHil && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-peach/15 px-2.5 py-1 font-mono text-xs font-bold uppercase tracking-wider text-peach-text">
                    <UserCheck className="h-3.5 w-3.5" />
                    Human Review
                  </span>
                )}

                {/* 헤더 한 줄: 좌 = 이름 + 설명(인라인) / 우 = 접수·처리·진행률 */}
                <div className={cn("flex items-baseline justify-between gap-2", isHil && "mt-1")}>
                  {/* 좌: 이름(에이전트만) + 설명 — 사람 단계는 칩이 이름 역할 */}
                  <div className="flex items-baseline gap-1.5 min-w-0">
                    {!isHil && (
                      <span className="shrink-0 font-display text-body-sm font-semibold text-ink">
                        {s.agent}
                      </span>
                    )}
                    {DESCRIPTION[s.agent] && (
                      <span className="text-[11px] text-ink-light truncate">
                        {DESCRIPTION[s.agent]}
                      </span>
                    )}
                  </div>
                  {/* 우: 사람 단계 = 확인 건수만 / 에이전트 = 접수·처리 + 진행률 */}
                  <div className="flex items-center gap-2 shrink-0 tabular-nums">
                    {isHil ? (
                      <span className="font-mono text-xs text-peach-text">
                        확인 <span className="font-bold">{s.received}</span>건
                      </span>
                    ) : (
                      <>
                        {s.received > 0 && (
                          <span className="font-mono text-[10px] text-ink-light">
                            접수 <span className="font-semibold text-ink">{s.received}</span>
                            {" · "}처리 <span className="font-semibold text-ink">{s.processed}</span>
                          </span>
                        )}
                        <span className={cn("font-mono text-[11px] font-bold", pctTone)}>{pctLabel}</span>
                      </>
                    )}
                  </div>
                </div>

                {/* 진행 막대 — 사람 단계는 게이지 없음 */}
                {!isHil && (
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-card">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        isDone ? "bg-mint" : "bg-brand",
                        s.percent === -1 && "animate-pulse",
                      )}
                      style={{ width: `${barPct}%` }}
                    />
                  </div>
                )}
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** 헤더 범례 점 */
function Legend({ dotClass, label, ping }: { dotClass: string; label: string; ping?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="relative inline-flex h-2.5 w-2.5">
        {ping && <span className={cn("absolute inset-0 animate-ping rounded-full", dotClass, "opacity-40")} />}
        <span className={cn("relative inline-flex h-2.5 w-2.5 rounded-full", dotClass)} />
      </span>
      {label}
    </span>
  );
}
