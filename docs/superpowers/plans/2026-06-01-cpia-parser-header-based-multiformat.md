# CPIA Parser 헤더 기반 다포맷 정규화 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CPIA 파서를 통합작업일보 전용에서 통합+업체 두 포맷 결정론 처리로 확장 — `data/demo_inputs/20250925/` 업체작업일보 10개(.xlsx 7 / .xlsm 3)를 정확히 파싱하면서 통합포맷 회귀 0.

**Architecture:** 시트4(컬럼 시프트 발생 시트)는 컬럼 인덱스 하드코딩 → 헤더 텍스트 해석으로 전환. 시트1/2/3(통합·업체 레이아웃 동일)은 기존 함수 보존 + 최소 패치(`_is_bp_code` 다중패턴 + final_flag 조건부 완화). 날짜 regex 일반화. LLM 없음.

**Tech Stack:** Python 3.11(pipeline/.venv, uv), openpyxl, pytest. 출력 스키마 `ParsedDailyReport`(`pipeline/state.py`) 불변.

**Spec:** `docs/superpowers/specs/2026-06-01-cpia-parser-header-based-multiformat-design.md`

**실행 환경 주의:**
- 테스트 실행: `cd "/Users/kyungseoplee/Project Agent/CPIA" && uv run --project pipeline python -m pytest <경로> -v`
- 파서 단독 실행: `CPIA_PARSER_VERIFY_LLM=off uv run --project pipeline python -c "..."` (LLM 검증 off)
- 모든 .py 상단 `from __future__ import annotations` 필수
- 한자 금지

**회귀 골든 (기존 파서 baseline 실측, 절대 사수):**
통합작업일보 → `activities=1193 / bp_summaries=99 / job_allocations=975 / equipment_allocations=1111`

**업체포맷 기대 (시뮬레이션 실측):**
demo_inputs 각 파일 → `activities=33 / bp_summaries=1 / job_allocations=76 / equipment=68`,
activity[0] = `work_content='PCW 20 배관 공사' / unit='m' / today_qty=30.0 / company(정규화)='중원엔지니어링' / bp_code='M15X_PH4_041' / trade='UT'`

---

## File Structure

- **Modify** `pipeline/agents/parser.py` — 모든 변경의 중심:
  - `_DATE_PATTERN`(L503) 일반화
  - `_BP_RE`/`_is_bp_code`(L100-106) 다중 패턴
  - `_resolve_sheet4_columns`(신규) + `_parse_sheet4_activities`(L346) 헤더 기반 전환
  - `_parse_sheet2/3`(L255/428) final_flag 조건부 완화
  - `parse_daily_report`(L539) LLM 검증 호출(L567-570) 제거
  - `_extract_meta`(L506) project prefix 에 `업체작업일보_` 추가
- **Create** `pipeline/tests/test_parser_subcon.py` — 업체포맷 골든 테스트 (신규)
- **Modify** `pipeline/tests/conftest.py` — `sample_subcon_path` fixture 추가
- **Modify** `pipeline/tests/test_parser.py` — 통합 회귀 골든 건수 갱신/확인 (필요 시)
- 출력 스키마·다운스트림(mapper/exporter/atomizer/forecaster)·`parser_node.py`·`parser_llm.py`: **무수정**

---

## Task 1: 날짜 regex 일반화 (.xlsm + 8자리 즉사 해소)

**Files:**
- Modify: `pipeline/agents/parser.py:503` (`_DATE_PATTERN`)
- Test: `pipeline/tests/test_filename_parser.py` (또는 test_parser.py 에 추가)

현 `_(\d{4})(\d{2})(\d{2})\.xlsx$|_(\d{6})\.xlsm?$` 는 8자리를 .xlsx 만, 6자리를 .xlsm 만 허용 → `_20250925.xlsm`(8자리+xlsm) 즉사.

- [ ] **Step 1: 실패 테스트 작성**

`pipeline/tests/test_filename_parser.py` 에 추가 (없으면 test_parser.py 에):

```python
import re
from pipeline.agents.parser import _DATE_PATTERN

def test_date_pattern_xlsm_8digit():
    """8자리 날짜 + .xlsm 조합도 추출돼야 한다 (업체작업일보)."""
    m = _DATE_PATTERN.search("업체작업일보_M15X_PH3_남웅건설_단열공사_20250925.xlsm")
    assert m is not None
    assert (m.group(1), m.group(2), m.group(3)) == ("2025", "09", "25")

def test_date_pattern_xlsx_8digit_still_works():
    """기존 통합포맷(.xlsx 8자리) 회귀 없음."""
    m = _DATE_PATTERN.search("통합작업일보_..._20250925.xlsx")
    assert m is not None and m.group(1) == "2025"
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA" && uv run --project pipeline python -m pytest pipeline/tests/test_filename_parser.py::test_date_pattern_xlsm_8digit -v`
Expected: FAIL (현 패턴이 8자리+xlsm 미매칭, `m is None`)

- [ ] **Step 3: 최소 구현**

`parser.py:503` 교체:

```python
_DATE_PATTERN = re.compile(r"_(\d{4})(\d{2})(\d{2})\.xls[mx]?$|_(\d{6})\.xls[mx]?$")
```

- [ ] **Step 4: 통과 확인**

Run: `uv run --project pipeline python -m pytest pipeline/tests/test_filename_parser.py -v`
Expected: PASS (두 테스트 모두)

- [ ] **Step 5: 커밋**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_filename_parser.py
git commit -m "fix(parser): _DATE_PATTERN 이 8자리 날짜+.xlsm 조합 수용 (업체작업일보)"
```

---

## Task 2: BP코드 다중 패턴

**Files:**
- Modify: `pipeline/agents/parser.py:100-106` (`_BP_RE`, `_is_bp_code`)
- Test: `pipeline/tests/test_parser.py`

현 `_BP_RE = ^PH[_\- ]?X[_\- ]?\d+$` 는 `M15X_PH4_041`(업체) 미매칭. 통합 `PH_X-088` 은 유지하면서 업체 패턴 추가.

- [ ] **Step 1: 실패 테스트 작성**

`test_parser.py` 에 추가:

```python
from pipeline.agents.parser import _is_bp_code

def test_is_bp_code_multiformat():
    # 통합포맷 (회귀)
    assert _is_bp_code("PH_X-088") is True
    assert _is_bp_code("PH_X-002") is True
    # 업체포맷 (신규)
    assert _is_bp_code("M15X_PH4_041") is True
    # 회사명은 코드 아님
    assert _is_bp_code("중원엔지니어링FAB") is False
    assert _is_bp_code("㈜해광FAB") is False
    assert _is_bp_code(None) is False
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --project pipeline python -m pytest pipeline/tests/test_parser.py::test_is_bp_code_multiformat -v`
Expected: FAIL (`M15X_PH4_041` 가 False)

- [ ] **Step 3: 최소 구현**

`parser.py:100-106` 교체:

```python
_BP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^PH[_\- ]?X[_\- ]?\d+$", re.IGNORECASE),   # 통합: PH_X-088
    re.compile(r"^[A-Za-z0-9]+_PH\d+_\d+$", re.IGNORECASE),  # 업체: M15X_PH4_041
)


def _is_bp_code(v: object) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    return any(p.match(s) for p in _BP_PATTERNS)
```

(`_BP_RE` 를 직접 참조하는 곳이 있으면 `_is_bp_code` 호출로 교체. grep: `grep -n _BP_RE pipeline/agents/parser.py`)

- [ ] **Step 4: 통과 확인**

Run: `uv run --project pipeline python -m pytest pipeline/tests/test_parser.py::test_is_bp_code_multiformat -v`
Expected: PASS

- [ ] **Step 5: 회귀 확인 (전체 parser 테스트)**

Run: `uv run --project pipeline python -m pytest pipeline/tests/test_parser.py -v`
Expected: 기존 테스트 전부 PASS (통합 BP 매칭 회귀 없음)

- [ ] **Step 6: 커밋**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser.py
git commit -m "feat(parser): BP코드 다중 패턴 (PH_X-NNN + M15X_PHn_NNN)"
```

---

## Task 3: 시트4 헤더 기반 컬럼 해석 (column shift 본체)

**Files:**
- Modify: `pipeline/agents/parser.py` (`_parse_sheet4_activities` L346, `_resolve_sheet4_columns` 신규)
- Test: `pipeline/tests/test_parser.py` (통합 회귀) + `test_parser_subcon.py` (업체, Task 6 에서 통합)

업체포맷은 '업체명' 컬럼 부재로 col7+ 가 1칸 좌측 시프트. 헤더 텍스트로 컬럼을 찾으면 통합('업체명' 있음)·업체(없음) 자동 흡수. today_qty 는 `금일실적[C]` (누적 D 아님).

- [ ] **Step 1: 헤더 해석기 실패 테스트 작성**

`test_parser.py` 에 추가:

```python
import openpyxl
from pipeline.agents.parser import _resolve_sheet4_columns

def test_resolve_sheet4_columns_integrated(sample_tong_path):
    """통합포맷: 업체명 컬럼 존재 → company_col 매핑."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True)
    cols = _resolve_sheet4_columns(wb["4.물량"])
    wb.close()
    assert cols["work_content"] == 8   # 통합: 작업내용 col8
    assert cols["unit"] == 9
    assert cols["today_qty"] == 12      # 금일실적[C]
    assert cols["today_cum"] == 13      # 금일누적[D]
    assert cols["progress"] == 14       # F% (row4 둘째 헤더) — 회귀 필수
    assert "company_col" in cols        # 업체명 컬럼 있음
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --project pipeline python -m pytest pipeline/tests/test_parser.py::test_resolve_sheet4_columns_integrated -v`
Expected: FAIL (`_resolve_sheet4_columns` 미정의 → ImportError/AttributeError)

- [ ] **Step 3: 헤더 해석기 구현**

`parser.py` 에 추가. **헤더는 2-row 스택**(row3 주 라벨 + row4 의 `[A][B][C][D]`·`F%` 마커)이므로
두 행을 함께 읽어야 한다 — 검증 결과 `progress_percent`(F%)가 row4 에만 있어 row3 단독으로는
회귀가 깨진다(통합 progress 누락). `금일실적`→today_qty / `금일누적`→today_cum 구분이 핵심:

```python
def _norm_header(v: object) -> str:
    return re.sub(r"\s+", "", str(v)) if v is not None else ""


def _resolve_sheet4_columns(ws, header_rows: tuple[int, int] = (3, 4)) -> dict[str, int]:
    """시트4 헤더 텍스트 → {필드: 컬럼인덱스} 매핑. 통합/업체 자동 흡수.

    헤더 2-row 스택(row3 주 라벨 + row4 [A][B][C][D]·F% 마커)을 함께 읽는다.
    '업체명' 헤더가 있으면 통합포맷(company_col 별도), 없으면 업체포맷
    (company 는 BP사 컬럼의 코드/회사명 교대행에서 추출).
    """
    cols: dict[str, int] = {}
    for c in range(1, ws.max_column + 1):
        h3 = _norm_header(ws.cell(header_rows[0], c).value)
        h4 = _norm_header(ws.cell(header_rows[1], c).value)
        h = h3 or h4
        if not h:
            continue
        if h == "공종":
            cols.setdefault("trade", c)
        elif h == "BP사":
            cols.setdefault("bp", c)
        elif h == "업체명":
            cols.setdefault("company_col", c)
        elif h.lower().startswith("scope"):
            cols.setdefault("scope", c)
        elif "대표물량" in h or "작업내용" in h:
            cols.setdefault("work_content", c)
        elif h == "단위":
            cols.setdefault("unit", c)
        elif "총물량" in h:
            cols.setdefault("plan_total", c)
        elif "전일누적" in h:
            cols.setdefault("yesterday_cum", c)
        elif "금일실적" in h:        # today_qty = 실적[C], 누적[D] 아님
            cols.setdefault("today_qty", c)
        elif "금일누적" in h:
            cols.setdefault("today_cum", c)
        elif "F%" in h3 or "F%" in h4:   # progress_percent — row4 위치 (회귀 필수)
            cols.setdefault("progress", c)
        elif "잔여" in h:
            cols.setdefault("remaining", c)
    required = ("trade", "bp", "work_content", "unit", "today_qty")
    missing = [f for f in required if f not in cols]
    if missing:
        raise ParseError(f"시트4 헤더 매핑 실패: {missing}")
    return cols
```

검증 실측(통합): 매핑 = `{trade:4, bp:5, company_col:6, scope:7, work_content:8, unit:9, plan_total:10, yesterday_cum:11, today_qty:12, today_cum:13, progress:14}`. 업체: company_col 없음, work_content:7 / unit:8 / today_qty:11.

- [ ] **Step 4: 헤더 해석기 통과 확인**

Run: `uv run --project pipeline python -m pytest pipeline/tests/test_parser.py::test_resolve_sheet4_columns_integrated -v`
Expected: PASS

- [ ] **Step 5: `_parse_sheet4_activities` 헤더 기반 전환**

`parser.py:346` `_parse_sheet4_activities(ws)` 를 매핑 기반으로 재작성. 통합포맷(company_col 있음)은 행별 ffill, 업체포맷(없음)은 BP사 컬럼 코드/회사명 교대행 group 처리. **모든 필드는 `cols` 매핑 인덱스로 읽고**, today_qty 는 `cols["today_qty"]`(금일실적). 출력 `Activity` dict 필드/기본값은 기존(L388-424) 그대로 유지.

핵심 로직:
```python
def _parse_sheet4_activities(ws) -> list[Activity]:
    cols = _resolve_sheet4_columns(ws)
    has_company_col = "company_col" in cols
    activities: list[Activity] = []
    if has_company_col:
        # 통합포맷: trade ffill + company 는 BP행에 종속(독립 ffill 아님 — 검증으로 확정)
        cur_trade = cur_bp = cur_company_raw = None
        for r in range(5, ws.max_row + 1):
            tv = ws.cell(r, cols["trade"]).value
            if tv is not None:
                cur_trade = str(tv)
            bv = ws.cell(r, cols["bp"]).value
            if bv is not None:
                cur_bp = str(bv).strip()
                # company 는 BP행 종속: col6 없으면 비움 (기존 parser.py:370-371 동작).
                # 독립 ffill 하면 직전 업체명이 새어나와 통합 31건 회귀 (검증 실측).
                cv = ws.cell(r, cols["company_col"]).value
                cur_company_raw = str(cv) if cv is not None else None
            wv = ws.cell(r, cols["work_content"]).value
            if wv is None:
                continue
            activities.append(_build_activity(ws, r, cols, cur_trade, cur_bp, cur_company_raw))
    else:
        # 업체포맷: BP사 컬럼 코드행~다음코드행 group, 회사명=group 내 첫 non-bp 값
        bpc = cols["bp"]
        code_rows = [r for r in range(5, ws.max_row + 1) if _is_bp_code(ws.cell(r, bpc).value)]
        for gi, start in enumerate(code_rows):
            end = (code_rows[gi + 1] - 1) if gi + 1 < len(code_rows) else ws.max_row
            bp_code = str(ws.cell(start, bpc).value).strip()
            company_raw = None
            for r in range(start, end + 1):
                v = ws.cell(r, bpc).value
                if v is not None and not _is_bp_code(v):
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
```

`_build_activity(ws, r, cols, trade, bp_code, company_raw)` 헬퍼는 기존 L388-424 의 Activity dict 구성을 그대로 옮기되 값 읽기를 `cols` 인덱스로. **수량 필드 6개 모두 매핑 인덱스로 읽어야 회귀 0** (검증 실측):
- `work_content = str(ws.cell(r, cols["work_content"]).value).strip()`
- `unit = _normalize_unit(str(ws.cell(r, cols["unit"]).value or "").strip())`
- `plan_total_qty = _safe_num(ws.cell(r, cols["plan_total"]).value)`
- `yesterday_cum_qty = _safe_num(ws.cell(r, cols["yesterday_cum"]).value)`
- `today_qty = c if c is not None else 0.0` (`c = _safe_num(ws.cell(r, cols["today_qty"]).value)`)
- `today_cum_qty = _safe_num(ws.cell(r, cols["today_cum"]).value)`
- `progress_percent = _safe_num(ws.cell(r, cols["progress"]).value) if "progress" in cols else None` ← row4 헤더, 누락 시 통합 회귀
- `scope = str(c7) if c7 is not None else None` (`c7 = ws.cell(r, cols["scope"]).value`), `zone = extract_zone(c7)`
- `company = normalize_company(split_company_and_zone(company_raw))`
- `trade`/`l5_disc = trade or ""`, 나머지 필드(remaining_*/wbs_*/wa/mapping_*/conditions/assigned_workers 등) 기존 기본값 그대로

- [ ] **Step 6: 통합 회귀 — 시트4 단위 테스트 (주의 2건, 실측 기반)**

Run (선택, 느림): `uv run --project pipeline python -m pytest pipeline/tests/test_parser.py -k sheet4`

**주의 — 실행 전 반드시 읽을 것:**
- ⚠️ **`test_parse_sheet4_required_fields` 는 헤더전환 전부터 FAIL (pre-existing).** 통합 원본에
  업체명 빈 BP행(예 `PH_X-080`: `company=''`, work_content='CMP 구간 기준점 마킹 및 천공')이
  31건 있어 `assert a["company"]` 가 깨진다. 이는 **기존 파서 동작이고 신규 회귀가 아니다**
  (검증: 헤더기반 결과 = 기존 결과, company 필드 diff 0). **이 테스트를 고치려 들지 말 것** —
  company 빈 31건 제거는 기존 동작 변경이라 이번 스코프 밖. 기대 결과: `1 failed, 9 passed`.
- ⚠️ 이 단위 테스트는 `read_only=True` 라 `ws.cell` 임의접근이 O(n²) → **~14분** 소요(실측).
  시트4 회귀의 **실질 검증은 Step 7 의 `act=1193` E2E**(`read_only=False`, 초 단위)로 한다.
  Step 6 은 시간 여유 있을 때만, 없으면 건너뛰고 Step 7 로.
- 판정: count/unit/today_qty/zone 등 **9개가 PASS** 면 회귀 없음 (required_fields 1건은 pre-existing).

- [ ] **Step 7: 통합 activities 건수 회귀 직접 확인**

Run:
```bash
CPIA_PARSER_VERIFY_LLM=off uv run --project pipeline python -c "
from pipeline.agents.parser import parse_daily_report
r=parse_daily_report('docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx')
print('act=%d'%len(r['activities']))
assert len(r['activities'])==1193, r['activities'].__len__()
print('OK 통합 act=1193 회귀 통과')
"
```
Expected: `OK 통합 act=1193 회귀 통과`

- [ ] **Step 8: 커밋**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser.py
git commit -m "feat(parser): 시트4 헤더 기반 컬럼 해석 — column shift 해소 (통합+업체)"
```

---

## Task 4: 시트1 코드/회사명 분리 (BP 다중패턴 효과 검증 — 코드 변경 불요 확정)

**Files:**
- Modify: `pipeline/tests/conftest.py` (업체 fixture — Task 4·5·6 공용, 여기서 최초 추가)
- Modify: `pipeline/tests/test_parser.py` (회귀 가드 추가). **`parser.py` 수정 없음.**

**검증으로 확정**: Task 2 의 `_is_bp_code` 다중패턴만 적용하면, 기존
`_parse_sheet1_bp_summaries`(col30 병합 group + skip 로직) 가 **그대로** 통합 99 / 업체 1 을
정확히 낸다. 업체파일 시트1 에도 col30 병합 group 이 있어 group 검출이 작동하며(실측),
bp/company 분리도 정확(통합 `PH_X-002`/`에스티엠`, 업체 `M15X_PH4_041`/`중원엔지니어링`).
→ **이 task 는 group fallback 같은 코드 변경이 불필요**하다. 회귀 가드 테스트만 추가한다.

- [ ] **Step 1: conftest 에 업체 fixture 추가 (Task 4·5·6 공용 — 여기서 한 번만)**

`pipeline/tests/conftest.py` 에 추가 (Task 6 에서 또 언급되지만 **중복 추가 금지**):
```python
@pytest.fixture(scope="session")
def sample_subcon_path(cpia_root) -> Path:
    return cpia_root / "data/demo_inputs/20250925/업체작업일보_M15X_PH3_㈜신성이엔지_골조공사_20250925.xlsx"

@pytest.fixture(scope="session")
def demo_inputs_dir(cpia_root) -> Path:
    return cpia_root / "data/demo_inputs/20250925"
```

- [ ] **Step 2: 업체 시트1 분리 가드 테스트 작성**

```python
def test_parse_sheet1_subcon_bp_company_split(sample_subcon_path):
    """업체포맷 시트1: BP코드와 회사명이 정확히 분리 (Task 2 다중패턴 효과)."""
    import openpyxl
    from pipeline.agents.parser import _parse_sheet1_bp_summaries
    wb = openpyxl.load_workbook(sample_subcon_path, data_only=True)
    summaries = _parse_sheet1_bp_summaries(wb["1.출력인원 현황"])
    wb.close()
    assert len(summaries) == 1
    s = summaries[0]
    assert s["bp_code"] == "M15X_PH4_041"
    assert "중원엔지니어링" in s["company"]   # 회사명이 company (코드 누출 X)
```

- [ ] **Step 3: 통과 확인 (Task 2 적용 후이므로 코드 변경 없이 PASS 기대)**

Run: `uv run --project pipeline python -m pytest pipeline/tests/test_parser.py::test_parse_sheet1_subcon_bp_company_split -v`
Expected: PASS (검증 실측 — 기존 함수가 업체 col30 group 으로 bp=1 정확 추출).
만약 FAIL 이면(예상 외) `_parse_sheet1_bp_summaries` group 검출에 BP코드 기반 fallback 추가:
col30 병합/solo 가 없을 때 `_is_bp_code` 코드행을 group 시작으로, 회사명=group 내 첫 non-bp col5.

- [ ] **Step 4: 통합 시트1 회귀 확인**

Run: `uv run --project pipeline python -m pytest pipeline/tests/test_parser.py -k sheet1 -v`
Expected: 기존 `test_parse_sheet1_*` (bp_summaries_count 99 등) 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add pipeline/tests/conftest.py pipeline/tests/test_parser.py
git commit -m "test(parser): 업체 fixture + 시트1 BP/회사명 분리 가드 (다중패턴 효과)"
```

---

## Task 5: 시트2/3 final_flag 조건부 완화

**Files:**
- Modify: `pipeline/agents/parser.py` (`_parse_sheet2_job_allocations` L255, `_parse_sheet3_equipment_allocations` L428)
- Test: `pipeline/tests/test_parser.py`

업체파일은 `col25` final_flag('O') 전무 → job/equip 0건. **무조건 완화는 통합 폭증(job 975→11836)** 이므로 조건부: 'O' 마커가 있으면(통합) 유지, 없으면(업체) 직종코드/장비대분류 존재로 판정.

- [ ] **Step 1: 시트2 final_flag 유무 판정 헬퍼 + 실패 테스트**

```python
def test_sheet2_job_subcon_nonzero(sample_subcon_path):
    """업체포맷: final_flag 없어도 job_allocations > 0."""
    import openpyxl
    from pipeline.agents.parser import _parse_sheet2_job_allocations
    wb = openpyxl.load_workbook(sample_subcon_path, data_only=True)
    jobs = _parse_sheet2_job_allocations(wb["2.직종별 인원현황"])
    wb.close()
    assert len(jobs) > 0   # 현재는 0 (col25=='O' 게이트)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --project pipeline python -m pytest pipeline/tests/test_parser.py::test_sheet2_job_subcon_nonzero -v`
Expected: FAIL (`len(jobs) == 0`)

- [ ] **Step 3: 조건부 완화 구현**

`_parse_sheet2_job_allocations`(L255) 와 `_parse_sheet3_equipment_allocations`(L428) 에서:
- 함수 시작 시 `col25` 전체 스캔해 'O' 값 존재 여부 판정: `has_final_flag = any(ws.cell(r,25).value == "O" for r in range(...))`.
- group 시작 조건의 `c25 == "O"` 와 row 판정의 `c25 != "O"` 를 **`has_final_flag` 일 때만** 적용. `has_final_flag` 가 False 면 'O' 조건 생략하고 나머지 조건(시트2: col4 직종코드 존재 + col6 직종명 + not admin / 시트3: col4 장비대분류 존재)으로 판정.

예 (시트2 row 판정):
```python
for r in range(start, end + 1):
    c4 = ws.cell(r, 4).value
    if c4 is None:
        continue
    if has_final_flag and ws.cell(r, 25).value != "O":
        continue
    job_type = str(ws.cell(r, 6).value or "").strip()
    if not job_type or _is_admin_job(job_type):
        continue
    ...
```
group 시작 식별(L269-280)의 `c25 != "O"` 도 동일하게 `has_final_flag` 가드.

- [ ] **Step 4: 업체 job/equip 통과 확인**

Run: `uv run --project pipeline python -m pytest pipeline/tests/test_parser.py::test_sheet2_job_subcon_nonzero -v`
Expected: PASS

- [ ] **Step 5: 통합 회귀 (job=975 / eq=1111 절대 사수)**

Run:
```bash
CPIA_PARSER_VERIFY_LLM=off uv run --project pipeline python -c "
from pipeline.agents.parser import parse_daily_report
r=parse_daily_report('docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx')
j,e=len(r['job_allocations']),len(r['equipment_allocations'])
print('job=%d eq=%d'%(j,e))
assert j==975 and e==1111, (j,e)
print('OK 통합 job=975 eq=1111 회귀 통과')
"
```
Expected: `OK 통합 job=975 eq=1111 회귀 통과` (폭증 없음 — has_final_flag 가드 검증)

- [ ] **Step 6: 커밋**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser.py
git commit -m "feat(parser): 시트2/3 final_flag 조건부 완화 ('O' 없는 업체포맷만)"
```

---

## Task 6: parse_daily_report 통합 + LLM 검증 제거 + 업체포맷 E2E 골든

**Files:**
- Modify: `pipeline/agents/parser.py` (`parse_daily_report` L539 — LLM 검증 호출 L567-570 제거, `_extract_meta` L532 project prefix)
- Create: `pipeline/tests/test_parser_subcon.py`
- (`conftest.py` 업체 fixture 는 **Task 4 Step 1 에서 이미 추가** — 중복 금지)

- [ ] **Step 1: conftest 업체 fixture 존재 확인**

Task 4 Step 1 에서 `sample_subcon_path` / `demo_inputs_dir` 가 이미 추가됐다. 없으면(Task 4 를 건너뛴 경우) 여기서 추가하되, 있으면 그대로 사용.

- [ ] **Step 2: 업체포맷 E2E 골든 테스트 작성**

`pipeline/tests/test_parser_subcon.py` 생성:
```python
from __future__ import annotations

import glob

import pytest

from pipeline.agents.parser import parse_daily_report


def test_subcon_e2e_golden(sample_subcon_path):
    """업체작업일보 1개 E2E — 시뮬레이션 실측 골든."""
    r = parse_daily_report(sample_subcon_path)
    assert len(r["activities"]) == 33
    assert len(r["bp_summaries"]) == 1
    assert len(r["job_allocations"]) == 76
    assert len(r["equipment_allocations"]) == 68
    a = r["activities"][0]
    assert a["work_content"] == "PCW 20 배관 공사"   # 'M' 아님
    assert a["unit"] == "m"                          # 총물량 아님
    assert a["today_qty"] == 30.0                    # 금일실적[C], 누적 120 아님
    assert "중원엔지니어링" in a["company"]            # 'F02 5F' 아님
    assert a["bp_code"] == "M15X_PH4_041"
    assert a["trade"] == "UT"


def test_subcon_all_demo_inputs_parse(demo_inputs_dir):
    """demo_inputs 10개 전부 ParseError 없이 33 activities (.xlsm 포함)."""
    files = sorted(glob.glob(str(demo_inputs_dir / "*")))
    assert len(files) == 10
    for f in files:
        r = parse_daily_report(f)
        assert len(r["activities"]) == 33, f
        assert len(r["bp_summaries"]) == 1, f


def test_subcon_determinism(sample_subcon_path):
    """동일 입력 2회 → 동일 출력 (결정성)."""
    r1 = parse_daily_report(sample_subcon_path)
    r2 = parse_daily_report(sample_subcon_path)
    assert r1["activities"] == r2["activities"]
```

- [ ] **Step 3: 실패 확인**

Run: `CPIA_PARSER_VERIFY_LLM=off uv run --project pipeline python -m pytest pipeline/tests/test_parser_subcon.py -v`
Expected: 일부 FAIL 가능 — 특히 `test_subcon_e2e_golden` 의 `_extract_meta` project 추출(`업체작업일보_` prefix) 또는 LLM 검증 호출이 Azure 크레덴셜 요구로 걸릴 수 있음.

- [ ] **Step 4: LLM 검증 제거 (함수 + 의존 테스트 동시) + project prefix 보강**

LLM 검증은 무력(spec §3.4)하고 결정론 헤더 추출이 대신하므로 완전 제거. 참조처는
parse_daily_report 호출과 test_parser.py 3개뿐 — 다른 prod 참조 0 (grep 확인 완료).
함수만 지우고 의존 테스트를 안 지우면 `test_should_verify_llm_env_parsing` 이
import 단계에서 collection error → 모듈 전체 abort → Task 7 회귀 게이트 실패한다.
**반드시 함수와 테스트를 같은 커밋에서 제거:**

1. `parser.py` parse_daily_report 의 LLM 검증 호출 블록 제거 (L567-570):
   `if _should_verify_llm(): _verify_sheet1_via_llm(...); _verify_sheet4_via_llm(...)`.
2. `parser.py` 함수 정의 3개 제거: `_should_verify_llm`, `_verify_sheet1_via_llm`,
   `_verify_sheet4_via_llm` (파일 하단 "LLM 검증 wrapper" 섹션 전체).
3. 미사용이 된 import 정리: `grep -n "json\.\|sys\." pipeline/agents/parser.py` 로
   확인 후 LLM 검증에서만 쓰였으면 `import json`/`import sys` 제거 (다른 곳에서 쓰면 유지).
4. `test_parser.py` 에서 죽은 검증 테스트 3개 제거 (기능이 사라져 vacuous 통과가 됨):
   `test_parse_daily_report_llm_verify_off_skip`(L520),
   `test_parse_daily_report_llm_verify_graceful_on_error`(L528),
   `test_should_verify_llm_env_parsing`(L540). 이 셋만 쓰던 import
   (`from unittest.mock import patch`)가 다른 테스트에서 안 쓰이면 같이 제거.

`_extract_meta`(L532) project fallback: `stem.replace("통합작업일보_", "")` →
`stem.replace("통합작업일보_", "").replace("업체작업일보_", "")`.

**주의 (건드리지 말 것):** `state.py:55-56` 의 today_qty/today_cum 주석("col 11"/"col 12")은
업체포맷 컬럼 번호라 통합 코드(col 12/13)와 달라 보이지만 pre-existing·동작 무관 —
주석 고치다가 작동하는 통합 코드를 건드리지 말 것.

- [ ] **Step 5: 통과 확인**

Run: `CPIA_PARSER_VERIFY_LLM=off uv run --project pipeline python -m pytest pipeline/tests/test_parser_subcon.py -v`
Expected: 3개 테스트 전부 PASS

- [ ] **Step 6: 커밋**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser_subcon.py pipeline/tests/conftest.py pipeline/tests/test_parser.py
git commit -m "feat(parser): 업체포맷 E2E 통합 + 무력 LLM 검증 제거 (demo_inputs 10개 골든)"
```

---

## Task 7: 전체 회귀 + 통합 E2E 골든 못박기

**Files:**
- Modify: `pipeline/tests/test_parser.py` (통합 E2E 골든 건수 명시 테스트 추가)

- [ ] **Step 1: 통합 E2E 골든 테스트 추가**

`test_parser.py` 에:
```python
def test_integrated_e2e_golden_counts(sample_tong_path):
    """통합포맷 회귀 골든 — baseline 실측 4건수 못박기."""
    r = parse_daily_report(sample_tong_path)
    assert len(r["activities"]) == 1193
    assert len(r["bp_summaries"]) == 99
    assert len(r["job_allocations"]) == 975
    assert len(r["equipment_allocations"]) == 1111
```

- [ ] **Step 2: 통과 확인**

Run: `CPIA_PARSER_VERIFY_LLM=off uv run --project pipeline python -m pytest pipeline/tests/test_parser.py::test_integrated_e2e_golden_counts -v`
Expected: PASS (1193/99/975/1111)

- [ ] **Step 3: parser 회귀 — 빠른 핵심 (권장) + 선택적 전체**

**빠른 핵심** (read_only=False, 초 단위 — 이걸로 회귀 판정):
Run: `CPIA_PARSER_VERIFY_LLM=off uv run --project pipeline python -m pytest pipeline/tests/test_parser_subcon.py pipeline/tests/test_filename_parser.py pipeline/tests/test_parser_node.py pipeline/tests/test_parser_post.py pipeline/tests/test_parser.py::test_integrated_e2e_golden_counts pipeline/tests/test_parser.py::test_is_bp_code_multiformat pipeline/tests/test_parser.py::test_resolve_sheet4_columns_integrated -v`
Expected: 전부 PASS (업체 골든 33/1/76/68 + 통합 E2E 1193/99/975/1111 + 날짜 + 노드 + post).

**선택적 전체** (시트4 단위 테스트 포함 → `read_only=True` O(n²) 로 **~14분**):
Run: `CPIA_PARSER_VERIFY_LLM=off uv run --project pipeline python -m pytest pipeline/tests/test_parser.py pipeline/tests/test_parser_subcon.py pipeline/tests/test_filename_parser.py pipeline/tests/test_parser_node.py pipeline/tests/test_parser_post.py -v`
Expected: `test_parse_sheet4_required_fields` **1건만 pre-existing FAIL** (Task 3 Step 6 참조 — 통합 원본 빈 업체명, 헤더전환 무관), 나머지 전부 PASS. 이 1건은 신규 회귀가 아니므로 통과로 간주.

- [ ] **Step 4: 다운스트림 인접 테스트 회귀 (무수정 확인)**

Run: `CPIA_PARSER_VERIFY_LLM=off uv run --project pipeline python -m pytest pipeline/tests/test_parser_job_equipment_insert.py -v`
Expected: PASS (parser 출력 스키마 불변 → DB insert 회귀 없음). 실패 시 스키마 변경이 새어나간 것 — 조사.

- [ ] **Step 5: 커밋**

```bash
git add pipeline/tests/test_parser.py
git commit -m "test(parser): 통합 E2E 골든 1193/99/975/1111 못박기 + 전체 회귀"
```

---

## 완료 기준 (Definition of Done)

1. `data/demo_inputs/20250925/` 10개(.xlsm 3 포함) 전부 ParseError 없이 33 activities, work_content/unit/today_qty/company/bp_code 정상 (issue #52 해소).
2. 통합포맷 회귀 골든 1193/99/975/1111 유지.
3. parser 빠른 핵심 스위트 green (업체 골든 33/1/76/68 + 통합 E2E 골든 1193/99/975/1111 + 날짜/BP/헤더). 시트4 단위 `test_parse_sheet4_required_fields` 는 **pre-existing fail**(통합 원본 빈 업체명 31건, 헤더전환·이번 스코프 무관 — 손대지 않음).
4. 출력 스키마(`ParsedDailyReport`) 불변 — 다운스트림 무수정.

## 미해결 / 다음 (이번 비목표)

- N종 제각각 양식 LLM 2-pass 인식 레이어 (다음 브레인스토밍)
- 업체 시트6(출력일보) 작업자별 WBS → mapper 매핑 보강
- 파일명 vs 내부 작업일자 불일치 경고 로그 (선택 — 본 plan 에 미포함, 필요 시 Task 추가)
