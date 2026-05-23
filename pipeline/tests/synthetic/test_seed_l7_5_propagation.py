"""seed → mapper row → Chroma upsert metadata 까지 l7_5_activity 전파 검증."""

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


def test_mapper_row_has_l7_5_activity_field():
    """activity_master.l7_5_activity 가 mapper row 의 l7_5_activity 키로 박힘."""
    m = _load_seed()
    am_row = {
        "wbs_activity_id": "act-1",
        "l5_disc": "건축",
        "l6_main": "콘크리트공사",
        "l7_sub": "RC공사",
        "l7_5_activity": "기초 콘크리트 타설",
        "sub_work_area": "B-zone",
        "company": "광건",
        "wa": "WA-1",
        "unit": "M3",
        "plan_total_qty": 100.0,
        "plan_mh_rev2": 500.0,
        "plan_start": date(2025, 1, 1),
        "plan_finish": date(2025, 6, 30),
    }
    rng = m._seeded_rng("test")
    row = m._build_mapper_row(date(2025, 3, 1), am_row, None, rng)
    assert row["l7_5_activity"] == "기초 콘크리트 타설"


def test_chroma_metadata_includes_l7_5_and_conditions():
    """chroma_upsert_day 호출 시 metadata 에 l7_5_activity / conditions 박힘.
    실 Chroma 호출 안 함 — mapper row 가 source 임을 확인.
    """
    m = _load_seed()
    am_row = {
        "wbs_activity_id": "act-1",
        "l5_disc": "전기",
        "l6_main": "전등설비공사",
        "l7_sub": "전등설비공사",
        "l7_5_activity": "전등 설비 설치",
        "sub_work_area": "",
        "company": "태우",
        "wa": "WA-2",
        "unit": "EA",
        "plan_total_qty": 200.0,
        "plan_mh_rev2": 800.0,
        "plan_start": date(2024, 9, 1),
        "plan_finish": date(2025, 12, 31),
    }
    rng = m._seeded_rng("test2")
    row = m._build_mapper_row(date(2025, 6, 1), am_row, None, rng)
    assert row["l7_5_activity"] == "전등 설비 설치"
    assert isinstance(row["conditions"], list)
    assert row["trade"] == "전기"  # l5_disc 그대로
