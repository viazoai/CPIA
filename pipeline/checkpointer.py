"""LangGraph checkpoint — Phase 1 PoC: InMemorySaver.

prod (Reporter cycle 또는 통합 cycle): PostgresSaver 전환.

Spec: docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §8.1
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver


def build_checkpointer():
    """Phase 1 PoC checkpointer — InMemorySaver.

    interrupt + Command(resume=...) cycle 지원에 필요한 thread-local 상태 저장소.
    """
    return InMemorySaver()
