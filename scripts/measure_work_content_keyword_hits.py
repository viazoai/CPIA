"""C1-pre — 9/22 mapper 의 parser_activities.work_content + ma.note 에 키워드 hit 율 측정.

hit 율 >= 10% 면 C1 (parser_post _extract_conditions) 진행 게이트.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date as _date_t
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.local")

from pipeline.db import PGClient  # noqa: E402

KEYWORDS = ["장비대기", "자재미입고", "우천", "돌관", "야간연장", "흐림", "맑음"]


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="m15x-ph3-ibl")
    p.add_argument("--date", default="2025-09-22")
    p.add_argument("--trades", default="건축,토목")
    args = p.parse_args()

    # asyncpg date 파라미터는 datetime.date 객체 필요 (str 불가)
    report_date: _date_t = _date_t.fromisoformat(args.date)
    trades = tuple(args.trades.split(","))
    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        rows = await pg._pool.fetch(
            """
            SELECT COALESCE(pa.work_content, '') AS wc, COALESCE(ma.note, '') AS note
            FROM mapper_activities ma
            JOIN pipeline_runs pr USING (run_id)
            LEFT JOIN parser_activities pa
              ON pa.run_id = ma.run_id AND pa.idx = ma.idx
            WHERE pr.site_id=$1 AND pr.report_date=$2
              AND ma.trade = ANY($3::text[])
              AND pr.is_mock = false
            """,
            args.site,
            report_date,
            list(trades),
        )
        n = len(rows)
        if n == 0:
            print(f"row 0 — site={args.site} date={args.date} trades={trades}")
            return
        print(f"\ntotal rows: {n}")
        print(f"site={args.site} date={args.date} trades={trades}\n")
        for kw in KEYWORDS:
            hits = sum(1 for r in rows if kw in r["wc"] or kw in r["note"])
            pct = hits / n * 100
            print(f"  '{kw}': {hits}/{n} ({pct:.1f}%)")
        any_hit = sum(
            1 for r in rows if any(kw in r["wc"] or kw in r["note"] for kw in KEYWORDS)
        )
        any_pct = any_hit / n * 100
        print(f"\nany keyword: {any_hit}/{n} ({any_pct:.1f}%)")

        # 게이트 판단
        if any_pct >= 10:
            verdict = ">= 10% — Task 11 (C1 _extract_conditions) 진행 가능"
        elif any_pct > 0:
            verdict = "< 10% — 사용자 게이트 (키워드 확장 또는 외부 데이터 검토)"
        else:
            verdict = (
                "0% — parser 가 work_content 에 conditions 정보 미수록. T11 skip 권장."
            )
        print(f"\n게이트: {verdict}")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
