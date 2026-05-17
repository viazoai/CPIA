"""가짜 작업일보 + 데모 CLI — Parser/Mapper skip, Activity 직접 주입.

Spec: docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §10

동기 (§10.1):
- 9/25 남웅 작업일보 sheet4 today_qty ≈ 0 → Forecaster cold_start → risk_level="정상" →
  hil_2 risky=[] → Optimizer 미진입. 데모 시연 불가.
- 가짜 작업일보 (9/26 or 9/27) 로 today_qty>0 + 장비대기/돌관 conditions trigger.

generate_fake_daily_report (§10.2):
- 인자: report_date / scenarios (company, l6_main, n_activities, incident, productivity_ratio,
  workers_ratio, unit) / activity_pools / baseline_workers / baseline_qty.
- 반환: list[Activity] (mapper output 형식 — atomizer/forecaster 호환).
- work_content = l7_5_activity 단순 활동명 (결정 #22).
- conditions = list[str] — state.Activity 계약 (forecaster:92 가 iterate). spec §10.2 본문은
  str 로 적혀 있으나 production type contract (state.py Activity.conditions: list[str]) +
  atomizer.py:58 (",".join) 와 forecaster.py:92 (for c in a["conditions"]) 가 list 를 요구.
  fake row 만 str 박으면 forecaster 가 문자 1개씩 iterate 해서 깨짐. list 로 맞춘다.
- assigned_workers = baseline_workers × workers_ratio (돌관 시 1.3).
- today_qty = baseline_qty × productivity_ratio (저하 시 0.45 등).

CLI (§10.4 + plan step 11.3):
- 첫 step: synthetic v2 적재 확인 (worker_source="synthetic_v2", limit=1) — 0 hit → abort.
- sites ON CONFLICT DO NOTHING 사전 INSERT (DEMO_SITE default).
- pg.insert_pipeline_run(run_id, site_id, date, status='running').
- generate_fake_daily_report → mapped Activity list.
- build_demo_graph(cfg).ainvoke({"run_id", "date", "mapped", ...}, thread_id=run_id).
- __interrupt__ payload 출력.
- --auto-select-all flag → 자동 Command(resume=[모든 risky key]) (interactive 우회).
- result["optimizer_advice"] 출력 + advice 1건 이상 검증.

scenario CLI 포맷: company|l6_main|n_activities|incident|productivity_ratio|workers_ratio|unit
예) "남웅건설|철근콘크리트공사|5|돌관|0.45|1.3|m3"
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import uuid

from pipeline.agents.optimizer.synthetic_v2 import _BP_TOTAL
from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient
from pipeline.state import Activity


def generate_fake_daily_report(
    report_date: str,
    scenarios: list[dict],
    activity_pools: dict[tuple[str, str], list[str]],
    baseline_workers: dict[tuple[str, str], float],
    baseline_qty: dict[tuple[str, str, str], float],
    seed: int = 42,
) -> list[Activity]:
    """Activity list 직접 생성 (§10.2 그대로).

    scenarios 예 (§10.2):
        {"company": "남웅건설", "l6_main": "철근콘크리트공사",
         "n_activities": 5, "incident": "장비대기",
         "productivity_ratio": 0.45, "workers_ratio": 1.0, "unit": "m3"}

    반환: list[Activity] — mapper output 형식. atomizer/forecaster 호환.
    """
    activities: list[Activity] = []
    rng = random.Random(seed)
    for sc in scenarios:
        key = (sc["company"], sc["l6_main"])
        pool = activity_pools.get(key) or [f"{sc['l6_main']} 작업"]
        base_workers = baseline_workers.get(key, 0.0)
        qty_key = (sc["company"], sc["l6_main"], sc["unit"])
        baseline_q = baseline_qty.get(qty_key, 0.0)
        for _ in range(sc["n_activities"]):
            activity_name = rng.choice(pool)
            cond = sc["incident"]
            today_qty = round(baseline_q * sc["productivity_ratio"] / sc["n_activities"], 1)

            # conditions list[str] (state.Activity 계약 — forecaster:92 iterate)
            conditions_list = ["맑음"] + ([cond] if cond != "정상" else [])

            # workers_ratio scenario 파라미터 (돌관 spike × 1.3)
            assigned_workers = round(base_workers * sc["workers_ratio"], 1)

            activities.append(
                {
                    "wbs_activity_id": None,
                    "l7_sub": None,
                    "l7_5_activity": None,
                    "sub_work_area": None,
                    "l5_disc": "건축" if "철근" in sc["l6_main"] else "설비",
                    "l6_main": sc["l6_main"],
                    "wa": "CUB",
                    "mapping_conf": 0.85,
                    "mapping_source": "fake_daily_report",
                    "requires_review": False,
                    "trade": sc["l6_main"],
                    "company": sc["company"],
                    "unit": sc["unit"],
                    "today_qty": today_qty,
                    "work_content": activity_name,
                    "conditions": conditions_list,
                    "assigned_workers": assigned_workers,
                    "worker_source": "mh_prorated",
                    "plan_total_qty": None,
                    "plan_mh": None,
                }
            )
    return activities


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def _parse_scenario(raw: str) -> dict:
    """company|l6_main|n_activities|incident|productivity_ratio|workers_ratio|unit"""
    parts = raw.split("|")
    if len(parts) != 7:
        raise ValueError(
            f"scenario 형식 오류 — 7개 필드 필요 (company|l6_main|n_activities|"
            f"incident|productivity_ratio|workers_ratio|unit). 입력: {raw}"
        )
    n_act = int(parts[2])
    if n_act <= 0:
        raise ValueError(f"n_activities > 0 필요 — 입력: {n_act} ({raw})")
    return {
        "company": parts[0],
        "l6_main": parts[1],
        "n_activities": n_act,
        "incident": parts[3],
        "productivity_ratio": float(parts[4]),
        "workers_ratio": float(parts[5]),
        "unit": parts[6],
    }


async def _check_synthetic_v2_loaded(cfg) -> bool:
    chroma = ChromaClient(host=cfg.chroma_host, port=cfg.chroma_port, ssl=cfg.chroma_ssl)
    coll = chroma.get_or_create_daily_activities()
    res = coll.get(where={"worker_source": "synthetic_v2"}, limit=1)
    return bool(res.get("ids"))


async def _ensure_site(pg: PGClient, site_id: str, name: str = "Demo Site") -> None:
    """sites ON CONFLICT DO NOTHING 사전 INSERT — pipeline_runs FK 대비."""
    assert pg._pool is not None
    async with pg._pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sites (site_id, name) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            site_id,
            name,
        )


async def _load_baseline_inputs(
    pg: PGClient,
    scenarios: list[dict],
    days: int = 90,
) -> tuple[
    dict[tuple[str, str], list[str]],
    dict[tuple[str, str], float],
    dict[tuple[str, str, str], float],
]:
    """activity_master 에서 activity_pool + baseline_workers + baseline_qty 산출.

    synthetic_v2._main_cli 와 동일 알고리즘:
      - mh_lookup[(co, l6)] = Σ plan_mh_rev2
      - sum_mh_per_co[co]   = Σ_l6 mh_lookup[(co, l6)]
      - baseline_workers    = _BP_TOTAL[co] × l6_mh / sum_mh
      - baseline_qty[(co, l6, unit)] = Σ plan_total_qty / days
      - activity_pool       = distinct l7_5_activity
    """
    assert pg._pool is not None
    mh_rows = await pg._pool.fetch(
        """
        SELECT company, l6_main, SUM(plan_mh_rev2) AS total_mh
        FROM activity_master
        WHERE company IS NOT NULL AND l6_main IS NOT NULL
        GROUP BY company, l6_main
        """
    )
    qty_rows = await pg._pool.fetch(
        """
        SELECT company, l6_main, unit, SUM(plan_total_qty)::float AS total_qty
        FROM activity_master
        WHERE company IS NOT NULL AND l6_main IS NOT NULL AND unit IS NOT NULL
        GROUP BY company, l6_main, unit
        """
    )
    act_rows = await pg._pool.fetch(
        """
        SELECT company, l6_main, l7_5_activity
        FROM activity_master
        WHERE company IS NOT NULL AND l6_main IS NOT NULL AND l7_5_activity IS NOT NULL
        """
    )

    mh_lookup: dict[tuple[str, str], int] = {
        (r["company"], r["l6_main"]): int(r["total_mh"] or 0) for r in mh_rows
    }
    sum_mh_per_co: dict[str, int] = {}
    for (co, _l6), mh in mh_lookup.items():
        sum_mh_per_co[co] = sum_mh_per_co.get(co, 0) + mh

    pool_lookup: dict[tuple[str, str], list[str]] = {}
    for r in act_rows:
        key = (r["company"], r["l6_main"])
        pool_lookup.setdefault(key, []).append(r["l7_5_activity"])
    for k, lst in pool_lookup.items():
        pool_lookup[k] = sorted(set(lst))

    qty_lookup: dict[tuple[str, str, str], float] = {}
    for r in qty_rows:
        total = float(r["total_qty"] or 0.0)
        qty_lookup[(r["company"], r["l6_main"], r["unit"])] = total / max(days, 1)

    # scenario 가 요청한 그룹만 산출 (전체 27 그룹 산출은 불필요)
    activity_pools: dict[tuple[str, str], list[str]] = {}
    baseline_workers: dict[tuple[str, str], float] = {}
    baseline_qty: dict[tuple[str, str, str], float] = {}
    for sc in scenarios:
        co = sc["company"]
        l6 = sc["l6_main"]
        unit = sc["unit"]
        key = (co, l6)
        bp_total = _BP_TOTAL.get(co, 0)
        sum_mh = sum_mh_per_co.get(co, 0)
        l6_mh = mh_lookup.get(key, 0)
        if bp_total == 0 or sum_mh == 0 or l6_mh == 0:
            bw = 0.0
        else:
            bw = bp_total * l6_mh / sum_mh
        baseline_workers[key] = bw
        activity_pools[key] = pool_lookup.get(key) or [f"{l6} 작업"]
        baseline_qty[(co, l6, unit)] = qty_lookup.get((co, l6, unit), 0.0)
    return activity_pools, baseline_workers, baseline_qty


def _initial_state(run_id: uuid.UUID, report_date: str, mapped: list[Activity]) -> dict:
    """build_demo_graph 진입 state — Parser/Mapper skip 이므로 parsed 는 empty."""
    return {
        "run_id": str(run_id),
        "date": report_date,
        "input_files": [],
        "raw_texts": {},
        "parsed": {
            "report_date": report_date,
            "project": "DEMO",
            "bp_summaries": [],
            "job_allocations": [],
            "equipment_allocations": [],
            "activities": [],
        },
        "mapped": mapped,
        "hil_1_corrections": {},
        "atomized_ids": [],
        "report_md": "",
        "forecast": [],
        "hil_2_selection": [],
        "pre_optimizer_cases": {},
        "optimizer_advice": [],
        "current_node": "demo_start",
        "status": "running",
    }


def _build_optimizer_config():
    from pipeline.agents.optimizer.agent import OptimizerConfig

    return OptimizerConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
        chroma_ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )


def _build_reporter_config():
    from pipeline.agents.reporter import ReporterConfig

    return ReporterConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
    )


def _build_forecaster_config():
    from pipeline.agents.forecaster import ForecasterConfig

    return ForecasterConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
        embedding_model=os.environ["EMBEDDING_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
        chroma_ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )


def build_demo_graph_config():
    """build_demo_graph 가 요구하는 GraphConfig — forecaster + optimizer 만 실 사용.

    mapper/atomizer 는 build_demo_graph 에서 노드 등록 안 함. 그래도 GraphConfig
    dataclass 는 두 필드 비-Optional 이라 placeholder 로 채워둠 (호출 안 됨).
    """
    from pipeline.agents.atomizer import AtomizerConfig
    from pipeline.agents.mapper import MapperConfig
    from pipeline.graph import GraphConfig

    common_pg = os.environ["POSTGRES_URL"]
    common_chroma_host = os.environ["CHROMA_HOST"]
    common_chroma_port = int(os.environ.get("CHROMA_PORT", "8000"))
    common_chroma_ssl = os.environ.get("CHROMA_SSL", "false").lower() == "true"
    return GraphConfig(
        mapper=MapperConfig(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            llm_model=os.environ["LLM_MODEL"],
            embedding_model=os.environ["EMBEDDING_MODEL"],
            postgres_url=common_pg,
            chroma_host=common_chroma_host,
            chroma_port=common_chroma_port,
            chroma_ssl=common_chroma_ssl,
        ),
        atomizer=AtomizerConfig(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            embedding_model=os.environ["EMBEDDING_MODEL"],
            postgres_url=common_pg,
            chroma_host=common_chroma_host,
            chroma_port=common_chroma_port,
            chroma_ssl=common_chroma_ssl,
        ),
        forecaster=_build_forecaster_config(),
        optimizer=_build_optimizer_config(),
        reporter=_build_reporter_config(),
    )


async def _main_cli() -> int:
    """CLI entry — pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report.

    Returns: 종료코드 (0 = success, !=0 = abort).
    """
    from langgraph.types import Command

    from pipeline.graph import build_demo_graph

    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="report_date (ISO YYYY-MM-DD).")
    parser.add_argument("--site-id", default="DEMO_SITE")
    parser.add_argument("--site-name", default="Demo Site")
    parser.add_argument(
        "--scenario",
        action="append",
        required=True,
        help=(
            "scenario pipe-separated: "
            "company|l6_main|n_activities|incident|productivity_ratio|workers_ratio|unit. "
            "여러 번 지정 가능."
        ),
    )
    parser.add_argument(
        "--auto-select-all",
        action="store_true",
        help="interactive input() 우회 — 모든 risky key 자동 resume.",
    )
    parser.add_argument("--days", type=int, default=90, help="baseline_qty 계산 시 분모.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # ── Step 1: synthetic v2 적재 확인 ──
    cfg = build_demo_graph_config()
    if not await _check_synthetic_v2_loaded(cfg.optimizer):
        print(
            "[ABORT] daily_activities (worker_source=synthetic_v2) row 0 — "
            "먼저 Task 3 적재 실행: "
            "`pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_v2 ...`"
        )
        return 2

    scenarios = [_parse_scenario(s) for s in args.scenario]

    # ── Step 2 + 3: sites + pipeline_runs ──
    run_id = uuid.uuid4()
    pg = PGClient(cfg.optimizer.postgres_url)
    await pg.connect()
    try:
        await _ensure_site(pg, args.site_id, args.site_name)
        await pg.insert_pipeline_run(run_id, args.site_id, args.date, status="running")
        # ── Step 4: baseline inputs + fake activities ──
        pools, base_workers, base_qty = await _load_baseline_inputs(pg, scenarios, days=args.days)
    finally:
        await pg.close()

    mapped = generate_fake_daily_report(
        report_date=args.date,
        scenarios=scenarios,
        activity_pools=pools,
        baseline_workers=base_workers,
        baseline_qty=base_qty,
        seed=args.seed,
    )
    print(f"[OK] generate_fake_daily_report: {len(mapped)} Activity rows (scenarios={len(scenarios)})")
    print(f"[OK] run_id={run_id} site_id={args.site_id} date={args.date}")

    # ── Step 5: build_demo_graph + 1st ainvoke ──
    graph = build_demo_graph(cfg)
    thread_id = f"demo-{run_id}"
    graph_config = {"configurable": {"thread_id": thread_id}}
    state = _initial_state(run_id, args.date, mapped)

    first = await graph.ainvoke(state, config=graph_config)

    # ── Step 6: __interrupt__ payload 출력 ──
    if "__interrupt__" not in first:
        print(
            "[INFO] __interrupt__ 미발생 — risky 0건 (Forecaster 가 모든 그룹 risk_level=정상). "
            "Optimizer 미진입."
        )
        forecast_rows = first.get("forecast", [])
        for r in forecast_rows:
            print(
                f"  forecast: {r['company']}|{r['l6_main']} "
                f"assessment={r.get('assessment')} risk={r.get('risk_level')} "
                f"reasoning={r.get('reasoning', '')[:80]}"
            )
        return 0

    interrupts = first["__interrupt__"]
    payload = interrupts[0].value
    risky_groups = payload.get("risky_groups", [])
    print(f"\n[HIL-2 INTERRUPT] risky_groups: {len(risky_groups)}")
    for g in risky_groups:
        print(
            f"  - {g['key']}: assessment={g.get('assessment')} "
            f"risk={g.get('risk_level')} preview_cases={len(g.get('preview_cases', []))}"
        )

    # ── Step 7: resume selection ──
    if args.auto_select_all:
        selection = [g["key"] for g in risky_groups]
        print(f"[AUTO] --auto-select-all → resume keys = {selection}")
    else:
        keys = [g["key"] for g in risky_groups]
        print("\n선택할 risky key (쉼표 구분, 빈 입력=skip):")
        for i, k in enumerate(keys):
            print(f"  [{i}] {k}")
        raw = input("선택> ").strip()
        if not raw:
            selection = []
        else:
            try:
                idxs = [int(x.strip()) for x in raw.split(",")]
                selection = [keys[i] for i in idxs]
            except (ValueError, IndexError) as exc:
                print(f"[ABORT] 선택 파싱 실패: {exc}")
                return 3

    final = await graph.ainvoke(Command(resume=selection), config=graph_config)

    # ── Step 8: advice 출력 ──
    advice = final.get("optimizer_advice", [])
    print(f"\n[OPTIMIZER] advice rows: {len(advice)}")
    for row in advice:
        print(
            f"\n--- {row['company']}|{row['l6_main']} "
            f"(forecast_assessment={row.get('forecast_assessment')}) ---"
        )
        diag = row.get("diagnosis", "")
        print(f"diagnosis: {diag[:300]}{'...' if len(diag) > 300 else ''}")
        recs = row.get("recommendations", [])
        for r in recs:
            print(f"  - [rank {r.get('rank')}] {r.get('text')}")
        rec_dist = row.get("recovery_distribution", {})
        if rec_dist:
            print(f"recovery_distribution: {rec_dist}")
    return 0


if __name__ == "__main__":
    code = asyncio.run(_main_cli())
    raise SystemExit(code)
