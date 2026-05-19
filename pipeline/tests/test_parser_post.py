"""parser_post 단위 테스트 — pure function, LLM 호출 X."""

from __future__ import annotations

from pipeline.agents.parser_post import (
    filter_marker_rows,
    pair_bp_summaries,
    normalize_company,
)


def test_filter_marker_rows_drops_markers():
    rows = [
        {"company_or_bp": "M15 PH-X"},
        {"company_or_bp": "FAB"},
        {"company_or_bp": "PH_X-002"},
        {"company_or_bp": "세보엠이씨"},
    ]
    out = filter_marker_rows(rows)
    assert len(out) == 2
    assert {r["company_or_bp"] for r in out} == {"PH_X-002", "세보엠이씨"}


def test_pair_bp_summaries_merges_adjacent():
    rows = [
        {"is_bp_code": True, "bp_code": "PH_X-002", "disc_abbrev": "공통가설", "zone": "FAB/CUB"},
        {
            "is_korean_company": True,
            "company": "㈜에스티엠",
            "disc_abbrev": "공통가설",
            "zone": "FAB/CUB",
            "today_cum_total": 162,
        },
    ]
    paired = pair_bp_summaries(rows)
    assert len(paired) == 1
    assert paired[0]["bp_code"] == "PH_X-002"
    assert paired[0]["company"] == "㈜에스티엠"
    assert paired[0]["today_cum_total"] == 162


def test_normalize_company_strips_juju_and_paren():
    assert normalize_company("㈜세보엠이씨") == "세보엠이씨"
    assert normalize_company("세아그린텍(Scrubber)") == "세아그린텍"
    assert normalize_company("창원기전FAB") == "창원기전FAB"
