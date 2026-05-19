from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_update_site_last_run_sets_run_id(pg_client, cleanup_test_rows):
    """G8 — update_site_last_run() 호출 시 sites.last_run_id 갱신."""
    from pipeline.db import update_site_last_run

    run_id = uuid4()
    cleanup_test_rows.append(run_id)
    site_id = "test-g8"
    # 사전: sites row + pipeline_runs row (sites.last_run_id FK 존재).
    async with pg_client._pool.acquire() as con:
        await con.execute("DELETE FROM sites WHERE site_id = $1", site_id)
        await con.execute(
            "INSERT INTO sites (site_id, name, is_mock) VALUES ($1, $2, true)",
            site_id,
            "Test G8",
        )
        await con.execute(
            "INSERT INTO pipeline_runs (run_id, site_id, report_date, status, started_at) VALUES ($1, $2, $3, $4, now())",
            run_id,
            site_id,
            date(2025, 9, 25),
            "running",
        )

    await update_site_last_run(pg_client, site_id=site_id, run_id=run_id)

    async with pg_client._pool.acquire() as con:
        row = await con.fetchrow("SELECT last_run_id FROM sites WHERE site_id=$1", site_id)
    assert row["last_run_id"] == run_id
