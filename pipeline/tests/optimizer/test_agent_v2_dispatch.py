"""Task 15 (#N19) — agent.py 의 _build_productivity_views v1 → v2 일원화 검증.

검증 포인트:
1. agent 모듈이 _build_productivity_views_v2 를 import (v1 import 제거)
2. v2 시그니처가 (pg, site_id, today) 3 인자 그대로
3. optimize() 의 view builder 블록이 v2 만 호출 (v1 부재)

backfill_v2 + live cycle 가 동일 source 사용 — 단일 산식 보장.
"""

from __future__ import annotations

import inspect

from pipeline.agents.optimizer import agent as agent_mod


def test_agent_imports_v2() -> None:
    """agent.py 가 _build_productivity_views_v2 를 노출."""
    assert hasattr(agent_mod, "_build_productivity_views_v2"), (
        "agent.py 가 _build_productivity_views_v2 를 import 하지 않음"
    )


def test_agent_does_not_import_v1() -> None:
    """v1 _build_productivity_views 는 agent 네임스페이스에 없어야 — 호출 경로 제거 검증."""
    assert not hasattr(agent_mod, "_build_productivity_views"), (
        "agent.py 가 여전히 v1 _build_productivity_views 를 import 중 — Task 15 미완"
    )


def test_v2_signature() -> None:
    """v2 시그니처: (pg, site_id, today) — 3 인자 고정."""
    from pipeline.agents.optimizer.view_builder import _build_productivity_views_v2

    sig = inspect.signature(_build_productivity_views_v2)
    params = list(sig.parameters.keys())
    assert params == ["pg", "site_id", "today"], (
        f"v2 시그니처 변경됨: {params} (기대: ['pg', 'site_id', 'today'])"
    )


def test_optimize_body_references_v2_only() -> None:
    """optimize 본문이 v2 만 호출 — v1 호출 텍스트 부재 확인 (static check)."""
    src = inspect.getsource(agent_mod.optimize)
    assert "_build_productivity_views_v2(" in src, "optimize() 가 _build_productivity_views_v2 호출하지 않음"
    # v1 호출 "_build_productivity_views(" (v2 suffix 없는 패턴) 부재 검증.
    # 정확히 v1 만 매칭: "_build_productivity_views(" 뒤에 "v" 가 안 와야 함.
    import re

    v1_pattern = re.compile(r"_build_productivity_views\((?!v)")
    assert not v1_pattern.search(src), "optimize() 가 여전히 v1 _build_productivity_views() 호출 중"


def test_v1_function_preserved_in_view_builder() -> None:
    """v1 _build_productivity_views 함수 자체는 view_builder.py 에 보존
    (다른 caller: scripts/backfill_daily_report_views.py, scripts/seed_dummy_year.py)."""
    from pipeline.agents.optimizer import view_builder

    assert hasattr(view_builder, "_build_productivity_views"), (
        "v1 함수가 view_builder.py 에서 제거됨 — 다른 caller 깨짐"
    )
    assert hasattr(view_builder, "_build_productivity_views_v2"), "v2 함수가 view_builder.py 에서 제거됨"
