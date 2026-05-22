from __future__ import annotations

import pytest

from pipeline.collector.filename_parser import ParsedFilename, parse_filename


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # 업체별 — 샘플 그대로
        (
            "업체작업일보_M15X_PH4_041_M15X_PH4_UT_ 중원엔지니어링_UT배관공사_FAB_250917.xlsm",
            ParsedFilename(
                kind="bp",
                project="M15X_PH4_041_M15X_PH4_UT",
                bp_name="중원엔지니어링",
                trade="UT배관공사",
                zone="FAB",
                date="2025-09-17",
            ),
        ),
        # 통합
        (
            "통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx",
            ParsedFilename(
                kind="integrated",
                project="M15X Ph-3 IBL PJT 작업일보",
                bp_name=None,
                trade=None,
                zone=None,
                date="2025-09-25",
            ),
        ),
        # 업체별 — 다른 zone
        (
            "업체작업일보_M15X_PH3_001_acme_콘크리트공사_CUB_260101.xlsx",
            ParsedFilename(
                kind="bp",
                project="M15X_PH3_001",
                bp_name="acme",
                trade="콘크리트공사",
                zone="CUB",
                date="2026-01-01",
            ),
        ),
    ],
)
def test_parse_filename_valid(name: str, expected: ParsedFilename) -> None:
    assert parse_filename(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "random.xlsx",  # prefix 미일치
        "업체작업일보_x.xlsx",  # 토큰 부족
        "업체작업일보_a_b_c_d_99999.xlsx",  # date 5자리
        "업체작업일보_a_b_c_d_2025091.xlsx",  # date 7자리
        "통합작업일보_X.xlsx",  # date 없음
        "업체작업일보_a_b_c_d_abcdef.xlsx",  # date 비숫자
        "",  # 빈 문자열
        ".xlsx",  # stem 비어
        "업체작업일보_M15X_a_b_250917.txt",  # 확장자 다름 (단 본 함수는 stem 만 봄 — 호출자가 ext 체크)
    ],
)
def test_parse_filename_invalid(name: str) -> None:
    # .txt 케이스는 stem 만 보면 valid 라 통과할 수 있음 — 호출자 책임.
    # 본 테스트는 prefix / 토큰 / date 형식만 검증.
    if name.endswith(".txt"):
        # stem 으로는 valid — 통과 케이스라 skip
        pytest.skip("ext 검증은 호출자 책임")
    assert parse_filename(name) is None


def test_parsed_filename_frozen() -> None:
    """ParsedFilename 은 frozen dataclass — site_id 는 별 인자."""
    pf = parse_filename("통합작업일보_X_250101.xlsx")
    assert pf is not None
    with pytest.raises((AttributeError, TypeError)):  # frozen → setattr 차단
        pf.date = "x"  # type: ignore[misc]
