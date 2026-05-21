"""Step C-a: mapper_activities 의 9-25 row 에 L7.5 매핑 결과 적용 + 마스터 갈아엎기.

사용자 결정 (2026-05-21):
- threshold 제거 — 207건 모두 매핑 (low score 도 포함)
- 단위/plan_total_qty/plan_mh 마스터의 매칭 L7.5 값으로 덮어쓰기
- today_qty (오늘 실적) 는 일보 그대로

선행 조건:
- prototype_l7_5_resolved 에 207 row 적재됨 (scripts/resolve_l7_5_prototype.py 결과)
- mapper_activities 에 l7_5_activity 컬럼 추가 (ALTER)
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

DSN = os.environ.get(
    "POSTGRES_URL",
    "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia",
)


async def main() -> None:
    pg = await asyncpg.connect(DSN)
    try:
        # 1) mapper_activities 에 l7_5_activity 컬럼 추가 (없으면)
        await pg.execute(
            "ALTER TABLE mapper_activities ADD COLUMN IF NOT EXISTS l7_5_activity text"
        )
        print("ALTER: mapper_activities.l7_5_activity 컬럼 OK")

        # 2) prototype_l7_5_resolved 와 JOIN 해서 갈아엎기 — 9-25 limited
        result = await pg.execute(
            """
            UPDATE mapper_activities ma
            SET l7_5_activity = r.matched_l7_5_activity,
                unit = COALESCE(r.matched_unit, ma.unit),
                plan_total_qty = COALESCE(r.matched_plan_total_qty, ma.plan_total_qty),
                plan_mh = COALESCE(r.matched_plan_mh, ma.plan_mh)
            FROM prototype_l7_5_resolved r
            WHERE ma.id = r.mapper_id
              AND r.matched_l7_5_activity IS NOT NULL
            """
        )
        print(f"UPDATE mapper_activities: {result}")

        # 3) 검증 — 9-25 mapper rows 의 l7_5 분포
        row = await pg.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE l7_5_activity IS NOT NULL) AS with_l75,
                   COUNT(DISTINCT l7_5_activity) AS distinct_l75
            FROM mapper_activities
            WHERE report_date = '2025-09-25'::date
            """
        )
        print(
            f"\n9-25 mapper_activities: total={row['total']} "
            f"with_l7_5={row['with_l75']} distinct_l7_5={row['distinct_l75']}"
        )

        # 4) sample 확인 — 갈아엎기 결과
        samples = await pg.fetch(
            """
            SELECT company, l6_main, l7_5_activity,
                   unit, today_qty, plan_total_qty, plan_mh, assigned_workers
            FROM mapper_activities
            WHERE report_date = '2025-09-25'::date
              AND l7_5_activity IS NOT NULL
              AND today_qty > 0
            ORDER BY company
            LIMIT 10
            """
        )
        print("\nSample (today_qty > 0):")
        for s in samples:
            print(
                f"  {s['company'][:10]:<10} | {s['l6_main'][:15]:<15} | "
                f"{(s['l7_5_activity'] or '')[:30]:<30} | "
                f"today={s['today_qty']:.1f}{s['unit']} "
                f"plan={s['plan_total_qty']} mh={s['plan_mh']} "
                f"w={s['assigned_workers']:.1f}"
            )
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
