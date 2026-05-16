"""Forecaster 공용 상수.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §0
"""

from __future__ import annotations

# PoC 가정: 1 인-day = 8 hour. 후속 cycle 에서 야간작업 별도 계산 시 본 상수 변경.
WORK_HOURS_PER_DAY = 8
