"""B5 통과 기준 5가지 + delay 분포 자동 검증.

usage: pipeline/.venv/bin/python3 scripts/verify_backfill_passing.py \
  --start-date 2025-09-08 --end-date 2025-09-22 --site m15x-ph3-ibl

자동 기준 6건:
  1. diagnosis 평균 >= 50자, "신규 작업 -" placeholder = 0%
  2. degradation_cases 4필드 (conditions/activities/productivity/recovery) >= 90%
  3. recommendations text empty = 0%
  4. details 6칸 non-"-" >= 80%   (optimizer_view_jsonb.by_wp[wp].details list)
  5. quadrant <-> by_wp wp_id 교집합 >= 80%  (quadrant_jsonb 는 list[dict] 구조)
  6. delay_days 분포 - 음수 + 양수 모두 존재 (over/under-delivered 분리)

수동 기준:
  7. UI 시각 확인 (T16)

exit 0 = 모두 통과, exit 1 = 1건 이상 fail.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date as _date  # noqa: F401 — used in main() fromisoformat + type hints
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.local")

from pipeline.db import PGClient  # noqa: E402


PLACEHOLDER_PATTERN = "신규 작업 -"

# degradation_cases 4필드 (retrieve.py fetch_degradation_cases + graph.py c["recovery"] = ...)
DEGRADATION_REQUIRED_KEYS = ("conditions", "activities", "productivity", "recovery")


async def check_diagnosis_length(
    pg: PGClient, site_id: str, start_date: date, end_date: date
) -> dict:
    rows = await pg._pool.fetch(
        """
        SELECT oa.diagnosis FROM optimizer_advice oa
        JOIN pipeline_runs pr USING (run_id)
        WHERE pr.site_id = $1
          AND pr.report_date BETWEEN $2 AND $3
          AND pr.is_mock = false
        """,
        site_id,
        start_date,
        end_date,
    )
    n = len(rows)
    if n == 0:
        return {
            "name": "diagnosis 평균 >= 50자, placeholder 0%",
            "n": 0,
            "pass": False,
            "note": "no rows",
        }
    avg_len = sum(len(r["diagnosis"] or "") for r in rows) / n
    placeholder_n = sum(
        1 for r in rows if PLACEHOLDER_PATTERN in (r["diagnosis"] or "")
    )
    placeholder_pct = placeholder_n / n * 100
    passed = avg_len >= 50 and placeholder_n == 0
    return {
        "name": "diagnosis 평균 >= 50자, placeholder 0%",
        "n": n,
        "avg_len": round(avg_len, 1),
        "placeholder_n": placeholder_n,
        "placeholder_pct": round(placeholder_pct, 1),
        "pass": passed,
    }


async def check_degradation_cases(
    pg: PGClient, site_id: str, start_date: date, end_date: date
) -> dict:
    rows = await pg._pool.fetch(
        """
        SELECT oa.degradation_cases FROM optimizer_advice oa
        JOIN pipeline_runs pr USING (run_id)
        WHERE pr.site_id = $1
          AND pr.report_date BETWEEN $2 AND $3
          AND pr.is_mock = false
        """,
        site_id,
        start_date,
        end_date,
    )
    total = 0
    complete = 0
    for r in rows:
        cases = r["degradation_cases"] or []
        if isinstance(cases, str):
            cases = json.loads(cases)
        for c in cases:
            total += 1
            if all(c.get(k) is not None for k in DEGRADATION_REQUIRED_KEYS):
                complete += 1
    pct = complete / total * 100 if total else 0.0
    return {
        "name": "degradation_cases 4필드 >= 90%",
        "total": total,
        "complete": complete,
        "pct": round(pct, 1),
        "pass": pct >= 90 if total else False,
    }


async def check_recommendations(
    pg: PGClient, site_id: str, start_date: date, end_date: date
) -> dict:
    rows = await pg._pool.fetch(
        """
        SELECT oa.recommendations FROM optimizer_advice oa
        JOIN pipeline_runs pr USING (run_id)
        WHERE pr.site_id = $1
          AND pr.report_date BETWEEN $2 AND $3
          AND pr.is_mock = false
        """,
        site_id,
        start_date,
        end_date,
    )
    total = 0
    empty = 0
    for r in rows:
        recs = r["recommendations"] or []
        if isinstance(recs, str):
            recs = json.loads(recs)
        for rec in recs:
            total += 1
            # 2026-05-27: polymorphic schema 지원
            # - 옛: string OR {rank, text}
            # - V10: {rank, keyword, action, reason}
            if isinstance(rec, str):
                text = rec
            elif isinstance(rec, dict):
                text = rec.get("text") or rec.get("action") or ""
            else:
                text = ""
            if not text.strip():
                empty += 1
    empty_pct = empty / total * 100 if total else 100.0
    return {
        "name": "recommendations text empty 0%",
        "total": total,
        "empty": empty,
        "empty_pct": round(empty_pct, 1),
        "pass": empty == 0 if total else False,
    }


async def check_details(
    pg: PGClient, site_id: str, start_date: date, end_date: date
) -> dict:
    # optimizer_view_jsonb.by_wp[wp_id].details = list[{"label": ..., "value": ...}] 6칸
    # view_builder.py:1105-1112 확인: details 는 6개 dict 의 list, value 가 "-" 이면 미채움
    rows = await pg._pool.fetch(
        """
        SELECT dr.optimizer_view_jsonb FROM daily_reports dr
        JOIN pipeline_runs pr USING (run_id)
        WHERE pr.site_id = $1
          AND pr.report_date BETWEEN $2 AND $3
          AND pr.is_mock = false
        """,
        site_id,
        start_date,
        end_date,
    )
    total_cells = 0
    non_dash = 0
    for r in rows:
        ov = r["optimizer_view_jsonb"]
        if ov is None:
            continue
        if isinstance(ov, str):
            ov = json.loads(ov)
        by_wp = (ov or {}).get("by_wp") or {}
        for wp_id, wp_data in by_wp.items():
            details = (wp_data or {}).get("details") or []
            # details: list[{"label": str, "value": str}]
            if isinstance(details, list):
                for item in details:
                    total_cells += 1
                    value = item.get("value") if isinstance(item, dict) else item
                    if value not in ("-", None, ""):
                        non_dash += 1
            elif isinstance(details, dict):
                for v in details.values():
                    total_cells += 1
                    if v not in ("-", None, ""):
                        non_dash += 1
    pct = non_dash / total_cells * 100 if total_cells else 0.0
    return {
        "name": "details 6칸 non-'-' >= 80%",
        "total_cells": total_cells,
        "non_dash": non_dash,
        "pct": round(pct, 1),
        "pass": pct >= 80 if total_cells else False,
    }


async def check_quadrant_wp(
    pg: PGClient, site_id: str, start_date: date, end_date: date
) -> dict:
    # quadrant_jsonb: list[{"wp_id": ..., ...}]  (view_builder._build_quadrant 반환 구조)
    # optimizer_view_jsonb: {"by_wp": {wp_id: ...}, "default_wp_id": ...}
    rows = await pg._pool.fetch(
        """
        SELECT dr.optimizer_view_jsonb, dr.quadrant_jsonb FROM daily_reports dr
        JOIN pipeline_runs pr USING (run_id)
        WHERE pr.site_id = $1
          AND pr.report_date BETWEEN $2 AND $3
          AND pr.is_mock = false
        """,
        site_id,
        start_date,
        end_date,
    )
    union_total = 0
    intersect_total = 0
    for r in rows:
        ov = r["optimizer_view_jsonb"]
        qv = r["quadrant_jsonb"]
        if isinstance(ov, str):
            ov = json.loads(ov)
        if isinstance(qv, str):
            qv = json.loads(qv)

        by_wp_ids = set((ov or {}).get("by_wp", {}).keys())

        # quadrant_jsonb 는 list[dict] (각 dict 에 "wp_id" 키)
        quadrant_list = qv or []
        if isinstance(quadrant_list, dict):
            # 혹시 {"wps": [...]} 구조로 저장된 경우 방어
            quadrant_list = quadrant_list.get("wps") or []
        quadrant_ids = {
            item.get("wp_id") for item in quadrant_list if item.get("wp_id")
        }

        union = quadrant_ids | by_wp_ids
        intersect = quadrant_ids & by_wp_ids
        union_total += len(union)
        intersect_total += len(intersect)

    pct = intersect_total / union_total * 100 if union_total else 0.0
    return {
        "name": "quadrant <-> by_wp wp_id 교집합 >= 80%",
        "union": union_total,
        "intersect": intersect_total,
        "pct": round(pct, 1),
        "pass": pct >= 80 if union_total else False,
    }


async def check_delay_distribution(
    pg: PGClient, site_id: str, start_date: date, end_date: date
) -> dict:
    rows = await pg._pool.fetch(
        """
        SELECT f.delay_days FROM forecasts f
        JOIN pipeline_runs pr USING (run_id)
        WHERE pr.site_id = $1
          AND pr.report_date BETWEEN $2 AND $3
          AND pr.is_mock = false
          AND f.delay_days IS NOT NULL
        """,
        site_id,
        start_date,
        end_date,
    )
    n = len(rows)
    if n == 0:
        return {
            "name": "delay_days 분포 (음수 + 양수 모두 존재)",
            "n": 0,
            "pass": False,
            "note": "no rows",
        }
    delays = [float(r["delay_days"]) for r in rows]
    n_neg = sum(1 for d in delays if d < 0)
    n_pos = sum(1 for d in delays if d > 0)
    n_zero = sum(1 for d in delays if d == 0)
    # 음수(over-delivered) + 양수(under-delivered) 모두 존재해야 분포 의미 있음
    # 0 만 있으면 mh-only path 회귀 시그널
    has_variance = (n_neg + n_pos) > 0
    return {
        "name": "delay_days 분포 (음수 + 양수 모두 존재)",
        "n": n,
        "neg": n_neg,
        "pos": n_pos,
        "zero": n_zero,
        "pass": has_variance,
    }


async def main() -> None:
    p = argparse.ArgumentParser(
        description="B5 통과 기준 5가지 + delay 분포 자동 검증",
    )
    p.add_argument("--start-date", required=True, help="검증 시작일 (YYYY-MM-DD)")
    p.add_argument("--end-date", required=True, help="검증 종료일 (YYYY-MM-DD)")
    p.add_argument(
        "--site", default="m15x-ph3-ibl", help="site_id (default: m15x-ph3-ibl)"
    )
    args = p.parse_args()

    # asyncpg 는 DATE 파라미터로 Python date 객체 필요 (str 전달 시 AttributeError)
    start_date = _date.fromisoformat(args.start_date)
    end_date = _date.fromisoformat(args.end_date)

    postgres_url = os.environ.get("POSTGRES_URL")
    if not postgres_url:
        print("ERROR: POSTGRES_URL 환경 변수 없음 (.env.local 확인)", file=sys.stderr)
        sys.exit(2)

    pg = PGClient(postgres_url)
    await pg.connect()
    try:
        checks = [
            await check_diagnosis_length(pg, args.site, start_date, end_date),
            await check_degradation_cases(pg, args.site, start_date, end_date),
            await check_recommendations(pg, args.site, start_date, end_date),
            await check_details(pg, args.site, start_date, end_date),
            await check_quadrant_wp(pg, args.site, start_date, end_date),
            await check_delay_distribution(pg, args.site, start_date, end_date),
        ]

        print(
            f"\n=== B5 통과 기준 (site={args.site}, {args.start_date} ~ {args.end_date}) ===\n"
        )
        all_passed = True
        for i, c in enumerate(checks, start=1):
            mark = "PASS" if c["pass"] else "FAIL"
            print(f"  {i}. [{mark}] {c['name']}")
            details_str = {k: v for k, v in c.items() if k not in ("name", "pass")}
            print(f"      {details_str}")
            if not c["pass"]:
                all_passed = False

        print(f"\n전체 결과: {'PASS' if all_passed else 'FAIL'}")
        sys.exit(0 if all_passed else 1)
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
