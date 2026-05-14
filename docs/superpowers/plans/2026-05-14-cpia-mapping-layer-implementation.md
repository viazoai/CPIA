# CPIA 매핑 레이어 구현 Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `docs/schema/mapping-layer.md` 의 매핑 레이어 — Parser 통합 스키마 + Mapper 6단계 (BP filter → 임베딩 → LLM rerank) + WA 결정 4단계 — 를 동작하는 코드로 구현하고 골든 79건 시뮬 회귀 테스트로 검증.

**Architecture:** Activity TypedDict 중심의 LangGraph node 패턴. Mapper 가 PG `activity_master` (BP filter) + Chroma `wbs_master` (임베딩 Top-K) + Azure OpenAI (LLM rerank) 3 컴포넌트를 협력 호출. 임베딩 input 은 작업line 자체만 (단순), LLM input 은 4시트 BP사 컨텍스트 (풍부) — 두 input 분리로 숫자 오염 방지.

**Tech Stack:** Python 3.11+, LangGraph + LangChain, Azure OpenAI (`gpt-5.1-chat-ai-board-test` + `text-embedding-3-small-ai-board-test` 1536d), PostgreSQL 16+ (asyncpg), ChromaDB (server mode, homelab Docker), uv 패키지 매니저, pytest.

**Spec:** `docs/schema/mapping-layer.md` + `docs/schema/state.md` + `docs/schema/postgres.md`

**마일스톤:** GATE 1 (2026-05-19) — Phase 0 합의 완료 + 7 에이전트 stub E2E. 이 plan 의 Task 1~9 까지가 GATE 1 의 매핑 레이어 부분.

---

## File Structure

```
pipeline/                            # A 트랙 (단독)
├── __init__.py                       (Task 0)
├── state.py                          (Task 1) — Activity, CPIAState, ParsedDailyReport TypedDict
├── db.py                             (Task 2) — asyncpg + activity_master 쿼리
├── chroma_client.py                  (Task 3) — Chroma server 연결 + wbs_master + daily_activities
├── agents/
│   ├── __init__.py                   (Task 0)
│   └── mapper.py                     (Task 7, 8) — Mapper 6단계 + WA 4단계
├── tests/
│   ├── conftest.py                   (Task 0) — 공용 fixture
│   ├── test_state.py                 (Task 1)
│   ├── test_db.py                    (Task 2)
│   ├── test_chroma_client.py         (Task 3)
│   ├── test_load_master.py           (Task 5)
│   ├── test_mapper_helpers.py        (Task 7) — build_embedding_input / build_llm_input / resolve_wa
│   ├── test_mapper_node.py           (Task 8) — mapper_node 통합
│   └── test_mapper_golden.py         (Task 9) — 79건 회귀
└── pyproject.toml                    (Task 0)

scripts/
├── load_master_list.py               (Task 4) — Master xlsx → PG + Chroma 동시 적재
└── migrate_to_homelab.sh             (Task 10) — 로컬 → homelab 마이그레이션 자동화

infra/local/                          (Task 0.5) — 로컬 우선 인프라
├── docker-compose.local.yml          PG + Chroma 컨테이너 정의
└── postgres-init.sql                 activity_master 테이블만 생성 (B 트랙 init.sql 의 부분)

.env.local                            (Task 0.5) — 로컬 환경 변수 (gitignore)
.env.homelab                          (Task 10) — homelab 환경 변수 (gitignore)
.env  →  symlink to one of above
```

**다른 에이전트 (Collector / Parser / Atomizer / Reporter / Forecaster / Optimizer) stub** 은 이 plan 범위 밖. 별도 plan 으로 GATE 1 까지 작성. Mapper 는 단독 호출 테스트로 검증.

## 인프라 환경 — 로컬 우선 + homelab 마이그레이션

**상황:** homelab Docker (PostgreSQL + ChromaDB) 인프라는 B 트랙에서 조성 진행 중. A 트랙은 B 트랙 완료 대기하지 않고 **로컬 Docker 로 우선 진행**.

**진행 단계:**
1. **Task 0.5 — 로컬 PG + Chroma Docker Compose 기동** (A 트랙 단독 작업)
2. **Task 1~9 — 로컬 환경 기반 Mapper 구현 + 골든 79건 검증**
3. **Task 10 — homelab 인프라 준비 완료 시점 마이그레이션** (PG `pg_dump` + Chroma 컬렉션 export/import)

**`.env` 분리 전략:**
- `.env.local` (로컬): `POSTGRES_URL=postgresql://cpia:cpia@localhost:5432/cpia`, `CHROMA_HOST=localhost`, `CHROMA_PORT=8000`
- `.env.homelab` (B 트랙 머지 후 채움): homelab DSN + Cloudflare Tunnel 경유 endpoint
- 코드는 `.env` 단일 파일 참조. 운영자가 `ln -sf .env.local .env` 또는 `.env.homelab` 로 전환.
- 기존 Azure OpenAI / LLM_MODEL 등은 둘 다 동일 (양쪽 .env 에 복붙).

**로컬 init.sql 정책:** `infra/local/postgres-init.sql` 은 mapping-layer 에 필요한 `activity_master` 테이블만 우선 생성. B 트랙의 정식 `infra/postgres/init.sql` (8 테이블 전체) 가 머지되면 Task 10 에서 그 스키마로 마이그레이션. **컬럼 정의는 `docs/schema/postgres.md §2` 그대로 따라 작성** — 호환성 확보.

---

## Task 0: Scaffold — pipeline 폴더 + uv 환경 + pytest 셋업

**Files:**
- Create: `pipeline/__init__.py`
- Create: `pipeline/agents/__init__.py`
- Create: `pipeline/tests/conftest.py`
- Modify: `pipeline/pyproject.toml`

- [ ] **Step 1: pipeline/__init__.py 빈 파일 생성**

```python
"""CPIA pipeline package."""
from __future__ import annotations
```

- [ ] **Step 2: pipeline/agents/__init__.py 동일하게**

```python
"""LangGraph agents."""
from __future__ import annotations
```

- [ ] **Step 3: pyproject.toml 작성**

```toml
[project]
name = "cpia-pipeline"
version = "0.1.0"
description = "CPIA — Construction Productivity Intelligence Agent pipeline"
requires-python = ">=3.11"
dependencies = [
    "langgraph>=0.2.0",
    "langchain>=0.3.0",
    "langchain-openai>=0.2.0",
    "openai>=1.50.0",
    "asyncpg>=0.30.0",
    "chromadb>=0.5.0",
    "openpyxl>=3.1.0",
    "python-dotenv>=1.0.0",
    "numpy>=1.26.0",
    "pydantic>=2.9.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.6.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]
testpaths = ["pipeline/tests"]

[tool.ruff]
line-length = 110
target-version = "py311"
```

- [ ] **Step 4: pipeline/tests/conftest.py 작성 (공용 fixture)**

```python
"""공용 pytest fixtures — DB·Chroma 연결, Master List 로드."""
from __future__ import annotations
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

CPIA_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(CPIA_ROOT / ".env")


@pytest.fixture(scope="session")
def cpia_root() -> Path:
    return CPIA_ROOT


@pytest.fixture(scope="session")
def sample_wbs_path(cpia_root) -> Path:
    return cpia_root / "docs/sample/WBS공정표_M15X IBL PH-3_CPRS_2025.09.25.xlsx"


@pytest.fixture(scope="session")
def sample_tong_path(cpia_root) -> Path:
    return cpia_root / "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"


@pytest.fixture(scope="session")
def azure_openai_env() -> dict[str, str]:
    """Azure OpenAI 환경 변수. 누락 시 테스트 skip."""
    keys = ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_API_VERSION", "LLM_MODEL", "EMBEDDING_MODEL"]
    env = {k: os.environ.get(k, "") for k in keys}
    if not all(env.values()):
        pytest.skip(f"Azure OpenAI env 누락: {[k for k, v in env.items() if not v]}")
    return env
```

- [ ] **Step 5: uv sync 환경 구성 + pytest 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
cd pipeline
uv sync
uv run pytest --collect-only
```

Expected: `collected 0 items` (테스트 없음, 환경 OK).

- [ ] **Step 6: Commit**

```bash
git add pipeline/__init__.py pipeline/agents/__init__.py pipeline/tests/conftest.py pipeline/pyproject.toml
git commit -m "scaffold: pipeline 패키지 + uv + pytest 셋업"
```

---

## Task 0.5: 로컬 PostgreSQL + ChromaDB Docker Compose 기동

**Files:**
- Create: `infra/local/docker-compose.local.yml`
- Create: `infra/local/postgres-init.sql`
- Create: `.env.local`
- Modify: `.gitignore` (`.env.local` 추가 — secret 보호)

**의도:** B 트랙 homelab 인프라 대기 안 함. 로컬에서 1분 안에 PG + Chroma 기동, Task 1~9 모두 로컬로 실행. Task 10 에서 homelab 으로 이관.

- [ ] **Step 1: infra/local/docker-compose.local.yml 작성**

```yaml
version: '3.9'

services:
  postgres:
    image: postgres:16
    container_name: cpia-pg-local
    environment:
      POSTGRES_USER: cpia
      POSTGRES_PASSWORD: cpia
      POSTGRES_DB: cpia
    ports:
      - "5432:5432"
    volumes:
      - cpia-pg-data:/var/lib/postgresql/data
      - ./postgres-init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cpia"]
      interval: 5s
      timeout: 5s
      retries: 10

  chroma:
    image: chromadb/chroma:0.5.20
    container_name: cpia-chroma-local
    ports:
      - "8000:8000"
    volumes:
      - cpia-chroma-data:/chroma/chroma
    environment:
      IS_PERSISTENT: TRUE
      ANONYMIZED_TELEMETRY: FALSE

volumes:
  cpia-pg-data:
  cpia-chroma-data:
```

- [ ] **Step 2: infra/local/postgres-init.sql 작성 — `activity_master` 우선만**

> **주의:** `docs/schema/postgres.md §2` 의 컬럼 정의를 정확히 따른다. B 트랙의 정식 init.sql 머지 시 Task 10 의 마이그레이션이 schema diff 없이 진행되도록.

```sql
-- 로컬 우선 PoC 스키마 — Task 10 마이그레이션 시 B 트랙 init.sql 로 교체.
-- 컬럼 정의는 docs/schema/postgres.md §2 그대로.

CREATE TABLE IF NOT EXISTS activity_master (
    wbs_activity_id   TEXT PRIMARY KEY,
    wa                TEXT,                              -- 'CUB' / 'FAB' (Master C4)
    l5_disc           TEXT NOT NULL,
    l6_main           TEXT,
    l6_code           TEXT,
    l7_sub            TEXT,
    l7_code           TEXT,
    l7_5_activity     TEXT,
    sub_work_area     TEXT,
    company           TEXT,
    unit              TEXT,
    plan_total_qty    NUMERIC,
    plan_mh_rev2      NUMERIC,
    plan_mh_rev1      NUMERIC,
    plan_mh_rev0      NUMERIC,
    plan_wv           NUMERIC,
    plan_start        DATE,
    plan_finish       DATE,
    actual_start      DATE,
    actual_finish     DATE,
    source_file       TEXT,
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_actmaster_lookup ON activity_master (l5_disc, company, unit);
CREATE INDEX IF NOT EXISTS idx_actmaster_wa_l6 ON activity_master (wa, l6_main);
CREATE INDEX IF NOT EXISTS idx_actmaster_period ON activity_master (plan_start, plan_finish);
```

- [ ] **Step 3: .env.local 작성 + .gitignore 에 추가**

```bash
# .env.local — 로컬 Docker 기준
# 운영자가 'ln -sf .env.local .env' 로 활성화

# Azure OpenAI (homelab 과 동일)
AZURE_OPENAI_ENDPOINT=https://skep-ai-board-for-test-foundry.cognitiveservices.azure.com/
AZURE_OPENAI_API_KEY=<기존 .env 값>
AZURE_OPENAI_API_VERSION=2024-12-01-preview
LLM_MODEL=gpt-5.1-chat-ai-board-test
EMBEDDING_MODEL=text-embedding-3-small-ai-board-test
EMBEDDING_DIM=1536

# 로컬 인프라
POSTGRES_URL=postgresql://cpia:cpia@localhost:5432/cpia
CHROMA_HOST=localhost
CHROMA_PORT=8000
```

```bash
# .gitignore 에 추가
echo "" >> .gitignore
echo "# Secret env files" >> .gitignore
echo ".env.local" >> .gitignore
echo ".env.homelab" >> .gitignore
```

- [ ] **Step 4: Docker Compose 기동 + 헬스체크**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/infra/local"
docker compose -f docker-compose.local.yml up -d

# PG 헬스체크
docker compose -f docker-compose.local.yml ps
# Expected: postgres healthy, chroma running

# PG 접속 테스트
psql postgresql://cpia:cpia@localhost:5432/cpia -c "\d activity_master"
# Expected: activity_master 테이블 + 인덱스 출력

# Chroma 헬스체크
curl http://localhost:8000/api/v1/heartbeat
# Expected: {"nanosecond heartbeat": ...}
```

- [ ] **Step 5: .env symlink — 로컬 활성화**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
# 기존 .env 가 있으면 백업
[ -f .env ] && mv .env .env.backup-$(date +%Y%m%d)
ln -sf .env.local .env
ls -la .env  # symlink 확인
```

- [ ] **Step 6: Commit**

```bash
git add infra/local/docker-compose.local.yml infra/local/postgres-init.sql .gitignore
# .env.local 은 gitignore 처리, 커밋 X
git commit -m "infra(local): PoC 로컬 Docker — PostgreSQL + ChromaDB + activity_master schema"
```

---

## Task 1: pipeline/state.py — Activity + CPIAState + ParsedDailyReport TypedDict

**Files:**
- Modify: `pipeline/state.py` (현재 빈 파일)
- Create: `pipeline/tests/test_state.py`

**Spec 참조:** `docs/schema/state.md §1, §2` + `docs/schema/mapping-layer.md §2` (ParsedDailyReport)

- [ ] **Step 1: tests/test_state.py 작성 — TypedDict instantiate 검증**

```python
from __future__ import annotations
from pipeline.state import (
    Activity, BPSummary, JobAllocation, EquipmentAllocation,
    ParsedDailyReport, CPIAState,
)


def test_activity_instantiate():
    a: Activity = {
        "wbs_activity_id": None, "l5_disc": "건축",
        "l6_main": None, "l7_sub": None, "l7_5_activity": None,
        "sub_work_area": None, "trade": "건축", "company": "남웅건설",
        "unit": "M2", "today_qty": 320.0, "work_content": "기초 거푸집 설치",
        "conditions": [], "assigned_workers": 81.0, "worker_source": "parsed",
        "plan_total_qty": None, "plan_mh": None,
        "requires_review": False, "wa": None,
        "mapping_conf": None, "mapping_source": None,
    }
    assert a["trade"] == "건축"
    assert a["assigned_workers"] == 81.0


def test_parsed_daily_report_instantiate():
    r: ParsedDailyReport = {
        "report_date": "20250925", "project": "M15X PH-3 IBL",
        "bp_summaries": [], "job_allocations": [],
        "equipment_allocations": [], "activities": [],
    }
    assert r["report_date"] == "20250925"


def test_cpia_state_instantiate():
    s: CPIAState = {
        "run_id": "00000000-0000-0000-0000-000000000000",
        "date": "20250925", "input_files": [],
        "raw_texts": {}, "parsed": [], "mapped": [],
        "hil_1_corrections": {}, "atomized_ids": [],
        "report_md": "", "forecast": [],
        "hil_2_selection": [], "optimizer_advice": [],
        "current_node": "collector", "status": "running",
    }
    assert s["status"] == "running"
```

- [ ] **Step 2: Run test → FAIL (module empty)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
uv run pytest tests/test_state.py -v
```

Expected: `ImportError: cannot import name 'Activity' from 'pipeline.state'`

- [ ] **Step 3: pipeline/state.py 작성**

```python
"""LangGraph State 스키마 — Agent 간 공유 데이터 계약.

Spec: docs/schema/state.md + docs/schema/mapping-layer.md §2
"""
from __future__ import annotations
from typing import Literal, TypedDict


class Activity(TypedDict):
    """작업일보 1행 = 매핑 단위."""
    # WBS 매핑 (Mapper 이후 채워짐)
    wbs_activity_id: str | None
    l5_disc: str
    l6_main: str | None
    l7_sub: str | None
    l7_5_activity: str | None
    sub_work_area: str | None

    # 작업일보 원천 (Parser 가 채움)
    trade: str
    company: str
    unit: str
    today_qty: float
    work_content: str
    conditions: list[str]

    # MH 비율 분배 (Mapper 이후)
    assigned_workers: float
    worker_source: Literal["parsed", "mh_prorated", "user_corrected"]

    # Master List 조회값
    plan_total_qty: float | None
    plan_mh: float | None

    # 매핑 결과 (Mapper 이후) — mapping-layer.md §3 추가 필드
    wa: str | None                         # 'CUB' / 'FAB' / None (H-i-L 1 대기)
    mapping_conf: float | None             # 0.0~1.0
    mapping_source: str | None             # 'auto_bp_single' / 'auto_l6_single'
                                            # / 'auto_sheet1_text' / 'hil_corrected' / 'hil_required'

    # H-i-L 1 플래그
    requires_review: bool


class BPSummary(TypedDict):
    """시트1 BP사 × 공종 row."""
    bp_code: str | None
    company: str
    disc_abbrev: str | None
    zone: str | None
    scope: str | None
    work_text_yesterday: str | None
    work_text_today: str | None
    work_text_tomorrow: str | None
    today_incr_total: int
    today_cum_total: int


class JobAllocation(TypedDict):
    """시트2 BP사 × 직종 row (Cum.T = 금일누계)."""
    bp_code: str | None
    company: str
    disc_abbrev: str | None
    job_type: str
    workers_cum_t: int


class EquipmentAllocation(TypedDict):
    """시트3 BP사 × 장비 row (Cum.T = 금일투입누계)."""
    bp_code: str | None
    company: str
    equipment_big: str
    equipment_mid: str
    equipment_spec: str | None
    count_cum_t: int


class ParsedDailyReport(TypedDict):
    """1 작업일보 xlsx — 4시트 통합 파싱 결과."""
    report_date: str
    project: str
    bp_summaries: list[BPSummary]
    job_allocations: list[JobAllocation]
    equipment_allocations: list[EquipmentAllocation]
    activities: list[Activity]


class CPIAState(TypedDict):
    """LangGraph 그래프 전체 상태."""
    # 입력
    run_id: str
    date: str
    input_files: list[str]

    # 파이프라인 누적
    raw_texts: dict[str, str]
    parsed: list[Activity]
    mapped: list[Activity]
    hil_1_corrections: dict
    atomized_ids: list[str]

    # 분기 결과
    report_md: str
    forecast: list[dict]
    hil_2_selection: list[str]
    optimizer_advice: list[dict]

    # 상태 추적
    current_node: str
    status: Literal[
        "running", "waiting_hil_1", "waiting_hil_2",
        "completed", "failed",
    ]
```

- [ ] **Step 4: Run test → PASS**

```bash
uv run pytest tests/test_state.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/state.py pipeline/tests/test_state.py
git commit -m "state: Activity·BPSummary·JobAllocation·EquipmentAllocation·ParsedDailyReport·CPIAState TypedDict"
```

---

## Task 2: pipeline/db.py — asyncpg + activity_master 쿼리

**Files:**
- Modify: `pipeline/db.py`
- Create: `pipeline/tests/test_db.py`

**Spec 참조:** `docs/schema/postgres.md §2` + `docs/schema/mapping-layer.md §3.1` (`BP filter` 단계 SQL)

- [ ] **Step 1: tests/test_db.py 작성 — connection + BP filter query**

```python
from __future__ import annotations
import os
import pytest
from pipeline.db import PGClient


@pytest.fixture(scope="module")
async def pg() -> PGClient:
    url = os.environ.get("POSTGRES_URL")
    if not url:
        pytest.skip("POSTGRES_URL 환경변수 없음")
    client = PGClient(url)
    await client.connect()
    yield client
    await client.close()


async def test_bp_candidate_lookup_namwung(pg: PGClient):
    """남웅건설 BP filter → (WA, L6) 2개 후보."""
    rows = await pg.fetch_bp_candidates("남웅건설")
    keys = {(r["wa"], r["l6_main"]) for r in rows}
    assert ("CUB", "철근콘크리트공사") in keys
    assert ("FAB", "철근콘크리트공사") in keys


async def test_activity_lookup_by_id(pg: PGClient):
    """wbs_activity_id 로 Plan 값 조회."""
    row = await pg.fetch_activity("TNMCB1F6501A03030032")
    # Master 적재 후 검증되므로 적재 안 됐으면 None
    if row is None:
        pytest.skip("activity_master 적재 안 됨 (Task 6 후 재실행)")
    assert row["company"] == "남웅건설"
    assert row["plan_mh_rev2"] is not None
```

- [ ] **Step 2: Run test → FAIL (module empty)**

```bash
uv run pytest tests/test_db.py -v
```

Expected: ImportError.

- [ ] **Step 3: pipeline/db.py 작성**

```python
"""PostgreSQL 클라이언트 — activity_master + pipeline_runs + mapping_corrections.

Spec: docs/schema/postgres.md
"""
from __future__ import annotations
import asyncpg
from typing import Any


class PGClient:
    """asyncpg connection pool 래퍼."""

    def __init__(self, dsn: str, min_size: int = 1, max_size: int = 5) -> None:
        self.dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._min_size = min_size
        self._max_size = max_size

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            self.dsn, min_size=self._min_size, max_size=self._max_size,
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def fetch_bp_candidates(self, company: str) -> list[dict[str, Any]]:
        """BP filter — 그 BP사의 (WA, L6) 후보 풀."""
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT
                    SUBSTR(wbs_activity_id, 1, 3) AS wa,  -- 임시: WBS ID 첫 3글자
                    l6_main
                FROM activity_master
                WHERE company = $1
                ORDER BY wa, l6_main
            """, company)
            return [dict(r) for r in rows]
        # 주의: 위 SUBSTR 은 임시. Task 4 의 적재 스크립트가 wa 컬럼을 별도 저장하면
        # 'SELECT DISTINCT wa, l6_main' 로 단순화. spec postgres.md §2 의 wbs_activity_id 패턴.

    async def fetch_activity(self, wbs_activity_id: str) -> dict[str, Any] | None:
        """ActivityID → Plan 값 + 메타."""
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT wbs_activity_id, l5_disc, l6_main, l7_sub, l7_5_activity,
                       sub_work_area, company, unit, plan_total_qty, plan_mh_rev2,
                       plan_start, plan_finish
                FROM activity_master
                WHERE wbs_activity_id = $1
            """, wbs_activity_id)
            return dict(row) if row else None
```

> **Note:** Task 4 적재 시 `activity_master` 에 `wa` 컬럼을 추가 컬럼으로 저장하도록 결정 (Master List C4 `Work Area` Code 값). 그러면 위 임시 SUBSTR 은 `SELECT DISTINCT wa, l6_main` 로 정정. Task 4 작성 시 함께 적용.

- [ ] **Step 4: Run test → 결과 의존적**

```bash
uv run pytest tests/test_db.py -v
```

Expected: `test_bp_candidate_lookup_namwung` 가 Master 적재 안 됐으면 SKIP, 적재 후 PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/db.py pipeline/tests/test_db.py
git commit -m "db: PGClient pool + fetch_bp_candidates / fetch_activity"
```

---

## Task 3: pipeline/chroma_client.py — wbs_master + daily_activities 컬렉션

**Files:**
- Modify: `pipeline/chroma_client.py`
- Create: `pipeline/tests/test_chroma_client.py`

**Spec:** `docs/schema/mapping-layer.md §5.2, §6.1`

- [ ] **Step 1: tests/test_chroma_client.py 작성**

```python
from __future__ import annotations
import os
import pytest
from pipeline.chroma_client import ChromaClient


@pytest.fixture(scope="module")
def chroma() -> ChromaClient:
    host = os.environ.get("CHROMA_HOST")
    port = os.environ.get("CHROMA_PORT", "8000")
    if not host:
        pytest.skip("CHROMA_HOST 환경변수 없음")
    return ChromaClient(host=host, port=int(port))


def test_get_wbs_master(chroma: ChromaClient):
    coll = chroma.get_or_create_wbs_master()
    assert coll.name == "wbs_master"


def test_get_daily_activities(chroma: ChromaClient):
    coll = chroma.get_or_create_daily_activities()
    assert coll.name == "daily_activities"
```

- [ ] **Step 2: Run test → FAIL (module empty)**

- [ ] **Step 3: pipeline/chroma_client.py 작성**

```python
"""ChromaDB 클라이언트 — wbs_master + daily_activities.

Spec: docs/schema/mapping-layer.md §5.2 + state.md §1.1 (ChromaDB 2 컬렉션)
"""
from __future__ import annotations
import chromadb
from chromadb.api.models.Collection import Collection


class ChromaClient:
    """homelab ChromaDB server 연결."""

    WBS_MASTER = "wbs_master"
    DAILY_ACTIVITIES = "daily_activities"

    def __init__(self, host: str, port: int = 8000) -> None:
        self.client = chromadb.HttpClient(host=host, port=port)

    def get_or_create_wbs_master(self) -> Collection:
        """1 doc = 1 (WA, L6) 그룹. doc text = mapping-layer.md §5.2 형식."""
        return self.client.get_or_create_collection(
            name=self.WBS_MASTER,
            metadata={"hnsw:space": "cosine"},
        )

    def get_or_create_daily_activities(self) -> Collection:
        """1 doc = 1 Activity (시트4 line). doc text = work_content."""
        return self.client.get_or_create_collection(
            name=self.DAILY_ACTIVITIES,
            metadata={"hnsw:space": "cosine"},
        )
```

- [ ] **Step 4: Run test → PASS (Chroma 서버 기동 후)**

```bash
uv run pytest tests/test_chroma_client.py -v
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/chroma_client.py pipeline/tests/test_chroma_client.py
git commit -m "chroma: HttpClient + wbs_master / daily_activities 컬렉션 헬퍼"
```

---

## Task 4: scripts/load_master_list.py — Master xlsx → PG + Chroma 동시 적재

**Files:**
- Create: `scripts/load_master_list.py`
- Create: `pipeline/tests/test_load_master.py`

**Spec:** `docs/schema/mapping-layer.md §5` + `docs/schema/postgres.md §10`

- [ ] **Step 1: tests/test_load_master.py 작성 — 파싱 함수만 (외부 의존 없음)**

```python
from __future__ import annotations
from pathlib import Path

from scripts.load_master_list import parse_master_groups, make_doc_text


def test_parse_master_groups(sample_wbs_path: Path):
    groups = parse_master_groups(sample_wbs_path)
    assert len(groups) >= 100  # spec 의 102개 기준
    # 남웅건설 (CUB, 철근콘크리트공사) 존재
    key = ("CUB", "철근콘크리트공사")
    assert key in groups
    rows = groups[key]
    assert any(r["company"] == "남웅건설" for r in rows)


def test_make_doc_text_structure(sample_wbs_path: Path):
    groups = parse_master_groups(sample_wbs_path)
    rows = groups[("FAB", "ACID배기설비공사")]
    text = make_doc_text("FAB", "ACID배기설비공사", rows)
    assert "Work Area: FAB" in text
    assert "Work PKG-1 (L6): ACID배기설비공사" in text
    assert "Discipline (L5): 설비" in text
```

- [ ] **Step 2: Run test → FAIL (module not exist)**

- [ ] **Step 3: scripts/load_master_list.py 작성**

```python
"""Master List xlsx → PG activity_master + Chroma wbs_master 동시 적재.

Spec: docs/schema/mapping-layer.md §5

사용:
    uv run scripts/load_master_list.py \
        --wbs docs/sample/WBS공정표_*.xlsx \
        --filter "company IN ('남웅건설', '세보엠이씨', '창원기전')"
    uv run scripts/load_master_list.py --upsert  # 전체 적재
"""
from __future__ import annotations
import argparse
import asyncio
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import asyncpg
import openpyxl
from dotenv import load_dotenv
from openai import AzureOpenAI

from pipeline.chroma_client import ChromaClient


CPIA_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(CPIA_ROOT / ".env")


# Master List 컬럼 인덱스 (실 데이터 검증)
C_AID = 1     # ActivityID
C_WA = 4      # Work Area code (CUB/FAB)
C_WA_NAME = 5
C_L5 = 14     # Discipline 한글
C_L6 = 16     # Work PKG-1
C_L7 = 18     # Work PKG-2
C_L75 = 20    # Activity
C_COMPANY = 24
C_UNIT = 25
C_PLAN_QTY = 30   # Rev.2 총수량
C_PLAN_MH = 31    # Rev.2 MH
C_PLAN_START = 37 # Rev.2 Start
C_PLAN_FINISH = 38  # Rev.2 Finish


def parse_master_groups(xlsx_path: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Master List xlsx → (WA, L6) 그룹 dict.

    각 그룹 안에 row 들 (l5/l6/l7/l75/company/unit/plan/일정) 보존.
    """
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    ws = wb["Master List"]
    rows = list(ws.iter_rows(values_only=True))[4:]  # R5~

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if not r[C_AID]:
            continue
        wa = r[C_WA]
        l6 = r[C_L6]
        if not wa or not l6:
            continue
        groups[(wa, l6)].append({
            "wbs_activity_id": r[C_AID],
            "wa": wa,
            "wa_name": r[C_WA_NAME],
            "l5": r[C_L5],
            "l6": l6,
            "l7": r[C_L7],
            "l75": r[C_L75],
            "company": r[C_COMPANY],
            "unit": r[C_UNIT],
            "plan_total_qty": r[C_PLAN_QTY],
            "plan_mh_rev2": r[C_PLAN_MH],
            "plan_start": r[C_PLAN_START],
            "plan_finish": r[C_PLAN_FINISH],
        })
    wb.close()
    return dict(groups)


def make_doc_text(wa: str, l6: str, rows: list[dict[str, Any]]) -> str:
    """Chroma wbs_master doc text — mapping-layer.md §5.2 형식."""
    wa_names = sorted({r["wa_name"] for r in rows if r["wa_name"]})
    l5s = sorted({r["l5"] for r in rows if r["l5"]})
    l7s = sorted({r["l7"] for r in rows if r["l7"]})
    l75s = sorted({r["l75"] for r in rows if r["l75"]})
    cos = sorted({r["company"] for r in rows if r["company"]})
    units = sorted({r["unit"] for r in rows if r["unit"]})

    return (
        f"Work Area: {wa} ({', '.join(wa_names)})\n"
        f"Discipline (L5): {l5s[0] if l5s else ''}\n"
        f"Work PKG-1 (L6): {l6}\n"
        f"Work PKG-2 (L7): {', '.join(l7s)}\n"
        f"Units: {', '.join(units)}\n"
        f"Activities (L7.5 sample): {', '.join(l75s[:8])}\n"
        f"Companies: {', '.join(cos[:8])}"
    )


async def upsert_pg(rows: list[dict[str, Any]], dsn: str, source_file: str) -> int:
    """PG activity_master 에 row 별 적재 (UPSERT)."""
    conn = await asyncpg.connect(dsn)
    try:
        inserted = 0
        for r in rows:
            await conn.execute("""
                INSERT INTO activity_master (
                    wbs_activity_id, wa, l5_disc, l6_main, l7_sub, l7_5_activity,
                    company, unit, plan_total_qty, plan_mh_rev2,
                    plan_start, plan_finish, source_file
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (wbs_activity_id) DO UPDATE SET
                    plan_total_qty = EXCLUDED.plan_total_qty,
                    plan_mh_rev2 = EXCLUDED.plan_mh_rev2,
                    plan_start = EXCLUDED.plan_start,
                    plan_finish = EXCLUDED.plan_finish,
                    loaded_at = now()
            """, r["wbs_activity_id"], r["wa"], r["l5"], r["l6"], r["l7"], r["l75"],
                r["company"], r["unit"], r["plan_total_qty"], r["plan_mh_rev2"],
                r["plan_start"], r["plan_finish"], source_file)
            inserted += 1
        return inserted
    finally:
        await conn.close()


def upsert_chroma(groups: dict[tuple[str, str], list[dict[str, Any]]],
                  azure: AzureOpenAI, embed_model: str) -> int:
    """Chroma wbs_master 에 (WA, L6) 그룹 단위로 임베딩 적재."""
    chroma = ChromaClient(
        host=os.environ["CHROMA_HOST"],
        port=int(os.environ.get("CHROMA_PORT", "8000")),
    )
    coll = chroma.get_or_create_wbs_master()

    ids, texts, metas = [], [], []
    for (wa, l6), rows in sorted(groups.items()):
        ids.append(f"{wa}|{l6}")
        texts.append(make_doc_text(wa, l6, rows))
        companies = sorted({r["company"] for r in rows if r["company"]})
        units = sorted({r["unit"] for r in rows if r["unit"]})
        metas.append({
            "wa": wa, "l6_main": l6,
            "l5_disc": sorted({r["l5"] for r in rows if r["l5"]})[0] if rows else "",
            "companies": ",".join(companies),
            "units": ",".join(units),
        })

    # 임베딩 (16개씩 batch)
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), 16):
        chunk = texts[i:i + 16]
        resp = azure.embeddings.create(model=embed_model, input=chunk)
        embeddings.extend([d.embedding for d in resp.data])

    coll.upsert(ids=ids, embeddings=embeddings, metadatas=metas, documents=texts)
    return len(ids)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wbs", type=Path,
                    default=CPIA_ROOT / "docs/sample/WBS공정표_M15X IBL PH-3_CPRS_2025.09.25.xlsx")
    ap.add_argument("--filter-companies", nargs="*", default=None,
                    help="적재할 BP사 명단. 미지정 시 전체.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print(f"[load] xlsx: {args.wbs}")
    groups = parse_master_groups(args.wbs)
    print(f"[load] 전체 (WA, L6) 그룹: {len(groups)}")

    if args.filter_companies:
        filter_set = set(args.filter_companies)
        groups = {
            k: [r for r in v if r["company"] in filter_set]
            for k, v in groups.items()
        }
        groups = {k: v for k, v in groups.items() if v}
        print(f"[load] filter 적용 후 그룹: {len(groups)}")

    all_rows = [r for rows in groups.values() for r in rows]
    print(f"[load] 적재 row: {len(all_rows)}")

    if args.dry_run:
        print("[load] dry-run 모드, 적재 생략")
        return

    # PG 적재
    dsn = os.environ["POSTGRES_URL"]
    n_pg = asyncio.run(upsert_pg(all_rows, dsn, str(args.wbs.name)))
    print(f"[load] PG activity_master upsert: {n_pg} rows")

    # Chroma 적재 (Azure OpenAI 임베딩)
    azure = AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    )
    n_chr = upsert_chroma(groups, azure, os.environ["EMBEDDING_MODEL"])
    print(f"[load] Chroma wbs_master upsert: {n_chr} groups")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test → PASS (파싱 함수만)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
uv run pytest tests/test_load_master.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/load_master_list.py pipeline/tests/test_load_master.py
git commit -m "load: Master xlsx → PG activity_master + Chroma wbs_master 동시 적재"
```

---

## Task 5: 실 Master 적재 + 검증 (운영 작업)

**의존성:** Task 0.5 의 로컬 Docker 기동 완료 (PG + Chroma 둘 다 running). `.env` 가 `.env.local` 로 symlink 된 상태. B 트랙 homelab 인프라는 대기 안 함 — Task 10 에서 마이그레이션.

- [ ] **Step 1: PG schema 확인**

```bash
psql "$POSTGRES_URL" -c "\d activity_master"
```

Expected: `wa TEXT`, `wbs_activity_id PK`, etc 모두 존재.

- [ ] **Step 2: dry-run 으로 적재 양 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
uv run scripts/load_master_list.py \
    --filter-companies 남웅건설 세보엠이씨 창원기전 \
    --dry-run
```

Expected: `적재 row: ~250` (남웅 179 + 세보 31 + 창원 28 + 중복 제거).

- [ ] **Step 3: 실 적재**

```bash
uv run scripts/load_master_list.py \
    --filter-companies 남웅건설 세보엠이씨 창원기전
```

Expected: `PG activity_master upsert: ~250 rows / Chroma wbs_master upsert: ~30 groups`.

- [ ] **Step 4: 검증 쿼리**

```bash
psql "$POSTGRES_URL" -c "
    SELECT company, COUNT(*) AS n
    FROM activity_master
    GROUP BY company
    ORDER BY n DESC;
"
```

Expected: 남웅건설 ~179, 세보엠이씨 ~31, 창원기전 ~28.

```bash
uv run python -c "
from pipeline.chroma_client import ChromaClient
import os
from dotenv import load_dotenv
load_dotenv()
c = ChromaClient(host=os.environ['CHROMA_HOST'], port=int(os.environ.get('CHROMA_PORT','8000')))
coll = c.get_or_create_wbs_master()
print(f'Chroma wbs_master count: {coll.count()}')
"
```

Expected: ~30 (BP사 후보 풀 그룹 수).

- [ ] **Step 5: Commit log (코드 변경 없으면 skip, 다만 .env.example 갱신이라면 commit)**

---

## Task 6: pipeline/agents/mapper.py — helper 함수들 (Mapper 6단계의 ②④⑥)

**Files:**
- Modify: `pipeline/agents/mapper.py`
- Create: `pipeline/tests/test_mapper_helpers.py`

**Spec:** `docs/schema/mapping-layer.md §3.1 (build_embedding_input / build_llm_input)` + `§4 (resolve_wa)`

- [ ] **Step 1: tests/test_mapper_helpers.py 작성**

```python
from __future__ import annotations
import pytest
from pipeline.state import Activity, BPSummary, ParsedDailyReport
from pipeline.agents.mapper import (
    build_embedding_input, build_llm_input, build_bp_context, resolve_wa, WAResolution,
)


@pytest.fixture
def activity_namwung() -> Activity:
    return {
        "wbs_activity_id": None, "l5_disc": "건축",
        "l6_main": None, "l7_sub": None, "l7_5_activity": None,
        "sub_work_area": None, "trade": "건축", "company": "남웅건설",
        "unit": "M2", "today_qty": 320.0, "work_content": "기초 거푸집 설치",
        "conditions": [], "assigned_workers": 81.0, "worker_source": "parsed",
        "plan_total_qty": None, "plan_mh": None,
        "requires_review": False, "wa": None, "mapping_conf": None,
        "mapping_source": None,
    }


@pytest.fixture
def parsed_report_minimal() -> ParsedDailyReport:
    return {
        "report_date": "20250925", "project": "M15X PH-3 IBL",
        "bp_summaries": [], "job_allocations": [],
        "equipment_allocations": [], "activities": [],
    }


def test_build_embedding_input_simple(activity_namwung):
    """임베딩 input 은 작업line 자체만 — BP 컨텍스트·숫자 제외."""
    text = build_embedding_input(activity_namwung)
    assert "회사: 남웅건설" in text
    assert "작업: 기초 거푸집 설치" in text
    assert "단위: M2" in text
    assert "공종: 건축" in text
    # BP 컨텍스트 미포함 확인
    assert "BP사 단위 컨텍스트" not in text
    assert "배관공" not in text


def test_build_llm_input_rich(activity_namwung, parsed_report_minimal):
    """LLM input 은 풍부 컨텍스트 포함."""
    text = build_llm_input(activity_namwung, parsed_report_minimal)
    assert "회사: 남웅건설" in text
    assert "BP사 단위 컨텍스트" in text


def test_resolve_wa_bp_scope_single(activity_namwung):
    """1단계 — BP scope WA 단일."""
    cand_pool = [("FAB", "ACID배기설비공사"), ("FAB", "ALKALI배기설비공사")]
    result = resolve_wa(activity_namwung, l6_choice="ACID배기설비공사",
                       cand_pool=cand_pool, parsed_report=None)
    assert result.value == "FAB"
    assert result.source == "auto_bp_single"


def test_resolve_wa_l6_single(activity_namwung):
    """2단계 — L6 결정 후 그 L6 의 WA 단일."""
    cand_pool = [("CUB", "CABLE TRAY공사"), ("FAB", "CABLE TRAY공사"),
                 ("FAB", "전등설비공사")]
    result = resolve_wa(activity_namwung, l6_choice="전등설비공사",
                       cand_pool=cand_pool, parsed_report=None)
    assert result.value == "FAB"
    assert result.source == "auto_l6_single"


def test_resolve_wa_hil_required(activity_namwung):
    """4단계 — WA 양쪽 다 가능 + 시트1 자연어 없음 → H-i-L."""
    cand_pool = [("CUB", "철근콘크리트공사"), ("FAB", "철근콘크리트공사")]
    result = resolve_wa(activity_namwung, l6_choice="철근콘크리트공사",
                       cand_pool=cand_pool, parsed_report=None)
    assert result.value is None
    assert result.source == "hil_required"
```

- [ ] **Step 2: Run test → FAIL (module empty)**

- [ ] **Step 3: pipeline/agents/mapper.py 작성 — helper 함수들**

```python
"""Mapper agent — 작업일보 → WBS 매핑.

Spec: docs/schema/mapping-layer.md §3 (6단계 흐름), §4 (WA 결정 4단계)

흐름:
  ① BP filter (PG)
  ② 임베딩 input 텍스트 (단순)
  ③ Chroma wbs_master Top-K → BP filter ∩
  ④ LLM input 텍스트 (풍부)
  ⑤ LLM 분류 (GPT-5.1)
  ⑥ WA 결정 4단계
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

from pipeline.state import Activity, BPSummary, ParsedDailyReport


# 시트2 직종 필터 — mapping-layer.md §2 의 Noise 제거 규칙
_TRADE_KEYWORDS = (
    "형틀", "철근", "콘크리트", "타설", "조적", "방수", "도장", "비계",
    "용접", "배관", "전기공", "덕트", "단열", "내장", "타일", "미장",
    "양생", "철골", "보온", "케이블",
)
_MGR_KEYWORDS = (
    "소장", "관리자", "감독", "감리", "안전", "Shop", "BIM", "공무",
    "설계", "품질", "운영", "창고",
)
_NOISE_KEYWORDS = ("기능공 투입 Total", "기능공 투입 total")


def _is_trade_job(job: str) -> bool:
    if any(n in job for n in _NOISE_KEYWORDS):
        return False
    if any(m in job for m in _MGR_KEYWORDS):
        return False
    return any(k in job for k in _TRADE_KEYWORDS)


@dataclass(frozen=True)
class WAResolution:
    """WA 결정 결과."""
    value: str | None   # 'CUB' / 'FAB' / None (H-i-L 1 대기)
    source: Literal[
        "auto_bp_single", "auto_l6_single", "auto_sheet1_text", "hil_required",
    ]


def build_embedding_input(activity: Activity) -> str:
    """임베딩 input — 작업line 자체만 (mapping-layer.md §3.1).

    숫자·BP 컨텍스트 제외. v2 의 숫자 오염 (배관공 165168 등) 방지.
    """
    return (
        f"회사: {activity['company']}\n"
        f"작업: {activity['work_content']}\n"
        f"단위: {activity['unit']}\n"
        f"공종: {activity['trade']}"
    )


def build_bp_context(company: str, parsed_report: ParsedDailyReport | None) -> str:
    """LLM input 용 BP사 단위 풍부 컨텍스트 (시트1+2+3 join, mapping-layer.md §3.1)."""
    if not parsed_report:
        return "  · (parsed_report 미제공 — BP 컨텍스트 없이 진행)"

    # 시트1
    summaries: list[BPSummary] = [
        s for s in parsed_report["bp_summaries"] if s["company"] == company
    ]
    work_texts = [s["work_text_today"] for s in summaries if s["work_text_today"]]
    today_incr = sum(s["today_incr_total"] for s in summaries)
    today_cum = sum(s["today_cum_total"] for s in summaries)
    work_text_str = " / ".join(t for t in work_texts[:2] if t)[:200] if work_texts else "미기재"

    sheet1_block = (
        f"  · [시트1] 주요작업 텍스트 (BP사 기재): {work_text_str}\n"
        f"  · [시트1] 금일 신규 투입 인원 (Incr.): {today_incr:,}명\n"
        f"  · [시트1] 금일 누적 인원 (Cum.): {today_cum:,}명-일"
    )

    # 시트2 — 기능공만, noise 제거
    jobs: dict[str, int] = {}
    for j in parsed_report["job_allocations"]:
        if j["company"] != company:
            continue
        if not _is_trade_job(j["job_type"]):
            continue
        jobs[j["job_type"]] = jobs.get(j["job_type"], 0) + j["workers_cum_t"]
    if jobs:
        top_jobs = sorted(jobs.items(), key=lambda x: -x[1])[:8]
        job_lines = "\n".join(f"      - {j}: {c:,}명-일" for j, c in top_jobs)
        sheet2_block = "  · [시트2] 기능공 직종 (금일누계 Cum.T):\n" + job_lines
    else:
        sheet2_block = "  · [시트2] 기능공 직종: 미신고"

    # 시트3
    eqs = [e for e in parsed_report["equipment_allocations"] if e["company"] == company]
    if eqs:
        top_eq = sorted(eqs, key=lambda e: -e["count_cum_t"])[:5]
        eq_lines = "\n".join(
            f"      - {e['equipment_big']}/{e['equipment_mid']} ({e['equipment_spec'] or '규격 미상'}): {e['count_cum_t']:,}회-일"
            for e in top_eq
        )
        sheet3_block = "  · [시트3] 투입 장비 (금일투입누계 Cum.T):\n" + eq_lines
    else:
        sheet3_block = "  · [시트3] 투입 장비: 미신고"

    return f"{sheet1_block}\n{sheet2_block}\n{sheet3_block}"


def build_llm_input(activity: Activity, parsed_report: ParsedDailyReport | None) -> str:
    """LLM input — 작업line + BP사 단위 풍부 컨텍스트 (mapping-layer.md §3.1)."""
    bp_ctx = build_bp_context(activity["company"], parsed_report)
    today_str = activity["today_qty"] if activity["today_qty"] not in (None, 0) else "-"
    plan_str = activity["plan_total_qty"] if activity["plan_total_qty"] not in (None, 0) else "-"
    return (
        f"회사: {activity['company']} (공종 {activity['trade']})\n"
        f"작업: {activity['work_content']}\n"
        f"단위: {activity['unit']}  |  금일실적: {today_str}  |  계획 총수량: {plan_str}\n"
        f"[BP사 단위 컨텍스트]\n{bp_ctx}"
    )


def resolve_wa(
    activity: Activity,
    l6_choice: str,
    cand_pool: list[tuple[str, str]],
    parsed_report: ParsedDailyReport | None,
) -> WAResolution:
    """WA 결정 4단계 (mapping-layer.md §4)."""
    # 1단계 — BP scope WA 단일
    bp_wa = {wa for wa, _ in cand_pool}
    if len(bp_wa) == 1:
        return WAResolution(value=next(iter(bp_wa)), source="auto_bp_single")

    # 2단계 — L6 결정 후 그 L6 의 WA 단일
    l6_wa = {wa for wa, l6 in cand_pool if l6 == l6_choice}
    if len(l6_wa) == 1:
        return WAResolution(value=next(iter(l6_wa)), source="auto_l6_single")

    # 3단계 — 시트1 자연어 LLM 추론 (PoC 비활성, GATE 2 활성)
    # TODO: GATE 2 진입 시 llm_infer_wa() 추가

    # 4단계 — H-i-L 강제
    return WAResolution(value=None, source="hil_required")
```

- [ ] **Step 4: Run test → PASS**

```bash
uv run pytest tests/test_mapper_helpers.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/mapper.py pipeline/tests/test_mapper_helpers.py
git commit -m "mapper: helper 함수 — build_embedding_input / build_llm_input / build_bp_context / resolve_wa (WA 4단계)"
```

---

## Task 7: pipeline/agents/mapper.py — `mapper_node` 통합 함수

**Files:**
- Modify: `pipeline/agents/mapper.py` (append)
- Create: `pipeline/tests/test_mapper_node.py`

**Spec:** `docs/schema/mapping-layer.md §3` (전체 6단계 통합)

- [ ] **Step 1: tests/test_mapper_node.py 작성 — 통합 테스트 (Azure OpenAI 실 호출 포함)**

```python
from __future__ import annotations
import pytest
from pipeline.state import Activity
from pipeline.agents.mapper import map_activity, MapperConfig


@pytest.fixture
def cfg(azure_openai_env) -> MapperConfig:
    """실 Azure 환경 사용 (.env)."""
    import os
    return MapperConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
        embedding_model=os.environ["EMBEDDING_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
    )


@pytest.mark.asyncio
async def test_map_activity_namwung(cfg):
    """남웅건설 '기초 거푸집 설치' → 철근콘크리트공사."""
    activity: Activity = {
        "wbs_activity_id": None, "l5_disc": "건축",
        "l6_main": None, "l7_sub": None, "l7_5_activity": None,
        "sub_work_area": None, "trade": "건축", "company": "남웅건설",
        "unit": "M2", "today_qty": 320.0, "work_content": "기초 거푸집 설치",
        "conditions": [], "assigned_workers": 81.0, "worker_source": "parsed",
        "plan_total_qty": None, "plan_mh": None,
        "requires_review": False, "wa": None, "mapping_conf": None,
        "mapping_source": None,
    }
    result = await map_activity(activity, parsed_report=None, cfg=cfg)
    assert result["l6_main"] == "철근콘크리트공사"
    # 남웅은 WA 양쪽 가능 → H-i-L
    assert result["wa"] is None
    assert result["mapping_source"] == "hil_required"
    assert result["requires_review"] is True


@pytest.mark.asyncio
async def test_map_activity_sebo(cfg):
    """세보엠이씨 'ACID 배기덕트 설치' → ACID배기설비공사 (FAB 단일 자동)."""
    activity: Activity = {
        "wbs_activity_id": None, "l5_disc": "설비",
        "l6_main": None, "l7_sub": None, "l7_5_activity": None,
        "sub_work_area": None, "trade": "설비", "company": "세보엠이씨",
        "unit": "M2", "today_qty": 0.0, "work_content": "ACID 배기덕트 설치",
        "conditions": [], "assigned_workers": 0.0, "worker_source": "parsed",
        "plan_total_qty": 4214.2, "plan_mh": None,
        "requires_review": False, "wa": None, "mapping_conf": None,
        "mapping_source": None,
    }
    result = await map_activity(activity, parsed_report=None, cfg=cfg)
    assert result["l6_main"] == "ACID배기설비공사"
    assert result["wa"] == "FAB"
    assert result["mapping_source"] == "auto_bp_single"
```

- [ ] **Step 2: Run test → FAIL (map_activity 미구현)**

- [ ] **Step 3: pipeline/agents/mapper.py 에 `map_activity` + `MapperConfig` 추가**

```python
# pipeline/agents/mapper.py 에 추가 (기존 helper 들 아래)

import json
from dataclasses import dataclass
from typing import Any

from openai import AzureOpenAI

from pipeline.db import PGClient
from pipeline.chroma_client import ChromaClient


@dataclass
class MapperConfig:
    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    llm_model: str
    embedding_model: str
    postgres_url: str
    chroma_host: str
    chroma_port: int
    top_k: int = 15
    max_candidates: int = 8
    conf_threshold: float = 0.7


async def map_activity(
    activity: Activity,
    parsed_report: ParsedDailyReport | None,
    cfg: MapperConfig,
) -> Activity:
    """매핑 6단계 흐름 (mapping-layer.md §3)."""
    client = AzureOpenAI(
        api_key=cfg.azure_api_key, api_version=cfg.azure_api_version,
        azure_endpoint=cfg.azure_endpoint,
    )

    # ① BP filter
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        cand_rows = await pg.fetch_bp_candidates(activity["company"])
    finally:
        await pg.close()
    cand_pool = [(r["wa"], r["l6_main"]) for r in cand_rows]
    if not cand_pool:
        # BP filter 후 0 → H-i-L (Master 미등록 BP사)
        return {**activity, "wa": None, "l6_main": None,
                "mapping_source": "hil_required",
                "mapping_conf": 0.0, "requires_review": True}

    # ② 임베딩 input (단순)
    embed_text = build_embedding_input(activity)
    resp = client.embeddings.create(model=cfg.embedding_model, input=[embed_text])
    inp_vec = resp.data[0].embedding

    # ③ Chroma Top-K → BP filter ∩
    chroma = ChromaClient(host=cfg.chroma_host, port=cfg.chroma_port)
    coll = chroma.get_or_create_wbs_master()
    chroma_result = coll.query(
        query_embeddings=[inp_vec], n_results=cfg.top_k,
        include=["documents", "metadatas"],
    )
    candidates: list[dict[str, Any]] = []
    for i, doc_id in enumerate(chroma_result["ids"][0]):
        meta = chroma_result["metadatas"][0][i]
        key = (meta["wa"], meta["l6_main"])
        if key in cand_pool:
            candidates.append({
                "key": key,
                "doc_text": chroma_result["documents"][0][i],
            })
            if len(candidates) >= cfg.max_candidates:
                break

    # 임베딩 결과에 BP filter 통과 후보 0개 (희박) → BP filter 전체 fallback
    if not candidates:
        candidates = [
            {"key": k, "doc_text": f"Work PKG-1 (L6): {k[1]} (WA: {k[0]})"}
            for k in cand_pool[:cfg.max_candidates]
        ]

    # ④ LLM input (풍부)
    llm_text = build_llm_input(activity, parsed_report)

    # ⑤ LLM 분류
    cand_str = "\n".join(f"[{i}] {c['doc_text']}" for i, c in enumerate(candidates))
    user_msg = (
        f"작업일보 1행을 WBS 매핑 후보 중 1개로 분류.\n\n"
        f"### 작업일보 + BP사 컨텍스트\n{llm_text}\n\n"
        f"### 후보\n{cand_str}\n\n"
        f'### 응답 (JSON only)\n'
        f'{{"choice": <int>, "confidence": <0.0~1.0 float>, "reason": "<짧게>"}}'
    )
    resp = client.chat.completions.create(
        model=cfg.llm_model,
        messages=[
            {"role": "system", "content": "건설 작업일보 ↔ WBS 매핑 분류기. 한국어 응답."},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
    )
    try:
        llm_result = json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError:
        return {**activity, "wa": None, "l6_main": None,
                "mapping_source": "hil_required",
                "mapping_conf": 0.0, "requires_review": True}

    choice = llm_result.get("choice", -1)
    if not (0 <= choice < len(candidates)):
        return {**activity, "wa": None, "l6_main": None,
                "mapping_source": "hil_required",
                "mapping_conf": 0.0, "requires_review": True}

    chosen_key = candidates[choice]["key"]
    confidence = float(llm_result.get("confidence", 0.0))

    # ⑥ WA 결정 4단계
    wa_result = resolve_wa(activity, l6_choice=chosen_key[1],
                           cand_pool=cand_pool, parsed_report=parsed_report)

    requires_review = (confidence < cfg.conf_threshold) or (wa_result.source == "hil_required")

    return {
        **activity,
        "wa": wa_result.value,
        "l6_main": chosen_key[1],
        "mapping_conf": confidence,
        "mapping_source": wa_result.source,
        "requires_review": requires_review,
    }
```

- [ ] **Step 4: Run test → PASS (실 Azure 호출 약 10s/case)**

```bash
uv run pytest tests/test_mapper_node.py -v
```

Expected: 2 passed (남웅·세보 둘 다).

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/mapper.py pipeline/tests/test_mapper_node.py
git commit -m "mapper: map_activity 통합 — BP filter → 임베딩 → LLM rerank → WA 결정"
```

---

## Task 8: tests/test_mapper_golden.py — 79건 회귀 테스트

**Files:**
- Create: `pipeline/tests/test_mapper_golden.py`

**Spec:** `docs/schema/mapping-layer.md §9` (골든 79건 + 안 A v3 98.7% 기준)

- [ ] **Step 1: 골든 dict 정의 + 시뮬 호출 + 정확도 측정**

```python
"""79건 골든 회귀 — mapping-layer.md §9.

시뮬 v3 기준 자동 정확도 ≥ 95% (CI 안정성), 운영 정확도 (H-i-L 후) = 100%.

실 Azure 호출 필요. 비용 ~$0.02/run.
"""
from __future__ import annotations
import asyncio
import os
import pytest

from pipeline.state import Activity, ParsedDailyReport
from pipeline.agents.mapper import map_activity, MapperConfig

import openpyxl


# 골든 79건 (mapping-layer.md §9.1)
GOLDEN: dict[int, tuple[str, str]] = {}
for r in range(99, 147):
    if r != 125:
        GOLDEN[r] = ("남웅건설", "철근콘크리트공사")
GOLDEN.update({
    452: ("세보엠이씨", "ACID배기설비공사"),
    453: ("세보엠이씨", "VOC설비공사"),
    454: ("세보엠이씨", "CABINET배기설비공사"),
    455: ("세보엠이씨", "ALKALI배기설비공사"),
    457: ("세보엠이씨", "H/G배기설비공사"),
    458: ("세보엠이씨", "비상배기덕트설비공사"),
    459: ("세보엠이씨", "일반공조설비공사"),
    461: ("세보엠이씨", "DCC설비공사"),
    462: ("세보엠이씨", "냉동기설비공사"),
    463: ("세보엠이씨", "냉동기설비공사"),
    465: ("세보엠이씨", "위생배관공사"),
    466: ("세보엠이씨", "NPW배관공사"),
    467: ("세보엠이씨", "H-VAC설비공사"),
    469: ("세보엠이씨", "일반공조설비공사"),
    472: ("세보엠이씨", "ACID배기설비공사"),
    473: ("세보엠이씨", "VOC설비공사"),
    474: ("세보엠이씨", "CABINET배기설비공사"),
    475: ("세보엠이씨", "ALKALI배기설비공사"),
    1207: ("세보엠이씨", "기계소화설비"),
    1208: ("세보엠이씨", "기계소화설비"),
    1209: ("세보엠이씨", "기계소화설비"),
    1210: ("세보엠이씨", "기계소화설비"),
    1211: ("세보엠이씨", "기계소화설비"),
    1212: ("세보엠이씨", "기계소화설비"),
    892: ("창원기전", "전등설비공사"),
    895: ("창원기전", "전등설비공사"),
    898: ("창원기전", "전등설비공사"),
    901: ("창원기전", "전등설비공사"),
    904: ("창원기전", "전등설비공사"),
    906: ("창원기전", "전력간선공사"),
    1230: ("창원기전", "전기소화설비"),
    1231: ("창원기전", "전기소화설비"),
})


def _ffill(rows, header_end, fill_cols):
    last = {c: None for c in fill_cols}
    out = []
    for i, r in enumerate(rows[header_end:], start=header_end + 1):
        rec = list(r)
        for c in fill_cols:
            if rec[c] is not None and str(rec[c]).strip() != "":
                last[c] = rec[c]
            else:
                rec[c] = last[c]
        out.append((i, rec))
    return out


def _load_inputs(tong_path) -> list[tuple[int, Activity]]:
    """시트4 의 골든 row 들을 Activity 로."""
    wb = openpyxl.load_workbook(tong_path, data_only=True, read_only=True)
    ws4 = wb["4.물량"]
    rows = _ffill(list(ws4.iter_rows(values_only=True)), 4, [1, 2, 3, 4, 5])
    activities: list[tuple[int, Activity]] = []
    for i, r in rows:
        if i not in GOLDEN:
            continue
        if not (r[5] and r[7]):
            continue
        activities.append((i, {
            "wbs_activity_id": None,
            "l5_disc": str(r[3]) if r[3] else "",
            "l6_main": None, "l7_sub": None, "l7_5_activity": None,
            "sub_work_area": None,
            "trade": str(r[3]) if r[3] else "",
            "company": str(r[5]).strip(),
            "unit": str(r[8] or "").strip(),
            "today_qty": float(r[11]) if isinstance(r[11], (int, float)) else 0.0,
            "work_content": str(r[7]).strip(),
            "conditions": [],
            "assigned_workers": 0.0, "worker_source": "parsed",
            "plan_total_qty": float(r[9]) if isinstance(r[9], (int, float)) else None,
            "plan_mh": None,
            "requires_review": False, "wa": None,
            "mapping_conf": None, "mapping_source": None,
        }))
    wb.close()
    return activities


@pytest.mark.asyncio
async def test_golden_accuracy(sample_tong_path, azure_openai_env):
    """안 A v3 자동 정확도 ≥ 95% (시뮬 기준 98.7%)."""
    cfg = MapperConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
        embedding_model=os.environ["EMBEDDING_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
    )

    inputs = _load_inputs(sample_tong_path)
    assert len(inputs) == 79, f"골든 입력 수 불일치: {len(inputs)}"

    correct = 0
    wrong = []
    for row, activity in inputs:
        result = await map_activity(activity, parsed_report=None, cfg=cfg)
        expected = GOLDEN[row][1]
        if result["l6_main"] == expected:
            correct += 1
        else:
            wrong.append((row, activity["work_content"], expected, result["l6_main"], result["mapping_conf"]))

    pct = correct / len(inputs) * 100
    print(f"\n정확도: {correct}/{len(inputs)} = {pct:.1f}%")
    for r, w, exp, got, conf in wrong:
        print(f"  ✗ R{r} '{w}' → 골든={exp} vs 결과={got} (conf {conf})")

    assert pct >= 95.0, f"자동 정확도 95% 미만: {pct:.1f}%"
```

- [ ] **Step 2: Run test → 결과 (Master 적재 + Chroma 적재 완료 후)**

```bash
uv run pytest tests/test_mapper_golden.py -v -s
```

Expected: `정확도: 78/79 = 98.7%` (시뮬 결과 재현). assert ≥ 95% 통과.

- [ ] **Step 3: 시간·비용 측정 — 회귀 테스트 부담**

```bash
time uv run pytest tests/test_mapper_golden.py -v -s
```

Expected: ~5분 (79건 × 5s/Activity). CI 에선 nightly 또는 manual trigger.

- [ ] **Step 4: pytest marker 추가 — CI 분리**

```python
# tests/test_mapper_golden.py 의 함수에 추가
@pytest.mark.slow  # CI 에선 -m "not slow" 로 스킵
@pytest.mark.golden
@pytest.mark.asyncio
async def test_golden_accuracy(...):
    ...
```

`pyproject.toml` 에 marker 등록:
```toml
[tool.pytest.ini_options]
markers = [
    "slow: 느린 테스트 (LLM 호출 포함)",
    "golden: 골든 회귀 테스트",
]
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/tests/test_mapper_golden.py pipeline/pyproject.toml
git commit -m "test: mapper golden 79건 회귀 — 시뮬 v3 98.7% 패턴 보존"
```

---

## Task 9: 최종 검증 + PR

- [ ] **Step 1: 전체 테스트 한 번 통과**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline"
uv run pytest tests/ -v -m "not slow"
```

Expected: 모두 PASS (slow / golden 제외).

- [ ] **Step 2: golden 별도 실행 + 결과 기록**

```bash
uv run pytest tests/test_mapper_golden.py -v -s -m golden | tee /tmp/cpia_golden_run.log
```

- [ ] **Step 3: 변경 요약 — README 또는 docs/ 에 실행 가이드 1 단락 추가 (optional)**

- [ ] **Step 4: PR 생성**

```bash
git push origin A_Track
gh pr create --title "feat: 매핑 레이어 구현 — state.py + Mapper 6단계 + 골든 79건 회귀" --body "..."
```

PR 본문 항목:
- 구현 모듈 4개 (state / db / chroma_client / mapper)
- Master List 적재 스크립트 + 실행 결과
- 골든 79건 정확도 (실 측정)
- B 트랙 의존성 체크리스트 (postgres init.sql, docker-compose)

- [ ] **Step 5: GATE 1 자기 체크**

매핑 레이어 단독 동작 확인:
- [ ] `pipeline/state.py` import 성공
- [ ] 로컬 Docker (PG + Chroma) 정상 동작
- [ ] `scripts/load_master_list.py` 실행 + 로컬 PG/Chroma 적재
- [ ] `pipeline/agents/mapper.py` 의 `map_activity` 단일 호출 성공
- [ ] 골든 79건 자동 정확도 ≥ 95%
- [ ] `requires_review=True` 케이스 약 60% (H-i-L 1 미구현 상태에선 적재 정지)

---

## Task 10: homelab 마이그레이션 (B 트랙 인프라 준비 후)

**트리거:** B 트랙이 `infra/postgres/init.sql` (8 테이블 전체) + `docker-compose.yml` (homelab Postgres + Chroma) 머지 + Cloudflare Tunnel 까지 작동 완료. PR comment 또는 카톡으로 신호 받음.

**Files:**
- Create: `scripts/migrate_to_homelab.sh`
- Modify: `.env.homelab` (B 트랙 머지 후 채움)

**전략:** 로컬에서 검증된 `activity_master` 데이터 + `wbs_master` Chroma 컬렉션을 homelab 으로 이관. 코드 변경 X (env switch 만).

- [ ] **Step 1: B 트랙 머지 확인**

```bash
git fetch origin main
git log origin/main -- infra/postgres/init.sql infra/docker-compose.yml
# Expected: B 트랙 commit 존재 + 7 테이블 (또는 8 테이블) 정의
```

- [ ] **Step 2: 로컬 activity_master 데이터 dump**

```bash
pg_dump postgresql://cpia:cpia@localhost:5432/cpia \
    --table=activity_master \
    --data-only \
    --column-inserts \
    > /tmp/cpia_activity_master_data.sql

wc -l /tmp/cpia_activity_master_data.sql
# Expected: 적재한 row 수 (남웅+세보+창원 ~250) + 헤더 line
```

- [ ] **Step 3: Chroma `wbs_master` 컬렉션 export**

```bash
uv run python <<'EOF'
from pipeline.chroma_client import ChromaClient
import os, json
from dotenv import load_dotenv
load_dotenv()  # .env.local

c = ChromaClient(host=os.environ['CHROMA_HOST'], port=int(os.environ.get('CHROMA_PORT', '8000')))
coll = c.get_or_create_wbs_master()
data = coll.get(include=['embeddings', 'documents', 'metadatas'])
with open('/tmp/cpia_wbs_master_export.json', 'w') as f:
    json.dump({
        'ids': data['ids'],
        'documents': data['documents'],
        'metadatas': data['metadatas'],
        'embeddings': [list(e) for e in data['embeddings']],
    }, f)
print(f"exported {len(data['ids'])} docs")
EOF
```

- [ ] **Step 4: .env.homelab 작성 + symlink 전환**

```bash
# .env.homelab — B 트랙 머지 후 PG/Chroma URL 채움
cat > .env.homelab <<'EOF'
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_API_VERSION=...
LLM_MODEL=gpt-5.1-chat-ai-board-test
EMBEDDING_MODEL=text-embedding-3-small-ai-board-test
EMBEDDING_DIM=1536

# homelab (B 트랙 머지 후 실제 값 채움)
POSTGRES_URL=postgresql://<user>:<pw>@<homelab-host>:5432/cpia
CHROMA_HOST=<homelab-host>
CHROMA_PORT=8000
EOF

# symlink 전환
ln -sf .env.homelab .env
```

- [ ] **Step 5: homelab PG 에 init.sql 적용 확인 + 데이터 restore**

```bash
# B 트랙이 이미 init.sql 적용했어야 함. 미적용이면 알림.
psql "$POSTGRES_URL" -c "\d activity_master" || {
    echo "ERROR: B 트랙 init.sql 미적용. /infra/postgres/init.sql 실행 요청 필요."
    exit 1
}

# 로컬에서 dump 한 데이터 restore
psql "$POSTGRES_URL" -f /tmp/cpia_activity_master_data.sql
psql "$POSTGRES_URL" -c "SELECT count(*) FROM activity_master;"
# Expected: 로컬과 동일한 row 수
```

- [ ] **Step 6: homelab Chroma 에 컬렉션 import**

```bash
uv run python <<'EOF'
from pipeline.chroma_client import ChromaClient
import os, json
from dotenv import load_dotenv
load_dotenv()  # 이제 .env.homelab

with open('/tmp/cpia_wbs_master_export.json') as f:
    data = json.load(f)

c = ChromaClient(host=os.environ['CHROMA_HOST'], port=int(os.environ.get('CHROMA_PORT', '8000')))
coll = c.get_or_create_wbs_master()
coll.upsert(
    ids=data['ids'],
    embeddings=data['embeddings'],
    documents=data['documents'],
    metadatas=data['metadatas'],
)
print(f"imported {len(data['ids'])} docs to homelab Chroma")
EOF
```

- [ ] **Step 7: 골든 회귀 재실행 (homelab 환경)**

```bash
cd pipeline
uv run pytest tests/test_mapper_golden.py -v -s -m golden
# Expected: 동일 정확도 (78/79 = 98.7%). 환경만 바뀐 거니 결과 동등.
```

- [ ] **Step 8: 로컬 Docker 정리 (선택 — 디버깅 자산으로 유지 가능)**

```bash
# 유지: cd infra/local && docker compose -f docker-compose.local.yml down
# 데이터 보존을 위해 -v (volume 삭제) 는 사용 X.
# A 트랙 단독 디버깅 시 .env.local symlink 로 재진입 가능.
```

- [ ] **Step 9: scripts/migrate_to_homelab.sh 작성 (재실행 가능하게)**

```bash
cat > scripts/migrate_to_homelab.sh <<'SCRIPT'
#!/usr/bin/env bash
# 로컬 → homelab 마이그레이션 자동화. 추가 BP사 적재 후 재실행 가능.
set -euo pipefail

CPIA_ROOT=$(git rev-parse --show-toplevel)
cd "$CPIA_ROOT"

# 1. dump
ln -sf .env.local .env && source .env
pg_dump "$POSTGRES_URL" --table=activity_master --data-only --column-inserts \
    > /tmp/cpia_activity_master_data.sql

# 2. Chroma export
uv run python scripts/_chroma_export.py /tmp/cpia_wbs_master_export.json

# 3. homelab restore
ln -sf .env.homelab .env && source .env
psql "$POSTGRES_URL" -c "TRUNCATE activity_master;"
psql "$POSTGRES_URL" -f /tmp/cpia_activity_master_data.sql
uv run python scripts/_chroma_import.py /tmp/cpia_wbs_master_export.json

# 4. 회귀 검증
cd pipeline && uv run pytest tests/test_mapper_golden.py -v -m golden
SCRIPT
chmod +x scripts/migrate_to_homelab.sh
```

- [ ] **Step 10: Commit + 머지**

```bash
git add scripts/migrate_to_homelab.sh
git commit -m "migrate: 로컬 → homelab 마이그레이션 자동화 스크립트"
git push origin A_Track
```

---

## 미해결 사안 (이번 plan 범위 밖, mapping-layer.md §8.1 그대로 인계)

| 사안 | 후속 plan |
|---|---|
| ① FA DUCT 임베딩 매칭 실패 (R459) | doc 어휘 풍부화 — GATE 2 |
| ③ 시트1 자연어 LLM 추론 (WA 3단계) | `resolve_wa()` 의 3단계 활성화 — GATE 2 |
| ④ `mapping_corrections` 자동 적용 K=3 | H-i-L 1 누적 + Mapper feedback — GATE 3 |
| ⑦ Plan 일자 Rev.0/Rev.2 선택 | `load_master_list.py` 의 plan_start/finish 컬럼 결정 |
| Mapper 의 `mapping_corrections` lookup (자가학습) | 별도 plan — Task 6 후속 |

---

## 변경 이력

| 일자 | 변경 | 작성 |
|---|---|---|
| 2026-05-14 | 초안 — mapping-layer.md spec 기반 9 task plan | A 트랙 |
