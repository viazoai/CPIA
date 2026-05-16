"""Forecaster synthetic.py 단위 테스트.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §9
"""

from __future__ import annotations

import random
from datetime import date

import pytest

from pipeline.agents.forecaster.synthetic import generate_synthetic_day


@pytest.fixture
def base_row():
    return {
        "company": "세보엠이씨",
        "l6_main": "일반공조설비공사",
        "l5_disc": "설비",
        "wa": "AC",
        "unit": "m",
        "today_qty": 80.0,
        "assigned_workers": 401.4,
        "work_content": "AHU 덕트 연결",
        "mapping_conf": 0.85,
    }


def test_generate_clear_normal(base_row):
    """맑음 + 정상 → ±5% 변동."""
    random.seed(42)
    result = generate_synthetic_day(base_row, day_offset=1, weather="맑음", incident="정상")
    assert "맑음" in result["conditions"]
    assert "정상" not in result["conditions"]
    assert 76 <= result["today_qty"] <= 84


def test_generate_rainy_decrease(base_row):
    """우천 → -15~25%."""
    random.seed(42)
    result = generate_synthetic_day(base_row, day_offset=2, weather="우천", incident="정상")
    assert "우천" in result["conditions"]
    assert 55 <= result["today_qty"] <= 70


def test_generate_equipment_wait(base_row):
    """장비대기 → -20~35%."""
    random.seed(42)
    result = generate_synthetic_day(base_row, day_offset=3, weather="맑음", incident="장비대기")
    assert "장비대기" in result["conditions"]
    assert 47 <= result["today_qty"] <= 66


def test_generate_seed_reproducible(base_row):
    """같은 seed → 동일 출력."""
    random.seed(42)
    r1 = generate_synthetic_day(base_row, day_offset=1, weather="맑음", incident="정상")
    random.seed(42)
    r2 = generate_synthetic_day(base_row, day_offset=1, weather="맑음", incident="정상")
    assert r1["today_qty"] == r2["today_qty"]


def test_generate_metadata_atomizer_schema_match(base_row):
    """생성된 row 가 atomizer _build_metadata 와 호환 schema."""
    random.seed(42)
    row = generate_synthetic_day(base_row, day_offset=1, weather="맑음", incident="정상")
    required_keys = {
        "date",
        "company",
        "l5_disc",
        "l6_main",
        "wa",
        "unit",
        "today_qty",
        "assigned_workers",
        "worker_source",
        "mapping_conf",
        "conditions",
        "work_content",
    }
    assert required_keys.issubset(row.keys())
    assert isinstance(row["conditions"], list)


def test_generate_date_offset(base_row):
    """day_offset=N → date 가 reference - N 일."""
    row = generate_synthetic_day(
        base_row, day_offset=5, weather="맑음", incident="정상", reference_date=date(2025, 9, 25)
    )
    assert row["date"] == "2025-09-20"
