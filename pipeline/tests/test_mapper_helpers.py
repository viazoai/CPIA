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


def test_resolve_wa_chroma_top1_fallback_when_pool_empty(activity_namwung):
    """Task 4 — cand_pool 빈 시 (BP master 미등록) → Chroma 선택 결과 그대로.

    사용자 명시: "work_area와 l6에 주로 매칭하고 bp는 추가로 도와주는 메타데이터.
    필터링으로 안됐으면 스킵이 된다 이러면 절대 안돼."
    """
    result = resolve_wa(
        activity_namwung,
        l6_choice="철근콘크리트공사",
        cand_pool=[],
        parsed_report=None,
        chosen_wa="FAB",
    )
    assert result.value == "FAB"
    assert result.source == "auto_chroma_top1"


def test_resolve_wa_chroma_top1_with_cub(activity_namwung):
    """Task 4 — fallback 에서 chosen_wa='CUB' 도 그대로 채택."""
    result = resolve_wa(
        activity_namwung,
        l6_choice="ACID배기설비공사",
        cand_pool=[],
        parsed_report=None,
        chosen_wa="CUB",
    )
    assert result.value == "CUB"
    assert result.source == "auto_chroma_top1"


def test_resolve_wa_backcompat_chosen_wa_default_none(activity_namwung):
    """Back-compat — chosen_wa 인자 미전달 (default None) 시 기존 동작 유지.

    기존 호출자가 chosen_wa 안 줘도 cand_pool 있으면 정상 동작.
    """
    cand_pool = [("FAB", "ACID배기설비공사"), ("FAB", "ALKALI배기설비공사")]
    result = resolve_wa(
        activity_namwung,
        l6_choice="ACID배기설비공사",
        cand_pool=cand_pool,
        parsed_report=None,
    )
    assert result.value == "FAB"
    assert result.source == "auto_bp_single"
