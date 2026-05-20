"""resolve_wa 7 단계 unit test — mapping-layer.md + spec §3.3 (2026-05-20 refactor).

7 단계:
  0. cand_pool 빈 → auto_chroma_top1 (chosen_wa 그대로)
  1. (신규 fix C) auto_bp_zone_match — activity.bp_code 일치 BPSummary.zone deterministic
  2. (신규 옵션 A) auto_llm_rerank — chosen_wa ∈ cand_pool 채택
  3. auto_bp_single — cand_pool wa 단일
  4. auto_l6_single — l6_choice 의 cand wa 단일
  5. auto_sheet1_text — 회사 단위 zones_in_sheet1 ∩ cand_wa_at_l6 단일
  6. hil_required — 위 모두 fail
"""

from __future__ import annotations

from pipeline.agents.mapper import resolve_wa


def _activity(
    bp_code: str | None = None,
    company: str = "남웅건설",
    work_content: str = "철근 배근",
    trade: str = "건축",
) -> dict:
    return {
        "company": company,
        "bp_code": bp_code,
        "work_content": work_content,
        "trade": trade,
        "zone": None,
        "scope": None,
        "unit": "ton",
        "today_qty": 0.0,
        "plan_total_qty": None,
        "yesterday_cum_qty": None,
        "today_cum_qty": None,
    }


def _parsed_with_bp_summary(bp_code: str, zone: str | None, company: str = "남웅건설") -> dict:
    return {
        "bp_summaries": [
            {"bp_code": bp_code, "company": company, "zone": zone},
        ],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }


def test_auto_chroma_top1_when_pool_empty():
    """0단계 — cand_pool 빈 시 chosen_wa 그대로."""
    r = resolve_wa(
        _activity(),
        l6_choice="철근콘크리트공사",
        cand_pool=[],
        parsed_report=None,
        chosen_wa="FAB",
    )
    assert r.value == "FAB"
    assert r.source == "auto_chroma_top1"


def test_auto_bp_zone_match_deterministic_overrides_llm():
    """1단계 (fix C) — activity.bp_code 일치 BPSummary.zone 우선. LLM 가 잘못 골랐어도 무시."""
    parsed = _parsed_with_bp_summary("PH_X-001", "FAB")
    r = resolve_wa(
        _activity(bp_code="PH_X-001"),
        l6_choice="철근콘크리트공사",
        cand_pool=[("FAB", "철근콘크리트공사"), ("CUB", "철근콘크리트공사")],
        parsed_report=parsed,
        chosen_wa="CUB",  # LLM 가 잘못 골랐어도
    )
    assert r.value == "FAB"
    assert r.source == "auto_bp_zone_match"


def test_auto_bp_zone_match_skipped_when_no_bp_code():
    """activity.bp_code 가 None 이면 fix C 무력화 — 다음 단계로."""
    parsed = _parsed_with_bp_summary("PH_X-001", "FAB")
    r = resolve_wa(
        _activity(bp_code=None),
        l6_choice="철근콘크리트공사",
        cand_pool=[("FAB", "철근콘크리트공사"), ("CUB", "철근콘크리트공사")],
        parsed_report=parsed,
        chosen_wa="FAB",
    )
    assert r.source != "auto_bp_zone_match"


def test_auto_bp_zone_match_skipped_when_zone_none():
    """BPSummary.zone=None (모호) → fix C 무력화 → llm_rerank 로 fallback."""
    parsed = _parsed_with_bp_summary("PH_X-001", None)
    r = resolve_wa(
        _activity(bp_code="PH_X-001"),
        l6_choice="철근콘크리트공사",
        cand_pool=[("FAB", "철근콘크리트공사"), ("CUB", "철근콘크리트공사")],
        parsed_report=parsed,
        chosen_wa="FAB",
    )
    assert r.value == "FAB"
    assert r.source == "auto_llm_rerank"


def test_auto_llm_rerank_fallback():
    """2단계 (옵션 A) — BP-zone 매칭 없으면 LLM chosen_wa ∈ cand_pool 채택."""
    r = resolve_wa(
        _activity(bp_code="PH_X-001"),
        l6_choice="철근콘크리트공사",
        cand_pool=[("FAB", "철근콘크리트공사"), ("CUB", "철근콘크리트공사")],
        parsed_report=None,  # bp_summaries 없음
        chosen_wa="CUB",
    )
    assert r.value == "CUB"
    assert r.source == "auto_llm_rerank"


def test_auto_llm_rerank_skipped_when_chosen_not_in_pool():
    """chosen_wa 가 cand_pool 에 없으면 → 다음 단계."""
    r = resolve_wa(
        _activity(bp_code="PH_X-001"),
        l6_choice="철근콘크리트공사",
        cand_pool=[("FAB", "철근콘크리트공사")],  # single
        parsed_report=None,
        chosen_wa="XXX",  # cand_pool 외
    )
    # cand_pool 단일 wa → auto_bp_single
    assert r.value == "FAB"
    assert r.source == "auto_bp_single"


def test_auto_bp_single():
    """3단계 — cand_pool wa 단일."""
    r = resolve_wa(
        _activity(bp_code="PH_X-041"),
        l6_choice="ACID배기설비공사",
        cand_pool=[("FAB", "ACID배기설비공사"), ("FAB", "ALKALI배기설비공사")],
        parsed_report=None,
        chosen_wa=None,
    )
    assert r.value == "FAB"
    assert r.source == "auto_bp_single"


def test_auto_l6_single():
    """4단계 — L6 결정 후 cand_pool wa 단일 (l6_choice 매칭)."""
    r = resolve_wa(
        _activity(bp_code="PH_X-X"),
        l6_choice="특정L6",
        cand_pool=[("FAB", "특정L6"), ("CUB", "다른L6")],
        parsed_report=None,
        chosen_wa=None,
    )
    assert r.value == "FAB"
    assert r.source == "auto_l6_single"


def test_auto_sheet1_text_legacy():
    """5단계 — 회사 단위 zones_in_sheet1 ∩ cand_wa_at_l6 단일."""
    parsed = {
        "bp_summaries": [
            {"bp_code": "PH_X-A", "company": "남웅건설", "zone": "FAB"},
            {"bp_code": "PH_X-B", "company": "남웅건설", "zone": "FAB"},  # 모두 FAB
        ],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }
    r = resolve_wa(
        _activity(bp_code="PH_X-Z"),  # bp_code 매칭 안 됨 — fix C skip
        l6_choice="철근콘크리트공사",
        cand_pool=[("FAB", "철근콘크리트공사"), ("CUB", "철근콘크리트공사")],
        parsed_report=parsed,
        chosen_wa=None,  # llm_rerank skip
    )
    assert r.value == "FAB"
    assert r.source == "auto_sheet1_text"


def test_hil_required_when_all_fail():
    """6단계 — 모든 fallback fail. cand_pool 다양 + zone 정보 없음."""
    parsed = {
        "bp_summaries": [],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }
    r = resolve_wa(
        _activity(bp_code="PH_X-X"),
        l6_choice="철근콘크리트공사",
        cand_pool=[("FAB", "철근콘크리트공사"), ("CUB", "철근콘크리트공사")],
        parsed_report=parsed,
        chosen_wa=None,
    )
    assert r.value is None
    assert r.source == "hil_required"
