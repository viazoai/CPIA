"""B3 — forecaster.forecast() 가 Semaphore 로 동시성 제한.

monkeypatch _forecast_one_group → 진입자 카운트.
mock pg.insert_forecast 도 진입자 카운트 (asyncpg pool acquire 보호 확인용).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_forecast_respects_semaphore(monkeypatch):
    monkeypatch.setenv("CPIA_LLM_CONCURRENCY", "2")
    from pipeline.agents.forecaster import agent as forecaster_agent

    in_flight = 0
    max_in_flight = 0

    async def fake_one_group(*args, **kwargs):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return {
            "company": "c",
            "l6_main": "l",
            "wa": "w",
            "assigned_workers": 0,
            "today_qty_by_unit": {},
            "main_unit": None,
            "assessment": "정상",
        }

    # 8 groups
    mapped = [
        {
            "company": f"c{i}",
            "l6_main": f"l{i}",
            "wa": f"w{i}",
            "work_content": "x",
            "trade": "건축",
        }
        for i in range(8)
    ]
    with (
        patch.object(forecaster_agent, "_forecast_one_group", side_effect=fake_one_group),
        patch.object(forecaster_agent, "PGClient") as MockPG,
        patch.object(forecaster_agent, "ChromaClient"),
        patch.object(forecaster_agent, "AzureOpenAI"),
    ):
        MockPG.return_value.connect = AsyncMock()
        MockPG.return_value.close = AsyncMock()
        MockPG.return_value.assert_pipeline_run_exists = AsyncMock()
        MockPG.return_value.insert_forecast = AsyncMock()
        cfg = type(
            "Cfg",
            (),
            {
                "postgres_url": "x",
                "chroma_host": "x",
                "chroma_port": 0,
                "chroma_ssl": False,
                "azure_api_key": "x",
                "azure_api_version": "x",
                "azure_endpoint": "x",
                "azure_timeout": 1,
                "azure_max_retries": 0,
            },
        )()
        await forecaster_agent.forecast(mapped, uuid.uuid4(), date(2025, 9, 22), cfg)

    assert max_in_flight == 2, f"expected max 2, got {max_in_flight}"
