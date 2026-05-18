"""GET /api/sites + /api/runs/:id/optimizer + /api/runs/:id/wp_summary — Phase 4.3~4.5 TDD (RED → GREEN).

테스트 전략:
- Phase 4.2 패턴 동일: lifespan 수동 실행 + AsyncClient(ASGITransport)
- PGClient.fetch_all 을 AsyncMock 으로 교체 (실 PG 연결 X)
- build_graph + _build_prod_graph_config mock (lifespan dummy graph)
- CPIA_CHECKPOINTER=memory, POSTGRES_URL=dummy
"""

from __future__ import annotations

import uuid
from datetime import date
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
# Phase 4.3 — GET /api/sites
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sites_returns_list(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """정상 DB 결과 → Site[] (list) 반환 + 200."""
    mock_pg.fetch_all = AsyncMock(
        return_value=[
            {
                "site_id": "SITE-001",
                "name": "M15X IBL",
                "location": "경기도 화성",
                "status": "normal",
                "plan_progress": 45.0,
                "actual_progress": 42.0,
                "gap_percent": -3.0,
                "spi": 0.93,
                "productivity_today": 88.0,
                "abnormal_trades": 1,
                "fte_saved": 2.5,
                "hours_saved": 350.0,
                "headcount": 120,
                "total_hours": 16800,
                "ai_replacement_rate": 2.08,
                "expected_completion": date(2026, 9, 30),
                "delay_days": 3.0,
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
                res = await client.get("/api/sites")

    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert len(body) == 1


@pytest.mark.asyncio
async def test_sites_shape(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """Site shape 검증 — id / progress_planned / progress_actual / recovered_completion / recovery_days."""
    mock_pg.fetch_all = AsyncMock(
        return_value=[
            {
                "site_id": "SITE-001",
                "name": "M15X IBL",
                "location": "경기도 화성",
                "status": "caution",
                "plan_progress": 50.0,
                "actual_progress": 48.0,
                "gap_percent": -2.0,
                "spi": 0.96,
                "productivity_today": 92.0,
                "abnormal_trades": 0,
                "fte_saved": 1.2,
                "hours_saved": 168.0,
                "headcount": 80,
                "total_hours": 11200,
                "ai_replacement_rate": 1.5,
                "expected_completion": date(2026, 10, 15),
                "delay_days": 5.0,
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
                res = await client.get("/api/sites")

    site = res.json()[0]
    # PG 컬럼명 → types.ts 필드명 매핑 확인
    assert site["id"] == "SITE-001"
    assert site["progress_planned"] == 50.0
    assert site["progress_actual"] == 48.0
    # PoC: recovered_completion = expected_completion 그대로
    assert site["recovered_completion"] == site["expected_completion"]
    # PoC: recovery_days = 0
    assert site["recovery_days"] == 0


@pytest.mark.asyncio
async def test_sites_empty(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """DB row 없음 → 빈 배열 반환 + 200."""
    mock_pg.fetch_all = AsyncMock(return_value=[])

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/sites")

    assert res.status_code == 200
    assert res.json() == []


# ---------------------------------------------------------------------------
# Phase 4.4 — GET /api/runs/:run_id/optimizer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimizer_returns_list(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """optimizer_advice rows → OptimizerOutput[] (배열) 반환 + 200."""
    run_id = str(uuid.uuid4())
    mock_pg.fetch_all = AsyncMock(
        return_value=[
            {
                "wp_id": "거푸집공사-A건설",
                "diagnosis": "장비 대기로 인한 저하 추정",
                "degradation_cases": [
                    {"date": "2026-04-10", "description": "크레인 대기 3h", "outcome": "회복 d+2"}
                ],
                "recommendations": [{"rank": 1, "text": "크레인 사전 배차 확인"}],
                "recovery_distribution": {"d+1": 2, "d+2": 1},
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
                res = await client.get(f"/api/runs/{run_id}/optimizer")

    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert len(body) == 1


@pytest.mark.asyncio
async def test_optimizer_shape(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """OptimizerOutput shape 검증 — wp_id / diagnosis / similar_cases / recommendations / details."""
    run_id = str(uuid.uuid4())
    mock_pg.fetch_all = AsyncMock(
        return_value=[
            {
                "wp_id": "거푸집공사-A건설",
                "diagnosis": "장비 대기로 인한 저하 추정",
                "degradation_cases": [
                    {"date": "2026-04-10", "description": "크레인 대기", "outcome": "회복"}
                ],
                "recommendations": [{"rank": 1, "text": "크레인 사전 배차"}],
                "recovery_distribution": {"d+1": 2, "not_recovered": 1},
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
                res = await client.get(f"/api/runs/{run_id}/optimizer")

    item = res.json()[0]
    assert "wp_id" in item
    assert "diagnosis" in item
    # similar_cases = degradation_cases JSONB
    assert isinstance(item["similar_cases"], list)
    assert item["similar_cases"][0]["date"] == "2026-04-10"
    # recommendations = rank 제거한 string 배열
    assert isinstance(item["recommendations"], list)
    assert isinstance(item["recommendations"][0], str)
    # details = list (빈 배열 허용)
    assert isinstance(item["details"], list)


@pytest.mark.asyncio
async def test_optimizer_empty(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """run_id 에 optimizer_advice 없음 → 빈 배열 + 200."""
    run_id = str(uuid.uuid4())
    mock_pg.fetch_all = AsyncMock(return_value=[])

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(f"/api/runs/{run_id}/optimizer")

    assert res.status_code == 200
    assert res.json() == []


# ---------------------------------------------------------------------------
# Phase 4.5 — GET /api/runs/:run_id/wp_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wp_summary_returns_list(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """wp_summary rows → WPSummaryRow[] 반환 + 200."""
    run_id = str(uuid.uuid4())
    mock_pg.fetch_all = AsyncMock(
        return_value=[
            {
                "wp_id": "WA-A-거푸집공사-A건설",
                "wp_name": "거푸집공사",
                "trade": "골조",
                "bp_name": "A건설",
                "start_date": date(2026, 5, 1),
                "end_date": date(2026, 6, 30),
                "progress_pct": 45.0,
                "productivity": 88.0,
                "status": "normal",
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
                res = await client.get(f"/api/runs/{run_id}/wp_summary")

    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert len(body) == 1


@pytest.mark.asyncio
async def test_wp_summary_shape(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """WPSummaryRow shape 검증 — wp_id / wp_name / trade / bp_name / dates / progress_pct / productivity / status."""
    run_id = str(uuid.uuid4())
    mock_pg.fetch_all = AsyncMock(
        return_value=[
            {
                "wp_id": "WA-A-거푸집공사-A건설",
                "wp_name": "거푸집공사",
                "trade": "골조",
                "bp_name": "A건설",
                "start_date": date(2026, 5, 1),
                "end_date": date(2026, 6, 30),
                "progress_pct": 45.0,
                "productivity": 88.0,
                "status": "caution",
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
                res = await client.get(f"/api/runs/{run_id}/wp_summary")

    row = res.json()[0]
    assert row["wp_id"] == "WA-A-거푸집공사-A건설"
    assert row["wp_name"] == "거푸집공사"
    assert row["trade"] == "골조"
    assert row["bp_name"] == "A건설"
    assert row["start_date"] == "2026-05-01"
    assert row["end_date"] == "2026-06-30"
    assert isinstance(row["progress_pct"], float)
    assert isinstance(row["productivity"], float)
    assert row["status"] == "caution"


@pytest.mark.asyncio
async def test_wp_summary_empty(
    mock_pg: MagicMock,
    mock_graph: MagicMock,
) -> None:
    """run_id 에 wp_summary 없음 → 빈 배열 + 200."""
    run_id = str(uuid.uuid4())
    mock_pg.fetch_all = AsyncMock(return_value=[])

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=mock_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(f"/api/runs/{run_id}/wp_summary")

    assert res.status_code == 200
    assert res.json() == []
