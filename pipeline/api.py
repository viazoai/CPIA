"""CPIA Pipeline FastAPI — /health + (4.2 이후) /run, /resume, /status.

Phase 4.1: 골격 + lifespan + GET /health 1개.
Phase 4.2 이후: POST /run, POST /resume, GET /status/{run_id} 추가 예정.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from pipeline.db import PGClient

DEFAULT_PG = "postgresql://cpia:cpia@127.0.0.1:5432/cpia"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — asyncpg pool 초기화 및 정리.

    app.state.pg 에 PGClient 인스턴스를 보관한다.
    LangGraph build_graph 통합은 Phase 4.2 (Command resume 필요) 에서 진행.
    """
    pg_url = os.getenv("POSTGRES_URL", DEFAULT_PG)
    pg = PGClient(pg_url)
    await pg.connect()
    app.state.pg = pg
    try:
        yield
    finally:
        await pg.close()


app = FastAPI(
    title="CPIA Pipeline API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    """PG 연결 OK + version 확인."""
    pg: PGClient = app.state.pg
    row = await pg.fetch_one("SELECT 1 AS ok")
    return {
        "status": "ok",
        "pg": row is not None and row["ok"] == 1,
        "version": app.version,
    }
