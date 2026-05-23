"""CPIA 1년치 더미 데이터 적재 — cycle bypass.

설계:  docs/superpowers/specs/2026-05-20-cpia-dummy-year-data-design.md (예정)
brain: notes/cpia-dummy-data-design-plan-2026-05-20

흐름:
  PHASE 0. anchor load — 9-25 mapper_activities + activity_master + sites
  PHASE 1. per-day INSERT loop (24-04-11 ~ 25-09-24)
    Case A (9-25 anchor 에 존재): anchor today_cum_qty 와 정합 분배
    Case B (9-25 전 종료, anchor 부재): activity_master.plan_total_qty 기반 분배
  PHASE 2. Chroma upsert (옵션 — 매주 1일 ~77 sample)
  PHASE 3. 정합 검증

옵션:
  python scripts/seed_dummy_year.py --start 2025-09-24 --end 2025-09-24 --chroma-skip
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import random
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.agents.optimizer.view_builder import (  # noqa: E402
    _build_contractor_bars,
    _build_kpi,
    _build_optimizer_view,
    _build_productivity_views,
    _build_quadrant,
    _build_s_curve,
    _build_scenarios,
    _build_trade_bars,
    _build_wp_summary,
)
from pipeline.agents.synthetic.distributions import (  # noqa: E402,F401
    P_NORM,
    PEAK_MULT,
    PLATEAU_END,
    RAMP_END,
    f3_cum_ratio,
    f3_daily_ratio,
)
from pipeline.db import PGClient  # noqa: E402

logger = logging.getLogger(__name__)

SITE_ID = "m15x-ph3-ibl"
PROJECT = "M15X Ph-3 IBL"
ANCHOR_DATE = date(2025, 9, 25)
DEFAULT_PG_URL = "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia"

# 9-25 anchor 실측 site mh/qty 비율. 모든 Case B + Case A fallback row 의 cum_actual_mh
# 산출에 이 상수를 사용하면 view_builder 의 site EVM CPI 가 86.1% 근처로 자연 정합된다
# (anchor mh_per_qty=5.1747, plan mh_per_qty=4.4552, CPI = 4.4552/5.1747 ≈ 0.861).
# 초기 일자에 active wbs 가 1-2 개만 있어도 CPI outlier 가 발생하지 않는다.
ANCHOR_SITE_MH_PER_QTY = 5.1747

DIAGNOSIS_PATTERNS: list[dict[str, Any]] = [
    {
        "tag": "weather_rain",
        "text": "당일 오전 강수로 외부 작업 지연 발생. {l6} 공정의 이동·세팅에 1.5h 추가 소요. 오후 정상화 후 일부 추가 인력 투입.",
        "recs": ["우천 시 실내 선행 작업 우선 배정", "이튿날 외부 작업 인력 +20% 검토"],
    },
    {
        "tag": "manpower_short",
        "text": "지정 BP사 {company} 인력 가용율이 평소보다 18% 낮음. 동일 공정 타 BP 와 임시 협업으로 진척률 보전.",
        "recs": ["{company} 인력 확보 우선순위 격상", "유사 공정 BP pool 사전 확보"],
    },
    {
        "tag": "material_delay",
        "text": "{l6} 자재 일부 입고 지연으로 오전 대기 발생. 오후 정상 작업 진행.",
        "recs": ["자재 입고 확인 콜 강화", "대체 자재 1주 사전 확보"],
    },
    {
        "tag": "rework",
        "text": "전일 시공분 일부 재작업 발생. 품질 점검 후 다음 활동 진행. 진도 -8% 영향.",
        "recs": ["전일 시공 품질 점검 강화", "체크리스트 일일 적용"],
    },
    {
        "tag": "trade_overlap",
        "text": "동일 공간 내 {l6} 외 2개 공종 동시 작업. 동선 충돌로 진행 속도 저하. 작업 순서 재조정 적용.",
        "recs": ["일일 작업 동선 미리 조율", "타 공종 진척에 따른 작업 영역 분리"],
    },
    {
        "tag": "spec_change",
        "text": "현장 조건 검토 결과 {l6} 일부 사양 조정 필요. 발주처 협의 후 변경 작업 1일 추가 소요.",
        "recs": ["사양 변경 발주처 fast-track 협의", "변경 영향도 사전 산정"],
    },
    {
        "tag": "normal_steady",
        "text": "{l6} 정상 진행. {company} 인력 가용 평소 수준. 다음 활동 연결 일정 준수.",
        "recs": ["현 페이스 유지", "후행 공정 사전 협조"],
    },
]

# F3 분포 import (Phase B Task B.1 분리 모듈)

# spec §5 — 사용자 결정: 7 tag → conditions list 매핑
TAG_TO_CONDS: dict[str, list[str]] = {
    "weather_rain": ["우천"],
    "manpower_short": ["인력부족"],
    "material_delay": ["자재미입고"],
    "rework": ["재작업"],
    "trade_overlap": ["병행작업"],
    "spec_change": ["사양변경"],
    "normal_steady": ["정상"],
}

# spec §7 — prod target 역산 상수
PROD_TARGET = 90.0
OUTLIER_PROB = 0.05


def _seeded_rng(seed_str: str) -> random.Random:
    h = hashlib.sha256(seed_str.encode("utf-8")).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def _noise(rng: random.Random, scale: float = 0.10) -> float:
    return 1.0 + (rng.random() * 2.0 - 1.0) * scale


def _pick_diagnosis(date_str: str, wa: str, company: str, l6: str) -> dict[str, Any]:
    idx = int(hashlib.md5(f"{date_str}|{wa}|{company}".encode()).hexdigest(), 16) % len(
        DIAGNOSIS_PATTERNS
    )
    pat = DIAGNOSIS_PATTERNS[idx]
    return {
        "tag": pat["tag"],
        "diagnosis": pat["text"].format(l6=l6, company=company),
        "recommendations": [r.format(l6=l6, company=company) for r in pat["recs"]],
        "conditions": TAG_TO_CONDS[pat["tag"]],  # spec §13.3
    }


def _date_run_id(d: date, salt: str = "dummy_seed") -> uuid.UUID:
    """date + salt 기반 결정성 UUID."""
    raw = hashlib.sha256(f"{salt}|{d.isoformat()}".encode()).hexdigest()
    return uuid.UUID(raw[:32])


# ============================================================================
# PHASE 0 — anchor + activity_master + sites load
# ============================================================================


async def load_anchor(pg: PGClient) -> dict[tuple[str, str, str], dict[str, Any]]:
    """9-25 mapper_activities 의 (wa, company, l6_main) 별 anchor."""
    rows = await pg._pool.fetch(
        """
        SELECT ma.wa, ma.company, ma.l6_main, ma.trade, ma.unit,
               ma.today_qty, ma.today_cum_qty, ma.cum_actual_mh_today, ma.cum_workers_today,
               ma.plan_total_qty, ma.plan_mh, ma.assigned_workers,
               ma.zone, ma.scope, ma.work_location_code,
               ma.wbs_mid_name, ma.wbs_sub_name, ma.wbs_detail_name,
               pa.work_content
        FROM mapper_activities ma
        JOIN pipeline_runs pr USING (run_id)
        LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
        WHERE pr.report_date = $1
          AND ma.is_mock = FALSE
          AND ma.mapping_source != 'dummy_seed'
          AND ma.wa IS NOT NULL
          AND ma.l6_main IS NOT NULL
          AND ma.company IS NOT NULL
        """,
        ANCHOR_DATE,
    )
    anchor: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        anchor[(r["wa"], r["company"], r["l6_main"])] = dict(r)
    return anchor


async def load_activity_master(pg: PGClient) -> list[dict[str, Any]]:
    rows = await pg._pool.fetch(
        """
        SELECT site_id, wa, l5_disc, l6_main, l7_sub, l7_5_activity,
               sub_work_area, company, unit,
               plan_total_qty, plan_mh_rev2, plan_start, plan_finish
        FROM activity_master
        WHERE site_id = $1 AND plan_start IS NOT NULL AND plan_finish IS NOT NULL
          AND company IS NOT NULL AND wa IS NOT NULL AND l6_main IS NOT NULL
        ORDER BY plan_start
        """,
        SITE_ID,
    )
    return [dict(r) for r in rows]


# ============================================================================
# Chroma sample-day predicate
# ============================================================================


def _chroma_should_seed(d: date, mode: str, start: date) -> bool:
    """일자별 Chroma upsert 여부.

    weekly = (start + 7n) + 9-24 anchor 인접
    all    = 전 일자
    anchor_only = 9-24 만 (smoke test 용)
    """
    if mode == "all":
        return True
    if mode == "anchor_only":
        return d == ANCHOR_DATE - timedelta(days=1)  # 9-24
    # weekly
    if d == ANCHOR_DATE - timedelta(days=1):
        return True
    return (d - start).days % 7 == 0


# ============================================================================
# PHASE 1 — per-row mapper_activities builder (Case A / Case B)
# ============================================================================


def _build_mapper_row(
    d: date,
    am_row: dict[str, Any],
    anchor_row: Optional[
        dict[str, Any]
    ],  # 인터페이스 보존 (호출자 영향 X), 내부 사용 X
    rng: random.Random,
) -> Optional[dict[str, Any]]:
    """activity_master row → 일자별 mapper_activities row.

    spec §10: 모든 일자 동일 F3 + prod target 역산 logic. Case A 분기 제거.
    spec §13.4: 보존 항목 (mapping_conf, parser pass-through) + 교체 항목 (분포·prod·trade·conditions·l7.5).
    """
    plan_start = am_row["plan_start"]
    plan_finish = am_row["plan_finish"]
    if d < plan_start or d > plan_finish:
        return None

    total_days = (plan_finish - plan_start).days + 1
    days_elapsed = (d - plan_start).days + 1
    progress = days_elapsed / total_days

    plan_total = float(am_row.get("plan_total_qty") or 0)
    plan_mh = float(am_row.get("plan_mh_rev2") or 0)

    # F3 분포
    ratio_today = f3_daily_ratio(progress)
    cum_frac = f3_cum_ratio(progress)

    # prod target 역산 (spec §7)
    # _pick_diagnosis 는 내부에서 hashlib 기반 결정성 선택 — rng 사용 안 함
    diag = _pick_diagnosis(str(d), am_row["wa"], am_row["company"], am_row["l6_main"])
    is_outlier = rng.random() < OUTLIER_PROB
    if is_outlier:
        actual_prod_pct = rng.choice([50.0, 150.0])
    else:
        actual_prod_pct = PROD_TARGET * (1.0 + (rng.random() * 2 - 1) * 0.10)

    today_qty = (
        plan_total / total_days * ratio_today * (1.0 + (rng.random() * 2 - 1) * 0.10)
    )
    today_cum_qty = plan_total * cum_frac
    cum_actual_mh = plan_mh * progress * actual_prod_pct / 100.0
    plan_mh_per_day = plan_mh / total_days if total_days > 0 else 0
    today_assigned_workers = max(
        1.0, plan_mh_per_day / 8.0 * (1.0 + (rng.random() * 2 - 1) * 0.10)
    )
    cum_workers_today = cum_actual_mh / 8.0

    return {
        "company": am_row["company"],
        "trade": am_row["l5_disc"],  # spec §9 — l5_disc 그대로 trade 컬럼
        "unit": am_row.get("unit") or "EA",
        "today_qty": today_qty,
        "today_cum_qty": today_cum_qty,
        "cum_actual_mh_today": cum_actual_mh,
        "cum_workers_today": cum_workers_today,
        "wa": am_row["wa"],
        "l5_disc": am_row["l5_disc"],
        "l6_main": am_row["l6_main"],
        "l7_sub": am_row.get("l7_sub") or "",
        "l7_5_activity": am_row.get("l7_5_activity") or "",  # spec §8
        "sub_work_area": am_row.get("sub_work_area") or "",
        "mapping_conf": 1.0,
        "mapping_source": "dummy_seed",
        "requires_review": False,
        "assigned_workers": today_assigned_workers,
        "worker_source": "dummy_seed",
        "plan_total_qty": plan_total,
        "plan_mh": plan_mh,
        "conditions": diag["conditions"],  # spec §5 — TAG_TO_CONDS[tag]
        "alternatives": [],
        "work_content": f"{am_row['l6_main']} 진행",
        "zone": "",
        "scope": "",
        "yesterday_cum_qty": today_cum_qty - today_qty
        if today_cum_qty > today_qty
        else 0,
        "progress_percent": progress * 100,
        "remaining_qty": max(0, plan_total - today_cum_qty),
        "remaining_percent": max(0, (1.0 - progress)) * 100,
        "note": "",
        "work_location_code": "",
        "wbs_mid_name": "",
        "wbs_sub_name": "",
        "wbs_detail_name": "",
        # diag 추가 정보 (호출자가 _build_optimizer_advice 에서 재사용)
        "_diag_tag": diag["tag"],
    }


def _classify_assessment(progress_ratio: float, day_ratio: float) -> str:
    """gap = progress - day_ratio 기반 결정성 분류."""
    gap = progress_ratio - day_ratio
    if gap >= -0.03:
        return "정상"
    if gap >= -0.07:
        return "주의"
    return "이상"


def _build_forecast_row(
    d: date,
    run_id: uuid.UUID,
    group: tuple[str, str, str],
    activities: list[dict[str, Any]],
    am_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """(wa, company, l6) group 별 forecasts row dict."""
    wa, company, l6 = group
    today_qty_sum = sum(a["today_qty"] for a in activities)
    today_workers_sum = sum(a["assigned_workers"] for a in activities)
    cum_actual_qty = sum(a["today_cum_qty"] for a in activities)
    cum_actual_mh = sum(a["cum_actual_mh_today"] for a in activities)
    plan_qty = sum(a["plan_total_qty"] for a in activities)
    plan_mh = sum(a["plan_mh"] for a in activities)
    unit = activities[0]["unit"]

    # plan_start / plan_finish: am_rows 의 그 group min/max
    am_grp = [
        r
        for r in am_rows
        if r["wa"] == wa and r["company"] == company and r["l6_main"] == l6
    ]
    plan_start = min((r["plan_start"] for r in am_grp), default=d)
    plan_finish = max((r["plan_finish"] for r in am_grp), default=d)
    total_days = (plan_finish - plan_start).days + 1
    days_elapsed = max(0, (d - plan_start).days + 1)
    progress_ratio = cum_actual_qty / plan_qty if plan_qty > 0 else 0
    day_ratio = days_elapsed / total_days if total_days > 0 else 0
    assessment = _classify_assessment(progress_ratio, day_ratio)

    plan_mh_per_day = plan_mh / total_days if total_days > 0 else 0
    expected_mh = plan_mh_per_day * days_elapsed
    # Fix 3: delay_days clamp ±30 (cum_actual_mh cap 의 안전 마진)
    delay_days = (
        round(max(-30, min(30, (expected_mh - cum_actual_mh) / plan_mh_per_day)))
        if plan_mh_per_day > 0
        else 0
    )
    # productivity clamp 0~150 (Fix 2 후 자연스럽지만 안전망)
    raw_prod = (cum_actual_mh / expected_mh * 100) if expected_mh > 0 else 100.0
    today_productivity = max(0.0, min(150.0, raw_prod))

    # spec §13.5 — activities 의 conditions list 들의 union (sorted)
    conditions_set = sorted(
        {c for a in activities for c in (a.get("conditions") or [])}
    )

    return {
        "run_id": run_id,
        "company": company,
        "l6_main": l6,
        "wa": wa,
        "today_qty_by_unit": {unit: today_qty_sum},
        "today_assigned_workers": today_workers_sum,
        "today_productivity": today_productivity,
        "plan_total_qty_by_unit": {unit: plan_qty},
        "plan_mh_sum": plan_mh,
        "plan_start": plan_start,
        "plan_finish": plan_finish,
        "plan_mh_per_day": plan_mh_per_day,
        "schedule_state": "on_schedule" if delay_days <= 1 else "post_due",
        "window_start": d - timedelta(days=7),
        "window_days": 7,
        "expected_in_window_mh": plan_mh_per_day * 7,
        "actual_in_window_mh": cum_actual_mh * (7 / max(days_elapsed, 1)),
        "mh_gap": (plan_mh_per_day * 7) - (cum_actual_mh * (7 / max(days_elapsed, 1))),
        "delay_days": delay_days,
        "rag_n_similar": 0,
        "similar_cases": [],
        "assessment": assessment,
        "reasoning": "",
        "recovery_likelihood": None,
        "expected_completion": plan_finish,
        "risk_level": assessment,
        "main_unit": unit,
        "today_conditions": ",".join(conditions_set) if conditions_set else "",
    }


def _build_optimizer_advice(
    d: date,
    run_id: uuid.UUID,
    forecast_row: dict[str, Any],
) -> dict[str, Any]:
    """risky 그룹 → fixture diagnosis. degradation_cases 결정성 2건."""
    wa = forecast_row["wa"]
    company = forecast_row["company"]
    l6 = forecast_row["l6_main"]
    date_str = d.isoformat()
    pat = _pick_diagnosis(date_str, wa, company, l6)
    # degradation_cases 결정성 2 건
    cases = [
        {
            "date": (d - timedelta(days=180)).isoformat(),
            "activities": [f"{l6} 작업"],
            "conditions": ",".join(
                pat["conditions"]
            ),  # spec §13.7 — list → comma-joined str
            "productivity": 78.0,
            "recovery": {"recovery_days": 3},
        },
        {
            "date": (d - timedelta(days=90)).isoformat(),
            "activities": [f"{l6} 작업"],
            "conditions": ",".join(pat["conditions"]),  # spec §13.7
            "productivity": 82.0,
            "recovery": {"recovery_days": 2},
        },
    ]
    return {
        "run_id": run_id,
        "company": company,
        "l6_main": l6,
        "forecast_assessment": forecast_row["assessment"],
        "diagnosis": pat["diagnosis"],
        "degradation_cases": cases,
        "recovery_pattern": [
            {"date": c["date"], "recovery_days": c["recovery"]["recovery_days"]}
            for c in cases
        ],
        "recovery_distribution": {"d+2": 1, "d+3": 1},
        "recommendations": pat["recommendations"],
    }


# ============================================================================
# PHASE 2 — Chroma daily_activities upsert (sample 일자)
# ============================================================================


async def chroma_upsert_day(
    d: date,
    run_id: uuid.UUID,
    mapper_rows: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> int:
    """sample 일자의 mapper_activities → Chroma daily_activities upsert.

    atomizer._make_doc_id 재사용. metadata key set 은 atomizer._build_metadata 와 호환.
    fail-fast (Chroma / Azure fail 시 raise).
    """
    from pipeline.agents.atomizer import _make_doc_id  # late import
    from pipeline.chroma_client import ChromaClient
    from openai import AzureOpenAI

    # valid filter: work_content + l6_main not empty
    valid = [r for r in mapper_rows if r.get("l6_main") and r.get("work_content")]
    if not valid:
        return 0

    date_str = d.isoformat()
    # dedup by doc_id — same as atomizer.atomize() within-call dedup semantics.
    seen: dict[str, int] = {}
    for i, r in enumerate(valid):
        doc_id = _make_doc_id(date_str, r["company"], r["l6_main"], r["work_content"])
        seen[doc_id] = i

    ids = list(seen.keys())
    documents = [valid[i]["work_content"] for i in seen.values()]
    metadatas = [
        {
            "date": date_str,
            "run_id": str(run_id),
            "company": valid[i]["company"],
            "l5_disc": valid[i].get("l5_disc") or "",  # spec §13.6
            "l6_main": valid[i]["l6_main"] or "",
            "l7_5_activity": valid[i].get("l7_5_activity") or "",  # spec §13.6
            "wa": valid[i]["wa"] or "",
            "unit": valid[i]["unit"],
            "today_qty": float(valid[i]["today_qty"]),
            "assigned_workers": float(valid[i]["assigned_workers"]),
            "worker_source": valid[i]["worker_source"],
            "mapping_conf": float(valid[i]["mapping_conf"] or 0.0),
            "conditions": ",".join(valid[i].get("conditions") or []),  # spec §13.6
        }
        for i in seen.values()
    ]

    azure = AzureOpenAI(
        api_key=cfg["AZURE_OPENAI_API_KEY"],
        api_version=cfg["AZURE_OPENAI_API_VERSION"],
        azure_endpoint=cfg["AZURE_OPENAI_ENDPOINT"],
        timeout=30.0,
        max_retries=3,
    )
    embeddings: list[list[float]] = []
    BATCH = 100
    for i in range(0, len(documents), BATCH):
        chunk = documents[i : i + BATCH]
        resp = azure.embeddings.create(model=cfg["EMBEDDING_MODEL"], input=chunk)
        embeddings.extend([item.embedding for item in resp.data])

    chroma = ChromaClient(host=cfg["CHROMA_HOST"], port=int(cfg["CHROMA_PORT"]))
    coll = chroma.get_or_create_daily_activities()
    for j in range(0, len(ids), BATCH):
        coll.upsert(
            ids=ids[j : j + BATCH],
            embeddings=embeddings[j : j + BATCH],
            documents=documents[j : j + BATCH],
            metadatas=metadatas[j : j + BATCH],
        )
    return len(ids)


# ============================================================================
# per-day INSERT loop
# ============================================================================


async def cleanup_dummy(pg: PGClient, start: date, end: date) -> int:
    """기존 dummy_seed row 삭제 — date range 내."""
    async with pg._pool.acquire() as con:
        result = await con.execute(
            """
            DELETE FROM pipeline_runs WHERE site_id=$1 AND report_date BETWEEN $2 AND $3
            AND run_id IN (
                SELECT DISTINCT run_id FROM mapper_activities WHERE mapping_source='dummy_seed'
            )
            """,
            SITE_ID,
            start,
            end,
        )
    try:
        n = int(result.split()[-1])
    except Exception:
        n = 0
    return n


async def seed_day(
    pg: PGClient,
    d: date,
    anchor: dict[tuple[str, str, str], dict[str, Any]],
    am_list: list[dict[str, Any]],
    chroma_cfg: Optional[dict[str, Any]] = None,
    chroma_only: bool = False,
) -> dict[str, int]:
    """단일 일자 적재. return: counts dict.

    chroma_cfg None  → PG 만 (기존 동작).
    chroma_cfg dict  → PG + Chroma sample 일자 (_chroma_should_seed 충족 시).
    chroma_only True → PG INSERT skip, Chroma 만 (T4 용).
    """
    run_id = _date_run_id(d)

    # 1. mapper_activities row build per activity_master entry (always — chroma_only 도 필요)
    rng_seed_prefix = f"{d.isoformat()}|"
    mapper_rows: list[dict[str, Any]] = []
    for i, am in enumerate(am_list):
        key = (am["wa"], am["company"], am["l6_main"])
        anchor_row = anchor.get(key)
        rng = _seeded_rng(rng_seed_prefix + "|".join(str(k) for k in key) + f"|{i}")
        r = _build_mapper_row(d, am, anchor_row, rng)
        if r is not None:
            mapper_rows.append(r)
    n_active = len(mapper_rows)
    if n_active == 0:
        return {"pipeline_runs": 0, "active": 0}

    # chroma_only: PG INSERT 전부 skip 하고 Chroma 만
    if chroma_only:
        n_chroma = 0
        if chroma_cfg and _chroma_should_seed(
            d,
            chroma_cfg.get("chroma_mode", "weekly"),
            chroma_cfg.get("seed_start", d),
        ):
            n_chroma = await chroma_upsert_day(d, run_id, mapper_rows, chroma_cfg)
        return {"active": n_active, "chroma_upserts": n_chroma}

    # 2. parser_activities row (mapper 의 일부 컬럼만)
    parser_rows: list[dict[str, Any]] = []
    for r in mapper_rows:
        parser_rows.append(
            {
                "company": r["company"],
                "trade": r["trade"],
                "l5_disc": "",
                "unit": r["unit"],
                "today_qty": r["today_qty"],
                "work_content": r["work_content"],
                "plan_total_qty": r["plan_total_qty"],
                "zone": r["zone"],
                "bp_code": "",
                "scope": r["scope"],
                "yesterday_cum_qty": r["yesterday_cum_qty"],
                "today_cum_qty": r["today_cum_qty"],
                "progress_percent": r["progress_percent"],
                "remaining_qty": r["remaining_qty"],
                "remaining_percent": r["remaining_percent"],
                "note": "",
                "work_location_code": "",
                "wbs_mid_name": "",
                "wbs_sub_name": "",
                "wbs_detail_name": "",
            }
        )

    # 3. INSERT — pipeline_runs first (FK 의존)
    async with pg._pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO pipeline_runs
                (run_id, site_id, report_date, status, current_node, completed_at, is_mock, atomized_count)
            VALUES ($1, $2, $3, 'completed', 'reporter', NOW(), FALSE, $4)
            ON CONFLICT (run_id) DO UPDATE SET status='completed', completed_at=NOW()
            """,
            run_id,
            SITE_ID,
            d,
            n_active,
        )

    # 4. parser_reports
    await pg.insert_parser_report(run_id, d, PROJECT, [], [], [], n_active)

    # 5. parser_activities + mapper_activities batch
    await pg.insert_parser_activities_batch(run_id, d, parser_rows)
    await pg.insert_mapper_activities_batch(run_id, d, mapper_rows)

    # 6. mapped_history (wa+l6_main+company NOT NULL)
    mh_rows = [
        {
            "wa": r["wa"],
            "l6_main": r["l6_main"],
            "company": r["company"],
            "today_qty": r["today_qty"],
            "today_assigned_workers": r["assigned_workers"],
            "unit": r["unit"],
        }
        for r in mapper_rows
    ]
    await pg.insert_mapped_history_batch(run_id, d, SITE_ID, mh_rows)

    # 7. forecasts — group by (wa, company, l6)
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in mapper_rows:
        groups.setdefault((r["wa"], r["company"], r["l6_main"]), []).append(r)
    forecast_rows: list[dict[str, Any]] = []
    for key, group_rows in groups.items():
        fc = _build_forecast_row(d, run_id, key, group_rows, am_list)
        await pg.insert_forecast(fc)
        forecast_rows.append(fc)

    # 8. optimizer_advice — risky 만 (assessment ∈ {이상, 주의}) 중 ~30% sampling = 전체 ~5%
    advice_rows: list[dict[str, Any]] = []
    for fc in forecast_rows:
        if fc["assessment"] not in ("이상", "주의"):
            continue
        # sampling: 결정성 hash 기준 ~30%
        h = int(
            hashlib.md5(
                f"{d.isoformat()}|{fc['wa']}|{fc['company']}|{fc['l6_main']}".encode()
            ).hexdigest(),
            16,
        )
        if (h % 100) >= 30:
            continue
        adv = _build_optimizer_advice(d, run_id, fc)
        await pg.insert_optimizer_advice(adv)
        advice_rows.append(adv)

    # 9. daily_reports row (report_md fixture)
    history_csv = {
        "date": d.isoformat(),
        "site_id": SITE_ID,
        "activities": n_active,
        "forecasts": len(forecast_rows),
        "risky": len(advice_rows),
    }
    report_md = f"# {PROJECT} 일일 보고서 ({d.isoformat()})\n\n- 활성 활동: {n_active}\n- 진단 그룹: {len(forecast_rows)}\n- 리스크 advice: {len(advice_rows)}\n"
    await pg.insert_daily_report(
        run_id, d, report_md, history_csv, bp_name="", site_id=SITE_ID
    )

    # 10. view_builder 9 jsonb upsert
    productivity = await _build_productivity_views(
        pg, run_id, SITE_ID, d, forecast_rows, []
    )
    quadrant = await _build_quadrant(pg, SITE_ID, d, productivity)
    wa_rows = await pg._pool.fetch(
        """
        SELECT l6_main, company, array_agg(DISTINCT wa) FILTER (WHERE wa IS NOT NULL) AS wa_list
        FROM mapper_activities WHERE run_id = $1 GROUP BY l6_main, company
        """,
        run_id,
    )
    wa_lookup = {
        (r["l6_main"], r["company"]): list(r["wa_list"] or []) for r in wa_rows
    }

    view_jsonbs = {
        "productivity_jsonb": productivity,
        "kpi_jsonb": await _build_kpi(pg, SITE_ID, d, productivity),
        "contractor_bars_jsonb": _build_contractor_bars(productivity),
        "trade_bars_jsonb": _build_trade_bars(productivity),
        "quadrant_jsonb": quadrant,
        "wp_summary_jsonb": await _build_wp_summary(
            pg, SITE_ID, d, productivity, quadrant
        ),
        "s_curve_jsonb": await _build_s_curve(pg, SITE_ID, d),
        "optimizer_view_jsonb": _build_optimizer_view(
            advice_rows, forecast_rows, [], wa_lookup=wa_lookup
        ),
        "scenarios_jsonb": _build_scenarios(advice_rows, forecast_rows),
    }
    for col, val in view_jsonbs.items():
        await pg.upsert_daily_report_view_col(run_id, SITE_ID, d, col, val)

    counts: dict[str, int] = {
        "pipeline_runs": 1,
        "parser_activities": n_active,
        "mapper_activities": n_active,
        "mapped_history": n_active,
        "forecasts": len(forecast_rows),
        "optimizer_advice": len(advice_rows),
        "daily_reports": 1,
    }

    # Chroma sample 일자 (PG INSERT 후, 같은 mapper_rows 사용)
    if chroma_cfg and _chroma_should_seed(
        d,
        chroma_cfg.get("chroma_mode", "weekly"),
        chroma_cfg.get("seed_start", d),
    ):
        n_chroma = await chroma_upsert_day(d, run_id, mapper_rows, chroma_cfg)
        counts["chroma_upserts"] = n_chroma

    return counts


# ============================================================================
# Main
# ============================================================================


async def amain() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=str, default="2024-04-11")
    p.add_argument("--end", type=str, default="2025-09-24")
    p.add_argument(
        "--chroma-on",
        action="store_true",
        default=False,
        help="Chroma daily_activities upsert (default off — PoC)",
    )
    p.add_argument(
        "--chroma-mode",
        type=str,
        default="weekly",
        choices=["weekly", "all", "anchor_only"],
        help="weekly = 매주 1일 + 9-24, all = 전 일자, anchor_only = 9-24 만",
    )
    p.add_argument(
        "--chroma-only",
        action="store_true",
        default=False,
        help="PG INSERT skip, Chroma 만 적재 (T4 용 — PG 는 이미 채워진 상태 가정)",
    )
    p.add_argument("--cleanup-only", action="store_true", default=False)
    p.add_argument(
        "--pg-url", type=str, default=os.environ.get("POSTGRES_URL", DEFAULT_PG_URL)
    )
    args = p.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    print(
        f"=== seed_dummy_year: {start} ~ {end} "
        f"(chroma_on={args.chroma_on}, mode={args.chroma_mode}, chroma_only={args.chroma_only}) ==="
    )

    # Chroma cfg build (--chroma-on 또는 --chroma-only 일 때만)
    chroma_cfg: Optional[dict[str, Any]] = None
    if args.chroma_on or args.chroma_only:
        required = [
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_VERSION",
            "EMBEDDING_MODEL",
            "CHROMA_HOST",
            "CHROMA_PORT",
        ]
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise RuntimeError(
                f"--chroma-on / --chroma-only requires env vars: {missing}"
            )
        chroma_cfg = {k: os.environ[k] for k in required}
        chroma_cfg["chroma_mode"] = args.chroma_mode
        chroma_cfg["seed_start"] = start

    pg = PGClient(args.pg_url)
    await pg.connect()
    try:
        if args.chroma_only:
            print("chroma_only: cleanup + PG INSERT skip (PG dummy 보존)")
        else:
            n_clean = await cleanup_dummy(pg, start, end)
            print(f"cleanup: {n_clean} pipeline_runs (dummy_seed) DELETE")
        if args.cleanup_only:
            return

        anchor = await load_anchor(pg)
        am_list = await load_activity_master(pg)
        # anchor 78사 보강 — anchor 에만 있고 activity_master 에 없는 (wa,company,l6) 의 virtual row
        am_keys = {(am["wa"], am["company"], am["l6_main"]) for am in am_list}
        anchor_only = [k for k in anchor.keys() if k not in am_keys]
        for key in anchor_only:
            a = anchor[key]
            wa, company, l6 = key
            plan_qty = float(a.get("plan_total_qty") or a.get("today_cum_qty") or 0)
            plan_mh = float(a.get("plan_mh") or 0)
            if (
                plan_qty <= 0
                and (a.get("cum_actual_mh_today") or 0) > 0
                and plan_mh > 0
            ):
                plan_qty = float(a["cum_actual_mh_today"]) / plan_mh * 100  # rough
            if plan_qty <= 0:
                plan_qty = 100.0  # 최소값
            if plan_mh <= 0:
                plan_mh = float(a.get("cum_actual_mh_today") or 0) or 100.0
            am_list.append(
                {
                    "site_id": SITE_ID,
                    "wa": wa,
                    "l5_disc": "",
                    "l6_main": l6,
                    "company": company,
                    "unit": a.get("unit") or "EA",
                    "plan_total_qty": plan_qty,
                    "plan_mh_rev2": plan_mh,
                    "plan_start": ANCHOR_DATE - timedelta(days=60),
                    "plan_finish": ANCHOR_DATE,
                }
            )
        print(
            f"anchor: {len(anchor)} (wa,company,l6_main) groups, "
            f"activity_master: {len(am_list) - len(anchor_only)} + anchor_only {len(anchor_only)} = {len(am_list)} rows"
        )

        totals: dict[str, int] = {}
        d = start
        day_count = 0
        while d <= end:
            counts = await seed_day(
                pg,
                d,
                anchor,
                am_list,
                chroma_cfg=chroma_cfg,
                chroma_only=args.chroma_only,
            )
            for k, v in counts.items():
                totals[k] = totals.get(k, 0) + v
            day_count += 1
            # progress log: 매 10일 또는 끝 또는 Chroma sample 일자
            n_chroma = counts.get("chroma_upserts")
            if day_count % 10 == 0 or d == end or n_chroma:
                active_n = counts.get("mapper_activities", counts.get("active", 0))
                chroma_msg = f" chroma={n_chroma}" if n_chroma else ""
                print(f"  [{d}] day#{day_count} active={active_n}{chroma_msg}")
            d += timedelta(days=1)

        print(f"=== TOTAL ({day_count} days) ===")
        for k, v in totals.items():
            print(f"  {k}: {v}")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(amain())
