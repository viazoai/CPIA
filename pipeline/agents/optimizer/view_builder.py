"""Optimizer 노드의 view builder — daily_reports.jsonb 컬럼 8개 산출."""

from __future__ import annotations

import logging
import statistics
from datetime import date
from typing import Any, Optional

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
    """site 전체 EVM 산출 — group_key='site'."""
    async with pg._pool.acquire() as con:
        plan_row = await con.fetchrow(
            """
            SELECT
              SUM(plan_total_qty * LEAST(1.0, GREATEST(0.0,
                  ($2::date - plan_start + 1)::float / NULLIF((plan_finish - plan_start + 1)::float, 0)
              )))::float AS cum_plan_qty,
              SUM(plan_mh_rev2 * LEAST(1.0, GREATEST(0.0,
                  ($2::date - plan_start + 1)::float / NULLIF((plan_finish - plan_start + 1)::float, 0)
              )))::float AS cum_plan_mh,
              SUM(plan_total_qty)::float AS plan_qty_full,
              SUM(plan_mh_rev2)::float AS plan_mh_full
            FROM activity_master
            WHERE site_id = $1
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


async def _evm_by_group(
    pg: PGClient,
    site_id: str,
    today: date,
    group_key: str,
) -> dict[str, dict[str, Any]]:
    """group_key (company / l6_main / wa_l6_company) 별 EVM dict.

    placeholder — Task B.4 에서 구현.
    """
    return {}


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
