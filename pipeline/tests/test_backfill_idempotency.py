"""B4 — _delete_previous_artifacts_statements SQL builder unit test.

실 DB 없이 SQL 시퀀스 + 인자만 검증. 진짜 멱등성은 D1 단계 실 backfill 결과.
"""

from __future__ import annotations


def test_clean_returns_ordered_statements():
    """--clean 시 cascade DELETE 4 statement 순서: advice -> forecasts -> daily_reports -> pipeline_runs.

    str / date object 둘 다 input 으로 허용. 내부에서 date object 로 변환 (asyncpg DATE bind).
    """
    import sys
    from datetime import date
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT))
    from scripts.backfill_optimizer_advice_llm import _delete_previous_artifacts_statements

    target = date(2025, 9, 22)
    # str input 도 허용 — 변환 검증
    stmts_from_str = _delete_previous_artifacts_statements(site_id="m15x-ph3-ibl", target_date="2025-09-22")
    stmts_from_date = _delete_previous_artifacts_statements(site_id="m15x-ph3-ibl", target_date=target)

    for stmts in (stmts_from_str, stmts_from_date):
        assert isinstance(stmts, list) and len(stmts) == 4
        keywords_in_order = [
            "DELETE FROM optimizer_advice",
            "DELETE FROM forecasts",
            "DELETE FROM daily_reports",
            "DELETE FROM pipeline_runs",
        ]
        for (sql, params), expected_kw in zip(stmts, keywords_in_order):
            assert expected_kw in sql, sql
            assert "m15x-ph3-ibl" in params
            assert target in params  # date object — asyncpg 가 PG DATE 컬럼에 직접 bind
