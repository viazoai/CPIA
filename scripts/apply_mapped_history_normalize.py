"""mapped_history company 정규화 + UNIQUE 충돌 합산 + merge_log 적재.

대상: data/company_normalize.json 의 fuzzy 매핑 + SLASH 통일 2건.
- 비충돌: 단순 UPDATE
- 충돌 (같은 run_id+wa+l6_main+site_id 에 src/tgt 동시 존재):
  1) merge_log 적재 (audit 용)
  2) tgt 의 today_qty / today_assigned_workers 에 src 값 합산
  3) src DELETE
- 같은 canonical 로 향하는 여러 variant 는 순차 처리 (단일 트랜잭션).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

DSN = os.environ.get(
    "POSTGRES_URL",
    "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia",
)
MAPPING_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "company_normalize.json"
)

SLASH_PAIRS: dict[str, str] = {
    "신성/케이엔솔": "신성",
    "태우/광건": "태우",
}


async def main() -> None:
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    canon: dict[str, str] = {
        v: info["canonical"]
        for v, info in data["matched_fuzzy"].items()
        if info["canonical"] != v
    }
    canon.update(SLASH_PAIRS)

    print(f"매핑 대상: {len(canon)}건")
    for v, c in canon.items():
        print(f"  {v} -> {c}")

    pg = await asyncpg.connect(DSN)
    try:
        total_merged = 0
        total_updated = 0
        async with pg.transaction():
            for variant, canonical in canon.items():
                # 1) 충돌 row 검색 (같은 run_id+wa+l6_main+site_id 에 양쪽 동시 존재)
                conflicts = await pg.fetch(
                    """
                    SELECT mh1.id AS src,
                           mh2.id AS tgt,
                           mh1.today_qty AS src_qty,
                           mh1.today_assigned_workers AS src_workers,
                           mh1.run_id,
                           mh1.report_date,
                           mh1.site_id,
                           mh1.wa,
                           mh1.l6_main
                    FROM mapped_history mh1
                    JOIN mapped_history mh2
                      USING (run_id, wa, l6_main, site_id)
                    WHERE mh1.company = $1
                      AND mh2.company = $2
                      AND mh1.id != mh2.id
                    """,
                    variant,
                    canonical,
                )
                for c in conflicts:
                    await pg.execute(
                        """
                        INSERT INTO mapped_history_merge_log
                          (src_id, tgt_id, run_id, report_date, site_id, wa, l6_main,
                           old_company, new_company, merged_today_qty)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                        """,
                        c["src"],
                        c["tgt"],
                        c["run_id"],
                        c["report_date"],
                        c["site_id"],
                        c["wa"],
                        c["l6_main"],
                        variant,
                        canonical,
                        c["src_qty"],
                    )
                    await pg.execute(
                        """
                        UPDATE mapped_history
                        SET today_qty = COALESCE(today_qty, 0) + COALESCE($1, 0),
                            today_assigned_workers = COALESCE(today_assigned_workers, 0)
                                                   + COALESCE($2, 0)
                        WHERE id = $3
                        """,
                        c["src_qty"],
                        c["src_workers"],
                        c["tgt"],
                    )
                    await pg.execute(
                        "DELETE FROM mapped_history WHERE id = $1", c["src"]
                    )
                    total_merged += 1

                # 2) 비충돌 row 일반 UPDATE
                upd = await pg.execute(
                    "UPDATE mapped_history SET company = $1 "
                    "WHERE company = $2 AND company <> $1",
                    canonical,
                    variant,
                )
                # upd 형식: "UPDATE N"
                try:
                    n = int(upd.split()[-1])
                except (ValueError, IndexError):
                    n = 0
                total_updated += n
                print(
                    f"  {variant} -> {canonical}: merged={len(conflicts)} updated={n}"
                )

        print(f"\n총 merged: {total_merged}, 총 updated: {total_updated}")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
