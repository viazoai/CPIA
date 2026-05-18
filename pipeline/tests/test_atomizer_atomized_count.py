from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_atomizer_update_helper_exists_and_updates(pg_client, cleanup_test_rows):
    """G5 회귀 방지 — pg.update_run_atomized_count 가 존재하고 정상 UPDATE."""
    run_id = uuid4()
    cleanup_test_rows.append(run_id)
    # 사전: pipeline_runs row
    async with pg_client._pool.acquire() as con:
        await con.execute(
            "INSERT INTO pipeline_runs (run_id, site_id, report_date, status, started_at) VALUES ($1, $2, $3, $4, now())",
            run_id,
            "test-atomizer",
            date(2025, 9, 25),
            "running",
        )
    await pg_client.update_run_atomized_count(run_id, 42)
    async with pg_client._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT atomized_count FROM pipeline_runs WHERE run_id = $1",
            run_id,
        )
    assert row["atomized_count"] == 42
