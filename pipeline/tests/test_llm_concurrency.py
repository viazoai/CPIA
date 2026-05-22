"""B3 — LLM 병렬화 Semaphore 테스트.

CPIA_LLM_CONCURRENCY=N 일 때 동시에 최대 N개만 진입.
"""

from __future__ import annotations

import asyncio

import pytest

from pipeline.agents._concurrency import get_llm_semaphore


@pytest.mark.asyncio
async def test_semaphore_default_4(monkeypatch):
    monkeypatch.delenv("CPIA_LLM_CONCURRENCY", raising=False)
    sem = get_llm_semaphore()
    assert sem._value == 4  # 기본 4


@pytest.mark.asyncio
async def test_semaphore_env_override(monkeypatch):
    monkeypatch.setenv("CPIA_LLM_CONCURRENCY", "2")
    sem = get_llm_semaphore()
    assert sem._value == 2


@pytest.mark.asyncio
async def test_semaphore_caps_concurrent(monkeypatch):
    """동시 진입자 <= N — 5개 task 를 2 동시 제한으로 돌리면 max concurrent = 2."""
    monkeypatch.setenv("CPIA_LLM_CONCURRENCY", "2")
    sem = get_llm_semaphore()
    in_flight = 0
    max_in_flight = 0

    async def work():
        nonlocal in_flight, max_in_flight
        async with sem:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1

    await asyncio.gather(*(work() for _ in range(5)))
    assert max_in_flight == 2
