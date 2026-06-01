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

from pipeline.agents.synthetic.distributions import (  # noqa: E402,F401
    P_NORM,
    PEAK_MULT,
    PLATEAU_END,
    RAMP_END,
    f3_cum_ratio,
    f3_daily_ratio,
)
from pipeline.agents.synthetic.seed_distribution import (  # noqa: E402
    bell_distribute,
    conserve_actual,
    cumulative,
)
from pipeline.db import PGClient  # noqa: E402
from pipeline.agents.optimizer._trade_frames import lookup_frame  # noqa: E402
from pipeline.agents.optimizer._work_content import (  # noqa: E402
    DEGRADE_CUT,
    factor_for,
    work_content_for,
)

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

# spec §7 — 2026-05-29: PROD_TARGET(90 고정) 은 condition→prod factor 로 대체.
# (condition 과 prod 가 독립 생성되던 문제 해소 — _work_content.CONDITION_PROD_FACTOR)
OUTLIER_PROB = 0.05


def _seeded_rng(seed_str: str) -> random.Random:
    h = hashlib.sha256(seed_str.encode("utf-8")).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def _noise(rng: random.Random, scale: float = 0.10) -> float:
    return 1.0 + (rng.random() * 2.0 - 1.0) * scale


# 사용자 결정 (2026-05-29): condition 분포 정상 ~60% + 저하 ~40%.
# 이전엔 7 tag 균등 (정상 14%, incident 86%) → 모든 wp 가 매일 incident 라 저하→회복
# 패턴이 안 생기고 일부 wp 는 정상날이 없어 회복 trajectory 가 비었다.
# 정상 비율을 높여 "대부분 정상 + 가끔 저하 → 회복" 실제 현장 패턴을 만든다.
_NORMAL_WEIGHT = 0.60


def _pick_diagnosis(date_str: str, wa: str, company: str, l6: str) -> dict[str, Any]:
    h = int(hashlib.md5(f"{date_str}|{wa}|{company}".encode()).hexdigest(), 16)
    r = (h % 1_000_000) / 1_000_000.0  # 결정성 [0, 1)
    if r < _NORMAL_WEIGHT:
        pat = next(p for p in DIAGNOSIS_PATTERNS if p["tag"] == "normal_steady")
    else:
        incidents = [p for p in DIAGNOSIS_PATTERNS if p["tag"] != "normal_steady"]
        idx = int((r - _NORMAL_WEIGHT) / (1.0 - _NORMAL_WEIGHT) * len(incidents))
        pat = incidents[min(idx, len(incidents) - 1)]
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
# PHASE 1 — per-row mapper_activities builder (reseed v2 — 정규분포 + 총합보존)
# ============================================================================


# 지각완료(stretch) 모델 (사용자 결정 2026-05-29 option2): 일부 활동의 actual 을
# plan_finish 너머 effective_finish = plan_finish + ext 까지 늘려 분배. 전체 물량은
# plan_total 그대로 다 소화(보존)하되 plan_finish 시점엔 미달 = 실 지연 갭. 정시 활동(ext=0)은
# plan_finish 까지 ~85% 엔벨로프 후 보존. 결정성 hash 선정. 게이트 결과 보고 비율/연장 튜닝.
DELAY_PROB = 0.55  # 활동 중 지각완료 비율 (게이트 결과 보고 튜닝)
DELAY_EXT_MIN_DAYS = 90
DELAY_EXT_MAX_DAYS = 240


def _activity_delay_ext(wa: str, company: str, l6: str, l7_5: str) -> int:
    """결정성 지각 연장일수 (0 = 정시). ~DELAY_PROB 활동만 ext>0."""
    h = int(hashlib.md5(f"{wa}|{company}|{l6}|{l7_5}".encode()).hexdigest(), 16)
    if (h % 100) >= int(DELAY_PROB * 100):
        return 0
    span = DELAY_EXT_MAX_DAYS - DELAY_EXT_MIN_DAYS + 1
    return DELAY_EXT_MIN_DAYS + (h // 100) % span


def _v2_activity_series(am_row: dict[str, Any]) -> dict[str, Any]:
    """활동 전체 기간의 plan/actual/mh 일별 시계열 (결정성, am_row 캐시).

    설계 §1 + 지각완료(stretch):
      plan 일별 = bell_distribute(plan_total, total_days) (계획 기간, Σ=plan_total),
      actual 일별 = conserve_actual(bell over eff_days, 조건factors) (Σ=plan_total 보존),
        eff_days = total_days + ext (지각 활동은 ext>0 → 더 긴 기간에 분배 → plan_finish 미달),
      mh 일별 = actual × (plan_mh/plan_total) ÷ factor (CPI=조건 생산성).
    am_list dict 가 일자 루프에서 재사용되므로 활동당 1회만 계산.
    """
    cached = am_row.get("_v2series")
    if cached is not None:
        return cached
    plan_start = am_row["plan_start"]
    plan_finish = am_row["plan_finish"]
    total_days = (plan_finish - plan_start).days + 1
    plan_total = float(am_row.get("plan_total_qty") or 0)
    plan_mh = float(am_row.get("plan_mh_rev2") or 0)
    wa = am_row["wa"]
    company = am_row["company"]
    l6 = am_row["l6_main"]
    l7_5 = am_row.get("l7_5_activity") or ""
    frame = lookup_frame(l6)[0]

    ext = _activity_delay_ext(wa, company, l6, l7_5)
    eff_days = total_days + ext

    # 조건 factor — actual 분배 전 기간(eff_days)
    conds: list[tuple[str, dict[str, Any]]] = []
    factors: list[float] = []
    for i in range(eff_days):
        dd = plan_start + timedelta(days=i)
        diag = _pick_diagnosis(str(dd), wa, company, l6)
        c = diag["conditions"][0] if diag["conditions"] else "정상"
        conds.append((c, diag))
        factors.append(factor_for(c, f"{dd}|{wa}|{company}|pf"))

    plan_daily = bell_distribute(plan_total, total_days)  # 계획 기간 bell
    actual_base = bell_distribute(
        plan_total, eff_days
    )  # actual 분배 기간 bell (지각=더 김)
    actual_daily = conserve_actual(actual_base, factors)  # Σ=plan_total 보존
    pmpq = (plan_mh / plan_total) if plan_total > 0 else 0.0
    mh_daily = [
        (aq * pmpq / f) if f > 0 else (aq * pmpq)
        for aq, f in zip(actual_daily, factors)
    ]
    series: dict[str, Any] = {
        "total_days": total_days,
        "eff_days": eff_days,
        "ext_days": ext,
        "plan_total": plan_total,
        "plan_mh": plan_mh,
        "frame": frame,
        "plan_daily": plan_daily,
        "plan_cum": cumulative(plan_daily),
        "actual_daily": actual_daily,
        "mh_daily": mh_daily,
        "cum_qty": cumulative(actual_daily),
        "cum_mh": cumulative(mh_daily),
        "factors": factors,
        "conds": conds,
    }
    am_row["_v2series"] = series
    return series


def _build_mapper_row(
    d: date,
    am_row: dict[str, Any],
    anchor_row: Optional[
        dict[str, Any]
    ],  # 인터페이스 보존 (호출자 영향 X), 내부 사용 X
    rng: random.Random,
) -> Optional[dict[str, Any]]:
    """activity_master row → 일자별 mapper_activities row (reseed v2).

    설계: 2026-05-29-cpia-reseed-v2-per-unit-seeding-design.md §1.
    plan 일별=정규분포(bell), actual=plan×조건factor + 활동별 총합보존(막바지 보정),
    today_cum_qty=Σ(일별 actual) (구 'plan_total×cum_frac' 계획곡선 추종 버그 제거).
    rng: 인터페이스 보존 (v2 는 _v2_activity_series 결정성 — 미사용).
    """
    plan_start = am_row["plan_start"]
    series = _v2_activity_series(am_row)
    idx = (d - plan_start).days
    # 지각 활동은 effective_finish(=plan_start+eff_days-1) 까지 row 생성 (plan_finish 너머).
    if idx < 0 or idx >= series["eff_days"]:
        return None

    total_days = series["total_days"]
    plan_total = series["plan_total"]
    plan_mh = series["plan_mh"]

    today_qty = series["actual_daily"][idx]
    today_cum_qty = series["cum_qty"][idx]
    cum_actual_mh = series["cum_mh"][idx]
    factor = series["factors"][idx]
    cond, diag = series["conds"][idx]

    # plan-relative 진척 (지각 구간 idx>=total_days 면 >1 = post_due)
    progress = (idx + 1) / total_days
    today_assigned_workers = max(1.0, series["mh_daily"][idx] / 8.0)
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
        # work_content: 저하일(factor<DEGRADE_CUT)=저하 narrative, 회복/정상일=회복 narrative.
        # retrieve 가 저하일 + D+1 회복일 work_content 를 가져와 similar_cases 저하/회복 분리.
        "work_content": work_content_for(
            series["frame"],
            cond,
            "저하" if factor < DEGRADE_CUT else "회복",
        ),
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
            "work_content": valid[i].get("work_content")
            or "",  # 2026-05-29 저하/회복 narrative
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
    """기존 dummy_seed row 삭제 — date range 내.

    2026-05-29: consolidated_reports FK 선삭제 추가. pipeline_runs 삭제 시
    consolidated_reports_run_id_fkey 위반을 막는다 (재seed 반복 시 발생하던 FK 에러).
    """
    async with pg._pool.acquire() as con:
        target_runs_sql = """
            SELECT pr.run_id FROM pipeline_runs pr
            WHERE pr.site_id=$1 AND pr.report_date BETWEEN $2 AND $3
            AND pr.run_id IN (
                SELECT DISTINCT run_id FROM mapper_activities WHERE mapping_source='dummy_seed'
            )
        """
        # FK 자식 테이블 선삭제 (run_id 참조).
        await con.execute(
            f"DELETE FROM consolidated_reports WHERE run_id IN ({target_runs_sql})",
            SITE_ID,
            start,
            end,
        )
        result = await con.execute(
            f"DELETE FROM pipeline_runs pr WHERE pr.run_id IN ({target_runs_sql})",
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
    trades: Optional[list[str]] = None,
) -> dict[str, int]:
    """단일 일자 적재. return: counts dict.

    chroma_cfg None  → PG 만 (기존 동작).
    chroma_cfg dict  → PG + Chroma sample 일자 (_chroma_should_seed 충족 시).
    chroma_only True → PG INSERT skip, Chroma 만 (T4 용).
    trades None      → trade filter 비활성 (기존 동작 보존).
    trades list      → 해당 trade row 만 mapper_rows 에 append. (2026-05-27 Task 19:
                       사용자 의도 — 적재 단계에서 건축·토목 외 trade row 자체를 차단.)
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
            # 2026-05-27 Task 19: trade filter — 적재 단계 차단 (사용자 의도).
            # trades None 이면 filter 비활성 (회귀 0). list 면 trade not in trades → skip.
            if trades is not None and r.get("trade") not in trades:
                continue
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

    # 2026-05-29 reseed-v2 (Task 6.3): seed 는 INPUT (mapper_activities) 전용.
    # forecaster/optimizer/reporter 산출은 실 prod graph (build_demo_graph) 가
    # 생성한다 — fixture INSERT 금지 (prod-graph-only). 구 step 7~10 (forecasts /
    # optimizer_advice / daily_reports / view jsonb) 제거.
    counts: dict[str, int] = {
        "pipeline_runs": 1,
        "parser_activities": n_active,
        "mapper_activities": n_active,
        "mapped_history": n_active,
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
# consolidated_reports backfill
# ============================================================================


async def _backfill_consolidated_reports(pg: PGClient, start: date, end: date) -> int:
    """(D-11) 단일 SITE_ID 의 consolidated_reports mock backfill.

    `scripts/seed_dummy_year.py:58` 의 단일 상수 SITE_ID = "m15x-ph3-ibl" 사용.
    `amain()` 의 `while d <= end:` 루프 다음에 별도 두 번째 루프로 호출.

    실패 (NoDataError / pipeline_runs 없음) 는 skip + log.

    Returns: backfill 된 row 수.
    """
    from pipeline.agents.exporter import (  # noqa: PLC0415
        NoDataError,
        fetch_sheet_data,
        render_xlsx,
    )
    from pipeline.db import (  # noqa: PLC0415
        fetch_site_by_id,
        upsert_consolidated_report,
    )

    count = 0
    site_row = await fetch_site_by_id(pg, SITE_ID)
    project_name = (site_row or {}).get("name") or PROJECT

    d = start
    while d <= end:
        try:
            data = await fetch_sheet_data(pg, SITE_ID, d)
        except NoDataError:
            logging.info("seed consolidated_reports skip — date=%s (no parser data)", d)
            d = d + timedelta(days=1)
            continue
        xlsx_bytes = render_xlsx(data, d, project=project_name)
        async with pg._pool.acquire() as con:
            run_row = await con.fetchrow(
                """
                SELECT run_id FROM pipeline_runs
                WHERE site_id=$1 AND report_date=$2
                ORDER BY started_at DESC NULLS LAST LIMIT 1
                """,
                SITE_ID,
                d,
            )
        if not run_row:
            logging.warning(
                "seed consolidated_reports skip — no pipeline_runs for date=%s", d
            )
            d = d + timedelta(days=1)
            continue
        await upsert_consolidated_report(
            pg,
            site_id=SITE_ID,
            report_date=d,
            xlsx_bytes=xlsx_bytes,
            run_id=run_row["run_id"],
        )
        async with pg._pool.acquire() as con:
            await con.execute(
                "UPDATE consolidated_reports SET is_mock=TRUE WHERE site_id=$1 AND report_date=$2",
                SITE_ID,
                d,
            )
        count += 1
        logging.info(
            "seed consolidated_reports OK — date=%s bytes=%d", d, len(xlsx_bytes)
        )
        d = d + timedelta(days=1)
    return count


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
    p.add_argument(
        "--trades",
        nargs="+",
        default=["건축", "토목"],
        help="적재할 trade list (default: 건축 토목). 사용자 의도: 시연 윈도우 trade 좁히기.",
    )
    args = p.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    print(
        f"=== seed_dummy_year: {start} ~ {end} "
        f"(chroma_on={args.chroma_on}, mode={args.chroma_mode}, chroma_only={args.chroma_only}, "
        f"trades={args.trades}) ==="
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
                trades=args.trades,
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

        c_count = await _backfill_consolidated_reports(pg, start, end)
        logging.info(
            "seed_dummy_year: consolidated_reports backfill = %d rows", c_count
        )

        print(f"=== TOTAL ({day_count} days) ===")
        for k, v in totals.items():
            print(f"  {k}: {v}")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(amain())
