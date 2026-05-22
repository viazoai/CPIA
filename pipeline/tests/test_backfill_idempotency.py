"""B4 — _delete_previous_artifacts_statements SQL builder unit test.

실 DB 없이 SQL 시퀀스 + 인자만 검증. 진짜 멱등성은 D1 단계 실 backfill 결과.
"""

from __future__ import annotations


def test_clean_returns_ordered_statements():
    """--clean 시 cascade DELETE 4 statement 순서: advice -> forecasts -> daily_reports -> pipeline_runs."""
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT))
    from scripts.backfill_optimizer_advice_llm import _delete_previous_artifacts_statements

    stmts = _delete_previous_artifacts_statements(site_id="m15x-ph3-ibl", target_date="2025-09-22")
    assert isinstance(stmts, list) and len(stmts) == 4
    keywords_in_order = [
        "DELETE FROM optimizer_advice",
        "DELETE FROM forecasts",
        "DELETE FROM daily_reports",
        "DELETE FROM pipeline_runs",
    ]
    for (sql, params), expected_kw in zip(stmts, keywords_in_order):
        assert expected_kw in sql, sql
        # params 는 list/tuple, 두 인자 ($1=site, $2=date)
        assert "m15x-ph3-ibl" in params
        assert "2025-09-22" in params
