"""LLM 기반 작업일보 parser — DEPRECATED (2026-05-20).

본 모듈은 chunk LLM parsing 으로 ParsedDailyReport 를 생성했으나, 5/20 부터
`pipeline.agents.parser.parse_daily_report` (rule-based + 시트1/4 LLM 검증 hybrid)
로 대체됨. 이 모듈은 본 cycle 의 graph entry 에서 호출되지 않음.

회귀 사용 (rule path 가 실패하는 비상 경로):
  - collector / run_one_cycle 의 import 를 parser_llm 으로 되돌리면 동작.
  - 또는 env flag `CPIA_PARSER=llm` 으로 graph entry 안에서 분기 (미구현).

대체 이유:
  - chunk LLM 270 호출 → 4-5 분 / cycle, ~$3 / cycle → 시연 마감 (6/5) 압력
  - rule + 시트1/4 LLM 검증 hybrid → ~20 초 / cycle, ~$0.55 / cycle
  - 매핑 정확도: mapper auto_bp_zone_match (BP-zone deterministic) 와 정합

spec: docs/superpowers/specs/2026-05-20-cpia-parser-mapper-refactor-design.md

----
이하 원본 docstring 보존 (회귀 사용 시 참고):

2026-05-19 신규. 기존 정규화 코드 (parser.py) 가 작업일보 양식 비일관 (2-row group +
시트2/3 다중 row pattern) 에 brittle 한 문제 해결. schema-guided LLM 으로 6 시트 추출.

설계:
  Phase A: openpyxl 으로 시트별 raw row → list[dict[col, value]]
  Phase B: row 3-4 헤더 추출 → col 의미 dict
  Phase C: 시트별 LLM 호출 (6 시트 × 1 호출, asyncio.gather 병렬)
            JSON mode + 출력 schema 강제 + retry 1회
            ↓
          ParsedDailyReport (BPSummary[] / JobAllocation[] / EquipmentAllocation[] /
                              Activity[] / WorkerOutput[] / ReportMeta)

비용 추정 (Azure gpt-5.1-chat-ai-board-test):
  통합 일보 1건 ≈ 150K input tokens (시트2/3 noise 필터 후) × 6 호출 ≈ $0.70
  업체별 일보 1건 ≈ 10K tokens × 6 호출 ≈ $0.05
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl
from openai import AzureOpenAI

from pipeline.agents import parser_post
from pipeline.state import ParsedDailyReport


@dataclass
class ParserConfig:
    """LLM Parser 호출 환경."""

    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    llm_model: str
    sheet_concurrency: int = 3  # 6 시트 LLM 호출 동시 (Azure rate-limit 회피)


# ---------------------------------------------------------------------------
# 메타 추출
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"_(\d{4})(\d{2})(\d{2})\.xlsx$|_(\d{6})\.xlsm?$")


def _extract_date_from_filename(p: Path) -> str:
    m = _DATE_RE.search(p.name)
    if not m:
        return ""
    if m.group(1):
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    ymd = m.group(4)
    return f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:6]}"


# ---------------------------------------------------------------------------
# 시트 raw → JSON
# ---------------------------------------------------------------------------


def _sheet_to_payload(
    ws,
    header_rows: tuple[int, ...] = (2, 3),
    body_start: int = 4,
    max_body_rows: int | None = None,
    row_filter=None,
    ffill_cols: tuple[int, ...] = (1, 2, 3, 4),
) -> tuple[dict[int, str], list[dict[int, Any]]]:
    """ws → (header_map, body_rows).

    header_map: {col_idx: "row3 헤더 | row4 sub-header"}
    body_rows: list[dict[col_idx, value]] — 빈 row skip. row_filter 통과만.
    ffill_cols: 작업일보 양식의 셀 병합 패턴 — col 1~4 (구분/Zone/공종/BP사) 가 묶여있어
                다음 row 빈 cell 은 forward-fill. col 5+ 는 ffill 안 함 (Scope/업체명 등 row 마다 다름).
    """
    rows = list(ws.iter_rows(values_only=True))

    header_map: dict[int, str] = {}
    for ri in header_rows:
        if ri >= len(rows):
            continue
        for c, v in enumerate(rows[ri]):
            if v is None:
                continue
            s = str(v).strip()
            if not s:
                continue
            existing = header_map.get(c, "")
            header_map[c] = f"{existing} | {s}" if existing else s

    body: list[dict[int, Any]] = []
    last_ffill: dict[int, Any] = dict.fromkeys(ffill_cols, None)
    for r in rows[body_start:]:
        d_raw = {c: v for c, v in enumerate(r) if v is not None and str(v).strip() != ""}
        if not d_raw:
            continue
        # forward-fill 메타 컬럼
        for fc in ffill_cols:
            if fc in d_raw:
                last_ffill[fc] = d_raw[fc]
            elif last_ffill[fc] is not None:
                d_raw[fc] = last_ffill[fc]
        if row_filter is not None and not row_filter(d_raw):
            continue
        body.append(d_raw)
        if max_body_rows is not None and len(body) >= max_body_rows:
            break
    return header_map, body


def _is_job_alloc_signal_row(d: dict[int, Any]) -> bool:
    """시트2 row 의미있는지 — 관리자 직종 / 0 인원 / 합계 row skip."""
    job = str(d.get(5, "") or "").strip()
    if not job or job in {"BP소장", "공사관리자", "안전관리자", "품질관리자", "일반관리자"}:
        return False
    for v in d.values():
        if isinstance(v, str) and "투입 Total" in v:
            return False
    cum_t = d.get(23)  # 금일누계 Cum.T
    try:
        if cum_t is not None and float(cum_t) <= 0:
            return False
    except (TypeError, ValueError):
        pass
    return True


_MARKER_PATTERNS = {"M15 PH-X", "FAB", "CUB", "M15X", "M15 X"}
_BP_CODE_RE = re.compile(r"^PH_X-\d+$")


def _is_real_bp(value: str | None) -> bool:
    """진짜 BP사 식별 — BP 코드 ('PH_X-123') 또는 한글 회사명."""
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
    bp = d.get(2)
    return bool(big and mid and _is_real_bp(bp))


# ---------------------------------------------------------------------------
# LLM prompt template
# ---------------------------------------------------------------------------

_TIMESHIFT_SCHEMA = (
    '{ "morning": int, "daytime": int, "overtime": int, '
    '"night": int, "all_night": int, "total": int }'
)

_SYS_BP_SUMMARIES = f"""당신은 건설 작업일보 시트1 (출력인원 현황) 파서. raw row JSON → BPSummaryRaw list (1 row = 1 출력).

# 입력
header_map = col_idx → 헤더 의미.
rows = list[dict[col_idx, value]] — 각 row 가 1 BP 단위 row.

# BPSummaryRaw 출력 schema (각 row 1개)
{{
  "row_idx": int,
  "col_4_value": str|null,
  "is_bp_code": bool,
  "is_korean_company": bool,
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
  "company_or_bp": str|null,
  "disc_code": str|null,
  "worker_code": str|null,
  "job_type": str|null,
  "disc_abbrev": str|null,
  "workers_today_cum": {_TIMESHIFT_SCHEMA}|null,
  "workers_cum_t": int|null,
  "final_flag": "O"|"X"|null
}}

# 핵심 규칙
1. **각 input row = 1 JobAllocationRaw**. len(rows) == len(items).
2. disc_code 는 raw 그대로 (Mm## 또는 Wk##). 의미 해석 X.
3. 모르는 필드 null. 시간대 6 필드 누락 시 각 0.

# 출력
{{ "job_allocations_raw": [JobAllocationRaw, ...] }}
"""

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

_SYS_ACTIVITIES = """건설 작업일보 시트4 (물량) 파서. 입력의 rows 리스트의 **각 row 가 1 Activity** 입니다.
rows 갯수와 동일한 수의 Activity 를 출력하세요 (절대 빈 list 반환 X).

# 헤더 ↔ schema 매핑 가이드 (header_map 의 string 보고 매칭)
- header "Zone"                          → activity.zone
- header "BP사" 또는 "협력업체"          → activity.bp_code (코드면 bp_code, 한글 회사명이면 company)
- header "업체명"                         → activity.company (한글)
- header "Scope"                          → activity.scope
- header "공종" 또는 "Dis"               → activity.trade / l5_disc (영문 약자 → 한글: TE=공통가설, AR=건축, CI=토목, ME=설비, EL=전기, UT=UT, IN=제어)
- header "대표물량_작업 내용"            → activity.work_content
- header "단위"                          → activity.unit (소문자: M2→m2, Ton→ton)
- header "총물량 [A]"                    → activity.plan_total_qty
- header "전일누적 [B]"                  → activity.yesterday_cum_qty
- header "금일실적 [C]"                  → activity.today_qty (기본 0)
- header "금일누적 [D = B+C]"            → activity.today_cum_qty
- header "F% [D/A]"                      → activity.progress_percent (0~1 float)
- header "잔여 [E = A-D]"                → activity.remaining_qty
- header "G% [100% - F]"                 → activity.remaining_percent (0~1 float)
- header "비고"                          → activity.note
- header "작업 위치_코드"                → activity.work_location_code
- header "중공종명" 또는 "공종명 (Line명)" → activity.wbs_mid_name
- header "소공종명"                      → activity.wbs_sub_name
- header "세공종명"                      → activity.wbs_detail_name

# 출력 schema (각 Activity)
{
  "zone": str|null, "bp_code": str|null, "company": str, "scope": str|null,
  "trade": str, "l5_disc": str, "work_content": str, "unit": str,
  "plan_total_qty": float|null, "yesterday_cum_qty": float|null,
  "today_qty": float, "today_cum_qty": float|null,
  "progress_percent": float|null, "remaining_qty": float|null, "remaining_percent": float|null,
  "note": str|null,
  "work_location_code": str|null, "wbs_mid_name": str|null,
  "wbs_sub_name": str|null, "wbs_detail_name": str|null
}

# 핵심 규칙
1. 입력 rows 의 **모든 row 가 1 Activity** — len(rows) == len(activities).
2. **list 안에는 반드시 object (dict) 만**. 문자열 / 숫자 직접 배치 X.
3. company 는 한글 회사명 우선 (header "업체명" 또는 한글 row 값). 회사명 없으면 BP 코드 그대로.
4. trade / l5_disc 동일 값 (둘 다 한글 공종명).
5. 누락 필드는 null. 추측 X. 0 도 OK (today_qty=0 정상).

# 출력 (JSON 만)
{ "activities": [Activity, ...] }
"""

_SYS_WORKER_OUTPUTS = """건설 작업일보 시트6 (출력일보) 파서. 각 row 마다 worker_name (작업자 성함) 가 있으면 무조건 1건 출력.

# 출력 schema (각 WorkerOutput)
{
  "worker_name": str, "job_type": str,
  "wbs_mid_name": str|null, "wbs_sub_name": str|null, "wbs_detail_name": str|null,
  "work_location_code": str|null, "work_content": str|null,
  "shift_morning": int, "shift_daytime": int, "shift_overtime": int,
  "shift_night": int, "shift_all_night": int,
  "note": str|null
}

# 규칙
1. **header_map 의 col 의미만 사용** — col 인덱스는 양식마다 다름.
2. worker_name (작업자 성함) 가 있는 row 는 무조건 1건 추출.
3. shift_* — 시간대별 "1" 또는 0. 빈 cell → 0.
4. 헤더/합계/빈 row skip.

# 출력 (JSON 만, 다른 설명 없음)
{ "worker_outputs": [WorkerOutput, ...] }
"""

_SYS_REPORT_META = """당신은 건설 작업일보 Cover 시트 (업체별만) 파서. raw row JSON → ReportMeta 1 객체.

# ReportMeta 출력 schema
{
  "project_name":  "M15X PH4" 등 또는 null,
  "project_code":  "M15X_PH4_041" 등 또는 null,
  "site_id":       null (Cover 에 site_id 명시 X — Merge 단계가 채움),
  "bp_name":       협력업체명 ("중원엔지니어링FAB" 등) 또는 null,
  "writer":        작성자 또는 null,
  "reviewer":      검토자 또는 null,
  "approval":      결재자 또는 null,
  "report_date":   "YYYY-MM-DD" — required,
  "document_no":   문서 번호 또는 null
}

# 출력 형식
{ "report_meta": ReportMeta }
"""


# ---------------------------------------------------------------------------
# LLM 호출 helper
# ---------------------------------------------------------------------------


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
    import time as _time

    input_rows_count = len(user_payload.get("rows", [])) if isinstance(user_payload, dict) else 0

    last_err: Exception | None = None
    last_result: Any = None
    for attempt in range(retries + 1):
        # exponential backoff between retries — Azure rate limit / content_filter 회피
        if attempt > 0:
            _time.sleep(2 ** (attempt - 1))  # 1s, 2s, 4s, 8s, ...
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
            if finish_reason == "length":
                last_err = RuntimeError(f"truncated (max_completion_tokens={max_completion_tokens})")
                continue
            if finish_reason == "content_filter":
                last_err = RuntimeError("content_filter blocked")
                if last_result is None:
                    last_result = []  # content_filter block → 빈 리스트로 폴백, raise 방지
                continue
            obj = json.loads(raw)
            result = obj.get(response_key)
            if input_rows_count > 0 and isinstance(result, list) and len(result) == 0:
                last_err = RuntimeError(f"empty list returned (input rows={input_rows_count})")
                last_result = result
                continue
            return result
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(
                f"[parser_llm] key={response_key} attempt={attempt} EXCEPTION {type(e).__name__}: {e}",
                file=_sys.stderr,
                flush=True,
            )
            continue
    if last_result is not None:
        print(f"[parser_llm] key={response_key} all retries failed, returning last_result", file=_sys.stderr, flush=True)
        return last_result
    raise RuntimeError(f"LLM extract '{response_key}' 실패 {retries+1}회: {last_err}")


def _llm_extract_chunked(
    client: AzureOpenAI,
    model: str,
    system_prompt: str,
    header_map: dict[int, str],
    rows: list[dict],
    response_key: str,
    chunk_size: int = 30,
    max_completion_tokens: int = 16000,
) -> list[dict]:
    """rows 를 chunk_size 단위로 분할 → 각 chunk LLM 호출 → 합쳐서 반환.

    LLM 이 단일 호출에서 큰 rows 처리 거절하는 케이스 (실측 80 rows 에서 거절) 회피.
    """
    if not rows:
        return []
    out: list[dict] = []
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        payload = {"header_map": header_map, "rows": chunk}
        partial = _llm_extract_sync(
            client, model, system_prompt, payload, response_key,
            retries=3, max_completion_tokens=max_completion_tokens,
        )
        if partial:
            out.extend(partial)
    return out


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------


async def parse_daily_report_llm(
    xlsx_path: Path | str,
    cfg: ParserConfig,
    max_rows_per_sheet: dict[str, int] | None = None,
) -> ParsedDailyReport:
    """xlsx 1건 → ParsedDailyReport (6 entity).

    통합 / 업체별 자동 판단 (시트6/Cover 존재 여부).
    시트별 LLM 호출 6 회 (병렬). Azure rate-limit 고려해 Semaphore.

    max_rows_per_sheet (sample mode): {"bp_summaries": 50, "job_allocations": 200, ...}
      _sheet_to_payload 의 max_body_rows 로 전달 — row_filter 통과한 signal row 만 limit.
      None 이면 full mode (전체 row 처리).
    """
    _max = max_rows_per_sheet or {}
    xlsx_path = Path(xlsx_path)
    report_date = _extract_date_from_filename(xlsx_path)

    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    try:
        sheet_names = wb.sheetnames
        has_worker_outputs = any("출력일보" in s for s in sheet_names)
        has_cover = "Cover" in sheet_names

        # Phase A — raw payload 추출
        payloads: dict[str, dict] = {}
        sn_sheet1 = next((s for s in sheet_names if s.startswith("1.")), None)
        sn_sheet2 = next((s for s in sheet_names if s.startswith("2.")), None)
        sn_sheet3 = next((s for s in sheet_names if s.startswith("3.")), None)
        sn_sheet4 = next((s for s in sheet_names if s.startswith("4.")), None)
        sn_sheet6 = next((s for s in sheet_names if "출력일보" in s), None)

        if sn_sheet1:
            h, b = _sheet_to_payload(
                wb[sn_sheet1],
                max_body_rows=_max.get("bp_summaries"),
            )
            payloads["bp_summaries"] = {"header_map": h, "rows": b}

        if sn_sheet2:
            h, b = _sheet_to_payload(
                wb[sn_sheet2], header_rows=(3, 4), body_start=5,
                row_filter=_is_job_alloc_signal_row,
                max_body_rows=_max.get("job_allocations"),
            )
            payloads["job_allocations"] = {"header_map": h, "rows": b}

        if sn_sheet3:
            h, b = _sheet_to_payload(
                wb[sn_sheet3], header_rows=(3, 4), body_start=5,
                row_filter=_is_equipment_signal_row,
                max_body_rows=_max.get("equipment_allocations"),
            )
            payloads["equipment_allocations"] = {"header_map": h, "rows": b}

        if sn_sheet4:
            h, b = _sheet_to_payload(
                wb[sn_sheet4],
                max_body_rows=_max.get("activities"),
            )
            payloads["activities"] = {"header_map": h, "rows": b}

        if sn_sheet6:
            # 시트6 (출력일보) 구조: row 1 = 시트명, row 2 = 일자 meta, row 3 = 헤더, row 4+ = 데이터.
            h, b = _sheet_to_payload(wb[sn_sheet6], header_rows=(2,), body_start=3)
            payloads["worker_outputs"] = {"header_map": h, "rows": b}

        cover_payload: dict | None = None
        if has_cover:
            ws = wb["Cover"]
            cover_rows = [
                {c: (str(v) if v is not None else None) for c, v in enumerate(r) if v is not None}
                for r in ws.iter_rows(values_only=True)
                if any(c is not None for c in r)
            ]
            cover_payload = {"rows": cover_rows, "filename": xlsx_path.name}
    finally:
        wb.close()

    # Phase C — LLM 호출 (시트별 1 회씩, 병렬)
    client = AzureOpenAI(
        api_key=cfg.azure_api_key,
        api_version=cfg.azure_api_version,
        azure_endpoint=cfg.azure_endpoint,
    )
    sem = asyncio.Semaphore(cfg.sheet_concurrency)

    async def _call_list(system_prompt: str, payload: dict, response_key: str, chunk_size: int = 30) -> list[dict]:
        async with sem:
            return await asyncio.to_thread(
                _llm_extract_chunked,
                client, cfg.llm_model, system_prompt,
                payload["header_map"], payload["rows"], response_key, chunk_size,
            )

    async def _call_single(system_prompt: str, payload: dict, response_key: str) -> Any:
        async with sem:
            return await asyncio.to_thread(
                _llm_extract_sync, client, cfg.llm_model, system_prompt, payload, response_key,
            )

    tasks: dict[str, asyncio.Task] = {}
    if "bp_summaries" in payloads:
        tasks["bp_summaries_raw"] = asyncio.create_task(
            _call_list(_SYS_BP_SUMMARIES, payloads["bp_summaries"], "bp_summaries_raw", chunk_size=15)
        )
    if "job_allocations" in payloads:
        tasks["job_allocations_raw"] = asyncio.create_task(
            _call_list(_SYS_JOB_ALLOCATIONS, payloads["job_allocations"], "job_allocations_raw", chunk_size=15)
        )
    if "equipment_allocations" in payloads:
        tasks["equipment_allocations_raw"] = asyncio.create_task(
            _call_list(_SYS_EQUIPMENT_ALLOCATIONS, payloads["equipment_allocations"], "equipment_allocations_raw", chunk_size=15)
        )
    if "activities" in payloads:
        tasks["activities"] = asyncio.create_task(
            _call_list(_SYS_ACTIVITIES, payloads["activities"], "activities", chunk_size=15)
        )
    if "worker_outputs" in payloads:
        tasks["worker_outputs"] = asyncio.create_task(
            _call_list(_SYS_WORKER_OUTPUTS, payloads["worker_outputs"], "worker_outputs", chunk_size=50)
        )
    if cover_payload is not None:
        tasks["report_meta"] = asyncio.create_task(
            _call_single(_SYS_REPORT_META, cover_payload, "report_meta")
        )

    results: dict[str, Any] = {}
    for k, t in tasks.items():
        results[k] = await t

    # post-processing: raw → 정제된 entity
    # dict-only guard — LLM 이 가끔 str / null 을 list 안에 섞어 출력 (schema 위반)
    def _dict_only(xs: Any) -> list[dict]:
        return [x for x in xs if isinstance(x, dict)] if isinstance(xs, list) else []

    bp_summaries = parser_post.transform_bp_summaries(_dict_only(results.get("bp_summaries_raw")))
    job_allocations = parser_post.transform_job_allocations(_dict_only(results.get("job_allocations_raw")))
    equipment_allocations = parser_post.transform_equipment_allocations(
        _dict_only(results.get("equipment_allocations_raw"))
    )
    activities = _dict_only(results.get("activities"))  # 이미 final shape (raw 변환 X)

    # project 명: Cover.project_name 우선, 그 다음 파일명 stem.
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
