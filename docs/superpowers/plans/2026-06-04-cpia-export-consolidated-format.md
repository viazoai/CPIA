# CPIA 통합작업일보 Export 양식 정합 — 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `exporter.render_xlsx` 가 통합작업일보 xlsx 를 UI 와 정합하게 — 구분(PJT)·시트1 공종 채움 + 업체 그룹 dedup·테두리 + 시트2·3 숨김 완전해제·흰색 + 시트1 "작업사항" 재정의 — 출력하도록 만든다.

**Architecture:** `exporter.py` 단일 파일. `_fill_output_manpower`/`_fill_quantity` 에 `project`·`company_trade` 전달(구분·공종 채움), `fetch_sheet_data` 가 `SheetData.company_trade` 채움, 신규 `_finalize_layout(wb, sheet_data)` 가 `render_xlsx` 끝에서 숨김해제·dedup·그룹테두리·시트1재정의를 일괄 적용. 회색은 PoC 아티팩트였으므로 capture 로직은 이식하지 않는다(템플릿 기본=흰색).

**Tech Stack:** Python 3.9, openpyxl 3.1.5(hair/thin/Border/freeze_panes/row·column_dimensions/get_column_letter 전부 지원 — 실측 확인), pytest(asyncio_mode=auto), PostgreSQL.

**Spec:** `docs/superpowers/specs/2026-06-04-cpia-export-consolidated-format-design.md`
**브랜치:** `feature/review-l75-hil`

---

## 확정 사실 (정밀조사 결과 — 흔들리지 말 것)

- `render_xlsx(sheet_data: SheetData, report_date: _date, project: str) -> bytes` (exporter.py:440). `project` 는 현재 미사용. 비-테스트 호출처(exporter_routes.py:43, consolidated_xlsx_node exporter.py:495, scripts/seed_dummy_year.py:701) 모두 `project` 를 site.name 폴백 'CPIA' 로 전달. 테스트의 lambda 대체(test_exporter_progress/node/agent_progress_e2e)는 render_xlsx 시그니처 불변이라 무영향.
- `SheetData` @dataclass (exporter.py:22-28): 필수 4 + `company_wa: dict = field(default_factory=dict)`. **새 필드 `company_trade` 도 `field(default_factory=dict)` 필수** (4 호출처 호환).
- `SheetData.quantity` 각 dict 는 `parser_activities.*` + `mapper_wa`/`mapper_l75` → `company`·`trade` 키 존재(parser_activities 컬럼, 2026-05-18_parser_mapper_outputs.sql:30-31). 9/25 7개사 전부 단일 trade.
- 전 시트 데이터 시작행 = `DATA_START_ROW=5` (exporter.py:237). 템플릿 헤더는 r4까지, r5 빈칸 — **shift 보정 불필요**(PoC 의 shift_for_header 는 이식 안 함).
- 시트별 그룹키(=Zone~업체명): 시트1 `(3,4,5)`, 시트2·3 `(2,3)`, 시트4 `(3,4,5,6)`. (`COL_OUTPUT_MANPOWER`/`COL_QUANTITY`/`COL_OCCUPATION`/`COL_EQUIPMENT` exporter.py:267-332 와 일치)
- 테두리 옵션1 확정: 업체 경계 top=`thin`, 내부 top=`hair`, 모든 행 bottom=`hair`, 좌우=`thin`.
- pytest 실행: `cd pipeline && .venv/bin/python -m pytest tests/test_exporter*.py -v` (pyproject.toml asyncio_mode=auto, pythonpath=[.]). import 는 `from pipeline.agents.exporter import ...`.
- **회귀 2건**: ① `test_exporter_render.py` 의 시트명 참조 3곳(시트1 rename) ② `_fill_*` 새 kwarg 기본값 None(test_exporter_wa_source.py 가 직접 호출).

### 실행 중 결정 (2026-06-04, Task 4 리뷰에서 발견)

**시트2 데이터구역 stray 병합 → 채움 전 unmerge (사용자 승인).** 템플릿 `2.직종별 인원현황` 데이터구역에 stray 수평병합 4개(`B87:F87`·`B88:F88`·`B171:F171`·`B172:F172`, col 2~6)가 박혀 있음(실측). 실 9/25 occupation=88행(r5~r92)이라 `r87`·`r88`이 충돌 → `_safe_set` 이 MergedCell 을 스킵해 채움 단계에서 col C~F 가 유실되고(렌더 실측: `r87=['항타공',None,None,None,None]`), `_dedup_and_border` 도 키를 오판한다. 기존 결함이나 spec §7.4 "88행 전부 보임" 과 충돌. 시트1 데이터구역 병합(388개)은 전부 우측 인원구역(col16~37, hidden 대상)이고 9/25 는 7행이라 무충돌. 시트3·4 데이터구역 병합 0.
→ **`render_xlsx` 에 `_unmerge_data_region(wb, sheet_data)` 단계를 `_fill_*` 호출 전에 추가**(Task 5). 각 시트 실 데이터행(`r5..r5+n-1`)과 교차하는 템플릿 병합만 해제 → 채움 정상화 + dedup 키 정확. 채움 후 `_finalize_layout` 에서 해제하면 이미 유실된 데이터 복구 불가하므로 반드시 채움 전.

## File Structure

- **Modify** `pipeline/agents/exporter.py`:
  - import 추가(상단 openpyxl 블록): `from openpyxl.styles import Alignment, Border, Side` / `from openpyxl.utils import get_column_letter`
  - `SheetData`: `company_trade` 필드 추가
  - 신규 모듈 상수: `_THIN`/`_HAIR`/`_GROUP_SHEETS`/`_SHEET1_TITLE`
  - 신규 함수: `_company_trade_map`, `_unhide_and_clean`, `_dedup_and_border`, `_polish_sheet1`, `_finalize_layout`
  - 수정 함수: `_fill_output_manpower`(공종 폴백+구분), `_fill_quantity`(구분), `fetch_sheet_data`(company_trade 채움), `render_xlsx`(_fill_* 인자 전달 + _finalize_layout 호출)
- **Create** `pipeline/tests/test_exporter_format.py`: 양식 정합 단위 테스트(LLM 0, PG 0 — fake SheetData / render_xlsx → openpyxl 재load)
- **Modify** `pipeline/tests/test_exporter_render.py`: 시트1 rename 반영(시트명 3곳)
- **Create(임시)** `/tmp/cpia_export_live_verify.py`: 실 DB 9/25 라이브 검증(Task 6, throwaway)

---

### Task 1: `company_trade` 맵 + `SheetData` 필드

**Files:**
- Modify: `pipeline/agents/exporter.py` (SheetData dataclass exporter.py:22-28, fetch_sheet_data return exporter.py:217-223, 신규 `_company_trade_map`)
- Test: `pipeline/tests/test_exporter_format.py` (Create)

- [ ] **Step 1: 실패 테스트 작성** — `pipeline/tests/test_exporter_format.py` 생성

```python
"""통합작업일보 export 양식 정합 단위 — fake SheetData / render_xlsx → openpyxl 재load. LLM 0, PG 0."""
from __future__ import annotations

from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook

from pipeline.agents.exporter import (
    SheetData,
    _company_trade_map,
    render_xlsx,
)


def test_company_trade_map_most_common():
    rows = [
        {"company": "광건", "trade": "건축"},
        {"company": "광건", "trade": "건축"},
        {"company": "장평건설", "trade": "토목"},
        {"company": "장평건설", "trade": "토목"},
        {"company": "장평건설", "trade": "건축"},  # 토목 2 > 건축 1
        {"company": None, "trade": "건축"},          # company 없으면 무시
        {"company": "선보", "trade": None},           # trade 없으면 무시
    ]
    m = _company_trade_map(rows)
    assert m["광건"] == "건축"
    assert m["장평건설"] == "토목"  # 최빈(토목 2 > 건축 1)
    assert None not in m
    assert "선보" not in m
    # 동률 결정론: 토목 vs 건축 1:1 → 사전순(건축 < 토목)
    assert _company_trade_map([{"company": "X", "trade": "토목"}, {"company": "X", "trade": "건축"}])["X"] == "건축"


def test_sheetdata_company_trade_default_empty():
    sd = SheetData(output_manpower=[], occupation_manpower=[], equipment=[], quantity=[])
    assert sd.company_trade == {}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python -m pytest tests/test_exporter_format.py -v`
Expected: FAIL — `ImportError: cannot import name '_company_trade_map'`

- [ ] **Step 3: 구현** — `exporter.py`

`SheetData` 에 필드 추가 (exporter.py:28, `company_wa` 다음 줄):
```python
    company_trade: dict = field(default_factory=dict)  # 시트1 공종 폴백용 company→trade 맵
```

`_coerce` 함수 위(또는 SheetData 아래)에 헬퍼 추가:
```python
def _company_trade_map(quantity: list[dict]) -> dict:
    """company → 대표 trade(최빈, 동률 시 사전순 — spec §5.2 D2, company_wa 와 동일 결정론).
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
```

`fetch_sheet_data` return (exporter.py:217-223) 에 `company_trade` 추가:
```python
    return SheetData(
        output_manpower=output_manpower,
        occupation_manpower=[_coerce(r) for r in job_rows],
        equipment=[_coerce(r) for r in eq_rows],
        quantity=[dict(r) for r in act_rows],
        company_wa=company_wa,
        company_trade=_company_trade_map([dict(r) for r in act_rows]),
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python -m pytest tests/test_exporter_format.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/exporter.py pipeline/tests/test_exporter_format.py
git commit -m "feat(exporter): SheetData.company_trade 맵 (시트1 공종 폴백 소스)"
```

---

### Task 2: 구분(col2) + 시트1 공종 폴백 — `_fill_*` 수정

**Files:**
- Modify: `pipeline/agents/exporter.py` (`_fill_output_manpower` exporter.py:350-367, `_fill_quantity` exporter.py:412-437, `render_xlsx` exporter.py:440-451)
- Test: `pipeline/tests/test_exporter_format.py`

- [ ] **Step 1: 실패 테스트 추가** — `test_exporter_format.py` 끝에

```python
def _sd_one_company():
    return SheetData(
        output_manpower=[{
            "company": "광건", "bp_code": "PH_X-070", "zone": "CUB",
            "disc_abbrev": None,  # 공종 비어있음 → company_trade 폴백
            "work_text_today": "천장 설치", "workers_today_incr": {"total": 5},
        }],
        occupation_manpower=[], equipment=[],
        quantity=[{
            "company": "광건", "trade": "건축", "mapper_wa": "CUB",
            "work_content": "경량벽체", "unit": "m2", "today_qty": 9,
        }],
        company_wa={"광건": "CUB"},
        company_trade={"광건": "건축"},
    )


def test_render_division_col2_first_row_only():
    """구분(col2) = project, 첫 데이터 행(r5)만. 시트1·4 모두."""
    from pipeline.agents.exporter import COL_OUTPUT_MANPOWER, COL_QUANTITY
    wb = load_workbook(BytesIO(render_xlsx(_sd_one_company(), date(2025, 9, 25), project="M15X Ph-3 IBL")))
    # rename 후 시트1 = '1.작업사항'
    ws1 = wb["1.작업사항"]
    assert ws1.cell(5, COL_OUTPUT_MANPOWER["project"]).value == "M15X Ph-3 IBL"
    ws4 = wb["4.물량"]
    assert ws4.cell(5, COL_QUANTITY["project"]).value == "M15X Ph-3 IBL"


def test_render_sheet1_trade_fallback_to_company_trade():
    """시트1 공종(col4): disc_abbrev 없으면 company_trade 폴백."""
    from pipeline.agents.exporter import COL_OUTPUT_MANPOWER
    wb = load_workbook(BytesIO(render_xlsx(_sd_one_company(), date(2025, 9, 25), project="M15X Ph-3 IBL")))
    ws1 = wb["1.작업사항"]
    assert ws1.cell(5, COL_OUTPUT_MANPOWER["trade"]).value == "건축"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python -m pytest tests/test_exporter_format.py::test_render_division_col2_first_row_only tests/test_exporter_format.py::test_render_sheet1_trade_fallback_to_company_trade -v`
Expected: FAIL — `KeyError: '1.작업사항'`(아직 rename 안 함) 또는 col2/col4 None. (rename 은 Task 5 — 이 두 테스트는 Task 5 전까지 빨간 채로 두고, Step 4 에서는 임시로 `wb["1.출력인원 현황"]` 로 확인해도 됨. **권장: 이 두 테스트는 Task 5 의 render_xlsx 통합 후 함께 green 확인**.)

> 주의: 시트1 rename 은 `_finalize_layout`(Task 5)에서 일어난다. Task 2 단독으로는 시트명이 아직 `1.출력인원 현황` 이다. Task 2 의 green 검증은 아래 Step 4 의 임시 테스트로 하고, 위 두 테스트(`1.작업사항` 참조)는 Task 5 에서 green 확인한다.

- [ ] **Step 3: 구현** — `exporter.py`

`_fill_output_manpower` 시그니처·본문 (exporter.py:350-367):
```python
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
        # ... 이하 기존 동일 (bp_code, scope, work_*, _fill_timeshift ×4)
```
(나머지 본문 줄은 기존 그대로 유지 — `bp_code`/`scope`/`work_y`/`work_t`/`work_n`/timeshift 4개)

`_fill_quantity` 시그니처·본문 (exporter.py:412-437):
```python
def _fill_quantity(ws, rows: list[dict], report_date: _date, *, project: str | None = None) -> None:
    C = COL_QUANTITY
    for i, row in enumerate(rows):
        r = DATA_START_ROW + i
        if i == 0 and project:
            _safe_set(ws, r, C["project"], project)  # 구분(PJT) — 첫 행 1회
        _safe_set(ws, r, C["zone"], (row.get("mapper_wa") or row.get("zone")))
        # ... 이하 기존 동일
```

`render_xlsx` (exporter.py:445-448) — 인자 전달:
```python
    _fill_output_manpower(wb["1.출력인원 현황"], sheet_data.output_manpower, report_date,
                          company_wa=sheet_data.company_wa, company_trade=sheet_data.company_trade, project=project)
    _fill_occupation(wb["2.직종별 인원현황"], sheet_data.occupation_manpower, report_date)
    _fill_equipment(wb["3.장비현황"], sheet_data.equipment, report_date)
    _fill_quantity(wb["4.물량"], sheet_data.quantity, report_date, project=project)
```

- [ ] **Step 4: 임시 green 확인**(시트명 rename 전이므로 `1.출력인원 현황` 으로 확인)

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python -c "
from datetime import date; from io import BytesIO; from openpyxl import load_workbook
from pipeline.agents.exporter import SheetData, render_xlsx, COL_OUTPUT_MANPOWER, COL_QUANTITY
sd = SheetData(output_manpower=[{'company':'광건','bp_code':'PH_X-070','zone':'CUB','disc_abbrev':None,'work_text_today':'x','workers_today_incr':{'total':5}}], occupation_manpower=[], equipment=[], quantity=[{'company':'광건','trade':'건축','mapper_wa':'CUB','work_content':'경량벽체','unit':'m2','today_qty':9}], company_wa={'광건':'CUB'}, company_trade={'광건':'건축'})
wb = load_workbook(BytesIO(render_xlsx(sd, date(2025,9,25), project='M15X Ph-3 IBL')))
ws1 = wb['1.출력인원 현황']
print('구분', ws1.cell(5, COL_OUTPUT_MANPOWER['project']).value, '공종', ws1.cell(5, COL_OUTPUT_MANPOWER['trade']).value)
print('시트4 구분', wb['4.물량'].cell(5, COL_QUANTITY['project']).value)
"
```
Expected: `구분 M15X Ph-3 IBL 공종 건축` / `시트4 구분 M15X Ph-3 IBL`

- [ ] **Step 5: 기존 단위테스트 회귀 확인**(시그니처 변경 호환)

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python -m pytest tests/test_exporter_wa_source.py -v`
Expected: PASS (4 passed) — 새 kwarg 기본값 None 으로 기존 직접호출 호환.

- [ ] **Step 6: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/exporter.py pipeline/tests/test_exporter_format.py
git commit -m "feat(exporter): 구분(col2) project + 시트1 공종 company_trade 폴백"
```

---

### Task 3: `_finalize_layout` 1부 — 숨김 완전해제 (`_unhide_and_clean`)

**Files:**
- Modify: `pipeline/agents/exporter.py` (import 추가 + 상수 + `_unhide_and_clean`)
- Test: `pipeline/tests/test_exporter_format.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
def test_unhide_and_clean_removes_hidden_outline_filter():
    import openpyxl
    from pipeline.agents.exporter import _unhide_and_clean, DATA_START_ROW
    ws = openpyxl.Workbook().active
    ws.auto_filter.ref = "B5:Y100"
    ws.row_dimensions[8].hidden = True
    ws.row_dimensions[8].outlineLevel = 2
    ws.column_dimensions["D"].hidden = True
    ws.freeze_panes = "F26"
    _unhide_and_clean(ws, n=10)
    assert ws.auto_filter.ref is None
    assert ws.row_dimensions[8].hidden is False
    assert ws.row_dimensions[8].outlineLevel == 0
    assert ws.column_dimensions["D"].hidden is False
    assert ws.freeze_panes == "A5"
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python -m pytest tests/test_exporter_format.py::test_unhide_and_clean_removes_hidden_outline_filter -v`
Expected: FAIL — `ImportError: cannot import name '_unhide_and_clean'`

- [ ] **Step 3: 구현** — `exporter.py`

상단 import 블록(exporter.py:233-234 부근)에 추가:
```python
from openpyxl.styles import Alignment, Border, Side  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402
```

`DATA_START_ROW = 5`(exporter.py:237) 아래에 상수:
```python
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
```

`render_xlsx` 위에 함수 추가:
```python
def _unhide_and_clean(ws, n: int) -> None:
    """autofilter 제거 + 데이터 영역 row/col hidden·outline 해제 + freeze 정상화(A5).
    데이터 영역(1..DATA_START_ROW+n+3) 한정 — 그 아래 빈 행 잔존 hidden 은 출력 무관."""
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
    except Exception:
        pass
    ws.freeze_panes = "A5"
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python -m pytest tests/test_exporter_format.py::test_unhide_and_clean_removes_hidden_outline_filter -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/exporter.py pipeline/tests/test_exporter_format.py
git commit -m "feat(exporter): _unhide_and_clean — autofilter/hidden/outline/freeze 정상화"
```

---

### Task 4: `_finalize_layout` 2부 — dedup + 그룹 테두리 (`_dedup_and_border`)

**Files:**
- Modify: `pipeline/agents/exporter.py` (`_dedup_and_border`)
- Test: `pipeline/tests/test_exporter_format.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
def test_dedup_clears_same_group_keeps_different_zone():
    import openpyxl
    from pipeline.agents.exporter import _dedup_and_border, DATA_START_ROW
    ws = openpyxl.Workbook().active
    # 시트4 형태: col3=zone, col4=공종, col5=bp, col6=업체. r5/r6 같은 그룹, r7 zone 다름
    data = [
        ("CUB", "건축", "PH_X-070", "광건"),
        ("CUB", "건축", "PH_X-070", "광건"),  # 직전과 전부 같음 → 비움
        ("FAB", "건축", "PH_X-070", "광건"),  # zone 다름 → 유지
    ]
    for i, (z, t, b, c) in enumerate(data):
        r = DATA_START_ROW + i
        ws.cell(r, 3, z); ws.cell(r, 4, t); ws.cell(r, 5, b); ws.cell(r, 6, c)
    _dedup_and_border(ws, n=3, c0=2, c1=17, key_cols=(3, 4, 5, 6))
    # r6(둘째) 키 비움
    assert ws.cell(DATA_START_ROW + 1, 3).value is None
    assert ws.cell(DATA_START_ROW + 1, 6).value is None
    # r7 zone 다르므로 유지
    assert ws.cell(DATA_START_ROW + 2, 3).value == "FAB"
    assert ws.cell(DATA_START_ROW + 2, 6).value == "광건"


def test_dedup_border_group_boundary_thin_internal_hair():
    import openpyxl
    from pipeline.agents.exporter import _dedup_and_border, DATA_START_ROW
    ws = openpyxl.Workbook().active
    for i, c in enumerate(["광건", "광건", "남웅"]):
        ws.cell(DATA_START_ROW + i, 6, c); ws.cell(DATA_START_ROW + i, 3, "CUB")
        ws.cell(DATA_START_ROW + i, 4, "건축"); ws.cell(DATA_START_ROW + i, 5, "B")
    _dedup_and_border(ws, n=3, c0=2, c1=17, key_cols=(3, 4, 5, 6))
    assert ws.cell(DATA_START_ROW + 0, 6).border.top.style == "thin"   # 첫 그룹 시작
    assert ws.cell(DATA_START_ROW + 1, 6).border.top.style == "hair"   # 같은 광건 내부
    assert ws.cell(DATA_START_ROW + 2, 6).border.top.style == "thin"   # 남웅 새 그룹
    assert ws.cell(DATA_START_ROW + 0, 6).border.bottom.style == "hair"


def test_dedup_border_skips_merged_cell():
    """border 범위에 병합셀이 있어도 크래시 없이 dedup·테두리 적용(MergedCell read-only 회피)."""
    import openpyxl
    from pipeline.agents.exporter import _dedup_and_border, DATA_START_ROW
    ws = openpyxl.Workbook().active
    for i in range(2):
        ws.cell(DATA_START_ROW + i, 3, "CUB")
        ws.cell(DATA_START_ROW + i, 6, "광건")
    ws.merge_cells(start_row=DATA_START_ROW, start_column=8, end_row=DATA_START_ROW, end_column=9)
    _dedup_and_border(ws, n=2, c0=2, c1=17, key_cols=(3, 4, 5, 6))  # 예외 없어야
    assert ws.cell(DATA_START_ROW + 1, 6).value is None  # 둘째 행 dedup 정상
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python -m pytest tests/test_exporter_format.py -k dedup -v`
Expected: FAIL — `ImportError: cannot import name '_dedup_and_border'`

- [ ] **Step 3: 구현** — `exporter.py` (`_unhide_and_clean` 아래)

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python -m pytest tests/test_exporter_format.py -k dedup -v`
Expected: PASS (3 passed — group_keys, border_boundary, skips_merged_cell)

- [ ] **Step 5: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/exporter.py pipeline/tests/test_exporter_format.py
git commit -m "feat(exporter): _dedup_and_border — Zone~업체명 dedup + 옵션1 그룹테두리"
```

---

### Task 5: `_finalize_layout` 3부 — 시트1 재정의 + 조립 + `render_xlsx` 통합

**Files:**
- Modify: `pipeline/agents/exporter.py` (`_polish_sheet1`, `_finalize_layout`, `render_xlsx`)
- Test: `pipeline/tests/test_exporter_format.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
def test_finalize_sheet1_renamed_and_headcount_hidden():
    wb = load_workbook(BytesIO(render_xlsx(_sd_one_company(), date(2025, 9, 25), project="M15X Ph-3 IBL")))
    assert wb.sheetnames == ["1.작업사항", "2.직종별 인원현황", "3.장비현황", "4.물량"]
    ws1 = wb["1.작업사항"]
    assert ws1.column_dimensions["J"].hidden is True   # col10 인원
    assert ws1.column_dimensions["AK"].hidden is True  # col37
    assert ws1.column_dimensions["I"].hidden is False  # col9 명일작업(주요작업까지 보임)


def test_finalize_sheet2_no_hidden_no_filter_white():
    sd = _sd_one_company()
    # 시트2 데이터 2행
    sd.occupation_manpower = [
        {"disc_abbrev": "건축", "company": "광건", "job_type": "비계공", "workers_cum_t": 3},
        {"disc_abbrev": "건축", "company": "광건", "job_type": "형틀목공", "workers_cum_t": 5},
    ]
    wb = load_workbook(BytesIO(render_xlsx(sd, date(2025, 9, 25), project="M15X Ph-3 IBL")))
    ws2 = wb["2.직종별 인원현황"]
    assert ws2.auto_filter.ref is None
    assert ws2.row_dimensions[5].hidden is False
    assert ws2.row_dimensions[6].hidden is False
    assert ws2.freeze_panes == "A5"
    assert ws2.column_dimensions["D"].hidden is False  # 템플릿 숨김열 D 풀림
    assert ws2.column_dimensions["Y"].hidden is False  # 템플릿 숨김열 Y 풀림
    # 흰색: 데이터셀 fill 미적용(템플릿 기본). 회색 PoC 아티팩트 재유입 방지 가드.
    assert ws2.cell(5, 2).fill.patternType is None


def test_finalize_empty_sheet_safe():
    """빈 시트(occupation/equipment=[]) 도 _finalize 가 안 깨짐."""
    sd = _sd_one_company()
    sd.occupation_manpower = []
    sd.equipment = []
    wb = load_workbook(BytesIO(render_xlsx(sd, date(2025, 9, 25), project="M15X Ph-3 IBL")))
    assert "2.직종별 인원현황" in wb.sheetnames
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python -m pytest tests/test_exporter_format.py -k finalize -v`
Expected: FAIL — sheetnames 가 아직 `1.출력인원 현황` (rename 미적용) / `_finalize_layout` 미호출

- [ ] **Step 3: 구현** — `exporter.py`

`_dedup_and_border` 아래:
```python
def _polish_sheet1(ws, n: int) -> None:
    """시트1 작업사항(col7·8·9): ' | '→줄바꿈 + wrap + 행높이(줄수 기반)."""
    for i in range(n):
        r = DATA_START_ROW + i
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
```

`render_xlsx` 본문 — `wb.save` 직전(exporter.py:448-449)에 호출:
```python
    _fill_quantity(wb["4.물량"], sheet_data.quantity, report_date, project=project)
    _finalize_layout(wb, sheet_data)   # 신규: 숨김해제+dedup+테두리+시트1재정의
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: 통과 확인 (Task 2 의 보류 테스트 포함 전체)**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python -m pytest tests/test_exporter_format.py -v`
Expected: PASS (전체) — Task 2 의 `test_render_division_col2_first_row_only`/`test_render_sheet1_trade_fallback_to_company_trade`(`1.작업사항` 참조)도 이제 green.

- [ ] **Step 5: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/exporter.py pipeline/tests/test_exporter_format.py
git commit -m "feat(exporter): _finalize_layout 조립 + render_xlsx 통합 (시트1 작업사항 재정의)"
```

---

### Task 6: 기존 테스트 회귀 수정 + 전체 회귀 + 라이브 검증

**Files:**
- Modify: `pipeline/tests/test_exporter_render.py` (시트1 rename 반영 3곳)
- Create(임시): `/tmp/cpia_export_live_verify.py`

- [ ] **Step 1: 회귀 — `test_exporter_render.py` 시트명 3곳 수정**

`test_render_xlsx_sheets_present` (test_exporter_render.py:110):
```python
    assert wb.sheetnames == ["1.작업사항", "2.직종별 인원현황", "3.장비현황", "4.물량"]
```
`test_render_xlsx_output_manpower_row` (test_exporter_render.py:117):
```python
    ws = wb["1.작업사항"]
```
`test_render_xlsx_sheet1_bp_is_company` (test_exporter_render.py:194):
```python
    ws = wb["1.작업사항"]
```

- [ ] **Step 2: exporter 전체 회귀**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python -m pytest tests/test_exporter_render.py tests/test_exporter_wa_source.py tests/test_exporter_merged_cell.py tests/test_exporter_node.py tests/test_exporter_progress.py tests/test_exporter_format.py -v`
Expected: PASS — 단위(DB 불필요) 전부 green. (DB 필요한 test_exporter_endpoint.py 는 DB 가동 시 별도 실행.)

> 만약 `test_render_xlsx_output_manpower_row` 가 여전히 실패하면: dedup 으로 r5(첫 행)는 절대 비워지지 않으므로 zone='FAB' 가 유지돼야 정상. 첫 행이 비었다면 `_dedup_and_border` 의 `is_new`(prev is None) 로직 확인.

- [ ] **Step 3: 라이브 검증 스크립트 작성** — `/tmp/cpia_export_live_verify.py`

```python
"""실 DB 9/25 → fetch_sheet_data → render_xlsx → 양식 정합 검증 (spec §7)."""
from __future__ import annotations
import asyncio, sys
from datetime import date
from io import BytesIO
sys.path.insert(0, "/Users/kyungseoplee/Project Agent/CPIA")
from openpyxl import load_workbook
from pipeline.db import PGClient
from pipeline.agents.exporter import fetch_sheet_data, render_xlsx

PG = "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia"

async def main():
    pg = PGClient(PG); await pg.connect()
    try:
        sd = await fetch_sheet_data(pg, "m15x-ph3-ibl", date(2025, 9, 25))
    finally:
        await pg.close()
    wb = load_workbook(BytesIO(render_xlsx(sd, date(2025, 9, 25), project="M15X Ph-3 IBL")))
    assert wb.sheetnames[0] == "1.작업사항", wb.sheetnames
    ws1 = wb["1.작업사항"]
    print("시트1 구분 r5:", ws1.cell(5, 2).value, "| 공종 r5:", ws1.cell(5, 4).value)
    print("시트1 col10(J) hidden:", ws1.column_dimensions["J"].hidden)
    # major 가드: 공종 폴백이 전 행에 작동하나(company 표기 mismatch 시 None 발생)
    none_trade = sum(1 for i in range(len(sd.output_manpower)) if ws1.cell(5 + i, 4).value is None)
    print("시트1 공종 None 행수(폴백 실패 — 0 이어야):", none_trade)
    for sn in ["1.작업사항", "2.직종별 인원현황", "3.장비현황", "4.물량"]:
        ws = wb[sn]
        n = {"1.작업사항": len(sd.output_manpower), "2.직종별 인원현황": len(sd.occupation_manpower),
             "3.장비현황": len(sd.equipment), "4.물량": len(sd.quantity)}[sn]
        hid = sum(1 for i in range(n) if ws.row_dimensions[5 + i].hidden)
        col_hid = sum(1 for k in ws.column_dimensions if ws.column_dimensions[k].hidden)
        print(f"  {sn}: 데이터 {n}행 hidden={hid} col_hidden={col_hid} autofilter={ws.auto_filter.ref} freeze={ws.freeze_panes}")
    ws4 = wb["4.물량"]
    print("시트4 r5 업체:", ws4.cell(5, 6).value, "→ r6 업체:", ws4.cell(6, 6).value, "(dedup이면 r6 None)")
    print("시트2 r5 fill:", wb["2.직종별 인원현황"].cell(5, 2).fill.patternType, "(None=흰색)")

asyncio.run(main())
```

- [ ] **Step 4: 라이브 검증 실행**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA" && pipeline/.venv/bin/python /tmp/cpia_export_live_verify.py`
Expected:
- `시트1 구분 r5: M15X Ph-3 IBL | 공종 r5: 건축`
- `시트1 col10(J) hidden: True`
- `시트1 공종 None 행수: 0` (company 표기 일치 → 폴백 전원 채워짐 — major 가드)
- 4시트 전부 row `hidden=0`, `autofilter=None`, `freeze=A5`; `col_hidden` 은 시트2·3·4=0, 시트1=28(J~AK 의도)
- `시트4 r5 업체: 광건 → r6 업체: None`
- `시트2 r5 fill: None (None=흰색)`

- [ ] **Step 5: UI 정합 비교 (선택, DB 가동 시)**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA" && curl -s "http://localhost:5537/api/mock/consolidated?date=2025-09-25" | pipeline/.venv/bin/python -c "import sys,json; d=json.load(sys.stdin); print('UI pjt:', d['pjt'], '| q0 zone/trade/bp_name:', d['quantity'][0]['zone'], d['quantity'][0]['trade'], d['quantity'][0]['bp_name'])"`
Expected: `UI pjt: M15X Ph-3 IBL | q0 zone/trade/bp_name: CUB 건축 광건` — 엑셀 시트4 r5(구분=M15X Ph-3 IBL, zone=CUB, 공종=건축, 업체=광건)와 일치.

- [ ] **Step 6: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/tests/test_exporter_render.py
git commit -m "test(exporter): 시트1 작업사항 rename 회귀 반영"
```

---

## 검증 종합 (전부 green 이어야 done)

1. `pytest tests/test_exporter_format.py -v` — 신규 양식 테스트 전부 PASS
2. `pytest tests/test_exporter_render.py tests/test_exporter_wa_source.py tests/test_exporter_merged_cell.py tests/test_exporter_node.py tests/test_exporter_progress.py -v` — 회귀 전부 PASS
3. `/tmp/cpia_export_live_verify.py` — 라이브 9/25: 구분·공종·숨김0·dedup·흰색·freeze 전부 기대값
4. (선택) UI `/api/mock/consolidated` 와 zone/공종/업체/구분 일치

## 비범위 (건드리지 말 것)

- 인원 '주간 몰림'(조출/연장/야간/철야 0): v2 데모 데이터 특성. 양식 작업 아님.
- `capture_col_styles` / 샘플 스타일 복제: 회색 원인, 이식 안 함.
- 템플릿 파일(`consolidated_template.xlsx`) 자체 수정 안 함 — 런타임 후처리만.
- `exporter.py`·테스트 외 파일 변경 없음. forecaster/optimizer/생산성 무관.
- `exporter_routes.py`·`consolidated_xlsx_node` 의 project 폴백 통일은 별도(현 범위 밖).

## 리스크 / 함정

- `_finalize_layout` 은 `SheetData` 리스트 길이(=데이터 행수)에 의존 — render_xlsx 가 박은 행수와 일치해야 dedup/테두리 범위 정확.
- `_fill_*` 새 kwarg 는 반드시 기본값 `None`(test_exporter_wa_source.py 직접호출 호환). `company_trade or {}` 방어 필수.
- 시트1 rename 은 `_finalize_layout` 마지막 단계 — `_GROUP_SHEETS` 루프·`_polish_sheet1`·col숨김은 모두 rename 전 `1.출력인원 현황` 이름으로 접근.
- 시트1 dedup 키 `(3,4,5)` 에 구분(col2) 미포함 — 구분은 `_fill_*` 의 i==0 1회로만 채워지므로 dedup 과 독립.
- 테두리 col 범위: 시트1 `c1=37`(숨김 col10~37 포함)·시트2·3 `c1=25` 는 템플릿 전폭 기준 — 숨김/빈 컬럼 테두리는 비가시라 무해(spec '각자'=전폭 해석).
- **시트1 공종 폴백 라이브 정합(major)**: `output_manpower.company`(bp_summaries)와 `company_trade` 키(parser_activities.company)가 문자열 일치해야 폴백이 채워진다. 9/25 는 양쪽 '광건' 등 동일 표기 확인됨. Task 6 라이브의 `공종 None 행수=0` 가드로 mismatch 즉시 검출.
