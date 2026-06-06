from __future__ import annotations

from uuid import uuid4

import pytest

import pipeline.graph as G
from pipeline.agents.mapper import MapperConfig


class _FakePG:
    """insert 호출 순서/시점만 기록하는 가짜 PGClient."""

    events: list[tuple] = []

    def __init__(self, url):
        self._url = url

    async def connect(self):
        pass

    async def close(self):
        pass

    async def fetch_bp_candidates(self, company):
        return []

    async def insert_parser_report(self, **kw):
        _FakePG.events.append(("parser_report", None))

    async def insert_parser_activities_batch(self, **kw):
        _FakePG.events.append(("parser_activities", len(kw["activities"])))

    async def insert_parser_job_allocations_batch(self, **kw):
        _FakePG.events.append(("job", len(kw["rows"])))

    async def insert_parser_equipment_allocations_batch(self, **kw):
        _FakePG.events.append(("equip", len(kw["rows"])))

    async def insert_mapper_activities_batch(self, **kw):
        # 청크 적재(idxs 동반)와 최종 full re-INSERT(idxs=None) 를 구분 기록.
        kind = "mapper_chunk" if kw.get("idxs") is not None else "mapper_final"
        _FakePG.events.append((kind, len(kw["activities"])))

    async def fetch_all(self, sql, *a):
        # l7.5 candidates / history batch queries: mapper expects specific keys,
        # return [] so the comprehensions produce empty map/set safely.
        if "activity_master" in sql or "l7_5_activity" in sql:
            return []
        return [{"n": 0}]


def _act(i):
    return {
        "company": f"co{i % 2}",
        "work_content": f"w{i}",
        "trade": "건축",
        "l6_main": None,
        "wa": None,
        "unit": "m3",
        "today_qty": 1,
    }


@pytest.mark.asyncio
async def test_mapper_node_chunks_and_emits(monkeypatch):
    _FakePG.events = []
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "mapper":
            progress.append((processed, total))

    async def _fake_map_one_inner(a, parsed_report, cfg, bp_cand_lookup, l75_cand_map=None, history_set=None):
        out = dict(a)
        out["l6_main"] = "L6"
        out["wa"] = "WA"
        return out

    async def _fake_prorate(mapped, parsed, pg):
        return mapped

    monkeypatch.setattr(G, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(G, "map_activity", _fake_map_one_inner)
    monkeypatch.setattr(G, "_prorate_mh", _fake_prorate)
    monkeypatch.setattr(G, "normalize_company", lambda c: c or "")
    monkeypatch.setattr(G, "PGClient", _FakePG)
    monkeypatch.setattr(G, "_MAPPER_PROGRESS_CHUNK", 20)

    n = 45
    parsed = {
        "project": "P",
        "activities": [_act(i) for i in range(n)],
        "bp_summaries": [],
        "job_allocations": [],
        "equipment_allocations": [],
    }
    cfg = G.GraphConfig(
        mapper=MapperConfig(
            azure_endpoint="x",
            azure_api_key="x",
            azure_api_version="x",
            llm_model="x",
            embedding_model="x",
            postgres_url="postgresql://x",
            chroma_host="x",
            chroma_port=1,
        ),
        atomizer=None,
        forecaster=None,
        optimizer=None,
        reporter=None,
    )
    state = {"parsed": parsed, "run_id": str(uuid4()), "date": "2025-09-25"}

    out = await G.mapper_node(state, cfg)
    assert len(out["mapped"]) == n

    kinds = [e[0] for e in _FakePG.events]
    first_mapper = kinds.index("mapper_chunk")
    assert "parser_activities" in kinds[:first_mapper]
    assert "parser_report" in kinds[:first_mapper]

    chunk_sizes = [e[1] for e in _FakePG.events if e[0] == "mapper_chunk"]
    assert sum(chunk_sizes) == n
    assert len(chunk_sizes) >= 2

    procs = [p for p, _ in progress]
    assert procs[0] == 0
    assert procs == sorted(procs)
    assert procs[-1] == n
    assert all(t == n for _, t in progress)
