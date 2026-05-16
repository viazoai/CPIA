"""Forecaster synthetic — Phase 1 더미 30일 generator.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §9

PM 원안 v2 §3-B 변동 패턴:
  weather="우천"      → today_qty × (1 - random[0.15, 0.25])
  incident="장비대기"  → today_qty × (1 - random[0.20, 0.35])
  incident="자재미입고" → today_qty × (1 - random[0.10, 0.20])
  기본 변동           → × (1 + random[-0.05, 0.05])

Chroma 적재 시 atomizer._build_metadata() 와 동일 schema 사용 (spec B-1).
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Optional


def generate_synthetic_day(
    base_row: dict,
    day_offset: int,
    weather: str,
    incident: str,
    reference_date: Optional[date] = None,
) -> dict:
    """1 row variation 생성 — atomizer schema 호환.

    base_row 는 9/25 매핑 결과 1 row.
    day_offset 은 reference_date 로부터 backward (1 = 어제).
    """
    if reference_date is None:
        reference_date = date(2025, 9, 25)

    delta = 0.0
    if weather == "우천":
        delta -= random.uniform(0.15, 0.25)
    if incident == "장비대기":
        delta -= random.uniform(0.20, 0.35)
    elif incident == "자재미입고":
        delta -= random.uniform(0.10, 0.20)
    delta += random.uniform(-0.05, 0.05)

    today_qty = base_row["today_qty"] * (1 + delta)
    conditions = [weather] + ([incident] if incident != "정상" else [])
    target_date = reference_date - timedelta(days=day_offset)

    return {
        "date": target_date.isoformat(),
        "company": base_row["company"],
        "l5_disc": base_row["l5_disc"],
        "l6_main": base_row["l6_main"],
        "wa": base_row["wa"],
        "unit": base_row["unit"],
        "today_qty": round(today_qty, 1),
        "assigned_workers": base_row["assigned_workers"],
        "worker_source": "synthetic",
        "mapping_conf": base_row.get("mapping_conf", 0.85),
        "conditions": conditions,
        "work_content": base_row["work_content"],
    }


async def _main_cli() -> None:
    """CLI entry — uv run python -m pipeline.agents.forecaster.synthetic.

    9/25 매핑 결과 (~30 unique (company, l6_main)) × 30일 = ~900 Chroma row 적재.
    atomizer 와 동일 _build_metadata 사용.
    """
    import argparse
    import hashlib
    import os

    from openai import AzureOpenAI

    from pipeline.chroma_client import ChromaClient
    from pipeline.db import PGClient

    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-date", default="2025-09-25")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    ref = date.fromisoformat(args.reference_date)

    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        rows = await pg._pool.fetch(
            """
            SELECT DISTINCT ON (company, l6_main)
                company, l6_main, l5_disc, wa, unit, plan_total_qty
            FROM activity_master
            WHERE company IS NOT NULL AND l6_main IS NOT NULL AND unit IS NOT NULL
            """
        )
    finally:
        await pg.close()

    azure = AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    )
    chroma = ChromaClient(
        host=os.environ["CHROMA_HOST"],
        port=int(os.environ.get("CHROMA_PORT", "8000")),
        ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )
    coll = chroma.get_or_create_daily_activities()

    weathers = ["맑음"] * 7 + ["우천"] * 2 + ["흐림"]
    incidents = ["정상"] * 8 + ["장비대기"] + ["자재미입고"]

    docs: list[str] = []
    metas: list[dict] = []
    ids: list[str] = []

    for r in rows:
        base_row = {
            "company": r["company"],
            "l6_main": r["l6_main"],
            "l5_disc": r["l5_disc"] or "",
            "wa": r["wa"] or "",
            "unit": r["unit"],
            "today_qty": float(r["plan_total_qty"] or 100) / max(args.days, 1),
            "assigned_workers": 50.0,
            "work_content": f"{r['l6_main']} 작업",
            "mapping_conf": 0.85,
        }
        for d in range(1, args.days + 1):
            w = random.choice(weathers)
            i = random.choice(incidents)
            row = generate_synthetic_day(base_row, day_offset=d, weather=w, incident=i, reference_date=ref)
            doc_id_raw = f"synthetic|{row['date']}|{row['company']}|{row['l6_main']}|{row['work_content']}"
            doc_id = hashlib.sha256(doc_id_raw.encode("utf-8")).hexdigest()[:16]
            ids.append(doc_id)
            docs.append(row["work_content"])
            metas.append(
                {
                    "date": row["date"],
                    "run_id": "synthetic",
                    "company": row["company"],
                    "l5_disc": row["l5_disc"],
                    "l6_main": row["l6_main"],
                    "wa": row["wa"],
                    "unit": row["unit"],
                    "today_qty": float(row["today_qty"]),
                    "assigned_workers": float(row["assigned_workers"]),
                    "worker_source": row["worker_source"],
                    "mapping_conf": float(row["mapping_conf"]),
                    "conditions": ",".join(row["conditions"]),
                }
            )

    seen: dict[str, int] = {}
    for idx, doc_id in enumerate(ids):
        seen[doc_id] = idx
    final_ids = list(seen.keys())
    final_docs = [docs[seen[i]] for i in final_ids]
    final_metas = [metas[seen[i]] for i in final_ids]

    embeddings: list[list[float]] = []
    batch = 16
    for i in range(0, len(final_docs), batch):
        chunk = final_docs[i : i + batch]
        resp = azure.embeddings.create(
            model=os.environ["EMBEDDING_MODEL"],
            input=chunk,
        )
        embeddings.extend([d.embedding for d in resp.data])

    coll.upsert(
        ids=final_ids,
        embeddings=embeddings,
        documents=final_docs,
        metadatas=final_metas,
    )

    print(f"OK upserted {len(final_ids)} rows to Chroma daily_activities.")


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main_cli())
