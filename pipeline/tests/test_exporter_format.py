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
