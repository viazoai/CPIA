"""Step C-b: 9-25 prototype 새 4단 산식 + daily_reports.jsonb 덮어쓰기.

산식 (사용자 결정 2026-05-21):
  인당 생산성 = today_qty / assigned_workers  (workers=0 -> 1 fallback)
  공종별 (L7.5) 생산성 = 인당 / (master plan_total_qty / (master plan_mh / 8)) x 100
  업체별 = wv-median + simple-mean 병렬 (wv = master plan_mh)
  현장 = 업체별 wv-median + simple-mean 병렬
  impact_raw = (100 - productivity) x plan_mh
  impact_normalized = (impact_raw / max) x 100   (0-100 UI 호환)

덮어쓰기 대상 (daily_reports 9-25 is_mock=false):
  kpi_jsonb / productivity_jsonb / contractor_bars_jsonb / trade_bars_jsonb /
  quadrant_jsonb / wp_summary_jsonb
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

DSN = os.environ.get(
    "POSTGRES_URL",
    "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia",
)
PROTO_DATE_STR = "2025-09-25"


def status_of(pct: float) -> str:
    if pct >= 90:
        return "normal"
    if pct >= 70:
        return "caution"
    return "risk"


def quadrant_of(prod: float, impact: float) -> str:
    # X: productivity (낮을수록 위험), Y: impact (높을수록 위험)
    if prod < 70 and impact >= 50:
        return "risk"
    if prod < 70:
        return "caution"
    if impact >= 50:
        return "watch"
    return "safe"


def weighted_median(values: list[float], weights: list[float]) -> float:
    if not values:
        return 0
    pairs = sorted(zip(values, weights))
    total = sum(weights)
    if total == 0:
        return sum(values) / len(values)
    cum = 0.0
    for v, w in pairs:
        cum += w
        if cum >= total / 2:
            return v
    return pairs[-1][0]


async def main() -> None:
    from datetime import date as _date

    proto = _date.fromisoformat(PROTO_DATE_STR)
    pg = await asyncpg.connect(DSN)
    try:
        # 사용자 통찰 (2026-05-21): seed_dummy_year.py 와 동일 로직 — today_qty/workers
        # 를 마스터 daily_qty 기반 noise 로 재산정해야 산식 정상 (단위 미스매치 회피).
        # 같은 (site, company, l6, l7_5) 의 master row 합산 -> plan_start/finish/qty/mh.
        # 9-25 가 (ps, pf) 안인 row 만 산식 적용.
        rows = await pg.fetch(
            """
            SELECT ma.id, pr.site_id, ma.run_id, ma.company, ma.l6_main, ma.l7_5_activity,
                   ma.unit, ma.zone, m.ps AS plan_start, m.pf AS plan_finish,
                   m.qty AS plan_total_qty, m.mh AS plan_mh
            FROM mapper_activities ma
            JOIN pipeline_runs pr USING (run_id)
            LEFT JOIN LATERAL (
                SELECT MIN(plan_start) AS ps, MAX(plan_finish) AS pf,
                       SUM(plan_total_qty) AS qty, SUM(plan_mh_rev2) AS mh
                FROM activity_master am
                WHERE am.site_id = pr.site_id AND am.company = ma.company
                  AND am.l6_main = ma.l6_main AND am.l7_5_activity = ma.l7_5_activity
            ) m ON TRUE
            WHERE ma.report_date = $1
              AND ma.l7_5_activity IS NOT NULL
              AND m.ps IS NOT NULL AND $1 BETWEEN m.ps AND m.pf
            """,
            proto,
        )
        print(f"산식 적용 row (9-25 plan 기간 안): {len(rows)}")

        import random

        rng = random.Random(20260521)

        # row 별 산식 — today_qty/workers 도 마스터 daily 기반 noise 로 재산정
        l75_items = []
        for r in rows:
            plan_qty = float(r["plan_total_qty"] or 0)
            plan_mh = float(r["plan_mh"] or 0)
            total_days = (r["plan_finish"] - r["plan_start"]).days + 1
            if total_days <= 0 or plan_qty <= 0 or plan_mh <= 0:
                continue

            daily_qty_master = plan_qty / total_days
            daily_workers_master = max(1.0, plan_mh / total_days / 8.0)

            # 더미 빌더 noise (사용자 통찰 — seed_dummy_year.py line 220 의 _noise)
            noise_q = 0.85 + 0.30 * rng.random()  # 0.85 ~ 1.15
            noise_w = 0.90 + 0.20 * rng.random()  # 0.90 ~ 1.10
            today_qty_sim = daily_qty_master * noise_q
            workers_sim = max(1.0, daily_workers_master * noise_w)

            perperson = today_qty_sim / workers_sim
            master_perperson = daily_qty_master / daily_workers_master
            productivity_raw = (
                (perperson / master_perperson * 100) if master_perperson > 0 else 0
            )
            productivity = min(productivity_raw, 150.0)
            impact_raw = max(0, 100 - productivity) * plan_mh

            l75_items.append(
                {
                    "id": r["id"],
                    "site_id": r["site_id"],
                    "company": r["company"],
                    "l6_main": r["l6_main"],
                    "l7_5_activity": r["l7_5_activity"],
                    "unit": r["unit"],
                    "today_qty": today_qty_sim,
                    "workers": workers_sim,
                    "plan_total_qty": plan_qty,
                    "plan_mh": plan_mh,
                    "total_days": total_days,
                    "daily_qty_master": daily_qty_master,
                    "perperson": perperson,
                    "master_perperson": master_perperson,
                    "productivity": productivity,
                    "impact_raw": impact_raw,
                    "zone": r["zone"],
                }
            )

        # impact 정규화
        max_impact = max((it["impact_raw"] for it in l75_items), default=1) or 1
        for it in l75_items:
            it["impact"] = it["impact_raw"] / max_impact * 100

        # 업체별 집계
        by_company: dict[str, list[dict]] = defaultdict(list)
        for it in l75_items:
            by_company[it["company"]].append(it)

        company_prod = {}
        for company, items in by_company.items():
            prods = [it["productivity"] for it in items]
            wvs = [it["plan_mh"] for it in items]
            company_prod[company] = {
                "simple_mean": (sum(prods) / len(prods)) if prods else 0,
                "wv_median": weighted_median(prods, wvs),
                "n": len(prods),
                "sum_wv": sum(wvs),
            }

        # 공종 (l6_main) 별 집계
        by_l6: dict[str, list[dict]] = defaultdict(list)
        for it in l75_items:
            by_l6[it["l6_main"]].append(it)
        l6_prod = {}
        for l6, items in by_l6.items():
            prods = [it["productivity"] for it in items]
            wvs = [it["plan_mh"] for it in items]
            l6_prod[l6] = {
                "simple_mean": (sum(prods) / len(prods)) if prods else 0,
                "wv_median": weighted_median(prods, wvs),
                "n": len(prods),
                "sum_wv": sum(wvs),
            }

        # 현장 (전체)
        all_company_mean = [v["simple_mean"] for v in company_prod.values()]
        all_company_wvmed = [v["wv_median"] for v in company_prod.values()]
        all_company_wv = [v["sum_wv"] for v in company_prod.values()]
        site_simple_mean = (
            sum(all_company_mean) / len(all_company_mean) if all_company_mean else 0
        )
        site_wv_median = weighted_median(all_company_wvmed, all_company_wv)

        # productivity_today: wv_median 우선 (사용자 권장)
        productivity_today = round(site_wv_median, 1)
        productivity_today_simple = round(site_simple_mean, 1)

        # ─── UI 컬럼 생성 ───
        contractor_bars = [
            {
                "label": company,
                "value": round(v["wv_median"], 1),  # wv-median 우선
                "status": status_of(v["wv_median"]),
                "baseline": 100,
            }
            for company, v in sorted(
                company_prod.items(), key=lambda x: -x[1]["wv_median"]
            )
        ]

        trade_bars = [
            {
                "label": l6,
                "value": round(v["wv_median"], 1),
                "status": status_of(v["wv_median"]),
                "baseline": 100,
            }
            for l6, v in sorted(l6_prod.items(), key=lambda x: -x[1]["wv_median"])
        ]

        quadrant = [
            {
                "wp_id": f"WP-{it['id']}",
                "wp_name": it["l7_5_activity"],
                "trade": it["l6_main"],
                "productivity": round(it["productivity"], 1),
                "impact": round(it["impact"], 1),
                "quadrant": quadrant_of(it["productivity"], it["impact"]),
                "size": round((it["plan_total_qty"] or 1) / 10, 1),
            }
            for it in l75_items
        ]

        wp_summary = [
            {
                "wp_id": f"WP-{it['id']}",
                "wp_name": it["l7_5_activity"],
                "trade": it["l6_main"],
                "bp_name": it["company"],
                "start_date": "2025-09-01",
                "end_date": "2025-12-31",
                "progress_pct": round(
                    min(100, (it["today_qty"] / max(it["plan_total_qty"], 1)) * 100), 1
                ),
                "productivity": round(it["productivity"], 1),
                "impact": round(it["impact"], 1),
                "baseline": 100,
                "status": status_of(it["productivity"]),
            }
            for it in l75_items
        ]

        kpi = {
            "productivity_today": productivity_today,
            "productivity_today_simple_mean": productivity_today_simple,
            "productivity_history_diff": 0,
            "delay_days": 0,
            "expected_completion": "2026-03-31",
            "recoverable_productivity": round(max(0, 100 - productivity_today), 1),
            "target_productivity": 100,
            "recovery_days": 0,
            "recovered_completion": "2026-03-31",
        }

        productivity = {
            "site": {
                "wv_median": round(site_wv_median, 2),
                "simple_mean": round(site_simple_mean, 2),
                "n_companies": len(company_prod),
                "n_l75": len(l75_items),
            },
            "by_company": {
                c: {
                    "wv_median": round(v["wv_median"], 2),
                    "simple_mean": round(v["simple_mean"], 2),
                    "n_l75": v["n"],
                    "sum_wv": round(v["sum_wv"], 1),
                }
                for c, v in company_prod.items()
            },
            "by_l6": {
                l6: {
                    "wv_median": round(v["wv_median"], 2),
                    "simple_mean": round(v["simple_mean"], 2),
                    "n_l75": v["n"],
                    "sum_wv": round(v["sum_wv"], 1),
                }
                for l6, v in l6_prod.items()
            },
        }

        # 통계 출력
        print("\n=== 산식 결과 ===")
        print(f"현장 wv_median: {site_wv_median:.1f}%")
        print(f"현장 simple_mean: {site_simple_mean:.1f}%")
        print(f"업체 수: {len(company_prod)}, L7.5 row: {len(l75_items)}")
        print(f"공종(l6) 수: {len(l6_prod)}")
        print("\n업체별:")
        for c, v in sorted(company_prod.items(), key=lambda x: -x[1]["wv_median"]):
            print(
                f"  {c:<12} wv_med={v['wv_median']:.1f} mean={v['simple_mean']:.1f} n={v['n']}"
            )

        # 덮어쓰기
        print("\n=== daily_reports.jsonb 9-25 덮어쓰기 ===")
        result = await pg.execute(
            """
            UPDATE daily_reports
            SET kpi_jsonb = $1::jsonb,
                productivity_jsonb = $2::jsonb,
                contractor_bars_jsonb = $3::jsonb,
                trade_bars_jsonb = $4::jsonb,
                quadrant_jsonb = $5::jsonb,
                wp_summary_jsonb = $6::jsonb
            WHERE report_date = $7 AND is_mock = false
            """,
            json.dumps(kpi),
            json.dumps(productivity),
            json.dumps(contractor_bars),
            json.dumps(trade_bars),
            json.dumps(quadrant),
            json.dumps(wp_summary),
            proto,
        )
        print(f"UPDATE: {result}")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
