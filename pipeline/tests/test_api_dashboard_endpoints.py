"""GET /api/sites/:site_id/reports + /api/dashboard/performance + /api/dashboard/impact
— Phase 4.6 + 4.7 + 4.8 TDD (RED -> GREEN).

테스트 전략:
- Phase 4.3~4.5 패턴 동일: lifespan 수동 실행 + AsyncClient(ASGITransport)
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
# Phase 4.6 — GET /api/sites/:site_id/reports?days=30
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_site_reports_returns_list(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """정상 DB 결과 -> ReportDaily[] (list) 반환 + 200."""
    mock_pg.fetch_all = AsyncMock(
        return_value=[
            {
                "date": "2026-05-18",
                "status": "normal",
                "productivity_today": 92.5,
                "delay_days": 2.0,
                "recovery_days": 0,
            }
        ]
    )

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/sites/SITE-001/reports?days=30")

    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert len(body) == 1


@pytest.mark.asyncio
async def test_site_reports_shape(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """ReportDaily shape 검증 — date / status / productivity_today / delay_days / recovery_days."""
    mock_pg.fetch_all = AsyncMock(
        return_value=[
            {
                "date": "2026-05-18",
                "status": "caution",
                "productivity_today": 78.0,
                "delay_days": 5.0,
                "recovery_days": 0,
            }
        ]
    )

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/sites/SITE-001/reports?days=30")

    row = res.json()[0]
    assert "date" in row
    assert row["status"] == "caution"
    assert isinstance(row["productivity_today"], float)
    assert isinstance(row["delay_days"], float)
    # PoC: recovery_days = 0
    assert row["recovery_days"] == 0


@pytest.mark.asyncio
async def test_site_reports_empty(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """site_id 에 report 없음 -> 빈 배열 반환 + 200."""
    mock_pg.fetch_all = AsyncMock(return_value=[])

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/sites/SITE-NONE/reports?days=30")

    assert res.status_code == 200
    assert res.json() == []


# ---------------------------------------------------------------------------
# Phase 4.7 — GET /api/dashboard/performance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_performance_kpi_shape(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """fleet_kpi shape 검증 — productivity_today / delay_days / recoverable_days / abnormal_trades."""
    mock_pg.fetch_one = AsyncMock(
        return_value={
            "productivity_today": 85.5,
            "delay_days": 3.0,
            "recoverable_days": 12,
            "abnormal_trades": 2,
        }
    )

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/dashboard/performance")

    assert res.status_code == 200
    body = res.json()
    assert "productivity_today" in body
    assert "delay_days" in body
    assert "recoverable_days" in body
    assert "abnormal_trades" in body


@pytest.mark.asyncio
async def test_performance_kpi_numeric_types(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """fleet_kpi 숫자 타입 검증 — float / int."""
    mock_pg.fetch_one = AsyncMock(
        return_value={
            "productivity_today": 90.0,
            "delay_days": 1.0,
            "recoverable_days": 5,
            "abnormal_trades": 0,
        }
    )

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/dashboard/performance")

    body = res.json()
    assert isinstance(body["productivity_today"], float)
    assert isinstance(body["delay_days"], float)
    assert isinstance(body["recoverable_days"], (int, float))
    assert isinstance(body["abnormal_trades"], int)


@pytest.mark.asyncio
async def test_performance_kpi_null_fallback(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """DB NULL -> 0 fallback 처리 확인."""
    mock_pg.fetch_one = AsyncMock(return_value=None)

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/dashboard/performance")

    assert res.status_code == 200
    body = res.json()
    assert body["productivity_today"] == 0.0
    assert body["delay_days"] == 0.0
    assert body["recoverable_days"] == 0
    assert body["abnormal_trades"] == 0


# ---------------------------------------------------------------------------
# Phase 4.8 — GET /api/dashboard/impact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_impact_returns_list(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """정상 DB 결과 -> ImpactSiteDistribution[] 반환 + 200."""
    mock_pg.fetch_all = AsyncMock(
        return_value=[
            {
                "site_id": "SITE-001",
                "site_name": "M15X IBL",
                "hours_saved": 350.0,
                "fte_saved": 2.5,
            }
        ]
    )

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/dashboard/impact")

    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert len(body) == 1


@pytest.mark.asyncio
async def test_impact_shape(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """ImpactSiteDistribution shape 검증 — site_id / site_name / hours_saved / fte_saved."""
    mock_pg.fetch_all = AsyncMock(
        return_value=[
            {
                "site_id": "SITE-001",
                "site_name": "M15X IBL",
                "hours_saved": 350.0,
                "fte_saved": 2.5,
            }
        ]
    )

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/dashboard/impact")

    item = res.json()[0]
    assert item["site_id"] == "SITE-001"
    assert item["site_name"] == "M15X IBL"
    assert isinstance(item["hours_saved"], float)
    assert isinstance(item["fte_saved"], float)


@pytest.mark.asyncio
async def test_impact_empty(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """sites 테이블 비어있음 -> 빈 배열 + 200."""
    mock_pg.fetch_all = AsyncMock(return_value=[])

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/dashboard/impact")

    assert res.status_code == 200
    assert res.json() == []
