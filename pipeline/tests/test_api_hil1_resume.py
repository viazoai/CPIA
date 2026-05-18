"""POST /api/runs/:run_id/hil_1/resume — Phase 4.2 TDD (RED → GREEN).

테스트 전략:
- lifespan 을 수동 실행 후 AsyncClient 호출 (httpx ASGITransport 는 lifespan 자동
  실행 X — lifespan_context 를 직접 제어하는 방식으로 안정적 테스트).
- app.state.graph 를 AsyncMock 으로 교체 (PG/Chroma/Azure 미기동 환경).
- CPIA_CHECKPOINTER=memory 로 InMemorySaver 사용.
- PGClient.connect/close 도 mock 해서 실 PG 연결 X.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import pipeline.api as api_module
from pipeline.api import app


# ---------------------------------------------------------------------------
# 공용 fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_memory_checkpointer(monkeypatch: pytest.MonkeyPatch) -> None:
    """테스트 중 InMemorySaver 사용 강제."""
    monkeypatch.setenv("CPIA_CHECKPOINTER", "memory")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://test:test@localhost:5432/test")


@pytest.fixture()
def mock_pg() -> MagicMock:
    """PGClient.connect / close / fetch_one 을 mock 처리."""
    pg = MagicMock()
    pg.connect = AsyncMock()
    pg.close = AsyncMock()
    pg.fetch_one = AsyncMock(return_value={"ok": 1})
    return pg


@pytest.fixture()
def mock_graph() -> MagicMock:
    """LangGraph compiled graph mock — ainvoke 가 결정론적 state dict 반환."""
    g = MagicMock()
    g.ainvoke = AsyncMock(return_value={"current_node": "atomizer"})
    return g


# ---------------------------------------------------------------------------
# 테스트 1: 정상 corrections — 200 + next_node 반환
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hil1_resume_returns_next_node(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """corrections {str→dict} 전달 시 200 + {"next_node": "<node>"} 반환."""
    run_id = str(uuid.uuid4())
    corrections = {"0": {"wa": "WA-A", "l6_main": "구조 타설"}}

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    f"/api/runs/{run_id}/hil_1/resume",
                    json={"corrections": corrections},
                )

    assert res.status_code == 200
    body = res.json()
    assert "next_node" in body
    assert isinstance(body["next_node"], str)
    assert body["next_node"] == "atomizer"


# ---------------------------------------------------------------------------
# 테스트 2: corrections value 구조 불량 (wa/l6_main 누락) → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hil1_resume_rejects_bad_correction_value(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """corrections value 에 wa/l6_main 키 누락 시 422 Unprocessable Entity.

    Pydantic CorrectionItem 검증으로 강제 — drift #N5 방어:
    JSON 스펙 상 object key 는 항상 string 이므로 int key 는 json.loads 시
    자동 string 으로 변환됨. 따라서 key 검증보다 value schema 검증이 핵심.
    """
    run_id = str(uuid.uuid4())
    # wa / l6_main 키 누락 → Pydantic validation error → 422
    bad_corrections = {"0": {"wrong_key": "X"}}

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    f"/api/runs/{run_id}/hil_1/resume",
                    json={"corrections": bad_corrections},
                )

    assert res.status_code == 422


# ---------------------------------------------------------------------------
# 테스트 3: graph.ainvoke 호출 시 thread_id = run_id 전달 확인
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hil1_resume_passes_thread_id(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """graph.ainvoke 가 config={"configurable": {"thread_id": str(run_id)}} 로 호출됨."""
    run_id = str(uuid.uuid4())
    corrections = {"1": {"wa": "WA-B", "l6_main": "방수 공사"}}

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post(
                    f"/api/runs/{run_id}/hil_1/resume",
                    json={"corrections": corrections},
                )

    # ainvoke 호출 여부 + config 인자 확인
    mock_graph.ainvoke.assert_called_once()
    call_kwargs = mock_graph.ainvoke.call_args
    # config 는 kwargs 또는 두 번째 positional
    config = call_kwargs.kwargs.get("config") or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
    assert config is not None
    assert config["configurable"]["thread_id"] == run_id
