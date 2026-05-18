"""공용 pytest fixtures — DB·Chroma 연결, Master List 로드."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import UUID

import pytest
from dotenv import load_dotenv

CPIA_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(CPIA_ROOT / ".env")

# scripts/ 모듈 import 를 위해 project root 를 sys.path 에 추가.
if str(CPIA_ROOT) not in sys.path:
    sys.path.insert(0, str(CPIA_ROOT))

from pipeline.db import PGClient  # noqa: E402


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
    keys = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION",
        "LLM_MODEL",
        "EMBEDDING_MODEL",
    ]
    env = {k: os.environ.get(k, "") for k in keys}
    if not all(env.values()):
        pytest.skip(f"Azure OpenAI env 누락: {[k for k, v in env.items() if not v]}")
    return env


@pytest.fixture
async def pg_client():
    """실 PG (cloudflared 5532) connection. 테스트 끝나면 close."""
    pg = PGClient(
        os.environ.get(
            "POSTGRES_URL",
            "postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia",
        )
    )
    await pg.connect()
    try:
        yield pg
    finally:
        await pg.close()


@pytest.fixture
async def cleanup_test_rows(pg_client):
    """테스트 run_id 기반 cleanup. test_run_ids 리스트에 추가하면 끝나고 삭제.

    PGClient 는 raw execute helper 가 없어 내부 _pool 로 직접 DELETE.
    """
    test_run_ids: list[UUID] = []
    yield test_run_ids
    assert pg_client._pool is not None
    async with pg_client._pool.acquire() as con:
        for run_id in test_run_ids:
            for table in (
                "parser_activities",
                "mapper_activities",
                "parser_reports",
                "parser_job_allocations",
                "parser_equipment_allocations",
                "pipeline_runs",
            ):
                try:
                    await con.execute(f"DELETE FROM {table} WHERE run_id = $1", run_id)
                except Exception:
                    pass
        # sites test row cleanup (테스트가 만든 'test-' 접두 site_id 정리)
        try:
            await con.execute("DELETE FROM sites WHERE site_id LIKE 'test-%'")
        except Exception:
            pass
