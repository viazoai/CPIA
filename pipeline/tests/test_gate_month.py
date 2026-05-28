"""Task 25 — gate_month 함수 자체 검증 (실 PG 호출 없이 import + sig)."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path


def _ensure_e2e_path() -> None:
    e2e_dir = Path(__file__).resolve().parent / "e2e"
    if str(e2e_dir) not in sys.path:
        sys.path.insert(0, str(e2e_dir))


def test_gate_month_callable():
    """gate_month 가 import 가능 + async 시그니처."""
    _ensure_e2e_path()
    from check_month_gate import gate_month  # type: ignore

    assert inspect.iscoroutinefunction(gate_month)
    sig = inspect.signature(gate_month)
    params = list(sig.parameters.keys())
    assert "month" in params
    assert "site_id" in params


def test_gate_month_checks_keys():
    """gate_month 가 7 check key 반환 (도큐먼트만)."""
    expected_keys = {
        "cold_start_zero",
        "g6_words_zero",
        "summary_complete",
        "trade_filter_clean",
        "no_kanji",
        "wp_count_reasonable",
        "point_in_time_populated",
    }
    _ensure_e2e_path()
    from check_month_gate import gate_month  # type: ignore

    source = inspect.getsource(gate_month)
    for k in expected_keys:
        assert f'"{k}"' in source, f"check key '{k}' 누락"
