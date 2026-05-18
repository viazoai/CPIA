# CPIA FE↔BE 연결 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Next.js FE 5 페이지가 mock fixture 호출 중인 상태에서 PG 적재 실 데이터 swap. 6 PG 적재 보완 + 11 BFF transform 함수 + 5 mock route 내부 교체 + e2e 검증.

**Architecture:** mock route 내부를 PG SELECT + transform 으로 전환. FE 컴포넌트 + fetch URL 모두 그대로. BE 측 atomizer/reporter/parser/mapper 노드 코드 수정으로 PG 적재 보완 (G2/G5/G8/G19/G23/G24).

**Tech Stack:** Python 3.11 (pipeline/.venv) + LangGraph + FastAPI + asyncpg + PostgreSQL (cloudflared 5532) / Next.js 14 + TypeScript / Azure OpenAI gpt-5.1.

**Spec:** `/Users/kyungseoplee/Project Agent/CPIA/docs/superpowers/specs/2026-05-18-cpia-fe-be-integration-design.md`

**Demo 마감:** 2026-06-05 (18일 남음)

**Naming 주의:** CLAUDE.md 가 Reporter → Exporter rename 명시 (2026-05-18) 했으나 본 plan 시점 `pipeline/agents/reporter.py` + `pipeline/graph.py:392 reporter_node` 그대로. rename PR 은 본 plan 범위 밖 (별 cycle). 본 plan 의 코드는 `reporter_node` 명칭 유지.

**PGClient 인스턴스화 실 패턴** (`pipeline/graph.py:93` 참고):
```python
pg = PGClient(cfg.mapper.postgres_url)
await pg.connect()
try:
    await pg.<method>(...)
finally:
    await pg.close()
```
`connect_pg(dsn)` 같은 헬퍼 함수는 존재하지 않음 — 위 패턴 그대로 사용.

---

## File Structure

### 신규 파일
- `infra/postgres/migrations/2026-05-19_sites_hours_saved_cum.sql` — G2 마이그
- `infra/postgres/migrations/2026-05-19_mapper_alternatives.sql` — G23 마이그
- `web/lib/transforms.ts` — BFF transform 11 함수 모음 (G1/G4/G6/G10/G11/G12/G17/G18/G20/G21/G22)
- `web/lib/pg.ts` — Next.js BFF asyncpg 클라이언트 (또는 fetch FastAPI proxy)
- `pipeline/tests/test_db_hours_saved_cum.py` — G2 단위 테스트
- `pipeline/tests/test_atomizer_atomized_count.py` — G5 단위 테스트
- `pipeline/tests/test_db_new_columns_insert.py` — G19 단위 테스트
- `pipeline/tests/test_mapper_alternatives.py` — G23 단위 테스트
- `pipeline/tests/test_parser_job_equipment_insert.py` — G24 단위 테스트
- `web/lib/__tests__/transforms.test.ts` — BFF transform unit test
- `tmp/run_prod_cycle.py` — Phase 3 prod 호출 throwaway script

### 수정 파일
- `pipeline/db.py:540-619` (insert_parser_activities_batch) — G19 신규 13 컬럼
- `pipeline/db.py:621-720` (insert_mapper_activities_batch) — G19 동일
- `pipeline/db.py` 끝 — `update_site_last_run()` / `update_site_hours_saved_cum()` 신규 helper
- `pipeline/graph.py:47` mapper_node — G19 INSERT 인자 추가 (db.py 변경 후 자동 적용)
- `pipeline/graph.py:47` mapper_node — G23 alternatives jsonb 적재
- `pipeline/graph.py:47` mapper_node — G24 (또는 parser_node 신설) job/equipment INSERT 호출
- `pipeline/graph.py:249` atomizer_node — G5 atomized_count UPDATE
- `pipeline/graph.py:392` reporter_node 또는 END edge — G8 + G2 UPDATE
- `pipeline/agents/parser_llm.py` — LLM 출력 신규 13 컬럼 검증 (이미 일치하나 회귀 방지)
- `web/app/api/mock/dashboard/route.ts` — Phase 5 내부 swap
- `web/app/api/mock/agent-tasks/route.ts` — 동일
- `web/app/api/mock/report/route.ts` — 동일
- `web/app/api/mock/review/route.ts` — 동일
- `web/app/api/mock/consolidated/route.ts` — 동일
- `web/app/(app)/home/page.tsx` — `loadFixture()` 호출 → real fetch (3 fixture)
- `web/lib/fixtures.ts` — Phase 5 후 loadFixture 가 real fetch 호출하도록 swap (또는 폐기)

---

# Phase 0 — Setup (전제 인프라)

## Task 0.1: web 패키지 설치 (postgres + playwright)

**Files:**
- Modify: `web/package.json`

- [ ] **Step 1: 패키지 설치**

```bash
cd web && npm install --save postgres && npm install --save-dev @playwright/test vitest @vitest/ui
```

- [ ] **Step 2: Playwright browser 설치**

```bash
cd web && npx playwright install --with-deps chromium
```

- [ ] **Step 3: 검증**

```bash
cd web && node -e "console.log(require('postgres').name || 'postgres OK')"
cd web && npx playwright --version
cd web && npx vitest --version
```

Expected: `postgres OK` + Playwright + vitest 버전 출력.

- [ ] **Step 4: Commit**

```bash
git add web/package.json web/package-lock.json
git commit -m "build(web): postgres + playwright + vitest 의존성 추가"
```

## Task 0.2: vitest + playwright config

**Files:**
- Create: `web/vitest.config.ts`
- Create: `web/playwright.config.ts`
- Create: `web/lib/__tests__/_mocks/pg.ts`

- [ ] **Step 1: vitest.config.ts**

```typescript
import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  test: { environment: "node", globals: true, setupFiles: ["./vitest.setup.ts"] },
  resolve: { alias: { "@": path.resolve(__dirname) } },
});
```

- [ ] **Step 2: vitest.setup.ts — pg mock**

```typescript
// web/vitest.setup.ts
import { vi } from "vitest";
vi.mock("@/lib/pg", () => ({ default: vi.fn() }));
```

- [ ] **Step 3: playwright.config.ts**

```typescript
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:5536" },
  webServer: { command: "npm run dev", port: 5536, reuseExistingServer: true },
});
```

- [ ] **Step 4: 검증**

```bash
cd web && npx vitest run --reporter=default 2>&1 | head -5
```

Expected: "No test files found" (정상 — 아직 테스트 없음)

- [ ] **Step 5: Commit**

```bash
git add web/vitest.config.ts web/vitest.setup.ts web/playwright.config.ts
git commit -m "build(web): vitest + playwright 설정"
```

## Task 0.3: pipeline conftest.py PGClient fixture

**Files:**
- Modify or Create: `pipeline/tests/conftest.py`

- [ ] **Step 1: PGClient fixture**

```python
# pipeline/tests/conftest.py
import os
import pytest
from uuid import UUID, uuid4
from pipeline.db import PGClient

@pytest.fixture
async def pg_client():
    """실 PG (cloudflared 5532) connection. 테스트 끝나면 close."""
    pg = PGClient(os.environ.get("POSTGRES_URL", "postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia"))
    await pg.connect()
    yield pg
    await pg.close()

@pytest.fixture
async def cleanup_test_rows(pg_client):
    """테스트 run_id 기반 cleanup. test_run_ids 리스트에 추가하면 끝나고 삭제."""
    test_run_ids: list[UUID] = []
    yield test_run_ids
    for run_id in test_run_ids:
        for table in ("parser_activities", "mapper_activities", "parser_reports", "parser_job_allocations", "parser_equipment_allocations", "pipeline_runs"):
            try:
                await pg_client.execute(f"DELETE FROM {table} WHERE run_id = $1", run_id)
            except Exception:
                pass
    # sites test row cleanup
    await pg_client.execute("DELETE FROM sites WHERE site_id LIKE 'test-%'")
```

- [ ] **Step 2: 검증**

```bash
cd pipeline && .venv/bin/python -m pytest tests/ -k "test_db_get_pipeline_run" -v 2>&1 | tail -5
```

Expected: 기존 테스트 통과 (fixture 정상 동작).

- [ ] **Step 3: Commit**

```bash
git add pipeline/tests/conftest.py
git commit -m "test(pipeline): PGClient fixture + cleanup_test_rows"
```

---

# Phase 1 — PG 마이그레이션

## Task 1.1: G2 sites.hours_saved_cum 마이그

**Files:**
- Create: `infra/postgres/migrations/2026-05-19_sites_hours_saved_cum.sql`

- [ ] **Step 1: 마이그 파일 작성**

```sql
-- G2 — sites.hours_saved_cum 컬럼 추가. 단위 = 시간 (h).
-- 적재 산식: reporter→END edge 가 ((AS_IS_MIN - TO_BE_MIN) / 60.0) × atomized_count 누적 UPDATE.
-- 상수: AS_IS_MIN=120 (일보당 사람 수작업 분), TO_BE_MIN=5 (일보당 AI 처리 분) → 1.917h/일보.

BEGIN;

ALTER TABLE sites
    ADD COLUMN IF NOT EXISTS hours_saved_cum NUMERIC DEFAULT 0 NOT NULL;

COMMENT ON COLUMN sites.hours_saved_cum IS 'cumulative hours saved since launch. UNIT: hours.';

COMMIT;
```

- [ ] **Step 2: 마이그 적용**

```bash
PGPASSWORD='K7mP2xQ9nR4v' pipeline/.venv/bin/python -c "
import asyncio, asyncpg
async def main():
    conn = await asyncpg.connect('postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia')
    with open('infra/postgres/migrations/2026-05-19_sites_hours_saved_cum.sql') as f:
        await conn.execute(f.read())
    print('migration applied')
    await conn.close()
asyncio.run(main())
"
```

Expected: `migration applied`

- [ ] **Step 3: 적용 검증**

```bash
pipeline/.venv/bin/python -c "
import asyncio, asyncpg
async def main():
    conn = await asyncpg.connect('postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia')
    row = await conn.fetchrow(\"SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_name='sites' AND column_name='hours_saved_cum'\")
    print(dict(row) if row else 'NOT FOUND')
    await conn.close()
asyncio.run(main())
"
```

Expected: `{'column_name': 'hours_saved_cum', 'data_type': 'numeric', 'is_nullable': 'NO', 'column_default': '0'}`

- [ ] **Step 4: Commit**

```bash
git add infra/postgres/migrations/2026-05-19_sites_hours_saved_cum.sql
git commit -m "feat(infra): G2 sites.hours_saved_cum 컬럼 추가 (단위 h)"
```

---

## Task 1.2: G23 mapper_activities.alternatives 마이그

**Files:**
- Create: `infra/postgres/migrations/2026-05-19_mapper_alternatives.sql`

- [ ] **Step 1: 마이그 파일 작성**

```sql
-- G23 — mapper_activities.alternatives jsonb 컬럼 추가.
-- mapper_node 의 RAG top-K (K=3) 후보 + score 적재. review 페이지의 대안 WP 후보 dropdown.

BEGIN;

ALTER TABLE mapper_activities
    ADD COLUMN IF NOT EXISTS alternatives JSONB DEFAULT '[]'::jsonb NOT NULL;

COMMENT ON COLUMN mapper_activities.alternatives IS
  'RAG top-K candidates as [{wa, l6_main, score}, ...]. Sorted by score DESC. K=3 default.';

CREATE INDEX IF NOT EXISTS mapper_activities_alternatives_gin
    ON mapper_activities USING GIN (alternatives);

COMMIT;
```

- [ ] **Step 2: 적용 + 검증**

```bash
PGPASSWORD='K7mP2xQ9nR4v' pipeline/.venv/bin/python -c "
import asyncio, asyncpg
async def main():
    conn = await asyncpg.connect('postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia')
    with open('infra/postgres/migrations/2026-05-19_mapper_alternatives.sql') as f:
        await conn.execute(f.read())
    row = await conn.fetchrow(\"SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mapper_activities' AND column_name='alternatives'\")
    print(dict(row))
    await conn.close()
asyncio.run(main())
"
```

Expected: `{'column_name': 'alternatives', 'data_type': 'jsonb'}`

- [ ] **Step 3: Commit**

```bash
git add infra/postgres/migrations/2026-05-19_mapper_alternatives.sql
git commit -m "feat(infra): G23 mapper_activities.alternatives jsonb 컬럼 추가"
```

---

# Phase 2 — BE 노드 코드 수정

## Task 2.1: G5 atomized_count — 이미 구현됨, 검증 only

> **중요:** Reviewer 발견 — `pipeline/db.py:238 PGClient.update_run_atomized_count()` 메서드 + `pipeline/agents/atomizer.py:137 await pg.update_run_atomized_count(run_id, len(ids))` 호출 이미 존재. PG 검증 시 최근 2 run (3dd88fbb, d648f466) 모두 `atomized_count=41` 정상 적재. 본 task 는 신규 구현 X. **회귀 방지 테스트 + Phase 3 prod cycle 호출 시 적재 확인 only**.

**Files:**
- Test: `pipeline/tests/test_atomizer_atomized_count.py` (회귀 방지)

- [ ] **Step 1: 회귀 방지 테스트 작성**

```python
# pipeline/tests/test_atomizer_atomized_count.py
import pytest
from uuid import uuid4

@pytest.mark.asyncio
async def test_atomizer_update_helper_exists(pg_client, cleanup_test_rows):
    """G5 회귀 방지 — pg.update_run_atomized_count 가 존재하고 정상 UPDATE."""
    run_id = uuid4()
    cleanup_test_rows.append(run_id)
    # 사전: pipeline_runs row
    await pg_client.execute(
        "INSERT INTO pipeline_runs (run_id, site_id, report_date, status, started_at) VALUES ($1, $2, $3, $4, now())",
        run_id, "test-atomizer", "2025-09-25", "running",
    )
    await pg_client.update_run_atomized_count(run_id, 42)
    row = await pg_client.fetch_all(
        "SELECT atomized_count FROM pipeline_runs WHERE run_id = $1", run_id,
    )
    assert row[0]["atomized_count"] == 42
```

- [ ] **Step 2: 테스트 통과 확인 (회귀 방지 — 처음부터 통과 기대)**

```bash
cd pipeline && .venv/bin/python -m pytest tests/test_atomizer_atomized_count.py -v
```

Expected: PASS (이미 구현된 코드의 회귀 방지)

- [ ] **Step 3: Commit**

```bash
git add pipeline/tests/test_atomizer_atomized_count.py
git commit -m "test(atomizer): G5 atomized_count 회귀 방지 테스트"
```

---

## Task 2.2: G8 reporter→END edge UPDATE sites.last_run_id

**Files:**
- Test: `pipeline/tests/test_db_update_site_last_run.py`
- Modify: `pipeline/db.py` 끝 — `update_site_last_run()` helper
- Modify: `pipeline/graph.py:392` reporter_node

- [ ] **Step 1: 실패 테스트 작성**

```python
# pipeline/tests/test_db_update_site_last_run.py
@pytest.mark.asyncio
async def test_update_site_last_run_sets_run_id():
    from pipeline.db import update_site_last_run
    run_id = uuid4()
    pg = PGClient(...)
    # 사전: sites row, last_run_id=NULL
    await pg.execute("INSERT INTO sites (site_id, name, is_mock) VALUES ('test-x', 'Test X', true)")

    await update_site_last_run(pg, site_id="test-x", run_id=run_id)

    row = await pg.fetch_one("SELECT last_run_id FROM sites WHERE site_id='test-x'")
    assert row["last_run_id"] == run_id
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_db_update_site_last_run.py -v
```

Expected: FAIL — ImportError

- [ ] **Step 3: helper 구현**

```python
# pipeline/db.py
async def update_site_last_run(pg: PGClient, site_id: str, run_id: UUID) -> None:
    """G8 — reporter→END 진입 시 sites.last_run_id 갱신."""
    await pg.execute(
        "UPDATE sites SET last_run_id = $1, updated_at = now() WHERE site_id = $2",
        run_id, site_id,
    )
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_db_update_site_last_run.py -v
```

Expected: PASS

- [ ] **Step 5: reporter_node 에서 호출**

`pipeline/graph.py:392` reporter_node 마지막 부분 (daily_reports INSERT 후):

```python
# reporter_node 안, daily_reports INSERT 직후
pg = PGClient(cfg.mapper.postgres_url)
await pg.connect()
try:
    await update_site_last_run(pg, site_id=state["site_id"], run_id=run_id)
finally:
    await pg.close()
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/db.py pipeline/graph.py pipeline/tests/test_db_update_site_last_run.py
git commit -m "feat(reporter): G8 sites.last_run_id 갱신"
```

---

## Task 2.3: G2 reporter→END edge UPDATE hours_saved_cum

**Files:**
- Test: `pipeline/tests/test_db_hours_saved_cum.py`
- Modify: `pipeline/db.py` 끝 — `update_site_hours_saved_cum()` helper
- Modify: `pipeline/graph.py:392` reporter_node

- [ ] **Step 1: 실패 테스트 작성**

```python
# pipeline/tests/test_db_hours_saved_cum.py
import pytest
from pipeline.db import update_site_hours_saved_cum, AS_IS_MIN, TO_BE_MIN

@pytest.mark.asyncio
async def test_hours_saved_cum_accumulates():
    """G2 — atomized_count × (AS_IS_MIN - TO_BE_MIN) / 60 시간 만큼 누적."""
    pg = PGClient(...)
    await pg.execute("INSERT INTO sites (site_id, name, is_mock, hours_saved_cum) VALUES ('test-y', 'Test Y', true, 10.0)")

    # 1차 적재: atomized_count=12
    await update_site_hours_saved_cum(pg, site_id="test-y", atomized_count=12)

    # 산식: (120 - 5) / 60 * 12 = 23.0 h. 누적 = 10 + 23 = 33
    row = await pg.fetch_one("SELECT hours_saved_cum FROM sites WHERE site_id='test-y'")
    assert float(row["hours_saved_cum"]) == pytest.approx(33.0, rel=1e-3)
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_db_hours_saved_cum.py -v
```

Expected: FAIL — ImportError

- [ ] **Step 3: helper 구현**

```python
# pipeline/db.py
AS_IS_MIN: int = 120   # 일보당 사람 수작업 분
TO_BE_MIN: int = 5     # 일보당 AI 처리 분

async def update_site_hours_saved_cum(
    pg: PGClient, site_id: str, atomized_count: int,
) -> None:
    """G2 — atomized_count 기반 절감 시간(h) 누적 UPDATE.

    Spec §6 G2. 산식: ((AS_IS_MIN - TO_BE_MIN) / 60.0) × atomized_count.
    """
    delta_h = (AS_IS_MIN - TO_BE_MIN) / 60.0 * atomized_count
    await pg.execute(
        "UPDATE sites SET hours_saved_cum = hours_saved_cum + $1, updated_at = now() WHERE site_id = $2",
        delta_h, site_id,
    )
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_db_hours_saved_cum.py -v
```

Expected: PASS

- [ ] **Step 5: reporter_node 에서 호출**

`pipeline/graph.py:392` reporter_node 안, update_site_last_run 직후:

```python
await update_site_hours_saved_cum(
    pg, site_id=state["site_id"], atomized_count=state.get("atomized_count", 0),
)
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/db.py pipeline/graph.py pipeline/tests/test_db_hours_saved_cum.py
git commit -m "feat(reporter): G2 hours_saved_cum 누적 적재"
```

---

## Task 2.4a: G19 — insert_parser_activities_batch 신규 13 컬럼

**Files:**
- Test: `pipeline/tests/test_db_new_columns_insert.py` (parser 부분만)
- Modify: `pipeline/db.py:540-619` (insert_parser_activities_batch)

> Reviewer 권고로 분리. 한 INSERT 함수만 본 task 에서 처리. mapper 는 Task 2.4b.

- [ ] **Step 1: 실패 테스트 작성**

```python
# pipeline/tests/test_db_new_columns_insert.py
@pytest.mark.asyncio
async def test_insert_parser_activities_persists_new_13_columns():
    """G19 — parser/mapper INSERT 가 신규 13 컬럼 모두 적재."""
    from pipeline.db import PGClient
    run_id = uuid4()
    activities = [{
        "idx": 0,
        "l5_disc": "건축",
        "trade": "건축",
        "company": "남웅건설",
        "unit": "m2",
        "today_qty": 100.0,
        "work_content": "거푸집 설치",
        "plan_total_qty": 1500.0,
        # 신규 13 컬럼
        "zone": "CUB",
        "bp_code": "PH_X-002",
        "scope": "F02 1F",
        "yesterday_cum_qty": 80.0,
        "today_cum_qty": 180.0,
        "progress_percent": 12.0,
        "remaining_qty": 1320.0,
        "remaining_percent": 88.0,
        "note": "우천 대응",
        "work_location_code": "CUB-F02",
        "wbs_mid_name": "철근콘크리트공사",
        "wbs_sub_name": "거푸집공사",
        "wbs_detail_name": "벽체 거푸집",
    }]
    pg = PGClient(...)
    await pg.insert_parser_activities_batch(run_id=run_id, report_date="2025-09-25", activities=activities)

    row = await pg.fetch_one("SELECT * FROM parser_activities WHERE run_id=$1 LIMIT 1", run_id)
    assert row["zone"] == "CUB"
    assert row["progress_percent"] == 12.0
    assert row["wbs_mid_name"] == "철근콘크리트공사"
    # ... 13 컬럼 전수
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_db_new_columns_insert.py -v
```

Expected: FAIL — 13 컬럼 NULL (현재 INSERT 함수가 신규 컬럼 안 채움)

- [ ] **Step 3: insert_parser_activities_batch 수정**

`pipeline/db.py:540-619` 안 INSERT SQL + values 부분 확장.

```python
INSERT INTO parser_activities
    (run_id, report_date, idx, l5_disc, trade, company, unit, today_qty,
     work_content, plan_total_qty,
     zone, bp_code, scope, yesterday_cum_qty, today_cum_qty,
     progress_percent, remaining_qty, remaining_percent, note,
     work_location_code, wbs_mid_name, wbs_sub_name, wbs_detail_name)
VALUES (...)
ON CONFLICT (run_id, idx) DO UPDATE SET ...
```

values 튜플에 신규 13 컬럼을 `activity.get("zone")` 등으로 추가.

- [ ] **Step 4: parser_activities 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_db_new_columns_insert.py::test_insert_parser_activities_persists_new_13_columns -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/db.py pipeline/tests/test_db_new_columns_insert.py
git commit -m "feat(db): G19 insert_parser_activities_batch 신규 13 컬럼"
```

---

## Task 2.4b: G19 — insert_mapper_activities_batch 신규 13 컬럼

**Files:**
- Test: `pipeline/tests/test_db_new_columns_insert.py` (mapper 케이스 추가)
- Modify: `pipeline/db.py:621-720` (insert_mapper_activities_batch)

- [ ] **Step 1: mapper 케이스 테스트 추가 — 동일 13 컬럼 입력 → insert_mapper_activities_batch 호출 → SELECT 검증**

```python
@pytest.mark.asyncio
async def test_insert_mapper_activities_persists_new_13_columns(pg_client, cleanup_test_rows):
    run_id = uuid4()
    cleanup_test_rows.append(run_id)
    # pipeline_runs 사전 INSERT 생략 (FK 없을 시)
    activities = [{
        "idx": 0, "company": "남웅건설", "trade": "건축", "unit": "m2",
        "today_qty": 100.0, "wa": "CUB", "l6_main": "철근콘크리트공사",
        "mapping_conf": 0.85, "mapping_source": "auto", "requires_review": False,
        "assigned_workers": 8.0, "worker_source": "mh", "plan_total_qty": 1500.0,
        "plan_mh": 456.0, "conditions": [],
        # 신규 13 컬럼
        "zone": "CUB", "bp_code": "PH_X-002", "scope": "F02 1F",
        "yesterday_cum_qty": 80.0, "today_cum_qty": 180.0,
        "progress_percent": 12.0, "remaining_qty": 1320.0, "remaining_percent": 88.0,
        "note": "우천 대응", "work_location_code": "CUB-F02",
        "wbs_mid_name": "철근콘크리트공사", "wbs_sub_name": "거푸집공사", "wbs_detail_name": "벽체 거푸집",
    }]
    await pg_client.insert_mapper_activities_batch(run_id=run_id, report_date="2025-09-25", activities=activities)
    row = (await pg_client.fetch_all("SELECT * FROM mapper_activities WHERE run_id=$1 LIMIT 1", run_id))[0]
    assert row["zone"] == "CUB"
    assert row["progress_percent"] == 12.0
    assert row["wbs_detail_name"] == "벽체 거푸집"
```

- [ ] **Step 2: 실패 확인 → 구현 → 통과 확인 → Commit**

```bash
.venv/bin/python -m pytest tests/test_db_new_columns_insert.py::test_insert_mapper_activities_persists_new_13_columns -v
# FAIL
# pipeline/db.py:621-720 INSERT SQL + values 13 컬럼 추가 (Task 2.4a 와 동일 패턴)
.venv/bin/python -m pytest tests/test_db_new_columns_insert.py -v
# PASS
git add pipeline/db.py pipeline/tests/test_db_new_columns_insert.py
git commit -m "feat(db): G19 insert_mapper_activities_batch 신규 13 컬럼"
```

---

## Task 2.5: G23 mapper_node RAG top-K alternatives 적재

**Files:**
- Test: `pipeline/tests/test_mapper_alternatives.py`
- Modify: `pipeline/agents/mapper.py` — resolve 함수에 top-K 반환 추가
- Modify: `pipeline/db.py:621-720` (insert_mapper_activities_batch) — alternatives 컬럼 추가

- [ ] **Step 1: 실패 테스트 작성**

```python
# pipeline/tests/test_mapper_alternatives.py
@pytest.mark.asyncio
async def test_mapper_persists_top_k_alternatives():
    """G23 — mapper_node 의 RAG top-3 후보가 alternatives jsonb 에 적재."""
    from pipeline.agents.mapper import resolve_activity_with_alternatives
    candidates = await resolve_activity_with_alternatives(
        work_content="거푸집 설치",
        company="남웅건설",
        cand_pool=[("CUB", "철근콘크리트공사"), ("CUB", "거푸집공사"), ("FAB", "철근콘크리트공사")],
        top_k=3,
    )
    assert len(candidates) <= 3
    assert all("score" in c for c in candidates)
    assert all("wa" in c and "l6_main" in c for c in candidates)
    # 정렬 검증
    scores = [c["score"] for c in candidates]
    assert scores == sorted(scores, reverse=True)
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_mapper_alternatives.py -v
```

Expected: FAIL — ImportError

- [ ] **Step 3: mapper.py 에 top-K 함수 추가**

`pipeline/agents/mapper.py` — 기존 resolve 함수 위에 top-K 변형 추가.

```python
async def resolve_activity_with_alternatives(
    work_content: str, company: str, cand_pool: list[tuple[str, str]], top_k: int = 3,
) -> list[dict]:
    """G23 — RAG top-K 후보 + score 반환.

    Returns [{wa, l6_main, score}, ...] sorted by score DESC.
    """
    scored = await _rag_score_candidates(work_content, cand_pool)  # 기존 RAG 점수 산출
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
```

- [ ] **Step 4: insert_mapper_activities_batch 에 alternatives 컬럼**

`pipeline/db.py:621-720` INSERT SQL 에 `alternatives` jsonb 컬럼 추가. mapper_node 가 `activity["alternatives"] = list[dict]` 로 넘기게.

- [ ] **Step 5: mapper_node 호출부 수정**

`pipeline/graph.py:47` mapper_node 안:

```python
# 기존 resolve 호출 자리
top_k = await resolve_activity_with_alternatives(
    work_content=act["work_content"], company=act["company"],
    cand_pool=cand_pool, top_k=3,
)
best = top_k[0] if top_k else None
act["wa"] = best["wa"] if best else None
act["l6_main"] = best["l6_main"] if best else None
act["mapping_conf"] = best["score"] if best else 0.0
act["alternatives"] = top_k  # G23 — 신규
```

- [ ] **Step 6: 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_mapper_alternatives.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add pipeline/db.py pipeline/agents/mapper.py pipeline/graph.py pipeline/tests/test_mapper_alternatives.py
git commit -m "feat(mapper): G23 alternatives top-K (K=3) 적재"
```

---

## Task 2.6: G24 parser → job_allocations / equipment_allocations INSERT 호출

**Files:**
- Test: `pipeline/tests/test_parser_job_equipment_insert.py`
- Modify: `pipeline/graph.py:47` (mapper_node, parser 흐름 부분) — INSERT 호출 추가

- [ ] **Step 1: 실패 테스트 작성**

```python
# pipeline/tests/test_parser_job_equipment_insert.py
@pytest.mark.asyncio
async def test_parser_persists_job_and_equipment_allocations():
    """G24 — parser 흐름이 job_allocations + equipment_allocations 적재."""
    from pipeline.graph import mapper_node  # parser 적재가 mapper_node 안에 있음

    state = {
        "run_id": "...",
        "site_id": "m15x-ph3-ibl",
        "date": "2025-09-25",
        "parsed_report": {
            "bp_summaries": [...],
            "job_allocations": [{"bp_code": "PH_X-002", "company": "에스티엠", "job_type": "철근공", ...}, ...],
            "equipment_allocations": [{"bp_code": "PH_X-002", "company": "에스티엠", "equipment_big": "크레인", "equipment_mid": "타워크레인", "equipment_spec": "T-200", ...}, ...],
            "activities": [...],
        },
        ...
    }
    cfg = GraphConfig(...)
    await mapper_node(state, cfg)

    # 검증
    pg = await connect_pg(cfg.pg_dsn)
    job_count = await pg.fetch_val("SELECT COUNT(*) FROM parser_job_allocations WHERE run_id=$1", state["run_id"])
    eq_count = await pg.fetch_val("SELECT COUNT(*) FROM parser_equipment_allocations WHERE run_id=$1", state["run_id"])
    assert job_count > 0
    assert eq_count > 0
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_parser_job_equipment_insert.py -v
```

Expected: FAIL — 적재 0

- [ ] **Step 3: mapper_node 안 호출 추가**

`pipeline/graph.py:111-122` parser 적재 부분 (insert_parser_report + insert_parser_activities_batch 옆) 에 추가:

```python
await pg.insert_parser_job_allocations_batch(
    run_id=run_id, report_date=date_str,
    job_allocations=parsed["job_allocations"],
)
_dbg(f"insert_parser_job_allocations_batch OK ({len(parsed['job_allocations'])} rows)")

await pg.insert_parser_equipment_allocations_batch(
    run_id=run_id, report_date=date_str,
    equipment_allocations=parsed["equipment_allocations"],
)
_dbg(f"insert_parser_equipment_allocations_batch OK ({len(parsed['equipment_allocations'])} rows)")
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_parser_job_equipment_insert.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/graph.py pipeline/tests/test_parser_job_equipment_insert.py
git commit -m "feat(parser): G24 job/equipment_allocations 적재 호출 추가"
```

---

# Phase 3 — BE 1cycle prod 호출 + 적재 검증

## Task 3.1: throwaway script 작성 + 호출

**Files:**
- Create: `tmp/run_prod_cycle.py`

- [ ] **Step 1: 호출 script 작성**

```python
# tmp/run_prod_cycle.py
"""Phase 3 — 통합 작업일보 1 파일 + 3사 필터로 prod graph 1 cycle 호출."""
from __future__ import annotations
import asyncio, os, uuid
from pathlib import Path

import openai
from pipeline.agents.parser_llm import ParserConfig, parse_daily_report_llm
from pipeline.api import _build_prod_graph_config
from pipeline.graph import build_graph
from pipeline.state import CPIAState

XLSX = Path("docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx")
POC_COMPANIES = {"남웅건설", "세보", "창원기전"}

async def main() -> None:
    parser_cfg = ParserConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
    )
    parsed = await parse_daily_report_llm(XLSX, parser_cfg)
    # 3사 필터
    parsed["bp_summaries"] = [s for s in parsed["bp_summaries"] if s["company"] in POC_COMPANIES]
    parsed["activities"] = [a for a in parsed["activities"] if a["company"] in POC_COMPANIES]
    parsed["job_allocations"] = [j for j in parsed["job_allocations"] if j["company"] in POC_COMPANIES]
    parsed["equipment_allocations"] = [e for e in parsed["equipment_allocations"] if e["company"] in POC_COMPANIES]

    cfg = _build_prod_graph_config()
    graph = build_graph(cfg)
    run_id = uuid.uuid4()
    state: CPIAState = {
        "run_id": str(run_id),
        "site_id": "m15x-ph3-ibl",
        "date": "2025-09-25",
        "parsed_report": parsed,
        "input_files": [str(XLSX)],
        "raw_texts": {},
    }
    config = {"configurable": {"thread_id": str(run_id)}}
    result = await graph.ainvoke(state, config=config)
    print(f"run_id={run_id} final node={result.get('current_node')}")

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 호출 실행 (백그라운드, ~10분)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && \
  source .env && \
  pipeline/.venv/bin/python tmp/run_prod_cycle.py
```

Expected: stdout 에 `run_id=<uuid> final node=reporter` 또는 hil_1 interrupt 시 `final node=mapper` 와 interrupt 페이로드.

- [ ] **Step 3: hil_1 interrupt 시 즉시 resume**

interrupt 발생 시:

```bash
curl -X POST "http://localhost:8001/api/runs/<run_id>/hil_1/resume" \
  -H "Content-Type: application/json" \
  -d '{"corrections": {}}'
```

corrections={} 로 모두 AI 결과 그대로 확정.

---

## Task 3.2: 적재 검증

**Files:** 신규 X (직접 SQL 쿼리)

- [ ] **Step 1: 6 적재 항목 모두 검증**

```bash
pipeline/.venv/bin/python -c "
import asyncio, asyncpg
async def main():
    conn = await asyncpg.connect('postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia')
    run_id = '<Phase 3.1 run_id 여기 붙이기>'
    # G5 atomized_count
    r = await conn.fetchrow(f\"SELECT atomized_count FROM pipeline_runs WHERE run_id='{run_id}'\")
    print('G5 atomized_count:', r['atomized_count'])
    # G8 last_run_id
    r = await conn.fetchrow(\"SELECT last_run_id FROM sites WHERE site_id='m15x-ph3-ibl'\")
    print('G8 last_run_id:', r['last_run_id'])
    # G2 hours_saved_cum
    r = await conn.fetchrow(\"SELECT hours_saved_cum FROM sites WHERE site_id='m15x-ph3-ibl'\")
    print('G2 hours_saved_cum:', r['hours_saved_cum'])
    # G19 신규 13 컬럼 NOT NULL 비율
    r = await conn.fetchrow(f\"SELECT COUNT(*) FILTER (WHERE zone IS NOT NULL) AS zone_ok, COUNT(*) FILTER (WHERE progress_percent IS NOT NULL) AS pp_ok, COUNT(*) AS total FROM parser_activities WHERE run_id='{run_id}'\")
    print('G19 zone/progress NOT NULL:', dict(r))
    # G23 alternatives
    r = await conn.fetchrow(f\"SELECT COUNT(*) FILTER (WHERE alternatives::text<>'[]') AS alt_ok, COUNT(*) AS total FROM mapper_activities WHERE run_id='{run_id}'\")
    print('G23 alternatives:', dict(r))
    # G24 job_allocations + equipment_allocations
    job = await conn.fetchval(f\"SELECT COUNT(*) FROM parser_job_allocations WHERE run_id='{run_id}'\")
    eq = await conn.fetchval(f\"SELECT COUNT(*) FROM parser_equipment_allocations WHERE run_id='{run_id}'\")
    print(f'G24 job={job} eq={eq}')
    await conn.close()
asyncio.run(main())
"
```

Expected: 모두 > 0 (또는 NULL 이 아닌 값). G2 hours_saved_cum 은 atomized_count × 1.917h.

- [ ] **Step 2: tmp/ 파일은 commit 안 함**

`tmp/` 디렉토리는 .gitignore 추가 또는 trash 처리. throwaway script 는 영속 X.

---

# Phase 4 — BFF transform 11 함수

`web/lib/transforms.ts` 모음. 각 함수 unit test 동반.

## Task 4.1: web/lib/pg.ts BFF asyncpg 클라이언트

**Files:**
- Create: `web/lib/pg.ts`
- Create: `web/package.json` 의 `pg` 또는 `postgres` 패키지 의존성 추가

- [ ] **Step 1: postgres 패키지 설치**

```bash
cd web && npm install postgres @types/node
```

- [ ] **Step 2: pg.ts 작성**

```typescript
// web/lib/pg.ts
import postgres from "postgres";

const sql = postgres(process.env.POSTGRES_URL!, {
  max: 5,
  idle_timeout: 30,
});

export default sql;
```

- [ ] **Step 3: 환경변수 검증** (tsx 로 ts 직접 실행)

```bash
cd web && npx tsx --eval "import sql from './lib/pg'; sql\`SELECT 1 as ok\`.then(r => console.log(r)).finally(() => sql.end());"
```

또는 임시 .mjs 파일:

```bash
cd web && cat > /tmp/pg_check.mjs <<'EOF'
import postgres from "postgres";
const sql = postgres(process.env.POSTGRES_URL);
sql`SELECT 1 as ok`.then(r => console.log(r)).finally(() => sql.end());
EOF
node /tmp/pg_check.mjs
```

Expected: `[{ok: 1}]`

- [ ] **Step 4: Commit**

```bash
git add web/lib/pg.ts web/package.json web/package-lock.json
git commit -m "feat(web): BFF postgres 클라이언트 추가"
```

---

## Task 4.2: G12 derive_progress_percent

**Files:**
- Test: `web/lib/__tests__/transforms.test.ts`
- Create: `web/lib/transforms.ts`

- [ ] **Step 1: 실패 테스트 작성**

```typescript
// web/lib/__tests__/transforms.test.ts
import { describe, it, expect } from "vitest";
import { deriveProgressPercent } from "../transforms";

describe("G12 deriveProgressPercent", () => {
  it.each([
    [{status: "completed", current_node: null}, 100],
    [{status: "running", current_node: "optimizer"}, 90],
    [{status: "running", current_node: "forecaster"}, 80],
    [{status: "running", current_node: "exporter"}, 70],
    [{status: "running", current_node: "atomizer"}, 60],
    [{status: "waiting_hil_1", current_node: "mapper"}, 50],
    [{status: "running", current_node: "mapper"}, 30],
    [{status: "running", current_node: "parser"}, 20],
  ])("%o → %d", (input, expected) => {
    expect(deriveProgressPercent(input.status, input.current_node)).toBe(expected);
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd web && npm test
```

Expected: FAIL — `deriveProgressPercent is not a function`

- [ ] **Step 3: transforms.ts 작성**

```typescript
// web/lib/transforms.ts
/** G12 — Tasks page 일자별 진행률. spec §5.3. */
export function deriveProgressPercent(
  status: string,
  current_node: string | null,
): number {
  if (status === "completed") return 100;
  if (status === "waiting_hil_1") return 50;
  const NODE_MAP: Record<string, number> = {
    parser: 20, mapper: 30, atomizer: 60, exporter: 70, forecaster: 80, optimizer: 90,
  };
  return NODE_MAP[current_node ?? ""] ?? 0;
}
```

- [ ] **Step 4: 통과 확인**

```bash
cd web && npm test
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/lib/transforms.ts web/lib/__tests__/transforms.test.ts
git commit -m "feat(web/bff): G12 deriveProgressPercent"
```

---

## Task 4.3: G15 trade 라벨 (산식 X, l6_main 직사용 검증)

→ 함수 신설 X. mock route swap 시 `mapper_activities.l6_main` 그대로 UI 에 흘림. 본 Task 는 SKIP (spec D-8 확정).

---

## Task 4.4: G1 derive_yearly_saving

- [ ] **Step 1: 테스트 작성**

```typescript
// web/lib/__tests__/transforms.test.ts 에 추가
import { deriveYearlySaving } from "../transforms";

describe("G1 deriveYearlySaving", () => {
  it("derive 산식: fte * 1.5 + hours * rate / 1e8", () => {
    // fte=15.4, hours_saved=2155, rate=50000원/h
    // = 15.4 * 1.5 + 2155 * 50000 / 1e8 = 23.1 + 1.0775 = 24.18
    const result = deriveYearlySaving(15.4, 2155, 50000);
    expect(result).toBeCloseTo(24.18, 1);
  });
});
```

- [ ] **Step 2: 구현**

```typescript
/** G1 — Dashboard impact 연간 환산 효과 (단위: 억). spec §7 G1. */
export function deriveYearlySaving(
  totalFteSaved: number, totalHoursSaved: number, hourlyRateKrw: number = 50000,
): number {
  return totalFteSaved * 1.5 + (totalHoursSaved * hourlyRateKrw) / 1e8;
}
```

- [ ] **Step 3: 통과 확인 + commit**

```bash
cd web && npm test && git add -A && git commit -m "feat(web/bff): G1 deriveYearlySaving"
```

---

## Task 4.5: G11 derive_item_status

- [ ] **Step 1: 테스트**

```typescript
describe("G11 deriveItemStatus", () => {
  it("Mapper stage — requires_review true → hil_pending", () => {
    expect(deriveItemStatus("Mapper", {requires_review: true, mapping_conf: 0.4})).toBe("hil_pending");
  });
  it("Mapper — mapping_conf >= 0.7 → done", () => {
    expect(deriveItemStatus("Mapper", {requires_review: false, mapping_conf: 0.85})).toBe("done");
  });
  it("HIL Review — mapping_corrections row → done", () => {
    expect(deriveItemStatus("HIL Review", {has_correction: true})).toBe("done");
  });
});
```

- [ ] **Step 2: 구현**

```typescript
/** G11 — Tasks page 우측 item 의 상태 derive. spec §5.3. */
export function deriveItemStatus(
  stage: string,
  row: { requires_review?: boolean; mapping_conf?: number; has_correction?: boolean; risk_level?: string },
): "done" | "processing" | "received" | "hil_pending" | "blocked" {
  if (row.risk_level === "이상") return "blocked";
  switch (stage) {
    case "Mapper":
      if (row.requires_review) return "hil_pending";
      if ((row.mapping_conf ?? 0) >= 0.7) return "done";
      if ((row.mapping_conf ?? 0) >= 0.4) return "processing";
      return "received";
    case "HIL Review":
      return row.has_correction ? "done" : "hil_pending";
    default:
      return "done";  // atomizer 이후 단계는 atomized_count 기반
  }
}
```

- [ ] **Step 3: 통과 확인 + commit**

```bash
cd web && npm test && git add -A && git commit -m "feat(web/bff): G11 deriveItemStatus"
```

---

## Task 4.6: G17 derive_wp_id_and_path

- [ ] **Step 1: 테스트 + 구현 + commit**

```typescript
/** G17 — wp_id/path derive. spec §5.4 / §5.5. */
export function deriveWpIdAndPath(
  wa: string | null, l6_main: string | null, site_name: string,
): { wp_id: string; wp_name: string; path: string } {
  const safe = (s: string | null) => (s ?? "unknown").replace(/\s+/g, "-").toLowerCase();
  const wp_id = `${safe(wa)}-${safe(l6_main)}`;
  const wp_name = `${wa ?? ""} ${l6_main ?? ""}`.trim();
  const path = [site_name, wa ?? "", l6_main ?? ""].filter(Boolean).join(" > ");
  return { wp_id, wp_name, path };
}
```

테스트: wa="FAB", l6_main="철근콘크리트공사" → wp_id="fab-철근콘크리트공사", path="M15X Ph-3 IBL > FAB > 철근콘크리트공사".

Commit: `feat(web/bff): G17 deriveWpIdAndPath`

---

## Task 4.7: G18 derive_impact

- [ ] **Step 1: 테스트 + 구현 + commit**

```typescript
/** G18 — quadrant Y 축 impact (0~100). spec §5.4. */
export function deriveImpact(
  planTotalQty: number | null, planMhRev2: number | null, normMax: number = 1e8,
): number {
  if (!planTotalQty || !planMhRev2) return 0;
  const raw = planTotalQty * planMhRev2;
  return Math.min(100, Math.max(0, (raw / normMax) * 100));
}
```

Commit: `feat(web/bff): G18 deriveImpact`

---

## Task 4.8: G21 derive_baseline

- [ ] **Step 1: 테스트 + 구현 + commit**

```typescript
import sql from "./pg";

/** G21 — 이력 평균 productivity. spec §5.4. */
export async function deriveBaseline(company: string, l6_main: string): Promise<number> {
  const rows = await sql`
    SELECT AVG(today_qty / NULLIF(ma.plan_mh, 0)) AS baseline
    FROM mapped_history mh
    LEFT JOIN mapper_activities ma USING (run_id, wa, l6_main, company)
    WHERE mh.company = ${company} AND mh.l6_main = ${l6_main}
  `;
  const baseline = rows[0]?.baseline;
  if (baseline) return Number(baseline);
  // fallback: forecasts.similar_cases jsonb 평균
  const fb = await sql`
    SELECT AVG((c->>'productivity')::numeric) AS baseline
    FROM forecasts, jsonb_array_elements(similar_cases) c
    WHERE company = ${company} AND l6_main = ${l6_main}
  `;
  return Number(fb[0]?.baseline ?? 0);
}
```

Commit: `feat(web/bff): G21 deriveBaseline (mapped_history + similar_cases fallback)`

---

## Task 4.9: G10 derive_stage_progress

- [ ] **Step 1: 테스트 + 구현 + commit**

```typescript
/** G10 — Tasks 중앙 7+1 단계 진행. spec §5.3 + §7 G10. */
export async function deriveStageProgress(date: string): Promise<AgentStageProgress[]> {
  const counts = await sql`
    SELECT
      (SELECT COUNT(*) FROM parser_reports WHERE report_date = ${date}) AS parser_reports,
      (SELECT COUNT(*) FROM parser_activities pa JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date}) AS parser_acts,
      (SELECT COUNT(*) FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date}) AS mapper_acts,
      (SELECT COUNT(*) FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date} AND ma.requires_review) AS hil_received,
      (SELECT COUNT(*) FROM mapping_corrections WHERE report_date = ${date}) AS hil_done,
      (SELECT COALESCE(SUM(atomized_count), 0) FROM pipeline_runs WHERE report_date = ${date}) AS atomized,
      (SELECT COUNT(*) FROM daily_reports WHERE report_date = ${date}) AS exporter,
      (SELECT COUNT(*) FROM forecasts f JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date}) AS forecasts_done,
      (SELECT COUNT(*) FROM forecasts f JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date} AND f.risk_level <> '정상') AS opt_received,
      (SELECT COUNT(*) FROM optimizer_advice oa JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date}) AS opt_done
  `;
  const c = counts[0];
  return [
    { step: 1, agent: "Collector",  is_hil: false, received: c.parser_reports, processed: c.parser_reports, percent: 100, waiting_hil: false },
    { step: 2, agent: "Parser",     is_hil: false, received: c.parser_reports, processed: c.parser_acts, percent: c.parser_reports > 0 ? 100 : 0, waiting_hil: false },
    { step: 3, agent: "Mapper",     is_hil: false, received: c.parser_acts, processed: c.mapper_acts, percent: c.parser_acts > 0 ? Math.round(c.mapper_acts / c.parser_acts * 100) : 0, waiting_hil: false },
    { step: 3.5, agent: "HIL Review", is_hil: true, received: c.hil_received, processed: c.hil_done, percent: c.hil_received > 0 ? Math.round(c.hil_done / c.hil_received * 100) : 0, waiting_hil: c.hil_received > c.hil_done },
    { step: 4, agent: "Atomizer",   is_hil: false, received: c.mapper_acts - c.hil_received, processed: c.atomized, percent: 0, waiting_hil: false },
    { step: 5, agent: "Exporter",   is_hil: false, received: c.atomized, processed: c.exporter, percent: 0, waiting_hil: false },
    { step: 6, agent: "Forecaster", is_hil: false, received: c.mapper_acts, processed: c.forecasts_done, percent: 0, waiting_hil: false },
    { step: 7, agent: "Optimizer",  is_hil: false, received: c.opt_received, processed: c.opt_done, percent: 0, waiting_hil: false },
  ];
  // percent 산식은 implementation 시 안전 division 으로 보강.
}
```

Commit: `feat(web/bff): G10 deriveStageProgress`

---

## Task 4.10: G22 wbs_tree_build

- [ ] **Step 1: 테스트 + 구현 + commit**

```typescript
/** G22 — Review 페이지 WBS 트리. spec §5.5. */
export async function wbsTreeBuild(siteId: string): Promise<WBSNode> {
  const rows = await sql`
    SELECT
      am.site_id, am.wa, am.l5_disc, am.l6_main,
      COUNT(*) FILTER (WHERE ma.requires_review) AS review_count,
      MIN(CASE f.risk_level WHEN '이상' THEN 1 WHEN '주의' THEN 2 ELSE 3 END) AS worst_risk
    FROM activity_master am
    LEFT JOIN mapper_activities ma USING (wa)
    LEFT JOIN forecasts f USING (run_id, l6_main, company)
    WHERE am.site_id = ${siteId}
    GROUP BY am.site_id, am.wa, am.l5_disc, am.l6_main
  `;
  // 4 레벨 트리 빌드 (site → wa → l5_disc → l6_main)
  // ... aggregate review_count up, status = worst risk
  return root;
}
```

Commit: `feat(web/bff): G22 wbsTreeBuild`

---

## Task 4.11: G6 derive_productivity_timeseries

- [ ] **Step 1: 테스트 + 구현 + commit**

```typescript
/** G6 — Dashboard fleet trend. spec §5.2 + §7 G6 (mapper_activities LEFT JOIN 명시). */
export async function deriveProductivityTimeseries(
  siteId: string, days: number = 30,
): Promise<{trend: FleetTrendPoint[]; sparklines: Record<string, number[]>}> {
  const rows = await sql`
    SELECT
      mh.report_date,
      mh.site_id,
      AVG(mh.today_qty / NULLIF(ma.plan_mh, 0)) AS productivity
    FROM mapped_history mh
    LEFT JOIN mapper_activities ma USING (run_id, wa, l6_main, company)
    WHERE mh.report_date >= CURRENT_DATE - ${days}::integer
    GROUP BY mh.report_date, mh.site_id
    ORDER BY mh.report_date
  `;
  // sparse 시 forecasts.similar_cases jsonb fallback ...
  // build trend (date, mean, min, max) + sparklines (Record<site_id, number[]>)
  return { trend, sparklines };
}
```

Commit: `feat(web/bff): G6 deriveProductivityTimeseries`

---

## Task 4.12a: G20 — _planned 라인 (활동 마스터 일별 보간)

**Files:** `web/lib/transforms.ts` (sub-함수 추가) + `web/lib/__tests__/transforms.test.ts`

- [ ] **Step 1: 테스트 + 구현 + commit**

```typescript
/** G20a — activity_master.plan_start~plan_finish 사이 일별 누적 진척률 보간. */
export async function _plannedCurve(siteId: string, endDate: string): Promise<{date: string; value: number}[]> {
  const rows = await sql`
    SELECT plan_start, plan_finish, plan_total_qty FROM activity_master WHERE site_id = ${siteId}
  `;
  // 일별 합산 / 누적 / 정규화 0~100. 일별 grid = plan_start MIN ~ endDate.
  return /* date 별 누적 % */;
}
```

Commit: `feat(web/bff): G20a deriveSCurve._plannedCurve`

## Task 4.12b: G20 — _actualCurve (mapped_history 누적)

- [ ] **Step 1: 테스트 + 구현 + commit**

```typescript
export async function _actualCurve(siteId: string, endDate: string): Promise<{date: string; value: number}[]> {
  const rows = await sql`
    SELECT report_date, SUM(today_qty) OVER (ORDER BY report_date) AS cum_qty
    FROM mapped_history WHERE site_id = ${siteId} AND report_date <= ${endDate}
    ORDER BY report_date
  `;
  return rows.map(r => ({date: r.report_date.toISOString().slice(0,10), value: Number(r.cum_qty)}));
}
```

Commit: `feat(web/bff): G20b _actualCurve`

## Task 4.12c: G20 — _forecastCurve (forecasts 외삽 선형)

- [ ] **Step 1: 테스트 + 구현 + commit**

```typescript
export async function _forecastCurve(siteId: string, endDate: string, actualLast: number, plannedTotal: number): Promise<{date: string; value: number}[]> {
  // forecasts.today_productivity 평균 → 일일 진척 가정 → endDate 부터 plannedTotal 도달 시점까지 선형 외삽
  const rows = await sql`SELECT AVG(today_productivity) AS avg_prod FROM forecasts WHERE run_id IN (SELECT last_run_id FROM sites WHERE site_id=${siteId})`;
  // 선형 외삽 array 반환
  return /* future dates × value */;
}
```

Commit: `feat(web/bff): G20c _forecastCurve (선형 외삽)`

## Task 4.12d: G20 — _recoveryCurve + deriveSCurve 통합

- [ ] **Step 1: 테스트 + 구현 + commit**

```typescript
export async function _recoveryCurve(siteId: string, wpId: string | null): Promise<{date: string; value: number}[]> {
  if (!wpId) return [];
  const rows = await sql`SELECT recovery_pattern FROM optimizer_advice WHERE run_id IN (SELECT last_run_id FROM sites WHERE site_id=${siteId})`;
  // recovery_pattern jsonb 펼치기
  return /* date 별 value */;
}

export async function deriveSCurve(siteId: string, endDate: string, wpId: string | null): Promise<SCurvePoint[]> {
  const [p, a, f, r] = await Promise.all([
    _plannedCurve(siteId, endDate),
    _actualCurve(siteId, endDate),
    _forecastCurve(siteId, endDate, /* actualLast */ 0, /* plannedTotal */ 0),
    _recoveryCurve(siteId, wpId),
  ]);
  // merge by date → SCurvePoint[]
  return /* merged array */;
}
```

Commit: `feat(web/bff): G20d _recoveryCurve + deriveSCurve 통합`

---

## Task 4.13: G4 derive_chat_sequence

- [ ] **Step 1: 테스트 + 구현 + commit**

```typescript
/** G4 — Home AgentChatLog 자연어 발화. spec §5.1 + §7 G4. */
export async function deriveChatSequence(runId: string): Promise<ChatMessage[]> {
  const stats = await sql`
    SELECT
      pr.started_at,
      pr.status,
      (SELECT COUNT(*) FROM parser_activities WHERE run_id = pr.run_id) AS parser_count,
      (SELECT COUNT(*) FROM mapper_activities WHERE run_id = pr.run_id) AS mapper_count,
      (SELECT COUNT(*) FROM mapper_activities WHERE run_id = pr.run_id AND requires_review) AS hil_count,
      pr.atomized_count,
      (SELECT COUNT(*) FROM daily_reports WHERE run_id = pr.run_id) AS reporter_count,
      (SELECT COUNT(*) FROM forecasts WHERE run_id = pr.run_id) AS forecast_count,
      (SELECT jsonb_agg(risk_level) FROM forecasts WHERE run_id = pr.run_id) AS risks,
      (SELECT COUNT(*) FROM optimizer_advice WHERE run_id = pr.run_id) AS optimizer_count
    FROM pipeline_runs pr WHERE pr.run_id = ${runId}
  `;
  const s = stats[0];
  const base = new Date(s.started_at);
  const off = (sec: number) => new Date(base.getTime() + sec * 1000).toISOString().slice(11, 19);

  return [
    { ts: off(0), agent: "Collector", type: "info", summary: `1건의 통합 작업일보 수신 완료.`, detail: undefined },
    { ts: off(30), agent: "Parser", type: "info", summary: `${s.parser_count}건의 활동 구조화 완료.`, detail: `BP사별 작업·인원·장비 시트 파싱.` },
    { ts: off(60), agent: "Mapper", type: s.hil_count > 0 ? "hil_request" : "info",
      summary: `WBS 매핑 ${s.mapper_count}건 완료. ${s.hil_count > 0 ? `${s.hil_count}건 확신도 낮아 검토 필요.` : "전건 자동 매핑."}` },
    // ... HIL / Atomizer / Exporter / Forecaster / Optimizer 5 더
  ];
}
```

Commit: `feat(web/bff): G4 deriveChatSequence (agent 별 자연어 템플릿)`

---

# Phase 5 — mock route 5종 내부 swap

## Task 5.1: home page.tsx — loadFixture → real fetch

**Files:**
- Modify: `web/app/(app)/home/page.tsx`
- Modify: `web/lib/fixtures.ts`

- [ ] **Step 1: 새 fetch helper 추가**

`web/lib/fixtures.ts` 의 `loadFixture` 안에서 분기 — 환경변수 `USE_REAL_DATA=1` 시 PG 직접 SELECT.

또는 새 helper `loadReal(name)`:

```typescript
import sql from "./pg";
import { deriveChatSequence } from "./transforms";

export async function loadReal(name: "sites_summary"): Promise<SitesSummary>;
export async function loadReal(name: "agent_status"): Promise<AgentStatus[]>;
export async function loadReal(name: "chat_sequence"): Promise<Record<string, ChatMessage[]>>;
export async function loadReal(name: string): Promise<any> {
  switch (name) {
    case "sites_summary": {
      const [agg] = await sql`SELECT
        COALESCE(SUM(atomized_count), 0) AS total_processed,
        COALESCE(SUM(atomized_count) FILTER (WHERE report_date = CURRENT_DATE), 0) AS today_count,
        ...
        FROM pipeline_runs, sites`;
      // ...
      return { ...agg, /* derive */ };
    }
    case "agent_status": {
      // 패턴 통일 — PG 직접 SELECT (FastAPI proxy 의존 제거). pipeline_runs.current_node 별 카운트.
      const counts = await sql`
        SELECT current_node, COUNT(*) AS n FROM pipeline_runs
        WHERE status = 'running' GROUP BY current_node
      `;
      const activeMap: Record<string, number> = Object.fromEntries(
        counts.map((r: any) => [String(r.current_node ?? "").toLowerCase(), Number(r.n)])
      );
      const AGENT_META: AgentStatus[] = [
        { step: 1, name: "Collector",  korean_name: "수집",   description: "작업일보 자동 수집",     model: "규칙 기반",       group: "collect", active_count: 0, state: "idle" },
        { step: 2, name: "Parser",     korean_name: "파싱",   description: "엑셀 → 구조화 JSON",     model: "gpt-5.1",         group: "collect", active_count: 0, state: "idle" },
        { step: 3, name: "Mapper",     korean_name: "매핑",   description: "WBS 매핑 + 확신도 산출", model: "gpt-5.1 + RAG",   group: "collect", active_count: 0, state: "idle" },
        { step: 4, name: "Atomizer",   korean_name: "적재",   description: "Vector DB 적재",          model: "임베딩 모델",     group: "analyze", active_count: 0, state: "idle" },
        { step: 5, name: "Exporter",   korean_name: "출력",   description: "통합 작업일보 생성",      model: "gpt-5.1",         group: "analyze", active_count: 0, state: "idle" },
        { step: 6, name: "Forecaster", korean_name: "진단",   description: "생산성 진단",             model: "Sonnet 4.6",      group: "analyze", active_count: 0, state: "idle" },
        { step: 7, name: "Optimizer",  korean_name: "조언",   description: "회복 조언",               model: "Opus 4.7",        group: "analyze", active_count: 0, state: "idle" },
      ];
      return AGENT_META.map(a => ({
        ...a,
        active_count: activeMap[a.name.toLowerCase()] ?? 0,
        state: (activeMap[a.name.toLowerCase()] ?? 0) > 0 ? "processing" : "idle",
      }));
    }
    case "chat_sequence": {
      const [latest] = await sql`SELECT run_id, report_date FROM pipeline_runs WHERE status='completed' ORDER BY started_at DESC LIMIT 1`;
      if (!latest) return {};
      const messages = await deriveChatSequence(latest.run_id);
      return { [latest.report_date.toISOString().slice(0, 10)]: messages };
    }
  }
}
```

- [ ] **Step 2: home page.tsx 의 loadFixture → loadReal swap**

```typescript
// web/app/(app)/home/page.tsx
import { loadReal } from "@/lib/fixtures";

export default async function HomePage() {
  const summary = await loadReal("sites_summary");
  const agents = await loadReal("agent_status");
  const chatByDate = await loadReal("chat_sequence");
  // ... (나머지 변경 X)
}
```

- [ ] **Step 3: 브라우저 검증**

```bash
cd web && rm -rf .next && npm run dev
```

브라우저 `http://localhost:5536/home` 접속 → 4 KPI 카드 + 7 agent + chat log 정상 렌더 확인.

- [ ] **Step 4: Commit**

```bash
git add web/lib/fixtures.ts web/app/(app)/home/page.tsx
git commit -m "feat(web/home): mock fixtures → real PG swap (sites_summary + agent_status + chat_sequence)"
```

---

## Task 5.2: /api/mock/dashboard route 내부 swap

**Files:**
- Modify: `web/app/api/mock/dashboard/route.ts`

- [ ] **Step 1: route 내부 PG SELECT + transform**

```typescript
import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import { deriveYearlySaving, deriveProductivityTimeseries } from "@/lib/transforms";

export async function GET() {
  // sites + forecasts LATERAL JOIN
  const sites = await sql`SELECT s.*, f.today_productivity, f.delay_days, f.risk_level FROM sites s LEFT JOIN LATERAL (SELECT * FROM forecasts WHERE run_id = s.last_run_id ORDER BY today_productivity LIMIT 1) f ON true`;
  // performance.fleet_kpi
  const perf = await sql`SELECT AVG(today_productivity) AS avg_productivity, AVG(delay_days) AS avg_delay, COUNT(*) FILTER (WHERE risk_level<>'정상') AS abnormal_total FROM forecasts WHERE run_id IN (SELECT last_run_id FROM sites)`;
  const recoverable = await sql`SELECT AVG((recovery_distribution->>'p50')::numeric) AS recoverable_days FROM optimizer_advice`;
  // impact.fleet_kpi
  const impact = await sql`SELECT SUM(headcount) AS total_headcount, SUM(hours_saved) AS total_hours_saved, SUM(fte_saved) AS total_fte_saved, SUM(headcount)*140 AS total_hours FROM sites`;
  // fleet_trend
  const trend = await deriveProductivityTimeseries("fleet");
  return NextResponse.json({
    sites, // FE Site[] shape 매핑 추가 필요
    dashboard: {
      performance: { fleet_kpi: { avg_productivity: perf[0].avg_productivity, avg_delay: perf[0].avg_delay, abnormal_total: perf[0].abnormal_total, recoverable_days: recoverable[0].recoverable_days }, fleet_trend: trend.trend, site_sparklines: trend.sparklines },
      impact: {
        fleet_kpi: { ...impact[0], yearly_saving: deriveYearlySaving(impact[0].total_fte_saved, impact[0].total_hours_saved), ai_replacement_rate: (impact[0].total_hours_saved / impact[0].total_hours) * 100 },
        site_distribution: sites.map(s => ({site_id: s.site_id, site_name: s.name, hours_saved: s.hours_saved, fte_saved: s.fte_saved})),
        monthly_trend: /* mock 유지 G7 */ MOCK_MONTHLY_TREND,
      },
    },
  });
}
```

- [ ] **Step 2: 브라우저 검증 + Commit**

`/dashboard` 페이지 두 탭 모두 정상 렌더 확인. commit `feat(web/dashboard): mock route 내부 PG swap`

---

## Task 5.3: /api/mock/agent-tasks route 내부 swap (1년 윈도우)

- [ ] **Step 1: PG SELECT + transform**

```typescript
import { deriveStageProgress, deriveItemStatus, deriveProgressPercent } from "@/lib/transforms";

export async function GET() {
  // 1년 윈도우 일자 리스트
  const dates = await sql`SELECT DISTINCT report_date FROM pipeline_runs WHERE report_date >= CURRENT_DATE - INTERVAL '1 year' ORDER BY report_date DESC`;
  const tasks: DailyTask[] = [];
  const progressByDate: Record<string, AgentStageProgress[]> = {};
  const itemsByDate: Record<string, Record<string, AgentTaskItem[]>> = {};
  for (const {report_date} of dates) {
    const dStr = report_date.toISOString().slice(0, 10);
    const [run] = await sql`SELECT status, current_node FROM pipeline_runs WHERE report_date=${dStr} ORDER BY started_at DESC LIMIT 1`;
    const totalCount = await sql`SELECT COUNT(DISTINCT (company, report_date)) AS c FROM parser_activities pa JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date=${dStr}`;
    const hasAnomaly = await sql`SELECT EXISTS(SELECT 1 FROM forecasts f JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date=${dStr} AND f.risk_level<>'정상') AS x`;
    tasks.push({
      date: dStr, total_count: totalCount[0].c,
      progress_percent: deriveProgressPercent(run.status, run.current_node),
      status: run.status === "waiting_hil_1" ? "review_pending" : run.status,
      has_anomaly: hasAnomaly[0].x,
    });
    progressByDate[dStr] = await deriveStageProgress(dStr);
    // itemsByDate: 단계별 12 sample
    // ...
  }
  return NextResponse.json({ tasks, progressByDate, itemsByDate });
}
```

- [ ] **Step 2: 브라우저 검증 + Commit**

---

## Task 5.4: /api/mock/report route 내부 swap

- [ ] **Step 1: 일자 리스트 + 단건 detail PG SELECT + transform**

`derive*` 함수 호출: deriveSCurve, deriveBaseline, deriveWpIdAndPath, deriveImpact, deriveStageProgress.

ReportDetail = { kpi, s_curve, contractor_bars, trade_bars, quadrant, optimizer, raw_data, wp_summary } 각 산식.

- [ ] **Step 2: 브라우저 검증 + Commit**

---

## Task 5.5: /api/mock/review route 내부 swap

- [ ] **Step 1: wbs_tree + cards PG SELECT**

```typescript
import { wbsTreeBuild, deriveWpIdAndPath } from "@/lib/transforms";

export async function GET() {
  const wbs = await wbsTreeBuild("m15x-ph3-ibl");
  const cardRows = await sql`SELECT id, run_id, idx, company, today_qty, unit, wa, l6_main, mapping_conf, requires_review, alternatives FROM mapper_activities WHERE requires_review = true ORDER BY mapping_conf ASC LIMIT 50`;
  const cards: ReviewItem[] = await Promise.all(cardRows.map(async (r) => {
    const work = await sql`SELECT work_content FROM parser_activities WHERE run_id=${r.run_id} AND idx=${r.idx}`;
    const {wp_id, path} = deriveWpIdAndPath(r.wa, r.l6_main, "M15X Ph-3 IBL");
    return {
      id: `r-${r.id}`, bp_name: r.company, work_content: work[0]?.work_content ?? "",
      quantity: Number(r.today_qty), unit: r.unit,
      ai_mapped_wp_id: wp_id, ai_mapped_path: path, confidence: Number(r.mapping_conf),
      status: r.requires_review ? "unconfirmed" : "confirmed",
      alternative_wps: r.alternatives.map((a: any) => ({...deriveWpIdAndPath(a.wa, a.l6_main, "M15X Ph-3 IBL"), score: a.score})),
    };
  }));
  return NextResponse.json({ wbs, cards });
}
```

- [ ] **Step 2: 브라우저 검증 + Commit**

---

## Task 5.6: /api/mock/consolidated route 내부 swap (1년 윈도우)

- [ ] **Step 1: 일자 리스트 + 4 시트 PG SELECT**

```typescript
export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const date = searchParams.get("date");

  if (!date) {
    // 1년 윈도우 일자 리스트
    const dates = await sql`SELECT DISTINCT pr.report_date FROM pipeline_runs pr WHERE pr.report_date >= CURRENT_DATE - INTERVAL '1 year' ORDER BY pr.report_date DESC LIMIT 365`;
    const summaries: ConsolidatedReportSummary[] = [];
    for (const {report_date} of dates) {
      const dStr = report_date.toISOString().slice(0, 10);
      const counts = await sql`SELECT
        (SELECT jsonb_array_length(bp_summaries) FROM parser_reports WHERE report_date=${dStr} LIMIT 1) AS output,
        (SELECT COUNT(*) FROM parser_job_allocations WHERE report_date=${dStr}) AS occupation,
        (SELECT COUNT(*) FROM parser_equipment_allocations WHERE report_date=${dStr}) AS equipment,
        (SELECT COUNT(*) FROM parser_activities WHERE report_date=${dStr}) AS quantity`;
      summaries.push({
        date: dStr, pjt: "M15X Ph-3 IBL",
        status: "ready",
        sheet_row_counts: { output_manpower: counts[0].output, occupation_manpower: counts[0].occupation, equipment: counts[0].equipment, quantity: counts[0].quantity },
      });
    }
    return NextResponse.json(summaries);
  }

  // 단건 — 4 시트 raw
  const bp_summaries = await sql`SELECT bp_summaries FROM parser_reports WHERE report_date=${date} LIMIT 1`;
  const job = await sql`SELECT * FROM parser_job_allocations WHERE report_date=${date}`;
  const eq = await sql`SELECT * FROM parser_equipment_allocations WHERE report_date=${date}`;
  const acts = await sql`SELECT * FROM parser_activities WHERE report_date=${date}`;
  // BP 시트1 (출력인원) — bp_summaries jsonb 펼치기
  const outputManpower = (bp_summaries[0]?.bp_summaries || []).map((s: any) => ({...}));
  return NextResponse.json({
    date, pjt: "M15X Ph-3 IBL", status: "ready",
    sheet_row_counts: { /* 동일 */ },
    output_manpower: outputManpower,
    occupation_manpower: job.map(j => ({/* transform */})),
    equipment: eq.map(e => ({/* transform */})),
    quantity: acts.map(a => ({/* transform */})),
  });
}
```

- [ ] **Step 2: xlsx 다운로드 버튼 — backlog 토스트**

ExportDailyList 또는 ConsolidatedReportCard 의 "엑셀 다운로드" 버튼 클릭 핸들러:

```typescript
const handleDownload = () => {
  alert("통합 xlsx 출력은 다음 PR 에서 제공됩니다. (시트 raw 는 화면에서 확인 가능)");
};
```

- [ ] **Step 3: 브라우저 검증 + Commit**

---

# Phase 6 — e2e 검증 + 데모 리허설

## Task 6.1: 5 페이지 브라우저 수동 검증

- [ ] **Step 1: dev server 재기동**

```bash
cd web && rm -rf .next && npm run dev
```

- [ ] **Step 2: 5 페이지 순차 접속**

브라우저 (port 5536):
- `/home` — 4 KPI + 7 agent + chat log 정상
- `/dashboard` — Performance 탭 (KPI 4 + 트렌드 + 카드 grid) + Impact 탭 (KPI 4 + 분포 + 라인)
- `/tasks` — 좌측 일자 (1년) + 중앙 8 단계 + 우측 12 item
- `/reports` — 좌측 일자 + § 01 트렌드 + § 02 산점도 + § 03 ForecastChart
- `/review` — 좌측 WBS 트리 + 우측 카드 + 확정 / 드래그앤드롭
- `/export` — 좌측 일자 + 우측 4 시트 탭

- [ ] **Step 3: 콘솔 에러 + Network 5xx 0 확인**

- [ ] **Step 4: Commit (수정사항 있을 시)**

---

## Task 6.2: Playwright 시나리오 작성 + 실행

**Files:**
- Create: `web/e2e/fe-be-integration.spec.ts`

- [ ] **Step 1: Playwright 시나리오**

```typescript
import { test, expect } from "@playwright/test";

test("home 5 page golden path", async ({ page }) => {
  for (const path of ["/home", "/dashboard", "/tasks", "/reports", "/review", "/export"]) {
    await page.goto(`http://localhost:5536${path}`);
    await expect(page.locator("text=/Loading|로딩/")).toBeHidden({ timeout: 15000 });
    // 콘솔 에러 0
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    expect(errors).toEqual([]);
  }
});

test("review HIL confirm flow", async ({ page }) => {
  await page.goto("http://localhost:5536/review");
  await page.locator("text=모두 AI 추천대로 확정").click();
  // mapping_corrections row 증가 확인 (DB 검증)
});
```

- [ ] **Step 2: 실행**

```bash
cd web && npx playwright test e2e/fe-be-integration.spec.ts
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add web/e2e/fe-be-integration.spec.ts
git commit -m "test(e2e): 5 페이지 golden path + HIL confirm flow"
```

---

## Task 6.3: 데모 리허설

- [ ] **Step 1: 시연 동선 문서화**

`docs/demo-script.md` 신규 작성. 5 페이지 순서 + 1 분당 클릭 + 자연어 멘트.

- [ ] **Step 2: 라이브 리허설 1 회**

stopwatch — 처음부터 끝까지 5 분 안 들어가는지 확인.

- [ ] **Step 3: PR 작성**

```bash
git push origin A_Track
gh pr create --title "feat: FE↔BE 연결 — 5 페이지 real PG swap + 6 BE 적재 보완" \
  --body "$(cat <<'EOF'
## Summary
- PG 적재 보완 6 (G2 hours_saved_cum, G5 atomized_count, G8 sites.last_run_id, G19 신규 13 컬럼, G23 alternatives, G24 job/equipment 호출)
- BFF transform 12 함수 (web/lib/transforms.ts)
- mock route 5종 내부 swap + home page real fetch
- e2e: 5 페이지 Playwright + HIL flow

## Test plan
- [x] pytest pipeline/tests/ 전 통과
- [x] vitest web/lib/__tests__/ 전 통과
- [x] Playwright e2e 통과
- [x] 브라우저 5 페이지 수동 검증
- [x] 데모 시나리오 5 분 안 확인

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

# 완료 기준

- pytest pipeline/tests/ 전 통과
- vitest web/lib/__tests__/ 전 통과
- Playwright e2e 5 페이지 통과
- 브라우저 5 페이지 콘솔 에러 0 + Network 5xx 0
- 데모 시나리오 5분 안 동작
- PR open + 조형준 프로 리뷰 대기
