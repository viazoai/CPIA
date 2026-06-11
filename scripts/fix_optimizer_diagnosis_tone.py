"""기존 optimizer_view 의 진단(diagnosis) '본문' 문체만 존댓말 서술체로 제자리 교정.

배경: 브리핑/헤드라인/만회방안은 자연어로 다듬었으나(fix_optimizer_briefing_inplace.py),
진단 본문은 손대지 않아 날짜·WP 마다 문어체("~분기점이다")가 9/25 톤(존댓말)과 어긋났다.
1줄째 데이터 라인(예: "정상 조건 · 금일 48.5 m3 (계획 일평균 500.1 m3)")은 보존하고,
그 아래 본문만 DIAG_POLISH_PROMPT 로 존댓말로 다시 쓴다. 사실·숫자 무손상(순수 톤 교정).

사용 (pipeline 컨테이너 이미지로 실행):
  AWS_URL='postgresql://...'
  docker run --rm --env-file .env -e POSTGRES_URL="$AWS_URL" \\
    -v "$PWD:/src:ro" -e PYTHONPATH=/src -w /src \\
    ghcr.io/viazoai/cpia-pipeline:latest \\
    /app/pipeline/.venv/bin/python scripts/fix_optimizer_diagnosis_tone.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

from pipeline.agents.optimizer.prompt import DIAG_POLISH_PROMPT  # noqa: E402

DSN = os.environ.get("POSTGRES_URL") or os.environ.get("DEV_DB_URL")
DEMO_DATES = ("2025-09-20", "2025-09-21", "2025-09-22", "2025-09-23", "2025-09-24", "2025-09-25")

# 이미 존댓말로 끝나는 본문은 건너뛴다(중복 호출 방지).
_JONDAE_END = re.compile(r"(습니다|됩니다|입니다|하겠습니다|있습니다|랍니다)[.\s]*$")


def _as_obj(v):
    if v is None:
        return None
    return json.loads(v) if isinstance(v, str) else v


def _azure() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    )


def _polish_body(azure: AzureOpenAI, model: str, body: str) -> str:
    """DIAG_POLISH_PROMPT 1회 호출 → 존댓말 본문. fail 시 raise."""
    resp = azure.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": DIAG_POLISH_PROMPT},
            {"role": "user", "content": json.dumps({"diagnosis_body": body}, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    out = json.loads(resp.choices[0].message.content)
    return (out.get("diagnosis_body") or "").strip()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="단일 날짜 (기본: 9/20~9/25)")
    parser.add_argument("--site", default=None)
    parser.add_argument("--dry-run", action="store_true", help="LLM 호출 + 미리보기, UPDATE 안 함")
    parser.add_argument("--limit-wp", type=int, default=None, help="WP N개만 (dry-run 점검용)")
    parser.add_argument("--force", action="store_true", help="이미 존댓말이어도 다시 교정")
    args = parser.parse_args()

    if not DSN:
        raise SystemExit("POSTGRES_URL(or DEV_DB_URL) 환경변수 필요")
    model = os.environ.get("LLM_MODEL", "gpt-5.1-chat-ai-board-test")
    azure = _azure()

    dates = (args.date,) if args.date else DEMO_DATES
    where = ["dr.is_mock = false", "dr.optimizer_view_jsonb IS NOT NULL"]
    params: list = [list(dates)]
    where.append(f"pr.report_date::text = ANY(${len(params)}::text[])")
    if args.site:
        params.append(args.site)
        where.append(f"pr.site_id = ${len(params)}")

    sql = (
        "SELECT dr.id, pr.run_id, pr.site_id, pr.report_date, dr.optimizer_view_jsonb "
        "FROM daily_reports dr JOIN pipeline_runs pr USING (run_id) "
        "WHERE " + " AND ".join(where) + " ORDER BY pr.report_date, pr.site_id"
    )

    conn = await asyncpg.connect(DSN)
    n_rows = n_wp = n_fix = n_skip = 0
    try:
        rows = await conn.fetch(sql, *params)
        print(f"대상 daily_reports row: {len(rows)}  dates={dates}  (dry-run={args.dry_run})")
        for r in rows:
            view = _as_obj(r["optimizer_view_jsonb"]) or {}
            by_wp = view.get("by_wp") or {}
            if not by_wp:
                continue
            n_rows += 1
            wp_items = list(by_wp.items())
            if args.limit_wp:
                wp_items = wp_items[: args.limit_wp]
            for wp_key, wp_view in wp_items:
                diag = wp_view.get("diagnosis") or ""
                if "\n" in diag:
                    head, body = diag.split("\n", 1)
                else:
                    head, body = "", diag
                body = body.strip()
                if not body:
                    continue
                # 이미 존댓말 종결이면 건너뜀(--force 로 강제 가능).
                if not args.force and _JONDAE_END.search(body):
                    n_skip += 1
                    continue
                try:
                    new_body = _polish_body(azure, model, body)
                except Exception as e:  # noqa: BLE001
                    print(f"  [SKIP] {r['report_date']} {wp_key}: {type(e).__name__}: {e}")
                    continue
                if not new_body:
                    continue
                new_diag = (head + "\n" + new_body) if head else new_body
                wp_view["diagnosis"] = new_diag
                n_fix += 1
                if args.dry_run:
                    print(f"\n── {r['report_date']} {wp_key}")
                    print(f"   [1줄째 보존] {head}")
                    print(f"   [전] {body[:200]}")
                    print(f"   [후] {new_body[:200]}")

            if not args.dry_run:
                await conn.execute(
                    "UPDATE daily_reports SET optimizer_view_jsonb = $1::jsonb WHERE id = $2",
                    json.dumps(view, ensure_ascii=False),
                    r["id"],
                )
        verb = "교정(미저장)" if args.dry_run else "교정"
        print(f"\n=== 요약 === row {n_rows} / 본문 {verb} {n_fix} / 이미 존댓말 skip {n_skip}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
