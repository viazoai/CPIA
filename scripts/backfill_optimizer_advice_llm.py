"""backfill_optimizer_advice_llm.py — 일반화 backfill orchestrator.

PoC (poc_optimizer_5day_backfill.py) 를 15일 범용으로 확장.

흐름 (일자별):
  1. --clean 시 같은 (site, date) 의 이전 run_id 결과 cascade DELETE
  2. mapper_activities hydrate
  3. 새 run_id 로 pipeline_runs INSERT
  4. build_atomized_demo_graph.ainvoke (forecaster -> hil_2 -> optimizer -> reporter)
  5. HIL_2 interrupt -> risky_groups auto-select -> Command(resume=selection) 재개
  6. backfill_v2.py 자동 호출 (없으면 warn + skip)

모든 일자 완료 후:
  - verify_backfill_passing.py 호출 (T9 생성 예정 — 없으면 warn + skip)

옵션:
  --days N            최근 N일 (기본 15). --start-date/--end-date 와 상호 배타.
  --start-date DATE   범위 시작 (YYYY-MM-DD)
  --end-date DATE     범위 끝 (YYYY-MM-DD)
  --site SITE_ID      현장 ID (기본 m15x-ph3-ibl)
  --trades T1,T2      공종 목록 (기본 건축,토목)
  --clean             이전 run_id 결과 cascade DELETE 후 재실행 (멱등)
  --dry-run           DB 변경 없이 후보 dates 만 출력
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.local")


from pipeline.api import _build_prod_graph_config  # noqa: E402
from pipeline.db import PGClient  # noqa: E402
from pipeline.graph import build_atomized_demo_graph  # noqa: E402
from pipeline.state import Activity  # noqa: E402

DEFAULT_SITE_ID = "m15x-ph3-ibl"
# 2026-05-27 Task 20: 시연 윈도우 (7/1~9/24) backfill default — seed_dummy_year (Task 19)
# 1차 filter 와 짝. 6월 이전 backfill 시 사용자가 --trades 로 override 가능.
DEFAULT_TRADES = ("건축", "토목")
DEFAULT_DAYS = 15


# ---------------------------------------------------------------------------
# SQL builder (pure — 테스트 가능)
# ---------------------------------------------------------------------------


def _delete_previous_artifacts_statements(
    site_id: str, target_date: date
) -> list[tuple[str, list]]:
    """artifacts (advice/forecasts/daily_reports) DELETE 3 statement 반환.

    advice -> forecasts -> daily_reports

    *** pipeline_runs 자체는 DELETE 안 함 ***
    이유: pipeline_runs.run_id 가 mapper_activities + parser_activities + collector_artifacts
    의 FK (ON DELETE CASCADE, infra/postgres/init.sql:53). DELETE FROM pipeline_runs
    WHERE site_id+date 시 해당 일자의 mapper_activities 통째로 cascade 삭제. mapper_activities
    는 backfill 의 hydrate source — 보존 필수.

    target_date: datetime.date (asyncpg 가 PG DATE 컬럼에 직접 bind).
                 str 받으면 datetime.date 로 변환 — 호출자 편의.
    """
    if isinstance(target_date, str):
        from datetime import datetime as _dt

        target_date = _dt.strptime(target_date, "%Y-%m-%d").date()
    sub = "SELECT run_id FROM pipeline_runs WHERE site_id=$1 AND report_date=$2"
    params = [site_id, target_date]
    return [
        (f"DELETE FROM optimizer_advice WHERE run_id IN ({sub})", params),
        (f"DELETE FROM forecasts WHERE run_id IN ({sub})", params),
        (f"DELETE FROM daily_reports WHERE run_id IN ({sub})", params),
    ]


# ---------------------------------------------------------------------------
# PoC 패턴 그대로 차용
# ---------------------------------------------------------------------------


def _dummy_seed_run_id(d: date) -> uuid.UUID:
    """seed_dummy_year.py:121 `_date_run_id` 와 동일 deterministic UUID."""
    raw = hashlib.sha256(f"dummy_seed|{d.isoformat()}".encode()).hexdigest()
    return uuid.UUID(raw[:32])


async def _delete_previous_artifacts(
    pg: PGClient, site_id: str, target_date: date
) -> None:
    """_delete_previous_artifacts_statements 의 SQL 을 asyncpg 로 순차 실행."""
    print(f"\n--- {target_date} cascade DELETE (site={site_id}) ---")
    stmts = _delete_previous_artifacts_statements(site_id, target_date)
    for sql, params in stmts:
        await pg._pool.execute(sql, *params)  # type: ignore[union-attr]
        print(f"  OK: {sql[:60]}...")


async def _hydrate_mapped(
    pg: PGClient, report_date: date, site_id: str, trades: tuple[str, ...]
) -> list[Activity]:
    """mapper_activities -> Activity dict list. forecaster/optimizer 가 보는 필드 채움."""
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
        site_id,
        report_date,
        list(trades),
    )
    mapped: list[Activity] = []
    for r in rows:
        d = dict(r)
        # conditions: jsonb -> list[str]
        conds = d.get("conditions")
        if isinstance(conds, str):
            try:
                parsed = json.loads(conds)
                d["conditions"] = parsed if isinstance(parsed, list) else [str(parsed)]
            except Exception:
                d["conditions"] = [conds] if conds else []
        elif conds is None:
            d["conditions"] = []
        # parser JOIN 으로 들어온 필드 정리
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
    run_id: uuid.UUID, report_date: date, mapped: list[Activity], site_id: str
) -> dict:
    """build_atomized_demo_graph 진입 state."""
    return {
        "run_id": str(run_id),
        "date": report_date.isoformat(),
        "input_files": [],
        "site_id": site_id,
        "raw_texts": {},
        "parsed": {
            "report_date": report_date.isoformat(),
            "project": "backfill",
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


async def _run_one_date(
    d: date, cfg, pg: PGClient, site_id: str, trades: tuple[str, ...]
) -> dict:
    print(f"\n=== {d} cycle ===")
    mapped = await _hydrate_mapped(pg, d, site_id, trades)
    print(f"  mapped ({'+'.join(trades)}): {len(mapped)} rows")
    if not mapped:
        return {"date": d.isoformat(), "status": "skipped_no_mapped"}

    run_id = uuid.uuid4()
    await pg._pool.execute(  # type: ignore[union-attr]
        "INSERT INTO pipeline_runs (run_id, site_id, report_date, status) "
        "VALUES ($1, $2, $3, 'running')",
        run_id,
        site_id,
        d,
    )

    graph = build_atomized_demo_graph(cfg)
    thread_id = f"backfill-{run_id}"
    g_cfg = {"configurable": {"thread_id": thread_id}}
    state = _initial_state(run_id, d, mapped, site_id)

    # 2026-05-26: hil_2 interrupt 폐기 — 모든 forecast wp 자동 선택 후 optimizer 직행.
    # graph.ainvoke 1회로 forecaster→hil_2→optimizer 전체 완주.
    print("  forecaster→hil_2(auto)→optimizer 호출...")
    final = await graph.ainvoke(state, config=g_cfg)

    advice = final.get("optimizer_advice", [])
    n_cold = sum(
        1 for a in advice if str(a.get("diagnosis", "")).startswith("신규 작업")
    )
    n_llm = len(advice) - n_cold
    print(
        f"  -> optimizer_advice rows={len(advice)} (LLM-driven={n_llm}, cold_start={n_cold})"
    )

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

    forecast = final.get("forecast", [])
    return {
        "date": d.isoformat(),
        "status": "ok",
        "run_id": str(run_id),
        "advice_n": len(advice),
        "llm_n": n_llm,
        "cold_start_n": n_cold,
        "forecast_n": len(forecast),
    }


def _call_backfill_v2(d: date, site_id: str) -> None:
    """각 일자 완료 후 daily_reports jsonb 재산출 (kpi/quadrant/optimizer_view 등).

    2026-05-23: backfill_v2.py (legacy) 가 아니라 backfill_daily_report_views_v2.py
    호출. --with-summary 옵션으로 Optimizer site_summary LLM (21c10f7) 까지
    같이 호출 -> daily_reports.site_summary_text 박힘 -> FE narrative 표시.

    PYTHONPATH 설정 필요 (script 가 pipeline.* import).
    """
    script = ROOT / "scripts" / "backfill_daily_report_views_v2.py"
    if not script.exists():
        print(f"  [warn] backfill_daily_report_views_v2.py not found — skip ({d})")
        return
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--date",
            d.isoformat(),
            "--site",
            site_id,
            "--with-summary",
        ],
        capture_output=False,
        env=env,
    )
    if result.returncode != 0:
        print(
            f"  [warn] backfill_daily_report_views_v2 exited {result.returncode} for {d}"
        )


def _call_verify_backfill(start: date, end: date, site_id: str) -> None:
    """모든 일자 완료 후 verify_backfill_passing.py 호출. T9 생성 예정 — 없으면 warn."""
    script = ROOT / "scripts" / "verify_backfill_passing.py"
    if not script.exists():
        print("[warn] verify_backfill_passing.py not found (T9 예정) — skip")
        return
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--start-date",
            start.isoformat(),
            "--end-date",
            end.isoformat(),
            "--site",
            site_id,
        ],
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"[warn] verify_backfill_passing.py exited {result.returncode}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def main() -> None:
    p = argparse.ArgumentParser(
        description="Generalized backfill orchestrator — LLM advice per date."
    )
    p.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"최근 N일 (기본 {DEFAULT_DAYS}). --start-date/--end-date 와 상호 배타.",
    )
    p.add_argument("--start-date", help="범위 시작 YYYY-MM-DD")
    p.add_argument("--end-date", help="범위 끝 YYYY-MM-DD")
    p.add_argument("--site", default=DEFAULT_SITE_ID, help="현장 ID")
    p.add_argument(
        "--trades",
        default=",".join(DEFAULT_TRADES),
        help="공종 목록 쉼표 구분 (기본 건축,토목)",
    )
    p.add_argument(
        "--clean",
        action="store_true",
        help="같은 (site, date) 이전 run 결과 cascade DELETE 후 재실행 (멱등)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="DB 변경 없이 후보 dates 만 출력",
    )
    args = p.parse_args()

    trades = tuple(t.strip() for t in args.trades.split(",") if t.strip())
    site_id = args.site

    # date range 파싱
    if args.start_date and args.end_date:
        from datetime import datetime

        start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(args.end_date, "%Y-%m-%d").date()
        dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    else:
        end = date.today()
        start = end - timedelta(days=args.days - 1)
        dates = [start + timedelta(days=i) for i in range(args.days)]

    print(f"backfill dates ({len(dates)}): {[d.isoformat() for d in dates]}")
    print(f"site: {site_id}  trades: {trades}")

    if args.dry_run:
        print("dry-run — DB 변경 없음")
        return

    cfg = _build_prod_graph_config()
    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        results = []
        for d in dates:
            if args.clean:
                await _delete_previous_artifacts(pg, site_id, d)

            r = await _run_one_date(d, cfg, pg, site_id, trades)
            results.append(r)

            # 각 일자 완료 후 backfill_v2.py 호출
            _call_backfill_v2(d, site_id)

        print("\n=== 요약 ===")
        for r in results:
            print(f"  {r}")

        # 모든 일자 완료 후 verify_backfill_passing.py 호출
        _call_verify_backfill(dates[0], dates[-1], site_id)

    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
