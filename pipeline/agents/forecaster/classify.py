"""Forecaster classify — assessment + risk_level 분류 룰. 순수 함수.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §6

4 함수:
  1. classify_assessment_rag       — RAG 모드 (delta ±15%/±25%)
  2. classify_assessment_plan      — Plan fallback (productivity ratio 0.85/0.65)
  3. classify_assessment           — routing (RAG 우선 + Plan fallback + cold start None)
  4. classify_risk_level           — hybrid (assessment + recovery + delay + state)
"""

from __future__ import annotations

from typing import Optional

from .constants import WORK_HOURS_PER_DAY

# ─── 분류 임계값 (Task 10 §11.3) ──────────────────────────────────────────
RAG_NORMAL_BOUND = 0.15  # |delta| <= 0.15 → 정상 (delta = (today-rag)/rag)
RAG_WARN_BOUND = 0.25  # 0.15 < |delta| <= 0.25 → 주의
PLAN_NORMAL_RATIO = 0.85  # today_prod / plan_prod_proxy >= 0.85 → 정상
PLAN_WARN_RATIO = 0.65  # 0.65 <= ratio < 0.85 → 주의
DELAY_DAYS_BOUND = 5  # delay_days > 5 → 누적 지연 신호
RECOVERY_LIKELIHOOD_BOUND = 0.7  # recovery >= 0.7 → 회복 가능


def classify_assessment_rag(today_prod: float, rag_avg_prod: float) -> str:
    """RAG 모드 — productivity delta 임계 ±15% / ±25%."""
    if rag_avg_prod == 0:
        return "정상"
    delta = (today_prod - rag_avg_prod) / rag_avg_prod
    # 임계 -RAG_NORMAL_BOUND / -RAG_WARN_BOUND (경계 포함). 부동소수점 epsilon 1e-9 로 boundary 보호.
    eps = 1e-9
    if delta >= -RAG_NORMAL_BOUND - eps:
        return "정상"
    if delta >= -RAG_WARN_BOUND - eps:
        return "주의"
    return "이상"


def classify_assessment_plan(
    today_prod: float,
    plan_total_qty_main: float,
    plan_mh_sum: float,
) -> str:
    """Plan fallback — 단위당 productivity ratio 임계 0.85 / 0.65.

    plan_prod_proxy = plan_total_qty[main_unit] / (plan_mh_sum / 8)
                     # 그 공종이 정상 진행 시 1 인-day 가 만드는 unit 수
    ratio           = today_prod / plan_prod_proxy
    """
    if plan_mh_sum <= 0 or plan_total_qty_main <= 0:
        return "정상"
    plan_prod_proxy = plan_total_qty_main / (plan_mh_sum / WORK_HOURS_PER_DAY)
    if plan_prod_proxy == 0:
        return "정상"
    ratio = today_prod / plan_prod_proxy
    if ratio >= PLAN_NORMAL_RATIO:
        return "정상"
    if ratio >= PLAN_WARN_RATIO:
        return "주의"
    return "이상"


def classify_assessment(
    rag_n: int,
    today_prod: float,
    rag_avg_prod: float,
    plan_total_qty_main: Optional[float],
    plan_mh_sum: Optional[float],
) -> Optional[str]:
    """RAG 우선 + Plan fallback + cold start.

    Spec §0.1 ②: rag_n >= 3 → RAG / else if plan 가용 → Plan / else None.
    """
    if rag_n >= 3:
        return classify_assessment_rag(today_prod, rag_avg_prod)
    if plan_mh_sum and plan_mh_sum > 0 and plan_total_qty_main:
        return classify_assessment_plan(today_prod, plan_total_qty_main, plan_mh_sum)
    return None


def classify_risk_level(
    assessment: Optional[str],
    recovery_likelihood: Optional[float],
    delay_days: Optional[float],
    schedule_state: str,
) -> Optional[str]:
    """hybrid 룰 — assessment + recovery + delay + state.

    임계 DELAY_DAYS_BOUND·RECOVERY_LIKELIHOOD_BOUND = 가정값 (회귀 후 조정).
    """
    if assessment is None:
        return None
    if schedule_state == "post_due":
        return "이상"
    if schedule_state == "unknown" or delay_days is None:
        return assessment

    if assessment == "정상":
        if delay_days > DELAY_DAYS_BOUND:
            return "주의"
        return "정상"
    if assessment == "주의":
        if (
            recovery_likelihood is not None
            and recovery_likelihood >= RECOVERY_LIKELIHOOD_BOUND
            and delay_days <= DELAY_DAYS_BOUND
        ):
            return "주의"
        return "이상"
    if delay_days <= 0:
        return "주의"
    return "이상"
