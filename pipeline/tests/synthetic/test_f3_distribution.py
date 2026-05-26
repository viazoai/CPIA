"""F3 piecewise 분포 함수 검증.

spec §4: ramp 15% + plateau 70% + late-rise 15%, peak=1.5×plateau.
적분 정확히 1.0 (정규화) + 경계값 + 단조성.
"""

from __future__ import annotations

import pytest

from pipeline.agents.synthetic.distributions import (
    PEAK_MULT,
    PLATEAU_END,
    P_NORM,
    RAMP_END,
    f3_cum_ratio,
    f3_daily_ratio,
)


def test_f3_constants():
    assert RAMP_END == 0.15
    assert PLATEAU_END == 0.85
    assert PEAK_MULT == 1.5
    assert P_NORM == pytest.approx(1.0 / 0.9625, abs=1e-4)  # ≈ 1.039


def test_f3_daily_ratio_boundaries():
    assert f3_daily_ratio(0.0) == pytest.approx(0.0)
    assert f3_daily_ratio(RAMP_END) == pytest.approx(P_NORM, abs=1e-6)
    assert f3_daily_ratio(0.5) == pytest.approx(P_NORM, abs=1e-6)  # plateau
    assert f3_daily_ratio(PLATEAU_END) == pytest.approx(P_NORM, abs=1e-6)
    assert f3_daily_ratio(1.0) == pytest.approx(P_NORM * PEAK_MULT, abs=1e-6)


def test_f3_cum_ratio_boundaries():
    assert f3_cum_ratio(0.0) == 0.0
    assert f3_cum_ratio(RAMP_END) == pytest.approx(0.5 * RAMP_END * P_NORM, abs=1e-6)  # ≈ 0.078
    assert f3_cum_ratio(0.5) == pytest.approx((0.5 * RAMP_END + (0.5 - RAMP_END)) * P_NORM, abs=1e-6)
    assert f3_cum_ratio(PLATEAU_END) == pytest.approx(
        (0.5 * RAMP_END + (PLATEAU_END - RAMP_END)) * P_NORM, abs=1e-6
    )
    # 핵심 검증: 적분 = 1.0
    assert f3_cum_ratio(1.0) == pytest.approx(1.0, abs=1e-6)


def test_f3_monotonic():
    """cum_ratio 는 progress 따라 단조 증가."""
    prev = -1.0
    for i in range(101):
        p = i / 100.0
        cur = f3_cum_ratio(p)
        assert cur >= prev - 1e-9, f"non-monotonic at progress={p}: prev={prev}, cur={cur}"
        prev = cur


def test_f3_daily_integral_approximation():
    """수치 적분으로 daily 의 sum ≈ 1.0 (1000 step)."""
    n = 1000
    dx = 1.0 / n
    total = sum(f3_daily_ratio(i * dx) * dx for i in range(n + 1))
    assert total == pytest.approx(1.0, abs=0.01)
