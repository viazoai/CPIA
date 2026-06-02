from __future__ import annotations

import sys
from pathlib import Path


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
