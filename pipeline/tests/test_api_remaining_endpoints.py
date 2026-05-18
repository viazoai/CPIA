"""GET /api/agents/status + /api/sites/:site_id/wbs_tree + /api/tasks
— Phase 4.9 + 4.10 + 4.11 TDD (RED -> GREEN).

테스트 전략:
- Phase 4.6~4.8 패턴 동일: lifespan 수동 실행 + AsyncClient(ASGITransport)
- PGClient.fetch_all / fetch_one 을 AsyncMock 으로 교체 (실 PG 연결 X)
- build_graph + _build_prod_graph_config mock (lifespan dummy graph)
- CPIA_CHECKPOINTER=memory, POSTGRES_URL=dummy
"""

from __future__ import annotations

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
    """PGClient.connect / close / fetch_one / fetch_all 을 mock 처리."""
    pg = MagicMock()
    pg.connect = AsyncMock()
    pg.close = AsyncMock()
    pg.fetch_one = AsyncMock(return_value={"ok": 1})
    pg.fetch_all = AsyncMock(return_value=[])
    return pg


@pytest.fixture()
def mock_graph() -> MagicMock:
    """LangGraph compiled graph mock."""
    g = MagicMock()
    g.ainvoke = AsyncMock(return_value={"current_node": "atomizer"})
    return g


# ---------------------------------------------------------------------------
# Phase 4.9 — GET /api/agents/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agents_status_returns_7(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """항상 7개 AgentStatus 반환 — step 1..7."""
    # active_count SQL 는 agent 별로 호출되므로 fetch_all = [] 기본값 충분
    mock_pg.fetch_all = AsyncMock(return_value=[{"count": 0}])

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/agents/status")

    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert len(body) == 7


@pytest.mark.asyncio
async def test_agents_status_shape(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """AgentStatus shape 검증 — 필수 필드 존재 + step 오름차순."""
    mock_pg.fetch_all = AsyncMock(return_value=[{"count": 0}])

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/agents/status")

    body = res.json()
    required_keys = {"step", "name", "korean_name", "description", "model", "group", "active_count", "state"}
    for item in body:
        assert required_keys <= item.keys(), f"missing keys in {item}"

    steps = [item["step"] for item in body]
    assert steps == list(range(1, 8)), f"step 순서 오류: {steps}"


@pytest.mark.asyncio
async def test_agents_status_state_processing(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """active_count > 0 이면 state='processing'."""
    # fetch_all 이 active_count=2 인 row 를 반환하도록 설정
    mock_pg.fetch_all = AsyncMock(return_value=[{"count": 2}])

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/agents/status")

    body = res.json()
    # 모든 agent 가 active_count=2 → state=processing
    for item in body:
        assert item["state"] == "processing", f"step {item['step']} state 오류: {item['state']}"
        assert item["active_count"] == 2


# ---------------------------------------------------------------------------
# Phase 4.10 — GET /api/sites/:site_id/wbs_tree
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wbs_tree_root_shape(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """DB 결과 없음 -> 루트 노드 (type=building) + 빈 children 반환."""
    mock_pg.fetch_all = AsyncMock(return_value=[])

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/sites/SITE-001/wbs_tree")

    assert res.status_code == 200
    root = res.json()
    assert root["type"] == "building"
    assert root["id"] == "SITE-001"
    assert root["parent_id"] is None
    assert isinstance(root["children"], list)


@pytest.mark.asyncio
async def test_wbs_tree_builds_hierarchy(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """l5_disc + l6_main rows -> trade/work_package 2단계 트리."""
    mock_pg.fetch_all = AsyncMock(
        return_value=[
            {"l5_disc": "골조", "l6_main": "거푸집공사"},
            {"l5_disc": "골조", "l6_main": "철근공사"},
            {"l5_disc": "마감", "l6_main": "도장공사"},
        ]
    )

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/sites/SITE-002/wbs_tree")

    root = res.json()
    # 루트 children = 2 trade (골조, 마감)
    assert len(root["children"]) == 2
    trade_names = {c["name"] for c in root["children"]}
    assert trade_names == {"골조", "마감"}

    # 골조 children = 2 work_package
    gonjo = next(c for c in root["children"] if c["name"] == "골조")
    assert gonjo["type"] == "trade"
    assert len(gonjo["children"]) == 2
    wp_names = {c["name"] for c in gonjo["children"]}
    assert wp_names == {"거푸집공사", "철근공사"}

    # work_package type 검증
    for wp in gonjo["children"]:
        assert wp["type"] == "work_package"


@pytest.mark.asyncio
async def test_wbs_tree_default_fields(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """PoC 기본값: review_count=0, status='unknown'."""
    mock_pg.fetch_all = AsyncMock(return_value=[{"l5_disc": "토공", "l6_main": "굴착공사"}])

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/sites/SITE-003/wbs_tree")

    root = res.json()
    # root 기본값
    assert root["review_count"] == 0
    assert root["status"] == "unknown"
    # trade 기본값
    trade = root["children"][0]
    assert trade["review_count"] == 0
    assert trade["status"] == "unknown"
    # work_package 기본값
    wp = trade["children"][0]
    assert wp["review_count"] == 0
    assert wp["status"] == "unknown"


# ---------------------------------------------------------------------------
# Phase 4.11 — GET /api/tasks?site_id=X&days=30
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_response_shape(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """응답 최상위 shape: tasks / progressByDate / itemsByDate 키 존재."""
    # fetch_all 두 번 호출됨 (tasks 조회 + items 조회) — 순서대로 다른 값 반환
    mock_pg.fetch_all = AsyncMock(
        side_effect=[
            # 1st call: tasks 집계 rows
            [
                {
                    "date": "2026-05-18",
                    "total_count": 5,
                    "progress_percent": 50.0,
                    "status": "running",
                    "has_anomaly": False,
                }
            ],
            # 2nd call: items rows
            [],
        ]
    )

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/tasks?site_id=SITE-001&days=30")

    assert res.status_code == 200
    body = res.json()
    assert "tasks" in body
    assert "progressByDate" in body
    assert "itemsByDate" in body


@pytest.mark.asyncio
async def test_tasks_daily_task_shape(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """DailyTask shape 검증 — date / total_count / progress_percent / status / has_anomaly."""
    mock_pg.fetch_all = AsyncMock(
        side_effect=[
            [
                {
                    "date": "2026-05-18",
                    "total_count": 80,
                    "progress_percent": 75.0,
                    "status": "completed",
                    "has_anomaly": True,
                }
            ],
            [],
        ]
    )

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/tasks?site_id=SITE-001&days=30")

    tasks = res.json()["tasks"]
    assert len(tasks) == 1
    t = tasks[0]
    assert t["date"] == "2026-05-18"
    assert t["total_count"] == 80
    assert isinstance(t["progress_percent"], float)
    assert t["status"] == "completed"
    assert t["has_anomaly"] is True


@pytest.mark.asyncio
async def test_tasks_progress_by_date_7_stages(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """progressByDate[date] 에 AgentStageProgress 8건 (7 agent + HIL) 존재."""
    mock_pg.fetch_all = AsyncMock(
        side_effect=[
            [
                {
                    "date": "2026-05-18",
                    "total_count": 10,
                    "progress_percent": 37.5,
                    "status": "running",
                    "has_anomaly": False,
                }
            ],
            [],
        ]
    )

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/tasks?site_id=SITE-001&days=30")

    progress = res.json()["progressByDate"]
    assert "2026-05-18" in progress
    stages = progress["2026-05-18"]
    # 7 agent + HIL = 8
    assert len(stages) == 8

    # step + agent 키 존재
    for s in stages:
        assert "step" in s
        assert "agent" in s
        assert "is_hil" in s
        assert "received" in s
        assert "processed" in s
        assert "percent" in s
        assert "waiting_hil" in s
