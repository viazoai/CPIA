"""LangGraph State 스키마 — Agent 간 공유 데이터 계약.

Spec: docs/schema/state.md + docs/schema/mapping-layer.md §2

2026-05-19 확장: 통합 작업일보 4 시트 + 업체별 시트6/Cover 풀 커버리지.
- TimeShiftCounts 신규 — 시간대 6 필드 (조출/주간/연장/야간/철야/Total) 공통 dict.
- BPSummary/JobAllocation/EquipmentAllocation 시간대 그룹 (전일 투입/누적 + 금일 투입/누적) jsonb.
- Activity 에 zone/bp_code/scope/yesterday_cum_qty/today_cum_qty/F%/잔여/G%/note/work_location/WBS path 추가.
- WorkerOutput (시트6 업체별) + ReportMeta (Cover 업체별) 신규 entity.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class TimeShiftCounts(TypedDict):
    """6 시간대 분포 — 인원 / 장비 공용 (조출/주간/연장/야간/철야/Total).

    BPSummary / JobAllocation / EquipmentAllocation 의 4 그룹 (전일 투입/누적,
    금일 투입/누적) 각각이 이 dict 1개를 가진다. PG 적재 시 jsonb.
    """

    morning: int  # 조출
    daytime: int  # 주간
    overtime: int  # 연장
    night: int  # 야간
    all_night: int  # 철야
    total: int  # Total


class Activity(TypedDict):
    """작업일보 시트4 1행 = 매핑 단위. spec 2026-05-16 §2 참조.

    옵션 X 채택 ((company, l6_main) 단위 분배):
    - 같은 (company, l6_main) Activity 들이 동일 assigned_workers reference
    - PoC 단계: wbs_activity_id / l7_sub / l7_5_activity / sub_work_area /
      plan_total_qty / plan_mh 는 항상 None (Master List 1:N 라 단일값 결정 불가)
      Forecaster / Reporter 는 (company, l6_main) candidate 를 PG 에서 직접 조회.

    2026-05-19 확장: 시트4 의 zone/bp_code/scope/누적/F%/잔여/G%/비고 추가 +
    업체별 일보 시트4 의 작업위치_코드 / WBS 중·소·세공종명 추가.
    """

    # 시트4 원천 (Parser 채움)
    zone: str | None  # 시트4 col 2 (FAB/CUB 등)
    bp_code: str | None  # 시트4 col 4 (PH_X-... 류)
    company: str  # 시트4 col 5 업체명
    scope: str | None  # 시트4 col 6
    trade: str  # 공종 (시트4 col 3)
    work_content: str  # 대표물량_작업 내용 (col 7)
    unit: str  # 단위 (col 8)
    plan_total_qty: float | None  # [A] 총물량 (col 9)
    yesterday_cum_qty: float | None  # [B] 전일누적 (col 10)
    today_qty: float  # [C] 금일실적 (col 11)
    today_cum_qty: float | None  # [D = B+C] 금일누적 (col 12)
    progress_percent: float | None  # F% [D/A] (col 13)
    remaining_qty: float | None  # [E = A-D] 잔여 (col 14)
    remaining_percent: float | None  # G% [100% - F] (col 15 통합 / col 14 업체)
    note: str | None  # 비고 (col 16)

    # 업체별 일보 시트4 추가 컬럼 (통합 일보엔 없음)
    work_location_code: str | None  # 작업 위치_코드 (업체 col 15)
    wbs_mid_name: str | None  # 중공종명 (업체 col 16)
    wbs_sub_name: str | None  # 소공종명 (업체 col 17)
    wbs_detail_name: str | None  # 세공종명 (업체 col 18)

    # WBS 매핑 (Mapper 이후 채워짐, 그 전엔 None)
    wbs_activity_id: str | None  # PoC: None — 1:N 단일 wbs 결정 불가
    l5_disc: str  # Parser 가 채움 (한글)
    l6_main: str | None  # Mapper LLM 결정
    l7_sub: str | None  # PoC: None — 1:N
    l7_5_activity: str | None  # PoC: None — 1:N
    sub_work_area: str | None  # PoC: None — 1:N
    conditions: list[str]

    # (company, l6_main) 단위 분배 결과 (_prorate_mh sub-step 이후)
    # 분배 공식: BP사 총 인원 × (그 l6 candidate Σplan_mh / 전체 매핑 l6 candidate Σplan_mh)
    assigned_workers: float
    worker_source: Literal[
        "parsed",  #   = 작업일보 명시 그대로 (드문 케이스)
        "mh_prorated",  #   = _prorate_mh() 적용됨 (기본)
        "user_corrected",  #   = H-i-L 1 사용자 보정 (Phase 2)
    ]
    plan_mh: float | None

    # 매핑 결과 (Mapper 이후) — mapping-layer.md §3 추가 필드
    wa: str | None  # Mapper WA 결정 4단계
    mapping_conf: float | None  # LLM rerank confidence (0.0~1.0)
    mapping_source: str | None  # 'auto_bp_single'/'auto_l6_single'/'auto_sheet1_text'/...

    # H-i-L 1 플래그
    requires_review: bool  # mapping_conf < 0.7 또는 mapping_source='hil_required'


class BPSummary(TypedDict):
    """시트1 BP사 × 공종 × Zone × Scope row.

    2026-05-19 확장: 시간대 4 그룹 (전일 투입/누적, 금일 투입/누적) 추가.
    """

    bp_code: str | None  # PH_X-... 류
    company: str  # 협력업체 (회사명)
    disc_abbrev: str | None  # 공종 (한글)
    zone: str | None  # FAB/CUB 등
    scope: str | None
    work_text_yesterday: str | None
    work_text_today: str | None
    work_text_tomorrow: str | None

    # 4 시간대 그룹 (jsonb 적재)
    workers_yesterday_incr: TimeShiftCounts | None  # 전일 투입인원
    workers_yesterday_cum: TimeShiftCounts | None  # 전일 누적인원
    workers_today_incr: TimeShiftCounts | None  # 금일 투입인원
    workers_today_cum: TimeShiftCounts | None  # 금일 누적인원

    # 편의 Total (jsonb 안 total 과 중복이지만 SQL filter/order 쉽게)
    today_incr_total: int
    today_cum_total: int


class JobAllocation(TypedDict):
    """시트2 BP사 × 직종 × 시간대.

    2026-05-19 확장: Mm##/sk## 코드 + 3 시간대 그룹 + 최종 (O/X).
    """

    bp_code: str | None
    company: str
    disc_abbrev: str | None
    manager_code: str | None  # Mm## (관리자/근로자 코드)
    worker_code: str | None  # sk## (기능공 코드)
    job_type: str

    # 3 시간대 그룹 (jsonb)
    workers_yesterday_cum: TimeShiftCounts | None  # 전일누계
    workers_today_incr: TimeShiftCounts | None  # 금일투입
    workers_today_cum: TimeShiftCounts | None  # 금일누계

    final_flag: str | None  # 최종 (O/X)

    # 편의 — 기존 호환
    workers_cum_t: int  # 금일누계 Total


class EquipmentAllocation(TypedDict):
    """시트3 BP사 × 장비 × 시간대.

    2026-05-19 확장: disc_abbrev + 3 시간대 그룹 + 최종.
    """

    bp_code: str | None
    company: str
    disc_abbrev: str | None  # ← 신규 (시트3 col 1 공종)
    equipment_big: str
    equipment_mid: str
    equipment_spec: str | None

    # 3 시간대 그룹 (jsonb)
    count_yesterday_cum: TimeShiftCounts | None  # 전일투입누계
    count_today_incr: TimeShiftCounts | None  # 금일투입
    count_today_cum: TimeShiftCounts | None  # 금일투입누계

    final_flag: str | None  # 최종 (O/X)

    # 편의 — 기존 호환
    count_cum_t: int  # 금일투입누계 Total


class WorkerOutput(TypedDict):
    """시트6 출력일보 (업체별 일보만) — 개별 작업자 단위.

    통합 작업일보엔 이 시트가 없음 (집계됨). 업체별만 들어온다.
    BI 에서 '오늘 누가 어디서 일했나' 쿼리 가능.
    """

    worker_name: str
    job_type: str  # 직종구분 (BP소장, 공사관리자, sk## 기능공 등)
    wbs_mid_name: str | None  # 중공종명
    wbs_sub_name: str | None  # 소공종명
    wbs_detail_name: str | None  # 세공종명
    work_location_code: str | None  # 작업 위치_코드
    work_content: str | None  # 금일 작업 사항
    # 시간대 (1/0 또는 시간)
    shift_morning: int
    shift_daytime: int
    shift_overtime: int
    shift_night: int
    shift_all_night: int
    note: str | None


class ReportMeta(TypedDict):
    """Cover 시트 (업체별 일보만) — 일보 메타."""

    project_name: str | None  # M15X PH4 등
    project_code: str | None  # M15X_PH4_041 등
    site_id: str | None  # m15x-ph3-ibl 류 (PG sites.site_id 매칭용)
    bp_name: str | None  # 협력업체명
    writer: str | None  # 작성자
    reviewer: str | None  # 검토자
    approval: str | None  # 결재자
    report_date: str
    document_no: str | None  # 문서 번호


class ParsedDailyReport(TypedDict):
    """1 작업일보 xlsx — 4 시트 통합 + 업체별 시트6/Cover.

    통합 작업일보: 시트1~4 채워짐. worker_outputs=[], report_meta=None.
    업체별 작업일보: 6 시트 모두 채워짐.
    Merge 후 통합 ParsedDailyReport: worker_outputs 는 N 업체 합쳐짐, report_meta 는
    site 단위 머지.
    """

    report_date: str
    project: str
    bp_summaries: list[BPSummary]
    job_allocations: list[JobAllocation]
    equipment_allocations: list[EquipmentAllocation]
    activities: list[Activity]
    worker_outputs: list[WorkerOutput]  # 업체별 시트6 — 통합 일보는 빈 list
    report_meta: ReportMeta | None  # 업체별 Cover — 통합 일보는 None


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


class BPSummaryRaw(TypedDict, total=False):
    """시트 1 의 row 단위 1:1 LLM 출력. parser_post.pair_bp_summaries (A.6) 가 페어링."""

    row_idx: int
    col_4_value: str | None
    is_bp_code: bool
    is_korean_company: bool
    bp_code: str | None
    company: str | None
    disc_abbrev: str | None
    zone: str | None
    scope: str | None
    work_text_today: str | None
    workers_today_cum: dict | None
    today_cum_total: int | None


class JobAllocationRaw(TypedDict, total=False):
    """시트 2 의 row 단위 1:1 LLM 출력. parser_post (A.6) 가 페어링."""

    row_idx: int
    company_or_bp: str | None
    disc_code: str | None  # Mm## 또는 Wk## (raw)
    worker_code: str | None  # sk##
    job_type: str | None
    disc_abbrev: str | None
    workers_today_cum: dict | None
    workers_cum_t: int | None
    final_flag: str | None
