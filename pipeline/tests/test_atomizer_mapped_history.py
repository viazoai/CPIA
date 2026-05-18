"""Atomizer mapped_history INSERT 통합 테스트 (Phase 3 RED).

검증 항목:
  1. test_atomizer_inserts_valid_mapped_to_history   — wa+l6 둘 다 not None N건 → mapped_history N row
  2. test_atomizer_skips_wa_none_activity            — wa=None / l6!=None → mapped_history 0건 (Chroma 적재)
  3. test_atomizer_skips_l6_none_activity            — l6_main=None → mapped_history + Chroma 모두 skip
  4. test_atomizer_mapped_history_grouping           — 동일 (wa, l6, company) 2건 → UPSERT, COUNT=1

Azure + Chroma 는 mock 처리 (PG 만 실 호출).
참조: test_reporter.py 의 patch(PGClient) 패턴
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest

from pipeline.agents.atomizer import AtomizerConfig, atomize
from pipeline.db import PGClient


def _cfg(pg_url: str) -> AtomizerConfig:
    return AtomizerConfig(
        azure_endpoint="https://fake.openai.azure.com/",
        azure_api_key="fake_key",
        azure_api_version="2024-12-01-preview",
        embedding_model="text-embedding-3-small-ai-board-test",
        postgres_url=pg_url,
        chroma_host="localhost",
        chroma_port=8000,
    )


def _sample_activity(
    *,
    l6_main: str | None = "철근콘크리트공사",
    wa: str | None = "CUB",
    company: str = "남웅건설",
    today_qty: float = 12.5,
    today_assigned_workers: float = 8.0,
    unit: str = "m2",
    work_content: str = "기초 거푸집 설치",
) -> dict:
    return {
        "wbs_activity_id": None,
        "l5_disc": "건축",
        "l6_main": l6_main,
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "trade": "건축",
        "company": company,
        "unit": unit,
        "today_qty": today_qty,
        "today_assigned_workers": today_assigned_workers,
        "work_content": work_content,
        "conditions": [],
        "assigned_workers": today_assigned_workers,
        "worker_source": "mh_prorated",
        "plan_total_qty": None,
        "plan_mh": None,
        "wa": wa,
        "mapping_conf": 0.82,
        "mapping_source": "auto_bp_single",
        "requires_review": False,
    }


def _parsed_report(report_date: str = "2025-09-27") -> dict:
    return {
        "report_date": report_date,
        "project": "TEST",
        "bp_summaries": [],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }


def _make_chroma_mock():
    """Chroma upsert 를 no-op 으로 mock."""
    mock_coll = MagicMock()
    mock_coll.upsert = MagicMock(return_value=None)
    mock_client = MagicMock()
    mock_client.get_or_create_daily_activities.return_value = mock_coll
    return mock_client


def _make_azure_mock(dim: int = 1536) -> MagicMock:
    """Azure embedding 응답을 고정값으로 mock."""
    mock_embedding = MagicMock()
    mock_embedding.embedding = [0.0] * dim

    mock_resp = MagicMock()
    mock_resp.data = [mock_embedding]

    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = mock_resp
    return mock_client


@pytest.fixture
def pg_url() -> str:
    url = os.environ.get("POSTGRES_URL")
    if not url:
        pytest.skip("POSTGRES_URL 환경변수 누락")
    return url


@pytest.mark.asyncio
async def test_atomizer_inserts_valid_mapped_to_history(pg_url: str) -> None:
    """wa + l6_main 둘 다 not None 인 활동 2건 → mapped_history 2 row INSERT."""
    run_id = uuid.uuid4()
    pg_real = PGClient(pg_url)
    await pg_real.connect()
    try:
        await pg_real.insert_pipeline_run(run_id, "m15x-ph3-ibl", "2025-09-27", "running")
    finally:
        await pg_real.close()

    mapped = [
        _sample_activity(
            wa="CUB", l6_main="철근콘크리트공사", company="남웅건설", work_content="거푸집 설치"
        ),
        _sample_activity(wa="STL", l6_main="철골공사", company="삼성물산", work_content="철골 설치"),
    ]

    with (
        patch("pipeline.agents.atomizer.AzureOpenAI", return_value=_make_azure_mock()),
        patch("pipeline.agents.atomizer.ChromaClient", return_value=_make_chroma_mock()),
    ):
        await atomize(mapped, _parsed_report(), run_id, _cfg(pg_url))

    pg_check = PGClient(pg_url)
    await pg_check.connect()
    try:
        async with pg_check._pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM mapped_history WHERE run_id=$1",
                run_id,
            )
        assert count == 2, f"2건 INSERT 기대, 실제: {count}"
    finally:
        await pg_check.delete_pipeline_run(run_id)
        await pg_check.close()


@pytest.mark.asyncio
async def test_atomizer_skips_wa_none_activity(pg_url: str) -> None:
    """wa=None / l6_main!=None → mapped_history INSERT 0건. Chroma 는 적재됨."""
    run_id = uuid.uuid4()
    pg_real = PGClient(pg_url)
    await pg_real.connect()
    try:
        await pg_real.insert_pipeline_run(run_id, "m15x-ph3-ibl", "2025-09-27", "running")
    finally:
        await pg_real.close()

    # wa=None 이지만 l6_main 있음 — Chroma 는 적재, mapped_history 는 skip
    mapped = [_sample_activity(wa=None, l6_main="철근콘크리트공사")]

    mock_chroma = _make_chroma_mock()

    with (
        patch("pipeline.agents.atomizer.AzureOpenAI", return_value=_make_azure_mock()),
        patch("pipeline.agents.atomizer.ChromaClient", return_value=mock_chroma),
    ):
        ids = await atomize(mapped, _parsed_report(), run_id, _cfg(pg_url))

    # Chroma 는 적재됨 (valid = [l6_main is not None])
    assert len(ids) == 1, f"Chroma ids: {ids}"
    mock_chroma.get_or_create_daily_activities.return_value.upsert.assert_called_once()

    pg_check = PGClient(pg_url)
    await pg_check.connect()
    try:
        async with pg_check._pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM mapped_history WHERE run_id=$1",
                run_id,
            )
        assert count == 0, f"wa=None 인데 mapped_history INSERT: {count}건"
    finally:
        await pg_check.delete_pipeline_run(run_id)
        await pg_check.close()


@pytest.mark.asyncio
async def test_atomizer_skips_l6_none_activity(pg_url: str) -> None:
    """l6_main=None → mapped_history + Chroma 모두 skip."""
    run_id = uuid.uuid4()
    pg_real = PGClient(pg_url)
    await pg_real.connect()
    try:
        await pg_real.insert_pipeline_run(run_id, "m15x-ph3-ibl", "2025-09-27", "running")
    finally:
        await pg_real.close()

    mapped = [_sample_activity(l6_main=None, wa="CUB")]

    mock_chroma = _make_chroma_mock()

    with (
        patch("pipeline.agents.atomizer.AzureOpenAI", return_value=_make_azure_mock()),
        patch("pipeline.agents.atomizer.ChromaClient", return_value=mock_chroma),
    ):
        ids = await atomize(mapped, _parsed_report(), run_id, _cfg(pg_url))

    # Chroma upsert 는 호출되지 않음 (valid=[] 이므로 조기 반환)
    assert ids == [], f"l6_main=None 인데 ids 반환: {ids}"
    mock_chroma.get_or_create_daily_activities.return_value.upsert.assert_not_called()

    pg_check = PGClient(pg_url)
    await pg_check.connect()
    try:
        async with pg_check._pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM mapped_history WHERE run_id=$1",
                run_id,
            )
        assert count == 0, f"l6_main=None 인데 mapped_history INSERT: {count}건"
    finally:
        await pg_check.delete_pipeline_run(run_id)
        await pg_check.close()


@pytest.mark.asyncio
async def test_atomizer_mapped_history_grouping(pg_url: str) -> None:
    """동일 (wa, l6, company) 2건 → ON CONFLICT UPDATE, COUNT=1, today_qty=마지막 값.

    산식 결정: ON CONFLICT UPDATE (마지막 값 채택) — 다음 cycle Phase 0 에서 합계 vs 마지막 합의.
    executemany 는 순서 보장 → 두 번째 row 의 today_qty 가 최종값.
    """
    run_id = uuid.uuid4()
    pg_real = PGClient(pg_url)
    await pg_real.connect()
    try:
        await pg_real.insert_pipeline_run(run_id, "m15x-ph3-ibl", "2025-09-27", "running")
    finally:
        await pg_real.close()

    # 같은 (wa, l6, company) — work_content 만 다름 (doc_id 는 달라서 Chroma 는 2건, PG 는 UPSERT)
    mapped = [
        _sample_activity(
            wa="CUB",
            l6_main="철근콘크리트공사",
            company="남웅건설",
            today_qty=10.0,
            work_content="기초 거푸집 설치",
        ),
        _sample_activity(
            wa="CUB",
            l6_main="철근콘크리트공사",
            company="남웅건설",
            today_qty=20.0,
            work_content="1F 벽체 타설",
        ),
    ]

    with (
        patch("pipeline.agents.atomizer.AzureOpenAI", return_value=_make_azure_mock()),
        patch("pipeline.agents.atomizer.ChromaClient", return_value=_make_chroma_mock()),
    ):
        await atomize(mapped, _parsed_report(), run_id, _cfg(pg_url))

    pg_check = PGClient(pg_url)
    await pg_check.connect()
    try:
        async with pg_check._pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM mapped_history WHERE run_id=$1",
                run_id,
            )
            fetched = await conn.fetchrow(
                "SELECT today_qty FROM mapped_history WHERE run_id=$1",
                run_id,
            )
        assert count == 1, f"동일 triplet UPSERT 기대 count=1, 실제: {count}"
        # executemany 순서 보장 → 두 번째 row(today_qty=20.0)가 최종값
        assert float(fetched["today_qty"]) == 20.0, (
            f"UPSERT 마지막 값 기대 20.0, 실제: {fetched['today_qty']}"
        )
    finally:
        await pg_check.delete_pipeline_run(run_id)
        await pg_check.close()
