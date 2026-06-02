"""CLI 진입점 — python -m pipeline.agents.recipe <xlsx>.

사용법:
    pipeline/.venv/bin/python -m pipeline.agents.recipe <xlsx_path>

출력 (stdout):
    format_class, confidence, generated_by, 4 엔티티 건수

종료 코드:
    0 — 정상
    2 — 인자 없음 (usage 출력)
"""

from __future__ import annotations

import sys

import openpyxl

from pipeline.agents.recipe import parse_with_recipe
from pipeline.agents.recipe.recognize import recognize_format


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m pipeline.agents.recipe <xlsx_path>", file=sys.stderr)
        sys.exit(2)

    path = sys.argv[1]

    wb = openpyxl.load_workbook(path, data_only=True)
    recipe = recognize_format(wb)
    wb.close()

    report = parse_with_recipe(path)

    acts = len(report["activities"])
    bps = len(report["bp_summaries"])
    jobs = len(report["job_allocations"])
    eqs = len(report["equipment_allocations"])

    print(f"format_class : {recipe.format_class}")
    print(f"confidence   : {recipe.confidence}")
    print(f"generated_by : {recipe.generated_by}")
    print(f"activities   : {acts}")
    print(f"bp_summaries : {bps}")
    print(f"job_allocations      : {jobs}")
    print(f"equipment_allocations: {eqs}")


if __name__ == "__main__":
    main()
