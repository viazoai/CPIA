"""view_builder _compose_evm 단위 테스트 — pure function, PG 호출 X."""

from __future__ import annotations

from pipeline.agents.optimizer.view_builder import _compose_evm


def test_compose_evm_세보엠이씨_기계소화():
    """세보엠이씨 기계소화 케이스: SPI~32.47, CPI~51.32."""
    plan_row = {
        "cum_plan_qty": 77774,
        "cum_plan_mh": 744043,
        "plan_qty_full": 77774,
        "plan_mh_full": 744043,
    }
    actual_row = {"cum_actual_qty": 25252, "cum_actual_mh": 470692}
    r = _compose_evm(plan_row, actual_row)
    assert abs(r["spi"] - 32.47) < 0.1, f"SPI={r['spi']}"
    assert abs(r["cpi"] - 51.32) < 0.1, f"CPI={r['cpi']}"


def test_compose_evm_returns_none_when_no_plan():
    """plan_qty_full=0 이면 SPI/CPI 모두 None."""
    plan_row = {
        "cum_plan_qty": 0,
        "cum_plan_mh": 0,
        "plan_qty_full": 0,
        "plan_mh_full": 0,
    }
    actual_row = {"cum_actual_qty": 0, "cum_actual_mh": 0}
    r = _compose_evm(plan_row, actual_row)
    assert r["spi"] is None
    assert r["cpi"] is None
    assert r["ev"] == 0


def test_compose_evm_cpi_none_when_ac_zero():
    """AC=0 (work 미시작) 이면 CPI=None, SPI 는 계산 가능."""
    plan_row = {
        "cum_plan_qty": 100,
        "cum_plan_mh": 800,
        "plan_qty_full": 100,
        "plan_mh_full": 800,
    }
    actual_row = {"cum_actual_qty": 20, "cum_actual_mh": 0}
    r = _compose_evm(plan_row, actual_row)
    assert r["spi"] == 20.0  # 20/100 x 100 (EV=20% of 800=160, PV=800 -> 20%)
    assert r["cpi"] is None


def test_compose_evm_plan_row_none_safe():
    """plan_row=None safe handling."""
    actual_row = {"cum_actual_qty": 100, "cum_actual_mh": 200}
    r = _compose_evm(None, actual_row)
    assert r["spi"] is None
    assert r["cpi"] is None
