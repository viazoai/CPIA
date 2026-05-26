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
        # sites.last_run_id → pipeline_runs FK 를 일시 DROP:
        # TRUNCATE ... CASCADE 가 sites 까지 cascade 되는 것을 차단.
        # ON DELETE SET NULL 동작은 복원 후 유지됨.
        await conn.execute(
            "ALTER TABLE sites DROP CONSTRAINT IF EXISTS sites_last_run_id_fkey;"
        )
        print("  ✓ sites_last_run_id_fkey 임시 DROP (cascade 회피)")

        tbl_list = ", ".join(TRUNCATE_TABLES)
        await conn.execute(f"TRUNCATE TABLE {tbl_list} RESTART IDENTITY CASCADE;")
        for tbl in TRUNCATE_TABLES:
            print(f"  ✓ TRUNCATE {tbl}")

        await conn.execute(
            "ALTER TABLE sites"
            " ADD CONSTRAINT sites_last_run_id_fkey"
            " FOREIGN KEY (last_run_id) REFERENCES pipeline_runs(run_id)"
            " ON DELETE SET NULL;"
        )
        print("  ✓ sites_last_run_id_fkey 복원")
    finally:
        await conn.close()


def reset_chroma() -> None:
    sys.path.insert(0, "/Users/kyungseoplee/Project Agent/CPIA")
    from pipeline.chroma_client import ChromaClient

    chroma = ChromaClient(host="localhost", port=5533)
    try:
        chroma.client.delete_collection(name="daily_activities")
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
