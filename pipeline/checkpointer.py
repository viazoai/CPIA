"""LangGraph checkpoint — Phase 2 통합 cycle: PostgresSaver (fallback InMemorySaver).

design-intent O-6: Reporter cycle 또는 통합 cycle 진입 시 PostgresSaver 전환.

환경 변수:
- CPIA_CHECKPOINTER=memory → InMemorySaver (Phase 1 호환, 개발/테스트용)
- 그 외 (default postgres) → _LazyAsyncPostgresSaver (POSTGRES_URL 필수)
- POSTGRES_URL 미설정 시 InMemorySaver 안전 fallback

build_checkpointer 는 sync 함수 — AsyncConnectionPool 의 await pool.open() 을
직접 호출 못 함. 따라서 _LazyAsyncPostgresSaver (AsyncPostgresSaver 상속) 가
첫 async method 호출 시 자동 pool.open() 처리. LangGraph 의
isinstance(checkpointer, BaseCheckpointSaver) 검사를 위해 base class 상속.

PG 테이블 (checkpoints + checkpoint_writes + checkpoint_blobs +
checkpoint_migrations) 은 sync PostgresSaver.setup() 가 idempotent 자동
생성 (현 cycle Step 4.4 시점에 박힘).

Spec: docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §7.4
"""

from __future__ import annotations

import os

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


class _LazyAsyncPostgresSaver(AsyncPostgresSaver):
    """AsyncPostgresSaver wrapper — 첫 async method 호출 시 AsyncConnectionPool 자동 open.

    AsyncConnectionPool 은 sync __init__ 안에서 await pool.open() 호출 불가.
    LangGraph 가 graph.ainvoke 안에서 aput/aget_tuple/aput_writes/alist 호출 —
    그 시점 (= async context 안) 에 pool.open() 을 첫 호출 시 lazy 수행.
    """

    def __init__(self, postgres_url: str):
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            postgres_url,
            kwargs={"autocommit": True},
            max_size=10,
            open=False,
        )
        super().__init__(pool)
        self._lazy_pool = pool
        self._opened = False

    async def _ensure_open(self) -> None:
        if not self._opened:
            await self._lazy_pool.open()
            self._opened = True

    async def aput(self, *args, **kwargs):
        await self._ensure_open()
        return await super().aput(*args, **kwargs)

    async def aget_tuple(self, *args, **kwargs):
        await self._ensure_open()
        return await super().aget_tuple(*args, **kwargs)

    async def aput_writes(self, *args, **kwargs):
        await self._ensure_open()
        return await super().aput_writes(*args, **kwargs)

    async def alist(self, *args, **kwargs):
        await self._ensure_open()
        async for x in super().alist(*args, **kwargs):
            yield x

    async def aget(self, *args, **kwargs):
        await self._ensure_open()
        return await super().aget(*args, **kwargs)


def build_checkpointer():
    """Phase 2 — PostgresSaver default, fallback InMemorySaver.

    InMemorySaver 분기:
    1. CPIA_CHECKPOINTER=memory 명시
    2. POSTGRES_URL 미설정

    PostgresSaver 분기 → _LazyAsyncPostgresSaver (async graph.ainvoke 정합).
    """
    if os.environ.get("CPIA_CHECKPOINTER", "postgres") == "memory":
        return InMemorySaver()

    postgres_url = os.environ.get("POSTGRES_URL")
    if not postgres_url:
        return InMemorySaver()

    return _LazyAsyncPostgresSaver(postgres_url)
