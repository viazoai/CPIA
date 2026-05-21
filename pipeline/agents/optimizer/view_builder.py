"""Optimizer 노드의 view builder — daily_reports.jsonb 컬럼 8개 산출."""

from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta
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

    컨셉 (2026-05-20, spec §8.1): actual anchor. mapper_activities 에 등장한 group 만 표시.
    company / l6_main 모두 FROM actual_agg LEFT JOIN plan_agg — 매핑 안 된 plan-only 업체/공종 제외.
    plan 만 있고 actual 없으면 그 group 은 결과에서 빠짐 — 시연 시 노이즈 제거.
    site 전체 EVM (_evm_for_group) 은 별도 함수, 분모=계획 유지.
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
              AND ma.is_mock = FALSE
            GROUP BY {actual_gkey}
        )
        SELECT a.gkey AS gkey,
               COALESCE(p.cum_plan_qty, 0)::float AS cum_plan_qty,
               COALESCE(p.cum_plan_mh, 0)::float AS cum_plan_mh,
               COALESCE(p.plan_qty_full, 0)::float AS plan_qty_full,
               COALESCE(p.plan_mh_full, 0)::float AS plan_mh_full,
               a.cum_actual_qty::float AS cum_actual_qty,
               a.cum_actual_mh::float AS cum_actual_mh
        FROM actual_agg a
        LEFT JOIN plan_agg p USING (gkey)
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
          AND ma.is_mock = FALSE
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
    """by_contractor dict → BarItem[] sorted by CPI desc.

    baseline=90: _bar_status 의 normal/caution 경계와 일치. spec §8.2.
    FE ProductivityBarToggle 의 underCount = value < baseline 카운트.
    """
    by_c = productivity.get("by_contractor", {}) or {}
    return sorted(
        [
            {
                "label": c,
                "value": round(d.get("cpi") or 0, 1),
                "baseline": 90,
                "status": _bar_status(d.get("cpi") or 0),
            }
            for c, d in by_c.items()
        ],
        key=lambda x: -x["value"],
    )


def _build_trade_bars(productivity: dict[str, Any]) -> list[dict[str, Any]]:
    """by_l6 dict -> BarItem[]. baseline=90 — spec §8.2."""
    by_l = productivity.get("by_l6", {}) or {}
    return sorted(
        [
            {
                "label": l,
                "value": round(d.get("cpi") or 0, 1),
                "baseline": 90,
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
    wa_lookup: Optional[dict[tuple[str, str], list[str]]] = None,
) -> dict[str, Any]:
    """§ 02 by_wp dict — 진단/유사사례/권고/상세 6칸.

    advice = optimizer_advice 의 row. forecast = forecasts 의 row (wa lookup).

    wa_lookup: (l6_main, company) → DISTINCT wa list. fan-out 용.
                전달되면 한 advice 를 wa list 의 각 wa 마다 by_wp 에 복사.
                None / 빈 dict 면 forecasts.wa 1개 기준 단일 key (기존 동작).
                spec §8.3 — quadrant dot 의 wp_id (mapper_activities 기반) 와 매칭 보장.
    """
    wa_lookup = wa_lookup or {}
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
        # fan-out: wa_lookup 의 모든 wa 마다 같은 advice 적재.
        # lookup miss → forecasts.wa 1개 fallback (기존 동작).
        wa_list = wa_lookup.get(
            (advice.get("l6_main"), advice.get("company"))
        ) or [matched_f.get("wa")]

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

        advice_dict = {
            "diagnosis": advice.get("diagnosis") or "",
            "similar_cases": similar_cases,
            "recommendations": recommendations,
            "details": details,
        }
        for wa in wa_list:
            wp_id = _wp_id_of(wa, advice.get("l6_main"), advice.get("company"))
            by_wp[wp_id] = advice_dict

    default_wp_id = next(iter(by_wp.keys()), None)
    return {"by_wp": by_wp, "default_wp_id": default_wp_id}


# ============================================================
# 공기단축 시나리오 (spec 2026-05-19 §5)
# ============================================================


def _coerce_date(v: Any) -> date | None:
    """expected_completion 입력이 date 객체 또는 ISO 문자열 (asyncpg vs jsonb) 모두 허용.

    spec §5.2 type contract: date | None. 안전 코어스.
    """
    if v is None:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def _expand_recovery_to_days(dist: dict | None) -> list[int]:
    """recovery_distribution → percentile 산출 가능한 list.

    spec §5.2 Step 1. not_recovered 는 +30 일 캡.
    """
    out: list[int] = []
    for key, count in (dist or {}).items():
        if key == "not_recovered":
            out.extend([30] * int(count))
        elif key.startswith("d+"):
            try:
                d = int(key[2:])
                out.extend([d] * int(count))
            except ValueError:
                continue
    return out


def _percentile(days: list[int], q: float) -> int:
    """q in [0, 1]. 빈 list → 0. spec §5.2 Step 2."""
    if not days:
        return 0
    sorted_days = sorted(days)
    if len(sorted_days) < 4:
        idx = min(len(sorted_days) - 1, int(q * len(sorted_days)))
        return sorted_days[idx]
    cuts = statistics.quantiles(sorted_days, n=100, method="inclusive")
    return int(round(cuts[max(0, min(98, int(q * 100) - 1))]))


def _match_forecast_by_company_l6(advice: dict, forecast: list[dict]) -> dict | None:
    """(company, l6_main) 매칭. spec §5.2.

    view_builder._build_optimizer_view 의 패턴과 동일 — 두 호출자 공유.
    """
    return next(
        (f for f in forecast
         if f.get("company") == advice.get("company")
         and f.get("l6_main") == advice.get("l6_main")),
        None,
    )


def _scenario(no_action_date, recovery_days: int, case_count: int) -> dict:
    """단일 시나리오 dict 빌드. spec §5.2 Step 3."""
    if no_action_date is None or recovery_days <= 0:
        return {
            "expected_completion": no_action_date.isoformat() if no_action_date else None,
            "recovery_days": recovery_days,
            "delta_days": 0,
            "case_count": case_count,
        }
    new_date = no_action_date - timedelta(days=recovery_days)
    return {
        "expected_completion": new_date.isoformat(),
        "recovery_days": recovery_days,
        "delta_days": -recovery_days,
        "case_count": case_count,
    }


def _build_scenarios(advice_rows: list[dict], forecast: list[dict]) -> dict:
    """공기단축 4 시나리오 산출 — site + by_wp.

    spec §5.1 shape + §5.2 산식.
    """
    site_days: list[int] = []
    for advice in advice_rows:
        site_days.extend(_expand_recovery_to_days(advice.get("recovery_distribution") or {}))

    site_no_action = None
    if forecast:
        ecs = [_coerce_date(f.get("expected_completion")) for f in forecast]
        ecs = [e for e in ecs if e is not None]
        site_no_action = max(ecs) if ecs else None

    site_scenarios = {
        "no_action": {
            "expected_completion": site_no_action.isoformat() if site_no_action else None,
            "recovery_days": 0,
            "delta_days": 0,
            "case_count": len(site_days),
        },
        "optimistic_p25":  _scenario(site_no_action, _percentile(site_days, 0.25), len(site_days)),
        "base_p50":        _scenario(site_no_action, _percentile(site_days, 0.50), len(site_days)),
        "pessimistic_p75": _scenario(site_no_action, _percentile(site_days, 0.75), len(site_days)),
    }

    by_wp: dict[str, dict] = {}
    for advice in advice_rows:
        f = _match_forecast_by_company_l6(advice, forecast)
        if f is None:
            continue
        wp_id = _wp_id_of(f.get("wa"), advice.get("l6_main"), advice.get("company"))
        wp_days = _expand_recovery_to_days(advice.get("recovery_distribution") or {})
        wp_no_action = _coerce_date(f.get("expected_completion"))
        by_wp[wp_id] = {
            "no_action": {
                "expected_completion": wp_no_action.isoformat() if wp_no_action else None,
                "recovery_days": 0,
                "delta_days": 0,
                "case_count": len(wp_days),
            },
            "optimistic_p25":  _scenario(wp_no_action, _percentile(wp_days, 0.25), len(wp_days)),
            "base_p50":        _scenario(wp_no_action, _percentile(wp_days, 0.50), len(wp_days)),
            "pessimistic_p75": _scenario(wp_no_action, _percentile(wp_days, 0.75), len(wp_days)),
        }

    return {"site": site_scenarios, "by_wp": by_wp}


# ─────────────────────────────────────────────────────────────────
# Phase 1 (2026-05-21) v2 helper: 4단 산식 + display_label
# ─────────────────────────────────────────────────────────────────

import random as _random


def _compute_daily_quota(plan_total_qty: float, total_days: int) -> float:
    """마스터 plan_total_qty 를 일일 quota 로 환산."""
    if total_days <= 0 or plan_total_qty <= 0:
        return 0.0
    return plan_total_qty / total_days


def _simulate_today_qty(
    daily_qty: float, daily_workers: float, seed: int
) -> dict[str, float]:
    """productivity 분포 = 중심 85% + ±20% 일반 + 5%/5% outlier (60%/150%).

    today_qty noise 가 직접 productivity 에 반영됨 (workers ±5% 만 — 영향 최소).
    분기:
      roll < 0.05: high outlier 1.40~1.55 (productivity ~140~155%, 산식에서 150 clamp)
      roll < 0.10: low outlier  0.55~0.65 (productivity 55~65%)
      else:       일반          0.65~1.05 (productivity 65~105%, 중심 85%)
    """
    rng = _random.Random(seed)
    roll = rng.random()
    if roll < 0.05:
        noise_q = 1.40 + 0.15 * rng.random()
    elif roll < 0.10:
        noise_q = 0.55 + 0.10 * rng.random()
    else:
        noise_q = 0.65 + 0.40 * rng.random()
    noise_w = 0.95 + 0.10 * rng.random()
    return {
        "today_qty": daily_qty * noise_q,
        "workers": max(1.0, daily_workers * noise_w),
    }


def _compute_productivity(perperson: float, master_perperson: float) -> float:
    """인당 / 마스터 인당 * 100. master <= 0 면 0."""
    if master_perperson <= 0:
        return 0.0
    return perperson / master_perperson * 100


def _weighted_median(values: list[float], weights: list[float]) -> float:
    """가중치 누적 50% 지점 값. 빈 list -> 0, weights 합 0 -> 단순 평균."""
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


def _normalize_impact(impacts: list[float]) -> list[float]:
    """impact_raw / max(impact_raw) * 100 → 0..100. 빈 list -> []."""
    if not impacts:
        return []
    mx = max(impacts)
    if mx <= 0:
        return [0.0] * len(impacts)
    return [round(x / mx * 100, 2) for x in impacts]


def _make_display_label(
    productivity_pct: float, perperson: float | None, unit: str | None
) -> str:
    """UI 표시 라벨. '98.9% (3.20 ton/인)' 형식, perperson/unit 없으면 '%만'."""
    if perperson is None or unit is None:
        return f"{productivity_pct:.1f}%"
    return f"{productivity_pct:.1f}% ({perperson:.2f} {unit}/인)"


# ─────────────────────────────────────────────────────────────────
# Task 9: _build_productivity_views_v2 — 메인 통합 산식
# ─────────────────────────────────────────────────────────────────


def _status_of(pct: float) -> str:
    """productivity 색상 분기 (UI status)."""
    if pct >= 90:
        return "normal"
    if pct >= 70:
        return "caution"
    return "risk"


def _quadrant_of(prod: float, impact: float) -> str:
    if prod < 70 and impact >= 50:
        return "risk"
    if prod < 70:
        return "caution"
    if impact >= 50:
        return "watch"
    return "safe"


def _group_perperson_unit(items: list[dict]) -> tuple[float | None, str | None]:
    """그룹 내 단위 일관성 검증 후 wv-mean perperson + dominant unit 반환.
    단위가 섞이면 (None, None)."""
    units = {it.get("unit") for it in items if it.get("unit")}
    if len(units) != 1:
        return None, None
    unit = units.pop()
    pps = [it["perperson"] for it in items if it.get("perperson") is not None]
    wvs = [it.get("plan_mh", 0) for it in items if it.get("perperson") is not None]
    if not pps:
        return None, unit
    tw = sum(wvs)
    if tw <= 0:
        avg = sum(pps) / len(pps)
    else:
        avg = sum(p * w for p, w in zip(pps, wvs)) / tw
    return avg, unit


_VIEWS_V2_EMPTY = {
    "kpi": {},
    "productivity": {},
    "contractor_bars": [],
    "trade_bars": [],
    "quadrant": [],
    "wp_summary": [],
}


async def _build_productivity_views_v2(
    pg: PGClient,
    site_id: str,
    today: date,
) -> dict:
    """Phase 1 신규 4단 산식 — daily_reports.jsonb 6 컬럼 생성.

    SQL 흐름:
      mapper_activities + LATERAL (activity_master 같은 site/company/l6/l7_5
      그룹의 plan_start MIN, plan_finish MAX, qty SUM, mh SUM) JOIN.
      report_date 가 plan 기간 안 + l7_5_activity not null 인 row 만.
    산식:
      row.today_qty/workers 를 마스터 daily × noise (helper) 로 재산정,
      productivity = (perperson / master_perperson) * 100, 150 clamp.
      impact_raw = (100 - productivity) * plan_mh, 정규화 0..100.
    """
    rows = await pg.fetch_all(
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
            WHERE am.site_id = pr.site_id
              AND am.company = ma.company
              AND am.l6_main = ma.l6_main
              AND am.l7_5_activity = ma.l7_5_activity
        ) m ON TRUE
        WHERE ma.report_date = $1
          AND pr.site_id = $2
          AND ma.l7_5_activity IS NOT NULL
          AND m.ps IS NOT NULL AND $1 BETWEEN m.ps AND m.pf
          AND ma.trade IN ('건축', '토목')
        """,
        today,
        site_id,
    )
    if not rows:
        return dict(_VIEWS_V2_EMPTY)

    # row 별 산식
    items: list[dict] = []
    for r in rows:
        plan_qty = float(r["plan_total_qty"] or 0)
        plan_mh = float(r["plan_mh"] or 0)
        total_days = (r["plan_finish"] - r["plan_start"]).days + 1
        if total_days <= 0 or plan_qty <= 0 or plan_mh <= 0:
            continue
        daily_qty_master = _compute_daily_quota(plan_qty, total_days)
        daily_workers_master = max(1.0, plan_mh / total_days / 8.0)
        # 결정성: hashlib.sha256 (built-in hash() 는 PYTHONHASHSEED 마다 다름).
        # 같은 (date, l7_5, company) -> 항상 같은 seed -> backfill idempotent.
        import hashlib as _hashlib

        _key = f"{today.toordinal()}|{r['l7_5_activity']}|{r['company']}"
        seed = int.from_bytes(
            _hashlib.sha256(_key.encode("utf-8")).digest()[:4], "big"
        )
        sim = _simulate_today_qty(daily_qty_master, daily_workers_master, seed)
        perperson = sim["today_qty"] / sim["workers"]
        master_perperson = daily_qty_master / daily_workers_master
        productivity = min(_compute_productivity(perperson, master_perperson), 150.0)
        impact_raw = max(0.0, 100 - productivity) * plan_mh
        items.append(
            {
                "id": r["id"],
                "site_id": r["site_id"],
                "company": r["company"],
                "l6_main": r["l6_main"],
                "l7_5_activity": r["l7_5_activity"],
                "unit": r["unit"],
                "today_qty": sim["today_qty"],
                "workers": sim["workers"],
                "plan_total_qty": plan_qty,
                "plan_mh": plan_mh,
                "perperson": perperson,
                "master_perperson": master_perperson,
                "productivity": productivity,
                "impact_raw": impact_raw,
            }
        )

    if not items:
        return dict(_VIEWS_V2_EMPTY)

    # impact 정규화
    impacts_norm = _normalize_impact([it["impact_raw"] for it in items])
    for it, ni in zip(items, impacts_norm):
        it["impact"] = ni

    # 업체별 집계
    from collections import defaultdict

    by_company: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_company[it["company"]].append(it)

    company_prod: dict[str, dict] = {}
    for company, rs in by_company.items():
        prods = [it["productivity"] for it in rs]
        wvs = [it["plan_mh"] for it in rs]
        pp, unit = _group_perperson_unit(rs)
        company_prod[company] = {
            "simple_mean": (sum(prods) / len(prods)) if prods else 0,
            "wv_median": _weighted_median(prods, wvs),
            "n": len(prods),
            "sum_wv": sum(wvs),
            "perperson": pp,
            "perperson_unit": unit,
        }

    # 공종별 (l6_main) 집계
    by_l6: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_l6[it["l6_main"]].append(it)
    l6_prod: dict[str, dict] = {}
    for l6, rs in by_l6.items():
        prods = [it["productivity"] for it in rs]
        wvs = [it["plan_mh"] for it in rs]
        pp, unit = _group_perperson_unit(rs)
        l6_prod[l6] = {
            "simple_mean": (sum(prods) / len(prods)) if prods else 0,
            "wv_median": _weighted_median(prods, wvs),
            "n": len(prods),
            "sum_wv": sum(wvs),
            "perperson": pp,
            "perperson_unit": unit,
        }

    # 현장 (전체) — 업체별 wv_median 들의 wv-median + 단순 평균
    all_med = [v["wv_median"] for v in company_prod.values()]
    all_mean = [v["simple_mean"] for v in company_prod.values()]
    all_wv = [v["sum_wv"] for v in company_prod.values()]
    site_wv_median = _weighted_median(all_med, all_wv)
    site_simple_mean = sum(all_mean) / len(all_mean) if all_mean else 0
    site_pp, site_unit = _group_perperson_unit(items)

    # ── UI 컬럼 ──
    contractor_bars = [
        {
            "label": company,
            "value": round(v["wv_median"], 1),
            "status": _status_of(v["wv_median"]),
            "baseline": 100,
            "perperson": round(v["perperson"], 2) if v["perperson"] is not None else None,
            "perperson_unit": (
                f"{v['perperson_unit']}/인" if v["perperson_unit"] else None
            ),
            "display_label": _make_display_label(
                v["wv_median"], v["perperson"], v["perperson_unit"]
            ),
        }
        for company, v in sorted(
            company_prod.items(), key=lambda x: -x[1]["wv_median"]
        )
    ]
    trade_bars = [
        {
            "label": l6,
            "value": round(v["wv_median"], 1),
            "status": _status_of(v["wv_median"]),
            "baseline": 100,
            "perperson": round(v["perperson"], 2) if v["perperson"] is not None else None,
            "perperson_unit": (
                f"{v['perperson_unit']}/인" if v["perperson_unit"] else None
            ),
            "display_label": _make_display_label(
                v["wv_median"], v["perperson"], v["perperson_unit"]
            ),
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
            "quadrant": _quadrant_of(it["productivity"], it["impact"]),
            "size": round((it["plan_total_qty"] or 1) / 10, 1),
            "perperson": round(it["perperson"], 2),
            "perperson_unit": f"{it['unit']}/인" if it["unit"] else None,
            "display_label": _make_display_label(
                it["productivity"], it["perperson"], it["unit"]
            ),
        }
        for it in items
    ]
    wp_summary = [
        {
            "wp_id": f"WP-{it['id']}",
            "wp_name": it["l7_5_activity"],
            "trade": it["l6_main"],
            "bp_name": it["company"],
            "start_date": str(today.replace(day=1)),  # placeholder
            "end_date": str(today),
            "progress_pct": round(
                min(100, (it["today_qty"] / max(it["plan_total_qty"], 1)) * 100), 1
            ),
            "productivity": round(it["productivity"], 1),
            "impact": round(it["impact"], 1),
            "baseline": 100,
            "status": _status_of(it["productivity"]),
            "perperson": round(it["perperson"], 2),
            "perperson_unit": f"{it['unit']}/인" if it["unit"] else None,
            "display_label": _make_display_label(
                it["productivity"], it["perperson"], it["unit"]
            ),
        }
        for it in items
    ]
    kpi = {
        "productivity_today": round(site_wv_median, 1),
        "productivity_today_simple_mean": round(site_simple_mean, 1),
        "productivity_today_perperson": (
            round(site_pp, 2) if site_pp is not None else None
        ),
        "productivity_today_unit": f"{site_unit}/인" if site_unit else None,
        "productivity_today_display": _make_display_label(
            site_wv_median, site_pp, site_unit
        ),
        "productivity_history_diff": 0,
        "delay_days": 0,
        "expected_completion": str(today.replace(day=1)),
        "recoverable_productivity": round(max(0, 100 - site_wv_median), 1),
        "target_productivity": 100,
        "recovery_days": 0,
        "recovered_completion": str(today.replace(day=1)),
    }
    productivity_dict = {
        "site": {
            "wv_median": round(site_wv_median, 2),
            "simple_mean": round(site_simple_mean, 2),
            "n_companies": len(company_prod),
            "n_l75": len(items),
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
    return {
        "kpi": kpi,
        "productivity": productivity_dict,
        "contractor_bars": contractor_bars,
        "trade_bars": trade_bars,
        "quadrant": quadrant,
        "wp_summary": wp_summary,
    }


# ─────────────────────────────────────────────────────────────────
# Task 10: ChromaDB augmentation (backfill 전용)
# ─────────────────────────────────────────────────────────────────


def _augment_history_if_sparse(items: list[dict], min_count: int = 5) -> list[dict]:
    """그룹 (company, l6_main) row 수 < min_count 면 동일 l6 다른 company 에서 보충.
    augment 된 row 는 metadata.augmented=True + augmented_from_company 적재.
    backfill 시점에만 호출 — live atomizer 는 사용 X."""
    from collections import defaultdict

    by_group: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for it in items:
        by_group[(it["company"], it["l6_main"])].append(it)
    augmented = list(items)
    for (co, l6), rs in by_group.items():
        if len(rs) >= min_count:
            continue
        need = min_count - len(rs)
        donors = [
            it
            for it in items
            if it.get("l6_main") == l6 and it.get("company") != co
        ]
        for donor in donors[:need]:
            aug = dict(donor)
            aug["company"] = co
            aug["metadata"] = {
                **donor.get("metadata", {}),
                "augmented": True,
                "augmented_from_company": donor["company"],
            }
            augmented.append(aug)
    return augmented
