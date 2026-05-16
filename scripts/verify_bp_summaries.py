"""시트1 today_incr_total 의미 검증 — 세보엠이씨 1387 의 출처.

검증 가설:
  H1 (그 날 신규 투입): 시트1 col28 = 그 날 BP사 신규 인원
  H2 (누계):           시트1 col28 = 9/3~9/25 누계 인원

방법:
  - 9/25 작업일보의 세보엠이씨 시트1 row raw 셀 값 dump
  - col28 (today_incr) 컬럼 헤더 라벨 + 값 + col35 (today_cum) 의 비율 확인
  - 비율이 1/22~1/23 (1일/22일 누계) 정도면 H1, 1.0 이면 H2

Parser 의 cell 인덱스 (col28 / col35) 는 pipeline/agents/parser.py:_parse_sheet1_bp_summaries
의 r[28] / r[35] 와 정합. 회사명 컬럼은 plan 의 r[3] 이 아니라 실제 parser 코드 기준 r[4].
Header end = row 4, forward-fill cols = [1, 2, 3, 4].
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
xlsx = ROOT / "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"

wb = openpyxl.load_workbook(xlsx, data_only=True, read_only=True)
ws = wb["1.출력인원 현황"]
rows = list(ws.iter_rows(values_only=True))


def _ffill(records, header_end: int, fill_cols: list[int]):
    """parser.py 의 _ffill 과 동일 로직 (병합 셀 forward-fill)."""
    if not records:
        return []
    width = max(len(r) for r in records)
    last = [None] * width
    out = []
    for i, r in enumerate(records):
        rec = list(r) + [None] * (width - len(r))
        if i < header_end:
            out.append((i, rec))
            continue
        for c in fill_cols:
            if c < len(rec) and rec[c] is not None and str(rec[c]).strip() != "":
                last[c] = rec[c]
            else:
                if c < len(rec):
                    rec[c] = last[c]
        out.append((i, rec))
    return out


print("=== 시트1 헤더 R3~R4 전체 (col9~col36 라벨) ===")
for i in (2, 3):
    r = rows[i]
    pairs = [(j, r[j]) for j in range(9, 37) if j < len(r)]
    print(f"R{i + 1}: {pairs}")

print()
print("=== col28 / col35 헤더 라벨 (R1~R5) ===")
for i, r in enumerate(rows[:5]):
    c28 = r[28] if len(r) > 28 else None
    c35 = r[35] if len(r) > 35 else None
    print(f"R{i + 1}: col28={c28!r} | col35={c35!r}")

print()
print("=== 세보엠이씨 row 발견 (parser 와 동일하게 r[4]=company, ffill 후) ===")
ffilled = _ffill(rows, header_end=4, fill_cols=[1, 2, 3, 4])
hit = 0
for i, r in ffilled:
    co = r[4] if len(r) > 4 else None
    if co and isinstance(co, str) and "세보" in co:
        col28 = r[28] if len(r) > 28 else None
        col35 = r[35] if len(r) > 35 else None
        ratio = (
            col28 / col35
            if (
                isinstance(col28, (int, float))
                and isinstance(col35, (int, float))
                and col35
            )
            else None
        )
        disc = r[3] if len(r) > 3 else None
        zone = r[2] if len(r) > 2 else None
        # 추가: col23~col36 전체 셀 dump (금일 투입/금일 누계 그룹 전체)
        full = [(j, r[j]) for j in range(23, 37) if j < len(r)]
        print(
            f"R{i + 1}: zone={zone!r} | disc={disc!r} | company={co!r}\n"
            f"   col28(today_incr)={col28} | col35(today_cum)={col35} | ratio={ratio}\n"
            f"   col23~col36 전체: {full}"
        )
        hit += 1

print()
print(f"=== 세보 매칭 row 수: {hit} ===")

# 추가: 전체 BP사 row 의 col28/col35 비율 분포 (H1/H2 판정 보조용)
print()
print("=== 전체 BP사 row col28/col35 ratio 분포 (참고) ===")
ratios = []
for i, r in ffilled[4:]:  # 헤더 스킵
    co = r[4] if len(r) > 4 else None
    if not (co and isinstance(co, str) and co.strip()):
        continue
    col28 = r[28] if len(r) > 28 else None
    col35 = r[35] if len(r) > 35 else None
    if isinstance(col28, (int, float)) and isinstance(col35, (int, float)) and col35:
        ratios.append((co, col28, col35, col28 / col35))

print(f"총 row {len(ratios)} 건 (col28·col35 둘 다 숫자, col35>0)")
if ratios:
    sample = sorted(ratios, key=lambda x: -x[2])[:10]
    print("col35 (today_cum) 상위 10건:")
    for co, c28, c35, ratio in sample:
        print(f"  company={co!r} | col28={c28} | col35={c35} | ratio={ratio:.4f}")

wb.close()
