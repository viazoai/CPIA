"""Mock data 를 PG row 로 backfill — is_mock=TRUE.

mock_review_cards.json → mapper_activities + parser_activities (13 row)
mock_report.json → daily_reports (N row, jsonb 컬럼들)

실행:
  POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
    pipeline/.venv/bin/python3 scripts/backfill_mock_rows.py

설계 메모:
- plan T0.2 의 `_split_kebab_wp_id` 가설은 잘못. mock card 의 `ai_mapped_wp_id` 는 `wp-N-N-N` 자체 ID format.
  대신 `ai_mapped_path` ("M15X > FAB (UT1) > 건축 > 거푸집공사") 의 ` > ` split 으로 wa/l6_main 추출.
- MOCK_SITE_ID = "m15x-ph3-ibl" (plan 의 DEMO_SITE 대신). DEMO_SITE 는 activity_master 에 없어
  wbsTreeBuild 가 빈 트리 반환 → 시연 시 wbs 가 빈 화면. m15x 면 activity_master 기반 정상 wbs.
- 적재 전 is_mock=TRUE row 전체 cleanup (idempotent).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.db import PGClient  # noqa: E402

MOCK_SITE_ID = "m15x-ph3-ibl"
MOCK_REVIEW_RUN_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
MOCK_REVIEW_DATE = date(2025, 9, 25)


def _split_path(path: str) -> tuple[str, str]:
    """ai_mapped_path → (wa, l6_main).

    예: "M15X > FAB (UT1) > 건축 > 거푸집공사" → ("FAB", "거푸집공사")
    "M15X > CUB (Main 공동구) > 건축 > 철근공사" → ("CUB", "철근공사")
    """
    parts = [p.strip() for p in (path or "").split(">")]
    if len(parts) < 4:
        return ("", "")
    wa = parts[1].split("(")[0].strip()
    return (wa, parts[3])


async def cleanup_mock(pg: PGClient) -> None:
    """이전 is_mock=TRUE row 전체 삭제 — idempotent re-run 보장.

    FK 의존성: daily_reports → pipeline_runs / mapper_activities → pipeline_runs / parser_activities → pipeline_runs.
    삭제 순서: 자식 먼저 → 부모 (pipeline_runs).
    """
    async with pg._pool.acquire() as con:
        await con.execute("DELETE FROM daily_reports WHERE is_mock = TRUE")
        await con.execute("DELETE FROM mapper_activities WHERE is_mock = TRUE")
        await con.execute("DELETE FROM parser_activities WHERE is_mock = TRUE")
        await con.execute("DELETE FROM forecasts WHERE is_mock = TRUE")
        await con.execute("DELETE FROM optimizer_advice WHERE is_mock = TRUE")
        await con.execute("DELETE FROM parser_reports WHERE is_mock = TRUE")
        await con.execute("DELETE FROM pipeline_runs WHERE is_mock = TRUE")


async def backfill_review_cards(pg: PGClient) -> int:
    cards = json.loads((ROOT / "data" / "mock_review_cards.json").read_text())

    async with pg._pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO pipeline_runs (run_id, site_id, report_date, status, is_mock)
            VALUES ($1, $2, $3, 'completed', TRUE)
            """,
            MOCK_REVIEW_RUN_ID,
            MOCK_SITE_ID,
            MOCK_REVIEW_DATE,
        )

        inserted = 0
        for idx, card in enumerate(cards):
            wa, l6 = _split_path(card.get("ai_mapped_path") or "")
            await con.execute(
                """
                INSERT INTO parser_activities
                  (run_id, report_date, idx, company, work_content, today_qty, unit, is_mock)
                VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE)
                """,
                MOCK_REVIEW_RUN_ID,
                MOCK_REVIEW_DATE,
                idx,
                card.get("bp_name"),
                card.get("work_content"),
                card.get("quantity"),
                card.get("unit"),
            )
            await con.execute(
                """
                INSERT INTO mapper_activities
                  (run_id, report_date, idx, company, today_qty, unit, wa, l6_main,
                   mapping_conf, requires_review, alternatives, is_mock)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, TRUE)
                """,
                MOCK_REVIEW_RUN_ID,
                MOCK_REVIEW_DATE,
                idx,
                card.get("bp_name"),
                card.get("quantity"),
                card.get("unit"),
                wa,
                l6,
                card.get("confidence"),
                card.get("status") == "unconfirmed",
                json.dumps(card.get("alternative_wps") or []),
            )
            inserted += 1
        return inserted


def _wrap_optimizer_view(opt: dict) -> dict:
    """mock_report 의 optimizer (single wp dict) → daily_reports.optimizer_view_jsonb shape.

    view_builder._build_optimizer_view 산출은 {by_wp: {wp_id: {...}}, default_wp_id}.
    mock 은 single wp 만 있으므로 by_wp dict 에 wp_id key 1개로 적재.
    """
    if not opt:
        return {"by_wp": {}, "default_wp_id": None}
    wp_id = opt.get("wp_id") or "default"
    advice = {
        "diagnosis": opt.get("diagnosis", ""),
        "similar_cases": opt.get("similar_cases", []),
        "recommendations": opt.get("recommendations", []),
        "details": opt.get("details", []),
    }
    return {"by_wp": {wp_id: advice}, "default_wp_id": wp_id}


async def backfill_report(pg: PGClient) -> int:
    report = json.loads((ROOT / "data" / "mock_report.json").read_text())
    daily = report.get("daily", [])
    details = report.get("details", {})

    inserted = 0
    async with pg._pool.acquire() as con:
        for d in daily:
            d_date = date.fromisoformat(d["date"])
            detail = details.get(d["date"], {})

            # date 기반 deterministic UUID (충돌 회피)
            run_id = uuid.UUID(int=(d_date.toordinal() << 96) | 0xDEAD)

            await con.execute(
                """
                INSERT INTO pipeline_runs (run_id, site_id, report_date, status, is_mock)
                VALUES ($1, $2, $3, 'completed', TRUE)
                """,
                run_id,
                MOCK_SITE_ID,
                d_date,
            )

            await con.execute(
                """
                INSERT INTO daily_reports
                  (run_id, site_id, report_date, report_md,
                   kpi_jsonb, s_curve_jsonb, contractor_bars_jsonb, trade_bars_jsonb,
                   quadrant_jsonb, wp_summary_jsonb, optimizer_view_jsonb,
                   scenarios_jsonb, productivity_jsonb, is_mock)
                VALUES ($1, $2, $3, '',
                        $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb,
                        $8::jsonb, $9::jsonb, $10::jsonb,
                        $11::jsonb, '{}'::jsonb, TRUE)
                """,
                run_id,
                MOCK_SITE_ID,
                d_date,
                json.dumps(detail.get("kpi") or {}),
                json.dumps(detail.get("s_curve") or []),
                json.dumps(detail.get("contractor_bars") or []),
                json.dumps(detail.get("trade_bars") or []),
                json.dumps(detail.get("quadrant") or []),
                json.dumps(detail.get("wp_summary") or []),
                json.dumps(_wrap_optimizer_view(detail.get("optimizer") or {})),
                json.dumps({}),
            )
            inserted += 1
    return inserted


async def main() -> None:
    url = os.environ.get(
        "POSTGRES_URL", "postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia"
    )
    pg = PGClient(url)
    await pg.connect()
    try:
        await cleanup_mock(pg)
        n_cards = await backfill_review_cards(pg)
        print(
            f"✅ mock_review_cards: {n_cards} mapper+parser rows (is_mock=TRUE, site={MOCK_SITE_ID})"
        )
        n_reports = await backfill_report(pg)
        print(
            f"✅ mock_report: {n_reports} daily_reports rows (is_mock=TRUE, site={MOCK_SITE_ID})"
        )
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
