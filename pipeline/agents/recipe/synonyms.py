from __future__ import annotations

from pipeline.agents.parser import _norm_header

# 헤더(정규화, _norm_header 가 공백 제거) -> 스키마 필드. 동의어는 같은 값으로.
_FIELD_SYNONYMS: dict[str, str] = {
    "공종": "trade",
    "Dis": "trade",
    "BP사": "bp",
    "협력업체": "bp",
    "업체명": "company_col",
    "Scope": "scope",
    "단위": "unit",
    "금일실적": "today_qty",
    "당일실적": "today_qty",
    "todayactual": "today_qty",
    "금일누적": "today_cum",
    "전일누적": "yesterday_cum",
    "총물량": "plan_total",
    # sheet2 (직종) 필수필드
    "관리자/근로자": "disc_code",  # col4 = Mm01/sk01 앵커
    "직종": "job_type",  # col6 = BP소장/배관공 등
    # sheet3 (장비) 필수/보조필드
    "대분류": "equip_big",
    "장비명": "equip_big",
    "중분류": "equip_mid",
    "규격": "equip_spec",  # "규 격" → _norm_header → "규격"
}

# 부분일치(substring) 필드 — 헤더에 토큰 포함 시 매핑 (날짜 brackets·group 라벨 흡수)
_FIELD_CONTAINS: list[tuple[str, str]] = [
    ("대표물량", "work_content"),
    ("작업내용", "work_content"),
    ("전일작업", "work_prev"),
    ("금일작업", "work_today"),
    ("명일작업", "work_tomorrow"),
]

# 시트명(정규화) -> role. canonical + 변이 alias.
_SHEET_ALIASES: dict[str, str] = {
    "1.출력인원현황": "bp_summary",
    "출력인원현황": "bp_summary",
    "출력인원": "bp_summary",
    "2.직종별인원현황": "job",
    "직종별인원현황": "job",
    "직종별인원": "job",
    "3.장비현황": "equip",
    "장비현황": "equip",
    "4.물량": "activity",
    "물량": "activity",
    "물량집계": "activity",
    "수량집계": "activity",
}


def field_for_header(raw) -> str | None:
    h = _norm_header(raw)
    if not h:
        return None
    if h in _FIELD_SYNONYMS:
        return _FIELD_SYNONYMS[h]
    if h.lower() in _FIELD_SYNONYMS:
        return _FIELD_SYNONYMS[h.lower()]
    for tok, fld in _FIELD_CONTAINS:
        if tok in h:
            return fld
    return None


def role_for_sheet(name: str) -> str | None:
    return _SHEET_ALIASES.get(_norm_header(name))
