"""collector_node — graph 진입 노드. listener 가 박은 input_files[0] 검증 + 메타 분해 (D-12)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pipeline.collector.filename_parser import parse_filename
from pipeline.db import PGClient, update_collector_inbox_status
from pipeline.state import CPIAState

log = logging.getLogger("cpia.collector_node")


async def collector_node(state: CPIAState) -> dict[str, Any]:
    """첨부 경로 검증 + filename_parser → state 메타 박기 + collector_inbox UPDATE.

    선행 (listener): collector_inbox INSERT(parse_status=pending) 완료.
    본 노드 책임 (Spec §6.5):
      1. state.input_files[0] 경로 존재 검증
      2. filename_parser 로 (bp_name, date, project) 분해
      3. message_id 가 state 에 있고 postgres_url 도 있으면 UPDATE(parse_status=running, run_id)
         — CLI 진입 (외부 listener 없이 main.py) 시 message_id absent → UPDATE skip
      4. mapper 가 쓸 메타 dict 반환
    """
    input_files = state.get("input_files") or []
    if not input_files:
        raise RuntimeError("collector_node: state.input_files 비어있음")
    path = Path(input_files[0])
    if not path.exists():
        raise FileNotFoundError(f"collector_node: {path}")
    meta = parse_filename(path.name)
    if meta is None:
        raise ValueError(f"collector_node: 파일명 규약 불일치 {path.name}")

    message_id = state.get("message_id")
    postgres_url = state.get("postgres_url")
    if message_id and postgres_url:
        # PGClient 는 connect()/close() 패턴 (async with 미지원).
        pg = PGClient(postgres_url)
        await pg.connect()
        try:
            await update_collector_inbox_status(
                pg,
                message_id,
                run_id=state["run_id"],
                parse_status="running",
            )
        finally:
            await pg.close()
    log.info(
        "collector_node: %s → bp=%s date=%s project=%s",
        path.name,
        meta.bp_name,
        meta.date,
        meta.project,
    )
    return {
        "bp_name": meta.bp_name or "_integrated",
        "report_date": meta.date,
        "project": meta.project,
    }
