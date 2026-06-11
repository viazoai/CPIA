"""daily_reports.site_summary_text 를 현재 적재 수치로 제자리 재생성.

배경(2026-06-11): 차트 아래 site_summary 브리핑이 longest-pole 보정(delay=48·recovery=5)
이전의 Σ 합산 버그 시절 수치(예: 99일 지연·66일 만회·"계획 동일 복귀")로 박혀 있어
차트와 안 맞았다. 현재 kpi/scenarios/s_curve 값으로 build_site_summary_payload +
generate_site_summary(고쳐진 SYSTEM_PROMPT_V10)을 다시 돌려 정합화한다.

사용 (pipeline 컨테이너 이미지로 실행):
  AWS_URL='postgresql://...'
  docker run --rm --env-file .env -e POSTGRES_URL="$AWS_URL" \\
    -v "$PWD:/src:ro" -e PYTHONPATH=/src -w /src \\
    ghcr.io/viazoai/cpia-pipeline:latest \\
    /app/pipeline/.venv/bin/python scripts/fix_site_summary_inplace.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

from pipeline.agents.optimizer.site_summary import (  # noqa: E402
    build_site_summary_payload,
    generate_site_summary,
)

DSN = os.environ.get("POSTGRES_URL") or os.environ.get("DEV_DB_URL")
DEMO_DATES = ("2025-09-20", "2025-09-21", "2025-09-22", "2025-09-23", "2025-09-24", "2025-09-25")


def _as_obj(v, default):
    if v is None:
        return default
    return json.loads(v) if isinstance(v, str) else v


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="단일 날짜 (기본: 9/20~9/25)")
    parser.add_argument("--site", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not DSN:
        raise SystemExit("POSTGRES_URL(or DEV_DB_URL) 환경변수 필요")
    model = os.environ.get("LLM_MODEL", "gpt-5.1-chat-ai-board-test")
    azure = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    )

    dates = (args.date,) if args.date else DEMO_DATES
    where = ["dr.is_mock = false"]
    params: list = [list(dates)]
    where.append(f"pr.report_date::text = ANY(${len(params)}::text[])")
    if args.site:
        params.append(args.site)
        where.append(f"pr.site_id = ${len(params)}")

    sql = (
        "SELECT dr.id, pr.site_id, pr.report_date::text AS report_date, "
        "       dr.kpi_jsonb, dr.scenarios_jsonb, dr.wp_summary_jsonb, "
        "       dr.optimizer_view_jsonb, dr.s_curve_jsonb "
        "FROM daily_reports dr JOIN pipeline_runs pr USING (run_id) "
        "WHERE " + " AND ".join(where) + " ORDER BY pr.report_date, pr.site_id"
    )

    conn = await asyncpg.connect(DSN)
    n = 0
    try:
        rows = await conn.fetch(sql, *params)
        print(f"대상 row: {len(rows)}  dates={dates}  (dry-run={args.dry_run})")
        for r in rows:
            kpi = _as_obj(r["kpi_jsonb"], {})
            scenarios = _as_obj(r["scenarios_jsonb"], {})
            wp_summary = _as_obj(r["wp_summary_jsonb"], [])
            optimizer_view = _as_obj(r["optimizer_view_jsonb"], {})
            s_curve = _as_obj(r["s_curve_jsonb"], [])
            payload = build_site_summary_payload(
                report_date=r["report_date"],
                site_id=r["site_id"],
                kpi=kpi,
                scenarios=scenarios,
                wp_summary=wp_summary,
                optimizer_view=optimizer_view,
                s_curve=s_curve,
            )
            try:
                summary = generate_site_summary(payload, azure=azure, model=model)
            except Exception as e:  # noqa: BLE001
                print(f"  [SKIP] {r['report_date']}: {type(e).__name__}: {e}")
                continue
            if not summary:
                continue
            n += 1
            if args.dry_run:
                print(f"\n── {r['report_date']}  (delay={payload['delay_days']} recovery={payload['ai_recovery_days']} "
                      f"no_action={payload['expected_completion']['if_no_action']} ai={payload['expected_completion']['ai_scenario']})")
                print("  ", summary)
            else:
                await conn.execute(
                    "UPDATE daily_reports SET site_summary_text = $1 WHERE id = $2",
                    summary, r["id"],
                )
        print(f"\n=== 요약 === site_summary {'생성(미저장)' if args.dry_run else '재생성'} {n}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
