"""Phase 1 (2026-05-21) backfill — view_builder._build_productivity_views_v2 호출.

기존 backfill_daily_report_views.py 보존 (구 산식 흐름 비교용),
이 스크립트는 530일 전체 또는 단일 일자로 daily_reports.jsonb 6컬럼 갱신.

흐름:
  1. mapper_activities 일자 list 수집 (mock site 제외)
  2. 각 (site_id, date) 별 _build_productivity_views_v2 호출
  3. 결과 비어있으면 (plan 기간 밖) empty dict 적재 (UI 빈 화면 sentinel)
  4. skip ratio > 30% 면 중단

ChromaDB upsert 는 본 스크립트 범위 외 — 별도 단계 (시연 critical 아님).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

from pipeline.agents.optimizer.view_builder import (  # noqa: E402
    _build_productivity_views_v2,
)
from pipeline.db import PGClient  # noqa: E402

DSN = os.environ.get(
    "POSTGRES_URL",
    "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia",
)


_JSONB_COLS = (
    "kpi_jsonb",
    "productivity_jsonb",
    "contractor_bars_jsonb",
    "trade_bars_jsonb",
    "quadrant_jsonb",
    "wp_summary_jsonb",
    "optimizer_view_jsonb",
    "scenarios_jsonb",
    "s_curve_jsonb",
)


async def update_one(
    raw_conn: asyncpg.Connection, site_id: str, the_date, result: dict
) -> None:
    """daily_reports 의 mock=false 매칭 row 의 6 jsonb 컬럼 UPDATE.
    매칭 row 가 없으면 INSERT (run_id NULL — backfill 전용 placeholder)."""
    set_clause = ", ".join(f"{c} = ${i + 1}::jsonb" for i, c in enumerate(_JSONB_COLS))
    args = [
        json.dumps(
            result.get(k.replace("_jsonb", ""), {}), ensure_ascii=False, default=str
        )
        for k in _JSONB_COLS
    ]
    upd = await raw_conn.execute(
        f"""
        UPDATE daily_reports
        SET {set_clause}
        WHERE site_id = ${len(_JSONB_COLS) + 1}
          AND report_date = ${len(_JSONB_COLS) + 2}::date
          AND is_mock = false
        """,
        *args,
        site_id,
        the_date,
    )
    # upd 형식 "UPDATE N" — N=0 이면 (site, date) 매칭 daily_reports row 없음 → skip
    # backfill 전용 — INSERT 까지는 안 함 (live pipeline_runs 가 생성한 row 만 갱신)
    return upd


async def main() -> None:
    from datetime import date as _date

    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--all-dates", action="store_true")
    parser.add_argument(
        "--site", default=None, help="단일 site_id 만 (기본 mock=false 전체)"
    )
    parser.add_argument(
        "--with-summary",
        action="store_true",
        help="LLM site_summary_text 도 같이 산출 (Azure OpenAI 호출, 일자 N 회).",
    )
    args = parser.parse_args()

    pg = PGClient(DSN)
    await pg.connect()
    raw = await asyncpg.connect(DSN)
    try:
        # site_id 목록 (mock 제외)
        sites_q = "SELECT site_id FROM sites WHERE is_mock = false"
        if args.site:
            sites_q += " AND site_id = $1"
            site_rows = await raw.fetch(sites_q, args.site)
        else:
            site_rows = await raw.fetch(sites_q)
        sites = [r["site_id"] for r in site_rows]
        print(f"대상 site: {len(sites)} -> {sites}")

        # 일자 목록
        if args.all_dates:
            d_rows = await raw.fetch(
                "SELECT DISTINCT report_date FROM mapper_activities ORDER BY 1"
            )
            dates = [r["report_date"] for r in d_rows]
        else:
            dates = [_date.fromisoformat(args.date or "2025-09-25")]
        print(f"대상 일자: {len(dates)}")

        stat = Counter()
        for site in sites:
            for d in dates:
                result = await _build_productivity_views_v2(pg, site, d)
                if not result.get("kpi"):
                    stat["empty"] += 1
                    # empty 도 jsonb 채워야 — 옛 데이터 stale 방지
                    empty_result = {
                        "kpi": {},
                        "productivity": {},
                        "contractor_bars": [],
                        "trade_bars": [],
                        "quadrant": [],
                        "wp_summary": [],
                    }
                    upd = await update_one(raw, site, d, empty_result)
                else:
                    stat["ok"] += 1
                    upd = await update_one(raw, site, d, result)
                    if args.with_summary:
                        # lazy import — formatter unused-import 휴리스틱 회피
                        from pipeline.agents.optimizer.site_summary import (
                            build_site_summary_payload,
                            generate_site_summary,
                        )

                        try:
                            payload = build_site_summary_payload(
                                report_date=d.isoformat(),
                                site_id=site,
                                kpi=result.get("kpi", {}),
                                scenarios=result.get("scenarios", {}),
                                wp_summary=result.get("wp_summary", []),
                                optimizer_view=result.get("optimizer_view", {}),
                                s_curve=result.get("s_curve", []),
                            )
                            summary = await asyncio.to_thread(
                                generate_site_summary, payload
                            )
                            await raw.execute(
                                "UPDATE daily_reports SET site_summary_text = $1 "
                                "WHERE site_id = $2 AND report_date = $3::date AND is_mock = false",
                                summary,
                                site,
                                d,
                            )
                            stat["summary_ok"] += 1
                            print(f"    [llm] summary: {summary[:80]}...")
                        except Exception as exc:
                            stat["summary_fail"] += 1
                            print(f"    [warn] site_summary failed for {d}: {exc}")
                if upd == "UPDATE 0":
                    stat["no_target"] += 1
            print(
                f"  {site}: ok={stat['ok']} empty={stat['empty']} no_target={stat['no_target']}"
            )

        total = stat["ok"] + stat["empty"]
        skip_pct = (stat["empty"] / total * 100) if total else 0
        print(
            f"\n=== 요약 ===\n"
            f"처리 (site×date): ok={stat['ok']} empty={stat['empty']} "
            f"no_target={stat['no_target']} (skip {skip_pct:.1f}%)"
        )
        if skip_pct > 30:
            raise RuntimeError(
                f"skip ratio {skip_pct:.1f}% > 30% — backfill 데이터 결손"
            )
    finally:
        await pg.close()
        await raw.close()


if __name__ == "__main__":
    asyncio.run(main())
