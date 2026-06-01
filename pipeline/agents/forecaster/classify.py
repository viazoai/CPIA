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
# 2026-05-29 사용자 결정: condition 저하 (정상 페이스 대비 생산성 하락) 를 risk_level 에 직접 반영.
# 이전엔 assessment(today vs rag평균) + delay 주도라, condition 별로 rag 평균도 같이 저하되면
# delta~0 → 정상으로 빠져 condition 저하 wp 가 위험/주의로 안 잡혔다.
RISK_PROD_WARN_RATIO = 0.85  # 정상 페이스 대비 < 85% → 주의
RISK_PROD_CRIT_RATIO = 0.70  # 정상 페이스 대비 < 70% → 이상

_LEVEL_ORDER = {"정상": 0, "주의": 1, "이상": 2}


def _worse(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """두 level 중 더 나쁜 쪽 (정상 < 주의 < 이상). None 은 무시."""
    cands = [x for x in (a, b) if x in _LEVEL_ORDER]
    if not cands:
        return a if a is not None else b
    return max(cands, key=lambda x: _LEVEL_ORDER[x])


def _prod_ratio_level(productivity_ratio: Optional[float]) -> Optional[str]:
    """정상 페이스 대비 생산성 비율 → level."""
    if productivity_ratio is None:
        return None
    if productivity_ratio < RISK_PROD_CRIT_RATIO:
        return "이상"
    if productivity_ratio < RISK_PROD_WARN_RATIO:
        return "주의"
    return "정상"


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
    productivity_ratio: Optional[float] = None,
) -> Optional[str]:
    """hybrid 룰 — (assessment + recovery + delay + state) 와 정상 페이스 대비 생산성 중 더 나쁜 쪽.

    2026-05-29: productivity_ratio (today_prod / 계획 정상 인당) threshold 추가.
    condition 저하 wp 가 assessment/delay 로는 정상으로 빠지더라도, 정상 페이스 대비
    생산성이 낮으면 (< 85% 주의, < 70% 이상) 위험/주의로 격상.
    임계 DELAY_DAYS_BOUND·RECOVERY_LIKELIHOOD_BOUND = 가정값 (회귀 후 조정).
    """
    prod_level = _prod_ratio_level(productivity_ratio)

    if assessment is None:
        # assessment 없으면(cold) 정상 페이스 대비만으로 판정.
        return prod_level
    if schedule_state == "post_due":
        return "이상"
    if schedule_state == "unknown" or delay_days is None:
        return _worse(assessment, prod_level)

    if assessment == "정상":
        base = "주의" if delay_days > DELAY_DAYS_BOUND else "정상"
    elif assessment == "주의":
        if (
            recovery_likelihood is not None
            and recovery_likelihood >= RECOVERY_LIKELIHOOD_BOUND
            and delay_days <= DELAY_DAYS_BOUND
        ):
            base = "주의"
        else:
            base = "이상"
    else:  # assessment == "이상"
        base = "주의" if delay_days <= 0 else "이상"

    return _worse(base, prod_level)
