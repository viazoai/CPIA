"""업체명 정규화 매핑 적용 — 9-25 1일치 prototype.

- 마스터 슬래시 통일 (영구, 전체 row): 신성/케이엔솔->신성, 태우/광건->태우
- 9-25 mapper_activities + mapped_history 의 company 변형 -> canonical
- 적용 전/후 (company, l6) L6 정합도 측정 보고
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import asyncpg

DSN = os.environ.get(
    "POSTGRES_URL",
    "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia",
)
MAPPING_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "company_normalize.json"
)
proto_date_STR = "2025-09-25"

# 마스터 슬래시 통일 (사용자 결정 13번, 전체 row 적용)
SLASH_PAIRS: dict[str, str] = {
    "신성/케이엔솔": "신성",
    "태우/광건": "태우",
}


async def measure(conn: asyncpg.Connection, when) -> dict[str, object]:
    row = await conn.fetchrow(
        """
        WITH ma AS (
            SELECT DISTINCT pr.site_id, ma.company, ma.l6_main
            FROM mapper_activities ma
            JOIN pipeline_runs pr USING (run_id)
            WHERE ma.report_date = $1
              AND ma.l6_main IN (
                  SELECT DISTINCT l6_main FROM activity_master
                  WHERE l5_disc IN ('건축','토목')
              )
        ), am AS (
            SELECT DISTINCT site_id, company, l6_main
            FROM activity_master WHERE l5_disc IN ('건축','토목')
        )
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE EXISTS (
                SELECT 1 FROM am
                WHERE am.site_id = ma.site_id
                  AND am.company = ma.company
                  AND am.l6_main = ma.l6_main
            )) AS matched
        FROM ma
        """,
        when,
    )
    total = row["total"] or 0
    matched = row["matched"] or 0
    pct = (matched / total * 100) if total else 0
    return {"total": total, "matched": matched, "pct": round(pct, 1)}


async def main() -> None:
    from datetime import date as _date  # ruff F401 회피 (runtime import)
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date", default=None, help="YYYY-MM-DD 단일 일자 (기본 2025-09-25)"
    )
    parser.add_argument("--all-dates", action="store_true", help="530일 전체 적용")
    args = parser.parse_args()

    proto_date = (
        None if args.all_dates else _date.fromisoformat(args.date or proto_date_STR)
    )
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))

    # 매핑 dict 구성 (변형 -> canonical, exact 제외)
    canon: dict[str, str] = {}
    for v, info in data["matched_fuzzy"].items():
        if info["canonical"] != v:
            canon[v] = info["canonical"]

    print(f"매핑 적용 대상: fuzzy {len(canon)}건 (exact 28건 변경 없음)")
    print(f"슬래시 통일 (전체 row): {SLASH_PAIRS}")
    print(f"적용 범위: {'530일 전체' if args.all_dates else proto_date}")

    conn = await asyncpg.connect(DSN)
    try:
        if not args.all_dates:
            before = await measure(conn, proto_date)
            print(f"\nBEFORE — (company, l6) 정합도: {before}")

        # mapped_history 는 unique 충돌 -> Task 4 (apply_mapped_history_normalize.py) 가 처리.
        # 여기서는 mapper_activities + activity_master 만.
        async with conn.transaction():
            # 1) 슬래시 통일 (전체 row, 영구)
            for slashed, first in SLASH_PAIRS.items():
                for tbl in ("activity_master", "mapper_activities"):
                    await conn.execute(
                        f"UPDATE {tbl} SET company = $1 WHERE company = $2",
                        first,
                        slashed,
                    )

            # 2) fuzzy 매핑 적용
            for variant, canonical in canon.items():
                if args.all_dates:
                    await conn.execute(
                        "UPDATE mapper_activities SET company = $1 "
                        "WHERE company = $2 AND company <> $1",
                        canonical,
                        variant,
                    )
                else:
                    await conn.execute(
                        "UPDATE mapper_activities SET company = $1 "
                        "WHERE report_date = $2::date AND company = $3 AND company <> $1",
                        canonical,
                        proto_date,
                        variant,
                    )

        if args.all_dates:
            # 530일 전체 — 표본 일자 3건 measure
            for d_str in ("2024-04-15", "2025-09-25", "2026-04-30"):
                d = _date.fromisoformat(d_str)
                m = await measure(conn, d)
                print(f"{d_str} — 정합도: {m}")
        else:
            after = await measure(conn, proto_date)
            print(f"AFTER  — (company, l6) 정합도: {after}")
            delta_pct = after["pct"] - before["pct"]
            print(
                f"\n변화: matched {before['matched']} -> {after['matched']} "
                f"({before['pct']}% -> {after['pct']}%, 델타 +{delta_pct:.1f}%p)"
            )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
