"""건축+토목 한정 업체명 정규화 매핑 자동 추출 -> data/company_normalize.json.

마스터 (activity_master) = canonical / 일보 (mapped_history) = 변형 후보.
정규화 = 공백 제거 + 접미 (㈜·건설·이엔지 등) 제거 + 한글↔영문 수동 매핑.
정규화 후 정확 일치 또는 접두 일치 -> 매핑 제안. 미매칭은 별도 표시.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

import asyncpg

DSN = os.environ.get(
    "POSTGRES_URL",
    "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia",
)
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "company_normalize.json"

TRAILING_SUFFIXES = [
    "주식회사",
    "㈜",
    "(주)",
    "건설화학",
    "글로벌베큠",
    "건설",
    "건업",
    "건영",
    "공사",
    "공업",
    "산업",
    "정공",
    "특수",
    "이엔지",
    "이앤씨",
    "이엔씨",
    "엔지",
    "엔씨",
    "에스앤디",
    "에스엔디",
    "에스앤피",
    "티엔씨",
    "테크노스",
    "테크",
    "코리아",
    "개발",
    "화학",
    "글로벌",
    "이앤지",
]

HANGUL_ENG: dict[str, str] = {
    "오티스": "OTIS",
}

# 사용자 결정 (2026-05-21): 자동 매핑 거부 (false positive)
USER_REJECT: set[str] = {"한국이엔씨", "제일공사"}

# 사용자 결정 (2026-05-21): 알고리즘 누락된 수동 추가
USER_ADD: dict[str, str] = {
    "삼표피앤씨": "삼표 피엔씨",
    "신성이엔지": "신성/케이엔솔",
    "케이엔솔㈜": "신성/케이엔솔",
}


def slash_first(name: str) -> str:
    """슬래시 a/b -> a 통일 (사용자 결정 13번)."""
    if "/" in name:
        return name.split("/")[0].strip()
    return name


def normalize(name: str) -> str:
    s = name.strip()
    if s in HANGUL_ENG:
        return HANGUL_ENG[s]
    s = re.sub(r"\s+", "", s)
    # 긴 접미부터 반복 제거
    changed = True
    while changed:
        changed = False
        for sfx in sorted(TRAILING_SUFFIXES, key=len, reverse=True):
            if s.endswith(sfx) and len(s) > len(sfx) + 1:
                s = s[: -len(sfx)]
                changed = True
                break
    return s


async def main() -> None:
    conn = await asyncpg.connect(DSN)
    try:
        rows = await conn.fetch(
            "SELECT DISTINCT company FROM activity_master "
            "WHERE l5_disc IN ('건축','토목') AND company IS NOT NULL "
            "ORDER BY company"
        )
        masters = sorted(r["company"] for r in rows)

        rows = await conn.fetch(
            "SELECT DISTINCT company FROM mapped_history "
            "WHERE l6_main IN (SELECT DISTINCT l6_main FROM activity_master "
            "WHERE l5_disc IN ('건축','토목')) "
            "AND company IS NOT NULL "
            "ORDER BY company"
        )
        mapped = sorted(r["company"] for r in rows)

        master_norm: dict[str, str] = {}
        for m in masters:
            master_norm.setdefault(normalize(m), m)

        mapping: dict[str, str | None] = {}
        reason: dict[str, str] = {}
        for v in mapped:
            # 사용자 거부 (false positive)
            if v in USER_REJECT:
                mapping[v] = None
                reason[v] = "user-reject"
                continue
            # 사용자 수동 추가
            if v in USER_ADD:
                mapping[v] = USER_ADD[v]
                reason[v] = f"user-add: -> '{USER_ADD[v]}'"
                continue
            if v in masters:
                mapping[v] = v
                reason[v] = "exact"
                continue
            nv = normalize(v)
            if nv in master_norm:
                mapping[v] = master_norm[nv]
                reason[v] = f"normalized: '{v}' -> '{nv}'"
                continue
            # mapped 가 master 시작으로 시작 (예: 광건티엔씨 -> 광건)
            cand_starts = sorted(
                [m for m in masters if v.startswith(m) and len(v) > len(m) + 1],
                key=len,
                reverse=True,
            )
            if cand_starts:
                mapping[v] = cand_starts[0]
                reason[v] = f"startswith: '{v}' starts with '{cand_starts[0]}'"
                continue
            # master 가 mapped 시작으로 시작 (예: 마스터=장평건설, mapped=장평)
            cand_substr = sorted(
                [m for m in masters if m.startswith(v) and len(m) > len(v) + 1],
                key=len,
            )
            if cand_substr:
                mapping[v] = cand_substr[0]
                reason[v] = f"reverse-startswith: '{cand_substr[0]}' starts with '{v}'"
                continue
            mapping[v] = None
            reason[v] = "unmatched"

        # 슬래시 통일 (a/b -> a) — canonical 출력에 적용
        # 결정 13번: 마스터 "신성/케이엔솔" -> "신성", "태우/광건" -> "태우"
        for v in list(mapping):
            if mapping[v]:
                mapping[v] = slash_first(mapping[v])

        out = {
            "generated_at": "2026-05-21",
            "scope": "건축+토목 한정",
            "master_count": len(masters),
            "mapped_count": len(mapped),
            "matched_exact": sorted(v for v, r in reason.items() if r == "exact"),
            "matched_fuzzy": {
                v: {"canonical": mapping[v], "reason": reason[v]}
                for v in sorted(mapping)
                if mapping[v] is not None and reason[v] != "exact"
            },
            "unmatched": sorted(v for v, m in mapping.items() if m is None),
            "masters_unused": sorted(
                m
                for m in masters
                if m not in {mapping[v] for v in mapping if mapping[v]}
            ),
        }
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(
            json.dumps(out, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"WROTE {OUT_PATH}")
        print(
            f"masters={len(masters)} mapped={len(mapped)} "
            f"matched_exact={len(out['matched_exact'])} "
            f"matched_fuzzy={len(out['matched_fuzzy'])} "
            f"unmatched={len(out['unmatched'])} "
            f"masters_unused={len(out['masters_unused'])}"
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
