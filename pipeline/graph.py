"""LangGraph StateGraph — Phase 1 mapper + atomizer + forecaster.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §10
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from langgraph.graph import END, START, StateGraph

from pipeline.agents.atomizer import AtomizerConfig, atomize
from pipeline.agents.forecaster import ForecasterConfig, forecast
from pipeline.agents.mapper import MapperConfig, _prorate_mh, map_activity
from pipeline.db import PGClient
from pipeline.state import Activity, CPIAState, ParsedDailyReport


@dataclass
class GraphConfig:
    mapper: MapperConfig
    atomizer: AtomizerConfig
    forecaster: ForecasterConfig


async def mapper_node(state: CPIAState, cfg: GraphConfig) -> dict:
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
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    parsed: ParsedDailyReport = state["parsed"]
    atomized_ids = await atomize(state["mapped"], parsed, run_id, cfg.atomizer)
    return {"atomized_ids": atomized_ids, "current_node": "atomizer"}


async def forecaster_node(state: CPIAState, cfg: GraphConfig) -> dict:
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    today = date.fromisoformat(state["date"])
    forecasts = await forecast(state["mapped"], run_id, today, cfg.forecaster)
    return {"forecast": forecasts, "current_node": "forecaster"}


def build_graph(cfg: GraphConfig):
    """Phase 1 StateGraph — mapper → atomizer → forecaster → END."""
    graph = StateGraph(CPIAState)

    async def _mapper(state: CPIAState) -> dict:
        return await mapper_node(state, cfg)

    async def _atomizer(state: CPIAState) -> dict:
        return await atomizer_node(state, cfg)

    async def _forecaster(state: CPIAState) -> dict:
        return await forecaster_node(state, cfg)

    graph.add_node("mapper", _mapper)
    graph.add_node("atomizer", _atomizer)
    graph.add_node("forecaster", _forecaster)
    graph.add_edge(START, "mapper")
    graph.add_edge("mapper", "atomizer")
    graph.add_edge("atomizer", "forecaster")
    graph.add_edge("forecaster", END)
    return graph.compile()
