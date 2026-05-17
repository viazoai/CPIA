"""graph.py E2E 회귀 — Phase 1 (mapper_node + atomizer_node).

Spec: docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md §1, Task 5.
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

from pipeline.agents.atomizer import AtomizerConfig
from pipeline.agents.forecaster import ForecasterConfig
from pipeline.agents.mapper import MapperConfig
from pipeline.agents.optimizer import OptimizerConfig
from pipeline.agents.parser import parse_daily_report
from pipeline.agents.reporter import ReporterConfig
from pipeline.chroma_client import ChromaClient
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
        reporter=ReporterConfig(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            llm_model=os.environ["LLM_MODEL"],
            postgres_url=common_pg,
        ),
    )


@pytest.fixture
def wbs_master_ready(cfg):
    """wbs_master Chroma 컬렉션 사전조건.

    load_master_list.py 는 (company, l6_main) 그룹 단위로 적재하므로
    실제 row 수는 unique BP 사 × l6_main 조합 수 (현 30). 비어있지 않은가만 보장.
    """
    chroma = ChromaClient(
        host=cfg.atomizer.chroma_host,
        port=cfg.atomizer.chroma_port,
        ssl=cfg.atomizer.chroma_ssl,
    )
    coll = chroma.get_or_create_wbs_master()
    count = coll.count()
    assert count >= 30, (
        f"wbs_master Chroma 컬렉션 row 수: {count} < 30. `scripts/load_master_list.py` 실행 필요."
    )


@pytest_asyncio.fixture
async def run_row(cfg):
    pg = PGClient(cfg.atomizer.postgres_url)
    await pg.connect()
    run_id = uuid.uuid4()
    try:
        await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
        try:
            yield run_id
        finally:
            await pg.delete_pipeline_run(run_id)
    finally:
        await pg.close()


@pytest.mark.slow
@pytest.mark.golden
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_graph_e2e_namwong_47(cfg, wbs_master_ready, run_row):
    """E2E: 9/25 작업일보 (남웅 47 row, 비계 제외) → mapper → atomizer → Chroma 적재.

    Task 4 dedup: 47 input → 11 unique doc_id (same work_content collapse).
    """
    xlsx_path = (
        "/Users/kyungseoplee/Project Agent/CPIA/docs/sample/"
        "통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
    )
    parsed = parse_daily_report(xlsx_path)

    namwong_acts = [
        a for a in parsed["activities"] if a["company"] == "남웅건설" and "비계" not in a["work_content"]
    ]
    assert len(namwong_acts) == 47, f"남웅 (비계 제외): {len(namwong_acts)} (예상 47)"

    parsed_filtered = {**parsed, "activities": namwong_acts}

    state = {
        "run_id": str(run_row),
        "date": "2025-09-25",
        "input_files": [xlsx_path],
        "raw_texts": {},
        "parsed": parsed_filtered,
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

    graph = build_graph(cfg)
    # optimizer cycle Task 8 — graph compiled with InMemorySaver checkpointer,
    # thread_id 필수 (interrupt/resume cycle 의 thread-local 상태 key).
    graph_config = {"configurable": {"thread_id": str(run_row)}}
    final = await graph.ainvoke(state, config=graph_config)

    assert len(final["mapped"]) == 47, f"mapped 수: {len(final['mapped'])}"
    assert all(a["l6_main"] == "철근콘크리트공사" for a in final["mapped"]), (
        f"l6_main 불일치: {set(a['l6_main'] for a in final['mapped'])}"
    )
    assert all(a["assigned_workers"] == 88.0 for a in final["mapped"]), (
        f"assigned_workers 값들: {set(a['assigned_workers'] for a in final['mapped'])}"
    )
    # Task 4 dedup 결과 = 11 unique doc_id (남웅 47 row → 11 unique work_content)
    assert len(final["atomized_ids"]) == 11, f"atomized_ids 수: {len(final['atomized_ids'])} (예상 11)"

    # Task 9 (forecaster_node) 후 forecast row 1건 생성 (남웅 = 1 (company, l6_main))
    assert len(final["forecast"]) == 1, f"forecast 수: {len(final['forecast'])}"
    forecast_row = final["forecast"][0]
    assert forecast_row["company"] == "남웅건설"
    assert forecast_row["l6_main"] == "철근콘크리트공사"
    assert forecast_row["today_assigned_workers"] == pytest.approx(88.0)
    assert forecast_row["assessment"] in {"정상", "주의", "이상", None}
    assert forecast_row["risk_level"] in {"정상", "주의", "이상", None}
    assert forecast_row["schedule_state"] in {"early", "on_schedule", "post_due", "unknown"}

    # optimizer cycle Task 8 — hil_2 / optimizer 노드 통합 검증.
    # 비-risky path (risk_level ∈ {정상, None}): hil_2 가 interrupt 미발생 → END 직행.
    # risky path (주의/이상): hil_2 가 interrupt → __interrupt__ payload 박힘 (resume 없음).
    if forecast_row["risk_level"] in {"주의", "이상"}:
        assert "__interrupt__" in final, (
            "risky path 인데 __interrupt__ 미발생 — hil_2_node interrupt 호출 누락 의심"
        )
    else:
        assert final.get("hil_2_selection") == [], (
            f"non-risky path: hil_2_selection != [] ({final.get('hil_2_selection')})"
        )
        assert final.get("pre_optimizer_cases") == {}, (
            f"non-risky path: pre_optimizer_cases != {{}} ({final.get('pre_optimizer_cases')})"
        )
        assert final.get("optimizer_advice") == [], (
            f"non-risky path: optimizer_advice != [] ({final.get('optimizer_advice')})"
        )
