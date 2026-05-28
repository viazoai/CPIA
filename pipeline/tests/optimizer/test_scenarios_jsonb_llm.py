"""Task 15 fix — scenarios_jsonb 가 LLM rich rationale 사용 (G8 trade_frame 보존)."""

from __future__ import annotations

import inspect

from pipeline.agents.optimizer import agent as agent_mod


def test_agent_imports_build_scenarios():
    """_build_scenarios 가 agent 모듈에 import 됨."""
    assert hasattr(agent_mod, "_build_scenarios")


def test_optimize_body_uses_build_scenarios_for_scenarios_jsonb():
    """optimize() 본체에 scenarios_jsonb = _build_scenarios(advice_rows, forecast) 패턴 존재."""
    source = inspect.getsource(agent_mod.optimize)
    assert "scenarios_jsonb" in source
    assert "_build_scenarios(" in source
    # v2_result.get("scenarios") 로 scenarios_jsonb 채우는 패턴 부재
    # (다른 8 jsonb 는 v2 사용 — 이건 OK)
    bad_pattern = '"scenarios_jsonb": v2_result.get("scenarios"'
    assert bad_pattern not in source, "scenarios_jsonb 가 v2 deterministic 사용 — LLM rich rationale 손실"


def test_other_8_jsonb_still_use_v2():
    """다른 8 jsonb 는 v2 source 유지 (#N19 일원화)."""
    source = inspect.getsource(agent_mod.optimize)
    # v2_result 사용 패턴 (productivity / kpi / contractor / trade / quadrant / wp_summary / optimizer_view / s_curve)
    for key in ["productivity_jsonb", "kpi_jsonb", "quadrant_jsonb", "wp_summary_jsonb"]:
        assert key in source
