"""db.py insert_forecast $29 placeholder 통합 test — 실 AWS PG.

point_in_time_delay_days 컬럼이 dict → PG 까지 정확히 영속되는지 검증.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from pipeline.db import PGClient

DSN = "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia"


@pytest.mark.asyncio
async def test_insert_forecast_point_in_time_persists():
    """Insert forecast row with point_in_time_delay_days=7, then SELECT and verify."""
    pg = PGClient(DSN)
    await pg.connect()
    try:
        # 1. 임시 pipeline_runs row 생성 (FK 충족용)
        run_id = uuid.uuid4()
        async with pg._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO pipeline_runs (run_id, site_id, report_date, status, started_at)
                VALUES ($1, $2, $3, 'completed', NOW())
                """,
                run_id,
                "test-site-v10",
                date(2025, 6, 15),
            )

        # 2. insert_forecast with point_in_time_delay_days=7
        await pg.insert_forecast(
            {
                "run_id": run_id,
                "company": "test-co",
                "l6_main": "test-wp",
                "today_qty_by_unit": [{"unit": "ea", "qty": 1.0}],
                "today_assigned_workers": 1.0,
                "today_productivity": 0.5,
                "plan_total_qty_by_unit": [{"unit": "ea", "qty": 30.0}],
                "plan_mh_sum": 100.0,
                "plan_start": date(2025, 6, 1),
                "plan_finish": date(2025, 6, 30),
                "plan_mh_per_day": 3.33,
                "schedule_state": "on_schedule",
                "window_start": date(2025, 6, 1),
                "window_days": 14,
                "expected_in_window_mh": 46.6,
                "actual_in_window_mh": 50.0,
                "mh_gap": -3.4,
                "delay_days": 0,
                "rag_n_similar": 5,
                "similar_cases": [],
                "assessment": "정상",
                "reasoning": "test",
                "recovery_likelihood": 0.8,
                "expected_completion": date(2025, 6, 30),
                "risk_level": "정상",
                "main_unit": "ea",
                "today_conditions": "정상",
                "wa": "토목-01",
                "point_in_time_delay_days": 7,  # 신규 $29
            }
        )

        # 3. SELECT 검증
        async with pg._pool.acquire() as conn:
            r = await conn.fetchrow(
                "SELECT point_in_time_delay_days FROM forecasts WHERE run_id=$1",
                run_id,
            )
            assert r is not None, "forecasts row 미적재"
            assert r["point_in_time_delay_days"] == 7, f"기대 7, 실제 {r['point_in_time_delay_days']}"
    finally:
        # cleanup
        async with pg._pool.acquire() as conn:
            await conn.execute("DELETE FROM forecasts WHERE run_id=$1", run_id)
            await conn.execute("DELETE FROM pipeline_runs WHERE run_id=$1", run_id)
        await pg.close()


@pytest.mark.asyncio
async def test_insert_forecast_point_in_time_none_safe():
    """None / 미전달 시 NULL 영속 — backwards compat 안전망."""
    pg = PGClient(DSN)
    await pg.connect()
    try:
        run_id = uuid.uuid4()
        async with pg._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO pipeline_runs (run_id, site_id, report_date, status, started_at) VALUES ($1, $2, $3, 'completed', NOW())",
                run_id,
                "test-site-v10-none",
                date(2025, 6, 15),
            )
        # point_in_time_delay_days key 누락
        await pg.insert_forecast(
            {
                "run_id": run_id,
                "company": "test-co",
                "l6_main": "test-wp",
                "today_qty_by_unit": [],
                "today_assigned_workers": 0.0,
                "today_productivity": 0.0,
                "plan_total_qty_by_unit": [],
                "plan_mh_sum": 0.0,
                "plan_start": None,
                "plan_finish": None,
                "plan_mh_per_day": None,
                "schedule_state": "unknown",
                "window_start": None,
                "window_days": 0,
                "expected_in_window_mh": None,
                "actual_in_window_mh": 0.0,
                "mh_gap": None,
                "delay_days": None,
                "rag_n_similar": 0,
                "similar_cases": [],
                "assessment": None,
                "reasoning": None,
                "recovery_likelihood": None,
                "expected_completion": None,
                "risk_level": None,
                "main_unit": None,
                "today_conditions": None,
                "wa": None,
            }
        )
        async with pg._pool.acquire() as conn:
            r = await conn.fetchrow(
                "SELECT point_in_time_delay_days FROM forecasts WHERE run_id=$1",
                run_id,
            )
            assert r is not None
            assert r["point_in_time_delay_days"] is None
    finally:
        async with pg._pool.acquire() as conn:
            await conn.execute("DELETE FROM forecasts WHERE run_id=$1", run_id)
            await conn.execute("DELETE FROM pipeline_runs WHERE run_id=$1", run_id)
        await pg.close()
