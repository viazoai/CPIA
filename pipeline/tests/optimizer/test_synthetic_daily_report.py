"""synthetic_daily_report.py 테스트 — 가짜 작업일보 + build_demo_graph (Task 11).

Spec: docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §10

2 test:
1. test_generate_fake_daily_report_unit            — pure unit. Activity dict 형식 + count.
2. test_demo_graph_e2e_namwong_dolgwan (@slow)     — fake mapped → build_demo_graph →
   __interrupt__ → Command(resume=[key]) → optimizer advice 1건. 실 LLM 1 회 (~$0.01~0.05).
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from langgraph.types import Command

from pipeline.agents.optimizer.synthetic_daily_report import (
    _initial_state,
    build_demo_graph_config,
    generate_fake_daily_report,
)
from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient


# ---------------------------------------------------------------------------
# Unit — generate_fake_daily_report
# ---------------------------------------------------------------------------


def test_generate_fake_daily_report_unit():
    """pure unit — Activity dict schema + count + conditions list + workers_ratio."""
    scenarios = [
        {
            "company": "남웅건설",
            "l6_main": "철근콘크리트공사",
            "n_activities": 5,
            "incident": "돌관",
            "productivity_ratio": 0.45,
            "workers_ratio": 1.3,
            "unit": "m3",
        },
        {
            "company": "세보엠이씨",
            "l6_main": "기계소화설비",
            "n_activities": 3,
            "incident": "정상",
            "productivity_ratio": 1.0,
            "workers_ratio": 1.0,
            "unit": "m",
        },
    ]
    pools = {
        ("남웅건설", "철근콘크리트공사"): ["철근배근", "거푸집설치", "콘크리트타설"],
        ("세보엠이씨", "기계소화설비"): ["스프링클러배관"],
    }
    baseline_workers = {
        ("남웅건설", "철근콘크리트공사"): 10.0,
        ("세보엠이씨", "기계소화설비"): 50.0,
    }
    baseline_qty = {
        ("남웅건설", "철근콘크리트공사", "m3"): 31.0,
        ("세보엠이씨", "기계소화설비", "m"): 20.0,
    }
    acts = generate_fake_daily_report(
        report_date="2025-09-27",
        scenarios=scenarios,
        activity_pools=pools,
        baseline_workers=baseline_workers,
        baseline_qty=baseline_qty,
    )

    # 5 + 3 = 8 Activity
    assert len(acts) == 8

    # 첫 5건은 남웅 (돌관)
    nw = [a for a in acts if a["company"] == "남웅건설"]
    assert len(nw) == 5
    a0 = nw[0]
    # conditions 는 list[str] — state.Activity 계약 (forecaster:92 iterate)
    assert isinstance(a0["conditions"], list)
    assert "맑음" in a0["conditions"]
    assert "돌관" in a0["conditions"]
    # workers_ratio=1.3 → 10 × 1.3 = 13.0
    assert a0["assigned_workers"] == 13.0
    # productivity_ratio=0.45, n_activities=5 → row 당 31.0 × 0.45 / 5 = 2.79 → round(1) = 2.8
    # group total (5 row 합산) = 5 × 2.8 = 14.0 (= baseline_q × ratio, 의도 부합)
    assert a0["today_qty"] == round(31.0 * 0.45 / 5, 1)
    assert sum(a["today_qty"] for a in nw) == pytest.approx(round(31.0 * 0.45 / 5, 1) * 5, abs=0.01)
    # work_content 단순 활동명 (pool 에 속함)
    assert a0["work_content"] in pools[("남웅건설", "철근콘크리트공사")]
    # mapper output 호환 필드
    assert a0["l6_main"] == "철근콘크리트공사"
    assert a0["unit"] == "m3"
    assert a0["worker_source"] == "mh_prorated"
    assert a0["mapping_source"] == "fake_daily_report"
    assert a0["plan_total_qty"] is None
    assert a0["plan_mh"] is None
    assert a0["wa"] == "CUB"
    assert 0.0 <= a0["mapping_conf"] <= 1.0
    assert a0["requires_review"] is False

    # 정상 케이스: conditions 에 "정상" 안 박힘 (맑음만)
    sb = [a for a in acts if a["company"] == "세보엠이씨"]
    assert len(sb) == 3
    a1 = sb[0]
    assert a1["conditions"] == ["맑음"]
    assert a1["assigned_workers"] == 50.0  # workers_ratio=1.0


# ---------------------------------------------------------------------------
# E2E — build_demo_graph + 실 LLM
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg_env():
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


@pytest.fixture
def chroma_ready(cfg_env):
    """남웅|철콘 synthetic_v2 row >= 20 보장 (Task 3 적재 결과)."""
    chroma = ChromaClient(
        host=os.environ["CHROMA_HOST"],
        port=int(os.environ.get("CHROMA_PORT", "8000")),
        ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )
    coll = chroma.get_or_create_daily_activities()
    res = coll.get(
        where={"$and": [{"company": "남웅건설"}, {"l6_main": "철근콘크리트공사"}]},
        include=["metadatas"],
    )
    metas = res.get("metadatas") or []
    assert len(metas) >= 20, f"daily_activities (남웅|철콘) {len(metas)} < 20. Task 3 적재 필요."


@pytest_asyncio.fixture
async def run_row(cfg_env):
    """pipeline_runs row 1건 + cascade cleanup."""
    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    run_id = uuid.uuid4()
    try:
        # sites DEMO_SITE 사전 보장 (CLI 와 동일 패턴)
        async with pg._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO sites (site_id, name) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                "DEMO_SITE",
                "Demo Site",
            )
        await pg.insert_pipeline_run(run_id, "DEMO_SITE", "2025-09-27")
        try:
            yield run_id
        finally:
            async with pg._pool.acquire() as conn:
                await conn.execute("DELETE FROM optimizer_advice WHERE run_id = $1", run_id)
                await conn.execute("DELETE FROM forecasts WHERE run_id = $1", run_id)
            await pg.delete_pipeline_run(run_id)
    finally:
        await pg.close()


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(600)
async def test_demo_graph_e2e_namwong_dolgwan(cfg_env, chroma_ready, run_row):
    """가짜 작업일보 (남웅 돌관) → build_demo_graph → __interrupt__ → resume → advice 1건.

    실 Forecaster LLM 1회 + 실 Optimizer LLM 1회 호출 (~$0.02~0.10).
    Spec §10 데모 시연 시나리오 정합 검증.
    """
    from pipeline.graph import build_demo_graph

    cfg = build_demo_graph_config()

    # baseline inputs 산출 — CLI 와 동일 경로 (PG activity_master 실 조회)
    pg = PGClient(cfg.optimizer.postgres_url)
    await pg.connect()
    try:
        from pipeline.agents.optimizer.synthetic_daily_report import _load_baseline_inputs

        scenarios = [
            {
                "company": "남웅건설",
                "l6_main": "철근콘크리트공사",
                "n_activities": 5,
                "incident": "돌관",
                "productivity_ratio": 0.45,
                "workers_ratio": 1.3,
                "unit": "m3",
            }
        ]
        pools, base_workers, base_qty = await _load_baseline_inputs(pg, scenarios, days=90)
    finally:
        await pg.close()

    mapped = generate_fake_daily_report(
        report_date="2025-09-27",
        scenarios=scenarios,
        activity_pools=pools,
        baseline_workers=base_workers,
        baseline_qty=base_qty,
    )
    assert len(mapped) == 5
    # 돌관 → workers_ratio 1.3, productivity_ratio 0.45 자연 risk_level=이상 trigger
    assert mapped[0]["assigned_workers"] > 0
    assert mapped[0]["today_qty"] > 0
    assert "돌관" in mapped[0]["conditions"]

    graph = build_demo_graph(cfg)
    thread_id = f"demo-test-{run_row}"
    graph_config = {"configurable": {"thread_id": thread_id}}
    state = _initial_state(run_row, "2025-09-27", mapped)

    # 1st ainvoke — Forecaster 실 LLM 1회 → hil_2 interrupt 예상
    first = await graph.ainvoke(state, config=graph_config)
    assert "__interrupt__" in first, (
        f"가짜 돌관 시나리오인데 __interrupt__ 미발생. forecast={first.get('forecast')}"
    )
    payload = first["__interrupt__"][0].value
    risky = payload.get("risky_groups", [])
    keys = [g["key"] for g in risky]
    target = "남웅건설|철근콘크리트공사"
    assert target in keys, f"risky_groups 에 {target} 없음: {keys}"

    # 2nd ainvoke — Command(resume=[target]) → Optimizer 실 LLM 1회
    final = await graph.ainvoke(Command(resume=[target]), config=graph_config)
    assert final.get("hil_2_selection") == [target]
    advice = final.get("optimizer_advice", [])
    assert len(advice) >= 1, "advice 0건 — Optimizer 미진입"
    row = advice[0]
    assert row["company"] == "남웅건설"
    assert row["l6_main"] == "철근콘크리트공사"
    assert isinstance(row.get("diagnosis"), str)
    assert len(row["diagnosis"]) > 0
    assert len(row.get("recommendations", [])) >= 1
    # 신 graph: optimizer → reporter → END (hil1-forecaster-reporter cycle)
    assert final.get("current_node") == "reporter"
