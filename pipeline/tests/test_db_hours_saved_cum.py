from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_hours_saved_cum_accumulates(pg_client):
    """G2 — atomized_count × (AS_IS_MIN - TO_BE_MIN) / 60 시간 만큼 누적."""
    from pipeline.db import update_site_hours_saved_cum

    site_id = "test-g2"
    async with pg_client._pool.acquire() as con:
        await con.execute("DELETE FROM sites WHERE site_id = $1", site_id)
        await con.execute(
            "INSERT INTO sites (site_id, name, is_mock, hours_saved_cum) VALUES ($1, $2, true, 10.0)",
            site_id,
            "Test G2",
        )

    # atomized_count=12 → delta = (120-5)/60 * 12 = 23.0 h. 누적 = 10 + 23 = 33
    await update_site_hours_saved_cum(pg_client, site_id=site_id, atomized_count=12)

    async with pg_client._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT hours_saved_cum FROM sites WHERE site_id = $1",
            site_id,
        )
    assert float(row["hours_saved_cum"]) == pytest.approx(33.0, rel=1e-3)

    # cleanup
    async with pg_client._pool.acquire() as con:
        await con.execute("DELETE FROM sites WHERE site_id = $1", site_id)
