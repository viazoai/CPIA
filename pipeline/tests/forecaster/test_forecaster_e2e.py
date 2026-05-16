"""Forecaster E2E — mapper + atomizer + forecaster 통과.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §12.3
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
import pytest_asyncio

from pipeline.agents.atomizer import AtomizerConfig, atomize
from pipeline.agents.forecaster import ForecasterConfig, forecast
from pipeline.agents.mapper import MapperConfig, _prorate_mh, map_activity
from pipeline.agents.parser import parse_daily_report
from pipeline.db import PGClient


@pytest_asyncio.fixture
async def setup(monkeypatch):
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
    common = dict(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        embedding_model=os.environ["EMBEDDING_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
        chroma_ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )
    mapper_cfg = MapperConfig(llm_model=os.environ["LLM_MODEL"], **common)
    atomizer_cfg = AtomizerConfig(**common)
    forecaster_cfg = ForecasterConfig(llm_model=os.environ["LLM_MODEL"], **common)

    pg = PGClient(common["postgres_url"])
    await pg.connect()
    run_id = uuid.uuid4()
    await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
    try:
        yield mapper_cfg, atomizer_cfg, forecaster_cfg, run_id, pg
    finally:
        await pg.delete_pipeline_run(run_id)
        await pg.close()


@pytest.mark.slow
@pytest.mark.golden
@pytest.mark.asyncio
@pytest.mark.timeout(900)
async def test_forecaster_e2e_namwong_47(setup):
    """E2E: 9/25 남웅 47 row → mapper → atomizer → forecaster.

    예상: 1 forecast row (남웅건설, 철근콘크리트공사). assessment ∈ {정상, 주의, 이상}.
    """
    mapper_cfg, atomizer_cfg, forecaster_cfg, run_id, pg = setup

    xlsx = "/Users/kyungseoplee/Project Agent/CPIA/docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
    parsed = parse_daily_report(xlsx)
    namwong = [
        a for a in parsed["activities"] if a["company"] == "남웅건설" and "비계" not in a["work_content"]
    ]
    assert len(namwong) == 47
    parsed_filt = {**parsed, "activities": namwong}

    # mapper
    mapped: list = []
    for a in namwong:
        r = await map_activity(a, parsed_report=parsed_filt, cfg=mapper_cfg)
        mapped.append(r)
    mapped = await _prorate_mh(mapped, parsed_filt, pg)

    # atomizer
    await atomize(mapped, parsed_filt, run_id, atomizer_cfg)

    # forecaster
    today = date(2025, 9, 25)
    forecasts = await forecast(mapped, run_id, today, forecaster_cfg)

    # 검증
    assert len(forecasts) == 1
    row = forecasts[0]
    assert row["company"] == "남웅건설"
    assert row["l6_main"] == "철근콘크리트공사"
    assert row["assessment"] in {"정상", "주의", "이상", None}
    assert row["risk_level"] in {"정상", "주의", "이상", None}
    assert row["today_assigned_workers"] == pytest.approx(88.0)
