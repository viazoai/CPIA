from __future__ import annotations

from uuid import uuid4

import pytest

import pipeline.agents.parser_node as pn


@pytest.mark.asyncio
async def test_parser_node_emits_monotonic_progress(monkeypatch):
    """parser_node: (0, len(files)) 선기록 후 파일마다 processed 단조 증가 → total."""
    calls: list[tuple[str, int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        calls.append((agent, processed, total))

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

    monkeypatch.setattr(pn, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(pn, "parse_daily_report", _fake_parse)

    state = {
        "run_id": str(uuid4()),
        "postgres_url": "postgresql://x",
        "input_files": ["/a.xlsm", "/b.xlsm", "/c.xlsm"],
    }
    out = await pn.parser_node(state)
    assert "parsed" in out

    parser_calls = [c for c in calls if c[0] == "parser"]
    assert all(t == 3 for _, _, t in parser_calls)
    processed_seq = [p for _, p, _ in parser_calls]
    assert processed_seq[0] == 0
    assert processed_seq == sorted(processed_seq)
    assert processed_seq[-1] == 3
