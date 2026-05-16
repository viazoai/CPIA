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

CLI: spec §4.5 (BASELINE_WORKERS 27 그룹 — downstream §3.4) + §4.7 (810 DROP) + §4.8 (baseline 재산출).
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Optional

# spec §3.4 — 9/25 작업일보 BP사별 총 인원 (시트1 today_incr 합)
# 출처: /tmp/cpia_flow_sim.py 실 호출 결과
_BP_TOTAL: dict[str, int] = {
    "남웅건설": 88,
    "세보엠이씨": 1387,
    "창원기전": 372,
}


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


async def _main_cli() -> None:
    """CLI entry — uv run python -m pipeline.agents.optimizer.synthetic_v2.

    spec §4.5 + §4.7 + §4.8 — 27 (company, l6_main) 그룹 × 90일 = ~2,430 Chroma row.

    절차:
        1. activity_master 에서 27 그룹 + 각 그룹의 main_unit + activity_pool + plan_total_qty 조회
        2. BP사 총 인원 (spec §3.4) 을 (company, l6_main) 별 Σplan_mh 비율로 분배 = baseline_workers
        3. baseline_qty_per_day = plan_total_qty (main_unit) / days
        4. 각 그룹별 generate_synthetic_v2_group 호출 → 90일 row 생성
        5. Chroma daily_activities 에서 worker_source="synthetic" row DROP (810 → 0)
           — mh_prorated (11) 와 synthetic_v2 (다음 적재) 는 보존
        6. Azure embedding (text-embedding-3-small 1536d) batch 호출 + Chroma upsert
        7. 적재 row 수 출력
    """
    import argparse
    import hashlib
    import os

    from openai import AzureOpenAI

    from pipeline.chroma_client import ChromaClient
    from pipeline.db import PGClient

    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-date", default="2025-09-25")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    ref = date.fromisoformat(args.reference_date)

    # ── Step 1: PG 조회 — 27 그룹 main_unit + activity_pool + total_qty + total_mh ──
    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        # main_unit = max plan_total_qty 의 unit (per (company, l6_main))
        group_rows = await pg._pool.fetch(
            """
            WITH g AS (
              SELECT company, l6_main, unit,
                     SUM(plan_total_qty)::float AS total_qty_unit,
                     SUM(plan_mh_rev2) AS total_mh_unit
              FROM activity_master
              WHERE company IS NOT NULL AND l6_main IS NOT NULL AND unit IS NOT NULL
              GROUP BY company, l6_main, unit
            )
            SELECT DISTINCT ON (company, l6_main)
                   company, l6_main, unit AS main_unit, total_qty_unit AS total_qty
            FROM g
            ORDER BY company, l6_main, total_qty_unit DESC NULLS LAST
            """
        )
        # Σplan_mh per (company, l6_main) — 모든 unit 합산
        mh_rows = await pg._pool.fetch(
            """
            SELECT company, l6_main, SUM(plan_mh_rev2) AS total_mh
            FROM activity_master
            WHERE company IS NOT NULL AND l6_main IS NOT NULL
            GROUP BY company, l6_main
            """
        )
        # activity_pool — distinct l7_5_activity per (company, l6_main)
        act_rows = await pg._pool.fetch(
            """
            SELECT company, l6_main, l7_5_activity
            FROM activity_master
            WHERE company IS NOT NULL
              AND l6_main IS NOT NULL
              AND l7_5_activity IS NOT NULL
            """
        )
    finally:
        await pg.close()

    mh_lookup: dict[tuple[str, str], int] = {
        (r["company"], r["l6_main"]): int(r["total_mh"] or 0) for r in mh_rows
    }
    pool_lookup: dict[tuple[str, str], list[str]] = {}
    for r in act_rows:
        key = (r["company"], r["l6_main"])
        pool_lookup.setdefault(key, []).append(r["l7_5_activity"])
    # dedup pool — 같은 l7_5_activity 가 여러 row 있을 수 있음
    for k, lst in pool_lookup.items():
        pool_lookup[k] = sorted(set(lst))

    # ── Step 2: baseline_workers — _prorate_mh 와 동일 알고리즘, 27 그룹 전체로 확장 ──
    # company 별 Σ(all mapped l6 mh) 합 → bp_total × (l6_mh / sum_mh) = baseline_workers
    sum_mh_per_co: dict[str, int] = {}
    for (co, _l6), mh in mh_lookup.items():
        sum_mh_per_co[co] = sum_mh_per_co.get(co, 0) + mh

    # ── Step 3~4: 27 그룹 generate ──
    docs: list[str] = []
    metas: list[dict] = []
    ids: list[str] = []
    for r in group_rows:
        company = r["company"]
        l6_main = r["l6_main"]
        main_unit = r["main_unit"]
        total_qty = float(r["total_qty"] or 0.0)
        key = (company, l6_main)

        bp_total = _BP_TOTAL.get(company, 0)
        sum_mh = sum_mh_per_co.get(company, 0)
        l6_mh = mh_lookup.get(key, 0)
        if bp_total == 0 or sum_mh == 0 or l6_mh == 0:
            baseline_workers = 0.0
        else:
            baseline_workers = bp_total * l6_mh / sum_mh
        baseline_qty_per_day = total_qty / max(args.days, 1)
        activity_pool = pool_lookup.get(key, [f"{l6_main} 작업"])
        if not activity_pool:
            activity_pool = [f"{l6_main} 작업"]

        rows = generate_synthetic_v2_group(
            company=company,
            l6_main=l6_main,
            activity_pool=activity_pool,
            baseline_workers=baseline_workers,
            baseline_qty_per_day=baseline_qty_per_day,
            unit=main_unit,
            days=args.days,
            seed=args.seed,
            reference_date=ref,
        )
        for row in rows:
            doc_id_raw = f"synthetic_v2|{row['date']}|{row['company']}|{row['l6_main']}|{row['work_content']}"
            doc_id = hashlib.sha256(doc_id_raw.encode("utf-8")).hexdigest()[:16]
            ids.append(doc_id)
            docs.append(row["work_content"])
            metas.append(
                {
                    "date": row["date"],
                    "run_id": "synthetic_v2",
                    "company": row["company"],
                    "l5_disc": "",
                    "l6_main": row["l6_main"],
                    "wa": "",
                    "unit": row["unit"],
                    "today_qty": float(row["today_qty"]),
                    "assigned_workers": float(row["assigned_workers"]),
                    "worker_source": row["worker_source"],
                    "mapping_conf": 0.85,
                    "conditions": row["conditions"],
                }
            )

    # dedup ids (within-batch — 같은 (date, company, l6_main, work_content) 충돌 시 후 index 우선)
    seen: dict[str, int] = {}
    for idx, doc_id in enumerate(ids):
        seen[doc_id] = idx
    final_ids = list(seen.keys())
    final_docs = [docs[seen[i]] for i in final_ids]
    final_metas = [metas[seen[i]] for i in final_ids]

    # ── Step 5: 현 synthetic 810 row DROP — mh_prorated + synthetic_v2 보존 ──
    chroma = ChromaClient(
        host=os.environ["CHROMA_HOST"],
        port=int(os.environ.get("CHROMA_PORT", "8000")),
        ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )
    coll = chroma.get_or_create_daily_activities()
    coll.delete(where={"worker_source": "synthetic"})

    # ── Step 6: Azure embedding batch + Chroma upsert ──
    azure = AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    )
    embeddings: list[list[float]] = []
    batch = 16
    for i in range(0, len(final_docs), batch):
        chunk = final_docs[i : i + batch]
        resp = azure.embeddings.create(
            model=os.environ["EMBEDDING_MODEL"],
            input=chunk,
        )
        embeddings.extend([d.embedding for d in resp.data])

    coll.upsert(
        ids=final_ids,
        embeddings=embeddings,
        documents=final_docs,
        metadatas=final_metas,
    )

    print(f'OK upserted {len(final_ids)} rows to Chroma daily_activities. worker_source="synthetic_v2".')


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main_cli())
