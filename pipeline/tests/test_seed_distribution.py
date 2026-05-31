"""순수 분포 함수 단위테스트 — 2초 결정론 루프 (DB/LLM 없음).

설계: docs/superpowers/specs/2026-05-29-cpia-reseed-v2-per-unit-seeding-design.md §1, §2
"""

from __future__ import annotations


from pipeline.agents.synthetic.seed_distribution import (
    bell_distribute,
    conserve_actual,
    cumulative,
)

EPS = 1e-6


# ---------------------------------------------------------------------------
# bell_distribute — Σ 보존 + 종형(unimodal) + 엣지
# ---------------------------------------------------------------------------


def test_bell_sums_to_total():
    for total, n in [(11.0, 10), (1300.0, 11), (9837.0, 44), (56.0, 25)]:
        s = sum(bell_distribute(total, n))
        assert abs(s - total) < EPS, f"Σ={s} != {total} (n={n})"


def test_bell_unimodal_peak_center():
    d = bell_distribute(100.0, 11)
    peak = d.index(max(d))
    # 피크가 중앙(±1) 근처
    assert abs(peak - 5) <= 1, f"peak idx={peak}"
    # 양 끝이 중앙보다 작음 (종형)
    assert d[0] < d[5] and d[-1] < d[5]
    # 대칭성 (정규분포)
    assert abs(d[0] - d[-1]) < EPS


def test_bell_edges():
    assert bell_distribute(100.0, 1) == [100.0]
    assert bell_distribute(0.0, 5) == [0.0] * 5
    assert bell_distribute(100.0, 0) == []


# ---------------------------------------------------------------------------
# conserve_actual — 총합 보존 + lag + 단위테스트 가능 불변식
# ---------------------------------------------------------------------------


def test_conserve_sums_to_plan_total():
    plan = bell_distribute(1000.0, 30)
    for fac in (0.85, 0.5, 1.0):
        factors = [fac] * 30
        actual = conserve_actual(plan, factors)
        assert abs(sum(actual) - 1000.0) < 1e-4, f"factor={fac} Σ={sum(actual)}"


def test_conserve_lag_in_head():
    """head 구간(앞 85%)에서 factor 0.8 이면 누적이 계획의 ~0.8 (lag)."""
    n = 100
    plan = bell_distribute(1000.0, n)
    factors = [0.8] * n
    actual = conserve_actual(plan, factors, tail_frac=0.15)
    cp = cumulative(plan)
    ca = cumulative(actual)
    # 중간 지점(idx 50, head 안) — actual/plan ≈ 0.8 (±0.03)
    mid = 50
    ratio = ca[mid] / cp[mid]
    assert 0.77 <= ratio <= 0.83, f"mid ratio={ratio:.3f} (lag 0.8 기대)"
    # 완료 시 100% 보존
    assert abs(ca[-1] - cp[-1]) < 1e-4


def test_conserve_total_with_mixed_factors():
    """저하/회복 섞여도 총합 보존."""
    n = 50
    plan = bell_distribute(500.0, n)
    # 정상 0.9, 저하 0.55, 회복 1.05 번갈아
    factors = [(0.9, 0.55, 1.05)[i % 3] for i in range(n)]
    actual = conserve_actual(plan, factors)
    assert abs(sum(actual) - 500.0) < 1e-4
    # 모든 일별 >= 0
    assert all(a >= -EPS for a in actual)


def test_conserve_monotonic_cum():
    n = 40
    plan = bell_distribute(800.0, n)
    factors = [0.82] * n
    ca = cumulative(conserve_actual(plan, factors))
    for i in range(1, len(ca)):
        assert ca[i] >= ca[i - 1] - EPS, f"누적 감소 idx={i}"


def test_conserve_short_activity():
    """tail_frac 적용 후 head 없는 짧은 활동 — 정규화로 보존."""
    for n in (1, 2, 3):
        plan = bell_distribute(100.0, n)
        actual = conserve_actual(plan, [0.8] * n)
        assert abs(sum(actual) - 100.0) < 1e-4, f"n={n} Σ={sum(actual)}"


def test_conserve_high_early_factor_no_overflow():
    """앞 구간 factor>1 (돌관) 로 head 가 plan 초과해도 총합 보존, 음수 없음."""
    n = 20
    plan = bell_distribute(200.0, n)
    factors = [1.3] * n  # 전부 초과
    actual = conserve_actual(plan, factors)
    assert abs(sum(actual) - 200.0) < 1e-4
    assert all(a >= -EPS for a in actual)
