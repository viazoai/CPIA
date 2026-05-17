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
    company: str,
    l6_main: str,
    baseline_unit: str,
) -> Optional[float]:
    """같은 (company, l6_main, unit) 의 conditions 에 incident 없는 row productivity 평균.

    0 row → None (cold_start 신호 — 호출자가 pre_cases[key]=[] 분기).
    incident 키워드: 장비대기 / 자재미입고 / 우천 / 돌관 / 야간연장.
    """
    prods: list[float] = []
    for m in metadatas:
        if m["company"] != company or m["l6_main"] != l6_main or m["unit"] != baseline_unit:
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
    company: str,
    l6_main: str,
    today: date,
    baseline_unit: str,
    baseline_value: float,
    n: int = 5,
) -> list[dict]:
    """Step 1 — 같은 (company, l6_main) 의 저하 case top-N recency.

    저하 정의: conditions ∋ {장비대기, 자재미입고, 돌관} AND group productivity < baseline*0.85.
    worker_source ∈ {"synthetic_v2", "mh_prorated"} 만 허용 (단순 synthetic 노이즈 회피).
    date < today (미래 행 제외).
    conditions 는 comma-joined str → `substring in` 검사.
    """
    by_date: dict[str, list] = defaultdict(list)
    for m, d in zip(metadatas, documents):
        if m["company"] != company or m["l6_main"] != l6_main:
            continue
        if m["date"] >= today.isoformat():
            continue
        if m.get("worker_source") not in ("synthetic_v2", "mh_prorated"):
            continue
        by_date[m["date"]].append((m, d))

    cases: list[dict] = []
    for d, rows in by_date.items():
        raw = rows[0][0].get("conditions") or ""
        if not any(c in raw for c in _DEGRADATION_INCIDENTS):
            continue
        prod = _group_day_productivity([m for m, _ in rows], baseline_unit)
        if prod >= baseline_value * _DEGRADATION_RATIO:
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
    company: str,
    l6_main: str,
    case_date: str,
    today: date,
    baseline_unit: str,
    baseline_value: float,
    window: int = 7,
) -> dict:
    """Step 2 — case_date+1 ~ +window 의 group productivity trajectory.

    회복 정의: productivity >= baseline_value * 0.95.
    recovery_days = 첫 ✓ 까지의 일수 (1-based, None 이면 미회복).
    target_d >= today 인 시점에서 break (window today clipped).
    """
    by_date: dict[str, list] = defaultdict(list)
    for m in metadatas:
        if m["company"] == company and m["l6_main"] == l6_main:
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
