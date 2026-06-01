from __future__ import annotations

from pipeline.agents.forecaster.agent import _bottleneck_unit


def test_bottleneck_picks_max_delay_unit():
    # 혼재 WP: ton 이 9일로 가장 지연 → 병목.
    assert _bottleneck_unit({"m3": 2, "ton": 9, "m2": 0}) == "ton"


def test_bottleneck_none_when_empty():
    assert _bottleneck_unit({}) is None


def test_bottleneck_negative_all_picks_least_ahead():
    # 전부 앞섬(음수)이면 가장 덜 앞선(최댓값) unit = 병목 후보.
    assert _bottleneck_unit({"m3": -5, "ton": -1}) == "ton"
