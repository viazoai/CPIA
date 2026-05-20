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

    # pipeline_runs row 사전 INSERT — atomizer.assert_pipeline_run_exists 통과 위해
    # (spec §4.4: atomizer 는 INSERT 책임 X, 호출부가 사전 보장)
    from pipeline.db import PGClient

    _pg = PGClient(os.environ["POSTGRES_URL"])
    await _pg.connect()
    try:
        try:
            await _pg.insert_pipeline_run(uuid.UUID(run_id), site_id, report_date)
            _log(f"pipeline_runs INSERT OK run_id={run_id}")
        except Exception as e:  # noqa: BLE001  # 이미 존재 시 conflict — skip
            _log(f"pipeline_runs INSERT skip ({type(e).__name__}: {e})")
    finally:
        await _pg.close()

    _log(f"graph.ainvoke start run_id={run_id}")
    first = await graph.ainvoke(state, config=config)
    _log(f"first done keys={sorted(k for k in first.keys() if not k.startswith('_'))}")

    # 다단 interrupt 처리 — HIL 1 + HIL 2 둘 다 자동 resume
    state_after = first
    for round_idx in range(1, 5):
        if "__interrupt__" not in state_after:
            break
        interrupts = state_after["__interrupt__"]
        intr_val = interrupts[0].value or {}
        rn = intr_val.get("review_needed", [])
        rg = intr_val.get("risky_groups", [])
        # HIL 1 resume = {} (corrections 없음 — AUTO_BYPASS path)
        # HIL 2 resume = risky_groups 의 모든 key (optimizer 가 전부 실행 — UI 검증용)
        if rn:
            resume_value: object = {}
            _log(
                f"interrupt round {round_idx}: HIL 1 review_needed={len(rn)} "
                f"(auto-resume with {{}})"
            )
        elif rg:
            resume_value = [g.get("key") for g in rg if g.get("key")]
            _log(
                f"interrupt round {round_idx}: HIL 2 risky_groups={len(rg)} "
                f"(auto-resume with {len(resume_value)} keys → optimizer 전체 실행)"
            )
        else:
            resume_value = []
            _log(f"interrupt round {round_idx}: unknown payload — resume=[]")
        state_after = await graph.ainvoke(Command(resume=resume_value), config=config)
        _log(
            f"  after resume {round_idx}: keys="
            f"{sorted(k for k in state_after.keys() if not k.startswith('_'))} "
            f"status={state_after.get('status')} current_node={state_after.get('current_node')} "
            f"atomized_ids={len(state_after.get('atomized_ids') or [])} "
            f"forecast={len(state_after.get('forecast') or [])} "
            f"opt={len(state_after.get('optimizer_advice') or [])} "
            f"report_md_len={len(state_after.get('report_md') or '')}"
        )
    final = state_after
    _log(f"final status={final.get('status')} current_node={final.get('current_node')}")
    _log(
        f"atomized_ids={len(final.get('atomized_ids') or [])} forecast={len(final.get('forecast') or [])} opt={len(final.get('optimizer_advice') or [])}"
    )
    _log(f"run_id={run_id}")


if __name__ == "__main__":
    asyncio.run(main())
