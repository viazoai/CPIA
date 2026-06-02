"""통합일보 09-25 → 회사별 건축/토목 업체파일 10개 (양식보존, 4시트 전부).

방식: UT 템플릿(.xlsm, Cover+10시트 풀포맷)을 베이스로 복사 → 시트1~4 의 데이터행만
회사별 건축/토목 실데이터(통합일보 parse 출처)로 덮어쓰기. 셀 스타일은 템플릿 데이터행을
복사해 보존. today_qty(금일실적)=0 케이스는 적절히 채움(계획 일부).

검증: 생성 후 parse_daily_report 로 4시트 재파싱 (activities/job/equip 카운트 + trade + company).

argv[1] (optional): 단일 회사 정규화명만 생성 (검증용). 없으면 10개 전부.
"""

from __future__ import annotations

import copy
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import openpyxl
from openpyxl.cell.cell import MergedCell

warnings.filterwarnings("ignore")
ROOT = Path("/Users/kyungseoplee/Project Agent/CPIA")
sys.path.insert(0, str(ROOT))
from pipeline.agents.parser import parse_daily_report  # noqa: E402

SRC = ROOT / "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
TEMPLATE = (
    ROOT / "data/input/_20250925_renamed_ut_bak/업체작업일보_M15X_PH3_㈜엔아이스틸_철골공사_20250925.xlsm"
)
OUT_DIR = ROOT / "data/demo_inputs/20250925"

# (파일표시명, trade_label, out_company, src_company)
# out_company = activity_master 이름(짧은이름 광건/태우/선보), src_company = 통합일보 normalize 결과
TARGETS = [
    ("장평건설", "토목공사", "장평건설", "장평건설"),
    ("남웅건설", "건축공사", "남웅건설", "남웅건설"),
    ("동신패널", "건축공사", "동신패널", "동신패널"),
    ("글로벌유명", "건축공사", "글로벌유명", "글로벌유명"),
    ("광건", "건축공사", "광건", "광건티엔씨"),
    ("태우", "건축공사", "태우", "태우이엔지"),
    ("선보", "건축공사", "선보", "선보건업"),
]

SHIFT_KEYS = ("morning", "daytime", "overtime", "night", "all_night", "total")


def _today_qty_fill(a: dict) -> float:
    """today_qty(금일실적)=0/None → 계획 기반 적절한 일일 진행량으로 채움.
    deterministic (work_content 해시) factor ∈ [0.015, 0.04] × 총물량. 최소 1.
    원본 today_qty 가 있으면 그대로."""
    tq = a.get("today_qty")
    if tq is not None and float(tq) > 0:
        return float(tq)
    plan = float(a.get("plan_total_qty") or 0)
    if plan <= 0:
        return 1.0
    h = sum(ord(ch) for ch in (a.get("work_content") or "x"))
    factor = 0.015 + (h % 26) / 1000.0  # 0.015 ~ 0.040
    return max(1.0, round(plan * factor, 1))


def _set(ws, r, c, v):
    cell = ws.cell(r, c)
    if isinstance(cell, MergedCell):  # 병합셀 (anchor 아님) → write 불가, skip
        return
    cell.value = v


def _copy_style_row(ws, src_r, dst_r, cmax):
    for c in range(1, cmax + 1):
        s = ws.cell(src_r, c)
        d = ws.cell(dst_r, c)
        if isinstance(d, MergedCell) or isinstance(s, MergedCell):
            continue
        if s.has_style:
            d._style = copy.copy(s._style)


def _clear_rows(ws, r_from, r_to, cmax):
    for r in range(r_from, r_to + 1):
        for c in range(1, cmax + 1):
            cell = ws.cell(r, c)
            if isinstance(cell, MergedCell):
                continue
            cell.value = None


def _fill_sheet4(ws, acts: list[dict], out_company: str):
    """업체포맷 시트4: r5=BP코드행(공종 c4 포함), r6=회사명행, 이후 활동행.
    c4=공종, c5=BP/회사, c6=Scope, c7=작업내용, c8=단위, c9=총물량, c10=전일누적,
    c11=금일실적, c12=금일누적, c13=F%, c14=잔여, c16=위치, c17=중공종, c18=소공종, c19=세공종.
    out_company 는 Task 4 에서 회사명 오버라이드에 사용 예정 (현재는 acts[0].company 유지)."""
    CMAX = 19
    DATA0 = 5
    style_row = 7  # 활동행 스타일 src (병합 없는 일반 데이터행)
    # 기존 데이터행 보존용 스타일 캡쳐 후 클리어
    _clear_rows(ws, DATA0, ws.max_row, CMAX)
    if not acts:
        return
    company = acts[0].get("company") or ""
    bp = acts[0].get("bp_code") or "PH_X-000"
    r = DATA0
    for i, a in enumerate(acts):
        _copy_style_row(ws, style_row, r, CMAX)
        _set(ws, r, 4, a.get("trade") or "")  # 공종
        # BP코드행(첫행) c5=BP코드, 둘째행 c5=회사명, 이후 빈칸
        if i == 0:
            _set(ws, r, 5, bp)
        elif i == 1:
            _set(ws, r, 5, company)
        plan = float(a.get("plan_total_qty") or 0)
        yest = float(a.get("yesterday_cum_qty") or 0)
        tq = _today_qty_fill(a)
        cum = yest + tq
        _set(ws, r, 6, a.get("scope") or "")  # Scope
        _set(ws, r, 7, a.get("work_content") or "")  # 작업내용
        _set(ws, r, 8, a.get("unit") or "")  # 단위
        _set(ws, r, 9, plan or None)  # 총물량 [A]
        _set(ws, r, 10, yest or None)  # 전일누적 [B]
        _set(ws, r, 11, tq)  # 금일실적 [C]
        _set(ws, r, 12, cum or None)  # 금일누적 [D]
        _set(ws, r, 13, round(cum / plan, 4) if plan else None)  # F%
        _set(ws, r, 14, round(plan - cum, 1) if plan else None)  # 잔여 [E]
        _set(ws, r, 15, round(1 - cum / plan, 4) if plan else None)  # G%
        _set(ws, r, 16, a.get("work_location_code") or a.get("scope") or "")  # 위치
        _set(ws, r, 17, a.get("l6_main") or a.get("trade") or "")  # 공종명/중공종
        r += 1


def _fill_sheet1(ws, summaries: list[dict], jobs: list[dict], company: str, trade: str):
    """출력인원: r5=BP코드행, r6=회사명행. c4=공종,c5=BP/회사,c7/8/9=작업텍스트,
    c24-29=금일투입 shift, c30=금일투입총, c31-36=금일누적 shift, c37=금일누적총,
    c10-15 전일투입, c17-22 전일누적. 병합셀(헤더 r3-4)은 보존.
    jobs 파라미터: Task 3 에서 직종별 rollup 로직 구현 예정 (현재 미사용)."""
    CMAX = 37
    DATA0 = 5
    style_row = 5
    # 데이터행만 클리어 (헤더 r1-4 보존)
    _clear_rows(ws, DATA0, ws.max_row, CMAX)
    if not summaries:
        # 워커 합산 row 1개라도 — bp_summaries 없으면 skip
        return
    # 회사 단위 1 그룹으로 합산 (BP행 + 회사행)
    bp = summaries[0].get("bp_code") or "PH_X-000"
    work_today = " | ".join(s.get("work_text_today") or "" for s in summaries if s.get("work_text_today"))[
        :200
    ]

    # shift 합산
    def _sum_shift(key):
        agg = {k: 0 for k in SHIFT_KEYS}
        for s in summaries:
            d = s.get(key) or {}
            for k in SHIFT_KEYS:
                agg[k] += int(d.get(k) or 0)
        return agg

    ti = _sum_shift("workers_today_incr")
    tc = _sum_shift("workers_today_cum")
    yi = _sum_shift("workers_yesterday_incr")
    yc = _sum_shift("workers_yesterday_cum")
    today_incr_total = sum(int(s.get("today_incr_total") or 0) for s in summaries) or ti["total"]
    today_cum_total = sum(int(s.get("today_cum_total") or 0) for s in summaries) or tc["total"]
    # r5: BP코드행 (공종 c4, BP c5, 작업텍스트, 워커)
    _copy_style_row(ws, style_row, DATA0, CMAX)
    _set(ws, DATA0, 4, trade)
    _set(ws, DATA0, 5, bp)
    _set(ws, DATA0, 7, work_today)
    _set(ws, DATA0, 8, work_today)
    for i, k in enumerate(SHIFT_KEYS):
        _set(ws, DATA0, 10 + i, yi[k] or None)  # 전일투입 c10-15
        _set(ws, DATA0, 17 + i, yc[k] or None)  # 전일누적 c17-22
        _set(ws, DATA0, 24 + i, ti[k] or None)  # 금일투입 c24-29
        _set(ws, DATA0, 31 + i, tc[k] or None)  # 금일누적 c31-36
    _set(ws, DATA0, 30, today_incr_total or None)  # 금일투입 총
    _set(ws, DATA0, 37, today_cum_total or None)  # 금일누적 총
    # r6: 회사명행
    _copy_style_row(ws, 6, DATA0 + 1, CMAX)
    _set(ws, DATA0 + 1, 5, company)


def _fill_sheet2(ws, jobs: list[dict], company: str, trade: str):
    """직종별: r6=BP코드행(Mm01), r7=회사명행, 이후 직종행. c2=공종,c3=BP/회사,
    c4=관리/근로코드,c6=직종,c7-12 전일누계,c13-18 금일투입,c19-24 금일누계,c25='O'."""
    CMAX = 25
    DATA0 = 6
    style_row = 8
    _clear_rows(ws, DATA0, ws.max_row, CMAX)
    if not jobs:
        return
    bp = jobs[0].get("bp_code") or "PH_X-000"
    # 파서 group-start 게이트: c4=='Mm01' + c3=BP(is_bp_code) + c2(공종) + c25=='O'.
    # → r6 에 Mm01 앵커행(관리자=BP소장, _is_admin_job 으로 필터됨) 을 둔다.
    # 회사명: 파서가 start+1..+5 의 c3 한글값에서 추출 → r7 c3=company.
    _copy_style_row(ws, style_row, DATA0, CMAX)
    _set(ws, DATA0, 2, trade)  # 공종
    _set(ws, DATA0, 3, bp)  # BP 코드
    _set(ws, DATA0, 4, "Mm01")  # group 앵커 (관리자 → 파싱 시 제외)
    _set(ws, DATA0, 5, "sk01")
    _set(ws, DATA0, 6, "BP소장")  # admin job → _is_admin_job 필터
    _set(ws, DATA0, 25, "O")
    # 실 직종행: r7 부터. r7 c3=회사명.
    r = DATA0 + 1
    for i, j in enumerate(jobs):
        _copy_style_row(ws, style_row, r, CMAX)
        if i == 0:
            _set(ws, r, 3, company)  # 회사명 (파서 company 추출)
        code = j.get("manager_code") or j.get("worker_code") or f"Wk{i:02d}"
        # Mm 으로 시작하면 관리자로 오인되므로 기능공은 Wk 강제
        if code.startswith("Mm"):
            code = f"Wk{i:02d}"
        _set(ws, r, 4, code)
        _set(ws, r, 6, j.get("job_type") or f"기능공{i:02d}")
        yc = j.get("workers_yesterday_cum") or {}
        ti = j.get("workers_today_incr") or {}
        tc = j.get("workers_today_cum") or {}
        for k_i, k in enumerate(SHIFT_KEYS):
            _set(ws, r, 7 + k_i, int(yc.get(k) or 0) or None)  # 전일누계 c7-12
            _set(ws, r, 13 + k_i, int(ti.get(k) or 0) or None)  # 금일투입 c13-18
            _set(ws, r, 19 + k_i, int(tc.get(k) or 0) or None)  # 금일누계 c19-24
        _set(ws, r, 25, "O")  # final_flag
        r += 1


def _write_equip_row(ws, r: int, e: dict):
    """장비행 1줄: col4=big col5=mid col6=spec + 6교대 + col25='O'."""
    _set(ws, r, 4, e.get("equipment_big") or "")
    _set(ws, r, 5, e.get("equipment_mid") or "")
    _set(ws, r, 6, e.get("equipment_spec"))
    yc = e.get("count_yesterday_cum") or {}
    ti = e.get("count_today_incr") or {}
    tc = e.get("count_today_cum") or {}
    for i, k in enumerate(SHIFT_KEYS):
        _set(ws, r, 7 + i, int(yc.get(k) or 0) or None)  # 전일누계 c7-12
        _set(ws, r, 13 + i, int(ti.get(k) or 0) or None)  # 금일투입 c13-18
        _set(ws, r, 19 + i, int(tc.get(k) or 0) or None)  # 금일누계 c19-24
    _set(ws, r, 25, "O")


def _fill_sheet3(ws, equips: list[dict], company: str, trade: str):
    """장비: equipment_allocations 로 채움. parser sheet3 게이트 미러
    (parser.py:512-582): 그룹시작행 col2=공종+col3=BP+col4=장비대분류,
    회사명행 col3=company, 장비행 col4=big/col5=mid/col6=spec,
    6교대 col7-12=전일누계/col13-18=금일투입/col19-24=금일누계, col25='O'."""
    CMAX = 25
    DATA0 = 6
    style_row = 6
    _clear_rows(ws, DATA0, ws.max_row, CMAX)
    if not equips:
        return
    bp = equips[0].get("bp_code") or "PH_X-000"
    # r6: 그룹시작행 (공종 col2 + BP col3 + 첫 장비 col4) — 첫 장비를 함께 기록
    _copy_style_row(ws, style_row, DATA0, CMAX)
    e0 = equips[0]
    _set(ws, DATA0, 2, trade)
    _set(ws, DATA0, 3, bp)
    _write_equip_row(ws, DATA0, e0)
    # r7: 회사명행 (col3=company). 첫 장비는 r6 에 기록됐으므로 r7 은 회사명만
    _copy_style_row(ws, 7, DATA0 + 1, CMAX)
    _set(ws, DATA0 + 1, 3, company)
    # 둘째 장비부터 r8...
    r = DATA0 + 2
    for e in equips[1:]:
        _copy_style_row(ws, style_row, r, CMAX)
        _write_equip_row(ws, r, e)
        r += 1


def build_one(out_company, src_company, raw_name, trade_label, by_co_act, by_co_job, by_co_sum, by_co_eq):
    wb = openpyxl.load_workbook(str(TEMPLATE), keep_vba=True)
    acts = by_co_act.get(src_company, [])
    jobs = by_co_job.get(src_company, [])
    sums = by_co_sum.get(src_company, [])
    eqs = by_co_eq.get(src_company, [])
    trade = acts[0].get("trade") if acts else "건축"
    _fill_sheet4(wb["4.물량"], acts, out_company)
    _fill_sheet1(wb["1.출력인원 현황"], sums, jobs, out_company, trade)
    _fill_sheet2(wb["2.직종별 인원현황"], jobs, out_company, trade)
    _fill_sheet3(wb["3.장비현황"], eqs, out_company, trade)
    fname = f"업체작업일보_M15X_PH3_{raw_name}_{trade_label}_20250925.xlsm"
    out = OUT_DIR / fname
    wb.save(str(out))
    return out, len(acts), len(jobs), len(sums), len(eqs)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    rep = parse_daily_report(str(SRC))
    by_co_act = defaultdict(list)
    for a in rep["activities"]:
        if a.get("trade") in ("건축", "토목"):
            by_co_act[a.get("company") or ""].append(a)
    by_co_job = defaultdict(list)
    for j in rep["job_allocations"]:
        by_co_job[j.get("company") or ""].append(j)
    by_co_sum = defaultdict(list)
    for s in rep["bp_summaries"]:
        by_co_sum[s.get("company") or ""].append(s)
    by_co_eq = defaultdict(list)
    for e in rep.get("equipment_allocations", []):
        by_co_eq[e.get("company") or ""].append(e)

    src_companies = [t[3] for t in TARGETS]
    for src in src_companies:
        assert by_co_act.get(src), f"src '{src}' act 없음 (by_co_act)"
        assert by_co_job.get(src), f"src '{src}' job 없음 (by_co_job)"
        assert by_co_eq.get(src), f"src '{src}' eq 없음 (by_co_eq)"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = [t for t in TARGETS if (only is None or t[2] == only)]
    if only is None:
        for old in OUT_DIR.glob("*.xls*"):
            old.unlink()
    print("=== 생성 + 재파싱 검증 ===")
    for raw_name, trade_label, out_company, src_company in targets:
        out, na, nj, ns, ne = build_one(
            out_company,
            src_company,
            raw_name,
            trade_label,
            by_co_act,
            by_co_job,
            by_co_sum,
            by_co_eq,
        )
        rp = parse_daily_report(str(out))
        pa = rp["activities"]
        pj = rp["job_allocations"]
        trades = sorted({x.get("trade") for x in pa})
        cos = sorted({x.get("company") for x in pa})
        jw = sum((j.get("workers_today_cum") or {}).get("total", 0) for j in pj)
        print(f"  {out.name}")
        print(f"     src: act={na} job={nj} sum={ns} eq={ne}")
        print(
            f"     parsed: act={len(pa)} trades={trades} companies={cos} | job={len(pj)} 금일누계워커합={jw}"
        )


if __name__ == "__main__":
    main()
