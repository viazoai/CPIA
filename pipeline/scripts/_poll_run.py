"""run status 폴링 — argv[1]=run_id, argv[2]=target status (기본 waiting_hil_1).

terminal(target/completed/failed) 도달 또는 timeout 까지 status/current_node 전이를 출력.
"""

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
    target = sys.argv[2] if len(sys.argv) > 2 else "waiting_hil_1"
    max_iters = int(sys.argv[3]) if len(sys.argv) > 3 else 48  # 48 * 15s = 12min
    con = await asyncpg.connect(_load_pg_url())
    last = None
    try:
        for i in range(max_iters):
            r = await con.fetchrow(
                "SELECT status, current_node FROM pipeline_runs WHERE run_id = $1",
                run_id,
            )
            if r is None:
                print(f"[{i}] run not found")
                return
            cur = (r["status"], r["current_node"])
            if cur != last:
                print(f"[{i * 15}s] status={r['status']} current_node={r['current_node']}", flush=True)
                last = cur
            if r["status"] in (target, "completed", "failed"):
                print(f"REACHED: {r['status']} (current_node={r['current_node']})")
                return
            await asyncio.sleep(15)
        print(f"TIMEOUT after {max_iters * 15}s — last status={last}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
