from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

# 상대 경로 import 보정
sys.path.insert(0, str(Path(__file__).parent.parent))
from db import PGClient


@pytest.fixture
async def pg() -> PGClient:
    """PostgreSQL 클라이언트 fixture — 테스트 함수 생명주기."""
    url = os.environ.get("POSTGRES_URL")
    if not url:
        pytest.skip("POSTGRES_URL 환경변수 없음")
    client = PGClient(url)
    await client.connect()
    yield client
    await client.close()


async def test_bp_candidate_lookup_namwung(pg: PGClient):
    """남웅건설 BP filter → (WA, L6) 후보 — Master 적재 전이면 빈 결과 (SKIP 아님)."""
    rows = await pg.fetch_bp_candidates("남웅건설")
    keys = {(r["wa"], r["l6_main"]) for r in rows}
    # Master 적재 후 (Task 5) 다음 키들이 포함되어야 함
    if not keys:
        pytest.skip("activity_master 적재 전 (Task 5 후 재검증)")
    assert ("CUB", "철근콘크리트공사") in keys
    assert ("FAB", "철근콘크리트공사") in keys


async def test_activity_lookup_by_id(pg: PGClient):
    """wbs_activity_id 로 Plan 값 조회 — Master 적재 전이면 SKIP."""
    row = await pg.fetch_activity("TNMCB1F6501A03030032")
    if row is None:
        pytest.skip("activity_master 적재 안 됨 (Task 5 후 재실행)")
    assert row["company"] == "남웅건설"
    assert row["plan_mh_rev2"] is not None


# ── fetch_l6_plan_mh_map ──────────────────────────────────────────


@pytest.mark.slow
async def test_fetch_l6_plan_mh_map_namwong(pg: PGClient):
    """남웅건설 단일 l6 — spec 3.4 기준값 1,676,807."""
    result = await pg.fetch_l6_plan_mh_map("남웅건설", ["철근콘크리트공사"])
    assert result == {"철근콘크리트공사": 1_676_807}


@pytest.mark.slow
async def test_fetch_l6_plan_mh_map_sebo_multi(pg: PGClient):
    """세보엠이씨 멀티 l6 — spec 3.4 top 3 검증."""
    l6_list = ["기계소화설비", "일반공조설비공사", "냉동기설비공사"]
    result = await pg.fetch_l6_plan_mh_map("세보엠이씨", l6_list)
    assert result["기계소화설비"] == 744_043
    assert result["일반공조설비공사"] == 708_154
    assert result["냉동기설비공사"] == 268_341


@pytest.mark.slow
async def test_fetch_l6_plan_mh_map_empty_list(pg: PGClient):
    """l6_list = [] -> {} 빈 dict."""
    result = await pg.fetch_l6_plan_mh_map("남웅건설", [])
    assert result == {}


@pytest.mark.slow
async def test_fetch_l6_plan_mh_map_unknown_company(pg: PGClient):
    """미등록 BP사 -> {} 빈 dict."""
    result = await pg.fetch_l6_plan_mh_map("ZZZ_unknown_BP", ["철근콘크리트공사"])
    assert result == {}


# ── insert / delete pipeline_run ──────────────────────────────────


@pytest.mark.slow
async def test_insert_delete_pipeline_run(pg: PGClient):
    """insert_pipeline_run + delete_pipeline_run 왕복."""
    run_id = uuid.uuid4()
    await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
    async with pg._pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT run_id FROM pipeline_runs WHERE run_id=$1",
            run_id,
        )
    assert row is not None
    await pg.delete_pipeline_run(run_id)
    async with pg._pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT run_id FROM pipeline_runs WHERE run_id=$1",
            run_id,
        )
    assert row is None


# ── update_run_atomized_count ─────────────────────────────────────


@pytest.mark.slow
async def test_update_run_atomized_count_happy(pg: PGClient):
    """pipeline_runs row 사전 INSERT -> atomized_count UPDATE 성공."""
    run_id = uuid.uuid4()
    await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
    try:
        await pg.update_run_atomized_count(run_id, 48)
        async with pg._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT atomized_count, current_node FROM pipeline_runs WHERE run_id=$1",
                run_id,
            )
        assert row["atomized_count"] == 48
        assert row["current_node"] == "atomizer"
    finally:
        await pg.delete_pipeline_run(run_id)


@pytest.mark.slow
async def test_update_run_atomized_count_missing_row_raises(pg: PGClient):
    """pipeline_runs row 미존재 -> RuntimeError."""
    fake_id = uuid.uuid4()
    with pytest.raises(RuntimeError, match="pipeline_runs.*미존재"):
        await pg.update_run_atomized_count(fake_id, 48)
