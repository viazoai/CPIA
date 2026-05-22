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
    await insert_collector_inbox(
        pg,
        message_id=mid,
        site_id="m15x-ph3-ibl",
        report_date=date(2025, 9, 26),
        bp_name="x",
        attachment_filename="x.xlsx",
        attachment_path="/tmp/x.xlsx",
    )
    await update_collector_inbox_status(pg, mid, parse_status="failed", error="boom")
    row = await fetch_collector_inbox_by_message_id(pg, mid)
    assert row["parse_status"] == "failed"
    assert row["error"] == "boom"

    async with pg._pool.acquire() as con:
        await con.execute("DELETE FROM collector_inbox WHERE message_id=$1", mid)


async def test_fetch_site_by_id_ok(pg: PGClient) -> None:
    site = await fetch_site_by_id(pg, "m15x-ph3-ibl")
    if site is None:
        pytest.skip("m15x-ph3-ibl 시드 미적용")
    assert site["site_id"] == "m15x-ph3-ibl"
    assert "name" in site


async def test_fetch_site_by_id_missing(pg: PGClient) -> None:
    site = await fetch_site_by_id(pg, "nonexistent-site-xyz")
    assert site is None
