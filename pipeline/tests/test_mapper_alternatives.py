"""G23 — mapper INSERT 가 alternatives jsonb 컬럼 (RAG top-K 후보) 을 적재.

FE review 페이지의 "대안 WP 후보 dropdown" 데이터 소스. 컬럼 자체는
2026-05-19 migration `add_mapper_alternatives.sql` 로 추가 (jsonb DEFAULT '[]').
"""

from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

from pipeline.agents.mapper import _attach_candidate_confs, _select_top_k_alternatives


def test_select_top_k_alternatives_dedup_distinct_l6():
    """l6 별 dedup — 같은 l6 의 wbs_master 항목이 여러 개여도 distinct l6 top-K(최고 score)."""
    cands = [
        {"key": ("FAB", "C/R 조성공사"), "score": 0.62},
        {"key": ("FAB", "C/R 조성공사"), "score": 0.60},  # dup l6 (낮은 score → 버려짐)
        {"key": ("CUB", "외장판넬공사"), "score": 0.58},
        {"key": ("FAB", "철골공사"), "score": 0.55},
    ]
    out = _select_top_k_alternatives(cands, k=5)
    assert [o["l6_main"] for o in out] == ["C/R 조성공사", "외장판넬공사", "철골공사"]  # distinct, score desc
    assert out[0]["score"] == 0.62  # dup 중 최고 score 만 남음


def test_select_top_k_alternatives_carries_conf():
    """review 카드용 — 각 후보에 부착된 LLM 신뢰도(c["conf"])를 출력에 함께 적재."""
    cands = [
        {"key": ("FAB", "C/R 조성공사"), "score": 0.62, "conf": 0.71},
        {"key": ("CUB", "외장판넬공사"), "score": 0.58, "conf": 0.40},
        {"key": ("FAB", "철골공사"), "score": 0.55},  # conf 누락 → 0.0 기본
    ]
    out = _select_top_k_alternatives(cands, k=5)
    by_l6 = {o["l6_main"]: o for o in out}
    assert by_l6["C/R 조성공사"]["conf"] == 0.71
    assert by_l6["외장판넬공사"]["conf"] == 0.40
    assert by_l6["철골공사"]["conf"] == 0.0


def test_attach_candidate_confs_forces_chosen_and_defaults():
    """LLM candidate_confidences 를 각 후보에 부착 + 선택 후보는 게이트 conf 로 고정, 누락은 0.0."""
    cands = [
        {"key": ("A", "l6a"), "score": 0.5},
        {"key": ("B", "l6b"), "score": 0.4},
        {"key": ("C", "l6c"), "score": 0.3},
    ]
    out = _attach_candidate_confs(cands, [0.20, 0.80, None], chosen_idx=0, chosen_conf=0.32)
    assert out[0]["conf"] == 0.32  # 선택 후보 → 게이트 mapping_conf 로 고정 (LLM 자가보고 0.20 무시)
    assert out[1]["conf"] == 0.80  # 비선택 후보 → LLM 신뢰도 그대로
    assert out[2]["conf"] == 0.0  # None → 0.0


def test_attach_candidate_confs_handles_missing_or_malformed():
    """candidate_confidences 가 None/짧음/비숫자여도 방어 (0.0), 선택 후보만 고정."""
    cands = [{"key": ("A", "l6a"), "score": 0.5}, {"key": ("B", "l6b"), "score": 0.4}]
    out = _attach_candidate_confs(cands, None, chosen_idx=1, chosen_conf=0.9)  # 리스트 아님
    assert out[0]["conf"] == 0.0
    assert out[1]["conf"] == 0.9  # 선택 후보 고정
    out2 = _attach_candidate_confs(
        [{"key": ("A", "l6a"), "score": 0.5}], ["bad"], chosen_idx=-1, chosen_conf=0.5
    )
    assert out2[0]["conf"] == 0.0  # 비숫자 → 0.0, chosen_idx 범위밖이면 고정 안 함


async def _seed_pipeline_run(pg_client, run_id) -> None:
    async with pg_client._pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO pipeline_runs (run_id, site_id, report_date, status, started_at)
            VALUES ($1, $2, $3, $4, now())
            """,
            run_id,
            "test-g23",
            date(2025, 9, 25),
            "running",
        )


async def test_insert_mapper_persists_alternatives_jsonb(pg_client, cleanup_test_rows):
    """G23 — insert_mapper_activities_batch 가 alternatives jsonb 컬럼에 top-K 후보 적재."""
    run_id = uuid4()
    cleanup_test_rows.append(run_id)
    await _seed_pipeline_run(pg_client, run_id)

    alts = [
        {"wa": "CUB", "l6_main": "철근콘크리트공사", "score": 0.85},
        {"wa": "CUB", "l6_main": "거푸집공사", "score": 0.62},
        {"wa": "FAB", "l6_main": "철근콘크리트공사", "score": 0.41},
    ]
    activities = [
        {
            "company": "남웅건설",
            "trade": "건축",
            "unit": "m2",
            "today_qty": 100.0,
            "wa": "CUB",
            "l6_main": "철근콘크리트공사",
            "mapping_conf": 0.85,
            "mapping_source": "auto_sheet1_text",
            "requires_review": False,
            "assigned_workers": 8.0,
            "worker_source": "mh_prorated",
            "plan_total_qty": 1500.0,
            "plan_mh": 456.0,
            "conditions": [],
            "alternatives": alts,
        }
    ]
    await pg_client.insert_mapper_activities_batch(
        run_id=run_id,
        report_date=date(2025, 9, 25),
        activities=activities,
    )

    async with pg_client._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT alternatives FROM mapper_activities WHERE run_id=$1 ORDER BY idx LIMIT 1",
            run_id,
        )
    assert row is not None
    saved = row["alternatives"]
    # asyncpg jsonb 는 driver 설정에 따라 dict/list 또는 str 으로 받음.
    if isinstance(saved, str):
        saved = json.loads(saved)

    assert isinstance(saved, list)
    assert len(saved) == 3
    assert saved[0]["wa"] == "CUB"
    assert saved[0]["l6_main"] == "철근콘크리트공사"
    assert float(saved[0]["score"]) == 0.85
    # score 내림차순 보존
    assert float(saved[0]["score"]) >= float(saved[1]["score"]) >= float(saved[2]["score"])
