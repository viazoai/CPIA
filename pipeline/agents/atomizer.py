"""Atomizer agent — mapped Activity[] → Chroma daily_activities 적재.

Spec: docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md §4.

LLM 없음 (Azure embedding 만). 1 mapped Activity = 1 Chroma doc.
doc_id = sha256(date|company|l6_main|work_content)[:16] (결정성 upsert).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from openai import AzureOpenAI

from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient
from pipeline.state import Activity, ParsedDailyReport


@dataclass
class AtomizerConfig:
    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    embedding_model: str
    postgres_url: str
    chroma_host: str
    chroma_port: int
    chroma_ssl: bool = False
    batch_size: int = 16
    azure_timeout: float = 30.0
    azure_max_retries: int = 3
    embedding_dim: int = 1536


def _make_doc_id(date: str, company: str, l6_main: str, work_content: str) -> str:
    """결정성 doc id — spec §4.2 (✓ Verified `73ff80435e312c41` for sample)."""
    raw = f"{date}|{company}|{l6_main}|{work_content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _build_metadata(a: Activity, date: str, run_id: str) -> dict[str, Any]:
    return {
        "date": date,
        "run_id": run_id,
        "company": a["company"],
        "l5_disc": a["l5_disc"],
        "l6_main": a["l6_main"] or "",
        "wa": a["wa"] or "",
        "unit": a["unit"],
        "today_qty": float(a["today_qty"]),
        "assigned_workers": float(a["assigned_workers"]),
        "worker_source": a["worker_source"],
        "mapping_conf": float(a["mapping_conf"] or 0.0),
        "conditions": ",".join(a["conditions"]),
    }


async def atomize(
    mapped: list[Activity],
    parsed_report: ParsedDailyReport,
    run_id: uuid.UUID,
    cfg: AtomizerConfig,
) -> list[str]:
    """mapped → Chroma daily_activities 적재. atomized_ids 반환. Spec §4.5."""
    valid = [a for a in mapped if a["l6_main"] is not None]
    if not valid:
        return []

    date = parsed_report["report_date"]

    # fail-fast: pipeline_runs row 미존재 시 Azure embedding / Chroma upsert 전 즉시 raise.
    # 같은 PG connection 을 끝까지 재사용하여 update_run_atomized_count 까지 단일 try/finally
    # 안에서 처리한다.
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        await pg.assert_pipeline_run_exists(run_id)

        azure = AzureOpenAI(
            api_key=cfg.azure_api_key,
            api_version=cfg.azure_api_version,
            azure_endpoint=cfg.azure_endpoint,
            timeout=cfg.azure_timeout,
            max_retries=cfg.azure_max_retries,
        )

        # doc_id 는 (date, company, l6_main, work_content) hash — 같은 BP사가 같은 l6 에
        # 같은 work_content 를 여러 번 적은 경우 (예: 남웅 47 row → 11 unique work_content)
        # 동일 doc_id 가 생성된다. Chroma 0.5.20 upsert/get 은 within-call 중복 id 를 거부 →
        # 단일 호출 내에서 미리 dedup (마지막 등장 metadata 채택).
        seen: dict[str, int] = {}
        for i, a in enumerate(valid):
            doc_id = _make_doc_id(date, a["company"], a["l6_main"], a["work_content"])
            seen[doc_id] = i  # 같은 id 면 뒤 index 가 덮어쓴다 (Chroma upsert semantics 와 동일).

        ids = list(seen.keys())
        documents = [valid[i]["work_content"] for i in seen.values()]
        metadatas = [_build_metadata(valid[i], date, str(run_id)) for i in seen.values()]

        embeddings: list[list[float]] = []
        for i in range(0, len(documents), cfg.batch_size):
            chunk = documents[i : i + cfg.batch_size]
            resp = azure.embeddings.create(model=cfg.embedding_model, input=chunk)
            embeddings.extend([d.embedding for d in resp.data])

        chroma = ChromaClient(host=cfg.chroma_host, port=cfg.chroma_port, ssl=cfg.chroma_ssl)
        coll = chroma.get_or_create_daily_activities()
        coll.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

        # mapped_history INSERT (wa + l6_main 둘 다 not None 활동만 — Phase 3 결정)
        # Chroma 적재 대상(valid) 은 l6_main is not None 만 — 기존 유지.
        mh_valid = [a for a in mapped if a["l6_main"] is not None and a["wa"] is not None]
        if mh_valid:
            # site_id 는 pipeline_runs 에서 조회 (atomize signature 미변경 방침)
            async with pg._pool.acquire() as _con:
                _row = await _con.fetchrow(
                    "SELECT site_id, report_date FROM pipeline_runs WHERE run_id=$1",
                    run_id,
                )
            _site_id: str = _row["site_id"] if _row else "UNKNOWN"
            _report_date = _row["report_date"] if _row else None
            mh_rows = [
                {
                    "wa": a["wa"],
                    "l6_main": a["l6_main"],
                    "company": a["company"],
                    "today_qty": a.get("today_qty"),
                    "today_assigned_workers": a.get("today_assigned_workers"),
                    "unit": a.get("unit"),
                }
                for a in mh_valid
            ]
            from datetime import date as _date_type

            _rd = (
                _report_date
                if isinstance(_report_date, _date_type)
                else (_date_type.fromisoformat(date) if _report_date is None else _report_date)
            )
            await pg.insert_mapped_history_batch(run_id, _rd, _site_id, mh_rows)

        await pg.update_run_atomized_count(run_id, len(ids))
    finally:
        await pg.close()

    return ids
