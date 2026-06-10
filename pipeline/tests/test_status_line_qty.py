from __future__ import annotations


def test_diag_prompt_v10_guards():
    from pipeline.agents.optimizer.prompt import DIAG_PROMPT_V10

    # 2026-06-10 (A): 전보식 1줄 → 자연 서술 2~3문장 재설계.
    assert "2~3문장" in DIAG_PROMPT_V10
    assert "서술체" in DIAG_PROMPT_V10
    assert "회복 패턴" in DIAG_PROMPT_V10  # 작성 관점 1 — 사례 흐름
    assert "한글 숫자 금지" in DIAG_PROMPT_V10


from decimal import Decimal
from pipeline.agents.optimizer.view_builder import _status_line_qty


def test_status_line_qty_basic():
    # today_qty 3.2545 → f"{:.1f}"="3.3" (3.25 정확값은 banker's rounding 으로 "3.2")
    fr = {
        "today_conditions": "자재미입고", "main_unit": "m",
        "today_qty_by_unit": {"m": 3.2545}, "plan_total_qty_by_unit": {"m": 1038.0},
        "plan_mh_sum": 52166.0, "plan_mh_per_day": 98.43,
    }
    # total_days=52166/98.43≈530 → plan_daily≈1.96 → "2.0"
    assert _status_line_qty(fr) == "자재미입고 조건 · 금일 3.3 m (계획 일평균 2.0 m)"


def test_status_line_qty_realistic_pg_types():
    """실 PG: JSONB 컬럼은 str, plan_mh_* 는 Decimal — 크래시 없이 처리."""
    fr = {
        "today_conditions": "정상", "main_unit": "m2",
        "today_qty_by_unit": '{"m2": 142.7}',          # JSONB → str
        "plan_total_qty_by_unit": '{"m2": 39202.0}',   # JSONB → str
        "plan_mh_sum": Decimal("430736"), "plan_mh_per_day": Decimal("1216.77"),
    }
    assert _status_line_qty(fr) == "정상 조건 · 금일 142.7 m2 (계획 일평균 110.7 m2)"


def test_status_line_qty_missing_plan():
    # 계획 필드 없으면 '계획 일평균 —'
    assert "계획 일평균 —" in _status_line_qty(
        {"today_conditions": "정상", "main_unit": "m2", "today_qty_by_unit": {"m2": 10.0}})


def test_status_line_qty_empty_unit_no_double_space():
    """main_unit 없으면(인원만 투입 0물량일) double-space 없이 — 경영진 UI 깨짐 방지."""
    out = _status_line_qty(
        {"today_conditions": "정상", "main_unit": None, "today_qty_by_unit": {}})
    assert "  " not in out  # double space 없음
    assert out == "정상 조건 · 금일 — (계획 일평균 —)"
