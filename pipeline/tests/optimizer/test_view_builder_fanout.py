"""_build_optimizer_view wa fan-out — 한 advice 가 여러 wa 에 대응 시 by_wp 에 모두 적재.

spec docs/superpowers/specs/2026-05-20-cpia-frontend-data-binding-design.md §8.3 (B) 옵션.
plan T1.1.

mapper_activities 의 (l6_main, company) → DISTINCT wa 가 1:N — view_builder 가 wa_lookup 받아
같은 advice 를 wa 마다 by_wp[wa-l6-company] 에 복사. wa_lookup 비어있으면 기존 동작 보존.
"""

from __future__ import annotations

from pipeline.agents.optimizer.view_builder import _build_optimizer_view


def _advice(company: str = "창원기전", l6: str = "CABLE TRAY공사") -> dict:
    return {
        "company": company,
        "l6_main": l6,
        "diagnosis": "test",
        "recommendations": [],
        "degradation_cases": [],
        "recovery_distribution": {},
        "recovery_pattern": [],
    }


def _forecast(company: str = "창원기전", l6: str = "CABLE TRAY공사", wa=None) -> dict:
    return {
        "company": company,
        "l6_main": l6,
        "wa": wa,
        "risk_level": "이상",
        "delay_days": 5,
    }


def test_fanout_single_wa():
    """(l6, company) → wa 1개 → by_wp key 1개."""
    result = _build_optimizer_view(
        [_advice()],
        [_forecast(wa="CUB")],
        mapped=[],
        wa_lookup={("CABLE TRAY공사", "창원기전"): ["CUB"]},
    )
    assert "cub-cable-tray공사-창원기전" in result["by_wp"]
    assert len(result["by_wp"]) == 1


def test_fanout_multi_wa():
    """(l6, company) → wa 2개 → by_wp key 2개, 같은 diagnosis 복사."""
    result = _build_optimizer_view(
        [_advice()],
        [_forecast(wa="CUB")],
        mapped=[],
        wa_lookup={("CABLE TRAY공사", "창원기전"): ["CUB", "FAB"]},
    )
    keys = list(result["by_wp"].keys())
    assert "cub-cable-tray공사-창원기전" in keys
    assert "fab-cable-tray공사-창원기전" in keys
    # fanout: 두 wa 가 같은 진단 복사. 진단 2줄째(LLM 현장여건="test") 보존.
    # (1줄째는 2026-06 결정론 물량 현황 prefix — 픽스처에 qty 없어 placeholder, 형식은
    #  test_status_line_qty 가 검증. 여기선 fanout 동일성 + LLM 라인 보존만 확인.)
    cub_diag = result["by_wp"]["cub-cable-tray공사-창원기전"]["diagnosis"]
    fab_diag = result["by_wp"]["fab-cable-tray공사-창원기전"]["diagnosis"]
    assert cub_diag == fab_diag
    assert cub_diag.endswith("test")


def test_no_wa_lookup_fallback():
    """wa_lookup 비어있으면 forecasts.wa 기반 단일 key (기존 동작 보존)."""
    result = _build_optimizer_view(
        [_advice(company="X", l6="Y")],
        [_forecast(company="X", l6="Y", wa=None)],
        mapped=[],
        wa_lookup={},
    )
    # forecasts.wa=None → "unknown" kebab
    assert "unknown-y-x" in result["by_wp"]


def test_no_wa_lookup_arg_omitted():
    """wa_lookup 인자 자체 omit (back-compat) — 기존 호출부 미수정 안전."""
    result = _build_optimizer_view(
        [_advice(company="X", l6="Y")],
        [_forecast(company="X", l6="Y", wa="ZONE1")],
        mapped=[],
    )
    # forecasts.wa="ZONE1" → kebab "zone1"
    assert "zone1-y-x" in result["by_wp"]
