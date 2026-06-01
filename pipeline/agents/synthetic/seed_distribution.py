"""정규분포(bell) plan 배분 + 조건 엔벨로프 actual 배분 (총합 보존).

설계: docs/superpowers/specs/2026-05-29-cpia-reseed-v2-per-unit-seeding-design.md §1

순수 함수 (DB/LLM/난수 전역상태 의존 X). 결정성은 호출자가 factor 리스트로 주입.

핵심 불변식:
  - bell_distribute: Σ(plan 일별) == plan_total
  - conserve_actual: Σ(actual 일별) == plan_total  (활동 완료 시 100% 보존)
  - actual 은 head 구간(앞 1-tail_frac)에서 plan×factor 로 lag, tail 구간에서 잔여 보정
    → 진행중(head) 누적 ≈ factor 평균 × plan-to-date, 완료 시 Σ=plan_total.
"""

from __future__ import annotations

import math
from typing import List, Sequence


def bell_distribute(total: float, n: int, sigma_div: float = 4.0) -> List[float]:
    """total 을 n일에 종형(정규분포) 배분. Σ == total (정확).

    중심 = 기간 중점, σ = n / sigma_div (기본 4 → ±2σ 가 기간 전체).
    n<=1 이면 [total]. total<=0 또는 n<=0 이면 [0]*max(n,0).
    """
    if n <= 0:
        return []
    if n == 1:
        return [float(total)]
    if total <= 0:
        return [0.0] * n
    mid = (n - 1) / 2.0
    sigma = max(n / sigma_div, 1e-9)
    weights = [math.exp(-0.5 * ((i - mid) / sigma) ** 2) for i in range(n)]
    wsum = sum(weights)
    if wsum <= 0:
        return [total / n] * n
    return [total * w / wsum for w in weights]


def conserve_actual(
    plan_daily: Sequence[float],
    factors: Sequence[float],
    tail_frac: float = 0.30,
) -> List[float]:
    """plan 일별 × factor(조건) 로 lag 시키되, tail 구간에서 잔여를 보정해 총합 보존.

    Σ(반환) == Σ(plan_daily) (정확 — 활동 완료 시 100%).
      - head = 앞 (1-tail_frac) 일: actual = plan×factor (lag).
      - tail = 뒤 tail_frac 일: 잔여(plan_total − head_sum)를 plan 비중으로 분배 (마무리 push).
    factors len 은 plan_daily len 과 같아야 함.
    """
    n = len(plan_daily)
    if n == 0:
        return []
    plan_total = float(sum(plan_daily))
    raw = [float(p) * float(f) for p, f in zip(plan_daily, factors)]
    if plan_total <= 0:
        return [0.0] * n

    k = max(1, math.ceil(n * tail_frac))  # tail 일수
    head_n = n - k
    if head_n <= 0:
        # 너무 짧은 활동 — raw 를 plan_total 로 정규화 (lag 표현 불가)
        s = sum(raw)
        return [r * plan_total / s for r in raw] if s > 0 else list(map(float, plan_daily))

    head = raw[:head_n]
    head_sum = sum(head)
    remaining = plan_total - head_sum
    tail_plan = list(plan_daily[head_n:])
    tail_plan_sum = sum(tail_plan)

    if remaining <= 0:
        # head 가 이미 plan_total 초과 (factor 가 앞에서 큼) — head 를 축소, tail 0.
        scale = plan_total / head_sum if head_sum > 0 else 0.0
        return [h * scale for h in head] + [0.0] * k

    if tail_plan_sum > 0:
        tail = [remaining * (tp / tail_plan_sum) for tp in tail_plan]
    else:
        tail = [remaining / k] * k
    return head + tail


def cumulative(series: Sequence[float]) -> List[float]:
    """누적합 리스트."""
    out: List[float] = []
    acc = 0.0
    for v in series:
        acc += float(v)
        out.append(acc)
    return out
