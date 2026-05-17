"""PostgresSaver 영속 + fallback 검증.

Spec §7.4 + design-intent O-6.
"""

from __future__ import annotations

import os

import pytest


@pytest.mark.asyncio
async def test_checkpointer_postgres_by_default(monkeypatch) -> None:
    """CPIA_CHECKPOINTER 미설정 + POSTGRES_URL 존재 → InMemorySaver 아님 (PostgresSaver wrapper).

    async test — AsyncPostgresSaver.__init__ 가 asyncio.get_running_loop() 요구.
    """
    from langgraph.checkpoint.memory import InMemorySaver

    if not os.environ.get("POSTGRES_URL"):
        pytest.skip("POSTGRES_URL 누락")
    monkeypatch.delenv("CPIA_CHECKPOINTER", raising=False)
    from pipeline.checkpointer import build_checkpointer

    saver = build_checkpointer()
    assert not isinstance(saver, InMemorySaver), "PostgresSaver default 동작 안 함"


@pytest.mark.asyncio
async def test_checkpointer_memory_fallback(monkeypatch) -> None:
    """CPIA_CHECKPOINTER=memory → InMemorySaver."""
    from langgraph.checkpoint.memory import InMemorySaver

    monkeypatch.setenv("CPIA_CHECKPOINTER", "memory")
    from pipeline.checkpointer import build_checkpointer

    saver = build_checkpointer()
    assert isinstance(saver, InMemorySaver)


@pytest.mark.asyncio
async def test_checkpointer_no_postgres_url_fallback(monkeypatch) -> None:
    """POSTGRES_URL 미설정 → InMemorySaver fallback."""
    from langgraph.checkpoint.memory import InMemorySaver

    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("CPIA_CHECKPOINTER", raising=False)
    from pipeline.checkpointer import build_checkpointer

    saver = build_checkpointer()
    assert isinstance(saver, InMemorySaver), "POSTGRES_URL 없으면 fallback 필요"
