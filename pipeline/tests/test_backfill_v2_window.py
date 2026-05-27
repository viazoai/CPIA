"""Task 21 — backfill_v2 의 --start-date / --end-date 윈도우."""

from __future__ import annotations

import pathlib


def test_backfill_v2_has_window_args():
    """--start-date / --end-date argparse 옵션."""
    src = pathlib.Path("scripts/backfill_daily_report_views_v2.py").read_text(
        encoding="utf-8"
    )
    assert "--start-date" in src
    assert "--end-date" in src


def test_backfill_v2_window_uses_between():
    """SQL 에 BETWEEN $1::date AND $2::date 패턴."""
    src = pathlib.Path("scripts/backfill_daily_report_views_v2.py").read_text(
        encoding="utf-8"
    )
    assert "BETWEEN" in src
    # 윈도우 분기에 args.start_date / args.end_date 참조
    assert "args.start_date" in src
    assert "args.end_date" in src


def test_backfill_v2_jsonb_cols_still_excludes_scenarios():
    """Task 15 fix 후속: scenarios_jsonb 는 _JSONB_COLS 에서 제외 유지 (live optimize 결과 보존)."""
    src = pathlib.Path("scripts/backfill_daily_report_views_v2.py").read_text(
        encoding="utf-8"
    )
    # _JSONB_COLS tuple 안에 "scenarios_jsonb" 명시적 line 부재 (주석 OK)
    import re

    # tuple literal 안에 활성 line ("scenarios_jsonb", ) 찾기
    match = re.search(r"_JSONB_COLS\s*=\s*\(([^)]*)\)", src, re.DOTALL)
    assert match, "_JSONB_COLS tuple 파싱 실패"
    tuple_body = match.group(1)
    # 활성 line (주석 제외) 에 "scenarios_jsonb" 있으면 fail
    active_lines = [
        l.strip()
        for l in tuple_body.split("\n")
        if l.strip() and not l.strip().startswith("#")
    ]
    active_text = " ".join(active_lines)
    assert (
        '"scenarios_jsonb"' not in active_text
        and "'scenarios_jsonb'" not in active_text
    ), "scenarios_jsonb 가 _JSONB_COLS 에 다시 추가됨 — Task 15 fix 결정 위반"
