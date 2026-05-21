"""mapper_activities 에 L7.5 매핑 결과 적용 + 마스터 갈아엎기 (Phase 1: 530일).

사용자 결정 (2026-05-21):
- threshold 제거 — matched_l7_5_activity 있으면 모두 매핑
- 단위/plan_total_qty/plan_mh 마스터의 매칭 L7.5 값으로 덮어쓰기
- today_qty (오늘 실적) 는 일보 그대로 (view_builder.py 가 noise 재산정 — Task 7~9)

선행 조건:
- prototype_l7_5_resolved 530일치 적재 (scripts/resolve_l7_5_prototype.py --all-dates)
"""

from __future__ import annotations

import argparse
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
    from datetime import date as _date

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date", default=None, help="단일 YYYY-MM-DD (기본 2025-09-25)"
    )
    parser.add_argument("--all-dates", action="store_true", help="530일 전체")
    args = parser.parse_args()

    pg = await asyncpg.connect(DSN)
    try:
        # 1) mapper_activities.l7_5_activity 컬럼 OK 보장
        await pg.execute(
            "ALTER TABLE mapper_activities ADD COLUMN IF NOT EXISTS l7_5_activity text"
        )
        print("ALTER: mapper_activities.l7_5_activity OK")

        # 2) 갈아엎기 — date 분기
        if args.all_dates:
            print("적용 범위: 530일 전체")
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
        else:
            proto = _date.fromisoformat(args.date or "2025-09-25")
            print(f"적용 범위: {proto}")
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
                  AND r.report_date = $1
                """,
                proto,
            )
        print(f"UPDATE mapper_activities: {result}")

        # 3) 검증 — 표본 일자 3건 (530일 모드) 또는 단일 일자
        sample_dates = (
            ["2024-04-15", "2025-09-25", "2026-04-30"]
            if args.all_dates
            else [args.date or "2025-09-25"]
        )
        print("\n=== 일자별 검증 ===")
        for d_str in sample_dates:
            row = await pg.fetchrow(
                """
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE l7_5_activity IS NOT NULL) AS with_l75,
                       COUNT(DISTINCT l7_5_activity) AS distinct_l75
                FROM mapper_activities
                WHERE report_date = $1::date
                """,
                _date.fromisoformat(d_str),
            )
            print(
                f"  {d_str}: total={row['total']} "
                f"with_l7_5={row['with_l75']} distinct={row['distinct_l75']}"
            )
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
