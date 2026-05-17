"""PGClient.insert_daily_report 테스트.

실 schema (infra/postgres/init.sql:33) = id, run_id, report_date, bp_name (nullable),
report_md, history_csv_row (jsonb, nullable), created_at — 7 컬럼.
postgres.md §5 의 'date' / 'summary' 필드명은 init.sql/실 PG 와 mismatch
(drift backlog 별 cycle). 본 cycle = code-only → 실 schema 정합 signature.

종합 보고서 (Reporter 위치 = Optimizer 다음 drift) → bp_name=None.
summary dict (total_workers / risk_counts / advice_count) 는 history_csv_row 컬럼에 박음.
"""

from __future__ import annotations

import json
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
async def test_insert_daily_report_roundtrip(pg_url: str) -> None:
    """insert_daily_report 1 row INSERT 후 SELECT 정합 검증."""
    run_id = uuid.uuid4()
    pg = PGClient(pg_url)
    await pg.connect()
    try:
        await pg.insert_pipeline_run(run_id, "DEMO_SITE", "2025-09-27", "running")
        await pg.insert_daily_report(
            run_id=run_id,
            report_date=date(2025, 9, 27),
            report_md="# 2025-09-27 작업일보 종합 보고서\n\n테스트 본문.",
            history_csv_row={
                "total_workers": 50.0,
                "risk_counts": {"정상": 2, "주의": 1, "이상": 0},
                "advice_count": 1,
            },
            bp_name=None,
        )
        async with pg._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT report_md, history_csv_row, bp_name FROM daily_reports WHERE run_id=$1",
                run_id,
            )
        assert row is not None
        assert "2025-09-27" in row["report_md"]
        assert row["bp_name"] is None
        hist = (
            json.loads(row["history_csv_row"])
            if isinstance(row["history_csv_row"], str)
            else row["history_csv_row"]
        )
        assert hist["total_workers"] == 50.0
        assert hist["risk_counts"]["주의"] == 1
        assert hist["advice_count"] == 1
    finally:
        await pg.delete_pipeline_run(run_id)
        await pg.close()
