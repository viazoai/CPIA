# CPIA Frontend Data Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 5 탭 (home/tasks/review/export/reports) 의 11 area 데이터 연결성 결함 fix + mock 백업 인프라 구축. 모든 변경은 BE/PG/route.ts 데이터 변환 레이어만 — 디자인 불가침.

**Architecture:** PG 7 테이블에 `is_mock` 컬럼 추가 + mock_*.json 의 review_cards / report 를 PG row 로 변환 적재. view_builder 의 `_build_optimizer_view` fan-out + `_evm_by_group` actual anchor + baseline 필드. wbsTreeBuild 의 CTE 재작성 + leaf id 통일.

**Tech Stack:** PostgreSQL (asyncpg + postgres.js) / Python 3.9 (pipeline) / Next.js + TypeScript (web) / Playwright MCP (검증) / pytest (BE unit)

**Spec:** `docs/superpowers/specs/2026-05-20-cpia-frontend-data-binding-design.md`

**디자인 불가침 — 모든 task 가 다음을 위반하지 않음:**
- `web/app/components/**/*.tsx` 의 JSX / className / 색상 / 간격 변경 금지
- 컴포넌트 prop 시그니처 변경 금지
- 새 페이지 / 새 컴포넌트 신설 금지

---

## File Structure

**Create:**
- `infra/postgres/migrations/2026-05-20_add_is_mock.sql` — 7 테이블 ALTER
- `tmp/backfill_mock_rows.py` — mock_review_cards + mock_report → PG row 변환 (one-shot)
- `tmp/verify_fe_data_binding.py` — 5 탭 API 인수 기준 자동 점검 (one-shot)
- `pipeline/tests/test_view_builder_fanout.py` — `_build_optimizer_view` fan-out unit test
- `pipeline/tests/test_view_builder_bars.py` — `_build_contractor_bars` baseline unit test

**Modify:**
- `pipeline/agents/optimizer/view_builder.py` — 3 함수 보강 (`_build_optimizer_view`, `_evm_by_group`, `_build_contractor_bars`/`_build_trade_bars`)
- `web/lib/transforms.ts` — `wbsTreeBuild` (SQL CTE + leaf id + siteName 인자)
- `web/lib/fixtures.ts` — `loadReal:sites_summary` SUM 들에 is_mock 분기
- `web/app/api/mock/review/route.ts` — wbsTreeBuild 호출부 siteName 전달 + is_mock 분기
- `web/app/api/mock/agent-tasks/route.ts` — Parser items SELECT + Mapper LIMIT 200 + total_count + is_mock
- `web/app/api/mock/consolidated/route.ts` — ORDER BY 추가 (2 곳) + is_mock
- `web/app/api/mock/report/route.ts` — is_mock 분기
- `web/app/api/mock/dashboard/route.ts` — is_mock 분기

**참조 (변경 없음):**
- `tmp/backfill_daily_reports.py` — view_builder 변경 후 재실행
- `scripts/run_one_cycle.py` — 검증 단계에서 재실행

---

## Phase 0 — Mock 백업 인프라

### Task 0.1: Migration — 7 테이블 is_mock 컬럼 추가

**Files:**
- Create: `infra/postgres/migrations/2026-05-20_add_is_mock.sql`

- [ ] **Step 1: Migration SQL 작성**

```sql
-- 2026-05-20: mock 데이터 백업 + 시연 fallback 용 is_mock 컬럼 추가
-- sites.is_mock 은 이미 존재 (제외)
-- 참조: spec 2026-05-20-cpia-frontend-data-binding-design.md §4

ALTER TABLE pipeline_runs       ADD COLUMN IF NOT EXISTS is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE parser_reports      ADD COLUMN IF NOT EXISTS is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE parser_activities   ADD COLUMN IF NOT EXISTS is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE mapper_activities   ADD COLUMN IF NOT EXISTS is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE forecasts           ADD COLUMN IF NOT EXISTS is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE optimizer_advice    ADD COLUMN IF NOT EXISTS is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE daily_reports       ADD COLUMN IF NOT EXISTS is_mock BOOL NOT NULL DEFAULT FALSE;

-- partial unique index 영향 X — 컬럼 set 에 is_mock 미포함
```

- [ ] **Step 2: Migration 실행**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h localhost -p 5532 -U cpia -d cpia \
  -f infra/postgres/migrations/2026-05-20_add_is_mock.sql
```

Expected: `ALTER TABLE` × 7 (each "ALTER TABLE")

- [ ] **Step 3: 검증 — 모든 테이블에 is_mock 존재 확인**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h localhost -p 5532 -U cpia -d cpia -c "
SELECT table_name, column_name FROM information_schema.columns
WHERE column_name = 'is_mock' ORDER BY table_name;"
```

Expected: 8 rows (sites + 7 신규)

- [ ] **Step 4: 회귀 — 기존 cycle SELECT 동작 영향 X 확인**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h localhost -p 5532 -U cpia -d cpia -c "
SELECT COUNT(*) FROM mapper_activities WHERE is_mock = FALSE;"
```

Expected: 기존 mapper_activities 전체 count (예: 146 또는 그 이상)

- [ ] **Step 5: Commit**

```bash
git add infra/postgres/migrations/2026-05-20_add_is_mock.sql
git commit -m "feat(db): 7 테이블 is_mock 컬럼 추가 — mock fallback 인프라"
```

---

### Task 0.2: Backfill 스크립트 — mock_review_cards.json → mapper_activities

**Files:**
- Create: `tmp/backfill_mock_rows.py`

- [ ] **Step 1: 사전 — mock_review_cards.json 의 첫 row 확인**

```bash
python3 -c "import json; d=json.load(open('data/mock_review_cards.json')); print(json.dumps(d[0], indent=2, ensure_ascii=False))"
```

Expected: `{id, bp_name, work_content, quantity, unit, ai_mapped_wp_id, ai_mapped_path, confidence, status, alternative_wps, ...}`

- [ ] **Step 2: backfill 스크립트 작성 — 첫 단계 mock pipeline_run + review cards**

```python
"""Mock data 를 PG row 로 backfill — is_mock=TRUE.

mock_review_cards.json → mapper_activities + parser_activities
mock_report.json → daily_reports (jsonb 컬럼들)

실행: pipeline/.venv/bin/python3 tmp/backfill_mock_rows.py
"""

from __future__ import annotations
import asyncio
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.db import PGClient

MOCK_RUN_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
MOCK_SITE_ID = "DEMO_SITE"
MOCK_DATE = date(2025, 9, 25)


def _split_kebab_wp_id(wp_id: str) -> tuple[str, str]:
    """ai_mapped_wp_id (kebab `wa-l6`) → (wa, l6_main) 역변환.
    
    예: "cub-cable-tray공사" → ("cub", "cable-tray공사")
    한국어 l6 가 dash 포함 가능 → 첫 dash 만 split.
    """
    parts = wp_id.split("-", 1)
    if len(parts) == 2:
        return parts[0].upper(), parts[1]
    return wp_id, ""


async def backfill_review_cards(pg: PGClient) -> int:
    cards = json.loads((ROOT / "data" / "mock_review_cards.json").read_text())
    
    async with pg._pool.acquire() as con:
        # mock pipeline_run row 사전 INSERT (FK 보장)
        await con.execute("""
            INSERT INTO pipeline_runs (run_id, site_id, report_date, status, is_mock)
            VALUES ($1, $2, $3, 'completed', TRUE)
            ON CONFLICT (run_id) DO UPDATE SET is_mock = TRUE
        """, MOCK_RUN_ID, MOCK_SITE_ID, MOCK_DATE)
        
        inserted = 0
        for idx, card in enumerate(cards):
            wa, l6 = _split_kebab_wp_id(card.get("ai_mapped_wp_id") or "")
            await con.execute("""
                INSERT INTO parser_activities (run_id, idx, company, work_content, today_qty, unit, is_mock)
                VALUES ($1, $2, $3, $4, $5, $6, TRUE)
                ON CONFLICT DO NOTHING
            """, MOCK_RUN_ID, idx, card.get("bp_name"), card.get("work_content"),
                card.get("quantity"), card.get("unit"))
            
            await con.execute("""
                INSERT INTO mapper_activities
                  (run_id, idx, company, today_qty, unit, wa, l6_main,
                   mapping_conf, requires_review, alternatives, is_mock)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, TRUE)
                ON CONFLICT DO NOTHING
            """, MOCK_RUN_ID, idx, card.get("bp_name"), card.get("quantity"), card.get("unit"),
                wa, l6, card.get("confidence"),
                card.get("status") == "unconfirmed",
                json.dumps(card.get("alternative_wps") or []))
            inserted += 1
        return inserted


async def main():
    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        n_cards = await backfill_review_cards(pg)
        print(f"✅ mock_review_cards: {n_cards} rows inserted (is_mock=TRUE)")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: 실행 + 결과 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  pipeline/.venv/bin/python3 tmp/backfill_mock_rows.py
```

Expected: `✅ mock_review_cards: 13 rows inserted`

- [ ] **Step 4: PG 검증**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h localhost -p 5532 -U cpia -d cpia -c "
SELECT COUNT(*) FROM mapper_activities WHERE is_mock = TRUE;
SELECT bp_name, ai_mapped_wp_id FROM mapper_activities ma 
  JOIN parser_activities pa ON pa.run_id=ma.run_id AND pa.idx=ma.idx
  WHERE ma.is_mock = TRUE LIMIT 3;" 2>&1 | head -10
```

Expected: count=13. 첫 3 row 의 bp_name + wp_id 표시.

- [ ] **Step 5: Commit**

```bash
git add tmp/backfill_mock_rows.py
git commit -m "feat(mock): mock_review_cards → mapper/parser_activities backfill (is_mock=TRUE)"
```

---

### Task 0.3: Backfill 스크립트 — mock_report.json → daily_reports

**Files:**
- Modify: `tmp/backfill_mock_rows.py` (append `backfill_report` 함수)

- [ ] **Step 1: 사전 — mock_report.json shape 확인**

```bash
python3 -c "
import json
d = json.load(open('data/mock_report.json'))
print('daily len:', len(d['daily']))
print('details dates:', list(d['details'].keys())[:3])
first = d['details'][list(d['details'].keys())[0]]
print('detail keys:', list(first.keys()))
print('kpi:', first.get('kpi'))
"
```

Expected: `daily len: N`, `detail keys: [kpi, s_curve, contractor_bars, trade_bars, quadrant, optimizer, scenarios, wp_summary, raw_data]`

- [ ] **Step 2: backfill_report 함수 추가**

```python
async def backfill_report(pg: PGClient) -> int:
    report = json.loads((ROOT / "data" / "mock_report.json").read_text())
    daily = report.get("daily", [])
    details = report.get("details", {})
    
    inserted = 0
    async with pg._pool.acquire() as con:
        for d in daily:
            d_date = date.fromisoformat(d["date"])
            detail = details.get(d["date"], {})
            
            # mock 별 run_id 는 date 기반 deterministic UUID
            run_id = uuid.UUID(int=int(d_date.toordinal()) << 96 | 0x000000000000DEAD)
            
            await con.execute("""
                INSERT INTO pipeline_runs (run_id, site_id, report_date, status, is_mock)
                VALUES ($1, $2, $3, 'completed', TRUE)
                ON CONFLICT (run_id) DO UPDATE SET is_mock = TRUE
            """, run_id, MOCK_SITE_ID, d_date)
            
            await con.execute("""
                INSERT INTO daily_reports
                  (run_id, site_id, report_date, report_md,
                   kpi_jsonb, s_curve_jsonb, contractor_bars_jsonb, trade_bars_jsonb,
                   quadrant_jsonb, wp_summary_jsonb, optimizer_view_jsonb,
                   scenarios_jsonb, productivity_jsonb, is_mock)
                VALUES ($1, $2, $3, '',
                        $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb,
                        $8::jsonb, $9::jsonb, $10::jsonb,
                        $11::jsonb, '{}'::jsonb, TRUE)
                ON CONFLICT DO NOTHING
            """, run_id, MOCK_SITE_ID, d_date,
                json.dumps(detail.get("kpi") or {}),
                json.dumps(detail.get("s_curve") or []),
                json.dumps(detail.get("contractor_bars") or []),
                json.dumps(detail.get("trade_bars") or []),
                json.dumps(detail.get("quadrant") or []),
                json.dumps(detail.get("wp_summary") or []),
                json.dumps(detail.get("optimizer") or {}),
                json.dumps(detail.get("scenarios") or {}))
            inserted += 1
    return inserted


# main() 에 추가:
# n_reports = await backfill_report(pg)
# print(f"✅ mock_report: {n_reports} daily_reports rows inserted")
```

- [ ] **Step 3: main() 에 backfill_report 호출 추가 + 실행**

```bash
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  pipeline/.venv/bin/python3 tmp/backfill_mock_rows.py
```

Expected: `✅ mock_review_cards: 13 ...`, `✅ mock_report: N daily_reports rows ...`

- [ ] **Step 4: PG 검증**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h localhost -p 5532 -U cpia -d cpia -c "
SELECT COUNT(*) FROM daily_reports WHERE is_mock = TRUE;
SELECT report_date, jsonb_array_length(contractor_bars_jsonb) AS cbar,
       jsonb_array_length(quadrant_jsonb) AS quad 
  FROM daily_reports WHERE is_mock = TRUE LIMIT 5;" 2>&1 | head -10
```

Expected: count > 0, cbar/quad > 0.

- [ ] **Step 5: Commit**

```bash
git add tmp/backfill_mock_rows.py
git commit -m "feat(mock): mock_report.json → daily_reports 전체 jsonb backfill"
```

---

### Task 0.4: Route.ts + fixtures.ts 에 is_mock 분기 추가

**Files:**
- Modify: `web/app/api/mock/review/route.ts`
- Modify: `web/app/api/mock/agent-tasks/route.ts`
- Modify: `web/app/api/mock/consolidated/route.ts`
- Modify: `web/app/api/mock/report/route.ts`
- Modify: `web/app/api/mock/dashboard/route.ts`
- Modify: `web/lib/fixtures.ts`

- [ ] **Step 1: 패턴 — 각 route.ts 맨 위 + 모든 mapper/forecasts/optimizer/daily_reports SELECT 에 useMock 분기**

각 파일 상단:
```ts
const useMock = process.env.CPIA_DEMO_FALLBACK === "on";
```

각 SQL 의 WHERE 절에 `AND <table>.is_mock = ${useMock}` 추가:

```ts
// 예: review/route.ts
const cardRows = await sql`
  SELECT ... FROM mapper_activities ma ...
  WHERE ma.requires_review = TRUE
    AND ma.is_mock = ${useMock}    -- ← 추가
  ORDER BY ma.mapping_conf ASC NULLS FIRST
`;
```

- [ ] **Step 2: review/route.ts 보강**

`siteRow` SELECT 의 `WHERE is_mock = FALSE` → `WHERE is_mock = ${useMock}`.
`cardRows` SELECT 에 `AND ma.is_mock = ${useMock}` 추가.

- [ ] **Step 3: agent-tasks/route.ts 보강**

dateRows / runRows / mapperItems 의 모든 SELECT 에 `AND pr.is_mock = ${useMock}` 또는 `AND ma.is_mock = ${useMock}` 추가.

- [ ] **Step 4: consolidated/route.ts 보강**

dates / counts / reportRows / acts 모두 `AND pr.is_mock = ${useMock}` 또는 해당 table.is_mock 추가.

- [ ] **Step 5: report/route.ts 보강**

rows SELECT 에 `AND dr.is_mock = ${useMock}` 추가.

- [ ] **Step 6: dashboard/route.ts 보강**

trend SELECT 에 `AND dr.is_mock = ${useMock}` 추가.

- [ ] **Step 7: fixtures.ts loadReal:sites_summary 보강**

agg / today / siteAgg / review / abnormal SQL 5개 모두 `WHERE is_mock = ${useMock}` (sites/pipeline_runs/mapper_activities/forecasts 각각). `loadReal:agent_status` 의 counts SELECT 에도 `AND is_mock = ${useMock}`. `loadReal:chat_sequence` 의 latest SELECT 도 동일.

- [ ] **Step 8: dev 서버 확인 — default 모드 (useMock=false)**

```bash
curl -s http://127.0.0.1:5536/api/mock/review | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('cards:', len(d['cards']))
print('wbs root:', d['wbs']['name'])"
```

Expected: cards 50건 (현재 PG 실측, mock 13 제외). wbs root 정상.

- [ ] **Step 9: env 토글 시연 fallback 확인**

```bash
# dev 서버 재시작 (env 적용)
CPIA_DEMO_FALLBACK=on PORT=5537 npm --prefix web run dev > /tmp/dev_mock.log 2>&1 &
sleep 5
curl -s http://127.0.0.1:5537/api/mock/review | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('mock cards:', len(d['cards']))"
```

Expected: `mock cards: 13` (mock_review_cards.json 의 13 row).

```bash
kill $(lsof -ti:5537) 2>/dev/null
```

- [ ] **Step 10: Commit**

```bash
git add web/
git commit -m "feat(web): is_mock 분기 5 route + fixtures.ts (CPIA_DEMO_FALLBACK env)"
```

---

## Phase 1 — view_builder fan-out + actual anchor + baseline

### Task 1.1: `_build_optimizer_view` fan-out — WP 클릭 시 진단 표시 fix

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:549` (`_build_optimizer_view`)
- Create: `pipeline/tests/test_view_builder_fanout.py`

- [ ] **Step 1: 실패 테스트 작성 — fan-out 결과 검증**

```python
# pipeline/tests/test_view_builder_fanout.py
"""_build_optimizer_view fan-out — 한 advice 가 여러 wa 에 대응 시 by_wp 에 모두 적재.

spec 2026-05-20-cpia-frontend-data-binding-design.md § 8.3 (B) 옵션.
"""
from __future__ import annotations
from pipeline.agents.optimizer.view_builder import _build_optimizer_view


def test_fanout_single_wa():
    """(l6, company) → wa 1개 → by_wp key 1개."""
    advice = [{
        "company": "창원기전", "l6_main": "CABLE TRAY공사",
        "diagnosis": "test", "recommendations": [], "degradation_cases": [],
        "recovery_distribution": {}, "recovery_pattern": [],
    }]
    forecast = [{"company": "창원기전", "l6_main": "CABLE TRAY공사",
                 "risk_level": "이상", "delay_days": 5}]
    wa_lookup = {("CABLE TRAY공사", "창원기전"): ["CUB"]}
    
    result = _build_optimizer_view(advice, forecast, mapped=[], wa_lookup=wa_lookup)
    
    assert "cub-cable-tray공사-창원기전" in result["by_wp"]
    assert len(result["by_wp"]) == 1


def test_fanout_multi_wa():
    """(l6, company) → wa 2개 → by_wp key 2개, 같은 diagnosis 복사."""
    advice = [{
        "company": "창원기전", "l6_main": "CABLE TRAY공사",
        "diagnosis": "test", "recommendations": [], "degradation_cases": [],
        "recovery_distribution": {}, "recovery_pattern": [],
    }]
    forecast = [{"company": "창원기전", "l6_main": "CABLE TRAY공사",
                 "risk_level": "이상", "delay_days": 5}]
    wa_lookup = {("CABLE TRAY공사", "창원기전"): ["CUB", "FAB"]}
    
    result = _build_optimizer_view(advice, forecast, mapped=[], wa_lookup=wa_lookup)
    
    keys = result["by_wp"].keys()
    assert "cub-cable-tray공사-창원기전" in keys
    assert "fab-cable-tray공사-창원기전" in keys
    assert result["by_wp"]["cub-cable-tray공사-창원기전"]["diagnosis"] == "test"
    assert result["by_wp"]["fab-cable-tray공사-창원기전"]["diagnosis"] == "test"


def test_no_wa_lookup_fallback():
    """wa_lookup 비어있으면 기존 None wa 동작 보존 (regression)."""
    advice = [{
        "company": "X", "l6_main": "Y",
        "diagnosis": "test", "recommendations": [], "degradation_cases": [],
        "recovery_distribution": {}, "recovery_pattern": [],
    }]
    forecast = [{"company": "X", "l6_main": "Y", "risk_level": "정상", "delay_days": 0}]
    
    result = _build_optimizer_view(advice, forecast, mapped=[], wa_lookup={})
    
    # wa_lookup 비어있으면 wa="unknown" 으로 적재 (기존 동작 유지)
    assert "unknown-y-x" in result["by_wp"]
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && \
  pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_view_builder_fanout.py -v 2>&1 | tail -20
```

Expected: FAIL — `TypeError: _build_optimizer_view() got an unexpected keyword argument 'wa_lookup'`

- [ ] **Step 3: `_build_optimizer_view` 수정 — wa_lookup 인자 + fan-out 로직**

`pipeline/agents/optimizer/view_builder.py:549` 의 `_build_optimizer_view` 시그니처 + 본문 변경:

```python
def _build_optimizer_view(
    advice_rows: list[dict[str, Any]],
    forecast: list[dict[str, Any]],
    mapped: list[dict[str, Any]],
    wa_lookup: dict[tuple[str, str], list[str]] | None = None,
) -> dict[str, Any]:
    """§ 02 by_wp dict — 진단/유사사례/권고/상세 6칸.
    
    wa_lookup: (l6_main, company) → DISTINCT wa list. fan-out 용.
                None 또는 빈 dict 면 wa="unknown" 단일 key 적재 (기존 동작).
    """
    wa_lookup = wa_lookup or {}
    by_wp: dict[str, dict[str, Any]] = {}
    
    for advice in advice_rows:
        matched_f = next(
            (f for f in forecast
             if f.get("company") == advice.get("company")
             and f.get("l6_main") == advice.get("l6_main")),
            None,
        )
        if matched_f is None:
            continue
        
        # fan-out: wa_lookup 의 모든 wa 마다 같은 advice 적재.
        # lookup miss → ["unknown"] fallback (기존 동작).
        wa_list = wa_lookup.get(
            (advice.get("l6_main"), advice.get("company")),
            None,
        ) or [matched_f.get("wa")]  # forecasts.wa 도 보존 (NULL 시 None → kebab "unknown")
        
        # 진단 dict (기존 로직 그대로)
        similar_cases = []
        for c in (advice.get("degradation_cases") or []):
            activities = c.get("activities") or []
            conditions = c.get("conditions") or ""
            productivity = c.get("productivity") or 0
            recovery = c.get("recovery") or {}
            rd = recovery.get("recovery_days") if isinstance(recovery, dict) else None
            similar_cases.append({
                "date": c.get("date") or "",
                "description": f"{conditions} - {activities[0] if activities else ''}, 생산성 {productivity:.1f}",
                "outcome": f"{rd}일 후 회복" if rd is not None else "미회복",
            })
        
        recs_raw = advice.get("recommendations") or []
        recommendations = [
            (r.get("text") if isinstance(r, dict) else str(r)) or "" for r in recs_raw
        ]
        
        rp = advice.get("recovery_pattern") or []
        rd_vals = [p.get("recovery_days") for p in rp if isinstance(p, dict) and p.get("recovery_days") is not None]
        avg_rd = (sum(rd_vals) / len(rd_vals)) if rd_vals else None
        rdist = advice.get("recovery_distribution") or {}
        rdist_text = " / ".join(f"{k}: {v}건" for k, v in rdist.items()) if isinstance(rdist, dict) else ""
        
        details = [
            {"label": "위험 평가", "value": matched_f.get("risk_level") or "—"},
            {"label": "진단 대상", "value": f"{advice.get('company') or ''} · {advice.get('l6_main') or ''}"},
            {"label": "유사 사례 수", "value": f"{len(advice.get('degradation_cases') or [])}건"},
            {"label": "평균 회복 일수", "value": f"{avg_rd:.1f}일" if avg_rd is not None else "—"},
            {"label": "회복 분포", "value": rdist_text or "—"},
            {"label": "일정 영향", "value": f"{round(matched_f.get('delay_days') or 0)}일 지연"},
        ]
        
        advice_dict = {
            "diagnosis": advice.get("diagnosis") or "",
            "similar_cases": similar_cases,
            "recommendations": recommendations,
            "details": details,
        }
        
        # fan-out: 각 wa 마다 by_wp 에 적재
        for wa in wa_list:
            wp_id = _wp_id_of(wa, advice.get("l6_main"), advice.get("company"))
            by_wp[wp_id] = advice_dict
    
    default_wp_id = next(iter(by_wp.keys()), None)
    return {"by_wp": by_wp, "default_wp_id": default_wp_id}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_view_builder_fanout.py -v 2>&1 | tail -10
```

Expected: 3 passed.

- [ ] **Step 5: 호출부 — `agent.py` 가 wa_lookup 전달**

`pipeline/agents/optimizer/agent.py` 의 `_build_optimizer_view` 호출 부근 (~line 184) 에 PG SELECT 로 wa_lookup 빌드:

```python
# wa_lookup: (l6_main, company) → DISTINCT wa list (NULL wa 제외).
async with pg._pool.acquire() as con:
    rows = await con.fetch("""
        SELECT l6_main, company, array_agg(DISTINCT wa) FILTER (WHERE wa IS NOT NULL) AS wa_list
        FROM mapper_activities
        WHERE run_id = $1
        GROUP BY l6_main, company
    """, run_id)
wa_lookup = {(r["l6_main"], r["company"]): list(r["wa_list"] or []) for r in rows}

view_jsonbs["optimizer_view_jsonb"] = _build_optimizer_view(
    advice_rows, forecast, mapped, wa_lookup=wa_lookup,
)
```

- [ ] **Step 6: `tmp/backfill_daily_reports.py` 도 wa_lookup 전달 보강**

같은 패턴으로 `tmp/backfill_daily_reports.py:93` 의 `_build_optimizer_view(advice_l, forecasts_l, [])` 를 wa_lookup 추가 호출로 변경.

- [ ] **Step 7: backfill 재실행 + PG 검증**

```bash
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  pipeline/.venv/bin/python3 tmp/backfill_daily_reports.py
```

Expected: 모든 jsonb 컬럼 success.

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h localhost -p 5532 -U cpia -d cpia -c "
SELECT jsonb_object_keys(optimizer_view_jsonb->'by_wp') 
  FROM daily_reports WHERE is_mock = FALSE ORDER BY created_at DESC LIMIT 1;" 2>&1 | head -20
```

Expected: keys 가 `fab-cable-tray공사-창원기전` 등 실 wa prefix (현재 unknown- 가 아닌).

- [ ] **Step 8: Commit**

```bash
git add pipeline/agents/optimizer/view_builder.py pipeline/agents/optimizer/agent.py \
        pipeline/tests/test_view_builder_fanout.py tmp/backfill_daily_reports.py
git commit -m "fix(view_builder): _build_optimizer_view wa fan-out — WP 진단 매칭 (§8.3)"
```

---

### Task 1.2: `_evm_by_group` actual anchor — 매핑된 업체만 표시

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:128` (`_evm_by_group`)

- [ ] **Step 1: 현재 cycle 의 contractor 갯수 확인 (before)**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h localhost -p 5532 -U cpia -d cpia -c "
SELECT jsonb_array_length(contractor_bars_jsonb) AS cbar_n,
       jsonb_array_length(trade_bars_jsonb) AS tbar_n
  FROM daily_reports WHERE is_mock = FALSE ORDER BY created_at DESC LIMIT 1;"
```

Expected (before): cbar_n=80, tbar_n=58.

- [ ] **Step 2: `_evm_by_group` 의 FROM 절 수정**

`view_builder.py:128` 의 `_evm_by_group` 함수 안 SQL 변경. `FROM plan_agg p FULL OUTER JOIN actual_agg a USING (gkey)` 부분을:

```python
sql = f"""
    WITH plan_agg AS (
        SELECT {plan_gkey} AS gkey,
               SUM(am.plan_total_qty * {_PROGRESS_RATIO_SQL})::float AS cum_plan_qty,
               SUM(am.plan_mh_rev2 * {_PROGRESS_RATIO_SQL})::float AS cum_plan_mh,
               SUM(am.plan_total_qty)::float AS plan_qty_full,
               SUM(am.plan_mh_rev2)::float AS plan_mh_full
        FROM activity_master am
        WHERE am.site_id = $1 AND {plan_gkey} IS NOT NULL
        GROUP BY {plan_gkey}
    ),
    actual_agg AS (
        SELECT {actual_gkey} AS gkey,
               SUM(COALESCE(ma.today_cum_qty, 0))::float AS cum_actual_qty,
               SUM(COALESCE(ma.cum_actual_mh_today, 0))::float AS cum_actual_mh
        FROM mapper_activities ma
        JOIN pipeline_runs pr USING (run_id)
        WHERE pr.site_id = $1 AND pr.report_date = $2 AND {actual_gkey} IS NOT NULL
        GROUP BY {actual_gkey}
    )
    SELECT a.gkey AS gkey,
           COALESCE(p.cum_plan_qty, 0)::float AS cum_plan_qty,
           COALESCE(p.cum_plan_mh, 0)::float AS cum_plan_mh,
           COALESCE(p.plan_qty_full, 0)::float AS plan_qty_full,
           COALESCE(p.plan_mh_full, 0)::float AS plan_mh_full,
           a.cum_actual_qty::float AS cum_actual_qty,
           a.cum_actual_mh::float AS cum_actual_mh
    FROM actual_agg a
    LEFT JOIN plan_agg p USING (gkey)
"""
```

핵심 변경: `FROM plan_agg p FULL OUTER JOIN actual_agg a` → `FROM actual_agg a LEFT JOIN plan_agg p`. actual 측에 있는 (= 실제 매핑된) gkey 만 나타남.

`_evm_for_group` (site EVM) 과 `_evm_by_wa_l6_company` 는 그대로 — 영향 X.

- [ ] **Step 3: backfill 재실행 + 검증 (after)**

```bash
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  pipeline/.venv/bin/python3 tmp/backfill_daily_reports.py
```

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h localhost -p 5532 -U cpia -d cpia -c "
SELECT jsonb_array_length(contractor_bars_jsonb) AS cbar_n,
       jsonb_array_length(trade_bars_jsonb) AS tbar_n
  FROM daily_reports WHERE is_mock = FALSE ORDER BY created_at DESC LIMIT 1;
SELECT contractor_bars_jsonb->0 FROM daily_reports WHERE is_mock = FALSE ORDER BY created_at DESC LIMIT 1;"
```

Expected: cbar_n=3 (창원기전 / 세보엠이씨 / 남웅건설), tbar_n 작아짐.

- [ ] **Step 4: 회귀 — site EVM (kpi_jsonb) 영향 없음 확인**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h localhost -p 5532 -U cpia -d cpia -c "
SELECT kpi_jsonb FROM daily_reports WHERE is_mock = FALSE ORDER BY created_at DESC LIMIT 1;"
```

Expected: cpi/spi/delay_days 값이 이전과 동일 (별도 함수 `_evm_for_group` 사용).

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/optimizer/view_builder.py
git commit -m "fix(view_builder): _evm_by_group actual anchor — 매핑된 업체만 표시 (§8.1)"
```

---

### Task 1.3: `_build_*_bars` baseline 필드 — "0개사" → 정상 표시

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:291` (`_build_contractor_bars`, `_build_trade_bars`)
- Create: `pipeline/tests/test_view_builder_bars.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# pipeline/tests/test_view_builder_bars.py
"""_build_contractor_bars / _build_trade_bars 의 baseline 필드.

spec § 8.2 — ProductivityBarToggle 의 underCount 계산용.
"""
from __future__ import annotations
from pipeline.agents.optimizer.view_builder import (
    _build_contractor_bars,
    _build_trade_bars,
)


def test_contractor_bars_has_baseline():
    productivity = {"by_contractor": {"창원기전": {"cpi": 85.0}, "세보": {"cpi": 95.0}}}
    bars = _build_contractor_bars(productivity)
    
    assert all("baseline" in b for b in bars)
    assert all(b["baseline"] == 90 for b in bars)


def test_trade_bars_has_baseline():
    productivity = {"by_l6": {"CABLE TRAY공사": {"cpi": 75.0}}}
    bars = _build_trade_bars(productivity)
    
    assert bars[0]["baseline"] == 90
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_view_builder_bars.py -v 2>&1 | tail -10
```

Expected: FAIL — `KeyError: 'baseline'`.

- [ ] **Step 3: `_build_contractor_bars` + `_build_trade_bars` 에 baseline 추가**

`view_builder.py:291` 의 두 함수 각각 dict comprehension 에 `"baseline": 90` 추가.

- [ ] **Step 4: 테스트 통과 확인**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_view_builder_bars.py -v 2>&1 | tail -10
```

Expected: 2 passed.

- [ ] **Step 5: backfill 재실행 + PG 검증**

```bash
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  pipeline/.venv/bin/python3 tmp/backfill_daily_reports.py
```

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h localhost -p 5532 -U cpia -d cpia -c "
SELECT contractor_bars_jsonb->0 FROM daily_reports WHERE is_mock = FALSE ORDER BY created_at DESC LIMIT 1;"
```

Expected: `{"label": "...", "value": ..., "baseline": 90, "status": "..."}` — baseline 키 존재.

- [ ] **Step 6: Commit**

```bash
git add pipeline/agents/optimizer/view_builder.py pipeline/tests/test_view_builder_bars.py
git commit -m "fix(view_builder): _build_*_bars baseline=90 — '0개사 평균미만' fix (§8.2)"
```

---

## Phase 2 — Review 탭

### Task 2.1: `wbsTreeBuild` SQL CTE 재작성 — 14736 → 63

**Files:**
- Modify: `web/lib/transforms.ts:162` (`wbsTreeBuild`)

- [ ] **Step 1: 사전 — 현재 review_count 확인**

```bash
curl -s http://127.0.0.1:5536/api/mock/review | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('root review_count:', d['wbs']['review_count'])"
```

Expected (before): 14736.

- [ ] **Step 2: `wbsTreeBuild` SQL 통째로 CTE 패턴으로 교체**

`web/lib/transforms.ts:162` 의 SQL 변경:

```ts
const useMock = process.env.CPIA_DEMO_FALLBACK === "on";
const rows = await sql`
  WITH review_agg AS (
    SELECT ma.wa, ma.l6_main, COUNT(*) AS review_count
    FROM mapper_activities ma JOIN pipeline_runs pr USING(run_id)
    WHERE pr.site_id = ${siteId}
      AND ma.requires_review = TRUE
      AND ma.is_mock = ${useMock}
    GROUP BY ma.wa, ma.l6_main
  ),
  forecast_agg AS (
    SELECT f.l6_main, f.company,
           MIN(CASE f.risk_level WHEN '이상' THEN 1 WHEN '주의' THEN 2 ELSE 3 END) AS worst_risk
    FROM forecasts f JOIN pipeline_runs pr USING(run_id)
    WHERE pr.site_id = ${siteId} AND f.is_mock = ${useMock}
    GROUP BY f.l6_main, f.company
  )
  SELECT am.site_id, am.wa, am.l5_disc, am.l6_main,
         COALESCE(ra.review_count, 0) AS review_count,
         fa.worst_risk
  FROM activity_master am
  LEFT JOIN review_agg ra ON ra.wa = am.wa AND ra.l6_main = am.l6_main
  LEFT JOIN forecast_agg fa ON fa.l6_main = am.l6_main AND fa.company = am.company
  WHERE am.site_id = ${siteId}
`;
```

- [ ] **Step 3: dev 서버 hot reload 확인**

```bash
curl -s http://127.0.0.1:5536/api/mock/review | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('root review_count:', d['wbs']['review_count'])"
```

Expected (after): 63 또는 실 mapper_activities WHERE requires_review AND pr.site_id='m15x-ph3-ibl' count.

- [ ] **Step 4: Playwright 시각 검증**

```bash
# dev 서버에서 /review 페이지 navigate 후 wbs root 옆 숫자 확인
```

Expected: WBS root 옆 알림 63.

- [ ] **Step 5: Commit**

```bash
git add web/lib/transforms.ts
git commit -m "fix(transforms): wbsTreeBuild SQL CTE — review_count 14736→63 (§6.2)"
```

---

### Task 2.2: `wbsTreeBuild` leaf id = `deriveWpIdAndPath` 통일 — wbs 클릭 매칭

**Files:**
- Modify: `web/lib/transforms.ts:218` (leaf 생성 부분)

- [ ] **Step 1: 사전 — 현재 wbs 클릭 시 0 매칭 확인**

curl 로는 클릭 시뮬레이션 어려움 → Playwright 또는 시각 확인.

- [ ] **Step 2: leaf 노드 id 변경**

`wbsTreeBuild` 안의 leaf 생성 (l6Node) 부분 (`transforms.ts:218` 부근):

```ts
const l6Node: WBSNode = {
  id: deriveWpIdAndPath(r.wa, r.l6_main, siteName).wp_id,  // ← 변경: `${discKey}::${r.l6_main}` 대신
  type: "work_package",
  name: r.l6_main,
  parent_id: discNode.id,
  review_count: reviewCount,
  status: riskToStatus(r.worst_risk),
  children: [],
};
```

trade / building 노드 id 는 그대로 (`${wa}::${l5_disc}` 등).

- [ ] **Step 3: 검증 — leaf id 와 card wp_id 가 일치하는지 curl 로 확인**

```bash
curl -s http://127.0.0.1:5536/api/mock/review | python3 -c "
import json, sys
d = json.load(sys.stdin)
# leaf id 들 추출
def leaves(n):
    if n.get('type') == 'work_package': return [n['id']]
    return [x for c in n.get('children', []) for x in leaves(c)]
leaf_ids = set(leaves(d['wbs']))
card_ids = set(c['ai_mapped_wp_id'] for c in d['cards'])
print('leaf 수:', len(leaf_ids))
print('card 수:', len(card_ids))
print('교집합:', len(leaf_ids & card_ids))
print('샘플:', list(leaf_ids)[:3], 'vs', list(card_ids)[:3])"
```

Expected: 교집합 > 0 (이전 0). leaf id format = card id format.

- [ ] **Step 4: Playwright 시각 검증 — CUB > 전기 > CABLE TRAY공사 클릭 시 창원기전 카드 표시**

- [ ] **Step 5: Commit**

```bash
git add web/lib/transforms.ts
git commit -m "fix(transforms): wbs leaf id = deriveWpIdAndPath format — wbs 클릭 매칭 (§6.3)"
```

---

### Task 2.3: `wbsTreeBuild` siteName 인자 + root 표시값

**Files:**
- Modify: `web/lib/transforms.ts:162` (시그니처)
- Modify: `web/app/api/mock/review/route.ts` (호출부)

- [ ] **Step 1: `wbsTreeBuild` 시그니처 변경**

`transforms.ts:162`:
```ts
export async function wbsTreeBuild(siteId: string, siteName: string): Promise<WBSNode> {
  ...
  const root: WBSNode = {
    id: siteId,
    type: "building",
    name: siteName,  // ← 변경
    parent_id: null,
    ...
  };
  ...
}
```

- [ ] **Step 2: review/route.ts 호출부 보강**

`web/app/api/mock/review/route.ts:18`:
```ts
const wbs = await wbsTreeBuild(siteId, siteName);
```

- [ ] **Step 3: 검증**

```bash
curl -s http://127.0.0.1:5536/api/mock/review | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('wbs root name:', d['wbs']['name'])"
```

Expected: `M15X Ph-3 IBL` (sites.name 컬럼 값).

- [ ] **Step 4: Commit**

```bash
git add web/lib/transforms.ts web/app/api/mock/review/route.ts
git commit -m "fix(transforms): wbsTreeBuild siteName 인자 — root 표시값 (§6.1)"
```

---

## Phase 3 — Export 탭

### Task 3.1: `consolidated/route.ts` SQL 에 ORDER BY 추가

**Files:**
- Modify: `web/app/api/mock/consolidated/route.ts`

- [ ] **Step 1: 사전 — 현재 시트 1-3 = 0 확인**

```bash
curl -s "http://127.0.0.1:5536/api/mock/consolidated?date=2025-09-25" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('sheet_row_counts:', d['sheet_row_counts'])"
```

Expected (before): output_manpower=0, occupation_manpower=0, equipment=0, quantity=292.

- [ ] **Step 2: 단건 path SQL 보강 (`route.ts:117`)**

```ts
const reportRows = await sql`
  SELECT bp_summaries, job_allocations, equipment_allocations
  FROM parser_reports
  WHERE report_date = ${date}
    AND is_mock = ${useMock}
  ORDER BY created_at DESC
  LIMIT 1
`;
```

- [ ] **Step 3: list path 의 jsonb_array_length subquery 도 보강 (`route.ts:53`)**

각 `SELECT jsonb_array_length(...) FROM parser_reports WHERE report_date = ${dStr} LIMIT 1` subquery 에 `ORDER BY created_at DESC` 추가:

```sql
SELECT jsonb_array_length(bp_summaries)
FROM parser_reports 
WHERE report_date = ${dStr} AND is_mock = ${useMock}
ORDER BY created_at DESC LIMIT 1
```

3 subquery 모두 동일 패턴.

- [ ] **Step 4: 검증 (after)**

```bash
curl -s "http://127.0.0.1:5536/api/mock/consolidated?date=2025-09-25" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('sheet_row_counts:', d['sheet_row_counts'])"
```

Expected: output_manpower=9, occupation_manpower=108, equipment=95, quantity=292.

- [ ] **Step 5: Commit**

```bash
git add web/app/api/mock/consolidated/route.ts
git commit -m "fix(consolidated): SQL ORDER BY created_at DESC — 시트 1-3 = 0 fix (§7.1)"
```

---

## Phase 4 — Tasks 탭

### Task 4.1: Parser items SELECT

**Files:**
- Modify: `web/app/api/mock/agent-tasks/route.ts:82`

- [ ] **Step 1: Parser items SELECT 추가**

`agent-tasks/route.ts` 의 dStr loop 안:

```ts
const parserItems = await sql`
  SELECT pa.id, pa.trade, pa.company, pa.work_content
  FROM parser_activities pa JOIN pipeline_runs pr USING(run_id)
  WHERE pr.report_date = ${dStr} AND pa.is_mock = ${useMock}
  ORDER BY pa.id
  LIMIT 200
`;
items["Parser"] = parserItems.map((r) => ({
  id: `parser-${r.id}`,
  trade: r.trade ?? r.work_content ?? "—",
  contractor: r.company ?? "—",
  status: "done" as const,
}));
```

- [ ] **Step 2: 검증**

```bash
curl -s http://127.0.0.1:5536/api/mock/agent-tasks | python3 -c "
import json, sys
d = json.load(sys.stdin)
items = d['itemsByDate']['2025-09-25']
print('Parser:', len(items['Parser']))
print('first Parser:', items['Parser'][0] if items['Parser'] else '-')"
```

Expected: `Parser: 200` (또는 실 parser_activities count), first row 의 contractor 가 실 BP명.

- [ ] **Step 3: Playwright — Tasks > Parser 클릭 → 목록 표시 확인**

- [ ] **Step 4: Commit**

```bash
git add web/app/api/mock/agent-tasks/route.ts
git commit -m "fix(agent-tasks): Parser items parser_activities SELECT (§5.1)"
```

---

### Task 4.2: Mapper LIMIT 12 → 200

**Files:**
- Modify: `web/app/api/mock/agent-tasks/route.ts:56`

- [ ] **Step 1: LIMIT 변경**

`agent-tasks/route.ts` 의 mapper SELECT 의 `LIMIT 12` → `LIMIT 200`.

- [ ] **Step 2: 검증**

```bash
curl -s http://127.0.0.1:5536/api/mock/agent-tasks | python3 -c "
import json, sys
d = json.load(sys.stdin)
items = d['itemsByDate']['2025-09-25']
print('Mapper:', len(items['Mapper']))"
```

Expected: `Mapper: 200` (또는 실 mapper_activities count).

- [ ] **Step 3: Commit**

```bash
git add web/app/api/mock/agent-tasks/route.ts
git commit -m "fix(agent-tasks): Mapper LIMIT 12 → 200 (§5.2)"
```

---

### Task 4.3: 헤더 total_count = parser_activities count

**Files:**
- Modify: `web/app/api/mock/agent-tasks/route.ts:46`

- [ ] **Step 1: deriveStageProgress 의 parser_acts 를 total_count 로 사용**

```ts
const stages = await deriveStageProgress(dStr);
const parserStage = stages.find((s) => s.agent === "Parser");
const mapperStage = stages.find((s) => s.agent === "Mapper");
const totalCount = parserStage?.processed ?? 0;
const processedCount = mapperStage?.processed ?? 0;

tasks.push({
  date: dStr,
  total_count: totalCount,                                    // ← 변경
  progress_percent: deriveProgressPercent(statusRaw, run?.current_node ?? null),
  status,
  has_anomaly: false,
});
```

- [ ] **Step 2: 검증**

```bash
curl -s http://127.0.0.1:5536/api/mock/agent-tasks | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('tasks:', d['tasks'])"
```

Expected: `total_count: 292` (parser_activities 처리 count).

- [ ] **Step 3: Playwright — Tasks 헤더 "접수 292건" 표시 확인**

- [ ] **Step 4: Commit**

```bash
git add web/app/api/mock/agent-tasks/route.ts
git commit -m "fix(agent-tasks): total_count = parser_acts (§5.3)"
```

---

## Phase 5 — Home 탭

### Task 5.1: `loadReal:sites_summary` SUM 에 is_mock 분기

**Files:**
- Modify: `web/lib/fixtures.ts:108` (`loadReal:sites_summary`)

- [ ] **Step 1: 모든 SUM SQL 에 useMock 분기 추가**

`fixtures.ts:108` 의 `loadReal("sites_summary")` 안의 5 SELECT 모두 보강:

```ts
const useMock = process.env.CPIA_DEMO_FALLBACK === "on";

const [agg] = await sql`
  SELECT COALESCE(SUM(atomized_count), 0) AS total_processed,
         MAX(started_at) AS last_started
  FROM pipeline_runs WHERE is_mock = ${useMock}    // ← 추가
`;
const [today] = await sql`
  SELECT COALESCE(atomized_count, 0) AS today_count
  FROM pipeline_runs
  WHERE status = 'completed' AND is_mock = ${useMock}    // ← 추가
  ORDER BY started_at DESC LIMIT 1
`;
const [siteAgg] = await sql`
  SELECT COALESCE(SUM(hours_saved), 0) AS total_hours_saved,
         COALESCE(SUM(fte_saved), 0) AS total_fte_saved,
         COALESCE(SUM(hours_saved_cum), 0) AS total_hours_saved_cum,
         COALESCE(SUM(headcount), 0) AS total_headcount
  FROM sites WHERE is_mock = ${useMock}    // ← 추가
`;
const [review] = await sql`
  SELECT COUNT(*) AS review_pending FROM mapper_activities
  WHERE requires_review = TRUE AND is_mock = ${useMock}    // ← 추가
`;
const [abnormal] = await sql`
  SELECT COUNT(*) AS abnormal_count FROM forecasts
  WHERE risk_level <> '정상' AND is_mock = ${useMock}    // ← 추가
`;
```

`loadReal:agent_status` 의 counts SQL 에도 `AND is_mock = ${useMock}` 추가.
`loadReal:chat_sequence` 의 latest SELECT 에도 동일.

- [ ] **Step 2: 검증 (default — useMock=false)**

```bash
curl -s http://127.0.0.1:5536/api/mock/agent-tasks > /dev/null  # warmup
# home 페이지 응답 확인 어려움 — PG 직접
PGPASSWORD=K7mP2xQ9nR4v psql -h localhost -p 5532 -U cpia -d cpia -c "
SELECT SUM(headcount) FROM sites WHERE is_mock = FALSE;"
```

Expected: 65 (m15x 단독).

- [ ] **Step 3: 검증 (env flag — useMock=true)**

```bash
# dev 서버 별도 포트 재기동
CPIA_DEMO_FALLBACK=on PORT=5537 npm --prefix web run dev > /tmp/dev_mock.log 2>&1 &
sleep 5
# home 페이지 navigate 후 KPI 값 확인 (또는 lib/fixtures.ts 직접 호출)
kill $(lsof -ti:5537) 2>/dev/null
```

- [ ] **Step 4: Commit**

```bash
git add web/lib/fixtures.ts
git commit -m "fix(fixtures): loadReal SUM 에 is_mock 분기 — home mock 섞임 (§9.1)"
```

---

## Phase 6 — Cycle 재실행 + 인수 검증

### Task 6.1: Cycle 재실행 (view_builder 변경 반영)

- [ ] **Step 1: 사이클 1 회 실행**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && \
  CPIA_HIL_AUTO_BYPASS=on CPIA_PARSER_VERIFY_LLM=off \
  POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  pipeline/.venv/bin/python3 scripts/run_one_cycle.py \
  "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx" \
  m15x-ph3-ibl 2025-09-25 2>&1 | tail -30
```

Expected: cycle 정상 통과 (atomized > 0, opt > 0, report_md > 0). view_builder 변경 정상 동작.

- [ ] **Step 2: 새 cycle 의 daily_reports.optimizer_view_jsonb keys 검증**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h localhost -p 5532 -U cpia -d cpia -c "
SELECT jsonb_object_keys(optimizer_view_jsonb->'by_wp')
  FROM daily_reports WHERE is_mock = FALSE 
  ORDER BY created_at DESC LIMIT 5;"
```

Expected: keys 가 `fab-...` / `cub-...` (실 wa prefix, unknown- 없음).

- [ ] **Step 3: contractor_bars count 검증**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h localhost -p 5532 -U cpia -d cpia -c "
SELECT jsonb_array_length(contractor_bars_jsonb), 
       contractor_bars_jsonb->0
  FROM daily_reports WHERE is_mock = FALSE 
  ORDER BY created_at DESC LIMIT 1;"
```

Expected: count=3, first bar 에 baseline=90 키 존재.

---

### Task 6.2: Playwright 5 탭 인수

- [ ] **Step 1: Playwright MCP 로 5 탭 순회**

```
1. /home → 4 KPI 표시 정상 (mock 미섞임)
2. /tasks → 헤더 "접수 292건", Parser 클릭 시 목록 표시, Mapper 200+
3. /review → wbs root "M15X Ph-3 IBL", root 알림 63, CUB > 전기 > CABLE TRAY공사 클릭 → 창원기전 카드 표시
4. /export → 시트 1: 9건, 시트 2: 108건, 시트 3: 95건, 시트 4: 292건
5. /reports → contractor_bars 3건, "{N}개 BP사 평균 미만" N>0, WP 클릭 → OptimizerResult 6칸 표시
```

- [ ] **Step 2: CPIA_DEMO_FALLBACK=on 토글 검증**

```bash
CPIA_DEMO_FALLBACK=on PORT=5538 npm --prefix web run dev > /tmp/dev_mock.log 2>&1 &
sleep 5
# 5 탭 빠른 순회 — mock_*.json 원본대로 표시되는지
kill $(lsof -ti:5538) 2>/dev/null
```

- [ ] **Step 3: 최종 commit (필요 시 verify_fe_data_binding.py 등 추가)**

```bash
git status
# 추가 fix 필요한 부분 있으면 별도 commit
```

---

## Remember

- Phase 0 (mock 백업) 은 다른 Phase 와 독립적으로 진행 가능 — 가장 위험 낮음
- Phase 1 (view_builder) 가 backfill_daily_reports.py 재실행과 함께 가야 daily_reports.*_jsonb 정정됨
- 모든 SQL 변경 후 즉시 curl/PG 로 결과 확인
- 디자인 불가침 — `.tsx` 파일 어느 것도 수정 안 함

## 인수 기준 종합

| 탭 | 인수 |
|---|---|
| home | KPI 4개가 m15x 단독 SUM (default) |
| tasks | Parser 클릭 시 200+ 표시, Mapper 동일, 헤더 "접수 292건" |
| review | root "M15X Ph-3 IBL" 알림 63, leaf 클릭 시 카드 표시 |
| export | 4 시트 9/108/95/292 모두 표시 |
| reports | 3 contractor bars, baseline 키, WP 클릭 시 진단 6칸 |
| mock fallback | env CPIA_DEMO_FALLBACK=on 시 mock_*.json 원본대로 |
