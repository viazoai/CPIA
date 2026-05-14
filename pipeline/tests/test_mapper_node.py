"""map_activity 통합 테스트 (Task 7) — 실 Azure 호출.

Spec: docs/schema/mapping-layer.md §3 (6단계 흐름).
"""

from __future__ import annotations

import os

import pytest

from pipeline.state import Activity
from pipeline.agents.mapper import map_activity, MapperConfig


@pytest.fixture
def cfg(azure_openai_env) -> MapperConfig:
    return MapperConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
        embedding_model=os.environ["EMBEDDING_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
    )


@pytest.mark.asyncio
async def test_map_activity_namwung(cfg):
    """남웅건설 '기초 거푸집 설치' → 철근콘크리트공사 + WA H-i-L (양쪽 가능)."""
    activity: Activity = {
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
    result = await map_activity(activity, parsed_report=None, cfg=cfg)
    assert result["l6_main"] == "철근콘크리트공사"
    # 남웅은 WA 양쪽 가능 → H-i-L
    assert result["wa"] is None
    assert result["mapping_source"] == "hil_required"
    assert result["requires_review"] is True


@pytest.mark.asyncio
async def test_map_activity_sebo(cfg):
    """세보엠이씨 'ACID 배기덕트 설치' → ACID배기설비공사 + FAB (BP scope 단일)."""
    activity: Activity = {
        "wbs_activity_id": None,
        "l5_disc": "설비",
        "l6_main": None,
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "trade": "설비",
        "company": "세보엠이씨",
        "unit": "M2",
        "today_qty": 0.0,
        "work_content": "ACID 배기덕트 설치",
        "conditions": [],
        "assigned_workers": 0.0,
        "worker_source": "parsed",
        "plan_total_qty": 4214.2,
        "plan_mh": None,
        "requires_review": False,
        "wa": None,
        "mapping_conf": None,
        "mapping_source": None,
    }
    result = await map_activity(activity, parsed_report=None, cfg=cfg)
    assert result["l6_main"] == "ACID배기설비공사"
    assert result["wa"] == "FAB"
    assert result["mapping_source"] == "auto_bp_single"
