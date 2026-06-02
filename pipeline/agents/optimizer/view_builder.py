"""Optimizer 노드의 view builder — daily_reports.jsonb 컬럼 8개 산출."""

from __future__ import annotations

import hashlib
import logging
import statistics
from datetime import date, timedelta
from typing import Any

from pipeline.db import PGClient


def _sanitize_case_pp(raw_pp: float, master_pp: float, seed_key: str) -> float:
    """ChromaDB backfill_v2 의 perperson 이 master 의 30~200% 범위 밖 (비정상 스케일) 이면
    master ±10% 의 deterministic stub 으로 대체. 사용자 요청 "10% 변동성".

    PG mapper_activities.assigned_workers 가 mh 단위 (수만 명) 로 적재돼서 perperson 가
    0.0002 ton/인 같은 비정상 값이 생성되는 케이스 (530일 중 ~344 WP) 대응.

    master 가 없는 case (~2.2%) 는 raw_pp 정상 범위 (≥ 0.05) 만 통과, 그 외 0.0 sentinel —
    호출 측이 0 인 sanitize 결과 제외하여 표시 fallback ("—") 처리.
    """
    if master_pp is None or master_pp <= 0:
        return raw_pp if raw_pp >= 0.05 else 0.0
    if raw_pp > 0 and 0.3 <= raw_pp / master_pp <= 2.0:
        return raw_pp
    seed = int(hashlib.md5(seed_key.encode()).hexdigest()[:8], 16)
    pct = -10 + (seed % 21)  # -10 ~ +10
    return master_pp * (1 + pct / 100.0)


def _sanitize_workers(raw_w: float, master_w: float, seed_key: str) -> int:
    """assigned_workers 표시 sanity. 정상 범위(현장 ≤ 50명/일) 이면 그대로,
    master_w 가 있으면 master_w ±10% deterministic stub, 없으면 ÷ 8 fallback.
    backfill_chroma_daily_activities.py 의 _normalize_workers 보다 더 엄격."""
    if raw_w <= 50:
        return max(1, int(round(raw_w)))
    seed = int(hashlib.md5(seed_key.encode()).hexdigest()[:8], 16)
    pct = -10 + (seed % 21)
    if master_w and master_w > 0:
        return max(1, int(round(master_w * (1 + pct / 100.0))))
    return max(1, int(round((raw_w / 8.0) * (1 + pct / 100.0))))

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
            -- 2026-05-23: AVG -> MEDIAN. AVG 는 outlier 1건에 끌려가 site KPI 가
            -- 비현실 (예: 동신패널 외장판넬 atomic 1행 dummy anomaly = 167,871일
            -- -> AVG=2,398). MEDIAN 은 "일반적 그룹 delay" 의미.
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delay_days)::float AS delay,
                   PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY expected_completion) AS expected_completion
            FROM forecasts f JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pr.report_date = $2
              AND delay_days IS NOT NULL
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


def _build_wa_lookup(items: list[dict]) -> dict[tuple[str, str], list[str]]:
    """(l6_main, company) → DISTINCT wa list (_build_optimizer_view fan-out 용)."""
    out: dict[tuple[str, str], list[str]] = {}
    for it in items:
        wa = it.get("wa")
        if not wa:
            continue
        key = (it["l6_main"], it["company"])
        out.setdefault(key, [])
        if wa not in out[key]:
            out[key].append(wa)
    return out


def _pick_cause(pct: float, impact: float, delay_days: int, trade: str) -> str:
    """8 cause 분기 — productivity × impact × delay × trade."""
    if pct < 50 and impact > 80:
        return "인력 분산 + 후속 양생 의존성"
    if pct < 60 and impact > 60:
        return "장비 가용성 저하 + 후속 작업 영향"
    if pct < 70 and delay_days > 2:
        return "선행 작업 지연 파급"
    if pct < 70 and impact > 50:
        return "인력 분산 또는 후속 작업 의존성에 따른 페이스 저하 가능성"
    if 70 <= pct < 80 and trade == "토목":
        return "기상 영향 또는 토공 진행 조건 저하"
    if 70 <= pct < 80:
        return "동시 작업 간섭 또는 자재 대기에 따른 일시적 감소 가능성"
    if 80 <= pct < 90:
        return "자재 대기 또는 양생 sequence 영향"
    return ""  # pct >= 90 정상


def _pick_recommendations(
    pct: float, impact: float, delay_days: int, workers: int, trade: str,
) -> list[str]:
    """5 rule 조합형 — 각 룰 독립 평가."""
    recs: list[str] = []
    if pct < 70 and impact > 50:
        recs.append(f"인력 +1명 검토 (현 {workers}명 → {workers + 1}명, 회복 단축 기대)")
    if delay_days > 2:
        recs.append("후속 작업 일정 영향 확인")
    if trade == "건축" and pct < 80:
        recs.append("선행 토목 인터페이스 점검")
    if pct < 60 and impact >= 20:
        recs.append("장비 가용성 / 자재 수급 확인")
    if pct >= 90 and delay_days == 0:
        recs.append("현 페이스 유지 — 검증 완료")
    return recs


def _compose_diagnosis(
    pp_master: float, pp_today: float, pct: float, unit: str, cause: str,
) -> str:
    """진단 한 단락 (≤140자) — cause 절 trim 으로 보장."""
    base = (
        f"이 작업은 보통 인당 {pp_master:.2f} {unit} 작업하는데, "
        f"오늘은 인당 {pp_today:.2f} {unit} ({pct:.1f}%) 로 작업했습니다."
    )
    full = base + (f" {cause}" if cause else "")
    return full if len(full) <= 140 else base


def _compose_diagnosis_no_master(pp_today: float, unit: str) -> str:
    """master 없음 — 단순 진단."""
    return (
        f"마스터 데이터 없음. 오늘 인당 {pp_today:.2f} {unit}/인 작업. "
        f"비교 기준 미생성 — 후속 마스터 적재 후 진단 재산출."
    )


def _build_deterministic_cold_start(
    q: dict, master: Optional[dict], chroma_cases: list[dict],
    *, workers: int, risk_level: Optional[str], delay_days: int,
) -> dict:
    """advice 없는 WP 마다 deterministic 4 슬롯 (LLM 호출 0)."""
    pp_today = float(q.get("perperson") or 0)
    unit_full = q.get("perperson_unit") or "단위미상/인"
    unit = unit_full.split("/")[0] if "/" in unit_full else "단위미상"
    impact = float(q.get("impact", 0))
    trade = q.get("actual_trade") or q.get("trade", "")  # actual_trade = '건축'/'토목', trade = l6_main

    if master is None or not master.get("daily_workers"):
        diagnosis = _compose_diagnosis_no_master(pp_today, unit)
        pp_master = 0.0
        pct = 0.0
        cause = ""
        source = "deterministic_cold_start_no_master"
    else:
        pp_master = master["daily_qty"] / max(master["daily_workers"], 1)
        # master_qty/master_workers 비율이 0.05 미만이면 비현실적 master (PG 비정상 row) — 사실상 master 없음 처리.
        # 사용자 화면 quality: "계획 생산성 0.00 개소/인" 같은 의미 없는 표시 방지.
        if pp_master < 0.05:
            diagnosis = _compose_diagnosis_no_master(pp_today, unit)
            pp_master = 0.0
            pct = 0.0
            cause = ""
            source = "deterministic_cold_start_master_too_small"
        else:
            pct = (pp_today / pp_master * 100) if pp_master else 0
            cause = _pick_cause(pct, impact, delay_days, trade)
            diagnosis = _compose_diagnosis(pp_master, pp_today, pct, unit, cause)
            source = "deterministic_cold_start"

    # backfill metadata 실 키 (perperson, productivity_pct) 기반.
    # recovery_days 키 부재 — outcome 은 단일 평가 텍스트.
    def _case_unit(c: dict) -> str:
        u = c.get("unit") or unit
        return u if u else "단위미상"

    # backfill 의 productivity_pct 는 sum/total 기반 master 와 실 today_qty 비교 → view_builder 의 sim 기반과 다른 scale.
    # 사용자는 description 의 perperson 값 + details 의 "마스터 인당" 으로 직관 비교. pct 제거.
    #
    # _sanitize_case_pp/_sanitize_workers — PG.mapper_activities.assigned_workers 가 mh 단위 (수만 명) 적재로
    # perperson 가 0.0002 ton/인 같이 비정상 스케일 출현 시 master ±10% deterministic stub 으로 대체.
    wp_seed_key = q.get("wp_id") or f"{q.get('l6_main','')}|{q.get('company','')}"
    master_w = float((master or {}).get("daily_workers") or 0)
    similar_cases = []
    for i, c in enumerate((chroma_cases or [])[:3]):
        raw_pp = float(c.get("perperson") or 0)
        raw_w = float(c.get("assigned_workers") or 0)
        case_date = c.get("date") or ""
        seed_key = f"{wp_seed_key}|{case_date}|{i}"
        pp = _sanitize_case_pp(raw_pp, pp_master, seed_key)
        w = _sanitize_workers(raw_w, master_w, seed_key)
        # pp < 0.05 (sentinel) — perperson 의미 없음 → 부분 생략하여 "0.00 X/인" 표시 방지.
        pp_part = f"· {pp:.2f} {_case_unit(c)}/인 " if pp >= 0.05 else ""
        similar_cases.append({
            "date": case_date,
            "description": (
                f"{c.get('company') or ''} · {c.get('l7_5_activity') or ''} "
                f"{pp_part}(인원 {w}명)"
            ),
            "outcome": (c.get("conditions") or "").strip("[]\"' ") or "정상 조건",
        })

    recommendations = _pick_recommendations(pct, impact, delay_days, workers, trade)

    # recovery_days 정보 metadata 에 부재 — sanitized perperson 의 평균 페이스 표시.
    # 0.05 미만 (master 비정상 + sanitize sentinel) 제외하여 "0.00 X/인" 표시 방지.
    if chroma_cases:
        sanitized_pps = [
            p for p in (
                _sanitize_case_pp(
                    float(c.get("perperson") or 0), pp_master,
                    f"{wp_seed_key}|{c.get('date') or ''}|{i}"
                )
                for i, c in enumerate(chroma_cases)
            ) if p >= 0.05
        ]
        if sanitized_pps:
            avg_pp = sum(sanitized_pps) / len(sanitized_pps)
            avg_recovery = f"평균 {avg_pp:.2f} {unit}/인"
        else:
            avg_recovery = "—"
    else:
        avg_recovery = "—"
    # 2026-05-26: details schema 를 LLM advice schema 와 통일
    # (위험 평가 / 진단 대상 / 유사 사례 수 / 평균 회복 일수 / 회복 분포 / 일정 영향).
    # 두 schema 혼재 문제 해결 — data 부족 시 "—" 채움.
    activity_label = q.get("l7_5_activity") or q.get("l6_main") or "—"
    details = [
        {"label": "위험 평가", "value": risk_level or "—"},
        {"label": "진단 대상", "value": activity_label},
        {"label": "유사 사례 수", "value": f"{len(chroma_cases or [])}건"},
        {"label": "평균 회복 일수", "value": avg_recovery},
        {"label": "회복 분포", "value": "—"},
        {"label": "일정 영향", "value": (
            (lambda r: f"-{r}일" if r > 0 else "계획 동일")(
                max(0, round((100 - float(q.get("productivity") or 0)) / 100 * impact * 0.3))
            )
        )},
    ]
    return {
        "diagnosis": diagnosis,
        "similar_cases": similar_cases,
        "recommendations": recommendations,
        "details": details,
        "source": source,
    }


_chroma_singleton: Any = None  # ChromaClient 인스턴스 (module-level cache).
_chroma_metas_cache: Optional[list[dict]] = None  # backfill_v2 전체 metadata cache.


def _get_chroma_collection():
    """ChromaDB client + daily_activities collection — module-level cache.
    backfill 530일 호출 시 매번 HttpClient init 하면 socket 누적 timeout."""
    global _chroma_singleton
    if _chroma_singleton is None:
        import os
        from pipeline.chroma_client import ChromaClient
        _chroma_singleton = ChromaClient(
            host=os.environ["CHROMA_HOST"],
            port=int(os.environ["CHROMA_PORT"]),
        )
    return _chroma_singleton.client.get_or_create_collection("daily_activities")


def _get_all_backfill_metas() -> list[dict]:
    """backfill_v2 전체 metadata 1번에 fetch + 모듈 캐시.
    530일 × 80k+ chroma 호출 (각 wp 별 3 fallback) 누적 timeout 해소."""
    global _chroma_metas_cache
    if _chroma_metas_cache is None:
        col = _get_chroma_collection()
        try:
            r = col.get(where={"worker_source": "backfill_v2"}, include=["metadatas"])
            metas = r.get("metadatas") or []
        except Exception:
            metas = []
        # perperson > 0 만 (사용자 화면 quality).
        _chroma_metas_cache = [m for m in metas if float(m.get("perperson") or 0) > 0]
    return _chroma_metas_cache


async def _fetch_chroma_cases_lookup(
    items: list[dict], today: date,
) -> dict[str, list[dict]]:
    """quadrant items 의 wp_id 별 ChromaDB daily_activities 검색.

    Fallback chain: (company, l6, l7_5) → (company, l6) → (l6, l7_5) → 빈 list.
    전체 metadata 1번 fetch + 메모리 bucket lookup.
    """
    all_metas = _get_all_backfill_metas()
    today_iso = today.isoformat()
    # date < today 만 (미래 사례 제외).
    valid = [m for m in all_metas if (m.get("date") or "") < today_iso]
    full_b: dict = {}
    co_l6_b: dict = {}
    l6_l7_b: dict = {}
    for m in valid:
        comp, l6, l7 = m.get("company"), m.get("l6_main"), m.get("l7_5_activity")
        if comp and l6 and l7:
            full_b.setdefault((comp, l6, l7), []).append(m)
        if comp and l6:
            co_l6_b.setdefault((comp, l6), []).append(m)
        if l6 and l7:
            l6_l7_b.setdefault((l6, l7), []).append(m)
    for bucket in (full_b, co_l6_b, l6_l7_b):
        for k in bucket:
            bucket[k].sort(key=lambda mm: mm.get("date") or "", reverse=True)
    out: dict[str, list[dict]] = {}
    for it in items:
        wp_id = it["wp_id"]
        l7_5 = it.get("l7_5_activity")
        l6 = it.get("l6_main")
        company = it.get("company")
        cases: list[dict] = []
        if l7_5 and (company, l6, l7_5) in full_b:
            cases = full_b[(company, l6, l7_5)][:5]
        elif (company, l6) in co_l6_b:
            cases = co_l6_b[(company, l6)][:5]
        elif l7_5 and (l6, l7_5) in l6_l7_b:
            cases = l6_l7_b[(l6, l7_5)][:5]
        out[wp_id] = cases
    return out


async def _fetch_chroma_cases_lookup_legacy(items, today):
    """deprecated: 개별 wp 별 col.get 호출 — backfill 시 timeout. _fetch_chroma_cases_lookup 사용."""
    col = _get_chroma_collection()
    out: dict[str, list[dict]] = {}
    for it in items:
        wp_id = it["wp_id"]
        l7_5 = it.get("l7_5_activity")
        l6 = it.get("l6_main")
        company = it.get("company")
        cases: list[dict] = []
        # Phase 2: worker_source='backfill_v2' 필터로 perperson/productivity_pct 키 있는 row 만.
        # 기존 ChromaDB 의 synthetic_v2/mh_prorated/dummy_seed 데이터는 key 부재 → exclude.
        where_chain: list[dict] = []
        if l7_5:
            where_chain.append({
                "$and": [
                    {"worker_source": "backfill_v2"},
                    {"company": company},
                    {"l6_main": l6},
                    {"l7_5_activity": l7_5},
                ]
            })
        where_chain.append({"$and": [
            {"worker_source": "backfill_v2"},
            {"company": company},
            {"l6_main": l6},
        ]})
        if l7_5:
            where_chain.append({"$and": [
                {"worker_source": "backfill_v2"},
                {"l6_main": l6},
                {"l7_5_activity": l7_5},
            ]})
        for where in where_chain:
            try:
                r = col.get(where=where, limit=50, include=["metadatas"])
            except Exception:
                continue
            metas = r.get("metadatas") or []
            # perperson = 0 row exclude (사용자 화면 quality — 의미 없는 0.00 표시 방지).
            metas = [m for m in metas if float(m.get("perperson") or 0) > 0]
            if metas:
                metas_sorted = sorted(metas, key=lambda m: m.get("date") or "", reverse=True)
                cases = metas_sorted[:5]
                break
        out[wp_id] = cases
    return out


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

    2026-05-27 Task 14: status = forecasts.risk_level 단일 source 통일 (spec §4.2.6).
    사용자 의도: 분포도 (왼쪽 wp_summary) 와 진단 (오른쪽 카드) 의 평가 일관성 보장.
    v2 (_build_productivity_views_v2) 와 동일 lookup 패턴 — 정합성 유지.

    baseline / bp_name / progress / dates 는 후속 task 에서 보강.
    """
    # forecasts.risk_level lookup (v2 와 동일 패턴)
    fc_rows = await pg.fetch_all(
        """
        SELECT f.company, f.l6_main, f.risk_level
        FROM forecasts f JOIN pipeline_runs pr USING (run_id)
        WHERE pr.report_date = $1 AND pr.site_id = $2
        """,
        today,
        site_id,
    )
    risk_lookup: dict[tuple[str, str], str] = {
        (fr["company"], fr["l6_main"]): fr["risk_level"]
        for fr in (fc_rows or [])
        if fr.get("risk_level")
    }

    out: list[dict[str, Any]] = []
    for q in quadrant_jsonb:
        risk_level = risk_lookup.get((q.get("company"), q.get("l6_main")))
        status = _risk_level_to_status(risk_level)
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
    """현 추세 연장 — 직전 7일 평균 rate x remaining days. 결정론적 linear.

    이전: 마지막 1일 delta 만 사용 → outlier (예: mock 9-25 today_qty=6608) 에 흔들림.
    개선: 직전 7일 윈도우 평균. rate <= 0 이면 planned 일평균의 70% 로 fallback.
    또 dedup: 같은 date 가 merged 안에 있으면 그 dict 에 forecast 키만 추가 (중복 row 방지).
    """
    from datetime import date as _date, timedelta
    actual_points = [m for m in merged if m.get("actual") is not None]
    if len(actual_points) < 2:
        return merged

    # 직전 7일 평균 rate (window size 최대 8개 점 — 7 delta).
    window = actual_points[-8:] if len(actual_points) >= 8 else actual_points
    rates: list[float] = []
    for i in range(1, len(window)):
        prev_pt = window[i - 1]
        cur_pt = window[i]
        prev_dt_w = _date.fromisoformat(prev_pt["date"]) if isinstance(prev_pt["date"], str) else prev_pt["date"]
        cur_dt_w = _date.fromisoformat(cur_pt["date"]) if isinstance(cur_pt["date"], str) else cur_pt["date"]
        days = max(1, (cur_dt_w - prev_dt_w).days)
        rates.append((cur_pt["actual"] - prev_pt["actual"]) / days)
    rate = sum(rates) / len(rates) if rates else 0.0

    # fallback: rate <= 0 (또는 매우 작음) 이면 planned 의 일평균 rate × 0.7.
    if rate <= 0:
        planned_points = [m for m in merged if m.get("planned") is not None]
        if len(planned_points) >= 2:
            first_p = planned_points[0]
            last_p = planned_points[-1]
            first_dt = _date.fromisoformat(first_p["date"]) if isinstance(first_p["date"], str) else first_p["date"]
            last_dt2 = _date.fromisoformat(last_p["date"]) if isinstance(last_p["date"], str) else last_p["date"]
            total_days = max(1, (last_dt2 - first_dt).days)
            planned_rate = (last_p["planned"] - first_p["planned"]) / total_days
            rate = planned_rate * 0.7

    last = actual_points[-1]
    last_dt = _date.fromisoformat(last["date"]) if isinstance(last["date"], str) else last["date"]
    last["forecast"] = last["actual"]  # forecast 시작점 = 마지막 actual

    # dedup: 같은 date 가 merged 안에 있으면 그 dict 에 forecast 키만 추가.
    by_date = {m["date"]: m for m in merged}
    out = list(merged)
    for i in range(1, days_ahead + 1):
        next_dt = last_dt + timedelta(days=i)
        key = next_dt.isoformat()
        forecast_val = last["actual"] + rate * i
        if key in by_date:
            by_date[key]["forecast"] = forecast_val
        else:
            new_pt = {"date": key, "forecast": forecast_val}
            out.append(new_pt)
            by_date[key] = new_pt
    return sorted(out, key=lambda x: x["date"])


async def _build_s_curve(
    pg: PGClient,
    site_id: str,
    today: date,
) -> list[dict[str, Any]]:
    """planned/actual/forecast/recovery 4 곡선 unified datapoint list.

    산식 (A): WV × MH 가중 + activity 단위 매칭 + progress cap.
    - 분모 = SUM(plan_wv × plan_mh_rev2)
    - planned[t] = SUM(weight × linear_progress(t)) / 분모 × 100
    - actual[t]  = SUM(weight × MIN(1, cum_qty(t) / plan_qty)) / 분모 × 100
                   (단 mapped_history 와 (wa,l6,company) 매칭되는 activity 만 포함)

    이전 단순 SUM(today_qty) / SUM(plan_total_qty) 는 단위 일관성 부재 (m³+ton+개 혼합).
    """
    async with pg._pool.acquire() as con:
        # site total weight (분모) = SUM(plan_wv × plan_mh_rev2)
        site_total_row = await con.fetchrow(
            """
            SELECT SUM(plan_wv * plan_mh_rev2)::float AS total
            FROM activity_master
            WHERE site_id = $1 AND plan_wv IS NOT NULL AND plan_mh_rev2 IS NOT NULL
              AND l5_disc IN ('건축', '토목')
            """,
            site_id,
        )
        site_total_weight = float(site_total_row["total"] or 0) or 1.0

        plan_end_row = await con.fetchrow(
            "SELECT MAX(plan_finish)::date AS pe FROM activity_master "
            "WHERE site_id = $1 AND l5_disc IN ('건축', '토목')",
            site_id,
        )
        plan_end = plan_end_row["pe"] if plan_end_row else today
        gs_end = max(today + timedelta(days=30), plan_end) if plan_end else (today + timedelta(days=30))

        # planned 곡선 — activity 단위 linear progress × WV×MH weight, 일자별 가중 sum.
        # 2026-05-29 Task 4.4: planned 는 이미 plan_wv×plan_mh 가중이라 unit 차원 추가 불필요 (불변).
        planned = await con.fetch(
            """
            SELECT gs.date::date AS date,
                   SUM(am.plan_wv * am.plan_mh_rev2 * LEAST(1.0, GREATEST(0.0,
                       (gs.date::date - am.plan_start + 1)::float
                       / NULLIF((am.plan_finish - am.plan_start + 1)::float, 0)
                   )))::float AS cum_plan_qty
            FROM activity_master am
            CROSS JOIN LATERAL (
                SELECT d AS date
                FROM generate_series(
                    (SELECT MIN(plan_start) FROM activity_master WHERE site_id = $1 AND l5_disc IN ('건축', '토목')),
                    $2::date,
                    '1 day'::interval
                ) AS d
            ) gs
            WHERE am.site_id = $1 AND am.plan_wv IS NOT NULL AND am.plan_mh_rev2 IS NOT NULL
              AND am.l5_disc IN ('건축', '토목')
            GROUP BY gs.date ORDER BY gs.date
            """,
            site_id,
            gs_end,
        )

        # actual 곡선 — (wa, l6_main) 매칭 + activity progress (cap=1) × weight 일자별 가중 sum.
        # company 매칭 제외: (wa, l6) 단위 매칭률 100% (시연 mock 정합성).
        # cum 누적 보장: 모든 (date × wa × l6) cross join 후 LEFT JOIN — 그날 작업 안 한
        # (wa, l6) 도 직전 누적 cum 유지. 미보정 시 그 일자 가중 sum 에서 빠져 actual % 가 dip.
        #
        # 2026-05-29 SSOT: day_qty 소스 mapped_history → mapper_activities.
        #   mapped_history 는 ON CONFLICT (run_id,wa,l6,company) 마지막값 채택(db.py:489)이라
        #   (wa,l6,company)에 l7_5 세부활동 여러개면 collapse·손실 → 실적% 심각 과소(9/23 11행
        #   sum285 vs mapper 60행 sum533, 27.8%). forecaster 누적(fetch_pg_actual_cum_qty)은
        #   mapper_activities 를 SUM 하므로 둘이 어긋나 'delay 0 vs gap 61%pt' 모순.
        #   → s-curve 실적도 mapper_activities (l7_5 전부 SUM, is_mock=false) 로 통일하여
        #   forecaster 와 동일 소스. report_date 당 단일 run 전제 (PoC/재적재 시 --clean 보장).
        # 2026-05-29 Task 4.4: actual s-curve grain 에 unit 차원 추가. 이전엔 (wa, l6_main)
        # 으로 묶어 혼재 단위(예 m³+ton) qty 를 단순 합산 → plan_qty 비율(cum/plan)이 단위
        # 섞여 왜곡. 이제 (wa, l6_main, unit) 별 누적·plan 비율 후 unit 별 weight 로 가중 sum.
        # weight = 단위별 SUM(plan_wv*plan_mh_rev2). planned 곡선(위)은 불변 (plan_wv×plan_mh 가중 그대로).
        actual = await con.fetch(
            """
            WITH am_agg AS (
                SELECT wa, l6_main, unit,
                       SUM(plan_total_qty)::float AS plan_qty,
                       SUM(plan_wv * plan_mh_rev2)::float AS weight
                FROM activity_master
                WHERE site_id = $1 AND plan_wv IS NOT NULL AND plan_mh_rev2 IS NOT NULL
                  AND unit IS NOT NULL
                  AND l5_disc IN ('건축', '토목')
                GROUP BY wa, l6_main, unit
            ),
            day_qty AS (
                -- 2026-05-29 SSOT: forecaster fetch_pg_actual_cum_qty 와 동일하게
                -- pipeline_runs JOIN 없이 mapper_activities 직접 SUM. JOIN 하면 과거
                -- cleanup 으로 run 삭제된 orphan mapper(전체의 93.6%, 주로 ≤6월 역사)
                -- 가 빠져 실적 급감(8%) → forecaster 누적과 어긋남. 단일 site 데모 전제.
                SELECT ma.report_date, ma.wa, ma.l6_main, ma.unit,
                       SUM(ma.today_qty)::float AS day_qty
                FROM mapper_activities ma
                WHERE ma.report_date <= $2
                  AND ma.is_mock = FALSE
                  AND ma.wa IS NOT NULL AND ma.l6_main IS NOT NULL
                  AND ma.unit IS NOT NULL
                  AND ma.trade IN ('건축', '토목')
                GROUP BY ma.report_date, ma.wa, ma.l6_main, ma.unit
            ),
            dates AS (
                SELECT DISTINCT report_date FROM day_qty
            ),
            full_grid AS (
                SELECT d.report_date, m.wa, m.l6_main, m.unit, m.plan_qty, m.weight
                FROM dates d CROSS JOIN am_agg m
            ),
            cum_actual AS (
                SELECT g.report_date, g.wa, g.l6_main, g.unit, g.plan_qty, g.weight,
                       SUM(COALESCE(dq.day_qty, 0)) OVER (
                           PARTITION BY g.wa, g.l6_main, g.unit ORDER BY g.report_date
                       )::float AS cum_qty
                FROM full_grid g
                LEFT JOIN day_qty dq USING (report_date, wa, l6_main, unit)
            )
            SELECT report_date,
                   SUM(weight * LEAST(1.0, cum_qty / NULLIF(plan_qty, 0)))::float AS cum_weighted
            FROM cum_actual
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

    # merge — planned/actual 모두 이미 일자별 가중 sum (누적), _merge_curves 의 cum 변환 안 씀.
    by_date: dict[str, dict[str, Any]] = {}
    for p in planned:
        d = p["date"]
        key = d.isoformat() if hasattr(d, "isoformat") else str(d)
        by_date.setdefault(key, {"date": key})["planned"] = float(p["cum_plan_qty"] or 0)
    for a in actual:
        d = a["report_date"]
        key = d.isoformat() if hasattr(d, "isoformat") else str(d)
        by_date.setdefault(key, {"date": key})["actual"] = float(a["cum_weighted"] or 0)
    if isinstance(recovery, list):
        for r in recovery:
            d = r.get("date")
            if d is None:
                continue
            key = d.isoformat() if hasattr(d, "isoformat") else str(d)
            by_date.setdefault(key, {"date": key})["recovery_days"] = r.get("recovery_days")
    merged = sorted(by_date.values(), key=lambda x: x["date"])

    # forecast 연장 (그대로)
    forecast_days = max(30, (plan_end - today).days + 30) if plan_end else 30
    extended = _extend_forecast(merged, days_ahead=forecast_days)

    # % 환산 — 분모 = site_total_weight
    for p in extended:
        for k in ("planned", "actual", "forecast"):
            if p.get(k) is not None:
                p[k] = round(min(100.0, p[k] / site_total_weight * 100), 2)
    return extended


def _recovery_distribution_text(degradation_cases: list[dict]) -> str:
    """'N건 중 M건 회복 | D+1 회복 4건 · 미회복 1건' 형식 (similar_cases 바로 밑)."""
    cases = degradation_cases or []
    total = len(cases)
    if not total:
        return "유사 저하 사례 없음"
    dist: dict[str, int] = {}
    recovered = 0
    for c in cases:
        rd = (c.get("recovery") or {}).get("recovery_days") if isinstance(c.get("recovery"), dict) else None
        if rd:
            dist[f"D+{rd}"] = dist.get(f"D+{rd}", 0) + 1
            recovered += 1
        else:
            dist["미회복"] = dist.get("미회복", 0) + 1
    parts = " · ".join(
        f"{k} 회복 {v}건" if k != "미회복" else f"미회복 {v}건"
        for k, v in sorted(dist.items())
    )
    return f"{total}건 중 {recovered}건 회복 | {parts}"


def _diagnosis_prefix(prod_info: Optional[dict], conditions: str) -> str:
    """진단 첫 줄 — '{조건} 조건에서 생산성 X {unit} (정상 페이스 대비 Z%)'.

    prod_info: {perperson, unit, productivity_pct}. None 이면 "" (LLM diagnosis 그대로).
    """
    if not prod_info:
        return ""
    cond = (conditions or "정상").split(",")[0].strip() or "정상"
    pp = prod_info.get("perperson")
    unit = prod_info.get("unit") or ""
    pct = prod_info.get("productivity_pct")
    if pp is None or pct is None:
        return ""
    dev = round(pct - 100)
    return f"{cond} 조건에서 생산성 {pp:.2f} {unit} (정상 페이스 대비 {dev:+d}%)."


def _build_optimizer_view(
    advice_rows: list[dict[str, Any]],
    forecast: list[dict[str, Any]],
    mapped: list[dict[str, Any]],
    wa_lookup: Optional[dict[tuple[str, str], list[str]]] = None,
    prod_lookup: Optional[dict[tuple[str, str], dict]] = None,
) -> dict[str, Any]:
    """§ 02 by_wp dict — 진단/유사사례/권고/상세 6칸.

    advice = optimizer_advice 의 row. forecast = forecasts 의 row (wa lookup).

    wa_lookup: (l6_main, company) → DISTINCT wa list. fan-out 용.
                전달되면 한 advice 를 wa list 의 각 wa 마다 by_wp 에 복사.
                None / 빈 dict 면 forecasts.wa 1개 기준 단일 key (기존 동작).
                spec §8.3 — quadrant dot 의 wp_id (mapper_activities 기반) 와 매칭 보장.
    """
    # late import — 모듈 상단 전역 import 는 autoflake 가 (멀리 떨어진 사용처를 놓쳐) 제거함.
    from pipeline.agents.optimizer._trade_frames import lookup_frame
    from pipeline.agents.optimizer._work_content import work_content_for

    wa_lookup = wa_lookup or {}
    prod_lookup = prod_lookup or {}
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
        # 2026-05-22: description 표현 fix — 단위 (main_unit) + 인원 수 명시.
        # 이전: "생산성 0.5" → 어느 단위인지 모름 (m/인? ton/인? %?)
        # 변경: "생산성 0.52 m/인 (인원 107명)" — main_unit 출처는 matched_f.main_unit (forecasts row).
        main_unit = matched_f.get("main_unit") or ""
        unit_suffix = f" {main_unit}/인" if main_unit else "/인"
        frame_cat, _frame_text = lookup_frame(advice.get("l6_main"))
        # 2026-05-29: 저하/회복 work_content 분리 (사용자 요청 — 직관적 narrative).
        # degraded = 저하일 work_content (실제 그날 작업).
        # recovered = 저하 조건의 "회복" bank narrative ("그 조건이 어떻게 풀렸나").
        #   D+1 metadata work_content 를 쓰면 회복일이 또 다른 incident 일 때 저하 문구가
        #   들어가 "회복: ~재시공 발생" 처럼 어긋났다. 저하 조건 기준 bank 로 일관.
        # FE (OptimizerResult) 가 condition/degraded/recovered/recovery_days 렌더.
        similar_cases = []
        for c in (advice.get("degradation_cases") or []):
            conditions = (c.get("conditions") or "정상").split(",")[0].strip()
            recovery = c.get("recovery") or {}
            rd = recovery.get("recovery_days") if isinstance(recovery, dict) else None
            degraded_wc = c.get("work_content") or ""
            recovered_wc = work_content_for(frame_cat, conditions, "회복")
            similar_cases.append({
                "date": c.get("date") or "",
                "condition": conditions,
                "degraded": degraded_wc,
                "recovered": recovered_wc,
                "recovery_days": rd,
                # legacy 호환 (옛 FE / export)
                "description": f"{conditions} — {degraded_wc}" if degraded_wc else conditions,
                "outcome": f"{rd}일 후 회복" if rd is not None else "미회복",
            })

        # 2026-05-28: V10 polymorphic — keyword/action/reason dict 도 그대로 forward.
        # FE (OptimizerResult.tsx) 가 string vs object 분기 렌더.
        recs_raw = advice.get("recommendations") or []
        recommendations: list = []
        for r in recs_raw:
            if isinstance(r, dict):
                if "keyword" in r and "action" in r:
                    # V10 schema — dict 그대로
                    recommendations.append(r)
                elif "text" in r:
                    # 옛 schema {rank, text} — text 만 string 으로
                    recommendations.append(r.get("text") or "")
                else:
                    recommendations.append(str(r))
            else:
                recommendations.append(str(r))
        # 2026-05-28: LLM 우회 (4건 출력) 차단 — wp 당 최대 3건 trim (사용자 의도: 1-2건 default, 복잡 시 3건).
        recommendations = recommendations[:3]

        # 6칸 details
        # 2026-05-29 (2차) 사용자: UI 가 3건만 표시하므로 회복 요약도 "표시되는 3건" 기준 +
        # 평균 회복일수 편입. (이전엔 5건 집계라 "5건 중 3건"처럼 보여 불일치.)
        cases_for_dist = (advice.get("degradation_cases") or [])[:3]
        rdist_text = _recovery_distribution_text(cases_for_dist)
        rd_vals = [
            (c.get("recovery") or {}).get("recovery_days")
            for c in cases_for_dist
            if isinstance(c.get("recovery"), dict) and (c.get("recovery") or {}).get("recovery_days")
        ]
        avg_rd: Optional[float] = (sum(rd_vals) / len(rd_vals)) if rd_vals else None
        # 평균 회복일수를 회복 요약줄(유사사례 바로 밑)에 편입 — 사용자 요청.
        if avg_rd is not None and rdist_text and "없음" not in rdist_text:
            rdist_text = f"{rdist_text} · 평균 {avg_rd:.1f}일 회복"

        # 2026-05-29: 진단 prefix (정상 페이스 대비 %) + LLM 패턴 판단 합성. (그룹 narrative)
        prod_info = prod_lookup.get((advice.get("company"), advice.get("l6_main")))
        prefix = _diagnosis_prefix(prod_info, matched_f.get("today_conditions") or "")
        llm_diag = advice.get("diagnosis") or ""
        diagnosis = f"{prefix}\n{llm_diag}".strip() if prefix else llm_diag

        # 2026-05-29 SSOT: per-wa 숫자 (위험평가·생산성·일정영향·산출근거)는 그 wa 의 forecast 에서.
        # 이전엔 matched_f (company,l6 첫 행) 를 모든 wa 에 broadcast → 같은 (company,l6)에 wp 2개면
        # 목록(per-wa risk) 과 카드(broadcast risk) 가 어긋났다 (예 cub/fab 승강기).
        for wa in wa_list:
            wp_id = _wp_id_of(wa, advice.get("l6_main"), advice.get("company"))
            wa_f = next(
                (
                    f
                    for f in forecast
                    if f.get("wa") == wa
                    and f.get("company") == advice.get("company")
                    and f.get("l6_main") == advice.get("l6_main")
                ),
                matched_f,
            )
            # 2026-05-29 SSOT: 금일 생산성 = 진단 prefix 와 동일 source (perperson m2/인).
            # 이전엔 today_productivity(정규화 %)에 " m2/인" 라벨을 붙여 단위 불일치
            # ("81.00 m2/인" 처럼) — prefix 의 perperson 과 어긋났다.
            _pp = prod_info.get("perperson") if prod_info else None
            _pu = prod_info.get("unit") if prod_info else None
            wa_prod_text = (
                f"{float(_pp):.2f} {_pu}" if (_pp is not None and _pu) else "—"
            )
            # 2026-05-29 (2차): 계획 생산성(계획 인당) — 계획 대비 금일 비교 (사용자 요청).
            # 금일생산성 ÷ (생산성%/100) 으로 역산 → 진단 prefix '정상 대비 %' 와 화면상 일치 보장.
            # (master_perperson 직접 표시 시 group/median 산식 차이로 %와 어긋나 0.63 vs 2.02(-19%) 모순.)
            _pct = prod_info.get("productivity_pct") if prod_info else None
            if _pp is not None and _pct and float(_pct) > 0 and _pu:
                plan_prod_text = f"{float(_pp) / (float(_pct) / 100.0):.2f} {_pu}"
            else:
                plan_prod_text = "—"
            wa_delay = round(wa_f.get("delay_days") or 0)
            # 2026-05-29 (2차): 산출근거를 인시(MH) jargon 대신 "며칠치 작업량" 직관 문장으로 (사용자 요청).
            if wa_delay > 0:
                delay_basis = f"계획 대비 약 {wa_delay}일치 작업량이 덜 진행돼 {wa_delay}일 지연"
                sched_val = f"{wa_delay}일 지연"
            elif wa_delay < 0:
                delay_basis = f"계획보다 약 {abs(wa_delay)}일치 작업량을 더 진행해 {abs(wa_delay)}일 앞섬"
                sched_val = f"{abs(wa_delay)}일 선행"
            else:
                delay_basis = "계획한 진도를 맞춰 진행 중 (지연 없음)"
                sched_val = "일정 충족"
            # 2026-05-29 (2차) 상세현황 정리 (사용자 요청):
            #  - 유사 사례 수 제거 → '공사기간'(마스터플랜 company+l6 기간) 추가
            #  - 계획 생산성 / 금일 생산성 (계획 대비 비교) · 일정 영향 = WP 공기단축 일수 · 산출근거
            plan_period = (prod_info.get("plan_period") if prod_info else None) or "—"
            details = [
                {"label": "진단 대상", "value": f"{advice.get('company') or ''} · {advice.get('l6_main') or ''}"},
                {"label": "공사기간", "value": plan_period},
                {"label": "계획 생산성", "value": plan_prod_text},
                {"label": "금일 생산성", "value": wa_prod_text},
                {"label": "일정 영향", "value": sched_val},
                {"label": "산출근거", "value": delay_basis},
            ]
            by_wp[wp_id] = {
                "diagnosis": diagnosis,
                "similar_cases": similar_cases,
                # similar_cases 바로 밑 표시용 회복 분포 ("N건 중 M건 D+1 회복").
                "recovery_distribution_text": rdist_text,
                "recommendations": recommendations,
                "details": details,
            }

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

    2026-05-26 변경 3: advice["scenarios"] (LLM 출력) 우선 사용.
    LLM 출력 없는 advice 는 deterministic percentile fallback (결정 #20 의 recovery_distribution 기반).

    LLM scenarios key (no_action/optimistic/base/pessimistic) → 기존 key
    (no_action/optimistic_p25/base_p50/pessimistic_p75) 로 매핑하여 FE 영향 0.
    """

    def _wp_block_from_llm(s: dict, no_action_date) -> dict:
        no_action_iso = (
            no_action_date.isoformat() if isinstance(no_action_date, date) else None
        )

        def _slot(key: str, default_delta: int = 0) -> dict:
            x = s.get(key) or {}
            return {
                "expected_completion": x.get("expected_completion") or no_action_iso,
                "recovery_days": int(x.get("recovery_days") or 0),
                "delta_days": int(x.get("delta_days") or default_delta),
                "case_count": 1,
                "rationale": x.get("rationale", ""),
            }

        return {
            "no_action": _slot("no_action"),
            "optimistic_p25": _slot("optimistic"),
            "base_p50": _slot("base"),
            "pessimistic_p75": _slot("pessimistic"),
        }

    def _wp_block_deterministic(advice: dict, no_action_date) -> dict:
        wp_days = _expand_recovery_to_days(advice.get("recovery_distribution") or {})
        return {
            "no_action": {
                "expected_completion": no_action_date.isoformat() if no_action_date else None,
                "recovery_days": 0,
                "delta_days": 0,
                "case_count": len(wp_days),
            },
            "optimistic_p25": _scenario(no_action_date, _percentile(wp_days, 0.75), len(wp_days)),
            "base_p50": _scenario(no_action_date, _percentile(wp_days, 0.50), len(wp_days)),
            "pessimistic_p75": _scenario(no_action_date, _percentile(wp_days, 0.25), len(wp_days)),
        }

    by_wp: dict[str, dict] = {}
    for advice in advice_rows:
        f = _match_forecast_by_company_l6(advice, forecast)
        if f is None:
            continue
        wp_id = _wp_id_of(f.get("wa"), advice.get("l6_main"), advice.get("company"))
        wp_no_action = _coerce_date(f.get("expected_completion"))
        llm_scenarios = advice.get("scenarios") or {}
        if llm_scenarios and any(llm_scenarios.get(k) for k in ("no_action", "optimistic", "base", "pessimistic")):
            by_wp[wp_id] = _wp_block_from_llm(llm_scenarios, wp_no_action)
        else:
            by_wp[wp_id] = _wp_block_deterministic(advice, wp_no_action)

    # site = by_wp 의 집계 (no_action 은 max ec, 나머지는 sum recovery_days)
    # 2026-05-28: median → sum 변경 (사용자 의도: "a공종 2일+b공종 1일+c공종 2일=5일").
    # 모든 advice 있는 wp 의 recovery_days 단순 합. 사용자가 산출 근거 직접 추적 가능.
    def _site_slot(slot_key: str) -> dict:
        items = [b[slot_key] for b in by_wp.values() if b.get(slot_key)]
        if not items:
            return {
                "expected_completion": None,
                "recovery_days": 0,
                "delta_days": 0,
                "case_count": 0,
            }
        ecs = [_coerce_date(it.get("expected_completion")) for it in items]
        ecs = [e for e in ecs if e is not None]
        max_ec = max(ecs) if ecs else None
        sum_rec = sum(int(it.get("recovery_days") or 0) for it in items)
        return {
            "expected_completion": max_ec.isoformat() if max_ec else None,
            "recovery_days": sum_rec,
            "delta_days": -sum_rec if slot_key != "no_action" else 0,
            "case_count": len(items),
        }

    site_scenarios = {
        "no_action": _site_slot("no_action"),
        "optimistic_p25": _site_slot("optimistic_p25"),
        "base_p50": _site_slot("base_p50"),
        "pessimistic_p75": _site_slot("pessimistic_p75"),
    }
    # by_wp 가 비어있고 forecast 만 있는 경우 — 최후 fallback (site no_action 만 forecast.max ec)
    if not by_wp and forecast:
        ecs = [_coerce_date(f.get("expected_completion")) for f in forecast]
        ecs = [e for e in ecs if e is not None]
        if ecs:
            site_scenarios["no_action"] = {
                "expected_completion": max(ecs).isoformat(),
                "recovery_days": 0,
                "delta_days": 0,
                "case_count": len(ecs),
            }

    return {"site": site_scenarios, "by_wp": by_wp}


# ─────────────────────────────────────────────────────────────────
# Phase 1 (2026-05-21) v2 helper: 4단 산식 + display_label
# ─────────────────────────────────────────────────────────────────



def _compute_daily_quota(plan_total_qty: float, total_days: int) -> float:
    """마스터 plan_total_qty 를 일일 quota 로 환산."""
    if total_days <= 0 or plan_total_qty <= 0:
        return 0.0
    return plan_total_qty / total_days


def _compute_productivity(perperson: float, master_perperson: float) -> float:
    """인당 / 마스터 인당 * 100. master <= 0 면 0."""
    if master_perperson <= 0:
        return 0.0
    return perperson / master_perperson * 100


def _row_productivity(
    today_qty: float,
    assigned_workers: float,
    daily_qty_master: float,
    daily_workers_master: float,
) -> dict[str, float]:
    """실 seeded today_qty/workers 로 perperson + productivity%. (구 _simulate_today_qty 폐기)"""
    perperson = (today_qty / assigned_workers) if assigned_workers > 0 else 0.0
    master_perperson = (
        (daily_qty_master / daily_workers_master) if daily_workers_master > 0 else 0.0
    )
    productivity = min(_compute_productivity(perperson, master_perperson), 150.0)
    return {"perperson": perperson, "productivity": productivity}


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


def _normalize_impact_share(impacts: list[float]) -> list[float]:
    """impact share-of-total (일별 합 = 100%). 사용자 요청 의도 "비율".

    이전 max-normalize (단일 wp 가 항상 100% 받음) 는 일별 합이 100% 가 아님 → share 로 변경.
    grouped_items 의 agg_impact 는 sum() 으로 group 합 = 그 wp_id 의 share. 모든 wp_id share 합 = 100%.

    NOTE 2026-05-22: line 374 의 `_normalize_impact(raw, p90)` 와 이름 충돌로 후자가 shadowing
    → line 743 호출 시 "takes 1 positional argument but 2 were given" 발생. 이름 분리.
    """
    if not impacts:
        return []
    total = sum(impacts)
    if total <= 0:
        return [0.0] * len(impacts)
    return [round(x / total * 100, 2) for x in impacts]


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


def _risk_level_to_status(risk_level: Optional[str]) -> str:
    """2026-05-27: forecaster.risk_level (정상/주의/이상) → FE status (normal/caution/risk).

    wp_summary.status 를 forecaster RAG delta 기반 평가와 일관성 있게 통일.
    """
    if risk_level == "이상":
        return "risk"
    if risk_level == "주의":
        return "caution"
    if risk_level == "정상":
        return "normal"
    return "normal"


def _quadrant_of(prod: float, impact: float) -> str:
    if prod < 70 and impact >= 50:
        return "risk"
    if prod < 70:
        return "caution"
    if impact >= 50:
        return "watch"
    return "safe"


def _quadrant_status3(prod: float, impact: float) -> str:
    """2026-05-29 (2차) 사용자 결정: status = 분포도 위치 기준 (점 색=위치).
    목록칩·카드·KPI 용 3-tier. 분포도 점은 FE 가 4값 quadrant 필드로 직접 4색(관찰=회색).
      위험(risk)=저생산<70 & 고임팩≥50 / 주의(caution)=저생산 단독 또는 고임팩 단독 / 정상(normal).
    risk_level(과거대비 RAG)은 LLM 진단 입력으로만 — UI status 미사용 (디럭스=초록위치인데 주황 해소).
    """
    if prod < 70 and impact >= 50:
        return "risk"
    if prod < 70 or impact >= 50:
        return "caution"
    return "normal"


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
               ma.unit, ma.zone, ma.wa, ma.today_qty, ma.assigned_workers, ma.trade,
               m.ps AS plan_start, m.pf AS plan_finish,
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
          AND ma.trade IN ('건축', '토목')  -- 2026-05-27 Task 17: 안전망 (#N17)
        """,
        today,
        site_id,
    )
    if not rows:
        # 2026-06-02 fallback: 실 prod run 은 parser.py:445 가 l7_5_activity=None 하드코딩이라
        # 위 (company,l6,l7_5) 매칭이 0행 → wp_summary 등 전부 빔(더미 시드만 l7_5 보유).
        # l7_5 없이 (wa,l6_main,company,unit) 로 실적 집계 + activity_master (company,l6,unit)
        # plan 매칭(1회). 다운스트림은 그대로(wp_id 그룹핑). dummy 경로는 위 쿼리가 잡으므로 불변.
        rows = await pg.fetch_all(
            """
            WITH actual AS (
                SELECT pr.site_id, ma.company, ma.l6_main, ma.unit, ma.wa,
                       SUM(COALESCE(ma.today_qty, 0))::float AS today_qty,
                       SUM(COALESCE(ma.assigned_workers, 0))::float AS assigned_workers,
                       MAX(ma.trade) AS trade
                FROM mapper_activities ma
                JOIN pipeline_runs pr USING (run_id)
                WHERE ma.report_date = $1
                  AND pr.site_id = $2
                  AND ma.trade IN ('건축', '토목')
                  AND ma.unit IS NOT NULL
                GROUP BY pr.site_id, ma.company, ma.l6_main, ma.unit, ma.wa
            ),
            plan AS (
                SELECT company, l6_main, unit,
                       MIN(plan_start) AS ps, MAX(plan_finish) AS pf,
                       SUM(plan_total_qty) AS qty, SUM(plan_mh_rev2) AS mh
                FROM activity_master
                WHERE site_id = $2
                GROUP BY company, l6_main, unit
            )
            SELECT (row_number() OVER ())::int AS id, a.site_id, NULL::uuid AS run_id,
                   a.company, a.l6_main, NULL::text AS l7_5_activity,
                   a.unit, NULL::text AS zone, a.wa,
                   a.today_qty, a.assigned_workers, a.trade,
                   p.ps AS plan_start, p.pf AS plan_finish,
                   p.qty AS plan_total_qty, p.mh AS plan_mh
            FROM actual a
            JOIN plan p ON p.company = a.company AND p.l6_main = a.l6_main AND p.unit = a.unit
            WHERE p.ps IS NOT NULL AND $1 BETWEEN p.ps AND p.pf
            """,
            today,
            site_id,
        )
    if not rows:
        return dict(_VIEWS_V2_EMPTY)

    # 2026-05-29 SSOT: forecasts.risk_level lookup — wp_summary·분포도·카드 status 단일 source.
    # (wa, company, l6_main) → risk_level. 이전엔 (company, l6_main) 키라 같은 (company,l6)에
    # wp 2개(예 cub/fab 승강기)면 last-writer-wins 로 한 risk 가 둘에 적용 → 목록 vs 카드 불일치.
    fc_rows = await pg.fetch_all(
        """
        SELECT f.wa, f.company, f.l6_main, f.risk_level
        FROM forecasts f JOIN pipeline_runs pr USING (run_id)
        WHERE pr.report_date = $1 AND pr.site_id = $2
        """,
        today,
        site_id,
    )
    risk_lookup: dict[tuple[str, str, str], str] = {
        (fr["wa"], fr["company"], fr["l6_main"]): fr["risk_level"]
        for fr in (fc_rows or [])
        if fr.get("risk_level")
    }

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
        # 2026-05-29 Task 4.1: _simulate_today_qty 폐기 — 실 seeded today_qty/workers 사용.
        # 이전엔 마스터 daily × random noise 로 재생성해 r["today_qty"]/assigned_workers 를
        # 버려서 condition-blind + forecaster 와 불일치. 이제 실 실적값으로 직접 산정.
        # 2026-06-02: assigned_workers 가 실 작업일보(통합)에서 mh-누계 단위(수만)로 들어와
        # perperson 왜곡 → productivity 7.9%/150 들쭉. _sanitize_workers (≤50 그대로, 그 외
        # master±10% / ÷8) 로 headcount 정상화. dummy(≤50)는 불변.
        _seed_w = f"{r['wa']}|{r['company']}|{r['l6_main']}|{r['unit']}"
        _workers_n = float(_sanitize_workers(
            float(r["assigned_workers"] or 0.0), daily_workers_master, _seed_w
        ))
        rp = _row_productivity(
            float(r["today_qty"] or 0.0),
            _workers_n,
            daily_qty_master,
            daily_workers_master,
        )
        perperson = rp["perperson"]
        master_perperson = daily_qty_master / daily_workers_master
        productivity = rp["productivity"]
        impact_raw = max(0.0, 100 - productivity) * plan_mh
        items.append(
            {
                "id": r["id"],
                "site_id": r["site_id"],
                "company": r["company"],
                "l6_main": r["l6_main"],
                "l7_5_activity": r["l7_5_activity"],
                "unit": r["unit"],
                "wa": r["wa"],
                "actual_trade": r["trade"],
                "assigned_workers": _workers_n,
                "today_qty": r["today_qty"],
                "workers": _workers_n,
                "plan_total_qty": plan_qty,
                "plan_mh": plan_mh,
                "perperson": perperson,
                "master_perperson": master_perperson,
                "master_daily_qty": daily_qty_master,
                "master_daily_workers": daily_workers_master,
                # 2026-05-29 SSOT: forecaster risk_level 동기 (wa 단위) — wp_summary·분포도·카드 통일.
                "risk_level": risk_lookup.get((r["wa"], r["company"], r["l6_main"])),
                "productivity": productivity,
                "impact_raw": impact_raw,
            }
        )

    if not items:
        return dict(_VIEWS_V2_EMPTY)

    # impact 정규화
    impacts_norm = _normalize_impact_share([it["impact_raw"] for it in items])
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
    # wp_id 별 group by — 같은 (wa, l6_main, company) 에 여러 mapper row 가 있을 때
    # quadrant/wp_summary 가 row 마다 중복되지 않도록 통합. wp_name 에 wa 추가하여 구역 구분.
    from collections import defaultdict
    import statistics as _stats

    groups: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        wp_id = _wp_id_of(it["wa"], it["l6_main"], it["company"])
        groups[wp_id].append(it)

    grouped_items: list[dict] = []
    for wp_id, grp in groups.items():
        head = grp[0]
        agg_today_qty = sum((it.get("today_qty") or 0) for it in grp)
        agg_workers = sum((it.get("workers") or 0) for it in grp)
        agg_assigned_workers = sum((it.get("assigned_workers") or 0) for it in grp)
        agg_plan_qty = sum((it.get("plan_total_qty") or 0) for it in grp)
        agg_plan_mh = sum((it.get("plan_mh") or 0) for it in grp)
        prods = [it["productivity"] for it in grp if it.get("productivity") is not None]
        impacts = [it.get("impact") or 0 for it in grp]
        agg_prod = _stats.median(prods) if prods else 0.0
        # impact 은 share-of-total — group SUM 이 그 wp_id 의 share. 일별 sum(grouped) = 100%.
        agg_impact = sum(impacts) if impacts else 0.0
        agg_pp = (agg_today_qty / agg_workers) if agg_workers else 0.0
        agg_master_dq = head.get("master_daily_qty") or 0
        agg_master_dw = head.get("master_daily_workers") or 0
        # 2026-05-29 Task 4.3: 혼재 WP 의 단위별 detail (m³/인·ton/인 분리). group 내부를
        # unit 으로 재집계하고 plan_mh 최대 unit 을 대표(rep)로 노출. wp_summary/quadrant headline 용.
        from collections import defaultdict as _dd

        by_unit = _dd(list)
        for it in grp:
            by_unit[it.get("unit")].append(it)
        units_detail = []
        for u, urs in by_unit.items():
            u_qty = sum((x.get("today_qty") or 0) for x in urs)
            u_workers = sum((x.get("workers") or 0) for x in urs)
            u_mh = sum((x.get("plan_mh") or 0) for x in urs)
            u_prods = [x["productivity"] for x in urs if x.get("productivity") is not None]
            units_detail.append({
                "unit": u,
                "perperson": round(u_qty / u_workers, 2) if u_workers else 0.0,
                "productivity": round(_stats.median(u_prods), 1) if u_prods else 0.0,
                "plan_mh": u_mh,
            })
        rep = max(units_detail, key=lambda d: d["plan_mh"]) if units_detail else None
        grouped_items.append({
            **head,
            "wp_id": wp_id,
            "today_qty": agg_today_qty,
            "workers": agg_workers,
            "assigned_workers": agg_assigned_workers,
            "plan_total_qty": agg_plan_qty,
            "plan_mh": agg_plan_mh,
            "perperson": agg_pp,
            "productivity": agg_prod,
            "impact": agg_impact,
            "master_daily_qty": agg_master_dq,
            "master_daily_workers": agg_master_dw,
            "row_count": len(grp),
            "units_detail": sorted(units_detail, key=lambda d: -d["plan_mh"]),
            "rep_unit": rep["unit"] if rep else None,
            "rep_perperson": rep["perperson"] if rep else None,
        })

    def _wp_name_with_wa(it: dict) -> str:
        # 2026-05-29 Task 4.2: 카드 라벨만 l7_5 → l6_main. row grain 은 l7_5 유지
        # (SELECT/grouping 불변) — 라벨 변경일 뿐 rollup 아님.
        wa = it.get("wa")
        return f"{it['l6_main']} · {wa}" if wa else it["l6_main"]

    # T17: impact > 0 필터 제거 — grouped_items 전체를 quadrant 에 포함.
    # 이전: impact=0 (plan_total_qty=0 || plan_mh=0) row 를 산점도에서 제외했으나,
    # optimizer_view.by_wp 는 cold_start fallback 으로 quadrant 전체를 커버해야 함.
    # impact=0 점은 산점도에서 size 최소(0.1)로 표시되어 UI 영향 최소.
    # 결과: quadrant wp_id 집합 = by_wp wp_id 집합 → verify 5번 Jaccard >= 80% 달성.
    quadrant = [
        {
            "wp_id": it["wp_id"],
            "wp_name": _wp_name_with_wa(it),
            "l7_5_activity": it["l7_5_activity"],
            "company": it["company"],
            "l6_main": it["l6_main"],
            "actual_trade": it.get("actual_trade") or "",
            "workers": int(it.get("assigned_workers") or 1),
            "trade": it["l6_main"],
            "productivity": round(it["productivity"], 1),
            "impact": round(it["impact"], 1),
            "quadrant": _quadrant_of(it["productivity"], it["impact"]),
            # 2026-05-29 (2차): 목록칩·카드용 status = 위치기반 3-tier. 분포도 점 색은 FE 가
            # 4값 quadrant 필드로 직접(관찰=회색). risk_level 은 LLM 입력으로만.
            "status": _quadrant_status3(it["productivity"], it["impact"]),
            "risk_level": it.get("risk_level"),
            "size": max(0.1, round((it["plan_total_qty"] or 1) / 10, 1)),
            "perperson": round(it["perperson"], 2),
            "perperson_unit": f"{it['unit']}/인" if it["unit"] else None,
            "display_label": _make_display_label(
                it["productivity"], it["perperson"], it["unit"]
            ),
            # 2026-05-29 Task 4.3: 혼재 WP 단위별 detail (group 내부 unit 별 perperson/prod/plan_mh).
            "units_detail": it.get("units_detail") or [],
        }
        for it in grouped_items
    ]
    # WP 목록 = impact 내림차순 (사용자: 임팩트 높은순).
    wp_summary = sorted(
        (
            {
                "wp_id": it["wp_id"],
                "wp_name": _wp_name_with_wa(it),
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
                # 2026-05-29 (2차): status = 위치기반 3-tier (분포도와 동일 기준). risk_level 보조.
                "status": _quadrant_status3(it["productivity"], it["impact"]),
                "risk_level": it.get("risk_level"),
                # 2026-05-29 Task 4.3: 단일 per-unit headline 은 plan_mh 최대 unit(rep) 기준.
                # 혼재 WP 에서 mixed-unit 합산 perperson 은 무의미 → 대표 단위로 노출.
                "perperson": (
                    it["rep_perperson"]
                    if it.get("rep_perperson") is not None
                    else round(it["perperson"], 2)
                ),
                "perperson_unit": (
                    f"{it['rep_unit']}/인"
                    if it.get("rep_unit")
                    else (f"{it['unit']}/인" if it["unit"] else None)
                ),
                # 2026-05-29 (2차): 계획 인당 생산성 — 상세현황 "계획 생산성"(계획대비 금일 비교)용.
                "master_perperson": (
                    round(it["master_daily_qty"] / it["master_daily_workers"], 2)
                    if it.get("master_daily_workers")
                    else None
                ),
                "display_label": _make_display_label(
                    it["productivity"],
                    (
                        it["rep_perperson"]
                        if it.get("rep_perperson") is not None
                        else it["perperson"]
                    ),
                    it.get("rep_unit") if it.get("rep_unit") else it["unit"],
                ),
                # 2026-05-29 Task 4.3: 혼재 WP 단위별 detail.
                "units_detail": it.get("units_detail") or [],
            }
            for it in grouped_items
        ),
        key=lambda w: -float(w.get("impact") or 0),
    )
    # kpi 의 delay_days / expected_completion 은 forecasts AGG 기반.
    # 이전 하드코딩 (0, today.replace(day=1)) 은 화면 진단 inconsistent — 시연 핵심 지표.
    async with pg._pool.acquire() as con:
        fc_agg = await con.fetchrow(
            """
            -- 2026-05-23: AVG -> MEDIAN. AVG 는 outlier 1건에 끌려가 site KPI 가
            -- 비현실 (예: 동신패널 외장판넬 atomic 1행 dummy anomaly = 167,871일
            -- -> AVG=2,398). MEDIAN 은 "일반적 그룹 delay" 의미.
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delay_days)::float AS delay,
                   PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY expected_completion) AS expected_completion
            FROM forecasts f JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pr.report_date = $2
              AND delay_days IS NOT NULL
""",
            site_id, today,
        )
    kpi_delay = round((fc_agg["delay"] if fc_agg else 0) or 0)
    kpi_ec = fc_agg["expected_completion"] if fc_agg else None
    # 2026-05-29 (2차): site KPI = wp 4사분면 중 최악 → 3-tier 한글(이상/주의/정상)로.
    # 분포도·목록·카드 status(_quadrant_of)와 동일 기준. risk(위험)→이상, caution(저생산)·
    # watch(고임팩)→주의, safe→정상. (report 목록 route 가 이상→risk, 주의→caution 매핑.)
    _q_order = {"safe": 0, "watch": 1, "caution": 1, "risk": 2}
    _q_to_kpi = {"risk": "이상", "caution": "주의", "watch": "주의", "safe": "정상"}
    _wp_quads = [_quadrant_of(it["productivity"], it["impact"]) for it in grouped_items]
    site_risk = (
        _q_to_kpi.get(max(_wp_quads, key=lambda x: _q_order.get(x, 0)))
        if _wp_quads
        else None
    )
    kpi = {
        "risk_level": site_risk,
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
        "delay_days": kpi_delay,
        "expected_completion": kpi_ec.isoformat() if kpi_ec else None,
        "recoverable_productivity": round(max(0, 100 - site_wv_median), 1),
        "target_productivity": 100,
        # recovery_days / recovered_completion 은 scenarios 산출 후 갱신 (return 직전).
        "recovery_days": 0,
        "recovered_completion": None,
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

    # Phase 2 — optimizer_view 통합 (advice 매칭 + cold_start fallback).
    advice_rows = await pg.fetch_all(
        "SELECT * FROM optimizer_advice WHERE run_id IN "
        "(SELECT run_id FROM pipeline_runs WHERE site_id=$1 AND report_date=$2)",
        site_id,
        today,
    )
    forecast_rows = await pg.fetch_all(
        "SELECT * FROM forecasts WHERE run_id IN "
        "(SELECT run_id FROM pipeline_runs WHERE site_id=$1 AND report_date=$2)",
        site_id,
        today,
    )
    # asyncpg 는 jsonb 를 str 로 반환 — list/dict 로 inflate.
    import json as _json
    _JSONB_KEYS = (
        "degradation_cases", "recommendations", "recovery_pattern",
        "recovery_distribution", "work_context",
    )
    for row in advice_rows:
        for k in _JSONB_KEYS:
            v = row.get(k)
            if isinstance(v, str):
                try:
                    row[k] = _json.loads(v)
                except Exception:
                    row[k] = None
    wa_lookup = _build_wa_lookup(items)
    # 2026-05-29 (2차) 사용자: 상세현황 '공사기간' = 그 공종(company+l6_main)의 마스터플랜 기간.
    # l6 단위 집계 — 시작일=MIN(plan_start), 종료일=MAX(plan_finish). (향후 l6 단위 계산 컨셉과 정합.)
    _date_rows = await pg.fetch_all(
        "SELECT company, l6_main, MIN(plan_start) AS ps, MAX(plan_finish) AS pf "
        "FROM activity_master WHERE site_id=$1 GROUP BY company, l6_main",
        site_id,
    )
    _l6_period = {
        (r["company"], r["l6_main"]): (
            f"{r['ps'].isoformat()} ~ {r['pf'].isoformat()}"
            if r.get("ps") and r.get("pf")
            else None
        )
        for r in (_date_rows or [])
    }
    # 2026-05-29: 진단 prefix (정상 페이스 대비 %) 산출용 — wp_summary 의 perperson/productivity_pct.
    prod_lookup = {
        (w["bp_name"], w["trade"]): {
            "perperson": w.get("perperson"),
            "unit": w.get("perperson_unit"),
            "productivity_pct": w.get("productivity"),
            "master_perperson": w.get("master_perperson"),
            "plan_period": _l6_period.get((w["bp_name"], w["trade"])),
        }
        for w in wp_summary
    }
    optimizer_view = _build_optimizer_view(
        advice_rows, forecast_rows, items, wa_lookup, prod_lookup=prod_lookup,
    )

    # 2026-05-28 Task 16: cold_start 분기 폐기. 사용자 명시 — "콜드케이스는 절대로 없어야돼
    # 오류가 나면 다시 재시도 하던가 해야되고 조건식에 안걸리면 그 날짜만 따로 취합해서
    # 재시도 하던가 해야돼". 모든 wp 는 LLM advice 보장 (retry 3-tier + Task 30 failed_wps
    # batch). advice 적재 실패한 wp 는 by_wp entry X — FE 가 graceful handling.
    # by_wp = quadrant 1:1 보장은 retry path 가 책임 (cold_start fan-out 폐기).
    quadrant_ids = {q["wp_id"] for q in quadrant}
    optimizer_view["by_wp"] = {
        k: v for k, v in optimizer_view["by_wp"].items() if k in quadrant_ids
    }
    if optimizer_view.get("default_wp_id") is None and optimizer_view["by_wp"]:
        optimizer_view["default_wp_id"] = next(iter(optimizer_view["by_wp"].keys()))

    # 2026-05-29: advice backfill 이 저장한 LLM scenarios (daily_reports.scenarios_jsonb)
    # 우선 사용. backfill_v2 자체 _build_scenarios 는 deterministic 이라 wp_summary 합(76)이
    # LLM site(29)와 어긋났다 (사용자 핵심: site=Σwp). LLM scenarios 는 site=Σby_wp 일관.
    scen_rows = await pg.fetch_all(
        "SELECT dr.scenarios_jsonb FROM daily_reports dr "
        "JOIN pipeline_runs pr USING (run_id) "
        "WHERE pr.site_id=$1 AND pr.report_date=$2 AND dr.scenarios_jsonb IS NOT NULL "
        "ORDER BY dr.created_at DESC LIMIT 1",
        site_id, today,
    )
    llm_scen = None
    if scen_rows:
        raw = scen_rows[0].get("scenarios_jsonb")
        llm_scen = _json.loads(raw) if isinstance(raw, str) else raw
    if llm_scen and llm_scen.get("by_wp"):
        scenarios = llm_scen
    else:
        scenarios = _build_scenarios(advice_rows, forecast_rows)
    s_curve = await _build_s_curve(pg, site_id, today)

    # kpi.recovery_days / recovered_completion 은 scenarios.site.base_p50 기준 매핑.
    base_p50 = (scenarios.get("site") or {}).get("base_p50") or {}
    kpi["recovery_days"] = int(base_p50.get("recovery_days") or 0)
    kpi["recovered_completion"] = base_p50.get("expected_completion") or kpi.get("expected_completion")

    # 2026-05-29 (2차) SSOT: KPI delay = site s-curve 기준 "며칠 뒤처졌나".
    # 기존 forecasts.delay median 은 오늘 활성 WP(대부분 on-pace=0)만 봐서 전체 진척 lag 와 어긋났다
    # (delay 0 인데 gap 18%pt·recovery 33 모순). s-curve 의 today 실적이 계획상 며칠 전 수준인지로 환산
    # → delay·gap·recovery 가 한 방향 (현황 D+N 지연, AI 로 recovery 만회).
    _today_iso = today.isoformat()
    _actual_today = None
    for _p in s_curve:
        if _p.get("date") == _today_iso and _p.get("actual") is not None:
            _actual_today = _p["actual"]
            break
    if _actual_today is None:
        _aps = [_p for _p in s_curve if _p.get("actual") is not None]
        _actual_today = _aps[-1]["actual"] if _aps else None
    if _actual_today is not None:
        _cross = None  # planned 가 현재 actual 수준에 도달했던 마지막 날 (<= today)
        for _p in s_curve:
            if _p.get("date", "") > _today_iso:
                break
            if _p.get("planned") is not None and _p["planned"] <= _actual_today:
                _cross = _p["date"]
        if _cross:
            kpi["delay_days"] = max(0, (today - date.fromisoformat(_cross)).days)

    # 2026-05-29: wp_summary.recovery_days = scenarios.by_wp[wp].base_p50 (단일 source).
    # FE WPSummaryTable 의 결정론 recoveryDays() 폐기 — site=Σ(wp recovery_days) 와 정합.
    scen_by_wp = scenarios.get("by_wp") or {}
    for w in wp_summary:
        wp_scen = scen_by_wp.get(w["wp_id"]) or {}
        w_bp50 = wp_scen.get("base_p50") or {}
        w["recovery_days"] = int(w_bp50.get("recovery_days") or 0)

    # 2026-05-29 (2차) 사용자 결정: per-WP 카드 '일정 영향' = 그 WP 의 공기단축 일수(scenarios.by_wp)
    # 기준. 카드 안에서 '지연 N일 ↔ 공기단축 -N일' 정합 + site = Σ 와 일관. (forecaster point-in-time
    # delay 는 orphan 누적 cum 으로 0 이라 카드용으로 부적합 — 모든 카드 '일정 충족' 모순 해소.)
    _ov_by_wp = optimizer_view.get("by_wp") or {}
    for _wp_id, _ov in _ov_by_wp.items():
        _rec = int(((scen_by_wp.get(_wp_id) or {}).get("base_p50") or {}).get("recovery_days") or 0)
        if _rec > 0:
            _sched_val = f"{_rec}일 지연"
            _basis = f"AI 분석상 약 {_rec}일치 작업량이 밀려, 만회 시 {_rec}일 단축 가능"
        else:
            _sched_val = "일정 충족"
            _basis = "계획한 진도를 맞춰 진행 중 (지연 없음)"
        for _d in _ov.get("details") or []:
            if _d.get("label") == "일정 영향":
                _d["value"] = _sched_val
            elif _d.get("label") == "산출근거":
                _d["value"] = _basis

    return {
        "kpi": kpi,
        "productivity": productivity_dict,
        "contractor_bars": contractor_bars,
        "trade_bars": trade_bars,
        "quadrant": quadrant,
        "wp_summary": wp_summary,
        "optimizer_view": optimizer_view,
        "scenarios": scenarios,
        "s_curve": s_curve,
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
