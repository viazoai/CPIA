from __future__ import annotations

import openpyxl
from pipeline.agents.recipe.fingerprint import fingerprint
from pipeline.agents.recipe.model import FormatRecipe, SheetRecipe, REQUIRED_FIELDS

UNI = "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
BP = "docs/sample/업체작업일보_M15X_PH4_041_M15X_PH4_UT_ 중원엔지니어링_UT배관공사_FAB_250917.xlsx"


def test_recipe_model_construct():
    sr = SheetRecipe(
        sheet_name="4.물량",
        columns={"work_content": 7, "unit": 8, "today_qty": 11, "trade": 4, "bp": 5},
        timeshift_blocks={},
        group_boundary="bp_company_pair",
        header_rows=(3, 4),
        final_flag_col=None,
    )
    fr = FormatRecipe(
        fingerprint="abc",
        format_class="업체",
        sheets={"activity": sr},
        generated_by="deterministic",
        confidence=1.0,
    )
    assert fr.sheets["activity"].columns["today_qty"] == 11
    assert "today_qty" in REQUIRED_FIELDS["activity"]


def test_fingerprint_distinguishes_and_is_stable():
    wb_u = openpyxl.load_workbook(UNI, data_only=True)
    wb_b = openpyxl.load_workbook(BP, data_only=True)
    fu1 = fingerprint(wb_u)
    fu2 = fingerprint(wb_u)
    fb = fingerprint(wb_b)
    assert fu1 == fu2  # 같은 wb 두 번 → 동일 (결정성)
    assert fu1 != fb  # 통합 vs 업체 → 다름
    assert len(fu1) == 64  # sha256 hex
    wb_u.close()
    wb_b.close()


from pipeline.agents.recipe.bpcode import is_bp_code_v2, looks_like_code_no_korean


def test_bp_code_v2_accepts_variants():
    # 기존 통합/업체 (회귀)
    assert is_bp_code_v2("PH_X-088")
    assert is_bp_code_v2("M15X_PH4_041")
    # P1 변종 — 누출 차단 대상
    assert is_bp_code_v2("M15X-PH4-041")     # dash
    assert is_bp_code_v2("M15X_PH4_041A")    # trailing suffix
    # 회사명은 코드 아님
    assert not is_bp_code_v2("중원엔지니어링")
    assert not is_bp_code_v2("협력업체01")


def test_leak_guard_flags_ascii_only_codeish():
    # 한글 0글자 + 코드 모양 → 회사명 아님 (격리 대상)
    assert looks_like_code_no_korean("ABC-2025-001")
    assert not looks_like_code_no_korean("중원엔지니어링")
    assert not looks_like_code_no_korean("Hyundai E&C")  # 공백 포함 영문 회사명 — 코드 모양 아님
