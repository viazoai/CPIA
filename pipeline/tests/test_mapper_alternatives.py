"""G23 — mapper INSERT 가 alternatives jsonb 컬럼 (RAG top-K 후보) 을 적재.

FE review 페이지의 "대안 WP 후보 dropdown" 데이터 소스. 컬럼 자체는
2026-05-19 migration `add_mapper_alternatives.sql` 로 추가 (jsonb DEFAULT '[]').
"""

from __future__ import annotations

import json
from datetime import date
from uuid import uuid4


async def _seed_pipeline_run(pg_client, run_id) -> None:
    async with pg_client._pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO pipeline_runs (run_id, site_id, report_date, status, started_at)
            VALUES ($1, $2, $3, $4, now())
            """,
            run_id,
            "test-g23",
            date(2025, 9, 25),
            "running",
        )


async def test_insert_mapper_persists_alternatives_jsonb(pg_client, cleanup_test_rows):
    """G23 — insert_mapper_activities_batch 가 alternatives jsonb 컬럼에 top-K 후보 적재."""
    run_id = uuid4()
    cleanup_test_rows.append(run_id)
    await _seed_pipeline_run(pg_client, run_id)

    alts = [
        {"wa": "CUB", "l6_main": "철근콘크리트공사", "score": 0.85},
        {"wa": "CUB", "l6_main": "거푸집공사", "score": 0.62},
        {"wa": "FAB", "l6_main": "철근콘크리트공사", "score": 0.41},
    ]
    activities = [
        {
            "company": "남웅건설",
            "trade": "건축",
            "unit": "m2",
            "today_qty": 100.0,
            "wa": "CUB",
            "l6_main": "철근콘크리트공사",
            "mapping_conf": 0.85,
            "mapping_source": "auto_sheet1_text",
            "requires_review": False,
            "assigned_workers": 8.0,
            "worker_source": "mh_prorated",
            "plan_total_qty": 1500.0,
            "plan_mh": 456.0,
            "conditions": [],
            "alternatives": alts,
        }
    ]
    await pg_client.insert_mapper_activities_batch(
        run_id=run_id,
        report_date=date(2025, 9, 25),
        activities=activities,
    )

    async with pg_client._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT alternatives FROM mapper_activities WHERE run_id=$1 ORDER BY idx LIMIT 1",
            run_id,
        )
    assert row is not None
    saved = row["alternatives"]
    # asyncpg jsonb 는 driver 설정에 따라 dict/list 또는 str 으로 받음.
    if isinstance(saved, str):
        saved = json.loads(saved)

    assert isinstance(saved, list)
    assert len(saved) == 3
    assert saved[0]["wa"] == "CUB"
    assert saved[0]["l6_main"] == "철근콘크리트공사"
    assert float(saved[0]["score"]) == 0.85
    # score 내림차순 보존
    assert float(saved[0]["score"]) >= float(saved[1]["score"]) >= float(saved[2]["score"])
