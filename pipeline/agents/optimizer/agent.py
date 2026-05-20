"""Optimizer agent — optimize() + cold_start + _compute_recovery_distribution.

Spec: docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §7

원칙:
- retrieve import X — pre_optimizer_cases (state 사전 영속) 만 사용 (결정 #8 + F5).
- _compute_recovery_distribution 은 코드단 deterministic 산출 (결정 #20).
  LLM 응답이 recovery_distribution 박았으면 override X (코드 값이 정답).
- cold_start (len(cases) < 3): LLM skip, diagnosis="cold_start", recommendations=[],
  recovery_pattern=[], recovery_distribution=_compute_recovery_distribution(cases).
  cold_start row 도 PG INSERT 보장 (cold_start signal 보존).
- fail-fast: LLM crash 시 exception 그대로 raise (결정 #10).
- temperature 박지 않음 (gpt-5 family 미지원 — 결정 #9).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date

from openai import AzureOpenAI

from pipeline.agents.optimizer.prompt import (
    FEW_SHOT_MESSAGES,
    SYSTEM_PROMPT,
    build_llm_user_input,
)
from pipeline.agents.optimizer.view_builder import (
    _build_contractor_bars,
    _build_kpi,
    _build_optimizer_view,
    _build_productivity_views,
    _build_quadrant,
    _build_s_curve,
    _build_scenarios,
    _build_trade_bars,
    _build_wp_summary,
)
from pipeline.db import PGClient

logger = logging.getLogger(__name__)


@dataclass
class OptimizerConfig:
    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    llm_model: str  # "gpt-5.1-chat-ai-board-test"
    postgres_url: str
    chroma_host: str
    chroma_port: int
    chroma_ssl: bool = False
    azure_timeout: float = 60.0
    azure_max_retries: int = 3


def _compute_recovery_distribution(cases: list[dict]) -> dict[str, int]:
    """결정 #20 — 코드단 deterministic 산출. LLM 출력 override.

    Counter([c.recovery.recovery_days for c in cases]) → {"d+1": N, "d+2": N, ..., "not_recovered": N}
    """
    counter: Counter[str] = Counter()
    for c in cases:
        rd = c["recovery"]["recovery_days"]
        key = f"d+{rd}" if rd is not None else "not_recovered"
        counter[key] += 1
    return dict(counter)


def _compose_cold_start_row(r: dict, cases: list[dict], run_id: uuid.UUID) -> dict:
    return {
        "run_id": run_id,
        "company": r["company"],
        "l6_main": r["l6_main"],
        "forecast_assessment": r["assessment"],
        "diagnosis": "cold_start",
        "degradation_cases": cases,
        "recovery_pattern": [],
        "recovery_distribution": _compute_recovery_distribution(cases),
        "recommendations": [],
    }


def _compose_row(r: dict, cases: list[dict], llm_output: dict, run_id: uuid.UUID) -> dict:
    recovery_pattern = [{"date": c["date"], "recovery_days": c["recovery"]["recovery_days"]} for c in cases]
    return {
        "run_id": run_id,
        "company": r["company"],
        "l6_main": r["l6_main"],
        "forecast_assessment": r["assessment"],
        "diagnosis": llm_output["diagnosis"],
        "degradation_cases": cases,
        "recovery_pattern": recovery_pattern,
        # ★ LLM 출력 override — 코드단 deterministic 값을 정답으로 박음
        "recovery_distribution": _compute_recovery_distribution(cases),
        "recommendations": llm_output["recommendations"],
    }


def _call_azure_llm(llm_input: dict, cfg: OptimizerConfig, azure: AzureOpenAI) -> dict:
    """Azure gpt-5.1 호출 — fail-fast (retry 없음, exception 그대로 raise)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *FEW_SHOT_MESSAGES,
        {"role": "user", "content": json.dumps(llm_input, ensure_ascii=False)},
    ]
    resp = azure.chat.completions.create(
        model=cfg.llm_model,
        messages=messages,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


async def optimize(
    forecast: list[dict],
    hil_2_selection: list[str],
    pre_optimizer_cases: dict[str, list[dict]],
    run_id: uuid.UUID,
    today: date,
    cfg: OptimizerConfig,
    site_id: Optional[str] = None,
    mapped: Optional[list] = None,
) -> list[dict]:
    """선택된 그룹 별 advice row 생성 + PG insert. fail-fast (LLM crash = 전체 fail).

    Args:
        forecast: Forecaster 산출 row list (state["forecast"]).
        hil_2_selection: PM 이 hil_2 modal 에서 선택한 "{company}|{l6_main}" key list.
        pre_optimizer_cases: hil_2_node 가 사전 영속한 dict[key, cases].
            각 case 는 retrieve 모듈 산출물 (degradation case + 'recovery' 키 trajectory) 그대로.
            agent.py 본 함수는 retrieve 를 호출하지 않음 — state 사전 영속 값만 소비 (결정 #8).
        run_id: pipeline_runs run_id.
        today: 보고 일자.
        cfg: OptimizerConfig.
        site_id: 현장 식별자 (sites.site_id) — view builder UPSERT 용.
        mapped: Mapper 산출 Activity list — view builder 에 전달.

    Returns:
        advice row list (state["optimizer_advice"] 에 박힘).
    """
    mapped = mapped or []
    advice_rows: list[dict] = []
    azure = AzureOpenAI(
        api_key=cfg.azure_api_key,
        api_version=cfg.azure_api_version,
        azure_endpoint=cfg.azure_endpoint,
        timeout=cfg.azure_timeout,
        max_retries=cfg.azure_max_retries,
    )
    for r in forecast:
        key = f"{r['company']}|{r['l6_main']}"
        if key not in hil_2_selection:
            continue
        cases = pre_optimizer_cases.get(key, [])
        if len(cases) < 3:
            advice_rows.append(_compose_cold_start_row(r, cases, run_id))
            continue
        llm_input = build_llm_user_input(r, cases)
        llm_output = _call_azure_llm(llm_input, cfg, azure)  # fail-fast
        advice_rows.append(_compose_row(r, cases, llm_output, run_id))

    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        for row in advice_rows:
            await pg.insert_optimizer_advice(row)

        # view builder 8 jsonb 산출 + daily_reports partial UPSERT
        if site_id:
            try:
                productivity = await _build_productivity_views(pg, run_id, site_id, today, forecast, mapped)
                quadrant = await _build_quadrant(pg, site_id, today, productivity)
                # wa_lookup: (l6_main, company) → DISTINCT wa list (NULL 제외).
                # spec §8.3 — quadrant dot 의 wp_id 와 by_wp key 매칭 보장 (fan-out).
                wa_rows = await pg._pool.fetch(
                    """
                    SELECT l6_main, company,
                           array_agg(DISTINCT wa) FILTER (WHERE wa IS NOT NULL) AS wa_list
                    FROM mapper_activities
                    WHERE run_id = $1
                    GROUP BY l6_main, company
                    """,
                    run_id,
                )
                wa_lookup = {
                    (r["l6_main"], r["company"]): list(r["wa_list"] or [])
                    for r in wa_rows
                }
                view_jsonbs = {
                    "productivity_jsonb": productivity,
                    "kpi_jsonb": await _build_kpi(pg, site_id, today, productivity),
                    "contractor_bars_jsonb": _build_contractor_bars(productivity),
                    "trade_bars_jsonb": _build_trade_bars(productivity),
                    "quadrant_jsonb": quadrant,
                    "wp_summary_jsonb": await _build_wp_summary(pg, site_id, today, productivity, quadrant),
                    "s_curve_jsonb": await _build_s_curve(pg, site_id, today),
                    "optimizer_view_jsonb": _build_optimizer_view(
                        advice_rows, forecast, mapped, wa_lookup=wa_lookup
                    ),
                    "scenarios_jsonb": _build_scenarios(advice_rows, forecast),
                }
                for col, val in view_jsonbs.items():
                    try:
                        await pg.upsert_daily_report_view_col(run_id, site_id, today, col, val)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("upsert %s fail: %s. partial write 유지.", col, e)
            except Exception as e:  # noqa: BLE001
                logger.error("build_optimizer_views fail: %s. backfill 으로 fallback.", e)
    finally:
        await pg.close()
    return advice_rows
