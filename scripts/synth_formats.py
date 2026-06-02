"""합성 adversarial corpus 생성기 — V1~V5 변이 생성.

각 변이는 의미적으로 동치 (레이블/위치만 바뀌고 값은 보존).
Task 14: 로딩 가능한 .xlsx (>=4 시트) 생성 검증만. 의미 등치 검증은 Task 15.

⚠️ 한계 (왜 합성이 필요한가): 현재 가용한 실 업체 파일(docs/sample + data/demo_inputs 10개)은
fingerprint 1종 — 전부 동일 시트구조/헤더(같은 M15X IBL 템플릿)에 셀 company 도 전부 '중원엔지니어링'
복제본이다. 즉 spec 가 전제한 'P1 양식 변이(컬럼/헤더/시트명 변이)'를 보여줄 실 corpus 가 없다.
따라서 변이 흡수 능력은 이 합성 변이(V1 시트rename / V2 동의어 / V3 컬럼shuffle / V4 업체명컬럼삽입)로
검증한다 — V1~V3 는 fingerprint 가 실제로 바뀌면서도 parse 등가 유지됨을 test_synth_* 가 증명.
실 다양한 업체 양식이 확보되면 그 파일들로 골든 등가 테스트를 보강해야 한다.
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
    """V2: 헤더 동의어 치환 (결정론 recipe 가 흡수하는 동의어만).

    - sheet4: `대표물량_작업 내용` → `작업내용` (work_content — _resolve_sheet4_columns 가 흡수)
    - sheet3: `대분류` → `장비명` (equip_big — field_for_header 동의어 흡수)

    주의: `금일실적`→`당일실적` 류 sheet4 today_qty 동의어는 _resolve_sheet4_columns 가
    "금일실적" 만 인식하므로 결정론 흡수 불가 (Tier2 LLM 영역). V2 는 결정론 등치 변이만 담아
    Task 15 등가 테스트가 통과하도록 한다.
    """
    swap_map = {
        "대표물량_작업내용": "작업내용",
        "대분류": "장비명",
    }
    for name in wb.sheetnames:
        ws = wb[name]
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
    """V4: activity 시트에 `업체명` 컬럼 삽입 (vendor → 통합축).

    업체파일 BP사 컬럼(col 5)은 BP 코드행과 회사명행이 교대로 들어있다. 통합포맷의
    company_col 은 회사명만 담으므로, col 5 의 회사명(비-BP코드 한글값)을 ffill 해 새
    company_col(col 6)에 채운다 — BP 코드가 company 로 누출되지 않도록 (값 의미 보존).
    """
    from pipeline.agents.recipe.bpcode import is_bp_code_v2

    activity_name = _find_activity_sheet(wb)
    ws = wb[activity_name]
    bp_col = 5
    insert_at = 6
    max_row = ws.max_row or 0

    _insert_column_right(ws, insert_at, fill_value=None)
    ws.cell(3, insert_at).value = "업체명"
    ws.cell(4, insert_at).value = None

    # col 5 의 회사명을 ffill 해 company_col 에 기록 (BP 코드행은 직전 회사명 유지)
    cur_company: str | None = None
    for r in range(5, max_row + 1):
        v = ws.cell(r, bp_col).value
        if v is not None and not is_bp_code_v2(v):
            s = str(v).strip()
            if s:
                cur_company = s
        ws.cell(r, insert_at).value = cur_company


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

    # data_only=True: 수식 셀을 캐시값(리터럴)으로 읽어 재저장 — 원본 헤더 다수가
    # =CONCATENATE(...) 수식(예: "금일 작업사항 [09/17]")이라, formula 모드로 재저장하면
    # openpyxl 이 캐시값을 잃어 data_only 로 다시 읽을 때 None 이 된다. 합성 corpus 는 값만 필요하므로
    # 리터럴로 고정하는 것이 정확 (값 보존, 의미 등치 유지).
    wb = load_workbook(src_path, data_only=True)
    _VARIANTS[variant](wb)
    wb.save(out_path)
    wb.close()
