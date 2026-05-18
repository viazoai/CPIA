"""PGClient.get_pipeline_run helper 테스트 (Phase 3 fix).

검증 항목:
  1. 존재하는 run_id 조회 시 dict 반환 + 필드 타입 검증
  2. 존재하지 않는 run_id 조회 시 None 반환
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest

from pipeline.db import PGClient


@pytest.fixture
def pg_url() -> str:
    url = os.environ.get("POSTGRES_URL")
    if not url:
        pytest.skip("POSTGRES_URL 환경변수 누락")
    return url


@pytest.mark.asyncio
async def test_get_pipeline_run_existing(pg_url: str) -> None:
    """존재하는 run_id 조회 시 dict 반환 + report_date 가 datetime.date 타입임을 검증."""
    run_id = uuid.uuid4()
    pg = PGClient(pg_url)
    await pg.connect()
    try:
        await pg.insert_pipeline_run(run_id, "m15x-ph3-ibl", "2025-09-25", "running")
        result = await pg.get_pipeline_run(run_id)
        assert result is not None, "row 가 존재해야 하나 None 반환"
        assert result["site_id"] == "m15x-ph3-ibl"
        assert isinstance(result["report_date"], date), (
            f"asyncpg 가 datetime.date 반환해야 하나 {type(result['report_date'])} 반환"
        )
        assert result["run_id"] == run_id
    finally:
        await pg.delete_pipeline_run(run_id)
        await pg.close()


@pytest.mark.asyncio
async def test_get_pipeline_run_missing(pg_url: str) -> None:
    """존재하지 않는 run_id 조회 시 None 반환을 검증."""
    non_existent = uuid.uuid4()
    pg = PGClient(pg_url)
    await pg.connect()
    try:
        result = await pg.get_pipeline_run(non_existent)
        assert result is None, f"미존재 run_id 인데 None 이 아닌 {result} 반환"
    finally:
        await pg.close()
