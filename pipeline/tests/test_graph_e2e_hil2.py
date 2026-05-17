"""graph.py E2E hil_2 — interrupt + Command(resume=) 4 path (Task 9 slow).

Spec: docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §12.3

4 path:
  1. test_graph_e2e_hil2_interrupt_payload     — risky 1건 → __interrupt__ + preview_cases schema
  2. test_graph_e2e_hil2_resume_optimizer      — Command(resume=[key]) → optimizer → END
  3. test_graph_e2e_hil2_skip_no_risky         — risky 0건 → conditional edge END 직행
  4. test_graph_e2e_hil2_resume_empty_selection — Command(resume=[]) → optimizer skip → END

전략:
- mapper/atomizer/forecaster 노드는 module-level monkeypatch 로 무력화 (LLM cost 0).
- hil_2 node 는 실 Chroma + 실 PG 호출 — 남웅|철근콘크리트공사|m3 가 Task 3 적재 데이터로 baseline + degradation cases 검색 가능 (test_optimize_namwong_e2e 와 동일 데이터셋).
- test 2 (resume → optimizer) 만 실 Azure LLM 호출 (1 회, $0.01~0.05).
- 각 test 는 unique run_id + unique thread_id 로 격리.
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from langgraph.types import Command

from pipeline.agents.atomizer import AtomizerConfig
from pipeline.agents.forecaster import ForecasterConfig
from pipeline.agents.mapper import MapperConfig
from pipeline.agents.optimizer import OptimizerConfig
from pipeline.agents.reporter import ReporterConfig
from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient
from pipeline import graph as graph_module
from pipeline.graph import GraphConfig, build_graph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg() -> GraphConfig:
    keys = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION",
        "LLM_MODEL",
        "EMBEDDING_MODEL",
        "POSTGRES_URL",
        "CHROMA_HOST",
    ]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        pytest.skip(f"env 누락: {missing}")
    common_pg = os.environ["POSTGRES_URL"]
    common_chroma_host = os.environ["CHROMA_HOST"]
    common_chroma_port = int(os.environ.get("CHROMA_PORT", "8000"))
    common_chroma_ssl = os.environ.get("CHROMA_SSL", "false").lower() == "true"
    return GraphConfig(
        mapper=MapperConfig(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            llm_model=os.environ["LLM_MODEL"],
            embedding_model=os.environ["EMBEDDING_MODEL"],
            postgres_url=common_pg,
            chroma_host=common_chroma_host,
            chroma_port=common_chroma_port,
            chroma_ssl=common_chroma_ssl,
        ),
        atomizer=AtomizerConfig(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            embedding_model=os.environ["EMBEDDING_MODEL"],
            postgres_url=common_pg,
            chroma_host=common_chroma_host,
            chroma_port=common_chroma_port,
            chroma_ssl=common_chroma_ssl,
        ),
        forecaster=ForecasterConfig(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            llm_model=os.environ["LLM_MODEL"],
            embedding_model=os.environ["EMBEDDING_MODEL"],
            postgres_url=common_pg,
            chroma_host=common_chroma_host,
            chroma_port=common_chroma_port,
            chroma_ssl=common_chroma_ssl,
        ),
        optimizer=OptimizerConfig(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            llm_model=os.environ["LLM_MODEL"],
            postgres_url=common_pg,
            chroma_host=common_chroma_host,
            chroma_port=common_chroma_port,
            chroma_ssl=common_chroma_ssl,
        ),
        reporter=ReporterConfig(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            llm_model=os.environ["LLM_MODEL"],
            postgres_url=common_pg,
        ),
    )


@pytest_asyncio.fixture
async def run_row(cfg):
    """pipeline_runs row 1건 + cascade cleanup (optimizer_advice + forecasts)."""
    pg = PGClient(cfg.optimizer.postgres_url)
    await pg.connect()
    run_id = uuid.uuid4()
    try:
        await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
        try:
            yield run_id
        finally:
            async with pg._pool.acquire() as conn:
                await conn.execute("DELETE FROM optimizer_advice WHERE run_id = $1", run_id)
                await conn.execute("DELETE FROM forecasts WHERE run_id = $1", run_id)
            await pg.delete_pipeline_run(run_id)
    finally:
        await pg.close()


@pytest.fixture
def chroma_ready(cfg):
    """daily_activities 컬렉션 사전조건 — 남웅|철근콘크리트공사 그룹 cases >= 3 보장.

    Task 3 적재 (synthetic_v2 90일 × 27 그룹) 후 남웅|철콘 비-incident row >= 50 보유.
    """
    chroma = ChromaClient(
        host=cfg.optimizer.chroma_host,
        port=cfg.optimizer.chroma_port,
        ssl=cfg.optimizer.chroma_ssl,
    )
    coll = chroma.get_or_create_daily_activities()
    res = coll.get(
        where={"$and": [{"company": "남웅건설"}, {"l6_main": "철근콘크리트공사"}]},
        include=["metadatas"],
    )
    metas = res.get("metadatas") or []
    assert len(metas) >= 20, (
        f"daily_activities (남웅|철콘) row 수: {len(metas)} < 20. "
        "`python -m pipeline.agents.optimizer.synthetic_v2 ...` (Task 3) 실행 필요."
    )


# ---------------------------------------------------------------------------
# Monkeypatch helpers — mapper/atomizer/forecaster 노드 stub 화
# ---------------------------------------------------------------------------


def _make_risky_forecast_row() -> dict:
    """남웅|철근콘크리트공사 risky 1건 stub.

    실 Chroma 의 남웅|철콘|m3 baseline_v2 ≈ 31.0 (test_synthetic_v2_baseline_recheck_after_load).
    today_productivity 12.5 = baseline 의 ~40% → 의도적 'risk_level=이상' 시그널.
    hil_2_node 가 이 row 를 보고 degradation cases 5건 검색 (cases >= 3 → cold_start X).
    """
    return {
        "company": "남웅건설",
        "l6_main": "철근콘크리트공사",
        "assessment": "이상",
        "risk_level": "이상",
        "reasoning": "test stub — today_productivity 가 baseline 의 ~40% (의도적 이상)",
        "main_unit": "m3",
        "today_productivity": 12.5,
        "today_assigned_workers": 88.0,
        "today_conditions": "맑음,장비대기",
    }


def _make_normal_forecast_row() -> dict:
    """risky 0건 시나리오 — risk_level=정상 1건 (hil_2 가 interrupt 미발생)."""
    return {
        "company": "남웅건설",
        "l6_main": "철근콘크리트공사",
        "assessment": "정상",
        "risk_level": "정상",
        "reasoning": "test stub — risk_level=정상 (skip path)",
        "main_unit": "m3",
        "today_productivity": 31.0,
        "today_assigned_workers": 88.0,
        "today_conditions": "맑음",
    }


def _patch_pre_hil2_nodes(monkeypatch, forecast_rows: list[dict]) -> None:
    """mapper / atomizer / forecaster 노드를 stub 으로 치환.

    forecast_rows 가 hil_2_node 에 그대로 전달됨. LLM 호출 0, DB 호출 0.
    """

    async def _stub_mapper(state, cfg):
        return {"mapped": [], "current_node": "mapper"}

    async def _stub_atomizer(state, cfg):
        return {"atomized_ids": [], "current_node": "atomizer"}

    async def _stub_forecaster(state, cfg):
        return {"forecast": forecast_rows, "current_node": "forecaster"}

    monkeypatch.setattr(graph_module, "mapper_node", _stub_mapper)
    monkeypatch.setattr(graph_module, "atomizer_node", _stub_atomizer)
    monkeypatch.setattr(graph_module, "forecaster_node", _stub_forecaster)


def _initial_state(run_id: uuid.UUID) -> dict:
    return {
        "run_id": str(run_id),
        "date": "2025-09-25",
        "input_files": [],
        "raw_texts": {},
        "parsed": {
            "report_date": "2025-09-25",
            "project": "M15X_PH3_IBL",
            "bp_summaries": [],
            "job_allocations": [],
            "equipment_allocations": [],
            "activities": [],
        },
        "mapped": [],
        "hil_1_corrections": {},
        "atomized_ids": [],
        "report_md": "",
        "forecast": [],
        "hil_2_selection": [],
        "pre_optimizer_cases": {},
        "optimizer_advice": [],
        "current_node": "",
        "status": "running",
    }


# ---------------------------------------------------------------------------
# Test 1 — risky 1건 → __interrupt__ + payload schema
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_graph_e2e_hil2_interrupt_payload(cfg, chroma_ready, run_row, monkeypatch):
    """risky 1건 fixture → graph.ainvoke → __interrupt__ + preview_cases schema 검증.

    spec §12.3 ①: payload 필드 검증.
    """
    _patch_pre_hil2_nodes(monkeypatch, [_make_risky_forecast_row()])
    graph = build_graph(cfg)
    thread_id = f"hil2-interrupt-{run_row}"
    graph_config = {"configurable": {"thread_id": thread_id}}
    state = _initial_state(run_row)

    final = await graph.ainvoke(state, config=graph_config)

    # __interrupt__ payload 존재
    assert "__interrupt__" in final, "risky 1건 인데 __interrupt__ 미발생"
    interrupts = final["__interrupt__"]
    assert len(interrupts) >= 1, f"interrupt list empty: {interrupts}"
    payload = interrupts[0].value
    # payload schema: {"risky_groups": [...]}
    assert "risky_groups" in payload, f"interrupt payload missing 'risky_groups': {payload}"
    groups = payload["risky_groups"]
    assert len(groups) == 1, f"risky_groups 수: {len(groups)} (expected 1)"
    g = groups[0]
    # spec §12.3 ①: key + assessment + risk_level + today_productivity + today_conditions + preview_cases
    assert g["key"] == "남웅건설|철근콘크리트공사"
    assert g["assessment"] == "이상"
    assert g["risk_level"] == "이상"
    assert g["today_productivity"] == 12.5
    assert g["today_conditions"] == "맑음,장비대기"
    assert "preview_cases" in g
    assert isinstance(g["preview_cases"], list)
    # cases >= 3 (cold_start X) — 남웅|철콘 Chroma 데이터 적재 전제
    assert len(g["preview_cases"]) >= 3, (
        f"preview_cases len = {len(g['preview_cases'])} < 3 — cold_start path 진입 "
        "(Task 3 적재 미실행 또는 baseline_v2 None 의심)"
    )
    # 각 case 가 retrieve.fetch_degradation_cases + recovery 머지 구조
    for c in g["preview_cases"]:
        assert "date" in c
        assert "conditions" in c
        assert "productivity" in c
        assert "recovery" in c
        assert "recovery_days" in c["recovery"]


# ---------------------------------------------------------------------------
# Test 2 — Command(resume=[key]) → optimizer node 실행 (실 LLM 1 회)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_graph_e2e_hil2_resume_optimizer(cfg, chroma_ready, run_row, monkeypatch):
    """interrupt 발생 후 Command(resume=[key]) → optimizer 실행 → END.

    실 Azure LLM 1 회 호출 (gpt-5.1-chat-ai-board-test) — cost ~$0.01~0.05.
    final state: optimizer_advice 1건 이상.
    """
    _patch_pre_hil2_nodes(monkeypatch, [_make_risky_forecast_row()])
    graph = build_graph(cfg)
    thread_id = f"hil2-resume-{run_row}"
    graph_config = {"configurable": {"thread_id": thread_id}}
    state = _initial_state(run_row)

    # 1st ainvoke → __interrupt__ 까지 진행
    first = await graph.ainvoke(state, config=graph_config)
    assert "__interrupt__" in first

    key = "남웅건설|철근콘크리트공사"
    # 2nd ainvoke with Command(resume=[key]) → optimizer 실행
    final = await graph.ainvoke(Command(resume=[key]), config=graph_config)

    # hil_2_selection 박힘
    assert final.get("hil_2_selection") == [key]
    # pre_optimizer_cases 박힘 (>=3건 cases)
    cases = final["pre_optimizer_cases"].get(key, [])
    assert len(cases) >= 3, f"pre_optimizer_cases[{key}] len = {len(cases)} < 3"
    # optimizer_advice 1건 (실 LLM 응답)
    advice = final.get("optimizer_advice", [])
    assert len(advice) >= 1, f"optimizer_advice 수: {len(advice)} (expected >= 1)"
    row = advice[0]
    assert row["company"] == "남웅건설"
    assert row["l6_main"] == "철근콘크리트공사"
    assert row["forecast_assessment"] == "이상"
    # LLM path (cold_start X — cases >= 3) → diagnosis 가 sentinel 아닌 실 str
    assert isinstance(row["diagnosis"], str)
    assert row["diagnosis"] != "cold_start"
    assert len(row["diagnosis"]) > 0
    # recommendations 1건 이상
    assert len(row["recommendations"]) >= 1
    # 신 graph: optimizer → reporter → END (hil1-forecaster-reporter cycle)
    assert final.get("current_node") == "reporter"


# ---------------------------------------------------------------------------
# Test 3 — risky 0건 → __interrupt__ 미발생, END 직행
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_graph_e2e_hil2_skip_no_risky(cfg, run_row, monkeypatch):
    """risky 0건 → hil_2 가 interrupt 미발생 → conditional_edge 가 END 분기.

    final state: hil_2_selection=[], pre_optimizer_cases={}, optimizer_advice=[].
    """
    _patch_pre_hil2_nodes(monkeypatch, [_make_normal_forecast_row()])
    graph = build_graph(cfg)
    thread_id = f"hil2-skip-{run_row}"
    graph_config = {"configurable": {"thread_id": thread_id}}
    state = _initial_state(run_row)

    final = await graph.ainvoke(state, config=graph_config)

    # __interrupt__ 없음
    assert "__interrupt__" not in final, f"risky 0건 인데 __interrupt__ 발생: {final.get('__interrupt__')}"
    # hil_2 노드는 빈 selection / 빈 cases 만 박고 END 분기
    assert final.get("hil_2_selection") == []
    assert final.get("pre_optimizer_cases") == {}
    # optimizer 노드 미실행 → optimizer_advice 빈 list (initial_state 값 그대로)
    assert final.get("optimizer_advice") == []
    # 신 graph: hil_2 → reporter → END (hil1-forecaster-reporter cycle)
    assert final.get("current_node") == "reporter"


# ---------------------------------------------------------------------------
# Test 4 — Command(resume=[]) → optimizer skip (PM 빈 선택)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_graph_e2e_hil2_resume_empty_selection(cfg, chroma_ready, run_row, monkeypatch):
    """risky 1건 + Command(resume=[]) (PM 빈 선택) → conditional_edge END 분기.

    final state: hil_2_selection=[], optimizer_advice=[]. LLM 호출 0.
    """
    _patch_pre_hil2_nodes(monkeypatch, [_make_risky_forecast_row()])
    graph = build_graph(cfg)
    thread_id = f"hil2-empty-{run_row}"
    graph_config = {"configurable": {"thread_id": thread_id}}
    state = _initial_state(run_row)

    # 1st ainvoke → __interrupt__
    first = await graph.ainvoke(state, config=graph_config)
    assert "__interrupt__" in first

    # 2nd ainvoke with Command(resume=[]) → optimizer skip
    final = await graph.ainvoke(Command(resume=[]), config=graph_config)

    assert "__interrupt__" not in final, f"resume=[] 후 재발생한 __interrupt__: {final.get('__interrupt__')}"
    assert final.get("hil_2_selection") == []
    # optimizer 미실행 → optimizer_advice 빈 list (초기값 그대로)
    assert final.get("optimizer_advice") == []
    # 신 graph: hil_2 conditional_edge 가 optimizer 우회 시에도 reporter 진입 → END
    assert final.get("current_node") == "reporter"
