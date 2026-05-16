"""Master List xlsx 파싱 단위 테스트.

`scripts/load_master_list.py` 의 순수 함수 (parse_master_groups, make_doc_text)
검증. PG·Chroma·Azure 의존 없음 — Task 5 통합 테스트에서 실 적재 검증.
"""

from __future__ import annotations

from pathlib import Path

from scripts.load_master_list import make_doc_text, parse_master_groups


def test_parse_master_groups(sample_wbs_path: Path):
    groups = parse_master_groups(sample_wbs_path)
    assert len(groups) >= 100  # spec 기준 102 그룹 근처

    key = ("CUB", "철근콘크리트공사")
    assert key in groups
    rows = groups[key]
    assert any(r["company"] == "남웅건설" for r in rows)


def test_make_doc_text_structure(sample_wbs_path: Path):
    groups = parse_master_groups(sample_wbs_path)
    rows = groups[("FAB", "ACID배기설비공사")]
    text = make_doc_text("FAB", "ACID배기설비공사", rows)
    assert "Work Area: FAB" in text
    assert "Work PKG-1 (L6): ACID배기설비공사" in text
    assert "Discipline (L5): 설비" in text
