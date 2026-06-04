"""통합작업일보 export 양식 정합 단위 — fake SheetData / render_xlsx → openpyxl 재load. LLM 0, PG 0."""

from __future__ import annotations


from pipeline.agents.exporter import (
    SheetData,
    _company_trade_map,
)


def test_company_trade_map_most_common():
    rows = [
        {"company": "광건", "trade": "건축"},
        {"company": "광건", "trade": "건축"},
        {"company": "장평건설", "trade": "토목"},
        {"company": "장평건설", "trade": "토목"},
        {"company": "장평건설", "trade": "건축"},  # 토목 2 > 건축 1
        {"company": None, "trade": "건축"},  # company 없으면 무시
        {"company": "선보", "trade": None},  # trade 없으면 무시
    ]
    m = _company_trade_map(rows)
    assert m["광건"] == "건축"
    assert m["장평건설"] == "토목"  # 최빈(토목 2 > 건축 1)
    assert None not in m
    assert "선보" not in m
    # 동률 결정론: 토목 vs 건축 1:1 → 사전순(건축 < 토목)
    assert (
        _company_trade_map([{"company": "X", "trade": "토목"}, {"company": "X", "trade": "건축"}])["X"]
        == "건축"
    )
    assert _company_trade_map([]) == {}  # 빈 입력 → 빈 맵


def test_sheetdata_company_trade_default_empty():
    sd = SheetData(output_manpower=[], occupation_manpower=[], equipment=[], quantity=[])
    assert sd.company_trade == {}


# ──────────────────────────────────────────────────────────────────────────────
# Task 2 — 구분(col2) / 시트1 공종 company_trade 폴백
# ──────────────────────────────────────────────────────────────────────────────

from datetime import date  # noqa: E402
from io import BytesIO  # noqa: E402

from openpyxl import load_workbook  # noqa: E402

from pipeline.agents.exporter import render_xlsx  # noqa: E402


def _sd_one_company():
    return SheetData(
        output_manpower=[
            {
                "company": "광건",
                "bp_code": "PH_X-070",
                "zone": "CUB",
                "disc_abbrev": None,  # 공종 비어있음 → company_trade 폴백
                "work_text_today": "천장 설치",
                "workers_today_incr": {"total": 5},
            }
        ],
        occupation_manpower=[],
        equipment=[],
        quantity=[
            {
                "company": "광건",
                "trade": "건축",
                "mapper_wa": "CUB",
                "work_content": "경량벽체",
                "unit": "m2",
                "today_qty": 9,
            }
        ],
        company_wa={"광건": "CUB"},
        company_trade={"광건": "건축"},
    )


def test_render_division_col2_first_row_only():
    """구분(col2) = project, 첫 데이터 행(r5)만. 시트1·4 모두."""
    from pipeline.agents.exporter import COL_OUTPUT_MANPOWER, COL_QUANTITY

    wb = load_workbook(BytesIO(render_xlsx(_sd_one_company(), date(2025, 9, 25), project="M15X Ph-3 IBL")))
    # rename 후 시트1 = '1.작업사항'
    ws1 = wb["1.작업사항"]
    assert ws1.cell(5, COL_OUTPUT_MANPOWER["project"]).value == "M15X Ph-3 IBL"
    ws4 = wb["4.물량"]
    assert ws4.cell(5, COL_QUANTITY["project"]).value == "M15X Ph-3 IBL"


def test_render_sheet1_trade_fallback_to_company_trade():
    """시트1 공종(col4): disc_abbrev 없으면 company_trade 폴백."""
    from pipeline.agents.exporter import COL_OUTPUT_MANPOWER

    wb = load_workbook(BytesIO(render_xlsx(_sd_one_company(), date(2025, 9, 25), project="M15X Ph-3 IBL")))
    ws1 = wb["1.작업사항"]
    assert ws1.cell(5, COL_OUTPUT_MANPOWER["trade"]).value == "건축"


def test_unhide_and_clean_removes_hidden_outline_filter():
    import openpyxl
    from pipeline.agents.exporter import _unhide_and_clean

    ws = openpyxl.Workbook().active
    ws.auto_filter.ref = "B5:Y100"
    ws.row_dimensions[8].hidden = True
    ws.row_dimensions[8].outlineLevel = 2
    ws.column_dimensions["D"].hidden = True
    ws.freeze_panes = "F26"
    _unhide_and_clean(ws, n=10)
    assert ws.auto_filter.ref is None
    assert ws.row_dimensions[8].hidden is False
    assert ws.row_dimensions[8].outlineLevel == 0
    assert ws.column_dimensions["D"].hidden is False
    assert ws.column_dimensions["D"].outlineLevel == 0
    assert ws.sheet_view.showOutlineSymbols is False
    assert ws.freeze_panes == "A5"
