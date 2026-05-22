"""parser_node — 1 첨부 = 1 ParsedDailyReport (D-12, D-3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.agents.parser_node import parser_node

SAMPLE_XLSX = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "sample"
    / "통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
)


def test_parser_node_returns_parsed_report() -> None:
    state = {"input_files": [str(SAMPLE_XLSX)]}
    out = parser_node(state)
    # mapper 가 state["parsed"] (singular, dict) 로 읽음 — D-12 + 기존 mapper contract
    assert "parsed" in out
    report = out["parsed"]
    # ParsedDailyReport 는 TypedDict — dict-style 접근
    assert report["bp_summaries"]  # 비어있지 않음
    assert report["activities"]


def test_parser_node_raises_on_missing_input_files() -> None:
    with pytest.raises((KeyError, IndexError)):
        parser_node({})
