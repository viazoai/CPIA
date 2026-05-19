"""G24 — parser_job_allocations + parser_equipment_allocations 적재 회귀.

기존엔 db.py 의 insert_*_batch 함수는 존재했지만 graph.py mapper_node 에서
호출하지 않아 두 테이블 row count = 0 이었음. 본 테스트는 함수 자체 sanity
(스키마/jsonb 적재 OK) + graph.py 호출 회귀 (source grep) 둘 다 보장.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4


async def _seed_pipeline_run(pg_client, run_id) -> None:
    async with pg_client._pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO pipeline_runs (run_id, site_id, report_date, status, started_at)
            VALUES ($1, $2, $3, $4, now())
            """,
            run_id,
            "test-g24",
            date(2025, 9, 25),
            "running",
        )


async def test_insert_parser_job_allocations_persists(pg_client, cleanup_test_rows):
    """G24 — insert_parser_job_allocations_batch 호출 시 row 적재 + jsonb 보존."""
    run_id = uuid4()
    cleanup_test_rows.append(run_id)
    await _seed_pipeline_run(pg_client, run_id)

    tsc = {"morning": 0, "daytime": 5, "overtime": 0, "night": 0, "all_night": 0, "total": 5}
    rows = [
        {
            "bp_code": "PH_X-002",
            "company": "남웅건설",
            "disc_abbrev": "건축",
            "manager_code": "Mm01",
            "worker_code": "sk01",
            "job_type": "철근공",
            "workers_yesterday_cum": tsc,
            "workers_today_incr": tsc,
            "workers_today_cum": tsc,
            "final_flag": "O",
            "workers_cum_t": 5,
        },
        {
            "bp_code": "PH_X-002",
            "company": "세보",
            "disc_abbrev": "건축",
            "manager_code": None,
            "worker_code": "sk02",
            "job_type": "거푸집공",
            "workers_yesterday_cum": tsc,
            "workers_today_incr": tsc,
            "workers_today_cum": tsc,
            "final_flag": "O",
            "workers_cum_t": 3,
        },
    ]
    await pg_client.insert_parser_job_allocations_batch(
        run_id=run_id,
        report_date=date(2025, 9, 25),
        rows=rows,
    )
    async with pg_client._pool.acquire() as con:
        cnt = await con.fetchval("SELECT COUNT(*) FROM parser_job_allocations WHERE run_id=$1", run_id)
        sample = await con.fetchrow(
            "SELECT company, job_type FROM parser_job_allocations WHERE run_id=$1 ORDER BY idx LIMIT 1",
            run_id,
        )
    assert cnt == 2
    assert sample["company"] == "남웅건설"
    assert sample["job_type"] == "철근공"


async def test_insert_parser_equipment_allocations_persists(pg_client, cleanup_test_rows):
    """G24 — insert_parser_equipment_allocations_batch 호출 시 row 적재."""
    run_id = uuid4()
    cleanup_test_rows.append(run_id)
    await _seed_pipeline_run(pg_client, run_id)

    tsc = {"morning": 0, "daytime": 1, "overtime": 0, "night": 0, "all_night": 0, "total": 1}
    rows = [
        {
            "bp_code": "PH_X-002",
            "company": "남웅건설",
            "disc_abbrev": "건축",
            "equipment_big": "크레인",
            "equipment_mid": "타워크레인",
            "equipment_spec": "T-200",
            "count_yesterday_cum": tsc,
            "count_today_incr": tsc,
            "count_today_cum": tsc,
            "final_flag": "O",
            "count_cum_t": 1,
        },
    ]
    await pg_client.insert_parser_equipment_allocations_batch(
        run_id=run_id,
        report_date=date(2025, 9, 25),
        rows=rows,
    )
    async with pg_client._pool.acquire() as con:
        cnt = await con.fetchval("SELECT COUNT(*) FROM parser_equipment_allocations WHERE run_id=$1", run_id)
        sample = await con.fetchrow(
            "SELECT equipment_big, equipment_mid FROM parser_equipment_allocations WHERE run_id=$1 LIMIT 1",
            run_id,
        )
    assert cnt == 1
    assert sample["equipment_big"] == "크레인"
    assert sample["equipment_mid"] == "타워크레인"


def test_graph_mapper_node_calls_job_and_equipment_inserts():
    """G24 회귀 — graph.py mapper_node 가 두 INSERT helper 를 호출해야 한다.

    원인: 이전엔 호출 누락 → 두 테이블 영속 row 항상 0. 본 테스트는 source
    수준에서 호출 존재 자체를 보장 (graph_e2e 통합 테스트가 LLM/Chroma 비용
    큼). 호출이 삭제되면 즉시 fail.
    """
    src = Path(__file__).resolve().parents[1] / "graph.py"
    text = src.read_text(encoding="utf-8")
    assert "insert_parser_job_allocations_batch" in text, (
        "graph.py mapper_node 가 insert_parser_job_allocations_batch 호출 누락"
    )
    assert "insert_parser_equipment_allocations_batch" in text, (
        "graph.py mapper_node 가 insert_parser_equipment_allocations_batch 호출 누락"
    )
