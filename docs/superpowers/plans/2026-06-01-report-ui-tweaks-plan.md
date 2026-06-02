# Reports UI 정밀화 + recovery_days SSOT 일치 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reports 화면에서 (1) WP목록 라벨을 Work Area(FAB/CUB)로 바꾸고, (2) §03 장문 AI 권고 카드를 숨기고, (3) WP목록 "공기 단축"과 §03 "최적화공기"를 AI 추천 기준으로 정확히 일치(옵션 B)시킨다.

**Architecture:** 변경1·2는 FE 전용(`web/`), 재적재 0. 변경3은 BE(`pipeline/agents/optimizer/view_builder.py`)에서 (a) 회사명 정규화, (b) wp_summary↔scenarios.by_wp 매칭을 정규화 (company, l6) + wa-우선 + 1회귀속으로 고치고, (c) §03 site base_p50 = Σ(보이는 wp_summary recovery_days)로 재계산한다. 그 후 데모 날짜의 `daily_reports` jsonb를 deterministic views 재생성(옵티마이저 advice 재호출 없음)으로 갱신한다.

**Tech Stack:** Next.js(web/), Python LangGraph(pipeline/, `uv run`), PostgreSQL(AWS 43.200.85.209:5532), `scripts/backfill_daily_report_views_v2.py`, vitest, Playwright MCP.

**Spec:** `docs/superpowers/specs/2026-06-01-report-ui-tweaks-design.md` (spec-reviewer Approved).

---

## File Structure

| File | 책임 | 변경 |
|------|------|------|
| `web/lib/work-area.ts` | `workAreaOf(wpId, wpName)` 순수 헬퍼 (FAB/CUB 파생) | **Create** |
| `web/lib/__tests__/work-area.test.ts` | 헬퍼 단위 테스트 | **Create** |
| `web/app/components/reports/WPSummaryTable.tsx` | WP목록 테이블 — 헤더·셀 라벨 | Modify `:37, :65` |
| `web/app/components/charts/ForecastChart.tsx` | §03 차트 — AI 권고 카드 게이트 | Modify `:49-58`(props), `:390`(게이트) |
| `web/app/(app)/reports/page.tsx` | §03 렌더 — showAdvice 미전달 | Modify `:269-327` 영역 |
| `pipeline/agents/optimizer/view_builder.py` | 회사명 정규화 + 매칭 + site 재계산 | Modify `:398-406, :1335-1345, :1366-1453, :2151-2185` |
| `pipeline/tests/optimizer/test_recovery_ssot.py` | 변경3 회귀 테스트 | **Create** |

**기존 패턴 준수:** view_builder는 큰 단일 파일(~2200줄)이지만 재구조화하지 않는다(surgical). 헬퍼는 모듈 상단 함수로 추가. FE 헬퍼는 `web/lib/`에 둬 vitest로 테스트.

---

## Task 1: WP목록 Work Area 라벨 (FE, 재적재 0)

**Files:**
- Create: `web/lib/work-area.ts`
- Create: `web/lib/__tests__/work-area.test.ts`
- Modify: `web/app/components/reports/WPSummaryTable.tsx:37,65`

근거: `wp_id`는 항상 `{wa}-{l6}-{company}` kebab (`view_builder.py:406` `_wp_id_of`). 9/24 실값 앞토큰은 `fab`/`cub` 뿐. fallback은 `wp_name`의 " · " 뒤(`_wp_name_with_wa` = `f"{l6_main} · {wa}"`, `view_builder.py:1897`).

- [ ] **Step 1: 헬퍼 실패 테스트 작성** — `web/lib/__tests__/work-area.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { workAreaOf } from "@/lib/work-area";

describe("workAreaOf", () => {
  it("wp_id 앞토큰을 대문자 wa로", () => {
    expect(workAreaOf("fab-철근콘크리트공사-남웅건설", "철근콘크리트공사 · FAB")).toBe("FAB");
    expect(workAreaOf("cub-도장공사-선보", "도장공사 · CUB")).toBe("CUB");
  });
  it("회사·l6에 하이픈 있어도 첫 토큰만", () => {
    expect(workAreaOf("fab-c/r-조성공사-한국", "")).toBe("FAB");
    expect(workAreaOf("cub-pc공사-삼표-피엔씨", "")).toBe("CUB");
  });
  it("wp_id 비면 wp_name의 ' · ' 뒤 fallback", () => {
    expect(workAreaOf("", "철근콘크리트공사 · FAB")).toBe("FAB");
  });
  it("둘 다 없으면 빈 문자열", () => {
    expect(workAreaOf("", "철근콘크리트공사")).toBe("");
  });
});
```

- [ ] **Step 2: 테스트 실패 확인** — Run: `cd web && npx vitest run lib/__tests__/work-area.test.ts`
  Expected: FAIL (`Cannot find module '@/lib/work-area'`).

- [ ] **Step 3: 헬퍼 구현** — `web/lib/work-area.ts`

```ts
// WP목록 "Work Area" 라벨 — wp_id 앞토큰(fab/cub)을 대문자로. fallback: wp_name " · " 뒤.
// wp_id 포맷: `{wa}-{l6}-{company}` (BE view_builder _wp_id_of). 앞토큰만 쓰므로 하이픈 포함 l6/회사 무관.
export function workAreaOf(wpId: string, wpName: string): string {
  const head = (wpId ?? "").split("-")[0]?.trim();
  if (head) return head.toUpperCase();
  const tail = (wpName ?? "").split("·")[1]?.trim();
  return tail ? tail.toUpperCase() : "";
}
```

- [ ] **Step 4: 테스트 통과 확인** — Run: `cd web && npx vitest run lib/__tests__/work-area.test.ts`
  Expected: PASS (4 passed).

- [ ] **Step 5: WPSummaryTable 적용** — `WPSummaryTable.tsx`
  - 상단 import 추가: `import { workAreaOf } from "@/lib/work-area";`
  - `:37` 헤더: `<th className="px-3 py-1.5 font-medium">WP명</th>` → `<th className="px-3 py-1.5 font-medium">Work Area</th>`
  - `:65` 셀: `{row.wp_name}` → `{workAreaOf(row.wp_id, row.wp_name)}`
  - 공종 셀(`:67` `{row.trade}`)·나머지 칼럼 불변.

- [ ] **Step 6: 빌드 타입 체크** — Run: `cd web && npx tsc --noEmit`
  Expected: 에러 0.

- [ ] **Step 7: 커밋**

```bash
git add web/lib/work-area.ts web/lib/__tests__/work-area.test.ts web/app/components/reports/WPSummaryTable.tsx
git commit -m "feat(reports): WP목록 라벨을 Work Area(FAB/CUB)로"
```

---

## Task 2: §03 AI 권고 카드 숨김 (FE, 재적재 0)

**Files:**
- Modify: `web/app/components/charts/ForecastChart.tsx:49-58, :390`
- Modify: `web/app/(app)/reports/page.tsx` (ForecastChart 렌더 — showAdvice 미전달)

근거: 권고 카드는 `ForecastChart.tsx:390-433`의 인라인 `<ul>` (`aiAdvice && aiAdvice.length > 0` 게이트). 그래프(`:194-297`)·KPI(`:112-172`)·3선표(`:300-374`)·LLM요약(`:376-387`)은 별개 형제. 권고 데이터는 §02 `OptimizerResult`에도 있으므로 숨겨도 손실 0. 코드 삭제 아님(플래그) — 복구 가능.

- [ ] **Step 1: prop 추가** — `ForecastChart.tsx` Props 인터페이스(`:32-41` 사이)에 추가:

```ts
  /** §03 하단 WP별 AI 권고 카드 노출. 기본 false(숨김). 권고는 §02 OptimizerResult 에 잔존. */
  showAdvice?: boolean;
```
  그리고 구조분해(`:49-58`)에 `showAdvice = false,` 추가.

- [ ] **Step 2: 게이트 조건에 AND** — `ForecastChart.tsx:390`
  `{aiAdvice && aiAdvice.length > 0 ? (` → `{showAdvice && aiAdvice && aiAdvice.length > 0 ? (`
  (블록 `:390-433` 전체가 false 시 미렌더. `:426-431` 캡션도 블록 내부라 함께 사라짐.)

- [ ] **Step 3: page.tsx 확인** — `web/app/(app)/reports/page.tsx`의 `<ForecastChart ... />`(약 `:270`)에 `showAdvice`를 **넘기지 않음**(기본 false). `aiAdvice` IIFE(`:281-325`)는 보존(무해, 복구용). 변경 없음 확인만; 만약 누군가 `showAdvice`를 넘기고 있으면 제거.

- [ ] **Step 4: 타입 체크** — Run: `cd web && npx tsc --noEmit`
  Expected: 에러 0.

- [ ] **Step 5: Playwright 검증** — dev 서버 `make web2`(5537) 가동 상태에서:
  Run (Playwright MCP): `http://127.0.0.1:5537/reports?date=2025-09-24` 로드 → `browser_evaluate`로 `document.body.innerText.includes("공기 단축 가능한 공종")` === `false` 확인, "공정률 추세 예측"(그래프) 과 LLM요약 단락 존재 확인.
  Expected: 권고 헤더 미존재, 그래프·요약 존재.

- [ ] **Step 6: 커밋**

```bash
git add web/app/components/charts/ForecastChart.tsx web/app/(app)/reports/page.tsx
git commit -m "feat(reports): §03 AI 권고 카드 숨김 (showAdvice 플래그, 기본 off)"
```

---

## Task 3: recovery_days SSOT 일치 (BE, 옵션 B)

> 변경3은 4 하위 태스크. 3.1 정규화 → 3.2 매칭 → 3.3 site 재계산 → 3.4 재생성·검증. 각 단계 TDD.

**공통 컨텍스트 (실 9/24 데이터로 검증된 케이스):**
- `남웅`(advice/forecast) vs `남웅건설`(mapper) — 같은 회사. fab 철근만 어긋남(`fab-철근-남웅` by_wp 5 ↔ `fab-철근-남웅건설` wp_summary —). cub 철근은 양쪽 "남웅건설"이라 이미 매칭.
- `otis 승강기`: 오늘 fab·cub 둘 다 활동(wp_summary 2행), advice는 1건(by_wp `fab-승강기-otis` 4뿐). → cub 행이 — . **1 advice → 1 wp_summary 행만 귀속(중복 금지)**.
- `장평 포장`: 오늘 fab만 활동(wp_summary `fab-포장-장평` 1행), advice는 `cub-포장-장평`(by_wp 5). wa만 다름 → fab 행에 귀속돼야.
- advice grain = (company, l6_main) — wa 없음. wa는 forecast에서 옴(`f.get("wa")`, `view_builder.py:1417`).

### Task 3.1: `_normalize_company` 헬퍼

**Files:** Modify `pipeline/agents/optimizer/view_builder.py` (`:398` 근처 `_wp_id_of` 위에 추가), Create `pipeline/tests/optimizer/test_recovery_ssot.py`

- [ ] **Step 1: 9/24 DISTINCT company 전수 확인 (정규화 규칙 근거)** — Run:
```bash
/opt/homebrew/opt/libpq/bin/psql "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia" -At -c \
"SELECT DISTINCT company FROM mapper_activities ma JOIN pipeline_runs pr USING(run_id) JOIN sites s ON s.site_id=pr.site_id WHERE s.is_mock=FALSE AND pr.report_date='2025-09-24' ORDER BY company"
```
  → 출력 그대로 보고. 정규화 규칙(접미사 절단 토큰 목록)을 이 실값으로 확정. 서로 다른 회사가 한 키로 합쳐지지 않는지 육안 검증.

- [ ] **Step 2: 실패 테스트** — `test_recovery_ssot.py`
```python
from __future__ import annotations
from pipeline.agents.optimizer.view_builder import _normalize_company

def test_normalize_company_merges_suffix_variants():
    assert _normalize_company("남웅건설") == _normalize_company("남웅")
def test_normalize_company_keeps_distinct():
    # 9/24 실 회사들은 서로 다른 정규형 유지 (Step 1 출력 기반으로 케이스 채움)
    assert _normalize_company("한국") != _normalize_company("해광")
    assert _normalize_company("선보") != _normalize_company("서림공영")
def test_normalize_company_longest_suffix_first():
    # '종합건설' 이 '건설' 보다 먼저 절단돼야 (sorted len desc) — 'XX종합건설' -> 'XX'
    assert _normalize_company("우리종합건설") == "우리"
```

- [ ] **Step 3: 실패 확인** — Run: `cd pipeline && uv run pytest tests/optimizer/test_recovery_ssot.py -q`
  Expected: FAIL (ImportError `_normalize_company`).

- [ ] **Step 4: 구현** — `view_builder.py` `_wp_id_of` 위에:
```python
# 회사명 정규화 — forecaster/optimizer advice 는 "남웅", mapper 는 "남웅건설" 처럼
# 같은 회사를 다른 문자열로 보유 → wp_id 불일치. 후행 법인격 토큰 절단으로 통일.
# Step 1 의 9/24 DISTINCT company 출력으로 _SUFFIXES 를 확정(서로 다른 회사 합쳐지지 않게).
_COMPANY_SUFFIXES = ("건설", "산업", "중공업", "종합건설", "이엔씨", "기업")

def _normalize_company(company: Optional[str]) -> str:
    c = (company or "").strip()
    for suf in sorted(_COMPANY_SUFFIXES, key=len, reverse=True):
        if c.endswith(suf) and len(c) > len(suf):
            return c[: -len(suf)]
    return c
```
  (※ Step 1 출력 보고 `_COMPANY_SUFFIXES` 최종 확정 — 과병합 0 검증 필수.)

- [ ] **Step 5: 통과 확인** — Run: `cd pipeline && uv run pytest tests/optimizer/test_recovery_ssot.py -q`
  Expected: PASS.

### Task 3.2: 정규화 + wa-우선 + 1회귀속 매칭

**Files:** Modify `view_builder.py:1417`(by_wp 키), `:2179-2185`(wp_summary 재assign), `:2190-2203`(카드 일정영향 동일 lookup)

설계: by_wp 키를 **정규화 company**로 만들고, 재assign을 **정규화 (company,l6)+wa-우선+1회귀속** 으로 바꾼다. by_wp 키 문자열을 되쪼개지 않도록, `_build_scenarios`가 by_wp 각 엔트리에 매칭 메타를 함께 보관한다.

- [ ] **Step 1: 실패 테스트 (매칭 시나리오)** — `test_recovery_ssot.py`에 추가. `_build_scenarios` + 재assign 로직을 직접 호출하는 단위 테스트. 픽스처는 9/24 3대 케이스:
```python
def test_assign_recovery_normalizes_and_attributes_once():
    # advice grain=(company,l6), wa 없음. forecast 가 wa 제공.
    advice_rows = [
        {"company": "남웅", "l6_main": "철근콘크리트공사", "scenarios": {"base": {"recovery_days": 5}}},
        {"company": "장평건설", "l6_main": "포장공사", "scenarios": {"base": {"recovery_days": 5}}},
        {"company": "otis", "l6_main": "승강기공사", "scenarios": {"base": {"recovery_days": 4}}},
    ]
    forecast = [
        {"company": "남웅", "l6_main": "철근콘크리트공사", "wa": "fab", "expected_completion": "2026-03-29"},
        {"company": "장평건설", "l6_main": "포장공사", "wa": "cub", "expected_completion": "2026-03-29"},
        {"company": "otis", "l6_main": "승강기공사", "wa": "fab", "expected_completion": "2026-03-29"},
    ]
    # wp_summary: mapper grain (company,l6,wa) — 회사명 "남웅건설"(접미사), 포장 fab(advice는 cub), 승강기 fab+cub 둘 다
    wp_summary = [
        {"wp_id": "fab-철근콘크리트공사-남웅건설", "bp_name": "남웅건설", "trade": "철근콘크리트공사"},
        {"wp_id": "fab-포장공사-장평건설",       "bp_name": "장평건설", "trade": "포장공사"},
        {"wp_id": "fab-승강기공사-otis",          "bp_name": "otis",     "trade": "승강기공사"},
        {"wp_id": "cub-승강기공사-otis",          "bp_name": "otis",     "trade": "승강기공사"},
    ]
    scenarios = _build_scenarios(advice_rows, forecast)
    assign_recovery_to_wp_summary(wp_summary, scenarios)  # 신규 추출 함수
    rec = {w["wp_id"]: w["recovery_days"] for w in wp_summary}
    assert rec["fab-철근콘크리트공사-남웅건설"] == 5   # 회사명 정규화로 매칭
    assert rec["fab-포장공사-장평건설"] == 5          # wa 다르지만 (company,l6)로 귀속
    # 승강기: advice 1건(4) → 두 wa 행 중 하나에만 귀속, 합 4 (중복 금지)
    assert rec["fab-승강기공사-otis"] + rec["cub-승강기공사-otis"] == 4
```

- [ ] **Step 2: 실패 확인** — Run: `cd pipeline && uv run pytest tests/optimizer/test_recovery_ssot.py -q`
  Expected: FAIL.

- [ ] **Step 3: 구현**
  - `_build_scenarios`(`:1417`): by_wp 키는 **기존 그대로**(`advice.get("company")` 미변경 — quadrant·optimizer_view 등 by_wp 키를 쓰는 다른 소비자 영향 0). 각 엔트리에 **정규화 매칭 메타 `_match`만 추가**:
    ```python
    f = _match_forecast_by_company_l6(advice, forecast)
    if f is None:
        continue
    wp_id = _wp_id_of(f.get("wa"), advice.get("l6_main"), advice.get("company"))  # 기존 유지
    llm_scenarios = advice.get("scenarios") or {}
    block = (_wp_block_from_llm(llm_scenarios, wp_no_action)
             if (llm_scenarios and any(llm_scenarios.get(k) for k in ("no_action","optimistic","base","pessimistic")))
             else _wp_block_deterministic(advice, wp_no_action))
    block["_match"] = {  # 내부 매칭 전용 — 직렬화 전 제거(Task 3.3)
        "company": _normalize_company(advice.get("company")),
        "l6_main": advice.get("l6_main"),
        "wa": f.get("wa"),
    }
    by_wp[wp_id] = block
    ```
  - 재assign 함수 추출 — `assign_recovery_to_wp_summary`. **by_wp 키 문자열에 의존하지 않고 `_match` 메타로 매칭**. 2-pass(exact-wa 우선 → 잔여 1회 귀속), 각 풀 항목은 `del`/`popleft`로 **1회 소진**이라 단일 advice 가 여러 wa 행에 중복 귀속되지 않음:
    ```python
    def assign_recovery_to_wp_summary(wp_summary: list[dict], scenarios: dict) -> None:
        from collections import defaultdict, deque
        scen_by_wp = scenarios.get("by_wp") or {}
        pool: dict[tuple, deque] = defaultdict(deque)  # (norm_company, l6) -> deque[(wa, rec)]
        for blk in scen_by_wp.values():
            m = blk.get("_match") or {}
            rec = int(((blk.get("base_p50") or {}).get("recovery_days")) or 0)
            pool[(m.get("company"), m.get("l6_main"))].append((m.get("wa"), rec))

        def _key(w): return (_normalize_company(w.get("bp_name")), w.get("trade"))
        def _wa(w): return (w["wp_id"].split("-")[0] or "").strip()

        for w in wp_summary:
            w["recovery_days"] = 0
        # pass 1 — exact wa 우선 (advice 의 forecast wa 와 같은 행이 먼저 claim)
        for w in wp_summary:
            q = pool.get(_key(w))
            if not q:
                continue
            idx = next((i for i, (qwa, _) in enumerate(q) if qwa == _wa(w)), None)
            if idx is not None:
                _, rec = q[idx]; del q[idx]; w["recovery_days"] = rec
        # pass 2 — wa 불일치 잔여 1회 귀속 (포장 fab↔cub 류)
        for w in wp_summary:
            if w.get("recovery_days"):
                continue
            q = pool.get(_key(w))
            if q:
                _, rec = q.popleft(); w["recovery_days"] = rec
    ```
    검증 직관: otis 승강기(advice fab 1건=4) → fab 행 pass1 claim=4, cub 행은 pass1·2 모두 풀이 비어 0 → **합 4(중복 없음)**. `_match["company"]`·`_key` 둘 다 `_normalize_company` 사용(양쪽 동일 정규화 — spec-reviewer 권고 #2).
  - `:2179-2185` 기존 루프를 `assign_recovery_to_wp_summary(wp_summary, scenarios)` 호출로 대체.
  - `:2190-2203` 카드 '일정 영향': assign 후 `recmap = {w["wp_id"]: w["recovery_days"] for w in wp_summary}` 를 만들어 `_rec = recmap.get(_wp_id, 0)` 로 참조(기존 `scen_by_wp.get(_wp_id)` exact lookup 대신 — wp_summary 와 동일 값 보장).

- [ ] **Step 4: 통과 확인** — Run: `cd pipeline && uv run pytest tests/optimizer/test_recovery_ssot.py -q`
  Expected: PASS (정규화·wa귀속·중복금지 전부).

### Task 3.3: §03 site = Σ(보이는 wp_summary) 재계산

**Files:** Modify `view_builder.py:2151-2154`(kpi) + assign 직후

근거: 현재 `scenarios.site.base_p50`은 `_build_scenarios`에서 by_wp 전체 합(`:1440`)으로 산출되고, `kpi.recovery_days`는 그걸 `:2153`에서 가져옴. 옵션 B는 site = 보이는 wp_summary 합.

- [ ] **Step 1: 실패 테스트** — `test_recovery_ssot.py`
```python
def test_site_base_p50_equals_visible_wp_sum():
    # 위 픽스처 재사용: 보이는 wp_summary 합 = 5+5+4 = 14
    scenarios = _build_scenarios(advice_rows, forecast)
    assign_recovery_to_wp_summary(wp_summary, scenarios)
    recompute_site_base_p50(scenarios, wp_summary)  # 신규
    assert scenarios["site"]["base_p50"]["recovery_days"] == sum(w["recovery_days"] for w in wp_summary)
    assert scenarios["site"]["base_p50"]["recovery_days"] == 14
```

- [ ] **Step 2: 실패 확인** — Run: `cd pipeline && uv run pytest tests/optimizer/test_recovery_ssot.py -q` → FAIL.

- [ ] **Step 3: 구현** — assign 직후 호출할 함수:
```python
def recompute_site_base_p50(scenarios: dict, wp_summary: list[dict]) -> None:
    total = sum(int(w.get("recovery_days") or 0) for w in wp_summary)
    site = scenarios.setdefault("site", {})
    bp = site.setdefault("base_p50", {})
    bp["recovery_days"] = total
    bp["delta_days"] = -total
    bp["case_count"] = sum(1 for w in wp_summary if (w.get("recovery_days") or 0) > 0)
    # expected_completion(AI 시나리오 완공)은 site.no_action ec - total 로 일관 갱신
    na = (site.get("no_action") or {}).get("expected_completion")
    if na:
        from datetime import date as _d, timedelta as _td
        try:
            bp["expected_completion"] = (_d.fromisoformat(na) - _td(days=total)).isoformat()
        except Exception:
            pass
```
  `view_builder.py` 결합 순서 (정확히 이 순서):
  1. (기존) scenarios 빌드 → wp_summary 빌드.
  2. **원본 `:2151-2154` kpi.recovery_days/recovered_completion 블록을 삭제**(중복·stale assignment 방지 — 단순 음영 아님).
  3. `assign_recovery_to_wp_summary(wp_summary, scenarios)` 호출(기존 `:2179-2185` 루프 대체).
  4. `recompute_site_base_p50(scenarios, wp_summary)` 호출.
  5. kpi 재파생을 **여기서**(recompute 뒤):
```python
    base_p50 = (scenarios.get("site") or {}).get("base_p50") or {}
    kpi["recovery_days"] = int(base_p50.get("recovery_days") or 0)
    kpi["recovered_completion"] = base_p50.get("expected_completion") or kpi.get("expected_completion")
```
  6. 직렬화 전 `_match` 메타 제거(내부 키가 `scenarios_jsonb` 로 새어나가지 않게):
```python
    for blk in (scenarios.get("by_wp") or {}).values():
        blk.pop("_match", None)
```
  (`scenarios`/`kpi`/`wp_summary` 가 `return` 되기 직전이면 OK.)

- [ ] **Step 4: 통과 확인** — Run: `cd pipeline && uv run pytest tests/optimizer/test_recovery_ssot.py -q` → PASS.

- [ ] **Step 5: 전체 optimizer 테스트 회귀** — Run: `cd pipeline && uv run pytest tests/optimizer/ -q -m "not slow"`
  Expected: 기존 테스트 PASS (특히 `test_scenarios_jsonb_llm.py`, `test_view_builder_v2.py`). site=Σby_wp를 단언하던 기존 테스트가 있으면 옵션 B 의도대로 갱신(보이는 합 기준).

- [ ] **Step 6: 커밋**
```bash
git add pipeline/agents/optimizer/view_builder.py pipeline/tests/optimizer/test_recovery_ssot.py
git commit -m "fix(optimizer): recovery_days SSOT — 회사명 정규화+wa귀속, site=Σ보이는WP (옵션 B)"
```

### Task 3.4: 데모 날짜 재생성 + tie-out 검증

**Files:** 없음(데이터 재생성). `scripts/backfill_daily_report_views_v2.py` 사용.

- [ ] **Step 1: 9/24 views 재생성 (deterministic, advice 재호출 X)** — Run:
```bash
cd pipeline && set -a; source ../.env.local; set +a && \
PYTHONPATH="$PWD/.." uv run python ../scripts/backfill_daily_report_views_v2.py \
  --date 2025-09-24 --site m15x-ph3-ibl
```
  Expected: 1 date built, 에러 0. (`--with-summary` 생략 — site_summary_text LLM 재호출 불필요. 단 생략 시 기존 site_summary_text 가 보존되는지 Step 2 에서 확인. 만약 NULL 로 덮이면 `--with-summary` 추가 — LLM 1회 호출, optimizer advice 는 재호출 X.)

- [ ] **Step 2: DB tie-out 검증** — Run:
```bash
/opt/homebrew/opt/libpq/bin/psql "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia" -At <<'SQL'
WITH latest AS (
  SELECT dr.scenarios_jsonb AS sc, dr.wp_summary_jsonb AS ws, dr.site_summary_text AS st
  FROM daily_reports dr JOIN pipeline_runs pr USING(run_id) JOIN sites s ON s.site_id=pr.site_id
  WHERE s.is_mock=FALSE AND dr.is_mock=FALSE AND pr.report_date='2025-09-24'
  ORDER BY dr.created_at DESC LIMIT 1)
SELECT 'wp_sum='||COALESCE(sum((e->>'recovery_days')::int),0) FROM latest, jsonb_array_elements(ws) e
UNION ALL SELECT 'site_base_p50='||(sc->'site'->'base_p50'->>'recovery_days') FROM latest
UNION ALL SELECT 'summary_null='||(st IS NULL)::text FROM latest;
SQL
```
  Expected: `wp_sum` == `site_base_p50` (tie-out). `summary_null=false`(요약 보존). 4개 "—" 중 정규화·wa 케이스(철근FAB·포장FAB·승강기CUB)가 값으로 채워졌는지 행별 확인(이전 검증 쿼리 재사용).

- [ ] **Step 3: UI tie-out 검증 (9/24)** — `make web2`(5537) 가동 후 Playwright MCP:
  `http://127.0.0.1:5537/reports?date=2025-09-24` → `browser_evaluate`로 WP목록 "공기 단축" 칼럼 합과 §03 "최적화 공기" 숫자 추출 → **동일** 확인. (Task 1 라벨이 Work Area 로 떠야 함.)

- [ ] **Step 4: 2번째 데모 날짜 재생성·검증** — 시연 시 띄울 다른 날짜(사용자 확인)에도 Step 1~3 반복. (spec-reviewer 권고: 보이는 모든 날짜 tie-out.)

- [ ] **Step 5: 커밋 불필요(데이터)** — 변경은 DB. 산출물 없음. 검증 결과만 보고.

---

## 검증 게이트 (전체)

1. `cd web && npx vitest run` → FE 단위 PASS.
2. `cd web && npx tsc --noEmit` → 타입 0.
3. `cd pipeline && uv run pytest tests/optimizer/ -q -m "not slow"` → BE PASS.
4. 9/24(+2번째 데모날짜) DB: `Σ wp_summary recovery_days == site.base_p50.recovery_days`.
5. 9/24 UI: WP목록 라벨 FAB/CUB, "공기 단축" 칼럼 합 == §03 "최적화 공기", §03 권고 카드 미노출.

## Out of scope

- 전체 530일 재생성(데모 후 일괄).
- 상세카드·분포도 라벨 FAB/CUB 통일(이번엔 WP목록만).
- fab/cub 스패닝 company의 advice 분할(1 advice → 2 wa) — 1회귀속으로 충분, 분할은 후속.
- `kpi.expected_completion` median 정합(기존 known-minor).
