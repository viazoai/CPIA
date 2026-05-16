from __future__ import annotations

from state import (
    Activity,
    BPSummary,
    EquipmentAllocation,
    JobAllocation,
    ParsedDailyReport,
    CPIAState,
)


def test_activity_instantiate():
    a: Activity = {
        "wbs_activity_id": None,
        "l5_disc": "건축",
        "l6_main": None,
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "trade": "건축",
        "company": "남웅건설",
        "unit": "M2",
        "today_qty": 320.0,
        "work_content": "기초 거푸집 설치",
        "conditions": [],
        "assigned_workers": 81.0,
        "worker_source": "parsed",
        "plan_total_qty": None,
        "plan_mh": None,
        "requires_review": False,
        "wa": None,
        "mapping_conf": None,
        "mapping_source": None,
    }
    assert a["trade"] == "건축"
    assert a["assigned_workers"] == 81.0


def test_bp_summary_instantiate():
    bp: BPSummary = {
        "bp_code": "PH_X-001",
        "company": "남웅건설",
        "disc_abbrev": "AR",
        "zone": "FAB",
        "scope": "A구간",
        "work_text_yesterday": "RC 거푸집",
        "work_text_today": "RC 거푸집 및 철근",
        "work_text_tomorrow": "RC 타설",
        "today_incr_total": 42,
        "today_cum_total": 81,
    }
    assert bp["company"] == "남웅건설"
    assert bp["today_cum_total"] == 81


def test_job_allocation_instantiate():
    job: JobAllocation = {
        "bp_code": "PH_X-001",
        "company": "남웅건설",
        "disc_abbrev": "AR",
        "job_type": "배관공",
        "workers_cum_t": 19,
    }
    assert job["job_type"] == "배관공"
    assert job["workers_cum_t"] == 19


def test_equipment_allocation_instantiate():
    equip: EquipmentAllocation = {
        "bp_code": "PH_X-001",
        "company": "남웅건설",
        "equipment_big": "굴삭운반기계류",
        "equipment_mid": "Back Hoe",
        "equipment_spec": "2㎥ 미만",
        "count_cum_t": 2,
    }
    assert equip["equipment_mid"] == "Back Hoe"
    assert equip["count_cum_t"] == 2


def test_parsed_daily_report_instantiate():
    r: ParsedDailyReport = {
        "report_date": "20250925",
        "project": "M15X PH-3 IBL",
        "bp_summaries": [],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }
    assert r["report_date"] == "20250925"


def test_cpia_state_instantiate():
    s: CPIAState = {
        "run_id": "00000000-0000-0000-0000-000000000000",
        "date": "20250925",
        "input_files": [],
        "raw_texts": {},
        "parsed": [],
        "mapped": [],
        "hil_1_corrections": {},
        "atomized_ids": [],
        "report_md": "",
        "forecast": [],
        "hil_2_selection": [],
        "optimizer_advice": [],
        "current_node": "collector",
        "status": "running",
    }
    assert s["status"] == "running"
