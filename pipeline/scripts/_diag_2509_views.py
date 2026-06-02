"""09-25 (235ff35d) vs 09-24 적재 상태 스냅샷 — forecaster/optimizer 미표시 근본원인 추적.

읽기 전용. prod DB(.env POSTGRES_URL) 의 실제 적재값만 본다 (룰베이스/복원 없음).
"""

from __future__ import annotations

import asyncio
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
    dsn = _load_pg_url()
    con = await asyncpg.connect(dsn)
    try:
        print("=== pipeline_runs (09-24, 09-25) ===")
        rows = await con.fetch(
            """
            SELECT run_id, site_id, report_date, status, is_mock, started_at, completed_at
            FROM pipeline_runs
            WHERE report_date IN ('2025-09-24','2025-09-25')
            ORDER BY report_date, started_at
            """
        )
        for r in rows:
            print(
                f"  {r['report_date']} run={str(r['run_id'])[:8]} site={r['site_id']} "
                f"status={r['status']} is_mock={r['is_mock']} started={r['started_at']} completed={r['completed_at']}"
            )

        from datetime import date as _date

        for d_str in ("2025-09-24", "2025-09-25"):
            d = _date.fromisoformat(d_str)
            print(f"\n===== {d_str} =====")

            # mapper_activities: total + distinct (wa,l6,company) + distinct (company,l6)
            m = await con.fetchrow(
                """
                SELECT COUNT(*) AS total,
                       COUNT(DISTINCT (ma.wa, ma.l6_main, ma.company)) AS grp_wa_l6_co,
                       COUNT(DISTINCT (ma.company, ma.l6_main)) AS grp_co_l6,
                       COUNT(*) FILTER (WHERE ma.is_mock = FALSE) AS real_rows,
                       COUNT(DISTINCT (ma.wa, ma.l6_main, ma.company))
                         FILTER (WHERE ma.is_mock = FALSE) AS grp_wa_l6_co_real
                FROM mapper_activities ma
                JOIN pipeline_runs pr USING (run_id)
                WHERE pr.report_date = $1
                """,
                d,
            )
            print(
                f"  mapper: total={m['total']} real={m['real_rows']} "
                f"grp(wa,l6,co)={m['grp_wa_l6_co']} real={m['grp_wa_l6_co_real']} "
                f"grp(co,l6)={m['grp_co_l6']}"
            )

            # forecasts
            f = await con.fetchrow(
                """
                SELECT COUNT(*) AS c,
                       COUNT(*) FILTER (WHERE delay_days IS NOT NULL) AS with_delay
                FROM forecasts fc JOIN pipeline_runs pr USING (run_id)
                WHERE pr.report_date = $1
                """,
                d,
            )
            print(f"  forecasts: count={f['c']} with_delay={f['with_delay']}")
            fsample = await con.fetch(
                """
                SELECT fc.company, fc.l6_main, fc.wa, fc.delay_days, fc.risk_level
                FROM forecasts fc JOIN pipeline_runs pr USING (run_id)
                WHERE pr.report_date = $1 ORDER BY fc.delay_days DESC NULLS LAST LIMIT 6
                """,
                d,
            )
            for r in fsample:
                print(
                    f"    fc: {r['wa']} | {r['l6_main']} | {r['company']} | "
                    f"delay={r['delay_days']} risk={r['risk_level']}"
                )

            # optimizer_advice
            oa = await con.fetchrow(
                """
                SELECT COUNT(*) AS c
                FROM optimizer_advice oa JOIN pipeline_runs pr USING (run_id)
                WHERE pr.report_date = $1
                """,
                d,
            )
            print(f"  optimizer_advice: count={oa['c']}")
            oasample = await con.fetch(
                """
                SELECT oa.company, oa.l6_main
                FROM optimizer_advice oa JOIN pipeline_runs pr USING (run_id)
                WHERE pr.report_date = $1 LIMIT 6
                """,
                d,
            )
            for r in oasample:
                print(f"    oa: {r['l6_main']} | {r['company']}")

            # daily_reports jsonb 적재 상태
            dr = await con.fetchrow(
                """
                SELECT run_id, site_id, report_date,
                       jsonb_array_length(COALESCE(wp_summary_jsonb,'[]'::jsonb)) AS wp_summary_n,
                       jsonb_array_length(COALESCE(quadrant_jsonb,'[]'::jsonb)) AS quadrant_n,
                       jsonb_array_length(COALESCE(contractor_bars_jsonb,'[]'::jsonb)) AS contractor_n,
                       jsonb_array_length(COALESCE(trade_bars_jsonb,'[]'::jsonb)) AS trade_n,
                       jsonb_array_length(COALESCE(s_curve_jsonb,'[]'::jsonb)) AS scurve_n,
                       (optimizer_view_jsonb IS NOT NULL) AS has_optview,
                       (kpi_jsonb IS NOT NULL) AS has_kpi,
                       (scenarios_jsonb IS NOT NULL) AS has_scen
                FROM daily_reports
                WHERE report_date = $1
                ORDER BY report_date
                """,
                d,
            )
            if dr:
                print(
                    f"  daily_reports run={str(dr['run_id'])[:8]} site={dr['site_id']}: "
                    f"wp_summary={dr['wp_summary_n']} quadrant={dr['quadrant_n']} "
                    f"contractor={dr['contractor_n']} trade={dr['trade_n']} scurve={dr['scurve_n']} "
                    f"optview={dr['has_optview']} kpi={dr['has_kpi']} scen={dr['has_scen']}"
                )
            else:
                print("  daily_reports: NO ROW")

            # daily_reports 가 여러 run 일 수 있으니 전부
            drs = await con.fetch(
                "SELECT run_id, created_at FROM daily_reports WHERE report_date = $1",
                d,
            )
            if len(drs) != 1:
                print(f"  ⚠ daily_reports rows for {d}: {len(drs)}")
                for r in drs:
                    print(f"     run={str(r['run_id'])[:8]} created={r['created_at']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
