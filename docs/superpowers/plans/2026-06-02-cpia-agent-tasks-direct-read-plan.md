# CPIA Agent Tasks 단계별 카드 — 실 테이블 직독 + 데이터 유무 분기 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/tasks` 맨 오른쪽 "단계별 건 목록" 카드를 8단계 가변 컬럼으로 되살리되, 데이터는 각 단계 실 출력 테이블에서 직독하고 Collector/Parser는 데이터 유무로 자동 분기한다.

**Architecture:** e632e55에서 유실된 가변 컬럼 골격(`AgentColumn`/`AgentTaskRow`)을 되살린다. e632e55는 컬럼을 FE가 `AGENT_COLUMNS` 정적 import했으나, Parser 분기로 컬럼이 동적이므로 **API가 `columns`를 함께 반환**하고 FE는 props로 받는다. 순수 변환 로직(단축가능일·진단 톤·Parser 분기 판정)은 `lib/agent-task-rows.ts`로 분리해 vitest 단위 테스트한다. 모든 작업은 `web/`(B_Track) 한정, pipeline 변경 없음.

**Tech Stack:** Next.js 14 App Router, TypeScript, vitest + @testing-library/react (jsdom — `web/vitest.config.ts` 이미 존재), PostgreSQL(porsager `postgres` via `@/lib/pg` — jsonb를 자동 파싱해 **객체/배열로 반환**, 문자열 아님), Playwright(e2e 수동 검증).

**Spec:** `docs/superpowers/specs/2026-06-02-cpia-agent-tasks-direct-read-design.md`

---

## 확정된 설계 결정 (스펙의 애매점 → 명확화)

이 플랜을 짜면서 확정한 것들. 구현 중 재논의 금지.

1. **컬럼 전달 경로** — API(`/api/runs/items`, `/api/mock/agent-tasks/[date]`)가 응답에 `columns: AgentColumn[]`를 포함한다. FE `AgentTaskItemList`는 `columns`를 **props로 받는다**(정적 `AGENT_COLUMNS` import 제거). `AGENT_COLUMNS`는 server route에서만 참조.
2. **진단 표시 = 상태칩** — Forecaster/Optimizer는 진단(`risk_level`)을 **상태칩**으로 표시한다(`statusTone`=`risk`/`caution`/`normal`, `statusLabel`=`이상`/`주의`/`정상`). 진단을 별도 데이터 컬럼에 넣지 않는다. `statusHeaderFor`가 Forecaster/Optimizer에서 "진단"을 반환. → Forecaster 데이터 컬럼 4개(WA·WBS·업체·지연일), Optimizer 5개(+단축가능일).
3. **단축가능일** — `recoveryRepDays(dist)`: `recovery_distribution`에서 `d+N` 키 중 카운트 최다 N(동률 시 작은 N) → `"D+N"`, `d+N` 키 없으면 `"—"`.
4. **Parser 분기** — `parserMode(counts)`: 시트1/2/3 부속 합계 > 0 → `"full"`(공종·업체·카테고리·건수), 0 → `"agg"`(공종·업체·활동건수). 부분 채움이면 full 유지, 빈 카테고리는 건수 0.
5. **Exporter 활동건수** = `pipeline_runs.atomized_count` (atomizer가 적재한 doc 수. mapper 행수 아님).
6. **Atomizer 단위** = `mapper_activities` 활동 행 중 `l6_main IS NOT NULL` (atomizer valid 조건과 동일). 작업내용=`parser_activities.work_content` JOIN, 조건=`mapper_activities.conditions`(jsonb 배열 → comma-join).
7. **Human Review** — `requires_review=true` 우선 정렬, 없으면 전체를 `검토완료`(done)로 표시. 빈 카드 아님.
8. **정렬** = `AgentItemTone` 기반 `TONE_SORT`(processing<received<hil_pending<blocked<risk<caution<done<normal). 구 `STATUS_SORT` 제거.
9. **구 `AgentTaskItem` 완전 제거** — 5개 파일에서 신 타입으로 전환.

---

## 파일 구조

| 파일 | 책임 | 작업 |
|---|---|---|
| `web/lib/types.ts` | 타입 정의 | 수정: `AgentColumn`/`AgentTaskRow`/`AgentItemTone` 추가, `AgentTaskItem` 제거 |
| `web/lib/agent-task-rows.ts` | 순수 변환 헬퍼 (테스트 대상) | 신규: `recoveryRepDays`·`toneFromRisk`·`parserMode`·`condText`·`TONE_SORT`·`sortRows` |
| `web/lib/agent-task-schema.ts` | 단계별 컬럼 정의 단일 source | 신규: `AGENT_COLUMNS`·`PARSER_COLUMNS_FULL/AGG`·`statusHeaderFor` |
| `web/app/api/runs/items/route.ts` | 실 DB → `{columns, items}` | 수정(재작성): 8단계 분기 직독 |
| `web/app/api/mock/agent-tasks/[date]/route.ts` | mock → `{columns, items}` shape 동기 | 수정 |
| `web/app/components/tasks/AgentTaskItemList.tsx` | 가변 컬럼 렌더 | 수정: `columns` props |
| `web/app/(app)/tasks/page.tsx` | 데이터 배선 | 수정: `columns`/`rows` 전달 |
| `web/tests/agent-task-rows.test.ts` | 헬퍼 단위 테스트 | 신규 |
| `web/tests/agent-task-schema.test.ts` | 컬럼 정의 테스트 | 신규 |

작업 디렉토리: 모든 명령은 `cd "/Users/kyungseoplee/Project Agent/CPIA/web"` 기준. 테스트: `npx vitest run <path>`.

---

## Task 1: 타입 정의 (`web/lib/types.ts`)

**Files:**
- Modify: `web/lib/types.ts` (구 `AgentTaskItem` 인터페이스 제거, 신 타입 추가)

- [ ] **Step 1: 구 `AgentTaskItem` 제거 + 신 타입 추가**

`web/lib/types.ts`의 `export interface AgentTaskItem { ... }` 블록(현재 ~96-101행)을 통째로 아래로 교체:

```ts
// 단계(Agent)별 카드는 행 단위·컬럼이 다르다 (파일/업체/활동/WP) — 고정 4필드 대신
// per-step 컬럼 정의(AgentColumn) + generic row(AgentTaskRow). 컬럼 단일 source:
// lib/agent-task-schema.ts. 컬럼은 API 응답(columns)으로 전달된다.
export type AgentItemTone =
  | "done" | "processing" | "received" | "hil_pending" | "blocked"  // 처리 상태
  | "normal" | "caution" | "risk";                                  // 진단 톤

export interface AgentColumn {
  key: string;                 // row.values 의 키
  label: string;               // 헤더 표시명
  align?: "left" | "right";
  mono?: boolean;
}

export interface AgentTaskRow {
  id: string;
  values: Record<string, string>;  // column.key → 표시값
  statusLabel: string;
  statusTone: AgentItemTone;
}
```

- [ ] **Step 2: 타입 컴파일 확인**

Run: `npx tsc --noEmit 2>&1 | head -30`
Expected: `AgentTaskItem` 참조하던 4개 파일(route.ts·mock route·AgentTaskItemList.tsx·page.tsx)에서 에러 발생(다음 Task들에서 해소). `types.ts` 자체 문법 에러는 없어야 함.

- [ ] **Step 3: Commit**

```bash
git add web/lib/types.ts
git commit -m "feat(tasks): AgentColumn/AgentTaskRow/AgentItemTone 타입 추가, 구 AgentTaskItem 제거"
```

---

## Task 2: 순수 변환 헬퍼 (`web/lib/agent-task-rows.ts`) — TDD

**Files:**
- Create: `web/lib/agent-task-rows.ts`
- Test: `web/tests/agent-task-rows.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

`web/tests/agent-task-rows.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { recoveryRepDays, toneFromRisk, parserMode, condText, sortRows } from "@/lib/agent-task-rows";
import type { AgentTaskRow } from "@/lib/types";

describe("recoveryRepDays", () => {
  it("d+N 최다 카운트의 N 을 D+N 으로", () => {
    expect(recoveryRepDays({ "d+1": 3, not_recovered: 2 })).toBe("D+1");
    expect(recoveryRepDays({ "d+2": 3, "d+1": 1 })).toBe("D+2");
  });
  it("동률이면 작은 N", () => {
    expect(recoveryRepDays({ "d+1": 1, "d+2": 1 })).toBe("D+1");
  });
  it("d+N 키 없으면 — (전부 미회복)", () => {
    expect(recoveryRepDays({ not_recovered: 5 })).toBe("—");
  });
  it("null/빈 객체 → —", () => {
    expect(recoveryRepDays(null)).toBe("—");
    expect(recoveryRepDays({})).toBe("—");
  });
});

describe("toneFromRisk", () => {
  it("이상→risk, 주의→caution, 그외→normal", () => {
    expect(toneFromRisk("이상")).toBe("risk");
    expect(toneFromRisk("주의")).toBe("caution");
    expect(toneFromRisk("정상")).toBe("normal");
    expect(toneFromRisk(null)).toBe("normal");
  });
});

describe("parserMode", () => {
  it("부속 합>0 → full, 0 → agg", () => {
    expect(parserMode({ content: 0, job: 0, equip: 0 })).toBe("agg");
    expect(parserMode({ content: 5, job: 0, equip: 0 })).toBe("full");
    expect(parserMode({ content: 0, job: 12, equip: 3 })).toBe("full");
  });
});

describe("condText", () => {
  it("jsonb 배열을 comma-join, 빈값은 정상", () => {
    expect(condText(["자재미입고"])).toBe("자재미입고");
    expect(condText(["정상"])).toBe("정상");
    expect(condText([])).toBe("정상");
    expect(condText(null)).toBe("정상");
  });
});

describe("sortRows", () => {
  it("미처리/위험 먼저, normal 마지막", () => {
    const mk = (tone: AgentTaskRow["statusTone"], id: string): AgentTaskRow =>
      ({ id, values: {}, statusLabel: "", statusTone: tone });
    const out = sortRows([mk("normal", "a"), mk("risk", "b"), mk("hil_pending", "c")]);
    expect(out.map((r) => r.id)).toEqual(["b", "c", "a"]);
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `npx vitest run tests/agent-task-rows.test.ts`
Expected: FAIL — `Failed to resolve import "@/lib/agent-task-rows"`.

- [ ] **Step 3: 헬퍼 구현**

`web/lib/agent-task-rows.ts`:

```ts
import type { AgentItemTone, AgentTaskRow } from "@/lib/types";

/** recovery_distribution(JSONB) → 대표 단축일 "D+N". d+N 키 중 카운트 최다(동률 시 작은 N).
 *  d+N 키가 없으면(전부 미회복) "—". */
export function recoveryRepDays(dist: Record<string, number> | null | undefined): string {
  if (!dist) return "—";
  let bestN = Infinity;
  let bestCount = -1;
  for (const [k, v] of Object.entries(dist)) {
    const m = /^d\+(\d+)$/.exec(k);
    if (!m) continue; // not_recovered 등 제외
    const n = Number(m[1]);
    const c = Number(v) || 0;
    if (c > bestCount || (c === bestCount && n < bestN)) {
      bestCount = c;
      bestN = n;
    }
  }
  return bestCount < 0 ? "—" : `D+${bestN}`;
}

/** forecasts.risk_level("정상|주의|이상") → 진단 톤. */
export function toneFromRisk(risk: string | null | undefined): AgentItemTone {
  return risk === "이상" ? "risk" : risk === "주의" ? "caution" : "normal";
}

/** 시트1/2/3 부속 건수 합 > 0 이면 풀 파싱 run(full), 0 이면 적재 시드(agg). */
export function parserMode(counts: { content: number; job: number; equip: number }): "full" | "agg" {
  return counts.content + counts.job + counts.equip > 0 ? "full" : "agg";
}

/** mapper_activities.conditions(jsonb 배열) → 표시 문자열. 빈값은 "정상". */
export function condText(conds: string[] | null | undefined): string {
  if (!conds || conds.length === 0) return "정상";
  return conds.join(", ");
}

const TONE_SORT: Record<AgentItemTone, number> = {
  processing: 0, received: 1, hil_pending: 2, blocked: 3,
  risk: 4, caution: 5, done: 6, normal: 7,
};

export function sortRows(rows: AgentTaskRow[]): AgentTaskRow[] {
  return [...rows].sort((a, b) => (TONE_SORT[a.statusTone] ?? 9) - (TONE_SORT[b.statusTone] ?? 9));
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `npx vitest run tests/agent-task-rows.test.ts`
Expected: PASS (5 describe 블록 전부 green).

- [ ] **Step 5: Commit**

```bash
git add web/lib/agent-task-rows.ts web/tests/agent-task-rows.test.ts
git commit -m "feat(tasks): agent-task-rows 변환 헬퍼 + 단위 테스트 (recoveryRepDays/toneFromRisk/parserMode/condText/sortRows)"
```

---

## Task 3: 컬럼 정의 (`web/lib/agent-task-schema.ts`) — TDD

**Files:**
- Create: `web/lib/agent-task-schema.ts`
- Test: `web/tests/agent-task-schema.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

`web/tests/agent-task-schema.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { AGENT_COLUMNS, PARSER_COLUMNS_FULL, PARSER_COLUMNS_AGG, statusHeaderFor } from "@/lib/agent-task-schema";

describe("AGENT_COLUMNS", () => {
  it("8단계 키가 모두 존재", () => {
    for (const a of ["Collector", "Mapper", "Human Review", "Atomizer", "Exporter", "Forecaster", "Optimizer"]) {
      expect(AGENT_COLUMNS[a], a).toBeDefined();
    }
  });
  it("Forecaster 데이터 컬럼 4개(WA·WBS·업체·지연일, 진단은 상태칩)", () => {
    expect(AGENT_COLUMNS.Forecaster.map((c) => c.key)).toEqual(["warea", "wbs", "company", "delay"]);
  });
  it("Optimizer 데이터 컬럼 5개(+단축가능일)", () => {
    expect(AGENT_COLUMNS.Optimizer.map((c) => c.key)).toEqual(["warea", "wbs", "company", "delay", "recover"]);
  });
  it("Atomizer 에 조건 컬럼", () => {
    expect(AGENT_COLUMNS.Atomizer.map((c) => c.key)).toContain("cond");
  });
});

describe("PARSER 변형", () => {
  it("FULL=카테고리·건수, AGG=활동건수", () => {
    expect(PARSER_COLUMNS_FULL.map((c) => c.key)).toEqual(["trade", "company", "category", "count"]);
    expect(PARSER_COLUMNS_AGG.map((c) => c.key)).toEqual(["trade", "company", "count"]);
  });
});

describe("statusHeaderFor", () => {
  it("Forecaster/Optimizer=진단, Human Review=검토, 기타=상태", () => {
    expect(statusHeaderFor("Forecaster")).toBe("진단");
    expect(statusHeaderFor("Optimizer")).toBe("진단");
    expect(statusHeaderFor("Human Review")).toBe("검토");
    expect(statusHeaderFor("Mapper")).toBe("상태");
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `npx vitest run tests/agent-task-schema.test.ts`
Expected: FAIL — import 해소 실패.

- [ ] **Step 3: 구현**

`web/lib/agent-task-schema.ts`:

```ts
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `npx vitest run tests/agent-task-schema.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/lib/agent-task-schema.ts web/tests/agent-task-schema.test.ts
git commit -m "feat(tasks): AGENT_COLUMNS 8단계 + Parser FULL/AGG 변형 + statusHeaderFor"
```

---

## Task 4: API 직독 (`web/app/api/runs/items/route.ts`) — 재작성

응답 형태를 `{ ok, agent, columns, items }`로 바꾸고 8단계를 실 테이블에서 직독한다. 변환은 Task 2 헬퍼 사용. DB 의존이라 단위 테스트 대신 Task 8 라이브 검증으로 확인한다(헬퍼는 Task 2에서 이미 커버).

**Files:**
- Modify(재작성): `web/app/api/runs/items/route.ts`

- [ ] **Step 1: route.ts 재작성**

상단 import/상수:
```ts
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

import fs from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import type { AgentColumn, AgentTaskRow } from "@/lib/types";
import { AGENT_COLUMNS, PARSER_COLUMNS_FULL, PARSER_COLUMNS_AGG, statusHeaderFor } from "@/lib/agent-task-schema";
import { recoveryRepDays, toneFromRisk, parserMode, condText, sortRows } from "@/lib/agent-task-rows";

const DATA_DIR = process.env.DATA_DIR ?? path.join(process.cwd(), "data");

function fmtDelay(d: number | null | undefined): string {
  if (d == null) return "—";
  const n = Math.round(Number(d));
  return n > 0 ? `+${n}일` : `${n}일`;
}
```

GET 핸들러 — `run_id`/`agent` 파라미터 검증은 기존과 동일(없으면 400). 그 다음 단계별 분기:

```ts
let rows: AgentTaskRow[] = [];
let columns: AgentColumn[] = AGENT_COLUMNS[agent] ?? [];

if (agent === "Collector") {
  const runRows = (await (sql as any)`
    SELECT TO_CHAR(report_date,'YYYYMMDD') AS d FROM pipeline_runs WHERE run_id=${runId} LIMIT 1`) as Array<{ d: string }>;
  const dateCompact = runRows[0]?.d ?? "";
  const tradeRows = (await (sql as any)`
    SELECT company, MAX(trade) AS trade FROM parser_activities WHERE run_id=${runId} GROUP BY company`) as Array<{ company: string; trade: string | null }>;
  // 디스크 파일 우선, 없으면 업체목록 폴백
  let files: string[] = [];
  if (dateCompact) {
    const all = await fs.readdir(path.join(DATA_DIR, "input", dateCompact)).catch(() => [] as string[]);
    files = all.filter((f) => /\.(xlsx|xlsm)$/i.test(f));
  }
  if (files.length > 0) {
    rows = files.map((f, i) => {
      const matched = tradeRows.find((r) => r.company && f.includes(r.company));
      return {
        id: String(i + 1).padStart(3, "0"),
        values: { trade: matched?.trade ?? (/통합/.test(f) ? "전체" : "—"), company: matched?.company ?? f.split("_")[0], file: f },
        statusLabel: "수집완료", statusTone: "done",
      };
    });
  } else {
    rows = tradeRows.map((r, i) => ({
      id: String(i + 1).padStart(3, "0"),
      values: { trade: r.trade ?? "—", company: r.company, file: `${r.company} 작업일보` },
      statusLabel: "수집완료", statusTone: "done",
    }));
  }
}

else if (agent === "Parser") {
  const [qty, job, equip, content] = (await Promise.all([
    (sql as any)`SELECT company, COUNT(*)::int c, MAX(trade) trade FROM parser_activities WHERE run_id=${runId} GROUP BY company`,
    (sql as any)`SELECT company, COUNT(*)::int c FROM parser_job_allocations WHERE run_id=${runId} GROUP BY company`,
    (sql as any)`SELECT company, COUNT(*)::int c FROM parser_equipment_allocations WHERE run_id=${runId} GROUP BY company`,
    (sql as any)`SELECT e->>'company' company, COUNT(*)::int c FROM parser_reports pr, jsonb_array_elements(pr.bp_summaries) e WHERE pr.run_id=${runId} GROUP BY 1`,
  ])) as Array<Array<{ company: string; c: number; trade?: string | null }>>;
  const totals = {
    content: content.reduce((s, r) => s + r.c, 0),
    job: job.reduce((s, r) => s + r.c, 0),
    equip: equip.reduce((s, r) => s + r.c, 0),
  };
  const tradeBy = new Map(qty.map((r) => [r.company, r.trade ?? "—"]));
  if (parserMode(totals) === "agg") {
    columns = PARSER_COLUMNS_AGG;
    rows = qty.map((r, i) => ({
      id: String(i + 1).padStart(3, "0"),
      values: { trade: r.trade ?? "—", company: r.company, count: String(r.c) },
      statusLabel: "파싱완료", statusTone: "done",
    }));
  } else {
    columns = PARSER_COLUMNS_FULL;
    const cnt = (arr: Array<{ company: string; c: number }>, co: string) => arr.find((r) => r.company === co)?.c ?? 0;
    const companies = Array.from(new Set([...qty, ...job, ...equip, ...content].map((r) => r.company).filter(Boolean)));
    const CATS: Array<[string, (co: string) => number]> = [
      ["작업내용(시트1)", (co) => cnt(content, co)],
      ["인원(시트2)", (co) => cnt(job, co)],
      ["장비(시트3)", (co) => cnt(equip, co)],
      ["물량(시트4)", (co) => cnt(qty, co)],
    ];
    rows = companies.flatMap((co) =>
      CATS.map(([label, getc], i) => ({
        id: `${co}-${i}`,
        values: { trade: tradeBy.get(co) ?? "—", company: co, category: label, count: String(getc(co)) },
        statusLabel: "파싱완료", statusTone: "done" as const,
      })),
    );
  }
}

else if (agent === "Mapper") {
  const r = (await (sql as any)`
    SELECT ma.idx, COALESCE(ma.l5_disc, ma.trade) trade, ma.company, pa.work_content, ma.l6_main
    FROM mapper_activities ma LEFT JOIN parser_activities pa ON pa.run_id=ma.run_id AND pa.idx=ma.idx
    WHERE ma.run_id=${runId} ORDER BY ma.idx`) as Array<any>;
  rows = r.map((a) => ({
    id: String(a.idx).padStart(3, "0"),
    values: { trade: a.trade ?? "—", company: a.company, work: a.work_content ?? "—", wbs: a.l6_main ?? "(미매핑)" },
    statusLabel: a.l6_main != null ? "매핑완료" : "검토필요",
    statusTone: a.l6_main != null ? "done" : "hil_pending",
  }));
}

else if (agent === "Human Review") {
  const r = (await (sql as any)`
    SELECT ma.idx, COALESCE(ma.l5_disc, ma.trade) trade, ma.company, pa.work_content, ma.l6_main, ma.mapping_conf, ma.requires_review
    FROM mapper_activities ma LEFT JOIN parser_activities pa ON pa.run_id=ma.run_id AND pa.idx=ma.idx
    WHERE ma.run_id=${runId} ORDER BY ma.requires_review DESC, ma.mapping_conf ASC NULLS FIRST, ma.idx`) as Array<any>;
  rows = r.map((a) => ({
    id: String(a.idx).padStart(3, "0"),
    values: {
      trade: a.trade ?? "—", company: a.company, work: a.work_content ?? "—",
      wbs: a.l6_main ?? "(대안 검토)",
      conf: a.mapping_conf != null ? `${Math.round(Number(a.mapping_conf) * 100)}%` : "—",
    },
    statusLabel: a.requires_review ? "검토대기" : "검토완료",
    statusTone: a.requires_review ? "hil_pending" : "done",
  }));
}

else if (agent === "Atomizer") {
  const r = (await (sql as any)`
    SELECT ma.idx, COALESCE(ma.l5_disc, ma.trade) trade, ma.company, ma.l6_main, ma.conditions, pa.work_content
    FROM mapper_activities ma LEFT JOIN parser_activities pa ON pa.run_id=ma.run_id AND pa.idx=ma.idx
    WHERE ma.run_id=${runId} AND ma.l6_main IS NOT NULL ORDER BY ma.idx`) as Array<any>;
  rows = r.map((a) => ({
    id: String(a.idx).padStart(3, "0"),
    values: {
      trade: a.trade ?? "—", company: a.company, wbs: a.l6_main ?? "—",
      work: a.work_content ?? "—", cond: condText(a.conditions),
    },
    statusLabel: "적재완료", statusTone: "done",
  }));
}

else if (agent === "Exporter") {
  const r = (await (sql as any)`
    SELECT TO_CHAR(report_date,'YYYY-MM-DD') d, COALESCE(atomized_count,0) cnt
    FROM pipeline_runs WHERE run_id=${runId} LIMIT 1`) as Array<{ d: string; cnt: number }>;
  if (r[0]) rows = [{ id: "001", values: { date: r[0].d, report: "통합 작업일보", count: String(r[0].cnt) }, statusLabel: "생성완료", statusTone: "done" }];
}

else if (agent === "Forecaster") {
  const r = (await (sql as any)`
    SELECT wa, l6_main, company, delay_days, risk_level FROM forecasts WHERE run_id=${runId}
    ORDER BY (risk_level='이상') DESC, (risk_level='주의') DESC, delay_days DESC NULLS LAST`) as Array<any>;
  rows = r.map((f, i) => ({
    id: String(i + 1).padStart(3, "0"),
    values: { warea: f.wa ?? "—", wbs: f.l6_main ?? "—", company: f.company ?? "—", delay: fmtDelay(f.delay_days) },
    statusLabel: f.risk_level ?? "—", statusTone: toneFromRisk(f.risk_level),
  }));
}

else if (agent === "Optimizer") {
  const r = (await (sql as any)`
    SELECT oa.company, oa.l6_main, oa.recovery_distribution, f.wa, f.delay_days, f.risk_level
    FROM optimizer_advice oa
    LEFT JOIN forecasts f ON f.run_id=oa.run_id AND f.company=oa.company AND f.l6_main=oa.l6_main
    WHERE oa.run_id=${runId}
    ORDER BY (f.risk_level='이상') DESC, (f.risk_level='주의') DESC, oa.l6_main`) as Array<any>;
  rows = r.map((o, i) => ({
    id: String(i + 1).padStart(3, "0"),
    values: {
      warea: o.wa ?? "—", wbs: o.l6_main ?? "—", company: o.company ?? "—",
      delay: fmtDelay(o.delay_days), recover: recoveryRepDays(o.recovery_distribution),
    },
    statusLabel: o.risk_level ?? "—", statusTone: toneFromRisk(o.risk_level),
  }));
}

return NextResponse.json({ ok: true, agent, columns, items: sortRows(rows) });
```
> 주의: `recovery_distribution`은 asyncpg가 jsonb를 객체로 반환하는지 문자열로 반환하는지 `@/lib/pg` 구현에 따라 다르다. 문자열이면 `JSON.parse` 필요 — Step 2에서 실제 응답으로 확인하고, 객체가 아니면 `recoveryRepDays(typeof o.recovery_distribution === "string" ? JSON.parse(o.recovery_distribution) : o.recovery_distribution)`로 보정. `conditions`도 동일하게 확인.

- [ ] **Step 2: 타입 컴파일 + 실 응답 확인 (jsonb 파싱 검증)**

Run:
```bash
npx tsc --noEmit 2>&1 | grep "runs/items" || echo "route.ts 타입 OK"
# dev 서버(5537)가 떠 있는 상태에서 실 run 으로 jsonb 반환형 확인
RID=f57e8ae0-3f76-00c2-3047-c2abc8da3dd8
curl -s "http://localhost:5537/api/runs/items?run_id=$RID&agent=Optimizer" | head -c 600
# Parser FULL 분기는 09-24 시드(부속 0)에선 발현 안 됨 → FULL SQL 테이블/컬럼명 오타만이라도 검증(빈 결과·무에러 확인):
URL=$(grep '^POSTGRES_URL=' web/.env.local | cut -d= -f2- | tr -d '"')
Z=00000000-0000-0000-0000-000000000000
psql "$URL" -c "SELECT company,COUNT(*) FROM parser_job_allocations WHERE run_id='$Z' GROUP BY company" >/dev/null && echo "job SQL OK"
psql "$URL" -c "SELECT company,COUNT(*) FROM parser_equipment_allocations WHERE run_id='$Z' GROUP BY company" >/dev/null && echo "equip SQL OK"
psql "$URL" -c "SELECT e->>'company',COUNT(*) FROM parser_reports pr, jsonb_array_elements(pr.bp_summaries) e WHERE pr.run_id='$Z' GROUP BY 1" >/dev/null && echo "content SQL OK"
```
Expected: `{"ok":true,"agent":"Optimizer","columns":[...],"items":[{"id":"001","values":{"warea":...,"recover":"D+1" 또는 "—"},...}]}`. `recover`가 `"[object Object]"`나 빈값이면 jsonb 파싱 보정(위 주의) 적용 후 재확인. 그리고 `job/equip/content SQL OK` 3줄 출력(FULL 분기 SQL 오타 없음 — 첫 실 파싱 run 전에 미리 검증).

- [ ] **Step 3: Commit**

```bash
git add web/app/api/runs/items/route.ts
git commit -m "feat(tasks): runs/items 8단계 실 테이블 직독 + columns 반환 + Collector/Parser 데이터 유무 분기"
```

---

## Task 5: 가변 컬럼 렌더 (`AgentTaskItemList.tsx`)

e632e55 버전을 되살리되 `columns`를 정적 import 대신 **props로 받는다**.

**Files:**
- Modify: `web/app/components/tasks/AgentTaskItemList.tsx`

- [ ] **Step 1: 컴포넌트 교체**

`web/app/components/tasks/AgentTaskItemList.tsx` 전체를 교체 — e632e55 버전 기반, 단 `Props`에 `columns` 추가하고 `AGENT_COLUMNS` import 제거, `statusHeaderFor`만 유지:

```tsx
"use client";
import { cn } from "@/lib/utils";
import { CheckCircle2, Loader2, Inbox, Pause, AlertOctagon } from "lucide-react";
import type { AgentColumn, AgentTaskRow, AgentItemTone, AgentStageProgress } from "@/lib/types";
import { statusHeaderFor } from "@/lib/agent-task-schema";

interface Props {
  selectedAgent: string | null;
  stage: AgentStageProgress | null;
  columns: AgentColumn[];
  rows: AgentTaskRow[];
}

const TONE_META: Record<AgentItemTone, { cls: string; Icon: React.ComponentType<{ className?: string }> }> = {
  done:        { cls: "text-mint-text bg-mint-light",   Icon: CheckCircle2 },
  processing:  { cls: "text-sky-text bg-sky-light",     Icon: Loader2 },
  received:    { cls: "text-ink-mid bg-surface-soft",   Icon: Inbox },
  hil_pending: { cls: "text-brand-text bg-brand-light", Icon: Pause },
  blocked:     { cls: "text-rose-text bg-rose-light",   Icon: AlertOctagon },
  normal:      { cls: "text-mint-text bg-mint-light",   Icon: CheckCircle2 },
  caution:     { cls: "text-sun-text bg-sun-light",     Icon: Pause },
  risk:        { cls: "text-rose-text bg-rose-light",   Icon: AlertOctagon },
};

export function AgentTaskItemList({ selectedAgent, stage, columns, rows }: Props) {
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
          <div className="flex h-full items-center justify-center text-body-sm text-ink-light">단계 미선택</div>
        )}
        {selectedAgent && rows.length === 0 && (
          <div className="flex h-full items-center justify-center text-body-sm text-ink-light">해당 단계에 표시할 건이 없습니다</div>
        )}
        {selectedAgent && rows.length > 0 && (
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface-soft/80 backdrop-blur text-[11px] text-ink-mid">
              <tr className="border-b border-border-soft">
                {columns.map((col) => (
                  <th key={col.key} className={cn("px-3 py-1.5 font-medium", col.align === "right" ? "text-right" : "text-left", col.mono && "font-mono")}>
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
                      <td key={col.key} className={cn("px-3 py-1 text-[12px]", col.align === "right" ? "text-right" : "text-left", col.mono && "font-mono", ci === 0 ? "text-ink" : "text-ink-mid")}>
                        {row.values[col.key] ?? "—"}
                      </td>
                    ))}
                    <td className="px-3 py-1 text-right">
                      <span className={cn("inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[10px] font-semibold", meta.cls)}>
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
```

- [ ] **Step 2: 렌더 테스트 (@testing-library/react)**

`web/tests/agent-task-item-list.test.tsx`:
```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentTaskItemList } from "@/app/components/tasks/AgentTaskItemList";

describe("AgentTaskItemList", () => {
  it("columns props 로 동적 헤더 + values 렌더, Forecaster 상태헤더=진단", () => {
    render(
      <AgentTaskItemList
        selectedAgent="Forecaster"
        stage={{ step: 6, agent: "Forecaster", is_hil: false, received: 1, processed: 1, percent: 100, waiting_hil: false }}
        columns={[{ key: "warea", label: "Work Area" }, { key: "wbs", label: "WBS" }]}
        rows={[{ id: "001", values: { warea: "FAB", wbs: "C/R 조성공사" }, statusLabel: "이상", statusTone: "risk" }]}
      />
    );
    expect(screen.getByText("Work Area")).toBeDefined();
    expect(screen.getByText("진단")).toBeDefined();      // statusHeader
    expect(screen.getByText("C/R 조성공사")).toBeDefined();
    expect(screen.getByText("이상")).toBeDefined();        // statusLabel
  });
});
```
> `web/vitest.config.ts`가 **이미 존재**한다(jsdom + `@vitejs/plugin-react` + `@` alias + `setupFiles: ["./vitest.setup.ts"]`). 그대로 쓰고 **새로 생성·수정 금지**(덮어쓰면 기존 통과 테스트 회귀). jsdom·@testing-library/react·@vitejs/plugin-react 모두 devDependencies에 설치돼 있어 추가 불필요. 단 `vitest.setup.ts`가 `@/lib/pg`를 전역 mock하므로 **route를 import하는 테스트는 피한다**(본 헬퍼·컴포넌트 테스트는 pg 비의존이라 무관).

Run: `npx vitest run tests/agent-task-item-list.test.tsx`
Expected: PASS (환경 보완 후).

- [ ] **Step 3: Commit**

```bash
git add web/app/components/tasks/AgentTaskItemList.tsx web/tests/agent-task-item-list.test.tsx
git commit -m "feat(tasks): AgentTaskItemList 가변 컬럼 렌더 (columns props) + 렌더 테스트"
```

---

## Task 6: mock route + page.tsx 배선

**Files:**
- Modify: `web/app/api/mock/agent-tasks/[date]/route.ts`
- Modify: `web/app/(app)/tasks/page.tsx`

- [ ] **Step 1: mock route를 `{columns, items}` shape로**

`web/app/api/mock/agent-tasks/[date]/route.ts`가 반환하는 `items: Record<agent, ...>`를 신 shape로 바꾼다. `DetailData`가 `{ stages, items: Record<string, {columns: AgentColumn[]; rows: AgentTaskRow[]}> }` 형태가 되도록 한다. 구 `AgentTaskItem` import 제거.

**구체 타겟:** 각 agent → `{ columns: AGENT_COLUMNS[agent] ?? [], rows: AgentTaskRow[] }` (Parser는 `PARSER_COLUMNS_AGG`). 현재 mock route(`app/api/mock/agent-tasks/[date]/route.ts:57-75`)는 Mapper/Parser만 실 데이터로 채우고 나머지 6개 agent는 빈 배열이다 — 그 구조를 유지하되 형식만: 채우던 agent(Mapper/Parser)는 `rows`를 runs/items route와 같은 키(Mapper `{trade,company,work,wbs}`, Parser AGG `{trade,company,count}`)로 만들고, 안 채우던 6개는 `{ columns: AGENT_COLUMNS[agent] ?? [], rows: [] }`. mock은 DB progress 없을 때의 fallback 경로이므로 데이터 완전성보다 **shape 정합**이 목적(빈 rows여도 카드가 "표시할 건이 없습니다"로 정상 렌더).

- [ ] **Step 2: page.tsx — columns/rows 배선**

`web/app/(app)/tasks/page.tsx`:
- import: `AgentTaskItem` → `AgentColumn, AgentTaskRow`.
- `DetailData.items` 타입을 `Record<string, { columns: AgentColumn[]; rows: AgentTaskRow[] }>`로.
- `dbItems` state를 `{ columns: AgentColumn[]; rows: AgentTaskRow[] }`로(기본 `{columns:[],rows:[]}`). `/api/runs/items` 응답에서 `columns`/`items` 둘 다 받아 저장. **주의: `setDbItems([])` 호출부가 현재 4곳(~line 65·171·186 등)에 흩어져 있으니 `grep -n "setDbItems(" "app/(app)/tasks/page.tsx"`로 전수 찾아 모두 `setDbItems({ columns: [], rows: [] })`로 교체**(안 하면 TS 타입 에러).
- `itemsForAgent`를 `rowsForAgent`/`columnsForAgent`로 분리:
  ```ts
  const rowsForAgent: AgentTaskRow[] = hasProgress ? dbItems.rows
    : selectedAgent ? (detail?.items ?? {})[selectedAgent]?.rows ?? [] : [];
  const columnsForAgent: AgentColumn[] = hasProgress ? dbItems.columns
    : selectedAgent ? (detail?.items ?? {})[selectedAgent]?.columns ?? [] : [];
  ```
- `<AgentTaskItemList selectedAgent={selectedAgent} stage={selectedStage} columns={columnsForAgent} rows={rowsForAgent} />`.

- [ ] **Step 3: 빌드 검증**

Run: `npx tsc --noEmit 2>&1 | grep -E "page.tsx|mock/agent-tasks|AgentTaskItem" || echo "타입 OK"`
Expected: `AgentTaskItem` 잔존 참조 0, 타입 에러 0.

- [ ] **Step 4: Commit**

```bash
git add web/app/api/mock/agent-tasks/[date]/route.ts "web/app/(app)/tasks/page.tsx"
git commit -m "feat(tasks): mock route + tasks page 를 columns/rows shape 로 배선"
```

---

## Task 7: 구 `AgentTaskItem` 잔재 제거 + 풀 빌드

**Files:**
- 전역 확인

- [ ] **Step 1: 잔재 grep**

Run: `grep -rn "AgentTaskItem" web/ --include="*.ts" --include="*.tsx" | grep -v node_modules | grep -v ".next"`
Expected: 출력 없음(0건). 남으면 해당 파일 신 타입으로 정리.

- [ ] **Step 2: 풀 타입체크 + 빌드 + 단위테스트**

Run:
```bash
npx tsc --noEmit && echo "TSC OK"
npx vitest run tests/agent-task-rows.test.ts tests/agent-task-schema.test.ts tests/agent-task-item-list.test.tsx
npm run build 2>&1 | tail -15
```
Expected: TSC OK, vitest 전부 PASS, `npm run build` 성공(✓ Compiled).

- [ ] **Step 3: Commit**

```bash
git add -A web/
git commit -m "chore(tasks): AgentTaskItem 잔재 제거 확인 + 빌드 통과"
```

---

## Task 8: 라이브 e2e 검증 (09-24 실 run, Playwright)

DB·dev 서버 의존이라 자동 단위테스트로 못 잡는 통합 동작을 실제 화면으로 검증한다.

**Files:** 없음(검증 전용)

- [ ] **Step 1: dev 서버 확인**

Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:5537/tasks`
Expected: `200`. 아니면 `cd web && npm run dev2` 로 기동.

- [ ] **Step 2: 8단계 API 직독 실값 대조**

Run:
```bash
RID=f57e8ae0-3f76-00c2-3047-c2abc8da3dd8; B=http://localhost:5537
for A in Collector Parser Mapper "Human Review" Atomizer Exporter Forecaster Optimizer; do
  echo "== $A =="; curl -s "$B/api/runs/items?run_id=$RID&agent=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote('$A'))")" | python3 -c "import sys,json;d=json.load(sys.stdin);print('cols',[c['key'] for c in d.get('columns',[])]);print('n',len(d.get('items',[])));[print(' ',i['values'],i['statusLabel']) for i in d.get('items',[])[:2]]"
done
```
Expected (스펙 §3·§8과 일치):
- Collector: cols `[trade,company,file]`, 20건, `선보 작업일보`.
- Parser: cols `[trade,company,count]`(agg 분기), 20건, 선보 48.
- Mapper: `[trade,company,work,wbs]`, 171건.
- Human Review: 171건, statusLabel `검토완료`(09-24 요검토 0).
- Atomizer: `[trade,company,wbs,work,cond]`, cond=`정상`/`자재미입고`.
- Exporter: 1건, count=171.
- Forecaster: `[warea,wbs,company,delay]`, statusLabel `이상`/`주의`/`정상`, 상위 `FAB·C/R 조성공사·해광·+195일·이상`.
- Optimizer: `[warea,wbs,company,delay,recover]`, recover=`D+1` 또는 `—`.

- [ ] **Step 3: Playwright 화면 캡처 (Playwright MCP)**

`/tasks` → 좌측 09-24 선택 → 중앙 Workflow에서 단계별 클릭하며 우측 카드 스크린샷. 확인: 가변 헤더(단계마다 컬럼 다름), Forecaster/Optimizer 상태칩이 진단 색(이상=빨강), Optimizer 단축가능일 `D+N`/`—`. (브라우저 점유 시 Step 2 API 대조로 갈음하고 그 사실을 보고)

- [ ] **Step 4: 최종 보고**

검증 3요소(명령/원본 출력/결론)로 8단계 전부 보고. 통과 시에만 "완료". `npm run build`(시연 5535/5537 prod 반영)는 사용자 지시 시 `make build`.

---

## 스코프 밖 (이 플랜에서 하지 않음)
- reports 화면과의 진단 SSOT 일원화(`wp_summary.status`) — 별도 작업.
- `wp_summary`가 실 prod run에서 비는 근본 원인(`parser.py:445`) — A_Track.
- pipeline(A_Track) 코드 변경.
- Parser FULL 분기 라이브 e2e — 현 DB에 부속 채워진 run 없음(Task 2/3 단위테스트로 커버, 첫 실 파싱 run 시 재확인).
