from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from pipeline.agents.mapper import _prorate_mh
from pipeline.db import PGClient
from pipeline.state import Activity, BPSummary, ParsedDailyReport


@pytest_asyncio.fixture
async def real_pg():
    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    yield pg
    await pg.close()


def _act(company: str, l6: str | None, **kw) -> Activity:
    return {
        "wbs_activity_id": None,
        "l5_disc": "건축",
        "l6_main": l6,
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "trade": "건축",
        "company": company,
        "unit": "m2",
        "today_qty": 0.0,
        "work_content": "test",
        "conditions": [],
        "assigned_workers": 0.0,
        "worker_source": "parsed",
        "plan_total_qty": None,
        "plan_mh": None,
        "wa": "CUB",
        "mapping_conf": 0.9,
        "mapping_source": "auto_bp_single",
        "requires_review": False,
        **kw,
    }


def _summ(company: str, today_incr: int) -> BPSummary:
    return {
        "bp_code": None,
        "company": company,
        "disc_abbrev": "건축",
        "zone": "CUB",
        "scope": None,
        "work_text_yesterday": None,
        "work_text_today": None,
        "work_text_tomorrow": None,
        "today_incr_total": today_incr,
        "today_cum_total": 0,
    }


@pytest.mark.asyncio
async def test_prorate_single_l6():
    """남웅 88명, l6=1 → 88.0 그대로."""
    mapped = [_act("남웅건설", "철근콘크리트공사") for _ in range(3)]
    parsed: ParsedDailyReport = {
        "report_date": "2025-09-25",
        "project": "test",
        "bp_summaries": [_summ("남웅건설", 88)],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }
    pg = AsyncMock()
    pg.fetch_l6_plan_mh_map = AsyncMock(return_value={"철근콘크리트공사": 1_676_807})

    result = await _prorate_mh(mapped, parsed, pg)

    assert all(a["assigned_workers"] == 88.0 for a in result)
    assert all(a["worker_source"] == "mh_prorated" for a in result)


@pytest.mark.asyncio
async def test_prorate_zero_total():
    """bp_total=0 → 0.0."""
    mapped = [_act("XYZ", "철근콘크리트공사")]
    parsed: ParsedDailyReport = {
        "report_date": "2025-09-25",
        "project": "test",
        "bp_summaries": [_summ("XYZ", 0)],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }
    pg = AsyncMock()
    pg.fetch_l6_plan_mh_map = AsyncMock(return_value={"철근콘크리트공사": 100})

    result = await _prorate_mh(mapped, parsed, pg)
    assert result[0]["assigned_workers"] == 0.0


@pytest.mark.asyncio
async def test_prorate_zero_plan_mh():
    """Σmh=0 → 균등 분배."""
    mapped = [_act("XYZ", f"l6_{i}") for i in range(4)]
    parsed: ParsedDailyReport = {
        "report_date": "2025-09-25",
        "project": "test",
        "bp_summaries": [_summ("XYZ", 80)],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }
    pg = AsyncMock()
    pg.fetch_l6_plan_mh_map = AsyncMock(return_value={"l6_0": 0, "l6_1": 0, "l6_2": 0, "l6_3": 0})

    result = await _prorate_mh(mapped, parsed, pg)
    for a in result:
        assert a["assigned_workers"] == 20.0


@pytest.mark.asyncio
async def test_prorate_unmapped_skip():
    """l6_main=None Activity → assigned_workers 미변경."""
    mapped = [
        _act("남웅건설", "철근콘크리트공사"),
        _act("남웅건설", None, requires_review=True),
    ]
    parsed: ParsedDailyReport = {
        "report_date": "2025-09-25",
        "project": "test",
        "bp_summaries": [_summ("남웅건설", 88)],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }
    pg = AsyncMock()
    pg.fetch_l6_plan_mh_map = AsyncMock(return_value={"철근콘크리트공사": 1_676_807})

    result = await _prorate_mh(mapped, parsed, pg)
    assert result[0]["assigned_workers"] == 88.0
    assert result[0]["worker_source"] == "mh_prorated"
    assert result[1]["assigned_workers"] == 0.0
    assert result[1]["worker_source"] == "parsed"


@pytest.mark.asyncio
async def test_prorate_multi_l6_share():
    """3 l6, 인원 100 → plan_mh 비율 (50/30/20%) → 50/30/20명."""
    mapped = [_act("CO", f"l6_{i}") for i in range(3)]
    parsed: ParsedDailyReport = {
        "report_date": "2025-09-25",
        "project": "test",
        "bp_summaries": [_summ("CO", 100)],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }
    pg = AsyncMock()
    pg.fetch_l6_plan_mh_map = AsyncMock(return_value={"l6_0": 500, "l6_1": 300, "l6_2": 200})

    result = await _prorate_mh(mapped, parsed, pg)
    lookup = {a["l6_main"]: a["assigned_workers"] for a in result}
    assert lookup["l6_0"] == 50.0
    assert lookup["l6_1"] == 30.0
    assert lookup["l6_2"] == 20.0


@pytest.mark.slow
@pytest.mark.asyncio
async def test_prorate_sebo_real_pg(real_pg):
    """세보엠이씨 1387명 → 기계소화설비 421.7 / 일반공조설비공사 401.4 / 냉동기설비공사 152.1.

    Spec docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md §3.
    실 PG (activity_master) 에서 plan_mh_rev2 sum 으로 비례 분배 검증.
    """
    sebo_l6s = [
        "기계소화설비",
        "일반공조설비공사",
        "냉동기설비공사",
        "CABINET배기설비공사",
        "VOC설비공사",
        "비상배기덕트설비공사",
        "ACID배기설비공사",
        "위생배관공사",
        "ALKALI배기설비공사",
        "H/G배기설비공사",
        "DCC설비공사",
        "NPW배관공사",
        "H-VAC설비공사",
    ]
    mapped = [_act("세보엠이씨", l6) for l6 in sebo_l6s]
    parsed: ParsedDailyReport = {
        "report_date": "2025-09-25",
        "project": "test",
        "bp_summaries": [_summ("세보엠이씨", 1387)],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }
    result = await _prorate_mh(mapped, parsed, real_pg)
    lookup = {a["l6_main"]: round(a["assigned_workers"], 1) for a in result}
    assert lookup["기계소화설비"] == 421.7
    assert lookup["일반공조설비공사"] == 401.4
    assert lookup["냉동기설비공사"] == 152.1
    assert round(sum(lookup.values()), 0) == 1387
