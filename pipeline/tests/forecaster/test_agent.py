"""Forecaster agent.py 단위 테스트 — `_forecast_one_group()` row 구조.

Spec: docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §2.1 + §2.2 + §11.1
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pipeline.agents.forecaster.agent import ForecasterConfig, _forecast_one_group


def _make_cfg() -> ForecasterConfig:
    """단위 테스트용 ForecasterConfig — 실 endpoint/key 불필요 (mock 으로 주입)."""
    return ForecasterConfig(
        azure_endpoint="https://stub",
        azure_api_key="stub",
        azure_api_version="2024-12-01-preview",
        llm_model="stub-llm",
        embedding_model="stub-embed",
        postgres_url="postgresql://stub",
        chroma_host="stub",
        chroma_port=0,
        rag_n_candidates=10,
        rag_top_k=5,
        rag_window_days=30,
    )


def _activity(unit: str, qty: float, conditions: list[str]) -> dict[str, Any]:
    """단일 Activity dict — Activity TypedDict 의 필수 필드만."""
    return {
        "wbs_activity_id": None,
        "l5_disc": "건축",
        "l6_main": "철근콘크리트공사",
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "trade": "건축",
        "company": "남웅건설",
        "unit": unit,
        "today_qty": qty,
        "work_content": "기초공사 거푸집",
        "conditions": conditions,
        "assigned_workers": 88.0,
        "worker_source": "mh_prorated",
        "plan_total_qty": None,
        "plan_mh": None,
        "wa": "CUB",
        "mapping_conf": 0.85,
        "mapping_source": "auto_bp_single",
        "requires_review": False,
    }


@pytest.mark.asyncio
async def test_forecast_row_has_main_unit_and_today_conditions():
    """spec §2.2 (v3.1) — Forecaster row 가 main_unit + today_conditions 2 필드 추가.

    today_productivity 는 Phase 1 시점 이미 박힘 (agent.py:196). v3.1 정정 핵심.
    """
    activities = [
        _activity(unit="m3", qty=80.0, conditions=["맑음"]),
        _activity(unit="m2", qty=20.0, conditions=["흐림"]),
    ]

    pg = MagicMock()
    pg.fetch_plan_for_group = AsyncMock(return_value=None)  # cold-start path (Plan 없음)
    pg.fetch_all = AsyncMock(return_value=[])  # A8 fetch_pg_actual_cum_qty — empty PG history

    # Chroma collection mock — RAG 0건 (cold-start 유사 케이스 없음)
    coll = MagicMock()
    coll.query = MagicMock(
        return_value={"ids": [[]], "documents": [[]], "distances": [[]], "metadatas": [[]]}
    )
    coll.get = MagicMock(return_value={"metadatas": []})

    # Azure embedding mock — 1536 dim dummy (값은 의미 X)
    embed_resp = MagicMock()
    embed_resp.data = [MagicMock(embedding=[0.0] * 1536)]
    azure = MagicMock()
    azure.embeddings.create = MagicMock(return_value=embed_resp)
    # LLM 은 cold-start path 라 호출 X — chat.completions.create 미설정 OK

    row = await _forecast_one_group(
        company="남웅건설",
        l6_main="철근콘크리트공사",
        activities=activities,
        run_id=uuid.uuid4(),
        today=date(2025, 9, 25),
        pg=pg,
        coll=coll,
        azure=azure,
        cfg=_make_cfg(),
    )

    assert "main_unit" in row, "v3.1: main_unit 신규 필드"
    assert "today_conditions" in row, "v3.1: today_conditions 신규 필드"
    # today_productivity 는 Phase 1 시점 이미 박힘 — 기존 검증
    assert "today_productivity" in row

    # 의미 검증: main_unit 은 max qty unit = "m3"
    assert row["main_unit"] == "m3"
    # today_conditions 는 set 합집합 정렬 join — "맑음", "흐림" sorted
    assert row["today_conditions"] == "맑음,흐림"
