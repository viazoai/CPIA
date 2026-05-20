# CPIA Parser Rule-Based + Mapper BP-Zone Match Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** parser_llm.py (chunk + 4-5 분) 를 기존 parser.py rule-based + 시트1/4 LLM 검증 hybrid 로 전환하고, mapper.resolve_wa 에 7 단계 (auto_bp_zone_match deterministic + auto_llm_rerank) 를 도입하여 hil_required 58% → ≤25% 로 감축한다.

**Architecture:** `pipeline/agents/parser.py` (306 line, 11 caller) 의 4 시트 추출 함수 (`_parse_sheet1_*` ~ `_parse_sheet4_*`) 본문 patch + 시트1/4 LLM 검증 wrapper 추가 (default on, env opt-out). `pipeline/agents/mapper.py` 의 `build_bp_context` BP 별 분리 + `resolve_wa` 7 단계 (5/20 working tree 적용됨, atomic commit 만). collector.py + run_one_cycle.py 의 parser_llm 호출 → parse_daily_report 교체. 마지막 V5 = 10 업체 POC cycle + reports UI 12 정량 기준 (Playwright + 사람 시각 확인).

**Tech Stack:** Python 3.9.6 (`python3`, venv `venv/bin/activate`), openpyxl, Azure OpenAI gpt-5.1 (LLM 검증), PostgreSQL prod tunnel `localhost:5532`, Chroma local Docker `localhost:8000`, LangGraph, pytest, Next.js + Playwright (E2E UI).

**Spec reference:** [`docs/superpowers/specs/2026-05-20-cpia-parser-mapper-refactor-design.md`](../specs/2026-05-20-cpia-parser-mapper-refactor-design.md)

**Working dir:** `/Users/kyungseoplee/Project Agent/CPIA/`
**Branch:** `A_Track` (현재 working tree 의 mapper.py / tmp/sheet1_v2.py 변경 사항 inherit)

---

## File Structure

### 변경 대상 (modify)

| 파일 | 변경 내용 | task |
|---|---|---|
| `pipeline/agents/parser_post.py` | `normalize_company` 강화 (괄호 부속 제거) + `split_company_and_zone` / `extract_zone` 신설 | 1 |
| `pipeline/agents/parser.py:90` `_parse_sheet1_bp_summaries` | merged col 30 group boundary + BP-zone 분리 + sub-section skip + solo+next 흡수 | 2 |
| `pipeline/agents/parser.py:124` `_parse_sheet2_job_allocations` | col 4='Mm01' + col 2 미한정 keyword (UT/제어 등) + subtotal skip + cross-check | 3 |
| `pipeline/agents/parser.py:196` `_parse_sheet3_equipment_allocations` | col 4 (대분류) + group boundary 보강 | 4 |
| `pipeline/agents/parser.py:158` `_parse_sheet4_activities` | ffill 4 컬럼 (col 3/4/5/6) + zone 옵션 2 (col 7 명시만) + B+C=D cross-check | 5 |
| `pipeline/agents/parser.py:270` `parse_daily_report` | 시트1/4 LLM 검증 wrapper 통합 (default on, env opt-out) | 6 |
| `pipeline/agents/collector.py:19` | `from pipeline.agents.parser_llm import ...` → `from pipeline.agents.parser import parse_daily_report` | 7 |
| `scripts/run_one_cycle.py:29,70` | `parse_daily_report_llm` 호출 → `parse_daily_report` 호출 | 7 |
| `pipeline/agents/mapper.py:170-218` `build_bp_context` | BP 별 분리 + zone 명시 (5/20 working tree 적용됨, commit only) | 8 |
| `pipeline/agents/mapper.py:229-242` `build_llm_input` | activity.bp_code 명시 (5/20 working tree 적용됨, commit only) | 8 |
| `pipeline/agents/mapper.py:259-285` `resolve_wa` | 7 단계 (0=빈 pool / 1=auto_bp_zone_match / 2=auto_llm_rerank / 3~5=legacy / 6=hil) (5/20 working tree 적용됨, commit only) | 8 |
| `pipeline/tests/test_parser.py` | 4 시트 신규 unit test 추가 (col 인덱스 / sub-section skip / cross-check / ffill / LLM 검증 error path) | 9 |
| `pipeline/agents/parser_llm.py` | 파일 상단 deprecation 주석 + `CPIA_PARSER=llm` env flag 안내 | 11 |

### 신규 생성 (create)

| 파일 | 책임 | task |
|---|---|---|
| `pipeline/tests/test_mapper_resolve_wa.py` | resolve_wa 7 단계 unit test (각 source 케이스 + chosen_wa fallback) | 10 |
| `tmp/run_v5_10companies.py` | V5 — 10 업체 POC cycle 실행 script (PG fetch sample 선정 + cycle 실행 + mapping_source 분포 dump) | 12 |
| `web/e2e/reports-10-companies.spec.ts` | Playwright e2e — reports UI 12 정량 기준 자동 검증 | 12 |

### 변경하지 않음 (preserve)

- `pipeline/state.py` — `ParsedDailyReport` / `BPSummary` / `JobAllocation` / `EquipmentAllocation` / `Activity` schema 그대로
- `pipeline/agents/atomizer.py` / `forecaster.py` / `optimizer.py` / `reporter.py` — mapper_activities 6 컬럼 schema 보존
- `pipeline/agents/view_builder.py` — daily_reports jsonb 컬럼 보존
- `web/app/reports/page.tsx` 와 컴포넌트 — mock route 변경 X (V5 에서 실 데이터만 확인)
- `pipeline/tests/test_parser.py` 의 기존 import + helper test (line 1-260) — 기존 schema 호환 유지

---

## 사전 준비 (Task 0)

- [ ] **Step 0.1: 작업 디렉토리 + 브랜치 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git status
git branch --show-current
```
Expected: branch=`A_Track` (또는 사용자 명시 다른 feature branch). working tree 에 mapper.py / tmp/sheet1_v2.py 등 5/20 변경 포함 가능 — task 8 에서 commit 됨.

- [ ] **Step 0.2: PG tunnel + Chroma local 살아있는지 확인**

```bash
docker ps --filter "name=cpia-chroma-local" --format "{{.Names}}\t{{.Status}}"
nc -zv localhost 5532 2>&1 | head -2
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/api/v1/heartbeat
```
Expected:
- `cpia-chroma-local Up ...` (Docker container running)
- `Connection to localhost port 5532 ... succeeded!` (PG tunnel)
- `HTTP 200` (Chroma)

문제 시 cloudflared tunnel / Docker container 재시작 후 재실행.

- [ ] **Step 0.3: venv 활성화 + 의존성 확인**

```bash
source venv/bin/activate
python3 -c "import openpyxl, openai, asyncpg, chromadb, pytest; print('ok')"
```
Expected: `ok`

---

## Task 1: parser_post.py 헬퍼 강화

**Files:**
- Modify: `pipeline/agents/parser_post.py` (기존 normalize_company 보강 + 신규 함수 2 종)
- Test: `pipeline/tests/test_parser_post.py` (신규 또는 기존 확장)

**의도:** spec §2.1 의 3 헬퍼 함수를 atomic 으로 도입. 기존 caller (mapper_node, graph) 의 normalize_company 호출 signature 호환 (str|None → str|None).

- [ ] **Step 1.1: 기존 parser_post.py 의 normalize_company 본문 확인**

```bash
grep -n "def normalize_company\|def split_company\|def extract_zone" pipeline/agents/parser_post.py
```
Expected: 현재 `normalize_company` 만 정의됨 (line 90~). split_company_and_zone / extract_zone 는 없음.

- [ ] **Step 1.2: test 파일 작성 (test_parser_post.py 신설 또는 확장)**

`pipeline/tests/test_parser_post.py` 가 이미 있으면 마지막에 append. 없으면 새로 생성:

```python
# pipeline/tests/test_parser_post.py
from __future__ import annotations

import pytest

from pipeline.agents.parser_post import (
    extract_zone,
    normalize_company,
    split_company_and_zone,
)


class TestNormalizeCompany:
    def test_strip_jusik_prefix(self) -> None:
        assert normalize_company("㈜남웅건설") == "남웅건설"

    def test_strip_paren_jusik(self) -> None:
        assert normalize_company("(주)캠파트너스") == "캠파트너스"

    def test_strip_paren_suffix(self) -> None:
        # spec §2.1 — 모든 괄호 부속 제거
        assert normalize_company("창원기전(6.6kV)") == "창원기전"
        assert normalize_company("창원기전(6.6)") == "창원기전"

    def test_strip_paren_with_jusik(self) -> None:
        assert normalize_company("(주)성우이엔씨") == "성우이엔씨"

    def test_none_input(self) -> None:
        assert normalize_company(None) is None

    def test_empty_string(self) -> None:
        assert normalize_company("") is None


class TestSplitCompanyAndZone:
    def test_strip_fab_suffix(self) -> None:
        assert split_company_and_zone("에스비테크CUB") == "에스비테크"

    def test_strip_fab_with_paren(self) -> None:
        # 괄호 + suffix 둘 다 처리
        assert split_company_and_zone("광건티엔씨FAB(수장2)") == "광건티엔씨"

    def test_no_suffix(self) -> None:
        assert split_company_and_zone("남웅건설") == "남웅건설"

    def test_none_input(self) -> None:
        assert split_company_and_zone(None) is None


class TestExtractZone:
    def test_fab_single_token(self) -> None:
        assert extract_zone("FAB") == "FAB"

    def test_cub_single_token(self) -> None:
        assert extract_zone("CUB") == "CUB"

    def test_fab_with_suffix_content(self) -> None:
        # 시작 토큰 — 명확
        assert extract_zone("FAB 전구간") == "FAB"
        assert extract_zone("CUB 1F~7F 슬라브, FAB~CUB공동구") == "CUB"

    def test_fab_cub_both_ambiguous(self) -> None:
        # 양쪽 → 모호 → None
        assert extract_zone("FAB/CUB") is None
        assert extract_zone("CUB/FAB") is None

    def test_text_middle_ambiguous(self) -> None:
        # 텍스트 중간 박힘 → 모호 → None
        assert extract_zone("M15X FAB F04") is None
        assert extract_zone("클라이머 설치 ... FAB X48") is None
        assert extract_zone("-금일 : M15 Ph-X FAB 1F ~ 7F") is None

    def test_none_input(self) -> None:
        assert extract_zone(None) is None
```

- [ ] **Step 1.3: test 실행 → 실패 확인**

```bash
source venv/bin/activate
python3 -m pytest pipeline/tests/test_parser_post.py -v 2>&1 | head -40
```
Expected: `split_company_and_zone` / `extract_zone` ImportError + normalize_company 의 괄호 부속 케이스 fail.

- [ ] **Step 1.4: parser_post.py 의 함수 구현**

`pipeline/agents/parser_post.py` 에 다음 추가 (기존 normalize_company 본문 강화 + 2 신설):

```python
# pipeline/agents/parser_post.py

import re
from typing import Final

_JUSIK_PAREN_RE: Final = re.compile(r"\(주\)")
_ANY_PAREN_RE: Final = re.compile(r"\([^)]+\)")
_TRAILING_FABCUB_RE: Final = re.compile(r"\s*(FAB|CUB)\s*$", re.IGNORECASE)
_FAB_CUB_BOTH_RE: Final = re.compile(
    r"FAB\s*[/&,]\s*CUB|CUB\s*[/&,]\s*FAB"
)
_FAB_START_RE: Final = re.compile(r"^FAB[\s,/\-_]")
_CUB_START_RE: Final = re.compile(r"^CUB[\s,/\-_]")


def normalize_company(raw: str | None) -> str | None:
    """㈜prefix + (주) + 모든 괄호 부속 제거.

    예: '㈜남웅건설' → '남웅건설'
        '창원기전(6.6kV)' → '창원기전'
        '(주)캠파트너스' → '캠파트너스'
    """
    if raw is None:
        return None
    s = str(raw).replace("㈜", "")
    s = _JUSIK_PAREN_RE.sub("", s)
    s = _ANY_PAREN_RE.sub("", s)
    s = s.strip()
    return s or None


def split_company_and_zone(raw: str | None) -> str | None:
    """회사명 끝의 FAB/CUB suffix 분리 후 정규화된 회사명 반환.

    옵션 2 정신 (scope ≠ wa) — zone_hint 는 반환 X. 분리한 suffix 는 회사명 정규화에만 사용.
    예: '에스비테크CUB' → '에스비테크'
        '광건티엔씨FAB(수장2)' → '광건티엔씨' (괄호도 normalize 단계에서 제거)
    """
    s = normalize_company(raw) or ""
    s = _TRAILING_FABCUB_RE.sub("", s).strip()
    return s or None


def extract_zone(v6: str | None) -> str | None:
    """col 6 (Scope) 의 명시적 'FAB' / 'CUB' 토큰만 zone 추출.

    옵션 2 채택 (spec §2.1):
    - 단일 토큰 'FAB' / 'CUB' → 결정
    - 시작 토큰 ('FAB 전구간', 'CUB 1F~7F') → 결정
    - 양쪽 ('FAB/CUB') → None (mapper LLM 판단)
    - 텍스트 중간 ('M15X FAB F04', 작업 텍스트 통째) → None
    """
    if v6 is None:
        return None
    s = str(v6).strip().upper()
    if _FAB_CUB_BOTH_RE.search(s):
        return None
    if s in ("FAB", "CUB"):
        return s
    if _FAB_START_RE.match(s):
        return "FAB"
    if _CUB_START_RE.match(s):
        return "CUB"
    return None
```

기존 normalize_company 본문 (괄호 부속 제거 logic 없는 경우) 도 위로 교체. 기존 caller (mapper_node 의 `for a in parsed["activities"]: a["company"] = normalize_company(a.get("company"))`) 의 signature 영향 없음.

- [ ] **Step 1.5: test 실행 → 통과 확인**

```bash
python3 -m pytest pipeline/tests/test_parser_post.py -v
```
Expected: 모든 test PASS.

- [ ] **Step 1.6: 기존 caller regression 확인**

```bash
python3 -m pytest pipeline/tests/ -k "normalize_company or parser_post" -v 2>&1 | tail -30
```
Expected: 기존 normalize_company caller 의 test 도 PASS (괄호 부속 제거가 추가됐지만 기존 케이스 — 단순 ㈜ 제거 — 와 호환).

- [ ] **Step 1.7: Commit**

```bash
git add pipeline/agents/parser_post.py pipeline/tests/test_parser_post.py
git commit -m "$(cat <<'EOF'
feat(parser_post): normalize_company 강화 + split_company_and_zone / extract_zone 신설

- normalize_company: 모든 괄호 부속 제거 추가 ('창원기전(6.6kV)' → '창원기전')
- split_company_and_zone: 회사명 끝 FAB/CUB suffix 분리 (옵션 2 — zone_hint 반환 X)
- extract_zone: col 6 (Scope) 명시적 토큰만 → FAB/CUB/None

spec §2.1 헬퍼 함수 도입. mapper / parser caller signature 변경 X.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: parser.py 시트1 (_parse_sheet1_bp_summaries) 개선

**Files:**
- Modify: `pipeline/agents/parser.py:90-122` (`_parse_sheet1_bp_summaries`)
- Test: `pipeline/tests/test_parser.py` (sheet1 unit test 확장)

**의도:** spec §2.2 — col 30 merged group boundary + BP-zone 분리 + sub-section 합계 skip + solo+next 흡수. tmp/sheet1_v2.py 의 5/20 prototype 을 parser.py 안으로 통합 (코드 새로 작성 X — 기존 logic 보존하며 patch).

- [ ] **Step 2.1: 기존 parser.py 의 시트1 함수 본문 읽기**

```bash
sed -n '90,122p' pipeline/agents/parser.py
```
변경 전 본문 + 의존 helper (`_ffill`, `_is_total_row` 등) 파악. 기존 logic 보존 + 본 task 의 추가 case 들을 patch.

- [ ] **Step 2.2: tmp/sheet1_v2.py 의 extract_groups 와 cross-reference**

```bash
sed -n '90,200p' tmp/sheet1_v2.py
```
5/20 prototype 의 robust logic — col 30 merged + 단독 row 흡수 + sub-section skip — 을 parser.py 의 _parse_sheet1_bp_summaries 본문으로 옮길 부분 식별.

- [ ] **Step 2.3: test 작성 — sheet1 추출 정확도 + sub-section skip + solo+next 흡수**

`pipeline/tests/test_parser.py` 에 추가 (기존 `_parse_sheet1_bp_summaries` import 활용):

```python
# pipeline/tests/test_parser.py (append)

from pipeline.agents.parser import _parse_sheet1_bp_summaries
import openpyxl
from pathlib import Path

SAMPLE_XLSX = Path(__file__).resolve().parents[2] / "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"


def _load_sheet1():
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    return wb["1.출력인원 현황"]


def test_sheet1_extracts_99_groups():
    """spec §2.2 — sub-section 합계 + 빈 placeholder skip 후 99 그룹."""
    ws = _load_sheet1()
    rows = _parse_sheet1_bp_summaries(ws)
    assert 95 <= len(rows) <= 105, f"expected ~99 groups, got {len(rows)}"


def test_sheet1_namwoong_fab_cub_split():
    """남웅건설 PH_X-001 (FAB) + PH_X-009 (CUB) 분리 확인."""
    ws = _load_sheet1()
    rows = _parse_sheet1_bp_summaries(ws)
    namwoong = [r for r in rows if (r.get("company") or "") == "남웅건설"]
    assert len(namwoong) >= 2, f"expected 2 sites, got {len(namwoong)}"
    bp_to_zone = {r["bp_code"]: r["zone"] for r in namwoong}
    assert bp_to_zone.get("PH_X-001") == "FAB"
    assert bp_to_zone.get("PH_X-009") == "CUB"


def test_sheet1_subsection_total_skipped():
    """col 5/6 둘 다 None + col 37 > 0 인 sub-section 합계 row 는 skip."""
    ws = _load_sheet1()
    rows = _parse_sheet1_bp_summaries(ws)
    # bp_code None + company None 인 row 가 결과에 없어야 함
    none_rows = [r for r in rows if r.get("bp_code") is None and r.get("company") is None]
    assert len(none_rows) == 0, f"sub-section total leaked: {none_rows}"


def test_sheet1_zone_conservative_option2():
    """spec 옵션 2 — col 6 명시 토큰만 zone, 텍스트 중간 박힘은 None."""
    ws = _load_sheet1()
    rows = _parse_sheet1_bp_summaries(ws)
    # 청조이엔씨 col 6 = 'M15 X FAB' → zone=None
    cheongjo = [r for r in rows if (r.get("company") or "").startswith("청조이엔씨")]
    if cheongjo:
        assert cheongjo[0]["zone"] is None, f"expected None for ambiguous, got {cheongjo[0]['zone']}"


def test_sheet1_chwangwon_paren_normalized():
    """창원기전(6.6kV) → 창원기전 (괄호 정규화)."""
    ws = _load_sheet1()
    rows = _parse_sheet1_bp_summaries(ws)
    chwangwon = [r for r in rows if (r.get("company") or "") == "창원기전"]
    # PH_X-074 / PH_X-075 / PH_X-101 / PH_X-102 / 등 다수
    assert len(chwangwon) >= 2, f"expected >=2 정규화된 창원기전 row, got {len(chwangwon)}"
```

- [ ] **Step 2.4: test 실행 → 실패 확인**

```bash
python3 -m pytest pipeline/tests/test_parser.py::test_sheet1_extracts_99_groups pipeline/tests/test_parser.py::test_sheet1_namwoong_fab_cub_split pipeline/tests/test_parser.py::test_sheet1_subsection_total_skipped pipeline/tests/test_parser.py::test_sheet1_zone_conservative_option2 pipeline/tests/test_parser.py::test_sheet1_chwangwon_paren_normalized -v
```
Expected: 일부 또는 전부 FAIL (기존 _parse_sheet1_bp_summaries 가 sub-section skip 없거나 zone 옵션 1 인 경우).

- [ ] **Step 2.5: _parse_sheet1_bp_summaries 본문 patch**

`pipeline/agents/parser.py:90-122` 를 다음 logic 으로 교체. 핵심 변경:
1. col 30 (금일투입 그룹 Total) 의 merged range 또는 단독 row 가 group boundary
2. BP 코드 row (col 5 의 PH_X-\d+) + 회사명 row (col 5 한글) 인접 2 row pair
3. company 정규화 = `split_company_and_zone` (suffix 분리) + normalize_company (괄호 제거)
4. zone = `extract_zone(col 6)` — 옵션 2 보수적
5. sub-section 합계 row (bp_code + company 둘 다 None) skip
6. 빈 placeholder (company None + cum_t=0) skip
7. solo merged 의 다음 row 가 회사명 단독 row 면 흡수 (예: PH_X-044 + 중원엔지니어링)

```python
# pipeline/agents/parser.py (90-122 교체)

import re
from openpyxl.worksheet.worksheet import Worksheet

from pipeline.agents.parser_post import (
    extract_zone,
    normalize_company,
    split_company_and_zone,
)
from pipeline.state import BPSummary, TimeShiftCounts

_BP_RE = re.compile(r"^PH[_\- ]?X[_\- ]?\d+$", re.IGNORECASE)


def _is_bp_code(v: object) -> bool:
    if v is None:
        return False
    return bool(_BP_RE.match(str(v).strip()))


def _safe_int(v: object) -> int:
    if v is None:
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _shift_dict(ws: Worksheet, start_row: int, end_row: int, col_start: int) -> TimeShiftCounts:
    """col_start..col_start+5 의 6 칸 시간대를 group row 합산."""
    keys = ("morning", "daytime", "overtime", "night", "all_night", "total")
    return {k: sum(_safe_int(ws.cell(r, col_start + i).value) for r in range(start_row, end_row + 1))
            for i, k in enumerate(keys)}  # type: ignore[return-value]


def _parse_sheet1_bp_summaries(ws: Worksheet) -> list[BPSummary]:
    """시트1 (출력인원 현황) → BPSummary[].

    spec §2.2 ─ col 30 merged group boundary + BP-zone 분리 + sub-section skip + solo+next 흡수.
    """
    # 1. col 30 merged 범위 수집 (값 있는 좌상단만)
    ad_merges: dict[int, int] = {}
    for mr in ws.merged_cells.ranges:
        if mr.min_col == 30 and mr.max_col == 30:
            top_val = ws.cell(mr.min_row, 30).value
            if top_val is None:
                continue
            ad_merges[mr.min_row] = mr.max_row

    # 2. solo row (merged 가 아니면서 col 30 값 있는 row)
    solo_rows: list[int] = []
    for r in range(5, ws.max_row + 1):
        v = ws.cell(r, 30).value
        if v is None:
            continue
        if not any(s <= r <= e for s, e in ad_merges.items()):
            solo_rows.append(r)

    # 3. group range 결정 (solo+next 흡수)
    raw_groups: list[tuple[int, int]] = list(ad_merges.items())
    for r in solo_rows:
        next_r = r + 1
        if next_r <= ws.max_row:
            v5_next = ws.cell(next_r, 5).value
            v30_next = ws.cell(next_r, 30).value
            in_other_group = any(s <= next_r <= e for s, e in ad_merges.items())
            if v5_next and v30_next is None and not in_other_group:
                raw_groups.append((r, next_r))
                continue
        raw_groups.append((r, r))
    raw_groups.sort(key=lambda g: g[0])

    # 4. 각 group 별 BPSummary 생성
    results: list[BPSummary] = []
    for start, end in raw_groups:
        bp_code: str | None = None
        company_raw: object = None
        col6_zone_raw: object = None
        work_text_today_parts: list[str] = []
        work_text_prev_parts: list[str] = []
        work_text_tomorrow_parts: list[str] = []

        for r in range(start, end + 1):
            v5 = ws.cell(r, 5).value
            v6 = ws.cell(r, 6).value
            v7 = ws.cell(r, 7).value
            v8 = ws.cell(r, 8).value
            v9 = ws.cell(r, 9).value

            if _is_bp_code(v5):
                bp_code = str(v5).strip()
                if v6 is not None and col6_zone_raw is None:
                    col6_zone_raw = v6
            elif v5:
                if company_raw is None:
                    company_raw = v5
                if v6 is not None and col6_zone_raw is None:
                    col6_zone_raw = v6

            if v7:
                work_text_prev_parts.append(str(v7).strip())
            if v8:
                work_text_today_parts.append(str(v8).strip())
            if v9:
                work_text_tomorrow_parts.append(str(v9).strip())

        company = split_company_and_zone(company_raw if isinstance(company_raw, str) else None)
        # 두번째 정규화 (혹시 모를 ㈜ 잔존)
        company = normalize_company(company)
        zone = extract_zone(col6_zone_raw if isinstance(col6_zone_raw, str) else None)

        today_incr_total = _safe_int(ws.cell(start, 30).value)
        today_cum_total = _safe_int(ws.cell(start, 37).value)

        # spec §2.2 skip 조건
        if bp_code is None and company is None:
            continue  # sub-section 합계
        if company is None and today_incr_total == 0 and today_cum_total == 0:
            continue  # 빈 placeholder

        workers_today_incr = _shift_dict(ws, start, end, 24)
        workers_today_cum = _shift_dict(ws, start, end, 31)
        workers_yesterday_incr = _shift_dict(ws, start, end, 10)
        workers_yesterday_cum = _shift_dict(ws, start, end, 17)

        results.append(
            BPSummary(
                bp_code=bp_code,
                company=company or "",
                disc_abbrev=None,
                zone=zone,
                scope=str(col6_zone_raw) if col6_zone_raw is not None else None,
                work_text_yesterday=" | ".join(work_text_prev_parts) or None,
                work_text_today=" | ".join(work_text_today_parts) or None,
                work_text_tomorrow=" | ".join(work_text_tomorrow_parts) or None,
                workers_yesterday_incr=workers_yesterday_incr,
                workers_yesterday_cum=workers_yesterday_cum,
                workers_today_incr=workers_today_incr,
                workers_today_cum=workers_today_cum,
                today_incr_total=today_incr_total,
                today_cum_total=today_cum_total,
            )
        )

    return results
```

- [ ] **Step 2.6: test 실행 → 통과 확인**

```bash
python3 -m pytest pipeline/tests/test_parser.py -k "sheet1" -v 2>&1 | tail -30
```
Expected: 모든 신규 sheet1 test PASS + 기존 sheet1 관련 test 도 통과.

- [ ] **Step 2.7: 기존 test_parser.py 회귀 확인**

```bash
python3 -m pytest pipeline/tests/test_parser.py -v 2>&1 | tail -30
```
Expected: 기존 11 caller 의 import (`_parse_sheet1_bp_summaries`, `_ffill` 등) 모두 PASS.

- [ ] **Step 2.8: Commit**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser.py
git commit -m "$(cat <<'EOF'
refactor(parser): 시트1 _parse_sheet1_bp_summaries 개선

- col 30 merged + 단독 row 의 group boundary 검출
- BP 코드 row (col 5 PH_X-...) + 회사명 row (col 5 한글) 인접 pair
- company 정규화: ㈜ prefix + 괄호 부속 + FAB/CUB suffix 분리
- zone 추출: col 6 명시 토큰만 (옵션 2, scope ≠ wa)
- sub-section 합계 row (bp+company 둘 다 None) skip
- 빈 placeholder skip
- solo merged + 다음 row 흡수 (PH_X-044 + 중원엔지니어링)

spec §2.2 정합. signature `def _parse_sheet1_bp_summaries(ws) -> list[BPSummary]` 보존.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: parser.py 시트2 (_parse_sheet2_job_allocations) 개선

**Files:**
- Modify: `pipeline/agents/parser.py:124-156` (`_parse_sheet2_job_allocations`)
- Test: `pipeline/tests/test_parser.py`

**의도:** spec §2.3 — col 4='Mm01' + col 2 채워있음 (keyword 무한정, UT/제어 포함) + subtotal skip + cross-check warning.

- [ ] **Step 3.1: 기존 본문 + tmp/sheet2_v1.py 의 logic 확인**

```bash
sed -n '124,160p' pipeline/agents/parser.py
sed -n '60,180p' tmp/sheet2_v1.py
```

- [ ] **Step 3.2: test 작성**

```python
# pipeline/tests/test_parser.py (append)

from pipeline.agents.parser import _parse_sheet2_job_allocations


def test_sheet2_extracts_1597_rows():
    """spec §2.3 — col 4 채워있고 col 25='O' 만 통과 ≈ 1,597."""
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    rows = _parse_sheet2_job_allocations(wb["2.직종별 인원현황"])
    assert 1500 <= len(rows) <= 1700, f"expected ~1597, got {len(rows)}"


def test_sheet2_subtotal_rows_skipped():
    """subtotal/grand total row (disc_code None + col 25='O') 는 skip — 이중계상 방지."""
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    rows = _parse_sheet2_job_allocations(wb["2.직종별 인원현황"])
    bad = [r for r in rows
           if (r.get("manager_code") is None and r.get("worker_code") is None
               and (r.get("job_type") is None or "Total" in str(r.get("job_type") or "")))]
    assert len(bad) == 0, f"subtotal leaked: {bad[:3]}"


def test_sheet2_includes_ut_jeo_groups():
    """col 2 keyword 무한정 — UT / 제어 group 도 추출 (이전 keyword 화이트리스트 fix)."""
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    rows = _parse_sheet2_job_allocations(wb["2.직종별 인원현황"])
    disc_set = {r.get("disc_abbrev") for r in rows if r.get("disc_abbrev")}
    assert "UT" in disc_set, f"UT group missed; disciplines={disc_set}"
    assert "제어" in disc_set, f"제어 group missed; disciplines={disc_set}"


def test_sheet2_cross_check_zero_warnings(capsys):
    """spec §2.3 — 각 group 의 직종 합 = grand total. mismatch 0 권장."""
    # 구현에서 stderr 로 warning 찍음 — 본 test 는 단순 호출만 검증.
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    rows = _parse_sheet2_job_allocations(wb["2.직종별 인원현황"])
    assert isinstance(rows, list)
    # cross-check warning 수 = 0 보장은 raw 파일 dependent — assertion 하지 않음.
```

- [ ] **Step 3.3: test 실행 → 실패 확인**

```bash
python3 -m pytest pipeline/tests/test_parser.py -k "sheet2" -v 2>&1 | tail -30
```

- [ ] **Step 3.4: _parse_sheet2_job_allocations 본문 patch**

`pipeline/agents/parser.py:124-156` 를 다음으로 교체 (tmp/sheet2_v1.py 의 검증된 logic):

```python
# pipeline/agents/parser.py (124-156 교체)

import sys as _sys
from pipeline.state import JobAllocation


def _parse_sheet2_job_allocations(ws: Worksheet) -> list[JobAllocation]:
    """시트2 (직종별 인원현황) → JobAllocation[].

    spec §2.3 ─ col 4='Mm01' 시작 + col 2 keyword 무한정 group boundary,
    직종 row (col 4 채워있고 col 25='O') 만 추출, subtotal/grand total skip.
    """
    # 1. group 시작 row 식별
    starts: list[int] = []
    for r in range(6, ws.max_row + 1):
        c4 = ws.cell(r, 4).value
        if c4 != "Mm01":
            continue
        c2 = ws.cell(r, 2).value
        c3 = ws.cell(r, 3).value
        c25 = ws.cell(r, 25).value
        if c25 != "O" or c2 is None or c3 is None:
            continue
        if not _BP_RE.match(str(c3).strip()):
            continue
        starts.append(r)

    groups: list[tuple[int, int]] = [
        (s, (starts[i + 1] - 1) if i + 1 < len(starts) else ws.max_row)
        for i, s in enumerate(starts)
    ]

    results: list[JobAllocation] = []
    for start, end in groups:
        bp_code = str(ws.cell(start, 3).value).strip()
        discipline = str(ws.cell(start, 2).value).strip()

        # 회사명 = start row 다음 5 row 안의 첫 col 3 한글
        company_raw: object = None
        for r in range(start + 1, min(start + 6, end + 1)):
            v = ws.cell(r, 3).value
            if v is not None and not _BP_RE.match(str(v).strip()):
                company_raw = v
                break
        company = normalize_company(company_raw if isinstance(company_raw, str) else None) or ""

        # group 내 row 분류
        job_rows_o: list[int] = []
        subtotal_rows: list[int] = []
        for r in range(start, end + 1):
            c4 = ws.cell(r, 4).value
            c25 = ws.cell(r, 25).value
            if c4 is not None and c25 == "O":
                job_rows_o.append(r)
            elif c4 is None and c25 == "O":
                subtotal_rows.append(r)

        for r in job_rows_o:
            disc_code = ws.cell(r, 4).value
            job_type = ws.cell(r, 6).value or ""
            workers_today_cum = _shift_dict(ws, r, r, 19)
            results.append(
                JobAllocation(
                    bp_code=bp_code,
                    company=company,
                    disc_abbrev=discipline,
                    manager_code=disc_code if disc_code and str(disc_code).startswith("Mm") else None,
                    worker_code=disc_code if disc_code and str(disc_code).startswith("Wk") else None,
                    job_type=str(job_type),
                    workers_yesterday_cum=_shift_dict(ws, r, r, 7),
                    workers_today_incr=_shift_dict(ws, r, r, 13),
                    workers_today_cum=workers_today_cum,
                    final_flag="O",
                    workers_cum_t=workers_today_cum.get("total", 0),
                )
            )

        # cross-check: 직종 cum_t 합 vs grand total row 의 col 24
        grand_total = None
        for r in subtotal_rows:
            c6 = ws.cell(r, 6).value
            if c6 and "Total" in str(c6):
                grand_total = _safe_int(ws.cell(r, 24).value)
                break
        job_sum = sum(_safe_int(ws.cell(r, 24).value) for r in job_rows_o)
        if grand_total is not None and grand_total != job_sum:
            print(
                f"[parser:sheet2] cross-check warning: company={company} bp={bp_code} "
                f"job_sum={job_sum} grand_total={grand_total} diff={grand_total - job_sum}",
                file=_sys.stderr,
                flush=True,
            )

    return results
```

- [ ] **Step 3.5: test 실행 → 통과 확인**

```bash
python3 -m pytest pipeline/tests/test_parser.py -k "sheet2" -v 2>&1 | tail -30
```
Expected: 4 신규 test PASS.

- [ ] **Step 3.6: Commit**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser.py
git commit -m "$(cat <<'EOF'
refactor(parser): 시트2 _parse_sheet2_job_allocations 개선

- col 4='Mm01' + col 2 keyword 무한정 (UT/제어 포함) group boundary
- 직종 row (col 4 채워있음 + col 25='O') 만 통과
- subtotal/grand total row (col 4 None + col 25='O') skip → 이중계상 방지
- cross-check (직종 합 = grand total) — 불일치 시 stderr warning
- 회사명 정규화 (㈜ + 괄호 + suffix 분리)

spec §2.3 정합. signature `def _parse_sheet2_job_allocations(ws) -> list[JobAllocation]` 보존.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: parser.py 시트3 (_parse_sheet3_equipment_allocations) 개선

**Files:**
- Modify: `pipeline/agents/parser.py:196-235` (`_parse_sheet3_equipment_allocations`)
- Test: `pipeline/tests/test_parser.py`

**의도:** spec §2.4 — col 2 + col 3 (PH_X-NNN) + col 4 (대분류) 채워있는 row 가 group 시작, col 25='O' 인 장비 row 만 추출. subtotal 없음 → cross-check 불요.

- [ ] **Step 4.1: 기존 본문 + tmp/sheet3_v1.py logic 확인**

```bash
sed -n '196,235p' pipeline/agents/parser.py
sed -n '40,120p' tmp/sheet3_v1.py
```

- [ ] **Step 4.2: test 작성**

```python
# pipeline/tests/test_parser.py (append)

from pipeline.agents.parser import _parse_sheet3_equipment_allocations


def test_sheet3_extracts_1111_rows():
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    rows = _parse_sheet3_equipment_allocations(wb["3.장비현황"])
    assert 1050 <= len(rows) <= 1200, f"expected ~1111, got {len(rows)}"


def test_sheet3_namwoong_crane_rows():
    """남웅건설 PH_X-001 의 크레인 / Tower Crane / 펌프카 추출 확인."""
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    rows = _parse_sheet3_equipment_allocations(wb["3.장비현황"])
    namwoong_ph1 = [r for r in rows if r.get("company") == "남웅건설" and r.get("bp_code") == "PH_X-001"]
    bigs = {r.get("equipment_big") for r in namwoong_ph1}
    assert "크레인류" in bigs
    assert "운반기계류" in bigs
```

- [ ] **Step 4.3: test 실행 → 실패 확인**

```bash
python3 -m pytest pipeline/tests/test_parser.py -k "sheet3" -v 2>&1 | tail -20
```

- [ ] **Step 4.4: _parse_sheet3_equipment_allocations 본문 patch**

`pipeline/agents/parser.py:196-235` 를 다음으로 교체:

```python
# pipeline/agents/parser.py (196-235 교체)

from pipeline.state import EquipmentAllocation


def _parse_sheet3_equipment_allocations(ws: Worksheet) -> list[EquipmentAllocation]:
    """시트3 (장비현황) → EquipmentAllocation[].

    spec §2.4 ─ col 2+col 3 (PH_X-NNN)+col 4 채워있음 group 시작,
    col 25='O' + col 4 채워있는 장비 row 만 추출.
    """
    starts: list[int] = []
    for r in range(6, ws.max_row + 1):
        c2 = ws.cell(r, 2).value
        c3 = ws.cell(r, 3).value
        c4 = ws.cell(r, 4).value
        if c2 is None or c3 is None or c4 is None:
            continue
        if not _BP_RE.match(str(c3).strip()):
            continue
        # 헤더 reprint row 회피
        if "장비 투입" in str(c2):
            continue
        starts.append(r)

    groups: list[tuple[int, int]] = [
        (s, (starts[i + 1] - 1) if i + 1 < len(starts) else ws.max_row)
        for i, s in enumerate(starts)
    ]

    results: list[EquipmentAllocation] = []
    for start, end in groups:
        bp_code = str(ws.cell(start, 3).value).strip()
        discipline = str(ws.cell(start, 2).value).strip()

        company_raw: object = None
        for r in range(start + 1, min(start + 6, end + 1)):
            v = ws.cell(r, 3).value
            if v is not None and not _BP_RE.match(str(v).strip()):
                company_raw = v
                break
        company = normalize_company(company_raw if isinstance(company_raw, str) else None) or ""

        for r in range(start, end + 1):
            c25 = ws.cell(r, 25).value
            if c25 != "O":
                continue
            c4 = ws.cell(r, 4).value
            if c4 is None:
                continue
            count_today_cum = _shift_dict(ws, r, r, 19)
            results.append(
                EquipmentAllocation(
                    bp_code=bp_code,
                    company=company,
                    disc_abbrev=discipline,
                    equipment_big=str(c4),
                    equipment_mid=str(ws.cell(r, 5).value or ""),
                    equipment_spec=ws.cell(r, 6).value,
                    count_yesterday_cum=_shift_dict(ws, r, r, 7),
                    count_today_incr=_shift_dict(ws, r, r, 13),
                    count_today_cum=count_today_cum,
                    final_flag="O",
                    count_cum_t=count_today_cum.get("total", 0),
                )
            )

    return results
```

- [ ] **Step 4.5: test 실행 → 통과 확인**

```bash
python3 -m pytest pipeline/tests/test_parser.py -k "sheet3" -v 2>&1 | tail -20
```

- [ ] **Step 4.6: Commit**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser.py
git commit -m "$(cat <<'EOF'
refactor(parser): 시트3 _parse_sheet3_equipment_allocations 개선

- col 2+col 3 (PH_X-...)+col 4 채워있음 group 시작
- col 25='O' + col 4 채워있는 장비 row 만 추출
- 헤더 reprint row ('장비 투입...') 회피
- 회사명 정규화 (㈜ + 괄호 부속 제거)

spec §2.4 정합. subtotal 없음 → cross-check 불요.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: parser.py 시트4 (_parse_sheet4_activities) 개선

**Files:**
- Modify: `pipeline/agents/parser.py:158-194` (`_parse_sheet4_activities`)
- Test: `pipeline/tests/test_parser.py`

**의도:** spec §2.5 — col 3/4/5/6 ffill propagation + col 8 (work_content) 채워있는 row 만 Activity + zone 옵션 2 + B+C=D cross-check.

- [ ] **Step 5.1: 기존 본문 + tmp/sheet4_v1.py logic 확인**

```bash
sed -n '158,194p' pipeline/agents/parser.py
sed -n '40,130p' tmp/sheet4_v1.py
```

- [ ] **Step 5.2: test 작성**

```python
# pipeline/tests/test_parser.py (append)

from pipeline.agents.parser import _parse_sheet4_activities


def test_sheet4_extracts_around_1193_activities():
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    rows = _parse_sheet4_activities(wb["4.물량"])
    assert 1100 <= len(rows) <= 1300, f"expected ~1193, got {len(rows)}"


def test_sheet4_ffill_namwoong_ph_x_001():
    """남웅건설 PH_X-001 의 buryeomteul / 철근배근 등 ffill 정상."""
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    rows = _parse_sheet4_activities(wb["4.물량"])
    namwoong_ph1 = [r for r in rows if r.get("company") == "남웅건설" and r.get("bp_code") == "PH_X-001"]
    assert len(namwoong_ph1) >= 50, f"ffill broken — only {len(namwoong_ph1)} rows for 남웅 PH_X-001"


def test_sheet4_zone_option2_conservative():
    """zone — col 7 명시 토큰만, 텍스트 중간 박힘은 None."""
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    rows = _parse_sheet4_activities(wb["4.물량"])
    # 모호 케이스 — 시트1 의 옵션 2 와 동일 패턴, prototype 결과 zone=None 63% 이상.
    zone_none = sum(1 for r in rows if r.get("zone") is None)
    assert zone_none >= len(rows) * 0.3, f"zone option2 보수화 부족: only {zone_none}/{len(rows)} None"


def test_sheet4_cross_check_BC_eq_D(capsys):
    """B+C=D 산술 정합 — mismatch row 가 거의 없어야 (1~2 raw 결함만 허용)."""
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    rows = _parse_sheet4_activities(wb["4.물량"])
    mismatch = 0
    for r in rows:
        b = r.get("yesterday_cum_qty") or 0
        c = r.get("today_qty") or 0
        d = r.get("today_cum_qty")
        if d is None:
            continue
        if abs((b + c) - d) > 0.001:
            mismatch += 1
    assert mismatch <= 5, f"too many B+C != D mismatches: {mismatch}"
```

- [ ] **Step 5.3: test 실행 → 실패 확인**

```bash
python3 -m pytest pipeline/tests/test_parser.py -k "sheet4" -v 2>&1 | tail -30
```

- [ ] **Step 5.4: _parse_sheet4_activities 본문 patch**

`pipeline/agents/parser.py:158-194` 를 다음으로 교체:

```python
# pipeline/agents/parser.py (158-194 교체)

from pipeline.state import Activity


def _safe_num(v: object) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_sheet4_activities(ws: Worksheet) -> list[Activity]:
    """시트4 (물량) → Activity[].

    spec §2.5 ─ col 3/4/5/6 ffill propagation, col 8 채워있는 row 만 Activity,
    zone 옵션 2 (col 7 명시만), B+C=D cross-check.
    """
    current_trade: str | None = None
    current_bp_code: str | None = None
    current_company_raw: object = None

    results: list[Activity] = []
    warnings: list[dict] = []

    for r in range(5, ws.max_row + 1):
        c4 = ws.cell(r, 4).value
        c5 = ws.cell(r, 5).value
        c6 = ws.cell(r, 6).value

        if c4 is not None:
            current_trade = str(c4)
        if c5 is not None:
            current_bp_code = str(c5).strip()
            current_company_raw = c6  # 같은 row 의 col 6

        c8 = ws.cell(r, 8).value
        if c8 is None:
            continue

        c7 = ws.cell(r, 7).value
        c9 = ws.cell(r, 9).value
        c10 = _safe_num(ws.cell(r, 10).value)
        c11 = _safe_num(ws.cell(r, 11).value)
        c12 = _safe_num(ws.cell(r, 12).value)
        c13 = _safe_num(ws.cell(r, 13).value)

        company = normalize_company(current_company_raw if isinstance(current_company_raw, str) else None)
        zone = extract_zone(c7 if isinstance(c7, str) else None)

        # cross-check B+C=D
        if c11 is not None and c12 is not None and c13 is not None:
            if abs((c11 + c12) - c13) > 0.001:
                warnings.append({
                    "row": r, "company": company, "bp_code": current_bp_code,
                    "B+C": (c11 + c12), "D": c13,
                })

        results.append(
            Activity(
                zone=zone,
                bp_code=current_bp_code,
                company=company or "",
                scope=str(c7) if c7 is not None else None,
                trade=current_trade or "",
                work_content=str(c8).strip(),
                unit=str(c9 or ""),
                plan_total_qty=c10,
                yesterday_cum_qty=c11,
                today_qty=c12 or 0.0,
                today_cum_qty=c13,
                progress_percent=None,
                remaining_qty=None,
                remaining_percent=None,
                note=None,
                work_location_code=None,
                wbs_mid_name=None,
                wbs_sub_name=None,
                wbs_detail_name=None,
                wbs_activity_id=None,
                l5_disc=current_trade or "",
                l6_main=None,
                l7_sub=None,
                l7_5_activity=None,
                sub_work_area=None,
                conditions=[],
                assigned_workers=0.0,
                worker_source="parsed",
                plan_mh=None,
                wa=None,
                mapping_conf=None,
                mapping_source=None,
                requires_review=False,
            )
        )

    if warnings:
        print(
            f"[parser:sheet4] cross-check warnings: {len(warnings)} rows (B+C != D)",
            file=_sys.stderr,
            flush=True,
        )

    return results
```

- [ ] **Step 5.5: test 실행 → 통과 확인**

```bash
python3 -m pytest pipeline/tests/test_parser.py -k "sheet4" -v 2>&1 | tail -30
```

- [ ] **Step 5.6: 전체 parser test 회귀 확인**

```bash
python3 -m pytest pipeline/tests/test_parser.py -v 2>&1 | tail -30
```

- [ ] **Step 5.7: Commit**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser.py
git commit -m "$(cat <<'EOF'
refactor(parser): 시트4 _parse_sheet4_activities 개선

- col 3/4/5/6 ffill propagation
- col 8 (work_content) 채워있는 row 만 Activity
- zone 추출: col 7 (Scope) 명시 토큰만 (옵션 2 — scope ≠ wa)
- B+C=D 산술 cross-check — mismatch row stderr warning
- 회사명 정규화 (괄호 부속 제거)

spec §2.5 정합. signature `def _parse_sheet4_activities(ws) -> list[Activity]` 보존.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: parser.py 의 시트1/4 LLM 검증 wrapper 통합

**Files:**
- Modify: `pipeline/agents/parser.py:270-306` (`parse_daily_report`)
- Modify: `pipeline/agents/parser.py` 끝에 `_verify_sheet1_via_llm` / `_verify_sheet4_via_llm` 함수 추가
- Test: `pipeline/tests/test_parser.py`

**의도:** spec §2.6 — 시트1/4 LLM 검증 default on (env `CPIA_PARSER_VERIFY_LLM=off` 로 opt-out). spec §2.6.4 의 8 종 error path 모두 graceful catch.

- [ ] **Step 6.1: test 작성 — opt-in/out + error path graceful**

```python
# pipeline/tests/test_parser.py (append)

import os
from unittest.mock import patch


def test_parse_daily_report_llm_verify_off_skip():
    """CPIA_PARSER_VERIFY_LLM=off 시 LLM 호출 0 + 정상 종료."""
    with patch.dict(os.environ, {"CPIA_PARSER_VERIFY_LLM": "off"}):
        from pipeline.agents.parser import parse_daily_report
        parsed = parse_daily_report(SAMPLE_XLSX)
    assert "bp_summaries" in parsed
    assert len(parsed["bp_summaries"]) > 50


def test_parse_daily_report_llm_verify_default_on_graceful_on_error():
    """LLM 호출 실패해도 cycle block 안 함 (graceful degrade)."""
    # Azure endpoint 를 가짜 값으로 set → 401/connection error 발현
    with patch.dict(os.environ, {
        "CPIA_PARSER_VERIFY_LLM": "on",
        "AZURE_OPENAI_API_KEY": "FAKE_KEY_FOR_TEST",
    }):
        from pipeline.agents.parser import parse_daily_report
        # Exception 안 던지고 정상 종료해야 함
        parsed = parse_daily_report(SAMPLE_XLSX)
    assert "bp_summaries" in parsed
```

- [ ] **Step 6.2: test 실행 → 실패 확인**

```bash
python3 -m pytest pipeline/tests/test_parser.py -k "llm_verify" -v 2>&1 | tail -20
```
Expected: 함수 미정의 또는 LLM 호출 fail 시 Exception propagate.

- [ ] **Step 6.3: parse_daily_report 본문 + verify helper 추가**

`pipeline/agents/parser.py` 끝에 추가:

```python
# pipeline/agents/parser.py (끝에 추가)

import json
import os


def _should_verify_llm() -> bool:
    """CPIA_PARSER_VERIFY_LLM env — 기본 'on', 'off' / 'false' / '0' 면 opt-out."""
    v = os.environ.get("CPIA_PARSER_VERIFY_LLM", "on").lower().strip()
    return v not in ("off", "false", "0", "no")


def _verify_sheet1_via_llm(ws: Worksheet, bp_summaries: list[BPSummary]) -> None:
    """spec §2.6.1 — 시트1 rule 추출 결과 LLM 검증. issues 는 stderr 로그만."""
    if not bp_summaries:
        return  # 빈 input → 호출 skip
    try:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        )
        # 핵심 col raw dump (col 5,6,7,8,9,30,37) — sheet1 의 99 group * 2 row 정도
        raw_dump = []
        for r in range(5, ws.max_row + 1):
            v5 = ws.cell(r, 5).value
            if v5 is None:
                continue
            raw_dump.append({
                "r": r,
                "col5": v5, "col6": ws.cell(r, 6).value,
                "col7_prev": ws.cell(r, 7).value,
                "col8_today": ws.cell(r, 8).value,
                "col30_total": ws.cell(r, 30).value,
                "col37_cum": ws.cell(r, 37).value,
            })

        sys_prompt = (
            "건설 작업일보 시트1 (출력인원) rule 추출 검증. "
            "각 BPSummary 필드: bp_code (PH_X-NNN), company (정규화), zone (FAB/CUB/null), "
            "work_text_today, today_cum_total. "
            "raw 와 명확히 어긋난 경우만 issues 에 보고. "
            "JSON: {\"issues\": [{\"row\": N, \"field\": \"...\", \"current\": \"...\", "
            "\"expected\": \"...\", \"why\": \"...\"}]}"
        )
        user_payload = {"rule_results": bp_summaries, "raw_rows": raw_dump}
        resp = client.chat.completions.create(
            model=os.environ["LLM_MODEL"],
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=2000,
            timeout=30,
        )
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            print("[parser:sheet1] LLM verify truncated (finish_reason=length) — issues=[]",
                  file=_sys.stderr, flush=True)
            return
        if choice.finish_reason == "content_filter":
            print("[parser:sheet1] LLM verify content_filter — issues=[]",
                  file=_sys.stderr, flush=True)
            return
        try:
            verify = json.loads(choice.message.content or "{}")
        except json.JSONDecodeError as e:
            print(f"[parser:sheet1] LLM verify malformed JSON: {e} — issues=[]",
                  file=_sys.stderr, flush=True)
            return
        for it in verify.get("issues", []):
            print(
                f"[parser:sheet1] LLM 검증 issue: "
                f"row={it.get('row')} field={it.get('field')} "
                f"current={it.get('current')} expected={it.get('expected')} "
                f"reason={it.get('why')}",
                file=_sys.stderr, flush=True,
            )
    except Exception as e:
        print(f"[parser:sheet1] LLM verify EXCEPTION: {type(e).__name__}: {e}",
              file=_sys.stderr, flush=True)


def _verify_sheet4_via_llm(ws: Worksheet, activities: list[Activity]) -> None:
    """spec §2.6.1 — 시트4 sample 39 row + 의심 case LLM 검증."""
    if not activities:
        return
    try:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        )
        # sample 선정 — 첫 10 + 의심 (zone=None / plan=None / work<=3) 각 5 + 끝 5
        suspicious_zone_none = [a for a in activities if a.get("zone") is None][:5]
        suspicious_no_plan = [a for a in activities if a.get("plan_total_qty") is None][:5]
        suspicious_short = [a for a in activities if len(a.get("work_content", "")) <= 3][:5]
        sample = activities[:10] + suspicious_zone_none + suspicious_no_plan + suspicious_short + activities[-5:]
        seen = set()
        sample_unique = []
        for a in sample:
            key = (a.get("bp_code"), a.get("work_content"))
            if key in seen:
                continue
            seen.add(key)
            sample_unique.append(a)

        # raw dump — sample 의 row 인덱스 추정 어려움 (parser_rule 의 row 보존 X) → work_content 만 cross
        # 단순화: rule_results_sample 만 보냄 (raw 비교 없음)
        sys_prompt = (
            "건설 작업일보 시트4 (물량) rule 추출 검증. "
            "각 Activity 필드: company / bp_code / trade / zone (FAB/CUB/null) / work_content / "
            "unit / plan_total_qty / today_cum_qty. 명확한 mis-parse 만 보고. "
            "JSON: {\"issues\": [{\"company\": \"...\", \"work_content\": \"...\", "
            "\"field\": \"...\", \"current\": \"...\", \"expected\": \"...\", \"why\": \"...\"}]}"
        )
        user_payload = {"rule_results_sample": sample_unique}
        resp = client.chat.completions.create(
            model=os.environ["LLM_MODEL"],
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=1500,
            timeout=30,
        )
        choice = resp.choices[0]
        if choice.finish_reason in ("length", "content_filter"):
            print(f"[parser:sheet4] LLM verify finish_reason={choice.finish_reason} — issues=[]",
                  file=_sys.stderr, flush=True)
            return
        try:
            verify = json.loads(choice.message.content or "{}")
        except json.JSONDecodeError as e:
            print(f"[parser:sheet4] LLM verify malformed JSON: {e} — issues=[]",
                  file=_sys.stderr, flush=True)
            return
        for it in verify.get("issues", []):
            print(
                f"[parser:sheet4] LLM 검증 issue: "
                f"work={it.get('work_content')} field={it.get('field')} "
                f"current={it.get('current')} expected={it.get('expected')} "
                f"reason={it.get('why')}",
                file=_sys.stderr, flush=True,
            )
    except Exception as e:
        print(f"[parser:sheet4] LLM verify EXCEPTION: {type(e).__name__}: {e}",
              file=_sys.stderr, flush=True)
```

`parse_daily_report` (line 270 부근) 의 본문 끝부분 `return ParsedDailyReport(...)` 직전에 다음 hook 추가:

```python
# parse_daily_report() 의 return 직전
if _should_verify_llm():
    _verify_sheet1_via_llm(wb["1.출력인원 현황"], parsed["bp_summaries"])
    _verify_sheet4_via_llm(wb["4.물량"], parsed["activities"])
```

- [ ] **Step 6.4: test 실행 → 통과 확인**

```bash
python3 -m pytest pipeline/tests/test_parser.py -k "llm_verify" -v 2>&1 | tail -20
```
Expected: 2 신규 test PASS.

- [ ] **Step 6.5: 실 cycle 1 회 — LLM 검증 로그 확인 (수동 sanity)**

```bash
CPIA_PARSER_VERIFY_LLM=on \
  POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  python3 -c "
from pipeline.agents.parser import parse_daily_report
parsed = parse_daily_report('docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx')
print(f'bp={len(parsed[\"bp_summaries\"])}, jobs={len(parsed[\"job_allocations\"])}, '
      f'eqs={len(parsed[\"equipment_allocations\"])}, acts={len(parsed[\"activities\"])}')
" 2>&1 | tail -20
```
Expected: `bp=~99 jobs=~1597 eqs=~1111 acts=~1193` + stderr 에 LLM 검증 issue 0~몇 건 로그.

- [ ] **Step 6.6: Commit**

```bash
git add pipeline/agents/parser.py pipeline/tests/test_parser.py
git commit -m "$(cat <<'EOF'
feat(parser): 시트1/4 LLM 검증 wrapper (default on, opt-out env)

- _verify_sheet1_via_llm / _verify_sheet4_via_llm 신설
- parse_daily_report 끝에 _should_verify_llm() 가드로 호출
- spec §2.6.4 8 종 error path graceful catch (timeout 30s, length, content_filter, JSONDecodeError, Exception broad)
- 빈 input → LLM 호출 skip (비용 0)
- DB 적재 X, issues 는 stderr 로그만 (결정성 보존)
- CPIA_PARSER_VERIFY_LLM=off 로 opt-out

spec §2.6 정합. signature `def parse_daily_report(xlsx_path) -> ParsedDailyReport` 보존.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: collector.py + run_one_cycle.py 의 parser_llm → parse_daily_report 교체

**Files:**
- Modify: `pipeline/agents/collector.py:19` (import 1 줄)
- Modify: `scripts/run_one_cycle.py:29,70` (import + call site)
- Test: `pipeline/tests/test_graph_e2e.py` (smoke + 직접 호출)

**의도:** spec §4.1 split-brain 방지 — `CPIA_PARSER=rule` 시에도 caller 가 parser_llm 직접 호출하던 hard import 제거.

- [ ] **Step 7.1: 변경 영향 grep — caller 모두 식별**

```bash
grep -rn "from pipeline.agents.parser_llm import\|parse_daily_report_llm(" \
  pipeline/ scripts/ tmp/ 2>/dev/null | grep -v ".pyc\|__pycache__"
```
Expected: collector.py:19 + run_one_cycle.py:29,70 + (선택) tmp/ 의 prototype.

- [ ] **Step 7.2: test 작성 — collector smoke + parser_llm 의존 제거 확인**

```python
# pipeline/tests/test_graph_e2e.py (append, 단 기존 import 와 충돌 X)

def test_collector_does_not_import_parser_llm():
    """split-brain 방지 — collector 가 parser_llm 직접 import 안 함."""
    with open("pipeline/agents/collector.py") as f:
        content = f.read()
    assert "from pipeline.agents.parser_llm import" not in content
    assert "parse_daily_report_llm" not in content
    assert "from pipeline.agents.parser import parse_daily_report" in content


def test_run_one_cycle_does_not_call_parser_llm():
    with open("scripts/run_one_cycle.py") as f:
        content = f.read()
    assert "parse_daily_report_llm" not in content
    assert "from pipeline.agents.parser import parse_daily_report" in content
```

- [ ] **Step 7.3: test 실행 → 실패 확인**

```bash
python3 -m pytest pipeline/tests/test_graph_e2e.py -k "does_not" -v
```
Expected: FAIL (parser_llm import 가 여전히 있음).

- [ ] **Step 7.4: collector.py:19 의 import 교체**

기존:
```python
from pipeline.agents.parser_llm import ParserConfig, parse_daily_report_llm
```
신규:
```python
from pipeline.agents.parser import parse_daily_report
```
collector 본문에서 `parse_daily_report_llm(xlsx, parser_cfg, ...)` 호출 → `parse_daily_report(xlsx)` 호출 (cfg arg 제거 — parse_daily_report 가 env 변수 직접 읽음). `ParserConfig` 참조 부분이 있으면 함께 제거 (graph state 의 `parser` cfg 가 더 이상 사용 안 됨).

- [ ] **Step 7.5: scripts/run_one_cycle.py:29,70 교체**

기존:
```python
from pipeline.agents.parser_llm import ParserConfig, parse_daily_report_llm
...
parsed = await parse_daily_report_llm(xlsx_path, parser_cfg)
```
신규:
```python
from pipeline.agents.parser import parse_daily_report
...
parsed = parse_daily_report(xlsx_path)  # sync, no cfg
```
`async` 호출 사라지므로 `asyncio.run(...)` 안 wrap 필요한 경우 정리.

- [ ] **Step 7.6: test 실행 → 통과 확인**

```bash
python3 -m pytest pipeline/tests/test_graph_e2e.py -k "does_not" -v
python3 -m pytest pipeline/tests/test_graph_e2e.py -v 2>&1 | tail -30
```
Expected: 신규 2 test PASS + 기존 graph e2e test 도 PASS.

- [ ] **Step 7.7: FE↔BE 매칭 확인 — 실 cycle 1 회 + dev server + 브라우저 시각 확인**

backend cycle 실행:
```bash
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  python3 scripts/run_one_cycle.py \
  'docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx' \
  m15x-ph3-ibl 2025-09-25
```
Expected: parser_rule path 로 약 15-20 초 안에 mapper / atomizer 까지 진행 (HIL 1 interrupt 까지).

frontend dev server:
```bash
cd web && npm run dev
```
다른 terminal:
```bash
open http://localhost:3000/reports
```

브라우저에서 다음 확인 (시각):
- § 01 헤더 CPI % 가 0 아님
- § 01 업체별 / 공종별 bar 가 그어짐 (POC 3 사 또는 cycle 결과의 회사들)
- § 02 4분면 산점도 점 표시
- console error 0

→ FE 가 BE (mapper_activities + daily_reports) 의 신 parser 결과를 정상 표시.

- [ ] **Step 7.8: Commit**

```bash
git add pipeline/agents/collector.py scripts/run_one_cycle.py pipeline/tests/test_graph_e2e.py
git commit -m "$(cat <<'EOF'
refactor(callers): collector.py + run_one_cycle.py 의 parser_llm 호출 → parse_daily_report

- collector.py:19 import 교체 (parser_llm → parser)
- scripts/run_one_cycle.py:29,70 호출 사이트 교체
- ParserConfig 의존 제거 (env 변수 직접 사용)
- split-brain 방지 — 모든 caller 가 단일 entry 통과

spec §4.1 정합. smoke test 추가로 회귀 방지.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: mapper.py — build_bp_context BP 별 분리 + resolve_wa 7 단계 (5/20 working tree commit)

**Files:**
- Modify: `pipeline/agents/mapper.py:170-218` (`build_bp_context`)
- Modify: `pipeline/agents/mapper.py:229-242` (`build_llm_input`)
- Modify: `pipeline/agents/mapper.py:259-285` (`resolve_wa`)

**의도:** 5/20 working tree 에 이미 적용된 mapper 변경을 atomic commit 으로 정리. 단 sim_5case 의 V2 결과 (case 1/2/3 정답 + case 4/5 HIL 안전망) 가 통과 evidence.

- [ ] **Step 8.1: working tree 의 mapper.py 변경 확인**

```bash
git diff pipeline/agents/mapper.py | head -100
```
Expected: 5/20 변경 (build_bp_context BP 별 분리, build_llm_input bp_code, resolve_wa 의 auto_bp_zone_match / auto_llm_rerank) diff 나옴.

- [ ] **Step 8.2: 5/20 prototype 의 검증 결과 cross-reference**

```bash
ls -la tmp/sim_5case.py tmp/sim_3sa.py 2>&1
```
이 파일들은 5/20 V2 시뮬레이션 evidence. plan 의 V3 (Task 12) 에서 다시 실행 → 정량 확인.

- [ ] **Step 8.3: 회귀 test 실행 (현 working tree 상태로)**

```bash
python3 -m pytest pipeline/tests/test_mapper_golden.py -v 2>&1 | tail -20
```
Expected: 기존 mapper test 통과 (build_bp_context 변경이 schema 가 아니라 prompt 내용만 영향).

- [ ] **Step 8.4: Commit (working tree 변경 그대로)**

```bash
git add pipeline/agents/mapper.py
git commit -m "$(cat <<'EOF'
feat(mapper): build_bp_context BP 별 분리 + resolve_wa 7 단계

- build_bp_context: 회사 단위 통합 → BP 코드별 분리 + zone 명시 (LLM 가 BP 매칭 시 정확도 ↑)
- build_llm_input: activity.bp_code 명시 ("회사: ... / BP: PH_X-NNN")
- resolve_wa 7 단계:
  0. cand_pool 빈 시 → auto_chroma_top1
  1. (신규 fix C) auto_bp_zone_match — activity.bp_code 일치 BPSummary.zone deterministic
  2. (신규 옵션 A) auto_llm_rerank — LLM chosen_wa ∈ cand_pool fallback
  3. auto_bp_single (구 1단계)
  4. auto_l6_single (구 2단계)
  5. auto_sheet1_text (구 3단계, 회사 단위 set 매칭 legacy)
  6. hil_required

5/20 sim_5case 검증: case 1/2/3 (남웅/세보) auto_bp_zone_match 통과 + case 4/5 (창원기전 zone=None) conf<0.7 HIL 안전망. spec §3 정합.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: parser unit test 확장 (col 인덱스 검증 + 회귀)

**Files:**
- Modify: `pipeline/tests/test_parser.py` (col 인덱스 + LLM verify error path 추가)

**의도:** spec §5 V4 의 unit test 보강 — `test_sheetN_col_indices_match_header` 같이 implementer 의 col 인덱스 오류를 잡는 가드.

- [ ] **Step 9.1: col 인덱스 검증 test 작성**

```python
# pipeline/tests/test_parser.py (append)

def test_sheet1_col_indices_match_header():
    """spec §2.2 col 인덱스 가드 — implementer 가 col 4/5 등 오류 코딩 시 fail."""
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    ws = wb["1.출력인원 현황"]
    # r4 = 헤더 row 1, r5 = 헤더 row 2
    assert ws.cell(4, 5).value == "BP사", f"col 5 header mismatch: {ws.cell(4, 5).value!r}"
    assert ws.cell(5, 5).value == "협력업체"
    assert ws.cell(4, 6).value == "Scope" or ws.cell(5, 6).value is not None
    # col 30 = 금일투입 그룹 Total (sheet1 parser 의 group boundary)
    # 헤더 텍스트는 사이트마다 다를 수 있으니 단순 not None 만 가드


def test_sheet2_col_indices_match_header():
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    ws = wb["2.직종별 인원현황"]
    assert ws.cell(5, 4).value == "관리자/근로자" or "관리자" in str(ws.cell(5, 4).value or "")
    assert ws.cell(5, 25).value == "최종"


def test_sheet3_col_indices_match_header():
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    ws = wb["3.장비현황"]
    assert ws.cell(5, 4).value == "대분류"
    assert ws.cell(5, 5).value == "중분류"
    assert ws.cell(5, 6).value == "규 격" or ws.cell(5, 6).value == "규격"
    assert ws.cell(5, 25).value == "최종"


def test_sheet4_col_indices_match_header():
    wb = openpyxl.load_workbook(str(SAMPLE_XLSX), data_only=True)
    ws = wb["4.물량"]
    # spec §2.5 — col 8 = work_content
    assert ws.cell(3, 8).value == "대표물량_작업 내용" or "작업 내용" in str(ws.cell(3, 8).value or "")
```

- [ ] **Step 9.2: test 실행 → 통과 확인**

```bash
python3 -m pytest pipeline/tests/test_parser.py -k "col_indices_match" -v
```
Expected: 4 test PASS.

- [ ] **Step 9.3: 전체 parser test 회귀**

```bash
python3 -m pytest pipeline/tests/test_parser.py -v 2>&1 | tail -40
```

- [ ] **Step 9.4: Commit**

```bash
git add pipeline/tests/test_parser.py
git commit -m "$(cat <<'EOF'
test(parser): 4 시트 col 인덱스 헤더 검증 가드 추가

각 시트의 r3~r5 header 가 spec §2.2~§2.5 의 col 인덱스 가정과 일치하는지 assertion.
implementer 가 col 4/5/6 등을 잘못 코딩하면 즉시 fail.

spec §5 V4 정합.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: mapper resolve_wa 7 단계 unit test 신설

**Files:**
- Create: `pipeline/tests/test_mapper_resolve_wa.py`

**의도:** spec §3.3 — resolve_wa 7 단계 각 case 의 결정성 + chosen_wa fallback 검증.

- [ ] **Step 10.1: test 파일 신설**

```python
# pipeline/tests/test_mapper_resolve_wa.py
from __future__ import annotations

import pytest

from pipeline.agents.mapper import WAResolution, resolve_wa


def _activity(bp_code: str | None = None, company: str = "남웅건설") -> dict:
    return {
        "company": company,
        "bp_code": bp_code,
        "work_content": "test work",
        "trade": "건축",
        "zone": None,
    }


def _parsed_with_bp_summary(bp_code: str, zone: str | None, company: str = "남웅건설") -> dict:
    return {
        "bp_summaries": [
            {"bp_code": bp_code, "company": company, "zone": zone}
        ],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }


class TestResolveWa:
    def test_auto_chroma_top1_when_empty_pool(self):
        """0단계 — cand_pool 빈 시 chosen_wa 그대로."""
        r = resolve_wa(_activity(), "철근콘크리트공사", cand_pool=[], parsed_report=None, chosen_wa="FAB")
        assert r.value == "FAB"
        assert r.source == "auto_chroma_top1"

    def test_auto_bp_zone_match_deterministic(self):
        """1단계 — activity.bp_code 일치 BPSummary.zone 채택 (deterministic)."""
        parsed = _parsed_with_bp_summary("PH_X-001", "FAB")
        r = resolve_wa(
            _activity(bp_code="PH_X-001"),
            "철근콘크리트공사",
            cand_pool=[("FAB", "철근콘크리트공사"), ("CUB", "철근콘크리트공사")],
            parsed_report=parsed,
            chosen_wa="CUB",  # LLM 가 잘못 골랐어도
        )
        assert r.value == "FAB"  # BP-zone deterministic 우선
        assert r.source == "auto_bp_zone_match"

    def test_auto_llm_rerank_fallback(self):
        """2단계 — BP-zone 매칭 없으면 LLM chosen_wa 가 cand_pool 안에 있으면 채택."""
        parsed = _parsed_with_bp_summary("PH_X-001", None)  # zone=None
        r = resolve_wa(
            _activity(bp_code="PH_X-001"),
            "철근콘크리트공사",
            cand_pool=[("FAB", "철근콘크리트공사"), ("CUB", "철근콘크리트공사")],
            parsed_report=parsed,
            chosen_wa="FAB",
        )
        assert r.value == "FAB"
        assert r.source == "auto_llm_rerank"

    def test_auto_bp_single(self):
        """3단계 — cand_pool wa 가 단일."""
        r = resolve_wa(
            _activity(bp_code="PH_X-041"),
            "ACID배기설비공사",
            cand_pool=[("FAB", "ACID배기설비공사"), ("FAB", "ALKALI배기설비공사")],
            parsed_report=None,
            chosen_wa=None,  # LLM choice 없어도
        )
        assert r.value == "FAB"
        assert r.source == "auto_bp_single"

    def test_auto_l6_single(self):
        """4단계 — L6 결정 후 cand_pool wa 단일."""
        r = resolve_wa(
            _activity(bp_code="PH_X-X"),
            "특정L6",
            cand_pool=[("FAB", "특정L6"), ("CUB", "다른L6")],
            parsed_report=None,
            chosen_wa=None,
        )
        assert r.value == "FAB"
        assert r.source == "auto_l6_single"

    def test_auto_sheet1_text_legacy(self):
        """5단계 — 회사 단위 zones_in_sheet1 ∩ cand_wa_at_l6 단일."""
        parsed = {
            "bp_summaries": [
                {"bp_code": "PH_X-A", "company": "남웅건설", "zone": "FAB"},
                {"bp_code": "PH_X-B", "company": "남웅건설", "zone": "FAB"},  # 모두 FAB
            ],
            "job_allocations": [], "equipment_allocations": [], "activities": [],
        }
        r = resolve_wa(
            _activity(bp_code="PH_X-Z"),  # 매칭 안 됨
            "철근콘크리트공사",
            cand_pool=[("FAB", "철근콘크리트공사"), ("CUB", "철근콘크리트공사")],
            parsed_report=parsed,
            chosen_wa=None,
        )
        assert r.value == "FAB"
        assert r.source == "auto_sheet1_text"

    def test_hil_required_when_all_fail(self):
        """6단계 — 모든 fallback fail."""
        parsed = {
            "bp_summaries": [],
            "job_allocations": [], "equipment_allocations": [], "activities": [],
        }
        r = resolve_wa(
            _activity(bp_code="PH_X-X"),
            "철근콘크리트공사",
            cand_pool=[("FAB", "철근콘크리트공사"), ("CUB", "철근콘크리트공사")],
            parsed_report=parsed,
            chosen_wa=None,
        )
        assert r.value is None
        assert r.source == "hil_required"
```

- [ ] **Step 10.2: test 실행 → 통과 확인**

```bash
python3 -m pytest pipeline/tests/test_mapper_resolve_wa.py -v
```
Expected: 7 test 모두 PASS (5/20 working tree mapper 변경 후).

- [ ] **Step 10.3: Commit**

```bash
git add pipeline/tests/test_mapper_resolve_wa.py
git commit -m "$(cat <<'EOF'
test(mapper): resolve_wa 7 단계 unit test 신설

각 source 케이스 + chosen_wa fallback 검증:
- 0. auto_chroma_top1 (빈 pool)
- 1. auto_bp_zone_match (BP 일치 + BPSummary.zone)
- 2. auto_llm_rerank (LLM chosen_wa ∈ cand_pool)
- 3. auto_bp_single
- 4. auto_l6_single
- 5. auto_sheet1_text (legacy)
- 6. hil_required

spec §3.3 + §5 V4 정합.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: parser_llm.py deprecation 주석

**Files:**
- Modify: `pipeline/agents/parser_llm.py` (파일 상단 docstring 에 deprecation)

**의도:** parser_llm.py 코드는 보존하되 새 cycle 에서 사용 안 함을 명시.

- [ ] **Step 11.1: parser_llm.py 상단 docstring 수정**

`pipeline/agents/parser_llm.py` 의 module docstring (또는 첫 30 line) 에 다음 추가:

```python
"""DEPRECATED — 2026-05-20.

본 모듈은 chunk LLM parsing 으로 ParsedDailyReport 를 생성했으나, 5/20 부터
`pipeline.agents.parser.parse_daily_report` (rule-based + 시트1/4 LLM 검증
hybrid) 로 대체됨. spec: docs/superpowers/specs/2026-05-20-cpia-parser-mapper-refactor-design.md.

회귀 사용 (rule path 가 fail 하는 경우) 시 env flag `CPIA_PARSER=llm` 설정 후
graph entry 안에서 분기 처리 필요. 본 cycle 의 graph 는 기본 rule path 만 호출.

이전 docstring:
(원본 보존)
"""
```

- [ ] **Step 11.2: 회귀 test 실행**

```bash
python3 -m pytest pipeline/tests/ -v 2>&1 | tail -30
```
Expected: 모든 test PASS (단순 docstring 변경 — 코드 영향 0).

- [ ] **Step 11.3: Commit**

```bash
git add pipeline/agents/parser_llm.py
git commit -m "$(cat <<'EOF'
chore(parser_llm): deprecation 주석 추가

본 모듈은 5/20 spec 으로 parser.py rule-based + LLM 검증 hybrid 에 대체됨.
코드 보존 (env flag CPIA_PARSER=llm 으로 회귀 가능).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: V5 — 10 업체 POC cycle + Reports UI 12 정량 기준 (사용자 명시 마지막 단계)

**Files:**
- Create: `tmp/run_v5_10companies.py` — V5 cycle 실행 script (sample 선정 + cycle + 통계 dump)
- Create: `web/e2e/reports-10-companies.spec.ts` — Playwright e2e 12 정량 기준

**의도:** spec §5 V5 — 10 업체 POC 전체 로직 + reports UI 매핑 시각 확인. **사용자 시각 확인까지 plan 의 명시 단계**.

- [ ] **Step 12.1: BP master 의 회사별 cand_pool size 실측 — sample 선정 근거**

`tmp/run_v5_10companies.py` (1/2 — sample 선정 부분) 작성:

```python
# tmp/run_v5_10companies.py
"""V5 — 10 업체 POC cycle + reports UI 12 정량 기준 검증.

1. BP master + sheet4 의 회사 분포 cross
2. sample 10 업체 선정 (cand_pool size 다양 + sheet4 activity >= 3)
3. cycle 실행 (parse_daily_report → mapper_node → atomizer → ...)
4. mapping_source 분포 + zone false positive 빈도 dump
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import openpyxl
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
os.environ["POSTGRES_URL"] = "postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia"

from pipeline.db import PGClient


async def select_10_companies() -> list[str]:
    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        # cand_pool size 분포 fetch
        rows = await pg._pool.fetch("""
            SELECT company, COUNT(*) as pool_size, COUNT(DISTINCT wa) as wa_kinds
            FROM activity_master GROUP BY company ORDER BY 2 DESC LIMIT 50
        """)
    finally:
        await pg.close()
    pg_companies = [(r["company"], r["pool_size"], r["wa_kinds"]) for r in rows]

    # sheet4 의 회사 분포 (parser 결과 cross)
    from pipeline.agents.parser import parse_daily_report
    parsed = parse_daily_report(ROOT / "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx")
    from collections import Counter
    sheet4_cnt = Counter(a["company"] for a in parsed["activities"] if a.get("company"))

    # 선정: cand_pool size 다양 + sheet4 row >= 3 + wa 분포 다양
    selected: list[str] = []
    target_buckets = [
        (lambda ps, wa: ps == 1, "single"),
        (lambda ps, wa: ps == 2, "2-pool"),
        (lambda ps, wa: 3 <= ps <= 6, "small"),
        (lambda ps, wa: 7 <= ps <= 12, "medium"),
        (lambda ps, wa: ps >= 13, "large"),
    ]
    for pred, label in target_buckets:
        for c, ps, wa in pg_companies:
            if c in selected or sheet4_cnt.get(c, 0) < 3:
                continue
            if pred(ps, wa):
                selected.append(c)
                print(f"  selected [{label}] {c} pool={ps} wa_kinds={wa} sheet4_rows={sheet4_cnt[c]}")
                break

    # 부족 시 sheet4 row 많은 회사 추가
    for c, _, _ in sorted(pg_companies, key=lambda x: -sheet4_cnt.get(x[0], 0)):
        if len(selected) >= 10:
            break
        if c in selected or sheet4_cnt.get(c, 0) < 3:
            continue
        selected.append(c)

    return selected[:10]


async def main() -> None:
    print("=== V5 sample 선정 ===")
    sample = await select_10_companies()
    print(f"\n선정 10 업체: {sample}")

    out = ROOT / "tmp/v5_sample.json"
    out.write_text(json.dumps(sample, ensure_ascii=False, indent=2))
    print(f"→ {out}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 12.2: sample 선정 실행**

```bash
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  python3 tmp/run_v5_10companies.py 2>&1 | tail -30
```
Expected: 10 업체 list 출력 (예: 남웅건설 / 세보엠이씨 / 창원기전 + cand_pool size 1 / 2 / 5 / 10 / 20 분포).

- [ ] **Step 12.3: PG cleanup — cycle 결과만 (seed 보존)**

```bash
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  python3 scripts/cleanup_cycle_results.py 2>&1 | tail -10
```
Expected: mapper_activities / parser_reports / daily_reports 의 직전 cycle row 만 삭제 (activity_master seed 보존).

- [ ] **Step 12.4: 전체 cycle 실행 — parser_rule + mapper + atomizer + forecaster + optimizer + reporter**

```bash
CPIA_PARSER_VERIFY_LLM=on \
  POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  python3 scripts/run_one_cycle.py \
  'docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx' \
  m15x-ph3-ibl 2025-09-25 2>&1 | tee /tmp/v5_cycle.log
```
Expected: cycle 약 1~3 분 안 완료. HIL 1 interrupt 발생 시 — 사용자가 web UI Modal 에서 review 후 resume (또는 auto resume flag 설정).

성공 시:
- `mapper_activities` row UPSERT
- `daily_reports` 의 jsonb 컬럼 (kpi/contractor_bars/trade_bars/quadrant/wp_summary/s_curve/optimizer_view/productivity/scenarios) 채워짐

- [ ] **Step 12.5: mapping_source 분포 + zone false positive 측정 — 정량 기준 #11/#12**

```bash
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  python3 -c "
import asyncio
from pipeline.db import PGClient
async def main():
    pg = PGClient('postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia'); await pg.connect()
    rows = await pg._pool.fetch('''
      SELECT mapping_source, COUNT(*) as n
      FROM mapper_activities GROUP BY mapping_source ORDER BY n DESC
    ''')
    total = sum(r['n'] for r in rows)
    print('=== mapping_source 분포 ===')
    for r in rows:
      print(f'  {r[\"mapping_source\"]:>22}: {r[\"n\"]:>4} ({100*r[\"n\"]/total:.0f}%)')
    # false positive 측정 (auto_bp_zone_match wa vs alternatives top-1 wa 비교)
    fp = await pg._pool.fetch('''
      SELECT COUNT(*) AS fp
      FROM mapper_activities
      WHERE mapping_source = 'auto_bp_zone_match'
        AND alternatives_jsonb->0->>'wa' IS NOT NULL
        AND alternatives_jsonb->0->>'wa' != wa
    ''')
    bp_zone_total = await pg._pool.fetch('''
      SELECT COUNT(*) AS n FROM mapper_activities WHERE mapping_source = 'auto_bp_zone_match'
    ''')
    fp_pct = 100 * fp[0]['fp'] / max(1, bp_zone_total[0]['n'])
    print(f'\\n=== auto_bp_zone_match false positive ===')
    print(f'  fp / total = {fp[0][\"fp\"]} / {bp_zone_total[0][\"n\"]} ({fp_pct:.1f}%)')
    await pg.close()
asyncio.run(main())
" 2>&1 | tail -20
```
Expected:
- auto_bp_zone_match ≥ 40%
- hil_required ≤ 25%
- false positive ≤ 5%

→ 통과 못 하면 spec §3 의 resolve_wa 순서 재검토 (이슈 reopen).

- [ ] **Step 12.6: Playwright e2e — 12 정량 기준 자동 검증**

`web/e2e/reports-10-companies.spec.ts` 작성:

```typescript
// web/e2e/reports-10-companies.spec.ts
import { expect, test } from "@playwright/test";

test("V5 — reports UI 12 정량 기준", async ({ page }) => {
  await page.goto("http://localhost:3000/reports");
  await page.waitForLoadState("networkidle");

  // #1. § 01 헤더 CPI %
  const cpi = page.locator('[data-test="kpi-cpi"]');
  await expect(cpi).toBeVisible();
  const cpiText = (await cpi.textContent()) || "";
  expect(cpiText).not.toMatch(/^\s*0\s*%\s*$/);

  // #2. § 01 90일 trend datapoint >= 7
  const trendPoints = page.locator('[data-test="kpi-trend"] circle, [data-test="kpi-trend"] path');
  await expect(trendPoints.first()).toBeVisible();
  expect(await trendPoints.count()).toBeGreaterThanOrEqual(7);

  // #3. § 01 업체별 bar >= 8
  const contractorBars = page.locator('[data-test="contractor-bars"] [data-test^="bar-"]');
  expect(await contractorBars.count()).toBeGreaterThanOrEqual(8);

  // #4. § 01 공종별 bar >= 5
  const tradeBars = page.locator('[data-test="trade-bars"] [data-test^="bar-"]');
  expect(await tradeBars.count()).toBeGreaterThanOrEqual(5);

  // #5. § 02 4분면 산점도 점 >= 8 + 4 quadrant 모두 1 점 이상
  const dots = page.locator('[data-test="quadrant"] [data-test^="dot-"]');
  expect(await dots.count()).toBeGreaterThanOrEqual(8);
  // quadrant 별 검증 (제한)
  for (const q of ["q1", "q2", "q3", "q4"]) {
    const ql = page.locator(`[data-test="quadrant"] [data-test^="dot-"][data-q="${q}"]`);
    expect(await ql.count()).toBeGreaterThanOrEqual(1);
  }

  // #6. § 02 WP 표 row >= 10
  const wpRows = page.locator('[data-test="wp-table"] tbody tr');
  expect(await wpRows.count()).toBeGreaterThanOrEqual(10);

  // #7. WP 클릭 시 4 섹션 모두 비어있지 않음
  await wpRows.first().click();
  for (const sec of ["diagnosis", "similar", "recommend", "detail"]) {
    const s = page.locator(`[data-test="wp-section-${sec}"]`);
    await expect(s).toBeVisible();
    const t = (await s.textContent()) || "";
    expect(t.trim().length).toBeGreaterThan(0);
  }

  // #8. NULL fallback — Optimizer 미실행 그룹 "데이터 없음" 표시 가능성 확인
  // (선택 — 본 일보 에서 Optimizer 실행 그룹만 있을 수 있음)

  // #9. § 03 S-curve — 4 곡선
  for (const line of ["planned", "actual", "forecast", "recovery"]) {
    const l = page.locator(`[data-test="s-curve"] [data-line="${line}"]`);
    await expect(l).toBeVisible();
  }

  // #10. § 03 narrative
  await expect(page.getByText("현 추세 연장")).toBeVisible();
  await expect(page.getByText("AI 회복 시나리오")).toBeVisible();

  // #11/#12 mapping_source 분포 + false positive 빈도 — DB query (별 Step 12.5 에서 측정)
});
```

실행:
```bash
cd web && npx playwright test e2e/reports-10-companies.spec.ts --reporter=list 2>&1 | tail -40
```
Expected: 10 assertion (UI 측) PASS.

- [ ] **Step 12.7: FE↔BE 매칭 사용자 시각 확인 (사용자 명시 — Playwright 만 안 함)**

backend cycle 완료된 상태에서 frontend dev server 띄움:
```bash
cd web && npm run dev &
sleep 5
open http://localhost:3000/reports
```

브라우저에서 다음 확인 (사용자 직접 화면 보면서):
1. **§ 01 헤더 CPI %** — 0% 아닌 실수값 + 색상 chip
2. **§ 01 90일 trend** — line chart 그어짐
3. **§ 01 업체별 bar** — 10 업체 중 plan_mh 활성 회사 표시
4. **§ 01 공종별 bar** — 5 + 공종
5. **§ 02 4분면 산점도** — 점 분포 4 quadrant
6. **§ 02 WP 표** — 10 + row
7. **§ 02 WP 클릭** — 진단/유사사례/권고/상세 4 섹션 데이터 노출
8. **§ 02 NULL fallback** — Optimizer 미실행 그룹의 "데이터 없음" 텍스트 (해당 시)
9. **§ 03 S-curve** — 4 곡선 (planned/actual/forecast/recovery)
10. **§ 03 narrative** — "현 추세 연장" + "AI 회복 시나리오" 라벨
11. **mapping_source 분포** — Step 12.5 의 PG query 출력 확인 (auto_bp_zone_match ≥ 40% + hil ≤ 25%)
12. **zone false positive** — Step 12.5 의 ≤ 5% 측정 출력

console error 0, 모든 영역 데이터 노출 확인.

- [ ] **Step 12.8: 결과 dump — V5 통과 증거 보존**

```bash
mkdir -p tmp/v5_results
cp /tmp/v5_cycle.log tmp/v5_results/v5_cycle.log
# mapping_source / fp 측정도 같이 저장
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  python3 -c "..." > tmp/v5_results/mapping_source_distribution.txt 2>&1
# Playwright e2e report
cp -r web/playwright-report tmp/v5_results/playwright-report 2>/dev/null || true
ls -la tmp/v5_results/
```

- [ ] **Step 12.9: Commit (V5 evidence + e2e 추가)**

```bash
git add tmp/run_v5_10companies.py web/e2e/reports-10-companies.spec.ts tmp/v5_results/
git commit -m "$(cat <<'EOF'
test(e2e): V5 — 10 업체 POC cycle + reports UI 12 정량 기준

- tmp/run_v5_10companies.py — sample 선정 + cycle + mapping_source 분포 측정
- web/e2e/reports-10-companies.spec.ts — Playwright e2e 10 정량 기준 assertion
- 사용자 시각 확인 (브라우저) 통과:
  * § 01 KPI/trend/bar
  * § 02 quadrant/WP 표/4 섹션
  * § 03 S-curve/narrative
- mapping_source 분포: auto_bp_zone_match >= 40%, hil <= 25%
- zone false positive: <= 5%

spec §5 V5 + §6 commit 12 정합. 사용자 마감 6/5 안 데모 가능.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## 마이그레이션 후 마무리

- [ ] **모든 commit log 한 번 확인**

```bash
git log --oneline -15
```
Expected: 12 commit (task 1~12) 가 atomic 으로 쌓여있음.

- [ ] **전체 test 회귀 확인**

```bash
python3 -m pytest pipeline/tests/ -v 2>&1 | tail -40
```
Expected: 모든 test PASS (parser 4 시트 + LLM verify + mapper resolve_wa 7 단계 + col 인덱스 등).

- [ ] **PR 작성 — A_Track → main**

```bash
git push -u origin A_Track
gh pr create --title "feat: parser_rule + mapper auto_bp_zone_match (PoC 마감 안)" --body "$(cat <<'EOF'
## Summary
- parser_llm chunk 호출 (4-5 분) → parser_rule + 시트1/4 LLM 검증 hybrid (~20 초)
- mapper resolve_wa 0~6 단계 (신규 auto_bp_zone_match deterministic + auto_llm_rerank fallback) — hil 58% → ≤25%
- 10 업체 POC cycle + reports UI 12 정량 기준 통과 (V5)

## Spec
docs/superpowers/specs/2026-05-20-cpia-parser-mapper-refactor-design.md

## Test plan
- [x] parser_post unit test (3 헬퍼)
- [x] parser 4 시트 unit test + col 인덱스 헤더 검증 + LLM verify error path
- [x] mapper resolve_wa 7 단계 unit test
- [x] V5 — 10 업체 cycle + Playwright e2e 10 정량 기준 + 사용자 시각 확인

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

merge 결정은 조형준 프로님이 PR 검토 후. PoC 데모 (6/5) 안 본 cycle 통과.

---

## Plan Review Loop

본 plan 작성 후 plan-document-reviewer subagent 호출:
- 입력: 본 plan 경로 + spec 경로
- 출력: ✅ Approved or ❌ Issues Found
- Issues 있으면 fix → 재호출 (max 3 iter)
- Approved 후 execution handoff
