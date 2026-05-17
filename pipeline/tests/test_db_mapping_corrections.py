"""PGClient.insert_mapping_correction 테스트.

실 schema (infra/postgres/init.sql:127): id, run_id, report_date, original JSONB,
corrected JSONB, created_at — 6 컬럼만. postgres.md §8 의 work_content/company/
trade/correction_type top-level 컬럼은 실 PG 에 미반영 (drift backlog 별 cycle).

본 cycle = code-only scope → signature 는 4 인자 (run_id, report_date, original,
corrected). work_content/company/trade/correction_type 는 original/corrected JSONB
안에 합쳐서 박음 (자가 학습 텍스트 검색은 JSONB 내부 검색으로 처리).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date

import pytest

from pipeline.db import PGClient


@pytest.fixture
def pg_url() -> str:
    url = os.environ.get("POSTGRES_URL")
    if not url:
        pytest.skip("POSTGRES_URL 환경변수 누락")
    return url


@pytest.mark.asyncio
async def test_insert_mapping_correction_roundtrip(pg_url: str) -> None:
    """insert_mapping_correction 1 row INSERT 후 SELECT 정합 검증."""
    run_id = uuid.uuid4()
    pg = PGClient(pg_url)
    await pg.connect()
    try:
        await pg.insert_pipeline_run(run_id, "DEMO_SITE", "2025-09-27", "running")
        await pg.insert_mapping_correction(
            run_id=run_id,
            report_date=date(2025, 9, 27),
            original={
                "work_content": "1F 벽체 콘크리트 타설",
                "company": "남웅건설",
                "trade": "철근콘크리트공사",
                "wa": "CUB",
                "l6_main": "철근콘크리트공사",
                "mapping_conf": 0.55,
                "mapping_source": "hil_required",
            },
            corrected={
                "wa": "CUB",
                "l6_main": "철근콘크리트공사",
                "mapping_source": "user_corrected",
                "correction_type": "replace",
            },
        )
        async with pg._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT report_date, original, corrected FROM mapping_corrections WHERE run_id=$1",
                run_id,
            )
        assert row is not None
        original = json.loads(row["original"]) if isinstance(row["original"], str) else row["original"]
        corrected = json.loads(row["corrected"]) if isinstance(row["corrected"], str) else row["corrected"]
        assert original["company"] == "남웅건설"
        assert original["work_content"] == "1F 벽체 콘크리트 타설"
        assert original["trade"] == "철근콘크리트공사"
        assert original["mapping_source"] == "hil_required"
        assert corrected["mapping_source"] == "user_corrected"
        assert corrected["correction_type"] == "replace"
    finally:
        await pg.delete_pipeline_run(run_id)
        await pg.close()
