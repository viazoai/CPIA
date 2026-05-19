# CPIA reports gap + Parser LLM 강화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reports 페이지 § 01/§ 02/§ 03 빈 화면을 EVM 산식 + Optimizer view builder + FE thin SELECT 로 채움. 선행 의존성 (Parser 부실) 도 함께 해결.

**Architecture:** 2 Phase 한 PR. Phase A (Parser LLM 강화) — row 1:1 추출 + Python post-processing + chunk 안정화. Phase B (view builder + FE) — Mapper U1.A/U1.B 로 EVM input 채움, Optimizer 가 view builder 흡수 → daily_reports 8 jsonb UPSERT, FE 4 mock route thin SELECT.

**Tech Stack:** Python 3.9.6 + LangGraph + Azure OpenAI gpt-5.1 + asyncpg + PostgreSQL + Next.js 14 + TypeScript + Playwright.

**Spec:** `docs/superpowers/specs/2026-05-19-cpia-reports-gap-and-parser-design.md` (r2, commit 110dcfa).

**Phase 진입 기준:** Phase A 의 시트 1 + 시트 4 expected row count 통과 시 Phase B 진입 (§ 6.3 partial pass). 시트 2/3 fail 은 cycle B 의 § 01 일부 NULL 허용.

---

## Phase A — Parser LLM 강화

### Task A.0: pytest scaffolding + xlsx fixture

**Files:**
- Create: `pipeline/tests/test_parser_llm_e2e.py`

- [ ] **Step 1: Test 파일 신설**

```python
# pipeline/tests/test_parser_llm_e2e.py
"""Parser LLM e2e 검증 — Stage 1 + Stage 2 expected row count assertion."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

from pipeline.agents.parser_llm import ParserConfig, parse_daily_report_llm


SAMPLE_XLSX_STAGE1 = Path("docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx")

# Stage 2 xlsx: 다른 일자 — 사용자 confirm 후 path 지정. 없으면 skip.
SAMPLE_XLSX_STAGE2 = Path("docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250926.xlsx")


def _cfg():
    return ParserConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
    )


@pytest.mark.asyncio
@pytest.mark.skipif(not SAMPLE_XLSX_STAGE1.exists(), reason="Stage 1 xlsx 누락")
async def test_stage1_expected_row_count():
    """Stage 1 — sample xlsx 1 회 측정 후 expected range 산출 (initial ±20%)."""
    parsed = await parse_daily_report_llm(SAMPLE_XLSX_STAGE1, _cfg())
    # initial assertion (Task A.10 에서 실측 후 보정)
    assert len(parsed["bp_summaries"]) >= 280, f"bp_summaries={len(parsed['bp_summaries'])}"
    assert len(parsed["job_allocations"]) >= 1400, f"job_allocations={len(parsed['job_allocations'])}"
    assert len(parsed["equipment_allocations"]) >= 800, f"equipment={len(parsed['equipment_allocations'])}"
    assert len(parsed["activities"]) >= 1150, f"activities={len(parsed['activities'])}"


@pytest.mark.asyncio
@pytest.mark.skipif(not SAMPLE_XLSX_STAGE2.exists(), reason="Stage 2 xlsx 누락")
async def test_stage2_expected_row_count():
    """Stage 2 — 다른 일자 xlsx 양식 변동성 검증."""
    parsed = await parse_daily_report_llm(SAMPLE_XLSX_STAGE2, _cfg())
    assert len(parsed["activities"]) >= 1000  # 다른 일자라 약간 range 다를 수 있음
    assert len(parsed["bp_summaries"]) >= 250
```

- [ ] **Step 2: Test 실행 — Stage 1 fail 확인 (current Parser 결과 0/118/13/532)**

Run: `cd /Users/kyungseoplee/Project\ Agent/CPIA && pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_parser_llm_e2e.py::test_stage1_expected_row_count -v`

Expected: FAIL (bp_summaries=0 < 280)

- [ ] **Step 3: Commit**

```bash
git add pipeline/tests/test_parser_llm_e2e.py
git commit -m "test: parser_llm e2e stage 1+2 expected row count assertions"
```

---

### Task A.1: `_SYS_BP_SUMMARIES` row 1:1 prompt + BPSummaryRaw schema

**Files:**
- Modify: `pipeline/agents/parser_llm.py:160-198` (`_SYS_BP_SUMMARIES`)
- Modify: `pipeline/state.py` (`BPSummaryRaw` TypedDict 추가)

- [ ] **Step 1: BPSummaryRaw TypedDict 추가**

`pipeline/state.py` 끝에 추가:

```python
class BPSummaryRaw(TypedDict, total=False):
    """시트 1 의 row 단위 1:1 LLM 출력. parser_post.pair_bp_summaries 가 페어링."""
    row_idx: int
    col_4_value: str | None
    is_bp_code: bool
    is_korean_company: bool
    bp_code: str | None
    company: str | None
    disc_abbrev: str | None
    zone: str | None
    scope: str | None
    work_text_today: str | None
    workers_today_cum: dict | None
    today_cum_total: int | None
```

- [ ] **Step 2: `_SYS_BP_SUMMARIES` 재작성** (parser_llm.py L160-198)

```python
_SYS_BP_SUMMARIES = f"""당신은 건설 작업일보 시트1 (출력인원 현황) 파서. raw row JSON → BPSummaryRaw list (1 row = 1 출력).

# 입력
header_map = col_idx → 헤더 의미.
rows = list[dict[col_idx, value]] — 각 row 가 1 BP 단위 row.

# BPSummaryRaw 출력 schema (각 row 1개)
{{
  "row_idx": int,
  "col_4_value": str|null,
  "is_bp_code": bool,              // col 4 가 "PH_X-..." 패턴 인지
  "is_korean_company": bool,        // col 4 가 한글 회사명인지
  "bp_code": str|null,
  "company": str|null,
  "disc_abbrev": str|null,
  "zone": str|null,
  "scope": str|null,
  "work_text_today": str|null,
  "workers_today_cum": {_TIMESHIFT_SCHEMA}|null,
  "today_cum_total": int|null
}}

# 핵심 규칙
1. **각 input row = 1 BPSummaryRaw**. len(rows) == len(bp_summaries_raw). 페어링 X (post-processing 책임).
2. col 4 = "PH_X-..." 면 is_bp_code=true, bp_code=col4 값. 한글이면 is_korean_company=true, company=col4 값.
3. 시간대 6 필드 누락 시 각 0.
4. **추측 X** — header_map 명시된 col 값만. 모르면 null.

# 출력
{{ "bp_summaries_raw": [BPSummaryRaw, ...] }}
"""
```

- [ ] **Step 3: parse_daily_report_llm 의 response_key 변경**

Line 521-524 (parse_daily_report_llm 안):

```python
if "bp_summaries" in payloads:
    tasks["bp_summaries_raw"] = asyncio.create_task(
        _call_list(_SYS_BP_SUMMARIES, payloads["bp_summaries"], "bp_summaries_raw", chunk_size=15)
    )
```

(post-processing 은 Task A.6 에서 추가)

- [ ] **Step 4: Commit**

```bash
git add pipeline/agents/parser_llm.py pipeline/state.py
git commit -m "feat(parser): _SYS_BP_SUMMARIES row 1:1 prompt + BPSummaryRaw schema (B1)"
```

---

### Task A.2: `_SYS_JOB_ALLOCATIONS` row 1:1 + disc_code rename

**Files:**
- Modify: `pipeline/agents/parser_llm.py:200-224` (`_SYS_JOB_ALLOCATIONS`)
- Modify: `pipeline/state.py` (`JobAllocationRaw` TypedDict)

- [ ] **Step 1: JobAllocationRaw schema 추가**

```python
# pipeline/state.py
class JobAllocationRaw(TypedDict, total=False):
    row_idx: int
    company_or_bp: str | None
    disc_code: str | None        # Mm## 또는 Wk## (raw)
    worker_code: str | None      # sk##
    job_type: str | None
    disc_abbrev: str | None
    workers_today_cum: dict | None
    workers_cum_t: int | None
    final_flag: str | None
```

- [ ] **Step 2: `_SYS_JOB_ALLOCATIONS` 재작성**

```python
_SYS_JOB_ALLOCATIONS = f"""당신은 건설 작업일보 시트2 (직종별 인원현황) 파서. raw row JSON → JobAllocationRaw list (1 row = 1 출력).

# 입력 col 의미
- col 1 = 공종 (한글), col 2 = BP사 (BP 코드 또는 한글 회사명)
- col 3 = 직종 코드 (Mm##=관리자, Wk##=기능공 둘 다 가능)
- col 4 = 근로자 코드 (sk##)
- col 5 = 직종명 (한글)
- col 6~22 = 시간대별 인원 (header_map 명시된 col 의미만 사용)
- col 23 = 금일누계 Cum.T

# JobAllocationRaw 출력 schema (각 input row 1개)
{{
  "row_idx": int,
  "company_or_bp": str|null,   // col 2 raw
  "disc_code": str|null,        // col 3 = "Mm##" 또는 "Wk##"
  "worker_code": str|null,      // col 4 = "sk##"
  "job_type": str|null,         // col 5
  "disc_abbrev": str|null,      // col 1
  "workers_today_cum": {_TIMESHIFT_SCHEMA}|null,
  "workers_cum_t": int|null,    // col 23
  "final_flag": "O"|"X"|null
}}

# 핵심 규칙
1. **각 input row = 1 JobAllocationRaw**. len(rows) == len(items).
2. disc_code 는 raw 그대로 (Mm## 또는 Wk##). 의미 해석 X.
3. 모르는 필드 null. 시간대 6 필드 누락 시 각 0.

# 출력
{{ "job_allocations_raw": [JobAllocationRaw, ...] }}
"""
```

- [ ] **Step 3: tasks dispatch 정정**

```python
if "job_allocations" in payloads:
    tasks["job_allocations_raw"] = asyncio.create_task(
        _call_list(_SYS_JOB_ALLOCATIONS, payloads["job_allocations"], "job_allocations_raw", chunk_size=15)
    )
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/agents/parser_llm.py pipeline/state.py
git commit -m "feat(parser): _SYS_JOB_ALLOCATIONS row 1:1 + disc_code rename (B2)"
```

---

### Task A.3: `_SYS_EQUIPMENT_ALLOCATIONS` row 1:1 + marker filter 강화

**Files:**
- Modify: `pipeline/agents/parser_llm.py:135-149` (`_is_equipment_signal_row`)
- Modify: `pipeline/agents/parser_llm.py:226-249` (`_SYS_EQUIPMENT_ALLOCATIONS`)
- Modify: `pipeline/state.py` (`EquipmentAllocationRaw`)

- [ ] **Step 1: filter 강화 — BP 패턴 검증**

```python
# pipeline/agents/parser_llm.py
import re

_MARKER_PATTERNS = {"M15 PH-X", "FAB", "CUB", "M15X", "M15 X"}
_BP_CODE_RE = re.compile(r"^PH_X-\d+$")


def _is_real_bp(value: str | None) -> bool:
    """진짜 BP사 식별 — BP 코드 또는 한글 회사명."""
    if not value:
        return False
    s = str(value).strip()
    if s in _MARKER_PATTERNS:
        return False
    if _BP_CODE_RE.match(s):
        return True
    if any("가" <= c <= "힣" for c in s):  # 한글 검사
        return True
    return False


def _is_equipment_signal_row(d: dict[int, Any]) -> bool:
    """시트3 row 의미있는지 — 0 대수 / marker row / 합계 row skip."""
    for v in d.values():
        if isinstance(v, str) and "투입 Total" in v:
            return False
    cum_t = d.get(23)
    try:
        if cum_t is not None and float(cum_t) <= 0:
            return False
    except (TypeError, ValueError):
        pass
    big = str(d.get(3, "") or "").strip()
    mid = str(d.get(4, "") or "").strip()
    bp = d.get(2)  # col 2 = BP사
    # marker row drop
    return bool(big and mid and _is_real_bp(bp))
```

- [ ] **Step 2: EquipmentAllocationRaw schema + prompt 재작성**

```python
# pipeline/state.py
class EquipmentAllocationRaw(TypedDict, total=False):
    row_idx: int
    company_or_bp: str | None
    disc_abbrev: str | None
    equipment_big: str | None
    equipment_mid: str | None
    equipment_spec: str | None
    count_today_cum: dict | None
    count_cum_t: int | None
    final_flag: str | None
```

```python
# parser_llm.py
_SYS_EQUIPMENT_ALLOCATIONS = f"""당신은 건설 작업일보 시트3 (장비현황) 파서. raw row JSON → EquipmentAllocationRaw list (1 row = 1 출력).

# 입력 col 의미
- col 1 = 공종 한글
- col 2 = BP사 (BP 코드 "PH_X-..." 또는 한글 회사명)
- col 3 = 장비 대분류 (필수)
- col 4 = 장비 중분류 (필수)
- col 5 = 규격
- col 6~ 시간대별 (header_map 명시)
- col 23 = 금일투입누계 Total

# EquipmentAllocationRaw schema
{{
  "row_idx": int,
  "company_or_bp": str|null,
  "disc_abbrev": str|null,
  "equipment_big": str|null,
  "equipment_mid": str|null,
  "equipment_spec": str|null,
  "count_today_cum": {_TIMESHIFT_SCHEMA}|null,
  "count_cum_t": int|null,
  "final_flag": "O"|"X"|null
}}

# 핵심 규칙
1. 각 row = 1 EquipmentAllocationRaw.
2. **marker row 사전 filter 됨** — input rows 에 'M15 PH-X' / 'FAB' / 'CUB' 같은 marker 없음. 정상 BP사 row 만.
3. company_or_bp 는 col 2 raw 그대로.

# 출력
{{ "equipment_allocations_raw": [EquipmentAllocationRaw, ...] }}
"""
```

- [ ] **Step 3: tasks dispatch 정정**

```python
if "equipment_allocations" in payloads:
    tasks["equipment_allocations_raw"] = asyncio.create_task(
        _call_list(_SYS_EQUIPMENT_ALLOCATIONS, payloads["equipment_allocations"], "equipment_allocations_raw", chunk_size=15)
    )
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/agents/parser_llm.py pipeline/state.py
git commit -m "feat(parser): equipment marker filter + row 1:1 prompt (B3)"
```

---

### Task A.4: `_SYS_ACTIVITIES` jsonschema validate 강화

**Files:**
- Modify: `pipeline/agents/parser_llm.py:251-295` (`_SYS_ACTIVITIES`)

이미 row 1:1 — schema validate 만 강화.

- [ ] **Step 1: prompt 끝부분 `# 출력 검증` 섹션 추가**

```python
# _SYS_ACTIVITIES 끝에 추가:
# 핵심 규칙
1. 입력 rows 의 **모든 row 가 1 Activity** — len(rows) == len(activities).
2. **list 안에는 반드시 object (dict) 만**. 문자열 / 숫자 직접 배치 X.
3. company 는 한글 회사명 우선 (header "업체명" 또는 한글 row 값). 회사명 없으면 BP 코드 그대로.
4. trade / l5_disc 동일 값 (둘 다 한글 공종명).
5. 누락 필드는 null. 추측 X.
```

- [ ] **Step 2: chunk_size 30→15**

```python
if "activities" in payloads:
    tasks["activities"] = asyncio.create_task(
        _call_list(_SYS_ACTIVITIES, payloads["activities"], "activities", chunk_size=15)
    )
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/agents/parser_llm.py
git commit -m "feat(parser): activities schema validate + chunk_size 30→15 (B4/B5)"
```

---

### Task A.5: `_llm_extract_sync` retry 강화 + content_filter handling

**Files:**
- Modify: `pipeline/agents/parser_llm.py:344-396` (`_llm_extract_sync`)

- [ ] **Step 1: retry 로직 정정 — 빈 list / content_filter 둘 다 retry trigger**

```python
def _llm_extract_sync(
    client: AzureOpenAI,
    model: str,
    system_prompt: str,
    user_payload: dict,
    response_key: str,
    retries: int = 2,
    max_completion_tokens: int = 16000,
) -> Any:
    """LLM 1 호출 → JSON 파싱 → response_key 값 반환.

    Retry trigger:
      - JSON parse 실패
      - truncated (finish_reason='length')
      - content_filter (finish_reason='content_filter')
      - 빈 list 응답 (input rows > 0 인데 결과 [])
    """
    import sys as _sys

    input_rows_count = len(user_payload.get("rows", [])) if isinstance(user_payload, dict) else 0

    last_err: Exception | None = None
    last_result: Any = None
    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=max_completion_tokens,
            )
            choice = resp.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            raw = choice.message.content or "{}"
            usage = getattr(resp, "usage", None)
            comp_tokens = getattr(usage, "completion_tokens", None) if usage else None
            print(
                f"[parser_llm] key={response_key} attempt={attempt} finish={finish_reason} "
                f"raw_len={len(raw)} completion_tokens={comp_tokens} preview={raw[:200]!r}",
                file=_sys.stderr,
                flush=True,
            )
            # truncate retry
            if finish_reason == "length":
                last_err = RuntimeError(f"truncated (max_completion_tokens={max_completion_tokens})")
                continue
            # content_filter retry
            if finish_reason == "content_filter":
                last_err = RuntimeError("content_filter blocked")
                continue
            obj = json.loads(raw)
            result = obj.get(response_key)
            # 빈 list 응답 retry (input rows > 0 인데 결과 비어있음)
            if input_rows_count > 0 and isinstance(result, list) and len(result) == 0:
                last_err = RuntimeError(f"empty list returned (input rows={input_rows_count})")
                last_result = result
                continue
            return result
        except Exception as e:
            last_err = e
            print(
                f"[parser_llm] key={response_key} attempt={attempt} EXCEPTION {type(e).__name__}: {e}",
                file=_sys.stderr,
                flush=True,
            )
            continue
    # 모든 retry fail — 마지막 빈 list 결과라도 반환 (전체 실패 대신 partial)
    if last_result is not None:
        print(f"[parser_llm] key={response_key} all retries failed, returning last_result", file=_sys.stderr, flush=True)
        return last_result
    raise RuntimeError(f"LLM extract '{response_key}' 실패 {retries+1}회: {last_err}")
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/agents/parser_llm.py
git commit -m "feat(parser): retry 2회 + 빈 list/content_filter retry trigger (B4/B6)"
```

---

### Task A.6: `parser_post.py` 신설 — pair_bp_summaries

**Files:**
- Create: `pipeline/agents/parser_post.py`

- [ ] **Step 1: parser_post.py 신설**

```python
# pipeline/agents/parser_post.py
"""Parser LLM 출력 → 정제된 entity list.

LLM 은 raw row 단위 1:1 추출만. 본 모듈이:
  - 페어링 (BP 코드 row + 회사명 row → 1 BPSummary)
  - marker row filter (sub-section 시작 marker drop)
  - company normalize (㈜prefix / FAB·CUB suffix split)
  - jsonschema validate
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_MARKER_SET = {"M15 PH-X", "FAB", "CUB", "M15X", "M15 X", "공통", "소계", "합계", "총계", "TOTAL"}
_BP_RE = re.compile(r"^PH_X-\d+$")


def _is_real_bp(value: str | None) -> bool:
    if not value:
        return False
    s = str(value).strip()
    if s in _MARKER_SET:
        return False
    if _BP_RE.match(s):
        return True
    return any("가" <= c <= "힣" for c in s)


def filter_marker_rows(raw_rows: list[dict], target_key: str = "company_or_bp") -> list[dict]:
    """marker row drop (sub-section 시작 marker)."""
    out = []
    for r in raw_rows:
        v = r.get(target_key)
        if _is_real_bp(v):
            out.append(r)
        else:
            logger.debug(f"filter_marker drop: {v!r}")
    return out


def pair_bp_summaries(raw_rows: list[dict]) -> list[dict]:
    """시트 1 의 2-row pairing.
    
    BP 코드 row (is_bp_code=true) + 다음 회사명 row (is_korean_company=true)
    + 같은 zone/disc_abbrev → 1 BPSummary 머지.
    그 외: each row = 1 BPSummary.
    """
    paired: list[dict] = []
    i = 0
    while i < len(raw_rows):
        r = raw_rows[i]
        next_r = raw_rows[i + 1] if i + 1 < len(raw_rows) else None
        is_pair = (
            r.get("is_bp_code")
            and next_r is not None
            and next_r.get("is_korean_company")
            and r.get("zone") == next_r.get("zone")
            and r.get("disc_abbrev") == next_r.get("disc_abbrev")
        )
        if is_pair:
            # merge — bp_code 는 r, company 는 next_r, 나머지 not-null 우선
            merged = {
                "bp_code": r.get("bp_code"),
                "company": next_r.get("company") or r.get("col_4_value"),
                "disc_abbrev": r.get("disc_abbrev") or next_r.get("disc_abbrev"),
                "zone": r.get("zone") or next_r.get("zone"),
                "scope": r.get("scope") or next_r.get("scope"),
                "work_text_today": next_r.get("work_text_today") or r.get("work_text_today"),
                "workers_today_cum": next_r.get("workers_today_cum") or r.get("workers_today_cum"),
                "today_cum_total": next_r.get("today_cum_total") or r.get("today_cum_total") or 0,
            }
            paired.append(merged)
            i += 2
        else:
            # single — bp_code 만 있는 row 또는 회사명만 있는 row
            single = {
                "bp_code": r.get("bp_code"),
                "company": r.get("company") or r.get("bp_code") or r.get("col_4_value"),
                "disc_abbrev": r.get("disc_abbrev"),
                "zone": r.get("zone"),
                "scope": r.get("scope"),
                "work_text_today": r.get("work_text_today"),
                "workers_today_cum": r.get("workers_today_cum"),
                "today_cum_total": r.get("today_cum_total") or 0,
            }
            paired.append(single)
            i += 1
    return paired


def normalize_company(raw: str | None) -> str | None:
    """㈜prefix 제거 / FAB·CUB suffix 분리 / sub-context split."""
    if not raw:
        return None
    s = str(raw).strip()
    # ㈜ prefix 제거
    s = s.lstrip("㈜").strip()
    # 괄호 안 sub-context 제거 — "세아그린텍(Scrubber)" → "세아그린텍"
    s = re.sub(r"\([^)]*\)", "", s).strip()
    # FAB / CUB suffix 분리 — "창원기전FAB" 는 보존 (구분 의미). suffix 분리 안 함.
    return s or None


def transform_job_allocations(raw_rows: list[dict]) -> list[dict]:
    """JobAllocationRaw list → JobAllocation list. company normalize + marker filter."""
    rows = filter_marker_rows(raw_rows, target_key="company_or_bp")
    return [
        {
            "company": normalize_company(r.get("company_or_bp")),
            "bp_code": r["company_or_bp"] if _BP_RE.match(str(r.get("company_or_bp") or "")) else None,
            "disc_abbrev": r.get("disc_abbrev"),
            "disc_code": r.get("disc_code"),
            "worker_code": r.get("worker_code"),
            "job_type": r.get("job_type"),
            "workers_today_cum": r.get("workers_today_cum"),
            "workers_cum_t": r.get("workers_cum_t") or 0,
            "final_flag": r.get("final_flag"),
        }
        for r in rows
        if r.get("job_type")  # job_type 없는 row drop
    ]


def transform_equipment_allocations(raw_rows: list[dict]) -> list[dict]:
    """EquipmentAllocationRaw → EquipmentAllocation."""
    rows = filter_marker_rows(raw_rows, target_key="company_or_bp")
    return [
        {
            "company": normalize_company(r.get("company_or_bp")),
            "bp_code": r["company_or_bp"] if _BP_RE.match(str(r.get("company_or_bp") or "")) else None,
            "disc_abbrev": r.get("disc_abbrev"),
            "equipment_big": r.get("equipment_big"),
            "equipment_mid": r.get("equipment_mid"),
            "equipment_spec": r.get("equipment_spec"),
            "count_today_cum": r.get("count_today_cum"),
            "count_cum_t": r.get("count_cum_t") or 0,
            "final_flag": r.get("final_flag"),
        }
        for r in rows
        if r.get("equipment_big") and r.get("equipment_mid")
    ]


def transform_bp_summaries(raw_rows: list[dict]) -> list[dict]:
    """BPSummaryRaw → BPSummary (페어링 + company normalize + marker filter)."""
    rows = filter_marker_rows(raw_rows, target_key="col_4_value")
    paired = pair_bp_summaries(rows)
    return [
        {
            "bp_code": r.get("bp_code"),
            "company": normalize_company(r.get("company")) or r.get("bp_code") or "",
            "disc_abbrev": r.get("disc_abbrev"),
            "zone": r.get("zone"),
            "scope": r.get("scope"),
            "work_text_today": r.get("work_text_today"),
            "workers_today_cum": r.get("workers_today_cum"),
            "today_cum_total": r.get("today_cum_total") or 0,
        }
        for r in paired
        if r.get("company") or r.get("bp_code")
    ]
```

- [ ] **Step 2: 단위 테스트 추가**

```python
# pipeline/tests/test_parser_post.py
from pipeline.agents.parser_post import (
    filter_marker_rows, pair_bp_summaries, normalize_company,
    transform_job_allocations, transform_bp_summaries,
)


def test_filter_marker_rows_drops_markers():
    rows = [
        {"company_or_bp": "M15 PH-X"},
        {"company_or_bp": "FAB"},
        {"company_or_bp": "PH_X-002"},
        {"company_or_bp": "세보엠이씨"},
    ]
    out = filter_marker_rows(rows)
    assert len(out) == 2
    assert {r["company_or_bp"] for r in out} == {"PH_X-002", "세보엠이씨"}


def test_pair_bp_summaries_merges_adjacent():
    rows = [
        {"is_bp_code": True, "bp_code": "PH_X-002", "disc_abbrev": "공통가설", "zone": "FAB/CUB"},
        {"is_korean_company": True, "company": "㈜에스티엠", "disc_abbrev": "공통가설", "zone": "FAB/CUB", "today_cum_total": 162},
    ]
    paired = pair_bp_summaries(rows)
    assert len(paired) == 1
    assert paired[0]["bp_code"] == "PH_X-002"
    assert paired[0]["company"] == "㈜에스티엠"
    assert paired[0]["today_cum_total"] == 162


def test_normalize_company_strips_juju_and_paren():
    assert normalize_company("㈜세보엠이씨") == "세보엠이씨"
    assert normalize_company("세아그린텍(Scrubber)") == "세아그린텍"
    assert normalize_company("창원기전FAB") == "창원기전FAB"  # suffix 보존
```

- [ ] **Step 3: pytest 실행 (asyncio mark 없는 sync 테스트)**

Run: `cd /Users/kyungseoplee/Project\ Agent/CPIA && pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_parser_post.py -v`

Expected: PASS 3 tests

- [ ] **Step 4: Commit**

```bash
git add pipeline/agents/parser_post.py pipeline/tests/test_parser_post.py
git commit -m "feat(parser): parser_post.py — pair/filter/normalize + unit tests"
```

---

### Task A.7: `parse_daily_report_llm` 가 parser_post 통합

**Files:**
- Modify: `pipeline/agents/parser_llm.py:546-564` (parse_daily_report_llm 끝부분)

- [ ] **Step 1: parser_post import 추가**

```python
# pipeline/agents/parser_llm.py 상단
from pipeline.agents import parser_post
```

- [ ] **Step 2: parse_daily_report_llm 의 results 합성 부분 정정**

```python
# Line 546-564 정정
results: dict[str, Any] = {}
for k, t in tasks.items():
    results[k] = await t

# post-processing
bp_summaries = parser_post.transform_bp_summaries(results.get("bp_summaries_raw") or [])
job_allocations = parser_post.transform_job_allocations(results.get("job_allocations_raw") or [])
equipment_allocations = parser_post.transform_equipment_allocations(results.get("equipment_allocations_raw") or [])
activities = results.get("activities") or []   # 이미 final shape

rm = results.get("report_meta") or {}
project = (rm.get("project_name") if isinstance(rm, dict) else None) or xlsx_path.stem

parsed: ParsedDailyReport = {
    "report_date": report_date or (rm.get("report_date") if isinstance(rm, dict) else "") or "",
    "project": project,
    "bp_summaries": bp_summaries,
    "job_allocations": job_allocations,
    "equipment_allocations": equipment_allocations,
    "activities": activities,
    "worker_outputs": results.get("worker_outputs") or [],
    "report_meta": rm if isinstance(rm, dict) and rm else None,
}
return parsed
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/agents/parser_llm.py
git commit -m "feat(parser): parse_daily_report_llm calls parser_post for pair/filter/normalize"
```

---

### Task A.8: Mapper company normalize 적용

**Files:**
- Modify: `pipeline/agents/mapper.py` (insert_mapper_activities_batch 직전)

- [ ] **Step 1: Mapper 의 mapped 빌드 시점 normalize 호출**

```python
# pipeline/agents/mapper.py 끝부분 (insert_mapper_activities_batch 호출 직전)
from pipeline.agents.parser_post import normalize_company

# mapped row 의 company 정규화
for a in mapped:
    a["company"] = normalize_company(a.get("company"))
```

- [ ] **Step 2: 단위 테스트** (회귀 방지)

`pipeline/tests/test_mapper_company_normalize.py`:

```python
import pytest
from pipeline.agents.parser_post import normalize_company

def test_mapper_normalizes_juju_prefix():
    assert normalize_company("㈜세보엠이씨") == "세보엠이씨"

def test_mapper_normalizes_paren_split():
    assert normalize_company("세아그린텍(Scrubber)") == "세아그린텍"
```

Run: `pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_mapper_company_normalize.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add pipeline/agents/mapper.py pipeline/tests/test_mapper_company_normalize.py
git commit -m "feat(mapper): normalize company (㈜ prefix / paren split)"
```

---

### Task A.9: pytest Stage 1 측정 + expected range 보정

**Files:**
- Modify: `pipeline/tests/test_parser_llm_e2e.py`

- [ ] **Step 1: Stage 1 실행 — 실측 row count 확보**

Run:
```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  PYTHONPATH=. pipeline/.venv/bin/python3 tmp/run_parser_capture.py
```

Expected: Phase A fix 후 결과:
- bp_summaries ≈ 250~330
- job_allocations ≈ 1,200~1,500
- equipment_allocations ≈ 700~900
- activities ≈ 1,100~1,250

- [ ] **Step 2: 실측 결과로 test_stage1 의 assertion range 보정**

```python
# 실측값 (예: bp=300) 기준 ±20%
assert 240 <= len(parsed["bp_summaries"]) <= 360, ...
assert 1000 <= len(parsed["job_allocations"]) <= 1750, ...
assert 600 <= len(parsed["equipment_allocations"]) <= 1050, ...
assert 950 <= len(parsed["activities"]) <= 1400, ...
```

- [ ] **Step 3: pytest 실행**

Run: `pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_parser_llm_e2e.py::test_stage1_expected_row_count -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pipeline/tests/test_parser_llm_e2e.py
git commit -m "test(parser): Stage 1 expected range 보정 (실측 기반)"
```

---

### Task A.10: pytest Stage 2 — 다른 일자 xlsx 측정

**Files:**
- Modify: `pipeline/tests/test_parser_llm_e2e.py`

**Prerequisite:** 다른 일자 xlsx 확보. 사용자에게 path 확인:
- (a) `docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250926.xlsx` 또는 비슷한 다른 일자 있음?
- (b) 없으면 Task A.10 skip 가능 — `@pytest.mark.skipif(not SAMPLE_XLSX_STAGE2.exists())`

- [ ] **Step 1: Stage 2 xlsx 확인**

Run: `ls docs/sample/통합작업일보*.xlsx`

- [ ] **Step 2: Stage 2 실행 (있는 경우)**

```bash
POSTGRES_URL=... PYTHONPATH=. pipeline/.venv/bin/python3 -c "
import asyncio
from pipeline.agents.parser_llm import ParserConfig, parse_daily_report_llm
import os
async def main():
    cfg = ParserConfig(...)
    parsed = await parse_daily_report_llm('docs/sample/<Stage2 xlsx>', cfg)
    print(f'bp={len(parsed[\"bp_summaries\"])}, job={len(parsed[\"job_allocations\"])}, eq={len(parsed[\"equipment_allocations\"])}, act={len(parsed[\"activities\"])}')
asyncio.run(main())
"
```

- [ ] **Step 3: Stage 1 + 2 range overlap 검증 + final range 산출 (Stage 1 ± Stage 2 의 ±10%)**

- [ ] **Step 4: Commit**

```bash
git add pipeline/tests/test_parser_llm_e2e.py
git commit -m "test(parser): Stage 2 expected range overlap 검증"
```

---

### **Phase A 검증 Gate** (Phase B 진입 전)

다음 통과 후 Phase B 진입:

- [ ] `test_stage1_expected_row_count` PASS
- [ ] `test_stage2_expected_row_count` PASS (또는 skipif)
- [ ] 시트 1 (bp_summaries) + 시트 4 (activities) expected range 통과 → **partial pass OK**
- [ ] 누적 비용 ≤ $10 (B7)

---

## Phase B — view builder + EVM + FE thin

### Task B.0: PG migration — daily_reports + mapper_activities 컬럼 추가

**Files:**
- Create: `infra/postgres/migrations/2026-05-19_daily_reports_views.sql`

- [ ] **Step 1: migration SQL 신설**

```sql
-- infra/postgres/migrations/2026-05-19_daily_reports_views.sql
-- Phase B: daily_reports 에 view jsonb 8개 + mapper_activities 에 cum_workers 2 컬럼

ALTER TABLE daily_reports
  ADD COLUMN IF NOT EXISTS kpi_jsonb              JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS contractor_bars_jsonb  JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS trade_bars_jsonb       JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS quadrant_jsonb         JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS wp_summary_jsonb       JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS s_curve_jsonb          JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS optimizer_view_jsonb   JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS productivity_jsonb     JSONB DEFAULT '{}'::jsonb;

-- daily_reports 가 (run_id, report_date, site_id) 단위 UPSERT 가능하도록
-- site_id 컬럼 보강 + unique index
ALTER TABLE daily_reports
  ADD COLUMN IF NOT EXISTS site_id text;

CREATE UNIQUE INDEX IF NOT EXISTS daily_reports_run_site_date_uq
  ON daily_reports (run_id, site_id, report_date)
  WHERE site_id IS NOT NULL;

-- mapper_activities EVM input source
ALTER TABLE mapper_activities
  ADD COLUMN IF NOT EXISTS cum_workers_today      DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS cum_actual_mh_today    DOUBLE PRECISION;
```

- [ ] **Step 2: migration 실행 (cloudflared 5532)**

Run:
```bash
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg, os
async def main():
    con = await asyncpg.connect(os.environ['POSTGRES_URL'])
    with open('infra/postgres/migrations/2026-05-19_daily_reports_views.sql') as f:
        await con.execute(f.read())
    print('migration applied')
asyncio.run(main())
"
```

Expected: `migration applied`

- [ ] **Step 3: 컬럼 추가 확인**

```bash
POSTGRES_URL=... pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg, os
async def main():
    con = await asyncpg.connect(os.environ['POSTGRES_URL'])
    rows = await con.fetch(\"SELECT column_name FROM information_schema.columns WHERE table_name='daily_reports' AND column_name LIKE '%_jsonb'\")
    print([r['column_name'] for r in rows])
asyncio.run(main())
"
```

Expected: 8 컬럼 모두 출현

- [ ] **Step 4: Commit**

```bash
git add infra/postgres/migrations/2026-05-19_daily_reports_views.sql
git commit -m "migration: daily_reports +8 view jsonb + mapper_activities +2 cum columns"
```

---

### Task B.1: Mapper U1.A — plan_mh propagate

**Files:**
- Modify: `pipeline/agents/mapper.py` (`l6_mh` map 재활용 부분 다음)
- Modify: `pipeline/db.py:621-731` (`insert_mapper_activities_batch` — 이미 plan_mh 컬럼 INSERT 함, 확인만)

- [ ] **Step 1: mapper.py U1.A 코드 추가**

```python
# pipeline/agents/mapper.py
# assigned_workers 산정 후 (이미 fetch 된 l6_mh map 재활용)
out: list[Activity] = []
for a in mapped:
    if a["l6_main"] is not None:
        key = (a["company"], a["l6_main"])
        # U1.A: plan_mh propagate
        l6_mh_map = l6_mh_by_company.get(a["company"], {})  # 이미 fetch 됨
        a = {
            **a,
            "assigned_workers": workers_lookup.get(key, 0.0),
            "worker_source": "mh_prorated",
            "plan_mh": l6_mh_map.get(a["l6_main"], 0),  # ★ U1.A
        }
    out.append(a)
return out
```

- [ ] **Step 2: 단위 테스트 추가**

```python
# pipeline/tests/test_mapper_u1a.py
def test_plan_mh_propagated():
    # mock l6_mh map + mapped → out 에 plan_mh 박힘 확인
    ...
```

- [ ] **Step 3: pytest 실행**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_mapper_u1a.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pipeline/agents/mapper.py pipeline/tests/test_mapper_u1a.py
git commit -m "feat(mapper): U1.A plan_mh propagate from l6_mh map"
```

---

### Task B.2: Mapper U1.B — cum_workers prorate + fallback

**Files:**
- Modify: `pipeline/agents/mapper.py` (U1.A 코드 옆)
- Modify: `pipeline/db.py` (insert_mapper_activities_batch — cum_workers 컬럼 추가)

- [ ] **Step 1: mapper.py U1.B 코드 추가**

```python
# pipeline/agents/mapper.py — U1.B
# parser_job_allocations 의 company 단위 cum_workers SUM
job_alloc_company_sum: dict[str, int] = {}
for ja in parsed.get("job_allocations", []):
    if ja.get("final_flag") != "O": continue
    c = ja.get("company")
    if c:
        job_alloc_company_sum[c] = job_alloc_company_sum.get(c, 0) + (ja.get("workers_cum_t") or 0)

# company 전체 plan_mh sum (prorate 분모)
company_total_plan_mh: dict[str, float] = {}
for a in out:
    c = a.get("company")
    if c and a.get("plan_mh"):
        company_total_plan_mh[c] = company_total_plan_mh.get(c, 0) + a["plan_mh"]

# active_l6 (균등 분배 fallback 용)
import collections
active_l6_for_company = collections.defaultdict(set)
for a in out:
    if a.get("company") and a.get("l6_main"):
        active_l6_for_company[a["company"]].add(a["l6_main"])

# U1.B: cum_workers + fallback
for a in out:
    if a.get("l6_main"):
        c = a["company"]
        workers_c = job_alloc_company_sum.get(c, 0)
        company_mh = company_total_plan_mh.get(c, 0)
        plan_mh = a.get("plan_mh", 0)
        n_l6 = len(active_l6_for_company[c]) if c else 0
        if company_mh > 0 and plan_mh > 0:
            a["cum_workers_today"] = workers_c * (plan_mh / company_mh)
            a["prorate_method"] = "plan_mh"
        elif n_l6 > 0:
            a["cum_workers_today"] = workers_c / n_l6
            a["prorate_method"] = "uniform_fallback"
            logger.warning(f"prorate fallback {c}/{a['l6_main']} — plan_mh=0")
        else:
            a["cum_workers_today"] = 0
            a["prorate_method"] = "zero"
        a["cum_actual_mh_today"] = a["cum_workers_today"] * 8.0
```

- [ ] **Step 2: db.py 의 `insert_mapper_activities_batch` 에 cum_workers 컬럼 추가**

`pipeline/db.py:621-731` — INSERT 컬럼 list 와 VALUES 에 `cum_workers_today`, `cum_actual_mh_today` 추가 (마찬가지로 `EXCLUDED.cum_workers_today` UPSERT clause).

- [ ] **Step 3: 단위 테스트 추가**

```python
# pipeline/tests/test_mapper_u1b.py
def test_prorate_plan_mh():
    # company total mh 1000, l6 mh 200 → weight 0.2 → cum_workers_today = 1000 × 0.2 = 200
    ...

def test_prorate_uniform_fallback_when_no_plan_mh():
    # plan_mh=0, n_l6=2 → workers / 2
    ...
```

- [ ] **Step 4: pytest 실행**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_mapper_u1b.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/mapper.py pipeline/db.py pipeline/tests/test_mapper_u1b.py
git commit -m "feat(mapper): U1.B cum_workers prorate (plan_mh 비율) + uniform fallback"
```

---

### Task B.3: `pipeline/optimizer/view_builder.py` 신설 — _build_productivity_views (EVM)

**Files:**
- Create: `pipeline/optimizer/view_builder.py`

- [ ] **Step 1: view_builder.py 신설 — _build_productivity_views**

```python
# pipeline/optimizer/view_builder.py
"""Optimizer 노드의 view builder — daily_reports.jsonb 컬럼 8개 산출."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from pipeline.db import PGClient

logger = logging.getLogger(__name__)


async def _build_productivity_views(
    pg: PGClient, run_id, site_id: str, today: date, forecast: list, mapped: list
) -> dict:
    """§ 01 EVM 산출 — today + by_contractor + by_l6 + by_wp snapshot.
    
    산식:
      cum_plan_qty/mh = Σ activity_master(g) 균등분배 누계
      cum_actual_qty  = parser_activities.today_cum_qty (g 매칭 SUM, mapper_activities 통해)
      cum_actual_mh   = mapper_activities.cum_actual_mh_today (g 매칭 SUM)
      EV = (cum_actual_qty / Σ plan_qty_full) × Σ plan_mh_full
      SPI = EV / PV, CPI = EV / AC
    """
    # group 단위 별 산출
    site_evm = await _evm_for_group(pg, site_id, today, group_key="site")
    by_contractor = await _evm_by_group(pg, site_id, today, group_key="company")
    by_l6 = await _evm_by_group(pg, site_id, today, group_key="l6_main")
    by_wp = await _evm_by_group(pg, site_id, today, group_key="wa_l6_company")

    return {
        "today": site_evm,
        "by_contractor": by_contractor,
        "by_l6": by_l6,
        "by_wp": by_wp,
    }


async def _evm_for_group(pg: PGClient, site_id: str, today: date, group_key: str) -> dict:
    """site 전체 EVM 산출 — group_key='site'."""
    async with pg._pool.acquire() as con:
        # cum_plan
        plan_row = await con.fetchrow("""
            SELECT
              SUM(plan_total_qty * LEAST(1.0, GREATEST(0.0,
                  ($2::date - plan_start + 1)::float / NULLIF((plan_finish - plan_start + 1)::float, 0)
              )))::float AS cum_plan_qty,
              SUM(plan_mh_rev2 * LEAST(1.0, GREATEST(0.0,
                  ($2::date - plan_start + 1)::float / NULLIF((plan_finish - plan_start + 1)::float, 0)
              )))::float AS cum_plan_mh,
              SUM(plan_total_qty)::float AS plan_qty_full,
              SUM(plan_mh_rev2)::float AS plan_mh_full
            FROM activity_master
            WHERE site_id = $1
        """, site_id, today)

        # cum_actual
        actual_row = await con.fetchrow("""
            SELECT
              COALESCE(SUM(ma.today_cum_qty), 0)::float AS cum_actual_qty,
              COALESCE(SUM(ma.cum_actual_mh_today), 0)::float AS cum_actual_mh
            FROM mapper_activities ma
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pr.report_date = $2
        """, site_id, today)

    return _compose_evm(plan_row, actual_row)


def _compose_evm(plan_row, actual_row) -> dict:
    """EV/PV/AC/SPI/CPI 산출."""
    if plan_row is None or plan_row["plan_qty_full"] in (None, 0):
        return {"spi": None, "cpi": None, "ev": 0, "pv": 0, "ac": 0}
    plan_qty_full = plan_row["plan_qty_full"] or 0
    plan_mh_full = plan_row["plan_mh_full"] or 0
    cum_plan_mh = plan_row["cum_plan_mh"] or 0
    cum_actual_qty = actual_row["cum_actual_qty"] or 0
    cum_actual_mh = actual_row["cum_actual_mh"] or 0

    progress = cum_actual_qty / plan_qty_full if plan_qty_full else 0
    EV = progress * plan_mh_full
    PV = cum_plan_mh
    AC = cum_actual_mh
    SPI = (EV / PV * 100) if PV > 0 else None
    CPI = (EV / AC * 100) if AC > 0 else None

    return {"spi": SPI, "cpi": CPI, "ev": EV, "pv": PV, "ac": AC,
            "cum_actual_qty": cum_actual_qty, "plan_qty_full": plan_qty_full}


async def _evm_by_group(pg: PGClient, site_id: str, today: date, group_key: str) -> dict[str, dict]:
    """group_key (company / l6_main / wa_l6_company) 별 EVM dict."""
    # 구현: group_key 별로 SQL GROUP BY + _compose_evm 호출. 상세는 spec § 5.1 의 산식 적용.
    # TODO: implement (각 group 별 plan + actual fetch + _compose_evm)
    return {}  # placeholder
```

- [ ] **Step 2: 단위 테스트 (compose_evm)**

```python
# pipeline/tests/test_view_builder_evm.py
from pipeline.optimizer.view_builder import _compose_evm

def test_compose_evm_세보엠이씨_기계소화():
    plan_row = {
        "cum_plan_qty": 77774, "cum_plan_mh": 744043,
        "plan_qty_full": 77774, "plan_mh_full": 744043,
    }
    actual_row = {"cum_actual_qty": 25252, "cum_actual_mh": 470692}
    r = _compose_evm(plan_row, actual_row)
    assert abs(r["spi"] - 32.47) < 0.1
    assert abs(r["cpi"] - 51.32) < 0.1
```

Run: `pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_view_builder_evm.py -v`
Expected: PASS (세보엠이씨 케이스 검증)

- [ ] **Step 3: Commit**

```bash
git add pipeline/optimizer/view_builder.py pipeline/tests/test_view_builder_evm.py
git commit -m "feat(view_builder): _build_productivity_views + _compose_evm (EVM)"
```

---

### Task B.4: view_builder _build_kpi + _build_contractor_bars + _build_trade_bars

**Files:**
- Modify: `pipeline/optimizer/view_builder.py`

- [ ] **Step 1: _build_kpi**

```python
async def _build_kpi(pg: PGClient, site_id: str, today: date, productivity: dict) -> dict:
    """§ 01 헤더 KPI — productivity_today, target, delay_days, expected_completion."""
    site_evm = productivity.get("today", {})
    cpi = site_evm.get("cpi")
    spi = site_evm.get("spi")
    
    async with pg._pool.acquire() as con:
        d_row = await con.fetchrow("""
            SELECT AVG(delay_days)::float AS delay,
                   MAX(expected_completion) AS expected_completion
            FROM forecasts f JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pr.report_date = $2
        """, site_id, today)
    return {
        "productivity_today": round(cpi or 0, 2),
        "spi": round(spi or 0, 2),
        "cpi": round(cpi or 0, 2),
        "target_productivity": 100,  # CPI 100 = 계획대로
        "delay_days": round(d_row["delay"] or 0),
        "expected_completion": d_row["expected_completion"].isoformat() if d_row["expected_completion"] else None,
    }
```

- [ ] **Step 2: _build_contractor_bars + _build_trade_bars**

```python
async def _build_contractor_bars(productivity: dict) -> list[dict]:
    """by_contractor dict → BarItem[] sorted by CPI desc."""
    by_c = productivity.get("by_contractor", {})
    return sorted(
        [{"label": c, "value": round(d.get("cpi") or 0, 1),
          "status": "normal" if (d.get("cpi") or 0) >= 90 else "caution" if (d.get("cpi") or 0) >= 80 else "risk"}
         for c, d in by_c.items()],
        key=lambda x: -x["value"],
    )


async def _build_trade_bars(productivity: dict) -> list[dict]:
    """by_l6 dict → BarItem[]."""
    by_l = productivity.get("by_l6", {})
    return sorted(
        [{"label": l, "value": round(d.get("cpi") or 0, 1),
          "status": "normal" if (d.get("cpi") or 0) >= 90 else "caution" if (d.get("cpi") or 0) >= 80 else "risk"}
         for l, d in by_l.items()],
        key=lambda x: -x["value"],
    )
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/optimizer/view_builder.py
git commit -m "feat(view_builder): _build_kpi + _build_contractor_bars + _build_trade_bars"
```

---

### Task B.5: view_builder _build_quadrant + _build_wp_summary + Impact P90

**Files:**
- Modify: `pipeline/optimizer/view_builder.py`

- [ ] **Step 1: _build_quadrant + impact P90 normalize**

```python
import statistics

def _normalize_impact(raw_values: list[float], p90: float) -> dict[str, float]:
    """raw qty×mh → 0~100 (P90 기준)."""
    return {k: min(100, (v / p90 * 100)) if p90 > 0 else 0 for k, v in raw_values}


async def _build_quadrant(pg: PGClient, site_id: str, today: date, productivity: dict) -> list[dict]:
    """4분면 산점도 점 — (wa, l6, company) per WP."""
    by_wp = productivity.get("by_wp", {})
    # impact = plan_total_qty × plan_mh_rev2 → P90 정규화
    async with pg._pool.acquire() as con:
        impact_rows = await con.fetch("""
            SELECT ma.wa, ma.l6_main, ma.company,
                   (SUM(ma.plan_total_qty) * AVG(ma.plan_mh))::float AS raw_impact
            FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 AND pr.report_date = $2
            GROUP BY ma.wa, ma.l6_main, ma.company
        """, site_id, today)
    raw_impacts = [r["raw_impact"] for r in impact_rows if r["raw_impact"]]
    p90 = statistics.quantiles(raw_impacts, n=10)[8] if len(raw_impacts) >= 10 else max(raw_impacts) if raw_impacts else 1
    
    out = []
    for r in impact_rows:
        wp_id = f"{(r['wa'] or 'unknown').lower().replace(' ', '-')}-{(r['l6_main'] or 'unknown').lower().replace(' ', '-')}-{(r['company'] or 'unknown').lower().replace(' ', '-')}"
        wp_evm = by_wp.get(wp_id, {})
        cpi = wp_evm.get("cpi", 0) or 0
        impact = min(100, (r["raw_impact"] / p90 * 100)) if p90 > 0 and r["raw_impact"] else 0
        # quadrant
        low_prod = cpi < 80
        high_impact = impact >= 50
        quadrant = "risk" if low_prod and high_impact else "caution" if low_prod else "watch" if high_impact else "safe"
        out.append({
            "wp_id": wp_id,
            "wp_name": f"{r['wa'] or ''} {r['l6_main'] or ''}".strip(),
            "trade": r["l6_main"] or "",
            "productivity": round(cpi, 1),
            "impact": round(impact, 1),
            "quadrant": quadrant,
            "size": max(30, min(120, int(impact))),
        })
    return out


async def _build_wp_summary(pg: PGClient, site_id: str, today: date, productivity: dict, quadrant_jsonb: list) -> list[dict]:
    """WP 표 — quadrant 와 같은 단위 + baseline + status."""
    by_wp = productivity.get("by_wp", {})
    # baseline = 같은 (company, l6) 의 mapped_history 평균 CPI
    # ... (implement baseline SQL)
    out = []
    for q in quadrant_jsonb:
        cpi = q["productivity"]
        status = "normal" if cpi >= 90 else "caution" if cpi >= 80 else "risk"
        out.append({
            **q,
            "baseline": 90,  # TODO: real baseline from mapped_history
            "status": status,
            "bp_name": "",  # TODO: from by_wp
            "progress_pct": 0,  # TODO: from by_wp progress
            "start_date": "",
            "end_date": "",
        })
    return out
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/optimizer/view_builder.py
git commit -m "feat(view_builder): _build_quadrant + impact P90 + _build_wp_summary"
```

---

### Task B.6: view_builder _build_s_curve (recovery_pattern 스키마 정합)

**Files:**
- Modify: `pipeline/optimizer/view_builder.py`

- [ ] **Step 1: _build_s_curve**

```python
async def _build_s_curve(pg: PGClient, site_id: str, today: date) -> list[dict]:
    """planned/actual/forecast/recovery 4 곡선 datapoint."""
    # planned curve — activity_master 균등분배 누계
    # actual curve — mapped_history 시계열 누적
    # forecast curve — 현 추세 연장 (deterministic linear)
    # recovery curve — optimizer_advice.recovery_pattern (스키마 정합 {date, recovery_days})
    
    # 구체 구현:
    async with pg._pool.acquire() as con:
        # planned curve (90일 시계열)
        planned = await con.fetch("""
            SELECT generate_series(MIN(plan_start), $2::date, '1 day')::date AS date,
                   SUM(plan_total_qty * LEAST(1.0, GREATEST(0.0,
                       (generate_series(MIN(plan_start), $2::date, '1 day')::date - plan_start + 1)::float
                       / NULLIF((plan_finish - plan_start + 1)::float, 0)
                   )))::float AS cum_plan_qty
            FROM activity_master WHERE site_id = $1
            GROUP BY date ORDER BY date
        """, site_id, today)
        
        actual = await con.fetch("""
            SELECT report_date, SUM(today_qty)::float AS day_qty
            FROM mapped_history WHERE site_id = $1 AND report_date <= $2
            GROUP BY report_date ORDER BY report_date
        """, site_id, today)
        
        # recovery_pattern (스키마 정합 — {date, recovery_days})
        rp_row = await con.fetchrow("""
            SELECT oa.recovery_pattern FROM optimizer_advice oa
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id = $1 ORDER BY oa.created_at DESC LIMIT 1
        """, site_id)
    
    # planned %, actual %, forecast (현 추세 연장), recovery (recovery_days 기반)
    # 산식: spec § 5.3
    ...  # implement
    return []  # placeholder
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/optimizer/view_builder.py
git commit -m "feat(view_builder): _build_s_curve + recovery_pattern 스키마 정합"
```

---

### Task B.7: view_builder _build_optimizer_view (4 섹션 + 6칸 details)

**Files:**
- Modify: `pipeline/optimizer/view_builder.py`

- [ ] **Step 1: _build_optimizer_view**

```python
def _build_optimizer_view(advice_rows: list[dict], forecast: list[dict], mapped: list[dict]) -> dict:
    """§ 02 by_wp dict — 진단/유사사례/권고/상세 6칸."""
    by_wp = {}
    for advice in advice_rows:
        # advice.company + advice.l6_main 으로 WP id (wa 부분은 forecasts/mapped 에서 lookup)
        for f in forecast:
            if f["company"] == advice["company"] and f["l6_main"] == advice["l6_main"]:
                wa = f.get("wa")
                wp_id = f"{(wa or 'unknown').lower().replace(' ','-')}-{advice['l6_main'].lower().replace(' ','-')}-{advice['company'].lower().replace(' ','-')}"
                
                # similar_cases 자연어 변환 (default Z1)
                similar_cases = []
                for c in (advice.get("degradation_cases") or []):
                    activities = c.get("activities", [])
                    conditions = c.get("conditions", "")
                    productivity = c.get("productivity", 0)
                    recovery = c.get("recovery", {})
                    rd = recovery.get("recovery_days")
                    similar_cases.append({
                        "date": c.get("date", ""),
                        "description": f"{conditions} — {activities[0] if activities else ''}, 생산성 {productivity:.1f}",
                        "outcome": f"{rd}일 후 회복" if rd is not None else "미회복",
                    })
                
                # recommendations text 만
                recs_raw = advice.get("recommendations") or []
                recommendations = [r["text"] if isinstance(r, dict) else str(r) for r in recs_raw]
                
                # 6칸 details
                rp = advice.get("recovery_pattern") or []
                rd_vals = [p.get("recovery_days") for p in rp if p.get("recovery_days") is not None]
                avg_rd = sum(rd_vals)/len(rd_vals) if rd_vals else None
                rdist = advice.get("recovery_distribution") or {}
                rdist_text = " / ".join(f"{k}: {v}건" for k, v in rdist.items())
                
                details = [
                    {"label": "위험 평가", "value": f.get("risk_level") or "—"},
                    {"label": "진단 대상", "value": f"{advice['company']} · {advice['l6_main']}"},
                    {"label": "유사 사례 수", "value": f"{len(advice.get('degradation_cases') or [])}건"},
                    {"label": "평균 회복 일수", "value": f"{avg_rd:.1f}일" if avg_rd else "—"},
                    {"label": "회복 분포", "value": rdist_text or "—"},
                    {"label": "일정 영향", "value": f"{round(f.get('delay_days') or 0)}일 지연"},
                ]
                
                by_wp[wp_id] = {
                    "diagnosis": advice.get("diagnosis") or "",
                    "similar_cases": similar_cases,
                    "recommendations": recommendations,
                    "details": details,
                }
                break
    
    # default_wp_id — 가장 high impact + risk_level 이상 우선
    default_wp_id = next(iter(by_wp.keys()), None) if by_wp else None
    
    return {"by_wp": by_wp, "default_wp_id": default_wp_id}
```

- [ ] **Step 2: 단위 테스트**

```python
# pipeline/tests/test_view_builder_optimizer_view.py
def test_optimizer_view_세보엠이씨_4섹션():
    advice = [{
        "company": "세보엠이씨", "l6_main": "기계소화설비",
        "diagnosis": "오늘 생산성은 정상 범위...",
        "degradation_cases": [{"date":"2025-09-23","activities":["철근 조립"],"conditions":"흐림","productivity":25.2,"recovery":{"recovery_days":1}}],
        "recommendations": [{"rank":1,"text":"장비 점검"},{"rank":2,"text":"..."}],
        "recovery_distribution": {"d+1": 2, "not_recovered": 1},
        "recovery_pattern": [{"date":"2025-09-23","recovery_days":1}],
    }]
    forecast = [{"company":"세보엠이씨","l6_main":"기계소화설비","wa":"FAB","risk_level":"정상","delay_days":-13}]
    v = _build_optimizer_view(advice, forecast, [])
    assert v["default_wp_id"] is not None
    wp = v["by_wp"][v["default_wp_id"]]
    assert wp["diagnosis"]
    assert len(wp["similar_cases"]) == 1
    assert len(wp["recommendations"]) == 2
    assert len(wp["details"]) == 6
```

- [ ] **Step 3: pytest**

Run: `pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_view_builder_optimizer_view.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pipeline/optimizer/view_builder.py pipeline/tests/test_view_builder_optimizer_view.py
git commit -m "feat(view_builder): _build_optimizer_view — 4 섹션 + 6칸 details (default Z1)"
```

---

### Task B.8: pipeline/db.py — upsert_daily_report_view_col (partial write)

**Files:**
- Modify: `pipeline/db.py`

- [ ] **Step 1: upsert helper**

```python
# pipeline/db.py 끝부분
async def upsert_daily_report_view_col(
    self, run_id, site_id: str, report_date: date, col: str, value: dict | list
) -> None:
    """daily_reports 의 jsonb 컬럼 1개 UPSERT — partial write 가드."""
    import json as _json
    async with self._pool.acquire() as con:
        await con.execute(
            f"""
            INSERT INTO daily_reports (run_id, site_id, report_date, {col})
            VALUES ($1, $2, $3, $4::jsonb)
            ON CONFLICT (run_id, site_id, report_date)
            DO UPDATE SET {col} = EXCLUDED.{col}
            """,
            run_id, site_id, report_date, _json.dumps(value, ensure_ascii=False, default=str),
        )
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/db.py
git commit -m "feat(db): upsert_daily_report_view_col — partial write per jsonb column"
```

---

### Task B.9: Optimizer agent — build_optimizer_views 호출 + partial write 가드

**Files:**
- Modify: `pipeline/agents/optimizer/agent.py:106-156` (`optimize`)

- [ ] **Step 1: optimize() 확장**

```python
# pipeline/agents/optimizer/agent.py
from pipeline.optimizer.view_builder import (
    _build_productivity_views, _build_kpi, _build_contractor_bars, _build_trade_bars,
    _build_quadrant, _build_wp_summary, _build_s_curve, _build_optimizer_view,
)

async def optimize(
    forecast, hil_2_selection, pre_optimizer_cases, run_id, today, cfg,
    site_id: str | None = None,  # 신규
    mapped: list | None = None,  # 신규
):
    advice_rows = [...]  # 기존
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        for row in advice_rows:
            await pg.insert_optimizer_advice(row)
        
        # 신규 흡수 — view builder (partial write 가드)
        if site_id:
            try:
                productivity = await _build_productivity_views(pg, run_id, site_id, today, forecast, mapped or [])
                quadrant = await _build_quadrant(pg, site_id, today, productivity)
                view_jsonbs = {
                    "productivity_jsonb": productivity,
                    "kpi_jsonb": await _build_kpi(pg, site_id, today, productivity),
                    "contractor_bars_jsonb": await _build_contractor_bars(productivity),
                    "trade_bars_jsonb": await _build_trade_bars(productivity),
                    "quadrant_jsonb": quadrant,
                    "wp_summary_jsonb": await _build_wp_summary(pg, site_id, today, productivity, quadrant),
                    "s_curve_jsonb": await _build_s_curve(pg, site_id, today),
                    "optimizer_view_jsonb": _build_optimizer_view(advice_rows, forecast, mapped or []),
                }
                for col, val in view_jsonbs.items():
                    try:
                        await pg.upsert_daily_report_view_col(run_id, site_id, today, col, val)
                    except Exception as e:
                        logger.warning(f"upsert {col} fail: {e}. partial write 유지.")
            except Exception as e:
                logger.error(f"build_optimizer_views fail: {e}. backfill 으로 fallback.")
    finally:
        await pg.close()
    return advice_rows
```

- [ ] **Step 2: pipeline/graph.py optimizer_node 정정 — site_id + mapped 전달**

`pipeline/graph.py` 의 `optimizer_node`:

```python
result = await optimize(
    forecast=state["forecast"],
    hil_2_selection=state["hil_2_selection"],
    pre_optimizer_cases=state["pre_optimizer_cases"],
    run_id=uuid.UUID(state["run_id"]),
    today=date.fromisoformat(state["date"]),
    cfg=cfg.optimizer,
    site_id=state.get("site_id"),     # ★
    mapped=state.get("mapped", []),    # ★
)
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/agents/optimizer/agent.py pipeline/graph.py
git commit -m "feat(optimizer): build view jsonb + daily_reports UPSERT (partial write 가드)"
```

---

### Task B.10: Backfill 스크립트 — 기존 cycle 일자 채움

**Files:**
- Create: `scripts/backfill_daily_report_views.py`

- [ ] **Step 1: 스크립트 신설**

```python
# scripts/backfill_daily_report_views.py
"""기존 9 cycle 일자에 daily_reports.view_jsonb 채움 — Phase B 마이그레이션 후 1회 실행."""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from pipeline.api import _build_prod_graph_config
from pipeline.db import PGClient
from pipeline.optimizer.view_builder import (
    _build_productivity_views, _build_kpi, _build_contractor_bars, _build_trade_bars,
    _build_quadrant, _build_wp_summary, _build_s_curve, _build_optimizer_view,
)


async def main():
    cfg = _build_prod_graph_config()
    pg = PGClient(cfg.mapper.postgres_url)
    await pg.connect()
    try:
        async with pg._pool.acquire() as con:
            runs = await con.fetch("""
                SELECT pr.run_id, pr.site_id, pr.report_date
                FROM pipeline_runs pr JOIN sites s ON s.site_id = pr.site_id
                WHERE s.is_mock = FALSE AND pr.status = 'completed'
                ORDER BY pr.report_date DESC
            """)
        print(f"[backfill] {len(runs)} cycles to backfill")
        for r in runs:
            run_id = r["run_id"]
            site_id = r["site_id"]
            today = r["report_date"]
            # forecast / advice / mapped from PG
            async with pg._pool.acquire() as con:
                forecast = await con.fetch("SELECT * FROM forecasts WHERE run_id=$1", run_id)
                advice = await con.fetch("SELECT * FROM optimizer_advice WHERE run_id=$1", run_id)
                mapped = await con.fetch("SELECT * FROM mapper_activities WHERE run_id=$1", run_id)
            forecast = [dict(f) for f in forecast]
            advice = [dict(a) for a in advice]
            mapped = [dict(m) for m in mapped]
            
            productivity = await _build_productivity_views(pg, run_id, site_id, today, forecast, mapped)
            quadrant = await _build_quadrant(pg, site_id, today, productivity)
            view_jsonbs = {
                "productivity_jsonb": productivity,
                "kpi_jsonb": await _build_kpi(pg, site_id, today, productivity),
                "contractor_bars_jsonb": await _build_contractor_bars(productivity),
                "trade_bars_jsonb": await _build_trade_bars(productivity),
                "quadrant_jsonb": quadrant,
                "wp_summary_jsonb": await _build_wp_summary(pg, site_id, today, productivity, quadrant),
                "s_curve_jsonb": await _build_s_curve(pg, site_id, today),
                "optimizer_view_jsonb": _build_optimizer_view(advice, forecast, mapped),
            }
            for col, val in view_jsonbs.items():
                try:
                    await pg.upsert_daily_report_view_col(run_id, site_id, today, col, val)
                except Exception as e:
                    print(f"[backfill] {run_id} {col} fail: {e}")
            print(f"[backfill] done {run_id} {site_id} {today}")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: backfill 실행**

```bash
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  PYTHONPATH=. pipeline/.venv/bin/python3 scripts/backfill_daily_report_views.py
```

Expected: `[backfill] done ...` 9 회

- [ ] **Step 3: PG 확인**

```bash
POSTGRES_URL=... pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg, os
async def main():
    con = await asyncpg.connect(os.environ['POSTGRES_URL'])
    r = await con.fetchrow(\"SELECT count(*) FROM daily_reports WHERE kpi_jsonb != '{}'::jsonb\")
    print(f'daily_reports rows with kpi_jsonb non-empty: {r[0]}')
asyncio.run(main())
"
```

Expected: 9 (또는 ≥ 1)

- [ ] **Step 4: Commit**

```bash
git add scripts/backfill_daily_report_views.py
git commit -m "feat(backfill): daily_report_views — 기존 cycle 일자 채움"
```

---

### Task B.11: FE — `/api/mock/report/route.ts` thin SELECT

**Files:**
- Modify: `web/app/api/mock/report/route.ts` (413 줄 → ~50 줄)

- [ ] **Step 1: thin route 재작성**

```typescript
// web/app/api/mock/report/route.ts
export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";

export async function GET() {
  const rows = await (sql as any)`
    SELECT pr.report_date,
           dr.kpi_jsonb, dr.contractor_bars_jsonb, dr.trade_bars_jsonb,
           dr.quadrant_jsonb, dr.wp_summary_jsonb, dr.s_curve_jsonb,
           dr.optimizer_view_jsonb, dr.productivity_jsonb
    FROM daily_reports dr
    JOIN pipeline_runs pr USING (run_id)
    JOIN sites s ON s.site_id = pr.site_id
    WHERE s.is_mock = FALSE
    ORDER BY pr.report_date DESC
  `;

  const daily = rows.map((r: any) => ({
    date: r.report_date instanceof Date ? r.report_date.toISOString().slice(0, 10) : String(r.report_date).slice(0, 10),
    status: r.kpi_jsonb?.risk_level === "이상" ? "risk" : r.kpi_jsonb?.risk_level === "주의" ? "caution" : "normal",
    productivity_today: r.kpi_jsonb?.productivity_today ?? 0,
    delay_days: r.kpi_jsonb?.delay_days ?? 0,
    recovery_days: r.kpi_jsonb?.recovery_days ?? 0,
  }));

  const details: Record<string, any> = {};
  for (const r of rows) {
    const date = r.report_date instanceof Date ? r.report_date.toISOString().slice(0, 10) : String(r.report_date).slice(0, 10);
    details[date] = {
      kpi: r.kpi_jsonb || {},
      s_curve: r.s_curve_jsonb || [],
      contractor_bars: r.contractor_bars_jsonb || [],
      trade_bars: r.trade_bars_jsonb || [],
      quadrant: r.quadrant_jsonb || [],
      optimizer: r.optimizer_view_jsonb || { by_wp: {}, default_wp_id: null },
      wp_summary: r.wp_summary_jsonb || [],
      raw_data: [],  // consolidated route 가 책임
    };
  }
  return NextResponse.json({ daily, details });
}
```

- [ ] **Step 2: vitest 회귀 — 기존 use-simulation.test.ts 통과 확인**

Run: `cd web && npm test -- use-simulation.test.ts`
Expected: PASS (이전과 동일)

- [ ] **Step 3: Commit**

```bash
git add web/app/api/mock/report/route.ts
git commit -m "refactor(fe): /api/mock/report thin SELECT — daily_reports view jsonb"
```

---

### Task B.12: FE — dashboard / agent-tasks / review thin SELECT

**Files:**
- Modify: `web/app/api/mock/dashboard/route.ts`
- Modify: `web/app/api/mock/agent-tasks/route.ts`
- Modify: `web/app/api/mock/review/route.ts`

- [ ] **Step 1: dashboard thin SELECT**

```typescript
// web/app/api/mock/dashboard/route.ts
export const dynamic = "force-dynamic";
import { NextResponse } from "next/server";
import sql from "@/lib/pg";

export async function GET() {
  // 90일 시계열 derive (daily_reports rows JOIN)
  const trend = await (sql as any)`
    SELECT pr.report_date,
           (dr.kpi_jsonb->>'cpi')::float AS cpi
    FROM daily_reports dr JOIN pipeline_runs pr USING (run_id)
    JOIN sites s ON s.site_id = pr.site_id
    WHERE s.is_mock = FALSE
    ORDER BY pr.report_date DESC LIMIT 90
  `;
  
  const latest = trend[0];
  return NextResponse.json({
    fleet: { kpi: { productivity_today: latest?.cpi ?? 0 }, trend },
    sites: [{ site_id: "m15x-ph3-ibl", name: "M15X Ph-3 IBL", status: "normal" }],
  });
}
```

- [ ] **Step 2: agent-tasks + review 동일 패턴으로 정정** (각 ~30 줄)

- [ ] **Step 3: Commit**

```bash
git add web/app/api/mock/{dashboard,agent-tasks,review}/route.ts
git commit -m "refactor(fe): dashboard/agent-tasks/review thin SELECT"
```

---

### Task B.13: FE — `web/lib/transforms.ts` 정리 (SQL 함수 제거)

**Files:**
- Modify: `web/lib/transforms.ts` (610 줄 → ~200 줄)

- [ ] **Step 1: SQL 사용 함수 제거**

제거: `deriveProductivityTimeseries` / `deriveStageProgress` / `deriveBaseline` / `wbsTreeBuild` / `deriveChatSequence` / `deriveSCurve` 및 내부 helpers (`_plannedCurve`, `_actualCurve`, `_forecastCurve`, `_recoveryCurve`).

유지: pure 함수 — `deriveProgressPercent` / `deriveYearlySaving` / `deriveItemStatus` / `deriveWpIdAndPath` / `deriveImpact`.

- [ ] **Step 2: vitest 회귀**

Run: `cd web && npm test`
Expected: 기존 transforms 테스트 일부 fail (제거된 함수) — 해당 테스트 파일 삭제 또는 skip.

- [ ] **Step 3: Commit**

```bash
git add web/lib/transforms.ts web/lib/__tests__/
git commit -m "refactor(fe): transforms.ts SQL 함수 제거 (산식 BE 이전)"
```

---

### Task B.14: FE reports/page.tsx — CPI/SPI 라벨 + selectedWpId fallback

**Files:**
- Modify: `web/app/(app)/reports/page.tsx`

- [ ] **Step 1: selectedWpId 초기값 4 단계 fallback**

```typescript
useEffect(() => {
  const detail = details[selectedDate];
  if (!detail) return;
  const wpSummary = detail.wp_summary || [];
  // 1. risk_level='이상' + high impact
  let initial = wpSummary
    .filter((w: any) => w.status === "risk")
    .sort((a: any, b: any) => (b.impact ?? 0) - (a.impact ?? 0))[0];
  // 2. risk_level='주의' + high impact
  if (!initial) initial = wpSummary
    .filter((w: any) => w.status === "caution")
    .sort((a: any, b: any) => (b.impact ?? 0) - (a.impact ?? 0))[0];
  // 3. by_wp dict 첫 row
  if (!initial) initial = wpSummary[0];
  // 4. 빈
  setSelectedWpId(initial?.wp_id ?? detail.optimizer?.default_wp_id ?? null);
}, [selectedDate, details]);
```

- [ ] **Step 2: ProductivityTrendChart 옆 CPI/SPI chip 추가**

```typescript
// reports/page.tsx 의 § 01 Section 안
<div className="flex gap-2 mt-2">
  <span className="chip chip-mint">SPI {detail.kpi.spi?.toFixed(1) ?? "—"}% (시공 진척률)</span>
  <span className="chip chip-brand">CPI {detail.kpi.cpi?.toFixed(1) ?? "—"}% (mh 효율)</span>
</div>
```

- [ ] **Step 3: Commit**

```bash
git add web/app/\(app\)/reports/page.tsx
git commit -m "feat(fe): reports selectedWpId fallback + CPI/SPI chip 라벨"
```

---

### Task B.15: FE OptimizerResult — 4 섹션 NULL fallback

**Files:**
- Modify: `web/app/components/reports/OptimizerResult.tsx:9-46`

- [ ] **Step 1: NULL fallback 표시 추가**

```typescript
export function OptimizerResult({ output }: { output: OptimizerOutput }) {
  return (
    <div className="...">
      <Row icon={<Brain />} tone="brand" title="진단">
        <p>{output.diagnosis || "진단 데이터 없음 (Optimizer 미실행 또는 cold_start)"}</p>
      </Row>
      <Row icon={<History />} tone="brand" title="유사 과거 사례" topBorder>
        {output.similar_cases?.length ? (
          <ul>{output.similar_cases.map((c, i) => <li key={i}>{c.date} · {c.description} → {c.outcome}</li>)}</ul>
        ) : (
          <p className="text-ink-light">유사 사례 없음 — 데이터 누적 후 갱신</p>
        )}
      </Row>
      <Row icon={<Lightbulb />} tone="sun" title="권고사항" topBorder>
        {output.recommendations?.length ? (
          <ul>{output.recommendations.map((r, i) => <li key={i}>{r}</li>)}</ul>
        ) : (
          <p className="text-ink-light">권고 미산출 — cold_start</p>
        )}
      </Row>
      <Row icon={<Database />} tone="mint" title="상세 현황" topBorder>
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5">
          {output.details?.map((d, i) => (
            <div key={i} className="contents">
              <dt>{d.label}</dt>
              <dd>{d.value || "—"}</dd>
            </div>
          ))}
        </dl>
      </Row>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/components/reports/OptimizerResult.tsx
git commit -m "feat(fe): OptimizerResult 4 섹션 NULL fallback (design-lens 5)"
```

---

### Task B.16: FE ForecastChart + diagnosis.ts — 라벨 + PRNG 제거

**Files:**
- Modify: `web/app/components/charts/ForecastChart.tsx`
- Modify: `web/lib/diagnosis.ts`

- [ ] **Step 1: ForecastChart 라벨 정정**

```typescript
// ForecastChart.tsx 의 ToggleChip 라벨
<ToggleChip label="만회 시나리오 (AI)" color="mint" ... />
<ToggleChip label="현 추세 연장" color="rose" ... />
```

- [ ] **Step 2: lib/diagnosis.ts PRNG 제거 + 실 통계 input**

```typescript
// web/lib/diagnosis.ts
export function diagnose(input: DiagnosisInput): ProductivityDiagnosis {
  // PRNG (mulberry32) 제거. base/optimistic/pessimistic 곡선을 deterministic linear extrapolation 으로.
  const { history_mean, today_progress, s_curve } = input;
  
  const firstUndef = s_curve.findIndex((p) => p.actual === undefined);
  const todayIdx = firstUndef === -1 ? s_curve.length - 1 : firstUndef - 1;
  const lastActual = todayIdx >= 0 ? (s_curve[todayIdx].actual ?? 0) : 0;
  
  // base = 현 추세 연장 (today_progress 율로 누적)
  const baseStep = today_progress / 100;
  const optimisticStep = baseStep * 1.18;
  const pessimisticStep = today_progress / 100 * 0.8;
  
  // 곡선 build — deterministic, jitter 없음
  const buildLinearCurve = (step: number): (number | null)[] => {
    const out: (number | null)[] = [];
    let cum = lastActual;
    for (let i = 0; i < s_curve.length; i++) {
      if (i < todayIdx) out.push(null);
      else if (i === todayIdx) out.push(lastActual);
      else { cum = Math.min(100, Math.max(0, cum + step)); out.push(cum); }
    }
    return out;
  };
  
  // ... 기존 산식 유지하되 PRNG 호출 모두 제거
  return { ... };
}
```

- [ ] **Step 3: vitest 회귀**

Run: `cd web && npm test diagnosis`
Expected: PASS (deterministic 결과)

- [ ] **Step 4: Commit**

```bash
git add web/lib/diagnosis.ts web/app/components/charts/ForecastChart.tsx
git commit -m "feat(fe): ForecastChart '현 추세 연장' 라벨 + diagnosis.ts PRNG 제거"
```

---

### Task B.17: FE Dashboard mock site 회색 + preview + modal

**Files:**
- Modify: `web/app/(app)/home/page.tsx` 또는 dashboard 의 site 카드 컴포넌트

- [ ] **Step 1: mock site 카드 회색 처리 + preview 라벨**

```typescript
// site card 컴포넌트
const isMock = site.is_mock;
return (
  <div className={`card ${isMock ? "opacity-50 grayscale" : ""}`} onClick={() => isMock ? showModal() : navigate(site)}>
    {isMock && <span className="badge">preview</span>}
    <div>{site.name}</div>
  </div>
);

function showModal() {
  // modal "데이터 준비 중 — Parser 강화 cycle 완료 후 synthetic 데이터 적재 예정"
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/...
git commit -m "feat(fe): mock site 회색 + preview 라벨 + '데이터 준비 중' modal"
```

---

### Task B.18: Playwright UI 캡쳐 + 정량 assertion

**Files:**
- Create: `web/tests/playwright/reports.spec.ts`

- [ ] **Step 1: playwright test 신설**

```typescript
// web/tests/playwright/reports.spec.ts
import { test, expect } from "@playwright/test";

test("reports page — 10 정량 기준", async ({ page }) => {
  await page.goto("http://localhost:5536/reports");
  await page.waitForLoadState("networkidle");
  
  // 1. CPI 헤더 % 표시
  const cpiHeader = await page.locator('text=/CPI \\d+/').first().textContent();
  expect(cpiHeader).toMatch(/CPI \d+\.\d+%/);
  
  // 2. 90일 trend chart line 그어짐
  expect(await page.locator(".recharts-area").count()).toBeGreaterThan(0);
  
  // 3. 업체별 bar count >= 5
  const contractorBars = await page.locator('[data-testid="contractor-bar"]').count();
  expect(contractorBars).toBeGreaterThanOrEqual(5);
  
  // 4. 공종별 bar count >= 8
  // ... 8 ~ 15
  
  // 5. 4분면 점 count >= 10 + 4 quadrant 모두 1점 이상
  const points = await page.locator('[data-testid="quadrant-point"]').count();
  expect(points).toBeGreaterThanOrEqual(10);
  
  // 6. WP 표 row >= 10
  expect(await page.locator('[data-testid="wp-row"]').count()).toBeGreaterThanOrEqual(10);
  
  // 7. 4 섹션 모두 빈 칸 0
  expect(await page.locator('text="진단 데이터 없음"').count()).toBe(0);
  
  // 8. 상세 6칸 표시
  expect(await page.locator('[data-testid="optimizer-detail"]').count()).toBe(6);
  
  // 9. S-curve 4 곡선
  expect(await page.locator(".recharts-line").count()).toBeGreaterThanOrEqual(4);
  
  // 10. narrative "현 추세 연장" + "AI 회복 시나리오"
  await expect(page.locator('text="현 추세 연장"')).toBeVisible();
  await expect(page.locator('text=/AI.*시나리오/')).toBeVisible();
});
```

- [ ] **Step 2: dev server 띄움 + playwright 실행**

```bash
cd web && (npm run dev &) && sleep 5 && npx playwright test reports.spec.ts
```

Expected: 10 assertion PASS

- [ ] **Step 3: Commit**

```bash
git add web/tests/playwright/reports.spec.ts
git commit -m "test(fe): reports playwright 10 정량 assertion (end-image 검증)"
```

---

## 최종 검증 + PR 생성

- [ ] 전체 pytest 실행: `pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -v`
- [ ] 전체 vitest 실행: `cd web && npm test`
- [ ] dev server :5536 reports 페이지 직접 확인
- [ ] git push + PR 생성

```bash
git push -u origin A_Track
gh pr create --title "feat: reports gap + parser 강화 (cycle A+B)" --body "..."
```

---

## 의존성 그래프 (참고)

```
A.0 (test scaffolding)
  ↓
A.1/A.2/A.3/A.4 (prompts 재작성, 병렬 가능)
  ↓
A.5 (retry)
  ↓
A.6/A.7 (parser_post 신설 + 통합)
  ↓
A.8 (mapper company normalize)
  ↓
A.9 (Stage 1 실측) → A.10 (Stage 2)
  ↓
[Phase A Gate: 시트 1 + 시트 4 통과]
  ↓
B.0 (PG migration)
  ↓
B.1 (Mapper U1.A) → B.2 (U1.B)
  ↓
B.3 (view_builder _build_productivity_views) → B.4/B.5/B.6/B.7 (8 builder)
  ↓
B.8 (db upsert) → B.9 (optimizer 통합)
  ↓
B.10 (backfill 실행)
  ↓
B.11/B.12 (FE thin routes) + B.13 (transforms 정리, 병렬)
  ↓
B.14/B.15/B.16/B.17 (FE 컴포넌트, 병렬)
  ↓
B.18 (Playwright 검증)
  ↓
PR 생성
```
