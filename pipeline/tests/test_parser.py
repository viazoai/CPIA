"""Parser 단위 테스트 — docs/superpowers/specs/2026-05-15-cpia-parser-design.md §9.1."""

from __future__ import annotations


from pipeline.agents.parser import (
    _disc_abbrev_to_kr,
    _ffill,
    _is_admin_job,
    _is_total_row,
    _normalize_unit,
)


def test_normalize_unit():
    assert _normalize_unit("M2") == "m2"
    assert _normalize_unit("m2") == "m2"
    assert _normalize_unit("Ton") == "ton"
    assert _normalize_unit("ton") == "ton"
    assert _normalize_unit("M3") == "m3"
    assert _normalize_unit("") == ""
    assert _normalize_unit("EA") == "ea"


def test_disc_abbrev_to_kr():
    assert _disc_abbrev_to_kr("AR") == "건축"
    assert _disc_abbrev_to_kr("ME") == "설비"
    assert _disc_abbrev_to_kr("EL") == "전기"
    assert _disc_abbrev_to_kr("UT") == "UT"
    assert _disc_abbrev_to_kr("TE") == "공통가설"
    assert _disc_abbrev_to_kr("IN") == "제어"
    assert _disc_abbrev_to_kr("CI") == "토목"
    assert _disc_abbrev_to_kr("XX") == "XX"
    assert _disc_abbrev_to_kr(None) is None


def test_is_admin_job():
    for job in ("BP소장", "공사관리자", "안전관리자", "품질관리자", "일반관리자"):
        assert _is_admin_job(job) is True, f"{job} 가 관리자로 인식 안 됨"
    for job in ("형틀공", "철근공", "콘크리트공", "비계공", "배관공"):
        assert _is_admin_job(job) is False, f"{job} 가 관리자로 잘못 인식"


def test_is_total_row():
    assert _is_total_row(("...", "기능공 투입 Total", 0, 0)) is True
    assert _is_total_row(("...", "BP사 투입 Total", 0, 0)) is True
    assert _is_total_row(("...", "형틀공", 100, 100)) is False
    assert _is_total_row(("...", None, 0, 0)) is False


def test_ffill_basic():
    rows = [
        ("h1", "h2", "h3", "h4", "h5"),
        ("h1", "h2", "h3", "h4", "h5"),
        ("h1", "h2", "h3", "h4", "h5"),
        ("h1", "h2", "h3", "h4", "h5"),
        ("A", "B", "C", "D", "E"),
        (None, None, None, None, "E2"),
        ("A2", None, "C2", None, "E3"),
    ]
    out = _ffill(rows, header_end=4, fill_cols=[0, 1, 2, 3])
    assert out == [
        (5, ["A", "B", "C", "D", "E"]),
        (6, ["A", "B", "C", "D", "E2"]),
        (7, ["A2", "B", "C2", "D", "E3"]),
    ]
