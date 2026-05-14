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


# ---------------------------------------------------------------------------
# Task 2: _parse_sheet4_activities 테스트
# ---------------------------------------------------------------------------
from pathlib import Path  # noqa: E402

import openpyxl  # noqa: E402
import pytest  # noqa: E402

from pipeline.agents.parser import _parse_sheet4_activities  # noqa: E402


@pytest.fixture(scope="module")
def sample_tong_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
    )


def test_parse_sheet4_activities_count(sample_tong_path: Path):
    """fixture loader 와 동일한 row 추출 — 골든 79건 포함."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["4.물량"]
    activities = _parse_sheet4_activities(ws)
    wb.close()
    assert len(activities) > 79, f"전체 row 수가 79 이하: {len(activities)}"
    companies = {a["company"] for a in activities}
    assert "남웅건설" in companies
    assert "세보엠이씨" in companies
    assert "창원기전" in companies


def test_parse_sheet4_unit_normalized(sample_tong_path: Path):
    """단위가 소문자로 정규화됐는지."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["4.물량"]
    activities = _parse_sheet4_activities(ws)
    wb.close()
    for a in activities:
        if a["unit"]:
            assert a["unit"] == a["unit"].lower(), f"unit 미정규화: {a['unit']!r}"


def test_parse_sheet4_today_qty_zero_default(sample_tong_path: Path):
    """today_qty 가 숫자 아니면 0.0. 음수는 정정/감산이라 valid (실 데이터 검증)."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["4.물량"]
    activities = _parse_sheet4_activities(ws)
    wb.close()
    for a in activities:
        assert isinstance(a["today_qty"], float)


def test_parse_sheet4_required_fields(sample_tong_path: Path):
    """company / work_content 가 빈 row 는 skip."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["4.물량"]
    activities = _parse_sheet4_activities(ws)
    wb.close()
    for a in activities:
        assert a["company"], f"company 비어있음: {a}"
        assert a["work_content"], f"work_content 비어있음: {a}"


# ---------------------------------------------------------------------------
# Task 3: _parse_sheet1_bp_summaries 테스트
# ---------------------------------------------------------------------------
from pipeline.agents.parser import _parse_sheet1_bp_summaries  # noqa: E402


def test_parse_sheet1_bp_summaries_count(sample_tong_path: Path):
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["1.출력인원 현황"]
    summaries = _parse_sheet1_bp_summaries(ws)
    wb.close()
    assert len(summaries) > 0, "bp_summaries 비어있음"
    companies = {s["company"] for s in summaries}
    assert "남웅건설" in companies, f"남웅건설 없음, 추출된 회사: {sorted(companies)[:10]}"


def test_parse_sheet1_bp_summaries_fields(sample_tong_path: Path):
    """BPSummary TypedDict 의 모든 필드 존재."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["1.출력인원 현황"]
    summaries = _parse_sheet1_bp_summaries(ws)
    wb.close()
    required_keys = {
        "bp_code",
        "company",
        "disc_abbrev",
        "zone",
        "scope",
        "work_text_yesterday",
        "work_text_today",
        "work_text_tomorrow",
        "today_incr_total",
        "today_cum_total",
    }
    for s in summaries:
        assert required_keys <= set(s.keys()), f"누락 키: {required_keys - set(s.keys())}"
        assert isinstance(s["today_incr_total"], int)
        assert isinstance(s["today_cum_total"], int)


def test_parse_sheet1_disc_abbrev_kr(sample_tong_path: Path):
    """disc_abbrev 가 한글로 변환됐거나 None."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["1.출력인원 현황"]
    summaries = _parse_sheet1_bp_summaries(ws)
    wb.close()
    valid_kr = {"건축", "설비", "전기", "UT", "공통가설", "제어", "토목"}
    for s in summaries:
        if s["disc_abbrev"] is not None:
            assert s["disc_abbrev"] in valid_kr or len(s["disc_abbrev"]) <= 5


# ---------------------------------------------------------------------------
# Task 4: _parse_sheet2_job_allocations 테스트
# ---------------------------------------------------------------------------
from pipeline.agents.parser import _parse_sheet2_job_allocations  # noqa: E402


def test_parse_sheet2_no_admin_jobs(sample_tong_path: Path):
    """관리자 직종 0건 (필터 작동)."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["2.직종별 인원현황"]
    jobs = _parse_sheet2_job_allocations(ws)
    wb.close()
    admin = {"BP소장", "공사관리자", "안전관리자", "품질관리자", "일반관리자"}
    for j in jobs:
        assert j["job_type"] not in admin, f"관리자 직종 누락 안 됨: {j}"


def test_parse_sheet2_no_total_rows(sample_tong_path: Path):
    """합계 row 0건."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["2.직종별 인원현황"]
    jobs = _parse_sheet2_job_allocations(ws)
    wb.close()
    for j in jobs:
        assert "투입 Total" not in (j.get("job_type") or ""), f"Total row 누락 안 됨: {j}"


def test_parse_sheet2_workers_cum_t_int(sample_tong_path: Path):
    """workers_cum_t 가 int."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["2.직종별 인원현황"]
    jobs = _parse_sheet2_job_allocations(ws)
    wb.close()
    for j in jobs:
        assert isinstance(j["workers_cum_t"], int)
