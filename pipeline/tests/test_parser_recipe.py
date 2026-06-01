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
