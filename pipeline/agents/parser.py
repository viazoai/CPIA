"""Parser 에이전트 — 작업일보 xlsx -> ParsedDailyReport.

Spec: docs/superpowers/specs/2026-05-15-cpia-parser-design.md
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import openpyxl

from pipeline.state import (
    Activity,
    BPSummary,
    EquipmentAllocation,
    JobAllocation,
    ParsedDailyReport,
)


class ParseError(Exception):
    """작업일보 포맷 위반."""


_DISC_ABBREV_TO_KR: dict[str, str] = {
    "AR": "건축",
    "ME": "설비",
    "EL": "전기",
    "UT": "UT",
    "TE": "공통가설",
    "IN": "제어",
    "CI": "토목",
}

_ADMIN_JOBS: frozenset[str] = frozenset({"BP소장", "공사관리자", "안전관리자", "품질관리자", "일반관리자"})


def _normalize_unit(s: str) -> str:
    """단위 대소문자 통일 (M2->m2, Ton->ton)."""
    return s.lower() if s else ""


def _disc_abbrev_to_kr(abbrev: str | None) -> str | None:
    """공종 약자 -> 한글 (알 수 없으면 원본 보존)."""
    if abbrev is None:
        return None
    return _DISC_ABBREV_TO_KR.get(abbrev, abbrev)


def _is_admin_job(job_type: str) -> bool:
    """관리자 직종 noise 판정 (시트2 필터)."""
    return job_type in _ADMIN_JOBS


def _is_total_row(row: tuple[Any, ...]) -> bool:
    """시트2 합계 row 판정 ('투입 Total' 포함)."""
    for cell in row:
        if isinstance(cell, str) and "투입 Total" in cell:
            return True
    return False


def _ffill(
    rows: list[tuple[Any, ...]],
    header_end: int,
    fill_cols: list[int],
) -> list[tuple[int, list[Any]]]:
    """헤더 이후 row 를 forward-fill (병합 셀 직전 값 채움).

    사전 조건: fill_cols 의 모든 인덱스는 row 의 열 수 이내여야 한다.
    조건 위반 시 해당 컬럼은 조용히 skip (데이터 손실 가능) — 호출부 책임.
    반환 row 번호는 1-indexed (header_end + 1 부터).
    """
    last: dict[int, Any] = {c: None for c in fill_cols}
    out: list[tuple[int, list[Any]]] = []
    for i, r in enumerate(rows[header_end:], start=header_end + 1):
        rec = list(r)
        for c in fill_cols:
            if c < len(rec) and rec[c] is not None and str(rec[c]).strip() != "":
                last[c] = rec[c]
            else:
                if c < len(rec):
                    rec[c] = last[c]
        out.append((i, rec))
    return out


def _parse_sheet1_bp_summaries(ws) -> list[BPSummary]:
    """시트 1 (출력인원 현황) -> BPSummary[]. 시뮬 v3 패턴 기반.

    Header end = row 4. Forward-fill cols = [1, 2, 3, 4] (병합 셀 패턴).
    r[2]=zone, r[3]=disc_abbrev, r[4]=company (BP 코드 row 는 mapper 무시),
    r[6]=work_text_yesterday, r[7]=work_text_today, r[8]=work_text_tomorrow,
    r[28]=today_incr_total, r[35]=today_cum_total.
    bp_code / scope: GATE 2 에서 보강 예정 -> None.
    """
    rows = _ffill(list(ws.iter_rows(values_only=True)), header_end=4, fill_cols=[1, 2, 3, 4])
    summaries: list[BPSummary] = []
    for _i, r in rows:
        if not r[4]:
            continue
        company = str(r[4]).strip()
        if not company:
            continue
        summaries.append(
            {
                "bp_code": None,
                "company": company,
                "disc_abbrev": _disc_abbrev_to_kr(str(r[3]).strip()) if r[3] else None,
                "zone": str(r[2]).strip() if r[2] else None,
                "scope": None,
                "work_text_yesterday": str(r[6]).strip() if r[6] else None,
                "work_text_today": str(r[7]).strip() if r[7] else None,
                "work_text_tomorrow": str(r[8]).strip() if r[8] else None,
                "today_incr_total": int(r[28]) if isinstance(r[28], (int, float)) else 0,
                "today_cum_total": int(r[35]) if isinstance(r[35], (int, float)) else 0,
            }
        )
    return summaries


def _parse_sheet2_job_allocations(ws) -> list[JobAllocation]:
    """시트 2 (직종별 인원현황) -> JobAllocation[]. 관리자 직종/합계 row 필터.

    cell 인덱스 (Task 0 시뮬 v3 발췌 / 실 파일 row 3 헤더 검증):
      r[1] = disc_abbrev (Dis 영문 약자),
      r[2] = company (BP사 - BP 코드 row 와 회사명 row 혼재, mapper 가 회사명으로만
      매치하므로 BP 코드 row 는 자연 무시),
      r[5] = job_type, r[23] = workers_cum_t (col 23 = 금일누계 계 컬럼).
    header_end = 5, fill_cols = [1, 2] (시뮬과 일치).
    """
    rows = _ffill(list(ws.iter_rows(values_only=True)), header_end=5, fill_cols=[1, 2])
    jobs: list[JobAllocation] = []
    for _i, r in rows:
        if _is_total_row(tuple(r)):
            continue
        company = str(r[2]).strip() if r[2] else ""
        job_type = str(r[5]).strip() if len(r) > 5 and r[5] else ""
        if not (company and job_type):
            continue
        if _is_admin_job(job_type):
            continue
        cum_t = int(r[23]) if len(r) > 23 and isinstance(r[23], (int, float)) else 0
        jobs.append(
            {
                "bp_code": None,
                "company": company,
                "disc_abbrev": _disc_abbrev_to_kr(str(r[1]).strip()) if r[1] else None,
                "job_type": job_type,
                "workers_cum_t": cum_t,
            }
        )
    return jobs


def _parse_sheet4_activities(ws) -> list[Activity]:
    """시트 4 (물량) -> Activity[]. fixture loader _load_inputs 이관.

    Header end = row 4. Forward-fill 컬럼 = [1, 2, 3, 4, 5] (병합 셀 패턴).
    필수 셀: r[5] (company), r[7] (work_content).
    """
    rows = _ffill(list(ws.iter_rows(values_only=True)), header_end=4, fill_cols=[1, 2, 3, 4, 5])
    activities: list[Activity] = []
    for _i, r in rows:
        if not (r[5] and r[7]):
            continue
        activities.append(
            {
                "wbs_activity_id": None,
                "l5_disc": str(r[3]) if r[3] else "",
                "l6_main": None,
                "l7_sub": None,
                "l7_5_activity": None,
                "sub_work_area": None,
                "trade": str(r[3]) if r[3] else "",
                "company": str(r[5]).strip(),
                "unit": _normalize_unit(str(r[8] or "").strip()),
                "today_qty": float(r[11]) if isinstance(r[11], (int, float)) else 0.0,
                "work_content": str(r[7]).strip(),
                "conditions": [],
                "assigned_workers": 0.0,
                "worker_source": "parsed",
                "plan_total_qty": float(r[9]) if isinstance(r[9], (int, float)) else None,
                "plan_mh": None,
                "requires_review": False,
                "wa": None,
                "mapping_conf": None,
                "mapping_source": None,
            }
        )
    return activities


def _parse_sheet3_equipment_allocations(ws) -> list[EquipmentAllocation]:
    """시트 3 (장비현황) -> EquipmentAllocation[].

    cell 인덱스 (Task 0 시뮬 v3 발췌 / 실 파일 row 3 헤더 검증):
      r[1] = disc_abbrev, r[2] = company,
      r[3] = equipment_big (대분류), r[4] = equipment_mid (중분류),
      r[5] = equipment_spec (규격, None 허용),
      r[23] = count_cum_t. header_end = 5, fill_cols = [1, 2] (시뮬과 일치).
    """
    rows = _ffill(list(ws.iter_rows(values_only=True)), header_end=5, fill_cols=[1, 2])
    eqs: list[EquipmentAllocation] = []
    for _i, r in rows:
        if _is_total_row(tuple(r)):
            continue
        company = str(r[2]).strip() if r[2] else ""
        big = str(r[3]).strip() if len(r) > 3 and r[3] else ""
        mid = str(r[4]).strip() if len(r) > 4 and r[4] else ""
        if not (company and big and mid):
            continue
        spec = str(r[5]).strip() if len(r) > 5 and r[5] else None
        cum_t = int(r[23]) if len(r) > 23 and isinstance(r[23], (int, float)) else 0
        eqs.append(
            {
                "bp_code": None,
                "company": company,
                "equipment_big": big,
                "equipment_mid": mid,
                "equipment_spec": spec,
                "count_cum_t": cum_t,
            }
        )
    return eqs


# ---------------------------------------------------------------------------
# Task 6: 공개 API
# ---------------------------------------------------------------------------

_DATE_PATTERN = re.compile(r"_(\d{4})(\d{2})(\d{2})\.xlsx$|_(\d{6})\.xlsm?$")


def _extract_meta(xlsx_path: Path, wb) -> tuple[str, str]:
    """파일명 -> report_date, 시트1 또는 파일명 -> project. 둘 다 실패 시 ParseError."""
    m = _DATE_PATTERN.search(xlsx_path.name)
    if m:
        if m.group(1):
            report_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        else:
            ymd = m.group(4)
            report_date = f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:6]}"
    else:
        raise ParseError(f"파일명에서 날짜 추출 실패: {xlsx_path.name}")

    project = ""
    sheet1_name = "1.출력인원 현황"
    if sheet1_name in wb.sheetnames:
        ws1 = wb[sheet1_name]
        for row in list(ws1.iter_rows(min_row=1, max_row=3, values_only=True)):
            for cell in row:
                if isinstance(cell, str) and ("M15X" in cell or "IBL" in cell or "PJT" in cell):
                    project = cell.strip()
                    break
            if project:
                break

    if not project:
        stem = xlsx_path.stem
        project = stem.replace("통합작업일보_", "").rsplit("_", 1)[0].strip()
        if not project:
            raise ParseError(f"project 추출 실패: {xlsx_path.name}")

    return report_date, project


def parse_daily_report(xlsx_path: Path | str) -> ParsedDailyReport:
    """작업일보 xlsx 1개 -> 4시트 통합 ParsedDailyReport.

    Args:
        xlsx_path: 통합작업일보 xlsx 절대 경로 (Path 또는 str).

    Returns:
        ParsedDailyReport -- spec 3 참조.

    Raises:
        ParseError: 시트명 누락, report_date/project 추출 실패.
    """
    xlsx_path = Path(xlsx_path)
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    try:
        required_sheets = {"1.출력인원 현황", "2.직종별 인원현황", "3.장비현황", "4.물량"}
        missing = required_sheets - set(wb.sheetnames)
        if missing:
            raise ParseError(f"시트 누락: {sorted(missing)}")

        report_date, project = _extract_meta(xlsx_path, wb)

        bp_summaries = _parse_sheet1_bp_summaries(wb["1.출력인원 현황"])
        job_allocations = _parse_sheet2_job_allocations(wb["2.직종별 인원현황"])
        equipment_allocations = _parse_sheet3_equipment_allocations(wb["3.장비현황"])
        activities = _parse_sheet4_activities(wb["4.물량"])
    finally:
        wb.close()

    return {
        "report_date": report_date,
        "project": project,
        "bp_summaries": bp_summaries,
        "job_allocations": job_allocations,
        "equipment_allocations": equipment_allocations,
        "activities": activities,
    }
