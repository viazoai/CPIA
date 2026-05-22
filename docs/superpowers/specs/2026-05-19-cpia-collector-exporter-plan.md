# CPIA Collector + Exporter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gmail IMAP IDLE 푸시 트리거 Collector + 통합 작업일보 xlsx Exporter (FastAPI endpoint) 를 PoC D-17 (2026-06-05) 까지 구현 + 단위/통합 테스트 + B_Track UI swap.

**Architecture:** FastAPI 1 프로세스 startup background task 로 IDLE 루프 (idle_worker = listener), 메일 도착 즉시 첨부 추출 + 파일명 정규식 식별 + in-process `graph.ainvoke({input_files=[path], message_id, site_id, run_id, postgres_url})` 호출. graph 진입점은 **collector → parser → mapper → hil_1 → atomizer → forecaster → hil_2 → optimizer → reporter** (D-12: collector_node + parser_node 가 listener 가 박은 path 를 graph 안에서 검증·파싱). Exporter 는 graph 밖 별 FastAPI endpoint (`GET /export/run`), `pipeline_runs JOIN parser_*` SELECT + openpyxl 템플릿 fill + xlsx binary stream. Spec 의 모든 결정 (D-1 ~ D-12) 반영.

**Tech Stack:** Python 3.11+ (`pipeline/.venv/bin/python3`), aioimaplib, openpyxl, asyncpg, FastAPI, pytest-asyncio, LangGraph 기존 (변경 0).

**Spec:** `docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md`

**Conflict isolation:** Spec §9 의 read-only 목록 절대 안 건드림 — `state.py` / `graph.py` / `parser_*` / `mapper.py` / `atomizer.py` / `forecaster/` / `optimizer/` / `reporter.py` 등. 다른 세션이 진행 중인 PR 머지 후 본 cycle PR rebase.

---

## File Structure

### 신규 파일 (13)

| 파일 | 책임 | LoC 예상 |
|---|---|---|
| `pipeline/collector/__init__.py` | namespace | 1 |
| `pipeline/collector/filename_parser.py` | 첨부 파일명 → `ParsedFilename` 순수 함수 | ~60 |
| `pipeline/collector/config.py` | `CollectorConfig` dataclass + env 로드 | ~40 |
| `pipeline/collector/idle_worker.py` | IMAP IDLE 루프 + 첨부 추출 + dedup + graph 호출 | ~180 |
| `pipeline/agents/exporter.py` | `SheetData` + `fetch_sheet_data` + `render_xlsx` | ~220 |
| `pipeline/agents/exporter_templates/__init__.py` | 빈 package marker | 0 |
| `pipeline/agents/exporter_templates/consolidated_template.xlsx` | dummy xlsx 복사본 (git LFS 없이 일반 add) | binary |
| `pipeline/exporter_routes.py` | FastAPI APIRouter (`/export/run`) | ~50 |
| `infra/postgres/migrations/2026-05-19_collector_inbox.sql` | `collector_inbox` 테이블 생성 | ~30 |
| `pipeline/tests/test_filename_parser.py` | filename_parser 단위 (parametrize 12+) | ~120 |
| `pipeline/tests/test_idle_worker.py` | idle_worker 단위 (aioimaplib mock) | ~150 |
| `pipeline/tests/test_exporter_render.py` | render_xlsx 단위 (BytesIO 재 load) | ~140 |
| `pipeline/tests/test_exporter_endpoint.py` | `/export/run` endpoint 통합 (httpx + PG fixture) | ~120 |

### 수정 파일 (3) — 변경 라인 최소

| 파일 | 변경 | 라인 |
|---|---|---|
| `pipeline/pyproject.toml` | dependencies 에 `aioimaplib>=1.1.0` 추가 | +1 |
| `pipeline/api.py` | startup hook + shutdown hook + `include_router` | +~15 |
| `pipeline/db.py` | helper 4개: `insert_collector_inbox`, `update_collector_inbox_status`, `fetch_collector_inbox_by_message_id`, `fetch_site_by_id` | +~80 |

### 환경 / 문서

| 파일 | 변경 |
|---|---|
| `pipeline/.env.example` | 8 신규 env (COLLECTOR_* + EXPORTER_TEMPLATE_PATH) |
| `docs/collector-gmail-setup.md` (신규) | 데모용 Gmail 계정 / App Password 발급 절차 |

---

## Task 0: 작업 환경 준비

**Files:**
- Modify: `pipeline/pyproject.toml` (+1줄)
- Create: `pipeline/collector/__init__.py`
- Create: `pipeline/agents/exporter_templates/__init__.py`

- [ ] **Step 1: aioimaplib 의존성 추가**

`pipeline/pyproject.toml:7~19` 의 dependencies 리스트 끝에 한 줄 추가:

```toml
    "aioimaplib>=1.1.0",
```

- [ ] **Step 2: 의존성 설치**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/pip install "aioimaplib>=1.1.0"
.venv/bin/python3 -c "import aioimaplib; print(aioimaplib.__version__)"
```

기대 출력: 1.x.x 버전 한 줄.

- [ ] **Step 3: 신규 디렉토리 + 빈 `__init__.py` 생성**

```bash
mkdir -p "/Users/kyungseoplee/Project Agent/CPIA/pipeline/collector"
mkdir -p "/Users/kyungseoplee/Project Agent/CPIA/pipeline/agents/exporter_templates"
echo "" > "/Users/kyungseoplee/Project Agent/CPIA/pipeline/collector/__init__.py"
echo "" > "/Users/kyungseoplee/Project Agent/CPIA/pipeline/agents/exporter_templates/__init__.py"
```

- [ ] **Step 4: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/"
git add pipeline/pyproject.toml pipeline/collector/__init__.py pipeline/agents/exporter_templates/__init__.py
git commit -m "chore(collector): add aioimaplib + namespace dirs"
```

---

## Task 1: `filename_parser.py` — 첨부 파일명 정규식 (TDD)

**Files:**
- Create: `pipeline/collector/filename_parser.py`
- Test: `pipeline/tests/test_filename_parser.py`

**참고:** Spec §6.2. 순수 함수, 의존성 0.

- [ ] **Step 1: 실패 테스트 먼저 작성**

`pipeline/tests/test_filename_parser.py`:

```python
from __future__ import annotations

import pytest

from pipeline.collector.filename_parser import ParsedFilename, parse_filename


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # 업체별 — 샘플 그대로
        (
            "업체작업일보_M15X_PH4_041_M15X_PH4_UT_ 중원엔지니어링_UT배관공사_FAB_250917.xlsm",
            ParsedFilename(
                kind="bp",
                project="M15X_PH4_041_M15X_PH4_UT",
                bp_name="중원엔지니어링",
                trade="UT배관공사",
                zone="FAB",
                date="2025-09-17",
            ),
        ),
        # 통합
        (
            "통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx",
            ParsedFilename(
                kind="integrated",
                project="M15X Ph-3 IBL PJT 작업일보",
                bp_name=None, trade=None, zone=None,
                date="2025-09-25",
            ),
        ),
        # 업체별 — 다른 zone
        (
            "업체작업일보_M15X_PH3_001_acme_콘크리트공사_CUB_260101.xlsx",
            ParsedFilename(
                kind="bp", project="M15X_PH3_001",
                bp_name="acme", trade="콘크리트공사", zone="CUB", date="2026-01-01",
            ),
        ),
    ],
)
def test_parse_filename_valid(name: str, expected: ParsedFilename) -> None:
    assert parse_filename(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "random.xlsx",                               # prefix 미일치
        "업체작업일보_x.xlsx",                        # 토큰 부족
        "업체작업일보_a_b_c_d_99999.xlsx",            # date 5자리
        "업체작업일보_a_b_c_d_2025091.xlsx",          # date 7자리
        "통합작업일보_X.xlsx",                        # date 없음
        "업체작업일보_a_b_c_d_abcdef.xlsx",           # date 비숫자
        "",                                           # 빈 문자열
        ".xlsx",                                      # stem 비어
        "업체작업일보_M15X_a_b_250917.txt",            # 확장자 다름 (단 본 함수는 stem 만 봄 — 호출자가 ext 체크)
    ],
)
def test_parse_filename_invalid(name: str) -> None:
    # .txt 케이스는 stem 만 보면 valid 라 통과할 수 있음 — 호출자 책임.
    # 본 테스트는 prefix / 토큰 / date 형식만 검증.
    if name.endswith(".txt"):
        # stem 으로는 valid — 통과 케이스라 skip
        pytest.skip("ext 검증은 호출자 책임")
    assert parse_filename(name) is None


def test_parsed_filename_frozen() -> None:
    """ParsedFilename 은 frozen dataclass — site_id 는 별 인자."""
    pf = parse_filename("통합작업일보_X_250101.xlsx")
    assert pf is not None
    with pytest.raises((AttributeError, TypeError)):  # frozen → setattr 차단
        pf.date = "x"  # type: ignore[misc]
```

- [ ] **Step 2: 테스트 실행해 fail 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/python3 -m pytest tests/test_filename_parser.py -v 2>&1 | head -30
```

기대 출력: `ModuleNotFoundError: No module named 'pipeline.collector.filename_parser'`.

- [ ] **Step 3: 구현 작성**

`pipeline/collector/filename_parser.py`:

```python
"""첨부 파일명 정규식 — Spec §6.2.

업체작업일보_<project>_..._<bp>_<trade>_<zone>_<YYMMDD>.xlsx[m]
통합작업일보_<project>_<YYMMDD>.xlsx
미일치 시 None. 호출자가 ext / dead_letter 처리.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional


@dataclass(frozen=True)
class ParsedFilename:
    kind: Literal["bp", "integrated"]
    project: str
    bp_name: Optional[str]
    trade: Optional[str]
    zone: Optional[str]
    date: str  # ISO YYYY-MM-DD


def parse_filename(name: str) -> Optional[ParsedFilename]:
    """첨부 파일명 → ParsedFilename. 미일치 None.

    날짜 토큰은 6-digit YYMMDD 또는 8-digit YYYYMMDD 둘 다 허용 — 실 sample 양쪽 다 존재.
    """
    stem = Path(name).stem
    if not (stem.startswith("업체작업일보_") or stem.startswith("통합작업일보_")):
        return None
    parts = stem.split("_")
    if len(parts) < 2:
        return None
    raw_date = parts[-1]
    if not raw_date.isdigit():
        return None
    if len(raw_date) == 6:
        date = f"20{raw_date[:2]}-{raw_date[2:4]}-{raw_date[4:6]}"
    elif len(raw_date) == 8:
        date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
    else:
        return None
    if stem.startswith("통합작업일보_"):
        project_tokens = parts[1:-1]
        if not project_tokens:
            return None
        return ParsedFilename(
            kind="integrated",
            project="_".join(project_tokens),
            bp_name=None, trade=None, zone=None,
            date=date,
        )
    # 업체별: 끝 4 토큰 = bp, trade, zone, date
    if len(parts) < 5:
        return None
    return ParsedFilename(
        kind="bp",
        project="_".join(parts[1:-4]),
        bp_name=parts[-4].strip(),
        trade=parts[-3],
        zone=parts[-2],
        date=date,
    )
```

- [ ] **Step 4: 테스트 실행해 pass 확인**

```bash
.venv/bin/python3 -m pytest tests/test_filename_parser.py -v 2>&1 | tail -20
```

기대 출력: `4 passed` (parametrize 3 + 1 frozen test).

- [ ] **Step 5: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/"
git add pipeline/collector/filename_parser.py pipeline/tests/test_filename_parser.py
git commit -m "feat(collector): filename_parser — 첨부 파일명 정규식 (업체별 + 통합)"
```

---

## Task 2: `collector_inbox` PG 마이그레이션 + db.py helper 4개

**Files:**
- Create: `infra/postgres/migrations/2026-05-19_collector_inbox.sql`
- Modify: `pipeline/db.py` (helper 4개 추가)
- Test: `pipeline/tests/test_db_collector_inbox.py`

**참고:** Spec §5.3 (SQL DDL), §4.2 (db.py 변경 라인).

- [ ] **Step 1: 마이그레이션 파일 작성**

`infra/postgres/migrations/2026-05-19_collector_inbox.sql`:

```sql
-- 2026-05-19 — collector_inbox 신규 (메일 dedup + run 추적)
-- Spec: docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md §5.3

BEGIN;

CREATE TABLE IF NOT EXISTS collector_inbox (
  message_id          TEXT PRIMARY KEY,
  received_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  site_id             TEXT NOT NULL,
  report_date         DATE NOT NULL,
  bp_name             TEXT NOT NULL,
  attachment_filename TEXT NOT NULL,
  attachment_path     TEXT NOT NULL,
  run_id              UUID REFERENCES pipeline_runs(run_id) ON DELETE SET NULL,
  parse_status        TEXT NOT NULL DEFAULT 'pending'
                        CHECK (parse_status IN ('pending','running','completed','failed','dead_letter')),
  error               TEXT,
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS collector_inbox_site_date_idx
  ON collector_inbox (site_id, report_date);

CREATE INDEX IF NOT EXISTS collector_inbox_status_idx
  ON collector_inbox (parse_status)
  WHERE parse_status IN ('pending','running','failed');

COMMIT;
```

- [ ] **Step 2: 마이그레이션 적용 (prod PG)**

```bash
PGPASSWORD=$(grep '^POSTGRES_URL=' "/Users/kyungseoplee/Project Agent/CPIA/.env" | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|') \
  psql -h cpia-pg.zoai.uk -p 5532 -U cpia -d cpia \
  -f "/Users/kyungseoplee/Project Agent/CPIA/infra/postgres/migrations/2026-05-19_collector_inbox.sql"

# 검증
PGPASSWORD=... psql -h cpia-pg.zoai.uk -p 5532 -U cpia -d cpia \
  -c "\d collector_inbox"
```

기대 출력: 테이블 컬럼 12개 + 인덱스 2개.

- [ ] **Step 3: db.py 의 기존 import / class 위치 확인**

```bash
grep -n "^class PGClient\|^async def \|^def " "/Users/kyungseoplee/Project Agent/CPIA/pipeline/db.py" | head -20
```

`PGClient` 클래스 안에 method 추가하지 말고, 기존 패턴 (모듈 레벨 helper) 따라 `pipeline/db.py` 끝에 helper 4개 추가.

- [ ] **Step 4: 실패 테스트 작성**

`pipeline/tests/test_db_collector_inbox.py`:

```python
from __future__ import annotations

import os
import uuid
from datetime import date

import pytest

from pipeline.db import (
    PGClient,
    fetch_collector_inbox_by_message_id,
    fetch_site_by_id,
    insert_collector_inbox,
    update_collector_inbox_status,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def pg():
    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    yield pg
    await pg.close()


async def test_insert_and_fetch(pg: PGClient) -> None:
    mid = f"<test-{uuid.uuid4()}@example.com>"
    await insert_collector_inbox(
        pg,
        message_id=mid,
        site_id="m15x-ph3-ibl",
        report_date=date(2025, 9, 26),
        bp_name="중원",
        attachment_filename="x.xlsx",
        attachment_path="/tmp/x.xlsx",
    )
    row = await fetch_collector_inbox_by_message_id(pg, mid)
    assert row is not None
    assert row["site_id"] == "m15x-ph3-ibl"
    assert row["parse_status"] == "pending"

    # cleanup
    async with pg._pool.acquire() as con:
        await con.execute("DELETE FROM collector_inbox WHERE message_id=$1", mid)


async def test_update_status(pg: PGClient) -> None:
    mid = f"<test-{uuid.uuid4()}@example.com>"
    rid = uuid.uuid4()
    await insert_collector_inbox(
        pg, message_id=mid, site_id="m15x-ph3-ibl",
        report_date=date(2025, 9, 26), bp_name="x",
        attachment_filename="x.xlsx", attachment_path="/tmp/x.xlsx",
    )
    # run_id reference 위해 pipeline_runs 에 row 미리 삽입 필요 — 그래서 NULL 로 갱신
    await update_collector_inbox_status(pg, mid, parse_status="failed", error="boom")
    row = await fetch_collector_inbox_by_message_id(pg, mid)
    assert row["parse_status"] == "failed"
    assert row["error"] == "boom"

    async with pg._pool.acquire() as con:
        await con.execute("DELETE FROM collector_inbox WHERE message_id=$1", mid)


async def test_fetch_site_by_id_ok(pg: PGClient) -> None:
    # m15x-ph3-ibl 는 mock_sites.json 시드 — 없으면 skip
    site = await fetch_site_by_id(pg, "m15x-ph3-ibl")
    if site is None:
        pytest.skip("m15x-ph3-ibl 시드 미적용")
    assert site["site_id"] == "m15x-ph3-ibl"
    assert "name" in site


async def test_fetch_site_by_id_missing(pg: PGClient) -> None:
    site = await fetch_site_by_id(pg, "nonexistent-site-xyz")
    assert site is None
```

- [ ] **Step 5: 테스트 fail 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/python3 -m pytest tests/test_db_collector_inbox.py -v 2>&1 | head -25
```

기대 출력: `ImportError` (helper 미구현).

- [ ] **Step 6: db.py 에 helper 4개 추가**

`pipeline/db.py` 파일 끝 (마지막 함수 다음) 에 추가:

```python
# ──────────────────────────────────────────────────────────────────────────────
# Collector inbox — Spec §5.3 (2026-05-19)
# ──────────────────────────────────────────────────────────────────────────────


async def insert_collector_inbox(
    pg: PGClient,
    *,
    message_id: str,
    site_id: str,
    report_date,  # datetime.date
    bp_name: str,
    attachment_filename: str,
    attachment_path: str,
) -> None:
    """신규 메일 첨부 1건 INSERT. PRIMARY KEY 위반 시 ON CONFLICT DO NOTHING — dedup.

    spec: 호출자가 본 fn 이전에 fetch_collector_inbox_by_message_id 로 dedup 확인.
    여기선 race safety 위해 ON CONFLICT 박음.
    """
    async with pg._pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO collector_inbox
                (message_id, site_id, report_date, bp_name,
                 attachment_filename, attachment_path)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (message_id) DO NOTHING
            """,
            message_id, site_id, report_date, bp_name,
            attachment_filename, attachment_path,
        )


async def update_collector_inbox_status(
    pg: PGClient,
    message_id: str,
    *,
    run_id=None,
    parse_status: str,
    error: str | None = None,
) -> None:
    """parse_status / run_id / error 갱신. updated_at 자동.

    parse_status: 'pending'|'running'|'completed'|'failed'|'dead_letter'
    """
    async with pg._pool.acquire() as con:
        await con.execute(
            """
            UPDATE collector_inbox
            SET parse_status = $2,
                run_id       = COALESCE($3, run_id),
                error        = $4,
                updated_at   = NOW()
            WHERE message_id = $1
            """,
            message_id, parse_status, run_id, error,
        )


async def fetch_collector_inbox_by_message_id(
    pg: PGClient, message_id: str,
) -> dict | None:
    """dedup 체크용. 없으면 None."""
    async with pg._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT * FROM collector_inbox WHERE message_id = $1",
            message_id,
        )
    return dict(row) if row else None


async def fetch_site_by_id(pg: PGClient, site_id: str) -> dict | None:
    """sites 테이블 1 row. 없으면 None."""
    async with pg._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT site_id, name, plan_progress, actual_progress, status, location "
            "FROM sites WHERE site_id = $1",
            site_id,
        )
    return dict(row) if row else None
```

- [ ] **Step 7: 테스트 pass 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
POSTGRES_URL="$(grep '^POSTGRES_URL=' ../.env | cut -d= -f2-)" \
  .venv/bin/python3 -m pytest tests/test_db_collector_inbox.py -v 2>&1 | tail -15
```

기대 출력: `4 passed` (또는 `3 passed 1 skipped` — 시드 상태 따라).

- [ ] **Step 8: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/"
git add infra/postgres/migrations/2026-05-19_collector_inbox.sql pipeline/db.py pipeline/tests/test_db_collector_inbox.py
git commit -m "feat(collector): collector_inbox 테이블 + db.py helper 4개"
```

---

## Task 3: `CollectorConfig` + idle_worker 핵심 함수

**Files:**
- Create: `pipeline/collector/config.py`
- Create: `pipeline/collector/idle_worker.py` (1차 — 헬퍼만)

**참고:** Spec §6.1, §6.4.

- [ ] **Step 1: `CollectorConfig` dataclass 작성**

`pipeline/collector/config.py`:

```python
"""CollectorConfig — env 로드 + GraphConfig 의존성 wiring.

Spec: docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md §8.2
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pipeline.graph import GraphConfig


@dataclass(frozen=True)
class CollectorConfig:
    host: str
    port: int
    user: str
    app_password: str
    default_site_id: str
    input_dir: Path
    dead_letter_dir: Path
    postgres_url: str
    graph_cfg: GraphConfig
    enabled: bool


def _bool(s: str | None, default: bool = False) -> bool:
    if s is None:
        return default
    return s.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_collector_config(graph_cfg: GraphConfig) -> CollectorConfig:
    """환경 변수에서 로드 — Spec §8.2 의 9 env.

    Spec §10 결정 (env-only, fail-fast):
    - 자격증명 (USER / APP_PASSWORD) 은 코드에 default 없음.
    - COLLECTOR_ENABLED=true 인데 USER 또는 APP_PASSWORD 가 비어있으면 RuntimeError.
    - COLLECTOR_ENABLED=false 면 자격증명 누락 허용 (로컬 / 테스트 환경).
    - host / port 는 운영 swap 편의를 위해 default 유지 (secrets 아님).
    """
    enabled = _bool(os.environ.get("COLLECTOR_ENABLED"), default=False)
    user = os.environ.get("COLLECTOR_IMAP_USER", "")
    app_password = os.environ.get("COLLECTOR_IMAP_APP_PASSWORD", "")
    if enabled and not (user and app_password):
        missing = [
            k for k, v in
            [("COLLECTOR_IMAP_USER", user), ("COLLECTOR_IMAP_APP_PASSWORD", app_password)]
            if not v
        ]
        raise RuntimeError(
            f"COLLECTOR_ENABLED=true 인데 자격증명 누락: {missing}. "
            "pipeline/.env.local 확인 (spec §10 결정 — 코드 default 없음)"
        )
    return CollectorConfig(
        host=os.environ.get("COLLECTOR_IMAP_HOST", "imap.gmail.com"),
        port=int(os.environ.get("COLLECTOR_IMAP_PORT", "993")),
        user=user,
        app_password=app_password,
        default_site_id=os.environ.get("COLLECTOR_DEFAULT_SITE_ID", "m15x-ph3-ibl"),
        input_dir=Path(os.environ.get("COLLECTOR_INPUT_DIR", "data/input")),
        dead_letter_dir=Path(os.environ.get("COLLECTOR_DEAD_LETTER_DIR", "data/input/dead_letter")),
        postgres_url=os.environ["POSTGRES_URL"],
        graph_cfg=graph_cfg,
        enabled=enabled,
    )
```

- [ ] **Step 2: idle_worker 골격 + helper 함수 작성**

`pipeline/collector/idle_worker.py`:

```python
"""IMAP IDLE 푸시 트리거 — Spec §6.

핵심:
- FastAPI startup 시 asyncio.create_task(idle_loop(cfg)) 호출.
- IDLE EXISTS notification 받으면 UNSEEN fetch → 첨부 추출 → 파일명 식별
  → collector_inbox INSERT → asyncio.create_task(run_for_attachment) fire-and-forget.
- shutdown 시 request_shutdown() + task.cancel().
"""

from __future__ import annotations

import asyncio
import email
import logging
import os
import uuid
from asyncio import create_task  # monkeypatch target 분리 — 테스트 patch 안정성
from datetime import date as _date  # insert_collector_inbox.report_date 는 datetime.date 기대
from email.message import Message
from pathlib import Path

from pipeline.collector.config import CollectorConfig
from pipeline.collector.filename_parser import ParsedFilename, parse_filename
from pipeline.db import (
    PGClient,
    fetch_collector_inbox_by_message_id,
    insert_collector_inbox,
    update_collector_inbox_status,
)

log = logging.getLogger("cpia.collector")

_shutdown = asyncio.Event()
_GRAPH_SEM = asyncio.Semaphore(int(os.environ.get("CPIA_COLLECTOR_CONCURRENCY", "2")))


def request_shutdown() -> None:
    _shutdown.set()


def _extract_attachments(msg: Message) -> list[tuple[str, bytes]]:
    """email.Message → [(filename, bytes), ...]. inline / multipart 처리."""
    out: list[tuple[str, bytes]] = []
    if not msg.is_multipart():
        return out
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if not filename:
            continue
        # RFC 2047 디코딩
        decoded = email.header.decode_header(filename)
        decoded_str = "".join(
            (s.decode(enc or "utf-8") if isinstance(s, bytes) else s)
            for s, enc in decoded
        )
        if not decoded_str.lower().endswith((".xlsx", ".xlsm")):
            continue
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes):
            out.append((decoded_str, payload))
    return out


def _save_to_input_dir(
    att_name: str, att_bytes: bytes, date_iso: str, cfg: CollectorConfig,
) -> Path:
    """data/input/<YYYYMMDD>/<att_name> 저장. 같은 이름 충돌 시 timestamp suffix."""
    yyyymmdd = date_iso.replace("-", "")
    dir_ = cfg.input_dir / yyyymmdd
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / att_name
    if path.exists():
        stem = path.stem
        path = dir_ / f"{stem}_{uuid.uuid4().hex[:8]}{path.suffix}"
    path.write_bytes(att_bytes)
    return path


def _to_dead_letter(att_name: str, att_bytes: bytes, cfg: CollectorConfig) -> None:
    """파일명 미일치 / 식별 실패 시 dead_letter 폴더로 이동 + log."""
    cfg.dead_letter_dir.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:8]
    path = cfg.dead_letter_dir / f"{Path(att_name).stem}_{suffix}{Path(att_name).suffix}"
    path.write_bytes(att_bytes)
    log.warning("dead_letter: %s → %s", att_name, path)
```

`run_for_attachment` / `idle_loop` / `_drain_new` 은 다음 Step.

- [ ] **Step 3: idle_worker 에 `run_for_attachment` 추가**

`pipeline/collector/idle_worker.py` 끝에 추가:

```python
async def run_for_attachment(
    attachment_path: Path,
    meta: ParsedFilename,
    site_id: str,
    message_id: str,
    cfg: CollectorConfig,
) -> None:
    """semaphore 보호 + graph 1회 호출. 실패 시 collector_inbox.failed 박음."""
    from pipeline.graph import build_graph  # circular import 회피 — 지연 로드

    async with _GRAPH_SEM:
        run_id = uuid.uuid4()
        pg = PGClient(cfg.postgres_url)
        await pg.connect()
        try:
            await update_collector_inbox_status(
                pg, message_id, run_id=run_id, parse_status="running",
            )
        finally:
            await pg.close()

        try:
            # D-12: graph 진입점이 collector_node — listener 는 path/메타-trigger 만 박고
            # date/bp_name/project 분해는 collector_node 가 담당 (single source of truth).
            # collector_inbox UPDATE(running) 도 collector_node 가 하므로 위쪽 명시적 UPDATE 는
            # listener 측 안전망 (graph 진입 전 사고 대비) — 중복 UPDATE 는 idempotent.
            graph = build_graph(cfg.graph_cfg)
            await graph.ainvoke(
                {
                    "run_id": str(run_id),
                    "input_files": [str(attachment_path)],
                    "site_id": site_id,                # D-11
                    "message_id": message_id,          # collector_node 가 collector_inbox UPDATE 용
                    "postgres_url": cfg.postgres_url,  # collector_node PG 접근
                },
                config={"configurable": {"thread_id": str(run_id)}},
            )
        except Exception as e:
            log.exception("graph failed for %s", attachment_path)
            pg = PGClient(cfg.postgres_url)
            await pg.connect()
            try:
                await update_collector_inbox_status(
                    pg, message_id, parse_status="failed", error=str(e)[:1000],
                )
            finally:
                await pg.close()
            return

        pg = PGClient(cfg.postgres_url)
        await pg.connect()
        try:
            await update_collector_inbox_status(pg, message_id, parse_status="completed")
        finally:
            await pg.close()
```

- [ ] **Step 4: idle_worker 에 `_drain_new` + `idle_loop` 추가**

```python
async def _process_one(imap, uid: str, cfg: CollectorConfig) -> None:
    """UNSEEN 메일 1통 처리: fetch → dedup → 첨부 추출 → graph 호출 fire-and-forget."""
    import aioimaplib  # noqa: F401

    typ, data = await imap.fetch(uid, "(RFC822)")
    if typ != "OK" or len(data) < 2:
        log.warning("fetch uid=%s 실패: %s", uid, typ); return
    raw = data[1] if isinstance(data[1], (bytes, bytearray)) else b"".join(data[1])
    if isinstance(raw, bytearray):
        raw = bytes(raw)
    msg = email.message_from_bytes(raw)
    message_id = msg.get("Message-ID")
    if not message_id:
        log.warning("uid=%s Message-ID 없음, skip", uid)
        await imap.store(uid, "+FLAGS", "\\Seen")
        return

    # dedup PG 체크
    pg = PGClient(cfg.postgres_url); await pg.connect()
    try:
        existing = await fetch_collector_inbox_by_message_id(pg, message_id)
    finally:
        await pg.close()
    if existing:
        log.info("dedup skip: %s", message_id)
        await imap.store(uid, "+FLAGS", "\\Seen"); return

    attachments = _extract_attachments(msg)
    if not attachments:
        log.info("no attachment: %s", message_id)
        await imap.store(uid, "+FLAGS", "\\Seen"); return

    site_id = cfg.default_site_id  # D-11
    for att_name, att_bytes in attachments:
        meta = parse_filename(att_name)
        if meta is None:
            _to_dead_letter(att_name, att_bytes, cfg)
            continue
        path = _save_to_input_dir(att_name, att_bytes, meta.date, cfg)
        sub_message_id = f"{message_id}#{att_name}"
        pg = PGClient(cfg.postgres_url); await pg.connect()
        try:
            await insert_collector_inbox(
                pg,
                message_id=sub_message_id,
                site_id=site_id,
                # meta.date 는 ISO str — asyncpg DATE 컬럼 바인딩에 datetime.date 필요
                report_date=_date.fromisoformat(meta.date),
                bp_name=meta.bp_name or "_integrated",
                attachment_filename=att_name,
                attachment_path=str(path),
            )
        finally:
            await pg.close()
        create_task(
            run_for_attachment(path, meta, site_id, sub_message_id, cfg)
        )

    await imap.store(uid, "+FLAGS", "\\Seen")


async def _drain_new(imap, cfg: CollectorConfig) -> None:
    """UNSEEN 메일 전부 처리. IDLE EXISTS 직후 + startup 시 호출."""
    typ, data = await imap.search("UNSEEN")
    if typ != "OK" or not data or not data[0]:
        return
    uids = data[0].split() if isinstance(data[0], bytes) else data[0].encode().split()
    for uid_bytes in uids:
        uid = uid_bytes.decode() if isinstance(uid_bytes, bytes) else uid_bytes
        try:
            await _process_one(imap, uid, cfg)
        except Exception:
            log.exception("uid=%s 처리 실패", uid)


async def idle_loop(cfg: CollectorConfig) -> None:
    """FastAPI startup background task. shutdown 까지 IDLE 유지 + reconnect."""
    import aioimaplib

    backoff = 1.0
    while not _shutdown.is_set():
        try:
            imap = aioimaplib.IMAP4_SSL(host=cfg.host, port=cfg.port)
            await imap.wait_hello_from_server()
            await imap.login(cfg.user, cfg.app_password)
            await imap.select("INBOX")
            backoff = 1.0
            await _drain_new(imap, cfg)  # 시작 시 누적 UNSEEN 처리
            while not _shutdown.is_set():
                idle_task = await imap.idle_start(timeout=29 * 60)
                try:
                    push_msg = await imap.wait_server_push()
                finally:
                    imap.idle_done()
                    try:
                        await asyncio.wait_for(idle_task, timeout=5)
                    except asyncio.TimeoutError:
                        pass
                # EXISTS notification 이 있으면 새 메일 처리
                if push_msg and any("EXISTS" in str(m) for m in push_msg):
                    await _drain_new(imap, cfg)
        except asyncio.CancelledError:
            log.info("idle_loop cancelled — graceful exit")
            return
        except Exception:
            log.exception("IDLE loop error, reconnect in %.1fs", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
```

- [ ] **Step 5: syntax / import 검증**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/python3 -c "from pipeline.collector.idle_worker import idle_loop, request_shutdown, run_for_attachment; print('OK')"
```

기대 출력: `OK`

- [ ] **Step 6: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/"
git add pipeline/collector/config.py pipeline/collector/idle_worker.py
git commit -m "feat(collector): IDLE loop + run_for_attachment + helpers (no tests yet)"
```

---

## Task 3.5: collector_node + parser_node + graph wiring (D-12)

**Spec:** `2026-05-19-cpia-collector-exporter-design.md` §3 D-12 + §4.1 + §6.5

**왜 별 Task:** 현 `pipeline/graph.py` 는 `mapper` 부터 노드 — `CLAUDE.md` 의 "Collector → Parser → Mapper" 선언과 drift. listener (Task 3) 가 박은 path 를 graph 안에서 검증·파싱해야 PostgresSaver checkpoint / HiL / run_id 추적이 일관. `parser_node` / `collector_node` 는 기존 함수 (`parse_daily_report`, `filename_parser.parse_filename`) 의 1-줄 graph 래퍼라 본 Task 범위 작음.

**Files:**
- Create: `pipeline/agents/parser_node.py`
- Create: `pipeline/agents/collector_node.py`
- Create: `pipeline/tests/test_parser_node.py`
- Create: `pipeline/tests/test_collector_node.py`
- Modify: `pipeline/state.py` (~4 줄 필드 추가)
- Modify: `pipeline/graph.py` (~6 줄, add_node 2 + add_edge 3 + 기존 `START→mapper` edge 교체)

**선행 의존:** Task 1 (filename_parser) + Task 2 (db.py helper) 완료.

---

- [ ] **Step 1: 현 state.py 가 D-12 필드 보유 여부 확인 (read-only)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python -c "
from pipeline.state import CPIAState
import typing
hints = typing.get_type_hints(CPIAState)
for k in ('parsed','date','site_id','bp_name','project','message_id','postgres_url'):
    print(k, '✓' if k in hints else '✗')
"
```

기대: `parsed`/`date`/`site_id` 는 이미 ✓ (mapper / atomizer 가 이미 사용 중 — 기존 contract). `bp_name`/`project`/`message_id`/`postgres_url` 중 ✗ 항목만 Step 2 에서 추가.

- [ ] **Step 2: state.py 누락 필드 추가**

`pipeline/state.py` 의 `CPIAState` TypedDict 안에 (Step 1 에서 ✗ 인 것만). 기존 키 `parsed` / `date` / `site_id` / `input_files` 는 위에 이미 정의되어 있어 collector/parser 가 동일 키로 박음 (mapper contract 유지):

```python
class CPIAState(TypedDict, total=False):
    # ... 기존 필드 유지 (수정 0) ...

    # D-12 — collector_node / parser_node 산출 + listener invoke 인자
    bp_name: str        # 첨부 파일명에서 분해된 BP 명 ('_integrated' 가능)
    project: str        # 파일명 prefix
    message_id: str     # listener invoke 시 박힘. CLI 진입 시 absent
    postgres_url: str   # collector_node 가 collector_inbox UPDATE 용
```

- [ ] **Step 3: parser_node TDD — 실패 테스트 먼저**

`pipeline/tests/test_parser_node.py`:

```python
"""parser_node — 1 첨부 = 1 ParsedDailyReport (D-12, D-3)."""
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.agents.parser_node import parser_node


SAMPLE_XLSX = (
    Path(__file__).resolve().parents[2]
    / "docs" / "sample"
    / "통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
)


def test_parser_node_returns_parsed_report() -> None:
    state = {"input_files": [str(SAMPLE_XLSX)]}
    out = parser_node(state)
    # mapper 가 state["parsed"] (singular dict) 로 읽음
    assert "parsed" in out
    report = out["parsed"]
    # ParsedDailyReport 는 TypedDict — dict-style 접근
    assert report["bp_summaries"]  # 비어있지 않음
    assert report["activities"]


def test_parser_node_raises_on_missing_input_files() -> None:
    with pytest.raises((KeyError, IndexError)):
        parser_node({})
```

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/python -m pytest tests/test_parser_node.py -v 2>&1 | tail -15
```
Expected: 2 FAILED with `ModuleNotFoundError: No module named 'pipeline.agents.parser_node'`.

- [ ] **Step 4: parser_node 구현 — 최소 코드**

`pipeline/agents/parser_node.py`:

```python
"""parser_node — graph 노드. 기존 parse_daily_report 의 1-줄 래퍼 (D-12)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pipeline.agents.parser import parse_daily_report  # 내부 변경 0
from pipeline.state import CPIAState

log = logging.getLogger("cpia.parser_node")


def parser_node(state: CPIAState) -> dict[str, Any]:
    """1 첨부 = 1 ParsedDailyReport (D-3 유지). mapper 가 state["parsed"] (singular) 로 읽음."""
    path = Path(state["input_files"][0])
    report = parse_daily_report(path)
    # ParsedDailyReport 는 TypedDict — dict-style 접근
    log.info(
        "parser_node: %s 파싱 완료 (bp_summaries=%d, activities=%d)",
        path.name, len(report["bp_summaries"]), len(report["activities"]),
    )
    return {"parsed": report}
```

Run:
```bash
.venv/bin/python -m pytest tests/test_parser_node.py -v 2>&1 | tail -10
```
Expected: 2 PASSED.

- [ ] **Step 5: collector_node TDD — 실패 테스트 먼저**

`pipeline/tests/test_collector_node.py`:

```python
"""collector_node — 파일명 검증 + 메타 분해 + collector_inbox UPDATE (D-12)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline.agents.collector_node import collector_node


pytestmark = pytest.mark.asyncio


@pytest.fixture
def integrated_xlsx(tmp_path: Path) -> Path:
    """파일명 규약 통과 + 실 존재."""
    p = tmp_path / "통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
    p.write_bytes(b"dummy")
    return p


async def test_collector_node_extracts_meta(integrated_xlsx: Path) -> None:
    state = {
        "run_id": "00000000-0000-0000-0000-000000000001",
        "input_files": [str(integrated_xlsx)],
        # message_id 없음 → collector_inbox UPDATE skip
    }
    out = await collector_node(state)
    assert out["bp_name"] == "_integrated"
    # mapper 가 state["date"] 로 읽음 (graph.py:64 등) — 기존 contract 와 일치
    assert out["date"] == "2025-09-25"
    assert out["project"] == "M15X Ph-3 IBL PJT 작업일보"


async def test_collector_node_updates_inbox_when_message_id(integrated_xlsx: Path) -> None:
    # PGClient 는 connect()/close() 패턴 (async with 미지원, pipeline/db.py:15+ 확인)
    fake_pg = AsyncMock()
    fake_pg.connect = AsyncMock()
    fake_pg.close = AsyncMock()
    state = {
        "run_id": "00000000-0000-0000-0000-000000000002",
        "input_files": [str(integrated_xlsx)],
        "message_id": "<abc@example.com>#att.xlsx",
        "postgres_url": "postgresql://x",
    }
    with patch("pipeline.agents.collector_node.PGClient", return_value=fake_pg), \
         patch("pipeline.agents.collector_node.update_collector_inbox_status",
               new=AsyncMock()) as mock_update:
        await collector_node(state)
    mock_update.assert_awaited_once_with(
        fake_pg, "<abc@example.com>#att.xlsx",
        run_id=state["run_id"], parse_status="running",
    )
    fake_pg.close.assert_awaited_once()


async def test_collector_node_raises_on_missing_file(tmp_path: Path) -> None:
    state = {
        "run_id": "00000000-0000-0000-0000-000000000003",
        "input_files": [str(tmp_path / "nonexistent.xlsx")],
    }
    with pytest.raises(FileNotFoundError):
        await collector_node(state)


async def test_collector_node_raises_on_bad_filename(tmp_path: Path) -> None:
    bad = tmp_path / "random.xlsx"; bad.write_bytes(b"x")
    state = {"run_id": "x", "input_files": [str(bad)]}
    with pytest.raises(ValueError):
        await collector_node(state)
```

Run:
```bash
.venv/bin/python -m pytest tests/test_collector_node.py -v 2>&1 | tail -15
```
Expected: 4 FAILED with `ModuleNotFoundError`.

- [ ] **Step 6: collector_node 구현 — 최소 코드**

`pipeline/agents/collector_node.py`:

```python
"""collector_node — graph 진입 노드. listener 가 박은 input_files[0] 검증 + 메타 분해 (D-12)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pipeline.collector.filename_parser import parse_filename
from pipeline.db import PGClient, update_collector_inbox_status
from pipeline.state import CPIAState

log = logging.getLogger("cpia.collector_node")


async def collector_node(state: CPIAState) -> dict[str, Any]:
    """첨부 경로 검증 + filename_parser → state 메타 박기 + collector_inbox UPDATE.

    선행 (listener): collector_inbox INSERT(parse_status=pending) 완료.
    본 노드 책임 (Spec §6.5):
      1. state.input_files[0] 경로 존재 검증
      2. filename_parser 로 (bp_name, date, project) 분해
      3. message_id 가 state 에 있고 postgres_url 도 있으면 UPDATE(parse_status=running, run_id)
         — CLI 진입 (외부 listener 없이 main.py) 시 message_id absent → UPDATE skip
      4. mapper 가 쓸 메타 dict 반환
    """
    input_files = state.get("input_files") or []
    if not input_files:
        raise RuntimeError("collector_node: state.input_files 비어있음")
    path = Path(input_files[0])
    if not path.exists():
        raise FileNotFoundError(f"collector_node: {path}")
    meta = parse_filename(path.name)
    if meta is None:
        raise ValueError(f"collector_node: 파일명 규약 불일치 {path.name}")

    message_id = state.get("message_id")
    postgres_url = state.get("postgres_url")
    if message_id and postgres_url:
        # PGClient 는 connect()/close() 패턴 (async with 미지원).
        # Task 2 의 update_collector_inbox_status 는 모듈-level async helper.
        pg = PGClient(postgres_url)
        await pg.connect()
        try:
            await update_collector_inbox_status(
                pg, message_id, run_id=state["run_id"], parse_status="running",
            )
        finally:
            await pg.close()
    log.info(
        "collector_node: %s → bp=%s date=%s project=%s",
        path.name, meta.bp_name, meta.date, meta.project,
    )
    return {
        "bp_name": meta.bp_name or "_integrated",
        "date": meta.date,           # mapper 가 state["date"] 로 읽음
        "project": meta.project,
    }
```

Run:
```bash
.venv/bin/python -m pytest tests/test_collector_node.py -v 2>&1 | tail -15
```
Expected: 4 PASSED.

- [ ] **Step 7: graph.py wiring — `START → collector → parser → mapper`**

`pipeline/graph.py` 의 `build_graph` 함수 안. 기존 add_node 블록 (line ~557+) 위에 추가하고, 기존 `graph.add_edge(START, "mapper")` 1줄을 3줄로 교체:

```python
# ── D-12 신규 노드 ────────────────────────────────────────
from pipeline.agents.collector_node import collector_node as _collector
from pipeline.agents.parser_node import parser_node as _parser

graph.add_node("collector", _collector)
graph.add_node("parser", _parser)

# 기존:  graph.add_edge(START, "mapper")
graph.add_edge(START, "collector")     # 교체
graph.add_edge("collector", "parser")  # 신규
graph.add_edge("parser", "mapper")     # 신규
```

import 는 함수 안 import 가 아닌 모듈 top-level 로 옮길 것 (현 graph.py 스타일 확인 후 일관 유지).

- [ ] **Step 8: graph compile + smoke 호출 검증**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/python -c "
from pipeline.graph import build_graph
from unittest.mock import MagicMock
g = build_graph(MagicMock())
print('nodes:', sorted(g.nodes.keys()))
print('entry edge from START:', [e for e in g.edges if 'START' in str(e) or e[0] == '__start__'])
"
```

Expected:
```
nodes: ['__start__', 'atomizer', 'collector', 'forecaster', 'hil_1', 'hil_2', 'mapper', 'optimizer', 'parser', 'reporter']
entry edge from START: [('__start__', 'collector')]
```

(`forecaster`/`hil_2` 분기 등은 conditional_edges 라 위 출력에 안 잡혀도 무관.)

- [ ] **Step 9: 기존 graph 회귀 테스트 (있다면) 실행**

```bash
.venv/bin/python -m pytest tests/test_graph_e2e.py tests/test_each_agent.py -v 2>&1 | tail -20
```
Expected: 기존 PASS 유지 (단 외부에서 `parsed` 를 직접 박던 fixture 가 있다면 `input_files` 만 박도록 변경 — 별도 cleanup PR 후보).

- [ ] **Step 10: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/"
git add pipeline/state.py pipeline/graph.py \
        pipeline/agents/parser_node.py pipeline/agents/collector_node.py \
        pipeline/tests/test_parser_node.py pipeline/tests/test_collector_node.py
git commit -m "feat(graph): D-12 collector_node + parser_node — graph 진입점이 collector"
```

---

## Task 4: idle_worker 단위 테스트 (aioimaplib mock)

**Files:**
- Create: `pipeline/tests/test_idle_worker.py`

**참고:** Spec §8.1. LLM bypass — graph 호출은 monkey-patch 로 stub.

- [ ] **Step 1: aioimaplib mock 패턴 테스트 작성**

`pipeline/tests/test_idle_worker.py`:

```python
"""idle_worker 단위 테스트 — graph 호출은 stub. aioimaplib mock.

Spec: §6, §8.1.
"""

from __future__ import annotations

import asyncio
import email
import os
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from pipeline.collector.config import CollectorConfig
from pipeline.collector.idle_worker import (
    _drain_new,
    _extract_attachments,
    _process_one,
    _save_to_input_dir,
    _to_dead_letter,
)
from pipeline.collector.filename_parser import parse_filename

pytestmark = pytest.mark.asyncio


def _fake_cfg(tmp_path: Path) -> CollectorConfig:
    return CollectorConfig(
        host="imap.gmail.com", port=993,
        user="x@gmail.com", app_password="x",
        default_site_id="m15x-ph3-ibl",
        input_dir=tmp_path / "input",
        dead_letter_dir=tmp_path / "dead_letter",
        postgres_url=os.environ.get("POSTGRES_URL", "postgresql://x"),
        graph_cfg=MagicMock(),  # 본 테스트에선 graph 호출 stub
        enabled=False,
    )


def _build_email_with_attachment(
    filename: str, payload: bytes = b"PK\x03\x04xxxxxx",
    message_id: str | None = None,
) -> bytes:
    """multipart 메일 raw bytes — RFC822."""
    from email.mime.application import MIMEApplication
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart()
    msg["From"] = "pm@example.com"
    msg["To"] = "collector@example.com"  # 테스트 placeholder — 실제 collector 주소는 env
    msg["Subject"] = "작업일보"
    msg["Message-ID"] = message_id or f"<{uuid.uuid4()}@example.com>"
    msg.attach(MIMEText("본문"))
    att = MIMEApplication(payload)
    att.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(att)
    return msg.as_bytes()


def test_extract_attachments_basic() -> None:
    raw = _build_email_with_attachment(
        "업체작업일보_M15X_a_b_c_250917.xlsx", payload=b"abc",
    )
    msg = email.message_from_bytes(raw)
    out = _extract_attachments(msg)
    assert len(out) == 1
    assert out[0][0] == "업체작업일보_M15X_a_b_c_250917.xlsx"
    assert out[0][1] == b"abc"


def test_extract_attachments_skips_non_xlsx() -> None:
    raw = _build_email_with_attachment("readme.txt", payload=b"x")
    msg = email.message_from_bytes(raw)
    assert _extract_attachments(msg) == []


def test_save_to_input_dir_collision(tmp_path: Path) -> None:
    cfg = _fake_cfg(tmp_path)
    p1 = _save_to_input_dir("x.xlsx", b"a", "2025-09-26", cfg)
    p2 = _save_to_input_dir("x.xlsx", b"b", "2025-09-26", cfg)
    assert p1.exists() and p2.exists()
    assert p1 != p2  # suffix 로 충돌 회피
    assert p1.parent.name == "20250926"


def test_to_dead_letter(tmp_path: Path) -> None:
    cfg = _fake_cfg(tmp_path)
    _to_dead_letter("garbage.xlsx", b"x", cfg)
    files = list(cfg.dead_letter_dir.glob("garbage_*.xlsx"))
    assert len(files) == 1


async def test_process_one_dedup(tmp_path: Path, monkeypatch) -> None:
    """이미 collector_inbox 에 있는 message_id 는 skip."""
    cfg = _fake_cfg(tmp_path)
    mid = f"<dup-{uuid.uuid4()}@example.com>"
    raw = _build_email_with_attachment(
        "업체작업일보_M15X_a_b_c_250917.xlsx", message_id=mid,
    )

    # fetch_collector_inbox_by_message_id 가 row 반환 → dedup skip
    async def fake_fetch(_pg, _mid):
        return {"message_id": _mid, "parse_status": "completed"}

    monkeypatch.setattr(
        "pipeline.collector.idle_worker.fetch_collector_inbox_by_message_id",
        fake_fetch,
    )
    monkeypatch.setattr(
        "pipeline.collector.idle_worker.insert_collector_inbox",
        AsyncMock(),  # 호출 안 되어야 함
    )
    monkeypatch.setattr("pipeline.collector.idle_worker.PGClient", MagicMock(
        return_value=AsyncMock(connect=AsyncMock(), close=AsyncMock()),
    ))

    create_task_mock = MagicMock()
    monkeypatch.setattr("pipeline.collector.idle_worker.create_task", create_task_mock)

    fake_imap = AsyncMock()
    fake_imap.fetch.return_value = ("OK", [b"1", raw, b")"])
    fake_imap.store = AsyncMock()

    await _process_one(fake_imap, "1", cfg)

    # graph 호출 안 일어남
    assert create_task_mock.call_count == 0
    fake_imap.store.assert_called_with("1", "+FLAGS", "\\Seen")


async def test_process_one_dispatches_graph(tmp_path: Path, monkeypatch) -> None:
    """첨부 valid + dedup miss 면 asyncio.create_task 로 graph 호출 dispatch."""
    cfg = _fake_cfg(tmp_path)
    mid = f"<new-{uuid.uuid4()}@example.com>"
    raw = _build_email_with_attachment(
        "업체작업일보_M15X_PH4_041_M15X_PH4_UT_acme_콘크리트_FAB_250917.xlsx",
        message_id=mid,
    )

    async def fake_fetch(_pg, _mid):
        return None  # dedup miss

    monkeypatch.setattr(
        "pipeline.collector.idle_worker.fetch_collector_inbox_by_message_id", fake_fetch,
    )
    monkeypatch.setattr(
        "pipeline.collector.idle_worker.insert_collector_inbox", AsyncMock(),
    )
    monkeypatch.setattr("pipeline.collector.idle_worker.PGClient", MagicMock(
        return_value=AsyncMock(connect=AsyncMock(), close=AsyncMock()),
    ))

    dispatched: list = []

    def fake_create_task(coro):
        dispatched.append(coro)
        coro.close()  # 실행 안 함 — graph 호출 차단

    monkeypatch.setattr(
        "pipeline.collector.idle_worker.create_task", fake_create_task,
    )

    fake_imap = AsyncMock()
    fake_imap.fetch.return_value = ("OK", [b"1", raw, b")"])
    fake_imap.store = AsyncMock()

    await _process_one(fake_imap, "1", cfg)

    assert len(dispatched) == 1  # graph 호출 task 1개 dispatch
    saved = list((cfg.input_dir / "20250917").glob("*.xlsx"))
    assert len(saved) == 1
```

- [ ] **Step 2: 테스트 실행해 fail 없는지 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/python3 -m pytest tests/test_idle_worker.py -v 2>&1 | tail -20
```

기대 출력: `6 passed`.

- [ ] **Step 3: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/"
git add pipeline/tests/test_idle_worker.py
git commit -m "test(collector): idle_worker 단위 (aioimaplib mock + graph stub)"
```

---

## Task 5: Exporter 템플릿 복사 + git add

**Files:**
- Create: `pipeline/agents/exporter_templates/consolidated_template.xlsx`

**참고:** Spec §7.2. `docs/sample/통합작업일보_DUMMY_20250926.xlsx` 를 템플릿으로 복사.

- [ ] **Step 1: dummy xlsx 복사**

```bash
cp "/Users/kyungseoplee/Project Agent/CPIA/docs/sample/통합작업일보_DUMMY_20250926.xlsx" \
   "/Users/kyungseoplee/Project Agent/CPIA/pipeline/agents/exporter_templates/consolidated_template.xlsx"
```

- [ ] **Step 2: 4 시트 r5 ~ r마지막 데이터 행 제거 (헤더만 남김)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/python3 - <<'PY'
from openpyxl import load_workbook
p = "agents/exporter_templates/consolidated_template.xlsx"
wb = load_workbook(p)
for sname in wb.sheetnames:
    ws = wb[sname]
    if ws.max_row > 4:
        # 5 행부터 끝까지 삭제
        ws.delete_rows(5, ws.max_row - 4)
wb.save(p)
print("done")
PY
```

기대 출력: `done`. 4 시트 모두 r4 까지만 남음 (헤더).

- [ ] **Step 3: openpyxl 로 시트 / 헤더 확인**

```bash
.venv/bin/python3 - <<'PY'
from openpyxl import load_workbook
wb = load_workbook("agents/exporter_templates/consolidated_template.xlsx")
for s in wb.sheetnames:
    ws = wb[s]
    print(f"{s}: {ws.max_row} rows × {ws.max_column} cols")
PY
```

기대 출력: 4 시트 모두 `max_row` ≤ 5.

- [ ] **Step 4: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/"
git add pipeline/agents/exporter_templates/consolidated_template.xlsx
git commit -m "feat(exporter): consolidated_template.xlsx (dummy 헤더만 보존)"
```

---

## Task 6: Exporter — `fetch_sheet_data` PG SELECT (TDD)

**Files:**
- Create: `pipeline/agents/exporter.py` (1차 — fetch 함수까지)
- Test: `pipeline/tests/test_exporter_endpoint.py` (1차 — fetch 만)

**참고:** Spec §7.1. `pipeline_runs JOIN parser_*` 패턴.

- [ ] **Step 1: 실패 테스트 작성**

`pipeline/tests/test_exporter_endpoint.py` (1차 — fetch_sheet_data 만):

```python
"""Exporter SELECT + endpoint 통합 테스트.

PG fixture 에 parser_reports + parser_activities + pipeline_runs row 직접 INSERT
→ fetch_sheet_data / endpoint 결정론적 검증. LLM 호출 0.

Spec: §7.1, §7.3, §8.1.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date

import pytest

from pipeline.agents.exporter import NoDataError, SheetData, fetch_sheet_data
from pipeline.db import PGClient

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def pg():
    pg = PGClient(os.environ["POSTGRES_URL"]); await pg.connect()
    yield pg
    await pg.close()


@pytest.fixture
async def seeded_run(pg: PGClient):
    """test run 1 + parser_reports + parser_activities row 시드."""
    run_id = uuid.uuid4()
    site_id = "m15x-ph3-ibl"
    rdate = date(2099, 1, 1)  # 미래 날짜 — 운영 데이터와 충돌 회피

    async with pg._pool.acquire() as con:
        # pipeline_runs 컬럼: run_id, site_id, report_date, status, current_node,
        # error, atomized_count, started_at (NOT NULL DEFAULT NOW()), completed_at
        # `created_at` 컬럼 없음 — started_at 의 default 사용 (생략).
        await con.execute(
            """
            INSERT INTO pipeline_runs (run_id, site_id, report_date, status)
            VALUES ($1, $2, $3, 'completed')
            """,
            run_id, site_id, rdate,
        )
        await con.execute(
            """
            INSERT INTO parser_reports
                (run_id, report_date, project, bp_summaries, job_allocations,
                 equipment_allocations, activity_count)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7)
            """,
            run_id, rdate, "TEST",
            json.dumps([{"zone": "FAB", "company": "acme", "today_incr_total": 5}]),
            json.dumps([{"disc_abbrev": "TE", "job_type": "BP소장"}]),
            json.dumps([{"equipment_big": "굴삭운반"}]),
            1,
        )
        await con.execute(
            """
            INSERT INTO parser_activities
                (run_id, report_date, idx, l5_disc, trade, company, unit, today_qty,
                 work_content, plan_total_qty)
            VALUES ($1, $2, 0, '공통가설', 'TE', 'acme', '인', 5, 'M15 환경유지', 100)
            """,
            run_id, rdate,
        )

    yield (run_id, site_id, rdate)

    async with pg._pool.acquire() as con:
        await con.execute("DELETE FROM parser_activities WHERE run_id=$1", run_id)
        await con.execute("DELETE FROM parser_reports WHERE run_id=$1", run_id)
        await con.execute("DELETE FROM pipeline_runs WHERE run_id=$1", run_id)


async def test_fetch_sheet_data_returns_jsonb_rows(pg: PGClient, seeded_run) -> None:
    run_id, site_id, rdate = seeded_run
    data = await fetch_sheet_data(pg, site_id, rdate)
    assert isinstance(data, SheetData)
    assert data.output_manpower[0]["zone"] == "FAB"
    assert data.occupation_manpower[0]["disc_abbrev"] == "TE"
    assert data.equipment[0]["equipment_big"] == "굴삭운반"
    assert data.quantity[0]["company"] == "acme"


async def test_fetch_sheet_data_no_data_raises(pg: PGClient) -> None:
    with pytest.raises(NoDataError):
        await fetch_sheet_data(pg, "nonexistent-site", date(2099, 12, 31))


async def test_fetch_sheet_data_filters_other_sites(pg: PGClient, seeded_run) -> None:
    """다른 site_id 면 NoDataError — JOIN 필터링 검증."""
    _run_id, _site_id, rdate = seeded_run
    with pytest.raises(NoDataError):
        await fetch_sheet_data(pg, "other-site-xyz", rdate)
```

- [ ] **Step 2: 테스트 실행해 fail 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/python3 -m pytest tests/test_exporter_endpoint.py::test_fetch_sheet_data_returns_jsonb_rows -v 2>&1 | head -20
```

기대 출력: `ModuleNotFoundError: No module named 'pipeline.agents.exporter'`.

- [ ] **Step 3: exporter.py 1차 (SheetData + fetch_sheet_data)**

`pipeline/agents/exporter.py`:

```python
"""Exporter — 통합 작업일보 xlsx 생성.

Spec: docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md §7
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date

from pipeline.db import PGClient


class NoDataError(Exception):
    """해당 (site_id, report_date) 의 parser_* row 0건."""


@dataclass
class SheetData:
    output_manpower: list[dict]      # 시트1
    occupation_manpower: list[dict]  # 시트2
    equipment: list[dict]             # 시트3
    quantity: list[dict]              # 시트4


async def fetch_sheet_data(
    pg: PGClient, site_id: str, report_date: _date,
) -> SheetData:
    """모든 run 의 jsonb 합집합 — Spec §7.1.

    parser_reports / parser_activities 는 site_id 컬럼 없음 → pipeline_runs JOIN.
    """
    async with pg._pool.acquire() as con:
        bp_rows = await con.fetch(
            """
            SELECT jsonb_array_elements(pt.bp_summaries) AS row
            FROM parser_reports pt
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pt.report_date = $2
            """,
            site_id, report_date,
        )
        job_rows = await con.fetch(
            """
            SELECT jsonb_array_elements(pt.job_allocations) AS row
            FROM parser_reports pt
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pt.report_date = $2
            """,
            site_id, report_date,
        )
        eq_rows = await con.fetch(
            """
            SELECT jsonb_array_elements(pt.equipment_allocations) AS row
            FROM parser_reports pt
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pt.report_date = $2
            """,
            site_id, report_date,
        )
        act_rows = await con.fetch(
            """
            SELECT pa.*
            FROM parser_activities pa
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pa.report_date = $2
            ORDER BY pa.run_id, pa.idx
            """,
            site_id, report_date,
        )

    if not (bp_rows or job_rows or eq_rows or act_rows):
        raise NoDataError(f"해당 ({site_id}, {report_date.isoformat()}) 데이터 없음")

    return SheetData(
        output_manpower=[r["row"] for r in bp_rows],
        occupation_manpower=[r["row"] for r in job_rows],
        equipment=[r["row"] for r in eq_rows],
        quantity=[dict(r) for r in act_rows],
    )
```

- [ ] **Step 4: 테스트 pass 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
POSTGRES_URL="$(grep '^POSTGRES_URL=' ../.env | cut -d= -f2-)" \
  .venv/bin/python3 -m pytest tests/test_exporter_endpoint.py -v -k fetch_sheet_data 2>&1 | tail -15
```

기대 출력: `3 passed`.

- [ ] **Step 5: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/"
git add pipeline/agents/exporter.py pipeline/tests/test_exporter_endpoint.py
git commit -m "feat(exporter): fetch_sheet_data PG SELECT (pipeline_runs JOIN)"
```

---

## Task 7: Exporter — `render_xlsx` + 시트별 fill (TDD)

**Files:**
- Modify: `pipeline/agents/exporter.py` (render_xlsx + 4 _fill_*)
- Test: `pipeline/tests/test_exporter_render.py`

**참고:** Spec §7.2. **첫 작업 = dummy xlsx 의 정확한 컬럼 인덱스를 openpyxl 로 확인**.

- [ ] **Step 1: 4 시트 헤더 컬럼 인덱스 추출**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/python3 - <<'PY'
from openpyxl import load_workbook
wb = load_workbook("/Users/kyungseoplee/Project Agent/CPIA/docs/sample/통합작업일보_DUMMY_20250926.xlsx")
for s in wb.sheetnames:
    ws = wb[s]
    print(f"\n=== {s} ===")
    # r3 + r4 + r5 헤더 합쳐 확인
    for r in (3, 4, 5):
        cells = [(c, ws.cell(r, c).value) for c in range(1, ws.max_column + 1)
                 if ws.cell(r, c).value is not None]
        if cells:
            print(f"r{r}:", cells)
PY
```

이 출력으로 `COL_OUTPUT_MANPOWER` / `COL_OCCUPATION` / `COL_EQUIPMENT` / `COL_QUANTITY` 4 dict 값 결정.

- [ ] **Step 2: render_xlsx 단위 테스트 작성**

`pipeline/tests/test_exporter_render.py`:

```python
"""render_xlsx 단위 — 가짜 SheetData → openpyxl bytes 재 load → cell 검증.

Spec: §7.2, §8.1. LLM 0. PG 0.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook

from pipeline.agents.exporter import SheetData, render_xlsx


@pytest.fixture
def fake_data() -> SheetData:
    return SheetData(
        output_manpower=[
            {
                "zone": "FAB", "disc_abbrev": "TE", "bp_code": "PH_X-003",
                "company": "아스타", "scope": "PJT",
                "work_text_yesterday": "전일", "work_text_today": "금일",
                "work_text_tomorrow": "명일",
                "workers_yesterday_incr": {"morning": 0, "daytime": 1, "overtime": 0,
                                            "night": 0, "all_night": 0, "total": 1},
                "workers_yesterday_cum": {"morning": 0, "daytime": 2, "overtime": 0,
                                          "night": 0, "all_night": 0, "total": 2},
                "workers_today_incr": {"morning": 0, "daytime": 3, "overtime": 0,
                                        "night": 0, "all_night": 0, "total": 3},
                "workers_today_cum": {"morning": 0, "daytime": 4, "overtime": 0,
                                      "night": 0, "all_night": 0, "total": 4},
            }
        ],
        occupation_manpower=[
            {"disc_abbrev": "TE", "bp_code": "PH_X-002", "job_type": "BP소장",
             "manager_code": "Mm01", "worker_code": "sk01", "workers_cum_t": 35},
        ],
        equipment=[
            {"disc_abbrev": "공통가설", "bp_code": "PH_X-002",
             "equipment_big": "굴삭운반", "equipment_mid": "Back Hoe",
             "equipment_spec": "2㎥ 미만", "count_cum_t": 0},
        ],
        quantity=[
            {"zone": "FAB", "trade": "TE", "bp_code": "PH_X-003", "company": "아스타",
             "scope": None, "work_content": "M15 환경유지", "unit": "인",
             "plan_total_qty": 100, "yesterday_cum_qty": 5, "today_qty": 3},
        ],
    )


def test_render_xlsx_returns_bytes(fake_data: SheetData) -> None:
    out = render_xlsx(fake_data, date(2025, 9, 26), project="M15X")
    assert isinstance(out, bytes)
    assert len(out) > 1000  # 빈 xlsx 도 4KB 정도라 1KB 이상이면 정상


def test_render_xlsx_sheets_present(fake_data: SheetData) -> None:
    out = render_xlsx(fake_data, date(2025, 9, 26), project="M15X")
    wb = load_workbook(BytesIO(out))
    assert wb.sheetnames == ["1.출력인원 현황", "2.직종별 인원현황", "3.장비현황", "4.물량"]


def test_render_xlsx_output_manpower_row(fake_data: SheetData) -> None:
    """시트1 r5 에 zone='FAB' 박혀야 함 (COL dict 가 정확한지 검증)."""
    out = render_xlsx(fake_data, date(2025, 9, 26), project="M15X")
    wb = load_workbook(BytesIO(out))
    ws = wb["1.출력인원 현황"]
    # 시트1 zone 컬럼은 r5 부근 어딘가에 'FAB' 가 박혀있어야 함
    found = any(
        ws.cell(5, c).value == "FAB"
        for c in range(1, ws.max_column + 1)
    )
    assert found, f"r5 row 어디에도 'FAB' 없음 — COL dict 확인. 실 r5: {[ws.cell(5, c).value for c in range(1, ws.max_column+1)]}"


def test_render_xlsx_quantity_row(fake_data: SheetData) -> None:
    """시트4 r5 에 work_content 'M15 환경유지' 박혀야 함."""
    out = render_xlsx(fake_data, date(2025, 9, 26), project="M15X")
    wb = load_workbook(BytesIO(out))
    ws = wb["4.물량"]
    found = any(
        ws.cell(5, c).value == "M15 환경유지"
        for c in range(1, ws.max_column + 1)
    )
    assert found


def test_render_xlsx_empty_sheet_keeps_header(fake_data: SheetData) -> None:
    """empty 시트 데이터 (e.g. equipment=[]) 도 헤더만 남아 깨지지 X."""
    fake_data.equipment.clear()
    out = render_xlsx(fake_data, date(2025, 9, 26), project="M15X")
    wb = load_workbook(BytesIO(out))
    ws = wb["3.장비현황"]
    # 헤더 행 (r1~r4) 살아있는지
    assert ws["B1"].value is not None or ws.max_row >= 4
```

- [ ] **Step 3: 테스트 실행해 fail 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/python3 -m pytest tests/test_exporter_render.py -v 2>&1 | head -15
```

기대 출력: `ImportError: cannot import name 'render_xlsx'`.

- [ ] **Step 4: exporter.py 에 render_xlsx + _fill_* 4 함수 추가**

Step 1 의 헤더 추출 결과를 바탕으로 4 시트의 COL dict 채움. `pipeline/agents/exporter.py` 끝에 추가:

```python
# ──────────────────────────────────────────────────────────────────────────────
# Render — Spec §7.2
# ──────────────────────────────────────────────────────────────────────────────

from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

TEMPLATE_PATH = Path(__file__).parent / "exporter_templates" / "consolidated_template.xlsx"
DATA_START_ROW = 5


# ⚠ Step 1 에서 dummy r3+r4 헤더 확인 후 정확한 column 인덱스로 갱신할 것.
# 아래는 dummy xlsx 가 가장 흔히 보이는 패턴 — 첫 실행 시 검증 테스트로 정정.
COL_OUTPUT_MANPOWER = {
    "zone": 3, "trade": 4, "bp_code": 5, "company": 5,  # bp_code/company 같은 col 사용 (BP사 한 칸)
    "scope": 6,
    "work_y": 7, "work_t": 8, "work_n": 9,
    "yest_incr": 10, "yest_cum": 17, "today_incr": 24, "today_cum": 31,
}
COL_OCCUPATION = {
    "trade": 2, "bp_code": 3, "manager_code": 4, "worker_code": 5,
    "job_type": 6, "yest_cum": 7, "today_incr": 13, "today_cum": 19,
}
COL_EQUIPMENT = {
    "trade": 2, "bp_code": 3, "eq_big": 4, "eq_mid": 5, "eq_spec": 6,
    "yest_cum": 7, "today_incr": 13, "today_cum": 19,
}
COL_QUANTITY = {
    "zone": 3, "trade": 4, "bp_code": 5, "company": 6, "scope": 7,
    "rep_work": 8, "unit": 9, "total_a": 10, "prev_cum_b": 11,
    "today_c": 12, "today_cum_d": 13, "f_pct": 14, "remain_e": 15, "g_pct": 16, "note": 17,
}


_WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]


def _korean_weekday(d) -> str:
    return _WEEKDAYS_KO[d.weekday()]


def _fill_timeshift(ws, row: int, col_start: int, ts: dict | None) -> None:
    if not ts:
        return
    for i, key in enumerate(["morning", "daytime", "overtime", "night", "all_night", "total"]):
        ws.cell(row=row, column=col_start + i, value=ts.get(key, 0))


def _fill_output_manpower(ws, rows: list[dict], report_date) -> None:
    ws["B2"].value = f"금일 작업 현황 : {report_date.isoformat()}, {_korean_weekday(report_date)}요일"
    C = COL_OUTPUT_MANPOWER
    for offset, bp in enumerate(rows):
        r = DATA_START_ROW + offset
        ws.cell(row=r, column=C["zone"], value=bp.get("zone"))
        ws.cell(row=r, column=C["trade"], value=bp.get("disc_abbrev"))
        ws.cell(row=r, column=C["bp_code"], value=bp.get("bp_code") or bp.get("company"))
        ws.cell(row=r, column=C["scope"], value=bp.get("scope"))
        ws.cell(row=r, column=C["work_y"], value=bp.get("work_text_yesterday"))
        ws.cell(row=r, column=C["work_t"], value=bp.get("work_text_today"))
        ws.cell(row=r, column=C["work_n"], value=bp.get("work_text_tomorrow"))
        _fill_timeshift(ws, r, C["yest_incr"], bp.get("workers_yesterday_incr"))
        _fill_timeshift(ws, r, C["yest_cum"], bp.get("workers_yesterday_cum"))
        _fill_timeshift(ws, r, C["today_incr"], bp.get("workers_today_incr"))
        _fill_timeshift(ws, r, C["today_cum"], bp.get("workers_today_cum"))


def _fill_occupation(ws, rows: list[dict], report_date) -> None:
    ws["B2"].value = f"금일 작업 현황 : {report_date.isoformat()}, {_korean_weekday(report_date)}요일"
    C = COL_OCCUPATION
    for offset, j in enumerate(rows):
        r = DATA_START_ROW + offset
        ws.cell(row=r, column=C["trade"], value=j.get("disc_abbrev"))
        ws.cell(row=r, column=C["bp_code"], value=j.get("bp_code") or j.get("company"))
        ws.cell(row=r, column=C["manager_code"], value=j.get("manager_code"))
        ws.cell(row=r, column=C["worker_code"], value=j.get("worker_code"))
        ws.cell(row=r, column=C["job_type"], value=j.get("job_type"))
        _fill_timeshift(ws, r, C["yest_cum"], j.get("workers_yesterday_cum"))
        _fill_timeshift(ws, r, C["today_incr"], j.get("workers_today_incr"))
        _fill_timeshift(ws, r, C["today_cum"], j.get("workers_today_cum"))


def _fill_equipment(ws, rows: list[dict], report_date) -> None:
    ws["B2"].value = f"금일 작업 현황 : {report_date.isoformat()}, {_korean_weekday(report_date)}요일"
    C = COL_EQUIPMENT
    for offset, e in enumerate(rows):
        r = DATA_START_ROW + offset
        ws.cell(row=r, column=C["trade"], value=e.get("disc_abbrev"))
        ws.cell(row=r, column=C["bp_code"], value=e.get("bp_code") or e.get("company"))
        ws.cell(row=r, column=C["eq_big"], value=e.get("equipment_big"))
        ws.cell(row=r, column=C["eq_mid"], value=e.get("equipment_mid"))
        ws.cell(row=r, column=C["eq_spec"], value=e.get("equipment_spec"))
        _fill_timeshift(ws, r, C["yest_cum"], e.get("count_yesterday_cum"))
        _fill_timeshift(ws, r, C["today_incr"], e.get("count_today_incr"))
        _fill_timeshift(ws, r, C["today_cum"], e.get("count_today_cum"))


def _fill_quantity(ws, rows: list[dict], report_date) -> None:
    ws["B2"].value = f"금일 작업 현황 : {report_date.isoformat()}, {_korean_weekday(report_date)}요일"
    C = COL_QUANTITY
    for offset, a in enumerate(rows):
        r = DATA_START_ROW + offset
        ws.cell(row=r, column=C["zone"], value=a.get("zone"))
        ws.cell(row=r, column=C["trade"], value=a.get("trade"))
        ws.cell(row=r, column=C["bp_code"], value=a.get("bp_code"))
        ws.cell(row=r, column=C["company"], value=a.get("company"))
        ws.cell(row=r, column=C["scope"], value=a.get("scope"))
        ws.cell(row=r, column=C["rep_work"], value=a.get("work_content"))
        ws.cell(row=r, column=C["unit"], value=a.get("unit"))
        ws.cell(row=r, column=C["total_a"], value=a.get("plan_total_qty"))
        ws.cell(row=r, column=C["prev_cum_b"], value=a.get("yesterday_cum_qty"))
        ws.cell(row=r, column=C["today_c"], value=a.get("today_qty"))
        # D / F% / E / G% / 비고 — Parser raw 에 있으면 사용
        ws.cell(row=r, column=C["today_cum_d"], value=a.get("today_cum_qty"))
        ws.cell(row=r, column=C["f_pct"], value=a.get("progress_percent"))
        ws.cell(row=r, column=C["remain_e"], value=a.get("remaining_qty"))
        ws.cell(row=r, column=C["g_pct"], value=a.get("remaining_percent"))
        ws.cell(row=r, column=C["note"], value=a.get("note"))


def render_xlsx(sheet_data: SheetData, report_date, project: str) -> bytes:
    """4 시트 fill → xlsx bytes. 템플릿 누락 시 FileNotFoundError."""
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"template not found: {TEMPLATE_PATH}")
    wb = load_workbook(TEMPLATE_PATH)
    _fill_output_manpower(wb["1.출력인원 현황"], sheet_data.output_manpower, report_date)
    _fill_occupation(wb["2.직종별 인원현황"], sheet_data.occupation_manpower, report_date)
    _fill_equipment(wb["3.장비현황"], sheet_data.equipment, report_date)
    _fill_quantity(wb["4.물량"], sheet_data.quantity, report_date)
    buf = BytesIO(); wb.save(buf); return buf.getvalue()
```

- [ ] **Step 5: 테스트 실행 + COL dict 정정**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/python3 -m pytest tests/test_exporter_render.py -v 2>&1 | tail -20
```

테스트가 fail 하면 `test_render_xlsx_output_manpower_row` 의 실 r5 출력을 보고 `COL_OUTPUT_MANPOWER["zone"]` 값을 정정. Step 1 의 헤더 추출 결과와 함께 한 셀씩 확인.

반복: COL dict 수정 → pytest → green. 4 시트 모두 green 까지.

기대 최종 출력: `5 passed`.

- [ ] **Step 6: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/"
git add pipeline/agents/exporter.py pipeline/tests/test_exporter_render.py
git commit -m "feat(exporter): render_xlsx + 4 시트 _fill_* + COL dict"
```

---

## Task 8: FastAPI `/export/run` endpoint (TDD)

**Files:**
- Create: `pipeline/exporter_routes.py`
- Test: `pipeline/tests/test_exporter_endpoint.py` (확장)

**참고:** Spec §7.3.

- [ ] **Step 1: endpoint 테스트 추가**

`pipeline/tests/test_exporter_endpoint.py` 끝에 추가:

```python
# ── /export/run endpoint 통합 ────────────────────────────────────

from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from pipeline.exporter_routes import router as exporter_router


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(exporter_router)
    return app


async def test_export_run_returns_xlsx(app, seeded_run) -> None:
    _run_id, site_id, rdate = seeded_run
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/export/run?site_id={site_id}&date={rdate.isoformat()}")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "통합작업일보" in r.headers["content-disposition"]
    assert len(r.content) > 1000


async def test_export_run_400_bad_date(app) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/export/run?site_id=m15x-ph3-ibl&date=BAD")
    assert r.status_code == 400


async def test_export_run_404_unknown_site(app) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/export/run?site_id=nonexistent-xyz&date=2099-01-01")
    assert r.status_code == 404


async def test_export_run_400_no_data(app) -> None:
    """site 존재하지만 해당 date 데이터 0 — 400."""
    # m15x-ph3-ibl 시드 있어야 함 — 없으면 skip
    pg = PGClient(os.environ["POSTGRES_URL"]); await pg.connect()
    try:
        async with pg._pool.acquire() as con:
            row = await con.fetchrow("SELECT site_id FROM sites WHERE site_id=$1", "m15x-ph3-ibl")
    finally:
        await pg.close()
    if not row:
        pytest.skip("m15x-ph3-ibl 시드 미적용")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/export/run?site_id=m15x-ph3-ibl&date=1900-01-01")
    assert r.status_code == 400
    assert "데이터 없음" in r.json()["detail"]
```

- [ ] **Step 2: 테스트 실행해 fail 확인**

```bash
.venv/bin/python3 -m pytest tests/test_exporter_endpoint.py -v -k "export_run" 2>&1 | head -15
```

기대 출력: `ModuleNotFoundError: No module named 'pipeline.exporter_routes'`.

- [ ] **Step 3: exporter_routes.py 작성**

`pipeline/exporter_routes.py`:

```python
"""FastAPI /export/run endpoint — Spec §7.3."""

from __future__ import annotations

import os
from datetime import date as _date

from fastapi import APIRouter, HTTPException, Response

from pipeline.agents.exporter import NoDataError, fetch_sheet_data, render_xlsx
from pipeline.db import PGClient, fetch_site_by_id

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/run")
async def export_consolidated(site_id: str, date: str) -> Response:
    try:
        report_date = _date.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")

    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        site = await fetch_site_by_id(pg, site_id)
        if not site:
            raise HTTPException(404, f"site_id={site_id} 없음")
        try:
            data = await fetch_sheet_data(pg, site_id, report_date)
        except NoDataError as e:
            raise HTTPException(400, str(e))
    finally:
        await pg.close()

    xlsx_bytes = render_xlsx(data, report_date, project=site.get("name") or "CPIA")
    filename = f"통합작업일보_{date}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: httpx 의존성 확인 + 테스트 pass**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/python3 -c "import httpx; print(httpx.__version__)"
# 없으면: .venv/bin/pip install "httpx>=0.27"
POSTGRES_URL="$(grep '^POSTGRES_URL=' ../.env | cut -d= -f2-)" \
  .venv/bin/python3 -m pytest tests/test_exporter_endpoint.py -v 2>&1 | tail -20
```

기대 출력: `7 passed` (또는 `6 passed 1 skipped`).

- [ ] **Step 5: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/"
git add pipeline/exporter_routes.py pipeline/tests/test_exporter_endpoint.py
git commit -m "feat(exporter): /export/run FastAPI endpoint + httpx 통합 테스트"
```

---

## Task 9: `pipeline/api.py` 의 기존 `lifespan` 확장 + `include_router`

**Files:**
- Modify: `pipeline/api.py` (기존 `lifespan` 함수 안에 collector task 삽입 + `include_router` 1줄)

**참고:** Spec §4.1, §6.1. 기존 endpoint 한 줄도 안 건드림.

**⚠ 중요 (reviewer fix)**: `pipeline/api.py:142~178` 는 이미 `@asynccontextmanager async def lifespan(app)` + `app = FastAPI(..., lifespan=lifespan)` 패턴을 쓰고 있다. FastAPI 의 `@app.on_event("startup")` 와 `lifespan=` 은 **mutually exclusive** — 둘 다 쓰면 `on_event` 핸들러는 무시되고 IDLE 루프가 안 뜬다. 따라서 기존 `lifespan()` 함수 안에 collector task 를 끼워넣는다.

또한 GraphConfig 빌더의 실 함수명은 `_build_prod_graph_config()` (`pipeline/api.py:63`). 이를 그대로 재사용.

- [ ] **Step 1: api.py 현 구조 확인**

```bash
grep -n "^app = \|^def \|^async def \|^@asynccontextmanager\|lifespan\|include_router\|_build_prod_graph_config" "/Users/kyungseoplee/Project Agent/CPIA/pipeline/api.py" | head -15
```

기대: `_build_prod_graph_config` (line ~63), `async def lifespan` (~142), `app = FastAPI(..., lifespan=lifespan)` (~178).

- [ ] **Step 2: import 추가**

`pipeline/api.py` 상단의 import 블록 끝에 추가:

```python
import asyncio  # 이미 있으면 skip
from pipeline.collector.config import load_collector_config
from pipeline.collector.idle_worker import idle_loop, request_shutdown
from pipeline.exporter_routes import router as exporter_router
```

- [ ] **Step 3: 기존 `lifespan()` 확장 — collector task spawn**

`pipeline/api.py` 의 `async def lifespan(app)` 함수 안, `app.state.cfg = cfg` 다음 줄에 추가하고, `try/finally` 블록의 finally 도 갱신:

기존 (참고):
```python
    cfg = _build_prod_graph_config()
    graph = build_graph(cfg)
    app.state.graph = graph
    app.state.cfg = cfg

    try:
        yield
    finally:
        await pg.close()
```

변경 후:
```python
    cfg = _build_prod_graph_config()
    graph = build_graph(cfg)
    app.state.graph = graph
    app.state.cfg = cfg

    # ── Collector (IMAP IDLE) ─────────────────────────────────────
    # Spec §6.1. COLLECTOR_ENABLED=false 면 task 안 띄움.
    # Spec §10 결정: collector_cfg 로드 실패는 fail-fast (try/except 로 swallow X).
    # - POSTGRES_URL 누락 → KeyError 그대로 전파 (앱 자체 부팅 불가)
    # - COLLECTOR_ENABLED=true + USER/PW 누락 → load_collector_config 가 RuntimeError 던짐 (의도된 startup fail)
    # - COLLECTOR_ENABLED=false (default) → 자격증명 누락 허용, 단순히 collector_task 미생성
    collector_cfg = load_collector_config(graph_cfg=cfg)
    collector_task = None
    if collector_cfg.enabled:
        collector_task = asyncio.create_task(idle_loop(collector_cfg))

    try:
        yield
    finally:
        if collector_task is not None:
            request_shutdown()
            collector_task.cancel()
            try:
                await collector_task
            except asyncio.CancelledError:
                pass
        await pg.close()
```

- [ ] **Step 4: `include_router` 추가**

`app = FastAPI(..., lifespan=lifespan)` 정의 직후 1줄:

```python
app.include_router(exporter_router)
```

- [ ] **Step 5: api.py syntax 검증 + 기존 테스트 회귀 없음 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/python3 -c "from pipeline.api import app; print([r.path for r in app.routes if hasattr(r, 'path')][:10])" 2>&1
# /export/run 이 출력 routes 에 보여야 함
POSTGRES_URL="$(grep '^POSTGRES_URL=' ../.env | cut -d= -f2-)" \
  COLLECTOR_ENABLED=false \
  .venv/bin/python3 -m pytest tests/test_api_smoke.py -v 2>&1 | tail -10
```

기대 출력: routes 에 `/export/run` 포함 + 기존 smoke 테스트 회귀 0.

- [ ] **Step 6: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/"
git add pipeline/api.py
git commit -m "feat(api): lifespan 안에 collector task + exporter router include"
```

---

## Task 10: 환경 변수 + Gmail 데모 계정 setup 문서

**Files:**
- Modify: `pipeline/.env.example`
- Create: `docs/collector-gmail-setup.md`

- [ ] **Step 1: .env.example 갱신**

`pipeline/.env.example` 끝에 추가:

```bash

# ── Collector (Gmail IMAP IDLE) ─────────────────────────────────
# Spec §10 결정 (env-only fail-fast): USER / APP_PASSWORD 는 .env.local 에서만 주입.
# .env.example 은 공개 git 추적 — 실 값 박지 말 것 (placeholder 만).
COLLECTOR_ENABLED=false                       # 운영/데모 시 true, 로컬/테스트는 false
COLLECTOR_IMAP_HOST=imap.gmail.com            # 다른 IMAP 서버 (사내 등) 로 swap 가능
COLLECTOR_IMAP_PORT=993
COLLECTOR_IMAP_USER=                          # .env.local 에서 채울 것 (예: <ops>@gmail.com)
COLLECTOR_IMAP_APP_PASSWORD=                  # .env.local 에서 채울 것 (16자 Gmail App Password)
COLLECTOR_DEFAULT_SITE_ID=m15x-ph3-ibl
COLLECTOR_INPUT_DIR=data/input
COLLECTOR_DEAD_LETTER_DIR=data/input/dead_letter
CPIA_COLLECTOR_CONCURRENCY=2

# ── Exporter ────────────────────────────────────────────────────
EXPORTER_TEMPLATE_PATH=pipeline/agents/exporter_templates/consolidated_template.xlsx
```

- [ ] **Step 2: Gmail setup 문서 작성**

`docs/collector-gmail-setup.md`:

```markdown
# CPIA Collector — Gmail 계정 설정

> Spec §8.2 의 Gmail 계정 발급 + IMAP IDLE 활성화 절차.
> Spec §10 결정 (env-only): 계정 주소 / App Password 는 `pipeline/.env.local` 에만 박는다 — 본 문서 / spec / plan / `.env.example` 어디에도 박지 않음.

## 1. Gmail 계정 준비

- 기존 데모 계정이 있으면 그대로 재사용. 없으면 임의 주소로 신규 가입 (예: `cpia-collector@gmail.com`, `poc-cpia-mail@gmail.com` 등 — 자유 변경).
- 본 계정은 PoC / 운영 데모 전용. 회사 메일 권한 / 정책 분리.

## 2. 2단계 인증 (2FA) 활성화

Google Account → Security → 2-Step Verification → 활성화.
App Password 발급 전제.

## 3. App Password 발급

Google Account → Security → 2-Step Verification → App passwords
→ "App name" 에 `CPIA Collector` 입력 → Create → 16자 password 생성 (`xxxx xxxx xxxx xxxx` 형태).
이 password 가 `COLLECTOR_IMAP_APP_PASSWORD` 환경 변수 값. 페이지 닫으면 다시 못 봄 — 즉시 안전한 곳에 복사.

## 4. IMAP 활성화

Gmail 설정 (톱니바퀴) → 전달 및 POP/IMAP → "IMAP 사용" 라디오 선택.

## 5. `pipeline/.env.local` 박기

```bash
COLLECTOR_ENABLED=true
COLLECTOR_IMAP_USER=<발급한 Gmail 주소>
COLLECTOR_IMAP_APP_PASSWORD=<3 단계에서 받은 16자, 공백 유무 무관>
```

`.env.local` 은 `.gitignore` 처리됨 (확인: `git check-ignore pipeline/.env.local` → 경로가 출력되면 OK).

## 6. 동작 확인 (smoke)

`pipeline/scripts/smoke_collector_imap.py` (bootstrap plan 산출) 실행:

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python pipeline/scripts/smoke_collector_imap.py
```

기대 출력:
```
connect imap.gmail.com:993 as <발급한 주소> ...
LOGIN: OK <발급한 주소> authenticated (Success)
SELECT INBOX: typ=OK, count=<수신함 메일 수>
```

실패 시 bootstrap plan (`2026-05-21-cpia-collector-env-bootstrap.md`) Task 4 Step 4 의 분류표 참고.

## 7. 데모 시나리오

1. PM 시뮬: 임의 발신 계정에서 `$COLLECTOR_IMAP_USER` (=.env.local 에 박은 주소) 로 첨부 보냄 (파일명 규약 따름)
2. Dashboard 의 `/tasks` 또는 `/dashboard` 페이지에서 새 run 진입 확인
3. `/export` 페이지에서 일자 선택 → "Export 엑셀" 클릭 → 다운로드

## 8. 계정 교체

다른 Gmail 계정 / 다른 IMAP 서버 (사내 메일 등) 로의 swap:
1. 새 계정에서 위 2~4 단계 반복
2. `pipeline/.env.local` 의 `COLLECTOR_IMAP_USER` / `COLLECTOR_IMAP_APP_PASSWORD` (필요 시 `COLLECTOR_IMAP_HOST` / `COLLECTOR_IMAP_PORT`) 수정
3. FastAPI 재기동
4. smoke 재실행 — 코드 / 재빌드 변경 0
```

- [ ] **Step 3: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/"
git add pipeline/.env.example docs/collector-gmail-setup.md
git commit -m "docs(collector): Gmail 데모 계정 setup 문서 + .env.example 확장"
```

---

## Task 11: B_Track UI swap 협업 문서

**Files:**
- Create: `docs/collector-exporter-ui-swap.md`

**참고:** Spec §7.4. B_Track 1줄 변경 가이드.

- [ ] **Step 1: swap 문서 작성**

`docs/collector-exporter-ui-swap.md`:

```markdown
# B_Track UI Swap — `ConsolidatedReportCard.tsx`

> Exporter FastAPI endpoint 준비 완료 (`GET /export/run?site_id&date`).
> B_Track 이 fallback (docs/sample 다운로드) 를 실 endpoint 호출로 교체.

## 변경 위치

`web/app/components/export/ConsolidatedReportCard.tsx:38~59` 의 `handleExport`.

## 변경 전 (현재 — fallback)

```typescript
const handleExport = async () => {
  if (busy) return;
  setBusy(true);
  const id = toast.loading(`Exporter 에이전트 작동 중…`);
  try {
    await new Promise((r) => setTimeout(r, 1500));
    const a = document.createElement("a");
    a.href = "/sample/cpia-consolidated-report.xlsx";
    a.download = `통합작업일보_${report.date}.xlsx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    toast.success(`통합 작업일보 다운로드 완료`);
  } catch {
    toast.error("Exporter 실행에 실패했습니다.");
  } finally {
    setBusy(false);
  }
};
```

## 변경 후 (실 endpoint)

`NEXT_PUBLIC_FASTAPI_BASE` env 추가 (예: `http://localhost:8000`).

```typescript
const handleExport = async () => {
  if (busy) return;
  setBusy(true);
  const id = toast.loading(`Exporter 에이전트 작동 중…`);
  try {
    const siteId = process.env.NEXT_PUBLIC_DEFAULT_SITE_ID || "m15x-ph3-ibl";
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_FASTAPI_BASE}/export/run?site_id=${siteId}&date=${report.date}`,
    );
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `통합작업일보_${report.date}.xlsx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success(`통합 작업일보 다운로드 완료`, { id });
  } catch (e) {
    toast.error(`Exporter 실행 실패: ${(e as Error).message}`, { id });
  } finally {
    setBusy(false);
  }
};
```

## .env.local.example 추가

```bash
NEXT_PUBLIC_FASTAPI_BASE=http://localhost:8000
NEXT_PUBLIC_DEFAULT_SITE_ID=m15x-ph3-ibl
```

## BFF proxy 대안 (CORS / 인증 통일에 유리)

`web/app/api/export/[date]/route.ts` 신규 — Next.js BFF 가 FastAPI fetch 후 stream pipe. PoC 에선 직접 fetch 도 충분.
```

- [ ] **Step 2: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/"
git add docs/collector-exporter-ui-swap.md
git commit -m "docs(exporter): B_Track UI swap 가이드 (NEXT_PUBLIC_FASTAPI_BASE 추가)"
```

---

## Task 12: E2E 데모 시나리오 검증

**Files:**
- (검증만, 파일 변경 없음)

- [ ] **Step 0: prerequisite — `sites.m15x-ph3-ibl` 시드 확인**

```bash
PGPASSWORD="$(grep '^POSTGRES_URL=' "/Users/kyungseoplee/Project Agent/CPIA/.env" | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|')" \
  psql -h cpia-pg.zoai.uk -p 5532 -U cpia -d cpia \
  -c "SELECT site_id, name FROM sites WHERE site_id='m15x-ph3-ibl';"
```

row 0 이면 `data/mock_sites.json` 시드 또는 다음 SQL 로 수동 INSERT:

```sql
INSERT INTO sites (site_id, name, is_mock) VALUES ('m15x-ph3-ibl', 'M15X Ph-3 IBL', true)
  ON CONFLICT (site_id) DO NOTHING;
```

- [ ] **Step 1: 데모 환경 변수 활성화**

`pipeline/.env.local` 에 (없으면 생성):

```bash
COLLECTOR_ENABLED=true
COLLECTOR_IMAP_USER=<실 Gmail 주소>
COLLECTOR_IMAP_APP_PASSWORD=<16자>
```

- [ ] **Step 2: FastAPI 기동**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
.venv/bin/python3 -m uvicorn pipeline.api:app --reload --port 8000 2>&1 | tee /tmp/cpia-api.log &
sleep 5
grep "idle_start\|idle_loop\|connector\|login" /tmp/cpia-api.log | head -5
```

기대: log 에 IDLE login 성공 + IDLE 진입 메시지.

- [ ] **Step 3: 테스트 메일 보내기 (PM 시뮬)**

별 Gmail 계정 또는 같은 계정에서 자기 자신에게:
- To: `$COLLECTOR_IMAP_USER` 값 (`pipeline/.env.local` 에 박은 주소). `echo $COLLECTOR_IMAP_USER` 로 확인 가능.
- 첨부: `docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx`

- [ ] **Step 4: collector_inbox PG row 확인**

```bash
PGPASSWORD=... psql -h cpia-pg.zoai.uk -p 5532 -U cpia -d cpia -c "
  SELECT message_id, parse_status, error, received_at
  FROM collector_inbox
  ORDER BY received_at DESC
  LIMIT 5;
"
```

기대: 최신 row 1 개 `parse_status='completed'`.

- [ ] **Step 5: Export 다운로드**

```bash
curl -s "http://localhost:8000/export/run?site_id=m15x-ph3-ibl&date=2025-09-25" \
  -o /tmp/test-consolidated.xlsx
ls -la /tmp/test-consolidated.xlsx
.venv/bin/python3 -c "
from openpyxl import load_workbook
wb = load_workbook('/tmp/test-consolidated.xlsx')
for s in wb.sheetnames:
    ws = wb[s]
    print(f'{s}: {ws.max_row} rows')
"
```

기대: 4 시트 모두 r5 이상 데이터.

- [ ] **Step 6: dead_letter 케이스 검증**

자기 자신에게 첨부 파일명을 `garbage.xlsx` 같이 미일치 형태로 보냄. 30초 대기.

```bash
ls "/Users/kyungseoplee/Project Agent/CPIA/data/input/dead_letter/" | head -3
```

기대: `garbage_*.xlsx` 파일 1개.

- [ ] **Step 7: 결과 보고서 작성**

`docs/collector-exporter-e2e-report-YYYY-MM-DD.md` 신규 작성:
- 메일 전송 시각 / collector_inbox row 시각 / parse 완료 시각 (latency 측정)
- Export 다운로드 xlsx 의 시트 row 수
- dead_letter 케이스 동작 여부

커밋:

```bash
git add docs/collector-exporter-e2e-report-*.md
git commit -m "docs(collector): E2E 검증 보고서 (PoC 데모 리허설)"
```

---

## 일정

| 주차 | Task |
|---|---|
| W1 (5/19~5/25) | Task 0 ~ 4 (env, filename_parser, migration, db helper, idle_worker, mock 테스트) |
| W2 (5/26~6/1) | Task 5 ~ 10 (template, fetch, render, endpoint, api wiring, env docs) |
| W3 (6/2~6/5) | Task 11, 12 (B_Track 협업, E2E 리허설) |

---

## Open issues

- **Gmail 계정 발급 시점**: Task 0 시작 전 사용자가 미리 발급해두면 W1 안에 IDLE 실 연결 가능.
- **`_get_graph_cfg()` 실 함수명**: Task 9 Step 3 에서 api.py 의 기존 GraphConfig 빌더 정확한 이름 확인 필요.
- **dummy xlsx COL dict 정확값**: Task 7 Step 1 의 헤더 추출 출력으로 한 셀씩 확정.
- **`pipeline_runs.site_id` 시드**: m15x-ph3-ibl 의 mock 운영 데이터가 PG 에 있어야 E2E 검증 가능. 없으면 Task 12 전에 수동 INSERT.

---

## Next step

1. plan-document-reviewer subagent 디스패치 → 이슈 반영 (max 3 iter)
2. 사용자 plan 리뷰 게이트
3. `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans` 로 실 실행
