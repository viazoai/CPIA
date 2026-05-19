"""Optimizer 노드의 view builder — daily_reports.jsonb 컬럼 8개 산출."""

from __future__ import annotations

import logging
import statistics
from datetime import date
from typing import Any

from pipeline.db import PGClient

logger = logging.getLogger(__name__)


async def _build_productivity_views(
    pg: PGClient,
    run_id: Any,
    site_id: str,
    today: date,
    forecast: list,
    mapped: list,
) -> dict[str, Any]:
    """§ 01 EVM 산출 — today + by_contractor + by_l6 + by_wp snapshot.

    산식:
      progress      = cum_actual_qty / plan_qty_full
      EV            = progress x plan_mh_full
      PV            = cum_plan_mh
      AC            = cum_actual_mh
      SPI           = EV / PV x 100
      CPI           = EV / AC x 100
    """
    site_evm = await _evm_for_group(pg, site_id, today, group_key="site")
    by_contractor = await _evm_by_group(pg, site_id, today, group_key="company")
    by_l6 = await _evm_by_group(pg, site_id, today, group_key="l6_main")
    by_wp = await _evm_by_group(pg, site_id, today, group_key="wa_l6_company")

    return {
        "today": site_evm,
        "by_contractor": by_contractor,
        "by_l6": by_l6,
        "by_wp": by_wp,
    }


async def _evm_for_group(
    pg: PGClient,
    site_id: str,
    today: date,
    group_key: str,
) -> dict[str, Any]:
    """site 전체 EVM 산출 — group_key='site'.

    컨셉 (2026-05-19 변경): 분모 = 마스터플랜 전체, 분자 = 통합 일보 mapper_activities 전체.
    mapped CTE 제거 — plan side 가 mapper_activities 매핑 결과에 종속되지 않음.
    """
    async with pg._pool.acquire() as con:
        plan_row = await con.fetchrow(
            """
            SELECT
              SUM(am.plan_total_qty * LEAST(1.0, GREATEST(0.0,
                  ($2::date - am.plan_start + 1)::float / NULLIF((am.plan_finish - am.plan_start + 1)::float, 0)
              )))::float AS cum_plan_qty,
              SUM(am.plan_mh_rev2 * LEAST(1.0, GREATEST(0.0,
                  ($2::date - am.plan_start + 1)::float / NULLIF((am.plan_finish - am.plan_start + 1)::float, 0)
              )))::float AS cum_plan_mh,
              SUM(am.plan_total_qty)::float AS plan_qty_full,
              SUM(am.plan_mh_rev2)::float AS plan_mh_full
            FROM activity_master am
            WHERE am.site_id = $1
            """,
            site_id,
            today,
        )

        actual_row = await con.fetchrow(
            """
            SELECT
              COALESCE(SUM(ma.today_cum_qty), 0)::float AS cum_actual_qty,
              COALESCE(SUM(ma.cum_actual_mh_today), 0)::float AS cum_actual_mh
            FROM mapper_activities ma
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pr.report_date = $2
            """,
            site_id,
            today,
        )

    return _compose_evm(plan_row, actual_row)


def _compose_evm(plan_row: Any, actual_row: Any) -> dict[str, Any]:
    """EV/PV/AC/SPI/CPI 산출."""
    if plan_row is None or plan_row["plan_qty_full"] in (None, 0):
        return {"spi": None, "cpi": None, "ev": 0, "pv": 0, "ac": 0}
    plan_qty_full = plan_row["plan_qty_full"] or 0
    plan_mh_full = plan_row["plan_mh_full"] or 0
    cum_plan_mh = plan_row["cum_plan_mh"] or 0
    cum_actual_qty = actual_row["cum_actual_qty"] or 0
    cum_actual_mh = actual_row["cum_actual_mh"] or 0

    progress = cum_actual_qty / plan_qty_full if plan_qty_full else 0
    ev = progress * plan_mh_full
    pv = cum_plan_mh
    ac = cum_actual_mh
    spi = (ev / pv * 100) if pv > 0 else None
    cpi = (ev / ac * 100) if ac > 0 else None

    return {
        "spi": spi,
        "cpi": cpi,
        "ev": ev,
        "pv": pv,
        "ac": ac,
        "cum_actual_qty": cum_actual_qty,
        "plan_qty_full": plan_qty_full,
    }


_PROGRESS_RATIO_SQL = (
    "LEAST(1.0, GREATEST(0.0, "
    "($2::date - am.plan_start + 1)::float / "
    "NULLIF((am.plan_finish - am.plan_start + 1)::float, 0)"
    "))"
)


async def _evm_by_group(
    pg: PGClient,
    site_id: str,
    today: date,
    group_key: str,
) -> dict[str, dict[str, Any]]:
    """group_key (company / l6_main / wa_l6_company) 별 EVM dict.

    컨셉 (2026-05-19): 분모 = activity_master 전체, 분자 = mapper_activities 전체.
    company / l6_main 은 FULL OUTER JOIN — plan/actual 한 쪽에만 있는 group 도 포함.
    wa_l6_company 는 wa 가 mapper 만 가진 키라 mapper anchor 유지.
    """
    if group_key == "company":
        plan_gkey = "am.company"
        actual_gkey = "ma.company"
    elif group_key == "l6_main":
        plan_gkey = "am.l6_main"
        actual_gkey = "ma.l6_main"
    elif group_key == "wa_l6_company":
        return await _evm_by_wa_l6_company(pg, site_id, today)
    else:
        return {}

    sql = f"""
        WITH plan_agg AS (
            SELECT {plan_gkey} AS gkey,
                   SUM(am.plan_total_qty * {_PROGRESS_RATIO_SQL})::float AS cum_plan_qty,
                   SUM(am.plan_mh_rev2 * {_PROGRESS_RATIO_SQL})::float AS cum_plan_mh,
                   SUM(am.plan_total_qty)::float AS plan_qty_full,
                   SUM(am.plan_mh_rev2)::float AS plan_mh_full
            FROM activity_master am
            WHERE am.site_id = $1 AND {plan_gkey} IS NOT NULL
            GROUP BY {plan_gkey}
        ),
        actual_agg AS (
            SELECT {actual_gkey} AS gkey,
                   SUM(COALESCE(ma.today_cum_qty, 0))::float AS cum_actual_qty,
                   SUM(COALESCE(ma.cum_actual_mh_today, 0))::float AS cum_actual_mh
            FROM mapper_activities ma
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pr.report_date = $2 AND {actual_gkey} IS NOT NULL
            GROUP BY {actual_gkey}
        )
        SELECT COALESCE(p.gkey, a.gkey) AS gkey,
               COALESCE(p.cum_plan_qty, 0)::float AS cum_plan_qty,
               COALESCE(p.cum_plan_mh, 0)::float AS cum_plan_mh,
               COALESCE(p.plan_qty_full, 0)::float AS plan_qty_full,
               COALESCE(p.plan_mh_full, 0)::float AS plan_mh_full,
               COALESCE(a.cum_actual_qty, 0)::float AS cum_actual_qty,
               COALESCE(a.cum_actual_mh, 0)::float AS cum_actual_mh
        FROM plan_agg p
        FULL OUTER JOIN actual_agg a USING (gkey)
    """
    async with pg._pool.acquire() as con:
        rows = await con.fetch(sql, site_id, today)

    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = r["gkey"]
        if not key:
            continue
        plan_row = {
            "cum_plan_qty": r["cum_plan_qty"],
            "cum_plan_mh": r["cum_plan_mh"],
            "plan_qty_full": r["plan_qty_full"],
            "plan_mh_full": r["plan_mh_full"],
        }
        actual_row = {
            "cum_actual_qty": r["cum_actual_qty"],
            "cum_actual_mh": r["cum_actual_mh"],
        }
        out[key] = _compose_evm(plan_row, actual_row)
    return out


async def _evm_by_wa_l6_company(
    pg: PGClient,
    site_id: str,
    today: date,
) -> dict[str, dict[str, Any]]:
    """wa_l6_company group — wa 는 mapper 전용 키라 mapper anchor 유지."""
    sql = f"""
        SELECT ma.wa AS wa, ma.l6_main AS l6_main, ma.company AS company,
               COALESCE(SUM(am.plan_total_qty * {_PROGRESS_RATIO_SQL}), 0)::float AS cum_plan_qty,
               COALESCE(SUM(am.plan_mh_rev2 * {_PROGRESS_RATIO_SQL}), 0)::float AS cum_plan_mh,
               COALESCE(SUM(am.plan_total_qty), 0)::float AS plan_qty_full,
               COALESCE(SUM(am.plan_mh_rev2), 0)::float AS plan_mh_full,
               COALESCE(SUM(ma.today_cum_qty), 0)::float AS cum_actual_qty,
               COALESCE(SUM(ma.cum_actual_mh_today), 0)::float AS cum_actual_mh
        FROM mapper_activities ma
        JOIN pipeline_runs pr USING (run_id)
        LEFT JOIN activity_master am
          ON am.company = ma.company
          AND am.l6_main = ma.l6_main
          AND am.site_id = pr.site_id
        WHERE pr.site_id = $1 AND pr.report_date = $2
        GROUP BY ma.wa, ma.l6_main, ma.company
    """
    async with pg._pool.acquire() as con:
        rows = await con.fetch(sql, site_id, today)

    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = _wp_id_of(r["wa"], r["l6_main"], r["company"])
        if not key:
            continue
        plan_row = {
            "cum_plan_qty": r["cum_plan_qty"],
            "cum_plan_mh": r["cum_plan_mh"],
            "plan_qty_full": r["plan_qty_full"],
            "plan_mh_full": r["plan_mh_full"],
        }
        actual_row = {
            "cum_actual_qty": r["cum_actual_qty"],
            "cum_actual_mh": r["cum_actual_mh"],
        }
        out[key] = _compose_evm(plan_row, actual_row)
    return out


async def _build_kpi(
    pg: PGClient,
    site_id: str,
    today: date,
    productivity: dict[str, Any],
) -> dict[str, Any]:
    """§ 01 헤더 KPI — productivity_today, target, delay_days, expected_completion."""
    site_evm = productivity.get("today", {}) or {}
    cpi = site_evm.get("cpi")
    spi = site_evm.get("spi")

    async with pg._pool.acquire() as con:
        d_row = await con.fetchrow(
            """
            SELECT AVG(delay_days)::float AS delay,
                   MAX(expected_completion) AS expected_completion
            FROM forecasts f JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pr.report_date = $2
            """,
            site_id,
            today,
        )
    delay = d_row["delay"] if d_row else None
    exp = d_row["expected_completion"] if d_row else None
    return {
        "productivity_today": round(cpi or 0, 2),
        "spi": round(spi or 0, 2),
        "cpi": round(cpi or 0, 2),
        "target_productivity": 100,
        "delay_days": round(delay or 0),
        "expected_completion": exp.isoformat() if exp else None,
    }


def _bar_status(cpi: float) -> str:
    """공통: CPI → status 라벨."""
    if cpi >= 90:
        return "normal"
    if cpi >= 80:
        return "caution"
    return "risk"


def _build_contractor_bars(productivity: dict[str, Any]) -> list[dict[str, Any]]:
    """by_contractor dict → BarItem[] sorted by CPI desc."""
    by_c = productivity.get("by_contractor", {}) or {}
    return sorted(
        [
            {
                "label": c,
                "value": round(d.get("cpi") or 0, 1),
                "status": _bar_status(d.get("cpi") or 0),
            }
            for c, d in by_c.items()
        ],
        key=lambda x: -x["value"],
    )


def _build_trade_bars(productivity: dict[str, Any]) -> list[dict[str, Any]]:
    """by_l6 dict -> BarItem[]."""
    by_l = productivity.get("by_l6", {}) or {}
    return sorted(
        [
            {
                "label": l,
                "value": round(d.get("cpi") or 0, 1),
                "status": _bar_status(d.get("cpi") or 0),
            }
            for l, d in by_l.items()
        ],
        key=lambda x: -x["value"],
    )


def _compute_impact_p90(raw_impacts: list[float]) -> float:
    """P90 (90 percentile) 산출. 짧으면 max fallback, 빈 list 면 1.0."""
    if not raw_impacts:
        return 1.0
    if len(raw_impacts) >= 10:
        return statistics.quantiles(raw_impacts, n=10)[8]
    return max(raw_impacts)


def _normalize_impact(raw_impact: float, p90: float) -> float:
    """raw -> 0~100 (P90 기준 ceiling)."""
    if p90 <= 0 or not raw_impact:
        return 0.0
    return min(100.0, raw_impact / p90 * 100.0)


def _quadrant_label(productivity: float, impact: float) -> str:
    """4분면 — risk / caution / watch / safe."""
    low_prod = productivity < 80
    high_impact = impact >= 50
    if low_prod and high_impact:
        return "risk"
    if low_prod:
        return "caution"
    if high_impact:
        return "watch"
    return "safe"


def _wp_id_of(
    wa: Optional[str], l6_main: Optional[str], company: Optional[str]
) -> str:
    """WP 식별자 — kebab-case (wa-l6_main-company)."""

    def _kebab(v: Optional[str]) -> str:
        return (v or "unknown").lower().replace(" ", "-")

    return f"{_kebab(wa)}-{_kebab(l6_main)}-{_kebab(company)}"


async def _build_quadrant(
    pg: PGClient,
    site_id: str,
    today: date,
    productivity: dict[str, Any],
) -> list[dict[str, Any]]:
    """4분면 산점도 점 — (wa, l6, company) per WP."""
    by_wp = productivity.get("by_wp", {}) or {}
    async with pg._pool.acquire() as con:
        impact_rows = await con.fetch(
            """
            SELECT ma.wa, ma.l6_main, ma.company,
                   (SUM(ma.plan_total_qty) * AVG(ma.plan_mh))::float AS raw_impact
            FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pr.report_date = $2
            GROUP BY ma.wa, ma.l6_main, ma.company
            """,
            site_id,
            today,
        )
    raw_impacts = [r["raw_impact"] for r in impact_rows if r["raw_impact"]]
    p90 = _compute_impact_p90(raw_impacts)

    out: list[dict[str, Any]] = []
    for r in impact_rows:
        wp_id = _wp_id_of(r["wa"], r["l6_main"], r["company"])
        wp_evm = by_wp.get(wp_id, {}) or {}
        cpi = wp_evm.get("cpi") or 0.0
        impact = _normalize_impact(r["raw_impact"], p90)
        out.append(
            {
                "wp_id": wp_id,
                "wp_name": f"{r['wa'] or ''} {r['l6_main'] or ''}".strip(),
                "trade": r["l6_main"] or "",
                "productivity": round(cpi, 1),
                "impact": round(impact, 1),
                "quadrant": _quadrant_label(cpi, impact),
                "size": max(30, min(120, int(impact))),
            }
        )
    return out


async def _build_wp_summary(
    pg: PGClient,
    site_id: str,
    today: date,
    productivity: dict[str, Any],
    quadrant_jsonb: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """WP 표 — quadrant 와 같은 단위 + baseline + status.

    baseline / bp_name / progress / dates 는 후속 task 에서 보강.
    본 task 는 quadrant 기반 status 만.
    """
    out: list[dict[str, Any]] = []
    for q in quadrant_jsonb:
        cpi = q.get("productivity") or 0
        status = "normal" if cpi >= 90 else "caution" if cpi >= 80 else "risk"
        out.append(
            {
                **q,
                "baseline": 90,
                "status": status,
                "bp_name": "",
                "progress_pct": 0,
                "start_date": "",
                "end_date": "",
            }
        )
    return out


def _merge_curves(
    planned: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    recovery: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """date 단위 datapoint 합성 — planned / actual / recovery 키 동시 노출.

    cum_plan_qty + cum_actual_qty (누적 변환) + recovery_days 합성.
    forecast 는 호출 측에서 마지막 actual 기준 linear 연장 추가.
    """
    by_date: dict[str, dict[str, Any]] = {}
    for p in planned:
        d = p["date"]
        key = d.isoformat() if hasattr(d, "isoformat") else str(d)
        by_date.setdefault(key, {"date": key})["planned"] = p.get("cum_plan_qty") or 0
    # actual 은 daily delta → cumulative 변환
    cum = 0.0
    for a in sorted(actual, key=lambda x: x["report_date"]):
        cum += float(a.get("day_qty") or 0)
        d = a["report_date"]
        key = d.isoformat() if hasattr(d, "isoformat") else str(d)
        by_date.setdefault(key, {"date": key})["actual"] = cum
    if recovery:
        for r in recovery:
            d = r.get("date")
            if d is None:
                continue
            key = d.isoformat() if hasattr(d, "isoformat") else str(d)
            by_date.setdefault(key, {"date": key})["recovery_days"] = r.get("recovery_days")
    return sorted(by_date.values(), key=lambda x: x["date"])


def _extend_forecast(merged: list[dict[str, Any]], days_ahead: int = 30) -> list[dict[str, Any]]:
    """현 추세 연장 — 마지막 actual rate x remaining days. 결정론적 linear.

    merged 의 마지막 actual 기준 rate 계산 → days_ahead 만큼 forecast 추가.
    """
    actual_points = [m for m in merged if m.get("actual") is not None]
    if len(actual_points) < 2:
        return merged
    last = actual_points[-1]
    prev = actual_points[-2]
    from datetime import date as _date, timedelta
    last_dt = _date.fromisoformat(last["date"]) if isinstance(last["date"], str) else last["date"]
    prev_dt = _date.fromisoformat(prev["date"]) if isinstance(prev["date"], str) else prev["date"]
    days = max(1, (last_dt - prev_dt).days)
    rate = (last["actual"] - prev["actual"]) / days
    last["forecast"] = last["actual"]  # forecast 시작점 = 마지막 actual
    out = list(merged)
    for i in range(1, days_ahead + 1):
        next_dt = last_dt + timedelta(days=i)
        out.append({
            "date": next_dt.isoformat(),
            "forecast": last["actual"] + rate * i,
        })
    return out


async def _build_s_curve(
    pg: PGClient,
    site_id: str,
    today: date,
) -> list[dict[str, Any]]:
    """planned/actual/forecast/recovery 4 곡선 unified datapoint list."""
    async with pg._pool.acquire() as con:
        planned = await con.fetch(
            """
            SELECT gs.date::date AS date,
                   SUM(am.plan_total_qty * LEAST(1.0, GREATEST(0.0,
                       (gs.date::date - am.plan_start + 1)::float
                       / NULLIF((am.plan_finish - am.plan_start + 1)::float, 0)
                   )))::float AS cum_plan_qty
            FROM activity_master am
            CROSS JOIN LATERAL (
                SELECT d AS date
                FROM generate_series(
                    (SELECT MIN(plan_start) FROM activity_master WHERE site_id = $1),
                    $2::date,
                    '1 day'::interval
                ) AS d
            ) gs
            WHERE am.site_id = $1
            GROUP BY gs.date ORDER BY gs.date
            """,
            site_id,
            today,
        )
        actual = await con.fetch(
            """
            SELECT report_date, SUM(today_qty)::float AS day_qty
            FROM mapped_history WHERE site_id = $1 AND report_date <= $2
            GROUP BY report_date ORDER BY report_date
            """,
            site_id,
            today,
        )
        rp_row = await con.fetchrow(
            """
            SELECT oa.recovery_pattern FROM optimizer_advice oa
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 ORDER BY oa.created_at DESC LIMIT 1
            """,
            site_id,
        )
    recovery = (rp_row["recovery_pattern"] if rp_row else None) or []
    merged = _merge_curves(
        [dict(r) for r in planned],
        [dict(r) for r in actual],
        recovery if isinstance(recovery, list) else [],
    )
    return _extend_forecast(merged, days_ahead=30)


def _build_optimizer_view(
    advice_rows: list[dict[str, Any]],
    forecast: list[dict[str, Any]],
    mapped: list[dict[str, Any]],
) -> dict[str, Any]:
    """§ 02 by_wp dict — 진단/유사사례/권고/상세 6칸.

    advice = optimizer_advice 의 row. forecast = forecasts 의 row (wa lookup).
    """
    by_wp: dict[str, dict[str, Any]] = {}
    for advice in advice_rows:
        # wa lookup — forecast 에서 (company, l6_main) 매칭
        matched_f = next(
            (f for f in forecast
             if f.get("company") == advice.get("company")
             and f.get("l6_main") == advice.get("l6_main")),
            None,
        )
        if matched_f is None:
            continue
        wa = matched_f.get("wa")
        wp_id = _wp_id_of(wa, advice.get("l6_main"), advice.get("company"))

        # 유사 사례 자연어 변환
        similar_cases = []
        for c in (advice.get("degradation_cases") or []):
            activities = c.get("activities") or []
            conditions = c.get("conditions") or ""
            productivity = c.get("productivity") or 0
            recovery = c.get("recovery") or {}
            rd = recovery.get("recovery_days") if isinstance(recovery, dict) else None
            similar_cases.append({
                "date": c.get("date") or "",
                "description": f"{conditions} - {activities[0] if activities else ''}, 생산성 {productivity:.1f}",
                "outcome": f"{rd}일 후 회복" if rd is not None else "미회복",
            })

        # 권고 text 만 추출
        recs_raw = advice.get("recommendations") or []
        recommendations: list[str] = []
        for r in recs_raw:
            if isinstance(r, dict):
                recommendations.append(r.get("text") or "")
            else:
                recommendations.append(str(r))

        # 6칸 details
        rp = advice.get("recovery_pattern") or []
        rd_vals = [p.get("recovery_days") for p in rp if isinstance(p, dict) and p.get("recovery_days") is not None]
        avg_rd: Optional[float] = (sum(rd_vals) / len(rd_vals)) if rd_vals else None
        rdist = advice.get("recovery_distribution") or {}
        rdist_text = " / ".join(f"{k}: {v}건" for k, v in rdist.items()) if isinstance(rdist, dict) else ""

        details = [
            {"label": "위험 평가", "value": matched_f.get("risk_level") or "—"},
            {"label": "진단 대상", "value": f"{advice.get('company') or ''} · {advice.get('l6_main') or ''}"},
            {"label": "유사 사례 수", "value": f"{len(advice.get('degradation_cases') or [])}건"},
            {"label": "평균 회복 일수", "value": f"{avg_rd:.1f}일" if avg_rd is not None else "—"},
            {"label": "회복 분포", "value": rdist_text or "—"},
            {"label": "일정 영향", "value": f"{round(matched_f.get('delay_days') or 0)}일 지연"},
        ]

        by_wp[wp_id] = {
            "diagnosis": advice.get("diagnosis") or "",
            "similar_cases": similar_cases,
            "recommendations": recommendations,
            "details": details,
        }

    default_wp_id = next(iter(by_wp.keys()), None)
    return {"by_wp": by_wp, "default_wp_id": default_wp_id}
