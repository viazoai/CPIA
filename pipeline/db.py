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

    async def fetch_bp_candidates(
        self,
        company: str,
        site_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """BP filter — 그 BP사의 (WA, L6) 후보 풀.

        활동 마스터에서 company 가 일치하는 row 의 DISTINCT (wa, l6_main) 반환.
        site_id 지정 시 해당 현장의 WBS 만 (back-compat: None = 전 현장).
        """
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as conn:
            if site_id is not None:
                rows = await conn.fetch(
                    """
                    SELECT DISTINCT wa, l6_main
                    FROM activity_master
                    WHERE company = $1 AND site_id = $2
                    ORDER BY wa, l6_main
                    """,
                    company,
                    site_id,
                )
            else:
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

    async def fetch_activity(
        self,
        wbs_activity_id: str,
        site_id: str | None = None,
    ) -> dict[str, Any] | None:
        """ActivityID → Plan 값 + 메타. site_id 지정 시 해당 현장만."""
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as conn:
            if site_id is not None:
                row = await conn.fetchrow(
                    """
                    SELECT wbs_activity_id, wa, l5_disc, l6_main, l7_sub, l7_5_activity,
                           sub_work_area, company, unit,
                           plan_total_qty, plan_mh_rev2, plan_start, plan_finish
                    FROM activity_master
                    WHERE wbs_activity_id = $1 AND site_id = $2
                    """,
                    wbs_activity_id,
                    site_id,
                )
            else:
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
        site_id: str | None = None,
    ) -> dict[str, int]:
        """단일 GROUP BY 쿼리로 (company) 의 여러 l6 plan_mh 합을 한 번에 조회.

        Spec 3.2 — _prorate_mh() 의 N+1 회피용.
        빈 l6_list / 미등록 BP사 -> {} 반환.
        site_id 지정 시 해당 현장만.
        """
        if not l6_list:
            return {}
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as conn:
            if site_id is not None:
                rows = await conn.fetch(
                    """
                    SELECT l6_main, sum(plan_mh_rev2) AS s
                    FROM activity_master
                    WHERE company = $1 AND l6_main = ANY($2::text[]) AND site_id = $3
                    GROUP BY l6_main
                    """,
                    company,
                    l6_list,
                    site_id,
                )
            else:
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

    async def assert_pipeline_run_exists(self, run_id: uuid.UUID) -> None:
        """Atomizer fail-fast 검증 — pipeline_runs row 미존재 시 즉시 RuntimeError.

        Spec 4.5 — Azure embedding + Chroma upsert 전에 row 존재 확인하여
        cost / orphan 방지. update_run_atomized_count 의 0-row RuntimeError 와
        동일 메시지 사용.
        """
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM pipeline_runs WHERE run_id=$1 LIMIT 1",
                run_id,
            )
        if row is None:
            raise RuntimeError(
                f"pipeline_runs(run_id={run_id}) 미존재 — fixture 설정 확인",
            )

    async def fetch_plan_for_group(
        self,
        company: str,
        l6_main: str,
        site_id: str | None = None,
    ) -> dict[str, Any] | None:
        """activity_master 의 (company, l6_main) candidate Σ. 미등록 시 None.

        Spec §5.2 — 2 SQL 분리로 jsonb_object_agg duplicate key 회피.
        site_id 지정 시 해당 현장만.
        """
        assert self._pool is not None, "connect() 미호출"
        site_filter = " AND site_id = $3" if site_id is not None else ""
        params_with_site = (company, l6_main, site_id) if site_id is not None else (company, l6_main)
        async with self._pool.acquire() as conn:
            qty_rows = await conn.fetch(
                f"""
                SELECT unit, SUM(plan_total_qty) AS qty
                FROM activity_master
                WHERE company = $1 AND l6_main = $2 AND unit IS NOT NULL{site_filter}
                GROUP BY unit
                """,
                *params_with_site,
            )
            if not qty_rows:
                return None
            summary = await conn.fetchrow(
                f"""
                SELECT
                    SUM(plan_mh_rev2) AS plan_mh_sum,
                    MIN(plan_start)   AS plan_start,
                    MAX(plan_finish)  AS plan_finish
                FROM activity_master
                WHERE company = $1 AND l6_main = $2{site_filter}
                """,
                *params_with_site,
            )
        return {
            "plan_total_qty_by_unit": {r["unit"]: float(r["qty"] or 0) for r in qty_rows},
            "plan_mh_sum": float(summary["plan_mh_sum"] or 0),
            "plan_start": summary["plan_start"],
            "plan_finish": summary["plan_finish"],
        }

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

    async def insert_forecast(self, row: dict) -> None:
        """forecasts 테이블 INSERT 1 row.

        Spec §5.6 + optimizer cycle Task 1 (v3.1) — 27 컬럼
        (id/created_at auto, main_unit + today_conditions Task 1 추가).
        Phase 2 — wa 컬럼 추가 (28 컬럼).
        row dict 키 = 컬럼명.
        """
        import json as _json

        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO forecasts (
                    run_id, company, l6_main,
                    today_qty_by_unit, today_assigned_workers, today_productivity,
                    plan_total_qty_by_unit, plan_mh_sum, plan_start, plan_finish, plan_mh_per_day,
                    schedule_state, window_start, window_days,
                    expected_in_window_mh, actual_in_window_mh, mh_gap, delay_days,
                    rag_n_similar, similar_cases,
                    assessment, reasoning, recovery_likelihood,
                    expected_completion, risk_level,
                    main_unit, today_conditions,
                    wa
                ) VALUES (
                    $1, $2, $3,
                    $4::jsonb, $5, $6,
                    $7::jsonb, $8, $9, $10, $11,
                    $12, $13, $14,
                    $15, $16, $17, $18,
                    $19, $20::jsonb,
                    $21, $22, $23,
                    $24, $25,
                    $26, $27,
                    $28
                )
                """,
                row["run_id"],
                row["company"],
                row["l6_main"],
                _json.dumps(row["today_qty_by_unit"]) if row.get("today_qty_by_unit") is not None else None,
                row.get("today_assigned_workers"),
                row.get("today_productivity"),
                _json.dumps(row["plan_total_qty_by_unit"])
                if row.get("plan_total_qty_by_unit") is not None
                else None,
                row.get("plan_mh_sum"),
                row.get("plan_start"),
                row.get("plan_finish"),
                row.get("plan_mh_per_day"),
                row.get("schedule_state"),
                row.get("window_start"),
                row.get("window_days"),
                row.get("expected_in_window_mh"),
                row.get("actual_in_window_mh"),
                row.get("mh_gap"),
                row.get("delay_days"),
                row.get("rag_n_similar"),
                _json.dumps(row["similar_cases"], ensure_ascii=False)
                if row.get("similar_cases") is not None
                else None,
                row.get("assessment"),
                row.get("reasoning"),
                row.get("recovery_likelihood"),
                row.get("expected_completion"),
                row.get("risk_level"),
                row.get("main_unit"),
                row.get("today_conditions"),
                row.get("wa"),
            )

    async def insert_optimizer_advice(self, row: dict) -> None:
        """optimizer_advice 테이블 INSERT 1 row — 9 컬럼 (id/created_at auto).

        Spec §9 + §3.1.1 — JSONB falsy 회피 (is not None) — cold_start 의 빈 dict/list 도 INSERT.
        """
        import json as _json

        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO optimizer_advice (
                    run_id, company, l6_main, forecast_assessment,
                    diagnosis, degradation_cases, recovery_pattern,
                    recovery_distribution, recommendations
                ) VALUES (
                    $1, $2, $3, $4,
                    $5, $6::jsonb, $7::jsonb,
                    $8::jsonb, $9::jsonb
                )
                """,
                row["run_id"],
                row["company"],
                row["l6_main"],
                row.get("forecast_assessment"),
                row.get("diagnosis"),
                _json.dumps(row["degradation_cases"], ensure_ascii=False)
                if row.get("degradation_cases") is not None
                else None,
                _json.dumps(row["recovery_pattern"]) if row.get("recovery_pattern") is not None else None,
                _json.dumps(row["recovery_distribution"])
                if row.get("recovery_distribution") is not None
                else None,
                _json.dumps(row["recommendations"], ensure_ascii=False)
                if row.get("recommendations") is not None
                else None,
            )

    async def insert_mapping_correction(
        self,
        run_id: uuid.UUID,
        report_date: _date,
        original: dict,
        corrected: dict,
    ) -> None:
        """mapping_corrections 테이블 INSERT 1 row.

        실 schema (infra/postgres/init.sql:127) = id, run_id, report_date, original
        JSONB, corrected JSONB, created_at — 6 컬럼. postgres.md §8 의 work_content/
        company/trade/correction_type top-level 컬럼은 실 PG 미반영 (drift backlog
        별 cycle). 본 cycle 은 code-only scope → original/corrected JSONB 안에
        합쳐서 박음.

        original 예: {wa, l6_main, mapping_conf, mapping_source, work_content,
                     company, trade} (Mapper 추천 + 컨텍스트)
        corrected 예: {wa, l6_main, mapping_source="user_corrected",
                      correction_type="replace"} (사용자 정정)
        """
        import json as _json

        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO mapping_corrections (run_id, report_date, original, corrected)
                VALUES ($1, $2, $3::jsonb, $4::jsonb)
                """,
                run_id,
                report_date,
                _json.dumps(original, ensure_ascii=False),
                _json.dumps(corrected, ensure_ascii=False),
            )

    async def insert_daily_report(
        self,
        run_id: uuid.UUID,
        report_date: _date,
        report_md: str,
        history_csv_row: dict | None,
        bp_name: str | None = None,
        site_id: str | None = None,
    ) -> None:
        """daily_reports 테이블 INSERT 1 row.

        site_id 가 None 이면 pipeline_runs 에서 fetch (upsert_daily_report_view_col
        의 partial unique index `(run_id, site_id, report_date) WHERE site_id IS NOT NULL`
        매칭 위해 NOT NULL 보장).
        """
        import json as _json

        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as conn:
            if site_id is None:
                row = await conn.fetchrow("SELECT site_id FROM pipeline_runs WHERE run_id=$1", run_id)
                site_id = row["site_id"] if row else None
            # 2026-05-20: UPDATE-first 패턴 — optimizer 가 먼저 daily_reports row 만들고 9 jsonb 채운 후
            # reporter 가 호출되므로 INSERT 시 UniqueViolation. upsert_daily_report_view_col 의 패턴 모방.
            hcsv = _json.dumps(history_csv_row, ensure_ascii=False) if history_csv_row is not None else None
            result = await conn.execute(
                """
                UPDATE daily_reports
                   SET bp_name = $4, report_md = $5, history_csv_row = $6::jsonb
                 WHERE run_id = $1 AND site_id = $2 AND report_date = $3
                """,
                run_id,
                site_id,
                report_date,
                bp_name,
                report_md,
                hcsv,
            )
            if result.endswith(" 0"):
                # row 없음 → INSERT (optimizer 가 view 산출 못 한 경우 새 row)
                await conn.execute(
                    """
                    INSERT INTO daily_reports (run_id, site_id, report_date, bp_name, report_md, history_csv_row)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                    """,
                    run_id,
                    site_id,
                    report_date,
                    bp_name,
                    report_md,
                    hcsv,
                )

    async def insert_mapped_history_batch(
        self,
        run_id: uuid.UUID,
        report_date: _date,
        site_id: str,
        rows: list[dict],
    ) -> None:
        """mapped_history 테이블 batch INSERT (ON CONFLICT UPDATE 멱등성).

        INSERT 대상 = wa + l6_main 둘 다 not None 인 활동 (Phase 3 결정).
        동일 (run_id, wa, l6_main, company) 재호출 시 today_qty / today_assigned_workers /
        unit 을 EXCLUDED 값으로 갱신 (마지막 값 채택 — 합계 vs 마지막 은 Phase 0 에서 합의).

        rows: [{"wa", "l6_main", "company", "today_qty", "today_assigned_workers", "unit"}, ...]
        """
        if not rows:
            return
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as con:
            await con.executemany(
                """
                INSERT INTO mapped_history
                    (run_id, report_date, site_id, wa, l6_main, company,
                     today_qty, today_assigned_workers, unit)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (run_id, wa, l6_main, company) DO UPDATE SET
                    today_qty              = EXCLUDED.today_qty,
                    today_assigned_workers = EXCLUDED.today_assigned_workers,
                    unit                   = EXCLUDED.unit
                """,
                [
                    (
                        run_id,
                        report_date,
                        site_id,
                        r["wa"],
                        r["l6_main"],
                        r["company"],
                        r["today_qty"],
                        r["today_assigned_workers"],
                        r["unit"],
                    )
                    for r in rows
                ],
            )

    async def get_pipeline_run(self, run_id: uuid.UUID) -> dict | None:
        """pipeline_runs 1 row 조회. 없으면 None."""
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as con:
            row = await con.fetchrow(
                "SELECT run_id, site_id, report_date, status, current_node"
                " FROM pipeline_runs WHERE run_id=$1",
                run_id,
            )
        return dict(row) if row else None

    async def insert_parser_report(
        self,
        run_id: uuid.UUID,
        report_date: _date,
        project: str,
        bp_summaries: list[dict],
        job_allocations: list[dict],
        equipment_allocations: list[dict],
        activity_count: int,
    ) -> None:
        """parser_reports 1 row INSERT (run_id 멱등 — ON CONFLICT DO UPDATE).

        시트1~3 (BPSummary / JobAllocation / EquipmentAllocation) 통째 jsonb.
        시트4 (activities) 는 parser_activities 에 정규화 적재 — count 만 여기 기록.
        """
        import json as _json

        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as con:
            await con.execute(
                """
                INSERT INTO parser_reports
                    (run_id, report_date, project,
                     bp_summaries, job_allocations, equipment_allocations,
                     activity_count)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7)
                ON CONFLICT (run_id) DO UPDATE SET
                    report_date           = EXCLUDED.report_date,
                    project               = EXCLUDED.project,
                    bp_summaries          = EXCLUDED.bp_summaries,
                    job_allocations       = EXCLUDED.job_allocations,
                    equipment_allocations = EXCLUDED.equipment_allocations,
                    activity_count        = EXCLUDED.activity_count
                """,
                run_id,
                report_date,
                project,
                _json.dumps(bp_summaries, ensure_ascii=False),
                _json.dumps(job_allocations, ensure_ascii=False),
                _json.dumps(equipment_allocations, ensure_ascii=False),
                activity_count,
            )

    async def insert_parser_activities_batch(
        self,
        run_id: uuid.UUID,
        report_date: _date,
        activities: list[dict],
    ) -> None:
        """parser_activities batch INSERT — Activity[] (Mapper 호출 전 raw).

        (run_id, idx) 멱등. activities idx = list index (Activity[] 순서).
        2026-05-19 확장: zone/bp_code/scope/누적/F%/잔여/G%/note/work_location/WBS path.
        """
        if not activities:
            return
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as con:
            await con.executemany(
                """
                INSERT INTO parser_activities
                    (run_id, report_date, idx,
                     l5_disc, trade, company, unit,
                     today_qty, work_content, plan_total_qty,
                     zone, bp_code, scope,
                     yesterday_cum_qty, today_cum_qty,
                     progress_percent, remaining_qty, remaining_percent,
                     note, work_location_code,
                     wbs_mid_name, wbs_sub_name, wbs_detail_name)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                        $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                        $21, $22, $23)
                ON CONFLICT (run_id, idx) DO UPDATE SET
                    l5_disc            = EXCLUDED.l5_disc,
                    trade              = EXCLUDED.trade,
                    company            = EXCLUDED.company,
                    unit               = EXCLUDED.unit,
                    today_qty          = EXCLUDED.today_qty,
                    work_content       = EXCLUDED.work_content,
                    plan_total_qty     = EXCLUDED.plan_total_qty,
                    zone               = EXCLUDED.zone,
                    bp_code            = EXCLUDED.bp_code,
                    scope              = EXCLUDED.scope,
                    yesterday_cum_qty  = EXCLUDED.yesterday_cum_qty,
                    today_cum_qty      = EXCLUDED.today_cum_qty,
                    progress_percent   = EXCLUDED.progress_percent,
                    remaining_qty      = EXCLUDED.remaining_qty,
                    remaining_percent  = EXCLUDED.remaining_percent,
                    note               = EXCLUDED.note,
                    work_location_code = EXCLUDED.work_location_code,
                    wbs_mid_name       = EXCLUDED.wbs_mid_name,
                    wbs_sub_name       = EXCLUDED.wbs_sub_name,
                    wbs_detail_name    = EXCLUDED.wbs_detail_name
                """,
                [
                    (
                        run_id,
                        report_date,
                        i,
                        a.get("l5_disc"),
                        a.get("trade"),
                        a["company"],
                        a.get("unit"),
                        a.get("today_qty"),
                        a.get("work_content"),
                        a.get("plan_total_qty"),
                        a.get("zone"),
                        a.get("bp_code"),
                        a.get("scope"),
                        a.get("yesterday_cum_qty"),
                        a.get("today_cum_qty"),
                        a.get("progress_percent"),
                        a.get("remaining_qty"),
                        a.get("remaining_percent"),
                        a.get("note"),
                        a.get("work_location_code"),
                        a.get("wbs_mid_name"),
                        a.get("wbs_sub_name"),
                        a.get("wbs_detail_name"),
                    )
                    for i, a in enumerate(activities)
                ],
            )

    async def insert_mapper_activities_batch(
        self,
        run_id: uuid.UUID,
        report_date: _date,
        activities: list[dict],
    ) -> None:
        """mapper_activities batch INSERT — Activity[] enriched (wa/l6_main/conf).

        (run_id, idx) 멱등. _prorate_mh 적용 후 호출. conditions 는 jsonb list.
        2026-05-19 확장: parser 산출 풀 컬럼 (zone/scope/누적/F%/잔여/note/work_location/WBS) 보존.
        """
        import json as _json

        if not activities:
            return
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as con:
            await con.executemany(
                """
                INSERT INTO mapper_activities
                    (run_id, report_date, idx,
                     company, trade, unit, today_qty,
                     wa, l6_main, mapping_conf, mapping_source, requires_review,
                     assigned_workers, worker_source,
                     plan_total_qty, plan_mh,
                     conditions,
                     zone, bp_code, scope,
                     yesterday_cum_qty, today_cum_qty,
                     progress_percent, remaining_qty, remaining_percent,
                     note, work_location_code,
                     wbs_mid_name, wbs_sub_name, wbs_detail_name,
                     alternatives,
                     cum_workers_today, cum_actual_mh_today)
                VALUES ($1, $2, $3,
                        $4, $5, $6, $7,
                        $8, $9, $10, $11, $12,
                        $13, $14,
                        $15, $16,
                        $17::jsonb,
                        $18, $19, $20,
                        $21, $22,
                        $23, $24, $25,
                        $26, $27,
                        $28, $29, $30,
                        $31::jsonb,
                        $32, $33)
                ON CONFLICT (run_id, idx) DO UPDATE SET
                    company            = EXCLUDED.company,
                    trade              = EXCLUDED.trade,
                    unit               = EXCLUDED.unit,
                    today_qty          = EXCLUDED.today_qty,
                    wa                 = EXCLUDED.wa,
                    l6_main            = EXCLUDED.l6_main,
                    mapping_conf       = EXCLUDED.mapping_conf,
                    mapping_source     = EXCLUDED.mapping_source,
                    requires_review    = EXCLUDED.requires_review,
                    assigned_workers   = EXCLUDED.assigned_workers,
                    worker_source      = EXCLUDED.worker_source,
                    plan_total_qty     = EXCLUDED.plan_total_qty,
                    plan_mh            = EXCLUDED.plan_mh,
                    conditions         = EXCLUDED.conditions,
                    zone               = EXCLUDED.zone,
                    bp_code            = EXCLUDED.bp_code,
                    scope              = EXCLUDED.scope,
                    yesterday_cum_qty  = EXCLUDED.yesterday_cum_qty,
                    today_cum_qty      = EXCLUDED.today_cum_qty,
                    progress_percent   = EXCLUDED.progress_percent,
                    remaining_qty      = EXCLUDED.remaining_qty,
                    remaining_percent  = EXCLUDED.remaining_percent,
                    note               = EXCLUDED.note,
                    work_location_code = EXCLUDED.work_location_code,
                    wbs_mid_name       = EXCLUDED.wbs_mid_name,
                    wbs_sub_name       = EXCLUDED.wbs_sub_name,
                    wbs_detail_name    = EXCLUDED.wbs_detail_name,
                    alternatives       = EXCLUDED.alternatives,
                    cum_workers_today  = EXCLUDED.cum_workers_today,
                    cum_actual_mh_today = EXCLUDED.cum_actual_mh_today
                """,
                [
                    (
                        run_id,
                        report_date,
                        i,
                        a["company"],
                        a.get("trade"),
                        a.get("unit"),
                        a.get("today_qty"),
                        a.get("wa"),
                        a.get("l6_main"),
                        a.get("mapping_conf"),
                        a.get("mapping_source"),
                        bool(a.get("requires_review", False)),
                        a.get("assigned_workers"),
                        a.get("worker_source"),
                        a.get("plan_total_qty"),
                        a.get("plan_mh"),
                        _json.dumps(a.get("conditions") or [], ensure_ascii=False),
                        a.get("zone"),
                        a.get("bp_code"),
                        a.get("scope"),
                        a.get("yesterday_cum_qty"),
                        a.get("today_cum_qty"),
                        a.get("progress_percent"),
                        a.get("remaining_qty"),
                        a.get("remaining_percent"),
                        a.get("note"),
                        a.get("work_location_code"),
                        a.get("wbs_mid_name"),
                        a.get("wbs_sub_name"),
                        a.get("wbs_detail_name"),
                        _json.dumps(a.get("alternatives") or [], ensure_ascii=False),
                        a.get("cum_workers_today"),
                        a.get("cum_actual_mh_today"),
                    )
                    for i, a in enumerate(activities)
                ],
            )

    # ------------------------------------------------------------------
    # 2026-05-19 — 신규 entity INSERT (시트2 / 시트3 / 시트6 / Cover)
    # ------------------------------------------------------------------

    async def insert_parser_job_allocations_batch(
        self,
        run_id: uuid.UUID,
        report_date: _date,
        rows: list[dict],
    ) -> None:
        """parser_job_allocations batch INSERT — 시트2 정규화.

        (run_id, idx) 멱등. 시간대 3 그룹 (전일누계/금일투입/금일누계) 각각 jsonb.
        rows: [{bp_code, company, disc_abbrev, manager_code, worker_code, job_type,
                workers_yesterday_cum: TimeShiftCounts, workers_today_incr, workers_today_cum,
                final_flag, workers_cum_t}, ...]
        """
        import json as _json

        if not rows:
            return
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as con:
            await con.executemany(
                """
                INSERT INTO parser_job_allocations
                    (run_id, report_date, idx,
                     bp_code, company, disc_abbrev,
                     manager_code, worker_code, job_type,
                     workers_yesterday_cum, workers_today_incr, workers_today_cum,
                     final_flag, workers_cum_t)
                VALUES ($1, $2, $3,
                        $4, $5, $6,
                        $7, $8, $9,
                        $10::jsonb, $11::jsonb, $12::jsonb,
                        $13, $14)
                ON CONFLICT (run_id, idx) DO UPDATE SET
                    bp_code               = EXCLUDED.bp_code,
                    company               = EXCLUDED.company,
                    disc_abbrev           = EXCLUDED.disc_abbrev,
                    manager_code          = EXCLUDED.manager_code,
                    worker_code           = EXCLUDED.worker_code,
                    job_type              = EXCLUDED.job_type,
                    workers_yesterday_cum = EXCLUDED.workers_yesterday_cum,
                    workers_today_incr    = EXCLUDED.workers_today_incr,
                    workers_today_cum     = EXCLUDED.workers_today_cum,
                    final_flag            = EXCLUDED.final_flag,
                    workers_cum_t         = EXCLUDED.workers_cum_t
                """,
                [
                    (
                        run_id,
                        report_date,
                        i,
                        r.get("bp_code"),
                        r["company"],
                        r.get("disc_abbrev"),
                        r.get("manager_code"),
                        r.get("worker_code"),
                        r["job_type"],
                        _json.dumps(r["workers_yesterday_cum"], ensure_ascii=False)
                        if r.get("workers_yesterday_cum") is not None
                        else None,
                        _json.dumps(r["workers_today_incr"], ensure_ascii=False)
                        if r.get("workers_today_incr") is not None
                        else None,
                        _json.dumps(r["workers_today_cum"], ensure_ascii=False)
                        if r.get("workers_today_cum") is not None
                        else None,
                        r.get("final_flag"),
                        int(r.get("workers_cum_t") or 0),
                    )
                    for i, r in enumerate(rows)
                ],
            )

    async def insert_parser_equipment_allocations_batch(
        self,
        run_id: uuid.UUID,
        report_date: _date,
        rows: list[dict],
    ) -> None:
        """parser_equipment_allocations batch INSERT — 시트3 정규화."""
        import json as _json

        if not rows:
            return
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as con:
            await con.executemany(
                """
                INSERT INTO parser_equipment_allocations
                    (run_id, report_date, idx,
                     bp_code, company, disc_abbrev,
                     equipment_big, equipment_mid, equipment_spec,
                     count_yesterday_cum, count_today_incr, count_today_cum,
                     final_flag, count_cum_t)
                VALUES ($1, $2, $3,
                        $4, $5, $6,
                        $7, $8, $9,
                        $10::jsonb, $11::jsonb, $12::jsonb,
                        $13, $14)
                ON CONFLICT (run_id, idx) DO UPDATE SET
                    bp_code             = EXCLUDED.bp_code,
                    company             = EXCLUDED.company,
                    disc_abbrev         = EXCLUDED.disc_abbrev,
                    equipment_big       = EXCLUDED.equipment_big,
                    equipment_mid       = EXCLUDED.equipment_mid,
                    equipment_spec      = EXCLUDED.equipment_spec,
                    count_yesterday_cum = EXCLUDED.count_yesterday_cum,
                    count_today_incr    = EXCLUDED.count_today_incr,
                    count_today_cum     = EXCLUDED.count_today_cum,
                    final_flag          = EXCLUDED.final_flag,
                    count_cum_t         = EXCLUDED.count_cum_t
                """,
                [
                    (
                        run_id,
                        report_date,
                        i,
                        r.get("bp_code"),
                        r["company"],
                        r.get("disc_abbrev"),
                        r["equipment_big"],
                        r["equipment_mid"],
                        r.get("equipment_spec"),
                        _json.dumps(r["count_yesterday_cum"], ensure_ascii=False)
                        if r.get("count_yesterday_cum") is not None
                        else None,
                        _json.dumps(r["count_today_incr"], ensure_ascii=False)
                        if r.get("count_today_incr") is not None
                        else None,
                        _json.dumps(r["count_today_cum"], ensure_ascii=False)
                        if r.get("count_today_cum") is not None
                        else None,
                        r.get("final_flag"),
                        int(r.get("count_cum_t") or 0),
                    )
                    for i, r in enumerate(rows)
                ],
            )

    async def insert_parser_worker_outputs_batch(
        self,
        run_id: uuid.UUID,
        report_date: _date,
        rows: list[dict],
        bp_name: str | None = None,
    ) -> None:
        """parser_worker_outputs batch INSERT — 시트6 (업체별만).

        Merge 단계에서 N 업체 worker_outputs 를 합쳐 하나의 run_id 로 INSERT.
        bp_name 은 row 자체에 박혀있으면 그쪽 우선 (Merge 가 채워줌).
        """
        if not rows:
            return
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as con:
            await con.executemany(
                """
                INSERT INTO parser_worker_outputs
                    (run_id, report_date, idx,
                     bp_name, worker_name, job_type,
                     wbs_mid_name, wbs_sub_name, wbs_detail_name,
                     work_location_code, work_content,
                     shift_morning, shift_daytime, shift_overtime,
                     shift_night, shift_all_night, note)
                VALUES ($1, $2, $3,
                        $4, $5, $6,
                        $7, $8, $9,
                        $10, $11,
                        $12, $13, $14,
                        $15, $16, $17)
                ON CONFLICT (run_id, idx) DO UPDATE SET
                    bp_name            = EXCLUDED.bp_name,
                    worker_name        = EXCLUDED.worker_name,
                    job_type           = EXCLUDED.job_type,
                    wbs_mid_name       = EXCLUDED.wbs_mid_name,
                    wbs_sub_name       = EXCLUDED.wbs_sub_name,
                    wbs_detail_name    = EXCLUDED.wbs_detail_name,
                    work_location_code = EXCLUDED.work_location_code,
                    work_content       = EXCLUDED.work_content,
                    shift_morning      = EXCLUDED.shift_morning,
                    shift_daytime      = EXCLUDED.shift_daytime,
                    shift_overtime     = EXCLUDED.shift_overtime,
                    shift_night        = EXCLUDED.shift_night,
                    shift_all_night    = EXCLUDED.shift_all_night,
                    note               = EXCLUDED.note
                """,
                [
                    (
                        run_id,
                        report_date,
                        i,
                        r.get("bp_name") or bp_name,
                        r["worker_name"],
                        r.get("job_type"),
                        r.get("wbs_mid_name"),
                        r.get("wbs_sub_name"),
                        r.get("wbs_detail_name"),
                        r.get("work_location_code"),
                        r.get("work_content"),
                        int(r.get("shift_morning") or 0),
                        int(r.get("shift_daytime") or 0),
                        int(r.get("shift_overtime") or 0),
                        int(r.get("shift_night") or 0),
                        int(r.get("shift_all_night") or 0),
                        r.get("note"),
                    )
                    for i, r in enumerate(rows)
                ],
            )

    async def insert_parser_report_meta_batch(
        self,
        run_id: uuid.UUID,
        report_date: _date,
        metas: list[dict],
    ) -> None:
        """parser_report_meta batch INSERT — Cover (업체별만).

        1 run × N 업체 = N row. UNIQUE (run_id, bp_name) 멱등.
        Merge 단계가 N 업체별 ReportMeta 를 dict list 로 모아 호출.
        """
        if not metas:
            return
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as con:
            await con.executemany(
                """
                INSERT INTO parser_report_meta
                    (run_id, report_date,
                     bp_name, project_name, project_code, site_id,
                     writer, reviewer, approval, document_no)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (run_id, bp_name) DO UPDATE SET
                    project_name = EXCLUDED.project_name,
                    project_code = EXCLUDED.project_code,
                    site_id      = EXCLUDED.site_id,
                    writer       = EXCLUDED.writer,
                    reviewer     = EXCLUDED.reviewer,
                    approval     = EXCLUDED.approval,
                    document_no  = EXCLUDED.document_no
                """,
                [
                    (
                        run_id,
                        report_date,
                        m["bp_name"],
                        m.get("project_name"),
                        m.get("project_code"),
                        m.get("site_id"),
                        m.get("writer"),
                        m.get("reviewer"),
                        m.get("approval"),
                        m.get("document_no"),
                    )
                    for m in metas
                ],
            )

    async def fetch_one(self, sql: str, *args: Any) -> dict[str, Any] | None:
        """임의 SELECT 1 row 조회 helper. 외부에서 _pool 직접 접근 대신 사용.

        Returns:
            첫 번째 row 를 dict 로 반환. row 없으면 None.
        """
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, *args)
        return dict(row) if row else None

    async def fetch_all(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        """임의 SELECT 다중 row 조회 helper. 외부에서 _pool 직접 접근 대신 사용.

        Returns:
            전체 row 를 list[dict] 로 반환. row 없으면 [].
        """
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, *args)
        return [dict(r) for r in rows]

    _VIEW_JSONB_COLS: tuple[str, ...] = (
        "kpi_jsonb",
        "contractor_bars_jsonb",
        "trade_bars_jsonb",
        "quadrant_jsonb",
        "wp_summary_jsonb",
        "s_curve_jsonb",
        "optimizer_view_jsonb",
        "productivity_jsonb",
        "scenarios_jsonb",
    )

    async def upsert_daily_report_view_col(
        self,
        run_id: uuid.UUID,
        site_id: str,
        report_date: _date,
        col: str,
        value: dict | list,
    ) -> None:
        """daily_reports 의 jsonb 컬럼 1개 UPSERT — partial write 가드.

        col 은 _VIEW_JSONB_COLS 화이트리스트 중 하나여야 함 (SQL injection 가드).
        """
        import json as _json

        if col not in self._VIEW_JSONB_COLS:
            raise ValueError(f"col '{col}' not in whitelist {self._VIEW_JSONB_COLS}")
        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as con:
            # UPDATE 우선 — partial unique index `(run_id, site_id, report_date)
            # WHERE site_id IS NOT NULL` 가 ON CONFLICT 와 안정 매칭 안 됨.
            # row 이미 존재 (reporter 가 INSERT) 보장 → UPDATE 만.
            row_count = await con.fetchval(
                f"""
                UPDATE daily_reports
                SET {col} = $4::jsonb
                WHERE run_id = $1 AND site_id = $2 AND report_date = $3
                RETURNING id
                """,
                run_id,
                site_id,
                report_date,
                _json.dumps(value, ensure_ascii=False, default=str),
            )
            if row_count is None:
                # 신규 INSERT (reporter 가 row 안 만든 경우만)
                await con.execute(
                    f"""
                    INSERT INTO daily_reports (run_id, site_id, report_date, report_md, {col})
                    VALUES ($1, $2, $3, '', $4::jsonb)
                    """,
                    run_id,
                    site_id,
                    report_date,
                    _json.dumps(value, ensure_ascii=False, default=str),
                )


async def update_site_last_run(pg: PGClient, site_id: str, run_id: uuid.UUID) -> None:
    """G8 — reporter→END 진입 시 sites.last_run_id 갱신."""
    assert pg._pool is not None, "connect() 미호출"
    async with pg._pool.acquire() as con:
        await con.execute(
            "UPDATE sites SET last_run_id = $1, updated_at = now() WHERE site_id = $2",
            run_id,
            site_id,
        )


# G2 상수 — Spec §6.
AS_IS_MIN: int = 120  # 일보당 사람 수작업 분
TO_BE_MIN: int = 5  # 일보당 AI 처리 분


async def update_site_hours_saved_cum(
    pg: PGClient,
    site_id: str,
    atomized_count: int,
) -> None:
    """G2 — atomized_count 기반 절감 시간(h) 누적 UPDATE.

    산식: ((AS_IS_MIN - TO_BE_MIN) / 60.0) * atomized_count.
    """
    assert pg._pool is not None, "connect() 미호출"
    delta_h = (AS_IS_MIN - TO_BE_MIN) / 60.0 * atomized_count
    async with pg._pool.acquire() as con:
        await con.execute(
            "UPDATE sites SET hours_saved_cum = hours_saved_cum + $1, updated_at = now() WHERE site_id = $2",
            delta_h,
            site_id,
        )
