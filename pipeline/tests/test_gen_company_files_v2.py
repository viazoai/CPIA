from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path("/Users/kyungseoplee/Project Agent/CPIA")
sys.path.insert(0, str(ROOT))

from pipeline.scripts import gen_company_files_v2 as gen  # noqa: E402

EXPECTED = {
    # out_company: (src_company, trade_label, act, job, eq)
    "장평건설": ("장평건설", "토목공사", 10, 27, 45),
    "남웅건설": ("남웅건설", "건축공사", 48, 36, 33),
    "동신패널": ("동신패널", "건축공사", 24, 8, 17),
    "글로벌유명": ("글로벌유명", "건축공사", 3, 7, 13),
    "광건": ("광건티엔씨", "건축공사", 24, 4, 13),
    "태우": ("태우이엔지", "건축공사", 2, 4, 12),
    "선보": ("선보건업", "건축공사", 4, 2, 3),
}


def test_targets_are_seven_4tuples():
    assert len(gen.TARGETS) == 7
    out_names = set()
    for t in gen.TARGETS:
        assert len(t) == 4, f"4-tuple 아님: {t}"
        disp, trade_label, out_company, src_company = t
        assert out_company in EXPECTED, f"미확정 out_company: {out_company}"
        exp_src, exp_trade, *_ = EXPECTED[out_company]
        assert src_company == exp_src
        assert trade_label == exp_trade
        out_names.add(out_company)
    assert out_names == set(EXPECTED)
    # src!=out 3건
    src_neq_out = {t[2] for t in gen.TARGETS if t[2] != t[3]}
    assert src_neq_out == {"광건", "태우", "선보"}


@pytest.fixture(scope="module")
def built_files(tmp_path_factory):
    """7개사 전부 임시 OUT_DIR 에 생성 후 재파싱 결과 반환 (결정론 loop)."""
    from pipeline.agents.parser import parse_daily_report

    tmp = tmp_path_factory.mktemp("gen_out")
    orig_out = gen.OUT_DIR
    gen.OUT_DIR = tmp
    try:
        rep = parse_daily_report(str(gen.SRC))
        by_act, by_job, by_sum, by_eq = (
            defaultdict(list),
            defaultdict(list),
            defaultdict(list),
            defaultdict(list),
        )
        for a in rep["activities"]:
            if a.get("trade") in ("건축", "토목"):
                by_act[a.get("company") or ""].append(a)
        for j in rep["job_allocations"]:
            by_job[j.get("company") or ""].append(j)
        for s in rep["bp_summaries"]:
            by_sum[s.get("company") or ""].append(s)
        for e in rep.get("equipment_allocations", []):
            by_eq[e.get("company") or ""].append(e)
        am_by_co = asyncio.run(gen._load_ongoing_am([t[2] for t in gen.TARGETS]))
        results = {}
        for raw_name, trade_label, out_company, src_company in gen.TARGETS:
            out, na, nj, ns, ne = gen.build_one(
                out_company,
                src_company,
                raw_name,
                trade_label,
                by_act,
                by_job,
                by_sum,
                by_eq,
                am_by_co,
            )
            results[out_company] = (out, parse_daily_report(str(out)))
        return results
    finally:
        gen.OUT_DIR = orig_out


@pytest.mark.parametrize("out_company", list(EXPECTED))
def test_sheet1_rollup_nonzero_when_jobs_present(built_files, out_company):
    """job 이 있으면 시트1 BP행 금일누계 총계 > 0 (롤업 반영)."""

    _, rp = built_files[out_company]
    sums = rp.get("bp_summaries", [])
    # 동신패널은 src sum=0 이라 과거엔 빈 시트 → 이제 job 롤업으로 채워져야 함
    if EXPECTED[out_company][3] > 0:  # job count > 0
        assert sums, f"{out_company} 시트1 bp_summaries 비어있음 (job 롤업 실패)"
        total_cum = sum(int(s.get("today_cum_total") or 0) for s in sums)
        assert total_cum > 0, f"{out_company} 시트1 금일누계 총계 0"


@pytest.mark.parametrize("out_company", list(EXPECTED))
def test_sheet3_equip_count_roundtrip(built_files, out_company):
    exp_eq = EXPECTED[out_company][4]
    _, rp = built_files[out_company]
    eqs = rp.get("equipment_allocations", [])
    assert len(eqs) == exp_eq, f"{out_company} eq {len(eqs)} != {exp_eq}"
    cos = {e.get("company") for e in eqs}
    assert cos == {out_company}, f"{out_company} eq company {cos}"


@pytest.mark.parametrize("out_company", list(EXPECTED))
def test_sheet4_no_zero_today_qty(built_files, out_company):
    """역산 후 today_qty==0 행 0건."""
    _, rp = built_files[out_company]
    zero = [a for a in rp["activities"] if not (a.get("today_qty") and float(a["today_qty"]) > 0)]
    assert not zero, f"{out_company} today_qty 0 행 {len(zero)}건"


@pytest.mark.parametrize("out_company", list(EXPECTED))
def test_sheet4_company_is_out_company(built_files, out_company):
    """파일 파싱 company == out_company (광건/태우/선보 정렬 확인)."""
    _, rp = built_files[out_company]
    cos = {a.get("company") for a in rp["activities"]}
    assert cos == {out_company}, f"{out_company}: {cos}"


@pytest.mark.parametrize("out_company", list(EXPECTED))
def test_sheet4_not_all_floored(built_files, out_company):
    """역산 활동이 전부 1.0 floor 가 아님 — 회사 단위 degenerate 방지 (option1 배분)."""
    _, rp = built_files[out_company]
    tqs = [float(a["today_qty"]) for a in rp["activities"] if a.get("today_qty") is not None]
    assert tqs, f"{out_company} today_qty 없음"
    assert any(q > 1.0 for q in tqs), f"{out_company} 전 활동 today_qty<=1.0 (degenerate)"
