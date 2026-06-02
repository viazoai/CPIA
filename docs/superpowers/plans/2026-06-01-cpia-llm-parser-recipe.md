# CPIA LLM Parser — 헤더 recipe 2-pass 모듈 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 업체별 작업일보 N종 양식(P1: 같은 M15X 시스템 내 컬럼·헤더·시트명 변이)을 헤더 recipe 로 인식해 통합 스키마 `ParsedDailyReport` 로 정규화하는 **독립 모듈**을 만든다. live prod(`parser.py`/graph) 미수정, 데모 후 feature-flag 융합.

**Architecture:** 2-pass. Pass1 `recognize_format(wb)` → `FormatRecipe`(시트역할 + 시트별 헤더→필드 컬럼맵 + 시간대 블록 + group 경계 신호 + final_flag 컬럼), 3-tier ladder(Tier1 결정론 동의어 → Tier2 LLM fallback(헤더만, miss 시, fingerprint 캐시) → Tier3 안전망 loud-fail). Pass2 `extract_with_recipe(wb, recipe)` 는 기존 `parser.py` 의 sheet1/2/3/4 추출 휴리스틱을 **recipe 컬럼 주입으로 포팅**(재작성 금지). 산출 `ParsedDailyReport` 계약 불변.

**Tech Stack:** Python 3.11 (worktree venv `pipeline/.venv`), openpyxl, dataclasses, hashlib, pytest, Azure OpenAI `gpt-5.1-chat-ai-board-test`(Tier2, 테스트는 mock). 모든 .py 에 `from __future__ import annotations`.

**Spec:** `docs/superpowers/specs/2026-06-01-cpia-llm-parser-2pass-design.md`

**검증 오라클(불변):** live `parser.py:625` `parse_daily_report` 의 실 산출이 골든. baseline 등가 = 통합 act=1193 / bp=99 / job=975 / eq=1111, 업체 act=33 / job=76 / eq=68.

**작업 환경:** worktree `/Users/kyungseoplee/cpia-parser-recipe-wt` (브랜치 `feature/parser-recipe`). 실행 python = `pipeline/.venv/bin/python`. 테스트 = `cd pipeline && ../pipeline/.venv/bin/python -m pytest ...` (또는 worktree 루트에서 `pipeline/.venv/bin/python -m pytest pipeline/tests/...`).

---

## File Structure

신규 (전부 `pipeline/agents/recipe/` 패키지 — live `parser.py` 미수정):

| 파일 | 책임 |
|---|---|
| `pipeline/agents/recipe/__init__.py` | 공개 API: `parse_with_recipe`, `recognize_format`, `FormatRecipe` re-export |
| `pipeline/agents/recipe/model.py` | `FormatRecipe` / `SheetRecipe` dataclass + 필수필드 정의 |
| `pipeline/agents/recipe/fingerprint.py` | `fingerprint(wb)` — 시트명 + 정규화 헤더텍스트 sha256 |
| `pipeline/agents/recipe/synonyms.py` | 시트 role alias + 헤더 동의어 테이블 (상수) |
| `pipeline/agents/recipe/bpcode.py` | `is_bp_code_v2`(다중패턴 확장) + `looks_like_code_no_korean`(누출 가드) |
| `pipeline/agents/recipe/recognize.py` | `recognize_format` (Tier1/2/3) + 캐시 I/O + LLM fallback hook |
| `pipeline/agents/recipe/extract.py` | sheet1/2/3/4 포팅 추출 + `extract_with_recipe` + `parse_with_recipe` |
| `data/parser_recipes/` | recipe 캐시 디렉토리 (`.gitkeep`) |
| `scripts/synth_formats.py` | V1~V5 합성 변이 생성기 |
| `pipeline/tests/test_parser_recipe.py` | 골든·합성·결정성·invariant 테스트 |

**재사용(import, 미수정):**
- `pipeline.agents.parser`: `ParseError`, `_safe_int`, `_safe_num`, `_normalize_unit`, `_disc_abbrev_to_kr`, `_is_admin_job`, `_shift_dict_sum`, `_shift_dict_row`, `_norm_header`, `_extract_meta`
- `pipeline.agents.parser_post`: `normalize_company`, `split_company_and_zone`, `extract_zone`
- `pipeline.state`: `Activity`, `BPSummary`, `JobAllocation`, `EquipmentAllocation`, `ParsedDailyReport`, `TimeShiftCounts`
- `pipeline.collector.filename_parser`: `parse_filename` (파일명 bp_name 추출 — company mismatch 비교용)

**포팅 원천(전사 대상, 미수정 원본):**
- sheet1: `parser.py:128-245` `_parse_sheet1_bp_summaries`
- sheet2: `parser.py:256-339` `_parse_sheet2_job_allocations`
- sheet3: `parser.py:512-582` `_parse_sheet3_equipment_allocations`
- sheet4: `parser.py:357-509` `_resolve_sheet4_columns` + `_build_activity` + `_parse_sheet4_activities`

---

## Task 0: 워크트리 venv 셋업 (선행 — 코드 전)

**Files:** 없음 (환경). git worktree 는 untracked `pipeline/.venv` 를 공유하지 않아 이 워크트리엔 venv 가 없다. pyproject 는 Python ≥3.11 요구(시스템 기본 3.9.6, `python3.11` = `/opt/homebrew/bin/python3.11`).

- [ ] **Step 1: venv 생성**
  Run: `cd /Users/kyungseoplee/cpia-parser-recipe-wt && /opt/homebrew/bin/python3.11 -m venv pipeline/.venv`
- [ ] **Step 2: 의존성 설치**
  Run: `pipeline/.venv/bin/pip install -e pipeline`
  (실패 시 최소 셋: `pipeline/.venv/bin/pip install openpyxl pytest openai`)
- [ ] **Step 3: import 검증**
  Run: `pipeline/.venv/bin/python -c "from pipeline.agents.parser import parse_daily_report; from pipeline.agents.parser_post import normalize_company; print('ok')"`
  Expected: `ok` (누락 dep 있으면 설치)
- [ ] **Step 4: baseline 오라클 확인 (실파일)**
  Run: `pipeline/.venv/bin/python -c "from pipeline.agents.parser import parse_daily_report as p; r=p('docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx'); print(len(r['activities']), len(r['bp_summaries']), len(r['job_allocations']), len(r['equipment_allocations']))"`
  Expected: `1193 99 975 1111`
  (venv 는 gitignore — 커밋 없음)

---

## Task 1: 패키지 scaffold + recipe 데이터 모델

**Files:**
- Create: `pipeline/agents/recipe/__init__.py`, `pipeline/agents/recipe/model.py`
- Create: `data/parser_recipes/.gitkeep`
- Test: `pipeline/tests/test_parser_recipe.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_parser_recipe.py
from __future__ import annotations
from pipeline.agents.recipe.model import FormatRecipe, SheetRecipe, REQUIRED_FIELDS


def test_recipe_model_construct():
    sr = SheetRecipe(
        sheet_name="4.물량",
        columns={"work_content": 7, "unit": 8, "today_qty": 11, "trade": 4, "bp": 5},
        timeshift_blocks={},
        group_boundary="bp_company_pair",
        header_rows=(3, 4),
        final_flag_col=None,
    )
    fr = FormatRecipe(
        fingerprint="abc",
        format_class="업체",
        sheets={"activity": sr},
        generated_by="deterministic",
        confidence=1.0,
    )
    assert fr.sheets["activity"].columns["today_qty"] == 11
    assert "today_qty" in REQUIRED_FIELDS["activity"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/kyungseoplee/cpia-parser-recipe-wt && pipeline/.venv/bin/python -m pytest pipeline/tests/test_parser_recipe.py::test_recipe_model_construct -v`
Expected: FAIL — `ModuleNotFoundError: pipeline.agents.recipe`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/agents/recipe/__init__.py
from __future__ import annotations
from pipeline.agents.recipe.model import FormatRecipe, SheetRecipe  # noqa: F401
```

```python
# pipeline/agents/recipe/model.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["bp_summary", "job", "equip", "activity"]

# Pass2 추출에 반드시 매핑돼야 하는 필드 (미매핑 시 Tier3 안전망)
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "bp_summary": ("bp_company", "scope", "work_today", "today_incr_total"),
    "job": ("trade", "bp_company", "disc_code", "job_type"),
    "equip": ("trade", "bp", "equip_big"),
    "activity": ("trade", "bp", "work_content", "unit", "today_qty"),
}


@dataclass
class SheetRecipe:
    sheet_name: str
    columns: dict[str, int]
    timeshift_blocks: dict[str, int]            # block_name -> 조출(첫칸) col_start
    group_boundary: str                          # "mm01_anchor" | "col30_merge" | "bp_company_pair" | "equip_triple" | "unknown"
    header_rows: tuple[int, int]
    final_flag_col: int | None = None


@dataclass
class FormatRecipe:
    fingerprint: str
    format_class: Literal["통합", "업체", "unknown"]
    sheets: dict[str, SheetRecipe] = field(default_factory=dict)
    generated_by: Literal["deterministic", "llm", "human"] = "deterministic"
    confidence: float = 1.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/kyungseoplee/cpia-parser-recipe-wt && pipeline/.venv/bin/python -m pytest pipeline/tests/test_parser_recipe.py::test_recipe_model_construct -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/kyungseoplee/cpia-parser-recipe-wt
mkdir -p data/parser_recipes && touch data/parser_recipes/.gitkeep
git add pipeline/agents/recipe/__init__.py pipeline/agents/recipe/model.py pipeline/tests/test_parser_recipe.py data/parser_recipes/.gitkeep
git commit -m "feat(recipe): FormatRecipe/SheetRecipe 데이터 모델 + 패키지 scaffold"
```

---

## Task 2: fingerprint (시트명 + 헤더텍스트 해시)

**Files:**
- Create: `pipeline/agents/recipe/fingerprint.py`
- Test: `pipeline/tests/test_parser_recipe.py`

- [ ] **Step 1: Write the failing test** (실파일 사용)

```python
import openpyxl
from pipeline.agents.recipe.fingerprint import fingerprint

UNI = "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
BP = "docs/sample/업체작업일보_M15X_PH4_041_M15X_PH4_UT_ 중원엔지니어링_UT배관공사_FAB_250917.xlsx"


def test_fingerprint_distinguishes_and_is_stable():
    wb_u = openpyxl.load_workbook(UNI, data_only=True)
    wb_b = openpyxl.load_workbook(BP, data_only=True)
    fu1 = fingerprint(wb_u)
    fu2 = fingerprint(wb_u)
    fb = fingerprint(wb_b)
    assert fu1 == fu2                 # 같은 wb 두 번 → 동일 (결정성)
    assert fu1 != fb                  # 통합 vs 업체 → 다름
    assert len(fu1) == 64             # sha256 hex
    wb_u.close(); wb_b.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pipeline/.venv/bin/python -m pytest pipeline/tests/test_parser_recipe.py::test_fingerprint_distinguishes_and_is_stable -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/agents/recipe/fingerprint.py
from __future__ import annotations
import hashlib
from pipeline.agents.parser import _norm_header


def fingerprint(wb, header_scan_rows: int = 5) -> str:
    """시트명(정렬) + 각 시트 헤더 영역(앞 N행) 정규화 텍스트의 sha256.

    같은 양식 = 같은 fingerprint (캐시 키). 컬럼 시프트·시트명/헤더 변이 시 달라짐.
    """
    parts: list[str] = []
    for name in sorted(wb.sheetnames):
        parts.append(f"##{name}")
        ws = wb[name]
        max_col = ws.max_column or 0
        for r in range(1, header_scan_rows + 1):
            cells = [_norm_header(ws.cell(r, c).value) for c in range(1, max_col + 1)]
            parts.append("|".join(cells))
    blob = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
```

- [ ] **Step 4: Run test to verify it passes** — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/recipe/fingerprint.py pipeline/tests/test_parser_recipe.py
git commit -m "feat(recipe): fingerprint — 시트명+헤더 sha256 캐시키"
```

---

## Task 3: BP코드 v2 다중패턴 + 누출 가드 (spec §4.1 ①)

**Files:**
- Create: `pipeline/agents/recipe/bpcode.py`
- Test: `pipeline/tests/test_parser_recipe.py`

- [ ] **Step 1: Write the failing test**

```python
from pipeline.agents.recipe.bpcode import is_bp_code_v2, looks_like_code_no_korean


def test_bp_code_v2_accepts_variants():
    # 기존 통합/업체 (회귀)
    assert is_bp_code_v2("PH_X-088")
    assert is_bp_code_v2("M15X_PH4_041")
    # P1 변종 — 누출 차단 대상
    assert is_bp_code_v2("M15X-PH4-041")     # dash
    assert is_bp_code_v2("M15X_PH4_041A")    # trailing suffix
    # 회사명은 코드 아님
    assert not is_bp_code_v2("중원엔지니어링")
    assert not is_bp_code_v2("협력업체01")


def test_leak_guard_flags_ascii_only_codeish():
    # 한글 0글자 + 코드 모양 → 회사명 아님 (격리 대상)
    assert looks_like_code_no_korean("ABC-2025-001")
    assert not looks_like_code_no_korean("중원엔지니어링")
    assert not looks_like_code_no_korean("Hyundai E&C")  # 공백 포함 영문 회사명 — 코드 모양 아님
```

- [ ] **Step 2: Run test to verify it fails** — Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/agents/recipe/bpcode.py
from __future__ import annotations
import re

# 기존 _BP_PATTERNS(parser.py:97) 확장: 구분자 [_\- ], 선택적 trailing 영문 1글자.
# 과확장 금지 — 반드시 영숫자 prefix + PH/Ph + 숫자 + 구분자 + 숫자 구조.
_BP_PATTERNS_V2: tuple[re.Pattern[str], ...] = (
    re.compile(r"^PH[_\- ]?X[_\- ]?\d+[A-Za-z]?$"),                      # 통합: PH_X-088
    re.compile(r"^[A-Za-z][A-Za-z0-9]*[_\- ][Pp][Hh]\d+[_\- ]\d+[A-Za-z]?$"),  # 업체: M15X_PH4_041 (+변종)
)
_HANGUL_RE = re.compile(r"[가-힣]")
_CODEISH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")  # 공백 없는 영숫자+구분자


def is_bp_code_v2(v: object) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    return any(p.match(s) for p in _BP_PATTERNS_V2)


def looks_like_code_no_korean(v: object) -> bool:
    """한글 0글자 + 코드 모양(공백 없는 영숫자+구분자) → company 로 두면 안 됨.

    외래 코드(ABC-2025-001) 가 _BP_PATTERNS_V2 를 빠져나가 company 로 누출되는 것 차단용.
    공백 포함 영문 회사명(Hyundai E&C)은 코드 모양 아님 → False(정상 회사명).
    """
    if v is None:
        return False
    s = str(v).strip()
    if _HANGUL_RE.search(s):
        return False
    return bool(_CODEISH_RE.match(s)) and any(ch.isdigit() for ch in s)
```

- [ ] **Step 4: Run test to verify it passes** — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/recipe/bpcode.py pipeline/tests/test_parser_recipe.py
git commit -m "feat(recipe): BP코드 v2 다중패턴 + 누출 가드 (한글0글자 코드 격리)"
```

---

## Task 4: 동의어/alias 테이블

**Files:**
- Create: `pipeline/agents/recipe/synonyms.py`
- Test: `pipeline/tests/test_parser_recipe.py`

동의어 테이블은 헤더 텍스트(`_norm_header` 로 공백 제거)를 스키마 필드로 매핑한다. 합성 변이(V2: `금일실적→당일실적` 등)와 영문 헤더(V5)를 흡수하도록 동의어 그룹으로.

- [ ] **Step 1: Write the failing test**

```python
from pipeline.agents.recipe.synonyms import field_for_header, role_for_sheet


def test_synonyms_map_headers_and_sheets():
    assert field_for_header("금일실적") == "today_qty"
    assert field_for_header("당일실적") == "today_qty"      # V2 동의어
    assert field_for_header("대표물량_작업내용") == "work_content"
    assert field_for_header("작업내용") == "work_content"
    assert field_for_header("BP사") == "bp"
    assert field_for_header("업체명") == "company_col"
    # sheet2/3 필수필드 (실측 헤더)
    assert field_for_header("관리자/근로자") == "disc_code"   # sheet2 col4 (Mm01 앵커)
    assert field_for_header("직종") == "job_type"            # sheet2 col6
    assert field_for_header("대분류") == "equip_big"          # sheet3 col4
    assert field_for_header("중분류") == "equip_mid"
    assert field_for_header("규 격") == "equip_spec"          # _norm_header 가 공백 제거 → "규격"
    # sheet1 작업텍스트 (헤더에 날짜 brackets 붙음 → substring)
    assert field_for_header("전일 작업사항 [09/24]") == "work_prev"
    assert field_for_header("금일 작업사항 [09/25]") == "work_today"
    assert field_for_header("명일 작업사항 [09/26]") == "work_tomorrow"
    assert field_for_header("ZZZ알수없음") is None
    assert role_for_sheet("4.물량") == "activity"
    assert role_for_sheet("물량집계") == "activity"          # V1 시트명 변이 alias
    assert role_for_sheet("1.출력인원 현황") == "bp_summary"
    assert role_for_sheet("2.직종별 인원현황") == "job"
    assert role_for_sheet("3.장비현황") == "equip"
```

- [ ] **Step 2: Run test to verify it fails** — Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/agents/recipe/synonyms.py
from __future__ import annotations
from pipeline.agents.parser import _norm_header

# 헤더(정규화, _norm_header 가 공백 제거) -> 스키마 필드. 동의어는 같은 값으로.
_FIELD_SYNONYMS: dict[str, str] = {
    "공종": "trade", "Dis": "trade",
    "BP사": "bp", "협력업체": "bp",
    "업체명": "company_col",
    "Scope": "scope",
    "단위": "unit",
    "금일실적": "today_qty", "당일실적": "today_qty", "todayactual": "today_qty",
    "금일누적": "today_cum",
    "전일누적": "yesterday_cum",
    "총물량": "plan_total",
    # sheet2 (직종) 필수필드
    "관리자/근로자": "disc_code",     # col4 = Mm01/sk01 앵커
    "직종": "job_type",              # col6 = BP소장/배관공 등
    # sheet3 (장비) 필수/보조필드
    "대분류": "equip_big", "장비명": "equip_big",
    "중분류": "equip_mid",
    "규격": "equip_spec",            # "규 격" → _norm_header → "규격"
}
# 부분일치(substring) 필드 — 헤더에 토큰 포함 시 매핑 (날짜 brackets·group 라벨 흡수)
_FIELD_CONTAINS: list[tuple[str, str]] = [
    ("대표물량", "work_content"), ("작업내용", "work_content"),
    ("전일작업", "work_prev"), ("금일작업", "work_today"), ("명일작업", "work_tomorrow"),
]

# 시트명(정규화) -> role. canonical + 변이 alias.
_SHEET_ALIASES: dict[str, str] = {
    "1.출력인원현황": "bp_summary", "출력인원현황": "bp_summary",
    "2.직종별인원현황": "job", "직종별인원현황": "job", "직종별인원": "job",
    "3.장비현황": "equip", "장비현황": "equip",
    "4.물량": "activity", "물량": "activity", "물량집계": "activity", "수량집계": "activity",
}


def field_for_header(raw) -> str | None:
    h = _norm_header(raw)
    if not h:
        return None
    if h in _FIELD_SYNONYMS:
        return _FIELD_SYNONYMS[h]
    if h.lower() in _FIELD_SYNONYMS:
        return _FIELD_SYNONYMS[h.lower()]
    for tok, fld in _FIELD_CONTAINS:
        if tok in h:
            return fld
    return None


def role_for_sheet(name: str) -> str | None:
    return _SHEET_ALIASES.get(_norm_header(name))
```

- [ ] **Step 4: Run test to verify it passes** — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/recipe/synonyms.py pipeline/tests/test_parser_recipe.py
git commit -m "feat(recipe): 헤더 동의어 + 시트 role alias 테이블 (V1/V2 변이 흡수)"
```

---

## Task 5: 시트별 recipe resolver (Tier1 결정론) + recognize_format

**Files:**
- Create: `pipeline/agents/recipe/recognize.py`
- Test: `pipeline/tests/test_parser_recipe.py`

**resolver 가 시트별로 발견할 것** (실측 헤더 기준):
- 공통: `field_for_header` 로 `trade/bp/company_col/scope/unit/today_qty/...` 컬럼 인덱스.
- **시간대 6칸 블록**: 헤더 row 에서 `조출`(block 첫칸) 위치를 찾고, 그 위 group 라벨(`전일누계`/`금일투입`/`금일누계`/`전일투입인원`/`금일투입인원` 등)으로 block 이름 결정. sheet1=4블록(yest_incr/yest_cum/today_incr/today_cum), sheet2/3=3블록(yest_cum/today_incr/today_cum).
- **group_boundary 신호**: bp_summary=`col30_merge`(금일투입 Total 병합), job=`mm01_anchor`(disc_code 컬럼 첫 `Mm01`), equip=`equip_triple`(trade+bp+equip_big 동시), activity=company_col 있으면 통합(ffill) 없으면 `bp_company_pair`.
- **final_flag_col**: 헤더/데이터에 `최종`('O') 컬럼 있으면 그 인덱스, 없으면 None.

> 컬럼 인덱스 매핑이 끝나면 canonical 양식에서 실측한 값과 일치해야 한다(아래 테스트). sheet4 는 `_resolve_sheet4_columns`(parser.py:357) 로직을 그대로 호출/재사용해도 됨.

- [ ] **Step 1: Write the failing test** (canonical 양식 컬럼 실측 고정)

```python
import openpyxl
from pipeline.agents.recipe.recognize import recognize_format

UNI = "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
BP = "docs/sample/업체작업일보_M15X_PH4_041_M15X_PH4_UT_ 중원엔지니어링_UT배관공사_FAB_250917.xlsx"


def test_recognize_integrated_format():
    wb = openpyxl.load_workbook(UNI, data_only=True)
    r = recognize_format(wb)
    assert r.format_class == "통합"
    assert r.generated_by == "deterministic"
    assert r.confidence == 1.0
    # sheet4 컬럼 (통합 실측: company_col=6 이 있어 이후 1칸 우측 시프트)
    # trade=4 bp=5 company_col=6 scope=7 work_content=8 unit=9 today_qty=12
    a = r.sheets["activity"]
    assert a.columns["trade"] == 4 and a.columns["bp"] == 5
    assert a.columns["company_col"] == 6 and a.columns["work_content"] == 8
    assert a.columns["unit"] == 9 and a.columns["today_qty"] == 12
    # sheet2 final_flag 존재(통합)
    assert r.sheets["job"].final_flag_col == 25
    # sheet2 timeshift (실측: today_cum block 첫칸 col19)
    assert r.sheets["job"].timeshift_blocks["today_cum"] == 19
    wb.close()


def test_recognize_vendor_format():
    wb = openpyxl.load_workbook(BP, data_only=True)
    r = recognize_format(wb)
    assert r.format_class == "업체"
    a = r.sheets["activity"]
    assert "company_col" not in a.columns          # 업체는 업체명 컬럼 없음
    assert a.columns["work_content"] == 7 and a.columns["today_qty"] == 11
    assert r.sheets["job"].final_flag_col is None   # 업체는 'O' 게이트 없음
    wb.close()
```

> 주의: 위 컬럼 인덱스는 **Task 시작 시 `pipeline/.venv/bin/python` 으로 두 실파일을 열어 헤더를 재실측해 확정**하라(다른 세션 골든과 동일해야 함). sheet1 timeshift today_incr block=col24, today_incr_total=col30, today_cum_total=col37 도 실측.

- [ ] **Step 2: Run test to verify it fails** — Expected: FAIL

- [ ] **Step 3: Write implementation**

`recognize.py` 에 `recognize_format(wb)` 구현:
1. `fingerprint(wb)` 계산 → 캐시 조회(Task 13 에서 추가; 지금은 skip).
2. 각 시트명 → `role_for_sheet`; role 별로 `_resolve_sheet_recipe(ws, role)` 호출.
3. `_resolve_sheet_recipe`:
   - sheet4(activity): `_resolve_sheet4_columns(ws)`(parser.py:357 import) 호출해 컬럼맵 획득. `group_boundary` = `company_col` 있으면 "col30_merge"(N/A, 통합 ffill) 표기상 "bp_company_pair" 아님 → activity 는 boundary 안 씀, "n/a" 로 둔다.
   - sheet1/2/3: 헤더 2-row 스캔으로 `field_for_header` 매핑 + 시간대 블록(조출 위치) + group_boundary + final_flag_col 발견.
   - 필수필드(`REQUIRED_FIELDS[role]`) 미매핑 시 그 필드를 `missing` 에 수집.
4. `format_class`: activity 시트에 `company_col` 있으면 "통합", 없으면 "업체".
5. `confidence` = 전체 role 의 (매핑 필수필드/총 필수필드) 비율. 모두 매핑 → 1.0.
6. Tier2/Tier3 분기는 Task 13/14/15 에서 추가; 지금은 결정론 성공 경로만.

```python
# pipeline/agents/recipe/recognize.py (핵심 골격 — 시간대/경계 발견 로직 포함)
from __future__ import annotations
import openpyxl
from pipeline.agents.parser import _resolve_sheet4_columns, _norm_header
from pipeline.agents.recipe.model import FormatRecipe, SheetRecipe, REQUIRED_FIELDS
from pipeline.agents.recipe.fingerprint import fingerprint
from pipeline.agents.recipe.synonyms import field_for_header, role_for_sheet

_SHIFT_GROUP_LABELS = {  # group 라벨 토큰 -> block. ★순서 중요: 긴/구체 토큰 먼저
    # (substring 매칭이라 '금일투입누계' 가 '금일투입' 보다 먼저 검사돼야 함 — 통합 sheet3)
    "전일투입누계": "yest_cum", "금일투입누계": "today_cum",   # 통합 sheet3 (전일투입누계/금일투입누계)
    "전일누계": "yest_cum", "전일누적": "yest_cum",            # sheet2 / sheet1 전일누적인원
    "금일누계": "today_cum", "금일누적": "today_cum",          # sheet2 / sheet1 금일누적인원
    "전일투입": "yest_incr",                                   # sheet1 전일투입인원
    "금일투입": "today_incr",                                  # sheet1 금일투입인원 / sheet2·통합sheet3 금일투입
}
# 검증(실측): 통합 sheet3 = 전일투입누계→yest_cum, 금일투입→today_incr, 금일투입누계→today_cum.
# 업체 sheet3 = 전일누계→yest_cum, 금일투입→today_incr, 금일누계→today_cum. 둘 다 3블록 해소돼야 Task9 eq=1111/68 통과.


def _find_timeshift_blocks(ws, label_row: int, sub_row: int, max_col: int) -> dict[str, int]:
    """label_row 의 group 라벨 아래 sub_row 에서 '조출' 첫칸을 찾아 block_start 매핑."""
    blocks: dict[str, int] = {}
    for c in range(1, max_col + 1):
        sub = _norm_header(ws.cell(sub_row, c).value)
        if sub != "조출":
            continue
        # 위쪽(label_row..label_row-1)에서 가장 가까운 group 라벨 탐색
        block_name = None
        for lr in (label_row, label_row - 1):
            for cc in range(c, 0, -1):
                lbl = _norm_header(ws.cell(lr, cc).value)
                hit = next((b for tok, b in _SHIFT_GROUP_LABELS.items() if tok in lbl), None)
                if hit:
                    block_name = hit
                    break
            if block_name:
                break
        if block_name and block_name not in blocks:
            blocks[block_name] = c
    return blocks


def _resolve_sheet_recipe(ws, role: str) -> tuple[SheetRecipe, list[str]]:
    max_col = ws.max_column or 0
    if role == "activity":
        cols = _resolve_sheet4_columns(ws)  # 기존 헤더해석 재사용 (회귀 안전)
        boundary = "n/a"
        sr = SheetRecipe(ws.title, cols, {}, boundary, (3, 4), None)
        missing = [f for f in REQUIRED_FIELDS["activity"] if f not in cols]
        return sr, missing

    # sheet1/2/3 헤더 row 추정: bp_summary = (3,4), job/equip = (4,5)
    hdr = (3, 4) if role == "bp_summary" else (4, 5)
    cols: dict[str, int] = {}
    for c in range(1, max_col + 1):
        for hr in hdr:
            fld = field_for_header(ws.cell(hr, c).value)
            if fld and fld not in cols:
                cols[fld] = c
    # bp_company 통합 키 (sheet1 col5 / sheet2·3 col3 = BP사/협력업체 동일 컬럼)
    if "bp" in cols:
        cols.setdefault("bp_company", cols["bp"])
    blocks = _find_timeshift_blocks(ws, hdr[0], hdr[1], max_col)
    # final_flag: 데이터에 'O' 가 있는 컬럼(통합) — 25 고정 탐지(실측) 또는 헤더 '최종'
    final_flag_col = None
    for c in range(1, max_col + 1):
        if any(ws.cell(r, c).value == "O" for r in range(hdr[1] + 1, min((ws.max_row or 0) + 1, hdr[1] + 200))):
            final_flag_col = c
            break
    boundary = {"bp_summary": "col30_merge", "job": "mm01_anchor", "equip": "equip_triple"}[role]
    # 시트1 group total 컬럼(today_incr_total/today_cum_total): 금일투입/금일누계 block 의 Total(조출+5)
    if role == "bp_summary":
        if "today_incr" in blocks:
            cols["today_incr_total"] = blocks["today_incr"] + 6   # 조출~철야(5) + Total(1)
        if "today_cum" in blocks:
            cols["today_cum_total"] = blocks["today_cum"] + 6
    sr = SheetRecipe(ws.title, cols, blocks, boundary, hdr, final_flag_col)
    missing = [f for f in REQUIRED_FIELDS[role] if f not in cols]
    return sr, missing


def recognize_format(wb) -> FormatRecipe:
    fp = fingerprint(wb)
    sheets: dict[str, SheetRecipe] = {}
    total_req = 0
    mapped_req = 0
    for name in wb.sheetnames:
        role = role_for_sheet(name)
        if role is None:
            continue
        sr, missing = _resolve_sheet_recipe(wb[name], role)
        sheets[role] = sr
        total_req += len(REQUIRED_FIELDS[role])
        mapped_req += len(REQUIRED_FIELDS[role]) - len(missing)
    fmt = "통합" if ("activity" in sheets and "company_col" in sheets["activity"].columns) else "업체"
    conf = (mapped_req / total_req) if total_req else 0.0
    return FormatRecipe(fp, fmt, sheets, "deterministic", conf)
```

> **재실측 확인(필수)**: 위 `today_incr_total = blocks["today_incr"]+6`, final_flag 탐지 컬럼=25, sheet2 today_cum block=19 등은 canonical 양식에서 실측해 테스트 기대값과 맞춰라. 어긋나면 offset/탐지로직을 실측에 맞게 조정(추측 금지).

- [ ] **Step 4: Run test to verify it passes** — Expected: PASS (두 테스트)

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/recipe/recognize.py pipeline/tests/test_parser_recipe.py
git commit -m "feat(recipe): recognize_format Tier1 결정론 — 시트역할+헤더컬럼+시간대블록+경계신호"
```

---

## Task 6: sheet4 추출 포팅 + 첫 baseline 등가

**Files:**
- Create: `pipeline/agents/recipe/extract.py`
- Test: `pipeline/tests/test_parser_recipe.py`

`parser.py:403-509`(`_build_activity` + `_parse_sheet4_activities`)를 `extract.py` 로 전사하되, `cols = _resolve_sheet4_columns(ws)` 대신 **`cols = recipe.sheets["activity"].columns`** 를 받아 쓴다. `_build_activity` 는 이미 `cols` 인자를 받으므로 그대로 import/재사용 가능.

- [ ] **Step 1: Write the failing test**

```python
import openpyxl
from pipeline.agents.recipe.recognize import recognize_format
from pipeline.agents.recipe.extract import extract_sheet4
from pipeline.agents.parser import parse_daily_report

UNI = "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
BP = "docs/sample/업체작업일보_M15X_PH4_041_M15X_PH4_UT_ 중원엔지니어링_UT배관공사_FAB_250917.xlsx"


def _activities_via_recipe(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    r = recognize_format(wb)
    acts = extract_sheet4(wb[r.sheets["activity"].sheet_name], r.sheets["activity"])
    wb.close()
    return acts


def test_sheet4_equiv_integrated():
    golden = parse_daily_report(UNI)["activities"]
    got = _activities_via_recipe(UNI)
    assert len(got) == len(golden) == 1193
    assert got == golden            # dict 완전 일치


def test_sheet4_equiv_vendor():
    golden = parse_daily_report(BP)["activities"]
    got = _activities_via_recipe(BP)
    assert len(got) == len(golden) == 33
    assert got == golden
```

- [ ] **Step 2: Run test to verify it fails** — Expected: FAIL

- [ ] **Step 3: Write implementation** — `extract.py` 에 `extract_sheet4(ws, sheet_recipe)`:
  - `parser.py:458-509` 로직 전사. `cols = sheet_recipe.columns`. `has_company_col = "company_col" in cols`. BP 판정은 **`is_bp_code_v2`**(Task3) 사용(누출 가드 포함). `_build_activity` 는 `from pipeline.agents.parser import _build_activity` 재사용.

- [ ] **Step 4: Run test to verify it passes** — Expected: PASS (1193 / 33 완전 일치)

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/recipe/extract.py pipeline/tests/test_parser_recipe.py
git commit -m "feat(recipe): sheet4 추출 포팅 — 통합1193/업체33 parse_daily_report 완전 등가"
```

---

## Task 7: sheet1 추출 포팅 (col30 경계 + 시간대 4블록)

**Files:** Modify `pipeline/agents/recipe/extract.py`; Test 추가.

`parser.py:128-245`(`_parse_sheet1_bp_summaries`) 전사. 하드코딩 컬럼 → recipe 치환표:

| 원본 리터럴 | recipe 치환 |
|---|---|
| `ws.cell(r, 5)` (BP/회사) | `cols["bp_company"]` |
| `ws.cell(r, 6)` (zone/scope) | `cols["scope"]` |
| `ws.cell(r, 7/8/9)` (작업텍스트) | `cols["work_prev"]/["work_today"]/["work_tomorrow"]` (없으면 skip) |
| `_shift_dict_sum(ws, start, end, 24/31/10/17)` | `blocks["today_incr"]/["today_cum"]/["yest_incr"]/["yest_cum"]` |
| `ws.cell(start, 30)` (today_incr_total) | `cols["today_incr_total"]` |
| `ws.cell(start, 37)` (today_cum_total) | `cols["today_cum_total"]` |
| col30 merged 경계 스캔 | `cols["today_incr_total"]` 컬럼의 merged_cells 스캔 |
| `_is_bp_code` | `is_bp_code_v2` |

> work_prev/today/tomorrow 헤더는 `field_for_header` 에 추가 필요: `전일작업사항→work_prev`, `금일작업사항→work_today`, `명일작업사항→work_tomorrow` (Task4 synonyms 에 보강 + Task4 테스트 갱신, 또는 본 Task 에서 추가).

- [ ] **Step 1: Write the failing test**

```python
from pipeline.agents.recipe.extract import extract_sheet1


def _bp_via_recipe(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    r = recognize_format(wb)
    out = extract_sheet1(wb[r.sheets["bp_summary"].sheet_name], r.sheets["bp_summary"])
    wb.close()
    return out


def test_sheet1_equiv_integrated():
    golden = parse_daily_report(UNI)["bp_summaries"]
    got = _bp_via_recipe(UNI)
    assert len(got) == len(golden) == 99
    assert got == golden


def test_sheet1_equiv_vendor_company():
    got = _bp_via_recipe(BP)
    assert {s["company"] for s in got} == {"중원엔지니어링"}   # 누출 0, 정규화 OK
```

- [ ] **Step 2-4:** 구현 → PASS (99 완전 일치, 업체 company 정상)
- [ ] **Step 5: Commit** — `feat(recipe): sheet1 추출 포팅 — col30 경계+시간대4블록, 통합99 등가`

---

## Task 8: sheet2 추출 포팅 (Mm01 + final_flag 게이트 + 시간대 3블록)

**Files:** Modify `extract.py`; Test 추가.

`parser.py:256-339` 전사. 치환표:

| 원본 | recipe |
|---|---|
| `has_final_flag = any(ws.cell(r,25)=='O' ...)` | `sr.final_flag_col is not None` (그리고 그 컬럼으로 검사) |
| `ws.cell(r, 4)` (Mm01/disc_code) | `cols["disc_code"]` |
| `ws.cell(r, 2)` (공종) | `cols["trade"]` |
| `ws.cell(r, 3)` (BP/회사) | `cols["bp_company"]` |
| `ws.cell(r, 6)` (job_type) | `cols["job_type"]` |
| `ws.cell(r, 25)` (최종) | `cols 의 final_flag_col` |
| `_shift_dict_row(ws, r, 7/13/19)` | `blocks["yest_cum"]/["today_incr"]/["today_cum"]` |
| `_is_bp_code` | `is_bp_code_v2` |
| group 시작 `c4 == "Mm01"` | `str(ws.cell(r, cols["disc_code"]).value) == "Mm01"` (mm01_anchor) |

import 재사용: `_disc_abbrev_to_kr`, `_is_admin_job`, `_shift_dict_row`, `normalize_company`, `split_company_and_zone`.

- [ ] **Step 1: Failing test** — `extract_sheet2` 등가:

```python
from pipeline.agents.recipe.extract import extract_sheet2
def test_sheet2_equiv():
    for path, n in [(UNI, 975), (BP, 76)]:
        golden = parse_daily_report(path)["job_allocations"]
        wb = openpyxl.load_workbook(path, data_only=True)
        r = recognize_format(wb)
        got = extract_sheet2(wb[r.sheets["job"].sheet_name], r.sheets["job"])
        wb.close()
        assert len(got) == len(golden) == n
        assert got == golden
```

- [ ] **Step 2-4:** PASS (975 / 76 등가)
- [ ] **Step 5: Commit** — `feat(recipe): sheet2 추출 포팅 — Mm01+final_flag 조건부 게이트, 975/76 등가`

---

## Task 9: sheet3 추출 포팅 (equip_triple 경계)

**Files:** Modify `extract.py`; Test 추가.

`parser.py:512-582` 전사. 치환표 sheet2 와 동일 패턴 + 장비 컬럼: `ws.cell(r,4)=equip_big`→`cols["equip_big"]`, `5=equip_mid`→`cols["equip_mid"]`, `6=equip_spec`→`cols["equip_spec"]`. group 시작 = trade+bp+equip_big 동시 채워짐 + `"장비 투입" in trade 값` reprint skip 유지.

- [ ] **Step 1: Failing test** `extract_sheet3` 등가 (UNI=1111, BP=68)
- [ ] **Step 2-4:** PASS
- [ ] **Step 5: Commit** — `feat(recipe): sheet3 추출 포팅 — equip_triple 경계, 1111/68 등가`

---

## Task 10: extract_with_recipe + parse_with_recipe (공개 API) + company mismatch review

**Files:** Modify `extract.py`, `__init__.py`; Test 추가.

- `extract_with_recipe(wb, recipe) -> ParsedDailyReport`: 4 추출 함수 호출 + `_extract_meta`(import) 로 report_date/project + `worker_outputs=[]`, `report_meta=None`.
- `parse_with_recipe(xlsx_path) -> ParsedDailyReport`: `load_workbook(data_only=True)` → `recognize_format` → `extract_with_recipe`. **company mismatch 가드**: 셀 company set 의 각 정규화 회사명이 **파일명 토큰 어디에도 안 나타나면** 영향 activity 들 `requires_review=True` + stderr 경고(결정성 보존). 셀 SSOT 유지(파일명으로 company 덮어쓰기 X).
  - 구현: `tokens = {_norm_header(t) for t in Path(path).stem.split("_")}`; 셀 company `c` 에 대해 `_norm_header(c)` 가 어떤 토큰의 부분문자열도 아니면 mismatch. (주의: `parse_filename` 의 `bp_name` 에 의존하지 말 것 — 데모 파일명 `업체작업일보_M15X_PH3_남웅건설_단열공사_20250925` 은 토큰 수가 달라 `bp_name='PH3'`, `trade='남웅건설'` 로 분해된다. 회사명 토큰은 위치가 불안정하므로 전체 토큰 membership 으로 비교.)
- `__init__.py` 에서 `parse_with_recipe`, `recognize_format`, `FormatRecipe` export.

- [ ] **Step 1: Write the failing test** — 전체 등가 게이트:

```python
from pipeline.agents.recipe import parse_with_recipe

def test_full_report_equiv_both_formats():
    for path in (UNI, BP):
        golden = parse_daily_report(path)
        got = parse_with_recipe(path)
        for key in ("activities", "bp_summaries", "job_allocations",
                    "equipment_allocations", "report_date", "project",
                    "worker_outputs", "report_meta"):
            assert got[key] == golden[key], f"{path} {key} 불일치"

def test_company_mismatch_sets_review():
    # 데모 클론: 파일명 토큰엔 '남웅건설'·'M15X'·'PH3' 등만 있고 '중원엔지니어링' 없음 → mismatch
    demo = "data/demo_inputs/20250925/업체작업일보_M15X_PH3_남웅건설_단열공사_20250925.xlsm"
    got = parse_with_recipe(demo)
    assert {a["company"] for a in got["activities"]} == {"중원엔지니어링"}  # 셀 SSOT, 덮어쓰기 X
    assert all(a["requires_review"] for a in got["activities"])            # 셀 company 가 파일명에 없음 → 전부 review
```

- [ ] **Step 2-4:** 구현 → PASS. **이게 spec §5.1 baseline 등가 게이트** — 통과하면 prod 융합 안전.
- [ ] **Step 5: Commit** — `feat(recipe): parse_with_recipe 공개 API — 양식 2종 전체 등가 + company mismatch review`

---

## Task 11: recipe 캐시 I/O (fingerprint 키)

**Files:** Modify `recognize.py` (+ `cache` 헬퍼); Test 추가.

- `_recipe_cache_path(fp) -> Path` = `data/parser_recipes/<fp>.json`.
- `save_recipe(recipe)`, `load_cached_recipe(fp) -> FormatRecipe | None` (dataclass ↔ json; `SheetRecipe` 도 직렬화).
- `recognize_format(wb, use_cache=True)`: fingerprint 계산 → 캐시 hit 시 그대로 반환(재해석 skip), miss 시 Tier1 수행 후 (generated_by 가 llm/human 일 때만) 저장. 결정론 recipe 는 매번 동일하니 캐시 불필요하지만, LLM/human recipe 는 반드시 캐시.

- [ ] **Step 1: Failing test** — round-trip + hit:

```python
from pipeline.agents.recipe.recognize import save_recipe, load_cached_recipe, recognize_format
def test_recipe_cache_roundtrip(tmp_path, monkeypatch):
    wb = openpyxl.load_workbook(BP, data_only=True)
    r = recognize_format(wb); wb.close()
    save_recipe(r)
    loaded = load_cached_recipe(r.fingerprint)
    assert loaded is not None
    assert loaded.format_class == r.format_class
    assert loaded.sheets["activity"].columns == r.sheets["activity"].columns
```

- [ ] **Step 2-4:** PASS
- [ ] **Step 5: Commit** — `feat(recipe): recipe 캐시 I/O (data/parser_recipes/<fp>.json)`

---

## Task 12: Tier2 LLM fallback (주입 가능 client, mock 검증)

**Files:** Modify `recognize.py`; Test 추가.

- `recognize_format(wb, llm_client=None)`: Tier1 후 `missing`(필수필드 미매핑) 또는 role 미발견이 있으면, `llm_client` 가 주어졌을 때 `_llm_fill_recipe_gaps(wb, partial, gaps, llm_client)` 호출. **LLM 에 보내는 것은 시트명 + 헤더 row 텍스트뿐**(전체 셀 금지 — parser_llm.py 함정 회피). 반환 매핑을 recipe 에 병합, `generated_by="llm"`, confidence 가중, 캐시 저장.
- `llm_client` 인터페이스: `complete(prompt:str)->str`(JSON). 테스트는 mock 으로 결정성 확보(메모리 `feedback_dry_test`: LLM 우회 검증).

- [ ] **Step 1: Failing test** — 동의어 miss 를 mock LLM 이 채움:

```python
def test_tier2_llm_fills_gap_deterministic():
    # work_content 동의어를 일부러 모르는 헤더로 바꾼 미니 wb 생성(또는 synth V2 사용)
    # mock client: 항상 같은 매핑 반환
    class MockLLM:
        def __init__(self): self.calls = 0
        def complete(self, prompt):
            self.calls += 1
            return '{"activity": {"work_content": 7}}'
    wb = ...  # synth_formats V2(work_content 헤더 미상)로 생성한 업체 변이
    m1 = MockLLM(); r1 = recognize_format(wb, llm_client=m1)
    assert r1.generated_by == "llm"
    assert r1.sheets["activity"].columns["work_content"] == 7
    # 결정성: 같은 입력 2회 → 동일 recipe
    m2 = MockLLM(); r2 = recognize_format(wb, llm_client=m2)
    assert r1.sheets["activity"].columns == r2.sheets["activity"].columns
```

> 이 테스트는 Task 14 의 synth_formats 에 의존 → 본 Task 는 synth 후 작성하거나, 인라인으로 헤더 1칸을 바꾼 임시 wb 를 만들어 검증.

- [ ] **Step 2-4:** 구현 → PASS (mock 결정성)
- [ ] **Step 5: Commit** — `feat(recipe): Tier2 LLM fallback (헤더만, 주입 client, mock 결정성 검증)`

---

## Task 13: Tier3 안전망 (loud-fail + 부분 recipe 방출)

**Files:** Modify `recognize.py`; Test 추가.

- `recognize_format`: Tier1+Tier2 후에도 `confidence < θ`(θ=1.0 PoC) 또는 필수필드 미매핑 또는 `group_boundary=="unknown"` 이면 `ParseError`(어느 role 의 어느 필드/시트가 미해결인지 명시) + 부분 recipe 를 `data/parser_recipes/_review/<fp>.json` 로 방출. **조용한 오염 절대 금지**.

- [ ] **Step 1: Failing test** — 필수필드 미매핑 양식(LLM 없음) → ParseError:

```python
import pytest
from pipeline.agents.parser import ParseError
def test_tier3_loud_fail_on_unmappable_required():
    wb = ...  # work_content 헤더를 알 수 없는 값으로 바꾼 업체 변이 + llm_client=None
    with pytest.raises(ParseError) as e:
        recognize_format(wb, llm_client=None)
    assert "work_content" in str(e.value)
```

- [ ] **Step 2-4:** PASS
- [ ] **Step 5: Commit** — `feat(recipe): Tier3 안전망 — loud-fail + 부분 recipe 방출 (조용한 오염 0)`

---

## Task 14: 합성 adversarial corpus 생성기 (V1~V5)

**Files:** Create `scripts/synth_formats.py`; Test 추가.

업체 canonical 파일을 변이시켜 P1 양식 N종 생성(openpyxl 로 새 xlsx write). 각 변이는 **의미 등가**(라벨/위치만 변경, 값 동일):
- V1: 시트명 rename (`4.물량`→`물량집계`, `1.출력인원 현황`→`출력인원`)
- V2: 헤더 동의어 치환 (`금일실적`→`당일실적`, `대표물량_작업 내용`→`작업내용`)
- V3: sheet4 컬럼 순서 shuffle (헤더+데이터 동시 이동)
- V4: 업체파일에 `업체명` 컬럼 삽입(통합축) — company 를 별도 컬럼으로
- V5: 영문 헤더 치환 (`금일실적`→`Today Actual` 등; synonyms 에 영문 추가 필요)

`synth_formats.py` API: `make_variant(src_path, variant: str, out_path)`.

- [ ] **Step 1: Failing test** — 각 변이가 유효 xlsx 생성 + 로드 가능:

```python
from scripts.synth_formats import make_variant
def test_synth_variants_load(tmp_path):
    for v in ("V1", "V2", "V3", "V4", "V5"):
        out = tmp_path / f"{v}.xlsx"
        make_variant(BP, v, str(out))
        wb = openpyxl.load_workbook(out, data_only=True)
        assert len(wb.sheetnames) >= 4
        wb.close()
```

- [ ] **Step 2-4:** 구현 → PASS
- [ ] **Step 5: Commit** — `feat(recipe): 합성 변이 생성기 V1~V5 (시트명/동의어/shuffle/업체명/영문)`

---

## Task 15: 합성 등가 + 결정성 골든 (LLM 경로 포함)

**Files:** Test 추가 (`test_parser_recipe.py`).

각 합성 변이 → `parse_with_recipe(variant)` 가 canonical 업체 산출과 **의미 등가**(라벨만 다르므로 동일 `ParsedDailyReport`). 동의어 테이블이 못 잡는 변이(V5 영문 일부)는 mock LLM fallback 으로 채워 등가. 결정성: 2회 실행 동일 + 캐시 hit 경로 동일.

- [ ] **Step 1: Failing test**

```python
CANON_BP = None  # parse_with_recipe(BP) 한 번 계산해 비교 기준

def test_synth_equivalence_and_determinism(tmp_path):
    canon = parse_with_recipe(BP)
    for v in ("V1", "V2", "V3", "V4"):
        out = tmp_path / f"{v}.xlsx"
        make_variant(BP, v, str(out))
        got1 = parse_with_recipe(str(out))
        got2 = parse_with_recipe(str(out))
        # 핵심 4 entity 건수·필드 등가 (report_date/project 는 파일명 의존이라 제외)
        for key in ("activities", "bp_summaries", "job_allocations", "equipment_allocations"):
            assert got1[key] == canon[key], f"{v} {key} 등가 실패"
            assert got1[key] == got2[key], f"{v} {key} 결정성 실패"
```

> V4(업체명 컬럼 삽입)는 format_class 가 "통합"이 되어 company 출처가 company_col 로 바뀌지만 값은 동일해야 함 — 등가 확인.

- [ ] **Step 2-4:** 구현/조정 → PASS (필요 시 synonyms/resolver 보강, 단 baseline 회귀 재확인)
- [ ] **Step 5: Commit** — `test(recipe): 합성 V1~V4 의미 등가 + 결정성 골든`

---

## Task 16: invariant + CLI 진입점 + 최종 회귀 sweep

**Files:** Modify `extract.py`(invariant 헬퍼 옵션), `__init__.py`(CLI); Test 추가.

- **캡쳐 정확성 invariant(본 모듈 범위)**: recipe 경로가 골든의 인원/장비 수치를 손실 없이 캡쳐했는지 = `parse_with_recipe` 의 job/bp/eq 집계가 `parse_daily_report` 와 동일. (Tasks 6-9 가 dict 완전 등가로 이미 증명하지만, 집계 invariant 로 한 번 더 가드.)
- **cross-sheet invariant 는 mapper-scope (본 모듈 밖)**: spec §4.3 ⓐ `Σ job workers_today_incr.total == Σ bp today_incr_total` 은 실측상 **성립 안 함** — 업체파일에서 job측=191, bp측=212(차이 21 = `_is_admin_job` 로 job_allocations 에서 제외된 관리자). 이건 parser 결함이 아니라 두 시트의 집계 모집단 차이이며, 분배 일관성은 mapper `_prorate_mh` 영역. 본 모듈은 "골든과 동일 캡쳐"만 보장하고 cross-sheet 등식은 검증하지 않는다(주석 명시).
- CLI: `python -m pipeline.agents.recipe <xlsx>` → recognize + parse 요약 출력(format_class, confidence, 건수). graph 미연결(데모 후 융합).
- 최종 sweep: 전체 테스트 그린 확인.

- [ ] **Step 1: Failing test (캡쳐 정확성)**

```python
def test_capture_exactness_vs_golden():
    for path in (UNI, BP):
        rep = parse_with_recipe(path)
        gold = parse_daily_report(path)
        assert sum(j["workers_today_incr"]["total"] for j in rep["job_allocations"]) \
               == sum(j["workers_today_incr"]["total"] for j in gold["job_allocations"])
        assert sum(b["today_incr_total"] for b in rep["bp_summaries"]) \
               == sum(b["today_incr_total"] for b in gold["bp_summaries"])
        assert sum(e["count_today_cum"]["total"] for e in rep["equipment_allocations"]) \
               == sum(e["count_today_cum"]["total"] for e in gold["equipment_allocations"])
```

- [ ] **Step 2: 실측 메모(추측 금지)** — cross-sheet 등식(job 191 vs bp 212)이 왜 다른지는 `_is_admin_job` 제외분으로 설명됨. 이 등식을 assert 하지 말 것. 캡쳐 정확성(recipe==golden)만 assert.
- [ ] **Step 3: CLI 구현** (`pipeline/agents/recipe/__main__.py`)
- [ ] **Step 4: 최종 회귀 sweep**

Run: `cd /Users/kyungseoplee/cpia-parser-recipe-wt && pipeline/.venv/bin/python -m pytest pipeline/tests/test_parser_recipe.py -v`
Expected: 전체 PASS. 그리고 **기존 parser 회귀 미오염 확인**:
Run: `pipeline/.venv/bin/python -m pytest pipeline/tests/test_parser.py -v` (live parser 미수정이므로 그린이어야 함)

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/recipe/__main__.py pipeline/tests/test_parser_recipe.py
git commit -m "feat(recipe): invariant 검증 + CLI 진입점 + 최종 회귀 sweep 그린"
```

---

## 완료 정의 (Definition of Done)

1. `parse_with_recipe` 가 통합·업체 2종을 `parse_daily_report` 와 **전체 등가**(1193/99/975/1111, 33/76/68) — 같은 코드 경로.
2. 합성 V1~V4 의미 등가 + 결정성(2회 동일) 통과.
3. Tier2(mock)·Tier3(loud-fail)·캐시 round-trip 통과.
4. live `parser.py`/graph **미수정** (회귀 0, `test_parser.py` 그린).
5. 데모 후 융합: `parser_node` 에 `CPIA_PARSER=recipe` flag 추가는 **별도 작업**(본 플랜 밖, spec §6) — 이 플랜은 독립 모듈 완성까지.

## 비고 (실행 중 주의)

- 모든 컬럼 인덱스·offset(today_incr_total=+6, final_flag=25, timeshift 7/13/19/24/31 등)은 **canonical 실파일 실측으로 확정**하라. 테스트 기대값과 어긋나면 추측으로 맞추지 말고 실측에 맞게 resolver 를 조정.
- 포팅은 **전사(transcribe)**, 재작성 금지 — spec §3.4 의 hard lesson(재작성 시 통합 job 975→11836 폭증). 등가 테스트가 가드.
- `from __future__ import annotations` 모든 .py 첫 줄. dataclass 직렬화는 `dataclasses.asdict` + 수동 역직렬화(SheetRecipe tuple header_rows 주의).
