# CPIA Reports 강화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** /reports 페이지의 4 영역 (업체별/공종별 생산성, 리스크 대안 검토, 공기단축 시나리오) 공란 해소 — Parser 시간대 가중 MH 환산 + EVM CPI 정상화 + WP by_wp dict lookup + scenarios_jsonb 신설.

**Architecture:** 7 task 로 분해. Task 0 = 가정 검증 (parser 시트2 cum 시계열 누적). Task 1~3 = BE 변경 (migration + mapper + view_builder + scenarios). Task 4~5 = FE 변경 (mock/report SELECT 확장 + page.tsx 어댑터). Task 6 = E2E. **각 BE↔FE 매칭 task 종결 직전 사용자 시각 검증 step 필수** (사용자 요구).

**Tech Stack:**
- BE: Python 3.11 + LangGraph + Azure OpenAI gpt-5.1 + PostgreSQL 16 + ChromaDB
- FE: Next.js 14 (App Router) + TypeScript + Tailwind
- Test: pytest (BE) + vitest (FE unit) + Playwright (E2E)

**Spec:** `docs/superpowers/specs/2026-05-19-cpia-reports-parser-mh-design.md`

**환경 (사용자 고정):**
- Python: `pipeline/.venv/bin/python3` 절대경로
- web dev: `npm run dev` (port 5536, 127.0.0.1)
- web test: `npm test` (vitest)
- pipeline cycle: `pipeline/.venv/bin/python3 scripts/run_one_cycle.py <xlsx> <site_id> <report_date>`
- PG: `.env` 의 `POSTGRES_URL` (로컬 5432 또는 prod tunnel 5532)
- 실 site_id: `m15x-ph3-ibl` (DB 소문자) vs FE `REPORT_SITE_ID = "M15X-Ph3-IBL"` (대소문자 drift — 본 cycle 외)
- 브랜치: A_Track (pipeline/ + web/ 동일 브랜치 OK — PoC cycle 분기 X)

---

## File Structure

### Create

| File | Responsibility |
|---|---|
| `infra/postgres/migrations/2026-05-19_scenarios_jsonb.sql` | `daily_reports.scenarios_jsonb` 컬럼 신설 |
| `pipeline/tests/test_mapper_weighted_mh.py` | mapper.py 가중 MH 헬퍼 2개 unit test |
| `pipeline/tests/test_optimizer_scenarios.py` | view_builder `_build_scenarios()` + percentile / 단조성 / cold_start unit test |
| `web/e2e/reports-real-data.spec.ts` | reports 페이지 E2E (WP 클릭 + scenarios 곡선 노출) |

### Modify

| File | 변경 |
|---|---|
| `pipeline/agents/mapper.py:476-502` | 8h 고정 prorate → 시간대 가중 헬퍼 `_weighted_mh_from_shift` / `_prorate_workers_with_mh` 추출 + 호출 |
| `pipeline/agents/optimizer/view_builder.py` (말미) | `_expand_recovery_to_days`, `_percentile`, `_scenario`, `_match_forecast`, `_build_scenarios` 5 helper 추가 |
| `pipeline/agents/optimizer/agent.py:170-196` | `optimize()` 의 view_jsonbs dict 에 `"scenarios_jsonb": _build_scenarios(advice_rows, forecast)` 한 줄 추가 |
| `web/app/api/mock/report/route.ts:7-17, 33-46` | SELECT 절에 `dr.scenarios_jsonb` 추가 + details build 에 `scenarios: r.scenarios_jsonb || {site: {}, by_wp: {}}` 추가 |
| `web/app/(app)/reports/page.tsx:14, 53, 59, 188` | type import + initial WP selection + diagnose 호출에 scenarios 전달 + OptimizerResult prop 어댑터 |
| `web/lib/fixtures.ts` | ReportDetail.optimizer shape (single → `{by_wp, default_wp_id}`), `scenarios?`, `ScenarioSet`, `Scenario` type 신규 |
| `web/lib/diagnosis-adapter.ts` | `toDiagnosisInput()` 의 4번째 optional param `scenarios?: ReportDetail["scenarios"]` 추가 + recovery 분기 |

---

## Task 0: Phase 0 — Parser 시트2 cum 시계열 누적 가정 검증

**가정 확인 — 이 가정 깨지면 Task 2 mapper 산식 전체 분기.** spec §3.1 V1.

**Files:**
- Run (no edits): 실 DB sample SQL 1 회

**Verification target:**
- `parser_job_allocations.workers_yesterday_cum.total + workers_today_incr.total ≈ workers_today_cum.total` (시계열 누적 가정 성립)
- 모든 row 가 `OK` → Task 1~6 진행
- 1 row 라도 `DRIFT` → spec §9 G-1 분기 (별 cycle 또는 spec 정정 후 재진입)

- [ ] **Step 1: 실 DB 에 검증 SQL 실행**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
PYTHONPATH=. pipeline/.venv/bin/python3 -c "
import asyncio
import os
from dotenv import load_dotenv
load_dotenv('.env')
from pipeline.db import PGClient

async def main():
    pg = PGClient(os.environ['POSTGRES_URL'])
    await pg.connect()
    rows = await pg._pool.fetch('''
        SELECT bp_code, company,
               (workers_yesterday_cum->>'total')::int AS y_total,
               (workers_today_incr->>'total')::int AS today_incr,
               (workers_today_cum->>'total')::int AS today_cum
        FROM parser_job_allocations
        WHERE final_flag='O'
          AND workers_yesterday_cum IS NOT NULL
          AND workers_today_incr IS NOT NULL
          AND workers_today_cum IS NOT NULL
        LIMIT 20
    ''')
    drift = 0
    for r in rows:
        y = r['y_total'] or 0
        i = r['today_incr'] or 0
        c = r['today_cum'] or 0
        ok = (y + i == c)
        if not ok:
            drift += 1
        print(f'{(r[\"company\"] or \"\")[:20]:20s}: {y:4d} + {i:3d} = {y+i:4d} vs cum {c:4d}  {\"OK\" if ok else \"DRIFT\"}')
    print(f'\\nTotal rows: {len(rows)}, DRIFT: {drift}')
    await pg.close()

asyncio.run(main())
"
```

Expected: 모든 row 가 `OK`, `DRIFT: 0`.

- [ ] **Step 2: 결과 분기 판단**

**시나리오 A (모든 row OK)**: 가정 성립. Task 1 로 진행.

**시나리오 B (DRIFT ≥ 1)**:
- 사용자에게 보고: 시계열 누적 가정 깨짐 — DRIFT row N건, sample data 첨부.
- spec §9 G-1 분기 토론 후 spec 정정. **Task 1~6 중단.**

**시나리오 C (rows 0건)**: parser_job_allocations 에 final_flag='O' + jsonb 다 채워진 row 없음. parser 실행 안 됨 또는 parser_post 가 시간대 jsonb 안 채움.
- 사용자에게 보고: parser 가 시트2 시간대 jsonb 적재 중인지 확인 필요.
- 본 plan 의 Task 2 mapper 변경 전에 parser 단계 점검 cycle 필요할 수 있음.

- [ ] **Step 3: V1 결과 요약을 plan 에 추가 commit (선택)**

만약 시나리오 A 확인되면 plan 본 파일에 검증 결과 한 줄 추가 + commit:

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
# (plan 파일에 "**V1 결과 (YYYY-MM-DD)**: parser_job_allocations N rows, DRIFT 0 — 가정 성립." 한 줄 추가)
git add docs/superpowers/plans/2026-05-19-cpia-reports-parser-mh-plan.md
git commit -m "docs(plan): Task 0 V1 검증 완료 — parser 시트2 cum 시계열 누적 가정 성립"
```

---

## Task 1: scenarios_jsonb 컬럼 추가 (migration)

**Files:**
- Create: `infra/postgres/migrations/2026-05-19_scenarios_jsonb.sql`

- [ ] **Step 1: migration 파일 작성**

```sql
-- 공기단축 예측 시나리오 jsonb — site 전체 + WP 별 4 시나리오
BEGIN;

ALTER TABLE daily_reports
  ADD COLUMN IF NOT EXISTS scenarios_jsonb JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN daily_reports.scenarios_jsonb IS
  'optimizer view_builder._build_scenarios() 산출. shape: {site: {no_action, optimistic_p25, base_p50, pessimistic_p75}, by_wp: {[wp_id]: 동일 4 키}}. 각 키 = {expected_completion: date, recovery_days: int, delta_days: int, case_count: int}.';

COMMIT;
```

- [ ] **Step 2: 실 DB 에 migration 적용**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
source <(grep -E '^(POSTGRES_URL)' .env | sed 's/^/export /')
psql "$POSTGRES_URL" -f infra/postgres/migrations/2026-05-19_scenarios_jsonb.sql
```

Expected output: `BEGIN`, `ALTER TABLE`, `COMMENT`, `COMMIT`.

- [ ] **Step 3: 컬럼 추가 검증 SQL**

```bash
psql "$POSTGRES_URL" -c "
  SELECT column_name, data_type, column_default
  FROM information_schema.columns
  WHERE table_name = 'daily_reports' AND column_name = 'scenarios_jsonb';
"
```

Expected:
```
  column_name   | data_type |   column_default
----------------+-----------+--------------------
 scenarios_jsonb | jsonb     | '{}'::jsonb
```

- [ ] **Step 4: Commit**

```bash
git add infra/postgres/migrations/2026-05-19_scenarios_jsonb.sql
git commit -m "db: add scenarios_jsonb column to daily_reports

공기단축 예측 시나리오 (낙관/기준/비관) 적재용 jsonb 컬럼.
shape: {site: {no_action, optimistic_p25, base_p50, pessimistic_p75}, by_wp: {...}}.
optimizer view_builder._build_scenarios() 가 채움 (별 task).
default {}::jsonb 라 기존 row 영향 0."
```

---

## Task 2: mapper.py 시간대 가중 MH 환산

**Files:**
- Create: `pipeline/tests/test_mapper_weighted_mh.py`
- Modify: `pipeline/agents/mapper.py` (모듈 상수 + 헬퍼 2개 추가 + line 476-502 교체)

- [ ] **Step 1: failing test 작성 — `_weighted_mh_from_shift` 헬퍼**

`pipeline/tests/test_mapper_weighted_mh.py` 신설:

```python
"""mapper.py 시간대 가중 MH 환산 헬퍼 단위 테스트.

spec §3.3 + §7 V2.
"""

from __future__ import annotations

import pytest

from pipeline.agents.mapper import _weighted_mh_from_shift, _prorate_workers_with_mh


# ============================================================
# _weighted_mh_from_shift
# ============================================================

def test_weighted_mh_daytime_only():
    """주간 10명 → 10 × 8 = 80 MH."""
    shift = {"morning": 0, "daytime": 10, "overtime": 0, "night": 0, "all_night": 0, "total": 10}
    assert _weighted_mh_from_shift(shift) == 80.0


def test_weighted_mh_mixed_shifts():
    """주간 10 + 연장 5 + 야간 2 → 80 + 20 + 16 = 116."""
    shift = {"morning": 0, "daytime": 10, "overtime": 5, "night": 2, "all_night": 0, "total": 17}
    assert _weighted_mh_from_shift(shift) == 116.0


def test_weighted_mh_all_night():
    """철야 3 → 3 × 12 = 36."""
    shift = {"morning": 0, "daytime": 0, "overtime": 0, "night": 0, "all_night": 3, "total": 3}
    assert _weighted_mh_from_shift(shift) == 36.0


def test_weighted_mh_morning_overtime():
    """조출 4 + 연장 4 → 4×2 + 4×4 = 24."""
    shift = {"morning": 4, "daytime": 0, "overtime": 4, "night": 0, "all_night": 0, "total": 8}
    assert _weighted_mh_from_shift(shift) == 24.0


def test_weighted_mh_none():
    """None → 0."""
    assert _weighted_mh_from_shift(None) == 0.0


def test_weighted_mh_empty_dict():
    """빈 dict → 0."""
    assert _weighted_mh_from_shift({}) == 0.0


def test_weighted_mh_missing_keys():
    """일부 키 누락 → 누락 키 0 처리."""
    shift = {"daytime": 5}  # 그 외 없음
    assert _weighted_mh_from_shift(shift) == 40.0
```

- [ ] **Step 2: test 실행 — fail 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
PYTHONPATH=. pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_mapper_weighted_mh.py -v
```

Expected: `ImportError: cannot import name '_weighted_mh_from_shift' from 'pipeline.agents.mapper'` (또는 동등).

- [ ] **Step 3: `_weighted_mh_from_shift` 헬퍼 구현**

`pipeline/agents/mapper.py` 의 모듈 상위 (import 직후, 다른 함수 정의 전) 에 추가:

```python
# ============================================================
# 시간대 가중 MH 환산 (spec 2026-05-19 §3.2~3.3)
# ============================================================

_SHIFT_WEIGHTS = {
    "morning":   2.0,   # 조출
    "daytime":   8.0,   # 주간 표준
    "overtime":  4.0,   # 연장
    "night":     8.0,   # 야간
    "all_night": 12.0,  # 철야
}


def _weighted_mh_from_shift(shift_dict: dict | None) -> float:
    """시트2 workers_today_cum jsonb (TimeShiftCounts) → 가중 MH.

    spec §3.2 가중치 (조출 2 / 주간 8 / 연장 4 / 야간 8 / 철야 12) 적용.
    None / 빈 dict / 키 누락 → 0.0 처리.
    """
    if not shift_dict:
        return 0.0
    return sum(
        float(shift_dict.get(k, 0) or 0) * w
        for k, w in _SHIFT_WEIGHTS.items()
    )
```

- [ ] **Step 4: test 실행 — 7개 통과 확인**

```bash
PYTHONPATH=. pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_mapper_weighted_mh.py::test_weighted_mh_daytime_only pipeline/tests/test_mapper_weighted_mh.py::test_weighted_mh_mixed_shifts pipeline/tests/test_mapper_weighted_mh.py::test_weighted_mh_all_night pipeline/tests/test_mapper_weighted_mh.py::test_weighted_mh_morning_overtime pipeline/tests/test_mapper_weighted_mh.py::test_weighted_mh_none pipeline/tests/test_mapper_weighted_mh.py::test_weighted_mh_empty_dict pipeline/tests/test_mapper_weighted_mh.py::test_weighted_mh_missing_keys -v
```

Expected: `7 passed`.

- [ ] **Step 5: `_prorate_workers_with_mh` test 추가**

`pipeline/tests/test_mapper_weighted_mh.py` 에 추가:

```python
# ============================================================
# _prorate_workers_with_mh
# ============================================================

def test_prorate_plan_mh_basic():
    """company A: 주간 100명 → 800 MH. l6-1 plan_mh=600, l6-2=200 → 600/200 분배."""
    parsed_report = {
        "job_allocations": [{
            "company": "A", "final_flag": "O",
            "workers_today_cum": {"morning": 0, "daytime": 100, "overtime": 0, "night": 0, "all_night": 0, "total": 100},
        }],
    }
    mapped = [
        {"company": "A", "l6_main": "l6-1", "plan_mh": 600.0},
        {"company": "A", "l6_main": "l6-2", "plan_mh": 200.0},
    ]
    company_total_plan_mh = {"A": 800.0}
    active_l6_for_company = {"A": {"l6-1", "l6-2"}}
    out = _prorate_workers_with_mh(mapped, parsed_report, company_total_plan_mh, active_l6_for_company)
    assert out[0]["cum_actual_mh_today"] == 600.0
    assert out[1]["cum_actual_mh_today"] == 200.0
    assert out[0]["prorate_method"] == "plan_mh"
    assert out[1]["prorate_method"] == "plan_mh"


def test_prorate_uniform_fallback():
    """plan_mh 없으면 균등 분배. 주간 60명 → 480 MH, 2개 l6 → 240/240."""
    parsed_report = {
        "job_allocations": [{
            "company": "B", "final_flag": "O",
            "workers_today_cum": {"morning": 0, "daytime": 60, "overtime": 0, "night": 0, "all_night": 0, "total": 60},
        }],
    }
    mapped = [
        {"company": "B", "l6_main": "l6-x", "plan_mh": 0},
        {"company": "B", "l6_main": "l6-y", "plan_mh": 0},
    ]
    company_total_plan_mh = {"B": 0.0}
    active_l6_for_company = {"B": {"l6-x", "l6-y"}}
    out = _prorate_workers_with_mh(mapped, parsed_report, company_total_plan_mh, active_l6_for_company)
    assert out[0]["cum_actual_mh_today"] == 240.0
    assert out[1]["cum_actual_mh_today"] == 240.0
    assert out[0]["prorate_method"] == "uniform_fallback"


def test_prorate_ignores_final_flag_x():
    """final_flag='X' 인 job_allocation 은 가산 X. → 0 MH."""
    parsed_report = {
        "job_allocations": [{
            "company": "C", "final_flag": "X",  # ← skip
            "workers_today_cum": {"morning": 0, "daytime": 100, "overtime": 0, "night": 0, "all_night": 0, "total": 100},
        }],
    }
    mapped = [{"company": "C", "l6_main": "l6-1", "plan_mh": 100.0}]
    company_total_plan_mh = {"C": 100.0}
    active_l6_for_company = {"C": {"l6-1"}}
    out = _prorate_workers_with_mh(mapped, parsed_report, company_total_plan_mh, active_l6_for_company)
    # company_weighted_mh[C] = 0 (skip), plan_mh > 0 → 0 * (100/100) = 0
    assert out[0]["cum_actual_mh_today"] == 0.0
    assert out[0]["prorate_method"] == "plan_mh"


def test_prorate_skips_activity_without_l6_main():
    """l6_main 가 None 인 activity 는 cum_actual_mh_today 박지 않음 (passthrough)."""
    parsed_report = {
        "job_allocations": [{
            "company": "D", "final_flag": "O",
            "workers_today_cum": {"morning": 0, "daytime": 10, "overtime": 0, "night": 0, "all_night": 0, "total": 10},
        }],
    }
    mapped = [{"company": "D", "l6_main": None, "plan_mh": 0}]
    company_total_plan_mh = {}
    active_l6_for_company = {}
    out = _prorate_workers_with_mh(mapped, parsed_report, company_total_plan_mh, active_l6_for_company)
    assert "cum_actual_mh_today" not in out[0]


def test_prorate_cum_workers_today_is_mh_div_8():
    """cum_workers_today (BI 호환) = cum_actual_mh_today / 8.0."""
    parsed_report = {
        "job_allocations": [{
            "company": "E", "final_flag": "O",
            "workers_today_cum": {"morning": 0, "daytime": 80, "overtime": 0, "night": 0, "all_night": 0, "total": 80},
        }],
    }
    mapped = [{"company": "E", "l6_main": "l6-1", "plan_mh": 100.0}]
    company_total_plan_mh = {"E": 100.0}
    active_l6_for_company = {"E": {"l6-1"}}
    out = _prorate_workers_with_mh(mapped, parsed_report, company_total_plan_mh, active_l6_for_company)
    # 80 × 8 = 640 MH, ÷ 8 = 80 workers
    assert out[0]["cum_actual_mh_today"] == 640.0
    assert out[0]["cum_workers_today"] == 80.0
```

- [ ] **Step 6: test 실행 — 5개 fail 확인**

```bash
PYTHONPATH=. pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_mapper_weighted_mh.py -v -k "prorate"
```

Expected: 5 fails on `ImportError: cannot import name '_prorate_workers_with_mh'`.

- [ ] **Step 7: `_prorate_workers_with_mh` 헬퍼 구현**

`pipeline/agents/mapper.py` 의 `_weighted_mh_from_shift` 직후에 추가:

```python
def _prorate_workers_with_mh(
    mapped: list[dict],
    parsed_report: dict,
    company_total_plan_mh: dict[str, float],
    active_l6_for_company: dict[str, set[str]],
) -> list[dict]:
    """company 단위 시간대 가중 누적 MH 산출 후 l6 비례 분배.

    spec §3.3.
    """
    # 1. company 단위 시간대 가중 누적 MH 합 (final_flag='O' 만)
    company_weighted_mh: dict[str, float] = {}
    for ja in parsed_report.get("job_allocations", []):
        if ja.get("final_flag") != "O":
            continue
        c = ja.get("company")
        if c:
            mh = _weighted_mh_from_shift(ja.get("workers_today_cum"))
            company_weighted_mh[c] = company_weighted_mh.get(c, 0.0) + mh

    # 2. l6 비례 분배
    prorated: list[dict] = []
    for a in mapped:
        if a.get("l6_main"):
            c = a["company"]
            weighted_mh_c = company_weighted_mh.get(c, 0.0)
            company_mh = company_total_plan_mh.get(c, 0.0)
            plan_mh_val = float(a.get("plan_mh") or 0)
            n_l6 = len(active_l6_for_company.get(c, set())) if c else 0
            if company_mh > 0 and plan_mh_val > 0:
                cum_actual_mh = weighted_mh_c * (plan_mh_val / company_mh)
                prorate_method = "plan_mh"
            elif n_l6 > 0:
                cum_actual_mh = weighted_mh_c / n_l6
                prorate_method = "uniform_fallback"
            else:
                cum_actual_mh = 0.0
                prorate_method = "zero"
            a = {
                **a,
                "cum_actual_mh_today": cum_actual_mh,
                "cum_workers_today": cum_actual_mh / 8.0,
                "prorate_method": prorate_method,
            }
        prorated.append(a)
    return prorated
```

- [ ] **Step 8: test 실행 — 12개 모두 통과 확인**

```bash
PYTHONPATH=. pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_mapper_weighted_mh.py -v
```

Expected: `12 passed`.

- [ ] **Step 9: 기존 mapper.py:476-502 inline 로직을 헬퍼 호출로 교체**

`pipeline/agents/mapper.py` 의 line 476-502 (현 `for a in out: ...` 블록) 을 삭제하고 한 줄로 교체:

```python
# 변경 전 (line 475-502):
prorated: list[Activity] = []
for a in out:
    if a.get("l6_main"):
        c = a["company"]
        workers_c = job_alloc_company_sum.get(c, 0)
        ...
        a["cum_workers_today"] = ...
        a["cum_actual_mh_today"] = a["cum_workers_today"] * 8.0
    prorated.append(a)

# 변경 후:
prorated = _prorate_workers_with_mh(
    out,
    parsed_report,
    company_total_plan_mh,
    active_l6_for_company,
)
```

또한 `job_alloc_company_sum` 산출 블록 (line 452-460) 은 더 이상 사용 안 되므로 삭제. `company_total_plan_mh` (line 463-467) 와 `active_l6_for_company` (line 470-473) 는 유지.

- [ ] **Step 10: 기존 mapper test 전체 실행 — regression 확인**

```bash
PYTHONPATH=. pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_mapper_u1b.py pipeline/tests/test_mapper_u1a.py pipeline/tests/test_prorate_mh.py -v
```

Expected: 모두 통과. **만약 fail → 산식 변경으로 기존 expected 값이 깨진 것** — 해당 test 의 expected 값을 spec §3 산식대로 재계산해서 갱신 (test 자체가 잘못된 가정이라면 수정 OK).

- [ ] **Step 11: Commit**

```bash
git add pipeline/agents/mapper.py pipeline/tests/test_mapper_weighted_mh.py
git commit -m "mapper: replace 8h fixed prorate with shift-weighted MH

mapper.py:476-502 의 8h 고정 산식 (workers_c × 8.0) 을 시간대 가중 헬퍼로 교체.
- _weighted_mh_from_shift: 시트2 workers_today_cum jsonb → 가중 MH (조출2/주간8/연장4/야간8/철야12)
- _prorate_workers_with_mh: company 단위 누적 MH 산출 후 l6 비례 분배 (기존 fallback 보존)

cum_actual_mh_today 의 의미가 단일 일자치 → 시계열 누적 (시트2 cum 패턴 그대로) 으로 fix.
downstream view_builder EVM CPI 가 자동 정합화.

test_mapper_weighted_mh.py 12 case + 기존 mapper test regression 0.
spec: docs/superpowers/specs/2026-05-19-cpia-reports-parser-mh-design.md §3.3"
```

---

## Task 3: optimizer view_builder `_build_scenarios` + agent UPSERT

**Files:**
- Create: `pipeline/tests/test_optimizer_scenarios.py`
- Modify: `pipeline/agents/optimizer/view_builder.py` (말미에 헬퍼 5개 추가)
- Modify: `pipeline/agents/optimizer/agent.py:177` (view_jsonbs dict 에 한 줄 추가)

- [ ] **Step 1: failing test 작성 — scenarios 산식**

`pipeline/tests/test_optimizer_scenarios.py` 신설:

```python
"""view_builder._build_scenarios 단위 테스트.

spec §5 + §7 V4.
"""

from __future__ import annotations

from datetime import date

import pytest

from pipeline.agents.optimizer.view_builder import (
    _build_scenarios,
    _expand_recovery_to_days,
    _percentile,
)


# ============================================================
# _expand_recovery_to_days
# ============================================================

def test_expand_recovery_basic():
    """{'d+1': 2, 'd+3': 3} → [1,1,3,3,3]."""
    out = _expand_recovery_to_days({"d+1": 2, "d+3": 3})
    assert sorted(out) == [1, 1, 3, 3, 3]


def test_expand_recovery_not_recovered_cap():
    """not_recovered → +30 일 캡."""
    out = _expand_recovery_to_days({"d+5": 2, "not_recovered": 3})
    assert sorted(out) == [5, 5, 30, 30, 30]


def test_expand_recovery_empty():
    """빈 dict → 빈 list."""
    assert _expand_recovery_to_days({}) == []
    assert _expand_recovery_to_days(None) == []


# ============================================================
# _percentile
# ============================================================

def test_percentile_monotonic():
    """[1,2,3,4,5,6,7,8,9,10] 에서 p25 ≤ p50 ≤ p75."""
    days = list(range(1, 11))
    p25 = _percentile(days, 0.25)
    p50 = _percentile(days, 0.50)
    p75 = _percentile(days, 0.75)
    assert p25 <= p50 <= p75


def test_percentile_empty():
    """빈 list → 0."""
    assert _percentile([], 0.5) == 0


def test_percentile_single_value():
    """1개 → 그 값."""
    assert _percentile([7], 0.5) == 7


# ============================================================
# _build_scenarios
# ============================================================

def test_scenarios_basic():
    """advice 1건 + forecast 1건 → site + by_wp 각각 4 시나리오."""
    advice_rows = [{
        "company": "A", "l6_main": "L6",
        "recovery_distribution": {"d+5": 3, "d+10": 2, "d+3": 5},
    }]
    forecast = [{
        "company": "A", "l6_main": "L6", "wa": "WA-1",
        "expected_completion": date(2026, 12, 31),
    }]
    out = _build_scenarios(advice_rows, forecast)
    
    # site 의 4 키 존재
    assert set(out["site"].keys()) == {"no_action", "optimistic_p25", "base_p50", "pessimistic_p75"}
    # no_action delta_days = 0
    assert out["site"]["no_action"]["delta_days"] == 0
    # 단조성: p25 ≤ p50 ≤ p75 (recovery_days)
    assert (
        out["site"]["optimistic_p25"]["recovery_days"]
        <= out["site"]["base_p50"]["recovery_days"]
        <= out["site"]["pessimistic_p75"]["recovery_days"]
    )
    # delta_days = -recovery_days
    assert out["site"]["base_p50"]["delta_days"] == -out["site"]["base_p50"]["recovery_days"]
    
    # by_wp 의 WP_ID 존재
    wp_id = "wa-1-l6-a"  # _wp_id_of (kebab) 의 결과
    assert wp_id in out["by_wp"]


def test_scenarios_cold_start():
    """advice 0건 → site no_action only, by_wp 빈 dict."""
    out = _build_scenarios([], [])
    assert out["by_wp"] == {}
    # site no_action 존재 + delta=0
    assert out["site"]["no_action"]["delta_days"] == 0
    # base_p50 도 delta=0 (cases 없으므로)
    assert out["site"]["base_p50"]["delta_days"] == 0


def test_scenarios_not_recovered_only():
    """recovery_distribution 이 not_recovered 만 → percentile 모두 30 (캡)."""
    advice_rows = [{
        "company": "A", "l6_main": "L6",
        "recovery_distribution": {"not_recovered": 5},
    }]
    forecast = [{
        "company": "A", "l6_main": "L6", "wa": "WA-1",
        "expected_completion": date(2026, 12, 31),
    }]
    out = _build_scenarios(advice_rows, forecast)
    assert out["site"]["base_p50"]["recovery_days"] == 30


def test_scenarios_forecast_mismatch_skipped():
    """advice 의 (company, l6_main) 이 forecast 에 없으면 by_wp 미포함."""
    advice_rows = [{
        "company": "A", "l6_main": "L6",
        "recovery_distribution": {"d+3": 3},
    }]
    forecast = [{
        "company": "DIFFERENT", "l6_main": "L6", "wa": "WA-1",
        "expected_completion": date(2026, 12, 31),
    }]
    out = _build_scenarios(advice_rows, forecast)
    assert out["by_wp"] == {}
    # site 는 여전히 advice 의 recovery 집계
    assert out["site"]["base_p50"]["recovery_days"] == 3
```

- [ ] **Step 2: test 실행 — fail 확인**

```bash
PYTHONPATH=. pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_optimizer_scenarios.py -v
```

Expected: 모두 fail (헬퍼 미정의).

- [ ] **Step 3: view_builder.py 말미에 헬퍼 5개 추가**

`pipeline/agents/optimizer/view_builder.py` 의 파일 끝에 추가:

```python
# ============================================================
# 공기단축 시나리오 (spec 2026-05-19 §5)
# ============================================================

from datetime import timedelta


def _expand_recovery_to_days(dist: dict | None) -> list[int]:
    """recovery_distribution → percentile 산출 가능한 list.
    
    spec §5.2 Step 1. not_recovered 는 +30 일 캡.
    """
    out: list[int] = []
    for key, count in (dist or {}).items():
        if key == "not_recovered":
            out.extend([30] * int(count))
        elif key.startswith("d+"):
            try:
                d = int(key[2:])
                out.extend([d] * int(count))
            except ValueError:
                continue
    return out


def _percentile(days: list[int], q: float) -> int:
    """q in [0, 1]. 빈 list → 0. spec §5.2 Step 2."""
    if not days:
        return 0
    sorted_days = sorted(days)
    if len(sorted_days) < 4:
        idx = min(len(sorted_days) - 1, int(q * len(sorted_days)))
        return sorted_days[idx]
    cuts = statistics.quantiles(sorted_days, n=100, method="inclusive")
    return int(round(cuts[max(0, min(98, int(q * 100) - 1))]))


def _match_forecast_by_company_l6(advice: dict, forecast: list[dict]) -> dict | None:
    """(company, l6_main) 매칭. spec §5.2.
    
    view_builder._build_optimizer_view 의 :561-566 패턴과 동일 — 두 호출자 공유.
    """
    return next(
        (f for f in forecast
         if f.get("company") == advice.get("company")
         and f.get("l6_main") == advice.get("l6_main")),
        None,
    )


def _scenario(no_action_date, recovery_days: int, case_count: int) -> dict:
    """단일 시나리오 dict 빌드. spec §5.2 Step 3."""
    if no_action_date is None or recovery_days <= 0:
        return {
            "expected_completion": no_action_date.isoformat() if no_action_date else None,
            "recovery_days": recovery_days,
            "delta_days": 0,
            "case_count": case_count,
        }
    new_date = no_action_date - timedelta(days=recovery_days)
    return {
        "expected_completion": new_date.isoformat(),
        "recovery_days": recovery_days,
        "delta_days": -recovery_days,
        "case_count": case_count,
    }


def _build_scenarios(advice_rows: list[dict], forecast: list[dict]) -> dict:
    """공기단축 4 시나리오 산출 — site + by_wp.
    
    spec §5.1 shape + §5.2 산식.
    """
    # site 전체: 모든 advice 의 recovery_distribution merge
    site_days: list[int] = []
    for advice in advice_rows:
        site_days.extend(_expand_recovery_to_days(advice.get("recovery_distribution") or {}))
    
    # site no_action expected_completion: forecast 의 MAX
    site_no_action = None
    if forecast:
        ecs = [f.get("expected_completion") for f in forecast if f.get("expected_completion")]
        site_no_action = max(ecs) if ecs else None
    
    site_scenarios = {
        "no_action": {
            "expected_completion": site_no_action.isoformat() if site_no_action else None,
            "recovery_days": 0,
            "delta_days": 0,
            "case_count": len(site_days),
        },
        "optimistic_p25":  _scenario(site_no_action, _percentile(site_days, 0.25), len(site_days)),
        "base_p50":        _scenario(site_no_action, _percentile(site_days, 0.50), len(site_days)),
        "pessimistic_p75": _scenario(site_no_action, _percentile(site_days, 0.75), len(site_days)),
    }
    
    # by_wp: advice 별 매칭 forecast 에서 wa lookup → wp_id
    by_wp: dict[str, dict] = {}
    for advice in advice_rows:
        f = _match_forecast_by_company_l6(advice, forecast)
        if f is None:
            continue
        wp_id = _wp_id_of(f.get("wa"), advice.get("l6_main"), advice.get("company"))
        wp_days = _expand_recovery_to_days(advice.get("recovery_distribution") or {})
        wp_no_action = f.get("expected_completion")
        by_wp[wp_id] = {
            "no_action": {
                "expected_completion": wp_no_action.isoformat() if wp_no_action else None,
                "recovery_days": 0,
                "delta_days": 0,
                "case_count": len(wp_days),
            },
            "optimistic_p25":  _scenario(wp_no_action, _percentile(wp_days, 0.25), len(wp_days)),
            "base_p50":        _scenario(wp_no_action, _percentile(wp_days, 0.50), len(wp_days)),
            "pessimistic_p75": _scenario(wp_no_action, _percentile(wp_days, 0.75), len(wp_days)),
        }
    
    return {"site": site_scenarios, "by_wp": by_wp}
```

- [ ] **Step 4: test 실행 — 11개 통과 확인**

```bash
PYTHONPATH=. pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_optimizer_scenarios.py -v
```

Expected: `11 passed`.

- [ ] **Step 5: optimizer/agent.py 의 view_jsonbs dict 에 한 줄 추가**

`pipeline/agents/optimizer/agent.py:177-187` 의 view_jsonbs dict 정의에 추가:

```python
# 변경 전:
view_jsonbs = {
    "productivity_jsonb": productivity,
    "kpi_jsonb": await _build_kpi(pg, site_id, today, productivity),
    "contractor_bars_jsonb": _build_contractor_bars(productivity),
    "trade_bars_jsonb": _build_trade_bars(productivity),
    "quadrant_jsonb": quadrant,
    "wp_summary_jsonb": await _build_wp_summary(pg, site_id, today, productivity, quadrant),
    "s_curve_jsonb": await _build_s_curve(pg, site_id, today),
    "optimizer_view_jsonb": _build_optimizer_view(advice_rows, forecast, mapped),
}

# 변경 후 (마지막 줄 추가):
view_jsonbs = {
    "productivity_jsonb": productivity,
    "kpi_jsonb": await _build_kpi(pg, site_id, today, productivity),
    "contractor_bars_jsonb": _build_contractor_bars(productivity),
    "trade_bars_jsonb": _build_trade_bars(productivity),
    "quadrant_jsonb": quadrant,
    "wp_summary_jsonb": await _build_wp_summary(pg, site_id, today, productivity, quadrant),
    "s_curve_jsonb": await _build_s_curve(pg, site_id, today),
    "optimizer_view_jsonb": _build_optimizer_view(advice_rows, forecast, mapped),
    "scenarios_jsonb": _build_scenarios(advice_rows, forecast),  # ← 신규
}
```

import 도 추가 (agent.py 상단 view_builder import 블록에 `_build_scenarios` 추가):

```python
from pipeline.agents.optimizer.view_builder import (
    _build_contractor_bars,
    _build_kpi,
    _build_optimizer_view,
    _build_productivity_views,
    _build_quadrant,
    _build_s_curve,
    _build_scenarios,   # ← 신규
    _build_trade_bars,
    _build_wp_summary,
)
```

- [ ] **Step 6: 기존 optimizer test regression 확인**

```bash
PYTHONPATH=. pipeline/.venv/bin/python3 -m pytest pipeline/tests/optimizer/ -v
```

Expected: 모두 통과 (regression 0).

- [ ] **Step 7: 실 pipeline run 1회 실행 — Task 1~3 정합 검증 (V3)**

Task 0 시나리오 A 의 sample xlsx 사용 (예: `docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx`). site_id 는 sites.site_id 의 실 값 (예: `m15x-ph3-ibl`).

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 scripts/run_one_cycle.py \
  "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx" \
  m15x-ph3-ibl \
  2025-09-25 \
  2>/tmp/run_one_cycle.log
```

Expected: stderr 에 `[parser_llm]` 로그, completed 후 `pipeline_runs.status='completed'`.

- [ ] **Step 8: V3 정합 검증 — kpi_jsonb / productivity_jsonb / scenarios_jsonb 실 값 확인**

```bash
source <(grep -E '^(POSTGRES_URL)' .env | sed 's/^/export /')
psql "$POSTGRES_URL" -c "
  SELECT pr.report_date,
         dr.kpi_jsonb->>'productivity_today' AS cpi,
         dr.kpi_jsonb->>'spi' AS spi,
         dr.productivity_jsonb->'today'->>'ac' AS ac,
         dr.productivity_jsonb->'today'->>'pv' AS pv,
         dr.productivity_jsonb->'today'->>'ev' AS ev,
         jsonb_array_length(dr.contractor_bars_jsonb) AS n_contractors,
         dr.scenarios_jsonb->'site'->'base_p50'->>'recovery_days' AS p50_days
  FROM daily_reports dr
  JOIN pipeline_runs pr USING (run_id)
  WHERE pr.site_id = 'm15x-ph3-ibl'
  ORDER BY pr.report_date DESC LIMIT 1;
"
```

Expected 검증 기준 (spec §7 V3):
- `cpi` ∈ [50, 150] 범위 (현 폭주 X)
- `spi` > 0
- `ac` 와 `pv` 같은 자릿수 (3~4배 차이 이내)
- `n_contractors` ≥ 1
- `p50_days` 가 정수 (0 또는 양수)

만약 cpi 가 여전히 폭주 (>1000) → mapper 산식 변경이 반영 안 됨. step 9 ~ 10 단계 재실행.

- [ ] **Step 9: Commit**

```bash
git add pipeline/agents/optimizer/view_builder.py pipeline/agents/optimizer/agent.py pipeline/tests/test_optimizer_scenarios.py
git commit -m "optimizer: add _build_scenarios + scenarios_jsonb upsert

view_builder 말미에 5 helper 추가:
- _expand_recovery_to_days: recovery_distribution dict → 일수 list (not_recovered=+30 cap)
- _percentile: statistics.quantiles 기반 percentile (cold_start graceful degrade)
- _match_forecast_by_company_l6: (company, l6_main) lookup (_build_optimizer_view 와 공유)
- _scenario: 단일 시나리오 dict 빌드 (recovery_days <= 0 → no_action 패스)
- _build_scenarios: site (전 advice merge) + by_wp 4 시나리오 산출

agent.py optimize() 의 view_jsonbs 에 scenarios_jsonb 한 줄 추가 → daily_reports UPSERT.

test_optimizer_scenarios.py 11 case (basic / cold_start / not_recovered cap / forecast mismatch).
spec §5.1~5.4."
```

---

## Task 4: web mock/report SELECT 확장 + types

**Files:**
- Modify: `web/app/api/mock/report/route.ts` (SELECT 1 컬럼 + details 1 키 추가)
- Modify: `web/lib/fixtures.ts` (ReportDetail.optimizer shape 정정, ScenarioSet/Scenario 신규)

**중요 (사용자 요구)**: 본 task 종결 직전 dev 서버 띄우고 endpoint 응답 직접 확인 (시각 검증).

- [ ] **Step 1: route.ts SELECT 절에 scenarios_jsonb 추가**

`web/app/api/mock/report/route.ts:7-17` 의 SELECT 절에 한 줄 추가:

```typescript
// 변경 전:
const rows = await (sql as any)`
  SELECT pr.report_date,
         dr.kpi_jsonb, dr.contractor_bars_jsonb, dr.trade_bars_jsonb,
         dr.quadrant_jsonb, dr.wp_summary_jsonb, dr.s_curve_jsonb,
         dr.optimizer_view_jsonb, dr.productivity_jsonb
  FROM daily_reports dr
  JOIN pipeline_runs pr USING (run_id)
  JOIN sites s ON s.site_id = pr.site_id
  WHERE s.is_mock = FALSE
  ORDER BY pr.report_date DESC
`;

// 변경 후:
const rows = await (sql as any)`
  SELECT pr.report_date,
         dr.kpi_jsonb, dr.contractor_bars_jsonb, dr.trade_bars_jsonb,
         dr.quadrant_jsonb, dr.wp_summary_jsonb, dr.s_curve_jsonb,
         dr.optimizer_view_jsonb, dr.productivity_jsonb,
         dr.scenarios_jsonb
  FROM daily_reports dr
  JOIN pipeline_runs pr USING (run_id)
  JOIN sites s ON s.site_id = pr.site_id
  WHERE s.is_mock = FALSE
  ORDER BY pr.report_date DESC
`;
```

- [ ] **Step 2: details build 에 scenarios 추가**

`web/app/api/mock/report/route.ts:33-46` 의 `details[date] = {...}` 객체에 한 줄 추가:

```typescript
details[date] = {
  kpi: r.kpi_jsonb || {},
  s_curve: r.s_curve_jsonb || [],
  contractor_bars: r.contractor_bars_jsonb || [],
  trade_bars: r.trade_bars_jsonb || [],
  quadrant: r.quadrant_jsonb || [],
  optimizer: r.optimizer_view_jsonb || { by_wp: {}, default_wp_id: null },
  scenarios: r.scenarios_jsonb || { site: {}, by_wp: {} },   // ← 신규
  wp_summary: r.wp_summary_jsonb || [],
  raw_data: [],
};
```

- [ ] **Step 3: fixtures.ts ReportDetail type 정정 + 신규 type**

`web/lib/fixtures.ts` 의 ReportDetail type 수정:

```typescript
export type Scenario = {
  expected_completion: string | null;
  recovery_days: number;
  delta_days: number;
  case_count: number;
};

export type ScenarioSet = {
  no_action: Scenario;
  optimistic_p25: Scenario;
  base_p50: Scenario;
  pessimistic_p75: Scenario;
};

export type OptimizerByWp = {
  by_wp: Record<string, OptimizerOutput>;
  default_wp_id: string | null;
};

export type ReportDetail = {
  kpi: ReportKpi;
  s_curve: SCurvePoint[];
  contractor_bars: BarItem[];
  trade_bars: BarItem[];
  quadrant: QuadrantPoint[];
  optimizer: OptimizerByWp;                  // ← 변경 (single → by_wp dict)
  scenarios?: {                              // ← 신규
    site?: Partial<ScenarioSet>;
    by_wp?: Record<string, ScenarioSet>;
  };
  wp_summary: any[];
  raw_data: any[];
};
```

**주의**: `optimizer` 의 기존 사용처가 single `OptimizerOutput` 으로 잡혀있을 수 있음. type 변경 후 TypeScript 컴파일 오류가 page.tsx:188 등에서 발생 — Task 5 에서 해결. 본 task 의 npm run build 는 fail 해도 OK (Task 5 후 통과).

- [ ] **Step 4: type 추가 검증 (vitest type check 생략 — Task 5 후 일괄)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/web"
npx tsc --noEmit 2>&1 | grep -E "(fixtures|reports/page)" | head -20
```

Expected: `reports/page.tsx` 에서 `Property 'by_wp' does not exist...` 류 에러 발생 (예상된 컴파일 오류, Task 5 에서 해소).

- [ ] **Step 5: 사용자 시각 검증 — dev 서버에서 endpoint 응답 직접 확인 (FE↔BE 매칭 step)**

먼저 dev 서버 띄우기:

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/web"
npm run dev
# 또는 background:
# (npm run dev > /tmp/web-dev.log 2>&1 &)
```

server ready 대기 (출력 `Local: http://127.0.0.1:5536` 확인).

별 터미널에서:

```bash
curl -s http://127.0.0.1:5536/api/mock/report | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'daily rows: {len(data[\"daily\"])}')
dates = list(data['details'].keys())
print(f'first date: {dates[0] if dates else None}')
if dates:
    d = data['details'][dates[0]]
    print(f'  optimizer.by_wp keys: {list(d[\"optimizer\"][\"by_wp\"].keys())[:3]}')
    print(f'  optimizer.default_wp_id: {d[\"optimizer\"][\"default_wp_id\"]}')
    print(f'  scenarios.site.base_p50: {d.get(\"scenarios\", {}).get(\"site\", {}).get(\"base_p50\")}')
    print(f'  scenarios.by_wp keys: {list(d.get(\"scenarios\", {}).get(\"by_wp\", {}).keys())[:3]}')
"
```

Expected (실제 출력 사용자가 직접 눈으로 확인):
- `daily rows` ≥ 1
- `optimizer.by_wp keys` 비어있지 않음 (Task 3 후 신규 run 의 row 라면 키 ≥ 1)
- `scenarios.site.base_p50` 가 `null` 아님 — `{"expected_completion": "...", "recovery_days": N, ...}` 형태

**사용자가 위 결과를 시각 확인 후 OK 라고 명시적으로 응답하기 전엔 다음 step 진행 X.**

만약 `scenarios.site.base_p50` 가 null 또는 빈 dict → Task 3 step 7 의 신규 pipeline run 이 안 됐거나 site_id 불일치. Task 3 step 7~8 재실행.

- [ ] **Step 6: dev 서버 stop**

```bash
# foreground: Ctrl+C
# background: pkill -f "next dev"
```

- [ ] **Step 7: Commit**

```bash
git add web/app/api/mock/report/route.ts web/lib/fixtures.ts
git commit -m "web: extend mock/report SELECT with scenarios_jsonb + ReportDetail types

route.ts SELECT 절에 dr.scenarios_jsonb 한 줄 + details build 에 scenarios 키 한 줄 추가.
endpoint 신설 0 — 기존 mock/report 가 사실 실 DB endpoint (route name 만 mock).

fixtures.ts:
- Scenario / ScenarioSet / OptimizerByWp type 신규
- ReportDetail.optimizer: single OptimizerOutput → OptimizerByWp (by_wp dict)
- ReportDetail.scenarios?: optional (cold_start 시 undefined)

page.tsx 의 type 컴파일 에러는 Task 5 에서 해소 예정 (예상된 drift).

dev 서버 endpoint 응답 사용자 시각 검증 완료 (scenarios.site.base_p50 노출 확인).
spec §6.1 + §6.4."
```

---

## Task 5: web reports/page.tsx 어댑터 + diagnosis-adapter 분기

**Files:**
- Modify: `web/app/(app)/reports/page.tsx:1, 53, 59, 188 + 상단 EMPTY_OPTIMIZER 상수`
- Modify: `web/lib/diagnosis-adapter.ts` (4번째 param 추가 + recovery 분기)

**중요 (사용자 요구)**: 본 task 종결 직전 dev 서버 + 브라우저 직접 진입해서 4 영역 채워지는지 시각 확인.

- [ ] **Step 1: page.tsx 상단에 EMPTY_OPTIMIZER 상수 + type import**

`web/app/(app)/reports/page.tsx:14` 의 import 직후 추가:

```typescript
import type { ReportDaily, OptimizerOutput } from "@/lib/types";

const EMPTY_OPTIMIZER: OptimizerOutput = {
  diagnosis: "",
  similar_cases: [],
  recommendations: [],
  details: [],
};
```

- [ ] **Step 2: page.tsx:53 initial WP selection 정정**

```typescript
// 변경 전:
setSelectedWpId(initial?.wp_id ?? (detail.optimizer as any)?.default_wp_id ?? null);

// 변경 후 (type 명시 — 동작 동일):
setSelectedWpId(initial?.wp_id ?? detail.optimizer?.default_wp_id ?? null);
```

- [ ] **Step 3: page.tsx:59 diagnose 호출에 scenarios 전달**

```typescript
// 변경 전:
return diagnose(toDiagnosisInput(detail.kpi, detail.s_curve, REPORT_SITE_ID));

// 변경 후:
return diagnose(toDiagnosisInput(detail.kpi, detail.s_curve, REPORT_SITE_ID, detail.scenarios));
```

- [ ] **Step 4: page.tsx:188 OptimizerResult prop 어댑터**

```tsx
// 변경 전:
<OptimizerResult output={detail.optimizer} />

// 변경 후:
<OptimizerResult
  output={
    detail.optimizer?.by_wp?.[selectedWpId ?? ""]
    ?? detail.optimizer?.by_wp?.[detail.optimizer?.default_wp_id ?? ""]
    ?? EMPTY_OPTIMIZER
  }
/>
```

- [ ] **Step 5: diagnosis-adapter.ts 4번째 param + recovery 분기**

`web/lib/diagnosis-adapter.ts` 의 `toDiagnosisInput` 시그니처 변경:

```typescript
// 변경 전:
export function toDiagnosisInput(
  kpi: ReportKpi,
  sCurve: SCurvePoint[],
  siteId: string,
): DiagnosisInput {
  // ... 기존 mock 로직 ...
  return mockBase;
}

// 변경 후:
import type { ReportDetail } from "./fixtures";

export function toDiagnosisInput(
  kpi: ReportKpi,
  sCurve: SCurvePoint[],
  siteId: string,
  scenarios?: ReportDetail["scenarios"],   // ← 신규 optional
): DiagnosisInput {
  // ... 기존 mock 로직 ...

  const mockBase = /* 기존 산식 결과 */;

  // BE scenarios 가 있고 base_p50 가 채워졌으면 recovery 만 대체
  if (
    scenarios?.site?.base_p50 &&
    typeof scenarios.site.base_p50.recovery_days === "number"
  ) {
    return {
      ...mockBase,
      recovery: {
        p25: scenarios.site.optimistic_p25?.recovery_days ?? 0,
        p50: scenarios.site.base_p50.recovery_days,
        p75: scenarios.site.pessimistic_p75?.recovery_days ?? 0,
      },
    };
  }

  return mockBase;
}
```

**주의**: 기존 mock 로직의 변수명 (mockBase 등) 은 현 파일 내용에 맞춰 조정. `DiagnosisInput.recovery` 필드명도 실 type 정의 확인 (p25/p50/p75 key 명).

- [ ] **Step 6: TypeScript 컴파일 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/web"
npx tsc --noEmit 2>&1 | head -30
```

Expected: error 0 (Task 4 의 type 컴파일 오류 해소).

- [ ] **Step 7: 사용자 시각 검증 — dev 서버 + 브라우저 직접 진입 (FE↔BE 매칭 핵심 step)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/web"
npm run dev
```

ready 대기 후 브라우저에서 다음 URL 진입:

```
http://127.0.0.1:5536/reports
```

**시각 확인 체크리스트** (사용자가 직접 눈으로 확인):

1. **/ 01 — 생산성 지표**
   - SPI / CPI chip 둘 다 숫자 표시 (— 아님)
   - 업체별 막대 (ProductivityBarToggle) 가 1개 이상 표시
   - 공종별 토글 클릭 시 막대 갱신

2. **/ 02 — 4분면 산점도**
   - QuadrantScatter 에 점 1개 이상 표시
   - 점 클릭 시 우측 진단 박스 갱신
   - **진단/유사 과거 사례/권고사항/상세 현황 4 칸 모두 텍스트 표시** (현 "데이터 없음" 메시지 X)
   - WP 변경 시 4 칸 내용도 변경 (by_wp dict lookup 동작)

3. **/ 03 — 공정률 추세 (공기 단축 예측 시나리오)**
   - ForecastChart 의 recovery 곡선 표시 (recoveryActive 시)
   - delay_days / recovery_days 숫자 표시

**사용자가 4 영역 모두 채워진 것을 시각 확인 후 OK 명시할 때까지 다음 step 진행 X.**

만약 일부 영역이 비어 있으면:
- 빈 영역 위치 + 어떤 영역 비어있는지 사용자에게 보고
- 브라우저 콘솔 에러 확인 (`F12` → Console)
- 네트워크 응답 확인 (`F12` → Network → `mock/report` 응답 데이터 검토)
- 원인 파악 후 어디 step 으로 돌아갈지 결정

- [ ] **Step 8: dev 서버 stop + Commit**

```bash
# Ctrl+C 또는 pkill -f "next dev"
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add web/app/\(app\)/reports/page.tsx web/lib/diagnosis-adapter.ts
git commit -m "web: reports page — by_wp dict lookup + scenarios adapter

page.tsx 3곳 + diagnosis-adapter.ts 변경:
- :14 EMPTY_OPTIMIZER 상수 추가 (OptimizerResult fallback)
- :53 initial WP selection 의 (detail.optimizer as any) 캐스트 제거 (type 명시)
- :59 diagnose 호출에 detail.scenarios 4번째 인자 전달
- :188 OptimizerResult output 어댑터: by_wp[selectedWpId] → by_wp[default_wp_id] → EMPTY 폴백

diagnosis-adapter.ts:
- toDiagnosisInput 시그니처에 scenarios?: ReportDetail['scenarios'] 추가
- BE scenarios.site.base_p50 가 있으면 recovery 객체만 mock → real 대체
- D-3 EWMA 드랍 결정 정합 (ForecastChart 곡선 시각 변경 0)

dev 서버 브라우저 시각 검증 완료 (4 영역 모두 데이터 노출).
spec §6.2 + §6.3."
```

---

## Task 6: E2E Playwright test

**Files:**
- Create: `web/e2e/reports-real-data.spec.ts`

- [ ] **Step 1: E2E test 작성**

`web/e2e/reports-real-data.spec.ts` 신설:

```typescript
import { test, expect } from "@playwright/test";

test.describe("/reports — real DB data", () => {
  test("ProductivityBar contractor row has non-zero value", async ({ page }) => {
    await page.goto("/reports");
    // ReportDailyList 첫 row 자동 선택 대기
    await page.waitForLoadState("networkidle");
    // contractor bar 1개 이상
    const bars = page.locator('[data-testid="contractor-bar-row"]');
    await expect(bars.first()).toBeVisible({ timeout: 5000 });
  });

  test("WP click toggles 4 panels with real diagnosis", async ({ page }) => {
    await page.goto("/reports");
    await page.waitForLoadState("networkidle");
    // QuadrantScatter 의 첫 점 클릭
    const firstPoint = page.locator('[data-testid="quadrant-point"]').first();
    await firstPoint.click();
    // 진단 박스 4 칸 텍스트 확인
    await expect(page.locator("text=진단")).toBeVisible();
    await expect(page.locator("text=진단 데이터 없음")).not.toBeVisible();
    await expect(page.locator("text=유사 사례 없음")).not.toBeVisible();
  });

  test("ForecastChart shows recovery line when WP selected", async ({ page }) => {
    await page.goto("/reports");
    await page.waitForLoadState("networkidle");
    await page.locator('[data-testid="quadrant-point"]').first().click();
    // recovery 곡선 SVG path 존재
    await expect(page.locator('[data-line="recovery"]')).toBeVisible({ timeout: 5000 });
  });
});
```

**주의**: `data-testid` 가 실제 컴포넌트에 박혀있는지 확인 필요. 없으면 다른 selector (text, role) 로 우회. 본 test 의 목표는 "E2E 가 시각 검증을 보조" 일 뿐 — 핵심 검증은 Task 5 step 7 의 사용자 직접 확인.

- [ ] **Step 2: Playwright test 실행**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/web"
# Playwright 미설치 시:
# npx playwright install chromium
npx playwright test e2e/reports-real-data.spec.ts --headed
```

Expected: 3 test 모두 pass. `--headed` 로 사용자가 자동화된 클릭 동작도 시각 확인 가능.

만약 fail:
- data-testid 가 컴포넌트에 안 박혀있으면 selector 변경 (예: `page.locator('circle').first()` for SVG scatter point)
- 또는 컴포넌트에 data-testid 박는 1줄 추가 commit 후 재실행

- [ ] **Step 3: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add web/e2e/reports-real-data.spec.ts
git commit -m "web: e2e test reports-real-data.spec.ts — regression for 4 panel fill

Task 5 의 시각 검증을 자동화 — 3 case:
- contractor bar 가 1개 이상 노출 (mapper MH 산식 fix 후 EVM CPI 정상)
- WP 클릭 시 진단 4칸 텍스트 노출 (by_wp dict lookup)
- ForecastChart recovery 곡선 노출 (scenarios 어댑터)

spec §7 V5."
```

---

## 종결 검증

모든 task 완료 후:

- [ ] **Final 1: 전체 test suite 실행**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
PYTHONPATH=. pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -v 2>&1 | tail -20
```

Expected: 모두 통과 (regression 0).

```bash
cd web && npm test 2>&1 | tail -10
```

Expected: vitest 통과.

- [ ] **Final 2: git log 확인**

```bash
git log --oneline -10
```

Expected: 6 atomic commits 박힌 상태.

- [ ] **Final 3: 사용자 최종 확인**

dev 서버 띄우고 사용자가 직접 /reports 페이지 진입해서 한 번 더 시각 확인. OK 면 PR 생성.

```bash
cd web && npm run dev
# 브라우저: http://127.0.0.1:5536/reports
```

- [ ] **Final 4: PR 생성 (사용자 명시 시)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git push origin A_Track
gh pr create --title "CPIA reports 강화 — parser MH 환산 + EVM CPI + WP 4칸 연결 + 공기단축 시나리오" --body "$(cat <<'EOF'
## Summary

- mapper.py: 8h 고정 prorate → 시간대 가중 MH 환산 (조출2/주간8/연장4/야간8/철야12) + 헬퍼 2개 추출
- optimizer: scenarios_jsonb 산출 (낙관/기준/비관 p25/p50/p75) + daily_reports UPSERT
- web: by_wp dict lookup + scenarios 어댑터 (FE UI 컴포넌트 변경 0 — 조형준 프로 디자인 보존)
- migration: daily_reports.scenarios_jsonb 1 컬럼 신설

## Test plan
- [ ] BE: `pytest pipeline/tests/test_mapper_weighted_mh.py test_optimizer_scenarios.py` 17 case 통과
- [ ] BE regression: `pytest pipeline/tests/` 전체 통과
- [ ] V3 신규 pipeline_run 후 daily_reports.kpi_jsonb.productivity_today ∈ [50, 150]
- [ ] FE: dev 서버에서 /reports 진입 → 4 영역 (생산성/4분면/진단/시나리오) 모두 데이터 노출
- [ ] E2E: `npx playwright test e2e/reports-real-data.spec.ts` 통과

## Spec
docs/superpowers/specs/2026-05-19-cpia-reports-parser-mh-design.md

PR pending 조형준 프로님 리뷰.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**주의**: main 머지 권한은 조형준 프로님. assistant 는 PR 생성까지만.

---

*plan 끝. 사용자 명시 요구 — Task 4/5 의 사용자 시각 검증 step (4-5, 5-7) 은 자동화 X, 사람이 직접 dev 서버 띄우고 브라우저 진입해서 확인. OK 응답 받기 전 다음 step 진행 X.*
