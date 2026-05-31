"""verify_seed_numbers.py — 적재 전 결정론적 숫자검증 (DB write 0, LLM 0).

설계: docs/superpowers/specs/2026-05-29-cpia-reseed-v2-per-unit-seeding-design.md §2

activity_master(plan)만 읽어 v2 시딩 시계열(_v2_activity_series)을 계산하고,
월별로 (a) 단위별 시공량 actual vs plan, (b) site 공정율(mh가중) actual vs plan,
(c) Σmh actual vs plan 을 대조. 마지막에 활동별 불변식(완료=총합보존·진행중 엔벨로프) 점검.

DB 에 아무것도 쓰지 않는다 — 시딩 로직의 숫자만 검증 ("바로 적재하지 말고 우선 숫자 검증").

사용:
  cd pipeline && set -a; source ../.env.local; set +a
  PYTHONPATH=$PWD/.. uv run python ../scripts/verify_seed_numbers.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.db import PGClient  # noqa: E402
from scripts.seed_dummy_year import _v2_activity_series  # noqa: E402

DEFAULT_SITE_ID = "m15x-ph3-ibl"
DEFAULT_PG_URL = "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia"
WINDOW_START = date(2024, 4, 11)
WINDOW_END = date(2025, 9, 24)


def _month_ends(start: date, end: date) -> list[date]:
    """start~end 사이 각 월말(마지막은 end 로 cap)."""
    out: list[date] = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        # 다음달 1일 - 1일 = 이번달 말일
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        last = date(ny, nm, 1) - timedelta(days=1)
        out.append(min(last, end))
        y, m = ny, nm
    return out


def _ratio_at(series: dict[str, Any], plan_start: date, t: date) -> tuple[float, float]:
    """t 시점 (actual_cum_ratio, plan_cum_ratio). plan 완료=total_days, actual 완료=eff_days.

    지각 활동: idx >= total_days (plan=1.0 완료) 인데 idx < eff_days (actual<1.0) → 갭.
    """
    idx = (t - plan_start).days
    if idx < 0:
        return 0.0, 0.0
    pt = series["plan_total"] or 1.0
    total_days = series["total_days"]
    eff_days = series["eff_days"]
    p = 1.0 if idx >= total_days else series["plan_cum"][idx] / pt
    a = 1.0 if idx >= eff_days else series["cum_qty"][idx] / pt
    return a, p


def _mh_cum_at(series: dict[str, Any], plan_start: date, t: date) -> tuple[float, float]:
    """t 시점 (actual_mh_cum, plan_mh_cum)."""
    idx = (t - plan_start).days
    if idx < 0:
        return 0.0, 0.0
    plan_mh = series["plan_mh"]
    pt = series["plan_total"] or 1.0
    total_days = series["total_days"]
    eff_days = series["eff_days"]
    a = sum(series["mh_daily"]) if idx >= eff_days else series["cum_mh"][idx]
    p = plan_mh if idx >= total_days else plan_mh * (series["plan_cum"][idx] / pt)
    return a, p


async def amain() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--site", default=DEFAULT_SITE_ID)
    p.add_argument("--start", default=WINDOW_START.isoformat())
    p.add_argument("--end", default=WINDOW_END.isoformat())
    p.add_argument("--trades", nargs="+", default=["건축", "토목"])
    p.add_argument("--pg-url", default=os.environ.get("POSTGRES_URL", DEFAULT_PG_URL))
    args = p.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    print(f"=== verify_seed_numbers: {start}~{end} site={args.site} trades={args.trades} (DB write 0) ===\n")

    pg = PGClient(args.pg_url)
    await pg.connect()
    try:
        rows = await pg._pool.fetch(
            """
            SELECT wa, company, l6_main, l7_5_activity, unit,
                   plan_total_qty, plan_mh_rev2, plan_wv, plan_start, plan_finish, l5_disc
            FROM activity_master
            WHERE site_id = $1 AND l5_disc = ANY($2::text[])
              AND plan_start IS NOT NULL AND plan_finish IS NOT NULL
              AND plan_total_qty IS NOT NULL AND plan_total_qty > 0
              AND wa IS NOT NULL AND l6_main IS NOT NULL AND company IS NOT NULL
            ORDER BY plan_start
            """,
            args.site,
            args.trades,
        )
    finally:
        await pg.close()

    acts: list[dict[str, Any]] = []
    for r in rows:
        am = dict(r)
        # PG numeric → Decimal. float 연산 위해 캐스팅.
        for k in ("plan_total_qty", "plan_mh_rev2", "plan_wv"):
            am[k] = float(am[k]) if am[k] is not None else 0.0
        s = _v2_activity_series(am)
        am["_series"] = s
        acts.append(am)
    print(f"활동 {len(acts)}건 (l7_5 행) 시계열 계산 완료\n")

    # ---- 월별 검증 ----
    print(
        f"{'월':<9}{'공정율 act':>11}{'공정율 plan':>12}{'gap%pt':>8}"
        f"{'Σmh act/plan':>15}{'월qty act/plan':>15}"
    )
    print("-" * 70)
    total_w = sum((a["plan_wv"] or 0) * (a["plan_mh_rev2"] or 0) for a in acts) or 1.0
    monthly_unit_rows: list[str] = []
    for me in _month_ends(start, end):
        m_start = date(me.year, me.month, 1)
        w_act = w_plan = 0.0
        mh_act = mh_plan = 0.0
        munit_a: dict[str, float] = defaultdict(float)
        munit_p: dict[str, float] = defaultdict(float)
        for a in acts:
            s = a["_series"]
            ps, unit = a["plan_start"], a["unit"]
            w = (a["plan_wv"] or 0) * (a["plan_mh_rev2"] or 0)
            ar, pr = _ratio_at(s, ps, me)
            w_act += w * ar
            w_plan += w * pr
            am_, pm_ = _mh_cum_at(s, ps, me)
            mh_act += am_
            mh_plan += pm_
            # 그 달 내 일별 qty 합 (actual=eff_days, plan=total_days 범위)
            td, ed = s["total_days"], s["eff_days"]
            lo_i = max(0, (m_start - ps).days, (start - ps).days)
            hi_i = min(ed - 1, (me - ps).days)
            for di in range(lo_i, hi_i + 1):
                munit_a[unit] += s["actual_daily"][di]
                if di < td:
                    munit_p[unit] += s["plan_daily"][di]
        pa = w_act / total_w * 100
        pp = w_plan / total_w * 100
        mh_ratio = (mh_act / mh_plan) if mh_plan > 0 else 0.0
        tot_ma = sum(munit_a.values())
        tot_mp = sum(munit_p.values())
        q_ratio = (tot_ma / tot_mp) if tot_mp > 0 else 0.0
        print(
            f"{me.isoformat()[:7]:<9}{pa:>10.1f}%{pp:>11.1f}%{pa - pp:>7.1f} "
            f"{mh_ratio:>13.2f}x {q_ratio:>13.2f}x"
        )
        # 단위별(그 달) — 혼재 큰 달만 상세
        unit_detail = " ".join(
            f"{u}:{(munit_a[u] / munit_p[u]):.2f}x" for u in sorted(munit_p) if munit_p[u] > 0
        )
        monthly_unit_rows.append(f"  {me.isoformat()[:7]} 단위별 act/plan: {unit_detail}")

    print("\n[단위별 월 actual/plan 비]")
    for line in monthly_unit_rows:
        print(line)

    # ---- 9/24 시점 불변식 ----
    print("\n[9/24 시점 불변식 점검]")
    n_delayed = sum(1 for a in acts if a["_series"]["ext_days"] > 0)
    w_delayed = sum(
        (a["plan_wv"] or 0) * (a["plan_mh_rev2"] or 0) for a in acts if a["_series"]["ext_days"] > 0
    )
    print(f"  지각완료(ext>0) 활동: {n_delayed}/{len(acts)}건, 가중 {w_delayed / total_w * 100:.0f}%")

    def _eff_finish(a: dict[str, Any]) -> date:
        return a["plan_start"] + timedelta(days=a["_series"]["eff_days"] - 1)

    actual_done = [a for a in acts if _eff_finish(a) <= end]
    active = [a for a in acts if a["plan_start"] <= end and _eff_finish(a) > end]
    notstarted = [a for a in acts if a["plan_start"] > end]

    # 보존: actual 완료 활동 Σactual==plan_total ±1%
    comp_fail = []
    for a in actual_done:
        sa = sum(a["_series"]["actual_daily"])
        pt = a["plan_total_qty"]
        if pt > 0 and abs(sa - pt) / pt > 0.01:
            comp_fail.append((a["company"], a["l6_main"], sa, pt))
    print(
        f"  actual 완료 {len(actual_done)}건: 총합보존(±1%) 통과 "
        f"{len(actual_done) - len(comp_fail)} / 실패 {len(comp_fail)}"
    )
    for c in comp_fail[:5]:
        print(f"    FAIL {c[0]} {c[1]}: Σactual={c[2]:.1f} vs plan={c[3]:.1f}")

    # 활성(미완료): on-plan 진행중 vs 지각(plan 완료인데 actual 미달)
    onplan, late = [], []
    for a in active:
        idx = (end - a["plan_start"]).days
        (late if idx >= a["_series"]["total_days"] else onplan).append(a)

    def _bands(group: list[dict[str, Any]]) -> list[float]:
        rs = []
        for a in group:
            ar, pr = _ratio_at(a["_series"], a["plan_start"], end)
            if pr > 0:
                rs.append(ar / pr)
        return sorted(rs)

    for label, group in (("진행중(plan 내)", onplan), ("지각(plan 완료·actual 미달)", late)):
        rs = _bands(group)
        if rs:
            n = len(rs)
            print(
                f"  {label} {len(group)}건: actual/plan "
                f"min={rs[0]:.2f} p50={rs[n // 2]:.2f} max={rs[-1]:.2f} 평균={sum(rs) / n:.2f}"
            )
    print(f"  미착수 {len(notstarted)}건")

    # site 9/24 최종
    w_act = sum(
        (a["plan_wv"] or 0) * (a["plan_mh_rev2"] or 0) * _ratio_at(a["_series"], a["plan_start"], end)[0]
        for a in acts
    )
    w_plan = sum(
        (a["plan_wv"] or 0) * (a["plan_mh_rev2"] or 0) * _ratio_at(a["_series"], a["plan_start"], end)[1]
        for a in acts
    )
    print(
        f"\n  → 9/24 site 공정율: actual {w_act / total_w * 100:.1f}% vs plan {w_plan / total_w * 100:.1f}% "
        f"(gap {(w_act - w_plan) / total_w * 100:.1f}%pt)"
    )


if __name__ == "__main__":
    asyncio.run(amain())
