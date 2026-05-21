"""Phase 1 view_builder v2 helper 단위 테스트.

5 helper + noise 분포 (85% 중심 + ±20% + 5%/5% outlier).
"""

from __future__ import annotations

import pytest

from pipeline.agents.optimizer.view_builder import (
    _compute_daily_quota,
    _compute_productivity,
    _make_display_label,
    _normalize_impact,
    _simulate_today_qty,
    _weighted_median,
)


def test_daily_quota_from_master():
    """plan_total_qty=100, total_days=10 -> daily=10.0."""
    assert _compute_daily_quota(100.0, 10) == pytest.approx(10.0)
    assert _compute_daily_quota(100.0, 0) == 0.0
    assert _compute_daily_quota(0.0, 5) == 0.0


def test_today_qty_simulation_noise_deterministic():
    """seed 고정 -> 동일 결과. noise_q range 0.55 ~ 1.55."""
    a = _simulate_today_qty(daily_qty=10.0, daily_workers=2.0, seed=42)
    b = _simulate_today_qty(daily_qty=10.0, daily_workers=2.0, seed=42)
    assert a == b
    assert 0.55 * 10.0 <= a["today_qty"] <= 1.55 * 10.0
    assert a["workers"] >= 1.0  # max(1.0, ...)


def test_today_qty_distribution_central_tendency():
    """200회 호출 평균 noise_q ≈ 0.85 (±0.05) — 경향성 + outlier 비율 5~25%."""
    samples = [
        _simulate_today_qty(daily_qty=10.0, daily_workers=2.0, seed=s)["today_qty"] for s in range(200)
    ]
    noises = [s / 10.0 for s in samples]
    avg_noise = sum(noises) / len(noises)
    assert 0.80 <= avg_noise <= 0.90, f"avg noise {avg_noise:.3f} not near 0.85"
    outliers = [n for n in noises if n < 0.65 or n > 1.40]
    assert 10 <= len(outliers) <= 50, f"outliers {len(outliers)}/200 out of [10,50]"


def test_productivity_calc():
    """perperson / master_perperson * 100."""
    assert _compute_productivity(perperson=5.0, master_perperson=5.0) == pytest.approx(100.0)
    assert _compute_productivity(perperson=4.0, master_perperson=5.0) == pytest.approx(80.0)
    assert _compute_productivity(perperson=5.0, master_perperson=0) == 0.0
    assert _compute_productivity(perperson=5.0, master_perperson=-1) == 0.0


def test_weighted_median_basic():
    """wv 가중 누적 50% 지점."""
    assert _weighted_median([10, 20, 30], [1, 1, 1]) == 20
    assert _weighted_median([10, 20, 30], [1, 10, 1]) == 20
    assert _weighted_median([], []) == 0
    # weights 합 0 -> 단순 평균 fallback
    assert _weighted_median([10, 20, 30], [0, 0, 0]) == pytest.approx(20.0)


def test_normalize_impact():
    """impact_raw / max(impact_raw) * 100 -> 0..100."""
    impacts = _normalize_impact([100, 200, 300])
    assert impacts == pytest.approx([33.33, 66.67, 100.0], abs=0.01)
    assert _normalize_impact([]) == []
    assert _normalize_impact([0, 0, 0]) == [0.0, 0.0, 0.0]


def test_display_label_format():
    """'98.9% (3.20 ton/인)' 형식 — perperson/unit 있으면 풀, 없으면 % 만."""
    assert _make_display_label(98.9, 3.2, "ton") == "98.9% (3.20 ton/인)"
    assert _make_display_label(81.3, 0.06, "m2") == "81.3% (0.06 m2/인)"
    assert _make_display_label(50, None, None) == "50.0%"
    assert _make_display_label(50, 1.5, None) == "50.0%"
    assert _make_display_label(50, None, "ton") == "50.0%"
