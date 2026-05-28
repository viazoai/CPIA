# CPIA Report 엔드 이미지 재정립 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-27-cpia-report-redesign-design.md` (commit `e380e6d`)

**Goal:** CPIA `/reports` 페이지의 LLM 산출물 3종 (optimizer recs+diag / scenarios / site_summary) 을 공종 고유 인사이트가 살아있는 형태로 재정립하고, 7/1~9/24 86일 데이터를 건축·토목 trade 한정으로 재 backfill 한다.

**Architecture:** PoC v10 (`/tmp/poc_v10_keyword_schema.py`) 검증된 keyword+action+reason 3 필드 schema + 공종 프레임 6 카테고리 (data/trade_frames.json) lookup. forecaster aggregate 산식 보강 (pace floor + delay cap + point_in_time). cold case 절대 금지 (cases<3 도 LLM 호출 + retry 3-tier). seed_dummy_year 단계에서 trade filter (건축·토목만). 3개월 점진 + gate_month 자동 검증.

**Tech Stack:** Python 3.11 (asyncio + asyncpg + AzureOpenAI SDK), PostgreSQL (AWS), Chroma (AWS, HNSW), Next.js 14 (TypeScript), Playwright (자동 검증), pytest.

**시연 마감:** 2026-06-05 (목, 9일 남음). 본 plan 다음 세션에서 자동 실행 예정.

**사용자 룰 (절대 보존):**
- mapper.py / forecaster/agent.py 변경 X (이번 사이클)
- FE 디자인 불가침 (spec §3.3 ✅/❌ 체크리스트)
- 건축·토목 만 적재 (7/1~9/24)
- 6월 이전 데이터 DELETE X
- 한자 0건
- 애매한 결정 시 실 데이터 LLM PoC 로 명확화

---

## File Structure (변경 대상)

### 신규 (3 파일)
- `data/trade_frames.json` — 6 카테고리 lookup table
- `pipeline/agents/optimizer/_trade_frames.py` — lookup_frame() helper
- `infra/postgres/migrations/2026-05-27_report_redesign.sql` — 컬럼 2개 추가

### 변경 (BE, 9 파일)
- `pipeline/agents/forecaster/aggregate.py` — pace floor + delay cap + point_in_time
- `pipeline/db.py` — insert_forecast SQL $29 placeholder + mapped_history.trade
- `pipeline/agents/atomizer.py` — mh_rows dict `.trade` 키
- `pipeline/agents/optimizer/prompt.py` — RECS/DIAG/SCENARIOS_PROMPT_V10 + build_*_input
- `pipeline/agents/optimizer/agent.py` — 2단계 호출 + 병렬 scenarios + retry
- `pipeline/agents/optimizer/site_summary.py` — SYSTEM_PROMPT_V10 + frame_category
- `pipeline/agents/optimizer/view_builder.py` — status 통일 + v2 일원화 + cold dispatch 폐기
- `scripts/seed_dummy_year.py` — --trades + --start/end-date argparse + trade filter
- `scripts/backfill_optimizer_advice_llm.py` — DEFAULT_TRADES + retry batch

### 변경 (FE, 3 파일 — 일부 이미 적용)
- `web/app/components/charts/ForecastChart.tsx` — 이미 적용 (recovery_days badge)
- `web/app/components/reports/OptimizerResult.tsx` — 추가 적용 필요 (polymorphic rendering)
- `web/app/(app)/reports/page.tsx` — 이미 적용 (recovery_days extract)

### 신규 테스트 (4 파일)
- `pipeline/tests/test_trade_frames.py`
- `pipeline/tests/test_aggregate_v10.py`
- `pipeline/tests/integration/test_optimizer_v10.py`
- `pipeline/tests/e2e/check_month_gate.py`

---

## Phase 1 — Infrastructure & Lookup (3 tasks)

### Task 1: Migration SQL (daily_reports.site_summary_text + forecasts.point_in_time_delay_days)

**Files:**
- Create: `infra/postgres/migrations/2026-05-27_report_redesign.sql`

- [ ] **Step 1: 파일 작성**

```sql
-- 2026-05-27_report_redesign.sql
-- 본 spec: docs/superpowers/specs/2026-05-27-cpia-report-redesign-design.md §4.2.7
-- nullable + default 없음 → Postgres metadata-only, lock < 1s

ALTER TABLE daily_reports
  ADD COLUMN IF NOT EXISTS site_summary_text TEXT;

ALTER TABLE forecasts
  ADD COLUMN IF NOT EXISTS point_in_time_delay_days INTEGER;
```

- [ ] **Step 2: AWS PG 에 적용 (idempotent)**

```bash
/opt/homebrew/Cellar/libpq/18.4/bin/psql "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia" \
  -f infra/postgres/migrations/2026-05-27_report_redesign.sql
```

- [ ] **Step 3: 컬럼 존재 검증**

```bash
/opt/homebrew/Cellar/libpq/18.4/bin/psql "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia" -c "
SELECT column_name FROM information_schema.columns
WHERE table_name IN ('daily_reports','forecasts')
  AND column_name IN ('site_summary_text','point_in_time_delay_days');
"
```
Expected: 2 행 출력.

- [ ] **Step 4: Commit**

```bash
git add infra/postgres/migrations/2026-05-27_report_redesign.sql
git commit -m "feat(migration): site_summary_text + point_in_time_delay_days 컬럼 추가"
```

---

### Task 2: data/trade_frames.json (6 카테고리)

**Files:**
- Create: `data/trade_frames.json`

- [ ] **Step 1: spec §4.2.1 의 6 카테고리 JSON 그대로 작성**

(spec §4.2.1 의 JSON 그대로. 한자 0건 보장)

- [ ] **Step 2: JSON 유효성 검증**

```bash
python3 -c "import json; print(len(json.load(open('data/trade_frames.json'))))"
```
Expected: `6`

- [ ] **Step 3: 한자 검출**

```bash
python3 -c "
import json, re
data = json.load(open('data/trade_frames.json'))
for cat, m in data.items():
    found = re.findall(r'[一-鿿]', m['frame_text'])
    assert not found, f'{cat} 한자 발견: {found}'
print('한자 0건 OK')
"
```
Expected: `한자 0건 OK`

- [ ] **Step 4: Commit**

```bash
git add data/trade_frames.json
git commit -m "feat(data): 공종 프레임 6 카테고리 lookup table"
```

---

### Task 3: _trade_frames.py lookup helper + unit test

**Files:**
- Create: `pipeline/agents/optimizer/_trade_frames.py`
- Test: `pipeline/tests/test_trade_frames.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# pipeline/tests/test_trade_frames.py
from __future__ import annotations
from pipeline.agents.optimizer._trade_frames import lookup_frame


def test_lookup_frame_known_wp():
    cat, txt = lookup_frame("철근콘크리트공사")
    assert cat == "골조"
    assert "적층" in txt


def test_lookup_frame_finish():
    cat, txt = lookup_frame("도장공사")
    assert cat == "마감"


def test_lookup_frame_envelope():
    cat, _ = lookup_frame("외장판넬공사")
    assert cat == "외장"


def test_lookup_frame_earth():
    cat, _ = lookup_frame("배수 공사")
    assert cat == "토공·흙막이"


def test_lookup_frame_fallback_unknown():
    cat, txt = lookup_frame("일반공조설비공사")
    assert cat == "일반"
    assert "균형" in txt or "일반" in txt


def test_lookup_frame_none():
    cat, _ = lookup_frame(None)
    assert cat == "일반"
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_trade_frames.py -v
```
Expected: ImportError (module not found)

- [ ] **Step 3: 구현**

```python
# pipeline/agents/optimizer/_trade_frames.py
"""trade 프레임 lookup — spec §4.2.2.

data/trade_frames.json → l6_main → (category, frame_text) 매핑.
miss 시 FALLBACK.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

_DATA_PATH = Path(__file__).resolve().parents[3] / "data" / "trade_frames.json"
_DATA = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
FALLBACK = (
    "일반",
    "본 공종은 건축·토목 카테고리 외이므로 일반 공정 관점에서 진단합니다. "
    "단위 생산성 + 계획 진척 + MH 효율 3 차원 균형을 본다.",
)


def lookup_frame(l6_main: str | None) -> Tuple[str, str]:
    """l6_main → (category, frame_text). miss 시 FALLBACK."""
    if not l6_main:
        return FALLBACK
    for cat, meta in _DATA.items():
        if l6_main in meta["wps"]:
            return cat, meta["frame_text"]
    return FALLBACK
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_trade_frames.py -v
```
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/optimizer/_trade_frames.py pipeline/tests/test_trade_frames.py
git commit -m "feat(optimizer): trade_frame lookup helper + unit tests"
```

---

## Phase 2 — Forecaster aggregate.py 산식 보강 (4 tasks)

### Task 4: pace floor 헬퍼 + test

**Files:**
- Modify: `pipeline/agents/forecaster/aggregate.py:62-154` (compute_delay 함수)
- Test: `pipeline/tests/test_aggregate_v10.py`

- [ ] **Step 1: 현재 aggregate.py 시그니처 read (실 코드 확인)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
sed -n '50,160p' pipeline/agents/forecaster/aggregate.py
```

- [ ] **Step 2: pace floor 테스트 작성**

```python
# pipeline/tests/test_aggregate_v10.py
from __future__ import annotations
from datetime import date
from pipeline.agents.forecaster.aggregate import compute_delay


def test_pace_floor_when_actual_zero():
    """actual_cum_qty=0, today_qty 매우 작음 → pace = plan_per_day × 0.3 floor 적용."""
    plan = {
        "plan_start": date(2025, 6, 10),
        "plan_finish": date(2025, 12, 30),
        "plan_mh_sum": 1000.0,
    }
    today = date(2025, 6, 30)
    out = compute_delay(
        plan=plan,
        today=today,
        actual_window_start=date(2025, 6, 10),
        actual_cum_mh=872.4,
        actual_cum_qty=0.0,
        plan_total_qty_main=1.0,
        today_qty_main=0.001,
    )
    # plan_per_day = 1.0 / 204 ≈ 0.0049
    # floor = max(0.001, 0.0049 × 0.3 = 0.00147) = 0.00147
    # remaining = 1.0 / 0.00147 ≈ 680일
    # delay_raw = 680 - 183 = 497
    # cap = 204 × 1.0 = 204
    # → delay_days = 204
    assert out["delay_days"] == 204
    assert out["delay_days"] <= 204  # cap 작동


def test_pace_floor_when_today_qty_normal():
    """today_qty 가 plan_per_day × 0.3 보다 크면 today_qty 사용."""
    plan = {
        "plan_start": date(2025, 6, 10),
        "plan_finish": date(2025, 12, 30),
        "plan_mh_sum": 1000.0,
    }
    out = compute_delay(
        plan=plan,
        today=date(2025, 6, 30),
        actual_window_start=date(2025, 6, 10),
        actual_cum_mh=500.0,
        actual_cum_qty=0.0,
        plan_total_qty_main=1.0,
        today_qty_main=0.01,  # plan_per_day(0.0049) × 0.3 = 0.00147 보다 큼
    )
    # pace = 0.01 사용. remaining = 100일. delay_raw = 100 - 183 = -83 (앞당김) → 0
    assert out["delay_days"] <= 0
```

- [ ] **Step 3: 실행 (실패 확인)**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_aggregate_v10.py::test_pace_floor_when_actual_zero -v
```
Expected: FAIL (현재 pace floor 적용 X)

- [ ] **Step 4: aggregate.py 구현 (pace floor + plan_per_day_qty 변수 정의)**

`pipeline/agents/forecaster/aggregate.py:130-141` 부분 수정.

**중요 (1차 review 발견)**: 현재 aggregate.py 에는 `plan_mh_per_day` 만 있고 qty 기반 `plan_per_day_qty` 변수 없음. **변수 정의 라인 추가 필요**.

```python
# AS-IS (line 130~):
#   avg_pace_qty = actual_cum_qty / window_days if window_days > 0 else 0.0
#   pace = avg_pace_qty if avg_pace_qty > 0 else today_qty_main

# TO-BE (pace floor + plan_per_day_qty 신규 정의):
# 1. plan_per_day_qty 변수 정의 (line 107 plan_mh_per_day 직후 추가)
plan_per_day_qty = plan_total_qty_main / total_days if total_days > 0 and plan_total_qty_main else 0.0

# 2. pace floor 적용
avg_pace_qty = actual_cum_qty / window_days if window_days > 0 else 0.0
if avg_pace_qty > 0:
    pace = avg_pace_qty
else:
    # pace floor — over-pessimistic 방지 (spec §4.2.3)
    pace = max(today_qty_main, plan_per_day_qty * 0.3)
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_aggregate_v10.py::test_pace_floor_when_actual_zero -v
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_aggregate_v10.py::test_pace_floor_when_today_qty_normal -v
```
Expected: 2 passed

- [ ] **Step 6: 회귀 — 기존 aggregate 테스트 통과 확인**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/forecaster/ -v
```
Expected: all green (또는 기존 통과 수 유지)

- [ ] **Step 7: Commit**

```bash
git add pipeline/agents/forecaster/aggregate.py pipeline/tests/test_aggregate_v10.py
git commit -m "feat(forecaster): pace floor (plan_per_day × 0.3) — over-pessimistic 방지"
```

---

### Task 5: delay cap

**Files:**
- Modify: `pipeline/agents/forecaster/aggregate.py:130-141`
- Test: `pipeline/tests/test_aggregate_v10.py` (확장)

- [ ] **Step 1: delay cap 테스트 추가**

```python
def test_delay_cap_total_days():
    """delay_raw > total_days × 1.0 → cap 됨."""
    plan = {
        "plan_start": date(2025, 6, 10),
        "plan_finish": date(2025, 6, 30),  # 21일짜리 wp
        "plan_mh_sum": 100.0,
    }
    out = compute_delay(
        plan=plan,
        today=date(2025, 6, 30),
        actual_window_start=date(2025, 6, 10),
        actual_cum_mh=50.0,
        actual_cum_qty=0.0,
        plan_total_qty_main=1.0,
        today_qty_main=0.0001,  # 매우 작음
    )
    # total_days = 21, cap = 21 × 1.0 = 21
    # pace floor 적용 후도 delay_raw 큼 → cap 적용
    assert out["delay_days"] is not None
    assert out["delay_days"] <= 21
```

- [ ] **Step 2: 실행 (실패 확인)**

- [ ] **Step 3: aggregate.py 구현 (delay cap)**

```python
# pace > 0 분기 안:
remaining_days = remaining_qty / pace
expected_completion = today + timedelta(days=round(remaining_days))
delay_days_raw = (expected_completion - plan_finish).days
# delay cap — total_days × 1.0 (spec §4.2.3)
delay_days = min(delay_days_raw, round(total_days * 1.0))
```

- [ ] **Step 4: 테스트 통과 확인**

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/forecaster/aggregate.py pipeline/tests/test_aggregate_v10.py
git commit -m "feat(forecaster): delay cap (total_days × 1.0)"
```

---

### Task 6: _compute_point_in_time_deficit_days helper

**Files:**
- Modify: `pipeline/agents/forecaster/aggregate.py`
- Test: `pipeline/tests/test_aggregate_v10.py` (확장)

- [ ] **Step 1: point_in_time 테스트 작성**

```python
def test_point_in_time_deficit_normal():
    """30일 30루베 plan, 15일째 실 7루베 → deficit 8 = 8일."""
    plan = {
        "plan_start": date(2025, 6, 1),
        "plan_finish": date(2025, 6, 30),  # 30일
        "plan_mh_sum": 100.0,
    }
    out = compute_delay(
        plan=plan,
        today=date(2025, 6, 15),
        actual_window_start=date(2025, 6, 1),
        actual_cum_mh=50.0,
        actual_cum_qty=7.0,
        plan_total_qty_main=30.0,
        today_qty_main=0.5,
    )
    # plan_per_day = 30/30 = 1.0
    # plan_qty_to_date = 1.0 × 14 = 14 (today_offset)
    # deficit = 14 - 7 = 7
    # point_in_time = 7 / 1.0 = 7
    assert out["point_in_time_delay_days"] == 7


def test_point_in_time_before_plan_start():
    """today < plan_start → point_in_time = 0."""
    plan = {"plan_start": date(2025, 7, 1), "plan_finish": date(2025, 12, 30), "plan_mh_sum": 100.0}
    out = compute_delay(plan=plan, today=date(2025, 6, 30),
                       actual_window_start=date(2025, 6, 30),
                       actual_cum_mh=0.0, actual_cum_qty=0.0,
                       plan_total_qty_main=10.0, today_qty_main=0.0)
    assert out["point_in_time_delay_days"] == 0


def test_point_in_time_after_plan_finish():
    """today > plan_finish → plan_qty_to_date = plan_total_qty (cap)."""
    plan = {"plan_start": date(2025, 5, 1), "plan_finish": date(2025, 5, 31), "plan_mh_sum": 100.0}
    out = compute_delay(plan=plan, today=date(2025, 6, 15),
                       actual_window_start=date(2025, 5, 1),
                       actual_cum_mh=80.0, actual_cum_qty=8.0,
                       plan_total_qty_main=10.0, today_qty_main=0.3)
    # plan_qty_to_date = min(today_offset × per_day, plan_total) = min(45 × 0.32, 10) = 10
    # deficit = 10 - 8 = 2 → 2/0.32 ≈ 6일
    assert out["point_in_time_delay_days"] > 0
```

- [ ] **Step 2: 실행 (실패 확인)**

- [ ] **Step 3: aggregate.py 구현 (point_in_time)**

`plan_per_day_qty` 는 Task 4 에서 정의됨 (Step 4). 그 변수 재사용.

```python
# compute_delay 반환 dict 산출 직전 추가:
today_offset = (today - plan_start).days
if plan_per_day_qty > 0 and today_offset > 0:
    plan_qty_to_date = min(plan_per_day_qty * today_offset, plan_total_qty_main)
    deficit_qty = max(0, plan_qty_to_date - actual_cum_qty)
    point_in_time_delay_days = round(deficit_qty / plan_per_day_qty)
else:
    point_in_time_delay_days = 0

return {
    ...,
    "delay_days": delay_days,
    "point_in_time_delay_days": point_in_time_delay_days,
    "mh_gap": mh_gap,
}
```

- [ ] **Step 4: 테스트 통과 + 회귀**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_aggregate_v10.py pipeline/tests/forecaster/ -v
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/forecaster/aggregate.py pipeline/tests/test_aggregate_v10.py
git commit -m "feat(forecaster): point_in_time_delay_days 산출 (deficit_qty / plan_per_day)"
```

---

### Task 7: db.py insert_forecast SQL $29 placeholder

**Files:**
- Modify: `pipeline/db.py:260-330` (insert_forecast 함수)

- [ ] **Step 1: 현재 insert_forecast SQL 정확 위치 read (애매성 해소)**

```bash
sed -n '255,335p' pipeline/db.py
```

- [ ] **Step 2: forecaster agent.py 가 insert_forecast 에 dict 전달하는 지점 read**

```bash
grep -n "insert_forecast\|point_in_time" pipeline/agents/forecaster/agent.py
```

- [ ] **Step 3: 통합 테스트 작성 (insert 후 SELECT)**

```python
# pipeline/tests/test_db_forecasts_v10.py
import asyncio, asyncpg, uuid
from datetime import date
from pipeline.db import PGClient
import pytest

DSN = "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia"


@pytest.mark.asyncio
async def test_insert_forecast_with_point_in_time():
    pg = PGClient(DSN)
    await pg.connect()
    try:
        # 임시 run_id
        run_id = uuid.uuid4()
        # ... pipeline_runs 임시 INSERT
        # ... insert_forecast 호출, point_in_time_delay_days=7 포함
        # ... SELECT 결과에서 point_in_time_delay_days = 7 확인
    finally:
        # 임시 row DELETE
        await pg.close()
```

- [ ] **Step 4: db.py:insert_forecast INSERT SQL 확장**

```python
# pipeline/db.py:insert_forecast 안
INSERT_SQL = """
    INSERT INTO forecasts (
      run_id, company, l6_main, today_qty_by_unit, today_assigned_workers,
      plan_total_qty_by_unit, plan_mh_sum, rag_n_similar, similar_cases,
      assessment, reasoning, expected_completion, delay_days, risk_level,
      today_productivity, plan_start, plan_finish, plan_mh_per_day,
      schedule_state, window_start, window_days, expected_in_window_mh,
      actual_in_window_mh, mh_gap, recovery_likelihood,
      [기존 24컬럼 + 4 추가...],
      point_in_time_delay_days
    ) VALUES ($1, $2, ..., $28, $29)
"""
# row.get("point_in_time_delay_days") 도 $29 위치에 전달
```

(주의: 현재 28 컬럼 위치 정확 식별 후 $29 추가. row dict 의 key 정확 확인)

- [ ] **Step 5: 테스트 통과 + 회귀**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_db_forecasts_v10.py -v
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/db.py pipeline/tests/test_db_forecasts_v10.py
git commit -m "feat(db): forecasts INSERT $29 placeholder — point_in_time_delay_days"
```

---

## Phase 3 — Optimizer prompt + agent (6 tasks)

### Task 8: RECS_PROMPT_V10 (keyword + action + reason)

**Files:**
- Modify: `pipeline/agents/optimizer/prompt.py`

- [ ] **Step 1: 현재 prompt.py 구조 read**

```bash
sed -n '1,100p' pipeline/agents/optimizer/prompt.py
```

- [ ] **Step 2: PoC v10 의 RECS_PROMPT_V10 텍스트 prompt.py 로 이전**

`/tmp/poc_v10_keyword_schema.py` 의 `RECS_PROMPT_V10` 문자열을 `pipeline/agents/optimizer/prompt.py` 의 신규 상수로 추가:

```python
# pipeline/agents/optimizer/prompt.py 끝에 추가
RECS_PROMPT_V10 = """...(v10 PoC 텍스트 그대로)..."""
```

- [ ] **Step 3: prompt 텍스트 unit 검증 (snapshot test)**

```python
# pipeline/tests/test_prompts_v10.py
from pipeline.agents.optimizer.prompt import RECS_PROMPT_V10


def test_recs_prompt_has_keyword_schema():
    assert "keyword" in RECS_PROMPT_V10
    assert "action" in RECS_PROMPT_V10
    assert "reason" in RECS_PROMPT_V10
    assert "5~10자" in RECS_PROMPT_V10  # keyword 가이드


def test_recs_prompt_no_kanji():
    import re
    found = re.findall(r"[一-鿿]", RECS_PROMPT_V10)
    assert not found, f"한자 발견: {found}"


def test_recs_prompt_g8_guard():
    assert "공종" in RECS_PROMPT_V10
    assert "trade_frame" in RECS_PROMPT_V10
```

- [ ] **Step 4: 테스트 통과**

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/optimizer/prompt.py pipeline/tests/test_prompts_v10.py
git commit -m "feat(prompt): RECS_PROMPT_V10 — keyword + action + reason 3 필드 schema"
```

---

### Task 9: DIAG_PROMPT_V10 (G6 강화 + delay 두 차원)

**Files:**
- Modify: `pipeline/agents/optimizer/prompt.py`

- [ ] **Step 1: PoC v9 의 DIAG_PROMPT 텍스트 ref + v10 keyword 인지 부분 추가 가드**

- [ ] **Step 2: 테스트 작성**

```python
def test_diag_prompt_g6_enhanced():
    from pipeline.agents.optimizer.prompt import DIAG_PROMPT_V10
    assert "정상범주" in DIAG_PROMPT_V10  # 금지 단어 명시
    assert "risk_level" in DIAG_PROMPT_V10
    assert "forward_delay_days" in DIAG_PROMPT_V10
    assert "point_in_time_delay_days" in DIAG_PROMPT_V10
    assert "mh_gap" in DIAG_PROMPT_V10
```

- [ ] **Step 3: 구현 (PoC v9 DIAG_PROMPT + v10 keyword 인지)**

- [ ] **Step 4: 테스트 통과**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(prompt): DIAG_PROMPT_V10 — G6 강화 + delay 두 차원 + mh_gap"
```

---

### Task 10: SCENARIOS_PROMPT_V10 (G8 강화)

**Files:**
- Modify: `pipeline/agents/optimizer/prompt.py:356-388` (기존 SCENARIOS_PROMPT 확장)

- [ ] **Step 1: 기존 SCENARIOS_PROMPT 보존 → V10 추가**

- [ ] **Step 2: 테스트**

```python
def test_scenarios_prompt_v10_g8():
    from pipeline.agents.optimizer.prompt import SCENARIOS_PROMPT_V10
    assert "trade_frame" in SCENARIOS_PROMPT_V10
    assert "rationale" in SCENARIOS_PROMPT_V10
    # 일반론 회피 가드
    assert "일반론" in SCENARIOS_PROMPT_V10 or "공종 고유" in SCENARIOS_PROMPT_V10
```

- [ ] **Step 3: 구현**

- [ ] **Step 4: 통과**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(prompt): SCENARIOS_PROMPT_V10 — G8 trade_frame rationale"
```

---

### Task 11: SITE_SUMMARY_PROMPT_V10 + frame_category payload

**Files:**
- Modify: `pipeline/agents/optimizer/site_summary.py`

- [ ] **Step 1: PoC v8 의 SITE_SUMMARY_PROMPT 참고 + frame_category 인용 가드 추가**

- [ ] **Step 2: build_site_summary_payload 에 top_risk_wps[i].frame_category 추가**

```python
# site_summary.py:build_site_summary_payload 안
from pipeline.agents.optimizer._trade_frames import lookup_frame

# top_risk_wps 만들 때:
cat, _ = lookup_frame(w.get("l6_main"))
top_risk_wps.append({
    "wp_name": w.get("wp_name"),
    "trade": w.get("trade"),
    "frame_category": cat,    # ★ 신규
    "diagnosis": diag,
    "top_recommendation": recs[0] if recs else None,
})
```

- [ ] **Step 3: 테스트**

```python
def test_site_summary_payload_has_frame_category():
    from pipeline.agents.optimizer.site_summary import build_site_summary_payload
    payload = build_site_summary_payload(
        report_date="2025-07-01", site_id="test",
        kpi={"delay_days": 5}, scenarios={},
        wp_summary=[{"wp_id": "x", "wp_name": "철근콘크리트공사", "trade": "건축",
                    "impact": 100, "l6_main": "철근콘크리트공사"}],
        optimizer_view={"by_wp": {"x": {"diagnosis": "test", "recommendations": ["r1"]}}},
        s_curve=[],
    )
    assert payload["top_risk_wps"][0]["frame_category"] == "골조"
```

- [ ] **Step 4: 통과 + Commit**

```bash
git commit -am "feat(site_summary): SYSTEM_PROMPT_V10 + frame_category payload"
```

---

### Task 12: build_*_input 4개 + trade_frame inject

**Files:**
- Modify: `pipeline/agents/optimizer/prompt.py`

- [ ] **Step 1: build_recs_input_v10 / build_diag_input_v10 / build_scenarios_input_v10 추가**

PoC v10 패턴 그대로:
```python
def build_recs_input_v10(forecast_row, cases, today_date, frame_category, frame_text):
    return {
        "today": {
            "date": today_date,
            "company": forecast_row["company"],
            "l6_main": forecast_row["l6_main"],
            "main_unit": forecast_row["main_unit"],
            "assessment": forecast_row["assessment"],
            "risk_level": forecast_row["risk_level"],
            "today_productivity": forecast_row["today_productivity"],
            "today_conditions": forecast_row["today_conditions"],
            "frame_category": frame_category,
            "forward_delay_days": forecast_row.get("delay_days"),
            "point_in_time_delay_days": forecast_row.get("point_in_time_delay_days"),
            "mh_gap": forecast_row.get("mh_gap"),
        },
        "trade_frame": frame_text,
        "degradation_cases": [...],
    }
```

- [ ] **Step 2: 테스트 + 통과**

- [ ] **Step 3: Commit**

```bash
git commit -am "feat(prompt): build_*_input_v10 — trade_frame + delay 두 차원 inject"
```

---

### Task 13: optimizer/agent.py — 2단계 + scenarios 병렬 + retry

**Files:**
- Modify: `pipeline/agents/optimizer/agent.py:106-200`

- [ ] **Step 1: 현재 agent.py:_process_one read**

```bash
sed -n '180,220p' pipeline/agents/optimizer/agent.py
```

- [ ] **Step 2: PoC v9 의 2단계 + scenarios 병렬 패턴 + retry 3회 통합**

```python
async def _process_one_with_retry(r, cases, run_id, today, cfg, azure, sem,
                                   failed_wps_today, max_retries=3):
    for attempt in range(max_retries):
        try:
            async with sem:
                category, frame_text = lookup_frame(r["l6_main"])
                recs_input = build_recs_input_v10(r, cases, today.isoformat(),
                                                  category, frame_text)
                scen_input = build_scenarios_input_v10(r, ..., category, frame_text)
                # 병렬: recs ‖ scenarios
                recs_task = _call_llm_v10(RECS_PROMPT_V10, recs_input, cfg, azure)
                scen_task = _call_llm_v10(SCENARIOS_PROMPT_V10, scen_input, cfg, azure)
                recs_out, scen_out = await asyncio.gather(recs_task, scen_task)
                # 순차: diag (recs 결과 인용)
                diag_input = build_diag_input_v10(recs_input, recs_out["recommendations"])
                diag_out = await _call_llm_v10(DIAG_PROMPT_V10, diag_input, cfg, azure)
            return _compose_row(r, cases, {
                "diagnosis": diag_out["diagnosis"],
                "recommendations": recs_out["recommendations"]
            }, run_id, scenarios=scen_out)
        except (openai.APIError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            if attempt == max_retries - 1:
                failed_wps_today.append((r["company"], r["l6_main"], str(e)))
                return None
            await asyncio.sleep(2 ** (attempt + 1))
```

- [ ] **Step 3: optimize() 끝부분에서 failed_wps_today 처리**

```python
# 1일 끝난 후 retry batch (spec §4.4.1.B)
if failed_wps_today:
    logger.warning(f"Day {today}: {len(failed_wps_today)} wp failed, retry batch...")
    # ... batch retry 1회
```

- [ ] **Step 4: Mock integration test**

```python
# pipeline/tests/optimizer/test_agent_v10_retry.py
@pytest.mark.asyncio
async def test_process_one_retries_on_api_error(monkeypatch):
    # AzureOpenAI 가 첫 2회 APIError, 3회째 성공 → 통과
    ...
    assert call_count == 3
```

- [ ] **Step 5: 통과 + Commit**

```bash
git commit -am "feat(optimizer): 2단계 호출 + scenarios 병렬 + retry 3-tier"
```

---

## Phase 4 — View builder + atomizer (5 tasks)

### Task 14: view_builder.py wp_summary.status = forecasts.risk_level

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:760-790`

- [ ] **Step 1: 현재 _build_wp_summary read (line 760-790)**

- [ ] **Step 2: forecasts SELECT 추가 + status 매핑**

```python
async def _build_wp_summary(pg, site_id, today, productivity, quadrant_jsonb):
    """status 산출 = forecasts.risk_level 인용 (spec §4.2.6)."""
    # forecasts row fetch by (l6_main, company)
    async with pg._pool.acquire() as con:
        f_rows = await con.fetch(
            """SELECT company, l6_main, risk_level FROM forecasts f
               JOIN pipeline_runs pr USING(run_id)
               WHERE pr.site_id=$1 AND pr.report_date=$2""",
            site_id, today
        )
    risk_by_wp = {(r["company"], r["l6_main"]): r["risk_level"] for r in f_rows}

    STATUS_MAP = {"정상": "normal", "주의": "caution", "이상": "risk"}

    out = []
    for q in quadrant_jsonb:
        # quadrant_jsonb 의 trade 가 l6_main 일 수도 — 정확히 추출
        risk_level = risk_by_wp.get((q.get("company"), q.get("l6_main")))
        status = STATUS_MAP.get(risk_level, "normal")
        out.append({**q, "baseline": 90, "status": status, ...})
    return out
```

- [ ] **Step 3: 테스트 + 통과**

- [ ] **Step 4: Commit**

```bash
git commit -am "feat(view_builder): wp_summary.status = forecasts.risk_level 일원화"
```

---

### Task 15: view_builder v2 일원화 (#N19)

**Files:**
- Modify: `pipeline/agents/optimizer/agent.py:219` (live LangGraph 호출 v1 → v2)

- [ ] **Step 1: agent.py:219 의 현재 v1 호출 read**

- [ ] **Step 2: v1 호출 → v2 (`_build_productivity_views_v2`) 변경**

- [ ] **Step 3: 회귀 — pipeline_runs 흐름 통과 확인**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/optimizer/ -v
```

- [ ] **Step 4: Commit**

```bash
git commit -am "fix(optimizer): agent.py:219 v1 → v2 일원화 (#N19)"
```

---

### Task 16: _build_deterministic_cold_start 분기 폐기

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:1904` (dispatch 분기)
- Delete (tests): `pipeline/tests/optimizer/test_view_builder_phase2.py:75-145` (cold_start 6 spot)

- [ ] **Step 1: 현재 dispatch 위치 read**

```bash
grep -n "_build_deterministic_cold_start" pipeline/agents/optimizer/view_builder.py
```

- [ ] **Step 2: 분기 삭제 (`if len(cases) < 3: return _build_deterministic_cold_start(...)` 제거)**

```python
# AS-IS:
if len(cases) < 3:
    return _build_deterministic_cold_start(...)
result = await call_optimizer_llm(...)
return result

# TO-BE (분기 제거):
result = await call_optimizer_llm(...)
return result
```

- [ ] **Step 3: 기존 cold_start 테스트 처리 (spec §4.5.1)**

- `pipeline/tests/optimizer/test_view_builder_phase2.py` 의 6 spot DELETE
- `pipeline/tests/optimizer/test_view_builder_v2.py:164` REPLACE (LLM mock path)
- `pipeline/tests/test_optimizer_scenarios.py:102` REPLACE

- [ ] **Step 4: 신규 test_cold_path_v10.py**

```python
# pipeline/tests/test_cold_path_v10.py
@pytest.mark.asyncio
async def test_cold_path_calls_llm_with_empty_cases():
    """cases=빈 array → LLM 호출 + diagnosis ≠ 'cold_start'."""
    # mock LLM 호출, recommendations 4건 보장
    ...
```

- [ ] **Step 5: 통과 + Commit**

```bash
git commit -am "feat(view_builder): _build_deterministic_cold_start 분기 폐기 + cases<3 LLM 강제"
```

---

### Task 17: view_builder.py:1447 trade 필터 안전망 (#N17)

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:1447`

- [ ] **Step 1: 현재 line 1447 확인 (working tree 잔재)**

```bash
git diff pipeline/agents/optimizer/view_builder.py | head -30
```

- [ ] **Step 2: 변경 stage + commit (안전망 유지)**

```bash
git add pipeline/agents/optimizer/view_builder.py
git commit -m "fix(view_builder): trade IN ('건축','토목') 안전망 (#N17)"
```

(working tree 잔재 + risk_level→status 헬퍼 + 금일 생산성 columns 함께 commit)

---

### Task 18: atomizer.py + db.py mapped_history.trade verify (★ 1차 review 발견 — 이미 적용)

**Files:**
- Verify only: `pipeline/agents/atomizer.py:184` (mh_rows 에 trade 키 이미 포함)
- Verify only: `pipeline/db.py:481-506` (mapped_history INSERT + ON CONFLICT EXCLUDED.trade 이미 포함)

**중요 (1차 review)**: 1차 feasibility reviewer 가 실 코드 확인 — `atomizer.py:184` 와 `db.py:481-506` 에 **이미 `trade` 키 + INSERT 컬럼 + EXCLUDED.trade 모두 존재**. 변경 사항 없음. Verify-only task.

- [ ] **Step 1: 실 코드 grep 으로 이미 적용 확인**

```bash
grep -n "trade" pipeline/agents/atomizer.py | head -10
grep -n "mapped_history\|EXCLUDED.trade" pipeline/db.py | head -10
```
Expected: atomizer.py:184 `"trade": a.get("trade"),` + db.py:481-506 INSERT 컬럼 + ON CONFLICT 모두 보여야 함.

- [ ] **Step 2: 통합 테스트 — atomize 호출 후 mapped_history.trade SELECT (회귀 확인)**

```python
# pipeline/tests/integration/test_atomizer_trade.py
@pytest.mark.asyncio
async def test_mapped_history_trade_populated():
    # 임시 run_id + atomize 호출 → mapped_history SELECT 시 trade 값 존재 확인
    ...
```

- [ ] **Step 3: 회귀 통과 확인 — 코드 변경 없으면 skip commit**

만약 이미 적용된 변경이 commit 안 됨 (working tree 잔재) 이면:
```bash
git add pipeline/agents/atomizer.py pipeline/db.py
git commit -m "fix(atomizer): mapped_history.trade — verify 완료 (#A-N3)"
```
이미 commit 됨이면 skip.

---

## Phase 5 — Seed + Backfill scripts (3 tasks)

### Task 19: seed_dummy_year.py trade filter + argparse 윈도우

**Files:**
- Modify: `scripts/seed_dummy_year.py`

- [ ] **Step 1: 현재 seed_dummy_year.py argparse + 일자 loop read**

```bash
grep -n "argparse\|add_argument\|for d in" scripts/seed_dummy_year.py | head -20
```

- [ ] **Step 2: argparse 확장 + trade filter 추가**

```python
parser.add_argument("--trades", nargs="+", default=["건축","토목"],
                    help="적재할 trade list (default: 건축 토목)")
parser.add_argument("--start-date", default="2025-07-01")
parser.add_argument("--end-date", default="2025-09-24")

# _build_mapper_row 직후
mapper_row = _build_mapper_row(d, am_row, anchor, rng)
if mapper_row["trade"] not in args.trades:
    stat["trade_filtered"] += 1
    continue   # PG INSERT skip
```

- [ ] **Step 3: 검증 (dry-run 1일)**

```bash
pipeline/.venv/bin/python3 scripts/seed_dummy_year.py \
  --start-date 2025-07-01 --end-date 2025-07-01 \
  --trades 건축 토목 --dry-run
```
Expected: skip 카운트 비건축·비토목 row 만큼.

- [ ] **Step 4: Commit**

```bash
git commit -am "feat(seed): trade filter (--trades) + 윈도우 (--start/end-date)"
```

---

### Task 20: backfill_optimizer_advice_llm.py DEFAULT_TRADES + retry batch

**Files:**
- Modify: `scripts/backfill_optimizer_advice_llm.py:53`

- [ ] **Step 1: 현재 DEFAULT_TRADES + flow read**

- [ ] **Step 2: 변경**

```python
# scripts/backfill_optimizer_advice_llm.py:53
DEFAULT_TRADES = ("건축", "토목")  # 안전망 (seed 가 1차 filter)

# main 끝부분 — failed_wps 종합 batch retry
if failed_wps_global:
    logger.warning(f"전체 {len(failed_wps_global)} wp 실패 — 최종 retry batch")
    # 1회 더 retry, 후도 실패 row 는 log
```

- [ ] **Step 3: 1일 dry-run**

```bash
pipeline/.venv/bin/python3 scripts/backfill_optimizer_advice_llm.py --date 2025-07-01
```

- [ ] **Step 4: Commit**

```bash
git commit -am "feat(backfill): DEFAULT_TRADES=('건축','토목') + failed_wps 종합 retry"
```

---

### Task 21: backfill_daily_report_views_v2.py 윈도우 + --with-summary 강제

**Files:**
- Modify: `scripts/backfill_daily_report_views_v2.py`

- [ ] **Step 1: 현재 argparse read (이미 --with-summary 옵션 존재)**

- [ ] **Step 2: --start-date / --end-date 추가 + --with-summary default true**

```python
parser.add_argument("--start-date", default=None)
parser.add_argument("--end-date", default=None)
parser.add_argument("--with-summary", action="store_true", default=True)  # default on

# all-dates 안 d_rows 쿼리 안에 BETWEEN 추가
if args.start_date and args.end_date:
    d_rows = await raw.fetch(
        "SELECT DISTINCT report_date FROM mapper_activities "
        "WHERE report_date BETWEEN $1::date AND $2::date ORDER BY 1",
        args.start_date, args.end_date,
    )
```

- [ ] **Step 3: 1일 dry-run**

- [ ] **Step 4: Commit**

```bash
git commit -am "feat(backfill_views_v2): 윈도우 + summary live default on"
```

---

## Phase 6 — FE polymorphic rendering (1 task)

### Task 22: OptimizerResult.tsx polymorphic recommendations

**Files:**
- Modify: `web/app/components/reports/OptimizerResult.tsx` (이미 일부 적용 — slice 만 done)

- [ ] **Step 1: 현재 recommendations rendering read**

```bash
sed -n '33,45p' web/app/components/reports/OptimizerResult.tsx
```

- [ ] **Step 2: polymorphic 분기 추가 (spec §4.2.8)**

```tsx
{output.recommendations.map((r, i) => {
  if (typeof r === "string") {
    return <li key={i} className="text-sm text-ink-mid leading-relaxed">{r}</li>;
  }
  return (
    <li key={i} className="mb-3 text-sm text-ink-mid leading-relaxed">
      <div className="flex items-baseline gap-2">
        <span className="rounded bg-mint-soft px-1.5 py-0.5 text-[12px] font-semibold text-mint-text">
          {r.keyword}
        </span>
        <span className="text-ink">{r.action}</span>
      </div>
      <div className="ml-2 mt-1 text-[12.5px] text-ink-mid">
        <span className="font-semibold">이유:</span> {r.reason}
      </div>
    </li>
  );
})}
```

- [ ] **Step 3: TypeScript 타입 union 명시**

```tsx
// OptimizerOutput 의 recommendations 타입
recommendations: (string | { rank?: number; keyword: string; action: string; reason: string })[];
```

- [ ] **Step 4: dev server hot reload + 6/30 화면 수동 검증 (옛 string schema 정상)**

```bash
cd web && pnpm dev   # 떠있으면 skip
# http://localhost:5536/reports → 6/30 → 옛 string 그대로 표시 확인
```

- [ ] **Step 5: Commit**

```bash
git add web/app/components/reports/OptimizerResult.tsx
git commit -m "feat(web/OptimizerResult): polymorphic recommendations (string vs object)"
```

---

## Phase 7 — Tests (3 tasks)

### Task 23: Integration test_optimizer_v10 (실 PG + Azure)

**Files:**
- Create: `pipeline/tests/integration/test_optimizer_v10.py`

- [ ] **Step 1: PoC v10 패턴 자동화 — 3 wp sample**

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_optimizer_v10_three_wp():
    """3 wp (risk=정상/주의/이상) × recs+diag+scenarios = 9 호출."""
    wps = [
        ("남웅건설", "철근콘크리트공사"),       # 정상
        ("에스비테크", "외장판넬공사"),          # 주의
        ("한신비텍", "NPW(2차 SCR) SYSTEM"),     # 이상
    ]
    for company, l6 in wps:
        result = await call_optimizer_v10(company, l6, date(2025, 6, 30))
        # G6 검증
        banned = ["정상범주", "정상 범위"]
        for word in banned:
            assert word not in result["diagnosis"], f"{company}: G6 위반 '{word}'"
        # keyword 검증
        for rec in result["recommendations"]:
            assert 3 <= len(rec["keyword"]) <= 12, f"keyword 길이: {rec['keyword']}"
            assert "action" in rec and "reason" in rec
        # delay 두 차원 인용
        diag = result["diagnosis"]
        assert "지연" in diag or "뒤처" in diag or "부족" in diag
```

- [ ] **Step 2: 실행 + 결과 확인**

- [ ] **Step 3: Commit**

```bash
git commit -am "test(optimizer): v10 integration — 3 wp × G6 + keyword + delay 인용"
```

---

### Task 24: Regression test_v10_vs_v7 (snapshot 비교)

**Files:**
- Create: `pipeline/tests/regression/test_v10_vs_v7.py`

- [ ] **Step 1: v7 결과 (PG 6/30) vs v10 재 호출 비교**

```python
async def test_general_recommendation_ratio_decrease():
    """v7 대비 v10 의 일반론 권고 비율 감소 확인."""
    v7_advices = await fetch_v7_optimizer_advices(date(2025, 6, 30), site_id="m15x-ph3-ibl")
    v10_advices = await rerun_v10_on_same(v7_advices)

    general_keywords = ["인력 재배치", "모니터링 강화", "후속공정 순서 교체"]
    v7_general = sum(1 for a in v7_advices for r in a["recommendations"]
                     if any(k in str(r) for k in general_keywords))
    v10_general = sum(1 for a in v10_advices for r in a["recommendations"]
                      if any(k in str(r) for k in general_keywords))
    v7_total = sum(len(a["recommendations"]) for a in v7_advices)
    v10_total = sum(len(a["recommendations"]) for a in v10_advices)

    v7_ratio = v7_general / v7_total if v7_total else 0
    v10_ratio = v10_general / v10_total if v10_total else 0
    assert v10_ratio < v7_ratio, f"일반론 비율 감소 실패: v7={v7_ratio:.2%} v10={v10_ratio:.2%}"
```

- [ ] **Step 2: 통과 + Commit**

```bash
git commit -am "test(regression): v10 일반론 권고 비율 v7 대비 감소 확인"
```

---

### Task 25: E2E gate_month 함수 + Playwright 자동 검증

**Files:**
- Create: `pipeline/tests/e2e/check_month_gate.py`
- Create: `pipeline/tests/e2e/playwright_reports_check.py`

- [ ] **Step 1: gate_month 함수 작성 (spec §4.4.2)**

```python
async def gate_month(month: int) -> dict:
    """월별 backfill 후 OK 판단 — 7 checks."""
    pg = await asyncpg.connect(DSN)
    checks = {}
    try:
        # 1. cold_start zero
        v = await pg.fetchval(
            "SELECT COUNT(*) FROM optimizer_advice oa JOIN pipeline_runs pr USING(run_id) "
            f"WHERE oa.diagnosis='cold_start' AND pr.report_date >= '2025-{month:02d}-01' "
            f"AND pr.report_date <= '2025-{month:02d}-31'"
        )
        checks["cold_start_zero"] = v == 0

        # 2. G6 banned words
        v = await pg.fetchval(
            "SELECT COUNT(*) FROM optimizer_advice oa JOIN pipeline_runs pr USING(run_id) "
            f"WHERE (oa.diagnosis LIKE '%정상범주%' OR oa.diagnosis LIKE '%정상 범위%') "
            f"AND pr.report_date >= '2025-{month:02d}-01'"
        )
        checks["g6_words_zero"] = v == 0

        # 3. site_summary not null
        v = await pg.fetchval(
            f"SELECT COUNT(*) FROM daily_reports WHERE site_summary_text IS NULL "
            f"AND report_date BETWEEN '2025-{month:02d}-01' AND '2025-{month:02d}-31' AND is_mock=false"
        )
        checks["summary_complete"] = v == 0

        # 4. trade filter clean
        v = await pg.fetchval(
            f"SELECT COUNT(*) FROM mapper_activities WHERE trade NOT IN ('건축','토목') "
            f"AND report_date BETWEEN '2025-{month:02d}-01' AND '2025-{month:02d}-31'"
        )
        checks["trade_filter_clean"] = v == 0

        # ... 추가 3 checks (skip_ratio, wp_count, etc.)
    finally:
        await pg.close()
    return checks


async def main(month: int):
    result = await gate_month(month)
    failed = [k for k, v in result.items() if not v]
    if failed:
        print(f"❌ Month {month} gate failed: {failed}")
        sys.exit(1)
    print(f"✅ Month {month} gate passed: {result}")
```

- [ ] **Step 2: Playwright 자동 검증 작성**

```python
# pipeline/tests/e2e/playwright_reports_check.py
async def check_reports_page(date_str: str):
    """reports 페이지 자동 스냅샷 + UI 가드 검증."""
    # mcp__playwright 또는 직접 Playwright 사용
    # http://localhost:5536/reports?date=YYYY-MM-DD
    # - KpiStrip / GapKpiCard / QuadrantCountKpi 모두 값
    # - 분포도 wp 모두 trade ∈ {건축,토목}
    # - wp 클릭 → OptimizerResult [keyword] action / 이유 표시
    # - 진단 G6 금지 단어 0건
    # - ForecastChart aiAdvice 박스 "−N일 만회" badge
    # - similar_cases 3건
    ...
```

- [ ] **Step 3: 1일 sample 로 통과 확인**

- [ ] **Step 4: Commit**

```bash
git commit -am "test(e2e): gate_month + Playwright reports 페이지 자동 검증"
```

---

## Phase 8 — Dry-run + 3개월 점진 실행 (5 tasks)

### Task 26: Azure quota dry-run (D-9~D-8)

**Files:**
- 실행만 (코드 변경 X)

- [ ] **Step 1: 7/1 1일 timing 측정**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
time pipeline/.venv/bin/python3 scripts/seed_dummy_year.py \
  --start-date 2025-07-01 --end-date 2025-07-01 --trades 건축 토목

time pipeline/.venv/bin/python3 scripts/backfill_optimizer_advice_llm.py --date 2025-07-01
```

- [ ] **Step 2: 측정 항목 기록**

- 60 wp × 3 LLM = 180 호출의 wall time
- 분당 burst (Azure 429 비율)
- cases<3 wp 비율 (cold_start 폐기 후 LLM 호출 증가량)
- 평균 wp 당 wall time

- [ ] **Step 3: 결과 기반 semaphore + retry 조정**

```bash
# 측정 결과에 따라 .env.local 수정 (필요 시)
export CPIA_LLM_CONCURRENCY=4   # 또는 측정 후 조정
```

- [ ] **Step 4: dry-run 결과 docs/superpowers/audit/ 에 기록**

```bash
git add docs/superpowers/audit/2026-05-28_quota_dryrun.md
git commit -m "audit(dryrun): 7/1 1일 timing 측정 결과"
```

- [ ] **Step 5: Fallback path 결정 (1일 처리 시간 기준)**

dry-run wall time 결과 따라 분기 (시연 마감 6/5 buffer 확보):

- **녹색 (< 15분 / 일)**: 86일 풀 backfill 진행 (Task 27-29 그대로)
- **노란색 (15~30분 / 일)**: 풀 backfill 시도 + 시연 일자 (7/15, 8/15, 9/15) 우선 보장
- **빨간색 (> 30분 / 일)**: **풀 backfill 포기 + 시연 일자 3개만 우선**. 나머지 일자는 v6/v7 결과 유지 (옛 schema polymorphic rendering 으로 자연 표시)

빨간색 진입 시 추가 task:
```bash
# 시연 일자 3개만 backfill (Task 27-29 대체)
for d in 2025-07-15 2025-08-15 2025-09-15; do
    pipeline/.venv/bin/python3 scripts/seed_dummy_year.py --start-date $d --end-date $d --trades 건축 토목
    pipeline/.venv/bin/python3 scripts/backfill_optimizer_advice_llm.py --date $d
    pipeline/.venv/bin/python3 scripts/backfill_daily_report_views_v2.py --date $d --with-summary
done
```

---

### Task 27: 7월 backfill + gate_month(7)

**Files:**
- 실행만

- [ ] **Step 1: 7월 chain 실행**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 scripts/seed_dummy_year.py \
  --start-date 2025-07-01 --end-date 2025-07-31 --trades 건축 토목

pipeline/.venv/bin/python3 scripts/backfill_optimizer_advice_llm.py \
  --start-date 2025-07-01 --end-date 2025-07-31

pipeline/.venv/bin/python3 scripts/backfill_daily_report_views_v2.py \
  --all-dates --with-summary \
  --start-date 2025-07-01 --end-date 2025-07-31
```

- [ ] **Step 2: gate_month(7) 통과 확인**

```bash
pipeline/.venv/bin/python3 -m pipeline.tests.e2e.check_month_gate 7
```
Expected: `✅ Month 7 gate passed`

- [ ] **Step 3: Playwright 자동 검증 (3 일자: 7/1, 7/15, 7/31)**

```bash
pipeline/.venv/bin/python3 -m pipeline.tests.e2e.playwright_reports_check \
  2025-07-01 2025-07-15 2025-07-31
```

- [ ] **Step 4: 통과 시 자동 다음 월 (사용자 묻지 않음)**

---

### Task 28: 8월 backfill + gate_month(8)

같은 패턴, 일자 범위만 `2025-08-01 ~ 2025-08-31`.

- [ ] **Step 1**: 8월 chain 실행
- [ ] **Step 2**: gate_month(8) 통과 확인
- [ ] **Step 3**: Playwright 자동 검증 (3 일자)
- [ ] **Step 4**: 통과 시 자동 다음

---

### Task 29: 9월 backfill + gate_month(9)

`2025-09-01 ~ 2025-09-24` (24일).

- [ ] **Step 1**: 9월 chain 실행
- [ ] **Step 2**: gate_month(9) 통과 확인
- [ ] **Step 3**: Playwright 자동 검증

---

### Task 30: 종합 retry batch + 시연 D-1 검증

- [ ] **Step 1**: failed_wps_global 종합 retry batch 1회

- [ ] **Step 2**: 시연 시나리오 일자 3개 (7/15, 8/15, 9/15) 수동 점검

- [ ] **Step 3**: 전체 SQL assertion

```bash
/opt/homebrew/Cellar/libpq/18.4/bin/psql "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia" -c "
SELECT 
  COUNT(*) FILTER (WHERE oa.diagnosis='cold_start') AS cold_start,
  COUNT(*) FILTER (WHERE oa.diagnosis LIKE '%정상범주%') AS g6_violations,
  COUNT(*) AS total
FROM optimizer_advice oa JOIN pipeline_runs pr USING(run_id)
WHERE pr.report_date BETWEEN '2025-07-01' AND '2025-09-24';
"
```
Expected: cold_start=0, g6_violations=0.

- [ ] **Step 4**: PR 작성 + push (사용자 머지 권한)

---

## Dependency Graph

```
Task 1 (migration) ──┐
Task 2 (trade_frames.json) ──┐
Task 3 (lookup_frame helper) ──┤
                              ├─→ Task 8-13 (prompts + agent)
Task 4-6 (aggregate.py) ──→ Task 7 (db.py forecast SQL) ──┘
                                                          │
Task 14-18 (view_builder + atomizer + db.py) ────────────┤
                                                          │
Task 19-21 (seed + backfill scripts) ────────────────────┤
                                                          │
Task 22 (FE polymorphic) ─────────────────────────────────┤
                                                          ↓
Task 23-25 (tests)                              Task 26 (dry-run)
                                                          ↓
                                       Task 27-29 (3개월 점진)
                                                          ↓
                                       Task 30 (종합 + 시연 검증)
```

병렬 가능 task:
- Phase 1 (Task 1·2·3) — 서로 독립
- Phase 3 (Task 8·9·10·11) — prompt 변경, 같은 파일이라 순차
- Phase 4 의 Task 14 / 17 / 18 — 다른 파일이라 병렬 가능
- Phase 7 의 Task 23·24·25 — 다른 파일이라 병렬 가능

---

## 애매 지점 (Plan 작성 중 발견) — 실행 전 PoC 로 명확화 필요

사용자 룰: "애매하다 싶으면 실제 데이터 한번 LLM PoC 해보면서 명확화"

### A1. `_build_deterministic_cold_start` 함수의 정확한 호출 위치
- 추정: `view_builder.py:1904` (1차 review feasibility agent 인용)
- **실행 전 확인 필요**: `grep -n "_build_deterministic_cold_start" pipeline/agents/optimizer/view_builder.py`
- 만약 위치 다르면 Task 16 의 dispatch 분기 위치 갱신

### A2. `db.py:insert_forecast` 의 정확한 컬럼 28 list + 순서
- 추정: 28 컬럼 (1차 review feasibility 인용)
- **실행 전 확인 필요**: `sed -n '260,330p' pipeline/db.py`
- 정확한 컬럼 list 확인 후 `point_in_time_delay_days` 의 $29 placeholder 정확 위치 결정

### A3. `mapped_history` 의 ON CONFLICT key 정확 컬럼
- 추정: `(run_id, wa, l6_main, company)`
- **실행 전 확인 필요**: `grep -A 20 "INSERT INTO mapped_history" pipeline/db.py`

### A4. `backfill_optimizer_advice_llm.py` 의 build_atomized_demo_graph 흐름
- 추정: graph 가 mapper node skip
- **실행 전 확인 필요**: `grep -n "build_atomized_demo_graph" pipeline/`

### A5. LLM 호출 시간 예산 (cases<3 폐기로 호출량 증가)
- Task 26 dry-run 결과로 명확화 (semaphore + retry 조정)

이 5건은 **각 task 의 Step 1 (현재 read) 에서 자동 해소** 됨.

---

## Skills Reference

- @superpowers:subagent-driven-development — 본 plan task 단위 실행 (subagent 분산)
- @superpowers:executing-plans — inline 실행 (단일 세션)
- @superpowers:test-driven-development — 각 task TDD 패턴
- @superpowers:finishing-a-development-branch — 모든 task 끝 후 PR + push

---

## Reference

- Spec: `docs/superpowers/specs/2026-05-27-cpia-report-redesign-design.md` (commit `e380e6d`)
- PoC: `/tmp/poc_action_prompt.py` (v7) / `/tmp/poc_trade_frames_v8.py` (v8) / `/tmp/poc_v9_g6_enhanced.py` (v9) / `/tmp/poc_v10_keyword_schema.py` (v10)
- PoC 결과: `/tmp/poc_v8_out2.log` / `/tmp/poc_v9_out.log` / `/tmp/poc_v10_out.log`
- 시연 마감: 2026-06-05 (목)
- Branch: A_Track, HEAD `e380e6d`
- 사용자: 조형준 프로 (시연자)
- AWS PG: `postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia`
- AWS Chroma: 43.200.85.209:5533
- Dev server: `cd web && pnpm dev` → `http://localhost:5536/reports` (`-H 0.0.0.0` 외부 머신 접근)
- venv: `pipeline/.venv/bin/python3`
