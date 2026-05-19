"""1 cycle 직접 실행 — parser_llm + graph.ainvoke + HIL auto-resume + stderr 캡쳐.

prod entry script. graph 외부에서 parser_llm 호출해 state["parsed"] 채운 후 graph.ainvoke.

사용:
  pipeline/.venv/bin/python3 scripts/run_one_cycle.py <xlsx> <site_id> <report_date>

stderr 에 parser_llm 의 `[parser_llm] key=... attempt=N EXCEPTION ...` 로그가 그대로 흘러나옴.
파일로 캡쳐하려면: `... 2>/tmp/run_one_cycle.log`
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from langgraph.types import Command  # noqa: E402

from pipeline.agents.parser_llm import ParserConfig, parse_daily_report_llm  # noqa: E402
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

    # Phase A: Parser (LLM)
    parser_cfg = ParserConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
    )
    _log("parser_llm.parse_daily_report_llm starting (Azure OpenAI 호출 다수)")
    parsed = await parse_daily_report_llm(xlsx, parser_cfg)
    _log(
        f"parser done: bp={len(parsed['bp_summaries'])} "
        f"job={len(parsed['job_allocations'])} "
        f"equip={len(parsed['equipment_allocations'])} "
        f"act={len(parsed['activities'])}"
    )

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
