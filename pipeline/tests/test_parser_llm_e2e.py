# pipeline/tests/test_parser_llm_e2e.py
"""Parser LLM e2e 검증 — Stage 1 + Stage 2 expected row count assertion."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

from pipeline.agents.parser_llm import ParserConfig, parse_daily_report_llm


SAMPLE_XLSX_STAGE1 = Path("docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx")
SAMPLE_XLSX_STAGE2 = Path("docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250926.xlsx")


def _cfg():
    return ParserConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
    )


@pytest.mark.asyncio
@pytest.mark.skipif(not SAMPLE_XLSX_STAGE1.exists(), reason="Stage 1 xlsx 누락")
async def test_stage1_expected_row_count():
    """Stage 1 — sample xlsx 1 회 측정 후 expected range 산출 (initial ±20%)."""
    parsed = await parse_daily_report_llm(SAMPLE_XLSX_STAGE1, _cfg())
    bp = parsed.get("bp_summaries") or []
    job = parsed.get("job_allocations") or []
    equip = parsed.get("equipment_allocations") or []
    act = parsed.get("activities") or []
    # 실측값 (2026-05-19): bp=205, job=1268, equip=690, act=1241 — ±20% range
    assert 164 <= len(bp) <= 256, f"bp_summaries={len(bp)}"
    assert 1014 <= len(job) <= 1585, f"job_allocations={len(job)}"
    assert 552 <= len(equip) <= 862, f"equipment_allocations={len(equip)}"
    assert 992 <= len(act) <= 1551, f"activities={len(act)}"


@pytest.mark.asyncio
@pytest.mark.skipif(not SAMPLE_XLSX_STAGE2.exists(), reason="Stage 2 xlsx 누락")
async def test_stage2_expected_row_count():
    """Stage 2 — 다른 일자 xlsx 양식 변동성 검증."""
    parsed = await parse_daily_report_llm(SAMPLE_XLSX_STAGE2, _cfg())
    bp = parsed.get("bp_summaries") or []
    act = parsed.get("activities") or []
    assert len(act) >= 1000
    assert len(bp) >= 250
