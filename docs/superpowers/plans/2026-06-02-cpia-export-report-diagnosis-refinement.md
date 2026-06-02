# CPIA Export WA · 최적화 공기 정합 · 진단/만회방안 재설계 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export 의 work area(Zone)를 mapper 해결값으로 채우고, "최적화 공기" headline 을 WP목록 단축일 합과 정합시키며, 진단을 "물량 현황 + 현장여건 2줄"·권고사항을 "만회방안 2건"으로 재설계한다.

**Architecture:** 3개 독립 파트. (A) exporter 가 `mapper_activities.wa` 를 소싱. (B) view_builder 가 site recovery 를 `Σ(wp_summary recovery_days)` 로 산출 + FE 가 전체 wp_summary 노출. (C) view_builder 가 진단 1줄을 결정론 물량 현황으로 작성, optimizer LLM 은 현장여건 1줄만, FE 라벨/건수/괄호 조정.

**Tech Stack:** Python 3.11 (pytest, asyncpg, openpyxl) · Next.js 14 + TypeScript (vitest, @testing-library/react) · Azure OpenAI (gpt-5.1)

**Spec:** `docs/superpowers/specs/2026-06-02-cpia-export-report-diagnosis-refinement-design.md`
**Branch:** A_Track (사용자 브랜치 정책 — feature 브랜치/worktree 안 만듦)
**검증 데이터:** 09-24 완주 run (원격 PG 43.200.85.209:5532). LLM 프롬프트는 단위테스트 불가 → POC 재실행 + 가드 충족으로 검증.

---

## File Structure

**Part A (Export WA):**
- Modify: `pipeline/agents/exporter.py` — `fetch_sheet_data`(JOIN mapper.wa + company→wa 맵), `_fill_quantity`(시트4 zone), `_fill_output_manpower`(시트1 zone)
- Modify: `web/app/api/mock/consolidated/route.ts` — zone 소스 정렬
- Test: `pipeline/tests/test_exporter_wa_source.py` (신규)

**Part B (최적화 공기 SSOT):**
- Modify: `pipeline/agents/optimizer/view_builder.py:~2257` — site recovery = Σ(wp_summary)
- Create: `web/lib/wp-rows.ts` — `wpRowsForStatus` 순수 헬퍼 (테스트용 추출)
- Modify: `web/app/(app)/reports/page.tsx:145-150` — 전체 wp_summary 노출
- Test: `pipeline/tests/test_view_builder_site_recovery.py` (신규), `web/tests/wp-rows.test.ts` (신규)

**Part C (진단/만회방안):**
- Modify: `pipeline/agents/optimizer/prompt.py:447` — `DIAG_PROMPT_V10` → 현장여건 1줄
- Modify: `pipeline/agents/optimizer/view_builder.py` — `_status_line_qty` 헬퍼 + 진단 합성(1210-1214) + 유사/만회 2건 trim(1198 등)
- Modify: `web/lib/types.ts:245` — `OptimizerOutput` 에 `delay_days?`/`recovery_days?` optional
- Modify: `web/app/components/reports/OptimizerResult.tsx` — 라벨/slice/괄호
- Modify: `web/app/(app)/reports/page.tsx:258` — delay/recovery prop 전달
- Test: `pipeline/tests/test_status_line_qty.py` (신규), `web/tests/optimizer-result.test.tsx` (확장)

---

## Part A — Export WA 빈칸

### Task A1: 시트4(물량) — fetch_sheet_data 가 mapper.wa JOIN

**Files:**
- Modify: `pipeline/agents/exporter.py:77-96` (act_rows 쿼리 + SheetData)
- Test: `pipeline/tests/test_exporter_wa_source.py`

- [ ] **Step 1: 실패 테스트 — act row 에 mapper_wa 가 실린다**

```python
# pipeline/tests/test_exporter_wa_source.py
import pytest
from pipeline.agents.exporter import _fill_quantity

def test_fill_quantity_prefers_mapper_wa(monkeypatch):
    """시트4 Zone = mapper_wa 우선, 없으면 parser zone fallback."""
    import openpyxl
    ws = openpyxl.Workbook().active
    rows = [
        {"mapper_wa": "FAB", "zone": None, "trade": "건축", "unit": "m2"},
        {"mapper_wa": None, "zone": "CUB", "trade": "토목", "unit": "m"},
        {"mapper_wa": "", "zone": "FAB", "trade": "건축", "unit": "m2"},
    ]
    _fill_quantity(ws, rows, __import__("datetime").date(2025, 9, 24))
    from pipeline.agents.exporter import COL_QUANTITY, DATA_START_ROW
    zcol = COL_QUANTITY["zone"]
    assert ws.cell(DATA_START_ROW + 0, zcol).value == "FAB"   # mapper_wa
    assert ws.cell(DATA_START_ROW + 1, zcol).value == "CUB"   # fallback parser zone
    assert ws.cell(DATA_START_ROW + 2, zcol).value == "FAB"   # 빈 mapper_wa → parser zone
```

- [ ] **Step 2: 실패 확인**

Run: `pipeline/.venv/bin/python -m pytest pipeline/tests/test_exporter_wa_source.py -v`
Expected: FAIL — `_fill_quantity` 가 아직 `row.get("zone")` 만 봄 → row0 이 None.

- [ ] **Step 3: `_fill_quantity` zone 소스 변경 (exporter.py:289)**

```python
# exporter.py:289 변경
_safe_set(ws, r, C["zone"], (row.get("mapper_wa") or row.get("zone")))
```

- [ ] **Step 4: 통과 확인**

Run: `pipeline/.venv/bin/python -m pytest pipeline/tests/test_exporter_wa_source.py -v`
Expected: PASS

- [ ] **Step 5: fetch_sheet_data 쿼리에 mapper.wa LEFT JOIN (exporter.py:77-87)**

```python
# act_rows 쿼리 교체:
act_rows = await con.fetch(
    """
    SELECT pa.*, ma.wa AS mapper_wa
    FROM parser_activities pa
    JOIN pipeline_runs pr USING (run_id)
    LEFT JOIN mapper_activities ma USING (run_id, idx)
    WHERE pr.site_id = $1 AND pa.report_date = $2
    ORDER BY pa.run_id, pa.idx
    """,
    site_id,
    report_date,
)
```
(`quantity=[dict(r) for r in act_rows]` 는 그대로 — 이제 `mapper_wa` 키 포함.)

- [ ] **Step 6: 커밋**

```bash
git add pipeline/agents/exporter.py pipeline/tests/test_exporter_wa_source.py
git commit -m "fix(exporter): 시트4 Zone=mapper.wa 우선 (빈 parser.zone fallback)"
```

---

### Task A2: 시트1(출력인원) — company→wa 대표값 주입

**[플랜 확정 결정]** BP(company)가 FAB·CUB 양쪽이면 **최빈 wa 1개**(동률이면 FAB). 콤마 병기 안 함 (시트1 셀 단일값).

**Files:**
- Modify: `pipeline/agents/exporter.py` — `fetch_sheet_data`(company_wa 맵 빌드 + SheetData 확장), `_fill_output_manpower`(:228)
- Test: `pipeline/tests/test_exporter_wa_source.py` (확장)

- [ ] **Step 1: 실패 테스트 — 시트1 Zone = company 최빈 wa**

```python
def test_fill_output_manpower_company_wa():
    import openpyxl
    from pipeline.agents.exporter import _fill_output_manpower, COL_OUTPUT_MANPOWER, DATA_START_ROW
    ws = openpyxl.Workbook().active
    rows = [{"company": "글로벌유명", "zone": None, "disc_abbrev": "건축"}]
    company_wa = {"글로벌유명": "FAB"}
    _fill_output_manpower(ws, rows, __import__("datetime").date(2025, 9, 24), company_wa=company_wa)
    assert ws.cell(DATA_START_ROW, COL_OUTPUT_MANPOWER["zone"]).value == "FAB"
```

- [ ] **Step 2: 실패 확인** — `_fill_output_manpower` 가 `company_wa` 인자 없음 → TypeError/None.

- [ ] **Step 3: `_fill_output_manpower` 시그니처+zone 변경 (exporter.py:224-228)**

```python
def _fill_output_manpower(ws, rows, report_date, *, company_wa: dict | None = None):
    C = COL_OUTPUT_MANPOWER
    company_wa = company_wa or {}
    for i, row in enumerate(rows):
        r = DATA_START_ROW + i
        _safe_set(ws, r, C["zone"], company_wa.get(row.get("company")) or row.get("zone"))
        ...  # 이하 동일
```

- [ ] **Step 4: fetch_sheet_data 가 company_wa 맵 빌드 + render_xlsx 배선**

```python
# fetch_sheet_data 안, act_rows fetch 직후 추가:
        wa_rows = await con.fetch(
            """
            SELECT ma.company, ma.wa
            FROM mapper_activities ma
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND ma.report_date = $2 AND COALESCE(ma.wa,'') <> ''
            """,
            site_id, report_date,
        )
# company별 최빈 wa (동률 FAB 우선)
from collections import Counter
_by_co: dict[str, Counter] = {}
for r in wa_rows:
    _by_co.setdefault(r["company"], Counter())[r["wa"]] += 1
company_wa = {
    co: max(cnt.items(), key=lambda kv: (kv[1], kv[0] == "FAB"))[0]
    for co, cnt in _by_co.items()
}
```
`SheetData` 에 `company_wa: dict` 필드 추가하고 `fetch_sheet_data` 반환에 포함. `render_xlsx` 가 `_fill_output_manpower(..., company_wa=sheet_data.company_wa)` 호출.

- [ ] **Step 5: 통과 확인** — `pytest pipeline/tests/test_exporter_wa_source.py -v` PASS

- [ ] **Step 6: 회귀 — 기존 exporter 렌더 테스트**

Run: `pipeline/.venv/bin/python -m pytest pipeline/tests/test_exporter_render.py pipeline/tests/test_exporter_merged_cell.py -v`
Expected: PASS (기존 동작 유지)

- [ ] **Step 7: 커밋**

```bash
git add pipeline/agents/exporter.py pipeline/tests/test_exporter_wa_source.py
git commit -m "fix(exporter): 시트1 Zone=company 최빈 mapper.wa 주입"
```

---

### Task A3: web /export 그리드 zone 소스 정렬

**Files:**
- Modify: `web/app/api/mock/consolidated/route.ts` (zone 매핑 — 시트4 `a.zone`, 시트1 `s.zone`)
- Test: 수동 (web 그리드는 BFF SELECT — Part A1/A2 의 BE 데이터에 의존). 가능하면 route 의 매핑 순수함수 추출 후 vitest.

- [ ] **Step 1: route.ts 가 mapper.wa 를 우선 노출**

`consolidated/route.ts` 의 PG SELECT 가 `parser_activities` 만 읽으면, A1 과 동일하게 `mapper_activities` LEFT JOIN 추가하고 zone 매핑을 `a.mapper_wa ?? a.zone` 으로. (route 의 실제 쿼리 구조 확인 후 적용 — `pa.*` 면 JOIN 추가, view/RPC 면 해당 소스 수정.)

- [ ] **Step 2: 실 검증**

Run (09-24): `curl -s "http://localhost:5537/api/mock/consolidated?...&date=2025-09-24" | python3 -c "import sys,json; d=json.load(sys.stdin); print([r.get('zone') for r in d['quantity'][:5]])"`
Expected: zone 이 FAB/CUB (빈칸 아님)

- [ ] **Step 3: 커밋**

```bash
git add web/app/api/mock/consolidated/route.ts
git commit -m "fix(export-web): /export Zone 컬럼 mapper.wa 우선"
```

---

## Part B — 최적화 공기 = WP목록 AI단축 합

### Task B1: view_builder — site recovery = Σ(wp_summary)

**근본원인**: `kpi.recovery_days`(`:2216`)·`scenarios.site.base_p50.recovery_days` 는 stored scenarios(by_wp 23 집합)에서 와서 wp_summary(13)의 합과 다름. **집계 모집단 교체** — wp_summary recovery 주입 루프(`:2252-2257`) 직후 그 13개의 합으로 site 를 재산출. (redundant 산식 신규 추가 아님.)

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:2257` 직후
- Test: `pipeline/tests/test_view_builder_site_recovery.py`

- [ ] **Step 1: 실패 테스트 — kpi.recovery_days == Σ(wp_summary recovery_days)**

```python
# pipeline/tests/test_view_builder_site_recovery.py
def test_site_recovery_equals_wp_summary_sum():
    """site recovery = 화면 wp_summary 합 (모집단 정합)."""
    wp_summary = [{"wp_id": "a", "recovery_days": 5}, {"wp_id": "b", "recovery_days": 2}, {"wp_id": "c", "recovery_days": 0}]
    kpi = {"recovery_days": 31}                       # stale (by_wp 23 합)
    scenarios = {"site": {"base_p50": {"recovery_days": 31}}}
    from pipeline.agents.optimizer.view_builder import reconcile_site_recovery
    reconcile_site_recovery(wp_summary, kpi, scenarios)
    assert kpi["recovery_days"] == 7
    assert scenarios["site"]["base_p50"]["recovery_days"] == 7
```

- [ ] **Step 2: 실패 확인** — `reconcile_site_recovery` 미정의.

- [ ] **Step 3: 헬퍼 추가 + 호출 (view_builder.py)**

```python
# 모듈 함수로 추가 (테스트 가능하게 순수):
def reconcile_site_recovery(wp_summary: list[dict], kpi: dict, scenarios: dict) -> None:
    """site recovery SSOT = Σ(wp_summary recovery_days). 화면 WP목록 합과 headline 정합."""
    total = sum(int(w.get("recovery_days") or 0) for w in wp_summary)
    kpi["recovery_days"] = total
    scenarios.setdefault("site", {}).setdefault("base_p50", {})["recovery_days"] = total
```
`view_builder.py:2257` (wp_summary recovery/delay 주입 for-loop) **직후** 호출:
```python
    reconcile_site_recovery(wp_summary, kpi, scenarios)
```

- [ ] **Step 4: 통과 확인** — PASS

- [ ] **Step 5: 실데이터 회귀 — 09-24 재빌드 후 정합**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA" && set -a && . ./.env.local && set +a && PYTHONPATH=$PWD pipeline/.venv/bin/python pipeline/scripts/_rebuild_views.py <09-24 run_id> 2025-09-24` 후
```sql
SELECT (scenarios_jsonb->'site'->'base_p50'->>'recovery_days')::int AS site,
  (SELECT SUM((e->>'recovery_days')::int) FROM jsonb_array_elements(wp_summary_jsonb) e) AS wp_sum
FROM daily_reports WHERE report_date='2025-09-24';
```
Expected: `site == wp_sum` (둘 다 동일 정수).

- [ ] **Step 6: 커밋**

```bash
git add pipeline/agents/optimizer/view_builder.py pipeline/tests/test_view_builder_site_recovery.py
git commit -m "fix(view_builder): site recovery=Σ(wp_summary) SSOT — headline·WP목록 합 정합"
```

---

### Task B2: FE — 전체 wp_summary 노출 (reduce-filter 제거)

**Files:**
- Create: `web/lib/wp-rows.ts`
- Modify: `web/app/(app)/reports/page.tsx:145-150`
- Test: `web/tests/wp-rows.test.ts`

- [ ] **Step 1: 실패 테스트 — status 필터만 적용, 전체 노출**

```typescript
// web/tests/wp-rows.test.ts
import { describe, it, expect } from "vitest";
import { wpRowsForStatus } from "@/lib/wp-rows";

const rows = [
  { wp_id: "a", status: "risk", recovery_days: 5 },
  { wp_id: "b", status: "normal", recovery_days: 2 },
] as any;

describe("wpRowsForStatus", () => {
  it("all → 전체 (visibleTrades/impact 필터 없음)", () => {
    expect(wpRowsForStatus(rows, "all")).toHaveLength(2);
  });
  it("risk → status 만 필터", () => {
    expect(wpRowsForStatus(rows, "risk").map((r) => r.wp_id)).toEqual(["a"]);
  });
});
```

- [ ] **Step 2: 실패 확인** — `wp-rows.ts` 없음.

- [ ] **Step 3: 헬퍼 작성**

```typescript
// web/lib/wp-rows.ts
import type { WPSummaryRow } from "@/lib/types";
export function wpRowsForStatus(
  rows: WPSummaryRow[],
  statusFilter: "normal" | "caution" | "risk" | "all",
): WPSummaryRow[] {
  return statusFilter === "all" ? rows : rows.filter((w) => w.status === statusFilter);
}
```

- [ ] **Step 4: 통과 확인** — `cd web && npx vitest run tests/wp-rows.test.ts` PASS

- [ ] **Step 5: page.tsx 배선 (145-150 교체)**

```typescript
// visibleTrades useMemo (108-111) 는 trade_bars 차트용이면 유지, WP목록 필터에선 미사용.
// filteredWpRowsBase 의 visibleTrades + impact 필터 제거 → 전체 wp_summary.
const filteredWpRowsBase = detail.wp_summary;
const filteredWpRows = wpRowsForStatus(filteredWpRowsBase, wpStatusFilter);
```
(import { wpRowsForStatus } from "@/lib/wp-rows" 추가. `visibleTrades` 가 WP목록에서만 쓰였으면 unused 정리.)

- [ ] **Step 6: 실 검증 (dev 5537)** — /reports 에서 WP목록 합(AI단축 컬럼) == "최적화 공기" headline, 4분면 클릭해도 headline 불변.

- [ ] **Step 7: 커밋**

```bash
git add web/lib/wp-rows.ts web/tests/wp-rows.test.ts "web/app/(app)/reports/page.tsx"
git commit -m "feat(report): WP목록 전체 wp_summary 노출 — headline 합과 정합 (visibleTrades/impact 필터 제거)"
```

---

## Part C — 진단/만회방안 재설계

### Task C1: DIAG_PROMPT_V10 → 현장여건 1줄

**Files:**
- Modify: `pipeline/agents/optimizer/prompt.py:447-481`

- [ ] **Step 1: `DIAG_PROMPT_V10` 본문 교체 (POC 확정본)**

```python
DIAG_PROMPT_V10 = """당신은 건설 현장 PM 의 일일 의사결정을 돕는 분석가입니다.
진단 1줄(생산성/물량 수치 현황)은 시스템이 이미 작성했습니다. 당신은 **2줄째 "현장여건" 1줄만** 작성합니다.

작성할 것: 현장여건 1줄 (개조식, 명사 종결). 오늘 진척을 만든/막은 현장 조건(자재·인력·기상·간섭·양중 등)을 trade_frame 제약과 연결해 1가지 신호로.
- 오늘 조건이 "정상" 이면 없는 장애를 지어내지 말 것 — trade_frame 상 오늘 가장 관건인 제약 1가지만.

규칙: 아라비아 숫자만(한글 숫자 금지), 인시(man-hour) 절대수치 금지, 회복 패턴·만회방안·"분기점" 금지, 한자·영어 약어 금지. 위험도 "이상" 이면 "정상범주/정상 범위" 금지.

출력 JSON: {"diagnosis": "현장여건 1줄"}
"""
```

- [ ] **Step 2: 가드 문자열 sanity 테스트 (프롬프트 자체는 LLM — 결정론 단위테스트 대신 핵심 가드 포함 확인)**

```python
# pipeline/tests/test_status_line_qty.py (같은 파일에 추가)
def test_diag_prompt_v10_guards():
    from pipeline.agents.optimizer.prompt import DIAG_PROMPT_V10
    assert "현장여건" in DIAG_PROMPT_V10
    assert "회복 패턴" in DIAG_PROMPT_V10  # 금지 명시
    assert "한글 숫자 금지" in DIAG_PROMPT_V10
```

- [ ] **Step 3: 통과 확인** — PASS

- [ ] **Step 4: 커밋**

```bash
git add pipeline/agents/optimizer/prompt.py pipeline/tests/test_status_line_qty.py
git commit -m "feat(optimizer): DIAG_PROMPT_V10 현장여건 1줄 — 회복패턴/분기점 폐기"
```

---

### Task C2: view_builder — 진단 1줄 = 결정론 물량 현황

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py` — `_status_line_qty` 헬퍼 + 진단 합성(1210-1214)
- Test: `pipeline/tests/test_status_line_qty.py`

- [ ] **Step 1: 실패 테스트 — 물량 현황 1줄 결정론**

```python
# pipeline/tests/test_status_line_qty.py
from pipeline.agents.optimizer.view_builder import _status_line_qty

def test_status_line_qty_basic():
    fr = {
        "today_conditions": "자재미입고", "main_unit": "m",
        "today_qty_by_unit": {"m": 3.25}, "plan_total_qty_by_unit": {"m": 1038.0},
        "plan_mh_sum": 52166.0, "plan_mh_per_day": 98.43,
    }
    # total_days=52166/98.43≈530 → plan_daily≈1.96 → 소수1자리
    assert _status_line_qty(fr) == "자재미입고 조건 · 금일 3.3 m (계획 일평균 2.0 m)"

def test_status_line_qty_normal_and_missing():
    assert _status_line_qty({"today_conditions": "", "main_unit": "m2",
        "today_qty_by_unit": {"m2": 142.7}, "plan_total_qty_by_unit": {"m2": 39202.0},
        "plan_mh_sum": 430736.0, "plan_mh_per_day": 1216.77}) == "정상 조건 · 금일 142.7 m2 (계획 일평균 110.7 m2)"
    # 계획 필드 없으면 '계획 —'
    assert "계획 —" in _status_line_qty({"today_conditions": "정상", "main_unit": "m2", "today_qty_by_unit": {"m2": 10.0}})
```

- [ ] **Step 2: 실패 확인** — `_status_line_qty` 미정의.

- [ ] **Step 3: 헬퍼 작성 (view_builder.py)**

```python
def _status_line_qty(fr: dict) -> str:
    """진단 1줄(현황) — 결정론 물량 기준. '{조건} 조건 · 금일 {qty} {unit} (계획 일평균 {plan} {unit})'.
    per-person % 는 forecast 생산성 basis 불일치로 미사용(스펙 caveat). 소수 1자리, 아라비아 숫자."""
    cond = (fr.get("today_conditions") or "정상").split(",")[0].strip() or "정상"
    unit = fr.get("main_unit") or ""
    tq = (fr.get("today_qty_by_unit") or {}).get(unit)
    pt = (fr.get("plan_total_qty_by_unit") or {}).get(unit)
    pmh, pmh_d = fr.get("plan_mh_sum"), fr.get("plan_mh_per_day")
    total_days = (pmh / pmh_d) if (pmh and pmh_d) else None
    plan_daily = (pt / total_days) if (pt and total_days) else None
    tq_s = f"{tq:.1f}" if isinstance(tq, (int, float)) else "—"
    pd_s = f"{plan_daily:.1f}" if isinstance(plan_daily, (int, float)) else "—"
    return f"{cond} 조건 · 금일 {tq_s} {unit} (계획 일평균 {pd_s} {unit})"
```

- [ ] **Step 4: 통과 확인** — PASS

- [ ] **Step 5: 진단 합성 교체 (view_builder.py:1210-1214)**

기존 `_diagnosis_prefix(prod_info, ...)` 호출을 물량 현황 줄로 교체. (현황 줄은 wa별 forecast `wa_f` 기준이므로, `wa_list` 루프 안에서 wa별 진단을 합성. 현재 그룹 단일 diagnosis 합성이면, 대표 `matched_f` 로 1줄 산출 후 LLM 여건과 합성.)
```python
        # 진단 1줄(물량 현황, 결정론) + 2줄째 LLM 현장여건.
        status_line = _status_line_qty(matched_f)
        llm_diag = advice.get("diagnosis") or ""        # 새 프롬프트 = 현장여건 1줄
        diagnosis = f"{status_line}\n{llm_diag}".strip()
```
(주의: `matched_f` 에 `today_qty_by_unit`/`plan_total_qty_by_unit`/`plan_mh_*`/`main_unit` 가 실려 있는지 forecast 로딩부에서 확인 — 없으면 SELECT 에 추가. Step 6 에서 실데이터로 검증.)

- [ ] **Step 6: 실데이터 검증 — 09-24 재빌드 후 진단 1줄 형식**

`_rebuild_views.py` 09-24 재실행 후 `optimizer_view_jsonb->'by_wp'->><wp>->>'diagnosis'` 1줄이 `"{조건} 조건 · 금일 N {unit} (계획 일평균 M {unit})"` 형식인지 + 한글 숫자 없는지 확인.

- [ ] **Step 7: 커밋**

```bash
git add pipeline/agents/optimizer/view_builder.py pipeline/tests/test_status_line_qty.py
git commit -m "feat(view_builder): 진단 1줄=결정론 물량 현황 (정상대비% 폐기, 물량 페이스)"
```

---

### Task C3: view_builder — 유사사례·만회방안 2건 trim

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:1198`(rdist [:3]→[:2]) + recommendations trim(3→2) + similar_cases 빌드부(3→2)

- [ ] **Step 1: 실 위치 확인 + 2건으로 변경**

- `view_builder.py:1198` `cases_for_dist = (advice.get("degradation_cases") or [])[:3]` → `[:2]`
- `similar_cases` 빌드 시 `[:3]` 또는 OptimizerResult slice 의존이면 BE 에서 `[:2]` 로 명시.
- recommendations trim (investigation 상 `:1193` 부근 `[:3]`) → `[:2]`.

- [ ] **Step 2: 회귀 — optimizer view 테스트**

Run: `pipeline/.venv/bin/python -m pytest pipeline/tests/test_view_builder_optimizer_view.py -v`
Expected: PASS (건수 기대값이 3 고정이면 2로 갱신)

- [ ] **Step 3: 커밋**

```bash
git add pipeline/agents/optimizer/view_builder.py pipeline/tests/test_view_builder_optimizer_view.py
git commit -m "feat(view_builder): 유사사례·만회방안 3→2건 trim"
```

---

### Task C4: OptimizerResult — 라벨/slice/괄호

**Files:**
- Modify: `web/lib/types.ts:245-252` (OptimizerOutput + delay_days/recovery_days optional)
- Modify: `web/app/components/reports/OptimizerResult.tsx`
- Test: `web/tests/optimizer-result.test.tsx` (확장)

- [ ] **Step 1: 실패 테스트 — "만회방안" 라벨 + 괄호 표시**

```typescript
// optimizer-result.test.tsx 에 추가
it("권고사항 라벨이 '만회방안' + 괄호에 지연/AI단축", () => {
  const { getByText } = render(
    <OptimizerResult output={out} delayDays={31} recoveryDays={2} />
  );
  expect(getByText(/만회방안/)).toBeTruthy();
  expect(getByText(/\(지연 \+31일\)/)).toBeTruthy();
  expect(getByText(/\(AI 단축 -2일\)/)).toBeTruthy();
});
```

- [ ] **Step 2: 실패 확인** — `cd web && npx vitest run tests/optimizer-result.test.tsx` FAIL (props 없음/라벨 "권고사항").

- [ ] **Step 3: types + 컴포넌트 변경**

```typescript
// types.ts OptimizerOutput 끝에:
//   delay_days?: number;
//   recovery_days?: number;
// OptimizerResult.tsx:
export function OptimizerResult({ output, delayDays, recoveryDays }:
  { output: OptimizerOutput; delayDays?: number; recoveryDays?: number }) {
```
- 진단 Row title: `title={`진단${typeof delayDays === "number" ? `  (지연 +${delayDays}일)` : ""}`}` — 또는 title 옆 span.
- 유사사례 `slice(0, 3)` → `slice(0, 2)`.
- 권고 Row title `"권고사항"` → `만회방안${typeof recoveryDays === "number" && recoveryDays > 0 ? `  (AI 단축 -${recoveryDays}일)` : ""}`.
- 만회방안 목록 `.map` 앞 `.slice(0, 2)` 추가.
- (괄호 표기는 디자인 불가침 — Row title 텍스트에 덧붙이는 수준, 마크업 구조 변경 X.)

- [ ] **Step 4: 통과 확인** — PASS

- [ ] **Step 5: 커밋**

```bash
git add web/lib/types.ts web/app/components/reports/OptimizerResult.tsx web/tests/optimizer-result.test.tsx
git commit -m "feat(report): 권고사항→만회방안 + 유사·만회 2건 + 진단/만회 괄호(지연·AI단축)"
```

---

### Task C5: reports/page.tsx — delay/recovery prop 전달

**Files:**
- Modify: `web/app/(app)/reports/page.tsx:258-264`

- [ ] **Step 1: 선택 WP row 의 delay/recovery 를 OptimizerResult 로 전달**

```typescript
// selectedWpId 의 wp_summary row 찾기 (이미 filteredWpRows/ wp_summary 보유)
const selectedWp = detail.wp_summary.find((w) => w.wp_id === selectedWpId);
// ...
<OptimizerResult
  output={detail.optimizer?.by_wp?.[selectedWpId ?? ""] ?? detail.optimizer?.by_wp?.[detail.optimizer?.default_wp_id ?? ""] ?? EMPTY_OPTIMIZER}
  delayDays={selectedWp?.delay_days}
  recoveryDays={selectedWp?.recovery_days}
/>
```

- [ ] **Step 2: 빌드/타입 검증**

Run: `cd web && npx tsc --noEmit`
Expected: 타입 에러 없음

- [ ] **Step 3: 실 검증 (dev 5537)** — WP 선택 시 진단 옆 `(지연 +N일)`, 만회방안 옆 `(AI 단축 -N일)` = WP목록 행 값과 동일.

- [ ] **Step 4: 커밋**

```bash
git add "web/app/(app)/reports/page.tsx"
git commit -m "feat(report): OptimizerResult 에 선택 WP 지연/AI단축 prop 배선"
```

---

## 최종 검증 (전체 e2e)

- [ ] **pipeline 회귀 전체**: `pipeline/.venv/bin/python -m pytest pipeline/tests/ -q` (기존 통과 스위트 유지; 사전 실패 제외)
- [ ] **web 회귀 전체**: `cd web && npx vitest run` (+ `npx tsc --noEmit`)
- [ ] **실 e2e (dev 5537 + API 8000)**: 09-25 7개 업로드 → Mapper HIL 확정 → 완주 → /reports:
  - export 시트 Zone 빈칸 0
  - 최적화 공기 == WP목록 AI단축 합 (4분면 무관 고정)
  - 진단 2줄(물량 현황 + 여건), 유사 2건, 만회방안 2건 + 괄호(지연/AI단축)
- [ ] **데이터 caveat 무회귀**: per-person % 미사용(물량 기준)으로 1061% 류 안 보임.

---

## Plan Review

플랜 작성 후 plan-document-reviewer 디스패치 → 이슈 수정 → 재리뷰 (최대 3회) → 승인 시 실행 핸드오프.
