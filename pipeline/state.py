"""LangGraph State 스키마 — Agent 간 공유 데이터 계약.

Spec: docs/schema/state.md + docs/schema/mapping-layer.md §2
"""

from __future__ import annotations

from typing import Literal, TypedDict


class Activity(TypedDict):
    """작업일보 1행 = 매핑 단위."""

    # WBS 매핑 (Mapper 이후 채워짐)
    wbs_activity_id: str | None
    l5_disc: str
    l6_main: str | None
    l7_sub: str | None
    l7_5_activity: str | None
    sub_work_area: str | None

    # 작업일보 원천 (Parser 가 채움)
    trade: str
    company: str
    unit: str
    today_qty: float
    work_content: str
    conditions: list[str]

    # MH 비율 분배 (Mapper 이후)
    assigned_workers: float
    worker_source: Literal["parsed", "mh_prorated", "user_corrected"]

    # Master List 조회값
    plan_total_qty: float | None
    plan_mh: float | None

    # 매핑 결과 (Mapper 이후) — mapping-layer.md §3 추가 필드
    wa: str | None
    mapping_conf: float | None
    mapping_source: str | None

    # H-i-L 1 플래그
    requires_review: bool


class BPSummary(TypedDict):
    """시트1 BP사 × 공종 row."""

    bp_code: str | None
    company: str
    disc_abbrev: str | None
    zone: str | None
    scope: str | None
    work_text_yesterday: str | None
    work_text_today: str | None
    work_text_tomorrow: str | None
    today_incr_total: int
    today_cum_total: int


class JobAllocation(TypedDict):
    """시트2 BP사 × 직종 row (Cum.T = 금일누계)."""

    bp_code: str | None
    company: str
    disc_abbrev: str | None
    job_type: str
    workers_cum_t: int


class EquipmentAllocation(TypedDict):
    """시트3 BP사 × 장비 row (Cum.T = 금일투입누계)."""

    bp_code: str | None
    company: str
    equipment_big: str
    equipment_mid: str
    equipment_spec: str | None
    count_cum_t: int


class ParsedDailyReport(TypedDict):
    """1 작업일보 xlsx — 4시트 통합 파싱 결과."""

    report_date: str
    project: str
    bp_summaries: list[BPSummary]
    job_allocations: list[JobAllocation]
    equipment_allocations: list[EquipmentAllocation]
    activities: list[Activity]


class CPIAState(TypedDict):
    """LangGraph 그래프 전체 상태."""

    # 입력
    run_id: str
    date: str
    input_files: list[str]

    # 파이프라인 누적
    raw_texts: dict[str, str]
    parsed: list[Activity]
    mapped: list[Activity]
    hil_1_corrections: dict
    atomized_ids: list[str]

    # 분기 결과
    report_md: str
    forecast: list[dict]
    hil_2_selection: list[str]
    optimizer_advice: list[dict]

    # 상태 추적
    current_node: str
    status: Literal[
        "running",
        "waiting_hil_1",
        "waiting_hil_2",
        "completed",
        "failed",
    ]
