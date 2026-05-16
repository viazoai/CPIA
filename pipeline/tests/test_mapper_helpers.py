"""Unit test — mapper.py helper 함수들 (Task 6)."""

from __future__ import annotations

import pytest

from pipeline.state import Activity, ParsedDailyReport
from pipeline.agents.mapper import (
    build_embedding_input,
    build_llm_input,
    resolve_wa,
)


@pytest.fixture
def activity_namwung() -> Activity:
    """남웅건설 — 기초 거푸집 설치."""
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


@pytest.fixture
def parsed_report_minimal() -> ParsedDailyReport:
    """최소 parsed report."""
    return {
        "report_date": "20250925",
        "project": "M15X PH-3 IBL",
        "bp_summaries": [],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }


def test_build_embedding_input_simple(activity_namwung):
    """임베딩 input 은 작업line 자체만 — BP 컨텍스트·숫자 제외."""
    text = build_embedding_input(activity_namwung)
    assert "회사: 남웅건설" in text
    assert "작업: 기초 거푸집 설치" in text
    assert "단위: M2" in text
    assert "공종: 건축" in text
    assert "BP사 단위 컨텍스트" not in text
    assert "배관공" not in text


def test_build_llm_input_rich(activity_namwung, parsed_report_minimal):
    """LLM input 은 작업line + BP사 컨텍스트를 포함."""
    text = build_llm_input(activity_namwung, parsed_report_minimal)
    assert "회사: 남웅건설" in text
    assert "작업: 기초 거푸집 설치" in text
    assert "BP사 단위 컨텍스트" in text


def test_resolve_wa_bp_scope_single(activity_namwung):
    """1단계 — BP scope WA 단일."""
    cand_pool = [("FAB", "ACID배기설비공사"), ("FAB", "ALKALI배기설비공사")]
    result = resolve_wa(
        activity_namwung,
        l6_choice="ACID배기설비공사",
        cand_pool=cand_pool,
        parsed_report=None,
    )
    assert result.value == "FAB"
    assert result.source == "auto_bp_single"


def test_resolve_wa_l6_single(activity_namwung):
    """2단계 — L6 결정 후 그 L6 의 WA 단일."""
    cand_pool = [
        ("CUB", "CABLE TRAY공사"),
        ("FAB", "CABLE TRAY공사"),
        ("FAB", "전등설비공사"),
    ]
    result = resolve_wa(
        activity_namwung,
        l6_choice="전등설비공사",
        cand_pool=cand_pool,
        parsed_report=None,
    )
    assert result.value == "FAB"
    assert result.source == "auto_l6_single"


def test_resolve_wa_hil_required(activity_namwung):
    """4단계 — 같은 L6 가 양쪽 WA 모두 있음 → H-i-L."""
    cand_pool = [("CUB", "철근콘크리트공사"), ("FAB", "철근콘크리트공사")]
    result = resolve_wa(
        activity_namwung,
        l6_choice="철근콘크리트공사",
        cand_pool=cand_pool,
        parsed_report=None,
    )
    assert result.value is None
    assert result.source == "hil_required"
