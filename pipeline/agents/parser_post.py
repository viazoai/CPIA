"""Parser LLM 출력 → 정제된 entity list.

LLM 은 raw row 단위 1:1 추출만. 본 모듈이:
  - 페어링 (BP 코드 row + 회사명 row → 1 BPSummary)
  - marker row filter (sub-section 시작 marker drop)
  - company normalize (㈜prefix / 괄호 sub-context 제거)
  - jsonschema validate
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_MARKER_SET = {"M15 PH-X", "FAB", "CUB", "M15X", "M15 X", "공통", "소계", "합계", "총계", "TOTAL"}
_BP_RE = re.compile(r"^PH_X-\d+$")


def _is_real_bp(value: str | None) -> bool:
    if not value:
        return False
    s = str(value).strip()
    if s in _MARKER_SET:
        return False
    if _BP_RE.match(s):
        return True
    return any("가" <= c <= "힣" for c in s)


def filter_marker_rows(raw_rows: list[dict], target_key: str = "company_or_bp") -> list[dict]:
    """marker row drop (sub-section 시작 marker)."""
    out = []
    for r in raw_rows:
        v = r.get(target_key)
        if _is_real_bp(v):
            out.append(r)
        else:
            logger.debug(f"filter_marker drop: {v!r}")
    return out


def pair_bp_summaries(raw_rows: list[dict]) -> list[dict]:
    """시트 1 의 2-row pairing.

    BP 코드 row (is_bp_code=true) + 다음 회사명 row (is_korean_company=true)
    + 같은 zone/disc_abbrev → 1 BPSummary 머지.
    그 외: each row = 1 BPSummary.
    """
    paired: list[dict] = []
    i = 0
    while i < len(raw_rows):
        r = raw_rows[i]
        next_r = raw_rows[i + 1] if i + 1 < len(raw_rows) else None
        is_pair = (
            r.get("is_bp_code")
            and next_r is not None
            and next_r.get("is_korean_company")
            and r.get("zone") == next_r.get("zone")
            and r.get("disc_abbrev") == next_r.get("disc_abbrev")
        )
        if is_pair:
            merged = {
                "bp_code": r.get("bp_code"),
                "company": next_r.get("company") or r.get("col_4_value"),
                "disc_abbrev": r.get("disc_abbrev") or next_r.get("disc_abbrev"),
                "zone": r.get("zone") or next_r.get("zone"),
                "scope": r.get("scope") or next_r.get("scope"),
                "work_text_today": next_r.get("work_text_today") or r.get("work_text_today"),
                "workers_today_cum": next_r.get("workers_today_cum") or r.get("workers_today_cum"),
                "today_cum_total": next_r.get("today_cum_total") or r.get("today_cum_total") or 0,
            }
            paired.append(merged)
            i += 2
        else:
            single = {
                "bp_code": r.get("bp_code"),
                "company": r.get("company") or r.get("bp_code") or r.get("col_4_value"),
                "disc_abbrev": r.get("disc_abbrev"),
                "zone": r.get("zone"),
                "scope": r.get("scope"),
                "work_text_today": r.get("work_text_today"),
                "workers_today_cum": r.get("workers_today_cum"),
                "today_cum_total": r.get("today_cum_total") or 0,
            }
            paired.append(single)
            i += 1
    return paired


def normalize_company(raw: str | None) -> str | None:
    """㈜prefix 제거 / 괄호 sub-context 제거 / FAB·CUB suffix 보존."""
    if not raw:
        return None
    s = str(raw).strip()
    s = s.lstrip("㈜").strip()
    s = re.sub(r"\([^)]*\)", "", s).strip()
    return s or None


def transform_job_allocations(raw_rows: list[dict]) -> list[dict]:
    """JobAllocationRaw list → JobAllocation list. company normalize + marker filter."""
    rows = filter_marker_rows(raw_rows, target_key="company_or_bp")
    return [
        {
            "company": normalize_company(r.get("company_or_bp")),
            "bp_code": r["company_or_bp"] if _BP_RE.match(str(r.get("company_or_bp") or "")) else None,
            "disc_abbrev": r.get("disc_abbrev"),
            "disc_code": r.get("disc_code"),
            "worker_code": r.get("worker_code"),
            "job_type": r.get("job_type"),
            "workers_today_cum": r.get("workers_today_cum"),
            "workers_cum_t": r.get("workers_cum_t") or 0,
            "final_flag": r.get("final_flag"),
        }
        for r in rows
        if r.get("job_type")
    ]


def transform_equipment_allocations(raw_rows: list[dict]) -> list[dict]:
    """EquipmentAllocationRaw → EquipmentAllocation."""
    rows = filter_marker_rows(raw_rows, target_key="company_or_bp")
    return [
        {
            "company": normalize_company(r.get("company_or_bp")),
            "bp_code": r["company_or_bp"] if _BP_RE.match(str(r.get("company_or_bp") or "")) else None,
            "disc_abbrev": r.get("disc_abbrev"),
            "equipment_big": r.get("equipment_big"),
            "equipment_mid": r.get("equipment_mid"),
            "equipment_spec": r.get("equipment_spec"),
            "count_today_cum": r.get("count_today_cum"),
            "count_cum_t": r.get("count_cum_t") or 0,
            "final_flag": r.get("final_flag"),
        }
        for r in rows
        if r.get("equipment_big") and r.get("equipment_mid")
    ]


def transform_bp_summaries(raw_rows: list[dict]) -> list[dict]:
    """BPSummaryRaw → BPSummary (페어링 + company normalize + marker filter)."""
    rows = filter_marker_rows(raw_rows, target_key="col_4_value")
    paired = pair_bp_summaries(rows)
    return [
        {
            "bp_code": r.get("bp_code"),
            "company": normalize_company(r.get("company")) or r.get("bp_code") or "",
            "disc_abbrev": r.get("disc_abbrev"),
            "zone": r.get("zone"),
            "scope": r.get("scope"),
            "work_text_today": r.get("work_text_today"),
            "workers_today_cum": r.get("workers_today_cum"),
            "today_cum_total": r.get("today_cum_total") or 0,
        }
        for r in paired
        if r.get("company") or r.get("bp_code")
    ]
