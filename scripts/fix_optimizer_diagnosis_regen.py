"""optimizer_view 의 진단(diagnosis)을 제자리 재작성 — 데이터 라인 제거 + 원인→패턴→해결.

배경(2026-06-11): 진단 첫머리 데이터 라벨("정상 조건 · 금일 X (계획 일평균 Y)")을 빼고,
"오늘 왜 떨어졌나(원인 + 물량 수치) → 과거 회복 패턴 → 이렇게 풀면 며칠 만회" 흐름으로
짧게(2~3문장) 재작성. 인용 수치는 기존 진단/헤드라인에 있는 값만(새 숫자 금지).
similar_cases·details·recommendations·briefing 등 나머지는 무손상.

사용 (pipeline 컨테이너 이미지로 실행):
  AWS_URL='postgresql://...'
  docker run --rm --env-file .env -e POSTGRES_URL="$AWS_URL" \\
    -v "$PWD:/src:ro" -e PYTHONPATH=/src -w /src \\
    ghcr.io/viazoai/cpia-pipeline:latest \\
    /app/pipeline/.venv/bin/python scripts/fix_optimizer_diagnosis_regen.py --dry-run --limit-wp 3
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

from pipeline.agents.optimizer.prompt import DIAG_REGEN_PROMPT  # noqa: E402

DSN = os.environ.get("POSTGRES_URL") or os.environ.get("DEV_DB_URL")
DEMO_DATES = ("2025-09-20", "2025-09-21", "2025-09-22", "2025-09-23", "2025-09-24", "2025-09-25")


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


def _regen(azure: AzureOpenAI, model: str, wp_view: dict) -> str:
    """DIAG_REGEN_PROMPT 1회 호출 → 새 진단 2~3문장. fail 시 raise."""
    # 기존 진단(수치·원인 출처) + 헤드라인(이슈·만회일수) + 과거 사례/회복분포 + 만회방안 전달.
    cases = []
    for c in (wp_view.get("similar_cases") or [])[:3]:
        cases.append({
            "date": c.get("date"),
            "condition": c.get("condition"),
            "degraded": c.get("degraded"),
            "recovered": c.get("recovered"),
            "recovery_days": c.get("recovery_days"),
        })
    recs = []
    for r in (wp_view.get("recommendations") or [])[:3]:
        if isinstance(r, dict):
            recs.append({"keyword": r.get("keyword"), "action": r.get("action")})
    payload = {
        "existing_diagnosis": wp_view.get("diagnosis"),  # 수치(금일/계획 물량)·원인 출처
        "headline": wp_view.get("briefing_headline"),    # 이슈 + 만회 일수
        "similar_cases": cases,
        "recovery_pattern": wp_view.get("recovery_distribution_text"),
        "recommendations": recs,                          # 해결책(조치) 출처
    }
    resp = azure.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": DIAG_REGEN_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    out = json.loads(resp.choices[0].message.content)
    return (out.get("diagnosis") or "").strip()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="단일 날짜 (기본: 9/20~9/25)")
    parser.add_argument("--site", default=None)
    parser.add_argument("--dry-run", action="store_true", help="LLM 호출 + 미리보기, UPDATE 안 함")
    parser.add_argument("--limit-wp", type=int, default=None, help="WP N개만 (dry-run 점검용)")
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
    n_rows = n_fix = 0
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
                if not (wp_view.get("diagnosis") or "").strip():
                    continue
                try:
                    new_diag = _regen(azure, model, wp_view)
                except Exception as e:  # noqa: BLE001
                    print(f"  [SKIP] {r['report_date']} {wp_key}: {type(e).__name__}: {e}")
                    continue
                if not new_diag:
                    continue
                old = wp_view.get("diagnosis")
                wp_view["diagnosis"] = new_diag
                n_fix += 1
                if args.dry_run:
                    print(f"\n── {r['report_date']} {wp_key}")
                    print(f"   [헤드라인] {wp_view.get('briefing_headline')}")
                    print(f"   [전] {(old or '').replace(chr(10),' / ')[:220]}")
                    print(f"   [후] {new_diag}")

            if not args.dry_run:
                await conn.execute(
                    "UPDATE daily_reports SET optimizer_view_jsonb = $1::jsonb WHERE id = $2",
                    json.dumps(view, ensure_ascii=False),
                    r["id"],
                )
        verb = "재작성(미저장)" if args.dry_run else "재작성"
        print(f"\n=== 요약 === row {n_rows} / 진단 {verb} {n_fix}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
