"""retrieve.py incident keyword 9종 매칭 검증 (spec §6)."""

from __future__ import annotations

from pipeline.agents.optimizer import retrieve


def test_incident_keywords_9_set():
    """9 keyword 모두 INCIDENT_KEYWORDS 에 있어야."""
    expected = {
        "장비대기",
        "자재미입고",
        "돌관",
        "우천",
        "야간연장",
        "인력부족",
        "재작업",
        "병행작업",
        "사양변경",
    }
    actual = getattr(retrieve, "INCIDENT_KEYWORDS", None)
    assert actual is not None, "INCIDENT_KEYWORDS 가 retrieve.py module level 에 없음"
    assert set(actual) == expected, f"keyword set 불일치: {set(actual) ^ expected}"


def test_incident_substring_matching_new_keywords():
    """새 4 keyword (인력부족·재작업·병행작업·사양변경) substring 매칭."""
    incident_kw = getattr(retrieve, "INCIDENT_KEYWORDS", None)
    assert incident_kw is not None
    for new_kw in ["인력부족", "재작업", "병행작업", "사양변경"]:
        conditions_raw = f"우천,{new_kw}"
        assert any(kw in conditions_raw for kw in incident_kw), f"{new_kw} 가 9 kw set 중 매칭 안 됨"
