"""PostgreSQL 클라이언트 — activity_master 조회 (BP filter + Plan 조회).

Spec: docs/schema/postgres.md §2 + docs/schema/mapping-layer.md §3.1
"""

from __future__ import annotations

import uuid
from datetime import date as _date
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

    async def fetch_l6_plan_mh_map(
        self,
        company: str,
        l6_list: list[str],
    ) -> dict[str, int]:
        """단일 GROUP BY 쿼리로 (company) 의 여러 l6 plan_mh 합을 한 번에 조회.

        Spec 3.2 — _prorate_mh() 의 N+1 회피용.
        빈 l6_list / 미등록 BP사 -> {} 반환.
        """
        if not l6_list:
            return {}
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT l6_main, sum(plan_mh_rev2) AS s
                FROM activity_master
                WHERE company = $1 AND l6_main = ANY($2::text[])
                GROUP BY l6_main
                """,
                company,
                l6_list,
            )
        return {r["l6_main"]: int(r["s"] or 0) for r in rows}

    async def insert_pipeline_run(
        self,
        run_id: uuid.UUID,
        site_id: str,
        date: str,
        status: str = "running",
    ) -> None:
        """integration test fixture 용 — pipeline_runs row INSERT.

        Spec 4.4 — Atomizer 가 INSERT 책임 X (fixture / FastAPI 가 사전 INSERT).
        """
        assert self._pool is not None, "connect() 미호출"
        # ISO 'YYYY-MM-DD' 문자열은 asyncpg 가 date 컬럼에 직접 바인딩 못 함 -> date 변환.
        report_date = _date.fromisoformat(date) if isinstance(date, str) else date
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO pipeline_runs (run_id, site_id, report_date, status) VALUES ($1, $2, $3, $4)",
                run_id,
                site_id,
                report_date,
                status,
            )

    async def delete_pipeline_run(self, run_id: uuid.UUID) -> None:
        """integration test fixture cleanup 용."""
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM pipeline_runs WHERE run_id=$1", run_id)

    async def update_run_atomized_count(
        self,
        run_id: uuid.UUID,
        count: int,
    ) -> None:
        """Atomizer 종료 시 호출. pipeline_runs row 가 사전 INSERT 되어 있어야 함.

        Spec 4.4 — silent no-op 방지를 위해 affected row 검증.
        0 row 면 RuntimeError -> integration test fixture 의 INSERT 빠짐 신호.
        """
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE pipeline_runs SET atomized_count = $1, current_node = 'atomizer' WHERE run_id = $2",
                count,
                run_id,
            )
        if result.endswith(" 0"):
            raise RuntimeError(
                f"pipeline_runs(run_id={run_id}) 미존재 — fixture 설정 확인",
            )
