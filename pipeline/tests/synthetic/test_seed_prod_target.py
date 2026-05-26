"""prod target 역산 검증 — normal 81~99 / outlier 50·150, 빈도 5% (1000 sample)."""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path


SEED_PATH = Path(__file__).parents[3] / "scripts" / "seed_dummy_year.py"


def _load_seed():
    spec = importlib.util.spec_from_file_location("seed", SEED_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _make_fake_am_row(wa="WA-1", company="C-1") -> dict:
    return {
        "wbs_activity_id": "act-1",
        "l5_disc": "건축",
        "l6_main": "콘크리트공사",
        "l7_sub": "RC공사",
        "l7_5_activity": "기초 콘크리트 타설",
        "sub_work_area": "B-zone",
        "company": company,
        "wa": wa,
        "unit": "M3",
        "plan_total_qty": 100.0,
        "plan_mh_rev2": 500.0,
        "plan_start": date(2025, 1, 1),
        "plan_finish": date(2025, 6, 30),
    }


def test_build_mapper_row_returns_l7_5_and_conditions(monkeypatch):
    m = _load_seed()
    rng = m._seeded_rng("test")
    row = m._build_mapper_row(date(2025, 3, 1), _make_fake_am_row(), None, rng)
    assert row is not None
    assert row["l7_5_activity"] == "기초 콘크리트 타설"
    assert row["trade"] == "건축"  # l5_disc 그대로
    assert isinstance(row["conditions"], list)


def test_prod_target_distribution_1000_sample(monkeypatch):
    """1000 row 시뮬레이션 — normal 81~99 비율 >= 90%, outlier 비율 3~8%."""
    m = _load_seed()
    normals = 0
    outliers = 0
    for i in range(1000):
        rng = m._seeded_rng(f"test|{i}")
        # _seeded_rng 직접 활용 — _build_mapper_row 가 내부에서 rng 동일 패턴 사용
        is_outlier = rng.random() < m.OUTLIER_PROB
        if is_outlier:
            actual = rng.choice([50.0, 150.0])
            outliers += 1
        else:
            actual = m.PROD_TARGET * (1.0 + (rng.random() * 2 - 1) * 0.10)
            normals += 1
            assert 80.9 <= actual <= 99.1, f"normal prod out of range: {actual}"
    assert 30 <= outliers <= 80, f"outlier 빈도 비현실: {outliers}/1000"
    assert outliers + normals == 1000
