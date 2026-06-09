"""기존 daily_reports 의 site 공기 만회일수를 longest-pole 산식으로 제자리 교정.

배경: site recovery 가 Σ(WP recovery_days) 로 적재돼 ~30공종에서 60~98일로 과대계상됨
(2026-06-09 fix a573b2b). 코드는 고쳤지만 DB 에 박힌 옛 값은 그대로라 화면이 안 바뀜.
backfill_v2 는 LLM rationale 보존을 위해 scenarios_jsonb 를 갱신 대상에서 제외하므로
화면이 읽는 site.base_p50.recovery_days 가 안 덮어써진다.

이 스크립트는 LLM·입력파일 없이, DB 의 기존 scenarios_jsonb.by_wp (WP별 완료예정일은
원래 정확) 에 새 reconcile_site_recovery 만 다시 적용해 site.* + kpi 만 교정한다.
by_wp·rationale·기타 컬럼은 무손상.

사용:
  # 미리보기 (DB 미변경)
  python scripts/fix_site_recovery_inplace.py --all-dates --dry-run
  # 실제 적용
  python scripts/fix_site_recovery_inplace.py --all-dates
  # 윈도우 / 단일
  python scripts/fix_site_recovery_inplace.py --start-date 2025-03-01 --end-date 2025-09-30
  python scripts/fix_site_recovery_inplace.py --date 2025-04-04
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

from pipeline.agents.optimizer.view_builder import reconcile_site_recovery  # noqa: E402

DSN = os.environ.get("POSTGRES_URL") or os.environ.get("DEV_DB_URL")


def _as_obj(v):
    if v is None:
        return None
    return json.loads(v) if isinstance(v, str) else v


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--all-dates", action="store_true")
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--site", default=None)
    parser.add_argument("--dry-run", action="store_true", help="변경 미리보기만 (UPDATE 안 함)")
    args = parser.parse_args()

    if not DSN:
        raise SystemExit("POSTGRES_URL(or DEV_DB_URL) 환경변수 필요")

    where = ["dr.is_mock = false", "dr.scenarios_jsonb IS NOT NULL"]
    params: list = []
    if args.site:
        params.append(args.site)
        where.append(f"pr.site_id = ${len(params)}")
    if args.start_date and args.end_date:
        params.append(args.start_date)
        params.append(args.end_date)
        where.append(f"pr.report_date BETWEEN ${len(params)-1}::date AND ${len(params)}::date")
    elif not args.all_dates:
        params.append(args.date or "2025-09-25")
        where.append(f"pr.report_date = ${len(params)}::date")

    sql = (
        "SELECT dr.id, pr.site_id, pr.report_date, "
        "       dr.scenarios_jsonb, dr.kpi_jsonb, dr.wp_summary_jsonb "
        "FROM daily_reports dr JOIN pipeline_runs pr USING (run_id) "
        "WHERE " + " AND ".join(where) + " ORDER BY pr.report_date"
    )

    conn = await asyncpg.connect(DSN)
    n_ok = n_chg = 0
    try:
        rows = await conn.fetch(sql, *params)
        print(f"대상 row: {len(rows)}  (dry-run={args.dry_run})")
        for r in rows:
            scenarios = _as_obj(r["scenarios_jsonb"]) or {}
            kpi = _as_obj(r["kpi_jsonb"]) or {}
            wp_summary = _as_obj(r["wp_summary_jsonb"]) or []

            old_site = ((scenarios.get("site") or {}).get("base_p50") or {}).get("recovery_days")
            old_kpi = kpi.get("recovery_days")

            reconcile_site_recovery(wp_summary, kpi, scenarios)

            new_site = ((scenarios.get("site") or {}).get("base_p50") or {}).get("recovery_days")
            new_kpi = kpi.get("recovery_days")
            n_ok += 1
            if (old_site, old_kpi) != (new_site, new_kpi):
                n_chg += 1
                d = r["report_date"]
                print(f"  {d}  site {old_site}->{new_site}  kpi {old_kpi}->{new_kpi}")
                if not args.dry_run:
                    await conn.execute(
                        "UPDATE daily_reports SET scenarios_jsonb = $1::jsonb, kpi_jsonb = $2::jsonb "
                        "WHERE id = $3",
                        json.dumps(scenarios, ensure_ascii=False, default=str),
                        json.dumps(kpi, ensure_ascii=False, default=str),
                        r["id"],
                    )
        verb = "변경 예정" if args.dry_run else "변경 적용"
        print(f"\n=== 요약 === 처리 {n_ok} / {verb} {n_chg}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
