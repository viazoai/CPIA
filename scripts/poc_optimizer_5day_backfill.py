"""PoC: 5일치 dummy_seed advice 를 실 cycle (forecaster + optimizer) 결과로 대체.

검증 목적: BE 가 진단/유사사례/권고/상세 등을 PG 에 우리가 원한 모양대로 적재하는가?

흐름:
  1. 5일치 dummy_seed run_id 의 optimizer_advice + forecasts DELETE
  2. 각 일자별:
     a. mapper_activities → Activity list (trade ∈ {건축, 토목}) 리히드레이션
     b. 새 run_id 로 pipeline_runs INSERT
     c. build_demo_graph (forecaster → hil_2 → optimizer → reporter) ainvoke
     d. interrupt 시 risky 전체 auto-select-all resume
  3. PG 변화 요약 출력

옵션:
  --sample-only       첫 1일 (9/22) 만 실행 — smoke test
  --dry-run           DB 변경 없이 후보만 출력
  --skip-delete       dummy advice DELETE 생략 (duplicate 위험)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.local")

from langgraph.types import Command  # noqa: E402

from pipeline.api import _build_prod_graph_config  # noqa: E402
from pipeline.db import PGClient  # noqa: E402
from pipeline.graph import build_demo_graph  # noqa: E402
from pipeline.state import Activity  # noqa: E402

SITE_ID = "m15x-ph3-ibl"
SAMPLE_DATE = date(2025, 9, 22)
TARGET_DATES = [
    date(2025, 9, 20),
    date(2025, 9, 21),
    date(2025, 9, 22),
    date(2025, 9, 23),
    date(2025, 9, 24),
]
TRADE_FILTER = ("건축", "토목")


def _dummy_seed_run_id(d: date) -> uuid.UUID:
    """seed_dummy_year.py:121 `_date_run_id` 와 동일 deterministic UUID."""
    raw = hashlib.sha256(f"dummy_seed|{d.isoformat()}".encode()).hexdigest()
    return uuid.UUID(raw[:32])


async def _delete_dummy_artifacts(pg: PGClient, dates: list[date]) -> None:
    print("\n--- dummy_seed optimizer_advice + forecasts DELETE ---")
    for d in dates:
        rid = _dummy_seed_run_id(d)
        n_adv = await pg._pool.fetchval(  # type: ignore[union-attr]
            "WITH d AS (DELETE FROM optimizer_advice WHERE run_id=$1 RETURNING 1) "
            "SELECT count(*) FROM d",
            rid,
        )
        n_fc = await pg._pool.fetchval(  # type: ignore[union-attr]
            "WITH d AS (DELETE FROM forecasts WHERE run_id=$1 RETURNING 1) "
            "SELECT count(*) FROM d",
            rid,
        )
        print(f"  {d}  run_id={rid}  advice_del={n_adv}  forecasts_del={n_fc}")


async def _hydrate_mapped(
    pg: PGClient, report_date: date, trades: tuple[str, ...]
) -> list[Activity]:
    """mapper_activities → Activity dict list. forecaster/optimizer 가 보는 필드 채움."""
    rows = await pg._pool.fetch(  # type: ignore[union-attr]
        """
        SELECT ma.zone, ma.bp_code, ma.company, ma.scope, ma.trade, ma.unit,
               ma.today_qty, ma.today_cum_qty, ma.yesterday_cum_qty,
               ma.plan_total_qty, ma.progress_percent, ma.remaining_qty,
               ma.remaining_percent, ma.note, ma.work_location_code,
               ma.wbs_mid_name, ma.l6_main, ma.conditions,
               ma.assigned_workers, ma.worker_source, ma.plan_mh,
               ma.wa, ma.mapping_conf, ma.mapping_source, ma.requires_review,
               pa.work_content, pa.l5_disc AS parser_l5_disc,
               pa.wbs_sub_name AS parser_wbs_sub_name,
               pa.wbs_detail_name AS parser_wbs_detail_name
        FROM mapper_activities ma
        JOIN pipeline_runs pr USING (run_id)
        LEFT JOIN parser_activities pa
          ON pa.run_id = ma.run_id AND pa.idx = ma.idx
        WHERE pr.site_id=$1 AND pr.report_date=$2
          AND ma.trade = ANY($3::text[])
        """,
        SITE_ID,
        report_date,
        list(trades),
    )
    mapped: list[Activity] = []
    for r in rows:
        d = dict(r)
        # conditions: jsonb → list[str]
        conds = d.get("conditions")
        if isinstance(conds, str):
            try:
                parsed = json.loads(conds)
                d["conditions"] = parsed if isinstance(parsed, list) else [str(parsed)]
            except Exception:
                d["conditions"] = [conds] if conds else []
        elif conds is None:
            d["conditions"] = []
        # parser JOIN 으로 들어온 필드 정리 (forecaster:277 `if not work_content: continue` 대비)
        d["work_content"] = d.get("work_content") or ""
        d["l5_disc"] = d.get("parser_l5_disc") or d.get("trade", "")
        d["wbs_sub_name"] = d.get("parser_wbs_sub_name")
        d["wbs_detail_name"] = d.get("parser_wbs_detail_name")
        d.pop("parser_l5_disc", None)
        d.pop("parser_wbs_sub_name", None)
        d.pop("parser_wbs_detail_name", None)
        # Activity TypedDict 필드 — mapper_activities 에 없는 필드 None/default
        d.setdefault("wbs_activity_id", None)
        d.setdefault("l7_sub", None)
        d.setdefault("l7_5_activity", None)
        d.setdefault("sub_work_area", None)
        d["worker_source"] = d.get("worker_source") or "mh_prorated"
        d["assigned_workers"] = float(d.get("assigned_workers") or 0.0)
        d["today_qty"] = float(d.get("today_qty") or 0.0)
        mapped.append(d)  # type: ignore[arg-type]
    return mapped


def _initial_state(
    run_id: uuid.UUID, report_date: date, mapped: list[Activity]
) -> dict:
    """build_demo_graph 진입 state."""
    return {
        "run_id": str(run_id),
        "date": report_date.isoformat(),
        "input_files": [],
        "site_id": SITE_ID,
        "raw_texts": {},
        "parsed": {
            "report_date": report_date.isoformat(),
            "project": "PoC",
            "bp_summaries": [],
            "job_allocations": [],
            "equipment_allocations": [],
            "activities": [],
            "worker_outputs": [],
            "report_meta": None,
        },
        "mapped": mapped,
        "hil_1_corrections": {},
        "atomized_ids": [],
        "report_md": "",
        "forecast": [],
        "hil_2_selection": [],
        "pre_optimizer_cases": {},
        "optimizer_advice": [],
        "current_node": "",
        "status": "running",
    }


async def _run_one_date(d: date, cfg, pg: PGClient) -> dict:
    print(f"\n=== {d} cycle ===")
    mapped = await _hydrate_mapped(pg, d, TRADE_FILTER)
    print(f"  mapped (건축+토목): {len(mapped)} rows")
    if not mapped:
        return {"date": d.isoformat(), "status": "skipped_no_mapped"}

    run_id = uuid.uuid4()
    await pg._pool.execute(  # type: ignore[union-attr]
        "INSERT INTO pipeline_runs (run_id, site_id, report_date, status) "
        "VALUES ($1, $2, $3, 'running')",
        run_id,
        SITE_ID,
        d,
    )

    graph = build_demo_graph(cfg)
    thread_id = f"poc-{run_id}"
    g_cfg = {"configurable": {"thread_id": thread_id}}
    state = _initial_state(run_id, d, mapped)

    print("  forecaster 호출 (LLM × group 수)...")
    first = await graph.ainvoke(state, config=g_cfg)
    if "__interrupt__" not in first:
        forecast = first.get("forecast", [])
        n_risky = sum(1 for r in forecast if r.get("risk_level") in {"주의", "이상"})
        print(f"  no interrupt — forecast={len(forecast)}, risky={n_risky}")
        return {
            "date": d.isoformat(),
            "status": "no_risky",
            "run_id": str(run_id),
            "forecast_n": len(forecast),
        }

    payload = first["__interrupt__"][0].value
    risky_groups = payload.get("risky_groups", [])
    print(f"  HIL_2 interrupt — risky_groups={len(risky_groups)}")
    selection = [
        g["key"]
        for g in risky_groups
        if g.get("note") not in {"no_main_unit", "cold_start_no_baseline"}
    ]
    skipped = len(risky_groups) - len(selection)
    print(f"  selection={len(selection)} (cold_start_skipped={skipped})")

    print(f"  optimizer 호출 (LLM × {len(selection)})...")
    final = await graph.ainvoke(Command(resume=selection), config=g_cfg)

    advice = final.get("optimizer_advice", [])
    n_cold = sum(
        1 for a in advice if str(a.get("diagnosis", "")).startswith("신규 작업")
    )
    n_llm = len(advice) - n_cold
    print(
        f"  → optimizer_advice rows={len(advice)} (LLM-driven={n_llm}, cold_start={n_cold})"
    )

    # 샘플 advice 1건 미리 보기
    if advice:
        sample = next(
            (a for a in advice if not str(a.get("diagnosis", "")).startswith("신규")),
            advice[0],
        )
        diag = sample.get("diagnosis", "")
        recs = sample.get("recommendations", [])
        print(f"  sample [{sample.get('company')}|{sample.get('l6_main')}]:")
        print(f"    diagnosis ({len(diag)}자): {diag[:200]}")
        if recs:
            first_rec = recs[0]
            print(f"    rec[0]: {json.dumps(first_rec, ensure_ascii=False)[:250]}")

    return {
        "date": d.isoformat(),
        "status": "ok",
        "run_id": str(run_id),
        "advice_n": len(advice),
        "llm_n": n_llm,
        "cold_start_n": n_cold,
        "risky_n": len(risky_groups),
    }


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sample-only", action="store_true", help="1일만 실행 (9/22)")
    p.add_argument("--dry-run", action="store_true", help="DB 미변경, 후보만 출력")
    p.add_argument("--skip-delete", action="store_true", help="dummy DELETE 생략")
    args = p.parse_args()

    dates = [SAMPLE_DATE] if args.sample_only else TARGET_DATES
    print(f"PoC dates: {[d.isoformat() for d in dates]}")
    print(f"trade filter: {TRADE_FILTER}")

    if args.dry_run:
        print("(dry-run — DB 변경 없음)")
        return

    cfg = _build_prod_graph_config()
    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        if not args.skip_delete:
            await _delete_dummy_artifacts(pg, dates)

        results = []
        for d in dates:
            r = await _run_one_date(d, cfg, pg)
            results.append(r)

        print("\n=== 요약 ===")
        for r in results:
            print(f"  {r}")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
