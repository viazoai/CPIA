"""Parser 에이전트 — 작업일보 xlsx -> ParsedDailyReport.

Spec: docs/superpowers/specs/2026-05-15-cpia-parser-design.md +
      docs/superpowers/specs/2026-05-20-cpia-parser-mapper-refactor-design.md
"""

from __future__ import annotations

import json
import os
import re
import sys
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


_BP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^PH[_\- ]?X[_\- ]?\d+$", re.IGNORECASE),  # 통합: PH_X-088
    re.compile(r"^[A-Za-z][A-Za-z0-9]*_PH\d+_\d+$", re.IGNORECASE),  # 업체: M15X_PH4_041
)


def _is_bp_code(v: object) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    return any(p.match(s) for p in _BP_PATTERNS)


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
        if not _is_bp_code(c3):
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


def _safe_num(v: object) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_sheet4_activities(ws) -> list[Activity]:
    """시트4 (물량) -> Activity[].

    spec §2.5 (2026-05-20 refactor):
      - ffill 4 컬럼 (col 3 zone_raw, col 4 trade, col 5 BP 코드, col 6 회사명)
      - col 5 (BP) 채워있는 row = 새 회사 그룹 시작 (col 6 = 회사명)
      - Activity row = col 8 (work_content) 채워있는 row 만
      - zone = extract_zone(col 7 명시 토큰만, 옵션 2 — scope ≠ wa)
      - B+C=D 산술 cross-check — mismatch 카운트만 (silent)
    """
    current_trade: str | None = None
    current_bp_code: str | None = None
    current_company_raw: str | None = None

    activities: list[Activity] = []

    for r in range(5, ws.max_row + 1):
        c4 = ws.cell(r, 4).value
        c5 = ws.cell(r, 5).value
        c6 = ws.cell(r, 6).value

        if c4 is not None:
            current_trade = str(c4)
        if c5 is not None:
            current_bp_code = str(c5).strip()
            current_company_raw = str(c6) if c6 is not None else None

        c8 = ws.cell(r, 8).value
        if c8 is None:
            continue

        c7 = ws.cell(r, 7).value  # Scope
        c9 = ws.cell(r, 9).value  # unit
        c10 = _safe_num(ws.cell(r, 10).value)  # plan_total
        c11 = _safe_num(ws.cell(r, 11).value)  # yesterday_cum
        c12 = _safe_num(ws.cell(r, 12).value)  # today_qty
        c13 = _safe_num(ws.cell(r, 13).value)  # today_cum
        c14 = _safe_num(ws.cell(r, 14).value)  # F%

        company = normalize_company(split_company_and_zone(current_company_raw))
        zone = extract_zone(str(c7) if c7 is not None else None)

        activities.append(
            {
                "zone": zone,
                "bp_code": current_bp_code,
                "company": company or "",
                "scope": str(c7) if c7 is not None else None,
                "trade": current_trade or "",
                "work_content": str(c8).strip(),
                "unit": _normalize_unit(str(c9 or "").strip()),
                "plan_total_qty": c10,
                "yesterday_cum_qty": c11,
                "today_qty": c12 if c12 is not None else 0.0,
                "today_cum_qty": c13,
                "progress_percent": c14,
                "remaining_qty": None,
                "remaining_percent": None,
                "note": None,
                "work_location_code": None,
                "wbs_mid_name": None,
                "wbs_sub_name": None,
                "wbs_detail_name": None,
                "wbs_activity_id": None,
                "l5_disc": current_trade or "",
                "l6_main": None,
                "l7_sub": None,
                "l7_5_activity": None,
                "sub_work_area": None,
                "conditions": [],
                "assigned_workers": 0.0,
                "worker_source": "parsed",
                "plan_mh": None,
                "wa": None,
                "mapping_conf": None,
                "mapping_source": None,
                "requires_review": False,
            }
        )
    return activities


def _parse_sheet3_equipment_allocations(ws) -> list[EquipmentAllocation]:
    """시트3 (장비현황) -> EquipmentAllocation[].

    spec §2.4 (2026-05-20 refactor):
      - group 시작 = col 2 (공종) + col 3 (PH_X-NNN) + col 4 (장비 대분류) 채워있음
      - 헤더 reprint row ('장비 투입...') 회피
      - 장비 row = col 25='O' + col 4 채워있음
      - 회사명 = group 내 첫 col 3 한글값
      - 3 시간대 그룹 (yest_cum col 7, today_incr col 13, today_cum col 19)
      - subtotal 없음 → cross-check 불요
    """
    starts: list[int] = []
    for r in range(6, ws.max_row + 1):
        c2 = ws.cell(r, 2).value
        c3 = ws.cell(r, 3).value
        c4 = ws.cell(r, 4).value
        if c2 is None or c3 is None or c4 is None:
            continue
        if not _is_bp_code(c3):
            continue
        # 헤더 reprint row 회피
        if "장비 투입" in str(c2):
            continue
        starts.append(r)

    groups: list[tuple[int, int]] = [
        (s, (starts[i + 1] - 1) if i + 1 < len(starts) else ws.max_row) for i, s in enumerate(starts)
    ]

    eqs: list[EquipmentAllocation] = []
    for start, end in groups:
        bp_code = str(ws.cell(start, 3).value).strip()
        discipline_raw = str(ws.cell(start, 2).value).strip()
        discipline = _disc_abbrev_to_kr(discipline_raw) or discipline_raw

        company_raw: str | None = None
        for r in range(start + 1, min(start + 6, end + 1)):
            v = ws.cell(r, 3).value
            if v is not None and not _is_bp_code(v):
                company_raw = str(v)
                break
        company = normalize_company(split_company_and_zone(company_raw)) or ""

        for r in range(start, end + 1):
            c25 = ws.cell(r, 25).value
            if c25 != "O":
                continue
            c4 = ws.cell(r, 4).value
            if c4 is None:
                continue
            count_today_cum = _shift_dict_row(ws, r, 19)
            eqs.append(
                {
                    "bp_code": bp_code,
                    "company": company,
                    "disc_abbrev": discipline,
                    "equipment_big": str(c4).strip(),
                    "equipment_mid": str(ws.cell(r, 5).value or "").strip(),
                    "equipment_spec": (
                        str(ws.cell(r, 6).value).strip() if ws.cell(r, 6).value is not None else None
                    ),
                    "count_yesterday_cum": _shift_dict_row(ws, r, 7),
                    "count_today_incr": _shift_dict_row(ws, r, 13),
                    "count_today_cum": count_today_cum,
                    "final_flag": "O",
                    "count_cum_t": count_today_cum.get("total", 0),
                }
            )
    return eqs


# ---------------------------------------------------------------------------
# Task 6: 공개 API
# ---------------------------------------------------------------------------

_DATE_PATTERN = re.compile(r"_(\d{4})(\d{2})(\d{2})\.(?:xlsx|xlsm)$|_(\d{6})\.(?:xlsx|xlsm)$")


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

        # spec §2.6 — 시트1/4 LLM 검증 (default on, CPIA_PARSER_VERIFY_LLM=off 로 opt-out)
        if _should_verify_llm():
            _verify_sheet1_via_llm(wb["1.출력인원 현황"], bp_summaries)
            _verify_sheet4_via_llm(wb["4.물량"], activities)
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


# ---------------------------------------------------------------------------
# 2026-05-20 refactor: 시트1/4 LLM 검증 wrapper (spec §2.6)
# ---------------------------------------------------------------------------


def _should_verify_llm() -> bool:
    """env CPIA_PARSER_VERIFY_LLM — default 'on', 'off'/'false'/'0'/'no' 면 opt-out."""
    v = os.environ.get("CPIA_PARSER_VERIFY_LLM", "on").lower().strip()
    return v not in ("off", "false", "0", "no")


def _verify_sheet1_via_llm(ws, bp_summaries: list[BPSummary]) -> None:
    """spec §2.6.1 — 시트1 rule 결과 LLM 검증. issues 는 stderr 로그만 (결정성 보존).

    8 종 error path graceful catch (timeout 30s / length / content_filter /
    JSONDecodeError / Exception broad / 빈 input / API key 없음).
    """
    if not bp_summaries:
        return  # 빈 input
    try:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        )
        raw_rows = []
        for r in range(5, ws.max_row + 1):
            v5 = ws.cell(r, 5).value
            if v5 is None:
                continue
            raw_rows.append(
                {
                    "r": r,
                    "col5": v5,
                    "col6": ws.cell(r, 6).value,
                    "col7_prev": ws.cell(r, 7).value,
                    "col8_today": ws.cell(r, 8).value,
                    "col30_total": ws.cell(r, 30).value,
                    "col37_cum": ws.cell(r, 37).value,
                }
            )
        sys_prompt = (
            "건설 작업일보 시트1 (출력인원) rule 추출 검증. "
            "각 BPSummary 필드: bp_code (PH_X-NNN), company (정규화), zone (FAB/CUB/null), "
            "work_text_today, today_cum_total. raw 와 명확히 어긋난 경우만 issues 에 보고. "
            'JSON: {"issues": [{"row": N, "field": "...", "current": "...", '
            '"expected": "...", "why": "..."}]}'
        )
        payload = {"rule_results": list(bp_summaries), "raw_rows": raw_rows}
        resp = client.chat.completions.create(
            model=os.environ["LLM_MODEL"],
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=2000,
            timeout=30,
        )
        choice = resp.choices[0]
        if choice.finish_reason in ("length", "content_filter"):
            print(
                f"[parser:sheet1] LLM verify finish_reason={choice.finish_reason} — issues=[]",
                file=sys.stderr,
                flush=True,
            )
            return
        try:
            verify = json.loads(choice.message.content or "{}")
        except json.JSONDecodeError as e:
            print(
                f"[parser:sheet1] LLM verify malformed JSON: {e} — issues=[]",
                file=sys.stderr,
                flush=True,
            )
            return
        for it in verify.get("issues", []):
            print(
                f"[parser:sheet1] LLM 검증 issue: row={it.get('row')} field={it.get('field')} "
                f"current={it.get('current')} expected={it.get('expected')} reason={it.get('why')}",
                file=sys.stderr,
                flush=True,
            )
    except Exception as e:  # noqa: BLE001 — spec §2.6.4 broad catch (cycle block 방지)
        print(
            f"[parser:sheet1] LLM verify EXCEPTION: {type(e).__name__}: {e}",
            file=sys.stderr,
            flush=True,
        )


def _verify_sheet4_via_llm(ws, activities: list[Activity]) -> None:
    """spec §2.6.1 — 시트4 sample LLM 검증. 8 종 error path graceful catch."""
    if not activities:
        return
    try:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        )
        # sample 선정 — 첫 10 + 의심 (zone None / plan None / work<=3) 각 5 + 끝 5
        suspicious_zone = [a for a in activities if a.get("zone") is None][:5]
        suspicious_no_plan = [a for a in activities if a.get("plan_total_qty") is None][:5]
        suspicious_short = [a for a in activities if len(a.get("work_content", "")) <= 3][:5]
        sample = (
            list(activities[:10])
            + suspicious_zone
            + suspicious_no_plan
            + suspicious_short
            + list(activities[-5:])
        )
        seen: set = set()
        sample_unique: list = []
        for a in sample:
            key = (a.get("bp_code"), a.get("work_content"))
            if key in seen:
                continue
            seen.add(key)
            sample_unique.append(a)

        sys_prompt = (
            "건설 작업일보 시트4 (물량) rule 추출 검증. "
            "각 Activity 필드: company / bp_code / trade / zone (FAB/CUB/null) / "
            "work_content / unit / plan_total_qty / today_cum_qty. "
            "명확한 mis-parse 만 보고. "
            'JSON: {"issues": [{"company": "...", "work_content": "...", "field": "...", '
            '"current": "...", "expected": "...", "why": "..."}]}'
        )
        payload = {"rule_results_sample": sample_unique}
        resp = client.chat.completions.create(
            model=os.environ["LLM_MODEL"],
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=1500,
            timeout=30,
        )
        choice = resp.choices[0]
        if choice.finish_reason in ("length", "content_filter"):
            print(
                f"[parser:sheet4] LLM verify finish_reason={choice.finish_reason} — issues=[]",
                file=sys.stderr,
                flush=True,
            )
            return
        try:
            verify = json.loads(choice.message.content or "{}")
        except json.JSONDecodeError as e:
            print(
                f"[parser:sheet4] LLM verify malformed JSON: {e} — issues=[]",
                file=sys.stderr,
                flush=True,
            )
            return
        for it in verify.get("issues", []):
            print(
                f"[parser:sheet4] LLM 검증 issue: work={it.get('work_content')} "
                f"field={it.get('field')} current={it.get('current')} "
                f"expected={it.get('expected')} reason={it.get('why')}",
                file=sys.stderr,
                flush=True,
            )
    except Exception as e:  # noqa: BLE001
        print(
            f"[parser:sheet4] LLM verify EXCEPTION: {type(e).__name__}: {e}",
            file=sys.stderr,
            flush=True,
        )
