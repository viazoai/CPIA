"""parser_post 단위 테스트 — pure function, LLM 호출 X."""

from __future__ import annotations

from pipeline.agents.parser_post import (
    extract_zone,
    filter_marker_rows,
    normalize_company,
    pair_bp_summaries,
    split_company_and_zone,
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


class TestNormalizeCompanyExtended:
    """spec §2.1 — 괄호 부속 + (주) prefix 일관 처리."""

    def test_strip_jusik_prefix(self) -> None:
        assert normalize_company("㈜남웅건설") == "남웅건설"

    def test_strip_paren_jusik(self) -> None:
        assert normalize_company("(주)캠파트너스") == "캠파트너스"

    def test_strip_paren_kv(self) -> None:
        assert normalize_company("창원기전(6.6kV)") == "창원기전"

    def test_strip_paren_with_jusik(self) -> None:
        assert normalize_company("(주)성우이엔씨") == "성우이엔씨"

    def test_none_input(self) -> None:
        assert normalize_company(None) is None

    def test_empty_string(self) -> None:
        assert normalize_company("") is None


class TestSplitCompanyAndZone:
    """spec §2.1 옵션 2 — FAB/CUB suffix 회사명에서 분리, zone 반환 X."""

    def test_strip_cub_suffix(self) -> None:
        assert split_company_and_zone("에스비테크CUB") == "에스비테크"

    def test_strip_fab_with_paren(self) -> None:
        assert split_company_and_zone("광건티엔씨FAB(수장2)") == "광건티엔씨"

    def test_no_suffix(self) -> None:
        assert split_company_and_zone("남웅건설") == "남웅건설"

    def test_none_input(self) -> None:
        assert split_company_and_zone(None) is None


class TestExtractZone:
    """spec §2.1 옵션 2 — col 6 (Scope) 명시 토큰만, 모호 시 None."""

    def test_fab_single_token(self) -> None:
        assert extract_zone("FAB") == "FAB"

    def test_cub_single_token(self) -> None:
        assert extract_zone("CUB") == "CUB"

    def test_fab_start_token(self) -> None:
        assert extract_zone("FAB 전구간") == "FAB"

    def test_cub_start_token_with_text(self) -> None:
        assert extract_zone("CUB 1F~7F 슬라브, FAB~CUB공동구") == "CUB"

    def test_fab_cub_both_ambiguous(self) -> None:
        assert extract_zone("FAB/CUB") is None
        assert extract_zone("CUB/FAB") is None

    def test_text_middle_ambiguous(self) -> None:
        assert extract_zone("M15X FAB F04") is None
        assert extract_zone("클라이머 설치 ... FAB X48") is None
        assert extract_zone("-금일 : M15 Ph-X FAB 1F ~ 7F") is None

    def test_none_input(self) -> None:
        assert extract_zone(None) is None
