from __future__ import annotations

from pipeline.agents.exporter import _fill_quantity


def test_fill_quantity_prefers_mapper_wa():
    """시트4 Zone = mapper_wa 우선, 없으면 parser zone fallback."""
    import openpyxl

    ws = openpyxl.Workbook().active
    rows = [
        {"mapper_wa": "FAB", "zone": None, "trade": "건축", "unit": "m2"},
        {"mapper_wa": None, "zone": "CUB", "trade": "토목", "unit": "m"},
        {"mapper_wa": "", "zone": "FAB", "trade": "건축", "unit": "m2"},
    ]
    _fill_quantity(ws, rows, __import__("datetime").date(2025, 9, 24))
    from pipeline.agents.exporter import COL_QUANTITY, DATA_START_ROW

    zcol = COL_QUANTITY["zone"]
    assert ws.cell(DATA_START_ROW + 0, zcol).value == "FAB"  # mapper_wa
    assert ws.cell(DATA_START_ROW + 1, zcol).value == "CUB"  # fallback parser zone
    assert ws.cell(DATA_START_ROW + 2, zcol).value == "FAB"  # 빈 mapper_wa -> parser zone


def test_fill_output_manpower_company_wa():
    import openpyxl
    from pipeline.agents.exporter import _fill_output_manpower, COL_OUTPUT_MANPOWER, DATA_START_ROW

    ws = openpyxl.Workbook().active
    rows = [{"company": "글로벌유명", "zone": None, "disc_abbrev": "건축"}]
    company_wa = {"글로벌유명": "FAB"}
    _fill_output_manpower(ws, rows, __import__("datetime").date(2025, 9, 24), company_wa=company_wa)
    assert ws.cell(DATA_START_ROW, COL_OUTPUT_MANPOWER["zone"]).value == "FAB"


def test_fill_output_manpower_fallback_when_company_absent():
    """company_wa 에 회사 없으면 parser zone 으로 fallback, 그것도 없으면 None."""
    import openpyxl
    from pipeline.agents.exporter import _fill_output_manpower, COL_OUTPUT_MANPOWER, DATA_START_ROW
    ws = openpyxl.Workbook().active
    rows = [
        {"company": "미지정", "zone": "CUB", "disc_abbrev": "토목"},   # 맵에 없음 → parser zone
        {"company": "미지정", "zone": None, "disc_abbrev": "토목"},     # 둘 다 없음 → None
    ]
    _fill_output_manpower(ws, rows, __import__("datetime").date(2025, 9, 24), company_wa={"글로벌유명": "FAB"})
    z = COL_OUTPUT_MANPOWER["zone"]
    assert ws.cell(DATA_START_ROW + 0, z).value == "CUB"
    assert ws.cell(DATA_START_ROW + 1, z).value is None


def test_company_wa_tiebreak_deterministic():
    """동률 wa: FAB 우선, 비-FAB 동률은 문자열 사전순으로 결정론적."""
    from collections import Counter
    key = lambda kv: (kv[1], kv[0] == "FAB", kv[0])
    # FAB 와 CUB 동률 → FAB 우선
    assert max(Counter({"CUB": 2, "FAB": 2}).items(), key=key)[0] == "FAB"
    # 비-FAB 3개 동률 (FAB 없음) → 사전순 마지막 (deterministic)
    assert max(Counter({"A": 1, "B": 1, "C": 1}).items(), key=key)[0] == "C"
    # 카운트 우선 (동률 아님)
    assert max(Counter({"CUB": 5, "FAB": 1}).items(), key=key)[0] == "CUB"
