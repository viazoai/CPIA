"""parser_node — graph 노드. 기존 parse_daily_report 의 1-줄 래퍼 (D-12)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pipeline.agents.parser import parse_daily_report  # 내부 변경 0
from pipeline.state import CPIAState

log = logging.getLogger("cpia.parser_node")


def parser_node(state: CPIAState) -> dict[str, Any]:
    """1 첨부 = 1 ParsedDailyReport (D-3 유지). mapper 가 state["parsed"] 로 읽음."""
    path = Path(state["input_files"][0])
    report = parse_daily_report(path)
    log.info(
        "parser_node: %s 파싱 완료 (bp_summaries=%d, activities=%d)",
        path.name,
        len(report["bp_summaries"]),
        len(report["activities"]),
    )
    return {"parsed": report}
