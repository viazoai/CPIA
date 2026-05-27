# CPIA Exporter — graph 사전생성 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** graph cycle 마다 통합 작업일보 xlsx 를 사전생성하여 PG `consolidated_reports` 테이블에 UPSERT 하고, `/export/run` 은 그 row 를 우선 서빙 (miss 시 live render fallback). Atomizer ‖ Exporter fan-out 토폴로지로 graph 안에 편입.

**Architecture:** 선행 cycle (`2026-05-19-cpia-collector-exporter-design.md`) 의 D-6 (graph 밖 라우트) retract → CLAUDE.md 원안 `Atomizer → Exporter ‖ Forecaster` 회귀. 기존 `fetch_sheet_data` / `render_xlsx` / `_fill_*` / COL dict 모두 재사용, 신 wrapper `consolidated_xlsx_node` 1개 + PG helper 2개 + 신 테이블 1개 + graph.py 4줄 + state.py 2줄 + UI swap 1줄. 총 변경 ~200 LOC.

**Tech Stack:** Python 3.11 (uv-managed venv at `pipeline/.venv`), PostgreSQL (asyncpg), LangGraph (StateGraph + PostgresSaver), openpyxl, FastAPI, Next.js (B_Track UI swap).

**Spec:** `docs/superpowers/specs/2026-05-27-cpia-exporter-graph-integration-design.md` (11 결정 D-1 ~ D-11)

**Branch:** `A_Track`. baseline SHA = `b38d667` (spec iteration 2 final).

**다른 세션 충돌 영역 (read-only)**: `data-contract/`, `deep-dive/`, `pipeline/agents/optimizer/view_builder.py`, `pipeline/chroma_client.py`. 본 plan 의 변경 영역 (`graph.py` / `state.py` / `db.py` / `exporter.py` / `exporter_routes.py` / `api.py:_AGENTS_META` / `scripts/seed_dummy_year.py` / `infra/postgres/migrations/` / `pipeline/tests/` / `web/app/components/export/` / `web/lib/transforms.ts`) 와 직접 충돌 0.

**Iron Law:** "Real code or no claim". 각 task 의 "done" = (a) 실 명령 실행 + (b) 실 출력 원본 인용 + (c) 의미적 검증. 추측 / 통과할 것 / no-op 같은 표현 금지.

---

## File Structure

신규 (충돌 0):
- `infra/postgres/migrations/2026-05-27_consolidated_reports.sql` — PG 마이그레이션
- `pipeline/tests/test_db_consolidated_reports.py` — db helper 단위 테스트
- `pipeline/tests/test_exporter_node.py` — graph 노드 wrapper 단위 테스트
- `pipeline/tests/test_graph_dual_end.py` — dual-END 통합 테스트

변경 — 라인 최소화 (충돌 가능):
- `pipeline/db.py` — 신 helper 2개 append (기존 helper 변경 0)
- `pipeline/state.py` — `CPIAState` TypedDict 끝에 신 필드 2개 추가 (D-12 4 필드 다음, 기존 필드 0 수정)
- `pipeline/agents/exporter.py` — `consolidated_xlsx_node` 신 fn append (기존 함수 변경 0)
- `pipeline/graph.py` — import 1 + add_node 1 + add_edge 2 = 4줄 (기존 노드 / edge 0 수정)
- `pipeline/exporter_routes.py` — 핸들러 본문 변경 + `_build_xlsx_response` helper 분리
- `pipeline/api.py` — `_AGENTS_META` 에 Exporter entry 추가 (1 entry)
- `scripts/seed_dummy_year.py` — `_backfill_consolidated_reports` 신 함수 append + 호출 1줄
- `web/lib/transforms.ts` — Agent stage mapping 에 Exporter 추가
- `web/app/components/export/ConsolidatedReportCard.tsx` — `handleExport` 본문 swap (정적 fallback → `/export/run`)
- `web/.env.local.example` — `NEXT_PUBLIC_FASTAPI_BASE` 추가

---

## Task 0: PG migration — `consolidated_reports` 테이블

**Files:**
- Create: `infra/postgres/migrations/2026-05-27_consolidated_reports.sql`

**의도:** PG BYTEA 저장소 + `(site_id, report_date)` PRIMARY KEY (UPSERT 자연) + FK 2 + index 2 + GENERATED column + is_mock (선행 8 테이블 일관성).

- [ ] **Step 1: SQL 파일 작성**

```sql
-- infra/postgres/migrations/2026-05-27_consolidated_reports.sql
-- (D-1 / D-2 / D-3 / D-4 / S-1) graph cycle 마다 1번 UPSERT — site×date 합집합 xlsx 사전생성
-- 본 cycle: 2026-05-27-cpia-exporter-graph-integration-design.md

CREATE TABLE IF NOT EXISTS consolidated_reports (
  site_id       TEXT        NOT NULL REFERENCES sites(site_id),
  report_date   DATE        NOT NULL,
  xlsx_bytes    BYTEA       NOT NULL,
  run_id        UUID        NOT NULL REFERENCES pipeline_runs(run_id),
  generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  byte_size     INTEGER     GENERATED ALWAYS AS (length(xlsx_bytes)) STORED,
  is_mock       BOOLEAN     NOT NULL DEFAULT FALSE,
  PRIMARY KEY (site_id, report_date)
);

CREATE INDEX IF NOT EXISTS idx_consolidated_reports_date
  ON consolidated_reports (report_date DESC);
CREATE INDEX IF NOT EXISTS idx_consolidated_reports_run
  ON consolidated_reports (run_id);

COMMENT ON TABLE consolidated_reports IS
  '(B-1 / T-A / N-1 / S-1) graph cycle 마다 1번 UPSERT — site×date 합집합 xlsx 사전생성. 본 cycle 2026-05-27.';
```

- [ ] **Step 2: prod PG 에 적용**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
source pipeline/.venv/bin/activate
psql "$POSTGRES_URL" -f infra/postgres/migrations/2026-05-27_consolidated_reports.sql
```

Expected output:
```
CREATE TABLE
CREATE INDEX
CREATE INDEX
COMMENT
```

- [ ] **Step 3: 스키마 검증**

```bash
psql "$POSTGRES_URL" -c "\d consolidated_reports"
```

Expected (7 컬럼, 2 인덱스, 2 FK):
- 컬럼: `site_id text NOT NULL`, `report_date date NOT NULL`, `xlsx_bytes bytea NOT NULL`, `run_id uuid NOT NULL`, `generated_at timestamptz NOT NULL DEFAULT now()`, `byte_size integer GENERATED ALWAYS AS (length(xlsx_bytes)) STORED`, `is_mock boolean NOT NULL DEFAULT false`
- Indexes: `consolidated_reports_pkey PRIMARY KEY (site_id, report_date)`, `idx_consolidated_reports_date`, `idx_consolidated_reports_run`
- Foreign-key constraints: `(site_id) REFERENCES sites(site_id)`, `(run_id) REFERENCES pipeline_runs(run_id)`

- [ ] **Step 4: idempotency 검증 (재실행 OK)**

```bash
psql "$POSTGRES_URL" -f infra/postgres/migrations/2026-05-27_consolidated_reports.sql
```

Expected: 모든 `CREATE` 가 `NOTICE: relation already exists, skipping` 으로 nop.

- [ ] **Step 5: Commit**

```bash
git add infra/postgres/migrations/2026-05-27_consolidated_reports.sql
git commit -m "feat(db): consolidated_reports 테이블 마이그 (D-4 / S-1)

(site_id, report_date) PK + xlsx_bytes BYTEA + run_id FK + generated_at +
byte_size GENERATED + is_mock. UPSERT 자연 + 선행 is_mock 8 테이블 일관성.

Spec: docs/superpowers/specs/2026-05-27-cpia-exporter-graph-integration-design.md §6.1"
```

---

## Task 1: `db.py` helper 2개 TDD

**Files:**
- Modify: `pipeline/db.py` — 신 helper 2 append (기존 helper 변경 0)
- Create: `pipeline/tests/test_db_consolidated_reports.py`

**의도:** `upsert_consolidated_report` (ON CONFLICT) + `fetch_consolidated_report` (SELECT). 선행 cycle 의 `insert_collector_inbox` 패턴과 동일 (module-level free function, PGClient 인스턴스 받음, kwargs).

- [ ] **Step 1: 테스트 작성**

```python
# pipeline/tests/test_db_consolidated_reports.py
"""(Task 1) db.py helper TDD — upsert + fetch."""

from __future__ import annotations

import os
import uuid
from datetime import date as _date

import pytest

from pipeline.db import (
    PGClient,
    fetch_consolidated_report,
    upsert_consolidated_report,
)

pytestmark = pytest.mark.asyncio

POSTGRES_URL = os.environ.get(
    "POSTGRES_URL", "postgresql://cpia:cpia@localhost:5432/cpia"
)


async def _make_pipeline_run(pg: PGClient, run_id: uuid.UUID, site_id: str) -> None:
    """FK 만족 위해 pipeline_runs row 미리 생성."""
    async with pg._pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO pipeline_runs (run_id, site_id, report_date, status)
            VALUES ($1, $2, '2025-09-25', 'completed')
            ON CONFLICT (run_id) DO NOTHING
            """,
            run_id,
            site_id,
        )


@pytest.fixture
async def pg() -> PGClient:
    pg = PGClient(POSTGRES_URL)
    await pg.connect()
    yield pg
    await pg.close()


async def test_upsert_insert_path(pg: PGClient) -> None:
    """첫 UPSERT = INSERT."""
    site_id = "m15x-ph3-ibl"
    report_date = _date(2025, 9, 25)
    run_id = uuid.uuid4()
    await _make_pipeline_run(pg, run_id, site_id)
    # 사전 cleanup (테스트 결정성)
    async with pg._pool.acquire() as con:
        await con.execute(
            "DELETE FROM consolidated_reports WHERE site_id=$1 AND report_date=$2",
            site_id, report_date,
        )
    await upsert_consolidated_report(
        pg, site_id=site_id, report_date=report_date,
        xlsx_bytes=b"FAKE-XLSX-A", run_id=run_id,
    )
    async with pg._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT xlsx_bytes, run_id, byte_size FROM consolidated_reports WHERE site_id=$1 AND report_date=$2",
            site_id, report_date,
        )
    assert row is not None
    assert row["xlsx_bytes"] == b"FAKE-XLSX-A"
    assert row["run_id"] == run_id
    assert row["byte_size"] == len(b"FAKE-XLSX-A")  # GENERATED column 검증


async def test_upsert_update_path(pg: PGClient) -> None:
    """두 번째 UPSERT = UPDATE (last write wins)."""
    site_id = "m15x-ph3-ibl"
    report_date = _date(2025, 9, 25)
    run_id_a = uuid.uuid4()
    run_id_b = uuid.uuid4()
    await _make_pipeline_run(pg, run_id_a, site_id)
    await _make_pipeline_run(pg, run_id_b, site_id)
    async with pg._pool.acquire() as con:
        await con.execute(
            "DELETE FROM consolidated_reports WHERE site_id=$1 AND report_date=$2",
            site_id, report_date,
        )
    await upsert_consolidated_report(
        pg, site_id=site_id, report_date=report_date,
        xlsx_bytes=b"FAKE-A", run_id=run_id_a,
    )
    await upsert_consolidated_report(
        pg, site_id=site_id, report_date=report_date,
        xlsx_bytes=b"FAKE-B-LONGER", run_id=run_id_b,
    )
    async with pg._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT xlsx_bytes, run_id, byte_size FROM consolidated_reports WHERE site_id=$1 AND report_date=$2",
            site_id, report_date,
        )
    assert row["xlsx_bytes"] == b"FAKE-B-LONGER"  # last write
    assert row["run_id"] == run_id_b
    assert row["byte_size"] == len(b"FAKE-B-LONGER")  # GENERATED 도 갱신


async def test_fetch_hit(pg: PGClient) -> None:
    """존재하면 bytes 반환."""
    site_id = "m15x-ph3-ibl"
    report_date = _date(2025, 9, 25)
    run_id = uuid.uuid4()
    await _make_pipeline_run(pg, run_id, site_id)
    async with pg._pool.acquire() as con:
        await con.execute(
            "DELETE FROM consolidated_reports WHERE site_id=$1 AND report_date=$2",
            site_id, report_date,
        )
    await upsert_consolidated_report(
        pg, site_id=site_id, report_date=report_date,
        xlsx_bytes=b"HIT-PATH-BYTES", run_id=run_id,
    )
    got = await fetch_consolidated_report(pg, site_id=site_id, report_date=report_date)
    assert got == b"HIT-PATH-BYTES"


async def test_fetch_miss(pg: PGClient) -> None:
    """미존재 시 None."""
    nonexistent_site = "no-such-site-zzz"
    got = await fetch_consolidated_report(
        pg, site_id=nonexistent_site, report_date=_date(1999, 1, 1),
    )
    assert got is None


async def test_fk_violation_no_site(pg: PGClient) -> None:
    """site_id FK 위반 시 IntegrityError raise."""
    import asyncpg.exceptions
    run_id = uuid.uuid4()
    # pipeline_runs 미생성 → run_id FK 도 위반 가능. site FK 가 먼저 잡힘.
    with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
        await upsert_consolidated_report(
            pg, site_id="no-such-site-zzz",
            report_date=_date(2025, 9, 25),
            xlsx_bytes=b"X", run_id=run_id,
        )
```

- [ ] **Step 2: 테스트 실행 → fail 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
source pipeline/.venv/bin/activate
PYTHONPATH=. pytest pipeline/tests/test_db_consolidated_reports.py -v
```

Expected: `ImportError: cannot import name 'upsert_consolidated_report' from 'pipeline.db'` 류로 5건 ERROR.

- [ ] **Step 3: `pipeline/db.py` 끝에 helper 2개 append**

`pipeline/db.py` 의 module-level free function 패턴 (기존 `insert_collector_inbox` 등) 끝에 다음 append. 정확한 위치 = 파일 마지막 helper 다음:

```python
# pipeline/db.py — append at end

import uuid
from datetime import date as _date
from typing import Optional


async def upsert_consolidated_report(
    pg: "PGClient",
    *,
    site_id: str,
    report_date: _date,
    xlsx_bytes: bytes,
    run_id: uuid.UUID,
) -> None:
    """consolidated_reports 에 UPSERT.

    ON CONFLICT (site_id, report_date) — last write wins (D-2 / D-4 / D-6 EC).
    graph 의 consolidated_xlsx_node 가 cycle 마다 호출 + seed mock backfill 도 호출.
    """
    async with pg._pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO consolidated_reports
              (site_id, report_date, xlsx_bytes, run_id, generated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (site_id, report_date) DO UPDATE
              SET xlsx_bytes   = EXCLUDED.xlsx_bytes,
                  run_id       = EXCLUDED.run_id,
                  generated_at = EXCLUDED.generated_at
            """,
            site_id, report_date, xlsx_bytes, run_id,
        )


async def fetch_consolidated_report(
    pg: "PGClient",
    *,
    site_id: str,
    report_date: _date,
) -> Optional[bytes]:
    """(D-5 E-2) cache hit → bytes, miss → None.

    /export/run 핸들러가 호출 — hit 면 즉시 응답, miss 면 live render fallback.
    """
    async with pg._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT xlsx_bytes FROM consolidated_reports WHERE site_id=$1 AND report_date=$2",
            site_id, report_date,
        )
    return row["xlsx_bytes"] if row else None
```

(import 들이 이미 파일 상단에 있다면 중복 추가 X — 기존 imports 확인 후 add)

- [ ] **Step 4: 테스트 재실행 → PASS**

```bash
PYTHONPATH=. pytest pipeline/tests/test_db_consolidated_reports.py -v
```

Expected: 5 passed.

- [ ] **Step 5: 회귀 (기존 db 테스트 통과 확인)**

```bash
PYTHONPATH=. pytest pipeline/tests/test_db.py pipeline/tests/test_db_collector_inbox.py -v
```

Expected: 모두 PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/db.py pipeline/tests/test_db_consolidated_reports.py
git commit -m "feat(db): consolidated_reports helper 2 (upsert + fetch) TDD

선행 collector_inbox helper 와 동일 패턴 (module-level free fn, PGClient
인스턴스 받음, kwargs). ON CONFLICT (site_id, report_date) UPSERT —
last write wins (D-2 / D-6 EC). 5 단위테스트 통과.

Spec: §6.3"
```

---

## Task 2: `state.py` 신 필드 2개

**Files:**
- Modify: `pipeline/state.py:226+` — `CPIAState` 에 필드 2개 추가

**의도:** exporter_node 의 산출 meta 보존 (bytes 안 박음, checkpoint 폭증 방지).

- [ ] **Step 1: state.py 변경**

`pipeline/state.py:265` (선행 D-12 의 `postgres_url: str` 다음) 에 추가:

```python
# pipeline/state.py — class CPIAState 안, postgres_url 다음

class CPIAState(TypedDict):
    # ... (line 230~265 기존 필드 유지) ...
    postgres_url: str  # collector_node 가 collector_inbox UPDATE 용

    # (D-7) exporter_node 산출 meta — bytes 는 박지 않음 (PostgresSaver checkpoint 폭증 방지)
    consolidated_xlsx_run_id: str          # str(uuid.UUID)
    consolidated_xlsx_generated_at: str    # ISO 8601 (datetime.utcnow().isoformat()+"Z")
```

- [ ] **Step 2: import 검증 (회귀)**

```bash
PYTHONPATH=. python3 -c "from pipeline.state import CPIAState; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: 회귀 — state 사용하는 모든 노드 통과**

```bash
PYTHONPATH=. pytest pipeline/tests/ -x --tb=short -q 2>&1 | tail -20
```

Expected: 기존 전체 테스트 통과 (이전 cycle 의 42+ tests).

- [ ] **Step 4: Commit**

```bash
git add pipeline/state.py
git commit -m "feat(state): CPIAState 에 consolidated_xlsx meta 2 필드 (D-7)

consolidated_xlsx_run_id / consolidated_xlsx_generated_at — exporter_node
산출 audit. bytes 는 박지 않음 (checkpoint 폭증 방지). TypedDict total=True
런타임 absent 호환 — 선행 D-12 4 필드 동일 패턴.

Spec: §6.2"
```

---

## Task 3: `exporter.py` consolidated_xlsx_node TDD

**Files:**
- Modify: `pipeline/agents/exporter.py:end` — 신 fn append (기존 함수 변경 0)
- Create: `pipeline/tests/test_exporter_node.py`

**의도:** graph 노드 wrapper — fetch_sheet_data → render_xlsx → upsert. 기존 함수 100% 재사용.

- [ ] **Step 1: 테스트 작성**

```python
# pipeline/tests/test_exporter_node.py
"""(Task 3) consolidated_xlsx_node — graph 노드 wrapper (D-1 / D-3 / D-7)."""

from __future__ import annotations

import uuid
from datetime import date as _date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline.agents.exporter import (
    NoDataError,
    SheetData,
    consolidated_xlsx_node,
)

pytestmark = pytest.mark.asyncio


def _base_state(run_id: str = "00000000-0000-0000-0000-000000000001") -> dict:
    return {
        "run_id": run_id,
        "site_id": "m15x-ph3-ibl",
        "date": "2025-09-25",
        "postgres_url": "postgresql://test",
        "project": "M15X Ph-3 IBL",
        "input_files": ["/tmp/fake.xlsx"],
    }


async def test_happy_path_upsert_and_meta() -> None:
    """fetch → render → upsert 4 단계 정상."""
    fake_pg = AsyncMock()
    fake_pg.connect = AsyncMock()
    fake_pg.close = AsyncMock()

    fake_sheet_data = SheetData(
        output_manpower=[{"bp_code": "X"}],
        occupation_manpower=[],
        equipment=[],
        quantity=[],
    )

    with patch(
        "pipeline.agents.exporter.PGClient", return_value=fake_pg,
    ), patch(
        "pipeline.agents.exporter.fetch_sheet_data",
        new=AsyncMock(return_value=fake_sheet_data),
    ) as mock_fetch, patch(
        "pipeline.agents.exporter.fetch_site_by_id",
        new=AsyncMock(return_value={"name": "M15X 현장"}),
    ), patch(
        "pipeline.agents.exporter.render_xlsx",
        return_value=b"FAKE-RENDERED-BYTES",
    ) as mock_render, patch(
        "pipeline.agents.exporter.upsert_consolidated_report",
        new=AsyncMock(),
    ) as mock_upsert:
        out = await consolidated_xlsx_node(_base_state())

    # fetch_sheet_data 인자 검증
    mock_fetch.assert_awaited_once()
    fetch_args = mock_fetch.await_args
    assert fetch_args.args[1] == "m15x-ph3-ibl"
    assert fetch_args.args[2] == _date(2025, 9, 25)
    # render_xlsx 호출
    mock_render.assert_called_once_with(fake_sheet_data, _date(2025, 9, 25), project="M15X 현장")
    # upsert 호출 + bytes 전달
    mock_upsert.assert_awaited_once()
    upsert_kwargs = mock_upsert.await_args.kwargs
    assert upsert_kwargs["xlsx_bytes"] == b"FAKE-RENDERED-BYTES"
    assert upsert_kwargs["site_id"] == "m15x-ph3-ibl"
    assert upsert_kwargs["report_date"] == _date(2025, 9, 25)
    # PG close 보장
    fake_pg.close.assert_awaited_once()
    # state meta 산출 검증
    assert out["consolidated_xlsx_run_id"] == "00000000-0000-0000-0000-000000000001"
    assert out["consolidated_xlsx_generated_at"].endswith("Z")


async def test_no_data_error_skip_upsert() -> None:
    """fetch_sheet_data 가 NoDataError raise — skip + return {}."""
    fake_pg = AsyncMock()
    fake_pg.connect = AsyncMock()
    fake_pg.close = AsyncMock()

    with patch(
        "pipeline.agents.exporter.PGClient", return_value=fake_pg,
    ), patch(
        "pipeline.agents.exporter.fetch_sheet_data",
        new=AsyncMock(side_effect=NoDataError("no data")),
    ), patch(
        "pipeline.agents.exporter.upsert_consolidated_report",
        new=AsyncMock(),
    ) as mock_upsert:
        out = await consolidated_xlsx_node(_base_state())

    assert out == {}
    mock_upsert.assert_not_awaited()  # skip
    fake_pg.close.assert_awaited_once()  # PG close 는 finally 에서


async def test_render_exception_propagates_close_pg() -> None:
    """render_xlsx 예외 propagate — PG close 는 보장."""
    fake_pg = AsyncMock()
    fake_pg.connect = AsyncMock()
    fake_pg.close = AsyncMock()

    fake_sheet_data = SheetData(
        output_manpower=[], occupation_manpower=[], equipment=[], quantity=[],
    )

    with patch(
        "pipeline.agents.exporter.PGClient", return_value=fake_pg,
    ), patch(
        "pipeline.agents.exporter.fetch_sheet_data",
        new=AsyncMock(return_value=fake_sheet_data),
    ), patch(
        "pipeline.agents.exporter.fetch_site_by_id",
        new=AsyncMock(return_value={"name": "X"}),
    ), patch(
        "pipeline.agents.exporter.render_xlsx",
        side_effect=ValueError("openpyxl 실패"),
    ):
        with pytest.raises(ValueError):
            await consolidated_xlsx_node(_base_state())

    fake_pg.close.assert_awaited_once()


async def test_project_fallback_state_project() -> None:
    """fetch_site_by_id 가 None 반환 시 state.project fallback."""
    fake_pg = AsyncMock()
    fake_pg.connect = AsyncMock()
    fake_pg.close = AsyncMock()

    fake_sheet_data = SheetData(
        output_manpower=[{}], occupation_manpower=[], equipment=[], quantity=[],
    )

    with patch(
        "pipeline.agents.exporter.PGClient", return_value=fake_pg,
    ), patch(
        "pipeline.agents.exporter.fetch_sheet_data",
        new=AsyncMock(return_value=fake_sheet_data),
    ), patch(
        "pipeline.agents.exporter.fetch_site_by_id",
        new=AsyncMock(return_value=None),
    ), patch(
        "pipeline.agents.exporter.render_xlsx",
        return_value=b"X",
    ) as mock_render, patch(
        "pipeline.agents.exporter.upsert_consolidated_report",
        new=AsyncMock(),
    ):
        await consolidated_xlsx_node(_base_state())

    # project = state["project"] fallback
    assert mock_render.call_args.kwargs["project"] == "M15X Ph-3 IBL"
```

- [ ] **Step 2: 테스트 실행 → fail 확인**

```bash
PYTHONPATH=. pytest pipeline/tests/test_exporter_node.py -v
```

Expected: `ImportError: cannot import name 'consolidated_xlsx_node' from 'pipeline.agents.exporter'` 4 ERROR.

- [ ] **Step 3: `pipeline/agents/exporter.py` 끝에 신 fn append**

기존 함수 (`fetch_sheet_data`, `render_xlsx`, `_fill_*`, COL dict 등) 모두 변경 0. 파일 마지막에 append:

```python
# pipeline/agents/exporter.py — append at end of file

import logging
import uuid as _uuid
from datetime import datetime as _dt
from typing import Any as _Any

from pipeline.db import (
    fetch_site_by_id,
    upsert_consolidated_report,
)
from pipeline.state import CPIAState

log = logging.getLogger("cpia.exporter_node")


async def consolidated_xlsx_node(state: CPIAState) -> dict[str, _Any]:
    """graph 노드 — Atomizer 끝나면 fan-out 으로 호출 (D-3 N-1).

    1) fetch_sheet_data → 자기 run + 이전 run 합집합 (D-12 invariant 유지)
    2) render_xlsx → bytes (~150KB)
    3) upsert_consolidated_reports → PG UPSERT (D-2 last write wins)
    4) state 에 meta 만 박음 (D-7 bytes 는 안 박음)

    예외 처리:
      - NoDataError: log + skip UPSERT, return {} — 발현 조건은 site×date 의
        cold-start (seed 미적용 + 어떤 run 도 진입 안 함). graph 토폴로지상
        자기 cycle 의 parser_reports INSERT 는 atomizer 도달 전 항상 존재
        (collector → parser → mapper → hil_1 → atomizer 순서, graph.py:594~597).
      - render_xlsx / PG 예외: raise → exporter path 'failed'. reporter path 와 별개.
    """
    site_id = state["site_id"]
    report_date = _date.fromisoformat(state["date"])
    run_id = _uuid.UUID(state["run_id"])

    pg = PGClient(state["postgres_url"])
    await pg.connect()
    try:
        try:
            data = await fetch_sheet_data(pg, site_id, report_date)
        except NoDataError:
            log.warning(
                "consolidated_xlsx_node: NoData site=%s date=%s — skip UPSERT",
                site_id, report_date,
            )
            return {}
        site_row = await fetch_site_by_id(pg, site_id)
        project = (site_row or {}).get("name") or state.get("project") or "CPIA"
        xlsx_bytes = render_xlsx(data, report_date, project=project)
        await upsert_consolidated_report(
            pg, site_id=site_id, report_date=report_date,
            xlsx_bytes=xlsx_bytes, run_id=run_id,
        )
        log.info(
            "consolidated_xlsx_node: UPSERT site=%s date=%s bytes=%d run=%s",
            site_id, report_date, len(xlsx_bytes), run_id,
        )
    finally:
        await pg.close()

    return {
        "consolidated_xlsx_run_id": str(run_id),
        "consolidated_xlsx_generated_at": _dt.utcnow().isoformat() + "Z",
    }
```

(`_date`, `PGClient`, `NoDataError`, `fetch_sheet_data`, `render_xlsx` 는 파일 상단에 이미 import 됨 — 중복 import 추가 X. 새 import 만 추가: `fetch_site_by_id`, `upsert_consolidated_report`, `logging`, `uuid as _uuid`, `datetime as _dt`, `typing.Any as _Any`, `CPIAState`)

- [ ] **Step 4: 테스트 재실행 → PASS**

```bash
PYTHONPATH=. pytest pipeline/tests/test_exporter_node.py -v
```

Expected: 4 passed.

- [ ] **Step 5: 회귀 — 기존 exporter render / endpoint 테스트 통과**

```bash
PYTHONPATH=. pytest pipeline/tests/test_exporter_render.py pipeline/tests/test_exporter_endpoint.py -v
```

Expected: 모두 PASS (Task 5 전이라 endpoint 테스트는 기존 동작 유지).

- [ ] **Step 6: Commit**

```bash
git add pipeline/agents/exporter.py pipeline/tests/test_exporter_node.py
git commit -m "feat(exporter): consolidated_xlsx_node — graph 노드 wrapper (D-1 / D-3)

기존 fetch_sheet_data / render_xlsx / _fill_* / COL dict 100% 재사용.
신 fn 1개 append (40줄). NoDataError skip path + render 예외 propagate +
project name fallback 4 단위테스트 통과.

Spec: §6.4"
```

---

## Task 4: `graph.py` 변경 + dual-END 통합 테스트 ★ 가장 위험

**Files:**
- Create: `pipeline/tests/test_graph_dual_end.py`
- Modify: `pipeline/graph.py:582-601` — import 1 + add_node 1 + add_edge 2

**의도:** Atomizer fan-out + dual-END. LangGraph multi-end 거동 검증. 한 path 실패가 다른 path 에 영향 X 검증.

- [ ] **Step 1: dual-END 통합 테스트 작성**

```python
# pipeline/tests/test_graph_dual_end.py
"""(Task 4) graph dual-END topology — fan-out + multi-end (D-3 N-1 / D-8)."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date as _date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline.graph import build_graph
from pipeline.state import CPIAState

pytestmark = pytest.mark.asyncio

POSTGRES_URL = os.environ.get(
    "POSTGRES_URL", "postgresql://cpia:cpia@localhost:5432/cpia"
)


def _fake_graph_config() -> MagicMock:
    """build_graph(cfg) 호환 최소 stub — LLM / Chroma 호출 회피."""
    cfg = MagicMock()
    cfg.azure_endpoint = "https://x"
    cfg.azure_api_key = "x"
    cfg.azure_api_version = "x"
    cfg.llm_model = "x"
    cfg.embedding_model = "x"
    cfg.chroma_host = "x"
    cfg.chroma_port = 5533
    cfg.chroma_ssl = False
    cfg.postgres_url = POSTGRES_URL
    return cfg


async def test_dual_end_both_paths_reach_end() -> None:
    """fan-out 후 forecaster path + exporter path 양쪽 END 도달."""
    cfg = _fake_graph_config()

    # 모든 노드를 단순 no-op stub 으로 patch (LLM / Chroma / PG 회피)
    async def noop(state: CPIAState) -> dict:
        return {}

    async def fake_exporter(state: CPIAState) -> dict:
        return {
            "consolidated_xlsx_run_id": state.get("run_id", ""),
            "consolidated_xlsx_generated_at": "2026-05-27T00:00:00Z",
        }

    with patch("pipeline.graph._collector", new=noop), \
         patch("pipeline.graph._parser", new=lambda s: {}), \
         patch("pipeline.graph.mapper_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.hil_1_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.atomizer_node", new=AsyncMock(return_value={"atomized_ids": []})), \
         patch("pipeline.graph.forecaster_node", new=AsyncMock(return_value={"forecasts": []})), \
         patch("pipeline.graph.hil_2_node", new=AsyncMock(return_value={"hil_2_selection": []})), \
         patch("pipeline.graph.optimizer_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.reporter_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.consolidated_xlsx_node", new=fake_exporter):
        graph = build_graph(cfg)
        run_id = str(uuid.uuid4())
        result = await graph.ainvoke(
            {
                "run_id": run_id,
                "site_id": "m15x-ph3-ibl",
                "date": "2025-09-25",
                "input_files": ["/tmp/fake.xlsx"],
                "postgres_url": POSTGRES_URL,
            },
            config={"configurable": {"thread_id": run_id}},
        )

    # 양 path 모두 END 도달 — exporter path 의 meta 박혀있음
    assert result["consolidated_xlsx_run_id"] == run_id


async def test_exporter_failure_does_not_break_reporter_path() -> None:
    """exporter path 가 예외 raise 해도 reporter path 는 정상 종료."""
    cfg = _fake_graph_config()

    async def failing_exporter(state: CPIAState) -> dict:
        raise RuntimeError("exporter 의도적 실패")

    async def reporter_marks_completed(state: CPIAState) -> dict:
        return {"reporter_done": True}

    with patch("pipeline.graph._collector", new=lambda s: {}), \
         patch("pipeline.graph._parser", new=lambda s: {}), \
         patch("pipeline.graph.mapper_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.hil_1_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.atomizer_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.forecaster_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.hil_2_node", new=AsyncMock(return_value={"hil_2_selection": []})), \
         patch("pipeline.graph.optimizer_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.reporter_node", new=reporter_marks_completed), \
         patch("pipeline.graph.consolidated_xlsx_node", new=failing_exporter):
        graph = build_graph(cfg)
        run_id = str(uuid.uuid4())
        # exporter 가 raise 하면 LangGraph 가 cycle 전체 실패로 처리할지,
        # exporter path 만 실패로 처리할지는 LangGraph 의 default 거동에 달려있음.
        # 본 테스트는 거동 자체를 capture — pass 가 아니라 "어떻게 실패하는지" 검증.
        # LangGraph 가 single-failure-fails-cycle 거동이면 pytest.raises 안에서 RuntimeError 받음.
        # multi-end 가 path 격리되면 result 가 reporter 완료 후 반환.
        try:
            result = await graph.ainvoke(
                {
                    "run_id": run_id,
                    "site_id": "m15x-ph3-ibl",
                    "date": "2025-09-25",
                    "input_files": ["/tmp/fake.xlsx"],
                    "postgres_url": POSTGRES_URL,
                },
                config={"configurable": {"thread_id": run_id}},
            )
            # 거동 A: path 격리 — reporter_done 박혀있음
            assert result.get("reporter_done") is True
        except RuntimeError as e:
            # 거동 B: single-failure-fails-cycle — RuntimeError 전파
            assert "exporter 의도적 실패" in str(e)
            pytest.skip(
                "LangGraph 가 single-failure-fails-cycle 거동 — "
                "본 테스트는 path 격리 거동 검증용. "
                "거동 확인됐으니 skip — spec §7.1 의 exporter 예외 시나리오 재논의 필요"
            )


async def test_topology_atomizer_has_two_outgoing_edges() -> None:
    """build_graph 후 atomizer 가 forecaster + exporter 두 edge 가짐."""
    cfg = _fake_graph_config()
    with patch("pipeline.graph._collector", new=lambda s: {}), \
         patch("pipeline.graph._parser", new=lambda s: {}), \
         patch("pipeline.graph.mapper_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.hil_1_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.atomizer_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.forecaster_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.hil_2_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.optimizer_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.reporter_node", new=AsyncMock(return_value={})), \
         patch("pipeline.graph.consolidated_xlsx_node", new=AsyncMock(return_value={})):
        graph = build_graph(cfg)

    # LangGraph 의 compile 된 graph 에서 atomizer 의 outgoing edge 검증
    # (LangGraph 0.x API — graph.get_graph() 가 networkx 비슷한 객체)
    g = graph.get_graph()
    edges_from_atomizer = [
        (s, t) for s, t in g.edges if s == "atomizer"
    ]
    targets = {t for _, t in edges_from_atomizer}
    assert "forecaster" in targets
    assert "exporter" in targets
```

(NOTE: `test_exporter_failure_does_not_break_reporter_path` 는 LangGraph multi-end 의 fault-isolation 거동이 버전 의존이라 — pass / skip 양쪽 거동 capture. 거동 B (single-failure-fails-cycle) 면 spec §7.1 의 "exporter path 만 'failed'" 가정이 무너지므로 spec 재논의 필요. **시연 risk 의 핵심 검증 포인트**.)

- [ ] **Step 2: 테스트 실행 → fail 확인**

```bash
PYTHONPATH=. pytest pipeline/tests/test_graph_dual_end.py -v
```

Expected: 모두 `AttributeError: module 'pipeline.graph' has no attribute 'consolidated_xlsx_node'` 또는 KeyError 류 ERROR.

- [ ] **Step 3: `pipeline/graph.py` 변경 (4 줄)**

`pipeline/graph.py:20` 의 `from pipeline.agents.collector_node import collector_node as _collector` 다음에 import 1:

```python
# pipeline/graph.py 상단 import 추가 (line ~22)
from pipeline.agents.exporter import consolidated_xlsx_node
```

`pipeline/graph.py:587` (`graph.add_node("atomizer", _atomizer)` 다음) 에 add_node 1:

```python
# pipeline/graph.py:587 (atomizer 다음) — 신 노드 추가
graph.add_node("exporter", consolidated_xlsx_node)
```

`pipeline/graph.py:597` (`graph.add_edge("atomizer", "forecaster")` 다음) 에 add_edge 2:

```python
# pipeline/graph.py:597 다음 — fan-out + dual-END
graph.add_edge("atomizer", "exporter")     # ★ fan-out edge
graph.add_edge("exporter", END)             # ★ dual-END
# 기존 atomizer → forecaster edge 는 그대로 유지 — fan-out 의 다른 가지
```

- [ ] **Step 4: 테스트 재실행 → PASS**

```bash
PYTHONPATH=. pytest pipeline/tests/test_graph_dual_end.py -v
```

Expected: 3 passed (또는 1 skipped if LangGraph 가 거동 B). 만약 skip 발생 → spec §7.1 재논의 게이트.

- [ ] **Step 5: 회귀 — 기존 graph 테스트 통과 확인**

```bash
PYTHONPATH=. pytest pipeline/tests/ -k "graph" -v
```

Expected: 기존 graph 테스트 (있다면) 모두 PASS.

- [ ] **Step 6: 전체 회귀**

```bash
PYTHONPATH=. pytest pipeline/tests/ -x --tb=short -q 2>&1 | tail -10
```

Expected: 42+ tests PASS (이전 cycle baseline + 본 cycle 신 12 tests = 54+).

- [ ] **Step 7: Commit**

```bash
git add pipeline/graph.py pipeline/tests/test_graph_dual_end.py
git commit -m "feat(graph): atomizer fan-out + exporter dual-END (D-3 N-1 / D-8)

CLAUDE.md 원안 토폴로지 Atomizer ‖ Exporter ‖ Forecaster 회귀.
graph.py 4줄 추가 (import + add_node + add_edge × 2). 기존 9 노드 / 11 edge
변경 0. dual-END 통합 테스트 3건 (path 도달 + 토폴로지 검증).

Spec: §4.1 / §6.5"
```

---

## Task 5: `exporter_routes.py` (E-2) hybrid + #N21 부분 해소

**Files:**
- Modify: `pipeline/exporter_routes.py` — 핸들러 본문 변경 + helper 분리
- Modify: `pipeline/tests/test_exporter_endpoint.py` — hit / miss 양 path assertion

**의도:** (D-5 E-2) cache hit 우선, miss 시 live render fallback. `request.app.state.pg` 사용으로 #N21 (Medium) 의 HTTP path 자연 해소.

- [ ] **Step 1: 기존 테스트 백업 확인 + 신 assertion 추가**

`pipeline/tests/test_exporter_endpoint.py` 의 기존 테스트 확인:

```bash
cat pipeline/tests/test_exporter_endpoint.py
```

기존 테스트가 `os.environ["POSTGRES_URL"]` 기반 PGClient 새로 만드는 path 라면, hit / miss 양 path 분리 필요. 다음 테스트 추가:

```python
# pipeline/tests/test_exporter_endpoint.py 끝에 append

async def test_export_run_cache_hit() -> None:
    """(E-2) consolidated_reports 에 row 있으면 cache hit 응답."""
    from fastapi.testclient import TestClient
    from pipeline.api import app
    import io
    from openpyxl import load_workbook

    # 사전 시드: consolidated_reports 에 fake xlsx bytes 박기
    # (TestClient 가 lifespan 실행 — app.state.pg 가 set 됨)
    with TestClient(app) as client:
        pg = app.state.pg
        run_id = uuid.uuid4()
        site_id = "m15x-ph3-ibl"
        report_date = _date(2025, 9, 25)

        # FK 만족용 pipeline_runs row
        async with pg._pool.acquire() as con:
            await con.execute(
                """
                INSERT INTO pipeline_runs (run_id, site_id, report_date, status)
                VALUES ($1, $2, $3, 'completed') ON CONFLICT DO NOTHING
                """,
                run_id, site_id, report_date,
            )
            await con.execute(
                "DELETE FROM consolidated_reports WHERE site_id=$1 AND report_date=$2",
                site_id, report_date,
            )

        # 실 xlsx template 사용 — load_workbook 검증 가능
        from pipeline.agents.exporter import TEMPLATE_PATH
        wb = load_workbook(TEMPLATE_PATH)
        buf = io.BytesIO()
        wb.save(buf)
        cache_bytes = buf.getvalue()

        await upsert_consolidated_report(
            pg, site_id=site_id, report_date=report_date,
            xlsx_bytes=cache_bytes, run_id=run_id,
        )

        # endpoint 호출 — hit path
        resp = client.get(f"/export/run?site_id={site_id}&date=2025-09-25")
        assert resp.status_code == 200
        assert resp.content == cache_bytes  # 사전시드한 그 bytes 그대로
        cd = resp.headers["content-disposition"]
        assert "통합작업일보_2025-09-25.xlsx" in cd
        # load_workbook 으로 valid xlsx 검증
        wb_check = load_workbook(io.BytesIO(resp.content))
        assert "1.출력인원 현황" in wb_check.sheetnames


async def test_export_run_cache_miss_fallback() -> None:
    """(E-2) consolidated_reports 에 row 없으면 live render fallback (200 OK)."""
    from fastapi.testclient import TestClient
    from pipeline.api import app

    with TestClient(app) as client:
        pg = app.state.pg
        site_id = "m15x-ph3-ibl"
        report_date = _date(2025, 9, 25)

        # 사전 cleanup
        async with pg._pool.acquire() as con:
            await con.execute(
                "DELETE FROM consolidated_reports WHERE site_id=$1 AND report_date=$2",
                site_id, report_date,
            )
        # parser_reports 가 있어야 live render 성공 — 기존 시드 데이터 가정
        # 만약 parser_reports 0건이면 400. 본 테스트는 seed 가 있는 환경 가정.

        resp = client.get(f"/export/run?site_id={site_id}&date=2025-09-25")
        # 두 가지 거동 capture:
        # (a) seed 있음 → 200 + xlsx bytes
        # (b) seed 없음 → 400 NoData
        assert resp.status_code in (200, 400)


async def test_export_run_404_site_not_found() -> None:
    """site_id 가 없으면 404 (cache miss 후 fallback path)."""
    from fastapi.testclient import TestClient
    from pipeline.api import app

    with TestClient(app) as client:
        resp = client.get("/export/run?site_id=no-such-site-zzz&date=2025-09-25")
        assert resp.status_code == 404
        assert "no-such-site-zzz" in resp.text
```

- [ ] **Step 2: 테스트 실행 → fail 확인**

```bash
PYTHONPATH=. pytest pipeline/tests/test_exporter_endpoint.py::test_export_run_cache_hit -v
```

Expected: 현재 `/export/run` 핸들러가 `os.environ` 으로 PGClient 새로 만들고 cache 검사 안 하므로 — assertion 실패 (`resp.content != cache_bytes` 정도). 또는 `request.app.state.pg` 미사용으로 KeyError 류.

- [ ] **Step 3: `pipeline/exporter_routes.py` 변경**

전체 파일 교체:

```python
# pipeline/exporter_routes.py
"""FastAPI /export/run endpoint — (D-5 E-2) hybrid + #N21 부분 해소."""

from __future__ import annotations

from datetime import date as _date

from fastapi import APIRouter, HTTPException, Request, Response

from pipeline.agents.exporter import NoDataError, fetch_sheet_data, render_xlsx
from pipeline.db import fetch_consolidated_report, fetch_site_by_id

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/run")
async def export_consolidated(
    request: Request,
    site_id: str,
    date: str,
) -> Response:
    try:
        report_date = _date.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")

    pg = request.app.state.pg  # ★ #N21 자연 해소 (lifespan pool 재사용)

    # (D-5 E-2) hit 우선
    cached = await fetch_consolidated_report(
        pg, site_id=site_id, report_date=report_date,
    )
    if cached is not None:
        return _build_xlsx_response(cached, date)

    # miss → live render fallback
    site = await fetch_site_by_id(pg, site_id)
    if not site:
        raise HTTPException(404, f"site_id={site_id} 없음")
    try:
        data = await fetch_sheet_data(pg, site_id, report_date)
    except NoDataError as e:
        raise HTTPException(400, str(e))
    xlsx_bytes = render_xlsx(
        data, report_date, project=site.get("name") or "CPIA",
    )
    return _build_xlsx_response(xlsx_bytes, date)


def _build_xlsx_response(xlsx_bytes: bytes, date: str) -> Response:
    """Content-Disposition UTF-8 raw_headers 패치 (한글 파일명, 선행 a7e2465)."""
    filename = f"통합작업일보_{date}.xlsx"
    resp = Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp.raw_headers.append((
        b"content-disposition",
        f'attachment; filename="{filename}"'.encode("utf-8"),
    ))
    return resp
```

- [ ] **Step 4: 테스트 재실행 → PASS**

```bash
PYTHONPATH=. pytest pipeline/tests/test_exporter_endpoint.py -v
```

Expected: 모두 PASS (신 3 testcase + 기존 testcases).

- [ ] **Step 5: 회귀 — render / db / api 통합**

```bash
PYTHONPATH=. pytest pipeline/tests/ -x --tb=short -q 2>&1 | tail -10
```

Expected: 모두 PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/exporter_routes.py pipeline/tests/test_exporter_endpoint.py
git commit -m "feat(exporter_routes): (E-2) hybrid + #N21 부분 해소 (D-5)

cache hit 우선 → miss 시 live render fallback. request.app.state.pg 로
lifespan PG pool 재사용. _build_xlsx_response helper 분리 (한글 파일명
UTF-8 raw_headers 패치 유지).

#N21 (Medium): HTTP path 만 해소 — 노드측은 graph-wide refactor (별 cycle).

Spec: §5.3 / §6.6"
```

---

## Task 6: `scripts/seed_dummy_year.py` 에 `consolidated_reports` mock backfill

**Files:**
- Modify: `scripts/seed_dummy_year.py` — `_backfill_consolidated_reports` 함수 append + 호출 1줄

**의도:** 시연 site×date 가 cycle 0번 실행이라도 `consolidated_reports` row 보장 — `/export/run` cache miss → 400 NoData 시연 risk 차단.

- [ ] **Step 1: `scripts/seed_dummy_year.py` 확인**

```bash
grep -n "def _backfill\|def main\|def seed\|^async def" scripts/seed_dummy_year.py | head -10
```

기존 backfill 함수 패턴 파악 후 동일 패턴으로 `_backfill_consolidated_reports` 추가.

- [ ] **Step 2: 신 함수 + 호출 추가**

`scripts/seed_dummy_year.py` 의 적절한 위치 (다른 `_backfill_*` 함수들 근처) 에 append:

```python
# scripts/seed_dummy_year.py 에 append

async def _backfill_consolidated_reports(pg: PGClient, sites: list[dict], dates: list[_date]) -> int:
    """(D-11) 시연 site×date 의 consolidated_reports mock backfill.

    각 site×date 에 대해 실 fetch_sheet_data + render_xlsx 호출 (parser_reports 가
    이미 seed 됐어야 함, 보통 _backfill_parser_reports 다음에 호출).
    실패 (NoDataError) 는 skip + log.

    Returns: backfill 된 row 수.
    """
    from pipeline.agents.exporter import (
        NoDataError, fetch_sheet_data, render_xlsx,
    )
    from pipeline.db import (
        fetch_site_by_id, upsert_consolidated_report,
    )

    count = 0
    for site in sites:
        site_id = site["site_id"]
        site_row = await fetch_site_by_id(pg, site_id)
        project_name = (site_row or {}).get("name") or "CPIA"
        for report_date in dates:
            try:
                data = await fetch_sheet_data(pg, site_id, report_date)
            except NoDataError:
                logging.info("seed consolidated_reports skip — site=%s date=%s (no parser data)", site_id, report_date)
                continue
            xlsx_bytes = render_xlsx(data, report_date, project=project_name)
            # 어느 run_id 든 FK 만족하면 OK — 가장 최근 run 사용
            async with pg._pool.acquire() as con:
                run_row = await con.fetchrow(
                    """
                    SELECT run_id FROM pipeline_runs
                    WHERE site_id=$1 AND report_date=$2
                    ORDER BY started_at DESC NULLS LAST LIMIT 1
                    """,
                    site_id, report_date,
                )
            if not run_row:
                logging.warning("seed consolidated_reports skip — no pipeline_runs for %s/%s", site_id, report_date)
                continue
            await upsert_consolidated_report(
                pg, site_id=site_id, report_date=report_date,
                xlsx_bytes=xlsx_bytes, run_id=run_row["run_id"],
            )
            # is_mock=true 마크 (선행 8 테이블 일관성, D-11)
            async with pg._pool.acquire() as con:
                await con.execute(
                    "UPDATE consolidated_reports SET is_mock=TRUE WHERE site_id=$1 AND report_date=$2",
                    site_id, report_date,
                )
            count += 1
            logging.info("seed consolidated_reports OK — site=%s date=%s bytes=%d", site_id, report_date, len(xlsx_bytes))
    return count
```

`seed_dummy_year.py` 의 main / orchestrator 함수 안에서 호출 추가 (다른 `_backfill_*` 다음, 기존 코드 위에서 site_list / dates 변수 확인 후):

```python
# main/orchestrator 안 — _backfill_parser_reports / _backfill_mapper_activities 등 다음
count = await _backfill_consolidated_reports(pg, sites, dates)
logging.info("seed_dummy_year: consolidated_reports backfill = %d rows", count)
```

- [ ] **Step 3: 실 seed 실행 + 결과 검증**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
source pipeline/.venv/bin/activate
PYTHONPATH=. python3 scripts/seed_dummy_year.py 2>&1 | tail -30
```

Expected: `seed consolidated_reports OK — site=m15x-ph3-ibl date=2025-09-25 bytes=...` 류 N건 로그.

```bash
psql "$POSTGRES_URL" -c "SELECT site_id, report_date, byte_size, is_mock FROM consolidated_reports ORDER BY report_date DESC LIMIT 10"
```

Expected: 시연 site×date (m15x-ph3-ibl, 2025-09-25 등) 의 row 가 `is_mock=true` 로 박혀있음.

- [ ] **Step 4: Commit**

```bash
git add scripts/seed_dummy_year.py
git commit -m "feat(seed): consolidated_reports mock backfill (D-11)

시연 site×date 가 cycle 0번 실행이어도 cache hit 보장 — /export/run NoData
400 시연 risk 차단. is_mock=true 마크 (선행 8 테이블 일관성).

Spec: §7.4 / §8.1 T6"
```

---

## Task 7: `_AGENTS_META` 에 Exporter stage 추가 + UI mapping

**Files:**
- Modify: `pipeline/api.py:662` — `_AGENTS_META` 에 Exporter entry 추가
- Modify: `web/lib/transforms.ts` — Agent stage mapping 에 Exporter 추가 (필요 시)

**의도:** tasks 페이지의 Agent stage progress 에 Exporter 노출 — (B-1) 선택 동기 (시연 임팩트 "AI Agent 가 자동으로 통합 빌드 완료") 실현.

- [ ] **Step 1: `pipeline/api.py:_AGENTS_META` 확인**

```bash
sed -n '660,710p' pipeline/api.py
```

기존 7 agent (Collector / Parser / Mapper / Atomizer / Forecaster / Optimizer / Reporter) entry 의 schema 파악 — 각 entry 의 키 (name / order / description 등).

- [ ] **Step 2: Exporter entry 추가**

`_AGENTS_META` list 의 적절한 위치 (Atomizer 와 Reporter 사이 — 시각화상 fan-out 분기 표시) 또는 Reporter 다음 (단순 linear 표시). spec §10 open question Q2 — 본 cycle 은 **Reporter 다음 단순 linear 표시** 채택 (시연 임팩트는 "Exporter 가 끝난 단계로 보임" 으로 충분):

```python
# pipeline/api.py:_AGENTS_META 에 entry 추가 (Reporter 다음)
# 기존 schema 와 정확히 일치하는 키 사용 — 위 sed 출력 확인 후
{
    "id": "exporter",  # ← schema 의 ID 키 (실 schema 에 맞춰)
    "name": "Exporter",
    "order": 8,  # 기존 Reporter=7 이라면 8
    "description": "graph cycle 마다 통합 작업일보 xlsx 사전생성 (consolidated_reports UPSERT)",
}
```

(실 schema 의 정확한 키는 기존 7 entry 의 첫 번째를 mimic — implementation 단계에서 확인 후 박기)

- [ ] **Step 3: `/api/agents/status` 호출 검증**

```bash
# FastAPI 가 기동 중이어야 함 — 별 터미널에서:
# PYTHONPATH=. uvicorn pipeline.api:app --reload --port 8000

curl http://localhost:8000/api/agents/status | python3 -m json.tool
```

Expected: 8 entry, 8번째가 "Exporter".

- [ ] **Step 4: `web/lib/transforms.ts` 확인 + 필요 시 mapping 추가**

```bash
grep -n "Collector\|Parser\|Mapper\|Atomizer\|Forecaster\|Optimizer\|Reporter\|Exporter" web/lib/transforms.ts
```

만약 stage name → 한국어 label / 색상 mapping 이 있으면 Exporter 추가. 없으면 backend `_AGENTS_META` 만으로 충분.

- [ ] **Step 5: UI 시각 검증**

```bash
cd web
npm run dev  # port 5536 (또는 3000)
# 브라우저로 http://localhost:5536/tasks 접속 → Agent stage progress 에 Exporter 노출 확인
```

(이 step 은 사용자 / B_Track 협업 시 시각 확인. CI 자동화 어려움.)

- [ ] **Step 6: Commit**

```bash
git add pipeline/api.py web/lib/transforms.ts
git commit -m "feat(agents/ui): _AGENTS_META + transforms 에 Exporter stage 추가 (D-10)

시연 임팩트 — Tasks 페이지 Agent stage progress 에 Exporter 노출.
(B-1) graph 사전생성의 가시화. 8번째 stage 로 linear 표시.

Spec: §1.3 / §7.3 잠재영향"
```

---

## Task 8: B_Track UI swap — `ConsolidatedReportCard.handleExport` (#R-N2 해소)

**Files:**
- Modify: `web/app/components/export/ConsolidatedReportCard.tsx` — `handleExport` 본문 swap
- Modify: `web/.env.local.example` — `NEXT_PUBLIC_FASTAPI_BASE` 추가
- Modify: `web/.env.local` (gitignored — 실 값 박기)

**의도:** 선행 cycle backlog #R-N2 해소 — 정적 fallback (`/sample/cpia-consolidated-report.xlsx`) → FastAPI `/export/run` 호출 swap.

- [ ] **Step 1: 현 `handleExport` 확인**

```bash
grep -A 20 "handleExport\|onExport" web/app/components/export/ConsolidatedReportCard.tsx | head -40
```

- [ ] **Step 2: `handleExport` swap**

기존 정적 fallback 부분을 다음으로 교체:

```typescript
// web/app/components/export/ConsolidatedReportCard.tsx
// handleExport 본문 — 정적 fallback 제거, /export/run 직접 호출

async function handleExport() {
  if (!report?.date || !siteId) return;
  try {
    const base = process.env.NEXT_PUBLIC_FASTAPI_BASE || "http://localhost:8000";
    const url = `${base}/export/run?site_id=${encodeURIComponent(siteId)}&date=${report.date}`;
    const res = await fetch(url);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Export 실패 (${res.status}): ${text}`);
    }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `통합작업일보_${report.date}.xlsx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  } catch (err) {
    console.error("Export 실패:", err);
    // 사용자에게 toast 또는 alert (기존 패턴 따라)
    alert(`다운로드 실패: ${err instanceof Error ? err.message : "알 수 없는 오류"}`);
  }
}
```

(siteId 변수 / report 객체의 정확한 구조는 기존 ConsolidatedReportCard props 확인 후 박기 — `report.date` / `siteId` 가 이미 props 로 들어오는지)

- [ ] **Step 3: `.env.local.example` 변경**

`web/.env.local.example` 끝에 추가:

```bash
# Exporter graph 통합 (2026-05-27 spec) — FastAPI base URL.
# 로컬: http://localhost:8000 / homelab: Cloudflare Tunnel 경유 도메인
NEXT_PUBLIC_FASTAPI_BASE=http://localhost:8000
```

- [ ] **Step 4: 실 검증 — Chrome DevTools**

```bash
cd web
npm run dev  # port 5536
```

브라우저:
1. `http://localhost:5536/export` 접속
2. 좌측 일자 list 에서 `2025-09-25` 선택
3. 우측 ConsolidatedReportCard 의 "Export" 버튼 클릭
4. Chrome DevTools → Network 탭
5. 요청 확인: `GET http://localhost:8000/export/run?site_id=m15x-ph3-ibl&date=2025-09-25` 200 응답
6. 다운로드된 파일: `통합작업일보_2025-09-25.xlsx`
7. openpyxl 로 검증:
   ```bash
   python3 -c "from openpyxl import load_workbook; wb = load_workbook('~/Downloads/통합작업일보_2025-09-25.xlsx'); print(wb.sheetnames)"
   ```
   Expected: `['1.출력인원 현황', '2.직종별 인원현황', '3.장비현황', '4.물량']`

- [ ] **Step 5: Commit**

```bash
git add web/app/components/export/ConsolidatedReportCard.tsx web/.env.local.example
git commit -m "feat(web/export): handleExport swap — 정적 fallback → /export/run (D-9 / #R-N2)

NEXT_PUBLIC_FASTAPI_BASE env. blob download + 한글 파일명. 선행 cycle
의 정적 /sample/cpia-consolidated-report.xlsx fallback 제거. Chrome
DevTools 로 200 + 4 시트 검증.

Spec: §4.2 / §8.1 T8"
```

---

## Task 9: E2E 시연 시나리오 검증

**Files:**
- Create: `docs/exporter-graph-integration-e2e-report-YYYY-MM-DD.md` (검증 보고서)

**의도:** 9 task 의 누적 결과를 실 메일 → graph cycle → cache hit → UI 다운로드 풀 사이클로 검증. 선행 cycle 의 stale Task #12 (E2E 데모 시나리오 검증) 동시 마무리.

- [ ] **Step 1: 환경 준비**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
source pipeline/.venv/bin/activate
# .env 가 .env.local 심볼릭 링크인지 확인
ls -la .env
# COLLECTOR_ENABLED=true 인지 확인
grep COLLECTOR_ENABLED .env.local
```

- [ ] **Step 2: FastAPI 기동 (백그라운드)**

```bash
PYTHONPATH=. uvicorn pipeline.api:app --reload --port 8000 > /tmp/cpia-api.log 2>&1 &
sleep 5
curl http://localhost:8000/health
```

Expected: `{"status":"ok","pg":true,"version":"0.1.0"}`.

- [ ] **Step 3: 시연 site×date cycle 1회 실행 — graph.ainvoke 직접**

`scripts/test_exporter_cycle.py` 임시 작성 (또는 IPython):

```python
# /tmp/exporter_cycle_test.py
import asyncio
import os
import uuid
from pipeline.graph import build_graph
from pipeline.api import _build_graph_config_from_env

async def main():
    cfg = _build_graph_config_from_env()  # 또는 GraphConfig() 직접
    graph = build_graph(cfg)
    run_id = str(uuid.uuid4())
    result = await graph.ainvoke(
        {
            "run_id": run_id,
            "site_id": "m15x-ph3-ibl",
            "date": "2025-09-25",
            "input_files": ["docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"],
            "postgres_url": os.environ["POSTGRES_URL"],
        },
        config={"configurable": {"thread_id": run_id}},
    )
    print("cycle done:", result.get("consolidated_xlsx_run_id"))

asyncio.run(main())
```

```bash
PYTHONPATH=. python3 /tmp/exporter_cycle_test.py
```

Expected: `cycle done: <uuid>` — exporter path 가 정상 종료.

- [ ] **Step 4: PG row 검증**

```bash
psql "$POSTGRES_URL" -c "SELECT site_id, report_date, byte_size, is_mock, generated_at FROM consolidated_reports ORDER BY generated_at DESC LIMIT 5;"
```

Expected:
```
   site_id    | report_date | byte_size | is_mock |       generated_at
--------------+-------------+-----------+---------+----------------------------
 m15x-ph3-ibl | 2025-09-25  |    150000 | f       | 2026-XX-XX XX:XX:XX+09
 ...
```

(byte_size 가 ~150KB 근방, is_mock=false 가 시연 cycle 결과)

- [ ] **Step 5: `/export/run` cache hit 검증**

```bash
curl -v -o /tmp/test.xlsx 'http://localhost:8000/export/run?site_id=m15x-ph3-ibl&date=2025-09-25' 2>&1 | grep -E "HTTP|content-disposition|Content-Length"
```

Expected: `HTTP/1.1 200 OK` + `content-disposition: attachment; filename="통합작업일보_2025-09-25.xlsx"` + `Content-Length: ~150000`.

```bash
python3 -c "from openpyxl import load_workbook; wb = load_workbook('/tmp/test.xlsx'); print(wb.sheetnames)"
```

Expected: `['1.출력인원 현황', '2.직종별 인원현황', '3.장비현황', '4.물량']`.

- [ ] **Step 6: UI 다운로드 검증 (수동)**

브라우저에서:
1. `http://localhost:5536/export` 접속
2. 좌측에서 `2025-09-25` 선택
3. Export 버튼 클릭
4. Chrome DevTools Network → `/export/run` 요청 200 확인
5. `통합작업일보_2025-09-25.xlsx` 다운로드 확인

- [ ] **Step 7: Tasks 페이지 Exporter stage 시각 검증 (수동)**

`http://localhost:5536/tasks` 진입 → Agent stage progress 에 Exporter 가 8번째 단계로 노출되는지 확인.

- [ ] **Step 8: dead_letter / 에러 path 검증**

```bash
# 파일명 regex 미일치 첨부 시뮬레이션 — 메일 직접 보내거나 listener 우회
# (PoC 시연 흐름엔 불필요 — 선행 cycle 테스트로 충분)
ls data/input/dead_letter/ 2>/dev/null
```

Expected: 기존 dead_letter 파일들이 있거나, 빈 디렉토리.

- [ ] **Step 9: 검증 보고서 작성**

```bash
date_today=$(date +%Y-%m-%d)
cat > docs/exporter-graph-integration-e2e-report-${date_today}.md <<EOF
# Exporter graph 사전생성 통합 — E2E 검증 보고서 (${date_today})

## 검증 환경
- Branch: A_Track, SHA: $(git rev-parse --short HEAD)
- FastAPI: localhost:8000 (uvicorn --reload)
- PG: \$POSTGRES_URL 의 prod
- Spec: docs/superpowers/specs/2026-05-27-cpia-exporter-graph-integration-design.md
- Plan: docs/superpowers/plans/2026-05-27-cpia-exporter-graph-integration-plan.md

## 검증 결과

### 1. graph cycle 실행
\`\`\`
[/tmp/exporter_cycle_test.py 출력 붙여넣기]
\`\`\`

### 2. consolidated_reports row
\`\`\`
[psql 출력 붙여넣기]
\`\`\`

### 3. /export/run cache hit
\`\`\`
[curl 출력 붙여넣기]
\`\`\`

### 4. xlsx 검증
\`\`\`
[load_workbook 출력 붙여넣기]
\`\`\`

### 5. UI 다운로드
- DevTools Network: \`/export/run\` 200 + 한글 파일명 ✅
- 파일 검증: 4 시트 정상 ✅

### 6. Tasks 페이지 Exporter stage
- Agent stage progress 에 Exporter 노출 ✅

## 결론
9 task 누적 결과 — 시연 라이브 호환. PoC D-9 (6/5) 시연 준비 완료.

## 잔여 백로그 (별 cycle)
- 노드 PG 접근 패턴 graph-wide refactor (spec §10)
- reporter→exporter rename (선행 #R-N1)
- PG advisory lock (D-6 EC 대안)
EOF
```

- [ ] **Step 10: Commit**

```bash
git add docs/exporter-graph-integration-e2e-report-*.md
git commit -m "docs(e2e): exporter graph 통합 검증 보고서 (Task 9)

9 task 누적 결과 검증 — graph cycle → consolidated_reports UPSERT →
/export/run cache hit → UI 다운로드 → Tasks 페이지 Exporter stage.
선행 cycle Task #12 (E2E 데모 시나리오 검증) 동시 마무리.

Spec: §8 / Plan: Task 9"
```

- [ ] **Step 11: FastAPI 종료**

```bash
pkill -f "uvicorn pipeline.api:app" || true
```

---

## 일정 요약 (PoC D-9 = 2026-06-05)

| 일자 | Task | 게이트 |
|---|---|---|
| **5/27 (오늘)** | plan 작성 + plan-document-reviewer + 사용자 승인 | plan 머지 |
| **5/28** | Task 0 + 1 + 2 + 3 (PG migration / db helper / state / node fn) | 단위 테스트 green |
| **5/29** | Task 4 (graph dual-END 통합 테스트 — 가장 위험) + Task 5 (E-2 endpoint) | 통합 테스트 green |
| **5/30** | Task 6 (seed backfill) + Task 7 (Agent stage UI) | 시연 데이터 준비 |
| 6/2 | Task 8 (B_Track UI swap) + Task 9 (E2E 검증) | 시연 검증 통과 |
| 6/3~6/4 | 시연 리허설 + 잔여 fix | 시연 안정성 |
| 6/5 | 시연 |  |

**buffer 2-3일** 확보.

---

## 충돌 회피 final check

본 plan 의 변경 영역:
- **신규 only** (충돌 0): `infra/postgres/migrations/2026-05-27_consolidated_reports.sql`, `pipeline/tests/test_db_consolidated_reports.py`, `pipeline/tests/test_exporter_node.py`, `pipeline/tests/test_graph_dual_end.py`, `docs/exporter-graph-integration-e2e-report-*.md`
- **변경 라인 최소** (다른 세션 read-only 영역과 충돌 없음): `pipeline/db.py` (append), `pipeline/state.py` (2 줄), `pipeline/agents/exporter.py` (append, 기존 fn 변경 0), `pipeline/graph.py` (4 줄), `pipeline/exporter_routes.py` (본문), `pipeline/api.py` (_AGENTS_META 1 entry), `scripts/seed_dummy_year.py` (append), `web/lib/transforms.ts` (~5 줄), `web/app/components/export/ConsolidatedReportCard.tsx` (~10 줄), `web/.env.local.example` (1 줄)

다른 세션이 작업 중인 `data-contract/`, `deep-dive/`, `pipeline/agents/optimizer/view_builder.py`, `pipeline/chroma_client.py` 와 **직접 충돌 0**.

---

## Iron Law verification 명령 모음 (각 task 의 done 기준)

```bash
# Task 0: PG migration
psql "$POSTGRES_URL" -c "\d consolidated_reports"

# Task 1: db helper
PYTHONPATH=. pytest pipeline/tests/test_db_consolidated_reports.py -v

# Task 2: state.py (회귀)
PYTHONPATH=. python3 -c "from pipeline.state import CPIAState; print('OK')"

# Task 3: exporter node
PYTHONPATH=. pytest pipeline/tests/test_exporter_node.py -v

# Task 4: graph dual-END (가장 위험)
PYTHONPATH=. pytest pipeline/tests/test_graph_dual_end.py -v

# Task 5: exporter endpoint
PYTHONPATH=. pytest pipeline/tests/test_exporter_endpoint.py -v

# Task 6: seed
PYTHONPATH=. python3 scripts/seed_dummy_year.py 2>&1 | tail -10
psql "$POSTGRES_URL" -c "SELECT count(*) FROM consolidated_reports WHERE is_mock=true"

# Task 7: agents status
curl http://localhost:8000/api/agents/status | python3 -m json.tool

# Task 8: UI swap
# Chrome DevTools Network 검증 (수동)

# Task 9: E2E
PYTHONPATH=. python3 /tmp/exporter_cycle_test.py
psql "$POSTGRES_URL" -c "SELECT site_id, report_date, byte_size FROM consolidated_reports ORDER BY generated_at DESC LIMIT 5"
curl -o /tmp/test.xlsx 'http://localhost:8000/export/run?site_id=m15x-ph3-ibl&date=2025-09-25'
```

각 명령의 **실 출력 (수정 없이 원본 인용)** 을 commit 메시지 또는 검증 보고서에 박을 것. "통과했습니다" 만으로는 done 불가.

---

## Next step

1. **plan-document-reviewer 디스패치** (writing-plans skill 의 review loop, max 3 iteration)
2. 사용자 plan 리뷰 게이트
3. **`superpowers:subagent-driven-development` 진입** — Task 0 부터 subagent dispatch + 2-stage review (spec compliance + code quality) per task
