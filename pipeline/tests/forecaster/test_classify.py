"""Forecaster classify.py 단위 테스트.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §6
"""

from __future__ import annotations


from pipeline.agents.forecaster.classify import (
    classify_assessment,
    classify_risk_level,
)


# ─── assessment: RAG 모드 ────────────────────────────────────────────────
def test_classify_assessment_rag_normal():
    """delta -10% (≥-15%) → 정상."""
    result = classify_assessment(
        rag_n=5, today_prod=0.9, rag_avg_prod=1.0, plan_total_qty_main=100, plan_mh_sum=1000
    )
    assert result == "정상"


def test_classify_assessment_rag_caution():
    """delta -20% (∈[-25%, -15%)) → 주의."""
    result = classify_assessment(
        rag_n=5, today_prod=0.8, rag_avg_prod=1.0, plan_total_qty_main=100, plan_mh_sum=1000
    )
    assert result == "주의"


def test_classify_assessment_rag_risk():
    """delta -30% (< -25%) → 이상."""
    result = classify_assessment(
        rag_n=5, today_prod=0.7, rag_avg_prod=1.0, plan_total_qty_main=100, plan_mh_sum=1000
    )
    assert result == "이상"


def test_classify_assessment_rag_boundary_normal():
    """delta = -15% 정확 → 정상 (≥-15%)."""
    result = classify_assessment(
        rag_n=5, today_prod=0.85, rag_avg_prod=1.0, plan_total_qty_main=100, plan_mh_sum=1000
    )
    assert result == "정상"


# ─── assessment: Plan fallback ───────────────────────────────────────────
def test_classify_assessment_plan_fallback_normal():
    """RAG=0, Plan productivity ratio 0.9 → 정상.

    plan_prod = 100 / (800 / 8) = 1.0 m/인-day
    today_prod = 0.9
    ratio = 0.9 / 1.0 = 0.9 ≥ 0.85 → 정상
    """
    result = classify_assessment(
        rag_n=0, today_prod=0.9, rag_avg_prod=0.0, plan_total_qty_main=100, plan_mh_sum=800
    )
    assert result == "정상"


def test_classify_assessment_plan_fallback_caution():
    """ratio 0.7 (∈[0.65, 0.85)) → 주의."""
    result = classify_assessment(
        rag_n=0, today_prod=0.7, rag_avg_prod=0.0, plan_total_qty_main=100, plan_mh_sum=800
    )
    assert result == "주의"


def test_classify_assessment_plan_fallback_risk():
    """ratio 0.5 (<0.65) → 이상."""
    result = classify_assessment(
        rag_n=0, today_prod=0.5, rag_avg_prod=0.0, plan_total_qty_main=100, plan_mh_sum=800
    )
    assert result == "이상"


def test_classify_assessment_cold_start():
    """RAG=0 + Plan 없음 → None."""
    result = classify_assessment(
        rag_n=0, today_prod=0.0, rag_avg_prod=0.0, plan_total_qty_main=None, plan_mh_sum=None
    )
    assert result is None


def test_classify_assessment_cold_start_zero_plan():
    """RAG=0 + Plan mh=0 → None."""
    result = classify_assessment(
        rag_n=0, today_prod=0.5, rag_avg_prod=0.0, plan_total_qty_main=100, plan_mh_sum=0
    )
    assert result is None


# ─── risk_level ──────────────────────────────────────────────────────────
def test_classify_risk_normal_on_track():
    """정상 + delay≤5 → 정상."""
    result = classify_risk_level("정상", None, 3.0, "on_schedule")
    assert result == "정상"


def test_classify_risk_normal_with_delay():
    """정상 + delay>5 → 주의 (누적 delay)."""
    result = classify_risk_level("정상", None, 10.0, "on_schedule")
    assert result == "주의"


def test_classify_risk_caution_recoverable():
    """주의 + recovery≥0.7 + delay≤5 → 주의."""
    result = classify_risk_level("주의", 0.8, 3.0, "on_schedule")
    assert result == "주의"


def test_classify_risk_caution_unrecoverable():
    """주의 + recovery<0.7 → 이상."""
    result = classify_risk_level("주의", 0.5, 3.0, "on_schedule")
    assert result == "이상"


def test_classify_risk_severe_ahead():
    """이상 + delay≤0 (ahead) → 주의 (회복 여유)."""
    result = classify_risk_level("이상", 0.7, -2.0, "on_schedule")
    assert result == "주의"


def test_classify_risk_severe_behind():
    """이상 + delay>0 → 이상."""
    result = classify_risk_level("이상", 0.7, 10.0, "on_schedule")
    assert result == "이상"


def test_classify_risk_post_due_forced():
    """post_due → 이상 강제 (assessment 무관)."""
    result = classify_risk_level("정상", None, 0.0, "post_due")
    assert result == "이상"


def test_classify_risk_unknown_falls_back_to_assessment():
    """schedule_state=unknown + delay None → assessment 그대로."""
    result = classify_risk_level("주의", 0.7, None, "unknown")
    assert result == "주의"


def test_classify_risk_cold_start_none():
    """assessment=None → None."""
    result = classify_risk_level(None, None, 0.0, "unknown")
    assert result is None


# ─── boundary tests (권고 #5) ────────────────────────────────────────────
def test_classify_assessment_rag_boundary_caution():
    """delta = -25% 정확 → 주의 (≥-25%)."""
    result = classify_assessment(
        rag_n=5, today_prod=0.75, rag_avg_prod=1.0, plan_total_qty_main=100, plan_mh_sum=1000
    )
    assert result == "주의"


def test_classify_assessment_plan_boundary_normal():
    """ratio = 0.85 정확 → 정상 (≥0.85).

    plan_prod = 100 / (800/8) = 1.0. today_prod = 0.85 → ratio = 0.85 정확.
    """
    result = classify_assessment(
        rag_n=0, today_prod=0.85, rag_avg_prod=0.0, plan_total_qty_main=100, plan_mh_sum=800
    )
    assert result == "정상"


def test_classify_assessment_plan_boundary_caution():
    """ratio = 0.65 정확 → 주의 (≥0.65)."""
    result = classify_assessment(
        rag_n=0, today_prod=0.65, rag_avg_prod=0.0, plan_total_qty_main=100, plan_mh_sum=800
    )
    assert result == "주의"


def test_classify_risk_normal_boundary_5days():
    """정상 + delay=5 정확 → 정상 (delay≤5)."""
    result = classify_risk_level("정상", None, 5.0, "on_schedule")
    assert result == "정상"


def test_classify_risk_caution_boundary_recovery_07():
    """주의 + recovery=0.7 정확 + delay≤5 → 주의 (recovery≥0.7)."""
    result = classify_risk_level("주의", 0.7, 5.0, "on_schedule")
    assert result == "주의"


def test_classify_risk_severe_boundary_delay_0():
    """이상 + delay=0 정확 → 주의 (delay≤0)."""
    result = classify_risk_level("이상", 0.5, 0.0, "on_schedule")
    assert result == "주의"


def test_classify_assessment_rag_boundary_epsilon():
    """boundary 가 약간 어긋났을 때의 분류 검증 (spec §11.3).

    classify_assessment_rag 의 eps=1e-9 보호 회귀 신호.
    rag_avg=1.0, today=0.75 → delta=-0.25 (RAG_WARN_BOUND 정확 경계).
    eps=1e-9 보다 큰 외측 (-1e-8) → "이상", 내측 (+1e-8) → "주의".
    """
    from pipeline.agents.forecaster.classify import classify_assessment_rag

    # 경계보다 1e-8 만큼 더 나쁨 (eps=1e-9 보호 범위 밖) → "이상"
    assert classify_assessment_rag(today_prod=0.75 - 1e-8, rag_avg_prod=1.0) == "이상"
    # 경계보다 1e-8 만큼 더 좋음 → "주의"
    assert classify_assessment_rag(today_prod=0.75 + 1e-8, rag_avg_prod=1.0) == "주의"
