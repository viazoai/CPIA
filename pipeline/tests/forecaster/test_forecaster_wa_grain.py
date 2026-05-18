"""Forecaster wa 차원 group_by 검증 — Phase 2 TDD.

동일 (company, l6_main) 이지만 wa 가 다른 activities 가 별개 forecast row 로
분리되는지 확인한다. 기존 (company, l6_main) 만으로 group 시 1 row 였을 케이스.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline.agents.forecaster.agent import ForecasterConfig, forecast


def _make_cfg() -> ForecasterConfig:
    """단위 테스트용 ForecasterConfig — 실 endpoint/key 불필요."""
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


def _activity(wa: str | None, company: str, l6_main: str) -> dict[str, Any]:
    """Activity fixture — wa 만 가변, 나머지 고정."""
    return {
        "wbs_activity_id": None,
        "l5_disc": "건축",
        "l6_main": l6_main,
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "trade": "건축",
        "company": company,
        "unit": "m3",
        "today_qty": 10.0,
        "work_content": "콘크리트 타설",
        "conditions": ["맑음"],
        "assigned_workers": 5.0,
        "worker_source": "mh_prorated",
        "plan_total_qty": None,
        "plan_mh": None,
        "wa": wa,
        "mapping_conf": 0.85,
        "mapping_source": "auto_bp_single",
        "requires_review": False,
    }


@pytest.mark.asyncio
async def test_forecast_splits_rows_by_wa():
    """wa 가 다른 activities 는 별개 forecast row 로 분리된다.

    fixture: 동일 company="A사", l6_main="철근콘크리트공사"
    - wa="FAB" 2건
    - wa="CUB" 2건
    기대: forecast rows 2건 (FAB / CUB 각 1건)
    """
    company = "A사"
    l6_main = "철근콘크리트공사"
    run_id = uuid.uuid4()

    mapped = [
        _activity(wa="FAB", company=company, l6_main=l6_main),
        _activity(wa="FAB", company=company, l6_main=l6_main),
        _activity(wa="CUB", company=company, l6_main=l6_main),
        _activity(wa="CUB", company=company, l6_main=l6_main),
    ]

    # PGClient mock
    pg_mock = MagicMock()
    pg_mock.connect = AsyncMock()
    pg_mock.close = AsyncMock()
    pg_mock.assert_pipeline_run_exists = AsyncMock()
    pg_mock.fetch_plan_for_group = AsyncMock(return_value=None)
    pg_mock.insert_forecast = AsyncMock()

    # Chroma collection mock — RAG 0건 (cold-start)
    coll_mock = MagicMock()
    coll_mock.query = MagicMock(
        return_value={"ids": [[]], "documents": [[]], "distances": [[]], "metadatas": [[]]}
    )
    coll_mock.get = MagicMock(return_value={"metadatas": []})

    chroma_client_mock = MagicMock()
    chroma_client_mock.get_or_create_daily_activities = MagicMock(return_value=coll_mock)

    # Azure embedding mock
    embed_resp = MagicMock()
    embed_resp.data = [MagicMock(embedding=[0.0] * 1536)]
    azure_mock = MagicMock()
    azure_mock.embeddings.create = MagicMock(return_value=embed_resp)

    with (
        patch("pipeline.agents.forecaster.agent.PGClient", return_value=pg_mock),
        patch("pipeline.agents.forecaster.agent.ChromaClient", return_value=chroma_client_mock),
        patch("pipeline.agents.forecaster.agent.AzureOpenAI", return_value=azure_mock),
    ):
        rows = await forecast(
            mapped=mapped,
            run_id=run_id,
            today=date(2025, 9, 25),
            cfg=_make_cfg(),
        )

    assert len(rows) == 2, (
        f"wa 가 다른 group 은 2 row 여야 함. 실제: {len(rows)} row\nwa 값: {[r.get('wa') for r in rows]}"
    )

    wa_values = {r.get("wa") for r in rows}
    assert wa_values == {"FAB", "CUB"}, f"row 의 wa 값이 FAB / CUB 여야 함. 실제: {wa_values}"
