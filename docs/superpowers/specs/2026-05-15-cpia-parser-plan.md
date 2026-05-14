# Parser 구현 Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `pipeline/agents/parser.py` 의 빈 파일을 `parse_daily_report(xlsx_path) -> ParsedDailyReport` 결정론적 구현으로 채우고, fixture loader 의 시트4 추출 로직을 이관, 골든 테스트가 시뮬 v3 패턴 (parsed_report=parsed) 으로 회귀하도록 수정, §9.4 실증 검증 스크립트까지 완성.

**Architecture:** openpyxl 단독, LLM 0회, 동기 함수. 시트4 는 fixture loader 검증 로직 이관, 시트1/2/3 은 `/tmp/cpia_full_sim_v3.py` 추출 패턴 기반 신규. 각 시트 함수는 module-private, 공개 API 1개. TDD — 각 시트 함수마다 실패 테스트 → 구현 → 통과 → 커밋. 마지막에 prod 골든 회귀 (실 Azure ~5분) + §9.4 실증 dump 로 사람 검증.

**Tech Stack:** Python 3.11 (uv 환경) / openpyxl 3.1+ / pytest-asyncio (golden 회귀용) / TypedDict (state.py 6종 그대로 사용)

**Spec reference:** `docs/superpowers/specs/2026-05-15-cpia-parser-design.md`

---

## File Structure

| 파일 | 동작 | 책임 |
|---|---|---|
| `pipeline/agents/parser.py` | **Create** (현 0 lines) | Parser 본체 — `parse_daily_report` + 시트별 헬퍼 5종 + 정규화 헬퍼 4종 + `ParseError` |
| `pipeline/tests/test_parser.py` | **Create** | Parser 단위 테스트 9건 (메타 / 시트1~4 / 정규화 / 약자변환 / ParseError / 결정성) |
| `pipeline/tests/test_mapper_golden.py` | **Modify** (line 13, 78-118, 137-143) | `_ffill` / `_load_inputs` 삭제. `parse_daily_report` import. `_match_golden` thin 헬퍼 신규. `parsed_report=parsed` 로 변경 |
| `scripts/parser_e2e_demo.py` | **Create** | §9.4 실증 검증 — Parser 출력 dump + Mapper sample 5건 dump + 체크포인트 C1~C8 |
| `pipeline/agents/__init__.py` | **Modify** | `parse_daily_report` re-export (optional, 일관성용) |

**변경 안 함:** `pipeline/state.py` (TypedDict 그대로 사용), `pipeline/agents/mapper.py` (이미 시뮬 v3 패턴으로 작성), `pipeline/db.py`, `pipeline/chroma_client.py`.

---

## Pre-flight — 시뮬 코드 정독

> spec §11 의 "보류 항목" 4개 (시트1 BP사 block 행 범위 / project 셀 위치 / 시트3 equipment_spec 컬럼 / `_match_golden` 위치) 를 구현 전에 해소. 이 단계는 코드 변경 없이 시뮬 스크립트 + 실 파일 확인만.

### Task 0: 시뮬 코드 셀 인덱스 표 확정

**Files (read-only):**
- `/tmp/cpia_full_sim_v3.py` (539 lines) — 시뮬 코드
- `/tmp/cpia_sheet23_value.py` (188 lines) — 시트2/3 값 추출 패턴
- `/tmp/cpia_parse_join.py` (170 lines) — 시트 join 패턴
- `docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx` — 실 파일 (시트명 확인)

- [ ] **Step 1: 시뮬 시트1 추출 패턴 발췌**

Run:
```bash
sed -n '110,140p' /tmp/cpia_full_sim_v3.py
```

기대 결과: `ws1 = wb2["1.출력인원 현황"]` / `ffill(rows, 4, [1,2,3,4])` / `r[2]=zone, r[3]=disc_abbrev, r[4]=company, r[7]=work_text_today, r[28]=incr, r[35]=cum` 추출 패턴 확인.

- [ ] **Step 2: 시뮬 시트2/3 추출 패턴 발췌**

Run:
```bash
grep -n "rows2\|rows3\|ws2\|ws3\|equipment_big\|equipment_mid\|equipment_spec\|workers_cum_t\|count_cum_t" /tmp/cpia_full_sim_v3.py /tmp/cpia_sheet23_value.py | head -30
```

기대 결과: 시트2 의 ffill header_end + job_type/cum_t 컬럼 인덱스, 시트3 의 equipment big/mid/spec/cum_t 컬럼 인덱스 확인.

- [ ] **Step 3: 실 파일에서 project 셀 위치 확인**

Run:
```bash
cd pipeline && uv run python3 -c "
import openpyxl
wb = openpyxl.load_workbook('../docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx', data_only=True, read_only=True)
ws = wb['1.출력인원 현황']
for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i >= 10: break
    print(i, [c for c in row[:10] if c is not None])
wb.close()
"
```

기대 결과: project 텍스트가 박힌 셀 위치 (보통 row 0~3 의 어딘가) 확인.

- [ ] **Step 4: Step 1~3 결과를 plan 안에 cell 인덱스 표로 inline 갱신**

이 Task 0 의 출력 4종 (`(시트1, company=r[4])`, `(시트2, job_type=r[X], cum_t=r[23])`, `(시트3, big=r[Y], mid=r[Z], spec=r[W], cum_t=r[23])`, `(meta, project=ws1[i][j])`) 을 Task 3/4/5/6 의 "구현" step 에 박아둘 정확한 인덱스 표로 정리. 이 단계 이후 cell 인덱스에 대한 추측 0건.

- [ ] **Step 5: 시뮬 코드와 spec §5 의 차이점 정리**

| spec §5 | 시뮬 v3 코드 | 결정 |
|---|---|---|
| BPSummary.bp_code | 시뮬 미추출 | 실 파일에서 확인 → 없으면 None |
| BPSummary.work_text_yesterday/tomorrow | 시뮬 미추출 (today 만) | 시트1 C6/C8 직접 추출 |
| BPSummary.scope | 시뮬 미추출 | 실 파일 확인 → 없으면 None |

세 필드 모두 BPSummary TypedDict 가 `| None` 허용이라 추출 실패 시 None 으로 안전 fallback.

이 Task 의 산출물은 Step 4 + Step 5 의 표 2개. plan 본문 (이 파일) 의 Task 3/4/5/6 의 cell 인덱스 자리에 inline 으로 갱신하면서 진행. Task 0 완료 후 commit 없음 (조사 단계).

---

## Task 1: 헬퍼 함수 + ParseError + `_ffill`

**Files:**
- Create: `pipeline/agents/parser.py` (헬퍼 5종 + ParseError 만 우선)
- Create: `pipeline/tests/test_parser.py` (헬퍼 단위 테스트)

- [ ] **Step 1.1: 실패 테스트 작성 — `pipeline/tests/test_parser.py`**

```python
"""Parser 단위 테스트 — docs/superpowers/specs/2026-05-15-cpia-parser-design.md §9.1."""

from __future__ import annotations

import pytest

from pipeline.agents.parser import (
    ParseError,
    _disc_abbrev_to_kr,
    _ffill,
    _is_admin_job,
    _is_total_row,
    _normalize_unit,
)


def test_normalize_unit():
    assert _normalize_unit("M2") == "m2"
    assert _normalize_unit("m2") == "m2"
    assert _normalize_unit("Ton") == "ton"
    assert _normalize_unit("ton") == "ton"
    assert _normalize_unit("M3") == "m3"
    assert _normalize_unit("") == ""
    assert _normalize_unit("EA") == "ea"


def test_disc_abbrev_to_kr():
    assert _disc_abbrev_to_kr("AR") == "건축"
    assert _disc_abbrev_to_kr("ME") == "설비"
    assert _disc_abbrev_to_kr("EL") == "전기"
    assert _disc_abbrev_to_kr("UT") == "UT"
    assert _disc_abbrev_to_kr("TE") == "공통가설"
    assert _disc_abbrev_to_kr("IN") == "제어"
    assert _disc_abbrev_to_kr("CI") == "토목"
    # 알 수 없는 약자 → 원본 보존
    assert _disc_abbrev_to_kr("XX") == "XX"
    assert _disc_abbrev_to_kr(None) is None


def test_is_admin_job():
    for job in ("BP소장", "공사관리자", "안전관리자", "품질관리자", "일반관리자"):
        assert _is_admin_job(job) is True, f"{job} 가 관리자로 인식 안 됨"
    for job in ("형틀공", "철근공", "콘크리트공", "비계공", "배관공"):
        assert _is_admin_job(job) is False, f"{job} 가 관리자로 잘못 인식"


def test_is_total_row():
    assert _is_total_row(("...", "기능공 투입 Total", 0, 0)) is True
    assert _is_total_row(("...", "BP사 투입 Total", 0, 0)) is True
    assert _is_total_row(("...", "형틀공", 100, 100)) is False
    assert _is_total_row(("...", None, 0, 0)) is False


def test_ffill_basic():
    rows = [
        ("h1", "h2", "h3", "h4", "h5"),  # header row 0
        ("h1", "h2", "h3", "h4", "h5"),  # header row 1
        ("h1", "h2", "h3", "h4", "h5"),  # header row 2
        ("h1", "h2", "h3", "h4", "h5"),  # header row 3 (header_end=4)
        ("A", "B", "C", "D", "E"),       # row 4 (1-indexed: 5)
        (None, None, None, None, "E2"),  # row 5
        ("A2", None, "C2", None, "E3"),  # row 6
    ]
    out = _ffill(rows, header_end=4, fill_cols=[0, 1, 2, 3])
    assert out == [
        (5, ["A", "B", "C", "D", "E"]),
        (6, ["A", "B", "C", "D", "E2"]),
        (7, ["A2", "B", "C2", "D", "E3"]),
    ]
```

- [ ] **Step 1.2: 테스트 실행 — 실패 확인**

Run:
```bash
cd pipeline && uv run pytest tests/test_parser.py -v 2>&1 | tail -20
```

Expected: `ImportError: cannot import name '...' from 'pipeline.agents.parser'` (parser.py 가 빈 파일이라 헬퍼 import 실패).

- [ ] **Step 1.3: `pipeline/agents/parser.py` 헬퍼 구현**

```python
"""Parser 에이전트 — 작업일보 xlsx → ParsedDailyReport.

Spec: docs/superpowers/specs/2026-05-15-cpia-parser-design.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import openpyxl

from pipeline.state import (
    Activity,
    BPSummary,
    EquipmentAllocation,
    JobAllocation,
    ParsedDailyReport,
)


class ParseError(Exception):
    """작업일보 포맷 위반."""


# spec §7 정규화 규칙 ---------------------------------------------------------

_DISC_ABBREV_TO_KR: dict[str, str] = {
    "AR": "건축",
    "ME": "설비",
    "EL": "전기",
    "UT": "UT",
    "TE": "공통가설",
    "IN": "제어",
    "CI": "토목",
}

_ADMIN_JOBS: frozenset[str] = frozenset(
    {"BP소장", "공사관리자", "안전관리자", "품질관리자", "일반관리자"}
)


def _normalize_unit(s: str) -> str:
    """단위 대소문자 통일 (M2→m2, Ton→ton)."""
    return s.lower() if s else ""


def _disc_abbrev_to_kr(abbrev: str | None) -> str | None:
    """공종 약자 → 한글 (알 수 없으면 원본 보존)."""
    if abbrev is None:
        return None
    return _DISC_ABBREV_TO_KR.get(abbrev, abbrev)


def _is_admin_job(job_type: str) -> bool:
    """관리자 직종 noise 판정 (시트2 필터)."""
    return job_type in _ADMIN_JOBS


def _is_total_row(row: tuple[Any, ...]) -> bool:
    """시트2 합계 row 판정 ('투입 Total' 포함)."""
    for cell in row:
        if isinstance(cell, str) and "투입 Total" in cell:
            return True
    return False


def _ffill(
    rows: list[tuple[Any, ...]],
    header_end: int,
    fill_cols: list[int],
) -> list[tuple[int, list[Any]]]:
    """헤더 이후 row 를 forward-fill (병합 셀 직전 값 채움).

    fixture loader (test_mapper_golden.py:63) 의 _ffill 이관.
    반환 row 번호는 1-indexed (header_end + 1 부터).
    """
    last: dict[int, Any] = {c: None for c in fill_cols}
    out: list[tuple[int, list[Any]]] = []
    for i, r in enumerate(rows[header_end:], start=header_end + 1):
        rec = list(r)
        for c in fill_cols:
            if c < len(rec) and rec[c] is not None and str(rec[c]).strip() != "":
                last[c] = rec[c]
            else:
                if c < len(rec):
                    rec[c] = last[c]
        out.append((i, rec))
    return out
```

- [ ] **Step 1.4: 테스트 통과 확인**

Run:
```bash
cd pipeline && uv run pytest tests/test_parser.py -v 2>&1 | tail -20
```

Expected: 5 passed (test_normalize_unit / test_disc_abbrev_to_kr / test_is_admin_job / test_is_total_row / test_ffill_basic).

- [ ] **Step 1.5: 커밋**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser.py
git commit -m "parser: ParseError + 정규화 헬퍼 5종 (단위/약자/관리자/Total/ffill)"
```

---

## Task 2: `_parse_sheet4_activities` (fixture loader 이관)

**Files:**
- Modify: `pipeline/agents/parser.py` (`_parse_sheet4_activities` 추가)
- Modify: `pipeline/tests/test_parser.py` (시트4 테스트 추가)

- [ ] **Step 2.1: 실패 테스트 추가**

`pipeline/tests/test_parser.py` 에 추가:

```python
from pathlib import Path
import openpyxl

from pipeline.agents.parser import _parse_sheet4_activities


@pytest.fixture(scope="module")
def sample_tong_path() -> Path:
    return Path(__file__).resolve().parents[2] / "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"


def test_parse_sheet4_activities_count(sample_tong_path: Path):
    """fixture loader 와 동일한 row 추출 — 골든 79건 포함."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["4.물량"]
    activities = _parse_sheet4_activities(ws)
    wb.close()

    # 골든 79건 모두 추출됐는지 — fixture loader 결과와 동일한 회사 분포
    assert len(activities) > 79, f"전체 row 수가 79 이하: {len(activities)}"
    companies = {a["company"] for a in activities}
    assert "남웅건설" in companies
    assert "세보엠이씨" in companies
    assert "창원기전" in companies


def test_parse_sheet4_unit_normalized(sample_tong_path: Path):
    """단위가 소문자로 정규화됐는지."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["4.물량"]
    activities = _parse_sheet4_activities(ws)
    wb.close()
    for a in activities:
        if a["unit"]:
            assert a["unit"] == a["unit"].lower(), f"unit 미정규화: {a['unit']!r}"


def test_parse_sheet4_today_qty_zero_default(sample_tong_path: Path):
    """today_qty 가 숫자 아니면 0.0 (fixture loader 동작 유지)."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["4.물량"]
    activities = _parse_sheet4_activities(ws)
    wb.close()
    for a in activities:
        assert isinstance(a["today_qty"], float)
        assert a["today_qty"] >= 0.0


def test_parse_sheet4_required_fields(sample_tong_path: Path):
    """company / work_content 가 빈 row 는 skip 됨."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["4.물량"]
    activities = _parse_sheet4_activities(ws)
    wb.close()
    for a in activities:
        assert a["company"], f"company 비어있음: {a}"
        assert a["work_content"], f"work_content 비어있음: {a}"
```

- [ ] **Step 2.2: 테스트 실행 — 실패 확인**

Run:
```bash
cd pipeline && uv run pytest tests/test_parser.py::test_parse_sheet4_activities_count -v 2>&1 | tail -10
```

Expected: `ImportError: cannot import name '_parse_sheet4_activities'`.

- [ ] **Step 2.3: `_parse_sheet4_activities` 구현 (fixture loader 이관)**

`pipeline/agents/parser.py` 에 추가 (`_ffill` 다음):

```python
def _parse_sheet4_activities(ws) -> list[Activity]:
    """시트 4 (물량) → Activity[]. fixture loader _load_inputs 이관.

    Header end = row 4. Forward-fill 컬럼 = [1, 2, 3, 4, 5] (병합 셀 패턴).
    필수 셀: r[5] (company), r[7] (work_content).
    """
    rows = _ffill(list(ws.iter_rows(values_only=True)), header_end=4, fill_cols=[1, 2, 3, 4, 5])
    activities: list[Activity] = []
    for i, r in rows:
        if not (r[5] and r[7]):
            continue
        activities.append(
            {
                "wbs_activity_id": None,
                "l5_disc": str(r[3]) if r[3] else "",
                "l6_main": None,
                "l7_sub": None,
                "l7_5_activity": None,
                "sub_work_area": None,
                "trade": str(r[3]) if r[3] else "",
                "company": str(r[5]).strip(),
                "unit": _normalize_unit(str(r[8] or "").strip()),
                "today_qty": float(r[11]) if isinstance(r[11], (int, float)) else 0.0,
                "work_content": str(r[7]).strip(),
                "conditions": [],
                "assigned_workers": 0.0,
                "worker_source": "parsed",
                "plan_total_qty": float(r[9]) if isinstance(r[9], (int, float)) else None,
                "plan_mh": None,
                "requires_review": False,
                "wa": None,
                "mapping_conf": None,
                "mapping_source": None,
            }
        )
    return activities
```

- [ ] **Step 2.4: 테스트 통과 확인**

Run:
```bash
cd pipeline && uv run pytest tests/test_parser.py -v 2>&1 | tail -15
```

Expected: 9 passed (기존 5 + 시트4 4).

- [ ] **Step 2.5: 커밋**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser.py
git commit -m "parser: _parse_sheet4_activities 이관 (fixture loader → Parser)"
```

---

## Task 3: `_parse_sheet1_bp_summaries` (신규, 시뮬 v3 패턴)

**Files:**
- Modify: `pipeline/agents/parser.py`
- Modify: `pipeline/tests/test_parser.py`

> **Task 0 산출물 참조:** 시뮬 패턴 — header_end=4, fill_cols=[1,2,3,4], r[2]=zone, r[3]=disc_abbrev, r[4]=company, r[6]=work_text_yesterday, r[7]=work_text_today, r[8]=work_text_tomorrow, r[28]=today_incr_total, r[35]=today_cum_total. bp_code/scope 는 실 파일 확인 후 None 또는 추출 위치 확정.

- [ ] **Step 3.1: 실패 테스트 추가**

```python
from pipeline.agents.parser import _parse_sheet1_bp_summaries


def test_parse_sheet1_bp_summaries_count(sample_tong_path: Path):
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["1.출력인원 현황"]
    summaries = _parse_sheet1_bp_summaries(ws)
    wb.close()
    assert len(summaries) > 0, "bp_summaries 비어있음"
    companies = {s["company"] for s in summaries}
    assert "남웅건설" in companies, f"남웅건설 없음, 추출된 회사: {sorted(companies)[:10]}"


def test_parse_sheet1_bp_summaries_fields(sample_tong_path: Path):
    """BPSummary TypedDict 의 모든 필드 존재."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["1.출력인원 현황"]
    summaries = _parse_sheet1_bp_summaries(ws)
    wb.close()
    required_keys = {
        "bp_code", "company", "disc_abbrev", "zone", "scope",
        "work_text_yesterday", "work_text_today", "work_text_tomorrow",
        "today_incr_total", "today_cum_total",
    }
    for s in summaries:
        assert required_keys <= set(s.keys()), f"누락 키: {required_keys - set(s.keys())}"
        assert isinstance(s["today_incr_total"], int)
        assert isinstance(s["today_cum_total"], int)


def test_parse_sheet1_disc_abbrev_kr(sample_tong_path: Path):
    """disc_abbrev 가 한글로 변환됐거나 None."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["1.출력인원 현황"]
    summaries = _parse_sheet1_bp_summaries(ws)
    wb.close()
    valid_kr = {"건축", "설비", "전기", "UT", "공통가설", "제어", "토목"}
    for s in summaries:
        if s["disc_abbrev"] is not None:
            # 한글 변환 됐거나 원본 보존 (모르는 약자 fallback)
            assert s["disc_abbrev"] in valid_kr or len(s["disc_abbrev"]) <= 5
```

- [ ] **Step 3.2: 실패 확인**

Run:
```bash
cd pipeline && uv run pytest tests/test_parser.py::test_parse_sheet1_bp_summaries_count -v 2>&1 | tail -10
```

Expected: ImportError.

- [ ] **Step 3.3: 구현 (시뮬 v3 패턴 기반)**

```python
def _parse_sheet1_bp_summaries(ws) -> list[BPSummary]:
    """시트 1 (출력인원 현황) → BPSummary[]. 시뮬 v3 패턴 기반."""
    rows = _ffill(list(ws.iter_rows(values_only=True)), header_end=4, fill_cols=[1, 2, 3, 4])
    summaries: list[BPSummary] = []
    for _i, r in rows:
        if not r[4]:  # company 비어있으면 skip
            continue
        company = str(r[4]).strip()
        if not company:
            continue
        summaries.append(
            {
                "bp_code": None,  # spec §11: 실 파일 확인 후 추출 위치 확정 — 우선 None
                "company": company,
                "disc_abbrev": _disc_abbrev_to_kr(str(r[3]).strip()) if r[3] else None,
                "zone": str(r[2]).strip() if r[2] else None,
                "scope": None,  # spec §11: 실 파일 확인 후 — 우선 None
                "work_text_yesterday": str(r[6]).strip() if r[6] else None,
                "work_text_today": str(r[7]).strip() if r[7] else None,
                "work_text_tomorrow": str(r[8]).strip() if r[8] else None,
                "today_incr_total": int(r[28]) if isinstance(r[28], (int, float)) else 0,
                "today_cum_total": int(r[35]) if isinstance(r[35], (int, float)) else 0,
            }
        )
    return summaries
```

- [ ] **Step 3.4: 통과 확인**

Run:
```bash
cd pipeline && uv run pytest tests/test_parser.py -v 2>&1 | tail -20
```

Expected: 12 passed.

- [ ] **Step 3.5: 커밋**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser.py
git commit -m "parser: _parse_sheet1_bp_summaries 신규 (시뮬 v3 패턴)"
```

---

## Task 4: `_parse_sheet2_job_allocations` (noise 필터)

> **Task 0 산출물 참조:** 시트2 셀 인덱스를 Task 0 Step 2 결과로 확정. 시뮬 패턴 우선 사용.

- [ ] **Step 4.1: 실패 테스트 추가**

```python
from pipeline.agents.parser import _parse_sheet2_job_allocations


def test_parse_sheet2_no_admin_jobs(sample_tong_path: Path):
    """관리자 직종 0건 (필터 작동)."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["2.직종별 인원현황"]
    jobs = _parse_sheet2_job_allocations(ws)
    wb.close()
    admin = {"BP소장", "공사관리자", "안전관리자", "품질관리자", "일반관리자"}
    for j in jobs:
        assert j["job_type"] not in admin, f"관리자 직종 누락 안 됨: {j}"


def test_parse_sheet2_no_total_rows(sample_tong_path: Path):
    """합계 row 0건."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["2.직종별 인원현황"]
    jobs = _parse_sheet2_job_allocations(ws)
    wb.close()
    for j in jobs:
        assert "투입 Total" not in (j.get("job_type") or ""), f"Total row 누락 안 됨: {j}"


def test_parse_sheet2_workers_cum_t_int(sample_tong_path: Path):
    """workers_cum_t 가 int."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["2.직종별 인원현황"]
    jobs = _parse_sheet2_job_allocations(ws)
    wb.close()
    for j in jobs:
        assert isinstance(j["workers_cum_t"], int)
        assert j["workers_cum_t"] >= 0
```

- [ ] **Step 4.2: 실패 확인**

Run:
```bash
cd pipeline && uv run pytest tests/test_parser.py::test_parse_sheet2_no_admin_jobs -v 2>&1 | tail -10
```

- [ ] **Step 4.3: 구현 (Task 0 Step 2 결과 cell 인덱스 사용)**

```python
def _parse_sheet2_job_allocations(ws) -> list[JobAllocation]:
    """시트 2 (직종별 인원현황) → JobAllocation[]. 관리자 직종/합계 row 필터.

    cell 인덱스 (Task 0 Step 2 시뮬 발췌 기준):
      r[3] = disc_abbrev, r[4] = company, r[5] = job_type, r[23] = workers_cum_t.
    header_end = 5, fill_cols = [1, 2, 3, 4]. 실 파일 검증 단계에서 조정 가능.
    """
    rows = _ffill(list(ws.iter_rows(values_only=True)), header_end=5, fill_cols=[1, 2, 3, 4])
    jobs: list[JobAllocation] = []
    for _i, r in rows:
        if _is_total_row(tuple(r)):
            continue
        company = str(r[4]).strip() if r[4] else ""
        job_type = str(r[5]).strip() if len(r) > 5 and r[5] else ""
        if not (company and job_type):
            continue
        if _is_admin_job(job_type):
            continue
        cum_t = int(r[23]) if len(r) > 23 and isinstance(r[23], (int, float)) else 0
        jobs.append(
            {
                "bp_code": None,
                "company": company,
                "disc_abbrev": _disc_abbrev_to_kr(str(r[3]).strip()) if r[3] else None,
                "job_type": job_type,
                "workers_cum_t": cum_t,
            }
        )
    return jobs
```

- [ ] **Step 4.4: 통과 확인**

Run:
```bash
cd pipeline && uv run pytest tests/test_parser.py -v 2>&1 | tail -20
```

Expected: 15 passed.

> **주의:** Step 4.3 의 cell 인덱스 (r[3], r[4], r[5], r[23]) 가 Task 0 Step 2 결과와 다르면 위 구현을 그 결과로 조정. 실 파일에서 추출 0건 나오면 인덱스 보정.

- [ ] **Step 4.5: 커밋**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser.py
git commit -m "parser: _parse_sheet2_job_allocations + noise 필터 (관리자/Total)"
```

---

## Task 5: `_parse_sheet3_equipment_allocations`

> **Task 0 산출물 참조:** 시트3 의 big/mid/spec/cum_t 컬럼 인덱스.

- [ ] **Step 5.1: 실패 테스트 추가**

```python
from pipeline.agents.parser import _parse_sheet3_equipment_allocations


def test_parse_sheet3_count(sample_tong_path: Path):
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["3.장비현황"]
    eqs = _parse_sheet3_equipment_allocations(ws)
    wb.close()
    assert len(eqs) > 0, "장비 0건"


def test_parse_sheet3_big_mid_filled(sample_tong_path: Path):
    """첫 5건의 equipment_big, equipment_mid 가 None 아님."""
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["3.장비현황"]
    eqs = _parse_sheet3_equipment_allocations(ws)
    wb.close()
    for e in eqs[:5]:
        assert e["equipment_big"], f"equipment_big 비어있음: {e}"
        assert e["equipment_mid"], f"equipment_mid 비어있음: {e}"


def test_parse_sheet3_count_cum_t_int(sample_tong_path: Path):
    wb = openpyxl.load_workbook(sample_tong_path, data_only=True, read_only=True)
    ws = wb["3.장비현황"]
    eqs = _parse_sheet3_equipment_allocations(ws)
    wb.close()
    for e in eqs:
        assert isinstance(e["count_cum_t"], int)
        assert e["count_cum_t"] >= 0
```

- [ ] **Step 5.2: 실패 확인**

Run:
```bash
cd pipeline && uv run pytest tests/test_parser.py::test_parse_sheet3_count -v 2>&1 | tail -10
```

- [ ] **Step 5.3: 구현**

```python
def _parse_sheet3_equipment_allocations(ws) -> list[EquipmentAllocation]:
    """시트 3 (장비현황) → EquipmentAllocation[].

    cell 인덱스 (Task 0 Step 2 시뮬 발췌 기준):
      r[4] = company, r[5] = equipment_big, r[6] = equipment_mid, r[7] = equipment_spec,
      r[23] = count_cum_t. header_end = 5, fill_cols = [1, 2, 3, 4, 5].
    """
    rows = _ffill(list(ws.iter_rows(values_only=True)), header_end=5, fill_cols=[1, 2, 3, 4, 5])
    eqs: list[EquipmentAllocation] = []
    for _i, r in rows:
        if _is_total_row(tuple(r)):
            continue
        company = str(r[4]).strip() if r[4] else ""
        big = str(r[5]).strip() if len(r) > 5 and r[5] else ""
        mid = str(r[6]).strip() if len(r) > 6 and r[6] else ""
        if not (company and big and mid):
            continue
        spec = str(r[7]).strip() if len(r) > 7 and r[7] else None
        cum_t = int(r[23]) if len(r) > 23 and isinstance(r[23], (int, float)) else 0
        eqs.append(
            {
                "bp_code": None,
                "company": company,
                "equipment_big": big,
                "equipment_mid": mid,
                "equipment_spec": spec,
                "count_cum_t": cum_t,
            }
        )
    return eqs
```

- [ ] **Step 5.4: 통과 확인**

Run:
```bash
cd pipeline && uv run pytest tests/test_parser.py -v 2>&1 | tail -20
```

Expected: 18 passed.

- [ ] **Step 5.5: 커밋**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser.py
git commit -m "parser: _parse_sheet3_equipment_allocations 신규"
```

---

## Task 6: `_extract_meta` + `parse_daily_report` 공개 API

**Files:**
- Modify: `pipeline/agents/parser.py` (공개 API 조립)
- Modify: `pipeline/tests/test_parser.py` (메타 / 통합 / 결정성 / ParseError 테스트)

- [ ] **Step 6.1: 실패 테스트 추가**

```python
import re

from pipeline.agents.parser import parse_daily_report


def test_parse_meta(sample_tong_path: Path):
    parsed = parse_daily_report(sample_tong_path)
    assert parsed["report_date"] == "2025-09-25"
    assert parsed["project"], f"project 비어있음: {parsed['project']!r}"
    assert "M15X" in parsed["project"] or "IBL" in parsed["project"]


def test_parse_daily_report_integration(sample_tong_path: Path):
    """공개 API — 4시트 통합 ParsedDailyReport."""
    parsed = parse_daily_report(sample_tong_path)
    assert len(parsed["bp_summaries"]) > 0
    assert len(parsed["job_allocations"]) > 0
    assert len(parsed["equipment_allocations"]) > 0
    assert len(parsed["activities"]) > 79  # 골든 79건 포함 + 그 외


def test_parse_determinism(sample_tong_path: Path):
    """같은 xlsx 2회 호출 → 동일 dict (결정성)."""
    p1 = parse_daily_report(sample_tong_path)
    p2 = parse_daily_report(sample_tong_path)
    assert p1 == p2


def test_parse_error_missing_sheet(tmp_path):
    """시트 누락 → ParseError."""
    bad_path = tmp_path / "broken.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "wrong_sheet"
    wb.save(bad_path)
    with pytest.raises(ParseError):
        parse_daily_report(bad_path)
```

- [ ] **Step 6.2: 실패 확인**

Run:
```bash
cd pipeline && uv run pytest tests/test_parser.py::test_parse_meta -v 2>&1 | tail -10
```

- [ ] **Step 6.3: 구현 (공개 API + 메타 추출)**

`pipeline/agents/parser.py` 에 추가 (모듈 맨 아래):

```python
_DATE_PATTERN = re.compile(r"_(\d{4})(\d{2})(\d{2})\.xlsx$|_(\d{6})\.xlsm?$")


def _extract_meta(xlsx_path: Path, wb) -> tuple[str, str]:
    """파일명 → report_date, 시트1 → project. 둘 다 실패 시 ParseError."""
    m = _DATE_PATTERN.search(xlsx_path.name)
    if m:
        if m.group(1):
            report_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        else:
            ymd = m.group(4)  # YYMMDD
            report_date = f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:6]}"
    else:
        raise ParseError(f"파일명에서 날짜 추출 실패: {xlsx_path.name}")

    # project — 시트1 의 상단 메타 셀에서 추출 (Task 0 Step 3 결과로 cell 위치 확정)
    project = ""
    if "1.출력인원 현황" in wb.sheetnames:
        ws1 = wb["1.출력인원 현황"]
        # Task 0 Step 3 결과 cell 위치 (예: row 1, col 0~5 의 어딘가)
        for row in list(ws1.iter_rows(min_row=1, max_row=3, values_only=True)):
            for cell in row:
                if isinstance(cell, str) and ("M15X" in cell or "IBL" in cell or "PJT" in cell):
                    project = cell.strip()
                    break
            if project:
                break

    if not project:
        # fallback — 파일명 일부
        stem = xlsx_path.stem
        project = stem.replace("통합작업일보_", "").rsplit("_", 1)[0].strip()
        if not project:
            raise ParseError(f"project 추출 실패: {xlsx_path.name}")

    return report_date, project


def parse_daily_report(xlsx_path: Path) -> ParsedDailyReport:
    """작업일보 xlsx 1개 → 4시트 통합 ParsedDailyReport.

    Args:
        xlsx_path: 통합작업일보 xlsx 절대 경로.

    Returns:
        ParsedDailyReport — spec §3 참조.

    Raises:
        ParseError: 시트명 누락, report_date/project 추출 실패.
    """
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)

    required_sheets = {"1.출력인원 현황", "2.직종별 인원현황", "3.장비현황", "4.물량"}
    missing = required_sheets - set(wb.sheetnames)
    if missing:
        wb.close()
        raise ParseError(f"시트 누락: {sorted(missing)}")

    report_date, project = _extract_meta(xlsx_path, wb)

    bp_summaries = _parse_sheet1_bp_summaries(wb["1.출력인원 현황"])
    job_allocations = _parse_sheet2_job_allocations(wb["2.직종별 인원현황"])
    equipment_allocations = _parse_sheet3_equipment_allocations(wb["3.장비현황"])
    activities = _parse_sheet4_activities(wb["4.물량"])

    wb.close()

    return {
        "report_date": report_date,
        "project": project,
        "bp_summaries": bp_summaries,
        "job_allocations": job_allocations,
        "equipment_allocations": equipment_allocations,
        "activities": activities,
    }
```

import 부분 (`re`) 도 파일 상단에 추가 필요:

```python
import re
from pathlib import Path
```

- [ ] **Step 6.4: 통과 확인**

Run:
```bash
cd pipeline && uv run pytest tests/test_parser.py -v 2>&1 | tail -25
```

Expected: 22 passed (기존 18 + 메타 1 + 통합 1 + 결정성 1 + ParseError 1).

- [ ] **Step 6.5: 커밋**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser.py
git commit -m "parser: 공개 API parse_daily_report + _extract_meta + 결정성/ParseError 테스트"
```

---

## Task 7: 골든 테스트 수정 (시뮬 v3 패턴 복원)

**Files:**
- Modify: `pipeline/tests/test_mapper_golden.py:13` (import 추가), `:63-118` (`_ffill`/`_load_inputs` 삭제), `:137-143` (`parse_daily_report` 호출 + `parsed_report=parsed`)

- [ ] **Step 7.1: `test_mapper_golden.py` 수정**

기존 line 13:
```python
import openpyxl
```
→ 삭제 (parser 가 이미 들고 있음).

기존 line 17:
```python
from pipeline.state import Activity
```
→ 추가:
```python
from pipeline.state import Activity
from pipeline.agents.parser import parse_daily_report
```

기존 line 63-118 (`_ffill` + `_load_inputs`) → **전체 삭제**.

대신 thin 헬퍼 추가:
```python
def _match_golden(activities: list[Activity], wb_path: Path) -> list[tuple[int, Activity]]:
    """Parser activities → 골든 row 번호 매칭. test_mapper_golden 전용 헬퍼.

    Parser 는 row 번호를 노출하지 않으므로 여기서 시트4 를 한 번 더 읽어
    (company, work_content) → row index 매핑을 만들고 GOLDEN dict 의 key 와 join.
    """
    import openpyxl as _openpyxl
    wb = _openpyxl.load_workbook(wb_path, data_only=True, read_only=True)
    ws = wb["4.물량"]
    row_map: dict[tuple[str, str], int] = {}
    for i, r in enumerate(ws.iter_rows(values_only=True), start=1):
        if i <= 4:
            continue
        if r[5] and r[7]:
            key = (str(r[5]).strip(), str(r[7]).strip())
            row_map.setdefault(key, i)
    wb.close()

    matched: list[tuple[int, Activity]] = []
    for a in activities:
        row = row_map.get((a["company"], a["work_content"]))
        if row is not None and row in GOLDEN:
            matched.append((row, a))
    return matched
```

기존 line 137-143 (test 본문) 수정:
```python
    parsed = parse_daily_report(sample_tong_path)
    inputs = _match_golden(parsed["activities"], sample_tong_path)
    assert len(inputs) == 79, f"골든 입력 수 불일치: {len(inputs)}"

    correct = 0
    wrong: list[tuple[int, str, str, str | None, float | None]] = []
    for row, activity in inputs:
        result = await map_activity(activity, parsed_report=parsed, cfg=cfg)  # ← parsed
        ...
```

- [ ] **Step 7.2: 골든 회귀 실행 (실 Azure ~5분, ~$0.02)**

Run:
```bash
cd pipeline && uv run pytest tests/test_mapper_golden.py -m golden -s -v 2>&1 | tail -30
```

Expected:
```
[golden] 정확도: 78/79 = 98.7%   (또는 그 이상)
PASSED   (in ~285s)
```

**판정 기준:**
- ≥ 95% → spec §1.1 베이스라인 충족, plan 진행
- < 95% → fail. 시트1~3 컨텍스트로 인한 정확도 후퇴 → Task 0 Step 2 의 cell 인덱스 재검증 (가짜 컨텍스트가 들어갔을 가능성)

- [ ] **Step 7.3: 결과 보고 (Iron Law 3요소)**

CLAUDE.md §3.4 형식으로 보고:
```
$ uv run pytest tests/test_mapper_golden.py -m golden -s -v
<pytest 출력 원본 그대로 (수정·생략 X)>
→ <결론: 베이스라인 동등 / 개선 / 후퇴>
```

- [ ] **Step 7.4: 커밋**

```bash
git add pipeline/tests/test_mapper_golden.py
git commit -m "test: 골든 회귀 — fixture loader 제거, parse_daily_report 호출 (시뮬 v3 패턴 복원)"
```

---

## Task 8: `scripts/parser_e2e_demo.py` (§9.4 실증 검증)

**Files:**
- Create: `scripts/parser_e2e_demo.py`

- [ ] **Step 8.1: 스크립트 작성**

```python
"""Parser → Mapper E2E 실 출력 dump — spec §9.4.

사용:
  uv run python3 scripts/parser_e2e_demo.py <xlsx_path> [--sample-rows R1,R2,...]

사람이 stdout 으로 검증할 체크포인트 C1~C8.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# project root 를 sys.path 에 추가
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from pipeline.agents.mapper import MapperConfig, build_bp_context, map_activity
from pipeline.agents.parser import parse_daily_report


GOLDEN_DEFAULTS = "99,452,892,1207,1230"
GOLDEN = {
    99: ("남웅건설", "철근콘크리트공사"),
    452: ("세보엠이씨", "ACID배기설비공사"),
    892: ("창원기전", "전등설비공사"),
    1207: ("세보엠이씨", "기계소화설비"),
    1230: ("창원기전", "전기소화설비"),
}


def dump_parser_output(parsed) -> None:
    print("=== Parser 출력 ===")
    print(f"report_date: {parsed['report_date']}")
    print(f"project:     {parsed['project']}")
    print()

    print(f"bp_summaries: {len(parsed['bp_summaries'])}건")
    for s in parsed["bp_summaries"][:5]:
        wt = (s["work_text_today"] or "")[:80]
        print(
            f"  {s['company']} ({s['bp_code'] or 'no-code'}) / "
            f"{s['disc_abbrev'] or '-'} / {s['zone'] or '-'}"
        )
        print(f"    work_text_today: '{wt}'")
        print(f"    today_incr: {s['today_incr_total']}, today_cum: {s['today_cum_total']}")
    print()

    print(f"job_allocations: {len(parsed['job_allocations'])}건 (관리자/Total 필터 후)")
    for j in parsed["job_allocations"][:5]:
        print(f"  {j['company']} / {j['job_type']} / cum_t={j['workers_cum_t']}")
    print()

    print(f"equipment_allocations: {len(parsed['equipment_allocations'])}건")
    for e in parsed["equipment_allocations"][:5]:
        print(
            f"  {e['company']} / {e['equipment_big']} / {e['equipment_mid']} / "
            f"{e['equipment_spec'] or '-'} / cum_t={e['count_cum_t']}"
        )
    print()

    print(f"activities: {len(parsed['activities'])}건 (필수 셀 검증 후)")
    for a in parsed["activities"][:5]:
        print(
            f"  {a['company']} / '{a['work_content']}' / {a['unit']} / "
            f"today_qty={a['today_qty']}"
        )
    print()


def check_postconditions(parsed) -> tuple[int, list[str]]:
    """체크포인트 C1~C5 자동 검증. (합격 개수, 실패 메시지 리스트) 반환."""
    failures: list[str] = []

    if len(parsed["bp_summaries"]) < 1:
        failures.append("C1: bp_summaries 비어있음")

    admin = {"BP소장", "공사관리자", "안전관리자", "품질관리자", "일반관리자"}
    if any(j["job_type"] in admin for j in parsed["job_allocations"]):
        failures.append("C2: 관리자 직종 누락 안 됨")

    if any("투입 Total" in (j["job_type"] or "") for j in parsed["job_allocations"]):
        failures.append("C3: Total row 누락 안 됨")

    for e in parsed["equipment_allocations"][:5]:
        if not e["equipment_big"]:
            failures.append(f"C4: equipment_big 비어있음 — {e}")
            break

    if len(parsed["activities"]) < 79:
        failures.append(f"C5: activities {len(parsed['activities'])} < 79 (골든 누락)")

    passed = 5 - len(failures)
    return passed, failures


async def dump_mapper_samples(parsed, sample_rows: list[int], cfg: MapperConfig) -> int:
    """Mapper 호출 결과 dump. (build_bp_context fallback 발생 건수) 반환."""
    print("=== Mapper 호출 (sample 5건 — 시뮬 v3 패턴 복원) ===")
    print()

    fallback_hits = 0

    # row → activity 매핑
    import openpyxl as _xlsx
    wb = _xlsx.load_workbook(parsed.get("__xlsx_path__"), data_only=True, read_only=True) \
        if parsed.get("__xlsx_path__") else None

    correct = 0
    for row in sample_rows:
        if row not in GOLDEN:
            print(f"[R{row}] GOLDEN 미정의, skip")
            continue
        golden_company, golden_l6 = GOLDEN[row]
        match = next(
            (a for a in parsed["activities"] if a["company"] == golden_company),
            None,
        )
        if not match:
            print(f"[R{row}] {golden_company} 의 Activity 없음")
            continue

        ctx = build_bp_context(match["company"], parsed)
        if "parsed_report 미제공" in ctx:
            fallback_hits += 1

        result = await map_activity(match, parsed_report=parsed, cfg=cfg)
        ok = result["l6_main"] == golden_l6
        if ok:
            correct += 1

        print(
            f"[R{row}] {match['company']} / '{match['work_content']}' / {match['unit']} / "
            f"today_qty={match['today_qty']}"
        )
        print(f"  → 골든:   {golden_l6}")
        print(
            f"  → 결과:   {result['l6_main']} / conf {result['mapping_conf']} / "
            f"source: {result['mapping_source']} {'✓' if ok else '✗'}"
        )
        print(f"  → BP 컨텍스트 (mapper.build_bp_context):")
        for line in ctx.splitlines():
            print(f"    {line}")
        print()

    print(f"=== 베이스라인 대비 ===")
    print(f"baseline (parsed_report=None, 2026-05-15):     78/79 = 98.7%")
    print(f"sample (parsed_report=parsed, {len(sample_rows)}건):           {correct}/{len(sample_rows)}")
    print()

    return fallback_hits


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx_path", type=Path)
    ap.add_argument("--sample-rows", default=GOLDEN_DEFAULTS)
    args = ap.parse_args()

    parsed = parse_daily_report(args.xlsx_path)
    parsed["__xlsx_path__"] = args.xlsx_path

    dump_parser_output(parsed)

    passed, failures = check_postconditions(parsed)
    print(f"=== 체크포인트 C1~C5 (Parser 단독) — {passed}/5 통과 ===")
    for f in failures:
        print(f"  ✗ {f}")
    print()

    sample_rows = [int(x) for x in args.sample_rows.split(",")]

    cfg = MapperConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
        embedding_model=os.environ["EMBEDDING_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
    )

    fallback_hits = await dump_mapper_samples(parsed, sample_rows, cfg)
    print(f"=== 체크포인트 C6 — fallback 메시지 {fallback_hits}건 (목표 0건) ===")
    print()

    # C7 — sample 5건 매핑 결과 (위에서 print 됨)
    # C8 — 결정성 (2회 호출 동일)
    parsed2 = parse_daily_report(args.xlsx_path)
    parsed2["__xlsx_path__"] = args.xlsx_path
    parsed.pop("__xlsx_path__", None)
    parsed2.pop("__xlsx_path__", None)
    determinism = parsed == parsed2
    print(f"=== 체크포인트 C8 — 결정성 (2회 호출 동일): {'✓ pass' if determinism else '✗ FAIL'} ===")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 8.2: 실행 (실 Azure ~30초 — 5건만)**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && uv run python3 scripts/parser_e2e_demo.py \
  "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx" 2>&1 | tee /tmp/parser_e2e_output.txt
```

- [ ] **Step 8.3: 체크포인트 C1~C8 결과 보고 (Iron Law 3요소)**

```
$ uv run python3 scripts/parser_e2e_demo.py docs/sample/통합작업일보_...xlsx
<위 스크립트의 stdout 원본 그대로 — Parser dump + Mapper dump + 체크포인트 결과>
→ 체크포인트 C1~C8 X/8 합격. C6 (fallback 0건) 확인 → 시뮬 v3 패턴 복원 성공.
```

- [ ] **Step 8.4: 커밋**

```bash
git add scripts/parser_e2e_demo.py
git commit -m "scripts: Parser → Mapper E2E 실 출력 dump (spec §9.4 체크포인트 C1~C8)"
```

---

## Task 9: 최종 정리 + 코드 리뷰 + PR

**Files:**
- Modify: `pipeline/agents/__init__.py` (re-export, optional)
- Review: `pipeline/agents/parser.py`, `pipeline/tests/test_parser.py`, `pipeline/tests/test_mapper_golden.py`, `scripts/parser_e2e_demo.py`

- [ ] **Step 9.1: `pipeline/agents/__init__.py` 갱신 (optional)**

```python
from pipeline.agents.mapper import map_activity, MapperConfig
from pipeline.agents.parser import parse_daily_report, ParseError

__all__ = ["map_activity", "MapperConfig", "parse_daily_report", "ParseError"]
```

- [ ] **Step 9.2: 자동 리뷰 병렬 실행 (memory feedback_auto_review)**

사용자 메모리 `feedback_auto_review` 룰: 의미 있는 변경 완료 시 Python / correctness / performance 리뷰어 병렬 실행.

3개 subagent 병렬 dispatch:
- `kieran-python-reviewer` — Python 패턴 / 타입 / 유지보수성
- `correctness-reviewer` — 로직 오류 / 엣지 케이스
- `performance-reviewer` — 알고리즘 복잡도 / I/O 패턴

각 리뷰어에게 review 대상 파일 4개 명시. 결과 합쳐서 사용자 보고.

- [ ] **Step 9.3: 리뷰 피드백 반영**

리뷰어가 지적한 이슈 중 합당한 것 fix. 불합당하다고 판단한 것은 push back 메모. 각 fix 후 `pytest tests/test_parser.py -v` 재실행.

- [ ] **Step 9.4: 전체 회귀 한 번 더**

Run:
```bash
cd pipeline && uv run pytest -v 2>&1 | tail -30
```

Expected: 전체 테스트 통과 (test_parser 22건 + test_mapper_golden 1건 + 기존 테스트).

- [ ] **Step 9.5: 최종 커밋 + PR (사용자 확인 후)**

```bash
git log --oneline A_Track ^main | head -20
```

A_Track 의 Parser 관련 커밋 묶음 확인 후, 사용자에게 PR 생성 동의 요청:
- "main 으로 PR 만들까요? 아니면 A_Track 에 더 쌓을까요?"

사용자 동의 시:
```bash
gh pr create --base main --head A_Track --title "feat(parser): Parser 에이전트 — Collector → Parser → Mapper prod 흐름 완성" --body "..."
```

---

## Plan Review

`plan-document-reviewer` 자동 dispatch 대신 self-review checklist 로 진행 (사용자 환경에 superpowers:plan-document-reviewer subagent 미설치). self-review 후 사용자 검토 게이트.

**self-review checklist:**
- [ ] 모든 Task 에 파일 경로 (Create/Modify/Test) 명시
- [ ] 모든 Step 이 2-5분 단위 atomic action
- [ ] TDD 사이클 (실패 테스트 → 실패 확인 → 구현 → 통과 확인 → 커밋) 일관
- [ ] 코드 블록이 placeholder 가 아닌 실제 구현 가능 코드
- [ ] 명령어가 expected output 과 함께 명시
- [ ] spec §9 의 9개 테스트 + §9.4 실증 검증 모두 plan task 에 매핑
- [ ] 한자 0건

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/specs/2026-05-15-cpia-parser-plan.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — Task 별 fresh subagent dispatch, 사용자 review 게이트 사이사이. fast iteration, 토큰 격리.

**2. Inline Execution** — 현 세션에서 Task 순차 실행, batch checkpoint. 토큰 사용 큼.

**어느 방식으로 진행할까요?**

---

## 변경 이력

| 날짜 | 내용 | 작성자 |
|---|---|---|
| 2026-05-15 | 초안 — Task 0 (pre-flight) + Task 1~9 (TDD step) + plan review + execution handoff | A 트랙 |
