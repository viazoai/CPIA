"""Forecaster integration tests — 실 PG + 실 Chroma + 실 Azure.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §12.2
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
import pytest_asyncio

from pipeline.agents.forecaster import ForecasterConfig, forecast
from pipeline.db import PGClient


@pytest.fixture
def cfg() -> ForecasterConfig:
    keys = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION",
        "LLM_MODEL",
        "EMBEDDING_MODEL",
        "POSTGRES_URL",
        "CHROMA_HOST",
    ]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        pytest.skip(f"env 누락: {missing}")
    return ForecasterConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
        embedding_model=os.environ["EMBEDDING_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
        chroma_ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )


@pytest_asyncio.fixture
async def run_row(cfg):
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    run_id = uuid.uuid4()
    try:
        await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
        try:
            yield run_id
        finally:
            await pg.delete_pipeline_run(run_id)
    finally:
        await pg.close()


def _make_activity(company: str, l6: str, unit: str, qty: float, workers: float) -> dict:
    return {
        "wbs_activity_id": None,
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "l5_disc": "설비",
        "l6_main": l6,
        "wa": "AC",
        "mapping_conf": 0.85,
        "mapping_source": "auto_bp_single",
        "requires_review": False,
        "trade": "공조",
        "company": company,
        "unit": unit,
        "today_qty": qty,
        "work_content": f"{l6} 작업",
        "conditions": ["맑음"],
        "assigned_workers": workers,
        "worker_source": "mh_prorated",
        "plan_total_qty": None,
        "plan_mh": None,
    }


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_forecaster_sebo_with_synthetic(cfg, run_row):
    """synthetic 30일 적재 후 세보 일반공조 1 row 생성. assessment != None."""
    mapped = [_make_activity("세보엠이씨", "일반공조설비공사", "m", 80, 401.4)]
    result = await forecast(mapped, run_row, date(2025, 9, 25), cfg)
    assert len(result) == 1
    row = result[0]
    assert row["company"] == "세보엠이씨"
    assert row["l6_main"] == "일반공조설비공사"
    assert row["assessment"] in {"정상", "주의", "이상"}
    assert row["schedule_state"] in {"early", "on_schedule", "post_due", "unknown"}
    assert row["risk_level"] in {"정상", "주의", "이상"}


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_forecaster_cold_start_unknown_bp(cfg, run_row):
    """미등록 BP사 → assessment=None, schedule_state=unknown."""
    mapped = [_make_activity("__nonexistent_company__", "__no__", "m", 80, 100)]
    result = await forecast(mapped, run_row, date(2025, 9, 25), cfg)
    assert len(result) == 1
    row = result[0]
    assert row["assessment"] is None
    assert row["schedule_state"] == "unknown"
    assert row["delay_days"] is None
    assert row["risk_level"] is None


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_forecaster_pg_insert_persisted(cfg, run_row):
    """forecasts 테이블에 row 가 실제 적재됐는지 검증."""
    mapped = [_make_activity("세보엠이씨", "일반공조설비공사", "m", 80, 401.4)]
    await forecast(mapped, run_row, date(2025, 9, 25), cfg)

    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        rows = await pg._pool.fetch(
            "SELECT company, l6_main, assessment, risk_level, schedule_state, "
            "delay_days, today_productivity, plan_mh_per_day "
            "FROM forecasts WHERE run_id = $1",
            run_row,
        )
    finally:
        await pg.close()
    assert len(rows) == 1
    assert rows[0]["company"] == "세보엠이씨"
    assert rows[0]["schedule_state"] is not None


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_forecaster_chroma_metadata_normalization(cfg, run_row):
    """Atomizer schema 의 conditions string → list 정규화 통과."""
    mapped = [_make_activity("세보엠이씨", "일반공조설비공사", "m", 80, 401.4)]
    result = await forecast(mapped, run_row, date(2025, 9, 25), cfg)
    if result[0]["rag_n_similar"] >= 1:
        first_case = result[0]["similar_cases"][0]
        assert isinstance(first_case["conditions"], list)
