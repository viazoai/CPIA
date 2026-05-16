"""Parser -> Mapper E2E 실 출력 dump -- spec §9.4.

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")


import openpyxl

from pipeline.agents.mapper import MapperConfig, build_bp_context, map_activity
from pipeline.agents.parser import _ffill, parse_daily_report


GOLDEN_DEFAULTS = "99,452,892,1207,1230"
GOLDEN = {
    99: ("남웅건설", "철근콘크리트공사"),
    452: ("세보엠이씨", "ACID배기설비공사"),
    892: ("창원기전", "전등설비공사"),
    1207: ("세보엠이씨", "기계소화설비"),
    1230: ("창원기전", "전기소화설비"),
}


def _build_row_to_activity(parsed, xlsx_path: Path) -> dict[int, dict]:
    """sheet4 를 한 번 더 read + ffill 해서 row -> activity 매핑.

    test_mapper_golden._match_golden 패턴 — 같은 company 의 row 가 여러 개일 때
    work_content 까지 매칭해서 정확한 activity 잡음. 데모용 한 회 호출.
    """
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    try:
        ws = wb["4.물량"]
        rows = _ffill(list(ws.iter_rows(values_only=True)), header_end=4, fill_cols=[1, 2, 3, 4, 5])
    finally:
        wb.close()

    activity_by_key: dict[tuple[str, str], dict] = {
        (a["company"], a["work_content"]): a for a in parsed["activities"]
    }
    row_to_activity: dict[int, dict] = {}
    for i, r in rows:
        if r[5] and r[7]:
            key = (str(r[5]).strip(), str(r[7]).strip())
            a = activity_by_key.get(key)
            if a is not None:
                row_to_activity.setdefault(i, a)
    return row_to_activity


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
            failures.append(f"C4: equipment_big 비어있음 -- {e}")
            break

    if len(parsed["activities"]) < 79:
        failures.append(f"C5: activities {len(parsed['activities'])} < 79 (골든 누락)")

    passed = 5 - len(failures)
    return passed, failures


async def dump_mapper_samples(
    parsed,
    sample_rows: list[int],
    row_to_activity: dict[int, dict],
    cfg: MapperConfig,
) -> int:
    """Mapper 호출 결과 dump. (build_bp_context fallback 발생 건수) 반환."""
    print("=== Mapper 호출 (sample 5건 -- 시뮬 v3 패턴 복원) ===")
    print()

    fallback_hits = 0
    correct = 0

    for row in sample_rows:
        if row not in GOLDEN:
            print(f"[R{row}] GOLDEN 미정의, skip")
            continue
        golden_company, golden_l6 = GOLDEN[row]
        match = row_to_activity.get(row)
        if not match:
            print(f"[R{row}] {golden_company} 의 Activity 매칭 실패 (sheet4 row 누락)")
            continue

        ctx = build_bp_context(match["company"], parsed)
        if "parsed_report 미제공" in ctx:
            fallback_hits += 1

        result = await map_activity(match, parsed_report=parsed, cfg=cfg)
        ok = result["l6_main"] == golden_l6
        if ok:
            correct += 1

        mark = "OK" if ok else "FAIL"
        print(
            f"[R{row}] {match['company']} / '{match['work_content']}' / {match['unit']} / "
            f"today_qty={match['today_qty']}"
        )
        print(f"  -> 골든:   {golden_l6}")
        print(
            f"  -> 결과:   {result['l6_main']} / conf {result['mapping_conf']} / "
            f"source: {result['mapping_source']} [{mark}]"
        )
        print("  -> BP 컨텍스트 (mapper.build_bp_context):")
        for line in ctx.splitlines():
            print(f"    {line}")
        print()

    print("=== 베이스라인 대비 ===")
    print("baseline (parsed_report=None, 2026-05-15): 78/79 = 98.7%")
    print("v3 패턴 복원 (전체 79건, Task 7 회귀):     77/79 = 97.5% (H-i-L 후 100%)")
    print(f"sample (parsed_report=parsed, {len(sample_rows)}건): {correct}/{len(sample_rows)}")
    print()

    return fallback_hits


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx_path", type=Path)
    ap.add_argument("--sample-rows", default=GOLDEN_DEFAULTS)
    args = ap.parse_args()

    parsed = parse_daily_report(args.xlsx_path)

    dump_parser_output(parsed)

    passed, failures = check_postconditions(parsed)
    print(f"=== 체크포인트 C1~C5 (Parser 단독) -- {passed}/5 통과 ===")
    for f in failures:
        print(f"  X {f}")
    print()

    sample_rows = [int(x) for x in args.sample_rows.split(",")]
    row_to_activity = _build_row_to_activity(parsed, args.xlsx_path)

    cfg = MapperConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
        embedding_model=os.environ["EMBEDDING_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
        chroma_ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )

    fallback_hits = await dump_mapper_samples(parsed, sample_rows, row_to_activity, cfg)
    print(f"=== 체크포인트 C6 -- fallback 메시지 {fallback_hits}건 (목표 0건) ===")
    print()

    parsed2 = parse_daily_report(args.xlsx_path)
    determinism = parsed == parsed2
    mark = "PASS" if determinism else "FAIL"
    print(f"=== 체크포인트 C8 -- 결정성 (2회 호출 동일): {mark} ===")


if __name__ == "__main__":
    asyncio.run(main())
