from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

import pipeline.agents.forecaster.agent as FA
from pipeline.agents.forecaster import ForecasterConfig


class _FakePG:
    def __init__(self, url):
        pass

    async def connect(self):
        pass

    async def close(self):
        pass

    async def assert_pipeline_run_exists(self, run_id):
        pass

    async def insert_forecast(self, row):
        pass


class _FakeColl:
    def get(self, **kw):
        return {"metadatas": [], "documents": []}


class _FakeChroma:
    def __init__(self, **kw):
        pass

    def get_or_create_daily_activities(self):
        return _FakeColl()


class _FakeAzure:
    def __init__(self, **kw):
        pass


def _act(i):
    return {
        "company": f"co{i}",
        "l6_main": f"L6_{i}",
        "wa": None,
        "work_content": f"w{i}",
    }


@pytest.mark.asyncio
async def test_forecaster_emits_per_group(monkeypatch):
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "forecaster":
            progress.append((processed, total))

    async def _fake_one_group(company, l6_main, activities, run_id, today, pg, coll, azure, cfg):
        return {"company": company, "l6_main": l6_main}

    monkeypatch.setattr(FA, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(FA, "PGClient", _FakePG)
    monkeypatch.setattr(FA, "ChromaClient", _FakeChroma)
    monkeypatch.setattr(FA, "AzureOpenAI", _FakeAzure)
    monkeypatch.setattr(FA, "_forecast_one_group", _fake_one_group)

    n = 6
    mapped = [_act(i) for i in range(n)]
    cfg = ForecasterConfig(
        azure_endpoint="x",
        azure_api_key="x",
        azure_api_version="x",
        llm_model="x",
        embedding_model="x",
        postgres_url="postgresql://x",
        chroma_host="x",
        chroma_port=1,
    )
    rows = await FA.forecast(mapped, uuid4(), date(2025, 9, 25), cfg)
    assert len(rows) == n

    procs = [p for p, _ in progress]
    assert procs[0] == 0
    assert procs == sorted(procs)
    assert procs[-1] == n
    assert all(t == n for _, t in progress)
