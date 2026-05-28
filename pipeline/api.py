"""CPIA Pipeline FastAPI — /health + /run + /resume + /status.

Phase 4.1: 골격 + lifespan + GET /health 1개.
Phase 4.2: POST /api/runs/:run_id/hil_1/resume + lifespan graph/checkpointer 통합.
Phase 4.3: GET /api/sites — Site[] 반환.
Phase 4.4: GET /api/runs/:run_id/optimizer — OptimizerOutput[] 반환.
Phase 4.5: GET /api/runs/:run_id/wp_summary — WPSummaryRow[] 반환.
Phase 4.6: GET /api/sites/:site_id/reports — ReportDaily[] 반환.
Phase 4.7: GET /api/dashboard/performance — fleet_kpi 반환.
Phase 4.8: GET /api/dashboard/impact — ImpactSiteDistribution[] 반환.
Phase 4.9: GET /api/agents/status — AgentStatus[] 반환.
Phase 4.10: GET /api/sites/:site_id/wbs_tree — WBSNode 트리 반환.
Phase 4.11: GET /api/tasks — DailyTask[] + progressByDate + itemsByDate 반환.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from langgraph.errors import EmptyChannelError, InvalidUpdateError
from langgraph.types import Command
from pydantic import BaseModel

from pipeline.collector.config import load_collector_config
from pipeline.collector.idle_worker import idle_loop, request_shutdown
from pipeline.db import PGClient
from pipeline.exporter_routes import router as exporter_router
from pipeline.graph import GraphConfig, build_graph


# ---------------------------------------------------------------------------
# Pydantic 요청/응답 모델
# ---------------------------------------------------------------------------


class CorrectionItem(BaseModel):
    """HIL 1 단일 보정 항목 — wa + l6_main 둘 다 필수."""

    wa: str
    l6_main: str


class Hil1ResumeRequest(BaseModel):
    """POST /api/runs/:run_id/hil_1/resume 요청 body.

    corrections key 는 반드시 string (drift #N5 방어 — hil_1_node 에서 int(k) 변환).
    """

    corrections: dict[str, CorrectionItem]


class Hil1ResumeResponse(BaseModel):
    """resume 후 진행된 노드명."""

    next_node: str


# ---------------------------------------------------------------------------
# lifespan
# ---------------------------------------------------------------------------


def _build_prod_graph_config() -> GraphConfig:
    """환경변수 기반 prod GraphConfig.

    POSTGRES_URL / AZURE_OPENAI_* / CHROMA_HOST 등에서 각 에이전트 config 를 조립.
    각 config 의 상세 필드는 pipeline/agents/* 의 dataclass 참조.

    Q3: os.environ.get("POSTGRES_URL", "") 사용 — lifespan 이 이미 미설정 RuntimeError
    처리하므로 여기서 KeyError 를 재발생시키지 않는다.
    """
    from pipeline.agents.atomizer import AtomizerConfig
    from pipeline.agents.forecaster import ForecasterConfig
    from pipeline.agents.mapper import MapperConfig
    from pipeline.agents.optimizer.agent import OptimizerConfig
    from pipeline.agents.reporter import ReporterConfig

    postgres_url = os.environ.get("POSTGRES_URL", "")  # Q3: KeyError → lifespan 이 먼저 검사
    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    azure_api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
    azure_api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    llm_model = os.environ.get("LLM_MODEL", "gpt-5.1-chat-ai-board-test")
    embedding_model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small-ai-board-test")
    chroma_host = os.environ.get("CHROMA_HOST", "localhost")
    chroma_port = int(os.environ.get("CHROMA_PORT", "8000"))

    mapper_cfg = MapperConfig(
        postgres_url=postgres_url,
        azure_endpoint=azure_endpoint,
        azure_api_key=azure_api_key,
        azure_api_version=azure_api_version,
        llm_model=llm_model,
        embedding_model=embedding_model,
        chroma_host=chroma_host,
        chroma_port=chroma_port,
    )
    atomizer_cfg = AtomizerConfig(
        postgres_url=postgres_url,
        azure_endpoint=azure_endpoint,
        azure_api_key=azure_api_key,
        azure_api_version=azure_api_version,
        embedding_model=embedding_model,
        chroma_host=chroma_host,
        chroma_port=chroma_port,
    )
    forecaster_cfg = ForecasterConfig(
        postgres_url=postgres_url,
        azure_endpoint=azure_endpoint,
        azure_api_key=azure_api_key,
        azure_api_version=azure_api_version,
        llm_model=llm_model,
        embedding_model=embedding_model,
        chroma_host=chroma_host,
        chroma_port=chroma_port,
    )
    optimizer_cfg = OptimizerConfig(
        postgres_url=postgres_url,
        azure_endpoint=azure_endpoint,
        azure_api_key=azure_api_key,
        azure_api_version=azure_api_version,
        llm_model=llm_model,
        chroma_host=chroma_host,
        chroma_port=chroma_port,
        chroma_ssl=False,
    )
    reporter_cfg = ReporterConfig(
        postgres_url=postgres_url,
        azure_endpoint=azure_endpoint,
        azure_api_key=azure_api_key,
        azure_api_version=azure_api_version,
        llm_model=llm_model,
    )
    return GraphConfig(
        mapper=mapper_cfg,
        atomizer=atomizer_cfg,
        forecaster=forecaster_cfg,
        optimizer=optimizer_cfg,
        reporter=reporter_cfg,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — PG pool + LangGraph graph/checkpointer 초기화 및 정리.

    app.state.pg     : PGClient
    app.state.graph  : compiled LangGraph (Command resume 가능)
    app.state.cfg    : GraphConfig

    POSTGRES_URL 환경변수 필수 — 미설정 시 RuntimeError (보안 차원).
    Q3: 이 검사가 _build_prod_graph_config() 보다 먼저 실행되어
        os.environ["POSTGRES_URL"] KeyError 를 방어한다.
    """
    pg_url = os.getenv("POSTGRES_URL")
    if not pg_url:
        raise RuntimeError("POSTGRES_URL 환경변수 미설정. .env.local 또는 export 로 명시 필요.")

    # PG pool
    pg = PGClient(pg_url)
    await pg.connect()
    app.state.pg = pg

    # LangGraph graph — build_graph 내부에서 build_checkpointer() 호출
    # (CPIA_CHECKPOINTER 환경변수로 checkpointer 종류 제어)
    cfg = _build_prod_graph_config()
    graph = build_graph(cfg)
    app.state.graph = graph
    app.state.cfg = cfg

    # ── Collector (IMAP IDLE) ─────────────────────────────────────
    # Spec §6.1. COLLECTOR_ENABLED=false 면 task 안 띄움.
    # Spec §10 결정: collector_cfg 로드 실패는 fail-fast (try/except 로 swallow X).
    # - POSTGRES_URL 누락 → KeyError 전파 (앱 부팅 불가) — 위 154 라인이 먼저 잡음
    # - COLLECTOR_ENABLED=true + USER/PW 누락 → load_collector_config 가 RuntimeError 던짐 (의도)
    # - COLLECTOR_ENABLED=false (default) → 자격증명 누락 허용, 단순히 collector_task 미생성
    collector_cfg = load_collector_config(graph_cfg=cfg)
    collector_task = None
    if collector_cfg.enabled:
        collector_task = asyncio.create_task(idle_loop(collector_cfg))

    try:
        yield
    finally:
        if collector_task is not None:
            request_shutdown()
            collector_task.cancel()
            try:
                await collector_task
            except asyncio.CancelledError:
                pass
        await pg.close()


app = FastAPI(
    title="CPIA Pipeline API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(exporter_router)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    """PG 연결 OK + version 확인."""
    pg: PGClient = app.state.pg
    row = await pg.fetch_one("SELECT 1 AS ok")
    return {
        "status": "ok",
        "pg": row is not None and row["ok"] == 1,
        "version": app.version,
    }


@app.post("/api/runs/{run_id}/hil_1/resume", response_model=Hil1ResumeResponse)
async def hil_1_resume(run_id: str, body: Hil1ResumeRequest) -> Hil1ResumeResponse:
    """HIL 1 interrupt 재개 — corrections 적용 후 다음 노드 반환.

    corrections key 는 string 필수 (drift #N5):
      hil_1_node 가 int(k) 변환 처리 (graph.py:128).
    mapping_corrections PG INSERT 는 hil_1_node 내부에서 자동 처리
      (graph.py:132~161) — endpoint 에서 별도 INSERT X.

    예외 분류 (Q2):
      EmptyChannelError  → 404 (thread_id 에 해당하는 checkpoint 없음)
      InvalidUpdateError → 409 (interrupt 상태 아님 — Command(resume) 부적합)
      그 외              → 500

    next_node 추출 (Q1):
      모든 *_node 함수가 current_node 키를 반환하므로 정상 경로에서는 항상 존재.
      None 인 경우(비정상) 는 명시적 500 raise — "unknown" silent fallback 제거.

    Response: {"next_node": "<resumed_node>"}
    """
    graph = app.state.graph

    # corrections dict[str, CorrectionItem] → dict[str, dict] (JSON serializable)
    corrections_payload: dict[str, dict] = {
        k: {"wa": v.wa, "l6_main": v.l6_main} for k, v in body.corrections.items()
    }

    try:
        result = await graph.ainvoke(
            Command(resume=corrections_payload),
            config={"configurable": {"thread_id": run_id}},
        )
    except EmptyChannelError as exc:
        # thread_id 에 해당하는 checkpoint 없음 → 404
        raise HTTPException(status_code=404, detail=f"run_id '{run_id}' 에 해당하는 checkpoint 없음") from exc
    except InvalidUpdateError as exc:
        # interrupt 상태가 아님 — Command(resume) 호출 부적합 → 409
        raise HTTPException(status_code=409, detail=f"graph 가 interrupt 대기 상태 아님: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"graph resume 실패: {exc}") from exc

    # Q1: current_node 가 None 이면 graph 반환 state 이상 — 명시적 500
    if not isinstance(result, dict) or result.get("current_node") is None:
        raise HTTPException(
            status_code=500,
            detail=f"graph 가 current_node 를 반환하지 않음. state keys: {list(result.keys()) if isinstance(result, dict) else type(result).__name__}",
        )

    next_node: str = result["current_node"]
    return Hil1ResumeResponse(next_node=next_node)


# ---------------------------------------------------------------------------
# Phase 4.3 — GET /api/sites
# ---------------------------------------------------------------------------

_SITES_SQL = """
SELECT s.site_id, s.name, s.location, s.status,
       s.plan_progress, s.actual_progress,
       (s.actual_progress - s.plan_progress) AS gap_percent,
       CASE WHEN s.plan_progress > 0 THEN s.actual_progress / s.plan_progress ELSE NULL END AS spi,
       COALESCE(f.today_productivity, 0) AS productivity_today,
       COALESCE(f.abnormal_trades, 0) AS abnormal_trades,
       s.fte_saved, s.hours_saved, s.headcount,
       (s.headcount * 140) AS total_hours,
       CASE WHEN s.headcount > 0 THEN s.hours_saved / (s.headcount * 140) * 100 ELSE 0 END AS ai_replacement_rate,
       f.expected_completion, f.delay_days
FROM sites s
LEFT JOIN LATERAL (
  SELECT MAX(today_productivity) AS today_productivity,
         COUNT(*) FILTER (WHERE risk_level <> '정상') AS abnormal_trades,
         MAX(expected_completion) AS expected_completion,
         MAX(delay_days) AS delay_days
  FROM forecasts WHERE run_id = s.last_run_id
) f ON TRUE
"""


def _serialize_site(row: dict[str, Any]) -> dict[str, Any]:
    """PG row → Site JSON (컬럼명 매핑 + NUMERIC float 변환 + date ISO 변환)."""
    expected_completion = row.get("expected_completion")
    if expected_completion is not None and hasattr(expected_completion, "isoformat"):
        expected_completion = expected_completion.isoformat()
    elif expected_completion is None:
        expected_completion = ""

    def _f(v: Any) -> float:  # NUMERIC → float
        return float(v) if v is not None else 0.0

    return {
        "id": row["site_id"],
        "name": row["name"],
        "location": row.get("location") or "",
        "status": row.get("status") or "unknown",
        "progress_planned": _f(row.get("plan_progress")),
        "progress_actual": _f(row.get("actual_progress")),
        "gap_percent": _f(row.get("gap_percent")),
        "spi": _f(row.get("spi")),
        "productivity_today": _f(row.get("productivity_today")),
        "abnormal_trades": int(row.get("abnormal_trades") or 0),
        "fte_saved": _f(row.get("fte_saved")),
        "hours_saved": _f(row.get("hours_saved")),
        "headcount": int(row.get("headcount") or 0),
        "total_hours": int(row.get("total_hours") or 0),
        "ai_replacement_rate": _f(row.get("ai_replacement_rate")),
        "expected_completion": expected_completion,
        # PoC: recovered_completion = expected_completion 그대로 (Optimizer recovery 미반영)
        "recovered_completion": expected_completion,
        "delay_days": _f(row.get("delay_days")),
        # PoC: recovery_days = 0 (Optimizer recovery 미반영)
        "recovery_days": 0,
    }


@app.get("/api/sites")
async def get_sites() -> list[dict[str, Any]]:
    """전체 현장 목록 — Site[].

    api-contract §3.1 SQL 그대로 사용. NUMERIC → float, date → ISO string.
    """
    pg: PGClient = app.state.pg
    rows = await pg.fetch_all(_SITES_SQL)
    return [_serialize_site(r) for r in rows]


# ---------------------------------------------------------------------------
# Phase 4.4 — GET /api/runs/:run_id/optimizer
# ---------------------------------------------------------------------------

_OPTIMIZER_SQL = """
SELECT
    l6_main || '-' || COALESCE(company, '') AS wp_id,
    diagnosis,
    degradation_cases,
    recommendations,
    recovery_distribution
FROM optimizer_advice
WHERE run_id = $1
"""


def _serialize_optimizer(row: dict[str, Any]) -> dict[str, Any]:
    """optimizer_advice row → OptimizerOutput JSON.

    similar_cases = degradation_cases JSONB (list[{date, description, outcome}])
    recommendations = [{rank, text}, ...] → list[str] (rank 제거)
    details = recovery_distribution key-value list (PoC 단순화)
    """
    similar_cases = row.get("degradation_cases") or []
    if not isinstance(similar_cases, list):
        similar_cases = []

    raw_recs = row.get("recommendations") or []
    if not isinstance(raw_recs, list):
        raw_recs = []
    # [{rank, text}, ...] → [str, ...] ; 단순 string 이면 그대로
    recommendations: list[str] = []
    for item in raw_recs:
        if isinstance(item, dict):
            recommendations.append(str(item.get("text", "")))
        else:
            recommendations.append(str(item))

    recovery_dist = row.get("recovery_distribution") or {}
    if isinstance(recovery_dist, dict):
        details = [{"label": k, "value": str(v)} for k, v in recovery_dist.items()]
    else:
        details = []

    return {
        "wp_id": row.get("wp_id") or "",
        "diagnosis": row.get("diagnosis") or "",
        "similar_cases": similar_cases,
        "recommendations": recommendations,
        "details": details,
    }


@app.get("/api/runs/{run_id}/optimizer")
async def get_optimizer(run_id: str) -> list[dict[str, Any]]:
    """run_id 의 optimizer_advice 목록 — OptimizerOutput[].

    run_id 미존재 시 빈 배열 반환 (PoC 단순화).
    """
    pg: PGClient = app.state.pg
    try:
        rows = await pg.fetch_all(_OPTIMIZER_SQL, run_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"optimizer 조회 실패: {exc}") from exc
    return [_serialize_optimizer(r) for r in rows]


# ---------------------------------------------------------------------------
# Phase 4.5 — GET /api/runs/:run_id/wp_summary
# ---------------------------------------------------------------------------

_WP_SUMMARY_SQL = """
SELECT
  mh.wa || '-' || mh.l6_main || '-' || mh.company AS wp_id,
  am.l6_main AS wp_name,
  am.l5_disc AS trade,
  mh.company AS bp_name,
  am.plan_start AS start_date,
  am.plan_finish AS end_date,
  CASE WHEN am.plan_total_qty > 0
    THEN COALESCE(SUM(mh2.today_qty), 0) / am.plan_total_qty * 100
    ELSE 0
  END AS progress_pct,
  COALESCE(f.today_productivity, 0) AS productivity,
  CASE
    WHEN f.risk_level = '정상' THEN 'normal'
    WHEN f.risk_level = '주의' THEN 'caution'
    WHEN f.risk_level = '이상' THEN 'risk'
    ELSE 'normal'
  END AS status
FROM mapped_history mh
LEFT JOIN activity_master am
  ON am.wa = mh.wa AND am.l6_main = mh.l6_main AND am.company = mh.company
LEFT JOIN mapped_history mh2
  ON mh2.wa = mh.wa AND mh2.l6_main = mh.l6_main AND mh2.company = mh.company
LEFT JOIN forecasts f
  ON f.wa = mh.wa AND f.l6_main = mh.l6_main AND f.company = mh.company AND f.run_id = mh.run_id
WHERE mh.run_id = $1
GROUP BY mh.wa, mh.l6_main, mh.company, am.l6_main, am.l5_disc, am.plan_start, am.plan_finish, am.plan_total_qty, f.today_productivity, f.risk_level
"""


def _serialize_wp_summary(row: dict[str, Any]) -> dict[str, Any]:
    """mapped_history + activity_master + forecasts join row → WPSummaryRow JSON."""

    def _f(v: Any) -> float:
        return float(v) if v is not None else 0.0

    start_date = row.get("start_date")
    if start_date is not None and hasattr(start_date, "isoformat"):
        start_date = start_date.isoformat()
    else:
        start_date = start_date or ""

    end_date = row.get("end_date")
    if end_date is not None and hasattr(end_date, "isoformat"):
        end_date = end_date.isoformat()
    else:
        end_date = end_date or ""

    return {
        "wp_id": row.get("wp_id") or "",
        "wp_name": row.get("wp_name") or "",
        "trade": row.get("trade") or "",
        "bp_name": row.get("bp_name") or "",
        "start_date": start_date,
        "end_date": end_date,
        "progress_pct": _f(row.get("progress_pct")),
        "productivity": _f(row.get("productivity")),
        "status": row.get("status") or "normal",
    }


@app.get("/api/runs/{run_id}/wp_summary")
async def get_wp_summary(run_id: str) -> list[dict[str, Any]]:
    """run_id 의 WP 단위 요약 — WPSummaryRow[].

    activity_master + mapped_history + forecasts triplet join.
    run_id 미존재 시 빈 배열 반환 (PoC 단순화).
    """
    pg: PGClient = app.state.pg
    try:
        rows = await pg.fetch_all(_WP_SUMMARY_SQL, run_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"wp_summary 조회 실패: {exc}") from exc
    return [_serialize_wp_summary(r) for r in rows]


# ---------------------------------------------------------------------------
# Phase 4.6 — GET /api/sites/:site_id/reports?days=30
# ---------------------------------------------------------------------------

_SITE_REPORTS_SQL = """
SELECT
  pr.report_date AS date,
  CASE
    WHEN MAX(CASE WHEN f.risk_level = '이상' THEN 1 ELSE 0 END) = 1 THEN 'risk'
    WHEN MAX(CASE WHEN f.risk_level = '주의' THEN 1 ELSE 0 END) = 1 THEN 'caution'
    WHEN COUNT(f.id) > 0 THEN 'normal'
    ELSE 'unknown'
  END AS status,
  COALESCE(MAX(f.today_productivity), 0) AS productivity_today,
  COALESCE(MAX(f.delay_days), 0) AS delay_days,
  0 AS recovery_days
FROM pipeline_runs pr
LEFT JOIN forecasts f ON f.run_id = pr.run_id
WHERE pr.site_id = $1
  AND pr.report_date >= CURRENT_DATE - ($2::int)
GROUP BY pr.report_date
ORDER BY pr.report_date ASC
"""


def _serialize_report_daily(row: dict[str, Any]) -> dict[str, Any]:
    """pipeline_runs + forecasts join row -> ReportDaily JSON."""

    def _f(v: Any) -> float:
        return float(v) if v is not None else 0.0

    date_val = row.get("date")
    if date_val is not None and hasattr(date_val, "isoformat"):
        date_val = date_val.isoformat()
    else:
        date_val = date_val or ""

    return {
        "date": date_val,
        "status": row.get("status") or "unknown",
        "productivity_today": _f(row.get("productivity_today")),
        "delay_days": _f(row.get("delay_days")),
        "recovery_days": 0,
    }


@app.get("/api/sites/{site_id}/reports")
async def get_site_reports(site_id: str, days: int = 30) -> list[dict[str, Any]]:
    """site_id 의 날짜별 작업일보 요약 — ReportDaily[].

    days (default 30, max 90) 범위 내 pipeline_runs + forecasts 집계.
    미존재 site_id 는 빈 배열 반환 (PoC 단순화).
    """
    days = min(days, 90)
    pg: PGClient = app.state.pg
    try:
        rows = await pg.fetch_all(_SITE_REPORTS_SQL, site_id, days)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"site reports 조회 실패: {exc}") from exc
    return [_serialize_report_daily(r) for r in rows]


# ---------------------------------------------------------------------------
# Phase 4.7 — GET /api/dashboard/performance
# ---------------------------------------------------------------------------

_DASHBOARD_PERFORMANCE_SQL = """
WITH last_runs AS (
  SELECT last_run_id FROM sites WHERE last_run_id IS NOT NULL
)
SELECT
  COALESCE(AVG(f.today_productivity), 0) AS productivity_today,
  COALESCE(MAX(f.delay_days), 0) AS delay_days,
  COALESCE(SUM(
    COALESCE((oa.recovery_distribution->>'d+1')::int * 1, 0) +
    COALESCE((oa.recovery_distribution->>'d+2')::int * 2, 0) +
    COALESCE((oa.recovery_distribution->>'d+3')::int * 3, 0) +
    COALESCE((oa.recovery_distribution->>'d+5')::int * 5, 0) +
    COALESCE((oa.recovery_distribution->>'d+7')::int * 7, 0)
  ), 0) AS recoverable_days,
  COUNT(f.id) FILTER (WHERE f.risk_level <> '정상') AS abnormal_trades
FROM last_runs lr
LEFT JOIN forecasts f ON f.run_id = lr.last_run_id
LEFT JOIN optimizer_advice oa ON oa.run_id = lr.last_run_id
"""


@app.get("/api/dashboard/performance")
async def get_dashboard_performance() -> dict[str, Any]:
    """전 site 통합 KPI 카드 — fleet_kpi.

    last_run_id 기준으로 forecasts + optimizer_advice 집계.
    DB 조회 결과 없음 -> 0 fallback.
    """
    pg: PGClient = app.state.pg
    try:
        row = await pg.fetch_one(_DASHBOARD_PERFORMANCE_SQL)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"dashboard/performance 조회 실패: {exc}") from exc

    if row is None:
        return {
            "productivity_today": 0.0,
            "delay_days": 0.0,
            "recoverable_days": 0,
            "abnormal_trades": 0,
        }

    def _f(v: Any) -> float:
        return float(v) if v is not None else 0.0

    def _i(v: Any) -> int:
        return int(v) if v is not None else 0

    return {
        "productivity_today": _f(row.get("productivity_today")),
        "delay_days": _f(row.get("delay_days")),
        "recoverable_days": _i(row.get("recoverable_days")),
        "abnormal_trades": _i(row.get("abnormal_trades")),
    }


# ---------------------------------------------------------------------------
# Phase 4.8 — GET /api/dashboard/impact
# ---------------------------------------------------------------------------

_DASHBOARD_IMPACT_SQL = """
SELECT site_id, name AS site_name, hours_saved, fte_saved
FROM sites
ORDER BY hours_saved DESC
"""


def _serialize_impact_site(row: dict[str, Any]) -> dict[str, Any]:
    """sites row -> ImpactSiteDistribution JSON."""

    def _f(v: Any) -> float:
        return float(v) if v is not None else 0.0

    return {
        "site_id": row.get("site_id") or "",
        "site_name": row.get("site_name") or "",
        "hours_saved": _f(row.get("hours_saved")),
        "fte_saved": _f(row.get("fte_saved")),
    }


@app.get("/api/dashboard/impact")
async def get_dashboard_impact() -> list[dict[str, Any]]:
    """전 site 의 AI impact 분포 — ImpactSiteDistribution[].

    sites 테이블의 hours_saved / fte_saved 내림차순.
    빈 테이블이면 빈 배열 반환 (PoC 단순화).
    """
    pg: PGClient = app.state.pg
    try:
        rows = await pg.fetch_all(_DASHBOARD_IMPACT_SQL)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"dashboard/impact 조회 실패: {exc}") from exc
    return [_serialize_impact_site(r) for r in rows]


# ---------------------------------------------------------------------------
# Phase 4.9 — GET /api/agents/status
# ---------------------------------------------------------------------------

_AGENTS_META: list[dict[str, Any]] = [
    {
        "step": 1,
        "name": "Collector",
        "korean_name": "수집",
        "description": "작업일보 파일 자동 수집",
        "model": "규칙 기반",
        "group": "collect",
    },
    {
        "step": 2,
        "name": "Parser",
        "korean_name": "파싱",
        "description": "텍스트 → 구조화 JSON",
        "model": "Sonnet 4.6",
        "group": "collect",
    },
    {
        "step": 3,
        "name": "Mapper",
        "korean_name": "매핑",
        "description": "WBS 활동 매핑",
        "model": "Sonnet 4.6",
        "group": "collect",
    },
    {
        "step": 4,
        "name": "Atomizer",
        "korean_name": "Atomizer",
        "description": "Vector DB 적재",
        "model": "임베딩 모델",
        "group": "collect",
    },
    {
        "step": 5,
        "name": "Reporter",
        "korean_name": "보고",
        "description": "통합 보고서 생성",
        "model": "Opus 4.7",
        "group": "analyze",
    },
    {
        "step": 6,
        "name": "Forecaster",
        "korean_name": "예측",
        "description": "생산성 진단",
        "model": "Sonnet 4.6",
        "group": "analyze",
    },
    {
        "step": 7,
        "name": "Optimizer",
        "korean_name": "조언",
        "description": "맥락 기반 조언",
        "model": "Opus 4.7",
        "group": "analyze",
    },
    {
        "step": 8,
        "name": "Exporter",
        "korean_name": "내보내기",
        "description": "graph cycle 마다 통합 xlsx 사전생성 (consolidated_reports UPSERT)",
        "model": "openpyxl",
        "group": "analyze",
    },
]

_AGENT_ACTIVE_COUNT_SQL = """
SELECT COUNT(*) AS count
FROM pipeline_runs
WHERE current_node = $1
  AND status NOT IN ('completed', 'failed')
"""


@app.get("/api/agents/status")
async def get_agents_status() -> list[dict[str, Any]]:
    """7개 Agent 메타데이터 + 실시간 active_count / state 반환 — AgentStatus[].

    active_count = pipeline_runs WHERE current_node = agent 이름(소문자) AND status not terminal.
    state 도출:
      active_count > 0 → "processing"
      해당 agent 가 waiting_hil 상태 (waiting_hil_1 / waiting_hil_2) → "waiting"
      그 외 → "idle"
    """
    pg: PGClient = app.state.pg
    result: list[dict[str, Any]] = []
    try:
        for meta in _AGENTS_META:
            node_name = meta["name"].lower()
            rows = await pg.fetch_all(_AGENT_ACTIVE_COUNT_SQL, node_name)
            active_count = int(rows[0]["count"]) if rows else 0

            if active_count > 0:
                state = "processing"
            else:
                state = "idle"

            result.append(
                {
                    **meta,
                    "active_count": active_count,
                    "state": state,
                }
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"agents/status 조회 실패: {exc}") from exc
    return result


# ---------------------------------------------------------------------------
# Phase 4.10 — GET /api/sites/:site_id/wbs_tree
# ---------------------------------------------------------------------------

_WBS_TREE_SQL = """
SELECT DISTINCT l5_disc, l6_main
FROM activity_master
WHERE l5_disc IS NOT NULL
ORDER BY l5_disc, l6_main
"""


def _build_wbs_tree(rows: list[dict[str, Any]], site_id: str) -> dict[str, Any]:
    """activity_master rows → WBSNode 단일 트리.

    Level 1 (root): site_id (type="building")
    Level 2: l5_disc (type="trade")
    Level 3: l6_main (type="work_package")

    PoC 단순화:
      review_count = 0 (backlog: mapping_corrections 누적 풍부화 필요)
      status = "unknown" (backlog: forecasts.risk_level 최악값 반영 필요)
    """
    root: dict[str, Any] = {
        "id": site_id,
        "type": "building",
        "name": site_id,
        "parent_id": None,
        "review_count": 0,
        "status": "unknown",
        "children": [],
    }
    trades: dict[str, dict[str, Any]] = {}

    for r in rows:
        l5 = r.get("l5_disc") or ""
        l6 = r.get("l6_main") or ""
        if not l5:
            continue

        if l5 not in trades:
            trade_node: dict[str, Any] = {
                "id": f"{site_id}/{l5}",
                "type": "trade",
                "name": l5,
                "parent_id": site_id,
                "review_count": 0,
                "status": "unknown",
                "children": [],
            }
            trades[l5] = trade_node
            root["children"].append(trade_node)

        if l6:
            trades[l5]["children"].append(
                {
                    "id": f"{site_id}/{l5}/{l6}",
                    "type": "work_package",
                    "name": l6,
                    "parent_id": f"{site_id}/{l5}",
                    "review_count": 0,
                    "status": "unknown",
                }
            )

    return root


@app.get("/api/sites/{site_id}/wbs_tree")
async def get_wbs_tree(site_id: str) -> dict[str, Any]:
    """site_id 의 WBS 트리 — WBSNode 단일 루트 객체.

    activity_master 의 l5_disc / l6_main 2단계를 site_id 루트 아래로 구성.
    PoC 단순화: review_count=0, status='unknown' — 다음 cycle 에 풍부화.
    """
    pg: PGClient = app.state.pg
    try:
        rows = await pg.fetch_all(_WBS_TREE_SQL)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"wbs_tree 조회 실패: {exc}") from exc
    return _build_wbs_tree(rows, site_id)


# ---------------------------------------------------------------------------
# Phase 4.11 — GET /api/tasks
# ---------------------------------------------------------------------------

# current_node → 파이프라인 전체 진행률 매핑
_NODE_PERCENT: dict[str, float] = {
    "collector": 12.5,
    "parser": 25.0,
    "mapper": 37.5,
    "hil_1": 37.5,
    "atomizer": 50.0,
    "reporter": 62.5,
    "forecaster": 75.0,
    "optimizer": 87.5,
    "completed": 100.0,
}

# AgentStageProgress 생성용 메타 (7 agent + HIL)
_STAGE_META: list[dict[str, Any]] = [
    {"step": 1, "agent": "Collector", "is_hil": False, "node": "collector"},
    {"step": 2, "agent": "Parser", "is_hil": False, "node": "parser"},
    {"step": 3, "agent": "Mapper", "is_hil": False, "node": "mapper"},
    {"step": 3.5, "agent": "HIL Review", "is_hil": True, "node": "hil_1"},
    {"step": 4, "agent": "Atomizer", "is_hil": False, "node": "atomizer"},
    {"step": 5, "agent": "Reporter", "is_hil": False, "node": "reporter"},
    {"step": 6, "agent": "Forecaster", "is_hil": False, "node": "forecaster"},
    {"step": 7, "agent": "Optimizer", "is_hil": False, "node": "optimizer"},
]

_TASKS_SQL = """
SELECT
  pr.report_date AS date,
  COUNT(*) AS total_count,
  AVG(
    CASE pr.current_node
      WHEN 'collector'  THEN 12.5
      WHEN 'parser'     THEN 25.0
      WHEN 'mapper'     THEN 37.5
      WHEN 'hil_1'      THEN 37.5
      WHEN 'atomizer'   THEN 50.0
      WHEN 'reporter'   THEN 62.5
      WHEN 'forecaster' THEN 75.0
      WHEN 'optimizer'  THEN 87.5
      WHEN 'completed'  THEN 100.0
      ELSE 0.0
    END
  ) AS progress_percent,
  CASE
    WHEN BOOL_OR(pr.status = 'failed') THEN 'review_pending'
    WHEN BOOL_AND(pr.status = 'completed') THEN 'completed'
    ELSE 'running'
  END AS status,
  BOOL_OR(
    EXISTS (
      SELECT 1 FROM forecasts f
      WHERE f.run_id = pr.run_id AND f.risk_level <> '정상'
    )
  ) AS has_anomaly
FROM pipeline_runs pr
WHERE pr.site_id = $1
  AND pr.report_date >= CURRENT_DATE - ($2::int)
GROUP BY pr.report_date
ORDER BY pr.report_date DESC
"""

_TASKS_ITEMS_SQL = """
SELECT
  pr.run_id::text AS run_id,
  pr.report_date::text AS date,
  mh.l6_main AS trade,
  mh.company AS contractor,
  pr.status
FROM pipeline_runs pr
LEFT JOIN mapped_history mh
  ON mh.run_id = pr.run_id
WHERE pr.site_id = $1
  AND pr.report_date >= CURRENT_DATE - ($2::int)
ORDER BY pr.report_date DESC, mh.l6_main
"""


def _serialize_daily_task(row: dict[str, Any]) -> dict[str, Any]:
    """pipeline_runs 집계 row → DailyTask JSON."""
    date_val = row.get("date")
    if date_val is not None and hasattr(date_val, "isoformat"):
        date_val = date_val.isoformat()
    else:
        date_val = str(date_val) if date_val is not None else ""

    return {
        "date": date_val,
        "total_count": int(row.get("total_count") or 0),
        "progress_percent": float(row.get("progress_percent") or 0.0),
        "status": row.get("status") or "running",
        "has_anomaly": bool(row.get("has_anomaly") or False),
    }


def _build_progress_by_date(
    tasks: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """날짜별 AgentStageProgress 8건 (7 agent + HIL) 생성.

    PoC 단순화: 각 stage 의 received = total_count, processed / percent = progress_percent
    기반으로 비례 추산. waiting_hil = False (PoC).
    backlog: pipeline_runs.current_node 실제 분포 기반 정밀화 필요.
    """
    result: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        date = task["date"]
        total = task["total_count"]
        overall_pct = task["progress_percent"]

        stages: list[dict[str, Any]] = []
        for sm in _STAGE_META:
            node_pct = _NODE_PERCENT.get(sm["node"], 0.0)
            # 해당 agent 까지 도달한 비율: overall >= node_pct 면 전부 processed
            if overall_pct >= node_pct:
                processed = total
                percent = 100.0
            else:
                processed = 0
                percent = 0.0

            stages.append(
                {
                    "step": sm["step"],
                    "agent": sm["agent"],
                    "is_hil": sm["is_hil"],
                    "received": total,
                    "processed": processed,
                    "percent": percent,
                    "waiting_hil": False,
                }
            )
        result[date] = stages
    return result


def _build_items_by_date(
    item_rows: list[dict[str, Any]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """mapped_history + pipeline_runs join rows → itemsByDate.

    itemsByDate[date][agent_name] = AgentTaskItem[]
    agent_name key = "Collector" ... "Optimizer" (AgentTaskItemList 에서 selectedAgent 와 일치 필요).
    PoC 단순화: 모든 item 은 "Collector" key 에 배치 (다음 cycle 에 current_node 기반 라우팅 필요).
    status 매핑:
      completed  → "done"
      running    → "processing"
      waiting_*  → "hil_pending"
      failed     → "blocked"
      그 외      → "received"
    """
    status_map = {
        "completed": "done",
        "running": "processing",
        "waiting_hil_1": "hil_pending",
        "waiting_hil_2": "hil_pending",
        "failed": "blocked",
    }

    result: dict[str, dict[str, list[dict[str, Any]]]] = {}
    idx_by_date: dict[str, int] = {}

    for row in item_rows:
        date_val = row.get("date") or ""
        if hasattr(date_val, "isoformat"):
            date_val = date_val.isoformat()
        else:
            date_val = str(date_val)

        trade = row.get("trade") or ""
        contractor = row.get("contractor") or ""
        run_id_str = row.get("run_id") or ""
        raw_status = row.get("status") or "running"
        item_status = status_map.get(raw_status, "received")

        if date_val not in result:
            result[date_val] = {"Collector": []}
            idx_by_date[date_val] = 1

        # 고유 ID: RPT-<date>-<순번>
        item_id = f"RPT-{date_val.replace('-', '')}-{idx_by_date[date_val]:03d}"
        idx_by_date[date_val] += 1

        result[date_val]["Collector"].append(
            {
                "id": item_id,
                "trade": trade,
                "contractor": contractor,
                "status": item_status,
            }
        )

    return result


@app.get("/api/tasks")
async def get_tasks(site_id: str, days: int = 30) -> dict[str, Any]:
    """날짜별 작업일보 처리 현황 — DailyTask[] + progressByDate + itemsByDate.

    tasks:           날짜별 pipeline_runs 집계 (DailyTask[])
    progressByDate:  날짜 → 8단계 AgentStageProgress[] (7 agent + HIL)
    itemsByDate:     날짜 → agent → AgentTaskItem[]

    PoC 단순화:
      progressByDate 는 overall progress_percent 에서 비례 추산.
      itemsByDate 는 "Collector" key 에 전부 배치 (current_node 기반 분류는 backlog).
    """
    days = min(days, 90)
    pg: PGClient = app.state.pg
    try:
        task_rows = await pg.fetch_all(_TASKS_SQL, site_id, days)
        item_rows = await pg.fetch_all(_TASKS_ITEMS_SQL, site_id, days)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"tasks 조회 실패: {exc}") from exc

    tasks = [_serialize_daily_task(r) for r in task_rows]
    progress_by_date = _build_progress_by_date(tasks)
    items_by_date = _build_items_by_date(item_rows)

    return {
        "tasks": tasks,
        "progressByDate": progress_by_date,
        "itemsByDate": items_by_date,
    }
