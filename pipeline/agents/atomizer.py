"""Atomizer agent — mapped Activity[] → Chroma daily_activities 적재.

Spec: docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md §4.

LLM 없음 (Azure embedding 만). 1 mapped Activity = 1 Chroma doc.
doc_id = sha256(date|company|l6_main|work_content)[:16] (결정성 upsert).
"""

from __future__ import annotations

import asyncio  # noqa: F401 — used by ChromaClient init retry wrap (L110)
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
        "conditions": ",".join(a.get("conditions") or []),
    }


async def atomize(
    mapped: list[Activity],
    parsed_report: ParsedDailyReport,
    run_id: uuid.UUID,
    cfg: AtomizerConfig,
) -> list[str]:
    """mapped → Chroma daily_activities 적재. atomized_ids 반환. Spec §4.5."""
    valid = [a for a in mapped if a["l6_main"] is not None and a.get("work_content")]
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

        # 2026-05-20: ChromaClient init 의 user_identity HTTP 호출 timeout (Errno 60) 방어.
        # mapper 의 동시 init 문제와 다르게 atomizer 는 단일 호출이지만, 첫 init 의 cold start
        # latency + network 변동을 위해 3 retry + exponential backoff.
        coll = None
        _last_err: Exception | None = None
        for _attempt in range(3):
            try:
                chroma = ChromaClient(host=cfg.chroma_host, port=cfg.chroma_port, ssl=cfg.chroma_ssl)
                coll = chroma.get_or_create_daily_activities()
                break
            except Exception as _e:  # noqa: BLE001
                _last_err = _e
                if _attempt < 2:
                    await asyncio.sleep(2**_attempt)
        if coll is None:
            raise RuntimeError(f"Chroma init failed after 3 retries: {type(_last_err).__name__}: {_last_err}")
        # 2026-05-20 hang 방지: Chroma 0.5.20 batch 권장 100 doc. 1000+ doc 통째 upsert 시
        # HNSW build hang 위험 (이전 cycle 153bfa17/d38605f9 atomizer 4시간 stuck 사례).
        _CHROMA_UPSERT_BATCH = 100
        for _j in range(0, len(ids), _CHROMA_UPSERT_BATCH):
            coll.upsert(
                ids=ids[_j : _j + _CHROMA_UPSERT_BATCH],
                embeddings=embeddings[_j : _j + _CHROMA_UPSERT_BATCH],
                documents=documents[_j : _j + _CHROMA_UPSERT_BATCH],
                metadatas=metadatas[_j : _j + _CHROMA_UPSERT_BATCH],
            )

        # mapped_history INSERT (wa + l6_main 둘 다 not None 활동만 — Phase 3 결정)
        # Chroma 적재 대상(valid) 은 l6_main is not None 만 — 기존 유지.
        mh_valid = [a for a in mapped if a["l6_main"] is not None and a["wa"] is not None]
        if mh_valid:
            # site_id / report_date 는 PGClient helper 로 캡슐화 — _pool 직접 접근 제거
            run_info = await pg.get_pipeline_run(run_id)
            if run_info is None:
                raise RuntimeError(f"pipeline_runs row not found for run_id={run_id}")
            _site_id: str = run_info["site_id"]
            _rd = run_info["report_date"]  # asyncpg 가 datetime.date 로 반환 보장
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
            await pg.insert_mapped_history_batch(run_id, _rd, _site_id, mh_rows)

        await pg.update_run_atomized_count(run_id, len(ids))
    finally:
        await pg.close()

    return ids
