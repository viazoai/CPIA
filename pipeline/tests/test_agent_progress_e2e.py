from __future__ import annotations

"""Cross-agent progress harness (C3 Task 8).

Each emitting node (parser, atomizer, exporter, forecaster, optimizer) must
record a (processed, total) sequence that is 0 -> total monotonic non-decreasing
with the last value equal to total and all totals consistent.

For mapper: parser_activities rows must be inserted before the first mapper_chunk.
"""

from datetime import date
from uuid import uuid4

import pytest

import pipeline.agents.atomizer as AT
import pipeline.agents.exporter as EX
import pipeline.agents.forecaster.agent as FA
import pipeline.agents.optimizer.agent as OA
import pipeline.agents.parser_node as PN
import pipeline.graph as G
from pipeline.agents.atomizer import AtomizerConfig
from pipeline.agents.forecaster import ForecasterConfig
from pipeline.agents.mapper import MapperConfig
from pipeline.agents.optimizer.agent import OptimizerConfig


# ---------------------------------------------------------------------------
# Shared assertion helper
# ---------------------------------------------------------------------------


def assert_monotonic(progress: list[tuple[int, int]], expected_total: int) -> None:
    procs = [p for p, _ in progress]
    assert procs, "no emit"
    assert procs[0] == 0
    assert procs == sorted(procs)
    assert procs[-1] == expected_total
    assert all(t == expected_total for _, t in progress)


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_parser_progress(monkeypatch):
    """parser_node: 0 -> total monotonic, last == len(files)."""
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "parser":
            progress.append((processed, total))

    def _fake_parse(p):
        return {
            "report_date": "2025-09-25",
            "project": "T",
            "bp_summaries": [{}],
            "job_allocations": [],
            "equipment_allocations": [],
            "activities": [{}],
            "worker_outputs": [],
            "report_meta": None,
        }

    monkeypatch.setattr(PN, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(PN, "parse_daily_report", _fake_parse)

    state = {
        "run_id": str(uuid4()),
        "postgres_url": "postgresql://x",
        "input_files": ["/a.xlsm", "/b.xlsm", "/c.xlsm"],
    }
    out = await PN.parser_node(state)
    assert "parsed" in out

    assert_monotonic(progress, 3)


# ---------------------------------------------------------------------------
# atomizer
# ---------------------------------------------------------------------------


class _AtomizerFakeColl:
    def upsert(self, **kw):
        pass


class _AtomizerFakeChroma:
    def __init__(self, **kw):
        pass

    def get_or_create_daily_activities(self):
        return _AtomizerFakeColl()


class _AtomizerFakeResp:
    def __init__(self, n):
        self.data = [type("E", (), {"embedding": [0.0]})() for _ in range(n)]


class _AtomizerFakeEmb:
    def create(self, model, input):
        return _AtomizerFakeResp(len(input))


class _AtomizerFakeAzure:
    def __init__(self, **kw):
        self.embeddings = _AtomizerFakeEmb()


class _AtomizerFakePG:
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


def _atomizer_act(i):
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
async def test_e2e_atomizer_progress(monkeypatch):
    """atomizer: 0 -> total monotonic, last == n (post-dedup total)."""
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "atomizer":
            progress.append((processed, total))

    monkeypatch.setattr(AT, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(AT, "AzureOpenAI", _AtomizerFakeAzure)
    monkeypatch.setattr(AT, "ChromaClient", _AtomizerFakeChroma)
    monkeypatch.setattr(AT, "PGClient", _AtomizerFakePG)

    n = 250
    mapped = [_atomizer_act(i) for i in range(n)]
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

    assert_monotonic(progress, n)


# ---------------------------------------------------------------------------
# exporter
# ---------------------------------------------------------------------------


class _ExporterFakePG:
    def __init__(self, url):
        pass

    async def connect(self):
        pass

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_e2e_exporter_progress(monkeypatch):
    """exporter: emits (0,1) then (1,1) — single-unit job, total==1."""
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "exporter":
            progress.append((processed, total))

    async def _fake_fetch_sheet(pg, site_id, report_date):
        return {"ok": True}

    async def _fake_site(pg, site_id):
        return {"name": "X"}

    async def _fake_upsert_report(pg, **kw):
        pass

    monkeypatch.setattr(EX, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(EX, "PGClient", _ExporterFakePG)
    monkeypatch.setattr(EX, "fetch_sheet_data", _fake_fetch_sheet)
    monkeypatch.setattr(EX, "fetch_site_by_id", _fake_site)
    monkeypatch.setattr(EX, "render_xlsx", lambda data, rd, project: b"xlsx")
    monkeypatch.setattr(EX, "upsert_consolidated_report", _fake_upsert_report)

    state = {
        "site_id": "s",
        "date": "2025-09-25",
        "run_id": str(uuid4()),
        "postgres_url": "postgresql://x",
    }
    out = await EX.consolidated_xlsx_node(state)
    assert "consolidated_xlsx_run_id" in out

    assert_monotonic(progress, 1)


# ---------------------------------------------------------------------------
# forecaster
# ---------------------------------------------------------------------------


class _ForecasterFakePG:
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


class _ForecasterFakeColl:
    def get(self, **kw):
        return {"metadatas": [], "documents": []}


class _ForecasterFakeChroma:
    def __init__(self, **kw):
        pass

    def get_or_create_daily_activities(self):
        return _ForecasterFakeColl()


class _ForecasterFakeAzure:
    def __init__(self, **kw):
        pass


def _forecaster_act(i):
    return {
        "company": f"co{i}",
        "l6_main": f"L6_{i}",
        "wa": None,
        "work_content": f"w{i}",
    }


@pytest.mark.asyncio
async def test_e2e_forecaster_progress(monkeypatch):
    """forecaster: 0 -> n monotonic, one emit per group."""
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "forecaster":
            progress.append((processed, total))

    async def _fake_one_group(company, l6_main, activities, run_id, today, pg, coll, azure, cfg):
        return {"company": company, "l6_main": l6_main}

    monkeypatch.setattr(FA, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(FA, "PGClient", _ForecasterFakePG)
    monkeypatch.setattr(FA, "ChromaClient", _ForecasterFakeChroma)
    monkeypatch.setattr(FA, "AzureOpenAI", _ForecasterFakeAzure)
    monkeypatch.setattr(FA, "_forecast_one_group", _fake_one_group)

    n = 6
    mapped = [_forecaster_act(i) for i in range(n)]
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

    assert_monotonic(progress, n)


# ---------------------------------------------------------------------------
# optimizer
# ---------------------------------------------------------------------------


class _OptimizerFakePG:
    insert_times: list[int] = []
    _emit_count = 0

    def __init__(self, url):
        pass

    async def connect(self):
        pass

    async def close(self):
        pass

    async def insert_optimizer_advice(self, row):
        _OptimizerFakePG.insert_times.append(_OptimizerFakePG._emit_count)

    async def upsert_daily_report_view_col(self, *a, **k):
        pass


@pytest.mark.asyncio
async def test_e2e_optimizer_progress(monkeypatch):
    """optimizer: 0 -> n monotonic, last == len(forecast)."""
    _OptimizerFakePG.insert_times = []
    _OptimizerFakePG._emit_count = 0
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "optimizer":
            _OptimizerFakePG._emit_count += 1
            progress.append((processed, total))

    async def _fake_retry(r, cases, run_id, today, cfg, azure, sem, failed_wps, pg, max_retries=3):
        row = {"company": r["company"], "l6_main": r["l6_main"]}
        await pg.insert_optimizer_advice(row)
        return row

    async def _fake_views(pg, site_id, today):
        return {}

    monkeypatch.setattr(OA, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(OA, "PGClient", _OptimizerFakePG)
    monkeypatch.setattr(OA, "AzureOpenAI", lambda **k: object())
    monkeypatch.setattr(OA, "_process_one_v10_with_retry", _fake_retry)
    monkeypatch.setattr(OA, "_build_productivity_views_v2", _fake_views)

    n = 4
    forecast = [{"company": f"c{i}", "l6_main": f"L{i}"} for i in range(n)]
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
    assert len(rows) == n

    assert_monotonic(progress, n)


# ---------------------------------------------------------------------------
# mapper — plus ordering assertion: parser_activities before first mapper_chunk
# ---------------------------------------------------------------------------


class _MapperFakePG:
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
        _MapperFakePG.events.append(("parser_report", None))

    async def insert_parser_activities_batch(self, **kw):
        _MapperFakePG.events.append(("parser_activities", len(kw["activities"])))

    async def insert_parser_job_allocations_batch(self, **kw):
        _MapperFakePG.events.append(("job", len(kw["rows"])))

    async def insert_parser_equipment_allocations_batch(self, **kw):
        _MapperFakePG.events.append(("equip", len(kw["rows"])))

    async def insert_mapper_activities_batch(self, **kw):
        kind = "mapper_chunk" if kw.get("idxs") is not None else "mapper_final"
        _MapperFakePG.events.append((kind, len(kw["activities"])))

    async def fetch_all(self, sql, *a):
        return [{"n": 0}]


def _mapper_act(i):
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
async def test_e2e_mapper_progress_and_ordering(monkeypatch):
    """mapper: 0 -> n monotonic AND parser_activities precedes first mapper_chunk."""
    _MapperFakePG.events = []
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "mapper":
            progress.append((processed, total))

    async def _fake_map_one_inner(a, parsed_report, cfg, bp_cand_lookup):
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
    monkeypatch.setattr(G, "PGClient", _MapperFakePG)
    monkeypatch.setattr(G, "_MAPPER_PROGRESS_CHUNK", 20)

    n = 45
    parsed = {
        "project": "P",
        "activities": [_mapper_act(i) for i in range(n)],
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

    # Progress monotonic invariant
    assert_monotonic(progress, n)

    # Ordering: parser_activities must precede first mapper_chunk
    kinds = [e[0] for e in _MapperFakePG.events]
    first_mapper = kinds.index("mapper_chunk")
    assert "parser_activities" in kinds[:first_mapper], (
        f"parser_activities not found before first mapper_chunk; events={_MapperFakePG.events}"
    )
    assert "parser_report" in kinds[:first_mapper], (
        f"parser_report not found before first mapper_chunk; events={_MapperFakePG.events}"
    )

    # All mapper chunks together cover all n activities
    chunk_sizes = [e[1] for e in _MapperFakePG.events if e[0] == "mapper_chunk"]
    assert sum(chunk_sizes) == n
    assert len(chunk_sizes) >= 2
