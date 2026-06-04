from __future__ import annotations
import pytest
import uuid
import datetime
from pipeline.db import PGClient
import os

PG = os.environ["POSTGRES_URL"]


@pytest.mark.asyncio
async def test_pick_l75_specific(monkeypatch):
    from pipeline.agents import mapper as M

    cands = ["기초공사 : 거푸집 공사", "기초공사 : 철근 콘크리트 타설", "RC Wall & Column 공사 : 거푸집 공사"]
    monkeypatch.setattr(M, "_call_l75_llm", lambda *a, **k: {"choice": 0, "confidence": 0.99, "reason": "x"})
    out = await M.pick_l75("기초 거푸집 설치", "철근콘크리트공사", "광건", "m2", cands, cfg=None)
    assert out["l7_5_activity"] == "기초공사 : 거푸집 공사"
    assert out["l75_conf"] == 0.99
    assert out["l7_5_alternatives"][0]["label"] in cands


@pytest.mark.asyncio
async def test_pick_l75_forced_best_guess(monkeypatch):
    # D5: LLM 이 -1(애매) 을 반환해도 후보가 있으면 best-guess(candidates[0]) 강제 배정.
    # 미분류(None)는 후보 0개일 때만. 낮은 conf 는 보존 → 게이트가 HIL 로 보냄.
    from pipeline.agents import mapper as M

    monkeypatch.setattr(
        M, "_call_l75_llm", lambda *a, **k: {"choice": -1, "confidence": 0.2, "reason": "no fit"}
    )
    out = await M.pick_l75(
        "비계 설치", "외장판넬공사", "남웅", "m2", ["Glass Wool Panel 설치", "Wind Column 설치"], cfg=None
    )
    assert out["l7_5_activity"] == "Glass Wool Panel 설치"  # best-guess 폴백 (미분류 아님)
    assert out["l75_conf"] == 0.2  # 낮은 conf 보존
    assert len(out["l7_5_alternatives"]) >= 1


@pytest.mark.asyncio
async def test_pick_l75_empty_candidates_unclassified():
    # 후보 0개 = 진짜 미분류 (l6 밑 master l7.5 없음) — 유일한 None 케이스.
    from pipeline.agents import mapper as M

    out = await M.pick_l75("X 작업", "후보없는공종", "C", "m2", [], cfg=None)
    assert out["l7_5_activity"] is None
    assert out["l7_5_alternatives"] == []


@pytest.mark.asyncio
async def test_l75_columns_roundtrip():
    pg = PGClient(PG)
    await pg.connect()
    run_id = uuid.uuid4()
    try:
        await pg.insert_pipeline_run(run_id, "m15x-ph3-ibl", "2025-09-25", "running")
        act = {
            "company": "T",
            "trade": "건축",
            "unit": "m2",
            "today_qty": 1.0,
            "wa": "FAB",
            "l6_main": "수장공사",
            "l7_5_activity": "경량벽체 설치",
            "l75_conf": 0.92,
            "l7_5_alternatives": [{"label": "경량벽체 설치", "score": 0.92}],
            "requires_review": False,
        }
        await pg.insert_mapper_activities_batch(run_id, datetime.date(2025, 9, 25), [act])
        rows = await pg.fetch_all(
            "SELECT l75_conf, l7_5_alternatives FROM mapper_activities WHERE run_id=$1",
            run_id,
        )
        assert rows, "row not inserted"
        assert float(rows[0]["l75_conf"]) == 0.92
        import json as _j

        alts = rows[0]["l7_5_alternatives"]
        alts = _j.loads(alts) if isinstance(alts, str) else alts
        assert alts[0]["label"] == "경량벽체 설치"
    finally:
        await pg.fetch_all("DELETE FROM mapper_activities WHERE run_id=$1", run_id)
        await pg.delete_pipeline_run(run_id)
        await pg.close()
