"""mapped_history 테이블 스키마 검증 테스트 (Phase 1.2 RED).

검증 항목:
  1. mapped_history 테이블 존재 (information_schema.tables)
  2. 필수 컬럼 전부 존재 (information_schema.columns)
  3. UNIQUE (run_id, wa, l6_main, company) constraint 존재 (pg_constraint)
  4. idx_mapped_history_site_date + idx_mapped_history_triplet 인덱스 둘 다 존재 (pg_indexes)

패턴: PGClient(pg_url) + await pg.connect() + finally: await pg.close()
참조: test_db_daily_reports.py / test_db_mapping_corrections.py
"""

from __future__ import annotations

import os

import pytest

from pipeline.db import PGClient


@pytest.fixture
def pg_url() -> str:
    url = os.environ.get("POSTGRES_URL")
    if not url:
        pytest.skip("POSTGRES_URL 환경변수 누락")
    return url


@pytest.fixture
async def pg(pg_url: str):
    client = PGClient(pg_url)
    await client.connect()
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_mapped_history_table_exists(pg: PGClient) -> None:
    """mapped_history 테이블이 public 스키마에 존재한다."""
    async with pg._pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'mapped_history'
            """,
        )
    assert len(rows) == 1, "mapped_history 테이블이 public 스키마에 없음"


@pytest.mark.asyncio
async def test_mapped_history_has_required_columns(pg: PGClient) -> None:
    """mapped_history 필수 컬럼 9개가 모두 존재한다."""
    required = {
        "id",
        "run_id",
        "report_date",
        "site_id",
        "wa",
        "l6_main",
        "company",
        "today_qty",
        "today_assigned_workers",
        "unit",
        "created_at",
    }
    async with pg._pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'mapped_history'
            """,
        )
    actual = {r["column_name"] for r in rows}
    missing = required - actual
    assert not missing, f"누락 컬럼: {missing}"


@pytest.mark.asyncio
async def test_mapped_history_unique_constraint(pg: PGClient) -> None:
    """UNIQUE (run_id, wa, l6_main, company) constraint 가 존재한다."""
    async with pg._pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT conname, contype, pg_get_constraintdef(oid) AS condef
            FROM pg_constraint
            WHERE conrelid = 'mapped_history'::regclass
              AND contype = 'u'
            """,
        )
    assert len(rows) >= 1, "mapped_history 에 UNIQUE constraint 없음"
    # constraint 정의에 4개 컬럼이 모두 포함돼야 함
    joined = " ".join(r["condef"] for r in rows)
    for col in ("run_id", "wa", "l6_main", "company"):
        assert col in joined, f"UNIQUE constraint 에 '{col}' 컬럼 없음 (condef: {joined})"


@pytest.mark.asyncio
async def test_mapped_history_two_indexes(pg: PGClient) -> None:
    """idx_mapped_history_site_date + idx_mapped_history_triplet 인덱스가 둘 다 존재한다."""
    expected = {
        "idx_mapped_history_site_date",
        "idx_mapped_history_triplet",
    }
    async with pg._pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'mapped_history'
            """,
        )
    actual = {r["indexname"] for r in rows}
    missing = expected - actual
    assert not missing, f"누락 인덱스: {missing} (실제: {actual})"
