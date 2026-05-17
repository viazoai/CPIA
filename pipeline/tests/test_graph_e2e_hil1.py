"""graph.py E2E hil_1 — interrupt + Command(resume=) 2 path.

Spec: docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.1

2 path:
  1. test_hil_1_skip_no_review        — requires_review=False 만 → __interrupt__ 미발생, END 도달
  2. test_hil_1_resume_with_corrections — requires_review=True 1건 → interrupt → resume → 적용 + PG row 1건

전략:
- mapper/atomizer/forecaster/hil_2 노드 module-level monkeypatch (LLM/PG cost 최소).
- hil_1 node 만 실 호출 검증. PG mapping_corrections INSERT 검증은 실 PG round-trip.
- 각 test = unique run_id + unique thread_id 격리.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
import pytest_asyncio
from langgraph.types import Command

from pipeline import graph as graph_module
from pipeline.agents.atomizer import AtomizerConfig
from pipeline.agents.forecaster import ForecasterConfig
from pipeline.agents.mapper import MapperConfig
from pipeline.agents.optimizer import OptimizerConfig
from pipeline.db import PGClient
from pipeline.graph import GraphConfig, build_graph


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
    )


@pytest_asyncio.fixture
async def run_row(cfg):
    """pipeline_runs row 1건 + cascade cleanup (mapping_corrections + forecasts + optimizer_advice)."""
    pg = PGClient(cfg.optimizer.postgres_url)
    await pg.connect()
    run_id = uuid.uuid4()
    try:
        await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
        try:
            yield run_id
        finally:
            async with pg._pool.acquire() as conn:
                await conn.execute("DELETE FROM mapping_corrections WHERE run_id = $1", run_id)
                await conn.execute("DELETE FROM optimizer_advice WHERE run_id = $1", run_id)
                await conn.execute("DELETE FROM forecasts WHERE run_id = $1", run_id)
            await pg.delete_pipeline_run(run_id)
    finally:
        await pg.close()


def _activity_dict(idx: int, requires_review: bool, mapping_conf: float = 0.85) -> dict:
    """fixture helper — Activity 19 키."""
    return {
        "wbs_activity_id": None,
        "l5_disc": "건축",
        "l6_main": "철근콘크리트공사",
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "trade": "철근콘크리트공사",
        "company": f"company_{idx}",
        "unit": "m3",
        "today_qty": 10.0,
        "work_content": f"work_{idx}",
        "conditions": ["맑음"],
        "assigned_workers": 5.0,
        "worker_source": "mh_prorated",
        "plan_total_qty": None,
        "plan_mh": None,
        "wa": "OLD_WA",
        "mapping_conf": mapping_conf,
        "mapping_source": "hil_required" if requires_review else "auto_bp_single",
        "requires_review": requires_review,
    }


def _patch_non_hil1_nodes(monkeypatch, mapped: list[dict]) -> None:
    """mapper / atomizer / forecaster / hil_2 / optimizer 스텁 — LLM/외부 호출 0.

    mapper 는 인자로 받은 `mapped` 반환. hil_1 만 실 호출.
    """

    async def _stub_mapper(state, cfg):
        return {"mapped": mapped, "current_node": "mapper"}

    async def _stub_atomizer(state, cfg):
        return {"atomized_ids": [], "current_node": "atomizer"}

    async def _stub_forecaster(state, cfg):
        return {"forecast": [], "current_node": "forecaster"}

    async def _stub_hil_2(state, cfg):
        return {"hil_2_selection": [], "pre_optimizer_cases": {}, "current_node": "hil_2"}

    async def _stub_optimizer(state, cfg):
        return {"optimizer_advice": [], "current_node": "optimizer"}

    monkeypatch.setattr(graph_module, "mapper_node", _stub_mapper)
    monkeypatch.setattr(graph_module, "atomizer_node", _stub_atomizer)
    monkeypatch.setattr(graph_module, "forecaster_node", _stub_forecaster)
    monkeypatch.setattr(graph_module, "hil_2_node", _stub_hil_2)
    monkeypatch.setattr(graph_module, "optimizer_node", _stub_optimizer)


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


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_hil_1_skip_no_review(cfg, run_row, monkeypatch):
    """requires_review=False 만 → __interrupt__ 미발생, END 도달."""
    mapped = [_activity_dict(0, False), _activity_dict(1, False)]
    _patch_non_hil1_nodes(monkeypatch, mapped)
    graph = build_graph(cfg)
    thread_id = f"hil1-skip-{run_row}"
    graph_config = {"configurable": {"thread_id": thread_id}}
    state = _initial_state(run_row)

    final = await graph.ainvoke(state, config=graph_config)

    assert "__interrupt__" not in final, (
        f"requires_review=False 만인데 __interrupt__ 발생: {final.get('__interrupt__')}"
    )
    assert final.get("hil_1_corrections") == {}
    # END 도달 (hil_2 stub 의 current_node="hil_2" 가 마지막 stub 통과 후 conditional_edge → END)
    assert final.get("current_node") in {"hil_1", "hil_2", "atomizer", "forecaster", "optimizer"}


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_hil_1_resume_with_corrections(cfg, run_row, monkeypatch):
    """requires_review=True 1건 → interrupt → resume → 적용 + PG row 1건."""
    mapped = [
        _activity_dict(0, True, mapping_conf=0.55),  # requires_review=True
        _activity_dict(1, False),
    ]
    _patch_non_hil1_nodes(monkeypatch, mapped)
    graph = build_graph(cfg)
    thread_id = f"hil1-resume-{run_row}"
    graph_config = {"configurable": {"thread_id": thread_id}}
    state = _initial_state(run_row)

    # 1st ainvoke → __interrupt__
    first = await graph.ainvoke(state, config=graph_config)
    assert "__interrupt__" in first, f"interrupt 미발생: keys={list(first.keys())}"
    interrupts = first["__interrupt__"]
    payload = interrupts[0].value
    assert "review_needed" in payload
    rn = payload["review_needed"]
    assert len(rn) == 1
    assert rn[0]["idx"] == 0
    assert rn[0]["work_content"] == "work_0"
    assert rn[0]["mapping_conf"] == 0.55
    assert rn[0]["mapping_source"] == "hil_required"

    # 2nd ainvoke with Command(resume={"0": {...}})
    # LangGraph 의 multi-resume 검사 (is_xxh3_128_hexdigest) 가 int key 에서 TypeError 발생 →
    # JSON round-trip 정합 str key 사용. hil_1_node 가 int(k) 변환 처리.
    final = await graph.ainvoke(
        Command(resume={"0": {"wa": "USER_CORRECTED", "l6_main": "철근콘크리트공사"}}),
        config=graph_config,
    )

    # corrections 박힘 (hil_1_node 가 int 로 변환)
    assert final.get("hil_1_corrections") == {0: {"wa": "USER_CORRECTED", "l6_main": "철근콘크리트공사"}}
    # mapped[0] 수정됨
    mapped_final = final["mapped"]
    assert mapped_final[0]["wa"] == "USER_CORRECTED"
    assert mapped_final[0]["mapping_source"] == "user_corrected"
    assert mapped_final[0]["requires_review"] is False
    # mapped[1] 영향 없음
    assert mapped_final[1]["wa"] == "OLD_WA"
    assert mapped_final[1]["requires_review"] is False

    # PG mapping_corrections row 1건
    pg = PGClient(cfg.mapper.postgres_url)
    await pg.connect()
    try:
        async with pg._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT original, corrected FROM mapping_corrections WHERE run_id=$1",
                run_row,
            )
        assert len(rows) == 1
        original = (
            json.loads(rows[0]["original"]) if isinstance(rows[0]["original"], str) else rows[0]["original"]
        )
        corrected = (
            json.loads(rows[0]["corrected"])
            if isinstance(rows[0]["corrected"], str)
            else rows[0]["corrected"]
        )
        assert original["work_content"] == "work_0"
        assert original["company"] == "company_0"
        assert original["mapping_source"] == "hil_required"
        assert corrected["wa"] == "USER_CORRECTED"
        assert corrected["mapping_source"] == "user_corrected"
        assert corrected["correction_type"] == "replace"
    finally:
        await pg.close()
