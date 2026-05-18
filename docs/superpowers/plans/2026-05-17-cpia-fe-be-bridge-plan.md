# CPIA FE↔BE Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CPIA 의 web/ mock fixture 호출을 실 BE (FastAPI + Next.js BFF) 로 swap. 14 결정 반영, ProductivityDiagnosis / ChatMessage 는 future cycle scope.

**Architecture:** FastAPI (port 8001) — `/run` `/resume` `/status` + GET 읽기 10 endpoint. Next.js BFF route 10 종이 proxy. web/lib/fixtures.ts → 실 fetch swap (USE_MOCK env). PG NUMERIC → API layer `float()` 변환. graph END node 가 sites.last_run_id + pipeline_runs.status='completed' 갱신.

**Tech Stack:** Python 3.11 + FastAPI 0.136 + uvicorn 0.46 + asyncpg 0.30 + LangGraph 0.2 AsyncPostgresSaver. Next.js App Router. PostgreSQL prod (127.0.0.1:5532 cloudflared tunnel cpia-pg.zoai.uk).

**PoC 마감:** 2026-06-05 (2.5 주 남음). main 머지는 조형준 프로님 (본인 권한 X).

**전체 task 수:** 21 task × 평균 5 step = ~100 step.

---

## Phase 0 — 데이터 backfill (시뮬 발견 R-3)

### Task 0-1: sites.last_run_id 시뮬 1 건 backfill

**Files:**
- Create: `infra/postgres/migrations/2026-05-17_sites_last_run_backfill.sql`

본 cycle 시뮬 1 건 (run_id b826e4d9) 이 sites 에 안 박혀있어 API 응답이 0/NULL 됨. D-1 graph END 패치는 신규 run 에만 적용 → 기존 row 는 backfill.

- [ ] **Step 1: migration 파일 작성**

```sql
-- 2026-05-17 — sites.last_run_id backfill (시뮬 1 건)
-- 본 cycle 시뮬 1 건 (run_id b826e4d9, site_id m15x-ph3-ibl) 가 D-1 결정 (graph END 노드 UPDATE) 전에 만들어짐.
-- 기존 row 는 backfill 필요 — 안 박으면 /api/sites 응답이 forecasts 정보 0/NULL.
-- 신규 run 은 D-1 patch (graph.py reporter→END edge) 가 자동 갱신.
BEGIN;
UPDATE sites SET last_run_id='b826e4d9-5b36-41fd-99fa-f989817c6122', updated_at=NOW()
WHERE site_id='m15x-ph3-ibl' AND last_run_id IS NULL;
-- 적용 확인
SELECT site_id, last_run_id FROM sites WHERE site_id='m15x-ph3-ibl';
COMMIT;
```

- [ ] **Step 2: dev PG 에 적용 (검증)**

Run: `PGPASSWORD='cpia' /opt/homebrew/opt/postgresql@16/bin/psql -h localhost -p 5432 -U cpia -d cpia -f infra/postgres/migrations/2026-05-17_sites_last_run_backfill.sql` (또는 psql 없으면 asyncpg 스크립트)
Expected: `UPDATE 1` + `last_run_id=b826e4d9-...`

- [ ] **Step 3: prod PG 에 적용**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA" && pipeline/.venv/bin/python3 -c "import asyncpg, asyncio; asyncio.run((lambda: asyncpg.connect('postgresql://cpia:K7mP2xQ9nR4v@127.0.0.1:5532/cpia').then(...))())"` (또는 asyncpg 짧은 스크립트)
Expected: 1 row UPDATE + SELECT 확인

- [ ] **Step 4: commit**

```bash
git add infra/postgres/migrations/2026-05-17_sites_last_run_backfill.sql
git commit -m "feat(db): sites.last_run_id backfill for 시뮬 1 건 (Phase 0)"
```

---

## Phase 1 — FastAPI 기반 (port 8001 + 3 endpoint)

### Task 1-1: pyproject.toml fastapi/uvicorn 명시 (lock 정합)

**Files:**
- Modify: `pipeline/pyproject.toml` (dependencies block)

시뮬 R-7: 이미 .venv 에 설치되어 있지만 pyproject 에 안 박혀있어 reproducible build 안 됨.

- [ ] **Step 1: pyproject.toml 의 dependencies 에 추가**

`[project] dependencies` 끝에 (psycopg 다음 줄):
```toml
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
```

- [ ] **Step 2: uv sync 로 lock 갱신**

Run: `cd pipeline && uv sync`
Expected: 변경 0 (이미 설치됨), uv.lock 만 갱신

- [ ] **Step 3: import 확인**

Run: `pipeline/.venv/bin/python3 -c "import fastapi, uvicorn; print(fastapi.__version__, uvicorn.__version__)"`
Expected: `0.136.1 0.46.0`

- [ ] **Step 4: commit**

```bash
git add pipeline/pyproject.toml pipeline/uv.lock
git commit -m "chore(deps): fastapi + uvicorn pyproject 명시"
```

### Task 1-2: pipeline/api.py 골격 + /health endpoint

**Files:**
- Create: `pipeline/api.py`
- Create: `pipeline/tests/test_api_health.py`

- [ ] **Step 1: failing test 작성**

```python
# pipeline/tests/test_api_health.py
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from pipeline.api import app

def test_health_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: 실패 확인**

Run: `cd pipeline && .venv/bin/python3 -m pytest tests/test_api_health.py -v`
Expected: `ModuleNotFoundError: No module named 'pipeline.api'` 또는 import fail

- [ ] **Step 3: minimal impl**

```python
# pipeline/api.py
from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CPIA Pipeline API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: 통과 확인**

Run: `cd pipeline && .venv/bin/python3 -m pytest tests/test_api_health.py -v`
Expected: `1 passed`

- [ ] **Step 5: 실 기동 검증**

Run: `cd pipeline && .venv/bin/uvicorn pipeline.api:app --port 8001 &` 그리고 `curl http://localhost:8001/health` (잠시 후 `kill %1`)
Expected: `{"status":"ok"}`

- [ ] **Step 6: commit**

```bash
git add pipeline/api.py pipeline/tests/test_api_health.py
git commit -m "feat(api): FastAPI 골격 + /health endpoint (port 8001)"
```

### Task 1-3: POST /run endpoint

**Files:**
- Modify: `pipeline/api.py` (~50 lines 추가)
- Create: `pipeline/tests/test_api_run.py`

**의도**: FE 가 새 pipeline run 시작. run_id 즉시 반환, graph 백그라운드 실행.

- [ ] **Step 1: failing test 작성**

```python
# pipeline/tests/test_api_run.py
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from pipeline.api import app

def test_post_run_returns_run_id():
    client = TestClient(app)
    response = client.post("/run", json={
        "site_id": "m15x-ph3-ibl",
        "date": "2026-05-17",
        "input_files": ["docs/sample/통합작업일보_test.xlsx"]
    })
    assert response.status_code == 200
    body = response.json()
    assert "run_id" in body
    assert body["status"] == "running"
    # uuid 형식 검증
    import uuid
    uuid.UUID(body["run_id"])
```

- [ ] **Step 2: 실패 확인**

Run: `pytest pipeline/tests/test_api_run.py -v`
Expected: `404 Not Found`

- [ ] **Step 3: minimal impl**

```python
# pipeline/api.py 에 추가
import asyncio
import uuid
from datetime import date as date_type
from pydantic import BaseModel
from pipeline.db import PGClient
from pipeline.graph import build_demo_graph, build_demo_graph_config

class RunRequest(BaseModel):
    site_id: str
    date: str  # YYYY-MM-DD
    input_files: list[str]

@app.post("/run")
async def run_pipeline(req: RunRequest) -> dict[str, str]:
    run_id = uuid.uuid4()
    pg = PGClient()
    await pg.connect()
    try:
        await pg.insert_pipeline_run(run_id, req.site_id, req.date, status="running")
    finally:
        await pg.close()
    # 백그라운드 graph 실행
    cfg = build_demo_graph_config()  # 기본 config
    graph = build_demo_graph(cfg)
    asyncio.create_task(graph.ainvoke(
        {"run_id": str(run_id), "date": req.date, "input_files": req.input_files, "mapped": []},
        config={"configurable": {"thread_id": str(run_id)}}
    ))
    return {"run_id": str(run_id), "status": "running"}
```

- [ ] **Step 4: 통과 확인**

Run: `pytest pipeline/tests/test_api_run.py -v`
Expected: `1 passed` (단 graph 실행은 백그라운드라 응답만 검증)

- [ ] **Step 5: 실 호출 검증 (dev PG)**

Run: `cd pipeline && POSTGRES_URL=postgresql://cpia:cpia@localhost:5432/cpia .venv/bin/uvicorn pipeline.api:app --port 8001 &; sleep 2; curl -X POST http://localhost:8001/run -d '{"site_id":"m15x-ph3-ibl","date":"2026-05-17","input_files":[]}' -H 'Content-Type: application/json'; kill %1`
Expected: `{"run_id":"...","status":"running"}` + dev PG `SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 1` 으로 row 확인

- [ ] **Step 6: commit**

### Task 1-4: GET /status/{run_id} + POST /resume

**Files:**
- Modify: `pipeline/api.py` (~80 lines 추가)
- Create: `pipeline/tests/test_api_status_resume.py`

- [ ] **Step 1: failing test 작성**

```python
def test_get_status_returns_pipeline_run_row():
    client = TestClient(app)
    # 사전 fixture: pipeline_runs row 1 개 INSERT
    response = client.get("/status/b826e4d9-5b36-41fd-99fa-f989817c6122")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "b826e4d9-5b36-41fd-99fa-f989817c6122"
    assert "status" in body
    assert "current_node" in body
    assert "atomized_count" in body

def test_post_resume_hil_1_corrections():
    client = TestClient(app)
    response = client.post("/resume/b826e4d9-5b36-41fd-99fa-f989817c6122",
        json={"corrections": {"0": {"wa": "CUB", "l6_main": "철근콘크리트공사"}}})
    assert response.status_code == 200
    assert "next_node" in response.json()
```

- [ ] **Step 2: 실패 확인 + impl**

Run: pytest fails → impl 추가 (`pipeline/api.py`):

```python
from langgraph.types import Command

@app.get("/status/{run_id}")
async def get_status(run_id: str) -> dict:
    pg = PGClient()
    await pg.connect()
    try:
        row = await pg.pool.fetchrow(
            "SELECT run_id, status, current_node, atomized_count, error, started_at, completed_at FROM pipeline_runs WHERE run_id=$1",
            uuid.UUID(run_id)
        )
        if row is None:
            raise HTTPException(status_code=404, detail=f"run_id {run_id} not found")
        # graph state next 도 같이
        from pipeline.checkpointer import get_checkpointer
        checkpointer = await get_checkpointer()
        cfg = build_demo_graph_config()
        graph = build_demo_graph(cfg)
        state = await graph.aget_state(config={"configurable": {"thread_id": run_id}})
        next_node = state.next[0] if state.next else None
        return {
            "run_id": str(row["run_id"]),
            "status": row["status"],
            "current_node": row["current_node"],
            "atomized_count": row["atomized_count"],
            "error": row["error"],
            "started_at": row["started_at"].isoformat() if row["started_at"] else None,
            "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
            "next_node": next_node,
        }
    finally:
        await pg.close()

class ResumeRequest(BaseModel):
    corrections: dict[str, dict] | None = None
    selections: list[str] | None = None

@app.post("/resume/{run_id}")
async def resume_pipeline(run_id: str, req: ResumeRequest) -> dict:
    cfg = build_demo_graph_config()
    graph = build_demo_graph(cfg)
    config = {"configurable": {"thread_id": run_id}}
    state = await graph.aget_state(config=config)
    if not state.next:
        raise HTTPException(status_code=400, detail="graph not paused")
    next_node = state.next[0]
    payload: Any
    if next_node == "hil_1_node":
        payload = req.corrections or {}
    elif next_node == "hil_2_node":
        payload = req.selections or []
    else:
        raise HTTPException(status_code=400, detail=f"unknown interrupt at {next_node}")
    asyncio.create_task(graph.ainvoke(Command(resume=payload), config=config))
    return {"next_node": next_node}
```

- [ ] **Step 3: 통과 + 실 호출 + commit**

Run: pytest pass + `curl http://localhost:8001/status/b826e4d9-...` (시뮬 1 건 사용) + commit.

---

## Phase 2 — pipeline/db.py helper 5 종 추가

### Task 2-1: update_site_last_run + update_run_status (D-1 + D-2)

**Files:**
- Modify: `pipeline/db.py` (~30 lines 추가)
- Create: `pipeline/tests/test_db_status_update.py`

- [ ] **Step 1: failing test 작성**

```python
# pipeline/tests/test_db_status_update.py
import pytest
import uuid
from datetime import date
from pipeline.db import PGClient

@pytest.mark.asyncio
async def test_update_run_status_all_5_values():
    pg = PGClient()
    await pg.connect()
    try:
        run_id = uuid.uuid4()
        await pg.insert_pipeline_run(run_id, "m15x-ph3-ibl", "2026-05-17")
        for status in ["running", "waiting_hil_1", "waiting_hil_2", "completed", "failed"]:
            await pg.update_run_status(run_id, status=status, current_node="test_node")
            row = await pg.pool.fetchrow("SELECT status, current_node FROM pipeline_runs WHERE run_id=$1", run_id)
            assert row["status"] == status
            assert row["current_node"] == "test_node"
        # completed 시 completed_at 자동 갱신
        await pg.update_run_status(run_id, status="completed")
        row = await pg.pool.fetchrow("SELECT completed_at FROM pipeline_runs WHERE run_id=$1", run_id)
        assert row["completed_at"] is not None
        # cleanup
        await pg.delete_pipeline_run(run_id)
    finally:
        await pg.close()

@pytest.mark.asyncio
async def test_update_site_last_run():
    pg = PGClient()
    await pg.connect()
    try:
        run_id = uuid.uuid4()
        await pg.insert_pipeline_run(run_id, "m15x-ph3-ibl", "2026-05-17")
        await pg.update_site_last_run("m15x-ph3-ibl", run_id)
        row = await pg.pool.fetchrow("SELECT last_run_id FROM sites WHERE site_id='m15x-ph3-ibl'")
        assert row["last_run_id"] == run_id
        # cleanup
        await pg.delete_pipeline_run(run_id)
    finally:
        await pg.close()
```

- [ ] **Step 2: 실패 확인**

Run: `pytest pipeline/tests/test_db_status_update.py -v`
Expected: `AttributeError: 'PGClient' object has no attribute 'update_run_status'`

- [ ] **Step 3: impl 추가**

```python
# pipeline/db.py PGClient class 끝에
    async def update_run_status(
        self,
        run_id: uuid.UUID,
        status: str,
        current_node: Optional[str] = None,
    ) -> None:
        """D-2: pipeline_runs.status / current_node / completed_at 갱신.

        status='completed' 또는 'failed' 시 completed_at 자동 NOW().
        CHECK 제약: running | waiting_hil_1 | waiting_hil_2 | completed | failed.
        """
        await self.pool.execute("""
            UPDATE pipeline_runs
            SET status=$1,
                current_node=COALESCE($2, current_node),
                completed_at=CASE WHEN $1 IN ('completed','failed') THEN NOW() ELSE completed_at END
            WHERE run_id=$3
        """, status, current_node, run_id)

    async def update_site_last_run(self, site_id: str, run_id: uuid.UUID) -> None:
        """D-1: sites.last_run_id 갱신 (graph END node 가 호출).

        last_run_id 가 갱신되어야 /api/sites 응답에 forecasts aggregate (productivity_today,
        abnormal_trades, expected_completion, delay_days) 가 포함됨.
        """
        await self.pool.execute("""
            UPDATE sites SET last_run_id=$1, updated_at=NOW() WHERE site_id=$2
        """, run_id, site_id)
```

- [ ] **Step 4: 통과 + commit**

### Task 2-2: fetch_sites_with_forecasts (Site 19 field SQL)

**Files:**
- Modify: `pipeline/db.py` (~30 lines)
- Create: `pipeline/api_helpers/site_queries.py` (~60 lines — float() 변환 포함, R-2)
- Create: `pipeline/tests/test_site_queries.py`

- [ ] **Step 1: failing test**

```python
# pipeline/tests/test_site_queries.py
import pytest
from pipeline.api_helpers.site_queries import fetch_sites_for_api
from pipeline.db import PGClient

@pytest.mark.asyncio
async def test_fetch_sites_for_api_returns_6_sites_with_19_fields():
    pg = PGClient()
    await pg.connect()
    try:
        sites = await fetch_sites_for_api(pg)
        assert len(sites) == 6
        first = sites[0]
        # 19 field 모두 존재
        expected_fields = {"id", "name", "location", "status", "progress_planned", "progress_actual",
                           "gap_percent", "spi", "productivity_today", "abnormal_trades",
                           "fte_saved", "hours_saved", "headcount", "total_hours", "ai_replacement_rate",
                           "expected_completion", "delay_days", "recovered_completion", "recovery_days"}
        assert set(first.keys()) >= expected_fields
        # float 변환 검증 (R-2)
        assert isinstance(first["fte_saved"], (int, float))
        assert isinstance(first["progress_planned"], (int, float))
        assert isinstance(first["gap_percent"], (int, float))
    finally:
        await pg.close()
```

- [ ] **Step 2: 실패 + impl**

```python
# pipeline/api_helpers/site_queries.py
from __future__ import annotations
from decimal import Decimal
from typing import Any
from pipeline.db import PGClient

def _to_float(v: Any) -> Any:
    """R-2: asyncpg Decimal → float (FE TS number 정합)."""
    if isinstance(v, Decimal):
        return float(v)
    return v

async def fetch_sites_for_api(pg: PGClient) -> list[dict]:
    """spec §4.1: Site 19 field. 시뮬 검증 완료 (sim_results.md §A)."""
    rows = await pg.pool.fetch("""
        SELECT s.site_id AS id, s.name, s.location, s.status,
               s.plan_progress AS progress_planned, s.actual_progress AS progress_actual,
               (s.actual_progress - s.plan_progress) AS gap_percent,
               CASE WHEN s.plan_progress > 0 THEN s.actual_progress / s.plan_progress ELSE NULL END AS spi,
               COALESCE(f.today_productivity, 0) AS productivity_today,
               COALESCE(f.abnormal_trades, 0) AS abnormal_trades,
               s.fte_saved, s.hours_saved, s.headcount,
               (s.headcount * 140) AS total_hours,
               CASE WHEN s.headcount > 0 THEN s.hours_saved / (s.headcount * 140) * 100 ELSE 0 END AS ai_replacement_rate,
               f.expected_completion, f.delay_days
        FROM sites s
        LEFT JOIN LATERAL (
          SELECT MAX(today_productivity) AS today_productivity,
                 COUNT(*) FILTER (WHERE risk_level <> '정상') AS abnormal_trades,
                 MAX(expected_completion) AS expected_completion,
                 MAX(delay_days) AS delay_days
          FROM forecasts WHERE run_id = s.last_run_id
        ) f ON TRUE
        ORDER BY s.site_id
    """)
    result = []
    for row in rows:
        d = {k: _to_float(v) for k, v in dict(row).items()}
        # D-3 (PoC fallback): recovered_completion = expected_completion, recovery_days = 0
        d["recovered_completion"] = d.get("expected_completion")
        d["recovery_days"] = 0
        # status 가 NULL 이면 'unknown' fallback
        if d.get("status") is None:
            d["status"] = "unknown"
        # expected_completion / delay_days NULL → 0 또는 빈 string
        if d.get("expected_completion") is None:
            d["expected_completion"] = ""
            d["recovered_completion"] = ""
        if d.get("delay_days") is None:
            d["delay_days"] = 0
        result.append(d)
    return result
```

- [ ] **Step 3: 통과 + 실 호출 검증 + commit**

### Task 2-3: fetch_sites_summary (SitesSummary 12 field)

**Files:**
- Modify: `pipeline/api_helpers/site_queries.py` (~30 lines 추가)
- Modify: `pipeline/tests/test_site_queries.py`

- [ ] **Step 1**: TDD 5 step (D-5 mock 3 필드 + D-8 today_count = SUM(atomized_count))

```python
async def fetch_summary_for_api(pg: PGClient) -> dict:
    """spec §4.2: SitesSummary 12 field. D-5 mock 3 + D-8 today_count = activity 단위."""
    sites = await pg.pool.fetch("SELECT COALESCE(SUM(hours_saved),0) AS hs, COALESCE(SUM(fte_saved),0) AS fs, COALESCE(SUM(headcount),0) AS hc FROM sites WHERE is_mock = false")
    today_runs = await pg.pool.fetch("""
        SELECT COALESCE(SUM(atomized_count),0) AS today_count,
               COUNT(*) FILTER (WHERE status='waiting_hil_1') AS review_pending,
               MAX(started_at) AS last_started
        FROM pipeline_runs WHERE report_date=CURRENT_DATE
    """)
    abnormal = await pg.pool.fetch("SELECT COUNT(*) AS n FROM forecasts f JOIN sites s ON f.run_id=s.last_run_id WHERE f.risk_level<>'정상'")
    hc = int(sites[0]["hc"]) or 1
    total_hours = hc * 140
    hours_saved = float(sites[0]["hs"])
    last_started = today_runs[0]["last_started"]
    return {
        "today_count": int(today_runs[0]["today_count"]),
        "review_pending": int(today_runs[0]["review_pending"]),
        "abnormal_count": int(abnormal[0]["n"]),
        "last_updated": last_started.strftime("%H:%M") if last_started else "—",
        "total_hours_saved": hours_saved,
        "total_fte_saved": float(sites[0]["fs"]),
        "total_headcount": hc,
        "total_hours": total_hours,
        "ai_replacement_rate": (hours_saved / total_hours * 100) if total_hours > 0 else 0,
        # D-5: mock 유지 3 필드
        "yearly_saving": 203.0,
        "total_processed": 1247,
        "total_hours_saved_cum": 12840,
    }
```

### Task 2-4: AGENT_META 7 hard-code (D-9)

**Files:**
- Create: `pipeline/api_helpers/agent_meta.py`
- Create: `pipeline/tests/test_agent_meta.py`

- [ ] **Step 1~5**: TDD 패턴. CLAUDE.md "Agent 역할 요약" 표 7 row 기준.

```python
# pipeline/api_helpers/agent_meta.py
from __future__ import annotations

AGENT_META: list[dict] = [
    {"step": 1, "name": "Collector",  "korean_name": "수집",    "description": "작업일보 자동 수집",                  "model": "규칙 기반",   "group": "collect"},
    {"step": 2, "name": "Parser",     "korean_name": "파싱",    "description": "원문 텍스트 → 구조화 JSON",            "model": "gpt-5.1",     "group": "collect"},
    {"step": 3, "name": "Mapper",     "korean_name": "매핑",    "description": "WBS 공종 매핑 (RAG + rerank)",          "model": "gpt-5.1",     "group": "collect"},
    {"step": 4, "name": "Atomizer",   "korean_name": "원자화",  "description": "Chroma 적재 (유사 이력 누적)",          "model": "임베딩 모델",  "group": "collect"},
    {"step": 5, "name": "Reporter",   "korean_name": "보고",    "description": "통합 Daily Report 생성",                "model": "gpt-5.1",     "group": "collect"},
    {"step": 6, "name": "Forecaster", "korean_name": "예측",    "description": "공종별 생산성 진단",                    "model": "gpt-5.1",     "group": "analyze"},
    {"step": 7, "name": "Optimizer",  "korean_name": "최적화",  "description": "맥락 기반 회복 조언",                   "model": "gpt-5.1",     "group": "analyze"},
]
```

### Task 2-5: state_reader (ReviewItem) + wbs_tree + adapters

**Files:**
- Create: `pipeline/api_helpers/state_reader.py` (~80 lines)
- Create: `pipeline/api_helpers/wbs_tree.py` (~50 lines)
- Create: `pipeline/api_helpers/adapters.py` (~50 lines)
- Create: `pipeline/tests/test_api_helpers.py`

- [ ] **Step 1~5**: 각 helper 별 TDD. 핵심:

```python
# pipeline/api_helpers/state_reader.py
async def fetch_review_items(graph, run_id: str) -> list[dict]:
    """D-6 + D-7: state.mapped → ReviewItem."""
    state = await graph.aget_state(config={"configurable": {"thread_id": run_id}})
    mapped = state.values.get("mapped", [])
    items = []
    for idx, a in enumerate(mapped):
        items.append({
            "id": f"r-{run_id[:8]}-{idx:03d}",
            "bp_name": a.get("company", ""),
            "work_content": a.get("work_content", ""),
            "quantity": float(a.get("today_qty", 0)),
            "unit": a.get("unit", ""),
            "ai_mapped_wp_id": a.get("wa", ""),
            # D-7: PoC fallback (l7_sub None)
            "ai_mapped_path": f"{a.get('l5_disc','?')} > {a.get('l6_main','?')} > {a.get('wa','?')}",
            "confidence": float(a.get("mapping_conf") or 0),
            "status": "unconfirmed" if a.get("requires_review") else "confirmed",
            "alternative_wps": [],  # Phase 2
        })
    return items
```

```python
# pipeline/api_helpers/wbs_tree.py
from __future__ import annotations
from pipeline.db import PGClient

async def build_wbs_tree(pg: PGClient, site_id: str) -> dict:
    """spec §4.6: activity_master 1059 row → WBSNode 3 depth 트리 (site → l5_disc → l6_main → l7_sub).
    PoC 데이터 한계 R-5: 4 trade (설비/전기/건축/소방) only.
    D-7: l7_sub NULL 인 row 는 l6 가 leaf (work_package).
    """
    rows = await pg.pool.fetch(
        "SELECT DISTINCT l5_disc, l6_main, l7_sub FROM activity_master WHERE l5_disc IS NOT NULL ORDER BY l5_disc, l6_main, l7_sub"
    )
    tree = {"id": site_id, "type": "building", "name": site_id, "parent_id": None,
            "review_count": 0, "status": "normal", "children": []}
    l5_map: dict[str, dict] = {}
    l6_map: dict[tuple[str, str], dict] = {}
    for r in rows:
        l5, l6, l7 = r["l5_disc"], r["l6_main"], r["l7_sub"]
        # depth 1: l5_disc (trade)
        if l5 not in l5_map:
            l5_node = {"id": f"{site_id}.{l5}", "type": "trade", "name": l5,
                       "parent_id": site_id, "review_count": 0, "status": "normal", "children": []}
            l5_map[l5] = l5_node
            tree["children"].append(l5_node)
        # depth 2: l6_main (work_package 또는 sub-trade)
        if l6 is None:
            continue
        key = (l5, l6)
        if key not in l6_map:
            # l7_sub 가 항상 None 인 l6 group 은 work_package, 그 외엔 sub-trade
            l6_node = {"id": f"{site_id}.{l5}.{l6}", "type": "work_package", "name": l6,
                       "parent_id": l5_map[l5]["id"], "review_count": 0, "status": "normal", "children": []}
            l6_map[key] = l6_node
            l5_map[l5]["children"].append(l6_node)
        # depth 3: l7_sub (있을 때만, leaf work_package)
        if l7 is not None:
            l6_map[key]["type"] = "trade"  # l7 이 있으면 l6 는 sub-trade
            l6_map[key]["children"].append({
                "id": f"{site_id}.{l5}.{l6}.{l7}", "type": "work_package", "name": l7,
                "parent_id": l6_map[key]["id"], "review_count": 0, "status": "normal", "children": []
            })
    return tree
```

```python
# pipeline/api_helpers/adapters.py
def adapt_optimizer_output(advice_row: dict) -> dict:
    """D-10: optimizer_advice row → FE OptimizerOutput shape."""
    deg_cases = advice_row.get("degradation_cases", []) or []
    similar = []
    for c in deg_cases:
        recovery = c.get("recovery", {}) or {}
        rd = recovery.get("recovery_days")
        outcome = f"D+{rd} 회복" if rd is not None else "미회복"
        activities = c.get("activities", []) or []
        first_act = activities[0] if activities else "활동 X"
        more = f" 외 {len(activities)-1}건" if len(activities) > 1 else ""
        similar.append({
            "date": c.get("date", ""),
            "description": f"{c.get('conditions','')} — {first_act}{more}",
            "outcome": outcome,
        })
    recs = sorted(advice_row.get("recommendations", []) or [], key=lambda r: r.get("rank", 99))
    return {
        "wp_id": f"{advice_row.get('company','')}|{advice_row.get('l6_main','')}",
        "diagnosis": advice_row.get("diagnosis", ""),
        "similar_cases": similar,
        "recommendations": [r.get("text", "") for r in recs],
        "details": [
            {"label": "회복 분포", "value": str(advice_row.get("recovery_distribution", {}))},
            {"label": "평가", "value": advice_row.get("forecast_assessment", "")},
        ],
    }
```

---

## Phase 3 — pipeline/graph.py 통합 (D-1 + D-2)

### Task 3-1: 각 node 진입 시 update_run_status + END 에 update_site_last_run

**Files:**
- Modify: `pipeline/graph.py` (~30 lines 추가)
- Modify: `pipeline/tests/test_graph_e2e_namwong.py` (회귀 확인)

- [ ] **Step 1: 회귀 baseline 확인 (수정 전)**

Run: `cd pipeline && .venv/bin/python3 -m pytest -x --tb=no -q 2>&1 | tail -5`
Expected: `1 failed + 197 passed + 1 xfailed` (본 cycle 의 baseline, 사전 합의)

- [ ] **Step 2: 각 agent node 의 진입에 status update 추가**

`pipeline/graph.py` 의 `mapper_node` / `hil_1_node` / `atomizer_node` / `forecaster_node` / `hil_2_node` / `optimizer_node` / `reporter_node` 각각 함수 첫 줄에:

```python
async def mapper_node(state, *, ...):
    pg = ...  # 기존 PGClient 또는 cfg 에서 받음
    await pg.update_run_status(uuid.UUID(state["run_id"]), status="running", current_node="mapper")
    # ... 기존 로직
```

`hil_1_node` 진입 시 `status="waiting_hil_1"`, resume 후 atomizer 진입 시 `status="running"`. 동일하게 hil_2.

`reporter_node` 의 마지막 (insert_daily_report 다음):
```python
await pg.update_site_last_run(state["site_id"], uuid.UUID(state["run_id"]))  # D-1
await pg.update_run_status(uuid.UUID(state["run_id"]), status="completed")    # D-2
```

- [ ] **Step 3: 회귀 재실행**

Run: `pytest -x --tb=short -q 2>&1 | tail -10`
Expected: `1 failed + 197 passed + 1 xfailed` 유지 (status update 만 추가, 로직 변경 X)

- [ ] **Step 4: 실 시뮬 e2e — synthetic_daily_report.py**

Run: `cd /Users/kyungseoplee/Project\ Agent/CPIA && set -a && source .env.local && set +a && PYTHONPATH=. pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report --scenario "남웅건설|철근콘크리트공사|3|장비대기|0.5|1.0|m3" --auto-select-all`
Expected: 정상 종료 + dev PG `SELECT status, completed_at FROM pipeline_runs ORDER BY started_at DESC LIMIT 1` → `('completed', NOT NULL)` + `SELECT last_run_id FROM sites WHERE site_id='m15x-ph3-ibl'` → 방금 run_id

- [ ] **Step 5: commit**

---

## Phase 4 — FastAPI GET endpoint 10 종

### Task 4-1: GET /api/sites + /api/sites/summary + /api/agents/status

**Files:**
- Modify: `pipeline/api.py` (~60 lines)
- Modify: `pipeline/tests/test_api_endpoints.py`

- [ ] **Step 1~5**: 각 endpoint 1 step 씩 TDD.

```python
@app.get("/api/sites")
async def api_sites() -> list[dict]:
    pg = PGClient()
    await pg.connect()
    try:
        return await fetch_sites_for_api(pg)
    finally:
        await pg.close()

@app.get("/api/sites/summary")
async def api_sites_summary() -> dict:
    pg = PGClient()
    await pg.connect()
    try:
        return await fetch_summary_for_api(pg)
    finally:
        await pg.close()

@app.get("/api/agents/status")
async def api_agents_status() -> list[dict]:
    pg = PGClient()
    await pg.connect()
    try:
        active_runs = await pg.pool.fetch(
            "SELECT current_node, COUNT(*) AS n FROM pipeline_runs WHERE status NOT IN ('completed','failed') GROUP BY current_node"
        )
        active_map = {r["current_node"]: r["n"] for r in active_runs if r["current_node"]}
        result = []
        for meta in AGENT_META:
            count = active_map.get(meta["name"].lower(), 0)
            state = "processing" if count > 0 else "idle"
            result.append({**meta, "active_count": count, "state": state})
        return result
    finally:
        await pg.close()
```

- [ ] **Step 5: 실 호출 + commit**

### Task 4-2: GET /api/runs/{id} 5 sub-endpoint (report + forecasts + optimizer + review + wbs)

**Files:**
- Modify: `pipeline/api.py` (~150 lines)

- [ ] **Step 1~5**: 5 endpoint 1 step 씩.

```python
@app.get("/api/runs/{run_id}/forecasts")
async def api_run_forecasts(run_id: str) -> list[dict]:
    pg = PGClient()
    await pg.connect()
    try:
        rows = await pg.pool.fetch("""
            SELECT today_productivity, risk_level, expected_completion, delay_days, similar_cases,
                   company, l6_main
            FROM forecasts WHERE run_id=$1 ORDER BY id
        """, uuid.UUID(run_id))
        return [{k: float(v) if isinstance(v, Decimal) else v for k, v in dict(r).items()} for r in rows]
    finally:
        await pg.close()

@app.get("/api/runs/{run_id}/optimizer")
async def api_run_optimizer(run_id: str) -> list[dict]:
    pg = PGClient()
    await pg.connect()
    try:
        rows = await pg.pool.fetch("SELECT * FROM optimizer_advice WHERE run_id=$1 ORDER BY id", uuid.UUID(run_id))
        return [adapt_optimizer_output(dict(r)) for r in rows]  # D-10 + D-12
    finally:
        await pg.close()

@app.get("/api/runs/{run_id}/report")
async def api_run_report(run_id: str) -> dict:
    """ReportDetail wrapper (spec §4.7 + crosswalk.md §22).
    합성: kpi (forecasts + optimizer 집계) + s_curve (D-13 plan-only) + contractor/trade bars
    + quadrant + optimizer[] (D-12 wide) + raw_data (D-11 equipment join).
    """
    pg = PGClient()
    await pg.connect()
    try:
        run_uuid = uuid.UUID(run_id)
        # ── KPI (ReportKpi 8 field) ──
        forecasts = await pg.pool.fetch(
            "SELECT today_productivity, expected_completion, delay_days, risk_level, company, l6_main FROM forecasts WHERE run_id=$1",
            run_uuid
        )
        f_list = [{k: float(v) if isinstance(v, Decimal) else v for k, v in dict(r).items()} for r in forecasts]
        max_prod = max((f["today_productivity"] for f in f_list if f["today_productivity"] is not None), default=0)
        max_delay = max((f["delay_days"] for f in f_list if f["delay_days"] is not None), default=0)
        max_exp = max((f["expected_completion"] for f in f_list if f["expected_completion"]), default=None)
        kpi = {
            "productivity_today": max_prod,
            "productivity_history_diff": -12,  # gap §A: mock 유지 (history avg 비교 산출 없음)
            "delay_days": max_delay,
            "expected_completion": max_exp.isoformat() if max_exp else "",
            "recoverable_productivity": 9,  # gap §A: mock 유지 (산식 미정)
            "target_productivity": 97,       # gap §A: mock 유지
            "recovery_days": 0,              # D-3 PoC fallback
            "recovered_completion": max_exp.isoformat() if max_exp else "",
        }
        # ── S-Curve (D-13: plan-only derive) ──
        site_row = await pg.pool.fetchrow("SELECT s.site_id, s.actual_progress FROM pipeline_runs p JOIN sites s ON p.site_id=s.site_id WHERE p.run_id=$1", run_uuid)
        plan_rows = await pg.pool.fetch(
            "SELECT MIN(plan_start) AS s, MAX(plan_finish) AS f, SUM(plan_total_qty) AS qty FROM activity_master WHERE plan_total_qty > 0"
        )
        # 간단: plan 시작~종료를 10 등분, 누적 % 선형 보간 (실 산식은 plan_total_qty 가중 가능)
        s_curve = []
        if plan_rows and plan_rows[0]["s"]:
            from datetime import timedelta
            start, finish = plan_rows[0]["s"], plan_rows[0]["f"]
            days = (finish - start).days
            actual = float(site_row["actual_progress"] or 0) if site_row else 0
            for i in range(11):
                d = start + timedelta(days=int(days * i / 10))
                planned_pct = i * 10  # 선형
                point = {"date": d.isoformat(), "planned": planned_pct}
                if i <= 5:  # 오늘까지 = 5번째 점 (가정)
                    point["actual"] = min(actual, planned_pct)
                s_curve.append(point)
        # ── Bars (contractor + trade) ──
        contractor_bars = []
        seen = {}
        for f in f_list:
            seen.setdefault(f["company"], []).append(f["today_productivity"] or 0)
        for company, vals in seen.items():
            avg = sum(vals) / len(vals) if vals else 0
            status = "normal" if avg >= 90 else "caution" if avg >= 70 else "risk"
            contractor_bars.append({"label": company, "value": avg, "status": status})
        trade_seen = {}
        for f in f_list:
            trade_seen.setdefault(f["l6_main"], []).append(f["today_productivity"] or 0)
        trade_bars = [{"label": t, "value": sum(v)/len(v) if v else 0,
                       "status": "normal" if (sum(v)/len(v) if v else 0) >= 90 else "caution" if (sum(v)/len(v) if v else 0) >= 70 else "risk"}
                      for t, v in trade_seen.items()]
        # ── Quadrant (forecasts row 별 1 point) ──
        quadrant = []
        for f in f_list:
            prod = f["today_productivity"] or 0
            impact = 50  # gap §A: mh_gap 기반 산식 미정, mock
            q = "risk" if prod < 70 and impact >= 50 else "caution" if prod < 90 else "safe"
            quadrant.append({
                "wp_id": f"{f['company']}|{f['l6_main']}",
                "wp_name": f["l6_main"], "trade": f["l6_main"],
                "productivity": prod, "impact": impact, "quadrant": q, "size": 1,
            })
        # ── Optimizer (D-12 wide) ──
        advice_rows = await pg.pool.fetch("SELECT * FROM optimizer_advice WHERE run_id=$1 ORDER BY id", run_uuid)
        optimizer_list = [adapt_optimizer_output(dict(r)) for r in advice_rows]
        # ── Raw data (D-11 equipment join: state.mapped + Parser EquipmentAllocation) ──
        # state.mapped 는 graph.aget_state 로
        graph = build_demo_graph(build_demo_graph_config())
        state = await graph.aget_state(config={"configurable": {"thread_id": run_id}})
        mapped = state.values.get("mapped", [])
        eq_alloc = state.values.get("parsed", {}).get("equipment_allocations", []) if isinstance(state.values.get("parsed"), dict) else []
        eq_by_company: dict[str, list[str]] = {}
        for e in eq_alloc:
            eq_by_company.setdefault(e.get("company", ""), []).append(e.get("equipment_big", ""))
        raw_data = []
        for a in mapped:
            raw_data.append({
                "building": site_row["site_id"] if site_row else "",
                "trade": a.get("trade", ""), "wp": a.get("wa", ""),
                "bp_name": a.get("company", ""), "work_content": a.get("work_content", ""),
                "quantity": float(a.get("today_qty") or 0), "unit": a.get("unit", ""),
                "workers": float(a.get("assigned_workers") or 0),
                "equipment": ",".join(eq_by_company.get(a.get("company", ""), [])),
            })
        return {
            "kpi": kpi, "s_curve": s_curve, "contractor_bars": contractor_bars,
            "trade_bars": trade_bars, "quadrant": quadrant,
            "optimizer": optimizer_list,  # D-12: list
            "raw_data": raw_data,
        }
    finally:
        await pg.close()

@app.get("/api/runs/{run_id}/review")
async def api_run_review(run_id: str) -> list[dict]:
    cfg = build_demo_graph_config()
    graph = build_demo_graph(cfg)
    return await fetch_review_items(graph, run_id)

@app.get("/api/runs/{run_id}/wbs")
async def api_run_wbs(run_id: str) -> dict:
    pg = PGClient()
    await pg.connect()
    try:
        # site_id 조회 → wbs_tree 빌드
        row = await pg.pool.fetchrow("SELECT site_id FROM pipeline_runs WHERE run_id=$1", uuid.UUID(run_id))
        if row is None:
            raise HTTPException(404)
        return await build_wbs_tree(pg, row["site_id"])
    finally:
        await pg.close()
```

### Task 4-3: GET /api/runs/{id} (RunStatus) + /api/tasks/daily-runs + /api/dashboard

**Files:**
- Modify: `pipeline/api.py` (~80 lines)

- [ ] **Step 1: failing test + impl 3 endpoint**

```python
@app.get("/api/runs/{run_id}")
async def api_run_detail(run_id: str) -> dict:
    """RunStatus alias of /status — FE 가 polling 쓰는 path. /status 와 동일 응답."""
    return await get_status(run_id)

@app.get("/api/tasks/daily-runs")
async def api_tasks_daily_runs() -> dict:
    """Tasks 좌측 패널 — 최근 14 일 pipeline_runs.
    DailyRun 5 field: date, total_count (atomized_count, D-8), status, has_anomaly, bar_value.
    """
    pg = PGClient()
    await pg.connect()
    try:
        rows = await pg.pool.fetch("""
            SELECT p.report_date, p.atomized_count, p.status,
                   EXISTS(SELECT 1 FROM forecasts WHERE run_id=p.run_id AND risk_level<>'정상') AS has_anomaly
            FROM pipeline_runs p
            WHERE p.report_date >= CURRENT_DATE - INTERVAL '14 days'
            ORDER BY p.report_date DESC
        """)
        daily_runs = []
        for r in rows:
            # status 매핑: waiting_hil_1 → review_pending
            ui_status = "review_pending" if r["status"] in ("waiting_hil_1", "waiting_hil_2") else r["status"]
            daily_runs.append({
                "date": r["report_date"].isoformat(),
                "total_count": int(r["atomized_count"] or 0),
                "status": ui_status,
                "has_anomaly": bool(r["has_anomaly"]),
                # gap §A-1: target_count 미정 — atomized_count 가 0 이상이면 1.0, 아니면 0 (단순 fallback)
                "bar_value": min(1.0, (r["atomized_count"] or 0) / 100.0),
            })
        # progress_by_date / chatByDate 는 mock 유지 (D-4) — 별 mock route 또는 빈 dict
        return {"runs": daily_runs, "progressByDate": {}, "chatByDate": {}}
    finally:
        await pg.close()

@app.get("/api/dashboard")
async def api_dashboard() -> dict:
    """DashboardFixture shape — performance.fleet_kpi 4 + impact (SitesSummary + site_distribution + mock 2)."""
    pg = PGClient()
    await pg.connect()
    try:
        sites = await fetch_sites_for_api(pg)
        summary = await fetch_summary_for_api(pg)
        # performance.fleet_kpi
        avg_prod = sum(s["productivity_today"] for s in sites) / max(len(sites), 1)
        avg_delay = sum(s["delay_days"] for s in sites) / max(len(sites), 1)
        abnormal_total = sum(s["abnormal_trades"] for s in sites)
        recoverable_days = sum(s["recovery_days"] for s in sites)
        # impact.site_distribution
        site_dist = [{"site_id": s["id"], "site_name": s["name"],
                      "hours_saved": s["hours_saved"], "fte_saved": s["fte_saved"]} for s in sites]
        return {
            "performance": {"fleet_kpi": {
                "avg_productivity": avg_prod, "avg_delay": avg_delay,
                "abnormal_total": abnormal_total, "recoverable_days": recoverable_days,
            }},
            "impact": {
                "fleet_kpi": summary,
                "site_distribution": site_dist,
                # mock 유지 (gap §A)
                "monthly_trend": [
                    {"month": "2026-01", "cumulative_fte": 8.2},
                    {"month": "2026-02", "cumulative_fte": 10.5},
                    {"month": "2026-03", "cumulative_fte": 12.9},
                    {"month": "2026-04", "cumulative_fte": 14.1},
                    {"month": "2026-05", "cumulative_fte": 15.4},
                ],
                # per_site_automation 도 mock (BE scope 밖)
                "per_site_automation": {
                    "m15x-ph3-ibl": [
                        {"function": "Data Stewardship", "rate": 78, "before_hours": 120, "after_hours": 26},
                        {"function": "P&L Reporting",   "rate": 65, "before_hours": 80,  "after_hours": 28},
                        {"function": "Risk Management", "rate": 55, "before_hours": 60,  "after_hours": 27},
                        {"function": "Deal Support",    "rate": 40, "before_hours": 40,  "after_hours": 24},
                    ],
                },
            },
        }
    finally:
        await pg.close()
```

- [ ] **Step 2: 실 호출 검증**

Run: `curl http://localhost:8001/api/tasks/daily-runs | jq '.runs | length'` (≥ 1 row 확인) + `curl http://localhost:8001/api/dashboard | jq '.performance.fleet_kpi'`
Expected: 200 OK + 4 fleet_kpi field 정수/실수 값.

- [ ] **Step 3: commit**

---

## Phase 5 — Next.js BFF route 10 종

### Task 5-1: web/lib/api.ts wrapper + USE_MOCK env

**Files:**
- Create: `web/lib/api.ts`
- Modify: `web/.env.local.example`

- [ ] **Step 1: .env.local.example 추가**

```
FASTAPI_URL=http://localhost:8001
USE_MOCK=false
```

- [ ] **Step 2: web/lib/api.ts**

```ts
const FASTAPI_URL = process.env.FASTAPI_URL || "http://localhost:8001";
const USE_MOCK = process.env.USE_MOCK === "true";

export async function apiGet<T>(path: string): Promise<T> {
  const base = USE_MOCK ? "/api/mock" : FASTAPI_URL;
  const res = await fetch(`${base}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${FASTAPI_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json() as Promise<T>;
}
```

### Task 5-2: BFF route 10 종 (proxy)

**Files:**
- Create: `web/app/api/sites/route.ts`
- Create: `web/app/api/sites/summary/route.ts`
- Create: `web/app/api/agents/status/route.ts`
- Create: `web/app/api/runs/[id]/route.ts`
- Create: `web/app/api/runs/[id]/{report,forecasts,optimizer,review,wbs}/route.ts` (5)
- Create: `web/app/api/tasks/daily-runs/route.ts`
- Create: `web/app/api/dashboard/route.ts`

- [ ] **Step 1~3**: 패턴 동일 — 각 route ~10 lines:

```ts
// web/app/api/sites/route.ts
import { NextResponse } from "next/server";

export async function GET() {
  const res = await fetch(`${process.env.FASTAPI_URL || "http://localhost:8001"}/api/sites`);
  if (!res.ok) return NextResponse.json({ error: "upstream" }, { status: 502 });
  return NextResponse.json(await res.json());
}
```

- [ ] **Step 4: 각 route `curl http://localhost:3000/api/<path>` 실 호출 검증**

- [ ] **Step 5: commit (route 묶음)**

---

## Phase 6 — fixtures → 실 fetch swap + e2e 검증

### Task 6-1: web/lib/types.ts D-12 (OptimizerOutput[] wide)

**Files:**
- Modify: `web/lib/types.ts`

- [ ] **Step 1~3**: `ReportDetail` 의 `optimizer: OptimizerOutput` → `optimizer: OptimizerOutput[]` 변경. tsc 통과 확인. commit.

### Task 6-2: page 별 fetch 경로 swap

**Files:**
- Modify: `web/app/(app)/{home,dashboard,sites/[id],tasks,review,reports}/page.tsx`

각 page 의 fetch 경로 명시 (before → after):

| Page | File | Before | After |
|---|---|---|---|
| home | `web/app/(app)/home/page.tsx:8-9` | `loadFixture("sites_summary")` + `loadFixture("agent_status")` | `apiGet<SitesSummary>("/api/sites/summary")` + `apiGet<AgentStatus[]>("/api/agents/status")` |
| dashboard | `web/app/(app)/dashboard/page.tsx:14` | `fetch("/api/mock/dashboard")` | `apiGet<{sites: Site[], dashboard: DashboardFixture}>("/api/dashboard")` (+ `/api/sites` 합본) |
| sites/[id] | `web/app/(app)/dashboard/sites/[id]/page.tsx:26` | `fetch("/api/mock/dashboard/${id}")` | `apiGet(`/api/runs/${runId}/report`)` (단 site_id → run_id 매핑 필요 — `/api/sites` 에서 last_run_id 추출) |
| tasks | `web/app/(app)/tasks/page.tsx:19` | `fetch("/api/mock/agent-tasks")` | `apiGet("/api/tasks/daily-runs")` |
| review | `web/app/(app)/review/page.tsx:16` | `fetch("/api/mock/review")` | `apiGet(`/api/runs/${runId}/wbs`)` + `apiGet(`/api/runs/${runId}/review`)` (각각 wbs / cards) |
| reports | `web/app/(app)/reports/page.tsx:18` | `fetch("/api/mock/report")` | `apiGet(`/api/runs/${runId}/report`)` (daily + details 합본) |

- [ ] **Step 1: web/lib/api.ts apiGet 사용으로 swap (home 부터)**

```tsx
// web/app/(app)/home/page.tsx (server component)
import { apiGet } from "@/lib/api";
import type { SitesSummary, AgentStatus } from "@/lib/types";

export default async function HomePage() {
  const summary = await apiGet<SitesSummary>("/api/sites/summary");
  const agents = await apiGet<AgentStatus[]>("/api/agents/status");
  // ... 기존 JSX 유지
}
```

- [ ] **Step 2: dashboard / sites/[id] / tasks / review / reports 5 page 동일 패턴 swap**

각 page 별 fetch URL 위 표대로 변경. site_id → run_id 매핑은 `/api/sites` 응답에서 `last_run_id` 추출.

- [ ] **Step 3: USE_MOCK=true 회귀 — `npm run dev` + 환경변수 토글로 양쪽 동작 확인**

Run: `cd web && USE_MOCK=true npm run dev` → 기존 mock 동작 + `USE_MOCK=false npm run dev` → 실 FastAPI 호출.

- [ ] **Step 4: TypeScript 컴파일 통과**

Run: `cd web && npx tsc --noEmit`
Expected: 0 error.

- [ ] **Step 5: commit**

```bash
git add web/app/\(app\)/
git commit -m "feat(web): Task 6-2 page 6 fetch 경로 swap (USE_MOCK env)"
```

### Task 6-3: e2e 검증 — prod tunnel + FastAPI + Next.js

- [ ] **Step 1**: prod tunnel 띄움 (cloudflared access tcp)
- [ ] **Step 2**: FastAPI 띄움 (`POSTGRES_URL=postgresql://cpia:K7mP2xQ9nR4v@127.0.0.1:5532/cpia .venv/bin/uvicorn pipeline.api:app --port 8001`)
- [ ] **Step 3**: Next.js 띄움 (`cd web && npm run dev`)
- [ ] **Step 4**: 페이지 5 종 (home/dashboard/sites/[id]/review/reports/tasks) 다 띄워서 데이터 흐름 + shape mismatch 검증
- [ ] **Step 5**: 시뮬 1 건 e2e — POST /run → Tasks 페이지에서 status 진행 확인 → Review 페이지에서 confirm → Reports 페이지 갱신

### Task 6-4: 시뮬 시나리오 README 작성

**Files:**
- Create: `docs/demo/2026-05-17-fe-be-bridge-demo-runbook.md`

- [ ] **Step 1~3**: 데모 시연 runbook (사전 셋업 + 단계별 화면 + 예상 데이터).

---

## 완료 게이트 (본 plan 의 끝)

- [ ] Phase 0: sites.last_run_id backfill 적용 (dev + prod)
- [ ] Phase 1: FastAPI 3 endpoint + /health (실 curl 통과)
- [ ] Phase 2: db.py helper 5 종 + api_helpers 5 모듈 (회귀 통과)
- [ ] Phase 3: graph.py 각 node 가 update_run_status 호출 (회귀 197 PASS 유지)
- [ ] Phase 4: FastAPI GET endpoint 10 종 (실 curl 통과, NUMERIC float 변환 확인)
- [ ] Phase 5: Next.js BFF route 10 종 (실 curl 통과)
- [ ] Phase 6: web page 5 종 swap (USE_MOCK=false 실 데이터 표시) + 시뮬 1 건 e2e
- [ ] mock 유지 결정 사항 (D-3 / D-4 / D-5 / FE 하드코딩 3종) 그대로 동작

**다음 cycle (PoC 시연 후)**:
- ProductivityDiagnosis BE adapter (D-3 followup, BE Forecaster EWMA 후)
- ChatMessage Hybrid DB derive (D-4 followup)
- SCurvePoint historical 누적 (daily_reports 30 일+ 운영 후)
- ReviewItem.alternative_wps Phase 2 (Mapper LLM top-3)

---

## 산출 commit 계획 (atomic, ~14 commits)

각 commit 에 본 plan 의 task id 마킹 (예: `feat(api): Task 1-3 POST /run 구현`).

| commit 순서 | 내용 |
|---|---|
| 1 | feat(db): Phase 0 sites.last_run_id backfill |
| 2 | chore(deps): Task 1-1 fastapi/uvicorn pyproject 명시 |
| 3 | feat(api): Task 1-2 FastAPI 골격 + /health |
| 4 | feat(api): Task 1-3 POST /run |
| 5 | feat(api): Task 1-4 GET /status + POST /resume |
| 6 | feat(db): Task 2-1 update_site_last_run + update_run_status |
| 7 | feat(api): Task 2-2~2-5 api_helpers 5 모듈 |
| 8 | feat(graph): Task 3-1 각 node status update + END last_run_id |
| 9 | feat(api): Task 4-1~4-3 GET endpoint 10 종 |
| 10 | feat(web): Task 5-1 api.ts wrapper + .env.local |
| 11 | feat(web): Task 5-2 BFF route 10 종 |
| 12 | feat(web): Task 6-1 types.ts D-12 wide + Task 6-2 fetch swap |
| 13 | feat(demo): Task 6-3 e2e 검증 + Task 6-4 runbook |
| 14 | docs: plan completion gate 통과 |

PR 머지 = 조형준 프로님 (본인 권한 X).
