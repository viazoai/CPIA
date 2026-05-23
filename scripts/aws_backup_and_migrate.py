"""AWS 마이그 orchestrator — backup / reset / restore subcommand.

usage:
  python scripts/aws_backup_and_migrate.py backup    # AWS → tmp/aws-backup-*.sql + chroma snapshot
  python scripts/aws_backup_and_migrate.py reset     # AWS PG TRUNCATE all + Chroma delete (위험)
  python scripts/aws_backup_and_migrate.py restore   # 로컬 dump → AWS push
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import asyncpg

AWS_PG_HOST = "43.200.85.209"
AWS_PG_PORT = 5532
AWS_PG_USER = "cpia"
AWS_PG_PWD = "K7mP2xQ9nR4v"
AWS_PG_DB = "cpia"
AWS_CHROMA_HOST = "43.200.85.209"
AWS_CHROMA_PORT = 5533

LOCAL_PG = "postgresql://cpia:cpia@localhost:5532/cpia"
LOCAL_CHROMA_HOST = "localhost"
LOCAL_CHROMA_PORT = 5533

TS = datetime.now().strftime("%Y%m%d-%H%M%S")
BACKUP_DIR = Path("/Users/kyungseoplee/Project Agent/CPIA/tmp")
BACKUP_DIR.mkdir(exist_ok=True)

PG_DUMP_OUT = BACKUP_DIR / f"aws-backup-{TS}.sql"
CHROMA_DUMP_OUT = BACKUP_DIR / f"chroma-aws-{TS}.jsonl"
LOCAL_DUMP_OUT = BACKUP_DIR / f"local-to-aws-{TS}.sql"
LOCAL_CHROMA_DUMP_OUT = BACKUP_DIR / f"chroma-local-{TS}.jsonl"

TRUNCATE_TABLES = [
    "optimizer_advice",
    "forecasts",
    "daily_reports",
    "mapped_history",
    "mapper_activities",
    "parser_activities",
    "pipeline_runs",
]


def run(cmd: list[str], env: dict | None = None) -> None:
    """subprocess + check + print."""
    print(f"$ {' '.join(cmd)}")
    res = subprocess.run(cmd, env=env, capture_output=False, text=True)
    if res.returncode != 0:
        raise SystemExit(f"command failed (rc={res.returncode}): {cmd}")


def backup_aws() -> None:
    """AWS PG + Chroma 백업."""
    env = {**os.environ, "PGPASSWORD": AWS_PG_PWD}
    print(f"=== AWS PG dump → {PG_DUMP_OUT} ===")
    run(
        [
            "pg_dump",
            "-h",
            AWS_PG_HOST,
            "-p",
            str(AWS_PG_PORT),
            "-U",
            AWS_PG_USER,
            "-d",
            AWS_PG_DB,
            "--exclude-table=checkpoints",
            "-f",
            str(PG_DUMP_OUT),
        ],
        env=env,
    )
    print(f"=== AWS Chroma snapshot → {CHROMA_DUMP_OUT} ===")
    run(
        [
            sys.executable,
            "scripts/chroma_export.py",
            "--host",
            AWS_CHROMA_HOST,
            "--port",
            str(AWS_CHROMA_PORT),
            "--collection",
            "daily_activities",
            "--out",
            str(CHROMA_DUMP_OUT),
        ]
    )
    print("✓ backup 완료")


async def reset_aws() -> None:
    """AWS PG TRUNCATE all + Chroma daily_activities delete. ⚠ 위험.

    A.3 hotfix 의 CASCADE 부작용 회피 — sites.last_run_id FK 임시 DROP/restore.
    """
    print("⚠ AWS reset — TRUNCATE all + Chroma delete")
    pg = await asyncpg.connect(
        f"postgresql://{AWS_PG_USER}:{AWS_PG_PWD}@{AWS_PG_HOST}:{AWS_PG_PORT}/{AWS_PG_DB}"
    )
    try:
        await pg.execute(
            "ALTER TABLE sites DROP CONSTRAINT IF EXISTS sites_last_run_id_fkey;"
        )
        print("  ✓ sites_last_run_id_fkey 임시 DROP (cascade 회피)")
        for tbl in TRUNCATE_TABLES:
            await pg.execute(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE;")
            print(f"  ✓ TRUNCATE {tbl}")
        await pg.execute(
            "ALTER TABLE sites ADD CONSTRAINT sites_last_run_id_fkey "
            "FOREIGN KEY (last_run_id) REFERENCES pipeline_runs(run_id) ON DELETE SET NULL;"
        )
        print("  ✓ sites_last_run_id_fkey 복원")
    finally:
        await pg.close()
    sys.path.insert(0, "/Users/kyungseoplee/Project Agent/CPIA")
    from pipeline.chroma_client import ChromaClient

    chroma = ChromaClient(host=AWS_CHROMA_HOST, port=AWS_CHROMA_PORT)
    try:
        chroma.client.delete_collection("daily_activities")
        print("  ✓ AWS Chroma daily_activities deleted")
    except Exception as e:  # noqa: BLE001
        print(f"  · skip: {type(e).__name__}: {e}")


def restore_from_local() -> None:
    """로컬 PG/Chroma → AWS."""
    print(f"=== 로컬 PG dump → {LOCAL_DUMP_OUT} ===")
    env = {**os.environ, "PGPASSWORD": "cpia"}
    run(
        [
            "pg_dump",
            "-h",
            "localhost",
            "-p",
            "5532",
            "-U",
            "cpia",
            "-d",
            "cpia",
            "--exclude-table=checkpoints",
            "--data-only",
            "-f",
            str(LOCAL_DUMP_OUT),
        ],
        env=env,
    )
    print(f"=== AWS PG restore ← {LOCAL_DUMP_OUT} ===")
    env_aws = {**os.environ, "PGPASSWORD": AWS_PG_PWD}
    run(
        [
            "psql",
            "-h",
            AWS_PG_HOST,
            "-p",
            str(AWS_PG_PORT),
            "-U",
            AWS_PG_USER,
            "-d",
            AWS_PG_DB,
            "-f",
            str(LOCAL_DUMP_OUT),
        ],
        env=env_aws,
    )
    print(f"=== 로컬 Chroma export → {LOCAL_CHROMA_DUMP_OUT} ===")
    run(
        [
            sys.executable,
            "scripts/chroma_export.py",
            "--host",
            "localhost",
            "--port",
            "5533",
            "--collection",
            "daily_activities",
            "--out",
            str(LOCAL_CHROMA_DUMP_OUT),
        ]
    )
    print(f"=== AWS Chroma import ← {LOCAL_CHROMA_DUMP_OUT} ===")
    run(
        [
            sys.executable,
            "scripts/chroma_import.py",
            "--host",
            AWS_CHROMA_HOST,
            "--port",
            str(AWS_CHROMA_PORT),
            "--collection",
            "daily_activities",
            "--in",
            str(LOCAL_CHROMA_DUMP_OUT),
        ]
    )
    print("✓ restore 완료")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["backup", "reset", "restore"])
    args = ap.parse_args()
    if args.mode == "backup":
        backup_aws()
    elif args.mode == "reset":
        asyncio.run(reset_aws())
    elif args.mode == "restore":
        restore_from_local()


if __name__ == "__main__":
    main()
