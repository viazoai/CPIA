"""C2 진단 — plan_total_qty 초과 row 식별. 적용은 별도 결정 (사용자 게이트).

DB 변경 0. SELECT 후 over-plan 그룹 list + ratio 출력만.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.local")

from pipeline.db import PGClient  # noqa: E402


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="m15x-ph3-ibl")
    p.add_argument("--trades", default="건축,토목")
    p.add_argument("--top", type=int, default=30, help="상위 N 그룹 출력")
    args = p.parse_args()

    trades = list(args.trades.split(","))
    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        rows = await pg._pool.fetch(
            """
            SELECT company, l6_main, unit,
                   SUM(today_qty)::float AS cum_qty,
                   MAX(plan_total_qty)::float AS plan_qty
            FROM mapper_activities ma
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id=$1 AND ma.trade = ANY($2::text[])
              AND pr.is_mock=false
            GROUP BY company, l6_main, unit
            HAVING MAX(plan_total_qty) > 0 AND SUM(today_qty) > MAX(plan_total_qty)
            ORDER BY SUM(today_qty) / NULLIF(MAX(plan_total_qty), 0) DESC
            """,
            args.site,
            trades,
        )
        print(f"\n=== C2 over-plan 진단 (site={args.site}, trades={trades}) ===\n")
        print(f"over-plan 그룹: {len(rows)}")
        if not rows:
            print("\n  (over-plan 그룹 없음)")
            return
        print(f"\n상위 {min(len(rows), args.top)}:")
        print(
            f"  {'company':<22} | {'l6_main':<22} | {'unit':<5} | {'cum_qty':>10} / {'plan_qty':>10} = {'ratio':>6}"
        )
        print(
            f"  {'-' * 22} | {'-' * 22} | {'-' * 5} | {'-' * 10} / {'-' * 10} = {'-' * 6}"
        )
        for r in rows[: args.top]:
            ratio = r["cum_qty"] / r["plan_qty"]
            company = (r["company"] or "")[:22]
            l6 = (r["l6_main"] or "")[:22]
            unit = (r["unit"] or "")[:5]
            print(
                f"  {company:<22} | {l6:<22} | {unit:<5} | {r['cum_qty']:>10.0f} / {r['plan_qty']:>10.0f} = {ratio * 100:>5.0f}%"
            )

        # 광건 수장공사 별도 분리 (시연 영향 분석 — A8 의 PG source 변경으로 우회됐는지)
        kgun_fab = [
            r
            for r in rows
            if "광건" in (r["company"] or "") and "수장" in (r["l6_main"] or "")
        ]
        if kgun_fab:
            print(
                f"\n광건 수장공사 over-plan: {len(kgun_fab)} 그룹 (시연 화면 영향 주체 — A8 우회 확인 필요)"
            )
        else:
            print("\n광건 수장공사: over-plan 없음 (또는 다른 trade)")

        # 시연 영향 자가 진단
        non_kgun = [
            r
            for r in rows
            if "광건" not in (r["company"] or "") or "수장" not in (r["l6_main"] or "")
        ]
        print(f"\n광건 수장 외 over-plan: {len(non_kgun)} 그룹")
        if non_kgun:
            print(
                "  -> cleanup 적용 시 이들 그룹의 시연 화면 (forecast/optimizer) 도 영향. 사용자 검토 필요."
            )
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
