"""seed _pick_diagnosis tag → conditions 매핑 검증.
spec §5 / §13.3.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


SEED_PATH = Path(__file__).parents[3] / "scripts" / "seed_dummy_year.py"


def _load_seed():
    spec = importlib.util.spec_from_file_location("seed", SEED_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_tag_to_conds_complete():
    m = _load_seed()
    assert set(m.TAG_TO_CONDS.keys()) == {
        "weather_rain",
        "manpower_short",
        "material_delay",
        "rework",
        "trade_overlap",
        "spec_change",
        "normal_steady",
    }
    assert m.TAG_TO_CONDS["normal_steady"] == ["정상"]
    assert m.TAG_TO_CONDS["weather_rain"] == ["우천"]


def test_pick_diagnosis_returns_conditions_key():
    m = _load_seed()
    diag = m._pick_diagnosis("2025-09-25", "WA-001", "광건", "콘크리트공사")
    assert "tag" in diag
    assert "conditions" in diag
    assert isinstance(diag["conditions"], list)
    assert diag["conditions"] == m.TAG_TO_CONDS[diag["tag"]]


def test_pick_diagnosis_deterministic():
    """같은 입력 → 같은 tag."""
    m = _load_seed()
    a = m._pick_diagnosis("2025-09-25", "WA-001", "광건", "콘크리트공사")
    b = m._pick_diagnosis("2025-09-25", "WA-001", "광건", "콘크리트공사")
    assert a["tag"] == b["tag"]
    assert a["conditions"] == b["conditions"]
