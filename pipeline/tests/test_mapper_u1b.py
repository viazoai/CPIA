"""Mapper U1.B — cum_workers prorate + fallback 단위 테스트.

prorate logic 을 helper-style pure function 으로 추출해 검증.
"""

from __future__ import annotations

import collections


def prorate_cum_workers(
    mapped: list[dict],
    job_allocations: list[dict],
) -> list[dict]:
    """parser_job_allocations 의 company workers_cum_t (final_flag=O) 를 activity 단위 prorate."""
    # company SUM
    job_alloc_sum: dict[str, int] = {}
    for ja in job_allocations:
        if ja.get("final_flag") != "O":
            continue
        c = ja.get("company")
        if c:
            job_alloc_sum[c] = job_alloc_sum.get(c, 0) + int(ja.get("workers_cum_t") or 0)
    # company total plan_mh
    company_total_plan_mh: dict[str, float] = {}
    for a in mapped:
        c = a.get("company")
        if c and a.get("plan_mh"):
            company_total_plan_mh[c] = company_total_plan_mh.get(c, 0.0) + float(a["plan_mh"])
    # active l6
    active_l6: dict[str, set] = collections.defaultdict(set)
    for a in mapped:
        if a.get("company") and a.get("l6_main"):
            active_l6[a["company"]].add(a["l6_main"])
    # prorate
    out = []
    for a in mapped:
        a = {**a}
        if a.get("l6_main"):
            c = a["company"]
            workers_c = job_alloc_sum.get(c, 0)
            company_mh = company_total_plan_mh.get(c, 0.0)
            plan_mh = float(a.get("plan_mh") or 0)
            n_l6 = len(active_l6[c]) if c else 0
            if company_mh > 0 and plan_mh > 0:
                a["cum_workers_today"] = workers_c * (plan_mh / company_mh)
                a["prorate_method"] = "plan_mh"
            elif n_l6 > 0:
                a["cum_workers_today"] = workers_c / n_l6
                a["prorate_method"] = "uniform_fallback"
            else:
                a["cum_workers_today"] = 0.0
                a["prorate_method"] = "zero"
            a["cum_actual_mh_today"] = a["cum_workers_today"] * 8.0
        out.append(a)
    return out


def test_prorate_plan_mh_weight():
    """plan_mh 비율로 prorate — company total=1000, activity=200 → 20%."""
    mapped = [
        {"company": "세보엠이씨", "l6_main": "콘크리트 타설", "plan_mh": 200.0},
        {"company": "세보엠이씨", "l6_main": "철근 가공", "plan_mh": 800.0},
    ]
    job_alloc = [{"company": "세보엠이씨", "workers_cum_t": 100, "final_flag": "O"}]
    out = prorate_cum_workers(mapped, job_alloc)
    assert out[0]["cum_workers_today"] == 20.0  # 100 × (200/1000)
    assert out[0]["prorate_method"] == "plan_mh"
    assert out[1]["cum_workers_today"] == 80.0  # 100 × (800/1000)
    assert out[0]["cum_actual_mh_today"] == 160.0  # 20 × 8.0


def test_prorate_uniform_fallback_when_plan_mh_zero():
    """plan_mh=0 인데 active_l6=2 → workers/2 균등 분배."""
    mapped = [
        {"company": "세보엠이씨", "l6_main": "L6_A", "plan_mh": 0},
        {"company": "세보엠이씨", "l6_main": "L6_B", "plan_mh": 0},
    ]
    job_alloc = [{"company": "세보엠이씨", "workers_cum_t": 60, "final_flag": "O"}]
    out = prorate_cum_workers(mapped, job_alloc)
    assert out[0]["cum_workers_today"] == 30.0
    assert out[0]["prorate_method"] == "uniform_fallback"
    assert out[1]["cum_workers_today"] == 30.0


def test_prorate_zero_when_no_l6_active():
    """l6_main 이 None 인 row 는 prorate skip + cum_workers 안 채워짐."""
    mapped = [{"company": "세보엠이씨", "l6_main": None, "plan_mh": 0}]
    job_alloc = [{"company": "세보엠이씨", "workers_cum_t": 60, "final_flag": "O"}]
    out = prorate_cum_workers(mapped, job_alloc)
    assert "cum_workers_today" not in out[0]


def test_prorate_excludes_final_flag_X():
    """final_flag != 'O' 인 job_allocation 은 SUM 제외."""
    mapped = [{"company": "세보엠이씨", "l6_main": "L6_A", "plan_mh": 100.0}]
    job_alloc = [
        {"company": "세보엠이씨", "workers_cum_t": 50, "final_flag": "X"},
        {"company": "세보엠이씨", "workers_cum_t": 30, "final_flag": "O"},
    ]
    out = prorate_cum_workers(mapped, job_alloc)
    assert out[0]["cum_workers_today"] == 30.0  # 50 무시
