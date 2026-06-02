"""parser_node — graph 노드. input_files 전체 비동기 병렬 파싱 + merge (PoC: multi-file 통합)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from pipeline.agents.parser import parse_daily_report  # 내부 변경 0
from pipeline.db import upsert_agent_progress
from pipeline.state import CPIAState, ParsedDailyReport

log = logging.getLogger("cpia.parser_node")

_PARSE_CONCURRENCY = 4  # 파일 단위 병렬 (sync parse 를 to_thread 로 wrap — 이벤트 루프 block 회피)


def _merge_reports(reports: list[ParsedDailyReport]) -> ParsedDailyReport:
    """N개 ParsedDailyReport → 1 통합 (concat). 각 업체 다른 작업 전제.

    activities/bp_summaries/job/equip/worker_outputs 를 단순 이어붙임.
    report_date 는 동일해야 정상 (불일치 시 경고). report_meta 는 첫 업체 것 (site 대표).
    """
    base = reports[0]
    dates = {r["report_date"] for r in reports if r.get("report_date")}
    if len(dates) > 1:
        log.warning("parser_node merge: report_date 불일치 %s", dates)
    return {
        "report_date": base["report_date"],
        "project": base["project"],
        "bp_summaries": [x for r in reports for x in r["bp_summaries"]],
        "job_allocations": [x for r in reports for x in r["job_allocations"]],
        "equipment_allocations": [x for r in reports for x in r["equipment_allocations"]],
        "activities": [x for r in reports for x in r["activities"]],
        "worker_outputs": [x for r in reports for x in r["worker_outputs"]],
        "report_meta": base["report_meta"],
    }


async def parser_node(state: CPIAState) -> dict[str, Any]:
    """input_files 전체를 비동기 병렬 파싱 → merge → 통합 ParsedDailyReport.

    sync parse_daily_report 를 asyncio.to_thread 로 wrap (Semaphore 4) — 이벤트 루프를
    block 하지 않아 mapper~ 진행 중에도 FastAPI 의 다른 요청(게이지 polling 등)이 응답한다.
    mapper 가 state["parsed"] 로 읽음.
    """
    files = [Path(f) for f in state["input_files"]]
    if not files:
        raise RuntimeError("parser_node: input_files 비어있음")
    sem = asyncio.Semaphore(_PARSE_CONCURRENCY)

    # B3 진행도 — run_id/postgres_url 는 exporter 와 동일하게 state 에서 추출.
    run_id = state["run_id"]
    pg_url = state["postgres_url"]
    total = len(files)
    await upsert_agent_progress(pg_url, run_id, "parser", 0, total)

    _done = 0  # plain int — sync 증가 후 local 캡쳐, 그 다음 await upsert (read-modify-write 사이 await X)

    async def _parse_one(p: Path) -> ParsedDailyReport:
        nonlocal _done
        async with sem:
            r = await asyncio.to_thread(parse_daily_report, p)
        _done += 1
        _local = _done
        await upsert_agent_progress(pg_url, run_id, "parser", _local, total)
        return r

    reports = list(await asyncio.gather(*[_parse_one(p) for p in files]))
    merged = _merge_reports(reports)
    log.info(
        "parser_node: %d개 파일 병렬 병합 (bp_summaries=%d, activities=%d)",
        len(files),
        len(merged["bp_summaries"]),
        len(merged["activities"]),
    )
    return {"parsed": merged}
