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

POSTGRES_URL = os.environ["POSTGRES_URL"]


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
    async with pg._pool.acquire() as con:
        await con.execute(
            "DELETE FROM consolidated_reports WHERE site_id=$1 AND report_date=$2",
            site_id,
            report_date,
        )
    await upsert_consolidated_report(
        pg,
        site_id=site_id,
        report_date=report_date,
        xlsx_bytes=b"FAKE-XLSX-A",
        run_id=run_id,
    )
    async with pg._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT xlsx_bytes, run_id, byte_size FROM consolidated_reports WHERE site_id=$1 AND report_date=$2",
            site_id,
            report_date,
        )
    assert row is not None
    assert row["xlsx_bytes"] == b"FAKE-XLSX-A"
    assert row["run_id"] == run_id
    assert row["byte_size"] == len(b"FAKE-XLSX-A")


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
            site_id,
            report_date,
        )
    await upsert_consolidated_report(
        pg,
        site_id=site_id,
        report_date=report_date,
        xlsx_bytes=b"FAKE-A",
        run_id=run_id_a,
    )
    await upsert_consolidated_report(
        pg,
        site_id=site_id,
        report_date=report_date,
        xlsx_bytes=b"FAKE-B-LONGER",
        run_id=run_id_b,
    )
    async with pg._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT xlsx_bytes, run_id, byte_size FROM consolidated_reports WHERE site_id=$1 AND report_date=$2",
            site_id,
            report_date,
        )
    assert row["xlsx_bytes"] == b"FAKE-B-LONGER"
    assert row["run_id"] == run_id_b
    assert row["byte_size"] == len(b"FAKE-B-LONGER")


async def test_fetch_hit(pg: PGClient) -> None:
    """존재하면 bytes 반환."""
    site_id = "m15x-ph3-ibl"
    report_date = _date(2025, 9, 25)
    run_id = uuid.uuid4()
    await _make_pipeline_run(pg, run_id, site_id)
    async with pg._pool.acquire() as con:
        await con.execute(
            "DELETE FROM consolidated_reports WHERE site_id=$1 AND report_date=$2",
            site_id,
            report_date,
        )
    await upsert_consolidated_report(
        pg,
        site_id=site_id,
        report_date=report_date,
        xlsx_bytes=b"HIT-PATH-BYTES",
        run_id=run_id,
    )
    got = await fetch_consolidated_report(pg, site_id=site_id, report_date=report_date)
    assert got == b"HIT-PATH-BYTES"


async def test_fetch_miss(pg: PGClient) -> None:
    """미존재 시 None."""
    nonexistent_site = "no-such-site-zzz"
    got = await fetch_consolidated_report(
        pg,
        site_id=nonexistent_site,
        report_date=_date(1999, 1, 1),
    )
    assert got is None


async def test_fk_violation_no_site(pg: PGClient) -> None:
    """site_id FK 위반 시 IntegrityError raise."""
    import asyncpg.exceptions

    # run_id 는 먼저 valid 하게 만든다 (pipeline_runs FK 는 site 가 valid 해야 INSERT 가능 →
    # 미리 m15x-ph3-ibl 로 run 을 만들고, 그 run_id 를 재사용). 이러면 upsert 시점에
    # 위반되는 FK 는 site_id 단 하나로 확정 — 결정성 보장.
    run_id = uuid.uuid4()
    await _make_pipeline_run(pg, run_id, "m15x-ph3-ibl")
    with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
        await upsert_consolidated_report(
            pg,
            site_id="no-such-site-zzz",
            report_date=_date(2025, 9, 25),
            xlsx_bytes=b"X",
            run_id=run_id,
        )
