"""Cycle 멱등 룰 #2 — (site_id, report_date, company) 단위 cleanup.

원래 아키텍처 의도: Collector 가 메일에서 N 개 업체별 일보 풀링 → 각 cycle 진입.
같은 (site, date) 에 N cycle 발생 가능. (site, date) 단위 cleanup 이면
두 번째 cycle 이 첫 번째 회사 row 누락 — 사용자 명시 누락 방지.

해결: cleanup 키 = (site_id, report_date, company). 회사 단위 cleanup.
다른 회사 row 는 보존. 같은 회사 cycle 재실행 시 latest wins.

CASCADE 룰:
  ┌─ company 컬럼 있는 child: company 단위 DELETE (cycle 회사 보존)
  │   parser_activities / parser_job_allocations / parser_equipment_allocations
  │   mapper_activities / mapped_history / forecasts / optimizer_advice
  ├─ company 없는 child: run_id 단위 DELETE (영향받은 run 만)
  │   daily_reports (그 run 의 9 jsonb 통째 제거 — 새 cycle 의 9 jsonb 가 view source)
  └─ keep (회사 분리 불가):
      pipeline_runs / parser_reports (jsonb 통째) / mapping_corrections

Chroma daily_activities: doc_id = SHA256(date|company|l6|work_content)[:16] 결정성.
같은 (date, company, l6, work_content) 면 새 atomizer upsert 가 자동 overwrite —
PG cleanup 후 새 cycle 의 atomizer 가 같은 doc_id 적재 시 충돌 X. 별도 Chroma cleanup 불요.
단 회사 표기 변경 (정규화 변경 등) 으로 doc_id 가 달라진 경우 옛 doc 남음 — 옵션 --chroma 시 cleanup.

사용:
  # CLI — site/date/회사 list 명시
  pipeline/.venv/bin/python3 scripts/cleanup_by_companies.py m15x-ph3-ibl 2025-09-25 남웅건설 세보엠이씨 창원기전

  # CLI — 회사 list 미지정 (= 그 (site, date) 의 모든 회사 row cleanup)
  pipeline/.venv/bin/python3 scripts/cleanup_by_companies.py m15x-ph3-ibl 2025-09-25 --all

  # 함수 import (run_one_cycle.py 안)
  from scripts.cleanup_by_companies import cleanup_by_companies
  deleted = await cleanup_by_companies(pg, site_id, report_date, companies, is_mock=False)

is_mock 보호: WHERE is_mock = FALSE 강제 — mock row 보호.

dry_run=True 옵션: 실 DELETE 없이 영향 row 수만 측정.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from pipeline.db import PGClient  # noqa: E402


async def cleanup_by_companies(
    pg: PGClient,
    site_id: str,
    report_date: str | date,
    companies: list[str] | None,
    is_mock: bool = False,
    dry_run: bool = False,
    cleanup_chroma: bool = False,
) -> dict:
    """(site_id, report_date, company) 단위 cleanup.

    Args:
        pg: 열린 PGClient
        site_id: m15x-ph3-ibl 등
        report_date: YYYY-MM-DD str 또는 datetime.date
        companies: 회사 list. None 이면 그 (site, date) 의 mapper_activities 모든 회사 자동 추출
        is_mock: True 면 is_mock=TRUE row 만 cleanup (기본 FALSE — real row)
        dry_run: True 면 row 수만 측정, 실 DELETE X
        cleanup_chroma: True 면 Chroma daily_activities 도 metadata 필터로 DELETE

    Returns:
        {table_name: deleted_count, ...}
    """
    rd = report_date if isinstance(report_date, date) else _parse_date(report_date)

    # 1. companies 자동 추출 (None 인 경우)
    if companies is None:
        rows = await pg._pool.fetch(
            """
            SELECT DISTINCT ma.company
            FROM mapper_activities ma
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pr.report_date = $2
              AND ma.is_mock = $3 AND ma.company IS NOT NULL
            """,
            site_id,
            rd,
            is_mock,
        )
        companies = [r["company"] for r in rows]
        if not companies:
            return {"runs_affected": 0, "rows_deleted": {}, "companies": []}

    # 2. affected_runs = 이 (site, date, company 들) 의 영향받은 run_id
    affected_runs = await pg._pool.fetch(
        """
        SELECT DISTINCT pr.run_id
        FROM pipeline_runs pr
        WHERE pr.site_id = $1 AND pr.report_date = $2 AND pr.is_mock = $3
          AND EXISTS (
            SELECT 1 FROM mapper_activities ma
            WHERE ma.run_id = pr.run_id AND ma.company = ANY($4::text[])
              AND ma.is_mock = $3
          )
        """,
        site_id,
        rd,
        is_mock,
        companies,
    )
    run_ids = [r["run_id"] for r in affected_runs]

    if not run_ids:
        return {
            "runs_affected": 0,
            "rows_deleted": {},
            "companies": companies,
            "note": "no affected runs",
        }

    # 3. cleanup 대상 SQL list — 순서: (FK CASCADE 순서, child 먼저)
    cleanups: list[tuple[str, str, list]] = [
        # company 컬럼 있는 child — company 단위 DELETE
        (
            "optimizer_advice",
            "DELETE FROM optimizer_advice WHERE run_id = ANY($1::uuid[]) AND company = ANY($2::text[]) AND is_mock = $3",
            [run_ids, companies, is_mock],
        ),
        (
            "forecasts",
            "DELETE FROM forecasts WHERE run_id = ANY($1::uuid[]) AND company = ANY($2::text[]) AND is_mock = $3",
            [run_ids, companies, is_mock],
        ),
        (
            "mapped_history",
            "DELETE FROM mapped_history WHERE site_id = $1 AND report_date = $2 AND company = ANY($3::text[])",
            [site_id, rd, companies],
        ),
        (
            "mapper_activities",
            "DELETE FROM mapper_activities WHERE run_id = ANY($1::uuid[]) AND company = ANY($2::text[]) AND is_mock = $3",
            [run_ids, companies, is_mock],
        ),
        (
            "parser_activities",
            "DELETE FROM parser_activities WHERE run_id = ANY($1::uuid[]) AND company = ANY($2::text[]) AND is_mock = $3",
            [run_ids, companies, is_mock],
        ),
        # company 없는 child — run_id 단위
        (
            "daily_reports",
            "DELETE FROM daily_reports WHERE run_id = ANY($1::uuid[]) AND is_mock = $2",
            [run_ids, is_mock],
        ),
    ]
    # parser_job_allocations + parser_equipment_allocations: company 컬럼 있는지 확인 후 추가
    # → 위 INDEX (persistence) 표 보면 14 컬럼이라 company 가 있을 듯. 안전을 위해 schema 확인 필요.
    # 일단 run_id + company 패턴 시도. company 없으면 SQL 가 column does not exist 에러 → 그때 회수.

    deleted: dict[str, int] = {}
    if dry_run:
        for table, sql_select, args in cleanups:
            # SELECT count 로 변환
            count_sql = sql_select.replace(
                "DELETE FROM ", "SELECT COUNT(*) AS n FROM ", 1
            )
            row = await pg._pool.fetchrow(count_sql, *args)
            deleted[table] = row["n"]
    else:
        for table, sql_del, args in cleanups:
            sql_with_returning = sql_del + " RETURNING 1"
            try:
                rows = await pg._pool.fetch(sql_with_returning, *args)
                deleted[table] = len(rows)
            except Exception as e:
                deleted[table] = f"ERROR: {type(e).__name__}: {e}"

    # 4. Chroma cleanup (옵션) — daily_activities WHERE date AND company IN companies
    chroma_deleted = 0
    if cleanup_chroma and not dry_run:
        try:
            from pipeline.chroma_client import ChromaClient

            chroma_host = os.environ.get("CHROMA_HOST", "localhost")
            chroma_port = int(os.environ.get("CHROMA_PORT", "5533"))
            chroma_ssl = os.environ.get("CHROMA_SSL", "false").lower() == "true"
            chroma = ChromaClient(host=chroma_host, port=chroma_port, ssl=chroma_ssl)
            coll = chroma.get_or_create_daily_activities()
            date_str = rd.isoformat() if isinstance(rd, date) else str(rd)
            where = {
                "$and": [
                    {"date": date_str},
                    {"company": {"$in": companies}},
                ]
            }
            # delete by where
            coll.delete(where=where)
            chroma_deleted = "by_where"
        except Exception as e:
            chroma_deleted = f"ERROR: {type(e).__name__}: {e}"

    return {
        "runs_affected": len(run_ids),
        "rows_deleted": deleted,
        "companies": companies,
        "chroma_deleted": chroma_deleted if cleanup_chroma else "skipped",
    }


def _parse_date(s: str) -> date:
    from datetime import datetime

    return datetime.strptime(s, "%Y-%m-%d").date()


async def _main():
    if len(sys.argv) < 3:
        print(__doc__)
        print(
            "usage: cleanup_by_companies.py <site_id> <report_date> [<co1> <co2> ...] [--all] [--dry] [--chroma]"
        )
        sys.exit(1)

    site_id = sys.argv[1]
    report_date = sys.argv[2]
    args = sys.argv[3:]

    dry_run = "--dry" in args
    cleanup_chroma = "--chroma" in args
    use_all = "--all" in args
    args = [a for a in args if not a.startswith("--")]
    companies = None if use_all else (args if args else None)

    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        result = await cleanup_by_companies(
            pg,
            site_id,
            report_date,
            companies,
            is_mock=False,
            dry_run=dry_run,
            cleanup_chroma=cleanup_chroma,
        )
        print("\n=== cleanup_by_companies result ===")
        print(f"runs_affected: {result['runs_affected']}")
        print(
            f"companies ({len(result['companies'])}): {result['companies'][:10]}{'...' if len(result['companies']) > 10 else ''}"
        )
        print("rows_deleted:")
        for t, n in result["rows_deleted"].items():
            print(f"  {t}: {n}")
        if cleanup_chroma:
            print(f"chroma: {result['chroma_deleted']}")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(_main())
