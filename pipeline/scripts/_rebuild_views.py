"""특정 run 의 optimizer view-build 만 재산출 + daily_reports upsert (전체 파이프라인 재실행 X).

agent.py:347-365 경로 재현. argv[1]=run_id, argv[2]=YYYY-MM-DD, argv[3]=site_id(기본 m15x-ph3-ibl).
view_builder.py 수정 후 기존 run 에 빠르게 반영해 Reports/대시보드 검증용.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date
from pathlib import Path

ROOT = Path("/Users/kyungseoplee/Project Agent/CPIA")
sys.path.insert(0, str(ROOT))
import os  # noqa: E402

for _l in (ROOT / ".env").read_text().splitlines():
    if "=" in _l and not _l.strip().startswith("#"):
        k, v = _l.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from pipeline.db import PGClient  # noqa: E402
from pipeline.agents.optimizer.view_builder import (  # noqa: E402
    _build_productivity_views_v2,
)


def _pg_url() -> str:
    for l in (ROOT / ".env").read_text().splitlines():
        if l.startswith("POSTGRES_URL="):
            return l.split("=", 1)[1].strip()


async def main() -> None:
    run_id = uuid.UUID(sys.argv[1])
    today = date.fromisoformat(sys.argv[2])
    site_id = sys.argv[3] if len(sys.argv) > 3 else "m15x-ph3-ibl"
    pg = PGClient(_pg_url())
    await pg.connect()
    try:
        advice_rows = await pg.fetch_all("SELECT * FROM optimizer_advice WHERE run_id=$1", run_id)
        forecast_rows = await pg.fetch_all("SELECT * FROM forecasts WHERE run_id=$1", run_id)
        v2 = await _build_productivity_views_v2(pg, site_id, today)
        cols = {
            "productivity_jsonb": v2.get("productivity", {}),
            "kpi_jsonb": v2.get("kpi", {}),
            "contractor_bars_jsonb": v2.get("contractor_bars", []),
            "trade_bars_jsonb": v2.get("trade_bars", []),
            "quadrant_jsonb": v2.get("quadrant", []),
            "wp_summary_jsonb": v2.get("wp_summary", []),
            "s_curve_jsonb": v2.get("s_curve", []),
            "optimizer_view_jsonb": v2.get("optimizer_view", {}),
            # scenarios 는 run 때 이미 빌드됨 — 재산출 불필요 (jsonb inflate 회피).
        }
        for col, val in cols.items():
            await pg.upsert_daily_report_view_col(run_id, site_id, today, col, val)
        # 요약
        def _n(x):
            return len(x) if isinstance(x, (list, dict)) else x
        print("rebuilt view cols for run", str(run_id)[:8])
        for k, v in cols.items():
            print(f"  {k}: {_n(v)}")
        # wp_summary 샘플
        ws = v2.get("wp_summary", [])
        print(f"\nwp_summary {len(ws)}건:")
        for w in ws[:8]:
            print(f"  {w.get('wp_name')} | {w.get('bp_name')} | prod={w.get('productivity')} status={w.get('status')}")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
