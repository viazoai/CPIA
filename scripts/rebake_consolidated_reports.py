"""consolidated_reports 전 캐시 날짜를 현재 exporter 로 재생성 (스키마 통일).

upsert_consolidated_report 는 INSERT 시 is_mock=FALSE 기본 → 재생성 전 기존 is_mock 을
읽어 두고 UPSERT 후 복원한다. 결정론(LLM 없음) → idempotent, 재실행 안전.

  python scripts/rebake_consolidated_reports.py --dry-run        # 렌더만(쓰기 X)
  python scripts/rebake_consolidated_reports.py                  # 전체 재생성
  python scripts/rebake_consolidated_reports.py --site m15x-ph3-ibl --start 2025-09-24 --end 2025-09-25
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.agents.exporter import NoDataError, fetch_sheet_data, render_xlsx  # noqa: E402
from pipeline.db import PGClient, fetch_site_by_id, upsert_consolidated_report  # noqa: E402

log = logging.getLogger("rebake")


async def _targets(pg, site, start, end):
    # run_id 필수(NOT NULL UUID FK) → 기존 행 run_id 를 그대로 재사용해 UPSERT.
    q = "SELECT site_id, report_date, is_mock, run_id FROM consolidated_reports WHERE TRUE"
    args = []
    if site:
        args.append(site); q += f" AND site_id = ${len(args)}"
    if start:
        args.append(start); q += f" AND report_date >= ${len(args)}"
    if end:
        args.append(end); q += f" AND report_date <= ${len(args)}"
    q += " ORDER BY site_id, report_date"
    async with pg._pool.acquire() as con:
        return await con.fetch(q, *args)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site"); ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    url = os.environ["POSTGRES_URL"]
    start = date.fromisoformat(a.start) if a.start else None
    end = date.fromisoformat(a.end) if a.end else None

    pg = PGClient(url); await pg.connect()
    rows = await _targets(pg, a.site, start, end)
    log.info("대상 %d건 (dry_run=%s)", len(rows), a.dry_run)
    ok = skip = err = 0
    proj_cache = {}
    for r in rows:
        sid, d, was_mock, rid = r["site_id"], r["report_date"], r["is_mock"], r["run_id"]
        try:
            data = await fetch_sheet_data(pg, sid, d)
        except NoDataError:
            skip += 1; log.info("skip(NoData) %s %s", sid, d); continue
        if sid not in proj_cache:
            site = await fetch_site_by_id(pg, sid)
            proj_cache[sid] = (site or {}).get("name") or "CPIA"
        try:
            b = render_xlsx(data, d, project=proj_cache[sid])
        except Exception:
            err += 1; log.exception("render 실패 %s %s", sid, d); continue
        if a.dry_run:
            ok += 1; log.info("[dry] %s %s -> %d bytes (is_mock=%s 유지예정)", sid, d, len(b), was_mock); continue
        # run_id 는 기존 행 값 그대로 재사용(NOT NULL UUID FK).
        await upsert_consolidated_report(pg, site_id=sid, report_date=d, xlsx_bytes=b, run_id=rid)
        # is_mock 복원 (upsert 가 INSERT 시 FALSE 로 넣을 수 있음)
        async with pg._pool.acquire() as con:
            await con.execute(
                "UPDATE consolidated_reports SET is_mock=$3 WHERE site_id=$1 AND report_date=$2",
                sid, d, was_mock,
            )
        ok += 1; log.info("rebake %s %s -> %d bytes (is_mock=%s)", sid, d, len(b), was_mock)
    await pg.close()
    log.info("완료: ok=%d skip=%d err=%d / 대상=%d", ok, skip, err, len(rows))
    if err:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
