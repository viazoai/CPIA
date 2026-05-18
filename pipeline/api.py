"""CPIA Pipeline FastAPI — /health + /run + /resume + /status.

Phase 4.1: 골격 + lifespan + GET /health 1개.
Phase 4.2: POST /api/runs/:run_id/hil_1/resume + lifespan graph/checkpointer 통합.
Phase 4.3: GET /api/sites — Site[] 반환.
Phase 4.4: GET /api/runs/:run_id/optimizer — OptimizerOutput[] 반환.
Phase 4.5: GET /api/runs/:run_id/wp_summary — WPSummaryRow[] 반환.
Phase 4.6: GET /api/sites/:site_id/reports — ReportDaily[] 반환.
Phase 4.7: GET /api/dashboard/performance — fleet_kpi 반환.
Phase 4.8: GET /api/dashboard/impact — ImpactSiteDistribution[] 반환.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from langgraph.errors import EmptyChannelError, InvalidUpdateError
from langgraph.types import Command
from pydantic import BaseModel

from pipeline.db import PGClient
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

    try:
        yield
    finally:
        await pg.close()


app = FastAPI(
    title="CPIA Pipeline API",
    version="0.1.0",
    lifespan=lifespan,
)


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
