"""Parser 단계별 intercept 진단 스크립트 (read-only, DB write X).

사용:
  pipeline/.venv/bin/python3 scripts/diag_parser_intercept.py <xlsx_path>            # Stage 1+3
  pipeline/.venv/bin/python3 scripts/diag_parser_intercept.py <xlsx_path> --llm      # + Stage 2 (Azure OpenAI 호출)
  pipeline/.venv/bin/python3 scripts/diag_parser_intercept.py <xlsx_path> --llm-chunks 1,500,1000   # 특정 chunk 만 LLM

목적: xlsx 시트2 15,501 row 중 DB 15 row 만 적재되는 누락의 정확한 단계 식별.
- Stage 1: xlsx → _sheet_to_payload (header_map, body) — 헤더 인식 + ffill 확인
- Stage 2: payload → _llm_extract_sync 1 chunk raw output (Azure OpenAI 호출, 옵션)
- Stage 3: raw → parser_post.transform_* — filter_marker_rows / normalize_company 의 누락량
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

import openpyxl  # noqa: E402

from pipeline.agents import parser_llm, parser_post  # noqa: E402


def _short(v, width: int = 30):
    if v is None:
        return None
    s = str(v).strip().replace("\n", " ")
    return s[:width] + ("..." if len(s) > width else "")


def stage1(xlsx_path: Path) -> dict:
    """Stage 1: xlsx → _sheet_to_payload — 헤더 + body 첫/끝 dump."""
    print("\n" + "=" * 80)
    print("STAGE 1 — xlsx → _sheet_to_payload (header_map + body_rows)")
    print("=" * 80)
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    sheet_names = wb.sheetnames

    sn_sheet1 = next((s for s in sheet_names if s.startswith("1.")), None)
    sn_sheet2 = next((s for s in sheet_names if s.startswith("2.")), None)
    sn_sheet3 = next((s for s in sheet_names if s.startswith("3.")), None)
    sn_sheet4 = next((s for s in sheet_names if s.startswith("4.")), None)

    payloads = {}

    def _dump(name, h, b, xlsx_rows):
        print(f"\n--- 시트 {name} ---")
        print(f"  xlsx max_row     : {xlsx_rows}")
        print(f"  body_rows length : {len(b)} (None/빈 row 제외 + ffill 적용 후)")
        print(f"  header_map keys  : {sorted(h.keys())}")
        for c in sorted(h.keys()):
            print(f"    col {c:2}: {_short(h[c], 50)}")
        print("  body[:5] (col 0~10):")
        for i, row in enumerate(b[:5]):
            preview = {k: _short(row.get(k), 20) for k in sorted(row.keys()) if k <= 10}
            print(f"    [{i}] {preview}")
        if len(b) > 10:
            print("  body[-3:] (col 0~10):")
            for i, row in enumerate(b[-3:]):
                preview = {
                    k: _short(row.get(k), 20) for k in sorted(row.keys()) if k <= 10
                }
                print(f"    [-{3 - i}] {preview}")

    if sn_sheet1:
        h, b = parser_llm._sheet_to_payload(wb[sn_sheet1])
        payloads["sheet1"] = {"sheet_name": sn_sheet1, "header_map": h, "rows": b}
        _dump(sn_sheet1, h, b, wb[sn_sheet1].max_row)
    if sn_sheet2:
        h, b = parser_llm._sheet_to_payload(
            wb[sn_sheet2],
            header_rows=(3, 4),
            body_start=5,
            row_filter=parser_llm._is_job_alloc_signal_row,
        )
        payloads["sheet2"] = {"sheet_name": sn_sheet2, "header_map": h, "rows": b}
        _dump(sn_sheet2, h, b, wb[sn_sheet2].max_row)
    if sn_sheet3:
        h, b = parser_llm._sheet_to_payload(
            wb[sn_sheet3],
            header_rows=(3, 4),
            body_start=5,
            row_filter=parser_llm._is_equipment_signal_row,
        )
        payloads["sheet3"] = {"sheet_name": sn_sheet3, "header_map": h, "rows": b}
        _dump(sn_sheet3, h, b, wb[sn_sheet3].max_row)
    if sn_sheet4:
        h, b = parser_llm._sheet_to_payload(wb[sn_sheet4])
        payloads["sheet4"] = {"sheet_name": sn_sheet4, "header_map": h, "rows": b}
        _dump(sn_sheet4, h, b, wb[sn_sheet4].max_row)

    wb.close()
    return payloads


def _signal_idx_sheet2(rows: list[dict]) -> list[int]:
    """시트2 body 에서 cum_t > 0 인 의미있는 row 의 index 목록 (참고용)."""
    out = []
    for i, r in enumerate(rows):
        cum_t = r.get(23) or r.get(11)  # col 23=금일Cum.T, col 11=전일Cum.T fallback
        try:
            if cum_t is not None and float(cum_t) > 0:
                out.append(i)
        except (TypeError, ValueError):
            pass
    return out


async def stage2_llm(payloads: dict, chunk_indices: list[int]) -> dict:
    """Stage 2: 시트2 의 지정 chunk index 들을 LLM 호출 → raw output dump.

    chunk_indices = body_rows 안의 chunk 시작 위치 (chunk_size=15). 예: [0, 500, 1000].
    """
    print("\n" + "=" * 80)
    print("STAGE 2 — payload → LLM raw output (chunk별 1:1 1 row 호출)")
    print("=" * 80)
    sheet2 = payloads.get("sheet2")
    if not sheet2:
        print("  시트2 payload 없음 — skip")
        return {}

    header_map = sheet2["header_map"]
    body_rows = sheet2["rows"]
    chunk_size = 15
    sig_idx = _signal_idx_sheet2(body_rows)
    print(
        f"  body length: {len(body_rows)}, signal (cum_t>0) row count: {len(sig_idx)}"
    )
    print(f"  signal idx first 20: {sig_idx[:20]}")
    print(f"  signal idx last 5:   {sig_idx[-5:]}")

    from openai import AzureOpenAI

    client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    )
    model = os.environ["LLM_MODEL"]

    results = {}
    for start in chunk_indices:
        if start >= len(body_rows):
            print(f"\n  chunk start={start} > body length {len(body_rows)} — skip")
            continue
        chunk = body_rows[start : start + chunk_size]
        print(
            f"\n--- chunk start={start} (rows {start}~{start + len(chunk) - 1}, count={len(chunk)}) ---"
        )
        print("  input row preview (col 2/5/11/23):")
        for r in chunk[:3]:
            print(
                f"    company_or_bp={_short(r.get(2), 15)} job={_short(r.get(5), 15)} cum_y={r.get(11)} cum_t={r.get(23)}"
            )
        try:
            raw = await asyncio.to_thread(
                parser_llm._llm_extract_sync,
                client=client,
                model=model,
                system_prompt=parser_llm._SYS_JOB_ALLOCATIONS,
                user_payload={"header_map": header_map, "rows": chunk},
                response_key="job_allocations_raw",
            )
            results[start] = raw
            print(
                f"  LLM raw output (len={len(raw) if isinstance(raw, list) else type(raw).__name__}):"
            )
            if isinstance(raw, list):
                for i, r in enumerate(raw[:5]):
                    print(f"    [{i}] {json.dumps(r, ensure_ascii=False)[:200]}")
                if len(raw) == 0:
                    print(
                        "    ⚠️  EMPTY LIST — LLM 이 해당 chunk 에서 유효 row 0 개 추출"
                    )
            else:
                print(f"    {raw!r}")
        except Exception as exc:
            print(f"  ❌ LLM 호출 실패: {type(exc).__name__}: {exc}")
            results[start] = {"error": str(exc)}

    return results


def stage3(stage2_results: dict) -> None:
    """Stage 3: LLM raw → parser_post.transform_job_allocations 변환."""
    print("\n" + "=" * 80)
    print(
        "STAGE 3 — LLM raw → parser_post.transform_job_allocations (filter + normalize)"
    )
    print("=" * 80)
    for start, raw in sorted(stage2_results.items()):
        if not isinstance(raw, list):
            print(f"\n  chunk {start}: raw error, skip")
            continue
        print(f"\n--- chunk start={start} ---")
        print(f"  raw count : {len(raw)}")
        transformed = parser_post.transform_job_allocations(raw)
        print(
            f"  after transform : {len(transformed)} (filter_marker_rows + job_type 필수)"
        )
        for i, t in enumerate(transformed[:5]):
            print(f"    [{i}] {json.dumps(t, ensure_ascii=False)[:200]}")
        # 회사명 정규화 영향 dump
        raw_companies = sorted(
            {r.get("company_or_bp") for r in raw if r.get("company_or_bp")}
        )
        trans_companies = sorted({t["company"] for t in transformed if t["company"]})
        print(f"  raw companies      : {raw_companies}")
        print(f"  normalized companies: {trans_companies}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx_path", type=Path)
    ap.add_argument(
        "--llm", action="store_true", help="Stage 2 LLM 호출 활성 (Azure OpenAI)"
    )
    ap.add_argument(
        "--llm-chunks",
        type=str,
        default="0,500,1000",
        help="Stage 2 chunk 시작 인덱스 (comma-separated). default 0,500,1000",
    )
    args = ap.parse_args()

    payloads = stage1(args.xlsx_path)

    if args.llm:
        chunk_indices = [int(x) for x in args.llm_chunks.split(",")]
        results = await stage2_llm(payloads, chunk_indices)
        stage3(results)
    else:
        print("\n  (Stage 2/3 skip — --llm 플래그로 활성)")


if __name__ == "__main__":
    asyncio.run(main())
