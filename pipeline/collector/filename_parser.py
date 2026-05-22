"""첨부 파일명 정규식 — Spec §6.2.

업체작업일보_<project>_..._<bp>_<trade>_<zone>_<YYMMDD>.xlsx[m]
통합작업일보_<project>_<YYMMDD>.xlsx
미일치 시 None. 호출자가 ext / dead_letter 처리.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional


@dataclass(frozen=True)
class ParsedFilename:
    kind: Literal["bp", "integrated"]
    project: str
    bp_name: Optional[str]
    trade: Optional[str]
    zone: Optional[str]
    date: str  # ISO YYYY-MM-DD


def parse_filename(name: str) -> Optional[ParsedFilename]:
    """첨부 파일명 → ParsedFilename. 미일치 None."""
    stem = Path(name).stem
    if not (stem.startswith("업체작업일보_") or stem.startswith("통합작업일보_")):
        return None
    parts = stem.split("_")
    if len(parts) < 2:
        return None
    raw_date = parts[-1]
    if not raw_date.isdigit():
        return None
    if len(raw_date) == 6:
        date = f"20{raw_date[:2]}-{raw_date[2:4]}-{raw_date[4:6]}"
    elif len(raw_date) == 8:
        date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
    else:
        return None
    if stem.startswith("통합작업일보_"):
        project_tokens = parts[1:-1]
        if not project_tokens:
            return None
        return ParsedFilename(
            kind="integrated",
            project="_".join(project_tokens),
            bp_name=None,
            trade=None,
            zone=None,
            date=date,
        )
    # 업체별: 끝 4 토큰 = bp, trade, zone, date
    if len(parts) < 5:
        return None
    return ParsedFilename(
        kind="bp",
        project="_".join(parts[1:-4]),
        bp_name=parts[-4].strip(),
        trade=parts[-3],
        zone=parts[-2],
        date=date,
    )
