"""POST /api/runs/:run_id/hil_1/resume — Phase 4.2 TDD (RED → GREEN).

테스트 전략:
- app.state.graph 를 AsyncMock 으로 교체 (PG/Chroma/Azure 미기동 환경)
- CPIA_CHECKPOINTER=memory 로 InMemorySaver 사용
- lifespan 은 POSTGRES_URL 가 필요하므로 monkeypatch 로 임시 설정
  (PGClient.connect 도 mock 해서 실 PG 연결 X)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

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
        patch("pipeline.api.PGClient", return_value=mock_pg),
        patch("pipeline.api.build_graph", return_value=MagicMock(compile=MagicMock(return_value=mock_graph))),
        patch("pipeline.api.build_checkpointer", return_value=MagicMock()),
    ):
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
# 테스트 2: corrections key 가 int → 422 Unprocessable Entity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hil1_resume_rejects_int_key(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """corrections key 가 int 인 경우 422 또는 400 에러 반환 (drift #N5 방어).

    JSON 은 항상 string key 만 허용 — dict[str, ...] pydantic 모델로 강제.
    JSON 스펙 상 int key 는 파이썬 json.loads 에서 string 으로 변환되므로
    실제로는 payload 구조 이상(중첩 누락 등)이 422 유발.
    여기서는 corrections 내부 value 구조가 틀린 경우를 edge case 로 검증.
    """
    run_id = str(uuid.uuid4())
    # wa / l6_main 키 누락 → Pydantic validation error → 422
    bad_corrections = {"0": {"wrong_key": "X"}}

    with (
        patch("pipeline.api.PGClient", return_value=mock_pg),
        patch("pipeline.api.build_graph", return_value=MagicMock(compile=MagicMock(return_value=mock_graph))),
        patch("pipeline.api.build_checkpointer", return_value=MagicMock()),
    ):
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
        patch("pipeline.api.PGClient", return_value=mock_pg),
        patch("pipeline.api.build_graph", return_value=MagicMock(compile=MagicMock(return_value=mock_graph))),
        patch("pipeline.api.build_checkpointer", return_value=MagicMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                f"/api/runs/{run_id}/hil_1/resume",
                json={"corrections": corrections},
            )

    # ainvoke 호출 여부 + config 인자 확인
    mock_graph.ainvoke.assert_called_once()
    call_kwargs = mock_graph.ainvoke.call_args
    # 두 번째 positional 또는 config 키워드 인자
    config = call_kwargs.kwargs.get("config") or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
    assert config is not None
    assert config["configurable"]["thread_id"] == run_id
