"""G19 회귀 테스트 — parser/mapper INSERT 가 신규 13 컬럼 적재 보장.

CPIA 2026-05-19 통합 작업일보 풀 스키마 확장에서 추가된 13 컬럼:
    zone, bp_code, scope,
    yesterday_cum_qty, today_cum_qty,
    progress_percent, remaining_qty, remaining_percent,
    note, work_location_code,
    wbs_mid_name, wbs_sub_name, wbs_detail_name.

회귀 방지: INSERT SQL 또는 values tuple 에서 13 컬럼이 누락되면 즉시 fail.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest


async def _seed_pipeline_run(pg_client, run_id) -> None:
    """FK 무관하지만 run_id 일관성을 위해 pipeline_runs row 선행 적재."""
    async with pg_client._pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO pipeline_runs (run_id, site_id, report_date, status, started_at)
            VALUES ($1, $2, $3, $4, now())
            """,
            run_id,
            "test-g19",
            date(2025, 9, 25),
            "running",
        )


async def test_insert_parser_activities_persists_new_13_columns(pg_client, cleanup_test_rows):
    """G19 — parser_activities INSERT 가 신규 13 컬럼 모두 적재."""
    run_id = uuid4()
    cleanup_test_rows.append(run_id)
    await _seed_pipeline_run(pg_client, run_id)

    activities = [
        {
            "l5_disc": "건축",
            "trade": "건축",
            "company": "남웅건설",
            "unit": "m2",
            "today_qty": 100.0,
            "work_content": "거푸집 설치",
            "plan_total_qty": 1500.0,
            # 신규 13 컬럼
            "zone": "CUB",
            "bp_code": "PH_X-002",
            "scope": "F02 1F",
            "yesterday_cum_qty": 80.0,
            "today_cum_qty": 180.0,
            "progress_percent": 12.0,
            "remaining_qty": 1320.0,
            "remaining_percent": 88.0,
            "note": "우천 대응",
            "work_location_code": "CUB-F02",
            "wbs_mid_name": "철근콘크리트공사",
            "wbs_sub_name": "거푸집공사",
            "wbs_detail_name": "벽체 거푸집",
        }
    ]
    await pg_client.insert_parser_activities_batch(
        run_id=run_id,
        report_date=date(2025, 9, 25),
        activities=activities,
    )

    async with pg_client._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT * FROM parser_activities WHERE run_id = $1 ORDER BY idx LIMIT 1",
            run_id,
        )
    assert row is not None
    assert row["zone"] == "CUB"
    assert row["bp_code"] == "PH_X-002"
    assert row["scope"] == "F02 1F"
    assert float(row["yesterday_cum_qty"]) == pytest.approx(80.0)
    assert float(row["today_cum_qty"]) == pytest.approx(180.0)
    assert float(row["progress_percent"]) == pytest.approx(12.0)
    assert float(row["remaining_qty"]) == pytest.approx(1320.0)
    assert float(row["remaining_percent"]) == pytest.approx(88.0)
    assert row["note"] == "우천 대응"
    assert row["work_location_code"] == "CUB-F02"
    assert row["wbs_mid_name"] == "철근콘크리트공사"
    assert row["wbs_sub_name"] == "거푸집공사"
    assert row["wbs_detail_name"] == "벽체 거푸집"


async def test_insert_mapper_activities_persists_new_13_columns(pg_client, cleanup_test_rows):
    """G19 — mapper_activities INSERT 가 신규 13 컬럼 모두 적재."""
    run_id = uuid4()
    cleanup_test_rows.append(run_id)
    await _seed_pipeline_run(pg_client, run_id)

    activities = [
        {
            "company": "남웅건설",
            "trade": "건축",
            "unit": "m2",
            "today_qty": 100.0,
            "wa": "CUB",
            "l6_main": "철근콘크리트공사",
            "mapping_conf": 0.85,
            "mapping_source": "auto",
            "requires_review": False,
            "assigned_workers": 8.0,
            "worker_source": "mh",
            "plan_total_qty": 1500.0,
            "plan_mh": 456.0,
            "conditions": [],
            # 신규 13 컬럼
            "zone": "CUB",
            "bp_code": "PH_X-002",
            "scope": "F02 1F",
            "yesterday_cum_qty": 80.0,
            "today_cum_qty": 180.0,
            "progress_percent": 12.0,
            "remaining_qty": 1320.0,
            "remaining_percent": 88.0,
            "note": "우천 대응",
            "work_location_code": "CUB-F02",
            "wbs_mid_name": "철근콘크리트공사",
            "wbs_sub_name": "거푸집공사",
            "wbs_detail_name": "벽체 거푸집",
        }
    ]
    await pg_client.insert_mapper_activities_batch(
        run_id=run_id,
        report_date=date(2025, 9, 25),
        activities=activities,
    )

    async with pg_client._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT * FROM mapper_activities WHERE run_id = $1 ORDER BY idx LIMIT 1",
            run_id,
        )
    assert row is not None
    assert row["zone"] == "CUB"
    assert row["bp_code"] == "PH_X-002"
    assert row["scope"] == "F02 1F"
    assert float(row["yesterday_cum_qty"]) == pytest.approx(80.0)
    assert float(row["today_cum_qty"]) == pytest.approx(180.0)
    assert float(row["progress_percent"]) == pytest.approx(12.0)
    assert float(row["remaining_qty"]) == pytest.approx(1320.0)
    assert float(row["remaining_percent"]) == pytest.approx(88.0)
    assert row["note"] == "우천 대응"
    assert row["work_location_code"] == "CUB-F02"
    assert row["wbs_mid_name"] == "철근콘크리트공사"
    assert row["wbs_sub_name"] == "거푸집공사"
    assert row["wbs_detail_name"] == "벽체 거푸집"
