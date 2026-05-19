"""Mapper U1.A — plan_mh propagate 단위 테스트.

mapper_node 안의 propagate logic 을 helper-style pure function 으로 추출해 검증.
실 mapper_node 통합은 후속 e2e 에서 검증.
"""

from __future__ import annotations


def propagate_plan_mh(mapped: list[dict], l6_mh_by_company: dict[str, dict[str, float]]) -> list[dict]:
    """mapped 의 l6_main 이 있으면 plan_mh 를 l6_mh 맵에서 lookup 해서 채움."""
    out = []
    for a in mapped:
        if a.get("l6_main") is not None:
            c = a.get("company")
            l6_map = l6_mh_by_company.get(c, {}) if c else {}
            a = {**a, "plan_mh": l6_map.get(a["l6_main"], 0)}
        out.append(a)
    return out


def test_plan_mh_propagated_for_matched_l6():
    """company+l6_main 매칭 시 plan_mh 가 맵 값으로 채워진다."""
    l6_mh = {"세보엠이씨": {"콘크리트 타설": 1500.0, "철근 가공": 800.0}}
    mapped = [
        {"company": "세보엠이씨", "l6_main": "콘크리트 타설"},
        {"company": "세보엠이씨", "l6_main": "철근 가공"},
    ]
    out = propagate_plan_mh(mapped, l6_mh)
    assert out[0]["plan_mh"] == 1500.0
    assert out[1]["plan_mh"] == 800.0


def test_plan_mh_zero_when_l6_not_in_map():
    """l6_main 이 맵에 없으면 plan_mh=0."""
    l6_mh = {"세보엠이씨": {"콘크리트 타설": 1500.0}}
    mapped = [{"company": "세보엠이씨", "l6_main": "철근 가공"}]
    out = propagate_plan_mh(mapped, l6_mh)
    assert out[0]["plan_mh"] == 0


def test_plan_mh_skip_when_no_l6_main():
    """l6_main=None 인 row 는 propagate 건드림 X."""
    l6_mh = {"세보엠이씨": {"콘크리트 타설": 1500.0}}
    mapped = [{"company": "세보엠이씨", "l6_main": None}]
    out = propagate_plan_mh(mapped, l6_mh)
    assert "plan_mh" not in out[0]


def test_plan_mh_zero_when_company_not_in_map():
    """company 가 맵에 없으면 plan_mh=0."""
    l6_mh = {"세보엠이씨": {"콘크리트 타설": 1500.0}}
    mapped = [{"company": "없는회사", "l6_main": "콘크리트 타설"}]
    out = propagate_plan_mh(mapped, l6_mh)
    assert out[0]["plan_mh"] == 0
