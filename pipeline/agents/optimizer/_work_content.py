"""work_content bank + condition→prod factor 공유 모듈.

seed_dummy_year (데이터 생성) + view_builder (similar_cases 조립) 가 공유한다.

- CONDITION_PROD_FACTOR: condition → 정상 대비 생산성 배율 범위 (저하/회복 패턴 실재화).
  현재 seed 는 condition 과 prod 가 독립 생성되어 저하/회복 패턴이 없었다 (모든 wp ~90%).
  이 매핑으로 condition 이 prod 를 실제 저하시켜 "저하 → 회복" 시계열이 생긴다.
- WORK_CONTENT_BANK: (frame_category, condition) → {저하, 회복} narrative.
  frame_category 는 _trade_frames.lookup_frame 의 결과 (골조/마감/외장/승강기/토공·흙막이/포장/일반).
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

_BANK_PATH = Path(__file__).resolve().parents[3] / "data" / "work_content_bank.json"
_BANK = json.loads(_BANK_PATH.read_text(encoding="utf-8"))

# condition → (min, max) 정상 대비 생산성 배율. prod_pct = 100 * factor.
# 저하 condition: factor < 0.85 (DEGRADE_CUT). 회복/정상: factor >= 0.95 (RECOVER_CUT).
# 돌관·야간연장: 추가 투입으로 prod 가 오히려 상승하거나 정상 유지.
CONDITION_PROD_FACTOR: dict[str, tuple[float, float]] = {
    "정상": (0.85, 0.98),
    "인력부족": (0.55, 0.68),
    "자재미입고": (0.45, 0.60),
    "장비대기": (0.50, 0.65),
    "우천": (0.55, 0.70),
    "병행작업": (0.72, 0.84),
    "사양변경": (0.62, 0.78),
    "재작업": (0.58, 0.72),
    "돌관": (1.02, 1.15),
    "야간연장": (0.98, 1.10),
}
DEGRADE_CUT = 0.85  # 정상 대비 85% 미만 = 저하 (degradation case)
RECOVER_CUT = 0.95  # 95% 이상 = 회복

_DEGRADE_FALLBACK = "조건 저하로 가용 구간만 부분 진행"
_RECOVERY_FALLBACK = "조건 해소 후 정상 페이스로 회복"


def _seeded_rng(seed_str: str) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256(seed_str.encode("utf-8")).digest()[:8], "big"))


def factor_for(condition: str, seed_str: str) -> float:
    """condition → 정상 대비 생산성 배율 (결정성 — seed_str 기반)."""
    lo, hi = CONDITION_PROD_FACTOR.get(condition, (0.85, 0.98))
    return lo + _seeded_rng(seed_str).random() * (hi - lo)


def is_degraded(condition: str, factor: float | None = None) -> bool:
    """저하 여부. factor 주어지면 factor 기준, 아니면 condition 의 평균 factor."""
    if factor is not None:
        return factor < DEGRADE_CUT
    lo, hi = CONDITION_PROD_FACTOR.get(condition, (0.85, 0.98))
    return (lo + hi) / 2 < DEGRADE_CUT


def work_content_for(frame_category: str, condition: str, kind: str) -> str:
    """(frame, condition, kind='저하'|'회복') → narrative. miss 시 fallback."""
    cond = (condition or "정상").split(",")[0].strip() or "정상"
    frame = _BANK.get(frame_category) or _BANK.get("일반", {})
    pair = frame.get(cond)
    if pair and kind in pair:
        return pair[kind]
    return _DEGRADE_FALLBACK if kind == "저하" else _RECOVERY_FALLBACK
