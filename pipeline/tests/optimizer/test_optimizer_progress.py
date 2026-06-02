from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

import pipeline.agents.optimizer.agent as OA
from pipeline.agents.optimizer.agent import OptimizerConfig


class _FakePG:
    insert_times: list[int] = []
    _emit_count = 0

    def __init__(self, url):
        pass

    async def connect(self):
        pass

    async def close(self):
        pass

    async def insert_optimizer_advice(self, row):
        _FakePG.insert_times.append(_FakePG._emit_count)

    async def upsert_daily_report_view_col(self, *a, **k):
        pass


@pytest.mark.asyncio
async def test_optimizer_streams_advice_and_emits(monkeypatch):
    _FakePG.insert_times = []
    _FakePG._emit_count = 0
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "optimizer":
            _FakePG._emit_count += 1
            progress.append((processed, total))

    async def _fake_retry(r, cases, run_id, today, cfg, azure, sem, failed_wps, pg, max_retries=3):
        row = {"company": r["company"], "l6_main": r["l6_main"]}
        await pg.insert_optimizer_advice(row)
        return row

    async def _fake_views(pg, site_id, today):
        return {}

    monkeypatch.setattr(OA, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(OA, "PGClient", _FakePG)
    monkeypatch.setattr(OA, "AzureOpenAI", lambda **k: object())
    monkeypatch.setattr(OA, "_process_one_v10_with_retry", _fake_retry)
    monkeypatch.setattr(OA, "_build_productivity_views_v2", _fake_views)

    forecast = [{"company": f"c{i}", "l6_main": f"L{i}"} for i in range(4)]
    selection = [f"{r['company']}|{r['l6_main']}" for r in forecast]
    cfg = OptimizerConfig(
        azure_endpoint="x",
        azure_api_key="x",
        azure_api_version="x",
        llm_model="x",
        postgres_url="postgresql://x",
        chroma_host="x",
        chroma_port=1,
    )
    rows = await OA.optimize(forecast, selection, {}, uuid4(), date(2025, 9, 25), cfg, site_id="s", mapped=[])
    assert len(rows) == 4
    assert len(_FakePG.insert_times) == 4
    procs = [p for p, _ in progress]
    assert procs and procs[-1] == 4
