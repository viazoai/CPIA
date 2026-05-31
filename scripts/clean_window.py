"""clean_window — 재backfill 전 date range 의 PG + ChromaDB 완전 정리.

중복 pipeline_runs 누적 (매 backfill 새 run) + ChromaDB 옛 doc (work_content 바뀌면
doc_id 변경되어 잔존) 를 제거. 깨끗한 재seed 보장.

사용: python scripts/clean_window.py 2025-09-10 2025-09-24
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import psycopg
from chroma_client import ChromaClient

DSN = "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia"
SITE_ID = "m15x-ph3-ibl"
CHROMA_HOST, CHROMA_PORT = "43.200.85.209", 5533

# run_id FK 자식 테이블 — pipeline_runs 삭제 전 선삭제.
# checkpoint* 는 thread_id 기반 (run_id 컬럼 없음) → 제외.
_CHILD_TABLES = [
    "consolidated_reports",
    "daily_reports",
    "forecasts",
    "optimizer_advice",
    "mapper_activities",
    "parser_activities",
    "mapped_history",
]


def main(start_iso: str, end_iso: str) -> None:
    start = date.fromisoformat(start_iso)
    end = date.fromisoformat(end_iso)
    dates = [
        (start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)
    ]

    # 1. PG — run_id 수집 후 자식 → 부모 삭제. 각 DELETE 독립 (autocommit).
    conn = psycopg.connect(DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "SELECT run_id FROM pipeline_runs WHERE site_id=%s AND report_date BETWEEN %s AND %s",
            (SITE_ID, start, end),
        )
        runs = [r[0] for r in cur.fetchall()]
        print(f"PG: {len(runs)} pipeline_runs in {start}~{end}")
        if runs:
            for tbl in _CHILD_TABLES:
                try:
                    cur.execute(f"DELETE FROM {tbl} WHERE run_id = ANY(%s)", (runs,))
                    print(f"  - {tbl}: {cur.rowcount} deleted")
                except (
                    psycopg.errors.UndefinedTable,
                    psycopg.errors.UndefinedColumn,
                ) as e:
                    print(f"  - {tbl}: skip ({type(e).__name__})")
            cur.execute("DELETE FROM pipeline_runs WHERE run_id = ANY(%s)", (runs,))
            print(f"  - pipeline_runs: {cur.rowcount} deleted")
    conn.close()

    # 2. ChromaDB — date range doc 삭제 (옛 work_content doc 제거).
    col = ChromaClient(
        host=CHROMA_HOST, port=CHROMA_PORT
    ).get_or_create_daily_activities()
    before = col.count()
    col.delete(where={"date": {"$in": dates}})
    after = col.count()
    print(
        f"Chroma: {before} -> {after} ({before - after} docs deleted for {len(dates)} dates)"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python scripts/clean_window.py <start> <end>")
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])
