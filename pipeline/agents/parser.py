"""Parser 에이전트 — 작업일보 xlsx → ParsedDailyReport.

Spec: docs/superpowers/specs/2026-05-15-cpia-parser-design.md
"""

from __future__ import annotations

from typing import Any


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
    """단위 대소문자 통일 (M2→m2, Ton→ton)."""
    return s.lower() if s else ""


def _disc_abbrev_to_kr(abbrev: str | None) -> str | None:
    """공종 약자 → 한글 (알 수 없으면 원본 보존)."""
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


def _parse_sheet4_activities(ws) -> list[Activity]:
    """시트 4 (물량) → Activity[]. fixture loader _load_inputs 이관.

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
