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

import asyncio
import json
import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date

import openai
from openai import AzureOpenAI

from pipeline.agents._concurrency import get_llm_semaphore
from pipeline.agents.optimizer._trade_frames import lookup_frame
from pipeline.agents.optimizer.prompt import (
    DIAG_PROMPT_V10,
    FEW_SHOT_MESSAGES,
    RECS_PROMPT_V10,
    SCENARIOS_PROMPT,
    SCENARIOS_PROMPT_V10,
    SYSTEM_PROMPT,
    build_diag_input_v10,
    build_llm_user_input,
    build_recs_input_v10,
    build_scenarios_input_v10,
    build_scenarios_llm_input,
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


def _apply_augmentation_weight(rows: list[dict]) -> list[tuple[dict, float]]:
    """augment 된 case 는 0.5 가중치, 일반 1.0. backfill 산출물 활용."""
    return [
        (r, 0.5 if r.get("metadata", {}).get("augmented") else 1.0)
        for r in rows
    ]


def _compose_row(r: dict, cases: list[dict], llm_output: dict, run_id: uuid.UUID, scenarios: Optional[dict] = None) -> dict:
    recovery_pattern = [{"date": c["date"], "recovery_days": c["recovery"]["recovery_days"]} for c in cases]
    row = {
        "run_id": run_id,
        "company": r["company"],
        "l6_main": r["l6_main"],
        "forecast_assessment": r["assessment"],
        "diagnosis": llm_output["diagnosis"],
        "degradation_cases": cases,
        "recovery_pattern": recovery_pattern,
        # LLM 출력 override — 코드단 deterministic 값을 정답으로 박음
        "recovery_distribution": _compute_recovery_distribution(cases),
        "recommendations": llm_output["recommendations"],
    }
    if scenarios is not None:
        row["scenarios"] = scenarios
    return row


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


def _call_azure_scenarios_llm(scenarios_input: dict, cfg: OptimizerConfig, azure: AzureOpenAI) -> dict:
    """scenarios LLM 호출 — SCENARIOS_PROMPT 사용. fail-fast."""
    messages = [
        {"role": "system", "content": SCENARIOS_PROMPT},
        {"role": "user", "content": json.dumps(scenarios_input, ensure_ascii=False)},
    ]
    resp = azure.chat.completions.create(
        model=cfg.llm_model,
        messages=messages,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


async def _call_azure_llm_async(llm_input: dict, cfg: OptimizerConfig, azure: AzureOpenAI) -> dict:
    """sync _call_azure_llm 을 asyncio.to_thread 로 감쌈 — 실 병렬 효과."""
    return await asyncio.to_thread(_call_azure_llm, llm_input, cfg, azure)


async def _call_azure_scenarios_llm_async(scenarios_input: dict, cfg: OptimizerConfig, azure: AzureOpenAI) -> dict:
    """sync _call_azure_scenarios_llm 을 asyncio.to_thread 로 감쌈."""
    return await asyncio.to_thread(_call_azure_scenarios_llm, scenarios_input, cfg, azure)


# ────────────────────────────────────────────────────────────────────────────────
# V10 — 2단계 호출 (recs ‖ scenarios 병렬 + diag 순차) + retry 3회
# Task 13 (2026-05-27). 사용자 의도:
#   1. recs/diag 분리 — diag 가 recs.recommendations 를 명시적으로 인용 (Action Plan 핵심 포인트).
#   2. scenarios 는 진단 path 와 독립 — asyncio.gather(recs, scenarios) → recs 완료 후 diag.
#   3. cold case 절대 금지 — cases<3 도 LLM 호출 (cold_start dispatch X).
#   4. Azure 일시 오류 (timeout / rate limit / JSON 파싱 실패) 시 in-line retry 3회 + exponential
#      backoff. 마지막 실패 시 failed_wps 취합 (Task 30 종합 retry batch 처리).
# ────────────────────────────────────────────────────────────────────────────────


def _call_v10_llm(prompt: str, payload: dict, cfg: OptimizerConfig, azure: AzureOpenAI) -> dict:
    """V10 LLM 호출 — prompt 인자화. fail-fast. retry 는 caller 가 처리."""
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    resp = azure.chat.completions.create(
        model=cfg.llm_model,
        messages=messages,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


async def _call_v10_llm_async(prompt: str, payload: dict, cfg: OptimizerConfig, azure: AzureOpenAI) -> dict:
    """sync _call_v10_llm 을 asyncio.to_thread 로 감쌈 — 실 병렬 효과."""
    return await asyncio.to_thread(_call_v10_llm, prompt, payload, cfg, azure)


async def _process_one_v10_with_retry(
    r: dict,
    cases: list[dict],
    run_id: uuid.UUID,
    today: date,
    cfg: OptimizerConfig,
    azure: AzureOpenAI,
    sem: asyncio.Semaphore,
    failed_wps: list,
    max_retries: int = 3,
):
    """V10 2단계 + scenarios 병렬 + retry 3회.

    1. recs ‖ scenarios 병렬 (asyncio.gather) — 독립 path.
    2. recs 결과 받은 후 diag 순차 (recs.recommendations 인용).
    3. retry: openai.APIError / asyncio.TimeoutError / json.JSONDecodeError / KeyError 발생 시
       exponential backoff (2^(attempt+1) 초) 후 재시도.
    4. 3회 모두 실패 → failed_wps 에 append + None 반환 (caller 가 skip).

    사용자 의도: cold case 절대 금지 → cases<3 도 LLM 호출. 실패만 retry batch.
    """
    category, frame_text = lookup_frame(r.get("l6_main"))
    today_iso = today.isoformat()

    # 결정론적 산출 (LLM 외)
    recovery_dist = _compute_recovery_distribution(cases)
    no_action_ec = r.get("expected_completion")
    if isinstance(no_action_ec, date):
        no_action_ec = no_action_ec.isoformat()

    recs_payload = build_recs_input_v10(r, cases, today_iso, category, frame_text)
    scen_payload = build_scenarios_input_v10(
        r, no_action_ec, recovery_dist, cases, category, frame_text
    )

    for attempt in range(max_retries):
        try:
            async with sem:
                # recs ‖ scenarios 병렬 — 진단 path 와 시나리오 path 독립
                recs_task = _call_v10_llm_async(RECS_PROMPT_V10, recs_payload, cfg, azure)
                scen_task = _call_v10_llm_async(SCENARIOS_PROMPT_V10, scen_payload, cfg, azure)
                recs_out, scen_out = await asyncio.gather(recs_task, scen_task)

                # recs 완료 후 diag 순차 — diag 가 recs.recommendations 를 인용
                diag_payload = build_diag_input_v10(
                    r,
                    cases,
                    today_iso,
                    category,
                    frame_text,
                    recs_out.get("recommendations") or [],
                )
                diag_out = await _call_v10_llm_async(DIAG_PROMPT_V10, diag_payload, cfg, azure)

            # _compose_row 가 기존 llm_output dict 구조 ({"diagnosis", "recommendations"}) 기대
            merged_llm_output = {
                "diagnosis": diag_out.get("diagnosis"),
                "recommendations": recs_out.get("recommendations") or [],
            }
            return _compose_row(r, cases, merged_llm_output, run_id, scenarios=scen_out)

        except (openai.APIError, asyncio.TimeoutError, json.JSONDecodeError, KeyError) as e:
            if attempt == max_retries - 1:
                failed_wps.append(
                    {
                        "company": r.get("company"),
                        "l6_main": r.get("l6_main"),
                        "error": f"{type(e).__name__}: {e}",
                    }
                )
                return None
            # exponential backoff: 2s / 4s / 8s
            await asyncio.sleep(2 ** (attempt + 1))

    return None


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
        hil_2_selection: 자동 선택된 "{company}|{l6_main}" key list (hil_2 interrupt 폐기 후 전체 wp).
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
    azure = AzureOpenAI(
        api_key=cfg.azure_api_key,
        api_version=cfg.azure_api_version,
        azure_endpoint=cfg.azure_endpoint,
        timeout=cfg.azure_timeout,
        max_retries=cfg.azure_max_retries,
    )

    sem = get_llm_semaphore()  # 함수 entry 에서 한 번 — closure 로 공유

    async def _process_one(r: dict, cases: list[dict]) -> dict:
        async with sem:  # LLM 호출 부분만 Semaphore 안
            llm_input = build_llm_user_input(r, cases)
            llm_output = await _call_azure_llm_async(llm_input, cfg, azure)
            # 2026-05-26: 변경 3 — 진단 직후 scenarios LLM 호출 (동일 sem 블록 안, 동일 wp).
            # _compute_recovery_distribution 은 cases 기반 deterministic (결정 #20) — LLM input 으로 전달.
            recovery_dist = _compute_recovery_distribution(cases)
            no_action_ec = r.get("expected_completion")
            if isinstance(no_action_ec, date):
                no_action_ec = no_action_ec.isoformat()
            scenarios_input = build_scenarios_llm_input(r, no_action_ec, recovery_dist, cases)
            scenarios_output = await _call_azure_scenarios_llm_async(scenarios_input, cfg, azure)
        return _compose_row(r, cases, llm_output, run_id, scenarios=scenarios_output)  # PG write 는 sem 밖

    # 2026-05-27 Task 13: V10 2단계 (recs ‖ scenarios 병렬 + diag 순차) + retry 3회.
    # cold case 절대 금지 — cases<3 도 LLM 호출. 실패만 failed_wps 에 모아서 종합 retry batch (Task 30) 가 처리.
    failed_wps: list[dict] = []
    tasks = []
    for r in forecast:
        key = f"{r['company']}|{r['l6_main']}"
        if key not in hil_2_selection:
            continue
        cases = pre_optimizer_cases.get(key, [])
        tasks.append(
            _process_one_v10_with_retry(
                r, cases, run_id, today, cfg, azure, sem, failed_wps, max_retries=3
            )
        )

    results = list(await asyncio.gather(*tasks)) if tasks else []
    advice_rows = [row for row in results if row is not None]

    # 실패 wp 로깅 (Task 30 종합 retry batch 가 처리)
    if failed_wps:
        logger.warning(
            "Day %s: %d wp failed after 3 retries — failed_wps_today=%s. "
            "To be retried in batch (Task 30).",
            today.isoformat(),
            len(failed_wps),
            failed_wps,
        )

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
