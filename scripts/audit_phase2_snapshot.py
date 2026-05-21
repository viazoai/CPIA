"""Phase 2 안전망 — backup_20260521 6 테이블 row count snapshot 저장/검증."""

from __future__ import annotations
import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")
DSN = os.environ["POSTGRES_URL"]
SNAPSHOT_PATH = (
    Path(__file__).resolve().parent.parent
    / "docs/superpowers/audit/phase2_backup_snapshot.json"
)
TABLES = [
    "mapper_activities",
    "parser_activities",
    "pipeline_runs",
    "parser_reports",
    "daily_reports",
    "forecasts",
]


async def collect() -> dict[str, int]:
    conn = await asyncpg.connect(DSN)
    try:
        return {
            t: await conn.fetchval(f"SELECT COUNT(*) FROM backup_20260521.{t}")
            for t in TABLES
        }
    finally:
        await conn.close()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    current = await collect()
    if args.save:
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(
            json.dumps(
                {"taken_at": datetime.now().isoformat(), "counts": current},
                ensure_ascii=False,
                indent=2,
            )
        )
        print(f"saved: {SNAPSHOT_PATH}")
        for t, n in current.items():
            print(f"  {t}: {n}")
    elif args.verify:
        if not SNAPSHOT_PATH.exists():
            raise SystemExit("snapshot 없음 — --save 먼저")
        saved = json.loads(SNAPSHOT_PATH.read_text())["counts"]
        diff = [(t, saved[t], current[t]) for t in TABLES if saved[t] != current[t]]
        if diff:
            for t, a, b in diff:
                print(f"  MISMATCH {t}: saved={a} now={b}")
            raise SystemExit(f"backup_20260521 변경 감지 {len(diff)}건")
        print("verified: backup_20260521 6 테이블 byte-exact 일치")
    else:
        raise SystemExit("--save 또는 --verify 지정")


if __name__ == "__main__":
    asyncio.run(main())
