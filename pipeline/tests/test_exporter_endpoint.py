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
