"""Collector — 메일 수신 업체별 작업일보 수집 + Parser 전달.

2026-05-19 신규. 기존 0 줄. Prod 흐름:
  업체 N개가 메일로 작업일보 xlsx 첨부 전송
    → Collector 가 메일 (IMAP / Gmail API / Outlook Graph) 에서 첨부 다운로드
    → 임시 dir 에 일자별 저장 (data/input/YYYYMMDD/업체작업일보_*.xlsx)
    → list[Path] 반환 → Parser × N (LLM) → Merge → Mapper → ... → Exporter

본 cycle 구현 범위 = 디렉토리 walk + 병렬 Parser 호출 (stub).
메일 통합 (IMAP/API 폴링 + 첨부 추출) 은 별 cycle 후속.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from pipeline.agents.parser_llm import ParserConfig, parse_daily_report_llm
from pipeline.state import ParsedDailyReport


@dataclass
class CollectorConfig:
    """Collector 동작 환경."""

    parser: ParserConfig
    file_concurrency: int = 4  # 파일 단위 병렬 (각 파일은 내부적으로 6 시트 LLM 호출)


def discover_daily_reports(input_dir: Path | str) -> list[Path]:
    """input_dir 안의 작업일보 xlsx 파일들 — 업체작업일보_*.xlsx 또는 통합작업일보_*.xlsx.

    재귀 탐색 X. 정렬 보장.
    """
    input_dir = Path(input_dir)
    if not input_dir.exists():
        return []
    candidates: list[Path] = []
    for p in sorted(input_dir.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".xlsx", ".xlsm"}:
            continue
        name = p.name
        if name.startswith("~$"):  # 엑셀 lock 파일 skip
            continue
        if "작업일보" in name or "업체작업일보" in name or "통합작업일보" in name:
            candidates.append(p)
    return candidates


async def collect_and_parse(
    input_dir: Path | str,
    cfg: CollectorConfig,
) -> list[ParsedDailyReport]:
    """input_dir 안 N개 xlsx → LLM Parser × N (병렬) → list[ParsedDailyReport].

    Merge 는 별 단계 (parser_node + merge_node 호출 흐름).
    """
    files = discover_daily_reports(input_dir)
    if not files:
        return []

    sem = asyncio.Semaphore(cfg.file_concurrency)

    async def _parse_one(path: Path) -> ParsedDailyReport:
        async with sem:
            return await parse_daily_report_llm(path, cfg.parser)

    return list(await asyncio.gather(*[_parse_one(p) for p in files]))
