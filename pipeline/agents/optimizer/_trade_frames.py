"""trade 프레임 lookup — spec §4.2.2.

data/trade_frames.json → l6_main → (category, frame_text) 매핑.
miss 시 FALLBACK.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

_DATA_PATH = Path(__file__).resolve().parents[3] / "data" / "trade_frames.json"
_DATA = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
FALLBACK = (
    "일반",
    "본 공종은 건축·토목 카테고리 외이므로 일반 공정 관점에서 진단합니다. "
    "단위 생산성 + 계획 진척 + MH 효율 3 차원 균형을 본다.",
)


def lookup_frame(l6_main: Optional[str]) -> Tuple[str, str]:
    """l6_main → (category, frame_text). miss 시 FALLBACK."""
    if not l6_main:
        return FALLBACK
    for cat, meta in _DATA.items():
        if l6_main in meta["wps"]:
            return cat, meta["frame_text"]
    return FALLBACK
