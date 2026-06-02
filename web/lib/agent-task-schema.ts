// 단계(Agent)별 카드 컬럼 정의 — 단일 source. 진단(Forecaster/Optimizer)은 컬럼이 아니라
// 상태칩(statusTone/statusLabel)으로 표시하므로 데이터 컬럼에 포함하지 않는다.
// Parser 는 데이터 유무로 컬럼이 달라져 route 가 PARSER_COLUMNS_FULL/AGG 중 골라 응답에 담는다.
import type { AgentColumn } from "@/lib/types";

export const PARSER_COLUMNS_FULL: AgentColumn[] = [
  { key: "trade", label: "공종" },
  { key: "company", label: "업체명" },
  { key: "category", label: "카테고리" },
  { key: "count", label: "건수", align: "right", mono: true },
];

export const PARSER_COLUMNS_AGG: AgentColumn[] = [
  { key: "trade", label: "공종" },
  { key: "company", label: "업체명" },
  { key: "count", label: "활동건수", align: "right", mono: true },
];

export const AGENT_COLUMNS: Record<string, AgentColumn[]> = {
  Collector: [
    { key: "trade", label: "공종" },
    { key: "company", label: "업체명" },
    { key: "file", label: "파일명" },
  ],
  Parser: PARSER_COLUMNS_AGG, // 기본값(시드). route 가 full 일 때 override.
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
    { key: "wbs", label: "WBS" },
    { key: "work", label: "작업내용" },
    { key: "cond", label: "조건" },
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
  ],
  Optimizer: [
    { key: "warea", label: "Work Area", mono: true },
    { key: "wbs", label: "WBS" },
    { key: "company", label: "업체명" },
    { key: "delay", label: "지연일", align: "right", mono: true },
    { key: "recover", label: "단축가능일", align: "right", mono: true },
  ],
};

const STATUS_HEADER: Record<string, string> = {
  Forecaster: "진단",
  Optimizer: "진단",
  "Human Review": "검토",
};

export function statusHeaderFor(agent: string | null): string {
  if (!agent) return "상태";
  return STATUS_HEADER[agent] ?? "상태";
}
