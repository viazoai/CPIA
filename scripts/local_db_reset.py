"""로컬 PG TRUNCATE all + Chroma daily_activities collection delete.

Phase A 시작 시 1회 + 재 seed 전 호출. activity_master / sites 는 reset 대상 X.
"""

from __future__ import annotations

import asyncio
import sys

import asyncpg

LOCAL_PG = "postgresql://cpia:cpia@localhost:5532/cpia"
TRUNCATE_TABLES = [
    "optimizer_advice",
    "forecasts",
    "daily_reports",
    "mapped_history",
    "mapper_activities",
    "parser_activities",
    "pipeline_runs",
]


async def reset_pg() -> None:
    conn = await asyncpg.connect(LOCAL_PG)
    try:
        for tbl in TRUNCATE_TABLES:
            await conn.execute(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE;")
            print(f"  ✓ TRUNCATE {tbl}")
    finally:
        await conn.close()


def reset_chroma() -> None:
    sys.path.insert(0, "/Users/kyungseoplee/Project Agent/CPIA")
    from pipeline.chroma_client import ChromaClient

    chroma = ChromaClient(host="localhost", port=5533)
    try:
        chroma.delete_collection("daily_activities")
        print("  ✓ Chroma daily_activities collection deleted")
    except Exception as e:  # noqa: BLE001
        print(f"  · Chroma delete skipped (not exists): {type(e).__name__}: {e}")


async def main() -> None:
    print("=== 로컬 DB reset ===")
    await reset_pg()
    reset_chroma()
    print("✓ reset 완료")


if __name__ == "__main__":
    asyncio.run(main())
