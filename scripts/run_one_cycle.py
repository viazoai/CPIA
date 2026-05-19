"""1 cycle 직접 실행 — rule-based parser + LLM 검증 + graph.ainvoke + HIL auto-resume.

prod entry script. graph 외부에서 parser.parse_daily_report 호출해 state["parsed"] 채운 후
graph.ainvoke. 2026-05-20: parser_llm chunk 4-5 분 → parser_rule + LLM 검증 ~20 초.

사용:
  pipeline/.venv/bin/python3 scripts/run_one_cycle.py <xlsx> <site_id> <report_date>

env:
  CPIA_PARSER_VERIFY_LLM=off  # 시트1/4 LLM 검증 skip (속도 ↑, 비용 0)
  CPIA_SAMPLE=1               # (deprecated) parser_llm 의 sample mode — 현 rule path 무시
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from langgraph.types import Command  # noqa: E402

from pipeline.agents.parser import parse_daily_report  # noqa: E402
from pipeline.api import _build_prod_graph_config  # noqa: E402
from pipeline.graph import build_graph  # noqa: E402


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[run_one {ts}] {msg}", flush=True)


async def main():
    if len(sys.argv) != 4:
        print("usage: run_one_cycle.py <xlsx_path> <site_id> <report_date>")
        sys.exit(1)
    xlsx, site_id, report_date = sys.argv[1], sys.argv[2], sys.argv[3]

    _log(f"start xlsx={xlsx} site={site_id} date={report_date}")

    # Phase A: Parser (rule-based + 시트1/4 LLM 검증, sync — 별 스레드 실행)
    verify_llm = os.environ.get("CPIA_PARSER_VERIFY_LLM", "on").lower()
    _log(
        f"parser.parse_daily_report starting (LLM 검증={verify_llm}, Azure OpenAI 호출 2회)"
    )
    parsed = await asyncio.to_thread(parse_daily_report, xlsx)
    _log(
        f"parser done: bp={len(parsed['bp_summaries'])} "
        f"job={len(parsed['job_allocations'])} "
        f"equip={len(parsed['equipment_allocations'])} "
        f"act={len(parsed['activities'])}"
    )

    # POC 3사 필터 (tmp/run_prod_cycle.py 패턴) — 회사명 비어있는 BP row 제거 →
    # mapper_activities.company NOT NULL constraint 위반 방지.
    POC_KEYWORDS = ("남웅", "세보", "창원기전")

    def _pass(c):
        return bool(c) and any(k in c for k in POC_KEYWORDS)

    parsed["bp_summaries"] = [
        s for s in parsed["bp_summaries"] if _pass(s.get("company"))
    ]
    parsed["activities"] = [a for a in parsed["activities"] if _pass(a.get("company"))]
    parsed["job_allocations"] = [
        j for j in (parsed.get("job_allocations") or []) if _pass(j.get("company"))
    ]
    parsed["equipment_allocations"] = [
        e
        for e in (parsed.get("equipment_allocations") or [])
        if _pass(e.get("company"))
    ]
    _log(
        f"3사 필터 후: bp={len(parsed['bp_summaries'])} act={len(parsed['activities'])} job={len(parsed['job_allocations'])} eq={len(parsed['equipment_allocations'])}"
    )
    if not parsed["activities"]:
        _log("STOP: 3사 필터 후 activities 0 — cycle 진행 불가")
        sys.exit(2)

    # Phase B: Graph
    cfg = _build_prod_graph_config()
    graph = build_graph(cfg)

    run_id = str(uuid.uuid4())
    state = {
        "run_id": run_id,
        "date": report_date,
        "site_id": site_id,
        "input_files": [xlsx],
        "raw_texts": {},
        "parsed": parsed,
        "mapped": [],
        "hil_1_corrections": {},
        "atomized_ids": [],
        "report_md": "",
        "forecast": [],
        "hil_2_selection": [],
        "pre_optimizer_cases": {},
        "optimizer_advice": [],
        "current_node": "",
        "status": "running",
    }

    config = {"configurable": {"thread_id": run_id}}
    _log(f"graph.ainvoke start run_id={run_id}")
    first = await graph.ainvoke(state, config=config)
    _log(f"first done keys={sorted(k for k in first.keys() if not k.startswith('_'))}")

    if "__interrupt__" in first:
        interrupts = first["__interrupt__"]
        rn = (interrupts[0].value or {}).get("review_needed", [])
        _log(f"HIL 1 interrupt — review_needed={len(rn)} (auto-resume with {{}})")
        final = await graph.ainvoke(Command(resume={}), config=config)
    else:
        final = first

    _log(f"final status={final.get('status')} current_node={final.get('current_node')}")
    _log(f"run_id={run_id}")


if __name__ == "__main__":
    asyncio.run(main())
