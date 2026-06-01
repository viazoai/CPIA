"""09-25 mapper_activities trade/l5_disc 실값 + wp_summary NULL vs [] 구분 + activity_master plan."""

from __future__ import annotations

import asyncio
from datetime import date as _date
from pathlib import Path

import asyncpg


def _load_pg_url() -> str:
    root = Path(__file__).resolve().parents[2]
    for f in (root / ".env", root / ".env.local"):
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if line.startswith("POSTGRES_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("POSTGRES_URL not found")


async def main() -> None:
    con = await asyncpg.connect(_load_pg_url())
    d = _date(2025, 9, 25)
    try:
        print("=== 09-25 mapper distinct (wa, l6_main, company, trade, l5_disc) + row count ===")
        rows = await con.fetch(
            """
            SELECT ma.wa, ma.l6_main, ma.company, ma.trade, ma.l5_disc, COUNT(*) AS n,
                   COUNT(*) FILTER (WHERE ma.wa IS NULL) AS wa_null
            FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id)
            WHERE pr.report_date = $1
            GROUP BY ma.wa, ma.l6_main, ma.company, ma.trade, ma.l5_disc
            ORDER BY n DESC
            """,
            d,
        )
        for r in rows:
            print(
                f"  wa={r['wa']!r} l6={r['l6_main']!r} co={r['company']!r} "
                f"trade={r['trade']!r} l5_disc={r['l5_disc']!r} n={r['n']} wa_null={r['wa_null']}"
            )

        print("\n=== 09-25 mapper trade value distribution ===")
        trows = await con.fetch(
            """
            SELECT ma.trade, ma.l5_disc, COUNT(*) AS n
            FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id)
            WHERE pr.report_date = $1
            GROUP BY ma.trade, ma.l5_disc ORDER BY n DESC
            """,
            d,
        )
        for r in trows:
            print(f"  trade={r['trade']!r} l5_disc={r['l5_disc']!r} n={r['n']}")

        print("\n=== daily_reports 09-25: NULL vs [] 구분 ===")
        dr = await con.fetchrow(
            """
            SELECT (wp_summary_jsonb IS NULL) AS wp_null,
                   (quadrant_jsonb IS NULL) AS quad_null,
                   (contractor_bars_jsonb IS NULL) AS contr_null,
                   (trade_bars_jsonb IS NULL) AS trade_null,
                   (s_curve_jsonb IS NULL) AS scurve_null,
                   kpi_jsonb::text AS kpi_txt,
                   LEFT(optimizer_view_jsonb::text, 200) AS optview_head,
                   jsonb_typeof(optimizer_view_jsonb) AS optview_type,
                   (optimizer_view_jsonb = '{}'::jsonb) AS optview_empty
            FROM daily_reports WHERE report_date = $1
            """,
            d,
        )
        print(
            f"  wp_summary NULL? {dr['wp_null']}  quadrant NULL? {dr['quad_null']}  "
            f"contractor NULL? {dr['contr_null']}  trade NULL? {dr['trade_null']}  scurve NULL? {dr['scurve_null']}"
        )
        print(f"  kpi_jsonb = {dr['kpi_txt']}")
        print(f"  optimizer_view type={dr['optview_type']} empty={{}}? {dr['optview_empty']}")
        print(f"  optimizer_view head = {dr['optview_head']}")

        print("\n=== activity_master plan for 중원엔지니어링 NPW/PCW배관공사 (site m15x-ph3-ibl) ===")
        am = await con.fetch(
            """
            SELECT company, l6_main, l5_disc, wa, unit,
                   plan_total_qty, plan_mh_rev2, plan_wv, plan_start, plan_finish
            FROM activity_master
            WHERE site_id = 'm15x-ph3-ibl'
              AND l6_main IN ('NPW배관공사','PCW배관공사')
            ORDER BY l6_main, company
            """
        )
        if not am:
            print("  (NO activity_master rows for these l6_main)")
        for r in am:
            print(
                f"  co={r['company']!r} l6={r['l6_main']!r} l5_disc={r['l5_disc']!r} wa={r['wa']!r} "
                f"unit={r['unit']!r} qty={r['plan_total_qty']} mh={r['plan_mh_rev2']} wv={r['plan_wv']} "
                f"start={r['plan_start']} finish={r['plan_finish']}"
            )
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
