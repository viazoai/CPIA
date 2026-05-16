"""synthetic v2 state machine — 시계열 회복 룰 7건 (spec §4.1 + §4.2).

룰 enumerate (spec §4.1 표):
1. 장비대기 1일차: productivity × (1 - random[0.20, 0.35])
2. 장비대기 1일차 → 익일: 80% 정상 복귀 / 20% 2일차 지속
3. 장비대기 2일차 → 익일: 30% 만회 (× 1.10) / 70% 정상
4. 우천 연속 2일 → 3일차: × 1.10 만회
5. 자재미입고 → 익일: 50% 정상 복귀 / 50% 2일차 지속
6. 야간연장 → 익일: × 0.90 (인원 피로 누적)
7. 돌관 (인원 spike) 당일: productivity × 0.85 효과 (혼잡, -10~20%) + assigned_workers × 1.3 spike.
   익일 효과 없음 (last_incident="돌관" 다음 turn 은 정상 random 분기).

work_content (결정 #22): activity_pool 단순 활동명 (조건 텍스트 조합 X).
conditions (결정 #19): comma-joined str (atomizer 패턴 통일).
seed (Hard rule): random.Random(seed) instance 만 사용 — 전역 random 금지.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Optional


def generate_synthetic_v2_group(
    company: str,
    l6_main: str,
    activity_pool: list[str],
    baseline_workers: float,
    baseline_qty_per_day: float,
    unit: str,
    days: int = 90,
    seed: int = 42,
    reference_date: Optional[date] = None,
) -> list[dict]:
    """state machine — 매일 conditions / workers / qty / work_content 결정.

    spec §4.2 의사코드 그대로 구현. seed 결정성 보장 (random.Random instance).

    Returns: list of dict — Chroma upsert ready row, atomizer 호환 conditions str.
        각 row 키:
            date (ISO str), company, l6_main, unit,
            today_qty (float, ≥ 0), assigned_workers (float, ≥ 0),
            conditions (str, comma-joined), work_content (str),
            worker_source ("synthetic_v2").
    """
    if reference_date is None:
        reference_date = date(2025, 9, 25)

    rng = random.Random(seed)
    state = {
        "last_incident": None,  # type: ignore[dict-item]
        "rain_streak": 0,
        "equip_wait_streak": 0,
    }
    rows: list[dict] = []

    for day_offset in range(days, 0, -1):
        target_date = reference_date - timedelta(days=day_offset)

        # ── incident 결정 (룰 2/3/5 + 룰 6 익일 피로 분기) ──
        compensation = 1.0
        fatigue_factor = 1.0

        if state["last_incident"] == "장비대기" and state["equip_wait_streak"] == 1:
            # 룰 2: 익일 80% 복귀 / 20% 2일차 지속
            if rng.random() < 0.8:
                incident = "정상"
                state["equip_wait_streak"] = 0
            else:
                incident = "장비대기"
                state["equip_wait_streak"] = 2
        elif state["last_incident"] == "장비대기" and state["equip_wait_streak"] == 2:
            # 룰 3: 2일차 → 익일 정상 (만회 30% × 1.10 / 정상 70%)
            incident = "정상"
            state["equip_wait_streak"] = 0
            compensation = 1.10 if rng.random() < 0.3 else 1.0
        elif state["last_incident"] == "자재미입고":
            # 룰 5: 익일 50% 복귀 / 50% 지속
            incident = "정상" if rng.random() < 0.5 else "자재미입고"
        elif state["last_incident"] == "야간연장":
            # 룰 6: 익일 새 random + fatigue × 0.90
            incident = rng.choices(
                ["정상", "장비대기", "자재미입고", "야간연장", "돌관"],
                weights=[6, 1.5, 1.5, 0.5, 0.5],
            )[0]
            fatigue_factor = 0.90
        else:
            incident = rng.choices(
                ["정상", "장비대기", "자재미입고", "야간연장", "돌관"],
                weights=[6, 1.5, 1.5, 0.5, 0.5],
            )[0]

        # 장비대기 신규 시작 → streak=1
        if incident == "장비대기" and state["last_incident"] != "장비대기":
            state["equip_wait_streak"] = 1

        # ── weather + rain streak ──
        weather = rng.choices(["맑음", "우천", "흐림"], weights=[6, 2, 2])[0]
        rain_streak_compensation = 1.10 if (state["rain_streak"] >= 2 and weather != "우천") else 1.0

        # ── productivity delta 계산 ──
        delta = 0.0
        if weather == "우천":
            delta -= rng.uniform(0.15, 0.25)
        if incident == "장비대기":
            delta -= rng.uniform(0.20, 0.35)  # 룰 1
        elif incident == "자재미입고":
            delta -= rng.uniform(0.10, 0.20)
        elif incident == "돌관":
            delta -= rng.uniform(0.10, 0.20)  # 룰 7: 혼잡 -10~20%
        delta += rng.uniform(-0.05, 0.05)

        today_qty = round(
            baseline_qty_per_day * (1 + delta) * rain_streak_compensation * compensation * fatigue_factor,
            1,
        )
        # 안전 가드 — 음수 방지 (극단 delta 시)
        if today_qty < 0:
            today_qty = 0.0

        # ── assigned_workers (룰 7 돌관 spike × 1.3) ──
        worker_multiplier = 1.3 if incident == "돌관" else 1.0
        assigned_workers = round(
            baseline_workers * worker_multiplier * rng.gauss(1.0, 0.1),
            1,
        )
        if assigned_workers < 0:
            assigned_workers = 0.0

        # ── work_content — 단순 활동명 (결정 #22) ──
        work_content = rng.choice(activity_pool)

        # ── conditions list → comma-joined str (결정 #19) ──
        conditions_list = [weather] + ([incident] if incident != "정상" else [])
        conditions_str = ",".join(conditions_list)

        rows.append(
            {
                "date": target_date.isoformat(),
                "company": company,
                "l6_main": l6_main,
                "unit": unit,
                "today_qty": today_qty,
                "assigned_workers": assigned_workers,
                "conditions": conditions_str,
                "work_content": work_content,
                "worker_source": "synthetic_v2",
            }
        )

        # ── state 업데이트 ──
        state["last_incident"] = incident
        state["rain_streak"] = state["rain_streak"] + 1 if weather == "우천" else 0

    return rows
