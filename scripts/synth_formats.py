"""합성 adversarial corpus 생성기 — V1~V5 변이 생성.

각 변이는 의미적으로 동치 (레이블/위치만 바뀌고 값은 보존).
Task 14: 로딩 가능한 .xlsx (>=4 시트) 생성 검증만. 의미 등치 검증은 Task 15.
"""

from __future__ import annotations

from openpyxl import load_workbook

from pipeline.agents.parser import _norm_header


# ──────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────


def _find_activity_sheet(wb) -> str:
    """인식 모듈 없이 단순 이름 탐색으로 activity 시트명 반환."""
    _ACTIVITY_NAMES = {"4.물량", "물량집계", "수량집계", "물량"}
    for name in wb.sheetnames:
        if _norm_header(name) in {_norm_header(n) for n in _ACTIVITY_NAMES}:
            return name
    # fallback: 마지막으로 등록된 인식 가능 시트
    return wb.sheetnames[0]


def _find_header_cell(
    ws, search_text: str, header_rows=(3, 4, 5)
) -> tuple[int, int] | None:
    """header_rows 내에서 _norm_header(cell) == _norm_header(search_text) 인 첫 셀 반환."""
    target = _norm_header(search_text)
    for r in header_rows:
        for c in range(1, (ws.max_column or 0) + 1):
            if _norm_header(ws.cell(r, c).value) == target:
                return r, c
    return None


def _get_col_data(ws, col: int, start_row: int = 1) -> list:
    """워크시트에서 지정 컬럼의 모든 셀 값을 start_row 부터 반환."""
    return [ws.cell(r, col).value for r in range(start_row, (ws.max_row or 0) + 1)]


def _set_col_data(ws, col: int, values: list, start_row: int = 1) -> None:
    """워크시트의 지정 컬럼에 values 를 start_row 부터 기록."""
    for i, v in enumerate(values):
        ws.cell(start_row + i, col).value = v


def _move_column(ws, from_col: int, to_col: int) -> None:
    """from_col 전체 셀을 to_col 로 이동. 이동 방향에 따라 중간 컬럼을 한 칸씩 shift.

    헤더 + 데이터 행 모두 함께 이동하므로 컬럼 의미가 보존됨.
    """
    max_row = ws.max_row or 0
    # 이동 대상 컬럼 값 저장
    col_vals = _get_col_data(ws, from_col, start_row=1)

    if from_col < to_col:
        # 오른쪽으로 이동: from_col+1 ~ to_col 을 한 칸 왼쪽으로 밀기
        for c in range(from_col, to_col):
            src_vals = _get_col_data(ws, c + 1, start_row=1)
            _set_col_data(ws, c, src_vals, start_row=1)
    else:
        # 왼쪽으로 이동: to_col ~ from_col-1 을 한 칸 오른쪽으로 밀기
        for c in range(from_col, to_col, -1):
            src_vals = _get_col_data(ws, c - 1, start_row=1)
            _set_col_data(ws, c, src_vals, start_row=1)

    # 저장된 원본 컬럼을 목적지에 기록
    _set_col_data(ws, to_col, col_vals, start_row=1)

    _ = max_row  # suppress unused-variable lint


def _insert_column_right(ws, insert_at: int, fill_value=None) -> None:
    """insert_at 컬럼 위치에 새 컬럼 삽입. 오른쪽 컬럼들을 한 칸씩 우측 shift.

    openpyxl insert_cols() 를 사용해 merged-cell 범위도 올바르게 우측 shift 함.
    새 컬럼은 fill_value 로 채움.
    """
    ws.insert_cols(insert_at)
    max_row = ws.max_row or 0
    for r in range(1, max_row + 1):
        ws.cell(r, insert_at).value = fill_value


# ──────────────────────────────────────────────
# 변이 구현
# ──────────────────────────────────────────────


def _apply_v1(wb) -> None:
    """V1: 시트명 변경.

    `4.물량` → `물량집계`, `1.출력인원 현황` → `출력인원`
    """
    rename_map = {
        "4.물량": "물량집계",
        "1.출력인원 현황": "출력인원",
    }
    for old, new in rename_map.items():
        if old in wb.sheetnames:
            wb[old].title = new


def _apply_v2(wb) -> None:
    """V2: 헤더 동의어 치환.

    activity 시트에서 `금일실적` → `당일실적`, `대표물량_작업 내용` → `작업내용`
    """
    activity_name = _find_activity_sheet(wb)
    ws = wb[activity_name]
    swap_map = {
        "금일실적": "당일실적",
        "대표물량_작업내용": "작업내용",
    }
    for r in range(1, min((ws.max_row or 0) + 1, 6)):
        for c in range(1, (ws.max_column or 0) + 1):
            norm = _norm_header(ws.cell(r, c).value)
            if norm in swap_map:
                ws.cell(r, c).value = swap_map[norm]


def _apply_v3(wb) -> None:
    """V3: sheet4 컬럼 순서 shuffle.

    `금일실적`(col 11) 을 `전일누적`(col 10) 앞으로 이동 — 헤더+데이터 함께 이동.
    실제 이동: col 11 → col 10 (두 컬럼을 swap 해 col 순서 10↔11 교환).
    """
    activity_name = _find_activity_sheet(wb)
    ws = wb[activity_name]

    # 이동 대상 컬럼 탐색 (헤더행 기준)
    pos = _find_header_cell(ws, "금일실적")
    if pos is None:
        # fallback: 고정 컬럼 인덱스 사용
        from_col, to_col = 11, 10
    else:
        from_col = pos[1]
        to_col = from_col - 1 if from_col > 1 else from_col + 1

    if from_col == to_col:
        return

    # swap: from_col ↔ to_col
    max_row = ws.max_row or 0
    for r in range(1, max_row + 1):
        a = ws.cell(r, from_col).value
        b = ws.cell(r, to_col).value
        ws.cell(r, from_col).value = b
        ws.cell(r, to_col).value = a


def _apply_v4(wb) -> None:
    """V4: activity 시트에 `업체명` 컬럼 삽입.

    기존 데이터의 BP사 컬럼(col 5)에서 업체명을 읽어 새 컬럼(col 6)에 삽입.
    이후 컬럼은 모두 우측으로 1칸 shift.
    """
    activity_name = _find_activity_sheet(wb)
    ws = wb[activity_name]

    # BP사 컬럼(col 5)에서 값 수집 (row5 이후 데이터)
    bp_col = 5
    max_row = ws.max_row or 0

    # 삽입 위치: BP사(col 5) 바로 다음 col 6
    insert_at = 6

    # 기존 컬럼을 우측으로 한 칸 밀기
    _insert_column_right(ws, insert_at, fill_value=None)

    # 헤더 행(3, 4)에 `업체명` 기록
    ws.cell(3, insert_at).value = "업체명"
    ws.cell(4, insert_at).value = None

    # 데이터 행 (row 5~): BP사 컬럼 값을 업체명 컬럼에 복사
    for r in range(5, max_row + 1):
        # insert 후 BP사 컬럼은 여전히 col 5 (shift 되지 않은 쪽)
        ws.cell(r, insert_at).value = ws.cell(r, bp_col).value


def _apply_v5(wb) -> None:
    """V5: 영문 헤더 치환.

    activity 시트의 한국어 헤더를 영문 동의어로 교체.
    """
    activity_name = _find_activity_sheet(wb)
    ws = wb[activity_name]
    en_map = {
        "금일실적": "Today Actual",
        "당일실적": "Today Actual",
        "대표물량_작업내용": "Work Content",
        "작업내용": "Work Content",
        "단위": "Unit",
        "공종": "Trade",
        "BP사": "BP",
        "전일누적": "Prev Cum",
        "금일누적": "Today Cum",
        "총물량": "Plan Total",
        "잔여": "Remaining",
        "구분": "Class",
    }
    for r in range(1, min((ws.max_row or 0) + 1, 6)):
        for c in range(1, (ws.max_column or 0) + 1):
            norm = _norm_header(ws.cell(r, c).value)
            if norm in en_map:
                ws.cell(r, c).value = en_map[norm]


# ──────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────

_VARIANTS = {
    "V1": _apply_v1,
    "V2": _apply_v2,
    "V3": _apply_v3,
    "V4": _apply_v4,
    "V5": _apply_v5,
}


def make_variant(src_path: str, variant: str, out_path: str) -> None:
    """src_path 를 읽어 variant 변이를 적용한 뒤 out_path 에 저장.

    Parameters
    ----------
    src_path:
        원본 vendor xlsx 경로.
    variant:
        변이 코드 — "V1" | "V2" | "V3" | "V4" | "V5".
    out_path:
        출력 xlsx 경로.

    Raises
    ------
    ValueError
        variant 가 알 수 없는 코드인 경우.
    """
    if variant not in _VARIANTS:
        raise ValueError(
            f"알 수 없는 변이 코드: {variant!r}. 유효값: {sorted(_VARIANTS)}"
        )

    # data_only=False: 수식 보존 + 재저장 가능
    wb = load_workbook(src_path)
    _VARIANTS[variant](wb)
    wb.save(out_path)
    wb.close()
