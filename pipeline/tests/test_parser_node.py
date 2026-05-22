"""parser_node — 1 첨부 = 1 ParsedDailyReport (D-12, D-3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.agents.parser_node import parser_node

SAMPLE_XLSX = Path(
    "/Users/kyungseoplee/Project Agent/CPIA/docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
)


def test_parser_node_returns_single_element_list() -> None:
    state = {"input_files": [str(SAMPLE_XLSX)]}
    out = parser_node(state)
    assert "parsed_reports" in out
    assert len(out["parsed_reports"]) == 1
    report = out["parsed_reports"][0]
    # ParsedDailyReport 는 TypedDict — dict-style 접근
    assert report["bp_summaries"]  # 비어있지 않음
    assert report["activities"]


def test_parser_node_raises_on_missing_input_files() -> None:
    with pytest.raises((KeyError, IndexError)):
        parser_node({})
