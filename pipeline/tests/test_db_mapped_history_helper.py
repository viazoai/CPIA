"""PGClient.insert_mapped_history_batch helper 테스트 (Phase 3 RED).

검증 항목:
  1. rows=[] 호출 시 INSERT 0건 + 예외 없음
  2. 1 row INSERT 후 SELECT 정합 검증
  3. 동일 (run_id, wa, l6_main, company) 2번 호출 시 ON CONFLICT UPDATE (today_qty 갱신)
  4. 다중 triplet (wa 다름) 일괄 INSERT + COUNT 검증

패턴: PGClient(pg_url) + await pg.connect() + try/finally pg.close()
cleanup: DELETE FROM mapped_history WHERE run_id=<test_run_id>
참조: test_db_daily_reports.py / test_db_mapping_corrections.py
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
async def test_insert_mapped_history_empty_returns(pg_url: str) -> None:
    """rows=[] 호출 시 INSERT 0건 + 예외 없음."""
    run_id = uuid.uuid4()
    pg = PGClient(pg_url)
    await pg.connect()
    try:
        await pg.insert_pipeline_run(run_id, "DEMO_SITE", "2025-09-27", "running")
        # 빈 rows — 예외 없이 즉시 반환해야 함
        await pg.insert_mapped_history_batch(
            run_id=run_id,
            report_date=date(2025, 9, 27),
            site_id="DEMO_SITE",
            rows=[],
        )
        async with pg._pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM mapped_history WHERE run_id=$1",
                run_id,
            )
        assert count == 0, f"rows=[] 인데 INSERT 발생: {count}건"
    finally:
        await pg.delete_pipeline_run(run_id)
        await pg.close()


@pytest.mark.asyncio
async def test_insert_mapped_history_single_row(pg_url: str) -> None:
    """1 row INSERT 후 SELECT 정합 검증."""
    run_id = uuid.uuid4()
    pg = PGClient(pg_url)
    await pg.connect()
    try:
        await pg.insert_pipeline_run(run_id, "DEMO_SITE", "2025-09-27", "running")
        await pg.insert_mapped_history_batch(
            run_id=run_id,
            report_date=date(2025, 9, 27),
            site_id="DEMO_SITE",
            rows=[
                {
                    "wa": "CUB",
                    "l6_main": "철근콘크리트공사",
                    "company": "남웅건설",
                    "today_qty": 12.5,
                    "today_assigned_workers": 8,
                    "unit": "m2",
                }
            ],
        )
        async with pg._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT wa, l6_main, company, today_qty, today_assigned_workers, unit
                FROM mapped_history
                WHERE run_id=$1
                """,
                run_id,
            )
        assert row is not None, "INSERT 된 row 없음"
        assert row["wa"] == "CUB"
        assert row["l6_main"] == "철근콘크리트공사"
        assert row["company"] == "남웅건설"
        assert float(row["today_qty"]) == 12.5
        assert int(row["today_assigned_workers"]) == 8
        assert row["unit"] == "m2"
    finally:
        await pg.delete_pipeline_run(run_id)
        await pg.close()


@pytest.mark.asyncio
async def test_insert_mapped_history_idempotent_on_conflict(pg_url: str) -> None:
    """동일 (run_id, wa, l6_main, company) 2번 호출 시 ON CONFLICT UPDATE (today_qty 갱신)."""
    run_id = uuid.uuid4()
    pg = PGClient(pg_url)
    await pg.connect()
    try:
        await pg.insert_pipeline_run(run_id, "DEMO_SITE", "2025-09-27", "running")
        row_first = {
            "wa": "CUB",
            "l6_main": "철근콘크리트공사",
            "company": "남웅건설",
            "today_qty": 10.0,
            "today_assigned_workers": 5,
            "unit": "m2",
        }
        row_second = {**row_first, "today_qty": 99.9, "today_assigned_workers": 7}

        await pg.insert_mapped_history_batch(
            run_id=run_id,
            report_date=date(2025, 9, 27),
            site_id="DEMO_SITE",
            rows=[row_first],
        )
        await pg.insert_mapped_history_batch(
            run_id=run_id,
            report_date=date(2025, 9, 27),
            site_id="DEMO_SITE",
            rows=[row_second],
        )

        async with pg._pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM mapped_history WHERE run_id=$1",
                run_id,
            )
            fetched = await conn.fetchrow(
                "SELECT today_qty, today_assigned_workers FROM mapped_history WHERE run_id=$1",
                run_id,
            )
        assert count == 1, f"UPSERT 인데 row 2개 생김: {count}"
        assert float(fetched["today_qty"]) == 99.9, (
            f"ON CONFLICT UPDATE 미적용: today_qty={fetched['today_qty']}"
        )
        assert int(fetched["today_assigned_workers"]) == 7
    finally:
        await pg.delete_pipeline_run(run_id)
        await pg.close()


@pytest.mark.asyncio
async def test_insert_mapped_history_batch_multiple_triplets(pg_url: str) -> None:
    """다중 triplet (wa 다름) 일괄 INSERT + COUNT 검증."""
    run_id = uuid.uuid4()
    pg = PGClient(pg_url)
    await pg.connect()
    try:
        await pg.insert_pipeline_run(run_id, "DEMO_SITE", "2025-09-27", "running")
        rows = [
            {
                "wa": "CUB",
                "l6_main": "철근콘크리트공사",
                "company": "남웅건설",
                "today_qty": 10.0,
                "today_assigned_workers": 5,
                "unit": "m2",
            },
            {
                "wa": "STL",
                "l6_main": "철골공사",
                "company": "삼성물산",
                "today_qty": 3.0,
                "today_assigned_workers": 2,
                "unit": "ton",
            },
            {
                "wa": "FIN",
                "l6_main": "마감공사",
                "company": "대우건설",
                "today_qty": 50.0,
                "today_assigned_workers": 10,
                "unit": "m2",
            },
        ]
        await pg.insert_mapped_history_batch(
            run_id=run_id,
            report_date=date(2025, 9, 27),
            site_id="DEMO_SITE",
            rows=rows,
        )
        async with pg._pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM mapped_history WHERE run_id=$1",
                run_id,
            )
        assert count == 3, f"3건 INSERT 기대, 실제: {count}"
    finally:
        await pg.delete_pipeline_run(run_id)
        await pg.close()
