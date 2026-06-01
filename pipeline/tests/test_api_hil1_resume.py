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
from langgraph.errors import EmptyChannelError, InvalidUpdateError
from langgraph.types import Command

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


# ---------------------------------------------------------------------------
# 테스트 4 (Q4): drift #N5 — corrections string key 가 Command(resume=) 인자에
#                그대로 전달. API layer 는 int 변환 X — hil_1_node 책임.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hil1_resume_preserves_string_key_in_command_resume(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """drift #N5: JSON corrections string key 가 Command(resume=) 의 resume payload
    에 string 그대로 전달돼야 함. int 변환은 hil_1_node (graph.py:128) 책임.
    """
    run_id = str(uuid.uuid4())
    corrections = {"5": {"wa": "WA-Z", "l6_main": "전기 공사"}}

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

    # ainvoke 첫 positional 인자 = Command(resume=...)
    cmd = mock_graph.ainvoke.call_args.args[0]
    assert isinstance(cmd, Command)
    # resume 는 {"corrections": {...}} truthy 래퍼 (langgraph 1.2.0 의 falsy-resume
    # 미전달 버그 회피 — 빈 보정도 전달되게 함). hil_1_node 가 언랩.
    assert set(cmd.resume) == {"corrections"}
    inner = cmd.resume["corrections"]
    # 래퍼 내부 corrections 의 key 가 string "5" 그대로 (int 5 X) — drift #N5
    assert "5" in inner
    assert 5 not in inner
    assert all(isinstance(k, str) for k in inner.keys())


# ---------------------------------------------------------------------------
# 테스트 5 (Q1): graph.ainvoke 결과에 current_node 누락 시 500 + 상세 detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hil1_resume_500_when_current_node_missing(
    mock_pg: MagicMock,
) -> None:
    """graph 가 current_node 없는 state 반환 시 500 raise (silent "unknown" 금지)."""
    bad_graph = MagicMock()
    bad_graph.ainvoke = AsyncMock(return_value={"other_key": "value"})  # current_node 누락

    run_id = str(uuid.uuid4())
    corrections = {"0": {"wa": "WA-A", "l6_main": "구조"}}

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=bad_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    f"/api/runs/{run_id}/hil_1/resume",
                    json={"corrections": corrections},
                )

    assert res.status_code == 500
    assert "current_node" in res.json()["detail"]


# ---------------------------------------------------------------------------
# 테스트 6 (Q2-a): EmptyChannelError → 404 (run_id 없음)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hil1_resume_404_when_checkpoint_missing(
    mock_pg: MagicMock,
) -> None:
    """존재하지 않는 run_id (checkpoint 없음) → EmptyChannelError → 404."""
    failing_graph = MagicMock()
    failing_graph.ainvoke = AsyncMock(side_effect=EmptyChannelError("no checkpoint"))

    run_id = str(uuid.uuid4())
    corrections = {"0": {"wa": "WA-A", "l6_main": "구조"}}

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=failing_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    f"/api/runs/{run_id}/hil_1/resume",
                    json={"corrections": corrections},
                )

    assert res.status_code == 404
    assert run_id in res.json()["detail"]


# ---------------------------------------------------------------------------
# 테스트 7 (Q2-b): InvalidUpdateError → 409 (interrupt 상태 아님)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hil1_resume_409_when_not_in_interrupt(
    mock_pg: MagicMock,
) -> None:
    """interrupt 대기 상태 아닌 graph 에 Command(resume) → InvalidUpdateError → 409."""
    failing_graph = MagicMock()
    failing_graph.ainvoke = AsyncMock(side_effect=InvalidUpdateError("not interrupted"))

    run_id = str(uuid.uuid4())
    corrections = {"0": {"wa": "WA-A", "l6_main": "구조"}}

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=failing_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    f"/api/runs/{run_id}/hil_1/resume",
                    json={"corrections": corrections},
                )

    assert res.status_code == 409
    assert "interrupt" in res.json()["detail"]
