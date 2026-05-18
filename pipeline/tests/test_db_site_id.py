"""Task 1 — activity_master.site_id migration 검증.

Spec: infra/postgres/migrations/2026-05-17_activity_master_site_id.sql
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from db import PGClient


@pytest.fixture
async def pg() -> PGClient:
    url = os.environ.get("POSTGRES_URL")
    if not url:
        pytest.skip("POSTGRES_URL 환경변수 없음")
    client = PGClient(url)
    await client.connect()
    yield client
    await client.close()


async def test_activity_master_has_site_id_column(pg: PGClient):
    """activity_master 에 site_id 컬럼 존재 + NOT NULL."""
    assert pg._pool is not None
    async with pg._pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'activity_master' AND column_name = 'site_id'
            """
        )
    assert row is not None, "site_id 컬럼 미존재 (migration 2026-05-17_activity_master_site_id.sql 미적용)"
    assert row["data_type"] == "text"
    assert row["is_nullable"] == "NO"


async def test_activity_master_pkey_is_composite(pg: PGClient):
    """PRIMARY KEY = (site_id, wbs_activity_id) 복합 — 같은 wbs_activity_id 가 다른 site 에 가능."""
    assert pg._pool is not None
    async with pg._pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT a.attname, array_position(i.indkey::int[], a.attnum::int) AS pos
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = 'activity_master'::regclass AND i.indisprimary
            ORDER BY pos
            """
        )
    cols = [r["attname"] for r in rows]
    assert cols == ["site_id", "wbs_activity_id"], f"PK = {cols} (예상 [site_id, wbs_activity_id])"


async def test_activity_master_site_indexes_exist(pg: PGClient):
    """site_id 기반 인덱스 3개 — Mapper / WBSTree / 기간 필터 용."""
    assert pg._pool is not None
    async with pg._pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'activity_master' AND indexname LIKE 'idx_actmaster_site%'
            """
        )
    names = {r["indexname"] for r in rows}
    assert "idx_actmaster_site_company" in names
    assert "idx_actmaster_site_l6" in names
    assert "idx_actmaster_site_period" in names


async def test_activity_master_existing_rows_backfilled(pg: PGClient):
    """기존 row 는 site_id='m15x-ph3-ibl' 로 backfill 됐어야 함."""
    assert pg._pool is not None
    async with pg._pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT site_id, COUNT(*) AS n FROM activity_master GROUP BY site_id ORDER BY site_id"
        )
    if not rows:
        pytest.skip("activity_master 빈 (TRUNCATE 후 재적재 대기)")
    site_ids = {r["site_id"] for r in rows}
    assert "m15x-ph3-ibl" in site_ids, f"backfill 실패 — site_ids = {site_ids}"


# ── Task 2 — db.py 4 함수의 site_id 인자 ───────────────────────────


async def test_fetch_bp_candidates_with_site_id(pg: PGClient):
    """site_id='m15x-ph3-ibl' 명시 → 기존 1059 row 와 동일 결과."""
    rows_all = await pg.fetch_bp_candidates("남웅건설")
    rows_site = await pg.fetch_bp_candidates("남웅건설", site_id="m15x-ph3-ibl")
    if not rows_all:
        pytest.skip("activity_master 적재 안 됨")
    assert rows_all == rows_site, "현재 유일 적재 site 라서 결과 동일해야 함"


async def test_fetch_bp_candidates_with_nonexistent_site_id(pg: PGClient):
    """존재 안 하는 site_id → 빈 list."""
    rows = await pg.fetch_bp_candidates("남웅건설", site_id="zzz-nonexistent-site")
    assert rows == []


async def test_fetch_activity_with_site_id(pg: PGClient):
    """fetch_activity(site_id=...) — 같은 wbs_activity_id 조회 결과 동일."""
    row_all = await pg.fetch_activity("TNMCB1F6501A03030032")
    row_site = await pg.fetch_activity("TNMCB1F6501A03030032", site_id="m15x-ph3-ibl")
    if row_all is None:
        pytest.skip("TNMCB1F6501A03030032 적재 안 됨")
    assert row_all == row_site


async def test_fetch_l6_plan_mh_map_with_site_id(pg: PGClient):
    """fetch_l6_plan_mh_map(site_id=...) — 결과 동일."""
    result_all = await pg.fetch_l6_plan_mh_map("남웅건설", ["철근콘크리트공사"])
    result_site = await pg.fetch_l6_plan_mh_map("남웅건설", ["철근콘크리트공사"], site_id="m15x-ph3-ibl")
    if not result_all:
        pytest.skip("남웅건설 철근콘크리트공사 적재 안 됨")
    assert result_all == result_site
