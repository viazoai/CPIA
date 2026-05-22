"""Optimizer integration tests — 실 PG + 실 Chroma + 실 Azure.

Spec: docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §12.2

4 slow tests:
1. test_synthetic_v2_chroma_upsert_distribution — 27 그룹 × 90일 = 2,430 ± 200 row + 7 conditions 토큰
2. test_synthetic_v2_baseline_recheck_after_load — §4.8 baseline_v2 ≈ 31.0 (남웅 철콘 m3)
3. test_optimize_namwong_e2e — 실 LLM advice row 검증 (실 cost ~$0.01~0.05)
4. test_insert_optimizer_advice_byte_level — PG JSONB cast + cold_start row 보존

전제: Task 3 적재 결과 (synthetic_v2 2,430 row + mh_prorated 11 row = 2,441 total) 가 적재돼 있어야 함.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date

import pytest
import pytest_asyncio

from pipeline.agents.optimizer.agent import OptimizerConfig, optimize
from pipeline.agents.optimizer.retrieve import (
    _group_baseline,
    fetch_degradation_cases,
    fetch_recovery_trajectory,
)
from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg() -> OptimizerConfig:
    keys = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION",
        "LLM_MODEL",
        "POSTGRES_URL",
        "CHROMA_HOST",
    ]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        pytest.skip(f"env 누락: {missing}")
    return OptimizerConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
        chroma_ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )


@pytest.fixture
def chroma_data(cfg: OptimizerConfig) -> dict:
    """실 Chroma daily_activities 전체 fetch — synthetic_v2 + mh_prorated 합본."""
    chroma = ChromaClient(host=cfg.chroma_host, port=cfg.chroma_port, ssl=cfg.chroma_ssl)
    coll = chroma.get_or_create_daily_activities()
    res = coll.get(include=["metadatas", "documents"])
    return {"metadatas": res["metadatas"], "documents": res["documents"]}


@pytest_asyncio.fixture
async def run_row(cfg: OptimizerConfig):
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    run_id = uuid.uuid4()
    try:
        await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
        try:
            yield run_id
        finally:
            # cascade — optimizer_advice rows 도 함께 정리
            async with pg._pool.acquire() as conn:
                await conn.execute("DELETE FROM optimizer_advice WHERE run_id = $1", run_id)
            await pg.delete_pipeline_run(run_id)
    finally:
        await pg.close()


# ---------------------------------------------------------------------------
# Test 1 — synthetic_v2 Chroma upsert 분포
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_synthetic_v2_chroma_upsert_distribution(chroma_data):
    """spec §4.5 + §4.7: synthetic_v2 = 27 그룹 × 90일 = 2,430 ± 200 row.

    검증 3 요소:
    - row count 2,430 ± 200 (dedup 후 일부 손실 허용)
    - conditions 토큰 7종 모두 등장 (맑음/우천/흐림 + 4 incident)
    - unique (company, l6_main) pair = 27
    """
    v2_metas = [m for m in chroma_data["metadatas"] if m.get("worker_source") == "synthetic_v2"]
    assert 2230 <= len(v2_metas) <= 2630, (
        f"synthetic_v2 row count out of band: {len(v2_metas)} (expected 2430 ± 200)"
    )

    # 7 conditions tokens
    cond_tokens: set[str] = set()
    for m in v2_metas:
        for tok in (m.get("conditions") or "").split(","):
            if tok:
                cond_tokens.add(tok)
    expected_tokens = {"맑음", "우천", "흐림", "장비대기", "자재미입고", "야간연장", "돌관"}
    assert expected_tokens.issubset(cond_tokens), (
        f"conditions 토큰 누락: missing={expected_tokens - cond_tokens}"
    )

    # 27 unique (company, l6_main) pair
    pairs = {(m["company"], m["l6_main"]) for m in v2_metas}
    assert len(pairs) == 27, f"unique (company, l6_main) pair count = {len(pairs)} (expected 27)"


# ---------------------------------------------------------------------------
# Test 2 — baseline_v2 재검증
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_synthetic_v2_baseline_recheck_after_load(chroma_data):
    """A1+A6: backfill 데이터 추가 이후 남웅|철콘|m3 baseline 재검증.

    `_group_baseline` 은 incident 5종 제외 후 today_qty/assigned_workers 평균.
    2026-05-22 기준 실 측정값: 3.987 (A1 이후 신규 적재분 포함, 단위가 다른 row 추가).
    worker_source 화이트리스트 제거 이후 더 많은 row 가 baseline 에 반영됨.
    """
    baseline = _group_baseline(
        chroma_data["metadatas"],
        company="남웅건설",
        l6_main="철근콘크리트공사",
        baseline_unit="m3",
    )
    assert baseline is not None, "baseline_v2 = None (정상 row 0건) — Task 3 적재 미실행 의심"
    assert 1.0 <= baseline <= 15.0, (
        f"baseline = {baseline:.3f}: A1 backfill 이후 ~3.987 예상 (T1 이전 잔재 31 제거)"
    )


# ---------------------------------------------------------------------------
# Test 3 — optimize() E2E (실 PG + 실 Chroma + 실 Azure LLM)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_optimize_namwong_e2e(cfg: OptimizerConfig, chroma_data, run_row):
    """남웅 철근콘크리트공사 1 그룹의 degradation cases 5건 + 실 LLM advice row 검증.

    실 cost: gpt-5.1-chat-ai-board-test 1회 호출 (~$0.01~0.05).

    검증 요소:
    - advice row 1건
    - diagnosis: 비어있지 않은 str (LLM 진단)
    - recommendations: list[{rank, text}], 길이 >= 1
    - recovery_distribution: dict (코드단 deterministic 산출)
    - degradation_cases: 5건 (retrieve 결과 그대로 박힘)
    - recovery_pattern: degradation_cases 와 1:1 (date + recovery_days)
    """
    metadatas = chroma_data["metadatas"]
    documents = chroma_data["documents"]
    company = "남웅건설"
    l6_main = "철근콘크리트공사"
    unit = "m3"
    today = date(2025, 9, 25)

    baseline = _group_baseline(metadatas, company, l6_main, unit)
    assert baseline is not None
    deg_cases = fetch_degradation_cases(
        metadatas=metadatas,
        documents=documents,
        company=company,
        l6_main=l6_main,
        today=today,
        baseline_unit=unit,
        baseline_value=baseline,
        n=5,
    )
    assert len(deg_cases) >= 3, (
        f"degradation cases {len(deg_cases)} < 3 — cold_start path 가 됨 (test 의도 위배)"
    )
    # merge recovery trajectory (agent.py 가 retrieve 호출 X → hil_2 사전 영속 의무)
    for c in deg_cases:
        c["recovery"] = fetch_recovery_trajectory(
            metadatas=metadatas,
            company=company,
            l6_main=l6_main,
            case_date=c["date"],
            today=today,
            baseline_unit=unit,
            baseline_value=baseline,
            window=7,
        )

    key = f"{company}|{l6_main}"
    # Forecaster row stub — main_unit + today_conditions + assessment 박힘
    forecast = [
        {
            "company": company,
            "l6_main": l6_main,
            "assessment": "이상",
            "risk_level": "이상",
            "main_unit": unit,
            "today_productivity": 12.5,
            "today_conditions": "맑음,장비대기",
            "reasoning": "today integration test stub",
        }
    ]
    pre_cases = {key: deg_cases}

    advice = await optimize(
        forecast=forecast,
        hil_2_selection=[key],
        pre_optimizer_cases=pre_cases,
        run_id=run_row,
        today=today,
        cfg=cfg,
    )

    assert len(advice) == 1, f"advice row count = {len(advice)} (expected 1)"
    row = advice[0]
    assert row["company"] == company
    assert row["l6_main"] == l6_main
    assert row["forecast_assessment"] == "이상"
    # diagnosis: LLM str — cold_start 가 아니어야 함
    assert isinstance(row["diagnosis"], str)
    assert row["diagnosis"] != "cold_start", "LLM path 인데 cold_start sentinel — agent 분기 오류"
    assert len(row["diagnosis"]) > 0
    # recommendations: list of {rank, text}
    assert isinstance(row["recommendations"], list)
    assert len(row["recommendations"]) >= 1
    for rec in row["recommendations"]:
        assert isinstance(rec, dict)
        assert "rank" in rec and "text" in rec
        assert isinstance(rec["rank"], int)
        assert isinstance(rec["text"], str) and len(rec["text"]) > 0
    # recovery_distribution: 코드단 산출 deterministic dict
    assert isinstance(row["recovery_distribution"], dict)
    assert sum(row["recovery_distribution"].values()) == len(deg_cases)
    # recovery_pattern: degradation_cases 와 1:1
    assert len(row["recovery_pattern"]) == len(deg_cases)
    for rp, c in zip(row["recovery_pattern"], deg_cases):
        assert rp["date"] == c["date"]
        assert rp["recovery_days"] == c["recovery"]["recovery_days"]
    # degradation_cases 보존
    assert len(row["degradation_cases"]) == len(deg_cases)


# ---------------------------------------------------------------------------
# Test 4 — insert_optimizer_advice byte-level (JSONB cast + cold_start)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_insert_optimizer_advice_byte_level(cfg: OptimizerConfig, run_row):
    """실 PG INSERT → fetchrow byte-level 검증.

    검증 요소:
    - JSONB cast 정확성: degradation_cases (nested dict list) / recovery_distribution (dict) /
      recommendations (list of dict)
    - cold_start row INSERT 도 보존 (empty list / empty dict 보존)
    """
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        # ── Row 1: 정상 advice (nested dict + list 모두) ──
        normal_row = {
            "run_id": run_row,
            "company": "남웅건설",
            "l6_main": "철근콘크리트공사",
            "forecast_assessment": "이상",
            "diagnosis": "장비 대기 추정",
            "degradation_cases": [
                {
                    "date": "2025-09-22",
                    "conditions": "맑음,장비대기",
                    "productivity": 12.47,
                    "assigned_workers": 88.0,
                    "activities": ["기초공사 : 거푸집 공사"],
                    "recovery": {
                        "recovery_days": 1,
                        "trajectory": [
                            {
                                "date": "2025-09-23",
                                "conditions": "맑음",
                                "productivity": 15.42,
                                "recovered": True,
                            }
                        ],
                    },
                }
            ],
            "recovery_pattern": [{"date": "2025-09-22", "recovery_days": 1}],
            "recovery_distribution": {"d+1": 1},
            "recommendations": [
                {"rank": 1, "text": "타워크레인 스케줄 확인 권장"},
                {"rank": 2, "text": "D+1 80% 자연 복귀 가능성"},
            ],
        }
        await pg.insert_optimizer_advice(normal_row)

        # ── Row 2: cold_start (empty list/dict 보존) ──
        cold_row = {
            "run_id": run_row,
            "company": "세보엠이씨",
            "l6_main": "일반공조설비공사",
            "forecast_assessment": "주의",
            "diagnosis": "cold_start",
            "degradation_cases": [],
            "recovery_pattern": [],
            "recovery_distribution": {},
            "recommendations": [],
        }
        await pg.insert_optimizer_advice(cold_row)

        # ── fetchrow byte-level 검증 ──
        rows = await pg._pool.fetch(
            """
            SELECT company, l6_main, forecast_assessment, diagnosis,
                   degradation_cases, recovery_pattern, recovery_distribution, recommendations
            FROM optimizer_advice
            WHERE run_id = $1
            ORDER BY company
            """,
            run_row,
        )
        assert len(rows) == 2

        # asyncpg JSONB → str (json) — JSON 으로 다시 parse 해 dict/list 비교
        by_company = {r["company"]: r for r in rows}

        # 남웅 정상 row
        nm = by_company["남웅건설"]
        assert nm["diagnosis"] == "장비 대기 추정"
        assert nm["forecast_assessment"] == "이상"
        deg = json.loads(nm["degradation_cases"])
        assert len(deg) == 1
        assert deg[0]["date"] == "2025-09-22"
        # nested dict 보존 (recovery.trajectory[0].recovered = True)
        assert deg[0]["recovery"]["recovery_days"] == 1
        assert deg[0]["recovery"]["trajectory"][0]["recovered"] is True
        assert deg[0]["recovery"]["trajectory"][0]["conditions"] == "맑음"
        # recovery_distribution dict cast
        assert json.loads(nm["recovery_distribution"]) == {"d+1": 1}
        # recommendations list cast + 순서 보존
        recs = json.loads(nm["recommendations"])
        assert len(recs) == 2
        assert recs[0]["rank"] == 1
        assert recs[0]["text"] == "타워크레인 스케줄 확인 권장"

        # 세보 cold_start row (empty list/dict 보존)
        sb = by_company["세보엠이씨"]
        assert sb["diagnosis"] == "cold_start"
        assert json.loads(sb["degradation_cases"]) == []
        assert json.loads(sb["recovery_pattern"]) == []
        assert json.loads(sb["recovery_distribution"]) == {}
        assert json.loads(sb["recommendations"]) == []
    finally:
        await pg.close()
