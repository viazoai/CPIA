"""기존 cycle 의 mapper_activities.plan_mh + cum_workers_today + cum_actual_mh_today 백필.

Phase B 의 B.1/B.2 가 신 graph 실행시만 동작 — 기존 cycle 은 NULL.
본 스크립트가 prorate 산식 (U1.B) 을 기존 row 에 UPDATE.
"""

from __future__ import annotations

import asyncio
import collections
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    url = os.environ["POSTGRES_URL"]
    con = await asyncpg.connect(url)
    try:
        runs = await con.fetch(
            """
            SELECT pr.run_id, pr.site_id, pr.report_date
            FROM pipeline_runs pr JOIN sites s ON s.site_id = pr.site_id
            WHERE s.is_mock = FALSE AND pr.status = 'completed'
            """
        )
        print(f"[mapper-backfill] {len(runs)} cycles")

        for r in runs:
            run_id = r["run_id"]
            site_id = r["site_id"]
            # 1. plan_mh 채움 (activity_master.plan_mh_rev2 by company+l6_main)
            am_rows = await con.fetch(
                """
                SELECT company, l6_main, SUM(plan_mh_rev2)::float AS mh
                FROM activity_master
                WHERE site_id = $1 AND plan_mh_rev2 IS NOT NULL
                GROUP BY company, l6_main
                """,
                site_id,
            )
            plan_mh_map = {
                (row["company"], row["l6_main"]): row["mh"] for row in am_rows
            }

            # 2. job_alloc SUM by company (final_flag='O')
            job_rows = await con.fetch(
                """
                SELECT company, SUM(COALESCE(workers_cum_t, 0))::int AS w
                FROM parser_job_allocations
                WHERE run_id = $1 AND final_flag = 'O'
                GROUP BY company
                """,
                run_id,
            )
            job_sum = {row["company"]: row["w"] for row in job_rows}

            # 3. company total plan_mh + active_l6
            ma_rows = await con.fetch(
                """
                SELECT id, company, l6_main
                FROM mapper_activities
                WHERE run_id = $1
                """,
                run_id,
            )
            company_total: dict[str, float] = collections.defaultdict(float)
            active_l6: dict[str, set] = collections.defaultdict(set)
            id_to_plan: dict[int, float] = {}
            for row in ma_rows:
                c = row["company"]
                l6 = row["l6_main"]
                pm = plan_mh_map.get((c, l6), 0.0) if c and l6 else 0.0
                id_to_plan[row["id"]] = pm
                if c and pm:
                    company_total[c] += pm
                if c and l6:
                    active_l6[c].add(l6)

            # 4. UPDATE row 별
            update_count = 0
            for row in ma_rows:
                rid = row["id"]
                c = row["company"]
                l6 = row["l6_main"]
                pm = id_to_plan[rid]
                workers_c = job_sum.get(c, 0)
                comp_mh = company_total.get(c, 0.0)
                if comp_mh > 0 and pm > 0:
                    cum_w = workers_c * (pm / comp_mh)
                elif l6 and len(active_l6[c]) > 0:
                    cum_w = workers_c / len(active_l6[c])
                else:
                    cum_w = 0.0
                cum_mh = cum_w * 8.0
                await con.execute(
                    """
                    UPDATE mapper_activities
                    SET plan_mh = $1, cum_workers_today = $2, cum_actual_mh_today = $3
                    WHERE id = $4
                    """,
                    pm or None,
                    cum_w,
                    cum_mh,
                    rid,
                )
                update_count += 1
            print(
                f"[mapper-backfill] {run_id} {site_id} {r['report_date']} updated={update_count}"
            )
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
