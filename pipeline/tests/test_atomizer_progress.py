from __future__ import annotations

from uuid import uuid4

import pytest

import pipeline.agents.atomizer as AT
from pipeline.agents.atomizer import AtomizerConfig


class _FakeColl:
    def upsert(self, **kw):
        pass


class _FakeChroma:
    def __init__(self, **kw):
        pass

    def get_or_create_daily_activities(self):
        return _FakeColl()


class _FakeResp:
    def __init__(self, n):
        self.data = [type("E", (), {"embedding": [0.0]})() for _ in range(n)]


class _FakeEmb:
    def create(self, model, input):
        return _FakeResp(len(input))


class _FakeAzure:
    def __init__(self, **kw):
        self.embeddings = _FakeEmb()


class _FakePG:
    def __init__(self, url):
        pass

    async def connect(self):
        pass

    async def close(self):
        pass

    async def assert_pipeline_run_exists(self, run_id):
        pass

    async def update_run_atomized_count(self, run_id, n):
        pass

    async def get_pipeline_run(self, run_id):
        return {"site_id": "s", "report_date": "2025-09-25"}

    async def insert_mapped_history_batch(self, *a, **k):
        pass


def _act(i):
    return {
        "company": "co",
        "l5_disc": "건축",
        "l6_main": "L6",
        "l7_5_activity": "",
        "work_content": f"w{i}",
        "wa": None,
        "trade": "건축",
        "unit": "m3",
        "today_qty": 1,
        "today_assigned_workers": 1,
        "conditions": [],
        "assigned_workers": 1,
        "worker_source": "manual",
        "mapping_conf": 0.9,
        "perperson": 0.0,
        "productivity_pct": 0.0,
    }


@pytest.mark.asyncio
async def test_atomizer_emits_post_dedup_total(monkeypatch):
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "atomizer":
            progress.append((processed, total))

    monkeypatch.setattr(AT, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(AT, "AzureOpenAI", _FakeAzure)
    monkeypatch.setattr(AT, "ChromaClient", _FakeChroma)
    monkeypatch.setattr(AT, "PGClient", _FakePG)

    n = 250
    mapped = [_act(i) for i in range(n)]
    parsed = {"report_date": "2025-09-25"}
    cfg = AtomizerConfig(
        azure_endpoint="x",
        azure_api_key="x",
        azure_api_version="x",
        embedding_model="x",
        postgres_url="postgresql://x",
        chroma_host="x",
        chroma_port=1,
        batch_size=100,
    )
    ids = await AT.atomize(mapped, parsed, uuid4(), cfg)
    assert len(ids) == n

    procs = [p for p, _ in progress]
    assert procs[0] == 0
    assert procs == sorted(procs)
    assert procs[-1] == n
    assert all(t == n for _, t in progress)
