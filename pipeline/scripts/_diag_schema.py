"""스키마 introspection — pipeline_runs / daily_reports / forecasts / optimizer_advice 컬럼."""

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
    con = await asyncpg.connect(_load_pg_url())
    try:
        for t in ("pipeline_runs", "daily_reports", "forecasts", "optimizer_advice"):
            rows = await con.fetch(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = $1
                ORDER BY ordinal_position
                """,
                t,
            )
            print(f"=== {t} ===")
            print("  " + ", ".join(f"{r['column_name']}({r['data_type']})" for r in rows))
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
