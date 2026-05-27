"""Task 20 — backfill_optimizer_advice_llm DEFAULT_TRADES 좁힘 검증."""

from __future__ import annotations

import pathlib


def test_default_trades_narrow():
    """DEFAULT_TRADES = ('건축', '토목') — 시연 윈도우."""
    src = pathlib.Path("scripts/backfill_optimizer_advice_llm.py").read_text(encoding="utf-8")
    # 정확한 tuple literal 검증
    assert 'DEFAULT_TRADES = ("건축", "토목")' in src or "DEFAULT_TRADES = ('건축', '토목')" in src, (
        "DEFAULT_TRADES 가 좁아지지 않음 (Task 20 미적용)"
    )
    # 기존 7-trade list 부재 확인
    assert '("설비", "전기"' not in src and "('설비', '전기'" not in src, "기존 7-trade DEFAULT_TRADES 잔존"


def test_user_override_via_args():
    """사용자가 --trades 로 override 가능 (6월 이전 backfill 시)."""
    src = pathlib.Path("scripts/backfill_optimizer_advice_llm.py").read_text(encoding="utf-8")
    # argparse --trades 명시 + default=DEFAULT_TRADES 참조
    assert "--trades" in src
    # default 가 DEFAULT_TRADES 변수 참조 형식 (또는 직접 명시)
    assert "DEFAULT_TRADES" in src
