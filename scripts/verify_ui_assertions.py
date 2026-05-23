"""Phase D UI 검증 — SQL assertion 8건 자동 실행.

spec §15.1 — site_summary NULL=0 / quadrant∩by_wp≥99% / degradation 4필드≥90% /
delay 음양 각≥1 / F3 S-curve≥95% / conditions tag≥5 / productivity median 80-100 /
outlier 2-10%.

스키마 조정 (2026-05-23):
  - daily_report_views_v2 없음 → daily_reports 직접 조회
  - optimizer_advice.quadrant/by_wp 없음 → daily_reports.quadrant_jsonb/wp_summary_jsonb
  - mapper_activities.conditions 는 jsonb 배열 → jsonb_array_elements unnest
"""

from __future__ import annotations

import asyncio
from datetime import date

import asyncpg

LOCAL_PG = "postgresql://cpia:cpia@localhost:5532/cpia"
SITE = "m15x-ph3-ibl"


async def run_check(
    pg, label: str, sql: str, params: tuple, predicate, expected: str
) -> bool:
    val = await pg.fetchval(sql, *params)
    ok = predicate(val)
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}: {val} (기대: {expected})")
    return ok


async def main(report_date: date = date(2025, 9, 25)) -> None:
    pg = await asyncpg.connect(LOCAL_PG)
    print(f"=== UI assertion 8건 — site={SITE}, date={report_date} ===")
    results = []

    # 1. site_summary (report_md) NULL=0
    # daily_report_views_v2 없음 → daily_reports.report_md 로 대체
    results.append(
        await run_check(
            pg,
            "site_summary NULL=0",
            """SELECT COUNT(*) FROM daily_reports dr
           JOIN pipeline_runs pr ON dr.run_id = pr.run_id
           WHERE pr.site_id=$1 AND pr.report_date=$2 AND dr.report_md IS NULL""",
            (SITE, report_date),
            lambda v: v == 0,
            "=0",
        )
    )

    # 2. quadrant ↔ by_wp wp_id 교집합 — wp_summary_jsonb 기준 ∩ quadrant_jsonb 비율
    # optimizer_advice.quadrant/by_wp 없음 → daily_reports.quadrant_jsonb/wp_summary_jsonb
    results.append(
        await run_check(
            pg,
            "quadrant ↔ by_wp ≥99%",
            """WITH q AS (
             SELECT DISTINCT qrow->>'wp_id' AS wp_id
             FROM daily_reports dr
             JOIN pipeline_runs pr ON dr.run_id = pr.run_id,
                  jsonb_array_elements(dr.quadrant_jsonb) qrow
             WHERE pr.site_id=$1 AND pr.report_date=$2
               AND qrow->>'wp_id' IS NOT NULL
           ),
           w AS (
             SELECT DISTINCT wrow->>'wp_id' AS wp_id
             FROM daily_reports dr
             JOIN pipeline_runs pr ON dr.run_id = pr.run_id,
                  jsonb_array_elements(dr.wp_summary_jsonb) wrow
             WHERE pr.site_id=$1 AND pr.report_date=$2
               AND wrow->>'wp_id' IS NOT NULL
           )
           SELECT 1.0 * COUNT(q.wp_id) / NULLIF(COUNT(w.wp_id), 0)
           FROM w LEFT JOIN q ON w.wp_id = q.wp_id""",
            (SITE, report_date),
            lambda v: (v or 0.0) >= 0.99,
            "≥0.99",
        )
    )

    # 3. degradation_cases 4필드 ≥ 90%
    results.append(
        await run_check(
            pg,
            "degradation 4필드 ≥ 90%",
            """SELECT 1.0 * SUM(CASE WHEN c->>'date' IS NOT NULL AND c->>'conditions' IS NOT NULL
           AND c->>'productivity' IS NOT NULL AND (c->'recovery'->>'recovery_days') IS NOT NULL
           THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)
           FROM pipeline_runs pr
           JOIN optimizer_advice oa ON oa.run_id = pr.run_id,
                jsonb_array_elements(oa.degradation_cases) c
           WHERE pr.site_id=$1 AND pr.report_date=$2""",
            (SITE, report_date),
            lambda v: (v or 0) >= 0.90,
            "≥0.90",
        )
    )

    # 4. delay 음수 ≥ 1
    results.append(
        await run_check(
            pg,
            "delay 음수≥1",
            """SELECT SUM(CASE WHEN delay_days < 0 THEN 1 ELSE 0 END)
           FROM forecasts f JOIN pipeline_runs pr USING (run_id)
           WHERE pr.site_id=$1 AND pr.report_date=$2 AND delay_days IS NOT NULL""",
            (SITE, report_date),
            lambda v: (v or 0) >= 1,
            "≥1 (음수)",
        )
    )

    # 5. delay 양수 ≥ 1
    results.append(
        await run_check(
            pg,
            "delay 양수≥1",
            """SELECT SUM(CASE WHEN delay_days > 0 THEN 1 ELSE 0 END)
           FROM forecasts f JOIN pipeline_runs pr USING (run_id)
           WHERE pr.site_id=$1 AND pr.report_date=$2 AND delay_days IS NOT NULL""",
            (SITE, report_date),
            lambda v: (v or 0) >= 1,
            "≥1 (양수)",
        )
    )

    # 6. F3 S-curve (완공 row today_cum_qty / plan_total_qty ≥ 0.95)
    results.append(
        await run_check(
            pg,
            "F3 완공 row cum_qty/plan ≥ 0.95",
            """SELECT MAX(today_cum_qty / NULLIF(plan_total_qty, 0)) FROM mapper_activities
           WHERE report_date=$1 AND plan_total_qty > 0""",
            (report_date,),
            lambda v: (v or 0) >= 0.95,
            "≥0.95",
        )
    )

    # 7. conditions tag ≥ 5종 발현
    # mapper_activities.conditions 는 jsonb 배열 → unnest 후 DISTINCT
    results.append(
        await run_check(
            pg,
            "conditions tag 다양성 ≥5",
            """SELECT COUNT(DISTINCT tag) FROM (
             SELECT jsonb_array_elements_text(conditions) AS tag
             FROM mapper_activities
             WHERE report_date=$1 AND conditions IS NOT NULL AND conditions != '[]'
           ) sub""",
            (report_date,),
            lambda v: (v or 0) >= 5,
            "≥5",
        )
    )

    # 8. productivity median 80~100
    results.append(
        await run_check(
            pg,
            "prod median 80~100",
            """SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY today_productivity)
           FROM forecasts f JOIN pipeline_runs pr USING (run_id)
           WHERE pr.site_id=$1 AND pr.report_date=$2 AND today_productivity > 0""",
            (SITE, report_date),
            lambda v: v is not None and 80 <= v <= 100,
            "80~100",
        )
    )

    # 9. outlier 빈도 2~10%
    results.append(
        await run_check(
            pg,
            "outlier 빈도 2~10%",
            """SELECT 1.0 * SUM(CASE WHEN today_productivity < 60 OR today_productivity > 130
           THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)
           FROM forecasts f JOIN pipeline_runs pr USING (run_id)
           WHERE pr.site_id=$1 AND pr.report_date=$2""",
            (SITE, report_date),
            lambda v: v is not None and 0.02 <= v <= 0.10,
            "0.02~0.10",
        )
    )

    n_pass = sum(results)
    print(
        f"\n전체: {n_pass}/{len(results)} {'PASS' if n_pass == len(results) else 'FAIL'}"
    )
    await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
