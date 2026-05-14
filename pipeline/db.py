"""PostgreSQL 클라이언트 — activity_master 조회 (BP filter + Plan 조회).

Spec: docs/schema/postgres.md §2 + docs/schema/mapping-layer.md §3.1
"""

from __future__ import annotations

from typing import Any

import asyncpg


class PGClient:
    """asyncpg connection pool 래퍼."""

    def __init__(self, dsn: str, min_size: int = 1, max_size: int = 5) -> None:
        self.dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._min_size = min_size
        self._max_size = max_size

    async def connect(self) -> None:
        """Connection pool 초기화."""
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=self._min_size,
            max_size=self._max_size,
        )

    async def close(self) -> None:
        """Connection pool 정리."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def fetch_bp_candidates(self, company: str) -> list[dict[str, Any]]:
        """BP filter — 그 BP사의 (WA, L6) 후보 풀.

        활동 마스터에서 company 가 일치하는 row 의 DISTINCT (wa, l6_main) 반환.
        """
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT wa, l6_main
                FROM activity_master
                WHERE company = $1
                ORDER BY wa, l6_main
                """,
                company,
            )
            return [dict(r) for r in rows]

    async def fetch_activity(self, wbs_activity_id: str) -> dict[str, Any] | None:
        """ActivityID → Plan 값 + 메타."""
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT wbs_activity_id, wa, l5_disc, l6_main, l7_sub, l7_5_activity,
                       sub_work_area, company, unit,
                       plan_total_qty, plan_mh_rev2, plan_start, plan_finish
                FROM activity_master
                WHERE wbs_activity_id = $1
                """,
                wbs_activity_id,
            )
            return dict(row) if row else None
