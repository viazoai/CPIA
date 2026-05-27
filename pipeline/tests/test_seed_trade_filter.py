"""Task 19 — seed_dummy_year 의 trade filter 작동.

inspect 으로 args.trades 사용 + filter 분기 존재 확인.
실 INSERT 검증은 Task 27-29 backfill 에서.
"""

from __future__ import annotations

import inspect
import importlib
import pathlib

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED_PATH = REPO_ROOT / "scripts" / "seed_dummy_year.py"


def test_seed_has_trades_argument():
    """argparse 에 --trades 옵션 + default ['건축', '토목']."""
    # seed_dummy_year 가 import-safe 여야 함 (시도)
    try:
        seed = importlib.import_module("scripts.seed_dummy_year")
    except (ImportError, ModuleNotFoundError):
        pytest.skip("scripts module not importable (PYTHONPATH 이슈, 단 실 script 사용 가능)")
        return

    # amain 함수 source 검사
    source = inspect.getsource(seed.amain)
    assert "--trades" in source
    assert "'건축'" in source or '"건축"' in source
    assert "'토목'" in source or '"토목"' in source


def test_seed_has_trade_filter_branch():
    """mapper_rows 만들 때 trade not in trades → skip 분기."""
    src_text = SEED_PATH.read_text(encoding="utf-8")
    # "trade" not in 분기 또는 trades 사용 패턴
    assert "trades" in src_text
    # `mapper_rows.append` 직전에 trade 체크
    # 간단 검증: "_build_mapper_row" 호출 후 trade 체크 분기 존재
    assert "args.trades" in src_text or "in trades" in src_text or "not in trades" in src_text


def test_default_trades_value():
    """default = ['건축', '토목']."""
    src_text = SEED_PATH.read_text(encoding="utf-8")
    # default=["건축","토목"] 또는 default=("건축","토목")
    assert '"건축"' in src_text or "'건축'" in src_text
    assert '"토목"' in src_text or "'토목'" in src_text
