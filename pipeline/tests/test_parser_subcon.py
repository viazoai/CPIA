from __future__ import annotations

import glob


from pipeline.agents.parser import parse_daily_report


def test_subcon_e2e_golden(sample_subcon_path):
    """업체작업일보 1개 E2E — 시뮬레이션 실측 골든."""
    r = parse_daily_report(sample_subcon_path)
    assert len(r["activities"]) == 33
    assert len(r["bp_summaries"]) == 1
    assert len(r["job_allocations"]) == 76
    assert len(r["equipment_allocations"]) == 68
    a = r["activities"][0]
    assert a["work_content"] == "PCW 20 배관 공사"  # 'M' 아님
    assert a["unit"] == "m"  # 총물량 아님
    assert a["today_qty"] == 30.0  # 금일실적[C], 누적 120 아님
    assert "중원엔지니어링" in a["company"]  # 'F02 5F' 아님
    assert a["bp_code"] == "M15X_PH4_041"
    assert a["trade"] == "UT"


def test_subcon_all_demo_inputs_parse(demo_inputs_dir):
    """demo_inputs 10개(동일 템플릿, 각 33 activity rows) 전부 ParseError 없이 파싱 (.xlsm 3개 포함)."""
    files = sorted(glob.glob(str(demo_inputs_dir / "*.xlsx")) + glob.glob(str(demo_inputs_dir / "*.xlsm")))
    assert len(files) == 10
    for f in files:
        r = parse_daily_report(f)
        assert len(r["activities"]) == 33, f
        assert len(r["bp_summaries"]) == 1, f


def test_subcon_determinism(sample_subcon_path):
    """동일 입력 2회 → 동일 출력 (결정성, 전체 ParsedDailyReport)."""
    r1 = parse_daily_report(sample_subcon_path)
    r2 = parse_daily_report(sample_subcon_path)
    assert r1 == r2
