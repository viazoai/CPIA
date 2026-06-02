"""run 을 hil_1 도달까지 폴링 → 전체 승인 resume → 완주까지 → 최종 카운트.

argv[1]=run_id. resume 은 빈 corrections (매퍼 결과 그대로 = '다 승인').
prod DB 적재값만 본다 (룰베이스/복원 없음).
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.request
from pathlib import Path

import asyncpg

API = "http://localhost:8000"


def _load_pg_url() -> str:
    for f in (Path("/Users/kyungseoplee/Project Agent/CPIA/.env"),):
        for line in f.read_text().splitlines():
            if line.strip().startswith("POSTGRES_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("POSTGRES_URL not found")


async def _status(con, rid):
    return await con.fetchrow("SELECT status, current_node FROM pipeline_runs WHERE run_id=$1", rid)


async def main() -> None:
    rid = sys.argv[1]
    con = await asyncpg.connect(_load_pg_url())
    try:
        # 1) hil_1 대기까지 폴링 (최대 30분)
        last = None
        reached_hil = False
        for i in range(120):  # 120*15s = 30min
            r = await _status(con, rid)
            cur = (r["status"], r["current_node"])
            if cur != last:
                print(f"[{i * 15}s] status={r['status']} node={r['current_node']}", flush=True)
                last = cur
            if r["status"] == "waiting_hil_1":
                reached_hil = True
                break
            if r["status"] in ("completed", "failed"):
                print(f"이미 종료: {r['status']}")
                break
            await asyncio.sleep(15)
        if not reached_hil:
            r = await _status(con, rid)
            if r["status"] != "completed":
                print(f"hil_1 미도달 (현재 {r['status']}/{r['current_node']}) — 중단")
                return

        # 2) 전체 승인 resume (빈 corrections) — 블로킹 (완주까지)
        if reached_hil:
            print("→ hil_1 resume (빈 corrections = 다 승인), 완주까지 대기...", flush=True)
            req = urllib.request.Request(
                f"{API}/api/runs/{rid}/hil_1/resume",
                data=json.dumps({"corrections": {}}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=2400) as resp:
                    body = resp.read().decode()
                print(f"resume 응답: {body}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"resume 호출 예외 (백그라운드 계속될 수 있음): {e}", flush=True)

        # 3) 완주 확인
        for i in range(40):
            r = await _status(con, rid)
            if r["status"] in ("completed", "failed"):
                print(f"최종 status={r['status']} node={r['current_node']}")
                break
            await asyncio.sleep(10)

        # 4) 최종 카운트 (prod 적재값)
        mp = await con.fetchval("SELECT COUNT(*) FROM mapper_activities WHERE run_id=$1", rid)
        mgt = await con.fetchval(
            "SELECT COUNT(*) FROM mapper_activities WHERE run_id=$1 AND trade IN ('건축','토목')", rid
        )
        td = await con.fetch(
            "SELECT trade, COUNT(*) n FROM mapper_activities WHERE run_id=$1 GROUP BY trade ORDER BY n DESC",
            rid,
        )
        fc = await con.fetchval("SELECT COUNT(*) FROM forecasts WHERE run_id=$1", rid)
        oa = await con.fetchval("SELECT COUNT(*) FROM optimizer_advice WHERE run_id=$1", rid)
        dr = await con.fetchrow(
            """
            SELECT jsonb_array_length(COALESCE(wp_summary_jsonb,'[]'::jsonb)) AS wp,
                   jsonb_array_length(COALESCE(quadrant_jsonb,'[]'::jsonb)) AS quad,
                   jsonb_array_length(COALESCE(contractor_bars_jsonb,'[]'::jsonb)) AS contr,
                   jsonb_array_length(COALESCE(trade_bars_jsonb,'[]'::jsonb)) AS tr,
                   jsonb_array_length(COALESCE(s_curve_jsonb,'[]'::jsonb)) AS sc
            FROM daily_reports WHERE run_id=$1
            """,
            rid,
        )
        print("\n=== 최종 적재 (run %s) ===" % rid[:8])
        print(f"mapper_acts={mp} 건축토목={mgt}")
        print("  trade: " + ", ".join(f"{r['trade']}={r['n']}" for r in td))
        print(f"forecasts={fc} optimizer_advice={oa}")
        if dr:
            print(
                f"daily_reports: wp_summary={dr['wp']} quadrant={dr['quad']} "
                f"contractor={dr['contr']} trade_bars={dr['tr']} s_curve={dr['sc']}"
            )
        else:
            print("daily_reports: NO ROW")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
