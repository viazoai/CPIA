"""Exporter — 통합 작업일보 xlsx 생성.

Spec: docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md §7
"""

from __future__ import annotations

import json
import logging
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import date as _date, datetime as _dt, timedelta

from pipeline.db import PGClient, fetch_site_by_id, upsert_agent_progress, upsert_consolidated_report
from pipeline.state import CPIAState


class NoDataError(Exception):
    """해당 (site_id, report_date) 의 parser_* row 0건."""


@dataclass
class SheetData:
    output_manpower: list[dict]  # 시트1
    occupation_manpower: list[dict]  # 시트2
    equipment: list[dict]  # 시트3
    quantity: list[dict]  # 시트4
    company_wa: dict = field(default_factory=dict)  # 시트1 Zone 용 company→최빈 wa 맵
    company_trade: dict = field(default_factory=dict)  # 시트1 공종 폴백용 company→trade 맵


def _company_trade_map(quantity: list[dict]) -> dict:
    """company → 대표 trade(최빈, 동률 시 사전순 — spec §5.2 D2).
    quantity dict 는 parser_activities.* 라 company·trade 키 보유. 둘 중 하나 없으면 무시."""
    from collections import Counter

    by_co: dict[str, Counter] = {}
    for a in quantity:
        co = a.get("company")
        tr = a.get("trade")
        if co and tr:
            by_co.setdefault(co, Counter())[tr] += 1
    # 최빈(count desc), 동률 시 사전순(trade asc) — most_common 은 삽입순서라 비결정. 결정론으로 고정.
    return {co: sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] for co, cnt in by_co.items()}


def _coerce(row) -> dict:
    """asyncpg jsonb codec 미등록 시 str 로 떨어지는 케이스 흡수."""
    v = row["row"]
    return json.loads(v) if isinstance(v, str) else v


def _reconstruct_output_manpower(
    agg_rows: list[dict],
    company_wa: dict,
    prev_map: dict | None = None,
    next_map: dict | None = None,
) -> list[dict]:
    """시드일(빈 bp_summaries) 시트1 재구성 — mapper per-company 집계 → _fill_output_manpower 호환 dict.
    시드는 전일/명일 작업텍스트·교대 내역 원천이 없어, 투입인원 총합만 today_incr.total 한 칸에 넣는다.
    prev_map / next_map: 인접일 업체별 작업텍스트 맵 (화면 route.ts 인접일 로직과 동일).
    """
    prev_map = prev_map or {}
    next_map = next_map or {}
    out: list[dict] = []
    for r in agg_rows:
        out.append({
            "company": r["company"],
            "bp_code": None,  # 시드 빈값 → _fill_output_manpower 가 company 폴백
            "zone": company_wa.get(r["company"]),
            "disc_abbrev": r.get("trade"),
            "scope": None,
            "work_text_today": r.get("work_today"),
            "work_text_yesterday": prev_map.get(r["company"]) or None,
            "work_text_tomorrow": next_map.get(r["company"]) or None,
            "workers_today_incr": {"total": round(r.get("workers_total") or 0)},
        })
    return out


async def _work_text_by_company(con, site_id: str, report_date: _date) -> dict:
    """특정 날짜의 업체별 '금일 작업' 텍스트 맵. bp_summaries 있으면 그 텍스트, 없으면 mapper work_content 집계.
    화면(route.ts)의 인접일 로직과 동일 — 단 exporter 는 site_id 필터(멀티사이트).
    """
    bp = await con.fetch(
        """
        SELECT jsonb_array_elements(pt.bp_summaries) AS row
        FROM parser_reports pt
        JOIN pipeline_runs pr USING (run_id)
        WHERE pr.site_id = $1 AND pt.report_date = $2
        """,
        site_id,
        report_date,
    )
    m: dict = {}
    if bp:
        for r in bp:
            s = _coerce(r)
            co = s.get("company")
            if co:
                m[co] = s.get("work_text_today") or ""
        return m
    agg = await con.fetch(
        """
        SELECT ma.company,
               string_agg(DISTINCT NULLIF(pa.work_content, ''), E'\n') AS work
        FROM mapper_activities ma
        JOIN pipeline_runs pr USING (run_id)
        LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
        WHERE pr.site_id = $1 AND ma.report_date = $2
          AND ma.trade IN ('건축', '토목')
        GROUP BY ma.company
        """,
        site_id,
        report_date,
    )
    for r in agg:
        m[r["company"]] = r["work"] or ""
    return m


async def fetch_sheet_data(
    pg: PGClient,
    site_id: str,
    report_date: _date,
) -> SheetData:
    """모든 run 의 jsonb 합집합 — Spec §7.1.

    parser_reports / parser_activities 는 site_id 컬럼 없음 → pipeline_runs JOIN.
    """
    async with pg._pool.acquire() as con:
        bp_rows = await con.fetch(
            """
            SELECT jsonb_array_elements(pt.bp_summaries) AS row
            FROM parser_reports pt
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pt.report_date = $2
            """,
            site_id,
            report_date,
        )
        job_rows = await con.fetch(
            """
            SELECT jsonb_array_elements(pt.job_allocations) AS row
            FROM parser_reports pt
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pt.report_date = $2
            """,
            site_id,
            report_date,
        )
        eq_rows = await con.fetch(
            """
            SELECT jsonb_array_elements(pt.equipment_allocations) AS row
            FROM parser_reports pt
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pt.report_date = $2
            """,
            site_id,
            report_date,
        )
        act_rows = await con.fetch(
            """
            SELECT pa.*, ma.wa AS mapper_wa, ma.l7_5_activity AS mapper_l75
            FROM parser_activities pa
            JOIN pipeline_runs pr USING (run_id)
            LEFT JOIN mapper_activities ma USING (run_id, idx)
            WHERE pr.site_id = $1 AND pa.report_date = $2
            ORDER BY pa.run_id, pa.idx
            """,
            site_id,
            report_date,
        )
        wa_rows = await con.fetch(
            """
            SELECT ma.company, ma.wa
            FROM mapper_activities ma
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND ma.report_date = $2 AND COALESCE(ma.wa, '') <> ''
            """,
            site_id,
            report_date,
        )
        out_agg_rows = []
        if not bp_rows:
            out_agg_rows = await con.fetch(
                """
                SELECT ma.company,
                       MAX(ma.trade) AS trade,
                       SUM(COALESCE(ma.assigned_workers, 0))::float AS workers_total,
                       string_agg(DISTINCT NULLIF(pa.work_content, ''), E'\n') AS work_today
                FROM mapper_activities ma
                JOIN pipeline_runs pr USING (run_id)
                LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
                WHERE pr.site_id = $1 AND ma.report_date = $2
                  AND ma.trade IN ('건축', '토목')
                GROUP BY ma.company
                ORDER BY ma.company
                """,
                site_id,
                report_date,
            )

        prev_map = await _work_text_by_company(con, site_id, report_date - timedelta(days=1))
        next_map = await _work_text_by_company(con, site_id, report_date + timedelta(days=1))

    if not (bp_rows or job_rows or eq_rows or act_rows):
        raise NoDataError(f"해당 ({site_id}, {report_date.isoformat()}) 데이터 없음")

    from collections import Counter

    _by_co: dict[str, Counter] = {}
    for _r in wa_rows:
        _by_co.setdefault(_r["company"], Counter())[_r["wa"]] += 1
    company_wa = {
        co: max(cnt.items(), key=lambda kv: (kv[1], kv[0] == "FAB", kv[0]))[0]
        for co, cnt in _by_co.items()
    }

    if bp_rows:
        output_manpower = []
        for _r in bp_rows:
            _d = _coerce(_r)
            _co = _d.get("company")
            _d["work_text_yesterday"] = prev_map.get(_co) or None
            _d["work_text_tomorrow"] = next_map.get(_co) or None
            output_manpower.append(_d)
    else:
        output_manpower = _reconstruct_output_manpower(
            [dict(r) for r in out_agg_rows], company_wa, prev_map, next_map
        )

    return SheetData(
        output_manpower=output_manpower,
        occupation_manpower=[_coerce(r) for r in job_rows],
        equipment=[_coerce(r) for r in eq_rows],
        quantity=[dict(r) for r in act_rows],
        company_wa=company_wa,
        company_trade=_company_trade_map([dict(r) for r in act_rows]),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Render — Spec §7.2
# ──────────────────────────────────────────────────────────────────────────────

from io import BytesIO  # noqa: E402
from pathlib import Path  # noqa: E402

from openpyxl import load_workbook  # noqa: E402
from openpyxl.cell.cell import MergedCell  # noqa: E402
from openpyxl.styles import Alignment, Border, Side  # noqa: E402,F401
from openpyxl.utils import get_column_letter  # noqa: E402,F401

TEMPLATE_PATH = Path(__file__).parent / "exporter_templates" / "consolidated_template.xlsx"
DATA_START_ROW = 5

_THIN = Side(style="thin")
_HAIR = Side(style="hair")

# 시트명 → (데이터 c0, c1, 그룹키 컬럼(=Zone~업체명), SheetData 리스트 속성)
_GROUP_SHEETS = [
    ("1.출력인원 현황", 2, 37, (3, 4, 5), "output_manpower"),
    ("2.직종별 인원현황", 2, 25, (2, 3), "occupation_manpower"),
    ("3.장비현황", 2, 25, (2, 3), "equipment"),
    ("4.물량", 2, 17, (3, 4, 5, 6), "quantity"),
]
_SHEET1_TITLE = "1.작업사항"


def _unhide_and_clean(ws, n: int) -> None:
    """autofilter 제거 + 데이터·헤더 영역 row/col hidden·outline 해제 + freeze 정상화(A5).
    행 1..(DATA_START_ROW+n+3) 처리 (헤더 4행 + 데이터 n행 + 여유 4행) — 그 아래 빈 행 잔존 hidden 은 출력 무관."""
    ws.auto_filter.ref = None
    for r in range(1, DATA_START_ROW + n + 4):
        rd = ws.row_dimensions[r]
        rd.hidden = False
        rd.outlineLevel = 0
    for key in list(ws.column_dimensions):
        cd = ws.column_dimensions[key]
        cd.hidden = False
        cd.outlineLevel = 0
    try:
        ws.sheet_view.showOutlineSymbols = False
    except AttributeError:
        pass
    ws.freeze_panes = "A5"


def _dedup_and_border(ws, n: int, c0: int, c1: int, key_cols: tuple) -> None:
    """직전 데이터 행과 그룹키(Zone~업체명) 전부 같으면 그 키 컬럼 비움(dedup).
    그룹 경계 top=thin, 같은 그룹 내부 top=hair, 모든 행 bottom=hair, 좌우=thin(옵션1)."""
    prev = None
    for i in range(n):
        r = DATA_START_ROW + i
        key = tuple(ws.cell(r, c).value for c in key_cols)
        is_new = prev is None or key != prev
        if not is_new:
            for c in key_cols:
                cell = ws.cell(r, c)
                if not isinstance(cell, MergedCell):
                    cell.value = None
        top = _THIN if is_new else _HAIR
        for c in range(c0, c1 + 1):
            cell = ws.cell(r, c)
            if isinstance(cell, MergedCell):
                continue
            cell.border = Border(top=top, bottom=_HAIR, left=_THIN, right=_THIN)
        prev = key


def _unmerge_data_region(wb, sheet_data: SheetData) -> None:
    """채움 전: 각 시트 데이터구역(r5..r5+n-1)에서 시작하는 템플릿 stray 병합 해제(헤더 병합 보존).
    시트2 B87:F87 등이 _safe_set 스킵을 유발해 데이터 유실/dedup 오판 → 채움 전 해제로 근본 차단."""
    counts = {
        "1.출력인원 현황": len(sheet_data.output_manpower),
        "2.직종별 인원현황": len(sheet_data.occupation_manpower),
        "3.장비현황": len(sheet_data.equipment),
        "4.물량": len(sheet_data.quantity),
    }
    for title, n in counts.items():
        if n <= 0:
            continue
        ws = wb[title]
        last = DATA_START_ROW + n - 1
        for rng in list(ws.merged_cells.ranges):  # list() 스냅샷 — unmerge 가 ranges 를 변형
            if DATA_START_ROW <= rng.min_row <= last:
                ws.unmerge_cells(str(rng))


def _polish_sheet1(ws, n: int) -> None:
    """시트1 작업사항(col7·8·9): ' | '→줄바꿈 + wrap + 행높이(줄수 기반).
    PJT(col2)~BP사(col5): 세로 위 맞춤(템플릿 기본 아래맞춤 교정, horizontal 보존)."""
    for i in range(n):
        r = DATA_START_ROW + i
        for c in (2, 3, 4, 5):
            cell = ws.cell(r, c)
            if isinstance(cell, MergedCell):
                continue
            cur = cell.alignment
            cell.alignment = Alignment(horizontal=cur.horizontal, vertical="top", wrap_text=cur.wrap_text)
        for c in (7, 8, 9):
            cell = ws.cell(r, c)
            if isinstance(cell.value, str) and " | " in cell.value:
                cell.value = cell.value.replace(" | ", "\n")
            cell.alignment = Alignment(wrap_text=True, vertical="top", horizontal="left")
        maxlines = max([str(ws.cell(r, c).value or "").count("\n") + 1 for c in (7, 8, 9)] + [1])
        ws.row_dimensions[r].height = max(15, min(maxlines, 12) * 14)


def _finalize_layout(wb, sheet_data: SheetData) -> None:
    """render_xlsx 후처리: 숨김해제 + dedup + 그룹테두리(옵션1) + 시트1 '작업사항' 재정의.
    회색 없음 — capture 미이식, 템플릿 기본(흰색) 유지."""
    counts = {
        "output_manpower": len(sheet_data.output_manpower),
        "occupation_manpower": len(sheet_data.occupation_manpower),
        "equipment": len(sheet_data.equipment),
        "quantity": len(sheet_data.quantity),
    }
    for title, c0, c1, key_cols, attr in _GROUP_SHEETS:
        ws = wb[title]
        n = counts[attr]
        _unhide_and_clean(ws, n)
        _dedup_and_border(ws, n, c0, c1, key_cols)
    # 시트1 재정의 (rename 전 이름으로 접근)
    ws1 = wb["1.출력인원 현황"]
    _polish_sheet1(ws1, counts["output_manpower"])
    for c in range(10, 38):
        ws1.column_dimensions[get_column_letter(c)].hidden = True
    ws1.title = _SHEET1_TITLE


def _safe_set(ws, r: int, c: int, value) -> None:
    """MergedCell-safe 셀 쓰기.

    openpyxl 은 병합 범위의 anchor(좌상단) 외 멤버 셀을 MergedCell 읽기전용 객체로
    반환한다. 해당 셀에 직접 value 를 쓰면 AttributeError 가 발생하므로, 대상 셀이
    MergedCell 이면 병합 범위의 anchor(min_row, min_col) 에 대신 쓴다.
    anchor 가 아닌 일반 셀은 그대로 쓴다.
    """
    cell = ws.cell(r, c)
    if isinstance(cell, MergedCell):
        for rng in ws.merged_cells.ranges:
            if rng.min_row <= r <= rng.max_row and rng.min_col <= c <= rng.max_col:
                ws.cell(rng.min_row, rng.min_col).value = value
                return
        # 병합 범위를 찾지 못한 경우(방어): 그냥 skip
        return
    cell.value = value

# COL_* 는 docs/sample/통합작업일보_M15X*.xlsx r3+r4+r5 헤더를 openpyxl 로 덤프해
# 직접 추출한 1-indexed 컬럼 번호. placeholder 아님.

# 시트1 헤더 (r3+r4):
#   r3: 2=구분, 3=Zone, 4=공종, 5=BP사, 6=Scope, 7=주요작업, 10=전일incr,
#       17=전일cum, 24=금일incr, 31=금일cum
#   r4: 2=PJT, 4=Dis, 5=협력업체, 7=전일작업, 8=금일작업, 9=명일작업,
#       10-15=조출/주간/연장/야간/철야/Total (incr 블록 시작)
# col 16/23/30/37 은 r4 라벨 없으나 r5 에 누계값 (예: 230) 박힘 → 블록 6셀 + final.
COL_OUTPUT_MANPOWER = {
    "project": 2,
    "zone": 3,
    "trade": 4,
    "bp_code": 5,  # col 5 가 r3='BP사', r4='협력업체' 동일 칸 (단일 컬럼 dual-meaning)
    "scope": 6,
    "work_y": 7,
    "work_t": 8,
    "work_n": 9,
    "yest_incr": 10,
    "yest_cum": 17,
    "today_incr": 24,
    "today_cum": 31,
}

# 시트2 헤더:
#   r4: 2=공종, 3=BP사, 6=직종, 7=전일누계, 13=금일투입, 19=금일누계
#   r5: 2=Dis, 3=협력업체, 4=관리자/근로자, 5=기능공, 6=[기능공],
#       7-12 / 13-18 / 19-24 timeshift 블록, 25=최종
COL_OCCUPATION = {
    "trade": 2,
    "bp_code": 3,
    "manager_code": 4,
    "worker_code": 5,
    "job_type": 6,
    "yest_cum": 7,
    "today_incr": 13,
    "today_cum": 19,
}

# 시트3 헤더:
#   r4: 2=공종, 3=BP사, 4=장비명(merged 4-6), 7=전일투입누계, 13=금일투입, 19=금일투입누계
#   r5: 2=Dis, 3=협력업체, 4=대분류, 5=중분류, 6=규격, 7-12/13-18/19-24 블록, 25=최종
COL_EQUIPMENT = {
    "trade": 2,
    "bp_code": 3,
    "eq_big": 4,
    "eq_mid": 5,
    "eq_spec": 6,
    "yest_cum": 7,
    "today_incr": 13,
    "today_cum": 19,
}

# 시트4 헤더:
#   r3: 2=구분, 3=Zone, 4=공종, 5=BP사, 6=업체명, 7=Scope, 8=대표물량_작업내용,
#       9=단위, 10=총물량, 11=전일누적, 12=금일실적, 13=금일누적, 15=잔여, 17=비고
#   r4: 14=F%, 16=G%
COL_QUANTITY = {
    "project": 2,
    "zone": 3,
    "trade": 4,
    "bp_code": 5,
    "company": 6,
    "scope": 7,
    "rep_work": 8,
    "unit": 9,
    "total_a": 10,
    "prev_cum_b": 11,
    "today_c": 12,
    "today_cum_d": 13,
    "f_pct": 14,
    "remain_e": 15,
    "g_pct": 16,
    "note": 17,
}


_WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]


def _korean_weekday(d: _date) -> str:
    return _WEEKDAYS_KO[d.weekday()]


def _fill_timeshift(ws, row: int, col_start: int, ts: dict | None) -> None:
    """6 연속 cell 채우기: morning/daytime/overtime/night/all_night/total."""
    if not ts:
        return
    for i, key in enumerate(["morning", "daytime", "overtime", "night", "all_night", "total"]):
        _safe_set(ws, row, col_start + i, ts.get(key, 0))


def _fill_output_manpower(
    ws, rows: list[dict], report_date: _date, *,
    company_wa: dict | None = None, company_trade: dict | None = None, project: str | None = None,
) -> None:
    C = COL_OUTPUT_MANPOWER
    company_wa = company_wa or {}
    company_trade = company_trade or {}
    for i, row in enumerate(rows):
        r = DATA_START_ROW + i
        if i == 0 and project:
            _safe_set(ws, r, C["project"], project)  # 구분(PJT) — 첫 행 1회
        _safe_set(ws, r, C["zone"], company_wa.get(row.get("company")) or row.get("zone"))
        _safe_set(ws, r, C["trade"], row.get("disc_abbrev") or company_trade.get(row.get("company")))
        # col 5 는 bp_code 와 company 가 동일 칸 — company 우선, BP사 컬럼=업체명 (spec D5).
        # 시드는 company 만, 9/25 실업로드는 둘 다 → 둘 다 company 표기. 헤더 r3='BP사' / r4='협력업체' 동일 칸.
        _safe_set(ws, r, C["bp_code"], row.get("company") or row.get("bp_code"))
        _safe_set(ws, r, C["scope"], row.get("scope"))
        _safe_set(ws, r, C["work_y"], row.get("work_text_yesterday"))
        _safe_set(ws, r, C["work_t"], row.get("work_text_today"))
        _safe_set(ws, r, C["work_n"], row.get("work_text_tomorrow"))
        _fill_timeshift(ws, r, C["yest_incr"], row.get("workers_yesterday_incr"))
        _fill_timeshift(ws, r, C["yest_cum"], row.get("workers_yesterday_cum"))
        _fill_timeshift(ws, r, C["today_incr"], row.get("workers_today_incr"))
        _fill_timeshift(ws, r, C["today_cum"], row.get("workers_today_cum"))


def _fill_occupation(ws, rows: list[dict], report_date: _date) -> None:
    C = COL_OCCUPATION
    for i, row in enumerate(rows):
        r = DATA_START_ROW + i
        _safe_set(ws, r, C["trade"], row.get("disc_abbrev"))
        _safe_set(ws, r, C["bp_code"], row.get("company") or row.get("bp_code"))
        _safe_set(ws, r, C["manager_code"], row.get("manager_code"))
        _safe_set(ws, r, C["worker_code"], row.get("worker_code"))
        _safe_set(ws, r, C["job_type"], row.get("job_type"))
        # 시트2 의 yest_cum / today_incr / today_cum 은 6 timeshift 블록 + 누계 cell.
        # parser 단계에서 timeshift dict 가 없으면 scalar workers_cum_t 만 'total' 자리에 박음.
        cum_t = row.get("workers_cum_t")
        if isinstance(row.get("workers_yesterday_cum"), dict):
            _fill_timeshift(ws, r, C["yest_cum"], row["workers_yesterday_cum"])
        elif cum_t is not None:
            _safe_set(ws, r, C["yest_cum"] + 5, cum_t)  # total 자리 (블록 시작+5)
        if isinstance(row.get("workers_today_incr"), dict):
            _fill_timeshift(ws, r, C["today_incr"], row["workers_today_incr"])
        if isinstance(row.get("workers_today_cum"), dict):
            _fill_timeshift(ws, r, C["today_cum"], row["workers_today_cum"])


def _fill_equipment(ws, rows: list[dict], report_date: _date) -> None:
    C = COL_EQUIPMENT
    for i, row in enumerate(rows):
        r = DATA_START_ROW + i
        _safe_set(ws, r, C["trade"], row.get("disc_abbrev"))
        _safe_set(ws, r, C["bp_code"], row.get("company") or row.get("bp_code"))
        _safe_set(ws, r, C["eq_big"], row.get("equipment_big"))
        _safe_set(ws, r, C["eq_mid"], row.get("equipment_mid"))
        _safe_set(ws, r, C["eq_spec"], row.get("equipment_spec"))
        cnt_cum = row.get("count_cum_t")
        if isinstance(row.get("count_yesterday_cum"), dict):
            _fill_timeshift(ws, r, C["yest_cum"], row["count_yesterday_cum"])
        elif cnt_cum is not None:
            _safe_set(ws, r, C["yest_cum"] + 5, cnt_cum)
        if isinstance(row.get("count_today_incr"), dict):
            _fill_timeshift(ws, r, C["today_incr"], row["count_today_incr"])
        if isinstance(row.get("count_today_cum"), dict):
            _fill_timeshift(ws, r, C["today_cum"], row["count_today_cum"])


def _fill_quantity(ws, rows: list[dict], report_date: _date, *, project: str | None = None) -> None:
    C = COL_QUANTITY
    for i, row in enumerate(rows):
        r = DATA_START_ROW + i
        if i == 0 and project:
            _safe_set(ws, r, C["project"], project)  # 구분(PJT) — 첫 행 1회
        _safe_set(ws, r, C["zone"], (row.get("mapper_wa") or row.get("zone")))
        _safe_set(ws, r, C["trade"], row.get("trade") or row.get("disc_abbrev"))
        _safe_set(ws, r, C["bp_code"], row.get("bp_code"))
        _safe_set(ws, r, C["company"], row.get("company"))
        _safe_set(ws, r, C["scope"], row.get("scope"))
        _safe_set(ws, r, C["rep_work"], row.get("mapper_l75") or row.get("work_content"))
        _safe_set(ws, r, C["unit"], row.get("unit"))
        _safe_set(ws, r, C["total_a"], row.get("plan_total_qty"))
        _safe_set(ws, r, C["prev_cum_b"], row.get("yesterday_cum_qty"))
        _safe_set(ws, r, C["today_c"], row.get("today_qty"))
        # D = B + C, E = A - D — 둘 다 산식 가능하면 채움 (None 안전).
        b = row.get("yesterday_cum_qty")
        c = row.get("today_qty")
        a = row.get("plan_total_qty")
        if b is not None and c is not None:
            d = b + c
            _safe_set(ws, r, C["today_cum_d"], d)
            if a:
                _safe_set(ws, r, C["f_pct"], round(d / a * 100, 2))
                _safe_set(ws, r, C["remain_e"], a - d)
                _safe_set(ws, r, C["g_pct"], round(100 - (d / a * 100), 2))
        _safe_set(ws, r, C["note"], row.get("note"))


def render_xlsx(sheet_data: SheetData, report_date: _date, project: str) -> bytes:
    """SheetData → xlsx bytes (template 복제 후 r5 부터 fill). Spec §7.2."""
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"template not found: {TEMPLATE_PATH}")
    wb = load_workbook(TEMPLATE_PATH)
    _unmerge_data_region(wb, sheet_data)   # 채움 전: 데이터구역 stray 병합 해제
    _fill_output_manpower(wb["1.출력인원 현황"], sheet_data.output_manpower, report_date,
                          company_wa=sheet_data.company_wa, company_trade=sheet_data.company_trade, project=project)
    _fill_occupation(wb["2.직종별 인원현황"], sheet_data.occupation_manpower, report_date)
    _fill_equipment(wb["3.장비현황"], sheet_data.equipment, report_date)
    _fill_quantity(wb["4.물량"], sheet_data.quantity, report_date, project=project)
    _finalize_layout(wb, sheet_data)       # 숨김해제+dedup+테두리+시트1재정의
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Graph node — Spec §6.4
# ──────────────────────────────────────────────────────────────────────────────

log = logging.getLogger("cpia.exporter_node")


async def consolidated_xlsx_node(state: CPIAState) -> dict[str, Any]:
    """graph 노드 — Atomizer 끝나면 fan-out 으로 호출 (D-3 N-1).

    1) fetch_sheet_data -> 자기 run + 이전 run 합집합 (D-12 invariant 유지)
    2) render_xlsx -> bytes (~150KB)
    3) upsert_consolidated_reports -> PG UPSERT (D-2 last write wins)
    4) state 에 meta 만 박음 (D-7 bytes 는 안 박음)

    예외 처리 (D-8 / 거동 B 대응):
      - 모든 예외 catch + log.exception + return {} — LangGraph 1.2.0 은 multi-end
        fault isolation 미지원 (issue #6170). 노드가 raise 하면 cycle 전체 실패.
        cycle 보호 위해 silent skip — D-6 EC 패턴으로 다음 cycle 자동 회복.
        NoDataError: WARN 레벨 (예상되는 cold-start). 기타: log.exception (운영 모니터링).
    """
    site_id = state["site_id"]
    report_date = _date.fromisoformat(state["date"])
    run_id = _uuid.UUID(state["run_id"])

    pg = PGClient(state["postgres_url"])
    await pg.connect()
    await upsert_agent_progress(state["postgres_url"], state["run_id"], "exporter", 0, 1)
    try:
        try:
            data = await fetch_sheet_data(pg, site_id, report_date)
        except NoDataError:
            log.warning(
                "consolidated_xlsx_node: NoData site=%s date=%s — skip UPSERT",
                site_id,
                report_date,
            )
            return {}
        try:
            site_row = await fetch_site_by_id(pg, site_id)
            project = (site_row or {}).get("name") or state.get("project") or "CPIA"
            xlsx_bytes = render_xlsx(data, report_date, project=project)
            await upsert_consolidated_report(
                pg,
                site_id=site_id,
                report_date=report_date,
                xlsx_bytes=xlsx_bytes,
                run_id=run_id,
            )
            await upsert_agent_progress(state["postgres_url"], state["run_id"], "exporter", 1, 1)
            log.info(
                "consolidated_xlsx_node: UPSERT site=%s date=%s bytes=%d run=%s",
                site_id,
                report_date,
                len(xlsx_bytes),
                run_id,
            )
        except Exception:
            log.exception(
                "consolidated_xlsx_node: render/upsert 실패 site=%s date=%s — skip + EC 회복",
                site_id,
                report_date,
            )
            return {}
    finally:
        await pg.close()

    return {
        "consolidated_xlsx_run_id": str(run_id),
        "consolidated_xlsx_generated_at": _dt.utcnow().isoformat() + "Z",
    }
