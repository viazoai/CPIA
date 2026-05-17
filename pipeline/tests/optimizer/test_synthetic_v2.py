"""Tests for synthetic v2 state machine — spec §4.1 + §4.2 + §4.3."""

from __future__ import annotations

import statistics

from pipeline.agents.optimizer.synthetic_v2 import generate_synthetic_v2_group

# ── 공용 fixture ────────────────────────────────────────────────
COMPANY = "남웅건설"
L6_MAIN = "철근콘크리트공사"
ACTIVITY_POOL_SINGLE = ["기초공사 : 거푸집 공사"]
ACTIVITY_POOL_MULTI = ["기초공사 : 거푸집 공사", "RC Wall : 철근 조립"]
BASELINE_WORKERS = 88.0
BASELINE_QTY = 20.0
UNIT = "m3"


def _gen(seed: int, days: int = 90, activity_pool=None) -> list[dict]:
    return generate_synthetic_v2_group(
        company=COMPANY,
        l6_main=L6_MAIN,
        activity_pool=activity_pool or ACTIVITY_POOL_SINGLE,
        baseline_workers=BASELINE_WORKERS,
        baseline_qty_per_day=BASELINE_QTY,
        unit=UNIT,
        days=days,
        seed=seed,
    )


# ── 룰 2 (장비대기 익일 80% 복귀) — 통계 검증 N=100 ─────────────────
def test_state_machine_equip_wait_recovery_d1_statistical():
    """룰 2: 장비대기 → 익일 정상 80% 통계 (N=100 sample, 0.7~0.9 band)."""
    recovered = 0
    total = 0
    for seed in range(100):
        rows = _gen(seed=seed, days=10)
        # rows 는 day_offset=days..1 순서 (과거 → 오늘 직전). 인덱스 i 의 다음 날 = i+1.
        for i in range(len(rows) - 1):
            if "장비대기" in rows[i]["conditions"]:
                total += 1
                if "장비대기" not in rows[i + 1]["conditions"]:
                    recovered += 1
    assert total >= 20, f"sample 부족 — total={total} (>=20 필요)"
    ratio = recovered / total
    assert 0.7 <= ratio <= 0.9, f"룰 2 익일 80% 복귀 = {ratio:.2%} (expected 0.70~0.90)"


# ── 룰 3 (장비대기 2일차 → 익일 100% 정상) ───────────────────────────
def test_state_machine_equip_wait_streak2_always_normal_next_day():
    """룰 3: 장비대기 2일차 (streak=2) → 익일 incident=정상 100% (spec §4.2)."""
    total = 0
    next_normal = 0
    for seed in range(200):
        rows = _gen(seed=seed, days=90)
        for i in range(1, len(rows) - 1):
            # streak=2 인 i 의 조건: i-1, i 둘 다 장비대기
            if "장비대기" in rows[i - 1]["conditions"] and "장비대기" in rows[i]["conditions"]:
                total += 1
                if "장비대기" not in rows[i + 1]["conditions"]:
                    next_normal += 1
    assert total >= 20, f"sample 부족 — total={total}"
    ratio = next_normal / total
    # 룰 3 은 100% (spec §4.2: incident=정상 강제). 1.0 band 엄격 검증.
    assert ratio == 1.0, f"룰 3 장비대기 2일차 → 익일 정상 = {ratio:.3f} (expected 1.000)"


# ── 룰 4 (우천 연속 2일 → 3일차 ×1.10 만회) ─────────────────────────
def test_state_machine_rain_streak_compensation_statistical():
    """룰 4: 우천 streak≥2 → 3일차 (비-우천) qty 평균이 정상 대비 +5% 이상."""
    qty_after_2day_rain_clear: list[float] = []
    qty_after_no_rain_clear: list[float] = []
    for seed in range(300):
        rows = _gen(seed=seed, days=90)
        for i in range(2, len(rows)):
            # 측정 대상: 비-우천 + 정상 incident
            if "우천" in rows[i]["conditions"]:
                continue
            if any(k in rows[i]["conditions"] for k in ["장비대기", "자재미입고", "야간연장", "돌관"]):
                continue
            prev_rain = "우천" in rows[i - 1]["conditions"]
            prev2_rain = "우천" in rows[i - 2]["conditions"]
            if prev_rain and prev2_rain:
                qty_after_2day_rain_clear.append(rows[i]["today_qty"])
            elif not prev_rain:
                qty_after_no_rain_clear.append(rows[i]["today_qty"])
    assert len(qty_after_2day_rain_clear) >= 50, (
        f"우천 streak sample 부족 — N={len(qty_after_2day_rain_clear)}"
    )
    assert len(qty_after_no_rain_clear) >= 100, f"normal sample 부족 — N={len(qty_after_no_rain_clear)}"
    avg_streak = statistics.mean(qty_after_2day_rain_clear)
    avg_normal = statistics.mean(qty_after_no_rain_clear)
    ratio = avg_streak / avg_normal
    # 1.10 만회 — 1.05~1.15 band (random noise 고려)
    assert 1.05 <= ratio <= 1.15, f"룰 4 우천 streak 만회 ratio = {ratio:.3f} (expected 1.05~1.15)"


# ── 룰 5 (자재미입고 → 익일 50% 정상 복귀) ──────────────────────────
def test_state_machine_material_recovery_d1_statistical():
    """룰 5: 자재미입고 → 익일 정상 50% 통계 (0.4~0.6 band)."""
    total = 0
    recovered = 0
    for seed in range(200):
        rows = _gen(seed=seed, days=90)
        for i in range(len(rows) - 1):
            if "자재미입고" in rows[i]["conditions"]:
                total += 1
                if "자재미입고" not in rows[i + 1]["conditions"]:
                    recovered += 1
    assert total >= 100, f"sample 부족 — total={total}"
    ratio = recovered / total
    assert 0.4 <= ratio <= 0.6, f"룰 5 자재미입고 익일 복귀 = {ratio:.2%} (expected 0.40~0.60)"


# ── 룰 6 (야간연장 → 익일 fatigue ×0.90) ─────────────────────────────
def test_state_machine_night_fatigue_next_day_statistical():
    """룰 6: 야간연장 → 익일 정상 qty 평균이 normal 대비 ~0.90 (0.83~0.97 band)."""
    qty_after_night: list[float] = []
    qty_after_normal: list[float] = []
    for seed in range(300):
        rows = _gen(seed=seed, days=90)
        for i in range(len(rows) - 1):
            next_cond = rows[i + 1]["conditions"]
            # 측정 대상: 익일이 정상 incident (fatigue 효과 격리)
            if any(k in next_cond for k in ["장비대기", "자재미입고", "야간연장", "돌관"]):
                continue
            if "야간연장" in rows[i]["conditions"]:
                qty_after_night.append(rows[i + 1]["today_qty"])
            elif not any(k in rows[i]["conditions"] for k in ["장비대기", "자재미입고", "야간연장", "돌관"]):
                qty_after_normal.append(rows[i + 1]["today_qty"])
    assert len(qty_after_night) >= 50, f"야간연장 sample 부족 — N={len(qty_after_night)}"
    avg_night = statistics.mean(qty_after_night)
    avg_normal = statistics.mean(qty_after_normal)
    ratio = avg_night / avg_normal
    # spec: ×0.90 — 0.83~0.97 band (weather random noise + uniform delta 고려)
    assert 0.83 <= ratio <= 0.97, f"룰 6 야간연장 익일 fatigue ratio = {ratio:.3f} (expected 0.83~0.97)"


# ── 룰 7 (돌관 → workers ×1.3 spike, 익일 효과 없음) ───────────────
def test_state_machine_dolgwan_worker_spike_statistical():
    """룰 7: 돌관 incident 시 assigned_workers 평균이 baseline × 1.3 ± noise."""
    dolgwan_workers: list[float] = []
    normal_workers: list[float] = []
    for seed in range(300):
        rows = _gen(seed=seed, days=90)
        for r in rows:
            if "돌관" in r["conditions"]:
                dolgwan_workers.append(r["assigned_workers"])
            elif not any(k in r["conditions"] for k in ["장비대기", "자재미입고", "야간연장", "돌관"]):
                normal_workers.append(r["assigned_workers"])
    assert len(dolgwan_workers) >= 100, f"돌관 sample 부족 — N={len(dolgwan_workers)}"
    avg_dolgwan = statistics.mean(dolgwan_workers)
    avg_normal = statistics.mean(normal_workers)
    ratio = avg_dolgwan / avg_normal
    # spec: × 1.3 spike — 1.20~1.40 band (gauss noise 고려)
    assert 1.20 <= ratio <= 1.40, f"룰 7 돌관 workers spike ratio = {ratio:.3f} (expected 1.20~1.40)"


# ── work_content 단순 활동명 (결정 #22) ──────────────────────────────
def test_work_content_is_simple_activity_name():
    """work_content 는 activity_pool 의 원소 그대로 — 조건 텍스트 조합 X."""
    pool = ["기초공사 : 거푸집 공사", "RC Wall : 철근 조립"]
    rows = _gen(seed=42, days=30, activity_pool=pool)
    for r in rows:
        assert r["work_content"] in pool, f"work_content '{r['work_content']}' 가 pool 밖"
        assert " / " not in r["work_content"], "work_content 는 단순 활동명, 조건 텍스트 조합 X"


# ── assigned_workers ±10% noise (돌관 X 일 때) ─────────────────────
def test_assigned_workers_within_10pct_noise_when_not_dolgwan():
    """돌관 X row 의 workers 가 baseline ±10% 안에 들어야 함 (gauss σ=0.1, ±3σ ~ ±30%)."""
    # gauss σ=0.1 — ±10% 안에 ~68% 만 들어감. 평균이 ±2% 안인지 통계로 검증.
    rows = _gen(seed=42, days=90)
    ratios: list[float] = []
    for r in rows:
        if "돌관" in r["conditions"]:
            continue
        ratios.append(r["assigned_workers"] / BASELINE_WORKERS)
    assert len(ratios) >= 50, f"sample 부족 — N={len(ratios)}"
    avg_ratio = statistics.mean(ratios)
    stdev_ratio = statistics.stdev(ratios)
    # 평균 1.0 ± 0.05, stdev 0.05~0.15 (gauss σ=0.1 근처)
    assert 0.95 <= avg_ratio <= 1.05, f"workers/baseline 평균 = {avg_ratio:.3f} (expected ~1.0)"
    assert 0.05 <= stdev_ratio <= 0.15, f"workers/baseline stdev = {stdev_ratio:.3f} (expected ~0.10)"


# ── conditions comma-joined str (결정 #19) ────────────────────────
def test_conditions_is_comma_joined_str():
    """conditions 는 str (atomizer 통일). comma-joined, 각 부분 trimmed."""
    rows = _gen(seed=42, days=30)
    for r in rows:
        assert isinstance(r["conditions"], str), f"conditions type={type(r['conditions'])} (expected str)"
        if "," in r["conditions"]:
            parts = r["conditions"].split(",")
            assert all(p.strip() == p for p in parts), "각 부분 trimmed"


# ── seed 재현성 (Hard rule: random.Random instance) ───────────────
def test_seed_reproducibility():
    """same seed → same rows (global random 오염 없음)."""
    rows1 = _gen(seed=42, days=30)
    rows2 = _gen(seed=42, days=30)
    assert rows1 == rows2, "same seed 같은 결과"
    # 다른 seed → 다른 결과 (sanity)
    rows3 = _gen(seed=43, days=30)
    assert rows1 != rows3, "다른 seed 다른 결과"
