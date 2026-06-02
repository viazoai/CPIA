from __future__ import annotations
import re

# 기존 _BP_PATTERNS(parser.py:97) 확장: 구분자 [_\- ], 선택적 trailing 영문 1글자.
# 과확장 금지 — 반드시 영숫자 prefix + PH/Ph + 숫자 + 구분자 + 숫자 구조.
_BP_PATTERNS_V2: tuple[re.Pattern[str], ...] = (
    re.compile(r"^PH[_\- ]?X[_\- ]?\d+[A-Za-z]?$"),  # 통합: PH_X-088
    re.compile(r"^[A-Za-z][A-Za-z0-9]*[_\- ][Pp][Hh]\d+[_\- ]\d+[A-Za-z]?$"),  # 업체: M15X_PH4_041 (+변종)
)
_HANGUL_RE = re.compile(r"[가-힣]")
_CODEISH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")  # 공백 없는 영숫자+구분자


def is_bp_code_v2(v: object) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    return any(p.match(s) for p in _BP_PATTERNS_V2)


def looks_like_code_no_korean(v: object) -> bool:
    """한글 0글자 + 코드 모양(공백 없는 영숫자+구분자) → company 로 두면 안 됨.

    외래 코드(ABC-2025-001) 가 _BP_PATTERNS_V2 를 빠져나가 company 로 누출되는 것 차단용.
    공백 포함 영문 회사명(Hyundai E&C)은 코드 모양 아님 → False(정상 회사명).
    """
    if v is None:
        return False
    s = str(v).strip()
    if _HANGUL_RE.search(s):
        return False
    return bool(_CODEISH_RE.match(s)) and any(ch.isdigit() for ch in s)
