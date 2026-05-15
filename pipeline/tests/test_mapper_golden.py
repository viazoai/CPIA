"""79건 골든 회귀 — mapping-layer.md §9.

시뮬 v3 기준 자동 정확도 >= 95% (CI 안정성), 운영 정확도 (H-i-L 후) = 100%.
실 Azure 호출 필요 (~5분, 비용 ~$0.02/run).
"""

from __future__ import annotations

import os
from pathlib import Path

import openpyxl
import pytest

from pipeline.agents.mapper import MapperConfig, map_activity
from pipeline.agents.parser import parse_daily_report
from pipeline.state import Activity


# 골든 79건 (mapping-layer.md §9.1)
GOLDEN: dict[int, tuple[str, str]] = {}
for _r in range(99, 147):
    if _r != 125:
        GOLDEN[_r] = ("남웅건설", "철근콘크리트공사")
GOLDEN.update(
    {
        452: ("세보엠이씨", "ACID배기설비공사"),
        453: ("세보엠이씨", "VOC설비공사"),
        454: ("세보엠이씨", "CABINET배기설비공사"),
        455: ("세보엠이씨", "ALKALI배기설비공사"),
        457: ("세보엠이씨", "H/G배기설비공사"),
        458: ("세보엠이씨", "비상배기덕트설비공사"),
        459: ("세보엠이씨", "일반공조설비공사"),
        461: ("세보엠이씨", "DCC설비공사"),
        462: ("세보엠이씨", "냉동기설비공사"),
        463: ("세보엠이씨", "냉동기설비공사"),
        465: ("세보엠이씨", "위생배관공사"),
        466: ("세보엠이씨", "NPW배관공사"),
        467: ("세보엠이씨", "H-VAC설비공사"),
        469: ("세보엠이씨", "일반공조설비공사"),
        472: ("세보엠이씨", "ACID배기설비공사"),
        473: ("세보엠이씨", "VOC설비공사"),
        474: ("세보엠이씨", "CABINET배기설비공사"),
        475: ("세보엠이씨", "ALKALI배기설비공사"),
        1207: ("세보엠이씨", "기계소화설비"),
        1208: ("세보엠이씨", "기계소화설비"),
        1209: ("세보엠이씨", "기계소화설비"),
        1210: ("세보엠이씨", "기계소화설비"),
        1211: ("세보엠이씨", "기계소화설비"),
        1212: ("세보엠이씨", "기계소화설비"),
        892: ("창원기전", "전등설비공사"),
        895: ("창원기전", "전등설비공사"),
        898: ("창원기전", "전등설비공사"),
        901: ("창원기전", "전등설비공사"),
        904: ("창원기전", "전등설비공사"),
        906: ("창원기전", "전력간선공사"),
        1230: ("창원기전", "전기소화설비"),
        1231: ("창원기전", "전기소화설비"),
    }
)


def _match_golden(activities: list[Activity], wb_path: Path) -> list[tuple[int, Activity]]:
    """Parser activities → 골든 row 번호 매칭. test_mapper_golden 전용 헬퍼.

    Parser 는 row 번호를 노출하지 않으므로 시트4 를 한 번 더 read + ffill 해서
    (company, work_content) → row index 매핑을 만들고 GOLDEN dict 의 key 와 join.
    """
    from pipeline.agents.parser import _ffill  # 함수 내부 import — 포매터의 unused 제거 우회

    wb = openpyxl.load_workbook(wb_path, data_only=True, read_only=True)
    ws = wb["4.물량"]
    rows = _ffill(list(ws.iter_rows(values_only=True)), header_end=4, fill_cols=[1, 2, 3, 4, 5])
    wb.close()
    row_map: dict[tuple[str, str], int] = {}
    for i, r in rows:
        if r[5] and r[7]:
            key = (str(r[5]).strip(), str(r[7]).strip())
            row_map.setdefault(key, i)

    matched: list[tuple[int, Activity]] = []
    for a in activities:
        row = row_map.get((a["company"], a["work_content"]))
        if row is not None and row in GOLDEN:
            matched.append((row, a))
    return matched


@pytest.mark.slow
@pytest.mark.golden
@pytest.mark.asyncio
async def test_golden_accuracy(sample_tong_path: Path, azure_openai_env):
    """안 A v3 자동 정확도 >= 95% (시뮬 기준 98.7%)."""
    cfg = MapperConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
        embedding_model=os.environ["EMBEDDING_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
    )

    parsed = parse_daily_report(sample_tong_path)
    inputs = _match_golden(parsed["activities"], sample_tong_path)
    assert len(inputs) == 79, f"골든 입력 수 불일치: {len(inputs)}"

    correct = 0
    wrong: list[tuple[int, str, str, str | None, float | None]] = []
    for row, activity in inputs:
        result = await map_activity(activity, parsed_report=parsed, cfg=cfg)
        expected = GOLDEN[row][1]
        if result["l6_main"] == expected:
            correct += 1
        else:
            wrong.append((row, activity["work_content"], expected, result["l6_main"], result["mapping_conf"]))

    pct = correct / len(inputs) * 100
    print(f"\n[golden] 정확도: {correct}/{len(inputs)} = {pct:.1f}%")
    for r_, w, exp, got, conf in wrong:
        print(f"  X R{r_} '{w}' -> 골든={exp} vs 결과={got} (conf {conf})")

    assert pct >= 95.0, f"자동 정확도 95% 미만: {pct:.1f}%"
