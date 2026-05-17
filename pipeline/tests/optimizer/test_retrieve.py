"""Tests for optimizer retrieve — spec §5.1~§5.4 + §12.1.

12 unit (mock metadatas/documents, no real Chroma — pytest 결정성 보장):
1.  test_fetch_degradation_cases_filters_incident_str_substring
2.  test_fetch_degradation_cases_excludes_future_date
3.  test_fetch_degradation_cases_excludes_recovered
4.  test_fetch_degradation_cases_excludes_legacy_synthetic
5.  test_fetch_degradation_cases_top_n_recency
6.  test_fetch_degradation_cases_includes_dolgwan
7.  test_fetch_recovery_trajectory_window_clipped_by_today
8.  test_fetch_recovery_trajectory_recovery_days_first_recovered
9.  test_fetch_recovery_trajectory_no_recovery
10. test_group_baseline_normal_only_excludes_all_incidents_inc_dolgwan
11. test_group_baseline_none_when_no_normal_rows
12. test_group_day_productivity_baseline_unit_zero_workers
"""

from __future__ import annotations

from datetime import date

from pipeline.agents.optimizer.retrieve import (
    _group_baseline,
    _group_day_productivity,
    fetch_degradation_cases,
    fetch_recovery_trajectory,
)

COMPANY = "남웅건설"
L6_MAIN = "철근콘크리트공사"
UNIT = "m3"
BASELINE = 31.072  # spec §0/§4.8 의 실제 baseline_v2 (참고용; 테스트 별 자체 값 사용 가능)


def _row(
    *,
    date_iso: str,
    today_qty: float,
    assigned_workers: float = 88.0,
    conditions: str = "맑음",
    company: str = COMPANY,
    l6_main: str = L6_MAIN,
    unit: str = UNIT,
    worker_source: str = "synthetic_v2",
    work_content: str = "기초공사 : 거푸집 공사",
) -> dict:
    """metadatas row factory — atomizer/synthetic_v2 schema 호환."""
    return {
        "date": date_iso,
        "company": company,
        "l6_main": l6_main,
        "unit": unit,
        "today_qty": today_qty,
        "assigned_workers": assigned_workers,
        "conditions": conditions,
        "worker_source": worker_source,
        "work_content": work_content,
    }


# ── 1. fetch_degradation_cases: conditions str substring 검사 ───────────
def test_fetch_degradation_cases_filters_incident_str_substring():
    """conditions = comma-joined str. '우천,장비대기' 같은 multi-token 도 substring 으로 매칭."""
    baseline = 20.0  # 저하 threshold = 17.0
    metas = [
        # incident 있음 + 저하 → 포함
        _row(date_iso="2025-09-20", today_qty=10.0 * 88, conditions="우천,장비대기"),
        # 단일 incident '장비대기'
        _row(date_iso="2025-09-19", today_qty=8.0 * 88, conditions="장비대기"),
        # '맑음' 만 (incident 없음) → 제외
        _row(date_iso="2025-09-18", today_qty=10.0 * 88, conditions="맑음"),
    ]
    docs = ["doc20", "doc19", "doc18"]
    cases = fetch_degradation_cases(
        metas,
        docs,
        COMPANY,
        L6_MAIN,
        today=date(2025, 9, 25),
        baseline_unit=UNIT,
        baseline_value=baseline,
        n=5,
    )
    assert len(cases) == 2
    dates = {c["date"] for c in cases}
    assert dates == {"2025-09-20", "2025-09-19"}


# ── 2. 미래 date 제외 ─────────────────────────────────────────────────
def test_fetch_degradation_cases_excludes_future_date():
    baseline = 20.0
    metas = [
        # date == today → 제외 (>= today)
        _row(date_iso="2025-09-25", today_qty=5.0 * 88, conditions="장비대기"),
        # date > today → 제외
        _row(date_iso="2025-09-26", today_qty=5.0 * 88, conditions="장비대기"),
        # date < today → 포함
        _row(date_iso="2025-09-24", today_qty=5.0 * 88, conditions="장비대기"),
    ]
    docs = ["d25", "d26", "d24"]
    cases = fetch_degradation_cases(
        metas,
        docs,
        COMPANY,
        L6_MAIN,
        today=date(2025, 9, 25),
        baseline_unit=UNIT,
        baseline_value=baseline,
    )
    assert len(cases) == 1
    assert cases[0]["date"] == "2025-09-24"


# ── 3. baseline*0.85 이상 (회복) 제외 ─────────────────────────────────
def test_fetch_degradation_cases_excludes_recovered():
    baseline = 20.0  # threshold = 17.0
    metas = [
        # productivity = 18.0 (> 17.0) → 회복으로 간주 → 제외
        _row(date_iso="2025-09-20", today_qty=18.0 * 88, conditions="장비대기"),
        # productivity = 10.0 (< 17.0) → 저하 → 포함
        _row(date_iso="2025-09-19", today_qty=10.0 * 88, conditions="장비대기"),
    ]
    docs = ["d1", "d2"]
    cases = fetch_degradation_cases(
        metas,
        docs,
        COMPANY,
        L6_MAIN,
        today=date(2025, 9, 25),
        baseline_unit=UNIT,
        baseline_value=baseline,
    )
    assert len(cases) == 1
    assert cases[0]["date"] == "2025-09-19"


# ── 4. legacy "synthetic" 제외, "synthetic_v2" + "mh_prorated" 만 ───────
def test_fetch_degradation_cases_excludes_legacy_synthetic():
    baseline = 20.0
    metas = [
        _row(
            date_iso="2025-09-20", today_qty=5.0 * 88, conditions="장비대기", worker_source="synthetic"
        ),  # legacy → 제외
        _row(
            date_iso="2025-09-19", today_qty=5.0 * 88, conditions="장비대기", worker_source="synthetic_v2"
        ),  # 포함
        _row(
            date_iso="2025-09-18", today_qty=5.0 * 88, conditions="장비대기", worker_source="mh_prorated"
        ),  # 포함
        _row(
            date_iso="2025-09-17", today_qty=5.0 * 88, conditions="장비대기", worker_source="user_corrected"
        ),  # 제외
    ]
    docs = ["d20", "d19", "d18", "d17"]
    cases = fetch_degradation_cases(
        metas,
        docs,
        COMPANY,
        L6_MAIN,
        today=date(2025, 9, 25),
        baseline_unit=UNIT,
        baseline_value=baseline,
    )
    sources = {c["date"] for c in cases}
    assert sources == {"2025-09-19", "2025-09-18"}


# ── 5. recency 내림차순 + top_n cap ─────────────────────────────────────
def test_fetch_degradation_cases_top_n_recency():
    baseline = 20.0
    # 7 일치 모두 incident + 저하 → top 5 (recency) 만 반환
    metas = []
    docs = []
    for i in range(1, 8):
        d_iso = f"2025-09-{10 + i:02d}"  # 2025-09-11 ~ 2025-09-17
        metas.append(_row(date_iso=d_iso, today_qty=5.0 * 88, conditions="장비대기"))
        docs.append(f"doc{i}")
    cases = fetch_degradation_cases(
        metas,
        docs,
        COMPANY,
        L6_MAIN,
        today=date(2025, 9, 25),
        baseline_unit=UNIT,
        baseline_value=baseline,
        n=5,
    )
    assert len(cases) == 5
    # 가장 최근 5 일 (9/17, 9/16, 9/15, 9/14, 9/13)
    assert [c["date"] for c in cases] == [
        "2025-09-17",
        "2025-09-16",
        "2025-09-15",
        "2025-09-14",
        "2025-09-13",
    ]


# ── 6. 돌관 incident 포함 ────────────────────────────────────────────
def test_fetch_degradation_cases_includes_dolgwan():
    """spec §5.1 — 저하 incident 3종 (장비대기 / 자재미입고 / 돌관) 모두 포함."""
    baseline = 20.0
    metas = [
        _row(date_iso="2025-09-20", today_qty=5.0 * 88, conditions="돌관"),
        _row(date_iso="2025-09-19", today_qty=5.0 * 88, conditions="자재미입고"),
        _row(date_iso="2025-09-18", today_qty=5.0 * 88, conditions="장비대기"),
        # 우천 / 야간연장 단독은 저하 트리거 incident 아님 (spec §5.1)
        _row(date_iso="2025-09-17", today_qty=5.0 * 88, conditions="우천"),
        _row(date_iso="2025-09-16", today_qty=5.0 * 88, conditions="야간연장"),
    ]
    docs = [f"doc{i}" for i in range(5)]
    cases = fetch_degradation_cases(
        metas,
        docs,
        COMPANY,
        L6_MAIN,
        today=date(2025, 9, 25),
        baseline_unit=UNIT,
        baseline_value=baseline,
    )
    dates = {c["date"] for c in cases}
    assert dates == {"2025-09-20", "2025-09-19", "2025-09-18"}


# ── 7. recovery window today 절단 ────────────────────────────────────
def test_fetch_recovery_trajectory_window_clipped_by_today():
    """case_date=9/20, today=9/23, window=7 → 후속 9/21, 9/22 만 (9/23 >= today break)."""
    baseline = 20.0
    metas = [
        _row(date_iso="2025-09-21", today_qty=15.0 * 88, conditions="맑음"),
        _row(date_iso="2025-09-22", today_qty=18.0 * 88, conditions="맑음"),
        _row(date_iso="2025-09-23", today_qty=20.0 * 88, conditions="맑음"),
        _row(date_iso="2025-09-24", today_qty=22.0 * 88, conditions="맑음"),
    ]
    out = fetch_recovery_trajectory(
        metas,
        COMPANY,
        L6_MAIN,
        case_date="2025-09-20",
        today=date(2025, 9, 23),
        baseline_unit=UNIT,
        baseline_value=baseline,
        window=7,
    )
    dates = [t["date"] for t in out["trajectory"]]
    assert dates == ["2025-09-21", "2025-09-22"]


# ── 8. 첫 회복일 = recovery_days (1-based) ──────────────────────────
def test_fetch_recovery_trajectory_recovery_days_first_recovered():
    """productivity ≥ baseline*0.95 = 19.0. d+1=15(미회복), d+2=20(회복) → recovery_days=2."""
    baseline = 20.0  # 회복 threshold = 19.0
    metas = [
        _row(date_iso="2025-09-21", today_qty=15.0 * 88, conditions="장비대기"),  # 15 < 19
        _row(date_iso="2025-09-22", today_qty=20.0 * 88, conditions="맑음"),  # 20 ≥ 19 ✓
        _row(date_iso="2025-09-23", today_qty=25.0 * 88, conditions="맑음"),  # 25 ≥ 19
    ]
    out = fetch_recovery_trajectory(
        metas,
        COMPANY,
        L6_MAIN,
        case_date="2025-09-20",
        today=date(2025, 9, 25),
        baseline_unit=UNIT,
        baseline_value=baseline,
        window=7,
    )
    assert out["recovery_days"] == 2
    assert [t["recovered"] for t in out["trajectory"]] == [False, True, True]


# ── 9. window 내 회복 없음 → recovery_days = None ───────────────────
def test_fetch_recovery_trajectory_no_recovery():
    baseline = 20.0  # 회복 threshold = 19.0
    metas = [
        _row(date_iso="2025-09-21", today_qty=5.0 * 88, conditions="장비대기"),
        _row(date_iso="2025-09-22", today_qty=6.0 * 88, conditions="장비대기"),
        _row(date_iso="2025-09-23", today_qty=7.0 * 88, conditions="자재미입고"),
    ]
    out = fetch_recovery_trajectory(
        metas,
        COMPANY,
        L6_MAIN,
        case_date="2025-09-20",
        today=date(2025, 9, 25),
        baseline_unit=UNIT,
        baseline_value=baseline,
        window=7,
    )
    assert out["recovery_days"] is None
    assert len(out["trajectory"]) == 3
    assert all(not t["recovered"] for t in out["trajectory"])


# ── 10. _group_baseline — 5 incident 전수 제외 ────────────────────
def test_group_baseline_normal_only_excludes_all_incidents_inc_dolgwan():
    """incident 5종 (장비대기 / 자재미입고 / 우천 / 돌관 / 야간연장) 전수 제외 후 평균.

    정상 row: today_qty=20, workers=88 → productivity=20/88 ≈ 0.227 (단위 동일).
    실값으로는 today_qty 100, workers 5 → 20.0; 두 정상 row 평균 = 20.0.
    """
    metas = [
        _row(date_iso="2025-09-01", today_qty=100.0, assigned_workers=5.0, conditions="맑음"),
        _row(date_iso="2025-09-02", today_qty=100.0, assigned_workers=5.0, conditions="흐림"),
        # 5종 incident → 전수 제외
        _row(date_iso="2025-09-03", today_qty=100.0, assigned_workers=5.0, conditions="장비대기"),
        _row(date_iso="2025-09-04", today_qty=100.0, assigned_workers=5.0, conditions="자재미입고"),
        _row(date_iso="2025-09-05", today_qty=100.0, assigned_workers=5.0, conditions="우천"),
        _row(date_iso="2025-09-06", today_qty=100.0, assigned_workers=5.0, conditions="돌관"),
        _row(date_iso="2025-09-07", today_qty=100.0, assigned_workers=5.0, conditions="야간연장"),
    ]
    baseline = _group_baseline(metas, COMPANY, L6_MAIN, UNIT)
    assert baseline == 20.0


# ── 11. 정상 row 0건 → None ─────────────────────────────────────────
def test_group_baseline_none_when_no_normal_rows():
    """모든 row 가 incident → None 반환 (cold_start 신호)."""
    metas = [
        _row(date_iso="2025-09-01", today_qty=100.0, assigned_workers=5.0, conditions="장비대기"),
        _row(date_iso="2025-09-02", today_qty=100.0, assigned_workers=5.0, conditions="우천,자재미입고"),
        _row(date_iso="2025-09-03", today_qty=100.0, assigned_workers=5.0, conditions="돌관"),
    ]
    baseline = _group_baseline(metas, COMPANY, L6_MAIN, UNIT)
    assert baseline is None


# ── 12. _group_day_productivity — 0 workers 분기 ──────────────────
def test_group_day_productivity_baseline_unit_zero_workers():
    """0 workers → 0.0 (ZeroDivisionError 회피). + baseline_unit 외 row qty 제외 boundary."""
    metas_zero = [
        _row(date_iso="2025-09-20", today_qty=100.0, assigned_workers=0.0, unit=UNIT),
    ]
    assert _group_day_productivity(metas_zero, UNIT) == 0.0

    # baseline_unit 외 row 의 qty 는 합산 X (m3 만 카운트)
    metas_mix = [
        _row(date_iso="2025-09-20", today_qty=80.0, assigned_workers=10.0, unit=UNIT),
        _row(date_iso="2025-09-20", today_qty=999.0, assigned_workers=10.0, unit="ton"),
    ]
    assert _group_day_productivity(metas_mix, UNIT) == 8.0

    # 빈 list → 0.0
    assert _group_day_productivity([], UNIT) == 0.0
