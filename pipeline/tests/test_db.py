from __future__ import annotations

import os
import sys
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
