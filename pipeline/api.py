"""CPIA Pipeline FastAPI — /health + /run + /resume + /status.

Phase 4.1: 골격 + lifespan + GET /health 1개.
Phase 4.2: POST /api/runs/:run_id/hil_1/resume + lifespan graph/checkpointer 통합.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from langgraph.errors import EmptyChannelError, InvalidUpdateError
from langgraph.types import Command
from pydantic import BaseModel

from pipeline.db import PGClient
from pipeline.graph import GraphConfig, build_graph


# ---------------------------------------------------------------------------
# Pydantic 요청/응답 모델
# ---------------------------------------------------------------------------


class CorrectionItem(BaseModel):
    """HIL 1 단일 보정 항목 — wa + l6_main 둘 다 필수."""

    wa: str
    l6_main: str


class Hil1ResumeRequest(BaseModel):
    """POST /api/runs/:run_id/hil_1/resume 요청 body.

    corrections key 는 반드시 string (drift #N5 방어 — hil_1_node 에서 int(k) 변환).
    """

    corrections: dict[str, CorrectionItem]


class Hil1ResumeResponse(BaseModel):
    """resume 후 진행된 노드명."""

    next_node: str


# ---------------------------------------------------------------------------
# lifespan
# ---------------------------------------------------------------------------


def _build_prod_graph_config() -> GraphConfig:
    """환경변수 기반 prod GraphConfig.

    POSTGRES_URL / AZURE_OPENAI_* / CHROMA_HOST 등에서 각 에이전트 config 를 조립.
    각 config 의 상세 필드는 pipeline/agents/* 의 dataclass 참조.

    Q3: os.environ.get("POSTGRES_URL", "") 사용 — lifespan 이 이미 미설정 RuntimeError
    처리하므로 여기서 KeyError 를 재발생시키지 않는다.
    """
    from pipeline.agents.atomizer import AtomizerConfig
    from pipeline.agents.forecaster import ForecasterConfig
    from pipeline.agents.mapper import MapperConfig
    from pipeline.agents.optimizer.agent import OptimizerConfig
    from pipeline.agents.reporter import ReporterConfig

    postgres_url = os.environ.get("POSTGRES_URL", "")  # Q3: KeyError → lifespan 이 먼저 검사
    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    azure_api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
    azure_api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    llm_model = os.environ.get("LLM_MODEL", "gpt-5.1-chat-ai-board-test")
    embedding_model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small-ai-board-test")
    chroma_host = os.environ.get("CHROMA_HOST", "localhost")
    chroma_port = int(os.environ.get("CHROMA_PORT", "8000"))

    mapper_cfg = MapperConfig(
        postgres_url=postgres_url,
        azure_endpoint=azure_endpoint,
        azure_api_key=azure_api_key,
        azure_api_version=azure_api_version,
        llm_model=llm_model,
        embedding_model=embedding_model,
        chroma_host=chroma_host,
        chroma_port=chroma_port,
    )
    atomizer_cfg = AtomizerConfig(
        postgres_url=postgres_url,
        azure_endpoint=azure_endpoint,
        azure_api_key=azure_api_key,
        azure_api_version=azure_api_version,
        embedding_model=embedding_model,
        chroma_host=chroma_host,
        chroma_port=chroma_port,
    )
    forecaster_cfg = ForecasterConfig(
        postgres_url=postgres_url,
        azure_endpoint=azure_endpoint,
        azure_api_key=azure_api_key,
        azure_api_version=azure_api_version,
        llm_model=llm_model,
        embedding_model=embedding_model,
        chroma_host=chroma_host,
        chroma_port=chroma_port,
    )
    optimizer_cfg = OptimizerConfig(
        postgres_url=postgres_url,
        azure_endpoint=azure_endpoint,
        azure_api_key=azure_api_key,
        azure_api_version=azure_api_version,
        llm_model=llm_model,
        chroma_host=chroma_host,
        chroma_port=chroma_port,
        chroma_ssl=False,
    )
    reporter_cfg = ReporterConfig(
        postgres_url=postgres_url,
        azure_endpoint=azure_endpoint,
        azure_api_key=azure_api_key,
        azure_api_version=azure_api_version,
        llm_model=llm_model,
    )
    return GraphConfig(
        mapper=mapper_cfg,
        atomizer=atomizer_cfg,
        forecaster=forecaster_cfg,
        optimizer=optimizer_cfg,
        reporter=reporter_cfg,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — PG pool + LangGraph graph/checkpointer 초기화 및 정리.

    app.state.pg     : PGClient
    app.state.graph  : compiled LangGraph (Command resume 가능)
    app.state.cfg    : GraphConfig

    POSTGRES_URL 환경변수 필수 — 미설정 시 RuntimeError (보안 차원).
    Q3: 이 검사가 _build_prod_graph_config() 보다 먼저 실행되어
        os.environ["POSTGRES_URL"] KeyError 를 방어한다.
    """
    pg_url = os.getenv("POSTGRES_URL")
    if not pg_url:
        raise RuntimeError("POSTGRES_URL 환경변수 미설정. .env.local 또는 export 로 명시 필요.")

    # PG pool
    pg = PGClient(pg_url)
    await pg.connect()
    app.state.pg = pg

    # LangGraph graph — build_graph 내부에서 build_checkpointer() 호출
    # (CPIA_CHECKPOINTER 환경변수로 checkpointer 종류 제어)
    cfg = _build_prod_graph_config()
    graph = build_graph(cfg)
    app.state.graph = graph
    app.state.cfg = cfg

    try:
        yield
    finally:
        await pg.close()


app = FastAPI(
    title="CPIA Pipeline API",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


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


@app.post("/api/runs/{run_id}/hil_1/resume", response_model=Hil1ResumeResponse)
async def hil_1_resume(run_id: str, body: Hil1ResumeRequest) -> Hil1ResumeResponse:
    """HIL 1 interrupt 재개 — corrections 적용 후 다음 노드 반환.

    corrections key 는 string 필수 (drift #N5):
      hil_1_node 가 int(k) 변환 처리 (graph.py:128).
    mapping_corrections PG INSERT 는 hil_1_node 내부에서 자동 처리
      (graph.py:132~161) — endpoint 에서 별도 INSERT X.

    예외 분류 (Q2):
      EmptyChannelError  → 404 (thread_id 에 해당하는 checkpoint 없음)
      InvalidUpdateError → 409 (interrupt 상태 아님 — Command(resume) 부적합)
      그 외              → 500

    next_node 추출 (Q1):
      모든 *_node 함수가 current_node 키를 반환하므로 정상 경로에서는 항상 존재.
      None 인 경우(비정상) 는 명시적 500 raise — "unknown" silent fallback 제거.

    Response: {"next_node": "<resumed_node>"}
    """
    graph = app.state.graph

    # corrections dict[str, CorrectionItem] → dict[str, dict] (JSON serializable)
    corrections_payload: dict[str, dict] = {
        k: {"wa": v.wa, "l6_main": v.l6_main} for k, v in body.corrections.items()
    }

    try:
        result = await graph.ainvoke(
            Command(resume=corrections_payload),
            config={"configurable": {"thread_id": run_id}},
        )
    except EmptyChannelError as exc:
        # thread_id 에 해당하는 checkpoint 없음 → 404
        raise HTTPException(status_code=404, detail=f"run_id '{run_id}' 에 해당하는 checkpoint 없음") from exc
    except InvalidUpdateError as exc:
        # interrupt 상태가 아님 — Command(resume) 호출 부적합 → 409
        raise HTTPException(status_code=409, detail=f"graph 가 interrupt 대기 상태 아님: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"graph resume 실패: {exc}") from exc

    # Q1: current_node 가 None 이면 graph 반환 state 이상 — 명시적 500
    if not isinstance(result, dict) or result.get("current_node") is None:
        raise HTTPException(
            status_code=500,
            detail=f"graph 가 current_node 를 반환하지 않음. state keys: {list(result.keys()) if isinstance(result, dict) else type(result).__name__}",
        )

    next_node: str = result["current_node"]
    return Hil1ResumeResponse(next_node=next_node)
