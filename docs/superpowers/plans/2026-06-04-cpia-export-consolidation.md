# CPIA Export 통합작업일보 정합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export(통합 작업일보) 화면·xlsx 에서 시드일(9/13~24) 시트1을 최종 적재 데이터(mapper_activities)로 재구성해 노출하고, 시트1/2/3 "BP사" 컬럼을 업체명으로 정합하며, 시트1 작업사항 셀 포맷을 통일한다.

**Architecture:** 시트 조립 로직을 순수 함수(`web/lib/consolidated-transforms.ts`, 그리고 `exporter.py` 헬퍼)로 추출해 단위테스트하고, route.ts·exporter.py 는 "bp_summaries 있으면 parser 데이터, 없으면 mapper per-company 재구성" 폴백을 호출한다. 시트2(직종)/시트3(장비)는 시드일 원천이 없어 빈 유지, 시트4(물량)는 현행 유지.

**Tech Stack:** Next.js 14 API Route(TypeScript) + vitest, Python LangGraph(`pipeline/agents/exporter.py`, openpyxl/asyncpg) + pytest, PostgreSQL `43.200.85.209:5532/cpia`.

**Spec:** `docs/superpowers/specs/2026-06-04-cpia-export-consolidation-design.md`

**확정된 사실(실 DB 측정, 재확인 불요):**
- 시드일 시트1 그레인 = per-company. 9/24 mapper = 20개사(전부 `trade IN ('건축','토목')`, 필터 무해), 9/25 bp_summaries = 7개사.
- 업체별 distinct work_content ≤ 3 (대부분 2) → `line-clamp-3` 정합, 폭주 없음.
- company→wa 최빈 매핑 가용(companyWa 재사용).
- 시트1 탭 라벨 = "1. 작업사항". 탭 배지 카운트 = 상세 route 반환 배열 길이(재구성 후 자동 정합).
- 9/25 bp_summaries 에는 `company`(광건)·`bp_code`(PH_X-070) 둘 다, 시드 mapper 는 `company` 만(bp_code 빈값).

---

## File Structure

| 파일 | 책임 | 변경 |
|---|---|---|
| `web/lib/consolidated-transforms.ts` | 시트1 행 빌더 순수 함수(bp_summaries→행, mapper집계→행, BP사 라벨) | **신규** |
| `web/tests/consolidated-transforms.test.ts` | 위 순수 함수 단위테스트 | **신규** |
| `web/app/api/mock/consolidated/route.ts` | 시트1 폴백 배선 + 재구성 쿼리 + 시트2/3 BP사=업체명 | 수정 |
| `web/app/components/export/SheetTable.tsx` | 시트1 작업사항 셀 line-clamp-3 통일 | 수정 |
| `web/tests/consolidated-sheet-cols.test.ts` | 시트1 작업사항 컬럼 cellClass 계약 | **신규** |
| `pipeline/agents/exporter.py` | 재구성 헬퍼 + fetch_sheet_data 배선 + BP사=업체명 | 수정 |
| `pipeline/tests/test_exporter_render.py` | 재구성 헬퍼 + BP사 render 테스트 | 수정 |

**범위 밖:** Report 생산성 12.6% 코드 수정(스펙 §1.6 문서화만), 시트2/3 시드 합성, 9/25 assigned_workers 오염.

---

## Task 0: 브랜치·베이스라인 확인

**Files:** 없음(점검만)

- [ ] **Step 1: 브랜치 확인**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA" && git branch --show-current`
Expected: `feature/review-l75-hil`

- [ ] **Step 2: 작업 트리 상태 확인**

Run: `git status --short`
Expected: 추적 안 된 data/ 등만(커밋된 spec 외 미커밋 소스 없음). 소스 충돌 없으면 진행.

- [ ] **Step 3: 베이스라인 web 테스트 green 확인**

Run: `cd web && npx vitest run 2>&1 | tail -15`
Expected: 전부 pass(이후 회귀 비교 기준).

- [ ] **Step 4: 베이스라인 pytest(exporter) green 확인**

Run: `cd pipeline && .venv/bin/pytest tests/test_exporter_render.py -q 2>&1 | tail -10`
Expected: 전부 pass.

---

## Task 1: web 순수 변환 함수 (consolidated-transforms.ts)

**Files:**
- Create: `web/lib/consolidated-transforms.ts`
- Test: `web/tests/consolidated-transforms.test.ts`

배경: 현재 route.ts 가 시트1 매핑을 인라인(`bp_summaries.map`)하고 `bp_code ?? company`(코드 우선)로 채운다. 이를 순수 함수로 추출 + BP사=업체명(`company ?? bp_code`)으로 바꾸고, 시드 재구성 함수를 추가한다.

- [ ] **Step 1: 실패 테스트 작성**

`web/tests/consolidated-transforms.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import {
  bpLabel,
  outputFromBpSummaries,
  reconstructOutputFromMapper,
  type MapperOutputAgg,
} from "@/lib/consolidated-transforms";

describe("consolidated-transforms", () => {
  it("bpLabel: 업체명 우선, 코드 폴백, 둘 다 없으면 빈문자", () => {
    expect(bpLabel("광건", "PH_X-070")).toBe("광건");
    expect(bpLabel(null, "PH_X-070")).toBe("PH_X-070");
    expect(bpLabel("", "PH_X-070")).toBe("PH_X-070");
    expect(bpLabel(undefined, undefined)).toBe("");
  });

  it("outputFromBpSummaries: 9/25 — BP사=업체명(코드 아님), per-company 유지, zone=companyWa", () => {
    const rows = outputFromBpSummaries(
      [{ company: "광건", bp_code: "PH_X-070", work_text_today: "A\nB", today_incr_total: 796 }],
      { 광건: "FAB" },
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].bp_code).toBe("광건"); // 코드 PH_X-070 아님
    expect(rows[0].zone).toBe("FAB");
    expect(rows[0].today_work).toBe("A\nB");
    expect(rows[0].prev_work).toBe(""); // work_text_yesterday 없으면 빈값
  });

  it("reconstructOutputFromMapper: 시드 — per-company, BP사=업체명, 전일/명일 빈값, day=반올림 인원", () => {
    const agg: MapperOutputAgg[] = [
      { company: "OTIS", trade: "건축", workers_total: 27.3, work_today: "승강로 작업" },
    ];
    const rows = reconstructOutputFromMapper(agg, { OTIS: "FAB" });
    expect(rows[0].bp_code).toBe("OTIS"); // 업체명
    expect(rows[0].zone).toBe("FAB");
    expect(rows[0].trade).toBe("건축");
    expect(rows[0].today_work).toBe("승강로 작업");
    expect(rows[0].main_work).toBe("승강로 작업");
    expect(rows[0].prev_work).toBe("");
    expect(rows[0].next_work).toBe("");
    expect(rows[0].day).toBe(27);
  });

  it("결정성: 동일 입력 2회 동일 출력", () => {
    const agg: MapperOutputAgg[] = [{ company: "A", trade: "토목", workers_total: 5, work_today: "x" }];
    expect(reconstructOutputFromMapper(agg, {})).toEqual(reconstructOutputFromMapper(agg, {}));
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd web && npx vitest run tests/consolidated-transforms.test.ts 2>&1 | tail -15`
Expected: FAIL — `Cannot find module '@/lib/consolidated-transforms'`.

- [ ] **Step 3: 최소 구현**

`web/lib/consolidated-transforms.ts`:

```ts
// 통합 작업일보 시트1(출력인원/작업사항) 행 빌더 — route.ts 에서 호출하는 순수 함수.
// 9/25 실업로드는 parser_reports.bp_summaries, 시드일은 mapper_activities 집계에서 재구성.
import type { OutputManpowerRow } from "@/lib/types";

const PJT = "M15X Ph-3 IBL";

/** "BP사" 컬럼 값 = 업체명 우선, 코드 폴백 (spec D5). 빈문자/0 은 폴백. */
export function bpLabel(company: unknown, bpCode: unknown): string {
  const c = company == null ? "" : String(company);
  if (c !== "") return c;
  return bpCode == null ? "" : String(bpCode);
}

/** 9/25 실업로드: parser_reports.bp_summaries jsonb 원소 → 시트1 행(원소 1개 = 업체 1개). */
export function outputFromBpSummaries(
  bpSummaries: any[],
  companyWa: Record<string, string>,
): OutputManpowerRow[] {
  return bpSummaries.map((s) => ({
    pjt: PJT,
    zone: String(companyWa[s.company] ?? s.zone ?? ""),
    trade: String(s.disc_abbrev ?? ""),
    bp_code: bpLabel(s.company, s.bp_code), // D5: 업체명
    scope: String(s.scope ?? ""),
    main_work: String(s.work_text_today ?? ""),
    prev_work: String(s.work_text_yesterday ?? ""),
    today_work: String(s.work_text_today ?? ""),
    next_work: String(s.work_text_tomorrow ?? ""),
    early: 0,
    day: Number(s.today_incr_total ?? 0),
    overtime: 0,
  }));
}

/** 시드일 mapper per-company 집계 행 (route 의 새 쿼리 결과). */
export interface MapperOutputAgg {
  company: string;
  trade: string | null;
  workers_total: number;
  work_today: string | null;
}

/** 시드일: mapper 집계 → 시트1 행(per-company). 전일/명일 작업텍스트 원천 없어 빈값. */
export function reconstructOutputFromMapper(
  aggRows: MapperOutputAgg[],
  companyWa: Record<string, string>,
): OutputManpowerRow[] {
  return aggRows.map((r) => ({
    pjt: PJT,
    zone: String(companyWa[r.company] ?? ""),
    trade: String(r.trade ?? ""),
    bp_code: bpLabel(r.company, null), // 시드 bp_code 빈값 → 업체명
    scope: "",
    main_work: String(r.work_today ?? ""),
    prev_work: "",
    today_work: String(r.work_today ?? ""),
    next_work: "",
    early: 0,
    day: Math.round(r.workers_total ?? 0),
    overtime: 0,
  }));
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd web && npx vitest run tests/consolidated-transforms.test.ts 2>&1 | tail -15`
Expected: PASS (4 tests).

- [ ] **Step 5: 커밋**

```bash
git add web/lib/consolidated-transforms.ts web/tests/consolidated-transforms.test.ts
git commit -m "feat(export): 시트1 행 빌더 순수함수 추출 + BP사=업체명 + 시드 재구성"
```

---

## Task 2: route.ts — 시트1 폴백 배선 + 시트2/3 BP사=업체명

**Files:**
- Modify: `web/app/api/mock/consolidated/route.ts:182-228`

route 는 `sql` 태그드 템플릿이라 단위테스트 대상이 아님 — Task 1 순수함수 테스트 + Task 6 라이브로 검증. 재구성 쿼리는 실 DB 에서 9/24 = 20행 반환 확인됨.

- [ ] **Step 1: import 추가**

route.ts 상단 import 블록에 추가:

```ts
import {
  outputFromBpSummaries,
  reconstructOutputFromMapper,
  bpLabel,
  type MapperOutputAgg,
} from "@/lib/consolidated-transforms";
```

- [ ] **Step 2: 시트1 — bp_summaries 폴백으로 교체**

현재 `output_manpower` 인라인 매핑(L183-196 `const output_manpower: OutputManpowerRow[] = bp_summaries.map(...)`) 전체를 아래로 교체. (companyWa 계산 블록 L164-180 다음, quantity 매핑 전.)

```ts
  // 시트1 — bp_summaries 있으면 그대로(BP사=업체명), 없으면(시드일) mapper per-company 재구성.
  let output_manpower: OutputManpowerRow[];
  if (bp_summaries.length > 0) {
    output_manpower = outputFromBpSummaries(bp_summaries, companyWa);
  } else {
    const outAgg = (await (sql as any)`
      SELECT ma.company,
             MAX(ma.trade)                                       AS trade,
             SUM(COALESCE(ma.assigned_workers, 0))::float        AS workers_total,
             string_agg(DISTINCT NULLIF(pa.work_content, ''), E'\n') AS work_today
      FROM mapper_activities ma
      LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
      WHERE ma.report_date = ${date}
        AND ma.is_mock = ${useMock}
        AND ma.trade IN ('건축', '토목')
      GROUP BY ma.company
      ORDER BY ma.company
    `) as MapperOutputAgg[];
    output_manpower = reconstructOutputFromMapper(outAgg, companyWa);
  }
```

- [ ] **Step 3: 시트2/3 — BP사=업체명**

시트2 occupation 매핑(L201) `bp_code: String(j.bp_code ?? j.company ?? "")` →
```ts
    bp_code: bpLabel(j.company, j.bp_code),
```
시트3 equipment 매핑(L217) `bp_code: String(e.bp_code ?? e.company ?? "")` →
```ts
    bp_code: bpLabel(e.company, e.bp_code),
```
(시트4 quantity 의 bp_code/bp_name 두 컬럼은 **변경 금지** — 이미 분리돼 있음.)

- [ ] **Step 4: 타입·빌드 검증**

Run: `cd web && npx tsc --noEmit 2>&1 | tail -15`
Expected: 에러 없음(또는 기존과 동일, 신규 에러 0).

- [ ] **Step 5: 커밋**

```bash
git add web/app/api/mock/consolidated/route.ts
git commit -m "feat(export): route 시트1 시드 재구성 폴백 + 시트2/3 BP사=업체명"
```

---

## Task 3: SheetTable.tsx — 시트1 작업사항 셀 포맷 통일

**Files:**
- Modify: `web/app/components/export/SheetTable.tsx:92-94`
- Test: `web/tests/consolidated-sheet-cols.test.ts`

현재 전일=`truncate`, 금일=`whitespace-normal`(\n 무시), 명일=`truncate`. 셋 다 `whitespace-pre-line line-clamp-3`(\n 보존 + 3줄 제한)로 통일.

- [ ] **Step 1: 실패 테스트 작성**

`web/tests/consolidated-sheet-cols.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { OUTPUT_MANPOWER_COLS } from "@/app/components/export/SheetTable";

const cell = (key: string) =>
  OUTPUT_MANPOWER_COLS.find((c) => c.key === key)?.cellClass ?? "";

describe("OUTPUT_MANPOWER_COLS 작업사항 셀 계약", () => {
  it("전일/금일/명일 셋 다 whitespace-pre-line + line-clamp-3, truncate 없음", () => {
    for (const k of ["prev_work", "today_work", "next_work"]) {
      expect(cell(k), `${k} pre-line`).toContain("whitespace-pre-line");
      expect(cell(k), `${k} clamp`).toContain("line-clamp-3");
      expect(cell(k), `${k} no-truncate`).not.toContain("truncate");
    }
  });
  it("BP사 라벨은 그대로(마크업 불변 — 디자인 보존)", () => {
    const bp = OUTPUT_MANPOWER_COLS.find((c) => c.key === "bp_code");
    expect(bp?.label).toBe("BP사");
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd web && npx vitest run tests/consolidated-sheet-cols.test.ts 2>&1 | tail -15`
Expected: FAIL — prev_work cellClass 에 `truncate` 있고 `line-clamp-3` 없음.

- [ ] **Step 3: 최소 구현**

`SheetTable.tsx` `OUTPUT_MANPOWER_COLS`(L92-94) 3줄 교체:

```ts
  { key: "prev_work",  label: "전일 작업사항", cellClass: "max-w-[160px] whitespace-pre-line line-clamp-3" },
  { key: "today_work", label: "금일 작업사항", cellClass: "max-w-[200px] whitespace-pre-line line-clamp-3 text-ink" },
  { key: "next_work",  label: "명일 작업사항", cellClass: "max-w-[160px] whitespace-pre-line line-clamp-3" },
```

(label·다른 컬럼·테이블 구조 불변 — 디자인 불가침. 변경은 cellClass 3개뿐.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd web && npx vitest run tests/consolidated-sheet-cols.test.ts 2>&1 | tail -15`
Expected: PASS (2 tests).

- [ ] **Step 5: 커밋**

```bash
git add web/app/components/export/SheetTable.tsx web/tests/consolidated-sheet-cols.test.ts
git commit -m "feat(export): 시트1 작업사항 전일/금일/명일 셀 line-clamp-3 통일"
```

---

## Task 4: exporter.py — xlsx 시드 재구성 + BP사=업체명

**Files:**
- Modify: `pipeline/agents/exporter.py` (`_reconstruct_output_manpower` 신규, `fetch_sheet_data`, `_fill_output_manpower`/`_fill_occupation`/`_fill_equipment`)
- Test: `pipeline/tests/test_exporter_render.py`

xlsx 다운로드(`/export/run`)도 화면과 동일 정렬. 재구성은 순수 헬퍼로 추출해 DB 없이 테스트.

- [ ] **Step 1: 실패 테스트 작성** (헬퍼 + BP사 render)

`pipeline/tests/test_exporter_render.py` 에 추가:

```python
def test_reconstruct_output_manpower_per_company() -> None:
    from pipeline.agents.exporter import _reconstruct_output_manpower
    agg = [
        {"company": "OTIS", "trade": "건축", "workers_total": 27.3, "work_today": "승강로 작업"},
        {"company": "광건", "trade": "건축", "workers_total": 12.0, "work_today": "면 작업"},
    ]
    out = _reconstruct_output_manpower(agg, {"OTIS": "FAB", "광건": "FAB"})
    assert len(out) == 2
    assert out[0]["company"] == "OTIS"
    assert out[0]["bp_code"] is None              # 시드 빈값 → _fill 에서 company 폴백
    assert out[0]["zone"] == "FAB"
    assert out[0]["disc_abbrev"] == "건축"
    assert out[0]["work_text_today"] == "승강로 작업"
    assert out[0]["work_text_yesterday"] is None
    assert out[0]["workers_today_incr"] == {"total": 27}  # 반올림, total 한 칸


def test_render_xlsx_sheet1_bp_is_company() -> None:
    """시트1 col5(BP사) = 업체명(코드 아님)."""
    from pipeline.agents.exporter import SheetData, render_xlsx, COL_OUTPUT_MANPOWER
    from openpyxl import load_workbook
    from io import BytesIO
    sd = SheetData(
        output_manpower=[{"company": "광건", "bp_code": "PH_X-070", "disc_abbrev": "건축",
                          "work_text_today": "x", "workers_today_incr": {"total": 5}}],
        occupation_manpower=[], equipment=[], quantity=[],
        company_wa={"광건": "FAB"},
    )
    wb = load_workbook(BytesIO(render_xlsx(sd, date(2025, 9, 24), project="M15X")))
    ws = wb["1.출력인원 현황"]
    assert ws.cell(5, COL_OUTPUT_MANPOWER["bp_code"]).value == "광건"  # 코드 아님
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd pipeline && .venv/bin/pytest tests/test_exporter_render.py::test_reconstruct_output_manpower_per_company tests/test_exporter_render.py::test_render_xlsx_sheet1_bp_is_company -v 2>&1 | tail -20`
Expected: FAIL — `_reconstruct_output_manpower` 미정의 + 시트1 col5 가 "PH_X-070"(현재 bp_code 우선).

- [ ] **Step 3: 헬퍼 구현 + BP사 우선순위 변경**

`exporter.py` — `fetch_sheet_data` 위에 헬퍼 추가:

```python
def _reconstruct_output_manpower(agg_rows: list[dict], company_wa: dict) -> list[dict]:
    """시드일(빈 bp_summaries) 시트1 재구성 — mapper per-company 집계 → _fill_output_manpower 호환 dict.
    시드는 전일/명일 작업텍스트·교대 내역 원천이 없어, 투입인원 총합만 today_incr.total 한 칸에 넣는다.
    """
    out: list[dict] = []
    for r in agg_rows:
        out.append({
            "company": r["company"],
            "bp_code": None,  # 시드 빈값 → _fill_output_manpower 가 company 폴백
            "zone": company_wa.get(r["company"]),
            "disc_abbrev": r.get("trade"),
            "scope": None,
            "work_text_today": r.get("work_today"),
            "work_text_yesterday": None,
            "work_text_tomorrow": None,
            "workers_today_incr": {"total": round(r.get("workers_total") or 0)},
        })
    return out
```

`_fill_output_manpower`(L256) BP사 우선순위 — `row.get("bp_code") or row.get("company")` →
```python
        _safe_set(ws, r, C["bp_code"], row.get("company") or row.get("bp_code"))
```
`_fill_occupation`(L272) `row.get("bp_code")` → `row.get("company") or row.get("bp_code")`
`_fill_equipment`(L294) `row.get("bp_code")` → `row.get("company") or row.get("bp_code")`

- [ ] **Step 4: 헬퍼·render 테스트 통과 확인**

Run: `cd pipeline && .venv/bin/pytest tests/test_exporter_render.py::test_reconstruct_output_manpower_per_company tests/test_exporter_render.py::test_render_xlsx_sheet1_bp_is_company -v 2>&1 | tail -20`
Expected: PASS.

- [ ] **Step 5: fetch_sheet_data 배선** (빈 bp_rows → 재구성)

`fetch_sheet_data` 의 `async with pg._pool.acquire() as con:` 블록 안, `wa_rows` 조회 다음에 추가(같은 con 사용):

```python
        out_agg_rows = []
        if not bp_rows:
            out_agg_rows = await con.fetch(
                """
                SELECT ma.company,
                       MAX(ma.trade) AS trade,
                       SUM(COALESCE(ma.assigned_workers, 0))::float AS workers_total,
                       string_agg(DISTINCT NULLIF(pa.work_content, ''), E'\n') AS work_today
                FROM mapper_activities ma
                JOIN pipeline_runs pr USING (run_id)
                LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
                WHERE pr.site_id = $1 AND ma.report_date = $2
                  AND ma.trade IN ('건축', '토목')
                GROUP BY ma.company
                ORDER BY ma.company
                """,
                site_id,
                report_date,
            )
```

`company_wa` 계산 다음, `return SheetData(...)` 의 `output_manpower=` 인자를 교체:
```python
    output_manpower = (
        [_coerce(r) for r in bp_rows]
        if bp_rows
        else _reconstruct_output_manpower([dict(r) for r in out_agg_rows], company_wa)
    )
    return SheetData(
        output_manpower=output_manpower,
        occupation_manpower=[_coerce(r) for r in job_rows],
        equipment=[_coerce(r) for r in eq_rows],
        quantity=[dict(r) for r in act_rows],
        company_wa=company_wa,
    )
```
(NoDataError 가드는 act_rows 가 있어 시드일도 통과 — 변경 없음.)

> **주의(의도된 비대칭):** exporter.py 재구성 쿼리는 `JOIN pipeline_runs ... pr.site_id=$1` 로 site 필터(멀티사이트 파이프라인), route.ts 쿼리는 `report_date`+`is_mock` 만(단일사이트 데모). 두 쿼리를 억지로 동일화하지 말 것. `E'\n'` 은 SQL 문자열 이스케이프로 그대로 유지(JS 보간 아님).

- [ ] **Step 6: 전체 exporter 테스트 green**

Run: `cd pipeline && .venv/bin/pytest tests/test_exporter_render.py -q 2>&1 | tail -10`
Expected: 전부 pass(기존 + 신규 2).

- [ ] **Step 7: 커밋**

```bash
git add pipeline/agents/exporter.py pipeline/tests/test_exporter_render.py
git commit -m "feat(export): xlsx 시드 시트1 mapper 재구성 + BP사=업체명(시트1/2/3)"
```

---

## Task 5: 전체 회귀 테스트

**Files:** 없음

- [ ] **Step 1: web 전체 vitest**

Run: `cd web && npx vitest run 2>&1 | tail -20`
Expected: 전부 pass(Task 0 베이스라인 대비 신규 실패 0).

- [ ] **Step 2: pipeline exporter 관련 테스트**

Run: `cd pipeline && .venv/bin/pytest tests/test_exporter_render.py tests/test_exporter_node.py tests/test_exporter_wa_source.py tests/test_db_consolidated_reports.py -q 2>&1 | tail -15`
Expected: 전부 pass.

---

## Task 6: 라이브 UI 검증

**Files:** 없음(실행·관찰만)

- [ ] **Step 1: uvicorn 재시작** (exporter.py 변경 반영 — `--reload` 없음)

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
lsof -ti:8000 | xargs kill 2>/dev/null
set -a; source .env 2>/dev/null; set +a
nohup pipeline/.venv/bin/uvicorn pipeline.api:app --port 8000 > /tmp/cpia_uvicorn.log 2>&1 &
sleep 3 && curl -s localhost:8000/health 2>&1 | head
```
Expected: uvicorn 기동(체크포인트 PG 영속이라 재시작 안전).

- [ ] **Step 2: dev 서버 확인** (`:5537` npm dev — 자동 reload)

화면 변경(route.ts/SheetTable.tsx)은 HMR 자동 반영. 미기동 시 `cd web && npm run dev`.

- [ ] **Step 3: 시드일(9/24) Export 화면 확인** (Playwright 또는 사용자)

`http://127.0.0.1:5537/export` → 좌측 목록 9/24 선택. 검증:
- "1. 작업사항" 탭: **20행**(업체별), BP사=업체명(OTIS/광건/…), 작업사항 표시.
- "2. 직종별"·"3. 장비현황" 탭: 빈상태("데이터가 없습니다") — 정상.
- "4. 물량" 탭: 현행대로 채워짐.

- [ ] **Step 4: 실업로드일(9/25) Export 화면 확인**

9/25 선택. 검증:
- "1. 작업사항": 7행, BP사=업체명(광건/글로벌유명/남웅건설/…, 코드 아님), 전일/금일/명일 작업사항 **세 컬럼 정렬 정합**(줄바꿈 보존, 3줄 제한).
- "2. 직종별"(88) / "3. 장비현황"(136): 풍부값 유지, BP사=업체명.
- "4. 물량": BP 코드 + BP사 2컬럼 유지(불변).

- [ ] **Step 5: xlsx 다운로드 확인** (선택 — 시간 되면)

9/24 "Excel 출력" → 다운로드 xlsx 의 "1.출력인원 현황" 시트에 업체별 행·BP사=업체명 기입, 9/25 는 4시트 정상.

- [ ] **Step 6: 결과 보고**

실 명령 출력(테스트 + UI 스냅샷/관찰)을 원본 그대로 보고. 의도 부합 확인 후 완료 선언.

---

## 완료 기준 (Definition of Done)

1. Task 1·3·4 신규 테스트 + 기존 테스트 전부 green (실 출력 인용).
2. 9/24 Export "작업사항" 탭 = 20행, BP사=업체명, 작업사항 노출.
3. 9/25 Export = 4시트 정상, BP사=업체명, 작업사항 3컬럼 정합.
4. 시트2/3 시드일 빈상태(설계대로), 시트4 불변.
5. 디자인: cellClass 3개(작업사항) 외 마크업/레이아웃/label 변경 0.
6. 생산성 12.6% 는 미수정(스펙 §1.6 문서화만) — 본 플랜 범위 밖.

## 후속 (별도 세션)
- Report 현장 생산성 12.6% 코드 수정 — view_builder PRIMARY/FALLBACK 경로. 실 run 비교 후 결정.
- 머지 전략(`feature/review-l75-hil` → main) 사용자 확인.
