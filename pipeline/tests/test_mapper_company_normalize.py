"""normalize_company 회귀 방지 — Mapper 가 이 함수에 의존하므로."""

from __future__ import annotations

from pipeline.agents.parser_post import normalize_company


def test_mapper_normalizes_juju_prefix():
    assert normalize_company("㈜세보엠이씨") == "세보엠이씨"


def test_mapper_normalizes_paren_split():
    assert normalize_company("세아그린텍(Scrubber)") == "세아그린텍"
