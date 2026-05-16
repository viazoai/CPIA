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
