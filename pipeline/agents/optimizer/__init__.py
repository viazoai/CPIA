"""CPIA Optimizer — Phase 1 PoC (synthetic v2 + hil_2)."""

from __future__ import annotations

from .agent import OptimizerConfig, optimize
from .synthetic_v2 import generate_synthetic_v2_group

__all__ = ["OptimizerConfig", "generate_synthetic_v2_group", "optimize"]
