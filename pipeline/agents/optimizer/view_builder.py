"""Optimizer 노드의 view builder — daily_reports.jsonb 컬럼 8개 산출."""

from __future__ import annotations

import logging
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
