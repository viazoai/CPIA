"""LLM 동시성 제어 — forecaster + optimizer + atomizer 공유.

env: CPIA_LLM_CONCURRENCY (기본 4)
사용: `async with get_llm_semaphore(): await asyncio.to_thread(azure_sync_call, ...)`
"""

from __future__ import annotations

import asyncio
import os

_DEFAULT = 4


def get_llm_semaphore() -> asyncio.Semaphore:
    """Lazy 생성 (event loop 별). 같은 loop 안에서는 같은 인스턴스가 자연스럽게 공유됨."""
    n = int(os.environ.get("CPIA_LLM_CONCURRENCY", str(_DEFAULT)))
    return asyncio.Semaphore(max(1, n))
