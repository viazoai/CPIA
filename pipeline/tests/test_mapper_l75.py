from __future__ import annotations
import pytest
import uuid
import datetime
from pipeline.db import PGClient
import os

PG = os.environ["POSTGRES_URL"]


@pytest.mark.asyncio
async def test_l75_columns_roundtrip():
    pg = PGClient(PG)
    await pg.connect()
    run_id = uuid.uuid4()
    try:
        await pg.insert_pipeline_run(run_id, "m15x-ph3-ibl", "2025-09-25", "running")
        act = {
            "company": "T",
            "trade": "건축",
            "unit": "m2",
            "today_qty": 1.0,
            "wa": "FAB",
            "l6_main": "수장공사",
            "l7_5_activity": "경량벽체 설치",
            "l75_conf": 0.92,
            "l7_5_alternatives": [{"label": "경량벽체 설치", "score": 0.92}],
            "requires_review": False,
        }
        await pg.insert_mapper_activities_batch(run_id, datetime.date(2025, 9, 25), [act])
        rows = await pg.fetch_all(
            "SELECT l75_conf, l7_5_alternatives FROM mapper_activities WHERE run_id=$1",
            run_id,
        )
        assert rows, "row not inserted"
        assert float(rows[0]["l75_conf"]) == 0.92
        import json as _j

        alts = rows[0]["l7_5_alternatives"]
        alts = _j.loads(alts) if isinstance(alts, str) else alts
        assert alts[0]["label"] == "경량벽체 설치"
    finally:
        await pg.fetch_all("DELETE FROM mapper_activities WHERE run_id=$1", run_id)
        await pg.delete_pipeline_run(run_id)
        await pg.close()
