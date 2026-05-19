"""기존 cycle 일자에 daily_reports.view_jsonb 채움 — Phase B 마이그레이션 후 1회 실행."""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from pipeline.db import PGClient
from pipeline.agents.optimizer.view_builder import (
    _build_productivity_views,
    _build_kpi,
    _build_contractor_bars,
    _build_trade_bars,
    _build_quadrant,
    _build_wp_summary,
    _build_s_curve,
    _build_optimizer_view,
)


# Minor 7: SELECT 명시 컬럼 (schema drift 가드)
_FORECAST_COLS = "company, l6_main, wa, risk_level, delay_days, expected_completion"
_ADVICE_COLS = "company, l6_main, diagnosis, degradation_cases, recommendations, recovery_distribution, recovery_pattern"

# _VIEW_JSONB_COLS 화이트리스트 (SQL injection 가드)
_VIEW_JSONB_COLS = (
    "kpi_jsonb",
    "contractor_bars_jsonb",
    "trade_bars_jsonb",
    "quadrant_jsonb",
    "wp_summary_jsonb",
    "s_curve_jsonb",
    "optimizer_view_jsonb",
    "productivity_jsonb",
)


def _parse_json_field(val: Any) -> Any:
    """DB에서 문자열로 저장된 JSON 필드를 파싱."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val


async def _update_view_col(
    pg: PGClient,
    run_id: Any,
    col: str,
    value: Any,
) -> None:
    """daily_reports 에서 run_id 기준 jsonb 컬럼 1개 UPDATE.

    daily_reports PK 는 id(bigint) 이고 (run_id, site_id, report_date) UNIQUE 제약이 없어
    ON CONFLICT 방식 대신 run_id 기준 UPDATE 사용.
    """
    if col not in _VIEW_JSONB_COLS:
        raise ValueError(f"col '{col}' not in whitelist {_VIEW_JSONB_COLS}")
    assert pg._pool is not None, "connect() 미호출"
    async with pg._pool.acquire() as con:
        await con.execute(
            f"UPDATE daily_reports SET {col} = $1::jsonb WHERE run_id = $2",
            json.dumps(value, ensure_ascii=False, default=str),
            run_id,
        )


async def main() -> None:
    postgres_url = os.environ["POSTGRES_URL"]
    pg = PGClient(postgres_url)
    await pg.connect()
    try:
        async with pg._pool.acquire() as con:
            runs = await con.fetch(
                """
                SELECT pr.run_id, pr.site_id, pr.report_date
                FROM pipeline_runs pr
                JOIN sites s ON s.site_id = pr.site_id
                WHERE s.is_mock = FALSE AND pr.status = 'completed'
                ORDER BY pr.report_date DESC
                """
            )
        print(f"[backfill] {len(runs)} cycles to backfill")

        for r in runs:
            run_id = r["run_id"]
            site_id = r["site_id"]
            today = r["report_date"]

            async with pg._pool.acquire() as con:
                forecast_rows = await con.fetch(
                    f"SELECT {_FORECAST_COLS} FROM forecasts WHERE run_id = $1",
                    run_id,
                )
                advice_rows = await con.fetch(
                    f"SELECT {_ADVICE_COLS} FROM optimizer_advice WHERE run_id = $1",
                    run_id,
                )
            # degradation_cases, recommendations, recovery_pattern 이 문자열로 저장된 경우 파싱
            forecast = [dict(f) for f in forecast_rows]
            advice = []
            for a in advice_rows:
                row = dict(a)
                row["degradation_cases"] = _parse_json_field(row.get("degradation_cases"))
                row["recommendations"] = _parse_json_field(row.get("recommendations"))
                row["recovery_distribution"] = _parse_json_field(row.get("recovery_distribution"))
                row["recovery_pattern"] = _parse_json_field(row.get("recovery_pattern"))
                advice.append(row)
            mapped: list[dict] = []  # view_builder 가 PG 에서 직접 fetch 하므로 backfill 에서 별도 fetch 불필요

            try:
                productivity = await _build_productivity_views(pg, run_id, site_id, today, forecast, mapped)
                quadrant = await _build_quadrant(pg, site_id, today, productivity)
                view_jsonbs = {
                    "productivity_jsonb": productivity,
                    "kpi_jsonb": await _build_kpi(pg, site_id, today, productivity),
                    "contractor_bars_jsonb": _build_contractor_bars(productivity),
                    "trade_bars_jsonb": _build_trade_bars(productivity),
                    "quadrant_jsonb": quadrant,
                    "wp_summary_jsonb": await _build_wp_summary(pg, site_id, today, productivity, quadrant),
                    "s_curve_jsonb": await _build_s_curve(pg, site_id, today),
                    "optimizer_view_jsonb": _build_optimizer_view(advice, forecast, mapped),
                }
                for col, val in view_jsonbs.items():
                    try:
                        await _update_view_col(pg, run_id, col, val)
                    except Exception as e:
                        print(f"[backfill] {run_id} {col} fail: {e}")
                print(f"[backfill] done {run_id} {site_id} {today}")
            except Exception as e:
                print(f"[backfill] {run_id} site={site_id} date={today} FAIL: {e}")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
