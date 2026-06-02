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
  // percent 또는 처리건수 어느 쪽으로든 완료 판정 (사람 단계는 percent 없이 처리=접수로 완료)
  if (s.percent >= 100) return "done";
  if (s.received > 0 && s.processed >= s.received) return "done";
  if (s.percent === -1 || (s.percent > 0 && s.percent < 100)) return "active";
  if (s.received > 0 && s.processed > 0) return "active";
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

  // 진행 프런티어 — active/done(=non-pending) 인 가장 마지막 단계 인덱스.
  // 이 인덱스 이하로 이어지는 라인은 "통과됨"으로 보고 초록 채움.
  // (사람 단계가 자체 건수를 0 으로 남겨도 뒷 단계가 시작되면 자동으로 라인이 채워짐)
  const frontierIdx = stages.reduce((m, s, i) => (stageState(s) !== "pending" ? i : m), -1);
  // 단계 완료 여부 — 프런티어보다 앞이거나, 프런티어 자신이 자체적으로 done.
  // 이걸로 "에이전트가 끝난 순간" 그 아래 라인이 (다음 단계 시작 전에) 초록으로 차오른다.
  const doneAt = (j: number) =>
    j < frontierIdx || (j === frontierIdx && stageState(stages[j]) === "done");

  return (
    <div className="flex flex-col h-full">
      {/* ── 헤더 ── */}
      <div className="px-4 py-2.5 border-b border-border-soft shrink-0">
        <div className="font-display text-h6 font-bold text-ink">Agent Workflow</div>
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
          // 노드 상태 — 프런티어 기준으로 통일 (HIL 이 percent·processed 를 0 으로 남겨도
          // 뒤 단계가 시작되면 "통과=완료"로 잡힘). 대기 단계는 회색.
          const ownState = stageState(s);
          const isActive = i === frontierIdx && ownState === "active";
          const isDone = i < frontierIdx || (i === frontierIdx && ownState === "done");
          const isPending = i > frontierIdx;

          // 연결선 — 노드 중앙 기준 위/아래 세그먼트로 분리해 끊김 없는 스파인.
          // 색: 통과한(완료) 노드 쪽이 mint. 사람(HIL) 노드에 인접한 세그먼트는 점선(수동 핸드오프).
          const prev = stages[i - 1];
          const next = stages[i + 1];
          // 라인 채움: "이전/이 단계가 완료된 순간" 채워짐 (다음 단계 시작을 기다리지 않음).
          const segAboveDone = i > 0 && doneAt(i - 1); // 이전 단계 완료 → 위(진입) 라인 채움
          const segAboveDashed = isHil || (!!prev && prev.is_hil);
          const segBelowDone = doneAt(i); // 이 단계 완료 → 아래(진출) 라인 채움
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

          return (
            <li key={s.agent} className="relative flex flex-1 gap-3">
              {/* ── 왼쪽 레일: 끊김 없는 스파인 + 세로 중앙 정렬된 메달리온 노드 ── */}
              <div className="relative flex w-11 shrink-0 items-center justify-center">
                {/* 위 세그먼트 — 컨테이너 top → 노드 상단(중앙-22px) */}
                {!isFirst && <RailSegment pos="above" dashed={segAboveDashed} done={segAboveDone} />}
                {/* 아래 세그먼트 — 노드 하단(중앙+22px) → 다음 노드 상단 */}
                {!isLast && <RailSegment pos="below" dashed={segBelowDashed} done={segBelowDone} />}

                {/* 메달리온 노드 — 카드 높이 기준 세로 중앙 */}
                <div className="relative z-10">
                  {/* 진행중 = 노드 안쪽 채워진 색이 천천히 점등(밝기 깜빡임)으로 작업중 표기.
                      에이전트=초록 / 사람=주황 */}
                  <span
                    className={cn(
                      "relative inline-flex h-11 w-11 items-center justify-center shadow-sm transition-all",
                      isHil
                        // 사람 단계 = 원형. 진행중(검토중)=주황 점등 / 완료=주황 / 대기=회색 외곽선
                        ? cn(
                            "rounded-full",
                            isActive
                              ? "bg-peach text-white shadow-md animate-node-lit"
                              : isDone
                                ? "bg-peach text-white"
                                : "border border-border-soft bg-surface-soft text-ink-light",
                          )
                        // 에이전트 = 둥근 사각. 진행중=초록 점등 / 완료=초록 / 대기=회색 외곽선
                        : cn(
                            "rounded-2xl",
                            isActive
                              ? "bg-mint text-white shadow-md animate-node-lit"
                              : isDone
                                ? "bg-mint text-white"
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
                        ? "border border-border-soft bg-mint-light"
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
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/**
 * 레일 연결선 세그먼트 — 노드 중앙 기준 위/아래 절반.
 *   기본은 회색, done 되면 초록(mint) 채움이 위→아래로 흐르는 애니메이션.
 *   사람 단계 인접 구간(dashed)은 점선 핸드오프 — 색만 전환.
 */
function RailSegment({ pos, dashed, done }: { pos: "above" | "below"; dashed: boolean; done: boolean }) {
  const posCls =
    pos === "above" ? "top-0 bottom-[calc(50%+22px)]" : "top-[calc(50%+22px)] bottom-0";
  if (dashed) {
    return (
      <span
        aria-hidden
        className={cn(
          "absolute left-1/2 -translate-x-1/2 border-l-2 border-dashed transition-colors duration-500",
          posCls,
          done ? "border-mint" : "border-border",
        )}
      />
    );
  }
  return (
    <span
      aria-hidden
      className={cn("absolute left-1/2 w-[3px] -translate-x-1/2 overflow-hidden rounded-full bg-border", posCls)}
    >
      {/* 초록 채움 — done 시 height 0→100% 로 흘러내림 */}
      <span
        className={cn(
          "absolute inset-x-0 top-0 rounded-full bg-mint transition-[height] duration-700 ease-out",
          done ? "h-full" : "h-0",
        )}
      />
    </span>
  );
}

