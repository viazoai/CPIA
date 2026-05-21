"""Phase 2 — mapper_activities 530일 (건축+토목) → ChromaDB daily_activities upsert.

import path (검증됨): pipeline.agents.atomizer._format_document line 69
- signature: (a: dict, date: str, perperson: float|None, productivity_pct: float|None) -> str
- backfill 모드 = perperson + productivity_pct 모두 전달 → full body 텍스트
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
from datetime import date as _date
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

from pipeline.agents.atomizer import _format_document  # noqa: E402
from pipeline.chroma_client import ChromaClient  # noqa: E402
from openai import AzureOpenAI  # noqa: E402

DSN = os.environ["POSTGRES_URL"]
CHROMA_HOST = os.environ["CHROMA_HOST"]
CHROMA_PORT = int(os.environ["CHROMA_PORT"])
AZ = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=os.environ["AZURE_OPENAI_API_VERSION"],
)
EMBED_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small-ai-board-test")
RUN_ID = "backfill_v2"


def _id_of(r: dict) -> str:
    key = f"{r['report_date']}|{r['l7_5_activity']}|{r['l6_main']}|{r['company']}|{RUN_ID}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


async def fetch_rows(conn: asyncpg.Connection, the_date) -> list[dict]:
    """건축+토목 만, distinct (date, l7_5, l6, company) — phase 2 WHERE 필터 적용.
    ma.trade IN ('건축', '토목')."""
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (pr.report_date, ma.l7_5_activity, ma.l6_main, ma.company)
               pr.report_date, ma.l7_5_activity, ma.l6_main, ma.company,
               ma.today_qty, ma.assigned_workers, ma.unit, ma.conditions,
               am.daily_qty AS master_daily_qty, am.daily_workers AS master_daily_workers
        FROM mapper_activities ma
        JOIN pipeline_runs pr USING (run_id)
        LEFT JOIN activity_master am
               ON am.site_id = pr.site_id AND am.company = ma.company
              AND am.l6_main = ma.l6_main AND am.l7_5_activity = ma.l7_5_activity
        WHERE ma.is_mock = false
          AND ma.l7_5_activity IS NOT NULL
          AND ma.trade IN ('건축', '토목')
          AND ($1::date IS NULL OR pr.report_date = $1::date)
        """,
        the_date,
    )
    return [dict(r) for r in rows]


def _compute_perperson(r: dict) -> tuple[float | None, float | None]:
    qty = float(r["today_qty"] or 0)
    workers = float(r["assigned_workers"] or 0)
    if workers == 0:
        return None, None
    pp_today = qty / workers
    m_qty = float(r["master_daily_qty"] or 0)
    m_workers = float(r["master_daily_workers"] or 0)
    if m_workers == 0 or m_qty == 0:
        return pp_today, None
    pp_master = m_qty / m_workers
    pct = pp_today / pp_master * 100 if pp_master else None
    return pp_today, pct


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--all-dates", action="store_true")
    args = ap.parse_args()
    the_date = (
        None if args.all_dates else _date.fromisoformat(args.date or "2025-09-25")
    )

    conn = await asyncpg.connect(DSN)
    try:
        rows = await fetch_rows(conn, the_date)
        print(f"fetched {len(rows)} row")
    finally:
        await conn.close()

    if not rows:
        print("no rows — exit")
        return

    chroma = ChromaClient(host=CHROMA_HOST, port=CHROMA_PORT)
    col = chroma.client.get_or_create_collection("daily_activities")

    BATCH = 64
    for i in range(0, len(rows), BATCH):
        chunk = rows[i : i + BATCH]
        ids = [_id_of(r) for r in chunk]
        docs: list[str] = []
        metas: list[dict] = []
        for r in chunk:
            date_str = r["report_date"].isoformat()
            pp_today, pct = _compute_perperson(r)
            doc = _format_document(
                {
                    "company": r["company"],
                    "l6_main": r["l6_main"],
                    "l7_5_activity": r["l7_5_activity"],
                    "today_qty": r["today_qty"],
                    "unit": r["unit"],
                    "assigned_workers": r["assigned_workers"],
                    "conditions": (r["conditions"] or "").split(",")
                    if r["conditions"]
                    else [],
                },
                date_str,
                perperson=pp_today,
                productivity_pct=pct,
            )
            docs.append(doc)
            metas.append(
                {
                    "l7_5_activity": r["l7_5_activity"],
                    "l6_main": r["l6_main"],
                    "company": r["company"],
                    "date": date_str,
                    "today_qty": float(r["today_qty"] or 0),
                    "assigned_workers": float(r["assigned_workers"] or 0),
                    "unit": r["unit"] or "",
                    "conditions": r["conditions"] or "",
                    "perperson": float(pp_today or 0),
                    "productivity_pct": float(pct or 0),
                    "run_id": RUN_ID,
                    "worker_source": "backfill_v2",
                }
            )
        embeds = AZ.embeddings.create(model=EMBED_MODEL, input=docs).data
        embeddings = [e.embedding for e in embeds]
        col.upsert(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
        print(f"  upserted {i + len(chunk)} / {len(rows)}")
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
