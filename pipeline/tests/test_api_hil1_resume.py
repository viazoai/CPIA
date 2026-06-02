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
# 테스트 1 (C5-4): 정상 corrections — 200 + {ok, run_id} 즉시 ack 반환
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hil1_resume_returns_ack(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """corrections {str→dict} 전달 시 200 + {"ok": True, "run_id": ...} ack 반환.

    C5-4: resume 는 백그라운드 실행 — 동기 next_node 반환 폐기.
    """
    import asyncio as _asyncio

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
                # 백그라운드 task 가 실행되도록 yield (cleanup 전 ainvoke 호출 보장)
                await _asyncio.sleep(0.05)

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["run_id"] == run_id
    assert "next_node" not in body


# ---------------------------------------------------------------------------
# 테스트 1b (C5-4): 즉시 반환 — 느린 ainvoke 가 끝나기 전에 200 ack 반환되고,
#                  백그라운드 task 가 스케줄돼 나중에 완료된다.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hil1_resume_returns_immediately_and_schedules_bg(mock_pg: MagicMock) -> None:
    """resume 응답이 ainvoke 완료를 기다리지 않고 즉시 반환됨 (FE 170s 타임아웃 회피)."""
    import asyncio as _asyncio

    started = _asyncio.Event()
    finished = _asyncio.Event()

    async def _slow_invoke(*a: object, **k: object) -> dict:
        started.set()
        await _asyncio.sleep(0.2)
        finished.set()
        return {"current_node": "atomizer"}

    slow_graph = MagicMock()
    slow_graph.ainvoke = _slow_invoke
    run_id = str(uuid.uuid4())
    corrections = {"0": {"wa": "WA-A", "l6_main": "구조"}}

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=slow_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    f"/api/runs/{run_id}/hil_1/resume",
                    json={"corrections": corrections},
                )
                assert res.status_code == 200
                # ainvoke 가 아직 끝나지 않았는데도 응답이 돌아왔다 = 즉시 반환
                assert finished.is_set() is False
                body = res.json()
                assert body["ok"] is True
                assert body["run_id"] == run_id
                # 백그라운드 task 는 결국 완료된다
                await _asyncio.wait_for(finished.wait(), timeout=2.0)


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
    """graph.ainvoke 가 config={"configurable": {"thread_id": str(run_id)}} 로 호출됨.

    C5-4: ainvoke 가 백그라운드 task 에서 실행되므로 assert 전 task 를 실행시킨다.
    """
    import asyncio as _asyncio

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
                # 스케줄된 백그라운드 task 가 실행되도록 yield
                await _asyncio.sleep(0.05)

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

    C5-4: ainvoke 가 백그라운드 task 에서 실행되므로 assert 전 task 를 실행시킨다.
    """
    import asyncio as _asyncio

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
                # 스케줄된 백그라운드 task 가 실행되도록 yield
                await _asyncio.sleep(0.05)

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
# 테스트 5 (C5-4): graph.ainvoke 가 EmptyChannelError (checkpoint 없음) 면
#                 백그라운드에서 set_run_status(..., "failed") 호출.
#                 동기 404 검출은 즉시반환으로 불가 — accepted tradeoff.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hil1_resume_bg_marks_failed_on_empty_channel(
    mock_pg: MagicMock,
) -> None:
    """존재하지 않는 run_id → 백그라운드 EmptyChannelError → set_run_status failed.

    C5-4: 즉시 200 ack 반환 후, 백그라운드 task 에서 예외 발생 시
    set_run_status(postgres_url, run_id, "failed") 로 마킹된다.
    """
    import asyncio as _asyncio

    failing_graph = MagicMock()
    failing_graph.ainvoke = AsyncMock(side_effect=EmptyChannelError("no checkpoint"))

    run_id = str(uuid.uuid4())
    corrections = {"0": {"wa": "WA-A", "l6_main": "구조"}}
    set_status_mock = AsyncMock()

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=failing_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
        patch.object(api_module, "set_run_status", set_status_mock),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    f"/api/runs/{run_id}/hil_1/resume",
                    json={"corrections": corrections},
                )
                # 즉시 200 ack
                assert res.status_code == 200
                # 백그라운드 task 가 실행되도록 yield
                await _asyncio.sleep(0.05)

    set_status_mock.assert_awaited_once()
    args = set_status_mock.await_args.args
    assert run_id in args
    assert "failed" in args


# ---------------------------------------------------------------------------
# 테스트 6 (C5-4): graph.ainvoke 가 InvalidUpdateError (interrupt 상태 아님) 면
#                 백그라운드에서 set_run_status(..., "failed") 호출.
#                 동기 409 검출은 즉시반환으로 불가 — accepted tradeoff.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hil1_resume_bg_marks_failed_on_invalid_update(
    mock_pg: MagicMock,
) -> None:
    """interrupt 대기 상태 아닌 graph → 백그라운드 InvalidUpdateError → failed 마킹.

    C5-4: 즉시 200 ack 반환 후, 백그라운드 예외는 set_run_status failed 처리.
    """
    import asyncio as _asyncio

    failing_graph = MagicMock()
    failing_graph.ainvoke = AsyncMock(side_effect=InvalidUpdateError("not interrupted"))

    run_id = str(uuid.uuid4())
    corrections = {"0": {"wa": "WA-A", "l6_main": "구조"}}
    set_status_mock = AsyncMock()

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=failing_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
        patch.object(api_module, "set_run_status", set_status_mock),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    f"/api/runs/{run_id}/hil_1/resume",
                    json={"corrections": corrections},
                )
                # 즉시 200 ack
                assert res.status_code == 200
                # 백그라운드 task 가 실행되도록 yield
                await _asyncio.sleep(0.05)

    set_status_mock.assert_awaited_once()
    args = set_status_mock.await_args.args
    assert run_id in args
    assert "failed" in args
