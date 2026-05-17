"""LangGraph State 스키마 — Agent 간 공유 데이터 계약.

Spec: docs/schema/state.md + docs/schema/mapping-layer.md §2
"""

from __future__ import annotations

from typing import Literal, TypedDict


class Activity(TypedDict):
    """작업일보 1행 = 매핑 단위. spec 2026-05-16 §2 참조.

    옵션 X 채택 ((company, l6_main) 단위 분배):
    - 같은 (company, l6_main) Activity 들이 동일 assigned_workers reference
    - PoC 단계: wbs_activity_id / l7_sub / l7_5_activity / sub_work_area /
      plan_total_qty / plan_mh 는 항상 None (Master List 1:N 라 단일값 결정 불가)
      Forecaster / Reporter 는 (company, l6_main) candidate 를 PG 에서 직접 조회.
    """

    # WBS 매핑 (Mapper 이후 채워짐, 그 전엔 None)
    wbs_activity_id: str | None  # PoC: None — 1:N 단일 wbs 결정 불가
    l5_disc: str  # Parser 가 채움 (한글)
    l6_main: str | None  # Mapper LLM 결정
    l7_sub: str | None  # PoC: None — 1:N
    l7_5_activity: str | None  # PoC: None — 1:N
    sub_work_area: str | None  # PoC: None — 1:N

    # 작업일보 원천 (Parser 가 채움)
    trade: str
    company: str
    unit: str
    today_qty: float  # 9/25 89.5% None → 0.0 표시
    work_content: str
    conditions: list[str]

    # (company, l6_main) 단위 분배 결과 (_prorate_mh sub-step 이후)
    # 분배 공식: BP사 총 인원 × (그 l6 candidate Σplan_mh / 전체 매핑 l6 candidate Σplan_mh)
    assigned_workers: float  # (company, l6_main) 단위 단일값
    worker_source: Literal[
        "parsed",  #   = 작업일보 명시 그대로 (드문 케이스)
        "mh_prorated",  #   = _prorate_mh() 적용됨 (기본)
        "user_corrected",  #   = H-i-L 1 사용자 보정 (Phase 2)
    ]

    # Master List 조회값 (PoC: None — Forecaster 가 PG 에서 Σ 조회)
    plan_total_qty: float | None
    plan_mh: float | None

    # 매핑 결과 (Mapper 이후) — mapping-layer.md §3 추가 필드
    wa: str | None  # Mapper WA 결정 4단계
    mapping_conf: float | None  # LLM rerank confidence (0.0~1.0)
    mapping_source: str | None  # 'auto_bp_single'/'auto_l6_single'/...

    # H-i-L 1 플래그
    requires_review: bool  # mapping_conf < 0.7 또는 mapping_source='hil_required'


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
    # optimizer cycle Task 1 (v3.1) — 3 필드 (hil_2 / Optimizer 데이터 계약)
    hil_2_selection: list[str]
    pre_optimizer_cases: dict[str, list[dict]]
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
