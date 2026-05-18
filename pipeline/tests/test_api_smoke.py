"""FastAPI /health 엔드포인트 스모크 테스트 (Phase 4.1 RED -> GREEN).

PG 연결이 활성화된 환경에서만 실행됨 — POSTGRES_URL 미설정 시 skip.
"""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

from pipeline.api import app


@pytest.fixture
def pg_url() -> str:
    url = os.getenv("POSTGRES_URL")
    if not url:
        pytest.skip("POSTGRES_URL 미설정")
    return url


@pytest.mark.asyncio
async def test_health_returns_ok(pg_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /health -> 200, status=ok, pg=True."""
    monkeypatch.setenv("POSTGRES_URL", pg_url)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            res = await client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["pg"] is True
    assert body["version"] == app.version


@pytest.mark.asyncio
async def test_health_returns_json_shape(pg_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /health 응답 JSON 키 집합이 정확히 {status, pg, version} 인지 확인."""
    monkeypatch.setenv("POSTGRES_URL", pg_url)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            res = await client.get("/health")
    body = res.json()
    assert set(body.keys()) == {"status", "pg", "version"}
