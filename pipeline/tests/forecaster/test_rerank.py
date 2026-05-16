"""Forecaster rerank.py 단위 테스트 — atomizer schema 정규화 + rerank.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §7
"""

from __future__ import annotations

import pytest

from pipeline.agents.forecaster.rerank import (
    _normalize_chroma_metadata,
    rerank_cases,
)


# ─── _normalize_chroma_metadata ──────────────────────────────────────────
def test_normalize_productivity_derive():
    """today_qty / assigned_workers → productivity."""
    m = {"today_qty": 80, "assigned_workers": 400, "conditions": "맑음"}
    result = _normalize_chroma_metadata(m)
    assert result["productivity"] == pytest.approx(0.2)


def test_normalize_zero_workers_safe():
    """workers=0 → productivity=0 (ZeroDivisionError 회피)."""
    m = {"today_qty": 80, "assigned_workers": 0, "conditions": ""}
    result = _normalize_chroma_metadata(m)
    assert result["productivity"] == 0.0


def test_normalize_conditions_string_to_list():
    """atomizer 의 ",".join() string → split list."""
    m = {"today_qty": 80, "assigned_workers": 100, "conditions": "맑음,우천"}
    result = _normalize_chroma_metadata(m)
    assert result["conditions"] == ["맑음", "우천"]


def test_normalize_conditions_empty_string():
    """conditions="" → []."""
    m = {"today_qty": 80, "assigned_workers": 100, "conditions": ""}
    result = _normalize_chroma_metadata(m)
    assert result["conditions"] == []


def test_normalize_conditions_missing_key():
    """conditions key 없음 → []."""
    m = {"today_qty": 80, "assigned_workers": 100}
    result = _normalize_chroma_metadata(m)
    assert result["conditions"] == []


# ─── rerank_cases ────────────────────────────────────────────────────────
def test_rerank_empty():
    """cases=[] → []."""
    assert rerank_cases([]) == []


def test_rerank_user_corrected_priority():
    """worker_source=user_corrected → distance ×0.7 (최우선)."""
    cases = [
        {
            "distance": 0.3,
            "metadata": {
                "today_qty": 1,
                "assigned_workers": 1,
                "conditions": "",
                "worker_source": "mh_prorated",
                "mapping_conf": 0.9,
            },
        },
        {
            "distance": 0.3,
            "metadata": {
                "today_qty": 1,
                "assigned_workers": 1,
                "conditions": "",
                "worker_source": "user_corrected",
                "mapping_conf": 0.9,
            },
        },
    ]
    result = rerank_cases(cases)
    assert result[0]["metadata"]["worker_source"] == "user_corrected"
    assert result[0]["rerank_score"] == pytest.approx(0.21)


def test_rerank_low_mapping_conf_demoted():
    """mapping_conf<0.7 → distance ×1.5 (우선순위 ↓)."""
    cases = [
        {
            "distance": 0.2,
            "metadata": {
                "today_qty": 1,
                "assigned_workers": 1,
                "conditions": "",
                "worker_source": "mh_prorated",
                "mapping_conf": 0.4,
            },
        },
        {
            "distance": 0.25,
            "metadata": {
                "today_qty": 1,
                "assigned_workers": 1,
                "conditions": "",
                "worker_source": "mh_prorated",
                "mapping_conf": 0.9,
            },
        },
    ]
    result = rerank_cases(cases)
    assert result[0]["metadata"]["mapping_conf"] == 0.9
    assert result[0]["rerank_score"] == pytest.approx(0.25)


def test_rerank_combined_user_corrected_low_conf():
    """user_corrected (×0.7) + low conf (×1.5) → ×1.05."""
    cases = [
        {
            "distance": 0.2,
            "metadata": {
                "today_qty": 1,
                "assigned_workers": 1,
                "conditions": "",
                "worker_source": "user_corrected",
                "mapping_conf": 0.4,
            },
        },
    ]
    result = rerank_cases(cases)
    assert result[0]["rerank_score"] == pytest.approx(0.2 * 0.7 * 1.5)


def test_rerank_normalized_conditions_in_result():
    """rerank 결과의 metadata 가 정규화 적용된 상태인지."""
    cases = [
        {
            "distance": 0.1,
            "metadata": {
                "today_qty": 80,
                "assigned_workers": 400,
                "conditions": "맑음,우천",
                "worker_source": "mh_prorated",
                "mapping_conf": 0.9,
            },
        },
    ]
    result = rerank_cases(cases)
    assert result[0]["metadata"]["productivity"] == pytest.approx(0.2)
    assert result[0]["metadata"]["conditions"] == ["맑음", "우천"]


def test_format_chroma_result_empty():
    """rag_result 가 비어있을 때 [] 반환."""
    from pipeline.agents.forecaster.agent import _format_chroma_result

    result = _format_chroma_result({"ids": [[]], "documents": [[]], "distances": [[]], "metadatas": [[]]})
    assert result == []


def test_format_chroma_result_normal():
    """ids/documents/distances/metadatas 의 zip 결과."""
    from pipeline.agents.forecaster.agent import _format_chroma_result

    rag = {
        "ids": [["a", "b"]],
        "documents": [["doc-a", "doc-b"]],
        "distances": [[0.1, 0.2]],
        "metadatas": [[{"k": "v1"}, {"k": "v2"}]],
    }
    result = _format_chroma_result(rag)
    assert len(result) == 2
    assert result[0] == {"document": "doc-a", "distance": 0.1, "metadata": {"k": "v1"}}
    assert result[1] == {"document": "doc-b", "distance": 0.2, "metadata": {"k": "v2"}}


def test_format_chroma_result_none_ids():
    """ids 가 None 일 때 [] 반환."""
    from pipeline.agents.forecaster.agent import _format_chroma_result

    result = _format_chroma_result({"ids": None, "documents": None, "distances": None, "metadatas": None})
    assert result == []


# ─── boundary tests (권고 #5) ────────────────────────────────────────────
def test_rerank_mapping_conf_boundary_07_not_demoted():
    """mapping_conf = 0.7 정확 → demote 없음 (< 0.7 strict)."""
    cases = [
        {
            "distance": 0.2,
            "metadata": {
                "today_qty": 1,
                "assigned_workers": 1,
                "conditions": "",
                "worker_source": "mh_prorated",
                "mapping_conf": 0.7,
            },
        },
    ]
    result = rerank_cases(cases)
    # mapping_conf == 0.7 은 < 0.7 false → 가중치 미적용
    assert result[0]["rerank_score"] == pytest.approx(0.2)
