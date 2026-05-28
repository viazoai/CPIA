from __future__ import annotations

from pipeline.agents.optimizer._trade_frames import lookup_frame


def test_lookup_frame_known_wp():
    cat, txt = lookup_frame("철근콘크리트공사")
    assert cat == "골조"
    assert "적층" in txt


def test_lookup_frame_finish():
    cat, txt = lookup_frame("도장공사")
    assert cat == "마감"


def test_lookup_frame_envelope():
    cat, _ = lookup_frame("외장판넬공사")
    assert cat == "외장"


def test_lookup_frame_earth():
    cat, _ = lookup_frame("배수 공사")
    assert cat == "토공·흙막이"


def test_lookup_frame_fallback_unknown():
    cat, txt = lookup_frame("일반공조설비공사")
    assert cat == "일반"
    assert "균형" in txt or "일반" in txt


def test_lookup_frame_none():
    cat, _ = lookup_frame(None)
    assert cat == "일반"
