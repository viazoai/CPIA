"""Recipe 기반 추출 — sheet4(물량) Activity[].

Task 6: parser.py _parse_sheet4_activities 를 그대로 포팅하되,
컬럼 위치를 _resolve_sheet4_columns 재호출이 아니라 recipe.columns 로 주입.
BP 코드 판정만 is_bp_code_v2 (Task 3) 로 교체. row loop·group 경계·company ffill·
skip·today_qty 파싱은 원본을 line-by-line 전사 (재설계 금지 — IRON LAW).
"""

from __future__ import annotations

from pipeline.agents.parser import _build_activity, _safe_int, _shift_dict_sum
from pipeline.agents.parser_post import (
    extract_zone,
    normalize_company,
    split_company_and_zone,
)
from pipeline.agents.recipe.bpcode import is_bp_code_v2
from pipeline.agents.recipe.model import SheetRecipe
from pipeline.state import Activity, BPSummary


def extract_sheet1(ws, sheet_recipe: SheetRecipe) -> list[BPSummary]:
    """시트1 (출력인원 현황) -> BPSummary[].

    _parse_sheet1_bp_summaries 전사:
      - 그룹 경계는 col30(=cols["today_incr_total"]) 컬럼의 merged range + solo row 흡수
      - 컬럼 위치는 recipe(sheet_recipe.columns/timeshift_blocks) 로 주입
      - BP 코드 판정만 is_bp_code_v2 로 교체, 그 외 row loop·skip·시간대 4블록은 line-by-line 전사
    """
    cols = sheet_recipe.columns
    blocks = sheet_recipe.timeshift_blocks
    tot_col = cols["today_incr_total"]
    cum_tot_col = cols.get("today_cum_total")
    bpc = cols["bp_company"]
    scol = cols.get("scope")

    # 1. col 30(=tot_col) merged 범위 수집 (값 있는 좌상단만)
    ad_merges: dict[int, int] = {}
    for mr in ws.merged_cells.ranges:
        if mr.min_col == tot_col and mr.max_col == tot_col:
            top_val = ws.cell(mr.min_row, tot_col).value
            if top_val is None:
                continue
            ad_merges[mr.min_row] = mr.max_row

    # 2. solo row (merged 가 아니면서 tot_col 값 있는 row)
    solo_rows: list[int] = []
    for r in range(5, ws.max_row + 1):
        v = ws.cell(r, tot_col).value
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
            v5_next = ws.cell(next_r, bpc).value
            v30_next = ws.cell(next_r, tot_col).value
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
            v5 = ws.cell(r, bpc).value
            v6 = ws.cell(r, scol).value if scol else None
            v7 = ws.cell(r, cols["work_prev"]).value if "work_prev" in cols else None
            v8 = ws.cell(r, cols["work_today"]).value if "work_today" in cols else None
            v9 = ws.cell(r, cols["work_tomorrow"]).value if "work_tomorrow" in cols else None

            if is_bp_code_v2(v5):
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

        today_incr_total = _safe_int(ws.cell(start, tot_col).value)
        today_cum_total = _safe_int(ws.cell(start, cum_tot_col).value) if cum_tot_col else 0

        # spec §2.2 skip 조건
        if bp_code is None and not company:
            continue  # sub-section 합계
        if not company and today_incr_total == 0 and today_cum_total == 0:
            continue  # 빈 placeholder

        workers_today_incr = _shift_dict_sum(ws, start, end, blocks["today_incr"])
        workers_today_cum = _shift_dict_sum(ws, start, end, blocks["today_cum"])
        workers_yesterday_incr = _shift_dict_sum(ws, start, end, blocks["yest_incr"])
        workers_yesterday_cum = _shift_dict_sum(ws, start, end, blocks["yest_cum"])

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
