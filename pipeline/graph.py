"""LangGraph StateGraph — Phase 1 mapper_node + atomizer_node 만.

Spec: docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md §1.

interrupt 2개 + Reporter/Forecaster/Optimizer 통합은 차후 graph.py spec 에서.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph

from pipeline.agents.atomizer import AtomizerConfig, atomize
from pipeline.agents.mapper import MapperConfig, _prorate_mh, map_activity
from pipeline.db import PGClient
from pipeline.state import Activity, CPIAState, ParsedDailyReport


@dataclass
class GraphConfig:
    mapper: MapperConfig
    atomizer: AtomizerConfig


async def mapper_node(state: CPIAState, cfg: GraphConfig) -> dict:
    """mapper_node — map_activity (각 Activity) + _prorate_mh (batch 분배)."""
    parsed: ParsedDailyReport = state["parsed"]

    mapped: list[Activity] = []
    for activity in parsed["activities"]:
        result = await map_activity(activity, parsed_report=parsed, cfg=cfg.mapper)
        mapped.append(result)

    pg = PGClient(cfg.mapper.postgres_url)
    await pg.connect()
    try:
        mapped = await _prorate_mh(mapped, parsed, pg)
    finally:
        await pg.close()

    return {"mapped": mapped, "current_node": "mapper"}


async def atomizer_node(state: CPIAState, cfg: GraphConfig) -> dict:
    """atomizer_node — atomize (Chroma daily_activities 적재)."""
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    parsed: ParsedDailyReport = state["parsed"]

    atomized_ids = await atomize(state["mapped"], parsed, run_id, cfg.atomizer)

    return {"atomized_ids": atomized_ids, "current_node": "atomizer"}


def build_graph(cfg: GraphConfig):
    """LangGraph StateGraph — Phase 1 (mapper + atomizer 만).

    inner async def 로 cfg 캡처 — lambda 회피 (reviewer C3 권고).
    """
    graph = StateGraph(CPIAState)

    async def _mapper(state: CPIAState) -> dict:
        return await mapper_node(state, cfg)

    async def _atomizer(state: CPIAState) -> dict:
        return await atomizer_node(state, cfg)

    graph.add_node("mapper", _mapper)
    graph.add_node("atomizer", _atomizer)
    graph.add_edge(START, "mapper")
    graph.add_edge("mapper", "atomizer")
    graph.add_edge("atomizer", END)
    return graph.compile()
