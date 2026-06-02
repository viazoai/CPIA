# pipeline/tests/test_db_agent_progress.py
"""(B3) upsert_agent_progress TDD — GREATEST monotonicity + total upsert.

spec 2026-06-02-cpia-0925-demo-refinement-design.md §6.2.
실 PG (POSTGRES_URL, conftest load_dotenv) 에 붙는다. agent_progress.run_id 는
FK 없음 → pipeline_runs row 불필요. fresh run_id + finally DELETE 로 멱등.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from pipeline.db import upsert_agent_progress

pytestmark = pytest.mark.asyncio

POSTGRES_URL = os.environ["POSTGRES_URL"]


async def _row(run_id: uuid.UUID, agent: str) -> asyncpg.Record | None:
    con = await asyncpg.connect(POSTGRES_URL)
    try:
        return await con.fetchrow(
            "SELECT processed, total FROM agent_progress WHERE run_id=$1 AND agent=$2",
            run_id,
            agent,
        )
    finally:
        await con.close()


async def _cleanup(run_id: uuid.UUID) -> None:
    con = await asyncpg.connect(POSTGRES_URL)
    try:
        await con.execute("DELETE FROM agent_progress WHERE run_id=$1", run_id)
    finally:
        await con.close()


async def test_insert_then_greatest_keeps_max() -> None:
    """두 번째 upsert 의 processed 가 더 작아도 GREATEST 가 max 유지, total 은 갱신."""
    run_id = uuid.uuid4()
    try:
        await upsert_agent_progress(POSTGRES_URL, run_id, "mapper", 5, 10)
        r1 = await _row(run_id, "mapper")
        assert r1 is not None
        assert r1["processed"] == 5
        assert r1["total"] == 10

        await upsert_agent_progress(POSTGRES_URL, run_id, "mapper", 3, 12)
        r2 = await _row(run_id, "mapper")
        assert r2["processed"] == 5, "GREATEST 가 out-of-order 작은 값으로 후퇴시키면 안 됨"
        assert r2["total"] == 12, "total 은 EXCLUDED 로 항상 갱신"

        await upsert_agent_progress(POSTGRES_URL, run_id, "mapper", 8, 12)
        r3 = await _row(run_id, "mapper")
        assert r3["processed"] == 8
        assert r3["total"] == 12
    finally:
        await _cleanup(run_id)


async def test_str_run_id_accepted() -> None:
    """run_id 가 str 이어도 set_current_node 처럼 정규화되어 동작."""
    run_id = uuid.uuid4()
    try:
        await upsert_agent_progress(POSTGRES_URL, str(run_id), "parser", 1, 7)
        r = await _row(run_id, "parser")
        assert r is not None
        assert r["processed"] == 1
        assert r["total"] == 7
    finally:
        await _cleanup(run_id)


async def test_swallow_on_bad_url() -> None:
    """connect 실패해도 예외 swallow (fire-and-forget) — raise 하지 않음."""
    await upsert_agent_progress("postgresql://nouser:nopass@127.0.0.1:1/nodb", uuid.uuid4(), "mapper", 1, 1)
