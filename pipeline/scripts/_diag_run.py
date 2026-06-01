"""특정 run_id 의 적재 상태 스냅샷 — argv[1]=run_id."""

from __future__ import annotations

import asyncio
import sys
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
    run_id = sys.argv[1]
    con = await asyncpg.connect(_load_pg_url())
    try:
        pr = await con.fetchrow(
            "SELECT report_date, site_id, status, atomized_count FROM pipeline_runs WHERE run_id=$1",
            run_id,
        )
        print(
            f"run={run_id[:8]} date={pr['report_date']} site={pr['site_id']} "
            f"status={pr['status']} atomized={pr['atomized_count']}"
        )

        m = await con.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE trade IN ('건축','토목')) AS gt_rows,
                   COUNT(DISTINCT (wa, l6_main, company)) AS grp,
                   COUNT(DISTINCT (wa, l6_main, company)) FILTER (WHERE trade IN ('건축','토목')) AS gt_grp
            FROM mapper_activities WHERE run_id=$1
            """,
            run_id,
        )
        print(
            f"mapper: total={m['total']} 건축토목행={m['gt_rows']} grp={m['grp']} 건축토목grp={m['gt_grp']}"
        )

        td = await con.fetch(
            "SELECT trade, COUNT(*) n FROM mapper_activities WHERE run_id=$1 GROUP BY trade ORDER BY n DESC",
            run_id,
        )
        print("  trade dist: " + ", ".join(f"{r['trade']}={r['n']}" for r in td))

        f = await con.fetchrow("SELECT COUNT(*) c FROM forecasts WHERE run_id=$1", run_id)
        oa = await con.fetchrow("SELECT COUNT(*) c FROM optimizer_advice WHERE run_id=$1", run_id)
        print(f"forecasts={f['c']} optimizer_advice={oa['c']}")

        dr = await con.fetchrow(
            """
            SELECT (wp_summary_jsonb IS NULL) AS wp_null,
                   jsonb_array_length(COALESCE(wp_summary_jsonb,'[]'::jsonb)) AS wp_n,
                   jsonb_array_length(COALESCE(quadrant_jsonb,'[]'::jsonb)) AS quad_n,
                   jsonb_array_length(COALESCE(contractor_bars_jsonb,'[]'::jsonb)) AS contr_n,
                   jsonb_array_length(COALESCE(trade_bars_jsonb,'[]'::jsonb)) AS trade_n,
                   jsonb_array_length(COALESCE(s_curve_jsonb,'[]'::jsonb)) AS sc_n,
                   (optimizer_view_jsonb = '{}'::jsonb) AS optview_empty,
                   (kpi_jsonb = '{}'::jsonb) AS kpi_empty
            FROM daily_reports WHERE run_id=$1
            """,
            run_id,
        )
        if dr:
            print(
                f"daily_reports: wp_summary={dr['wp_n']}(null={dr['wp_null']}) quadrant={dr['quad_n']} "
                f"contractor={dr['contr_n']} trade={dr['trade_n']} scurve={dr['sc_n']} "
                f"optview_empty={dr['optview_empty']} kpi_empty={dr['kpi_empty']}"
            )
        else:
            print("daily_reports: NO ROW for this run_id")

        # wp_summary 샘플 (FE Forecaster/Optimizer 카드가 읽는 것)
        sample = await con.fetch(
            """
            SELECT jsonb_array_elements(wp_summary_jsonb) AS wp
            FROM daily_reports WHERE run_id=$1
            """,
            run_id,
        )
        print(f"\nwp_summary rows ({len(sample)}):")
        import json as _json

        for s in sample[:15]:
            wp = _json.loads(s["wp"]) if isinstance(s["wp"], str) else s["wp"]
            print(
                f"  {wp.get('wp_name')} | trade={wp.get('trade')} prod={wp.get('productivity')} "
                f"impact={wp.get('impact')} status={wp.get('status')} recovery={wp.get('recovery_days')}"
            )
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
