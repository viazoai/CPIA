"""Parser 에이전트 — 작업일보 xlsx -> ParsedDailyReport.

Spec: docs/superpowers/specs/2026-05-15-cpia-parser-design.md
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import openpyxl

from pipeline.agents.parser_post import (
    extract_zone,
    normalize_company,
    split_company_and_zone,
)
from pipeline.state import (
    Activity,
    BPSummary,
    EquipmentAllocation,
    JobAllocation,
    ParsedDailyReport,
    TimeShiftCounts,
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


_BP_RE = re.compile(r"^PH[_\- ]?X[_\- ]?\d+$", re.IGNORECASE)


def _is_bp_code(v: object) -> bool:
    if v is None:
        return False
    return bool(_BP_RE.match(str(v).strip()))


def _safe_int(v: object) -> int:
    if v is None:
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _shift_dict_sum(ws, start: int, end: int, col_start: int) -> TimeShiftCounts:
    """col_start..col_start+5 의 6 칸 시간대를 group row 합산."""
    keys = ("morning", "daytime", "overtime", "night", "all_night", "total")
    return {  # type: ignore[return-value]
        k: sum(_safe_int(ws.cell(r, col_start + i).value) for r in range(start, end + 1))
        for i, k in enumerate(keys)
    }


def _parse_sheet1_bp_summaries(ws) -> list[BPSummary]:
    """시트1 (출력인원 현황) -> BPSummary[].

    spec §2.2 (2026-05-20 refactor):
      - col 30 (금일 투입 그룹 Total) 의 merged range 또는 단독 row 가 group boundary
      - BP 코드 row (col 5 = PH_X-NNN) + 회사명 row (col 5 한글) 인접 pair
      - company 정규화 = split_company_and_zone (FAB/CUB suffix 분리) + normalize_company
      - zone = extract_zone(col 6) — 옵션 2 보수 매칭
      - sub-section 합계 row (bp+company 둘 다 None) skip
      - 빈 placeholder (company None + cum=0) skip
      - solo merged + 다음 row 흡수 (회사명 단독 row)

    주의: ws 는 `read_only=False` 모드여야 함 (merged_cells.ranges 필요).
    """
    # 1. col 30 merged 범위 수집 (값 있는 좌상단만)
    ad_merges: dict[int, int] = {}
    for mr in ws.merged_cells.ranges:
        if mr.min_col == 30 and mr.max_col == 30:
            top_val = ws.cell(mr.min_row, 30).value
            if top_val is None:
                continue
            ad_merges[mr.min_row] = mr.max_row

    # 2. solo row (merged 가 아니면서 col 30 값 있는 row)
    solo_rows: list[int] = []
    for r in range(5, ws.max_row + 1):
        v = ws.cell(r, 30).value
        if v is None:
            continue
        if not any(s <= r <= e for s, e in ad_merges.items()):
            solo_rows.append(r)

    # 3. group range 결정 (solo+next 흡수)
    raw_groups: list[tuple[int, int]] = list(ad_merges.items())
    for r in solo_rows:
        next_r = r + 1
        absorbed = False
        if next_r <= ws.max_row:
            v5_next = ws.cell(next_r, 5).value
            v30_next = ws.cell(next_r, 30).value
            in_other = any(s <= next_r <= e for s, e in ad_merges.items())
            if v5_next and v30_next is None and not in_other:
                raw_groups.append((r, next_r))
                absorbed = True
        if not absorbed:
            raw_groups.append((r, r))
    raw_groups.sort(key=lambda g: g[0])

    # 4. 각 group → BPSummary
    summaries: list[BPSummary] = []
    for start, end in raw_groups:
        bp_code: str | None = None
        company_raw: str | None = None
        col6_zone_raw: str | None = None
        work_text_today_parts: list[str] = []
        work_text_prev_parts: list[str] = []
        work_text_tomorrow_parts: list[str] = []

        for r in range(start, end + 1):
            v5 = ws.cell(r, 5).value
            v6 = ws.cell(r, 6).value
            v7 = ws.cell(r, 7).value
            v8 = ws.cell(r, 8).value
            v9 = ws.cell(r, 9).value

            if _is_bp_code(v5):
                bp_code = str(v5).strip()
                if v6 is not None and col6_zone_raw is None:
                    col6_zone_raw = str(v6)
            elif v5:
                if company_raw is None:
                    company_raw = str(v5)
                if v6 is not None and col6_zone_raw is None:
                    col6_zone_raw = str(v6)

            if v7:
                work_text_prev_parts.append(str(v7).strip())
            if v8:
                work_text_today_parts.append(str(v8).strip())
            if v9:
                work_text_tomorrow_parts.append(str(v9).strip())

        company = normalize_company(split_company_and_zone(company_raw))
        zone = extract_zone(col6_zone_raw)

        today_incr_total = _safe_int(ws.cell(start, 30).value)
        today_cum_total = _safe_int(ws.cell(start, 37).value)

        # spec §2.2 skip 조건
        if bp_code is None and not company:
            continue  # sub-section 합계
        if not company and today_incr_total == 0 and today_cum_total == 0:
            continue  # 빈 placeholder

        workers_today_incr = _shift_dict_sum(ws, start, end, 24)
        workers_today_cum = _shift_dict_sum(ws, start, end, 31)
        workers_yesterday_incr = _shift_dict_sum(ws, start, end, 10)
        workers_yesterday_cum = _shift_dict_sum(ws, start, end, 17)

        summaries.append(
            {
                "bp_code": bp_code,
                "company": company or "",
                "disc_abbrev": None,
                "zone": zone,
                "scope": col6_zone_raw,
                "work_text_yesterday": " | ".join(work_text_prev_parts) or None,
                "work_text_today": " | ".join(work_text_today_parts) or None,
                "work_text_tomorrow": " | ".join(work_text_tomorrow_parts) or None,
                "workers_yesterday_incr": workers_yesterday_incr,
                "workers_yesterday_cum": workers_yesterday_cum,
                "workers_today_incr": workers_today_incr,
                "workers_today_cum": workers_today_cum,
                "today_incr_total": today_incr_total,
                "today_cum_total": today_cum_total,
            }
        )
    return summaries


def _shift_dict_row(ws, r: int, col_start: int) -> TimeShiftCounts:
    """단일 row 의 col_start..col_start+5 6 칸 → TimeShiftCounts."""
    keys = ("morning", "daytime", "overtime", "night", "all_night", "total")
    return {  # type: ignore[return-value]
        k: _safe_int(ws.cell(r, col_start + i).value) for i, k in enumerate(keys)
    }


def _parse_sheet2_job_allocations(ws) -> list[JobAllocation]:
    """시트2 (직종별 인원현황) -> JobAllocation[].

    spec §2.3 (2026-05-20 refactor):
      - group 시작 = col 4='Mm01' + col 25='O' + col 2 채워있음 + col 3=PH_X-NNN
      - 직종 row = col 4 채워있음 + col 25='O' (subtotal/grand total skip — col 4=None)
      - 관리자 직종 (BP소장 등) 은 _is_admin_job 으로 filter (sub-pipeline 호환)
      - 회사명 = group 내 다음 5 row 안의 첫 col 3 한글값 (BP 코드 아님)
      - manager_code: Mm## / worker_code: sk## or Wk##
      - 3 시간대 그룹 (yest_cum col 7, today_incr col 13, today_cum col 19)
      - cross-check (직종 cum.t 합 vs grand_total col 24) — 불일치 시 미사용 (silent)
    """
    # 1. group 시작 row 식별
    starts: list[int] = []
    for r in range(6, ws.max_row + 1):
        c4 = ws.cell(r, 4).value
        if c4 != "Mm01":
            continue
        c2 = ws.cell(r, 2).value
        c3 = ws.cell(r, 3).value
        c25 = ws.cell(r, 25).value
        if c25 != "O" or c2 is None or c3 is None:
            continue
        if not _BP_RE.match(str(c3).strip()):
            continue
        starts.append(r)

    groups: list[tuple[int, int]] = [
        (s, (starts[i + 1] - 1) if i + 1 < len(starts) else ws.max_row) for i, s in enumerate(starts)
    ]

    jobs: list[JobAllocation] = []
    for start, end in groups:
        bp_code = str(ws.cell(start, 3).value).strip()
        discipline_raw = str(ws.cell(start, 2).value).strip()
        # col 2 의 keyword 가 한글 (공통가설 / 설비 등) 이면 그대로, 영문 약자면 한글 변환
        discipline = _disc_abbrev_to_kr(discipline_raw) or discipline_raw

        # 회사명: start 다음 5 row 안의 첫 col 3 한글값
        company_raw: str | None = None
        for r in range(start + 1, min(start + 6, end + 1)):
            v = ws.cell(r, 3).value
            if v is not None and not _is_bp_code(v):
                company_raw = str(v)
                break
        company = normalize_company(split_company_and_zone(company_raw)) or ""

        for r in range(start, end + 1):
            c4 = ws.cell(r, 4).value
            c25 = ws.cell(r, 25).value
            if c4 is None or c25 != "O":
                continue
            job_type = str(ws.cell(r, 6).value or "").strip()
            if not job_type:
                continue
            if _is_admin_job(job_type):
                continue
            disc_code = str(c4).strip()
            manager_code = disc_code if disc_code.startswith("Mm") else None
            worker_code = disc_code if not disc_code.startswith("Mm") else None
            workers_today_cum = _shift_dict_row(ws, r, 19)
            jobs.append(
                {
                    "bp_code": bp_code,
                    "company": company,
                    "disc_abbrev": discipline,
                    "manager_code": manager_code,
                    "worker_code": worker_code,
                    "job_type": job_type,
                    "workers_yesterday_cum": _shift_dict_row(ws, r, 7),
                    "workers_today_incr": _shift_dict_row(ws, r, 13),
                    "workers_today_cum": workers_today_cum,
                    "final_flag": "O",
                    "workers_cum_t": workers_today_cum.get("total", 0),
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
    # read_only=False: 시트1 의 merged_cells.ranges 필요 (spec §2.2)
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
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
        "worker_outputs": [],
        "report_meta": None,
    }
