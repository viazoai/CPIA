from __future__ import annotations


def test_diag_prompt_v10_guards():
    from pipeline.agents.optimizer.prompt import DIAG_PROMPT_V10

    assert "현장여건" in DIAG_PROMPT_V10
    assert "회복 패턴" in DIAG_PROMPT_V10  # 금지 명시
    assert "한글 숫자 금지" in DIAG_PROMPT_V10
