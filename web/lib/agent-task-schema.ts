// 단계(Agent)별 "단계별 건 목록" 카드 컬럼 정의 — 단일 source.
// 설계 근거: docs/superpowers/specs/2026-06-01-cpia-agent-tasks-step-schema-design.md
//
// 여기 정의한 컬럼 key 는 API 라우트(/api/runs/items, /api/mock/agent-tasks/[date])가
// 채우는 AgentTaskRow.values 의 키와 1:1 이어야 한다. 상태(상태/검토)는 별도 status 칩으로
// 항상 마지막에 렌더되므로 컬럼 목록에는 포함하지 않는다.
import type { AgentColumn } from "@/lib/types";

export const AGENT_COLUMNS: Record<string, AgentColumn[]> = {
  Collector: [
    { key: "trade", label: "공종" },
    { key: "company", label: "업체명" },
    { key: "file", label: "파일명" },
  ],
  Parser: [
    { key: "trade", label: "공종" },
    { key: "company", label: "업체명" },
    { key: "category", label: "카테고리" },
    { key: "count", label: "건수", align: "right", mono: true },
  ],
  Mapper: [
    { key: "trade", label: "공종" },
    { key: "company", label: "업체명" },
    { key: "work", label: "작업내용" },
    { key: "wbs", label: "WBS" },
  ],
  "Human Review": [
    { key: "trade", label: "공종" },
    { key: "company", label: "업체명" },
    { key: "work", label: "작업내용" },
    { key: "wbs", label: "WBS" },
    { key: "conf", label: "확신도", align: "right", mono: true },
  ],
  Atomizer: [
    { key: "trade", label: "공종" },
    { key: "company", label: "업체명" },
    { key: "work", label: "작업내용" },
    { key: "activity", label: "작업사항" },
  ],
  Exporter: [
    { key: "date", label: "일자", mono: true },
    { key: "report", label: "통합 작업일보" },
    { key: "count", label: "활동 건수", align: "right", mono: true },
  ],
  Forecaster: [
    { key: "warea", label: "Work Area", mono: true },
    { key: "wbs", label: "WBS" },
    { key: "company", label: "업체명" },
    { key: "delay", label: "지연일", align: "right", mono: true },
    { key: "diag", label: "진단" },
  ],
  Optimizer: [
    { key: "warea", label: "Work Area", mono: true },
    { key: "wbs", label: "WBS" },
    { key: "company", label: "업체명" },
    { key: "delay", label: "지연일", align: "right", mono: true },
    { key: "recover", label: "단축가능일", align: "right", mono: true },
    { key: "diag", label: "진단" },
  ],
};

// 상태 칩 라벨 — 단계별 기본값(라우트가 row.statusLabel 로 덮어쓸 수 있음).
export const STATUS_HEADER: Record<string, string> = {
  "Human Review": "검토",
};
export function statusHeaderFor(agent: string | null): string {
  if (!agent) return "상태";
  return STATUS_HEADER[agent] ?? "상태";
}
