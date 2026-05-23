"""F3 piecewise 분포 — ramp + plateau + late-rise.

spec docs/superpowers/specs/2026-05-23-cpia-mock-rebuild-and-local-migration-design.md §4
"""

from __future__ import annotations

RAMP_END = 0.15
PLATEAU_END = 0.85
PEAK_MULT = 1.5
INTEGRAL = 0.5 * RAMP_END + (PLATEAU_END - RAMP_END) + (1.0 + PEAK_MULT) / 2.0 * (1.0 - PLATEAU_END)
P_NORM = 1.0 / INTEGRAL  # ≈ 1.039


def f3_daily_ratio(progress: float) -> float:
    """progress (0~1) → daily ratio (적분 = 1.0)."""
    if progress <= RAMP_END:
        return P_NORM * progress / RAMP_END
    if progress <= PLATEAU_END:
        return P_NORM
    return P_NORM * (1.0 + (progress - PLATEAU_END) / (1.0 - PLATEAU_END) * (PEAK_MULT - 1.0))


def f3_cum_ratio(progress: float) -> float:
    """progress (0~1) → cumulative ratio (0~1)."""
    if progress <= RAMP_END:
        return 0.5 * progress * progress / RAMP_END * P_NORM
    if progress <= PLATEAU_END:
        return (0.5 * RAMP_END + (progress - RAMP_END)) * P_NORM
    u = progress - PLATEAU_END
    late_part = u + 0.5 * (PEAK_MULT - 1.0) * u * u / (1.0 - PLATEAU_END)
    return (0.5 * RAMP_END + (PLATEAU_END - RAMP_END) + late_part) * P_NORM
