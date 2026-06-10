"""기존 daily_reports 의 optimizer_view 를 제자리로 (a) 만회방안 자연체 재작성 +
(b) 경영진 브리핑 한 단락 생성 으로 교정. (2026-06-10 A+C)

배경: "리스크 및 대안 검토" 진단을 룰베이스 전보문 대신 LLM 종합 브리핑 느낌으로
다듬는다(A+C). 코드/프롬프트는 전체 공통이지만, 이미 적재된 시연 데이터(9/24·9/25)는
파이프라인 재실행 없이 화면에 바로 반영해야 한다. recovery_days 인플레이스 교정과 동일
전략 — 단, 이번엔 LLM 1회/WP 를 호출(MIGRATION_POLISH_PROMPT).

입력은 optimizer_view_jsonb.by_wp[wp] 의 기존 데이터(진단/유사사례/권고/상세) + scenarios
의 AI 만회일수. 사실·숫자는 보존, 톤만 자연체로 바꾸고 브리핑을 종합한다.
diagnosis·similar_cases·details 등 나머지는 무손상.

사용 (pipeline 컨테이너 이미지로 실행 — Azure/asyncpg/dotenv 포함):
  docker run --rm --env-file .env -e POSTGRES_URL="$AWS_URL" -e PYTHONPATH=/app -w /app \\
    -v "$PWD/scripts:/app/scripts:ro" \\
    ghcr.io/viazoai/cpia-pipeline:latest \\
    /app/pipeline/.venv/bin/python scripts/fix_optimizer_briefing_inplace.py --dry-run
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

from pipeline.agents.optimizer.prompt import MIGRATION_POLISH_PROMPT  # noqa: E402

DSN = os.environ.get("POSTGRES_URL") or os.environ.get("DEV_DB_URL")
DEMO_DATES = ("2025-09-24", "2025-09-25")


def _as_obj(v):
    if v is None:
        return None
    return json.loads(v) if isinstance(v, str) else v


def _detail(details: list, label: str) -> str | None:
    for d in details or []:
        if d.get("label") == label:
            return d.get("value")
    return None


def _azure() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    )


def _polish_one(azure: AzureOpenAI, model: str, wp_view: dict, ai_recovery_days) -> dict:
    """MIGRATION_POLISH_PROMPT 1회 호출 → {briefing, recommendations}. fail 시 raise."""
    details = wp_view.get("details") or []
    payload = {
        "diagnosis": wp_view.get("diagnosis"),
        "similar_cases": wp_view.get("similar_cases") or [],
        "recovery_pattern": wp_view.get("recovery_distribution_text"),
        "details": {
            "wp": _detail(details, "진단 대상"),
            "plan_period": _detail(details, "공사기간"),
            "plan_productivity": _detail(details, "계획 생산성"),
            "today_productivity": _detail(details, "금일 생산성"),
            "schedule_impact": _detail(details, "일정 영향"),
            "schedule_basis": _detail(details, "산출근거"),
        },
        "ai_recovery_days": ai_recovery_days,
        "recommendations": wp_view.get("recommendations") or [],
    }
    resp = azure.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": MIGRATION_POLISH_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def _merge_recs(old: list, new: list) -> list:
    """LLM 이 돌려준 자연체 action/reason 을 기존 rank/keyword 에 매핑(순서 기준).

    keyword 가 비거나 어긋나면 기존 keyword 보존 — 사실 손상 방지.
    new 가 부족하면 그 항목은 기존 그대로 유지.
    """
    merged = []
    for i, o in enumerate(old or []):
        if not isinstance(o, dict):
            merged.append(o)
            continue
        n = new[i] if i < len(new) and isinstance(new[i], dict) else {}
        merged.append({
            "rank": o.get("rank", i + 1),
            "keyword": o.get("keyword"),  # 기존 keyword 보존 (사실)
            "action": (n.get("action") or o.get("action")),
            "reason": (n.get("reason") or o.get("reason")),
        })
    return merged


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="단일 날짜 (기본: 9/24+9/25)")
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
        "SELECT dr.id, pr.site_id, pr.report_date, "
        "       dr.optimizer_view_jsonb, dr.scenarios_jsonb "
        "FROM daily_reports dr JOIN pipeline_runs pr USING (run_id) "
        "WHERE " + " AND ".join(where) + " ORDER BY pr.report_date, pr.site_id"
    )

    conn = await asyncpg.connect(DSN)
    n_rows = n_wp = n_brief = 0
    try:
        rows = await conn.fetch(sql, *params)
        print(f"대상 daily_reports row: {len(rows)}  dates={dates}  (dry-run={args.dry_run})")
        for r in rows:
            view = _as_obj(r["optimizer_view_jsonb"]) or {}
            scen = _as_obj(r["scenarios_jsonb"]) or {}
            by_wp = view.get("by_wp") or {}
            scen_by_wp = scen.get("by_wp") or {}
            if not by_wp:
                continue
            n_rows += 1
            wp_items = list(by_wp.items())
            if args.limit_wp:
                wp_items = wp_items[: args.limit_wp]
            for wp_key, wp_view in wp_items:
                ai_rd = (
                    ((scen_by_wp.get(wp_key) or {}).get("base_p50") or {}).get("recovery_days")
                )
                try:
                    out = _polish_one(azure, model, wp_view, ai_rd)
                except Exception as e:  # noqa: BLE001
                    print(f"  [SKIP] {r['report_date']} {wp_key}: {type(e).__name__}: {e}")
                    continue
                briefing = (out.get("briefing") or "").strip()
                headline = (out.get("headline") or "").strip()
                new_recs = out.get("recommendations") or []
                if briefing:
                    wp_view["briefing"] = briefing
                    n_brief += 1
                if headline:
                    wp_view["briefing_headline"] = headline
                if new_recs:
                    wp_view["recommendations"] = _merge_recs(
                        wp_view.get("recommendations") or [], new_recs
                    )
                n_wp += 1
                if args.dry_run:
                    print(f"\n── {r['report_date']} {wp_key}")
                    print(f"   헤드라인: {headline}")
                    print(f"   브리핑: {briefing[:200]}")
                    if new_recs and isinstance(new_recs[0], dict):
                        print(f"   만회방안1: [{new_recs[0].get('keyword')}] {str(new_recs[0].get('action'))[:120]}")

            if not args.dry_run:
                await conn.execute(
                    "UPDATE daily_reports SET optimizer_view_jsonb = $1::jsonb WHERE id = $2",
                    json.dumps(view, ensure_ascii=False),
                    r["id"],
                )
        verb = "처리(미저장)" if args.dry_run else "저장"
        print(f"\n=== 요약 === row {n_rows} / WP {verb} {n_wp} / 브리핑 {n_brief}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
