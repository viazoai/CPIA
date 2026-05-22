"""LangGraph StateGraph — Phase 1 mapper + atomizer + forecaster + hil_2 + optimizer.

Spec:
- docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §10
- docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §8
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from datetime import date as _date

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt  # noqa: F401  (Command re-exported for callers)

from pipeline.agents.atomizer import AtomizerConfig, atomize
from pipeline.agents.collector_node import collector_node as _collector
from pipeline.agents.forecaster import ForecasterConfig, forecast
from pipeline.agents.mapper import MapperConfig, _prorate_mh, map_activity
from pipeline.agents.parser_node import parser_node as _parser
from pipeline.agents.optimizer.agent import OptimizerConfig, optimize
from pipeline.agents.parser_post import normalize_company
from pipeline.agents.optimizer.retrieve import (
    _group_baseline,
    fetch_degradation_cases,
    fetch_recovery_trajectory,
)
from pipeline.agents.reporter import ReporterConfig, report
from pipeline.checkpointer import build_checkpointer
from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient, update_site_hours_saved_cum, update_site_last_run
from pipeline.state import Activity, CPIAState, ParsedDailyReport

# Mapper LLM rerank 병렬도 — Azure rate-limit 고려해 기본 4. env 로 조정.
_MAPPER_CONCURRENCY = int(os.environ.get("CPIA_MAPPER_CONCURRENCY", "4"))


@dataclass
class GraphConfig:
    mapper: MapperConfig
    atomizer: AtomizerConfig
    forecaster: ForecasterConfig
    optimizer: OptimizerConfig  # optimizer cycle Task 8
    reporter: ReporterConfig  # hil1-forecaster-reporter cycle (2026-05-17)


async def mapper_node(state: CPIAState, cfg: GraphConfig) -> dict:
    """Mapper LLM (병렬) + Parser/Mapper 산출 PG 영속.

    각 에이전트 결과가 BI / 대시보드에서 SELECT 가능해야 한다는 요구로
    Parser 결과 (parser_reports + parser_activities) 와 Mapper 결과
    (mapper_activities) 를 본 노드에서 함께 INSERT. ON CONFLICT (run_id[, idx])
    DO UPDATE 라 재실행 멱등.

    BP cand_pool 미리 batch fetch (1 PG connection × N BP) → map_activity 안의
    매 활동마다 새 PG connection 폭발 회피. asyncio.gather +
    Semaphore(`CPIA_MAPPER_CONCURRENCY`, 기본 4) 로 묶어 Azure rate-limit 회피.
    """
    parsed: ParsedDailyReport = state["parsed"]
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    today = _date.fromisoformat(state["date"])

    # 정규화 타이밍 fix — fetch_bp_candidates 는 정확 일치 SQL (db.py:55).
    # ㈜/(주) prefix 가 LLM 응답에 섞이면 마스터와 mismatch 로 cand_pool 빔.
    # mapper 진입 직전 일괄 정규화 (line 138 의 mapper 후 정규화와 일관).
    for a in parsed["activities"]:
        a["company"] = normalize_company(a.get("company"))

    # BP cand_pool 미리 batch fetch — 1 PG connection 으로 모든 company 조회
    pg = PGClient(cfg.mapper.postgres_url)
    await pg.connect()
    try:
        unique_companies = {a["company"] for a in parsed["activities"] if a.get("company")}
        bp_cand_lookup: dict[str, list[tuple[str, str]]] = {}
        for company in unique_companies:
            cand_rows = await pg.fetch_bp_candidates(company)
            bp_cand_lookup[company] = [(r["wa"], r["l6_main"]) for r in cand_rows]
    finally:
        await pg.close()

    sem = asyncio.Semaphore(_MAPPER_CONCURRENCY)

    async def _map_one(a: Activity) -> Activity:
        async with sem:
            return await map_activity(
                a,
                parsed_report=parsed,
                cfg=cfg.mapper,
                bp_cand_lookup=bp_cand_lookup,
            )

    mapped: list[Activity] = list(await asyncio.gather(*[_map_one(a) for a in parsed["activities"]]))

    import sys as _sys

    def _dbg(msg: str) -> None:
        print(f"[mapper_node:{run_id}] {msg}", file=_sys.stderr, flush=True)

    _dbg(f"mapped len={len(mapped)} BEFORE prorate/INSERT")
    pg = PGClient(cfg.mapper.postgres_url)
    await pg.connect()
    _dbg(f"PG connected DSN={cfg.mapper.postgres_url[:40]}...")
    try:
        mapped = await _prorate_mh(mapped, parsed, pg)
        _dbg(f"prorate done, mapped len={len(mapped)}")

        await pg.insert_parser_report(
            run_id=run_id,
            report_date=today,
            project=parsed["project"],
            bp_summaries=parsed["bp_summaries"],
            job_allocations=parsed["job_allocations"],
            equipment_allocations=parsed["equipment_allocations"],
            activity_count=len(parsed["activities"]),
        )
        _dbg("insert_parser_report OK")
        await pg.insert_parser_activities_batch(
            run_id=run_id,
            report_date=today,
            activities=parsed["activities"],
        )
        _dbg(f"insert_parser_activities_batch OK ({len(parsed['activities'])} rows)")

        # G24 — 시트2 / 시트3 정규화 row 적재. 이전엔 호출 누락으로 두 테이블
        # row count 가 항상 0 이었음. ParsedDailyReport TypedDict (state.py) 에
        # 키는 이미 정의되어 있으나 graph 가 INSERT 함수를 호출하지 않았음.
        await pg.insert_parser_job_allocations_batch(
            run_id=run_id,
            report_date=today,
            rows=parsed.get("job_allocations") or [],
        )
        _dbg(f"insert_parser_job_allocations_batch OK ({len(parsed.get('job_allocations') or [])} rows)")
        await pg.insert_parser_equipment_allocations_batch(
            run_id=run_id,
            report_date=today,
            rows=parsed.get("equipment_allocations") or [],
        )
        _dbg(
            f"insert_parser_equipment_allocations_batch OK ({len(parsed.get('equipment_allocations') or [])} rows)"
        )

        # company 정규화 (㈜ prefix / 괄호 sub-context 제거) — A.6 와 일관
        for a in mapped:
            a["company"] = normalize_company(a.get("company"))

        await pg.insert_mapper_activities_batch(
            run_id=run_id,
            report_date=today,
            activities=mapped,
        )
        _dbg(f"insert_mapper_activities_batch OK ({len(mapped)} rows)")

        # 같은 transaction 안에서 SELECT 로 즉시 검증 (silent fail 진단)
        n_pr = await pg.fetch_all("SELECT count(*) AS n FROM parser_reports WHERE run_id=$1", run_id)
        n_pa = await pg.fetch_all("SELECT count(*) AS n FROM parser_activities WHERE run_id=$1", run_id)
        n_ma = await pg.fetch_all("SELECT count(*) AS n FROM mapper_activities WHERE run_id=$1", run_id)
        _dbg(
            f"verify SELECT: parser_reports={n_pr[0]['n']} parser_activities={n_pa[0]['n']} mapper_activities={n_ma[0]['n']}"
        )
    finally:
        await pg.close()
        _dbg("PG closed, mapper_node return")

    return {"mapped": mapped, "current_node": "mapper"}


def _build_review_needed(mapped: list[Activity]) -> list[dict]:
    """requires_review=True 인 Activity 만 review payload 빌드.

    Spec §5.1 — interrupt payload schema.
    """
    return [
        {
            "idx": i,
            "work_content": a["work_content"],
            "company": a["company"],
            "trade": a["trade"],
            "wa": a.get("wa"),
            "l6_main": a.get("l6_main"),
            "mapping_conf": a.get("mapping_conf"),
            "mapping_source": a.get("mapping_source"),
        }
        for i, a in enumerate(mapped)
        if a.get("requires_review")
    ]


def _apply_corrections(
    mapped: list[Activity],
    corrections: dict[int, dict],
) -> list[Activity]:
    """corrections dict (idx → {wa, l6_main}) 를 mapped 에 적용.

    Spec §5.1 #6:
    - 답한 row: wa/l6_main 수정 + mapping_source="user_corrected" + requires_review=False
    - 답 안 한 row (review_needed 였으나 corrections 에 없음): Mapper 추천 수용 +
      mapping_source="user_corrected" + requires_review=False (재시도 X — PoC 기본)
    """
    out: list[Activity] = []
    for i, a in enumerate(mapped):
        if a.get("requires_review"):
            c = corrections.get(i)
            if c:
                new_a: Activity = {
                    **a,
                    "wa": c["wa"],
                    "l6_main": c["l6_main"],
                    "mapping_source": "user_corrected",
                    "requires_review": False,
                }
            else:
                new_a = {
                    **a,
                    "mapping_source": "user_corrected",
                    "requires_review": False,
                }
            out.append(new_a)
        else:
            out.append(a)
    return out


async def hil_1_node(state: CPIAState, cfg) -> dict:
    """Mapper 결과 사람 검토. requires_review=True 가 1건 이상이면 interrupt.

    Spec §5.1. cfg = GraphConfig (PG INSERT 용 postgres_url 추출, cfg=None 이면
    PG insert skip — unit 테스트 path).

    env CPIA_HIL_AUTO_BYPASS={1|true|on} → review_needed 가 있어도 interrupt 건너뛰고
    빈 corrections 로 통과 (dev/검증 모드 — atomizer/forecaster 진행 위해).
    """
    mapped = state["mapped"]
    review_needed = _build_review_needed(mapped)
    if not review_needed:
        return {"hil_1_corrections": {}, "current_node": "hil_1"}

    if os.environ.get("CPIA_HIL_AUTO_BYPASS", "").lower() in ("1", "true", "on", "yes"):
        import sys as _sys_local

        print(
            f"[hil_1] AUTO_BYPASS — review_needed={len(review_needed)} 무시, interrupt 우회",
            file=_sys_local.stderr,
            flush=True,
        )
        return {"hil_1_corrections": {}, "current_node": "hil_1"}

    corrections_raw = interrupt({"review_needed": review_needed})
    corrections_raw = corrections_raw or {}
    corrections = {int(k): v for k, v in corrections_raw.items()}

    corrected = _apply_corrections(mapped, corrections)

    if cfg is not None and corrections:
        pg = PGClient(cfg.mapper.postgres_url)
        await pg.connect()
        try:
            run_id_str = state["run_id"]
            run_id = uuid.UUID(run_id_str) if isinstance(run_id_str, str) else run_id_str
            today = _date.fromisoformat(state["date"])
            for idx, c in corrections.items():
                original_a = mapped[idx]
                await pg.insert_mapping_correction(
                    run_id=run_id,
                    report_date=today,
                    original={
                        "work_content": original_a["work_content"],
                        "company": original_a.get("company"),
                        "trade": original_a.get("trade"),
                        "wa": original_a.get("wa"),
                        "l6_main": original_a.get("l6_main"),
                        "mapping_conf": original_a.get("mapping_conf"),
                        "mapping_source": original_a.get("mapping_source"),
                    },
                    corrected={
                        "wa": c["wa"],
                        "l6_main": c["l6_main"],
                        "mapping_source": "user_corrected",
                        "correction_type": "replace",
                    },
                )
        finally:
            await pg.close()

    return {
        "mapped": corrected,
        "hil_1_corrections": corrections,
        "current_node": "hil_1",
    }


async def atomizer_node(state: CPIAState, cfg: GraphConfig) -> dict:
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    parsed: ParsedDailyReport = state["parsed"]
    atomized_ids = await atomize(state["mapped"], parsed, run_id, cfg.atomizer)
    return {"atomized_ids": atomized_ids, "current_node": "atomizer"}


async def forecaster_node(state: CPIAState, cfg: GraphConfig) -> dict:
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    today = _date.fromisoformat(state["date"])
    forecasts = await forecast(state["mapped"], run_id, today, cfg.forecaster)
    return {"forecast": forecasts, "current_node": "forecaster"}


async def hil_2_node(state: CPIAState, cfg: GraphConfig) -> dict:
    """Forecaster 직후 — risky (주의/이상) 그룹별 degradation + recovery 사전 영속 + interrupt.

    Spec §8.2 (F5 정정 — coll.get 1회 + F7 정정 — None 분기).

    원칙:
    - retrieve.fetch_* 호출은 본 노드 책임 (agent.py 는 import X — 결정 #8 / Task 6 test 6.5).
    - Chroma coll.get(...) 그룹당 1회만 호출 후 metadatas/documents 두 함수 (degradation/recovery)
      에 전달 (round-trip 절감).
    - baseline None 또는 main_unit None 일 때 cold_start signal payload 박고 다음 그룹.
    - resume payload (Command(resume=[group_key, ...])) 가 hil_2_selection 으로 영속.
    - risky 0건 → interrupt 미발생, empty selection 반환 → conditional_edge 가 END 분기.
    """
    risky = [r for r in state["forecast"] if r["risk_level"] in {"주의", "이상"}]
    if not risky:
        return {"hil_2_selection": [], "pre_optimizer_cases": {}, "current_node": "hil_2"}

    chroma = ChromaClient(
        host=cfg.optimizer.chroma_host,
        port=cfg.optimizer.chroma_port,
        ssl=cfg.optimizer.chroma_ssl,
    )
    coll = chroma.get_or_create_daily_activities()
    today = _date.fromisoformat(state["date"])

    pre_cases: dict[str, list[dict]] = {}
    payload_groups: list[dict] = []
    for r in risky:
        key = f"{r['company']}|{r['l6_main']}"
        baseline_unit = r.get("main_unit")
        if baseline_unit is None:
            pre_cases[key] = []
            payload_groups.append(
                {
                    "key": key,
                    "assessment": r["assessment"],
                    "risk_level": r["risk_level"],
                    "reasoning": r["reasoning"],
                    "preview_cases": [],
                    "note": "no_main_unit",
                }
            )
            continue

        # F5: coll.get 1회 호출 후 두 함수에 metadatas/documents 전달.
        # 2026-05-22: company hard filter 제거 — l6_main 만 매칭하여 cross-company case 활용
        # (이전엔 합성 3사 외 75사가 case=0 cold_start fallback).
        result = coll.get(
            where={"l6_main": r["l6_main"]},
            include=["metadatas", "documents"],
        )
        metas, docs = result["metadatas"], result["documents"]

        baseline_value = _group_baseline(metas, None, r["l6_main"], baseline_unit)
        if baseline_value is None:
            # F7: None 분기 명시 — pre_cases[key]=[] 후 다음 그룹
            pre_cases[key] = []
            payload_groups.append(
                {
                    "key": key,
                    "assessment": r["assessment"],
                    "risk_level": r["risk_level"],
                    "reasoning": r["reasoning"],
                    "preview_cases": [],
                    "note": "cold_start_no_baseline",
                }
            )
            continue

        cases = fetch_degradation_cases(
            metas,
            docs,
            None,  # 2026-05-22 cross-company retrieve
            r["l6_main"],
            today,
            baseline_unit,
            baseline_value,
            n=5,
        )
        for c in cases:
            c["recovery"] = fetch_recovery_trajectory(
                metas,
                None,  # 2026-05-22 cross-company recovery 추세
                r["l6_main"],
                c["date"],
                today,
                baseline_unit,
                baseline_value,
                window=7,
            )
        pre_cases[key] = cases
        payload_groups.append(
            {
                "key": key,
                "assessment": r["assessment"],
                "risk_level": r["risk_level"],
                "reasoning": r["reasoning"],
                "today_productivity": r.get("today_productivity"),
                "today_conditions": r.get("today_conditions", ""),
                "preview_cases": cases,
            }
        )

    selected = interrupt({"risky_groups": payload_groups})
    return {
        "hil_2_selection": list(selected) if selected else [],
        "pre_optimizer_cases": pre_cases,
        "current_node": "hil_2",
    }


async def optimizer_node(state: CPIAState, cfg: GraphConfig) -> dict:
    """Optimizer — selected group 별 advice row 생성 + PG insert. retrieve 재호출 X.

    Spec §8.2 + §7. hil_2_node 가 사전 영속한 pre_optimizer_cases 만 소비.
    """
    # 2026-05-20: risky 0 인 cycle (1사 sample 등) 도 view 산출 (KPI/EVM 등 7 view 는 advice 무관)
    # 위해 early return 제거. optimize() 안에서 hil_2_selection 빈 → advice_rows=[] 진행.
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    today = _date.fromisoformat(state["date"])
    # site_id + mapped 전달 — optimize() 의 view 산출 (9 jsonb) block 진입 보장.
    # 미전달 시 agent.py:175 의 `if site_id:` block skip → daily_reports 의 9 jsonb 모두 default
    # ({} / []) 그대로. cycle 7차 issue A root cause fix.
    advice = await optimize(
        state["forecast"],
        state.get("hil_2_selection") or [],
        state.get("pre_optimizer_cases") or {},
        run_id,
        today,
        cfg.optimizer,
        site_id=state.get("site_id"),
        mapped=state.get("mapped"),
    )
    return {"optimizer_advice": advice, "current_node": "optimizer"}


async def reporter_node(state: CPIAState, cfg: GraphConfig) -> dict:
    """Mapper + Forecaster + Optimizer 결과 종합 보고서 생성 + PG INSERT.

    Spec §5.3. hil_2_selection=[] (Optimizer skip) 또는 risky 0건 path 에서도
    본 노드 진입. mapped empty → fallback MD + PG INSERT skip.
    """
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    today = _date.fromisoformat(state["date"])
    report_md, _summary = await report(
        mapped=state["mapped"],
        forecast_rows=state.get("forecast", []),
        optimizer_advice=state.get("optimizer_advice", []),
        run_id=run_id,
        today=today,
        cfg=cfg.reporter,
    )

    # G8 — reporter→END 진입 시 sites.last_run_id 갱신.
    # G2 — atomized_count 기반 사람 수작업 절감 시간(h) 누적.
    # state 가 site_id 를 propagate 안 한 경우 pipeline_runs 에서 직접 fetch.
    pg = PGClient(cfg.mapper.postgres_url)
    await pg.connect()
    try:
        site_id = state.get("site_id")
        if not site_id:
            async with pg._pool.acquire() as _con:  # type: ignore[attr-defined]
                _row = await _con.fetchrow("SELECT site_id FROM pipeline_runs WHERE run_id = $1", run_id)
            site_id = _row["site_id"] if _row else None
        if site_id:
            await update_site_last_run(pg, site_id=site_id, run_id=run_id)
            await update_site_hours_saved_cum(
                pg,
                site_id=site_id,
                atomized_count=len(state.get("atomized_ids", []) or []),
            )
        # 2026-05-20 Issue B fix: pipeline_runs.status='completed' + completed_at 갱신.
        # 이전엔 reporter_node 진입 후 graph 끝나도 status='running' 그대로 (completed_at=NULL).
        # cycle 7차 발견 — final status=running current_node=reporter.
        async with pg._pool.acquire() as _con:  # type: ignore[attr-defined]
            await _con.execute(
                "UPDATE pipeline_runs SET status='completed', completed_at=NOW() WHERE run_id=$1",
                run_id,
            )
    finally:
        await pg.close()

    return {"report_md": report_md, "current_node": "reporter", "status": "completed"}


def build_demo_graph(cfg: GraphConfig):
    """데모 graph — START → forecaster → hil_2 → (optimizer | END) → END.

    Spec §10.3. Parser/Mapper/Atomizer skip — state["mapped"] 에 가짜 Activity list
    사전 주입 가정 (LLM 비용 회피). build_graph 와 별도 (기존 graph 영향 X).

    `synthetic_daily_report.py` CLI + `test_synthetic_daily_report.py` E2E 가 호출.
    """
    graph = StateGraph(CPIAState)

    async def _forecaster(state: CPIAState) -> dict:
        return await forecaster_node(state, cfg)

    async def _hil_2(state: CPIAState) -> dict:
        return await hil_2_node(state, cfg)

    async def _optimizer(state: CPIAState) -> dict:
        return await optimizer_node(state, cfg)

    async def _reporter(state: CPIAState) -> dict:
        return await reporter_node(state, cfg)

    graph.add_node("forecaster", _forecaster)
    graph.add_node("hil_2", _hil_2)
    graph.add_node("optimizer", _optimizer)
    graph.add_node("reporter", _reporter)
    graph.add_edge(START, "forecaster")
    graph.add_edge("forecaster", "hil_2")
    graph.add_conditional_edges(
        "hil_2",
        lambda s: "optimizer" if s.get("hil_2_selection") else "reporter",
        {"optimizer": "optimizer", "reporter": "reporter"},
    )
    graph.add_edge("optimizer", "reporter")
    graph.add_edge("reporter", END)
    return graph.compile(checkpointer=build_checkpointer())


def build_atomized_demo_graph(cfg: GraphConfig):
    """START -> atomizer -> forecaster -> hil_2 -> (optimizer | reporter) -> END.

    2026-05-22 (Plan B6) — mapper / hil_1 만 skip. mapped 는 호출자가
    PG mapper_activities 에서 hydrate 해서 state['mapped'] 에 주입한 상태로 진입.
    pipeline_runs INSERT 도 호출자 책임 (atomizer.assert_pipeline_run_exists fail-fast).

    15일 backfill 의 표준 graph. build_demo_graph 의 node 패턴 + atomizer 추가.
    """
    graph = StateGraph(CPIAState)

    async def _atomizer(state: CPIAState) -> dict:
        return await atomizer_node(state, cfg)

    async def _forecaster(state: CPIAState) -> dict:
        return await forecaster_node(state, cfg)

    async def _hil_2(state: CPIAState) -> dict:
        return await hil_2_node(state, cfg)

    async def _optimizer(state: CPIAState) -> dict:
        return await optimizer_node(state, cfg)

    async def _reporter(state: CPIAState) -> dict:
        return await reporter_node(state, cfg)

    graph.add_node("atomizer", _atomizer)
    graph.add_node("forecaster", _forecaster)
    graph.add_node("hil_2", _hil_2)
    graph.add_node("optimizer", _optimizer)
    graph.add_node("reporter", _reporter)
    graph.add_edge(START, "atomizer")
    graph.add_edge("atomizer", "forecaster")
    graph.add_edge("forecaster", "hil_2")
    graph.add_conditional_edges(
        "hil_2",
        lambda s: "optimizer" if s.get("hil_2_selection") else "reporter",
        {"optimizer": "optimizer", "reporter": "reporter"},
    )
    graph.add_edge("optimizer", "reporter")
    graph.add_edge("reporter", END)
    return graph.compile(checkpointer=build_checkpointer())


def build_graph(cfg: GraphConfig):
    """StateGraph — mapper → atomizer → forecaster → hil_2 → (optimizer | END) → END.

    conditional_edges:
    - hil_2 → optimizer (hil_2_selection 비어있지 않음)
    - hil_2 → END (hil_2_selection 비어있음 = risky 0건 또는 PM 무선택)
    """
    graph = StateGraph(CPIAState)

    async def _mapper(state: CPIAState) -> dict:
        return await mapper_node(state, cfg)

    async def _hil_1(state: CPIAState) -> dict:
        return await hil_1_node(state, cfg)

    async def _atomizer(state: CPIAState) -> dict:
        return await atomizer_node(state, cfg)

    async def _forecaster(state: CPIAState) -> dict:
        return await forecaster_node(state, cfg)

    async def _hil_2(state: CPIAState) -> dict:
        return await hil_2_node(state, cfg)

    async def _optimizer(state: CPIAState) -> dict:
        return await optimizer_node(state, cfg)

    async def _reporter(state: CPIAState) -> dict:
        return await reporter_node(state, cfg)

    graph.add_node("collector", _collector)
    graph.add_node("parser", _parser)
    graph.add_node("mapper", _mapper)
    graph.add_node("hil_1", _hil_1)
    graph.add_node("atomizer", _atomizer)
    graph.add_node("forecaster", _forecaster)
    graph.add_node("hil_2", _hil_2)
    graph.add_node("optimizer", _optimizer)
    graph.add_node("reporter", _reporter)
    graph.add_edge(START, "collector")
    graph.add_edge("collector", "parser")
    graph.add_edge("parser", "mapper")
    graph.add_edge("mapper", "hil_1")
    graph.add_edge("hil_1", "atomizer")
    graph.add_edge("atomizer", "forecaster")
    graph.add_edge("forecaster", "hil_2")
    graph.add_conditional_edges(
        "hil_2",
        lambda s: "optimizer" if s.get("hil_2_selection") else "reporter",
        {"optimizer": "optimizer", "reporter": "reporter"},
    )
    graph.add_edge("optimizer", "reporter")
    graph.add_edge("reporter", END)
    return graph.compile(checkpointer=build_checkpointer())
