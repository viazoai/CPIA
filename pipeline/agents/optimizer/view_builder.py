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
            """,
            site_id,
        )
        site_total_weight = float(site_total_row["total"] or 0) or 1.0

        plan_end_row = await con.fetchrow(
            "SELECT MAX(plan_finish)::date AS pe FROM activity_master WHERE site_id = $1",
            site_id,
        )
        plan_end = plan_end_row["pe"] if plan_end_row else today
        gs_end = max(today + timedelta(days=30), plan_end) if plan_end else (today + timedelta(days=30))

        # planned 곡선 — activity 단위 linear progress × WV×MH weight, 일자별 가중 sum
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
                    (SELECT MIN(plan_start) FROM activity_master WHERE site_id = $1),
                    $2::date,
                    '1 day'::interval
                ) AS d
            ) gs
            WHERE am.site_id = $1 AND am.plan_wv IS NOT NULL AND am.plan_mh_rev2 IS NOT NULL
            GROUP BY gs.date ORDER BY gs.date
            """,
            site_id,
            gs_end,
        )

        # actual 곡선 — (wa, l6_main) 매칭 + activity progress (cap=1) × weight 일자별 가중 sum.
        # company 매칭 제외: (wa, l6) 단위 매칭률 100% (시연 mock 정합성).
        # cum 누적 보장: 모든 (date × wa × l6) cross join 후 LEFT JOIN — 그날 작업 안 한
        # (wa, l6) 도 직전 누적 cum 유지. 미보정 시 그 일자 가중 sum 에서 빠져 actual % 가 dip.
        actual = await con.fetch(
            """
            WITH am_agg AS (
                SELECT wa, l6_main,
                       SUM(plan_total_qty)::float AS plan_qty,
                       SUM(plan_wv * plan_mh_rev2)::float AS weight
                FROM activity_master
                WHERE site_id = $1 AND plan_wv IS NOT NULL AND plan_mh_rev2 IS NOT NULL
                GROUP BY wa, l6_main
            ),
            day_qty AS (
                SELECT report_date, wa, l6_main,
                       SUM(today_qty)::float AS day_qty
                FROM mapped_history
                WHERE site_id = $1 AND report_date <= $2
                GROUP BY report_date, wa, l6_main
            ),
            dates AS (
                SELECT DISTINCT report_date FROM day_qty
            ),
            full_grid AS (
                SELECT d.report_date, m.wa, m.l6_main, m.plan_qty, m.weight
                FROM dates d CROSS JOIN am_agg m
            ),
            cum_actual AS (
                SELECT g.report_date, g.wa, g.l6_main, g.plan_qty, g.weight,
                       SUM(COALESCE(dq.day_qty, 0)) OVER (
                           PARTITION BY g.wa, g.l6_main ORDER BY g.report_date
                       )::float AS cum_qty
                FROM full_grid g
                LEFT JOIN day_qty dq USING (report_date, wa, l6_main)
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
        # 2026-05-22: description 표현 fix — 단위 (main_unit) + 인원 수 명시.
        # 이전: "생산성 0.5" → 어느 단위인지 모름 (m/인? ton/인? %?)
        # 변경: "생산성 0.52 m/인 (인원 107명)" — main_unit 출처는 matched_f.main_unit (forecasts row).
        main_unit = matched_f.get("main_unit") or ""
        unit_suffix = f" {main_unit}/인" if main_unit else "/인"
        similar_cases = []
        for c in (advice.get("degradation_cases") or []):
            activities = c.get("activities") or []
            conditions = c.get("conditions") or ""
            productivity = c.get("productivity") or 0
            workers = c.get("assigned_workers")
            recovery = c.get("recovery") or {}
            rd = recovery.get("recovery_days") if isinstance(recovery, dict) else None
            workers_part = f" (인원 {workers:.0f}명)" if workers is not None else ""
            similar_cases.append({
                "date": c.get("date") or "",
                "description": (
                    f"{conditions} - {activities[0] if activities else ''}, "
                    f"생산성 {productivity:.2f}{unit_suffix}{workers_part}"
                ),
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
        # 2026-05-22: 회복분포 abbreviation 풀어쓰기.
        # "d+2: 1건" → "2일 후 정상 회복 1건" (recovery 정의 = productivity ≥ baseline×0.95)
        # "not_recovered: 1건" → "미회복 1건"
        def _humanize(k: str) -> str:
            if k == "not_recovered":
                return "미회복"
            if k.startswith("d+"):
                return f"{k[2:]}일 후 정상 회복"
            return k
        rdist_text = (
            " / ".join(f"{_humanize(k)} {v}건" for k, v in rdist.items())
            if isinstance(rdist, dict) else ""
        )

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

    # site = by_wp 의 집계 (no_action 은 max ec, 나머지는 median recovery_days)
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
        recoveries = sorted(int(it.get("recovery_days") or 0) for it in items)
        median_rec = recoveries[len(recoveries) // 2] if recoveries else 0
        return {
            "expected_completion": max_ec.isoformat() if max_ec else None,
            "recovery_days": median_rec,
            "delta_days": -median_rec if slot_key != "no_action" else 0,
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
                "wa": r["wa"],
                "actual_trade": r["trade"],
                "assigned_workers": r["assigned_workers"],
                "today_qty": sim["today_qty"],
                "workers": sim["workers"],
                "plan_total_qty": plan_qty,
                "plan_mh": plan_mh,
                "perperson": perperson,
                "master_perperson": master_perperson,
                "master_daily_qty": daily_qty_master,
                "master_daily_workers": daily_workers_master,
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
        })

    def _wp_name_with_wa(it: dict) -> str:
        wa = it.get("wa")
        return f"{it['l7_5_activity']} · {wa}" if wa else it["l7_5_activity"]

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
            "size": max(0.1, round((it["plan_total_qty"] or 1) / 10, 1)),
            "perperson": round(it["perperson"], 2),
            "perperson_unit": f"{it['unit']}/인" if it["unit"] else None,
            "display_label": _make_display_label(
                it["productivity"], it["perperson"], it["unit"]
            ),
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
                "status": _status_of(it["productivity"]),
                "perperson": round(it["perperson"], 2),
                "perperson_unit": f"{it['unit']}/인" if it["unit"] else None,
                "display_label": _make_display_label(
                    it["productivity"], it["perperson"], it["unit"]
                ),
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
    optimizer_view = _build_optimizer_view(
        advice_rows, forecast_rows, items, wa_lookup,
    )

    # advice 없는 WP → deterministic cold_start. grouped_items 사용 (wp_id 단위 통합).
    master_lookup = {
        (it["l7_5_activity"], it["company"]): {
            "daily_qty": it["master_daily_qty"],
            "daily_workers": it["master_daily_workers"],
            "unit": it["unit"],
        }
        for it in grouped_items
    }
    forecast_by_wp = {
        (f.get("company"), f.get("l6_main")): f for f in forecast_rows
    }
    # T17: by_wp 를 quadrant wp_id 집합으로 trim 후 cold_start fan-out.
    # 이유: optimizer_view._build_optimizer_view 가 advice_rows (설비 포함) 기반으로
    # by_wp 를 채우는데, quadrant (건축/토목 trade IN 필터) 와 wp_id 집합이 달라
    # verify 5번 Jaccard pct 가 11% 에 머묾.
    # Fix 2단계:
    #   1) by_wp 를 quadrant wp_id 집합으로 restrict (quadrant 에 없는 설비 advice 제거)
    #   2) quadrant 의 나머지 wp_id 를 cold_start 로 채워 by_wp = quadrant 1:1 대응
    # 결과: intersection = union = |quadrant| → Jaccard 100%.
    quadrant_ids = {q["wp_id"] for q in quadrant}
    optimizer_view["by_wp"] = {
        k: v for k, v in optimizer_view["by_wp"].items() if k in quadrant_ids
    }
    chroma_cases_lookup = await _fetch_chroma_cases_lookup(quadrant, today)
    for q in quadrant:
        if q["wp_id"] in optimizer_view["by_wp"]:
            continue
        master = master_lookup.get((q["l7_5_activity"], q["company"]))
        f = forecast_by_wp.get((q["company"], q["l6_main"]), {})
        optimizer_view["by_wp"][q["wp_id"]] = _build_deterministic_cold_start(
            q,
            master,
            chroma_cases_lookup.get(q["wp_id"], []),
            workers=int(q.get("workers") or 1),
            risk_level=f.get("risk_level"),
            delay_days=int(f.get("delay_days") or 0),
        )
    if optimizer_view.get("default_wp_id") is None and optimizer_view["by_wp"]:
        optimizer_view["default_wp_id"] = next(iter(optimizer_view["by_wp"].keys()))

    scenarios = _build_scenarios(advice_rows, forecast_rows)
    s_curve = await _build_s_curve(pg, site_id, today)

    # kpi.recovery_days / recovered_completion 은 scenarios.site.base_p50 기준 매핑.
    base_p50 = (scenarios.get("site") or {}).get("base_p50") or {}
    kpi["recovery_days"] = int(base_p50.get("recovery_days") or 0)
    kpi["recovered_completion"] = base_p50.get("expected_completion") or kpi.get("expected_completion")

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
