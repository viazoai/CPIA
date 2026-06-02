"""mapper.map_activity — 전건 HIL (C5-1). high-conf 성공 분기에서도 requires_review=True.

Azure/Chroma/PG 를 모두 패치해 LLM 호출 없이 line 515 분기를 결정론적으로 구동.
Spec 2026-06-02-cpia-0925-demo-refinement-design.md §5.1 #1.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from pipeline.agents.mapper import MapperConfig, map_activity
from pipeline.state import Activity


def _cfg() -> MapperConfig:
    return MapperConfig(
        azure_endpoint="https://x",
        azure_api_key="k",
        azure_api_version="2024-12-01-preview",
        llm_model="m",
        embedding_model="e",
        postgres_url="postgresql://t:t@localhost:5432/t",
        chroma_host="localhost",
        chroma_port=8000,
    )


def _activity() -> Activity:
    return {
        "wbs_activity_id": None,
        "l5_disc": "건축",
        "l6_main": None,
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "trade": "건축",
        "company": "남웅건설",
        "unit": "M2",
        "today_qty": 320.0,
        "work_content": "기초 거푸집 설치",
        "conditions": [],
        "assigned_workers": 81.0,
        "worker_source": "parsed",
        "plan_total_qty": None,
        "plan_mh": None,
        "requires_review": False,
        "wa": None,
        "mapping_conf": None,
        "mapping_source": None,
    }


def _fake_azure() -> MagicMock:
    """confidence=0.99 (conf_threshold=0.7 초과) → 원래라면 requires_review=False 분기."""
    client = MagicMock()
    client.embeddings.create.return_value = SimpleNamespace(data=[SimpleNamespace(embedding=[0.0] * 1536)])
    msg = SimpleNamespace(content=json.dumps({"choice": 0, "confidence": 0.99, "reason": "ok"}))
    client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=msg)])
    return client


def _fake_coll() -> MagicMock:
    coll = MagicMock()
    coll.query.return_value = {
        "ids": [["d0"]],
        "metadatas": [[{"wa": "CUB", "l6_main": "철근콘크리트공사"}]],
        "documents": [["CUB / 철근콘크리트공사"]],
        "distances": [[0.01]],
    }
    return coll


def test_map_activity_high_conf_still_requires_review() -> None:
    cfg = _cfg()
    fake_pg = MagicMock()
    fake_pg.connect = AsyncMock()
    fake_pg.close = AsyncMock()
    fake_pg.fetch_bp_candidates = AsyncMock(return_value=[{"wa": "CUB", "l6_main": "철근콘크리트공사"}])

    with (
        patch("pipeline.agents.mapper.AzureOpenAI", return_value=_fake_azure()),
        patch("pipeline.agents.mapper._get_wbs_master_coll", new=AsyncMock(return_value=_fake_coll())),
        patch("pipeline.agents.mapper.PGClient", return_value=fake_pg),
    ):
        result = asyncio.run(map_activity(_activity(), parsed_report=None, cfg=cfg))

    assert result["requires_review"] is True
    assert result["mapping_conf"] == 0.99
    assert result["l6_main"] == "철근콘크리트공사"
