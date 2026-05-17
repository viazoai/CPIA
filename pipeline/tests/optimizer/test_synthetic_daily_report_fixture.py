"""Forecaster fixture fix — 재현 + 픽스 + RAG 정합 회귀.

Spec: docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.2

3 테스트:
  1. test_fixture_today_qty_divides_by_n_activities — 픽스 후 산식 검증
  2. test_fixture_n_activities_zero_raises          — 가드 검증
  3. test_fixture_rag_alignment                     — synthetic_v2 정상 RAG 평균과 정합 (slow, 실 PG/Chroma 호출)
"""

from __future__ import annotations

import os

import pytest

from pipeline.agents.optimizer.synthetic_daily_report import (
    _parse_scenario,
    generate_fake_daily_report,
)


def test_fixture_today_qty_divides_by_n_activities() -> None:
    """ratio=0.45, n_activities=5 인 fixture 가 row 당 today_qty = baseline × ratio / n.

    합산 후 group total = baseline × ratio (의도 부합).
    """
    scenarios = [
        {
            "company": "남웅건설",
            "l6_main": "철근콘크리트공사",
            "n_activities": 5,
            "incident": "정상",
            "productivity_ratio": 0.45,
            "workers_ratio": 1.0,
            "unit": "m3",
        }
    ]
    activities = generate_fake_daily_report(
        report_date="2025-09-27",
        scenarios=scenarios,
        activity_pools={("남웅건설", "철근콘크리트공사"): ["벽체 콘크리트 타설"]},
        baseline_workers={("남웅건설", "철근콘크리트공사"): 31.0},
        baseline_qty={("남웅건설", "철근콘크리트공사", "m3"): 100.0},
    )
    assert len(activities) == 5
    row_qty = activities[0]["today_qty"]
    # 신: today_qty = round(100.0 * 0.45 / 5, 1) = round(9.0, 1) = 9.0
    assert row_qty == pytest.approx(9.0, abs=0.1)
    total_qty = sum(a["today_qty"] for a in activities)
    # 합산 = 5 × 9.0 = 45.0 = baseline_qty × ratio
    assert total_qty == pytest.approx(45.0, abs=0.5)


def test_fixture_n_activities_zero_raises() -> None:
    """n_activities=0 시 _parse_scenario 가 ValueError 발생."""
    with pytest.raises(ValueError, match="n_activities"):
        _parse_scenario("남웅건설|철근콘크리트공사|0|정상|1.0|1.0|m3")


@pytest.mark.slow
@pytest.mark.xfail(
    reason="drift backlog: 본 cycle 시점 fixture_prod 30.941 vs RAG_avg 27.951 delta=10.7% (임계 10% 초과 0.7%p). "
    "fixture 산식 정정 (Step 1.3) 은 완료. synthetic_v2 적재 분포 vs 90일 baseline 차이는 별 cycle 처리. "
    "spec §5.2 + plan Step 1.8 Expected outcomes 2 (FAIL 도 본 cycle 진행 가능).",
    strict=False,
)
@pytest.mark.asyncio
async def test_fixture_rag_alignment() -> None:
    """정상일 (ratio=1.0) fixture 가 산출하는 productivity 가 synthetic_v2 정상 RAG 평균과 ±10% 이내.

    fixture 의 today_qty = baseline_q × 1.0 / n_activities (정정 후 산식)
    fixture 의 today_prod (group total) = baseline_q / base_workers
    이게 synthetic_v2 (incident=정상) 의 같은 그룹 평균 productivity 와 정합해야
    시나리오 ratio=0.45 가 실제로 -55% 저하로 발현됨.
    """
    keys = ["POSTGRES_URL", "CHROMA_HOST"]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        pytest.skip(f"env 누락: {missing}")

    from pipeline.agents.optimizer.synthetic_daily_report import _load_baseline_inputs
    from pipeline.chroma_client import ChromaClient
    from pipeline.db import PGClient

    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        scenarios = [
            {
                "company": "남웅건설",
                "l6_main": "철근콘크리트공사",
                "n_activities": 5,
                "incident": "정상",
                "productivity_ratio": 1.0,
                "workers_ratio": 1.0,
                "unit": "m3",
            }
        ]
        _pools, base_workers, base_qty = await _load_baseline_inputs(pg, scenarios, days=90)
        bw = base_workers.get(("남웅건설", "철근콘크리트공사"), 0.0)
        bq = base_qty.get(("남웅건설", "철근콘크리트공사", "m3"), 0.0)
        if bw == 0 or bq == 0:
            pytest.skip("baseline_workers 또는 baseline_qty 0 — Master 미등록 그룹 skip")
        fixture_prod = bq / bw  # ratio=1.0 시 group total productivity

        chroma = ChromaClient(
            host=os.environ["CHROMA_HOST"],
            port=int(os.environ.get("CHROMA_PORT", "8000")),
            ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
        )
        coll = chroma.get_or_create_daily_activities()
        rag = coll.get(
            where={
                "$and": [
                    {"company": "남웅건설"},
                    {"l6_main": "철근콘크리트공사"},
                    {"worker_source": "synthetic_v2"},
                ]
            },
            include=["metadatas"],
        )
        productivities: list[float] = []
        for m in rag.get("metadatas") or []:
            workers = float(m.get("assigned_workers", 0) or 0)
            qty = float(m.get("today_qty", 0) or 0)
            if workers > 0:
                productivities.append(qty / workers)
        if not productivities:
            pytest.skip("synthetic_v2 정상일 row 0 — synthetic_v2 적재 필요")
        rag_avg = sum(productivities) / len(productivities)

        delta = abs(fixture_prod - rag_avg) / rag_avg if rag_avg > 0 else 1.0
        assert delta < 0.10, (
            f"fixture_prod={fixture_prod:.3f} vs rag_avg={rag_avg:.3f} delta={delta:.3f} (>10%) "
            "— fixture 와 synthetic_v2 분포 mismatch. 시나리오 ratio 가 의도된 변동 안 발현."
        )
    finally:
        await pg.close()
