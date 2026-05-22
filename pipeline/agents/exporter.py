"""Exporter — 통합 작업일보 xlsx 생성.

Spec: docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md §7
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date as _date

from pipeline.db import PGClient


class NoDataError(Exception):
    """해당 (site_id, report_date) 의 parser_* row 0건."""


@dataclass
class SheetData:
    output_manpower: list[dict]  # 시트1
    occupation_manpower: list[dict]  # 시트2
    equipment: list[dict]  # 시트3
    quantity: list[dict]  # 시트4


def _coerce(row) -> dict:
    """asyncpg jsonb codec 미등록 시 str 로 떨어지는 케이스 흡수."""
    v = row["row"]
    return json.loads(v) if isinstance(v, str) else v


async def fetch_sheet_data(
    pg: PGClient,
    site_id: str,
    report_date: _date,
) -> SheetData:
    """모든 run 의 jsonb 합집합 — Spec §7.1.

    parser_reports / parser_activities 는 site_id 컬럼 없음 → pipeline_runs JOIN.
    """
    async with pg._pool.acquire() as con:
        bp_rows = await con.fetch(
            """
            SELECT jsonb_array_elements(pt.bp_summaries) AS row
            FROM parser_reports pt
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pt.report_date = $2
            """,
            site_id,
            report_date,
        )
        job_rows = await con.fetch(
            """
            SELECT jsonb_array_elements(pt.job_allocations) AS row
            FROM parser_reports pt
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pt.report_date = $2
            """,
            site_id,
            report_date,
        )
        eq_rows = await con.fetch(
            """
            SELECT jsonb_array_elements(pt.equipment_allocations) AS row
            FROM parser_reports pt
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pt.report_date = $2
            """,
            site_id,
            report_date,
        )
        act_rows = await con.fetch(
            """
            SELECT pa.*
            FROM parser_activities pa
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pa.report_date = $2
            ORDER BY pa.run_id, pa.idx
            """,
            site_id,
            report_date,
        )

    if not (bp_rows or job_rows or eq_rows or act_rows):
        raise NoDataError(f"해당 ({site_id}, {report_date.isoformat()}) 데이터 없음")

    return SheetData(
        output_manpower=[_coerce(r) for r in bp_rows],
        occupation_manpower=[_coerce(r) for r in job_rows],
        equipment=[_coerce(r) for r in eq_rows],
        quantity=[dict(r) for r in act_rows],
    )
