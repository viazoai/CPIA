from __future__ import annotations

from uuid import uuid4

import pytest

import pipeline.agents.exporter as EX


class _FakePG:
    def __init__(self, url):
        pass

    async def connect(self):
        pass

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_exporter_emits_one_one_on_success(monkeypatch):
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
    monkeypatch.setattr(EX, "PGClient", _FakePG)
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
    assert (0, 1) in progress
    assert (1, 1) in progress
    procs = [p for p, _ in progress]
    assert procs == sorted(procs) and procs[-1] == 1
