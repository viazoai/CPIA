"""Reporter agent — Mapper + Forecaster + Optimizer 결과 종합 보고서.

Spec: docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.3

원안 v2 와의 의도적 drift (spec §3):
- 위치 = Optimizer 다음 (원안 = Atomizer 다음 병렬)
- 출력 = 종합 보고서 1 종 (원안 = 사내/발주처 2 종)
- LLM = Azure gpt-5.1 (원안 = Sonnet 4.6)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date as _date
from typing import Any

from openai import AzureOpenAI

from pipeline.db import PGClient
from pipeline.state import Activity


SYSTEM_PROMPT = """건설 현장 작업일보 종합 보고서 생성기.
입력 JSON 의 (1) 매핑 결과 (mapped) (2) 진단 (forecast) (3) 권고 (optimizer_advice) 를 받아
마크다운 종합 보고서 1 종을 생성한다.

출력 schema (마크다운, 머리말 + 3 부):
  # YYYY-MM-DD 작업일보 종합 보고서

  ## 1부 작업 통합
    - trade/BP사별 인원·물량·작업 요지 (mapped 합산)
    - 표 우선, 행 많으면 bullet

  ## 2부 생산성 진단
    - 공종별 today_productivity / risk_level / reasoning (forecast row 별 1 단락)
    - assessment=None (cold_start) 인 경우 "데이터 부족 — 판단 보류" 그대로 유지

  ## 3부 PM 선택 공종 권고 (optimizer_advice 가 비어있으면 본 부 전체 생략)
    - 공종별 diagnosis + recommendations rank 1~4 (optimizer_advice row 별)
    - recovery_distribution 가 있으면 footnote 인용

규칙:
  - 마크다운만 (HTML 사용 금지, 한자 사용 금지 — 한글 + 영어만)
  - 들여쓰기 1~2 단계만 (3 단계 이상 금지)
  - 텍스트는 한국어 위주, 코드/식별자/외래어 고유명사만 영어
  - 진단의 risk_level 과 reasoning 이 의미적으로 정합되도록 (분류 결과 뒤집지 말 것)
"""


@dataclass
class ReporterConfig:
    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    llm_model: str
    postgres_url: str
    azure_timeout: float = 60.0
    azure_max_retries: int = 3


def _build_llm_input(
    mapped: list[Activity],
    forecast_rows: list[dict],
    optimizer_advice: list[dict],
    today: _date,
) -> dict[str, Any]:
    """LLM user message JSON 빌더 — spec §5.3 few-shot 형식."""
    return {
        "date": today.isoformat(),
        "activities": [
            {
                "company": a.get("company"),
                "trade": a.get("trade"),
                "l6_main": a.get("l6_main"),
                "unit": a.get("unit"),
                "today_qty": a.get("today_qty"),
                "assigned_workers": a.get("assigned_workers"),
                "work_content": a.get("work_content"),
            }
            for a in mapped
        ],
        "forecast": forecast_rows,
        "optimizer_advice": optimizer_advice,
    }


def _build_summary(
    mapped: list[Activity],
    forecast_rows: list[dict],
    optimizer_advice: list[dict],
) -> dict:
    """summary JSONB — daily_reports.history_csv_row 컬럼에 박힘.

    운영 감사용 핵심 지표 (Dashboard 카드 소스).
    """
    qty_by_trade: dict[str, float] = {}
    for a in mapped:
        trade = a.get("trade") or "_unknown"
        qty_by_trade[trade] = qty_by_trade.get(trade, 0.0) + (a.get("today_qty") or 0.0)
    risk_counts: dict[str, int] = {"정상": 0, "주의": 0, "이상": 0}
    for f in forecast_rows:
        rl = f.get("risk_level")
        if rl in risk_counts:
            risk_counts[rl] += 1
    return {
        "total_workers": sum(a.get("assigned_workers") or 0.0 for a in mapped),
        "total_qty_by_trade": qty_by_trade,
        "risk_counts": risk_counts,
        "advice_count": len(optimizer_advice),
    }


async def report(
    mapped: list[Activity],
    forecast_rows: list[dict],
    optimizer_advice: list[dict],
    run_id: uuid.UUID,
    today: _date,
    cfg: ReporterConfig,
) -> tuple[str, dict]:
    """종합 보고서 생성 + PG INSERT (daily_reports.history_csv_row 컬럼).

    반환: (report_md, summary_dict). mapped empty 시 짧은 fallback + PG INSERT skip.
    """
    if not mapped:
        return ("# 보고서 생성 실패\n매핑 데이터 없음.", {})

    client = AzureOpenAI(
        api_key=cfg.azure_api_key,
        api_version=cfg.azure_api_version,
        azure_endpoint=cfg.azure_endpoint,
        timeout=cfg.azure_timeout,
        max_retries=cfg.azure_max_retries,
    )
    llm_input = _build_llm_input(mapped, forecast_rows, optimizer_advice, today)
    response = client.chat.completions.create(
        model=cfg.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(llm_input, ensure_ascii=False, default=str)},
        ],
    )
    report_md = response.choices[0].message.content or "# 보고서 생성 실패\nLLM 빈 응답."
    summary = _build_summary(mapped, forecast_rows, optimizer_advice)

    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        await pg.insert_daily_report(
            run_id=run_id,
            report_date=today,
            report_md=report_md,
            history_csv_row=summary,
            bp_name=None,
        )
    finally:
        await pg.close()

    return (report_md, summary)
