"""Optimizer retrieve — 2-step degradation case 검색 + 헬퍼.

Spec: docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §5

Signature:
    fetch_degradation_cases(metadatas, documents, company, l6_main, today,
                            baseline_unit, baseline_value, n=5) -> list[dict]
    fetch_recovery_trajectory(metadatas, company, l6_main, case_date, today,
                              baseline_unit, baseline_value, window=7) -> dict
    _group_baseline(metadatas, company, l6_main, baseline_unit) -> Optional[float]
    _group_day_productivity(metas_of_day, baseline_unit) -> float

conditions 는 atomizer 와 동일 comma-joined str (결정 #19) — `substring in` 검사.
INCIDENT 5종: 장비대기 / 자재미입고 / 우천 / 돌관 / 야간연장.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

# spec §5.1 / §5.3 — degradation 트리거 incident 3종 (장비대기 / 자재미입고 / 돌관)
_DEGRADATION_INCIDENTS = ("장비대기", "자재미입고", "돌관")
# spec §5.3 — baseline 산출 시 제외해야 할 incident 5종 전수
_ALL_INCIDENTS = ("장비대기", "자재미입고", "우천", "돌관", "야간연장")
# spec §5.1 / §5.3 — degradation 판정 컷오프 (baseline 대비 85% 미만)
_DEGRADATION_RATIO = 0.85
# spec §5.3 — recovery 판정 컷오프 (baseline 대비 95% 이상)
_RECOVERY_RATIO = 0.95


def _group_day_productivity(metas_of_day: list[dict], baseline_unit: str) -> float:
    """그 날 (company, l6_main) 의 baseline_unit Σ today_qty / assigned_workers.

    같은 그룹 = assigned_workers 동일 reference (downstream §3.4 옵션 X).
    0 workers 또는 metas 0건 → 0.0.
    """
    if not metas_of_day:
        return 0.0
    qty = sum(m["today_qty"] for m in metas_of_day if m["unit"] == baseline_unit)
    workers = metas_of_day[0]["assigned_workers"]
    return qty / workers if workers > 0 else 0.0


def _group_baseline(
    metadatas: list[dict],
    company: Optional[str],
    l6_main: str,
    baseline_unit: str,
    *,
    l7_5_activity: Optional[str] = None,
) -> Optional[float]:
    """같은 (l6_main, unit[, company][, l7_5_activity]) 의 conditions 에 incident 없는 row productivity 평균.

    0 row → None (cold_start 신호 — 호출자가 pre_cases[key]=[] 분기).
    incident 키워드: 장비대기 / 자재미입고 / 우천 / 돌관 / 야간연장.
    company is None → 회사 무관 (l6_main+unit 만 매칭) — 동종 공사 cross-company baseline.
    l7_5_activity 가 주어지면 동일 activity 만 남김 (phase 2).
    """
    prods: list[float] = []
    for m in metadatas:
        if l6_main and m["l6_main"] != l6_main:
            continue
        if m["unit"] != baseline_unit:
            continue
        if company is not None and m["company"] != company:
            continue
        if l7_5_activity and m.get("l7_5_activity") != l7_5_activity:
            continue
        raw = m.get("conditions") or ""
        if any(c in raw for c in _ALL_INCIDENTS):
            continue
        if m["assigned_workers"] > 0 and m["today_qty"] > 0:
            prods.append(m["today_qty"] / m["assigned_workers"])
    return sum(prods) / len(prods) if prods else None


def fetch_degradation_cases(
    metadatas: list[dict],
    documents: list[str],
    company: Optional[str],
    l6_main: str,
    today: date,
    baseline_unit: str,
    baseline_value: float,
    n: int = 5,
    *,
    l7_5_activity: Optional[str] = None,
) -> list[dict]:
    """Step 1 — 같은 (l6_main[, company]) 의 저하 case top-N recency.

    company is None → 회사 무관 (l6_main 만 매칭) — 동종 공사 cross-company case.
    저하 정의: conditions ∋ {장비대기, 자재미입고, 돌관} AND group productivity < baseline*0.85.
    worker_source ∈ {"synthetic_v2", "mh_prorated"} 만 허용 (단순 synthetic 노이즈 회피).
    date < today (미래 행 제외).
    conditions 는 comma-joined str → `substring in` 검사.
    """
    by_date: dict[str, list] = defaultdict(list)
    for m, d in zip(metadatas, documents):
        if l6_main and m["l6_main"] != l6_main:
            continue
        if company is not None and m["company"] != company:
            continue
        if l7_5_activity and m.get("l7_5_activity") != l7_5_activity:
            continue
        if m["date"] >= today.isoformat():
            continue
        # 2026-05-22: worker_source 화이트리스트 제거.
        # 이전엔 ('synthetic_v2','mh_prorated') 만 허용 → backfill_v2/dummy_seed 차단 → 광건/태우 등
        # 합성 3사 외 75사가 case=0 cold_start. 이제 모든 source 인정.
        by_date[m["date"]].append((m, d))

    cases: list[dict] = []
    for d, rows in by_date.items():
        raw = rows[0][0].get("conditions") or ""
        has_incident = any(c in raw for c in _DEGRADATION_INCIDENTS)
        prod = _group_day_productivity([m for m, _ in rows], baseline_unit)
        is_degraded = prod < baseline_value * _DEGRADATION_RATIO
        # 2026-05-22: degradation 정의 완화 — conditions ∋ incident OR prod 저하 둘 중 하나만 만족.
        # 이전엔 AND (conditions ∋ incident + prod < baseline×0.85) → backfill_v2 의 conditions='[]'
        # 빈 string row 가 모두 차단. 이제 prod 저하만으로도 충분 (수치 근거 기반).
        if not (has_incident or is_degraded):
            continue
        cases.append(
            {
                "date": d,
                "conditions": raw,
                "productivity": prod,
                "assigned_workers": rows[0][0]["assigned_workers"],
                "activities": [doc for _, doc in rows],
            }
        )
    cases.sort(key=lambda c: c["date"], reverse=True)
    return cases[:n]


def fetch_recovery_trajectory(
    metadatas: list[dict],
    company: Optional[str],
    l6_main: str,
    case_date: str,
    today: date,
    baseline_unit: str,
    baseline_value: float,
    window: int = 7,
    *,
    l7_5_activity: Optional[str] = None,
) -> dict:
    """Step 2 — case_date+1 ~ +window 의 group productivity trajectory.

    company is None → 회사 무관 매칭 (cross-company recovery 추세).
    회복 정의: productivity >= baseline_value * 0.95.
    recovery_days = 첫 ✓ 까지의 일수 (1-based, None 이면 미회복).
    target_d >= today 인 시점에서 break (window today clipped).
    """
    by_date: dict[str, list] = defaultdict(list)
    for m in metadatas:
        if l6_main and m["l6_main"] != l6_main:
            continue
        if company is not None and m["company"] != company:
            continue
        if l7_5_activity and m.get("l7_5_activity") != l7_5_activity:
            continue
        by_date[m["date"]].append(m)

    case_d = date.fromisoformat(case_date)
    trajectory: list[dict] = []
    for d_offset in range(1, window + 1):
        target_d = case_d + timedelta(days=d_offset)
        if target_d >= today:
            break
        target_iso = target_d.isoformat()
        if target_iso not in by_date:
            continue
        rows = by_date[target_iso]
        prod = _group_day_productivity(rows, baseline_unit)
        trajectory.append(
            {
                "date": target_iso,
                "conditions": rows[0].get("conditions") or "",
                "productivity": prod,
                "recovered": prod >= baseline_value * _RECOVERY_RATIO,
            }
        )
    recovery_days = next(
        (i + 1 for i, t in enumerate(trajectory) if t["recovered"]),
        None,
    )
    return {"trajectory": trajectory, "recovery_days": recovery_days}
