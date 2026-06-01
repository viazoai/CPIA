"""Recipe 기반 추출 — sheet4(물량) Activity[].

Task 6: parser.py _parse_sheet4_activities 를 그대로 포팅하되,
컬럼 위치를 _resolve_sheet4_columns 재호출이 아니라 recipe.columns 로 주입.
BP 코드 판정만 is_bp_code_v2 (Task 3) 로 교체. row loop·group 경계·company ffill·
skip·today_qty 파싱은 원본을 line-by-line 전사 (재설계 금지 — IRON LAW).
"""

from __future__ import annotations

from pipeline.agents.parser import _build_activity
from pipeline.agents.recipe.bpcode import is_bp_code_v2
from pipeline.agents.recipe.model import SheetRecipe
from pipeline.state import Activity


def extract_sheet4(ws, sheet_recipe: SheetRecipe) -> list[Activity]:
    """시트4 (물량) -> Activity[].

    _parse_sheet4_activities 전사:
      - 컬럼 위치는 recipe(sheet_recipe.columns) 로 주입 (통합/업체 흡수)
      - 통합포맷(company_col 존재): trade ffill + company 는 BP행에 종속(독립 ffill 아님)
      - 업체포맷(company_col 없음): BP 코드행~다음 코드행 group, company = group 내 첫 non-bp
      - Activity row = work_content 채워있는 row 만
      - zone = extract_zone(scope 명시 토큰만, 옵션 2 — scope ≠ wa)
    """
    cols = sheet_recipe.columns
    has_company_col = "company_col" in cols
    activities: list[Activity] = []
    if has_company_col:
        # 통합포맷: trade ffill + company 는 BP행에 종속(독립 ffill 아님)
        cur_trade = cur_bp = cur_company_raw = None
        for r in range(5, ws.max_row + 1):
            tv = ws.cell(r, cols["trade"]).value
            if tv is not None:
                cur_trade = str(tv)
            bv = ws.cell(r, cols["bp"]).value
            if bv is not None:
                cur_bp = str(bv).strip()
                cv = ws.cell(r, cols["company_col"]).value
                cur_company_raw = str(cv) if cv is not None else None
            wv = ws.cell(r, cols["work_content"]).value
            if wv is None:
                continue
            activities.append(_build_activity(ws, r, cols, cur_trade, cur_bp, cur_company_raw))
    else:
        # 업체포맷: BP사 컬럼 코드행~다음코드행 group, 회사명=group 내 첫 non-bp 값
        bpc = cols["bp"]
        code_rows = [r for r in range(5, ws.max_row + 1) if is_bp_code_v2(ws.cell(r, bpc).value)]
        for gi, start in enumerate(code_rows):
            end = (code_rows[gi + 1] - 1) if gi + 1 < len(code_rows) else ws.max_row
            bp_code = str(ws.cell(start, bpc).value).strip()
            company_raw = None
            for r in range(start, end + 1):
                v = ws.cell(r, bpc).value
                if v is not None and not is_bp_code_v2(v):
                    company_raw = str(v)
                    break
            cur_trade = None
            for r in range(5, start + 1):
                tv = ws.cell(r, cols["trade"]).value
                if tv is not None:
                    cur_trade = str(tv)
            for r in range(start, end + 1):
                if ws.cell(r, cols["work_content"]).value is None:
                    continue
                activities.append(_build_activity(ws, r, cols, cur_trade, bp_code, company_raw))
    return activities
