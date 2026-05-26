"""B3 — optimizer.optimize() 가 Semaphore 로 동시성 제한.

monkeypatch _call_azure_llm_async → 진입자 카운트.
mock PGClient, pg.insert_optimizer_advice, view_builder 함수들 모두 AsyncMock.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_optimize_respects_semaphore(monkeypatch):
    monkeypatch.setenv("CPIA_LLM_CONCURRENCY", "2")
    from pipeline.agents.optimizer import agent as optimizer_agent

    in_flight = 0
    max_in_flight = 0

    async def fake_call(llm_input, cfg, azure):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return {"diagnosis": "test", "recommendations": []}

    # 6 forecast rows — 2 excluded (not in hil_2_selection)
    forecast = [{"company": f"c{i}", "l6_main": f"l{i}", "assessment": "정상"} for i in range(6)]
    # only 4 selected (index 0..3) — remaining 2 filtered
    hil_2_selection = [f"c{i}|l{i}" for i in range(4)]
    pre_optimizer_cases = {f"c{i}|l{i}": [] for i in range(6)}
    run_id = uuid.uuid4()

    with (
        patch.object(optimizer_agent, "_call_azure_llm_async", side_effect=fake_call),
        patch.object(optimizer_agent, "PGClient") as MockPG,
    ):
        mock_pg = MagicMock()
        mock_pg.connect = AsyncMock()
        mock_pg.close = AsyncMock()
        mock_pg.insert_optimizer_advice = AsyncMock()
        MockPG.return_value = mock_pg

        cfg = type(
            "Cfg",
            (),
            {
                "postgres_url": "x",
                "azure_api_key": "x",
                "azure_api_version": "x",
                "azure_endpoint": "x",
                "azure_timeout": 1,
                "azure_max_retries": 0,
                "llm_model": "test-model",
            },
        )()
        await optimizer_agent.optimize(
            forecast=forecast,
            hil_2_selection=hil_2_selection,
            pre_optimizer_cases=pre_optimizer_cases,
            run_id=run_id,
            today=date(2025, 9, 22),
            cfg=cfg,
            site_id=None,
            mapped=None,
        )

    assert max_in_flight == 2, f"expected max 2, got {max_in_flight}"
