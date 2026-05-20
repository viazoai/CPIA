"""_build_contractor_bars / _build_trade_bars baseline 필드.

spec §8.2 — ProductivityBarToggle 의 underCount 계산용. CPI < 90 인 BP 수 산출.
_bar_status 의 normal/caution 경계 = 90 → baseline=90.
"""

from __future__ import annotations

from pipeline.agents.optimizer.view_builder import (
    _build_contractor_bars,
    _build_trade_bars,
)


def test_contractor_bars_has_baseline():
    productivity = {"by_contractor": {"창원기전": {"cpi": 85.0}, "세보엠이씨": {"cpi": 95.0}}}
    bars = _build_contractor_bars(productivity)
    assert all("baseline" in b for b in bars)
    assert all(b["baseline"] == 90 for b in bars)


def test_trade_bars_has_baseline():
    productivity = {"by_l6": {"CABLE TRAY공사": {"cpi": 75.0}}}
    bars = _build_trade_bars(productivity)
    assert bars[0]["baseline"] == 90


def test_contractor_bars_under_count_derivable():
    """FE 의 underCount 산출: value < baseline 인 bar 수."""
    productivity = {
        "by_contractor": {
            "창원기전": {"cpi": 79.3},  # under
            "세보엠이씨": {"cpi": 59.0},  # under
            "남웅건설": {"cpi": 32.2},  # under
            "OK업체": {"cpi": 95.0},  # OK
        }
    }
    bars = _build_contractor_bars(productivity)
    under = sum(1 for b in bars if b["value"] < b["baseline"])
    assert under == 3
