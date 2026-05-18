"""forecasts 테이블 wa 컬럼 + 인덱스 존재 검증.

Phase 1.1: WPSummaryRow grain = (wa, l6_main, company) triplet 결정 반영.
- forecasts.wa TEXT 컬럼 추가 확인
- idx_forecasts_wa_company_l6 인덱스 존재 확인
"""

from __future__ import annotations

import os

import asyncpg
import pytest


@pytest.fixture
def pg_url() -> str:
    url = os.environ.get("POSTGRES_URL")
    if not url:
        pytest.skip("POSTGRES_URL 환경변수 누락")
    return url


@pytest.mark.asyncio
async def test_forecasts_has_wa_column(pg_url: str) -> None:
    """forecasts 테이블에 wa TEXT 컬럼이 존재해야 한다."""
    conn = await asyncpg.connect(pg_url)
    try:
        rows = await conn.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'forecasts'
              AND column_name = 'wa'
            """
        )
        assert len(rows) == 1, f"forecasts 테이블에 wa 컬럼이 없음 (row count={len(rows)})"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_forecasts_has_wa_company_l6_index(pg_url: str) -> None:
    """forecasts 테이블에 idx_forecasts_wa_company_l6 인덱스가 존재해야 한다."""
    conn = await asyncpg.connect(pg_url)
    try:
        rows = await conn.fetch(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'forecasts'
              AND indexname = 'idx_forecasts_wa_company_l6'
            """
        )
        assert len(rows) == 1, f"idx_forecasts_wa_company_l6 인덱스가 없음 (row count={len(rows)})"
    finally:
        await conn.close()
