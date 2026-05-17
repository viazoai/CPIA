"""LangGraph StateGraph — Phase 1 mapper + atomizer + forecaster + hil_2 + optimizer.

Spec:
- docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §10
- docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §8
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date as _date

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt  # noqa: F401  (Command re-exported for callers)

from pipeline.agents.atomizer import AtomizerConfig, atomize
from pipeline.agents.forecaster import ForecasterConfig, forecast
from pipeline.agents.mapper import MapperConfig, _prorate_mh, map_activity
from pipeline.agents.optimizer.agent import OptimizerConfig, optimize
from pipeline.agents.optimizer.retrieve import (
    _group_baseline,
    fetch_degradation_cases,
    fetch_recovery_trajectory,
)
from pipeline.checkpointer import build_checkpointer
from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient
from pipeline.state import Activity, CPIAState, ParsedDailyReport


@dataclass
class GraphConfig:
    mapper: MapperConfig
    atomizer: AtomizerConfig
    forecaster: ForecasterConfig
    optimizer: OptimizerConfig  # optimizer cycle Task 8


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


def _build_review_needed(mapped: list[Activity]) -> list[dict]:
    """requires_review=True 인 Activity 만 review payload 빌드.

    Spec §5.1 — interrupt payload schema.
    """
    return [
        {
            "idx": i,
            "work_content": a["work_content"],
            "company": a["company"],
            "trade": a["trade"],
            "wa": a.get("wa"),
            "l6_main": a.get("l6_main"),
            "mapping_conf": a.get("mapping_conf"),
            "mapping_source": a.get("mapping_source"),
        }
        for i, a in enumerate(mapped)
        if a.get("requires_review")
    ]


def _apply_corrections(
    mapped: list[Activity],
    corrections: dict[int, dict],
) -> list[Activity]:
    """corrections dict (idx → {wa, l6_main}) 를 mapped 에 적용.

    Spec §5.1 #6:
    - 답한 row: wa/l6_main 수정 + mapping_source="user_corrected" + requires_review=False
    - 답 안 한 row (review_needed 였으나 corrections 에 없음): Mapper 추천 수용 +
      mapping_source="user_corrected" + requires_review=False (재시도 X — PoC 기본)
    """
    out: list[Activity] = []
    for i, a in enumerate(mapped):
        if a.get("requires_review"):
            c = corrections.get(i)
            if c:
                new_a: Activity = {
                    **a,
                    "wa": c["wa"],
                    "l6_main": c["l6_main"],
                    "mapping_source": "user_corrected",
                    "requires_review": False,
                }
            else:
                new_a = {
                    **a,
                    "mapping_source": "user_corrected",
                    "requires_review": False,
                }
            out.append(new_a)
        else:
            out.append(a)
    return out


async def hil_1_node(state: CPIAState, cfg) -> dict:
    """Mapper 결과 사람 검토. requires_review=True 가 1건 이상이면 interrupt.

    Spec §5.1. cfg = GraphConfig (PG INSERT 용 postgres_url 추출, cfg=None 이면
    PG insert skip — unit 테스트 path).
    """
    mapped = state["mapped"]
    review_needed = _build_review_needed(mapped)
    if not review_needed:
        return {"hil_1_corrections": {}, "current_node": "hil_1"}

    corrections_raw = interrupt({"review_needed": review_needed})
    corrections_raw = corrections_raw or {}
    corrections = {int(k): v for k, v in corrections_raw.items()}

    corrected = _apply_corrections(mapped, corrections)

    if cfg is not None and corrections:
        pg = PGClient(cfg.mapper.postgres_url)
        await pg.connect()
        try:
            run_id_str = state["run_id"]
            run_id = uuid.UUID(run_id_str) if isinstance(run_id_str, str) else run_id_str
            today = _date.fromisoformat(state["date"])
            for idx, c in corrections.items():
                original_a = mapped[idx]
                await pg.insert_mapping_correction(
                    run_id=run_id,
                    report_date=today,
                    original={
                        "work_content": original_a["work_content"],
                        "company": original_a.get("company"),
                        "trade": original_a.get("trade"),
                        "wa": original_a.get("wa"),
                        "l6_main": original_a.get("l6_main"),
                        "mapping_conf": original_a.get("mapping_conf"),
                        "mapping_source": original_a.get("mapping_source"),
                    },
                    corrected={
                        "wa": c["wa"],
                        "l6_main": c["l6_main"],
                        "mapping_source": "user_corrected",
                        "correction_type": "replace",
                    },
                )
        finally:
            await pg.close()

    return {
        "mapped": corrected,
        "hil_1_corrections": corrections,
        "current_node": "hil_1",
    }


async def atomizer_node(state: CPIAState, cfg: GraphConfig) -> dict:
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    parsed: ParsedDailyReport = state["parsed"]
    atomized_ids = await atomize(state["mapped"], parsed, run_id, cfg.atomizer)
    return {"atomized_ids": atomized_ids, "current_node": "atomizer"}


async def forecaster_node(state: CPIAState, cfg: GraphConfig) -> dict:
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    today = _date.fromisoformat(state["date"])
    forecasts = await forecast(state["mapped"], run_id, today, cfg.forecaster)
    return {"forecast": forecasts, "current_node": "forecaster"}


async def hil_2_node(state: CPIAState, cfg: GraphConfig) -> dict:
    """Forecaster 직후 — risky (주의/이상) 그룹별 degradation + recovery 사전 영속 + interrupt.

    Spec §8.2 (F5 정정 — coll.get 1회 + F7 정정 — None 분기).

    원칙:
    - retrieve.fetch_* 호출은 본 노드 책임 (agent.py 는 import X — 결정 #8 / Task 6 test 6.5).
    - Chroma coll.get(...) 그룹당 1회만 호출 후 metadatas/documents 두 함수 (degradation/recovery)
      에 전달 (round-trip 절감).
    - baseline None 또는 main_unit None 일 때 cold_start signal payload 박고 다음 그룹.
    - resume payload (Command(resume=[group_key, ...])) 가 hil_2_selection 으로 영속.
    - risky 0건 → interrupt 미발생, empty selection 반환 → conditional_edge 가 END 분기.
    """
    risky = [r for r in state["forecast"] if r["risk_level"] in {"주의", "이상"}]
    if not risky:
        return {"hil_2_selection": [], "pre_optimizer_cases": {}, "current_node": "hil_2"}

    chroma = ChromaClient(
        host=cfg.optimizer.chroma_host,
        port=cfg.optimizer.chroma_port,
        ssl=cfg.optimizer.chroma_ssl,
    )
    coll = chroma.get_or_create_daily_activities()
    today = _date.fromisoformat(state["date"])

    pre_cases: dict[str, list[dict]] = {}
    payload_groups: list[dict] = []
    for r in risky:
        key = f"{r['company']}|{r['l6_main']}"
        baseline_unit = r.get("main_unit")
        if baseline_unit is None:
            pre_cases[key] = []
            payload_groups.append(
                {
                    "key": key,
                    "assessment": r["assessment"],
                    "risk_level": r["risk_level"],
                    "reasoning": r["reasoning"],
                    "preview_cases": [],
                    "note": "no_main_unit",
                }
            )
            continue

        # F5: coll.get 1회 호출 후 두 함수에 metadatas/documents 전달
        result = coll.get(
            where={"$and": [{"company": r["company"]}, {"l6_main": r["l6_main"]}]},
            include=["metadatas", "documents"],
        )
        metas, docs = result["metadatas"], result["documents"]

        baseline_value = _group_baseline(metas, r["company"], r["l6_main"], baseline_unit)
        if baseline_value is None:
            # F7: None 분기 명시 — pre_cases[key]=[] 후 다음 그룹
            pre_cases[key] = []
            payload_groups.append(
                {
                    "key": key,
                    "assessment": r["assessment"],
                    "risk_level": r["risk_level"],
                    "reasoning": r["reasoning"],
                    "preview_cases": [],
                    "note": "cold_start_no_baseline",
                }
            )
            continue

        cases = fetch_degradation_cases(
            metas,
            docs,
            r["company"],
            r["l6_main"],
            today,
            baseline_unit,
            baseline_value,
            n=5,
        )
        for c in cases:
            c["recovery"] = fetch_recovery_trajectory(
                metas,
                r["company"],
                r["l6_main"],
                c["date"],
                today,
                baseline_unit,
                baseline_value,
                window=7,
            )
        pre_cases[key] = cases
        payload_groups.append(
            {
                "key": key,
                "assessment": r["assessment"],
                "risk_level": r["risk_level"],
                "reasoning": r["reasoning"],
                "today_productivity": r.get("today_productivity"),
                "today_conditions": r.get("today_conditions", ""),
                "preview_cases": cases,
            }
        )

    selected = interrupt({"risky_groups": payload_groups})
    return {
        "hil_2_selection": list(selected) if selected else [],
        "pre_optimizer_cases": pre_cases,
        "current_node": "hil_2",
    }


async def optimizer_node(state: CPIAState, cfg: GraphConfig) -> dict:
    """Optimizer — selected group 별 advice row 생성 + PG insert. retrieve 재호출 X.

    Spec §8.2 + §7. hil_2_node 가 사전 영속한 pre_optimizer_cases 만 소비.
    """
    if not state.get("hil_2_selection"):
        return {"optimizer_advice": [], "current_node": "optimizer"}
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    today = _date.fromisoformat(state["date"])
    advice = await optimize(
        state["forecast"],
        state["hil_2_selection"],
        state["pre_optimizer_cases"],
        run_id,
        today,
        cfg.optimizer,
    )
    return {"optimizer_advice": advice, "current_node": "optimizer"}


def build_demo_graph(cfg: GraphConfig):
    """데모 graph — START → forecaster → hil_2 → (optimizer | END) → END.

    Spec §10.3. Parser/Mapper/Atomizer skip — state["mapped"] 에 가짜 Activity list
    사전 주입 가정 (LLM 비용 회피). build_graph 와 별도 (기존 graph 영향 X).

    `synthetic_daily_report.py` CLI + `test_synthetic_daily_report.py` E2E 가 호출.
    """
    graph = StateGraph(CPIAState)

    async def _forecaster(state: CPIAState) -> dict:
        return await forecaster_node(state, cfg)

    async def _hil_2(state: CPIAState) -> dict:
        return await hil_2_node(state, cfg)

    async def _optimizer(state: CPIAState) -> dict:
        return await optimizer_node(state, cfg)

    graph.add_node("forecaster", _forecaster)
    graph.add_node("hil_2", _hil_2)
    graph.add_node("optimizer", _optimizer)
    graph.add_edge(START, "forecaster")
    graph.add_edge("forecaster", "hil_2")
    graph.add_conditional_edges(
        "hil_2",
        lambda s: "optimizer" if s.get("hil_2_selection") else END,
        {"optimizer": "optimizer", END: END},
    )
    graph.add_edge("optimizer", END)
    return graph.compile(checkpointer=build_checkpointer())


def build_graph(cfg: GraphConfig):
    """StateGraph — mapper → atomizer → forecaster → hil_2 → (optimizer | END) → END.

    conditional_edges:
    - hil_2 → optimizer (hil_2_selection 비어있지 않음)
    - hil_2 → END (hil_2_selection 비어있음 = risky 0건 또는 PM 무선택)
    """
    graph = StateGraph(CPIAState)

    async def _mapper(state: CPIAState) -> dict:
        return await mapper_node(state, cfg)

    async def _hil_1(state: CPIAState) -> dict:
        return await hil_1_node(state, cfg)

    async def _atomizer(state: CPIAState) -> dict:
        return await atomizer_node(state, cfg)

    async def _forecaster(state: CPIAState) -> dict:
        return await forecaster_node(state, cfg)

    async def _hil_2(state: CPIAState) -> dict:
        return await hil_2_node(state, cfg)

    async def _optimizer(state: CPIAState) -> dict:
        return await optimizer_node(state, cfg)

    graph.add_node("mapper", _mapper)
    graph.add_node("hil_1", _hil_1)
    graph.add_node("atomizer", _atomizer)
    graph.add_node("forecaster", _forecaster)
    graph.add_node("hil_2", _hil_2)
    graph.add_node("optimizer", _optimizer)
    graph.add_edge(START, "mapper")
    graph.add_edge("mapper", "hil_1")
    graph.add_edge("hil_1", "atomizer")
    graph.add_edge("atomizer", "forecaster")
    graph.add_edge("forecaster", "hil_2")
    graph.add_conditional_edges(
        "hil_2",
        lambda s: "optimizer" if s.get("hil_2_selection") else END,
        {"optimizer": "optimizer", END: END},
    )
    graph.add_edge("optimizer", END)
    return graph.compile(checkpointer=build_checkpointer())
