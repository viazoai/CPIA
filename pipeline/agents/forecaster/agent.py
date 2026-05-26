"""Forecaster agent — LangGraph node + main async forecast() entry.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §10
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from openai import AzureOpenAI

logger = logging.getLogger(__name__)

from pipeline.agents._concurrency import get_llm_semaphore
from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient
from pipeline.state import Activity

from .aggregate import (
    aggregate_today_by_unit,
    compute_delay,
    fetch_chroma_actual,
    fetch_pg_actual_cum_qty,
)
from .classify import classify_assessment, classify_risk_level
from .prompt import (
    SYSTEM_PROMPT,
    FEW_SHOT_MESSAGES,
    build_llm_user_input,
)
from .rerank import rerank_cases


@dataclass
class ForecasterConfig:
    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    llm_model: str
    embedding_model: str
    postgres_url: str
    chroma_host: str
    chroma_port: int
    chroma_ssl: bool = False
    azure_timeout: float = 60.0
    azure_max_retries: int = 3
    rag_n_candidates: int = 10
    rag_top_k: int = 5
    rag_window_days: int = 30
    # temperature 박지 않음 — spec C-1 정정 (gpt-5 family 미지원)


def _format_chroma_result(rag_result: dict) -> list[dict]:
    """Chroma query 결과 → rerank 입력 format."""
    if not rag_result.get("ids") or not rag_result["ids"][0]:
        return []
    return [
        {"document": doc, "distance": dist, "metadata": meta}
        for doc, dist, meta in zip(
            rag_result["documents"][0],
            rag_result["distances"][0],
            rag_result["metadatas"][0],
        )
    ]


async def _forecast_one_group(
    company: str,
    l6_main: str,
    activities: list[Activity],
    run_id: uuid.UUID,
    today: date,
    pg: PGClient,
    coll,
    azure: AzureOpenAI,
    cfg: ForecasterConfig,
) -> dict[str, Any]:
    """1 (company, l6_main) group 처리. Spec §1 ① ~ ⑧."""

    # ① 집계
    today_qty_by_unit = aggregate_today_by_unit(activities)
    today_assigned_workers = activities[0]["assigned_workers"]
    # qty>0 인 unit 만 후보. 모든 unit 0 → main_unit=None (의미적 "오늘 물량 0").
    positive_units = {u: q for u, q in today_qty_by_unit.items() if q > 0}
    main_unit = max(positive_units, key=positive_units.get) if positive_units else None
    today_productivity = (
        today_qty_by_unit[main_unit] / today_assigned_workers
        if main_unit and today_assigned_workers > 0
        else 0.0
    )
    work_content = " / ".join(set(a["work_content"] for a in activities if a.get("work_content")))[:200]
    conditions_set = sorted(set(c for a in activities for c in (a.get("conditions") or [])))

    # ② Plan
    plan = await pg.fetch_plan_for_group(company, l6_main)

    # ③ RAG 검색 + 정규화 + rerank
    # Chroma where 절은 한 dict 안에 하나의 operator 만 허용 + $gte/$lt 는 숫자 전용 →
    # date (ISO 문자열) range 는 코드단에서 윈도우 컷. (company, l6_main) 만 Chroma 필터.
    embed_resp = azure.embeddings.create(model=cfg.embedding_model, input=[work_content])
    today_embed = embed_resp.data[0].embedding
    where_filter = {
        "$and": [
            {"company": company},
            {"l6_main": l6_main},
        ]
    }
    # 필터로 좁혀진 공간이 요청 개수보다 작으면 chroma HNSW 가
    # 'ef or M too small' 에러 던짐. 사전에 docs 수 count 후 n_results clamp.
    # 2026-05-20: AWS Chroma 의 ef_search=10 boundary case 회피 — n_results < ef_search 보장.
    # cycle 6차 fail (forecaster fc=86 까지 진행 후 "ef or M too small") 의 root cause.
    preflight = coll.get(where=where_filter, include=[])
    n_filtered = len(preflight.get("ids", []) or [])
    safe_n = min(cfg.rag_n_candidates, n_filtered, 5)
    similar_cases_raw: list[dict[str, Any]] = []
    if safe_n > 0:
        try:
            rag_result = coll.query(
                query_embeddings=[today_embed],
                where=where_filter,
                n_results=safe_n,
            )
            similar_cases_raw = _format_chroma_result(rag_result)
        except Exception as _e:  # noqa: BLE001
            # 2026-05-20: HNSW "ef or M too small" (cycle 8차 재발) 또는 기타 Chroma error.
            # cap=5 만으로 부족 — n_filtered 가 작거나 HNSW 내부 상태로 fail 가능. Plan fallback.
            logger.warning(
                "Chroma query fail (n_results=%d, filter=%s): %s — Plan fallback",
                safe_n,
                where_filter,
                _e,
            )
    window_start_iso = (today - timedelta(days=cfg.rag_window_days)).isoformat()
    today_iso = today.isoformat()
    similar_cases_in_window = [
        c for c in similar_cases_raw if window_start_iso <= c["metadata"]["date"] < today_iso
    ]
    similar_cases = rerank_cases(similar_cases_in_window)[: cfg.rag_top_k]

    # ④ assessment
    rag_n = len(similar_cases)
    rag_avg_prod = sum(c["metadata"]["productivity"] for c in similar_cases) / rag_n if rag_n > 0 else 0.0
    # atomic 1:1 매칭 — group 안 mapper row 의 main_unit plan_total_qty distinct SUM.
    # 이전: plan["plan_total_qty_by_unit"][main_unit] (activity_master 의 l6_main SUM).
    # 문제: 매칭 안 된 atomic 까지 분모 합산 -> pace 작은 그룹의 remaining_days 폭주
    # (진특수 방수 9/25 case: l6=10,523 m2 vs atomic=194 m2 -> delay 26,517 일).
    # Fix: mapper_activities.plan_total_qty 가 atomic 매칭 결과 broadcast 라
    #      group 안 distinct value 의 SUM 만 사용. 같은 wbs 가 multiple mapper row
    #      로 들어와도 double count 방지.
    if main_unit:
        plan_qtys = {
            round(float(a["plan_total_qty"]), 4)
            for a in activities
            if a.get("unit") == main_unit and a.get("plan_total_qty") is not None
        }
        plan_main_qty = sum(plan_qtys) if plan_qtys else None
    else:
        plan_main_qty = None
    assessment = classify_assessment(
        rag_n=rag_n,
        today_prod=today_productivity,
        rag_avg_prod=rag_avg_prod,
        plan_total_qty_main=plan_main_qty,
        plan_mh_sum=plan["plan_mh_sum"] if plan else None,
    )

    # ⑤ compute_delay — 2026-05-22 qty 기반.
    # actual_cum_qty 는 PG mapper_activities 가 source of truth (Chroma 는 mapper 의 일부만 backfill).
    today_qty_main = today_qty_by_unit.get(main_unit, 0.0) if main_unit else 0.0
    actual_window_start, actual_cum_mh, _chroma_qty = fetch_chroma_actual(
        coll,
        company,
        l6_main,
        today,
        today_assigned_workers,
        today_qty_main=today_qty_main,
        main_unit=main_unit,
    )
    pg_cum_qty = await fetch_pg_actual_cum_qty(pg, company, l6_main, today, main_unit)
    actual_cum_qty = pg_cum_qty + today_qty_main
    delay_info = compute_delay(
        plan,
        today,
        actual_window_start,
        actual_cum_mh,
        actual_cum_qty=actual_cum_qty,
        plan_total_qty_main=plan_main_qty,
        today_qty_main=today_qty_main,
    )

    # ⑥ LLM
    if assessment is None:
        if main_unit is None:
            reasoning = "데이터 부족 — 오늘 물량 모든 unit 0 (인원만 투입). 판단 보류."
        elif plan is None:
            reasoning = "데이터 부족 — Plan 미등록 + RAG <3건. 판단 보류."
        elif plan_main_qty is None:
            reasoning = (
                f"데이터 부족 — main_unit '{main_unit}' 가 Plan unit set 에 없음 "
                "(작업일보 unit ↔ Plan unit 분류 불일치). RAG <3건. 판단 보류."
            )
        else:
            reasoning = "데이터 부족 — RAG <3건. 판단 보류."
        recovery_likelihood = None
    else:
        today_data = {
            "company": company,
            "l6_main": l6_main,
            "today_qty_by_unit": today_qty_by_unit,
            "today_assigned_workers": today_assigned_workers,
            "today_productivity": today_productivity,
            "conditions": conditions_set,
            "work_content": work_content,
        }
        llm_input = build_llm_user_input(today_data, similar_cases, plan, assessment)
        response = azure.chat.completions.create(
            model=cfg.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *FEW_SHOT_MESSAGES,
                {"role": "user", "content": json.dumps(llm_input, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        llm_out = json.loads(response.choices[0].message.content)
        reasoning = llm_out.get("reasoning", "")
        recovery_likelihood = llm_out.get("recovery_likelihood")

    # ⑦ risk_level
    risk_level = classify_risk_level(
        assessment,
        recovery_likelihood,
        delay_info["delay_days"],
        delay_info["schedule_state"],
    )

    # ⑧ row
    return {
        "run_id": run_id,
        "company": company,
        "l6_main": l6_main,
        "today_qty_by_unit": today_qty_by_unit,
        "today_assigned_workers": today_assigned_workers,
        "today_productivity": today_productivity,
        "plan_total_qty_by_unit": plan["plan_total_qty_by_unit"] if plan else None,
        "plan_mh_sum": plan["plan_mh_sum"] if plan else None,
        "plan_start": plan["plan_start"] if plan else None,
        "plan_finish": plan["plan_finish"] if plan else None,
        "plan_mh_per_day": delay_info["plan_mh_per_day"],
        "schedule_state": delay_info["schedule_state"],
        "window_start": delay_info["window_start"],
        "window_days": delay_info["window_days"],
        "expected_in_window_mh": delay_info["expected_in_window_mh"],
        "actual_in_window_mh": delay_info["actual_in_window_mh"],
        "mh_gap": delay_info["mh_gap"],
        "delay_days": delay_info["delay_days"],
        "rag_n_similar": rag_n,
        "similar_cases": [
            {
                "date": c["metadata"]["date"],
                "productivity": round(c["metadata"]["productivity"], 4),
                "conditions": c["metadata"]["conditions"],
            }
            for c in similar_cases
        ],
        "assessment": assessment,
        "reasoning": reasoning,
        "recovery_likelihood": recovery_likelihood,
        "expected_completion": delay_info.get("expected_completion") or (plan["plan_finish"] if plan else None),
        "risk_level": risk_level,
        # v3.1 (optimizer cycle Task 1) — Optimizer / hil_2 가 소비할 2 필드
        "main_unit": main_unit,
        "today_conditions": ",".join(conditions_set) if conditions_set else "",
    }


async def forecast(
    mapped: list[Activity],
    run_id: uuid.UUID,
    today: date,
    cfg: ForecasterConfig,
) -> list[dict[str, Any]]:
    """Forecaster entry. (wa, company, l6_main) group 별 1 row 생성 + PG INSERT."""
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    chroma = ChromaClient(host=cfg.chroma_host, port=cfg.chroma_port, ssl=cfg.chroma_ssl)
    coll = chroma.get_or_create_daily_activities()
    azure = AzureOpenAI(
        api_key=cfg.azure_api_key,
        api_version=cfg.azure_api_version,
        azure_endpoint=cfg.azure_endpoint,
        timeout=cfg.azure_timeout,
        max_retries=cfg.azure_max_retries,
    )

    try:
        await pg.assert_pipeline_run_exists(run_id)

        groups: dict[tuple[str | None, str, str], list[Activity]] = {}
        for a in mapped:
            if a["l6_main"] is None:
                continue
            if not a.get("work_content"):
                continue
            key = (a.get("wa"), a["company"], a["l6_main"])
            groups.setdefault(key, []).append(a)

        sem = get_llm_semaphore()  # 함수 entry 에서 한 번 — closure 로 공유

        async def _one(key: tuple[str | None, str, str], activities: list[Activity]) -> dict[str, Any]:
            wa, company, l6_main = key
            async with sem:  # LLM 호출 부분만 Semaphore 안
                row = await _forecast_one_group(
                    company,
                    l6_main,
                    activities,
                    run_id,
                    today,
                    pg,
                    coll,
                    azure,
                    cfg,
                )
            row["wa"] = wa
            await pg.insert_forecast(row)  # asyncpg pool 이 thread-safe — sem 밖
            return row

        tasks = [_one(k, v) for k, v in groups.items()]
        forecast_rows: list[dict[str, Any]] = list(await asyncio.gather(*tasks))

        return forecast_rows
    finally:
        await pg.close()
