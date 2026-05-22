"""B6 — build_atomized_demo_graph compile + node order smoke test."""

from __future__ import annotations

import pytest


def test_build_atomized_demo_graph_compiles(monkeypatch):
    """LangGraph compile 성공 + atomizer 가 entry 다음 노드."""
    import os

    keys = ["POSTGRES_URL", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        pytest.skip(f"env 누락: {missing}")

    # compile 시점에 AsyncConnectionPool.__init__ 이 asyncio.get_running_loop() 호출
    # — InMemorySaver 분기로 우회 (graph topology 검증이 목적이므로 OK).
    monkeypatch.setenv("CPIA_CHECKPOINTER", "memory")

    from pipeline.graph import build_atomized_demo_graph
    from pipeline.api import _build_prod_graph_config

    cfg = _build_prod_graph_config()
    graph = build_atomized_demo_graph(cfg)
    g = graph.get_graph()
    nodes = {n.id for n in g.nodes.values()}
    assert "atomizer" in nodes
    assert "forecaster" in nodes
    assert "hil_2" in nodes
    assert "optimizer" in nodes
    assert "reporter" in nodes

    edges = [(e.source, e.target) for e in g.edges]
    assert any(s == "__start__" and t == "atomizer" for s, t in edges), edges
    assert any(s == "atomizer" and t == "forecaster" for s, t in edges)
